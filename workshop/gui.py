"""Qt desktop workbench, independent of the lyric player's code."""
from __future__ import annotations

import ctypes
import hashlib
import json
import os
import queue
import subprocess
import sys
import time
from functools import cmp_to_key
from pathlib import Path

from PySide6.QtCore import Qt, QLibraryInfo, QSignalBlocker, QTimer, QTranslator, QCollator, QLocale, QSize, QItemSelectionModel
from PySide6.QtGui import QIcon, QTextCursor
from PySide6.QtWidgets import (QApplication, QDialog, QDialogButtonBox, QFileDialog,
    QMainWindow, QMessageBox, QListWidgetItem, QTreeWidgetItem, QVBoxLayout, QLineEdit, QPushButton, QTextBrowser)

from tools import convert_dpl_playlist, prepare_music
from .core import (Job, Settings, atomic_text, decode_text, create_job,
    filename, import_jobs, library_path, load_jobs, read_text,
    save_jobs, save_library_text, save_lyric_document, scan_audio_library, delete_playlist_file, shift_lrc, validate_lrc)
from .audio import AudioPreview
from .tool_setup import TOOLS, find_tool
from .help_page import HELP_HTML
from .runner import NAMES, Runner
from .shared_settings import settings_file
from .runtime import application_root, tool_command
from .version import PRODUCT_VERSION
from .qt_ui import LANGUAGES, PROCESSING_FIELDS, PROCESSING_ACTIVE_ROLE, PROCESSING_EXISTING_ROLE, WorkshopUi
from .playlists import PlaylistEntry, inspect_playlist, read_entries, write_entries
from . import theme


class WorkshopApp(QMainWindow, WorkshopUi):
    def __init__(self, base: Path):
        super().__init__()
        self.base = base.resolve()
        self.settings = Settings.load(self.base)
        self.jobs = load_jobs(Path(self.settings.work))
        self.songs, self.warnings = [], []
        self.editing_song, self.lyric_target = None, None
        self.lyric_baseline, self.lyric_snapshot = "", None
        self.dirty, self.loading, self.closing, self.ready_to_close = False, False, False, False
        self.playlist_baseline = ""
        self.playlist_baseline_name = ""
        self.playlist_target_name = ""
        self.playlist_items = {}
        self.playlist_entries, self.playlist_comments = [], []
        self.playlist_unparsed_lines, self.playlist_issues = [], []
        self.task_rows = {}
        self.library_rows = {}
        self.processing_rows = {}
        self.collator = QCollator(QLocale("zh_CN"))
        self.collator.setNumericMode(True)
        self.collator.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.processing_references = {}
        self.processing_reference_dialogs = {}
        self.tool_processes = []
        self.tool_poll_at, self.tool_config_stamp = 0, None
        self.preview = AudioPreview()
        self.preview_timer = QTimer(self)
        self.preview_timer.setInterval(150)
        self.preview_timer.timeout.connect(self.poll_preview)
        self.events = queue.Queue()
        self.setWindowTitle("On Screen Music · 音乐管理")
        self.resize(1220, 800)
        self.setMinimumSize(1000, 700)
        self.setWindowIcon(QIcon(str(Path(__file__).with_name("icons") / "workshop.svg")))
        theme.apply_theme(self, self.settings.theme)
        self.build_shell()
        self.build_library()
        self.build_lyric_editor()
        self.build_import()
        self.build_playlists()
        self.build_tasks()
        self.build_settings()
        self.import_tree.itemChanged.connect(lambda item, column: self.guard(lambda: self.processing_step_changed(item, column)))
        self.import_tree.itemSelectionChanged.connect(lambda: self.guard(self.update_processing_controls))
        self.import_tree.currentItemChanged.connect(lambda *_: self.guard(self.update_processing_controls))
        self.search.textChanged.connect(self.refresh_song_list)
        self.editor.textChanged.connect(self.modified)
        self.playlist_combo.activated.connect(lambda _: self.guard(self.load_playlist))
        self.scan()
        self.render_playlist()
        self.refresh_jobs()
        self.show_page("library")
        # Worker construction follows UI initialization to avoid orphan threads on startup errors.
        self.runner = Runner(self.base, self.events)
        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(100)
        self.poll_timer.timeout.connect(lambda: self.guard(self.poll))
        self.poll_timer.start()

    def guard(self, callback):
        try:
            return callback()
        except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
            message = str(exc)
            if self.settings.api_key:
                message = message.replace(self.settings.api_key, "[密钥已隐藏]")
            QMessageBox.critical(self, "音乐管理", message)
            return None

    def confirm(self, title, text):
        return QMessageBox.question(self, title, text,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes

    @staticmethod
    def job_active(job):
        return job.task_state in {"queued", "running", "cancelling"}

    def prompt_dirty(self):
        if not self.dirty:
            return True
        choice = QMessageBox.question(self, "未保存的歌词", "是否保存对当前歌词文件的修改？",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save)
        if choice == QMessageBox.StandardButton.Cancel:
            return False
        if choice == QMessageBox.StandardButton.Save:
            self.save_lyrics()
        self.dirty = False
        return True

    def show_page(self, page, prompt=True):
        self.content.setCurrentWidget(self.frames[page])
        self.page = page
        for name, button in self.nav_buttons.items():
            button.setChecked(name == page)

    def modified(self):
        if not self.loading:
            self.dirty = self.get(self.editor) != self.lyric_baseline
            self.update_lyric_controls()

    def scan(self):
        try:
            self.songs, self.warnings = scan_audio_library(Path(self.settings.library)), []
            self.songs.sort(key=cmp_to_key(lambda a, b: self.collator.compare(a.audio.stem, b.audio.stem)))
        except ValueError as exc:
            self.songs, self.warnings = [], [str(exc)]
        self.library_root_label.setText(self.settings.library)
        self.refresh_song_list(rebuild=True)
        self.refresh_song_choices()
        names = [p.name for p in sorted((Path(self.settings.library) / "playlists").glob("*.txt"))]
        text = self.playlist_combo.currentText()
        with QSignalBlocker(self.playlist_combo):
            self.playlist_combo.clear()
            self.playlist_combo.addItems(names)
            self.playlist_combo.setCurrentText(text)
        self.status.setText(f"资料库 {len(self.songs)} 首。" if self.songs
            else "资料库暂无歌曲。")

    def refresh_song_list(self, *_, rebuild=False):
        selected = self.tree_ids(self.song_tree)
        scroll = self.song_tree.verticalScrollBar()
        position = scroll.value()
        with QSignalBlocker(self.song_tree):
            self.song_tree.setUpdatesEnabled(False)
            try:
                if rebuild:
                    self.song_tree.clear()
                    self.library_rows = {}
                    for song in self.songs:
                        item = QTreeWidgetItem([song.audio.stem, ""])
                        item.setSizeHint(0, QSize(0, 40))
                        item.setData(0, Qt.ItemDataRole.UserRole, song.name)
                        item.setToolTip(0, str(song.audio))
                        self.song_tree.addTopLevelItem(item)
                        self.library_rows[song.name] = item
                        edit = QPushButton("编辑歌词")
                        edit.setObjectName("compactButton")
                        edit.setFixedHeight(30)
                        edit.setCursor(Qt.CursorShape.PointingHandCursor)
                        edit.clicked.connect(lambda _, s=song: self.guard(lambda: self.open_song_editor(s)))
                        self.song_tree.setItemWidget(item, 1, edit)
                query = self.search.text().casefold()
                visible = 0
                for song in self.songs:
                    matches = query in song.name.casefold()
                    self.library_rows[song.name].setHidden(not matches)
                    visible += bool(matches)
                self.select_ids(self.song_tree, selected)
                self.song_tree.doItemsLayout()
                scroll.setValue(position)
                self.library_summary.setText(f"共 {len(self.songs)} 首歌曲 · 显示 {visible} 首")
            finally:
                self.song_tree.setUpdatesEnabled(True)

    def selected_songs(self):
        names = self.tree_ids(self.song_tree)
        return [song for song in self.songs if song.name in names and not self.library_rows[song.name].isHidden()]

    def open_song_editor(self, song):
        if self.lyric_dialog.isVisible() and self.editing_song and self.editing_song.name == song.name:
            self.lyric_dialog.raise_()
            self.lyric_dialog.activateWindow()
            return
        if not self.prompt_dirty():
            return
        name = song.lyric.name if song.lyric else song.audio.stem + ".lrc"
        target = library_path(Path(self.settings.library), "lyrics", name)
        snapshot = target.read_bytes() if target.exists() else None
        text = decode_text(snapshot, name) if snapshot is not None else ""
        self.editing_song, self.lyric_target, self.lyric_snapshot = song, target, snapshot
        self.loading = True
        self.put(self.editor, text)
        self.lyric_baseline = self.get(self.editor)
        self.song_title.setText(song.audio.stem)
        self.lyric_file_label.setText(name)
        self.lyric_dialog.setWindowTitle("编辑歌词 · " + song.audio.stem)
        self.loading, self.dirty = False, False
        self.update_lyric_controls()
        self.start_preview(song.audio)
        self.lyric_dialog.open()

    def update_lyric_controls(self):
        self.editor.setReadOnly(self.editing_song is None)
        self.lyric_save_button.setEnabled(self.editing_song is not None and self.dirty)

    def ensure_idle_job(self, job):
        if self.job_active(job):
            raise ValueError("这首歌正在排队或处理中，请完成后再修改其工作结果。")

    def persist(self):
        save_jobs(Path(self.settings.work), self.jobs)
        self.refresh_jobs()

    def refresh_jobs(self):
        processing = [job for job in self.jobs if job.in_processing]
        current_ids = {job.id for job in processing}
        scroll = self.import_tree.verticalScrollBar()
        position = scroll.value()
        with QSignalBlocker(self.import_tree):
            self.import_tree.setUpdatesEnabled(False)
            try:
                removed_rows = []
                for job_id in list(self.processing_rows):
                    if job_id not in current_ids:
                        item = self.processing_rows.pop(job_id)
                        removed_rows.append(self.import_tree.indexOfTopLevelItem(item))
                # Remove adjacent rows together so bulk clearing triggers only one layout per range.
                ranges = []
                for index in sorted(removed_rows):
                    if ranges and index == ranges[-1][0] + ranges[-1][1]:
                        ranges[-1][1] += 1
                    else:
                        ranges.append([index, 1])
                for index, count in reversed(ranges):
                    self.import_tree.model().removeRows(index, count)
                for job in processing:
                    item = self.processing_rows.get(job.id)
                    if item is None:
                        item = QTreeWidgetItem()
                        item.setSizeHint(0, QSize(0, 36))
                        item.setData(0, Qt.ItemDataRole.UserRole, job.id)
                        item.setToolTip(0, job.source)
                        self.import_tree.addTopLevelItem(item)
                        self.processing_rows[job.id] = item
                        remove = QPushButton("×")
                        remove.setObjectName("rowAction")
                        remove.setMinimumSize(28, 28)
                        remove.setMaximumSize(32, 36)
                        remove.setCursor(Qt.CursorShape.PointingHandCursor)
                        remove.clicked.connect(lambda _, j=job: self.guard(lambda: self.remove_processing_jobs([j])))
                        self.import_tree.setItemWidget(item, 7, remove)
                        reference = QPushButton()
                        reference.setObjectName("compactButton")
                        reference.setMaximumHeight(30)
                        reference.setCursor(Qt.CursorShape.PointingHandCursor)
                        reference.clicked.connect(lambda _, j=job: self.guard(lambda: self.edit_processing_reference(j)))
                        self.import_tree.setItemWidget(item, 5, reference)
                    active = self.job_active(job)
                    item.setData(0, PROCESSING_ACTIVE_ROLE, active)
                    item.setData(0, PROCESSING_EXISTING_ROLE, job.existing_song)
                    if item.text(0) != job.stem:
                        item.setText(0, job.stem)
                    item.setToolTip(0, ("现有歌曲" if job.existing_song else "新文件") + "\n" + job.source)
                    for column, field in PROCESSING_FIELDS.items():
                        checked = bool(getattr(job, field)) and not (column == 1 and job.existing_song)
                        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
                        if item.checkState(column) != state or item.data(column, Qt.ItemDataRole.CheckStateRole) is None:
                            item.setCheckState(column, state)
                        hint = self.import_tree.headerItem().toolTip(column)
                        item.setToolTip(column, "处理中，暂不能修改。" if active else hint)
                    reference = self.import_tree.itemWidget(item, 5)
                    reference.setText("已填写" if self.processing_reference_text(job).strip() else "填写")
                    reference.setEnabled(not active)
                    reference.setToolTip("编辑这首歌的 AI 参考歌词。")
                    state = {"draft": "待处理", "queued": "已排队", "running": "处理中", "cancelling": "正在终止",
                             "succeeded": "已完成", "failed": "失败", "cancelled": "已终止"}.get(job.task_state, job.task_state)
                    if item.text(6) != state:
                        item.setText(6, state)
                    item.setToolTip(6, job.message or f"音频：{job.audio_status}\n歌词：{job.lyric_status}\nAI：{job.ai_status}")
                    remove = self.import_tree.itemWidget(item, 7)
                    remove.setEnabled(not active)
                    remove.setToolTip("处理中，请先在任务记录终止任务。" if active else "从处理列表移除，不删除歌曲或处理结果。")
                self.import_tree.doItemsLayout()
                scroll.setValue(position)
            finally:
                self.import_tree.setUpdatesEnabled(True)
        self.remove_all_processing_button.setEnabled(any(not self.job_active(job) for job in processing))
        self.update_processing_controls()
        tasks = [job for job in self.jobs if job.task_state != "draft"]
        current_ids = {job.id for job in tasks}
        for job_id in list(self.task_rows):
            if job_id not in current_ids:
                item, *_ = self.task_rows.pop(job_id)
                self.task_list.takeItem(self.task_list.row(item))
        for job in tasks:
            if job.id not in self.task_rows:
                item = QListWidgetItem()
                item.setSizeHint(QSize(0, 86))
                self.task_list.insertItem(0, item)
                parts = self.make_task_row(job)
                self.task_list.setItemWidget(item, parts[0])
                self.task_rows[job.id] = (item, *parts[1:])
            _, description, stage, progress, action = self.task_rows[job.id]
            active = self.job_active(job)
            action.setText("×" if active else "⌫")
            action.setToolTip("终止这个任务" if active else "删除这个任务记录")
            action.setEnabled(job.task_state != "cancelling")
            count = max(len(job.stages), 1)
            progress.setRange(0, 0 if job.task_state == "running" and count == 1 else 100)
            progress.setValue(100 if job.task_state == "succeeded" else min(100, round(job.completed_stages * 100 / count)))
            if job.task_state == "queued":
                description.setText("等待处理")
                stage.setText("已排队")
            elif job.task_state == "running":
                description.setText("正在处理")
                index = job.stages.index(job.current_stage) + 1 if job.current_stage in job.stages else 1
                stage.setText(f"{NAMES.get(job.current_stage, '准备中')} · {index}/{count}")
            elif job.task_state == "cancelling":
                description.setText("正在终止…")
                stage.setText("停止中")
            elif job.task_state == "failed":
                reason = " ".join(job.message.split())
                description.setText("失败 · " + (reason[:72] + "…" if len(reason) > 72 else reason))
                description.setToolTip(job.message)
                stage.setText("处理失败")
            elif job.task_state == "cancelled":
                description.setText("已终止，未采用或导出结果")
                stage.setText("已终止")
            else:
                description.setText("完成 · " + ("歌词已更新" if job.message == "处理完成，歌词已更新" else "结果已保存到工作目录"))
                stage.setText("已完成")
        active_count = sum(self.job_active(job) for job in tasks)
        self.task_summary.setText(f"{len(tasks)} 个任务 · {active_count} 个进行中" if tasks else "暂无任务")

    def task_action(self, job):
        if self.job_active(job):
            if self.confirm("终止任务", f"终止“{job.stem}”的处理？\n未完成的结果不会采用或导出，其他任务继续。"):
                self.runner.cancel(job.id)
                self.refresh_jobs()
            return
        self.jobs = [item for item in self.jobs if item.id != job.id]
        self.processing_references.pop(job.id, None)
        self.persist()
        self.status.setText("任务记录已删除。")

    def save_lyrics(self):
        if self.lyric_target is None:
            raise ValueError("请先打开一首歌曲的歌词。")
        if not self.dirty:
            return
        text = self.get(self.editor)
        save_lyric_document(self.settings, self.lyric_target.name, text, self.lyric_snapshot)
        self.lyric_baseline, self.lyric_snapshot = text, text.encode("utf-8")
        self.modified()
        self.scan()
        self.status.setText("歌词已保存。播放器点击“刷新”即可读取。")

    def offset_lyrics(self):
        text = shift_lrc(self.get(self.editor), float(self.offset.value()))
        self.replace_lyric_text(text)

    def mark_instrumental(self):
        self.replace_lyric_text("#INSTRUMENTAL\n")

    def replace_lyric_text(self, text):
        cursor = self.editor.textCursor()
        cursor.beginEditBlock()
        cursor.select(QTextCursor.SelectionType.Document)
        cursor.insertText(text)
        cursor.endEditBlock()
        self.editor.setTextCursor(cursor)

    @staticmethod
    def preview_time_text(milliseconds):
        seconds = max(0, int(milliseconds) // 1000)
        hours, seconds = divmod(seconds, 3600)
        minutes, seconds = divmod(seconds, 60)
        return f"{hours}:{minutes:02}:{seconds:02}" if hours else f"{minutes:02}:{seconds:02}"

    def start_preview(self, path):
        self.stop_preview()
        self.preview_message.hide()
        try:
            self.preview.load(path)
            with QSignalBlocker(self.preview_slider):
                self.preview_slider.setRange(0, min(self.preview.duration, 2147483647))
            self.preview_slider.setEnabled(self.preview.duration > 0)
            self.preview_play_button.setEnabled(True)
            self.poll_preview()
            self.preview_timer.start()
        except (OSError, ValueError) as exc:
            self.preview_failed(exc)

    def stop_preview(self):
        self.preview_timer.stop()
        self.preview.close()
        with QSignalBlocker(self.preview_slider):
            self.preview_slider.setSliderDown(False)
            self.preview_slider.setRange(0, 0)
        self.preview_slider.setEnabled(False)
        self.preview_play_button.setEnabled(False)
        self.preview_play_button.setText("播放")
        self.preview_time.setText("00:00 / 00:00")

    def preview_failed(self, error):
        self.stop_preview()
        self.preview_message.setText("无法试听：" + str(error))
        self.preview_message.show()

    def toggle_preview(self):
        if not self.preview.loaded:
            return
        try:
            self.preview.pause() if self.preview.playing() else self.preview.play()
            self.poll_preview()
        except (OSError, ValueError) as exc:
            self.preview_failed(exc)

    def seek_preview(self, value):
        self.preview_time.setText(self.preview_time_text(value) + " / " + self.preview_time_text(self.preview.duration))
        if self.preview.loaded and not self.preview_slider.isSliderDown():
            try:
                self.preview.seek(value)
                self.poll_preview()
            except (OSError, ValueError) as exc:
                self.preview_failed(exc)

    def poll_preview(self):
        if not self.preview.loaded:
            return
        try:
            position = self.preview.position()
            if not self.preview_slider.isSliderDown():
                with QSignalBlocker(self.preview_slider):
                    self.preview_slider.setValue(position)
                self.preview_time.setText(self.preview_time_text(position) + " / " + self.preview_time_text(self.preview.duration))
            self.preview_play_button.setText("暂停" if self.preview.playing() else "播放")
        except (OSError, ValueError) as exc:
            self.preview_failed(exc)

    def show_text(self, title, text):
        window = QDialog(self)
        window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        window.setWindowTitle(title)
        window.resize(800, 480)
        layout = QVBoxLayout(window)
        widget = self.make_text(True)
        self.put(widget, text, True)
        layout.addWidget(widget)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(window.close)
        layout.addWidget(buttons)
        window.show()
        return window

    def add_sources(self, directory):
        self.settings.validate()
        if directory:
            selected = QFileDialog.getExistingDirectory(self, "选择原始素材目录")
            if not selected:
                return
            folder = Path(selected).resolve()
            if Path(self.settings.work).resolve().is_relative_to(folder):
                raise ValueError("素材目录包含工作目录，请选择独立的原始素材目录。")
            sources = [track.source for track in prepare_music.discover_tracks(folder)]
        else:
            selected, _ = QFileDialog.getOpenFileNames(self, "选择音频或视频", "", "媒体 (*.mp3 *.wav *.flac *.m4a *.aac *.ogg *.opus *.wma *.mp4 *.flv *.mkv *.mov *.webm);;所有文件 (*)")
            sources = [Path(name) for name in selected]
        if not sources:
            return
        known = {str(song.audio.resolve()).casefold(): song for song in self.songs}
        existing = [known[str(source.resolve()).casefold()] for source in sources if str(source.resolve()).casefold() in known]
        external = [source for source in sources if str(source.resolve()).casefold() not in known]
        created = import_jobs(self.settings, external, self.jobs)
        self.jobs.extend(created)
        created.extend(self.add_existing_songs(existing, select=False))
        self.persist()
        self.select_processing_jobs([job.id for job in created])
        self.status.setText(f"已添加 {len(created)} 个素材。点击“开始所选处理”。")

    def select_processing_jobs(self, ids):
        with QSignalBlocker(self.import_tree):
            self.select_ids(self.import_tree, ids)
            for index in range(self.import_tree.topLevelItemCount()):
                item = self.import_tree.topLevelItem(index)
                if ids and item.data(0, Qt.ItemDataRole.UserRole) == ids[0]:
                    self.import_tree.setCurrentItem(item, 0, QItemSelectionModel.SelectionFlag.NoUpdate)
                    break
        self.update_processing_controls()

    def choose_existing_songs(self):
        dialog = QDialog(self)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.setWindowTitle("选择现有歌曲")
        dialog.setModal(True)
        dialog.resize(620, 500)
        box = QVBoxLayout(dialog)
        search = QLineEdit()
        search.setPlaceholderText("搜索歌名，可按 Ctrl 多选…")
        box.addWidget(search)
        tree = self.make_tree(["歌曲", "歌词"])
        box.addWidget(tree, 1)
        for song in self.songs:
            state = "已有歌词" if song.lyric and song.lyric.is_file() else "无歌词"
            item = QTreeWidgetItem([song.audio.stem, state])
            item.setData(0, Qt.ItemDataRole.UserRole, song.name)
            tree.addTopLevelItem(item)
        def filter_songs(text):
            for index in range(tree.topLevelItemCount()):
                item = tree.topLevelItem(index)
                item.setHidden(text.casefold() not in item.text(0).casefold())
        search.textChanged.connect(filter_songs)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("添加所选歌曲")
        box.addWidget(buttons)
        def accept():
            names = set(self.tree_ids(tree))
            if not names:
                raise ValueError("请选择至少一首歌曲。")
            self.add_existing_songs([song for song in self.songs if song.name in names])
            dialog.accept()
        buttons.accepted.connect(lambda: self.guard(accept))
        buttons.rejected.connect(dialog.reject)
        dialog.show()
        return dialog

    def add_existing_songs(self, songs, select=True):
        added = []
        for song in songs:
            source = str(song.audio.resolve())
            job = next((job for job in self.jobs if job.in_processing and job.existing_song
                        and job.source.casefold() == source.casefold()), None)
            if job is None:
                job = create_job(self.settings, song.audio, song.audio.stem, song)
                job.in_processing = True
                job.lyric_status = "已有歌词" if song.lyric and song.lyric.is_file() else "未处理"
                self.jobs.append(job)
            added.append(job)
        if select:
            self.persist()
            self.select_processing_jobs([job.id for job in added])
            self.status.setText(f"已选择 {len(added)} 首现有歌曲，音频无需转换。")
        return added

    def processing_step_changed(self, item, column):
        field = PROCESSING_FIELDS.get(column)
        job_id = item.data(0, Qt.ItemDataRole.UserRole)
        job = next((job for job in self.jobs if job.id == job_id), None)
        if field is None or job is None:
            return
        if self.job_active(job) or (column == 1 and job.existing_song) or (column == 4 and not job.process_recognize):
            self.refresh_jobs()
            return
        previous = getattr(job, field)
        setattr(job, field, item.checkState(column) == Qt.CheckState.Checked)
        try:
            save_jobs(Path(self.settings.work), self.jobs)
        except (OSError, ValueError):
            setattr(job, field, previous)
            self.refresh_jobs()
            raise
        self.refresh_jobs()

    def processing_reference_text(self, job):
        if job.id not in self.processing_references:
            path = job.path("reference")
            self.processing_references[job.id] = read_text(path) if path.is_file() else ""
        return self.processing_references[job.id]

    def write_job_reference(self, job, text):
        atomic_text(job.path("reference"), text)
        self.processing_references[job.id] = text
        item = self.processing_rows.get(job.id)
        if item is not None:
            self.import_tree.itemWidget(item, 5).setText("已填写" if text.strip() else "填写")
            self.update_processing_start_state()

    def edit_processing_reference(self, job):
        self.ensure_idle_job(job)
        existing = self.processing_reference_dialogs.get(job.id)
        if existing:
            existing[0].raise_()
            existing[0].activateWindow()
            return existing[0]
        dialog = QDialog(self)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.setWindowTitle("AI 参考歌词 · " + job.stem)
        dialog.resize(660, 520)
        box = QVBoxLayout(dialog)
        self.label(box, job.stem, "section")
        editor = self.make_text()
        editor.setPlaceholderText("粘贴这首歌对应版本的完整参考歌词…")
        self.put(editor, self.processing_reference_text(job))
        box.addWidget(editor, 1)
        self.label(box, "只保存到这首歌的工作记录；AI 校对时仅发送歌词文本。", "muted")
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("保存")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        box.addWidget(buttons)
        def save():
            self.ensure_idle_job(job)
            self.write_job_reference(job, self.get(editor))
            self.status.setText(job.stem + "：参考歌词已保存。")
            dialog.accept()
        buttons.accepted.connect(lambda: self.guard(save))
        buttons.rejected.connect(dialog.reject)
        self.processing_reference_dialogs[job.id] = (dialog, editor)
        dialog.finished.connect(lambda _: self.processing_reference_dialogs.pop(job.id, None))
        dialog.open()
        return dialog

    def update_processing_controls(self):
        selected = self.selected_jobs(self.import_tree)
        existing_count = sum(job.existing_song for job in selected)
        self.processing_hint.setText(f"已选 {len(selected)} 首 · {existing_count} 首现有歌曲保留原音频。" if selected
                                     else "逐行设置处理步骤，再选中需要开始的歌曲。现有歌曲保留原音频。")
        self.update_processing_start_state()

    def processing_problem(self):
        selected = self.selected_jobs(self.import_tree)
        if not selected:
            return "请先选择需要处理的歌曲。"
        for job in selected:
            recognize, ai = job.process_recognize, job.process_ai
            if self.job_active(job):
                return f"{job.stem} 正在处理中，请等任务结束。"
            if not Path(job.source).is_file():
                return f"找不到 {job.stem} 的原始文件。"
            conversion = job.process_convert and not job.existing_song
            if not conversion and not recognize and not ai:
                return f"请为 {job.stem} 选择至少一个有效的处理步骤。"
            if not conversion and Path(job.source).suffix.casefold() != ".mp3":
                return f"{job.stem} 需要先勾选统一格式与响度。"
            if ai:
                if not self.settings.api_key.strip():
                    return "请在参数设置中填写 AI 接口密钥。"
                try:
                    reference = self.processing_reference_text(job)
                    if not reference.strip():
                        return f"请先为 {job.stem} 填写参考歌词。"
                    if not recognize:
                        self.processing_ai_text(job)
                except (OSError, ValueError) as exc:
                    return str(exc)
        return ""

    def update_processing_start_state(self):
        problem = self.processing_problem()
        self.start_processing_button.setEnabled(not problem)
        self.start_processing_button.setToolTip(problem or "开始处理所选歌曲")

    def remove_processing_jobs(self, jobs):
        jobs = [job for job in jobs if job.in_processing]
        if not jobs:
            return
        for job in jobs:
            self.ensure_idle_job(job)
        for job in jobs:
            job.in_processing = False
        try:
            save_jobs(Path(self.settings.work), self.jobs)
        except (OSError, ValueError):
            for job in jobs:
                job.in_processing = True
            raise
        self.refresh_jobs()
        remaining = sum(job.in_processing and self.job_active(job) for job in self.jobs)
        self.status.setText(f"已移除 {len(jobs)} 首，歌曲和已保存的结果保持不变。"
                            + (f" 保留 {remaining} 首进行中的歌曲。" if remaining else ""))

    def remove_all_processing_jobs(self):
        self.remove_processing_jobs([job for job in self.jobs if job.in_processing and not self.job_active(job)])

    def processing_ai_text(self, job):
        sources = [job.path("candidate"), job.path("draft")]
        if job.original_lyric:
            sources.append(Path(job.original_lyric))
        else:
            matching = prepare_music.find_matching_lrc(Path(job.source))
            if matching:
                sources.append(matching)
        source = next((path for path in sources if path.is_file()), None)
        if source is None:
            raise ValueError(f"{job.stem} 没有可校对的歌词，请同时勾选本地识别。")
        text = validate_lrc(read_text(source))
        if text.startswith("#INSTRUMENTAL"):
            raise ValueError(f"{job.stem} 为纯音乐，不需要 AI 校对。")
        return text

    def selected_jobs(self, tree):
        ids = set(self.tree_ids(tree))
        return [job for job in self.jobs if job.id in ids]

    def start_import(self):
        problem = self.processing_problem()
        if problem:
            self.update_processing_start_state()
            raise ValueError(problem)
        selected = self.selected_jobs(self.import_tree)
        ai_inputs = {job.id: self.processing_ai_text(job) for job in selected if job.process_ai and not job.process_recognize}
        queued = 0
        for job in selected:
            stages = []
            job.language = LANGUAGES[self.processing_language.currentText()]
            if job.process_convert and not job.existing_song:
                stages.append("convert")
            else:
                job.audio, job.audio_status = job.source, "保留原 MP3"
            if job.process_recognize:
                stages.append("recognize")
            if job.process_ai:
                if job.id in ai_inputs:
                    atomic_text(job.path("ai_input"), ai_inputs[job.id])
                stages.append("ai")
            self.runner.enqueue(job, stages)
            queued += bool(stages)
        self.persist()
        self.status.setText(f"已安排 {queued} 首歌曲处理，进度可在任务记录中查看。")

    def playlist_path(self):
        name = self.playlist_combo.currentText().strip()
        if name and not name.casefold().endswith(".txt"):
            name += ".txt"
        return library_path(Path(self.settings.library), "playlists", filename(name, ".txt"))

    def playlist_text(self):
        text = write_entries(self.playlist_entries, self.playlist_comments)
        # Keep malformed/conflicting lines until the user explicitly chooses automatic repair.
        return text + "".join(line + "\n" for line in self.playlist_unparsed_lines)

    def update_playlist_check(self):
        issues = self.playlist_issues
        self.repair_playlist_button.setVisible(bool(issues))
        if issues:
            self.playlist_check_label.setText(f"歌单检查：发现 {len(issues)} 行错误")
            details = [issue.description() for issue in issues[:12]]
            if len(issues) > 12:
                details.append(f"另有 {len(issues) - 12} 行错误")
            self.playlist_check_label.setToolTip("\n".join(details))
            self.playlist_check_label.setStyleSheet(theme.colors("color: #a85818;", self.settings.theme))
        else:
            self.playlist_check_label.setText("歌单检查：未发现错误")
            self.playlist_check_label.setToolTip("")
            self.playlist_check_label.setStyleSheet("")
        self.update_playlist_save_state()

    def repair_playlist(self):
        cleaned, issues = inspect_playlist(Path(self.settings.library), self.playlist_text())
        self.playlist_entries, self.playlist_comments = read_entries(cleaned)
        self.playlist_unparsed_lines, self.playlist_issues = [], []
        self.render_playlist()
        self.update_playlist_check()
        self.status.setText(f"已移除 {len(issues)} 行错误，保存歌单后生效。")

    def render_playlist(self):
        self.playlist_entries.sort(key=cmp_to_key(lambda a, b: self.collator.compare(Path(a.audio).stem, Path(b.audio).stem)))
        self.playlist_list.clear()
        self.playlist_items = {}
        for entry in self.playlist_entries:
            self.insert_playlist_row(entry, self.playlist_list.count())
        self.playlist_add_item = QListWidgetItem(self.playlist_list)
        self.playlist_add_item.setSizeHint(QSize(0, 40))
        self.playlist_list.setItemWidget(self.playlist_add_item, self.make_playlist_add_row())
        self.refresh_song_choices()
        self.update_playlist_summary()

    def insert_playlist_row(self, entry, index):
        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, entry.audio)
        item.setSizeHint(QSize(0, 30))
        self.playlist_list.insertItem(index, item)
        self.playlist_list.setItemWidget(item, self.make_playlist_row(entry))
        self.playlist_items[entry.audio.casefold()] = item

    def update_playlist_summary(self):
        total = sum(entry.weight for entry in self.playlist_entries)
        self.playlist_summary.setText(f"{len(self.playlist_entries)} 首歌曲 · 总权重 {total}")
        self.update_playlist_save_state()

    def update_playlist_save_state(self):
        try:
            name = self.playlist_path().name
            modified = self.playlist_text() != self.playlist_baseline or name != self.playlist_baseline_name
        except ValueError:
            modified = False
        self.save_playlist_button.setEnabled(modified and not self.playlist_issues)
        try:
            can_delete = bool(self.playlist_baseline_name) and self.playlist_path().name == self.playlist_baseline_name and self.playlist_path().is_file()
        except ValueError:
            can_delete = False
        self.delete_playlist_button.setEnabled(can_delete)
        self.save_playlist_button.setToolTip("请先自动修复错误行。" if self.playlist_issues else "保存当前歌单")

    def edit_playlist_name(self, name):
        self.playlist_target_name = name

    def load_typed_playlist(self):
        if self.playlist_path().is_file() and self.playlist_path().name != self.playlist_baseline_name:
            self.load_playlist()

    def show_song_dialog(self):
        self.song_picker.setEditText("")
        self.add_weight.setValue(1)
        self.add_lyrics.setChecked(True)
        self.refresh_song_choices()
        self.song_dialog.open()
        self.song_picker.setFocus()

    def change_playlist_entry(self, entry, field, value):
        setattr(entry, field, value)
        self.update_playlist_summary()

    def refresh_song_choices(self):
        text = self.song_picker.currentText()
        used = {entry.audio.casefold() for entry in self.playlist_entries}
        self.available_songs = [song for song in self.songs if song.name.casefold() not in used]
        with QSignalBlocker(self.song_picker):
            self.song_picker.clear()
            self.song_picker.addItems([song.audio.stem for song in self.available_songs])
            self.song_picker.setEditText(text)
        self.song_completer.setModel(self.song_picker.model())
        self.update_song_choice()

    def chosen_song(self):
        text = self.song_picker.currentText().strip().casefold()
        matches = [song for song in self.available_songs if song.audio.stem.casefold() == text or song.name.casefold() == text]
        return matches[0] if len(matches) == 1 else None

    def update_song_choice(self):
        song = self.chosen_song() if hasattr(self, "available_songs") else None
        self.add_song_button.setEnabled(song is not None)
        text = self.song_picker.currentText().strip().casefold()
        if any(text in {Path(entry.audio).stem.casefold(), entry.audio.casefold()} for entry in self.playlist_entries):
            hint = "这首歌已经在歌单中，不能重复添加。"
        elif song is not None:
            hint = "已选中：" + song.audio.stem
        elif text and not any(song.audio.stem.casefold().startswith(text) for song in getattr(self, "available_songs", [])):
            hint = "没有匹配的歌曲。"
        else:
            hint = "输入完整歌名或从匹配列表选择。"
        self.song_choice_hint.setText(hint)

    def add_playlist_song(self):
        song = self.chosen_song()
        if song is None:
            raise ValueError("请选择完整、有效且尚未添加的歌曲。")
        lyric = song.lyric.name if song.lyric is not None else song.audio.stem + ".lrc"
        entry = PlaylistEntry(song.name, lyric, self.add_weight.value(), self.add_lyrics.isChecked())
        scroll = self.playlist_list.verticalScrollBar()
        previous = scroll.value()
        at_bottom = previous == scroll.maximum()
        self.playlist_entries.append(entry)
        self.playlist_entries.sort(key=cmp_to_key(lambda a, b: self.collator.compare(Path(a.audio).stem, Path(b.audio).stem)))
        self.insert_playlist_row(entry, self.playlist_entries.index(entry))
        self.playlist_list.doItemsLayout()
        scroll.setValue(scroll.maximum() if at_bottom else previous)
        self.song_picker.setEditText("")
        self.refresh_song_choices()
        self.update_playlist_summary()
        self.song_dialog.accept()
        self.status.setText("已添加：" + song.audio.stem)

    def remove_playlist_song(self, entry):
        scroll = self.playlist_list.verticalScrollBar()
        previous = scroll.value()
        self.playlist_list.setFocus()
        self.playlist_entries.remove(entry)
        item = self.playlist_items.pop(entry.audio.casefold())
        self.playlist_list.takeItem(self.playlist_list.row(item))
        self.playlist_list.doItemsLayout()
        scroll.setValue(previous)
        self.refresh_song_choices()
        self.update_playlist_summary()

    def load_playlist(self):
        if not self.discard_playlist_edits():
            self.playlist_combo.setCurrentText(self.playlist_target_name)
            return
        try:
            path = self.playlist_path()
            text = read_text(path)
            _, issues = inspect_playlist(Path(self.settings.library), text)
            entries, comments = read_entries(text, strict=False)
        except (OSError, ValueError):
            self.playlist_combo.setCurrentText(self.playlist_target_name)
            raise
        self.playlist_entries, self.playlist_comments = entries, comments
        self.playlist_issues = issues
        self.playlist_unparsed_lines = [issue.text for issue in issues if issue.unparsed]
        self.render_playlist()
        self.playlist_baseline = self.playlist_text()
        self.playlist_baseline_name = path.name
        self.playlist_target_name = path.name
        self.update_playlist_check()
        self.status.setText(f"歌单已载入，发现 {len(issues)} 行错误，可点击上方自动修复。" if issues else "歌单已载入，检查通过。")

    def new_playlist(self):
        if not self.discard_playlist_edits():
            return
        self.playlist_combo.setCurrentText("")
        self.playlist_baseline_name = ""
        self.playlist_target_name = ""
        self.playlist_entries, self.playlist_comments = [], []
        self.playlist_unparsed_lines, self.playlist_issues = [], []
        self.render_playlist()
        self.playlist_baseline = self.playlist_text()
        self.update_playlist_check()
        self.status.setText("输入新歌单名称，添加歌曲后保存。")

    def import_dpl(self):
        if not self.discard_playlist_edits():
            return
        source, _ = QFileDialog.getOpenFileName(self, "选择 PotPlayer DPL", "", "DPL (*.dpl)")
        if not source:
            return
        names, warnings = convert_dpl_playlist.extract_audio_names(convert_dpl_playlist.decode_dpl(Path(source).read_bytes()))
        text = convert_dpl_playlist.build_playlist(names)
        self.playlist_entries, self.playlist_comments = read_entries(text)
        _, self.playlist_issues = inspect_playlist(Path(self.settings.library), text)
        self.playlist_unparsed_lines = []
        self.playlist_combo.setCurrentText(Path(source).stem + ".txt")
        self.playlist_target_name = self.playlist_combo.currentText()
        self.playlist_baseline_name = ""
        self.render_playlist()
        self.playlist_baseline = ""
        self.update_playlist_check()
        self.status.setText(f"已导入 {len(names)} 首歌曲，保存后生效。")







    def discard_playlist_edits(self):
        target_name = self.playlist_target_name.strip()
        if target_name and not target_name.casefold().endswith(".txt"):
            target_name += ".txt"
        if self.playlist_text() == self.playlist_baseline and target_name == self.playlist_baseline_name:
            return True
        return self.confirm("未保存的歌单", "当前歌单编辑尚未保存，是否放弃这些编辑？")

    def save_playlist(self):
        target = self.playlist_path()
        text = self.playlist_text()
        _, self.playlist_issues = inspect_playlist(Path(self.settings.library), text)
        self.update_playlist_check()
        if self.playlist_issues:
            self.status.setText("歌单存在错误，请先点击上方的自动修复。")
            return
        save_library_text(self.settings, "playlists", target.name, text)
        self.playlist_baseline = text
        self.playlist_baseline_name = target.name
        self.playlist_target_name = target.name
        self.playlist_combo.setCurrentText(target.name)
        self.update_playlist_save_state()
        self.scan()
        self.status.setText("歌单已保存。播放器点击“刷新”即可读取。")

    def delete_playlist(self):
        target = self.playlist_path()
        if not self.playlist_baseline_name or target.name != self.playlist_baseline_name or not target.is_file():
            raise ValueError("请先打开要删除的歌单。")
        if not self.confirm("删除歌单", f"删除“{target.name}”？\n当前未保存的歌单编辑也会放弃。歌曲和歌词文件保留，原歌单会备份。"):
            return
        delete_playlist_file(self.settings, target.name)
        self.playlist_entries, self.playlist_comments = [], []
        self.playlist_unparsed_lines, self.playlist_issues = [], []
        self.playlist_baseline = self.playlist_baseline_name = self.playlist_target_name = ""
        self.playlist_combo.setCurrentText("")
        self.render_playlist()
        self.scan()
        self.update_playlist_check()
        self.status.setText("歌单已删除并备份，歌曲和歌词文件保持不变。")

    def setting_text(self, field, settings=None):
        settings = settings or self.settings
        value = getattr(settings, field)
        if field != "api_key" and value:
            path = (Path(settings.library) / value).resolve()
            return path.relative_to(settings.library).as_posix() if path.is_relative_to(settings.library) else str(path)
        return value

    def update_setting_state(self, field):
        text = self.setting_vars[field].text().strip()
        self.setting_save_buttons[field].setEnabled(text != self.setting_text(field))
        if field in self.setting_status_labels:
            exists = bool(text) and (Path(self.settings.library) / text).is_file()
            self.setting_status_labels[field].setText("文件已就绪" if exists else "尚未找到，可下载、自动查找或选择已有文件。")

    def choose_tool(self, field):
        pattern = "模型 (*.bin)" if field == "model" else "程序 (*.exe)"
        selected, _ = QFileDialog.getOpenFileName(self, "选择" + TOOLS[field][0], self.setting_vars[field].text(), pattern)
        if selected:
            self.setting_vars[field].setText(selected)

    def save_setting(self, field):
        if self.runner.busy:
            raise ValueError("请等进行中的任务结束后再改变设置。")
        value = self.setting_vars[field].text().strip()
        if field != "api_key" and value:
            path = (Path(self.settings.library) / value).resolve()
            if not path.is_file():
                raise ValueError("请选择已有文件，或使用下载/自动查找。")
            value = str(path)
        latest = Settings.load(self.base)
        setattr(latest, field, value)
        latest.save(self.base, fields={field})
        self.settings = Settings.load(self.base)
        self.setting_vars[field].setText(self.setting_text(field))
        for name in self.setting_vars:
            self.update_setting_state(name)
        self.update_processing_start_state()
        self.status.setText("该项设置已保存。")

    def detect_tool(self, field):
        path = find_tool(Path(self.settings.library), field, self.setting_vars[field].text().strip())
        if path is None:
            raise ValueError("未找到该工具，可点击下载，或选择已有文件。")
        self.setting_vars[field].setText(str(path))
        self.save_setting(field)

    def download_tool(self, field):
        if self.runner.busy:
            raise ValueError("请等进行中的任务结束后再下载工具。")
        if any(name == field and process.poll() is None for name, process in self.tool_processes):
            self.status.setText("该下载窗口已经打开，请在命令行中查看。")
            return
        args = tool_command("workshop.tool_setup", field, "--root", self.settings.library)
        process = subprocess.Popen(args, cwd=str(self.base), creationflags=subprocess.CREATE_NEW_CONSOLE)
        self.tool_processes.append((field, process))
        self.tool_config_stamp = settings_file(self.base).stat().st_mtime_ns if settings_file(self.base).exists() else None
        self.status.setText("已打开下载命令行：" + TOOLS[field][0] + "。完成后按回车关闭窗口。")

    def poll_tool_windows(self):
        if not self.tool_processes or time.monotonic() < self.tool_poll_at:
            return
        self.tool_poll_at = time.monotonic() + 1
        remaining = [(field, process) for field, process in self.tool_processes if process.poll() is None]
        path = settings_file(self.base)
        stamp = path.stat().st_mtime_ns if path.exists() else None
        if stamp != self.tool_config_stamp or len(remaining) != len(self.tool_processes):
            previous, latest = self.settings, Settings.load(self.base)
            for field, edit in self.setting_vars.items():
                if edit.text().strip() == self.setting_text(field, previous):
                    edit.setText(self.setting_text(field, latest))
            self.settings, self.tool_config_stamp = latest, stamp
            for field in self.setting_vars:
                self.update_setting_state(field)
            self.update_processing_start_state()
        self.tool_processes = remaining

    def cleanup_files(self):
        if self.runner.busy or any(process.poll() is None for _, process in self.tool_processes):
            raise ValueError("请等处理任务结束，并关闭下载窗口后再清理。")
        from .maintenance import show_cleanup_dialog
        return show_cleanup_dialog(self)

    def toggle_theme(self):
        selected = "light" if self.settings.theme == "dark" else "dark"
        latest = Settings.load(self.base)
        latest.theme = selected
        latest.save(self.base, fields={"theme"})
        self.settings.theme = selected
        theme.apply_theme(self, selected)
        for page, button in self.nav_buttons.items():
            button.setIcon(theme.navigation_icon(page, selected))
        self.song_completer.popup().setStyleSheet(theme.colors(theme.POPUP_STYLESHEET, selected))
        self.theme_button.setText("切换浅色" if selected == "dark" else "切换深色")
        self.update_playlist_check()
        for browser in self.findChildren(QTextBrowser, "helpDocument"):
            position = browser.verticalScrollBar().value()
            browser.setHtml(theme.colors(HELP_HTML, selected))
            browser.verticalScrollBar().setValue(position)

    def help(self):
        window = QDialog(self)
        window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        window.setWindowTitle("使用说明")
        window.resize(780, 680)
        layout = QVBoxLayout(window)
        browser = QTextBrowser()
        browser.setObjectName("helpDocument")
        browser.setOpenExternalLinks(False)
        browser.setFrameShape(QTextBrowser.Shape.NoFrame)
        browser.setHtml(theme.colors(HELP_HTML, self.settings.theme))
        layout.addWidget(browser)
        actions = self.row(layout)
        actions.addStretch()
        self.button(actions, "关闭", window.close)
        window.show()
        return window

    def about(self):
        window = QDialog(self)
        window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        window.setWindowTitle("关于音乐管理")
        window.setWindowIcon(self.windowIcon())
        window.resize(440, 260)
        layout = QVBoxLayout(window)
        layout.setContentsMargins(24, 22, 24, 18)
        layout.setSpacing(12)
        self.label(layout, "音乐管理", "brand")
        self.label(layout, "On Screen Music " + PRODUCT_VERSION + " · 音乐管理", "muted")
        self.label(layout, "On Screen Music 的音乐资料助手。\n整理音频、识别与校对歌词、管理歌单。")
        self.label(layout, "制作者：江沛宸 / Inseven、Codex", "muted")
        self.label(layout, "本软件包含 Qt / PySide6 等开源组件，许可与对应源码说明见软件目录 ThirdPartyNotices。", "muted")
        layout.addStretch()
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(window.close)
        layout.addWidget(buttons)
        window.show()
        return window

    def poll(self):
        self.poll_tool_windows()
        changed = False
        for _ in range(80):
            try:
                event, data = self.events.get_nowait()
            except queue.Empty:
                break
            if event == "log":
                job_id, line = data
                self.status.setText(line[-170:])
            else:
                changed = True
                job = next((job for job in self.jobs if job.id == data), None)
                if job and event == "finished":
                    self.status.setText(job.stem + "：" + job.message)
        if changed:
            self.persist()

    def closeEvent(self, event):
        if self.ready_to_close:
            event.accept()
            return
        event.ignore()
        if self.closing:
            return
        if not self.guard(self.prompt_dirty):
            return
        if not self.discard_playlist_edits():
            self.show_page("playlists")
            return
        if self.runner.busy and not self.confirm("任务仍在进行", "停止当前任务和剩余队列，然后退出？\n已完成结果和报告保留。"):
            return
        self.closing = True
        self.stop_preview()
        self.centralWidget().setEnabled(False)
        self.status.setText("正在停止任务并保存工作记录…")
        self.runner.close()
        self.finish_close()

    def finish_close(self):
        if self.runner.thread.is_alive():
            QTimer.singleShot(100, self.finish_close)
            return
        try:
            self.poll()
            self.persist()
        except (OSError, ValueError, RuntimeError) as exc:
            QMessageBox.critical(self, "保存工作记录失败", str(exc))
            self.closing = False
            self.centralWidget().setEnabled(True)
            self.runner = Runner(self.base, self.events)
            return
        self.poll_timer.stop()
        for dialog in self.findChildren(QDialog):
            dialog.close()
        self.ready_to_close = True
        self.close()


def main():
    import sys
    base = application_root()
    application = QApplication(sys.argv)
    application.setApplicationName("On Screen Music 音乐管理")
    application.setOrganizationName("OnScreenMusic")
    application.setWindowIcon(QIcon(str(Path(__file__).with_name("icons") / "workshop.svg")))
    application.setStyle("Fusion")
    translator = QTranslator(application)
    if translator.load("qtbase_zh_CN", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
        application.installTranslator(translator)
    mutex = None
    if os.name == "nt":
        kernel = ctypes.windll.kernel32
        kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
        kernel.CreateMutexW.restype = ctypes.c_void_p
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        # Development and deployed launches share one identity, just as they share the INI.
        key = hashlib.sha256(str(settings_file(base).resolve()).casefold().encode("utf-8")).hexdigest()[:20]
        mutex = kernel.CreateMutexW(None, False, "Local\\MusicWorkshop." + key)
        if not mutex:
            QMessageBox.critical(None, "音乐管理", "无法创建单实例锁。")
            return 1
        if kernel.GetLastError() == 183:
            QMessageBox.information(None, "音乐管理", "音乐管理已经在运行，请切换到已打开的窗口。")
            kernel.CloseHandle(mutex)
            return 0
    try:
        window = WorkshopApp(base)
        window.show()
        return application.exec()
    except Exception as exc:
        QMessageBox.critical(None, "音乐管理启动失败", str(exc))
        return 1
    finally:
        if mutex:
            ctypes.windll.kernel32.CloseHandle(mutex)
