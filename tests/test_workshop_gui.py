"""Qt interaction checks using temporary media and mocked online requests."""
from __future__ import annotations

import sys
from dataclasses import replace
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QCheckBox, QDialog, QLineEdit, QMessageBox, QPushButton, QSpinBox

from workshop.core import Settings, atomic_text, create_job, load_jobs, read_text
from workshop.gui import WorkshopApp
from workshop.shared_settings import read_ini

APPLICATION = QApplication.instance() or QApplication([])
APPLICATION.setStyle("Fusion")
APPLICATION.setQuitOnLastWindowClosed(False)


class FakePreview:
    def __init__(self):
        self.loaded, self.duration, self.volume = False, 0, 20
        self.at, self.is_playing, self.seeks = 0, False, []

    def load(self, path):
        self.source = path
        self.loaded, self.duration, self.at, self.is_playing = True, 180000, 0, False

    def close(self):
        self.loaded, self.duration, self.at, self.is_playing = False, 0, 0, False

    def position(self):
        return self.at

    def playing(self):
        return self.is_playing

    def play(self):
        if self.at >= self.duration:
            self.at = 0
        self.is_playing = True

    def pause(self):
        self.is_playing = False

    def seek(self, value):
        self.at = value
        self.seeks.append(value)

    def set_volume(self, value):
        self.volume = value


class WorkshopGuiTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="workshop-qt-test-")
        self.base = Path(self.temporary.name)
        self.library = self.base
        for folder in ("music", "lyrics", "playlists"):
            (self.library / folder).mkdir(parents=True)
        self.audio = self.library / "music" / "测试歌曲.mp3"
        self.audio.write_bytes(b"unchanged-original-audio")
        self.lyric = self.library / "lyrics" / "测试歌曲.lrc"
        self.lyric.write_text("[00:01.00]原始歌词\n", encoding="utf-8")
        (self.library / "playlists" / "测试歌单.txt").write_text("测试歌曲.mp3|测试歌曲.lrc\n", encoding="utf-8")
        Settings(str(self.library), str(self.base / "MusicWorkshopWork")).save(self.base)
        self.errors = []
        self.critical = mock.patch("workshop.gui.QMessageBox.critical", side_effect=lambda *args: self.errors.append(args[2]))
        self.critical.start()
        self.exception_hook = sys.excepthook
        sys.excepthook = lambda kind, value, trace: self.errors.append(str(value))
        self.preview = FakePreview()
        self.preview_patch = mock.patch("workshop.gui.AudioPreview", return_value=self.preview)
        self.preview_patch.start()
        self.app = WorkshopApp(self.base)
        self.job = create_job(self.app.settings, self.audio, self.audio.stem, self.app.songs[0])
        self.app.jobs.append(self.job)
        self.app.show()
        self.app.song_tree.setCurrentItem(self.app.song_tree.topLevelItem(0))
        APPLICATION.processEvents()
        self.app.open_song_editor(self.app.songs[0])
        self.app.lyric_dialog.reject()
        APPLICATION.processEvents()

    def tearDown(self):
        self.app.poll_timer.stop()
        self.app.preview_timer.stop()
        self.app.runner.close()
        self.app.runner.thread.join(3)
        self.app.ready_to_close = True
        self.app.close()
        self.app.deleteLater()
        APPLICATION.processEvents()
        sys.excepthook = self.exception_hook
        self.critical.stop()
        self.preview_patch.stop()
        self.temporary.cleanup()
        self.assertFalse(self.errors)

    def edit(self, text):
        if not self.app.lyric_dialog.isVisible():
            self.app.open_song_editor(self.app.editing_song)
        self.app.editor.setPlainText(text)
        APPLICATION.processEvents()

    def click(self, text):
        buttons = [button for button in self.app.findChildren(QPushButton) if button.text() == text]
        button = next((button for button in buttons if button.isVisible()), buttons[0])
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        APPLICATION.processEvents()

    def processing_option(self, job, field, checked=True):
        from workshop.qt_ui import PROCESSING_FIELDS
        column = next(column for column, name in PROCESSING_FIELDS.items() if name == field)
        self.app.processing_rows[job.id].setCheckState(column, Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        APPLICATION.processEvents()

    def processing_reference(self, job, text):
        from PySide6.QtWidgets import QDialogButtonBox
        dialog = self.app.edit_processing_reference(job)
        editor = self.app.processing_reference_dialogs[job.id][1]
        editor.setPlainText(text)
        QTest.mouseClick(dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Save), Qt.MouseButton.LeftButton)
        APPLICATION.processEvents()

    def test_manual_edit_saves_original_document_without_working_candidate(self):
        self.assertEqual(self.app.get(self.app.editor), "[00:01.00]原始歌词\n")
        self.edit("[00:01.00]校对歌词\n")
        self.click("保存")
        self.assertFalse(self.app.dirty)
        self.assertFalse(self.job.path("candidate").exists())
        self.assertEqual(read_text(self.lyric), "[00:01.00]校对歌词\n")
        self.assertFalse(self.app.lyric_save_button.isEnabled())
        self.assertEqual(self.audio.read_bytes(), b"unchanged-original-audio")

    def test_save_targets_custom_mapping_and_preserves_previous_version(self):
        self.edit("[00:01.00]新歌词\n")
        with mock.patch.object(self.app, "confirm") as confirm:
            self.click("保存")
            confirm.assert_not_called()
        self.assertEqual(read_text(self.lyric), "[00:01.00]新歌词\n")
        backups = list((self.base / "MusicWorkshopWork" / "backups").glob("*/测试歌曲.lrc"))
        self.assertEqual(read_text(backups[0]), "[00:01.00]原始歌词\n")

    def test_save_rejects_external_change(self):
        self.edit("[00:01.00]候选\n")
        self.lyric.write_text("[00:01.00]外部修改\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "其他操作修改"):
            self.app.save_lyrics()
        self.assertEqual(read_text(self.lyric), "[00:01.00]外部修改\n")

    def test_playlist_weight_and_lyric_switch_only_edit_references(self):
        self.app.playlist_combo.setCurrentText("测试歌单.txt")
        self.app.load_playlist()
        self.assertEqual(self.app.playlist_list.count(), 2)
        row = self.app.playlist_list.itemWidget(self.app.playlist_list.item(0))
        row.findChild(QSpinBox).setValue(3)
        row.findChild(QCheckBox).setChecked(False)
        self.app.save_playlist()
        self.assertEqual(read_text(self.library / "playlists/测试歌单.txt"), "测试歌曲.mp3|-\n" * 3)
        row.findChild(QCheckBox).setChecked(True)
        self.app.save_playlist()
        self.assertEqual(read_text(self.library / "playlists/测试歌单.txt"), "测试歌曲.mp3|测试歌曲.lrc\n" * 3)
        self.app.remove_playlist_song(self.app.playlist_entries[0])
        self.assertEqual(self.app.playlist_list.count(), 1)
        self.assertTrue(self.audio.exists())
        self.assertTrue(self.lyric.exists())

    def test_lyric_editor_has_only_manual_controls_and_is_outside_library_page(self):
        self.assertFalse(self.app.frames["library"].isAncestorOf(self.app.editor))
        self.assertTrue(self.app.lyric_dialog.isAncestorOf(self.app.editor))
        self.assertFalse(hasattr(self.app, "lyric_tabs"))
        self.assertFalse(hasattr(self.app, "reference"))
        texts = {button.text() for button in self.app.lyric_dialog.findChildren(QPushButton)}
        self.assertTrue({"保存", "关闭", "应用偏移", "播放"}.issubset(texts))
        self.assertFalse({"保存到工作目录", "采用到资料库", "另存 LRC", "查看修改", "本地识别", "生成 AI 候选"} & texts)

    def test_editor_close_discard_reopens_saved_text(self):
        job = self.job
        self.edit("[00:01]放弃的修改\n")
        with mock.patch("workshop.gui.QMessageBox.question", return_value=QMessageBox.StandardButton.Discard):
            self.app.lyric_dialog.reject()
        self.assertFalse(self.app.lyric_dialog.isVisible())
        self.assertFalse(job.path("candidate").exists())
        self.app.open_song_editor(self.app.songs[0])
        self.assertEqual(self.app.editor.toPlainText(), "[00:01.00]原始歌词\n")
        self.assertFalse(self.app.dirty)

    def test_editor_escape_and_close_guard_unsaved_changes(self):
        job = self.job
        self.edit("[00:02]不能静默丢失\n")
        with mock.patch("workshop.gui.QMessageBox.question", return_value=QMessageBox.StandardButton.Cancel):
            QTest.keyClick(self.app.lyric_dialog, Qt.Key.Key_Escape)
            self.assertTrue(self.app.lyric_dialog.isVisible())
            self.app.lyric_dialog.close()
            self.assertTrue(self.app.lyric_dialog.isVisible())
        self.assertTrue(self.app.dirty)
        with mock.patch("workshop.gui.QMessageBox.question", return_value=QMessageBox.StandardButton.Save):
            self.app.lyric_dialog.close()
        self.assertFalse(self.app.lyric_dialog.isVisible())
        self.assertEqual(read_text(self.lyric), "[00:02]不能静默丢失\n")

    def test_library_selection_search_and_filter_do_not_open_editor_or_create_jobs(self):
        self.app.editing_song = None
        before = len(self.app.jobs)
        item = self.app.song_tree.topLevelItem(0)
        button = self.app.song_tree.itemWidget(item, 1)
        with mock.patch.object(self.app.runner, "enqueue") as enqueue, \
             mock.patch("workshop.gui.read_text", side_effect=AssertionError("搜索不应重新读取歌词")):
            self.app.song_tree.setCurrentItem(item)
            self.app.search.setText("不匹配")
            self.assertIn("显示 0 首", self.app.library_summary.text())
            self.app.search.setText("测试")
            self.assertIn("显示 1 首", self.app.library_summary.text())
            enqueue.assert_not_called()
        self.assertIs(self.app.song_tree.itemWidget(item, 1), button)
        self.assertIsNone(self.app.editing_song)
        self.assertEqual(len(self.app.jobs), before)
        self.assertFalse(self.app.lyric_dialog.isVisible())

    def test_library_is_independent_of_playlists_and_has_no_status_or_jump_button(self):
        atomic_text(self.library / "playlists/错误映射.txt", "测试歌曲.mp3|别的歌词.lrc\ninvalid\n")
        with mock.patch("workshop.gui.read_text", side_effect=AssertionError("资料列表不应读取歌词或歌单")):
            self.app.scan()
        self.assertEqual(self.app.song_tree.columnCount(), 2)
        self.assertFalse(hasattr(self.app, "filter"))
        self.assertEqual(self.app.songs[0].lyric, self.lyric)
        texts = {button.text() for button in self.app.frames["library"].findChildren(QPushButton)}
        self.assertNotIn("处理歌曲", texts)
        item = self.app.song_tree.topLevelItem(0)
        button = self.app.song_tree.itemWidget(item, 1)
        self.assertGreaterEqual(button.height(), button.fontMetrics().height() + 6)
        self.assertGreaterEqual(item.sizeHint(0).height(), button.height() + 4)

    def test_normal_combo_popups_use_uniform_rows_without_menu_frame(self):
        from PySide6.QtWidgets import QStyle
        for combo in (self.app.processing_language, self.app.playlist_combo):
            self.assertEqual(combo.style().styleHint(QStyle.StyleHint.SH_ComboBox_Popup, None, combo), 0)
            self.assertEqual(combo.maxVisibleItems(), 12)
            self.assertEqual(combo.view().sizeHintForRow(0), 32)

    def test_each_library_row_opens_its_own_song(self):
        second = self.library / "music/另一首.mp3"
        second.write_bytes(b"unchanged-second-audio")
        atomic_text(self.library / "lyrics/另一首.lrc", "[00:03]另一首歌词\n")
        self.app.scan()
        item = self.app.library_rows[second.name]
        QTest.mouseClick(self.app.song_tree.itemWidget(item, 1), Qt.MouseButton.LeftButton)
        APPLICATION.processEvents()
        self.assertTrue(self.app.lyric_dialog.isVisible())
        self.assertEqual(self.app.editing_song.audio, second)
        self.assertEqual(self.app.editor.toPlainText(), "[00:03]另一首歌词\n")
        self.assertIn("另一首", self.app.lyric_dialog.windowTitle())
        self.assertEqual(second.read_bytes(), b"unchanged-second-audio")

    def test_manual_editor_save_preserves_processing_reference(self):
        job = self.job
        atomic_text(job.path("reference"), "单独保存的 AI 参考歌词")
        self.edit("[00:01]手动修改\n")
        self.click("保存")
        self.assertEqual(read_text(job.path("reference")), "单独保存的 AI 参考歌词")

    def test_all_pages_are_accessible_without_losing_editor(self):
        self.edit("[00:02.00]已保存候选\n")
        self.click("保存")
        self.app.lyric_dialog.reject()
        for page, button in self.app.nav_buttons.items():
            QTest.mouseClick(button, Qt.MouseButton.LeftButton)
            APPLICATION.processEvents()
            self.assertEqual(self.app.page, page)
            self.assertIs(self.app.content.currentWidget(), self.app.frames[page])
            self.assertTrue(button.isChecked())
        self.app.open_song_editor(self.app.songs[0])
        self.assertEqual(self.app.get(self.app.editor), "[00:02.00]已保存候选\n")
        self.assertFalse(self.app.dirty)

    def test_search_and_multiselection_use_filename_identity(self):
        self.app.search.setText("不匹配")
        self.assertTrue(self.app.song_tree.topLevelItem(0).isHidden())
        self.app.search.setText("测试")
        self.app.select_ids(self.app.song_tree, ["测试歌曲.mp3"])
        self.assertEqual([song.name for song in self.app.selected_songs()], ["测试歌曲.mp3"])

    def test_row_edit_button_opens_original_document_and_ignores_working_candidates(self):
        job = self.app.add_existing_songs(self.app.songs)[0]
        job.task_state = "succeeded"
        atomic_text(job.path("candidate"), "[00:02]最新处理结果\n")
        item = self.app.library_rows[self.audio.name]
        with mock.patch.object(self.app.runner, "enqueue") as enqueue:
            QTest.mouseClick(self.app.song_tree.itemWidget(item, 1), Qt.MouseButton.LeftButton)
            APPLICATION.processEvents()
            enqueue.assert_not_called()
        self.assertTrue(self.app.lyric_dialog.isVisible())
        self.assertEqual(self.app.editing_song.audio, self.audio)
        self.assertEqual(self.app.editor.toPlainText(), "[00:01.00]原始歌词\n")
        self.assertEqual(read_text(job.path("candidate")), "[00:02]最新处理结果\n")
        self.assertFalse(self.app.editor.isReadOnly())
        self.assertEqual(read_text(self.lyric), "[00:01.00]原始歌词\n")

    def test_task_progress_and_finished_event_do_not_replace_original_document(self):
        job = self.job
        job.stages = ["convert", "recognize"]
        job.completed_stages = 1
        job.current_stage = "recognize"
        job.task_state = "running"
        self.assertFalse(self.app.editor.isReadOnly())
        self.app.refresh_jobs()
        _, description, stage, progress, action = self.app.task_rows[job.id]
        self.assertEqual(progress.value(), 50)
        self.assertIn("2/2", stage.text())
        self.assertEqual(action.text(), "×")
        atomic_text(job.path("draft"), "[00:02.00]生成草稿\n")
        job.lyric_status = "成功"
        job.task_state = "succeeded"
        job.completed_stages = 2
        self.app.events.put(("finished", job.id))
        self.app.poll()
        self.assertFalse(self.app.editor.isReadOnly())
        self.assertEqual(self.app.get(self.app.editor), "[00:01.00]原始歌词\n")
        self.assertEqual(progress.value(), 100)
        self.assertEqual(description.text(), "完成 · 结果已保存到工作目录")
        self.assertEqual(action.text(), "⌫")
        self.assertEqual(self.app.task_list.count(), 1)

    def test_prefix_selection_duplicate_rejection_and_natural_sort(self):
        for name in ["F10", "F2", "A1"]:
            (self.library / "music" / (name + ".mp3")).write_bytes(b"test")
        self.app.scan()
        self.app.song_picker.setEditText("F")
        self.app.song_completer.setCompletionPrefix("F")
        matches = [self.app.song_completer.completionModel().index(i, 0).data()
                   for i in range(self.app.song_completer.completionCount())]
        self.assertEqual(matches, ["F2", "F10"])
        self.assertFalse(self.app.add_song_button.isEnabled())
        self.app.song_picker.setEditText("不存在")
        self.assertFalse(self.app.add_song_button.isEnabled())
        for name in ["F10", "F2", "A1"]:
            self.app.song_picker.setEditText(name)
            self.assertTrue(self.app.add_song_button.isEnabled())
            self.app.add_playlist_song()
        self.assertEqual([entry.audio for entry in self.app.playlist_entries], ["A1.mp3", "F2.mp3", "F10.mp3"])
        self.app.song_picker.setEditText("F2")
        self.assertFalse(self.app.add_song_button.isEnabled())
        with self.assertRaises(ValueError):
            self.app.add_playlist_song()

    def test_active_task_requires_confirmation_and_only_cancels_itself(self):
        job = self.job
        job.task_state = "running"
        with mock.patch.object(self.app, "confirm", return_value=False), mock.patch.object(self.app.runner, "cancel") as cancel:
            self.app.task_action(job)
            cancel.assert_not_called()
        with mock.patch.object(self.app, "confirm", return_value=True), mock.patch.object(self.app.runner, "cancel") as cancel:
            self.app.task_action(job)
            cancel.assert_called_once_with(job.id)
        self.assertEqual(read_text(self.lyric), "[00:01.00]原始歌词\n")

    def test_terminal_task_deletion_removes_record_and_preserves_files(self):
        job = self.job
        job.task_state = "failed"
        job.message = "测试失败原因"
        atomic_text(job.path("candidate"), "[00:01]已有候选\n")
        self.app.refresh_jobs()
        self.assertIn("测试失败原因", self.app.task_rows[job.id][1].text())
        self.app.task_action(job)
        self.assertFalse(self.app.jobs)
        self.assertEqual(self.app.task_list.count(), 0)
        self.assertTrue(job.path("candidate").is_file())
        self.assertEqual(read_text(self.lyric), "[00:01.00]原始歌词\n")

    def test_selected_text_uses_dark_foreground(self):
        from PySide6.QtGui import QPalette
        for widget in [self.app.editor, self.app.search, self.app.song_picker]:
            color = widget.palette().color(QPalette.ColorRole.HighlightedText)
            self.assertEqual(color.name(), "#183d78")
        self.assertNotIn("library", self.app.setting_vars)
        self.assertNotIn("work", self.app.setting_vars)
        self.assertFalse(self.app.setting_vars["model"].isReadOnly())

    def test_typing_prefix_opens_filtered_list_and_keyboard_selects_song(self):
        for name in ["F10", "F2", "Other"]:
            (self.library / "music" / (name + ".mp3")).write_bytes(b"test")
        self.app.scan()
        self.app.show_page("playlists")
        self.app.show_song_dialog()
        edit = self.app.song_picker.lineEdit()
        edit.setFocus()
        QTest.keyClicks(edit, "F")
        APPLICATION.processEvents()
        self.assertEqual(self.app.song_completer.completionCount(), 2)
        self.assertTrue(self.app.song_completer.popup().isVisible())
        # Real keyboard input is routed to Qt's active completion popup.
        QTest.keyClick(self.app.song_completer.popup(), Qt.Key.Key_Down)
        QTest.keyClick(self.app.song_completer.popup(), Qt.Key.Key_Return)
        APPLICATION.processEvents()
        self.assertEqual(self.app.chosen_song().audio.stem, "F2")
        self.assertTrue(self.app.add_song_button.isEnabled())

    def test_finished_task_preserves_unsaved_manual_edits(self):
        job = self.job
        self.edit("[00:01]未保存的手动编辑\n")
        atomic_text(job.path("candidate"), "[00:03]后台完成的候选\n")
        job.task_state = "succeeded"
        self.app.events.put(("finished", job.id))
        self.app.poll()
        self.assertFalse(self.app.editor.isReadOnly())
        self.assertTrue(self.app.dirty)
        self.assertEqual(self.app.get(self.app.editor), "[00:01]未保存的手动编辑\n")
        self.assertEqual(read_text(job.path("candidate")), "[00:03]后台完成的候选\n")

    def test_file_dialog_requires_processing_step_and_no_export_controls(self):
        source = self.base / "source" / "导入歌曲.mp3"
        source.parent.mkdir()
        source.write_bytes(b"original-mp3-unchanged")
        source.with_suffix(".lrc").write_text("[00:01.00]导入歌词\n", encoding="utf-8")
        with mock.patch("workshop.gui.QFileDialog.getOpenFileNames", return_value=([str(source)], "")):
            self.app.add_sources(False)
        self.assertTrue(self.app.start_processing_button.isEnabled())
        job = self.app.selected_jobs(self.app.import_tree)[0]
        self.processing_option(job, "process_convert", False)
        self.assertFalse(self.app.start_processing_button.isEnabled())
        self.processing_option(job, "process_recognize")
        self.assertTrue(self.app.start_processing_button.isEnabled())
        with mock.patch.object(self.app.runner, "enqueue") as enqueue:
            self.app.start_import()
        enqueue.assert_called_once_with(job, ["recognize"])
        self.assertEqual(source.read_bytes(), b"original-mp3-unchanged")
        self.assertFalse((self.library / "music" / source.name).exists())
        self.assertFalse(hasattr(self.app, "export_combo"))
        self.assertFalse(any(button.text() == "导出所选结果" for button in self.app.findChildren(QPushButton)))

    def test_start_button_tracks_invalid_selection_reference_key_and_running_task(self):
        self.assertFalse(self.app.start_processing_button.isEnabled())
        job = self.app.add_existing_songs(self.app.songs)[0]
        self.assertFalse(self.app.start_processing_button.isEnabled())
        self.processing_option(job, "process_ai")
        self.processing_reference(job, "参考歌词")
        self.assertFalse(self.app.start_processing_button.isEnabled())
        self.app.setting_vars["api_key"].setText("mock-only")
        self.app.save_setting("api_key")
        self.assertTrue(self.app.start_processing_button.isEnabled())
        self.processing_reference(job, "")
        self.assertFalse(self.app.start_processing_button.isEnabled())
        self.processing_reference(job, "完整参考歌词")
        self.assertTrue(self.app.start_processing_button.isEnabled())
        job.task_state = "running"
        self.app.refresh_jobs()
        self.assertFalse(self.app.start_processing_button.isEnabled())
        job.task_state = "succeeded"
        self.app.refresh_jobs()
        self.assertTrue(self.app.start_processing_button.isEnabled())

    def test_ai_without_lyrics_or_non_mp3_without_conversion_disables_start(self):
        job = self.app.add_existing_songs(self.app.songs)[0]
        self.processing_option(job, "process_ai")
        self.app.settings.api_key = "mock-only"
        self.processing_reference(job, "参考歌词")
        self.assertTrue(self.app.start_processing_button.isEnabled())
        self.lyric.unlink()
        self.app.update_processing_controls()
        self.assertFalse(self.app.start_processing_button.isEnabled())
        self.processing_option(job, "process_recognize")
        self.assertTrue(self.app.start_processing_button.isEnabled())
        self.processing_option(job, "process_ai", False)
        source = self.base / "temporary.wav"
        source.write_bytes(b"source")
        with mock.patch("workshop.gui.QFileDialog.getOpenFileNames", return_value=([str(source)], "")):
            self.app.add_sources(False)
        new = self.app.selected_jobs(self.app.import_tree)[0]
        self.processing_option(new, "process_convert", False)
        self.assertFalse(self.app.start_processing_button.isEnabled())
        self.processing_option(new, "process_convert")
        self.assertTrue(self.app.start_processing_button.isEnabled())

    def test_processing_row_removal_preserves_task_record_results_and_originals(self):
        job = self.app.add_existing_songs(self.app.songs)[0]
        job.task_state = "succeeded"
        atomic_text(job.path("candidate"), "[00:01]已保存结果\n")
        self.app.refresh_jobs()
        item = self.app.import_tree.topLevelItem(0)
        remove = self.app.import_tree.itemWidget(item, 7)
        self.assertTrue(remove.isEnabled())
        QTest.mouseClick(remove, Qt.MouseButton.LeftButton)
        APPLICATION.processEvents()
        self.assertEqual(self.app.import_tree.topLevelItemCount(), 0)
        self.assertFalse(job.in_processing)
        self.assertIn(job, self.app.jobs)
        self.assertIn(job.id, self.app.task_rows)
        self.assertEqual(read_text(job.path("candidate")), "[00:01]已保存结果\n")
        self.assertEqual(self.audio.read_bytes(), b"unchanged-original-audio")
        self.assertEqual(read_text(self.lyric), "[00:01.00]原始歌词\n")

    def test_processing_row_removal_is_disabled_while_running(self):
        job = self.app.add_existing_songs(self.app.songs)[0]
        job.task_state = "running"
        self.app.refresh_jobs()
        remove = self.app.import_tree.itemWidget(self.app.import_tree.topLevelItem(0), 7)
        self.assertFalse(remove.isEnabled())
        QTest.mouseClick(remove, Qt.MouseButton.LeftButton)
        self.assertTrue(job.in_processing)

    def test_processing_removal_keeps_other_rows_selection_and_scroll(self):
        template = self.job
        jobs = [replace(template, id=f"row-{i}", stem=f"Song{i:03}", in_processing=True)
                for i in range(100)]
        self.app.jobs.extend(jobs)
        self.app.refresh_jobs()
        self.app.show_page("import")
        self.app.select_processing_jobs([jobs[44].id, jobs[45].id])
        APPLICATION.processEvents()
        scroll = self.app.import_tree.verticalScrollBar()
        scroll.setValue(35)
        position = scroll.value()
        other = self.app.processing_rows[jobs[45].id]
        other_button = self.app.import_tree.itemWidget(other, 7)
        self.app.remove_processing_jobs([jobs[44]])
        APPLICATION.processEvents()
        self.assertEqual(scroll.value(), position)
        self.assertIs(self.app.processing_rows[jobs[45].id], other)
        self.assertIs(self.app.import_tree.itemWidget(other, 7), other_button)
        self.assertEqual(self.app.tree_ids(self.app.import_tree), [jobs[45].id])
        self.app.refresh_jobs()
        self.assertIs(self.app.processing_rows[jobs[45].id], other)
        self.assertNotIn(jobs[44].id, self.app.processing_rows)

    def test_remove_all_keeps_active_tasks_and_saved_reference(self):
        self.assertFalse(self.app.remove_all_processing_button.isEnabled())
        template = self.job
        jobs = [replace(template, id=f"bulk-{i}", stem=f"Song{i}", task_state=state,
                        directory=str(Path(self.app.settings.work) / "jobs" / f"bulk-{i}"),
                        in_processing=True)
                for i, state in enumerate(["draft", "queued", "succeeded", "running", "failed", "cancelling", "cancelled"])]
        self.app.jobs.extend(jobs)
        atomic_text(jobs[2].path("candidate"), "[00:01]已保存结果\n")
        self.app.refresh_jobs()
        self.app.select_processing_jobs([jobs[0].id])
        self.processing_reference(jobs[0], "移除前已保存的参考")
        self.assertTrue(self.app.remove_all_processing_button.isEnabled())
        self.click("移除全部")
        active_ids = [job.id for job in jobs if self.app.job_active(job)]
        self.assertEqual(list(self.app.processing_rows), active_ids)
        self.assertEqual(self.app.import_tree.topLevelItemCount(), 3)
        self.assertFalse(self.app.remove_all_processing_button.isEnabled())
        self.assertEqual(read_text(jobs[0].path("reference")), "移除前已保存的参考")
        self.assertEqual(read_text(jobs[2].path("candidate")), "[00:01]已保存结果\n")
        self.assertEqual(len(self.app.task_rows), 6)
        self.assertEqual(self.audio.read_bytes(), b"unchanged-original-audio")
        self.assertEqual(read_text(self.lyric), "[00:01.00]原始歌词\n")
        loaded = load_jobs(Path(self.app.settings.work))
        self.assertEqual([job.id for job in loaded if job.in_processing], active_ids)
        jobs[1].task_state = "succeeded"
        self.app.refresh_jobs()
        self.assertTrue(self.app.remove_all_processing_button.isEnabled())
        self.click("移除全部")
        self.assertEqual(self.app.import_tree.topLevelItemCount(), 2)

    def test_remove_all_clears_idle_rows_and_failed_save_leaves_list_intact(self):
        job = self.app.add_existing_songs(self.app.songs)[0]
        with mock.patch("workshop.gui.save_jobs", side_effect=OSError("模拟写入失败")):
            with self.assertRaises(OSError):
                self.app.remove_all_processing_jobs()
        self.assertTrue(job.in_processing)
        self.assertEqual(self.app.import_tree.topLevelItemCount(), 1)
        self.click("移除全部")
        self.assertFalse(job.in_processing)
        self.assertEqual(self.app.import_tree.topLevelItemCount(), 0)
        self.assertFalse(self.app.processing_rows)
        self.assertFalse(self.app.remove_all_processing_button.isEnabled())

    def test_existing_song_skips_conversion_and_can_recognize(self):
        job = self.app.add_existing_songs(self.app.songs)[0]
        self.assertTrue(job.existing_song)
        from workshop.qt_ui import ProcessingStepDelegate
        index = self.app.import_tree.indexFromItem(self.app.processing_rows[job.id], 1)
        self.assertFalse(ProcessingStepDelegate.enabled(index))
        self.assertFalse(job.process_convert)
        self.processing_option(job, "process_recognize")
        with mock.patch.object(self.app.runner, "enqueue") as enqueue:
            self.app.start_import()
        enqueue.assert_called_once_with(job, ["recognize"])
        self.assertEqual(self.audio.read_bytes(), b"unchanged-original-audio")
        self.assertEqual(job.target_lyric, "测试歌曲.lrc")

    def test_existing_song_ai_only_snapshots_custom_lyric_and_reference(self):
        job = self.app.add_existing_songs(self.app.songs)[0]
        self.processing_option(job, "process_ai")
        self.app.settings.api_key = "mock-no-network"
        self.processing_reference(job, "完整参考歌词")
        with mock.patch.object(self.app.runner, "enqueue") as enqueue:
            self.app.start_import()
        enqueue.assert_called_once_with(job, ["ai"])
        self.assertEqual(read_text(job.path("ai_input")), "[00:01.00]原始歌词\n")
        self.assertEqual(read_text(job.path("reference")), "完整参考歌词")
        self.assertEqual(read_text(self.lyric), "[00:01.00]原始歌词\n")

    def test_mixed_sources_only_convert_new_files(self):
        existing = self.app.add_existing_songs(self.app.songs)[0]
        source = self.base / "new.wav"
        source.write_bytes(b"temporary-input")
        with mock.patch("workshop.gui.QFileDialog.getOpenFileNames", return_value=([str(source)], "")):
            self.app.add_sources(False)
        new = next(job for job in self.app.jobs if job.source == str(source))
        self.app.select_processing_jobs([existing.id, new.id])
        self.assertFalse(existing.process_convert)
        self.assertTrue(new.process_convert)
        self.processing_option(existing, "process_recognize")
        self.processing_option(new, "process_recognize")
        with mock.patch.object(self.app.runner, "enqueue") as enqueue:
            self.app.start_import()
        self.assertEqual(enqueue.call_args_list, [mock.call(existing, ["recognize"]), mock.call(new, ["convert", "recognize"])])

    def test_processing_references_follow_each_song_and_validate_whole_selection(self):
        second = self.library / "music/第二首.mp3"
        second.write_bytes(b"temporary-mp3")
        atomic_text(self.library / "lyrics/第二首.lrc", "[00:02]第二首歌词\n")
        self.app.scan()
        jobs = self.app.add_existing_songs(self.app.songs)
        first, second = jobs
        self.processing_option(first, "process_ai")
        self.processing_option(second, "process_ai")
        self.app.settings.api_key = "mock-only"
        self.app.select_processing_jobs([first.id])
        self.processing_reference(first, "第一份参考")
        self.app.select_processing_jobs([second.id])
        self.app.select_processing_jobs([first.id, second.id])
        with mock.patch.object(self.app.runner, "enqueue") as enqueue:
            with self.assertRaisesRegex(ValueError, "填写参考歌词"):
                self.app.start_import()
            enqueue.assert_not_called()
        self.app.select_processing_jobs([second.id])
        self.processing_reference(second, "第二份参考")
        self.app.select_processing_jobs([first.id])
        self.assertEqual(self.app.processing_reference_text(first), "第一份参考")
        self.assertEqual(read_text(second.path("reference")), "第二份参考")
        self.app.select_processing_jobs([first.id, second.id])
        with mock.patch.object(self.app.runner, "enqueue") as enqueue:
            self.app.start_import()
        self.assertEqual(enqueue.call_count, 2)

    def test_processing_steps_and_repetition_are_independent_and_persisted(self):
        existing = self.app.add_existing_songs(self.app.songs)[0]
        source = self.base / "新素材.mp3"
        source.write_bytes(b"temporary-original")
        with mock.patch("workshop.gui.QFileDialog.getOpenFileNames", return_value=([str(source)], "")):
            self.app.add_sources(False)
        new = self.app.selected_jobs(self.app.import_tree)[0]
        self.app.settings.api_key = "mock-only"
        self.processing_option(existing, "process_ai")
        self.processing_reference(existing, "现有歌曲参考")
        self.processing_option(new, "process_recognize")
        self.processing_option(new, "allow_repetition")
        self.assertFalse(existing.process_recognize)
        self.assertFalse(existing.allow_repetition)
        self.assertFalse(new.process_ai)
        self.app.select_processing_jobs([existing.id, new.id])
        with mock.patch.object(self.app.runner, "enqueue") as enqueue:
            self.app.start_import()
        self.assertEqual(enqueue.call_args_list, [mock.call(existing, ["ai"]), mock.call(new, ["convert", "recognize"])])
        loaded = {job.id: job for job in load_jobs(Path(self.app.settings.work))}
        self.assertTrue(loaded[new.id].allow_repetition)
        self.assertTrue(loaded[new.id].process_convert)
        self.assertTrue(loaded[new.id].process_recognize)
        self.assertFalse(loaded[existing.id].process_convert)
        self.assertTrue(loaded[existing.id].process_ai)
        self.assertEqual(read_text(existing.path("ai_input")), "[00:01.00]原始歌词\n")
        self.assertEqual(source.read_bytes(), b"temporary-original")
        self.assertFalse(hasattr(self.app, "processing_reference_panel"))
        self.assertFalse(hasattr(self.app, "convert_on_import"))

    def test_processing_reference_dialog_cancel_keeps_saved_text(self):
        job = self.app.add_existing_songs(self.app.songs)[0]
        dialog = self.app.edit_processing_reference(job)
        self.app.processing_reference_dialogs[job.id][1].setPlainText("未保存参考")
        dialog.reject()
        self.assertFalse(job.path("reference").exists())
        self.assertNotIn(job.id, self.app.processing_reference_dialogs)
        self.processing_reference(job, "已保存参考")
        dialog = self.app.edit_processing_reference(job)
        editor = self.app.processing_reference_dialogs[job.id][1]
        self.assertEqual(editor.toPlainText(), "已保存参考")
        editor.setPlainText("取消这次修改")
        dialog.reject()
        self.assertEqual(read_text(job.path("reference")), "已保存参考")
        self.assertEqual(self.app.processing_reference_text(job), "已保存参考")

    def test_processing_native_checks_enforce_existing_active_and_repetition_rules(self):
        from workshop.qt_ui import ProcessingStepDelegate
        job = self.app.add_existing_songs(self.app.songs)[0]
        item = self.app.processing_rows[job.id]
        self.processing_option(job, "process_convert")
        self.assertFalse(job.process_convert)
        self.processing_option(job, "allow_repetition")
        self.assertFalse(job.allow_repetition)
        self.processing_option(job, "process_recognize")
        self.app.show_page("import")
        self.app.import_tree.setCurrentItem(item, 4)
        QTest.keyClick(self.app.import_tree, Qt.Key.Key_Space)
        APPLICATION.processEvents()
        self.assertTrue(job.allow_repetition)
        job.task_state = "running"
        self.app.refresh_jobs()
        for column in (1, 2, 3, 4):
            self.assertFalse(ProcessingStepDelegate.enabled(self.app.import_tree.indexFromItem(item, column)))
        self.assertFalse(self.app.import_tree.itemWidget(item, 5).isEnabled())
        QTest.keyClick(self.app.import_tree, Qt.Key.Key_Space)
        self.assertTrue(job.allow_repetition)
        self.processing_option(job, "process_ai")
        self.assertFalse(job.process_ai)

    def test_processing_checkbox_mouse_click_keeps_batch_selection(self):
        from PySide6.QtCore import QPoint
        (self.library / "music/第二首.mp3").write_bytes(b"temporary-original")
        self.app.scan()
        jobs = self.app.add_existing_songs(self.app.songs)
        self.app.show_page("import")
        APPLICATION.processEvents()
        item = self.app.processing_rows[jobs[0].id]
        rect = self.app.import_tree.visualRect(self.app.import_tree.indexFromItem(item, 2))
        QTest.mouseClick(self.app.import_tree.viewport(), Qt.MouseButton.LeftButton,
                         pos=QPoint(rect.left() + 14, rect.center().y()))
        APPLICATION.processEvents()
        self.assertTrue(jobs[0].process_recognize)
        self.assertFalse(jobs[1].process_recognize)
        self.assertEqual(set(self.app.tree_ids(self.app.import_tree)), {job.id for job in jobs})

    def test_processing_reference_write_failure_keeps_dialog_and_old_text(self):
        from PySide6.QtWidgets import QDialogButtonBox
        job = self.app.add_existing_songs(self.app.songs)[0]
        self.processing_reference(job, "旧参考")
        dialog = self.app.edit_processing_reference(job)
        self.app.processing_reference_dialogs[job.id][1].setPlainText("写入失败的新参考")
        with mock.patch("workshop.gui.atomic_text", side_effect=OSError("模拟写入失败")), \
             mock.patch("workshop.gui.QMessageBox.critical") as critical:
            QTest.mouseClick(dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Save), Qt.MouseButton.LeftButton)
            critical.assert_called_once()
        self.assertTrue(dialog.isVisible())
        self.assertEqual(read_text(job.path("reference")), "旧参考")
        self.assertEqual(self.app.processing_reference_text(job), "旧参考")
        dialog.reject()

    def test_adding_library_file_uses_existing_song_mapping_and_deduplicates(self):
        with mock.patch("workshop.gui.QFileDialog.getOpenFileNames", return_value=([str(self.audio)], "")):
            self.app.add_sources(False)
            self.app.add_sources(False)
        jobs = [job for job in self.app.jobs if job.in_processing]
        self.assertEqual(len(jobs), 1)
        self.assertTrue(jobs[0].existing_song)
        self.assertEqual(jobs[0].target_lyric, "测试歌曲.lrc")

    def test_existing_song_picker_adds_selection_and_review_button_is_removed(self):
        from PySide6.QtWidgets import QTreeWidget, QDialogButtonBox
        dialog = self.app.choose_existing_songs()
        tree = dialog.findChild(QTreeWidget)
        tree.setCurrentItem(tree.topLevelItem(0))
        QTest.mouseClick(dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Ok), Qt.MouseButton.LeftButton)
        APPLICATION.processEvents()
        self.assertEqual(self.app.import_tree.topLevelItemCount(), 1)
        self.assertFalse(any(button.text() == "审阅当前结果" for button in self.app.findChildren(QPushButton)))

    def test_document_save_button_tracks_actual_changes_revert_and_undo(self):
        from PySide6.QtGui import QTextCursor
        self.app.open_song_editor(self.app.editing_song)
        original = self.app.editor.toPlainText()
        self.assertFalse(self.app.lyric_save_button.isEnabled())
        self.app.editor.moveCursor(QTextCursor.MoveOperation.End)
        self.app.editor.insertPlainText("新增文字")
        self.assertTrue(self.app.lyric_save_button.isEnabled())
        self.app.editor.undo()
        self.assertEqual(self.app.editor.toPlainText(), original)
        self.assertFalse(self.app.lyric_save_button.isEnabled())
        self.app.editor.redo()
        self.assertTrue(self.app.lyric_save_button.isEnabled())
        self.app.editor.setPlainText(original)
        self.assertFalse(self.app.lyric_save_button.isEnabled())
        with mock.patch("workshop.gui.save_lyric_document") as save:
            self.app.save_lyrics()
            save.assert_not_called()

    def test_missing_lyric_document_can_be_created_without_changing_playlist(self):
        (self.library / "music/没有歌词.mp3").write_bytes(b"original")
        self.app.scan()
        song = next(song for song in self.app.songs if song.audio.stem == "没有歌词")
        self.app.open_song_editor(song)
        self.assertEqual(self.app.editor.toPlainText(), "")
        self.assertFalse(self.app.lyric_save_button.isEnabled())
        self.edit("[00:01]新歌词\n")
        self.click("保存")
        self.assertEqual(read_text(self.library / "lyrics/没有歌词.lrc"), "[00:01]新歌词\n")
        self.assertEqual(read_text(self.library / "playlists/测试歌单.txt"), "测试歌曲.mp3|测试歌曲.lrc\n")
        self.assertFalse(self.app.lyric_save_button.isEnabled())

    def test_offset_and_instrumental_changes_can_be_undone_and_clear_save_state(self):
        self.app.open_song_editor(self.app.editing_song)
        original = self.app.editor.toPlainText()
        self.app.offset.setValue(0.5)
        self.click("应用偏移")
        self.assertIn("[00:01.500]", self.app.editor.toPlainText())
        self.assertTrue(self.app.lyric_save_button.isEnabled())
        self.app.editor.undo()
        self.assertEqual(self.app.editor.toPlainText(), original)
        self.assertFalse(self.app.lyric_save_button.isEnabled())
        self.click("标为纯音乐")
        self.assertEqual(self.app.editor.toPlainText(), "#INSTRUMENTAL\n")
        self.app.editor.undo()
        self.assertEqual(self.app.editor.toPlainText(), original)
        self.assertFalse(self.app.lyric_save_button.isEnabled())

    def test_document_save_preserves_text_exactly_and_failure_keeps_edits(self):
        text = "\n[00:01]保留空行与空格  \n\n"
        self.edit(text)
        with mock.patch("workshop.gui.save_lyric_document", side_effect=OSError("模拟写入失败")), \
             mock.patch("workshop.gui.QMessageBox.critical") as critical:
            self.click("保存")
            critical.assert_called_once()
        self.assertTrue(self.app.dirty)
        self.assertTrue(self.app.lyric_save_button.isEnabled())
        self.assertEqual(read_text(self.lyric), "[00:01.00]原始歌词\n")
        self.click("保存")
        self.assertEqual(self.lyric.read_bytes(), text.encode("utf-8"))
        self.assertFalse(self.app.lyric_save_button.isEnabled())

    def test_preview_plays_pauses_seeks_and_stops_when_editor_closes(self):
        self.app.open_song_editor(self.app.editing_song)
        self.assertEqual(self.preview.source, self.audio)
        self.assertFalse(self.preview.playing())
        self.assertEqual(self.app.preview_time.text(), "00:00 / 03:00")
        self.click("播放")
        self.assertTrue(self.preview.playing())
        self.assertEqual(self.app.preview_play_button.text(), "暂停")
        self.app.preview_slider.setSliderDown(True)
        self.app.preview_slider.setValue(75000)
        self.assertEqual(self.preview.seeks, [])
        self.assertEqual(self.app.preview_time.text(), "01:15 / 03:00")
        self.app.preview_slider.setSliderDown(False)
        self.assertEqual(self.preview.seeks[-1], 75000)
        self.assertTrue(self.preview.playing())
        self.click("暂停")
        self.assertFalse(self.preview.playing())
        self.app.preview_slider.setValue(30000)
        self.assertEqual(self.preview.at, 30000)
        self.assertFalse(self.preview.playing())
        self.app.preview_volume.setValue(35)
        self.assertEqual(self.preview.volume, 35)
        self.app.lyric_dialog.reject()
        self.assertFalse(self.preview.loaded)
        self.assertFalse(self.app.preview_timer.isActive())

    def test_preview_track_click_and_drag_seek_once_and_keep_playback_state(self):
        from PySide6.QtCore import QPoint
        self.app.open_song_editor(self.app.songs[0])
        APPLICATION.processEvents()
        slider = self.app.preview_slider
        for playing in (True, False):
            self.preview.is_playing = playing
            self.preview.at = 0
            self.app.poll_preview()
            self.preview.seeks.clear()
            point = QPoint(round(slider.width() * .75), slider.height() // 2)
            QTest.mousePress(slider, Qt.MouseButton.LeftButton, pos=point)
            QTest.qWait(80)
            self.assertEqual(self.preview.seeks, [])
            self.assertEqual(self.preview.playing(), playing)
            QTest.mouseRelease(slider, Qt.MouseButton.LeftButton, pos=point)
            self.assertEqual(len(self.preview.seeks), 1)
            self.assertAlmostEqual(self.preview.at / self.preview.duration, .75, delta=.03)
            self.assertEqual(self.preview.playing(), playing)
        self.preview.seeks.clear()
        start = QPoint(round(slider.width() * .25), slider.height() // 2)
        end = QPoint(slider.width() // 2, slider.height() // 2)
        QTest.mousePress(slider, Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(slider, end)
        self.assertEqual(self.preview.seeks, [])
        QTest.mouseRelease(slider, Qt.MouseButton.LeftButton, pos=end)
        self.assertEqual(len(self.preview.seeks), 1)
        self.assertAlmostEqual(self.preview.at / self.preview.duration, .5, delta=.03)

    def test_preview_position_updates_do_not_seek_or_change_lyrics(self):
        self.app.open_song_editor(self.app.editing_song)
        self.preview.at = 61000
        self.app.poll_preview()
        self.assertEqual(self.app.preview_slider.value(), 61000)
        self.assertEqual(self.preview.seeks, [])
        self.assertEqual(self.app.preview_time.text(), "01:01 / 03:00")
        self.assertFalse(self.app.dirty)
        self.assertFalse(self.app.lyric_save_button.isEnabled())

    def test_preview_error_does_not_prevent_editing_and_saving(self):
        with mock.patch.object(self.preview, "load", side_effect=OSError("模拟音频无法解码")):
            self.app.open_song_editor(self.app.editing_song)
        self.assertFalse(self.app.preview_play_button.isEnabled())
        self.assertIn("无法试听", self.app.preview_message.text())
        self.edit("[00:01]仍能保存歌词\n")
        self.click("保存")
        self.assertEqual(read_text(self.lyric), "[00:01]仍能保存歌词\n")

    def test_settings_preserve_player_fields_and_mask_credentials(self):
        config = self.base / "OnScreenMusic.ini"
        atomic_text(config, read_text(config) + "\n[Playback]\nSingleRepeat=true\nPosition=456\n")
        self.app.setting_vars["api_key"].setText("test-only-key")
        self.app.save_setting("api_key")
        parser = read_ini(config)
        self.assertEqual(parser.get("Playback", "Position"), "456")
        self.assertEqual(parser.get("Playback", "SingleRepeat"), "true")
        self.assertEqual(self.app.setting_vars["api_key"].echoMode(), QLineEdit.EchoMode.Password)
        self.assertFalse((self.base / "MusicWorkshop.local.ini").exists())

    def test_settings_save_only_the_selected_tool_and_keep_pending_key(self):
        executable = self.base / "ffmpeg.exe"
        executable.write_bytes(b"test-tool")
        self.app.setting_vars["api_key"].setText("unsaved-key")
        self.app.setting_vars["ffmpeg"].setText(str(executable))
        self.app.save_setting("ffmpeg")
        loaded = Settings.load(self.base)
        self.assertEqual(loaded.ffmpeg, str(executable))
        self.assertEqual(loaded.api_key, "")
        self.assertEqual(self.app.setting_vars["api_key"].text(), "unsaved-key")
        self.assertFalse(self.app.setting_save_buttons["ffmpeg"].isEnabled())
        self.assertTrue(self.app.setting_save_buttons["api_key"].isEnabled())
        self.assertFalse(any(button.text() == "保存设置" for button in self.app.findChildren(QPushButton)))

    def test_tool_detection_saves_one_path_and_download_opens_one_console(self):
        executable = self.base / "whisper-cli.exe"
        executable.write_bytes(b"test-tool")
        with mock.patch("workshop.gui.find_tool", return_value=executable):
            self.app.detect_tool("whisper")
        self.assertEqual(Settings.load(self.base).whisper, str(executable))
        process = mock.Mock()
        process.poll.return_value = None
        with mock.patch("workshop.gui.subprocess.Popen", return_value=process) as launch:
            self.app.download_tool("model")
            self.app.download_tool("model")
            launch.assert_called_once()
        import subprocess
        self.assertEqual(launch.call_args.kwargs["creationflags"], subprocess.CREATE_NEW_CONSOLE)
        args = launch.call_args.args[0]
        self.assertIn("workshop.tool_setup", args)
        self.assertIn("model", args)
        self.assertNotIn("pythonw.exe", Path(args[0]).name.lower())

    def test_download_config_refresh_keeps_unsaved_fields(self):
        process = mock.Mock()
        process.poll.return_value = None
        with mock.patch("workshop.gui.subprocess.Popen", return_value=process):
            self.app.download_tool("model")
        self.app.setting_vars["api_key"].setText("pending-key")
        model = self.base / "tools/custom.bin"
        model.parent.mkdir(exist_ok=True)
        model.write_bytes(b"model")
        latest = Settings.load(self.base)
        latest.model = str(model)
        latest.save(self.base, fields={"model"})
        self.app.poll_tool_windows()
        self.assertEqual(self.app.settings.model, str(model))
        self.assertEqual(self.app.setting_vars["model"].text(), "tools/custom.bin")
        self.assertEqual(self.app.setting_vars["api_key"].text(), "pending-key")

    def test_theme_switch_preserves_edits_and_saves_only_appearance(self):
        from PySide6.QtGui import QPalette
        from PySide6.QtWidgets import QTextBrowser
        self.edit("[00:01.00]未保存的歌词\n")
        self.app.setting_vars["api_key"].setText("pending-key")
        current_key = Settings.load(self.base).api_key
        help_dialog = self.app.help()
        browser = help_dialog.findChild(QTextBrowser)
        help_text = browser.toPlainText()
        original_style = self.app.styleSheet()
        self.app.show_page("settings")
        QTest.mouseClick(self.app.theme_button, Qt.MouseButton.LeftButton)
        APPLICATION.processEvents()
        self.assertEqual(Settings.load(self.base).theme, "dark")
        self.assertEqual(Settings.load(self.base).api_key, current_key)
        self.assertEqual(self.app.setting_vars["api_key"].text(), "pending-key")
        self.assertEqual(self.app.editor.toPlainText(), "[00:01.00]未保存的歌词\n")
        self.assertTrue(self.app.dirty)
        self.assertEqual(browser.toPlainText(), help_text)
        palette = APPLICATION.palette()
        self.assertGreater(palette.color(QPalette.ColorRole.Text).lightness(), palette.color(QPalette.ColorRole.Base).lightness())
        self.assertGreater(palette.color(QPalette.ColorRole.HighlightedText).lightness(), palette.color(QPalette.ColorRole.Highlight).lightness())
        self.assertEqual(self.app.theme_button.text(), "切换浅色")
        QTest.mouseClick(self.app.theme_button, Qt.MouseButton.LeftButton)
        APPLICATION.processEvents()
        self.assertEqual(Settings.load(self.base).theme, "light")
        self.assertEqual(self.app.styleSheet(), original_style)
        self.assertEqual(self.app.theme_button.text(), "切换深色")
        help_dialog.close()

    def test_cleanup_dialog_requires_confirmation_and_preserves_backups_by_default(self):
        from PySide6.QtWidgets import QLabel
        temporary = self.base / 'MusicWorkshopWork/writes/leftover.lrc'
        backup = self.base / 'MusicWorkshopWork/backups/old/lyric.lrc'
        for path in (temporary, backup):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'old data')
        dialog = self.app.cleanup_files()
        clean = next(button for button in dialog.findChildren(QPushButton) if button.text() == '清理')
        deadline = time.monotonic() + 3
        while not clean.isEnabled() and time.monotonic() < deadline:
            QTest.qWait(50)
        self.assertTrue(clean.isEnabled())
        with mock.patch.object(self.app, 'confirm', return_value=False):
            QTest.mouseClick(clean, Qt.MouseButton.LeftButton)
        self.assertTrue(temporary.exists())
        with mock.patch.object(self.app, 'confirm', return_value=True):
            QTest.mouseClick(clean, Qt.MouseButton.LeftButton)
        deadline = time.monotonic() + 3
        while temporary.exists() and time.monotonic() < deadline:
            QTest.qWait(50)
        self.assertFalse(temporary.exists())
        QTest.qWait(150)
        self.assertTrue(backup.exists())
        self.assertTrue(self.lyric.exists())
        self.assertFalse(any('Qt 6' in label.text() for label in self.app.findChildren(QLabel)))
        dialog.close()

    def test_help_is_a_local_html_document(self):
        from PySide6.QtWidgets import QTextBrowser
        dialog = self.app.help()
        browser = dialog.findChild(QTextBrowser)
        self.assertIsNotNone(browser)
        self.assertIn("整理音乐，从这里开始", browser.toPlainText())
        self.assertIn("命令行", browser.toPlainText())
        self.assertIn("<h1", browser.toHtml())
        dialog.close()

    def test_delete_playlist_requires_confirmation_and_preserves_media_and_backup(self):
        self.app.playlist_combo.setCurrentText("测试歌单.txt")
        self.app.load_playlist()
        target = self.library / "playlists/测试歌单.txt"
        original = target.read_bytes()
        with mock.patch.object(self.app, "confirm", return_value=False):
            self.app.delete_playlist()
        self.assertEqual(target.read_bytes(), original)
        with mock.patch.object(self.app, "confirm", return_value=True):
            self.app.delete_playlist()
        self.assertFalse(target.exists())
        backups = list((self.base / "MusicWorkshopWork/backups").glob("*/测试歌单.txt"))
        self.assertEqual(backups[0].read_bytes(), original)
        self.assertTrue(self.audio.exists())
        self.assertTrue(self.lyric.exists())
        self.assertFalse(self.app.delete_playlist_button.isEnabled())

    def test_report_dialog_is_native_qt_readonly(self):
        dialog = self.app.show_text("报告", "报告内容")
        self.assertIsInstance(dialog, QDialog)
        self.assertTrue(dialog.isVisible())
        dialog.close()

    def test_close_saves_original_document_and_waits_for_worker(self):
        job = self.job
        self.edit("[00:01]关闭前的歌词编辑\n")
        with mock.patch("workshop.gui.QMessageBox.question", return_value=QMessageBox.StandardButton.Save):
            self.app.close()
        deadline = time.monotonic() + 3
        while self.app.isVisible() and time.monotonic() < deadline:
            QTest.qWait(50)
        self.assertFalse(self.app.runner.thread.is_alive())
        self.assertFalse(self.app.isVisible())
        self.assertFalse(job.path("candidate").exists())
        self.assertEqual(read_text(self.lyric), "[00:01]关闭前的歌词编辑\n")

    def test_unsaved_close_can_be_cancelled(self):
        self.edit("[00:03.00]保留编辑\n")
        with mock.patch("workshop.gui.QMessageBox.question", return_value=QMessageBox.StandardButton.Cancel):
            self.app.close()
        self.assertTrue(self.app.isVisible())
        self.assertFalse(self.app.closing)
        self.assertTrue(self.app.dirty)

    def test_compact_rows_show_at_least_twice_the_songs(self):
        from workshop.playlists import PlaylistEntry
        self.app.playlist_entries = [PlaylistEntry(f"Song{i:03}.mp3", "song.lrc") for i in range(100)]
        self.app.render_playlist()
        self.app.show_page("playlists")
        APPLICATION.processEvents()
        height = self.app.playlist_list.viewport().height()
        visible = sum(self.app.playlist_list.visualItemRect(self.app.playlist_list.item(i)).top() >= 0
                      and self.app.playlist_list.visualItemRect(self.app.playlist_list.item(i)).bottom() < height
                      for i in range(100))
        old_capacity = height // 72  # Previous 60 px row plus 6 px spacing on either side.
        self.assertGreaterEqual(visible, old_capacity * 2)
        self.assertEqual(self.app.playlist_list.item(0).sizeHint().height(), 30)
        self.assertEqual(self.app.playlist_list.count(), 101)

    def test_remove_visible_song_preserves_scroll_and_other_rows(self):
        from workshop.playlists import PlaylistEntry
        self.app.playlist_entries = [PlaylistEntry(f"Song{i:03}.mp3", "song.lrc") for i in range(100)]
        self.app.render_playlist()
        self.app.show_page("playlists")
        APPLICATION.processEvents()
        scroll = self.app.playlist_list.verticalScrollBar()
        scroll.setValue(1207)
        before = scroll.value()
        top_item = self.app.playlist_list.itemAt(1, 1)
        top_name = top_item.data(Qt.ItemDataRole.UserRole)
        row = self.app.playlist_list.itemWidget(self.app.playlist_list.item(44))
        QTest.mouseClick(row.findChild(QPushButton), Qt.MouseButton.LeftButton)
        APPLICATION.processEvents()
        self.assertEqual(scroll.value(), before)
        self.assertEqual(self.app.playlist_list.itemAt(1, 1).data(Qt.ItemDataRole.UserRole), top_name)
        self.assertIs(self.app.playlist_list.itemWidget(top_item),
                      self.app.playlist_list.itemWidget(self.app.playlist_items[top_name.casefold()]))
        scroll.setValue(scroll.maximum())
        self.app.remove_playlist_song(self.app.playlist_entries[-1])
        APPLICATION.processEvents()
        self.assertEqual(scroll.value(), scroll.maximum())
        self.assertGreater(scroll.value(), 0)

    def test_final_plus_row_opens_dialog_and_cancel_does_not_change_playlist(self):
        self.app.show_page("playlists")
        APPLICATION.processEvents()
        self.assertFalse(self.app.song_dialog.isVisible())
        QTest.mouseClick(self.app.playlist_add_button, Qt.MouseButton.LeftButton)
        self.assertTrue(self.app.song_dialog.isVisible())
        self.app.song_dialog.reject()
        self.assertFalse(self.app.playlist_entries)
        self.app.show_song_dialog()
        self.app.song_picker.setEditText("测试歌曲")
        self.app.add_weight.setValue(2)
        QTest.mouseClick(self.app.add_song_button, Qt.MouseButton.LeftButton)
        APPLICATION.processEvents()
        self.assertFalse(self.app.song_dialog.isVisible())
        self.assertEqual(self.app.playlist_entries[0].weight, 2)
        self.assertIs(self.app.playlist_list.item(self.app.playlist_list.count() - 1), self.app.playlist_add_item)

    def test_save_button_disables_when_edits_are_reverted_or_saved(self):
        self.app.playlist_combo.setCurrentText("测试歌单.txt")
        self.app.load_playlist()
        self.assertFalse(self.app.save_playlist_button.isEnabled())
        entry = self.app.playlist_entries[0]
        row = self.app.playlist_list.itemWidget(self.app.playlist_list.item(0))
        weight, lyric = row.findChild(QSpinBox), row.findChild(QCheckBox)
        weight.setValue(3)
        self.assertTrue(self.app.save_playlist_button.isEnabled())
        weight.setValue(1)
        self.assertFalse(self.app.save_playlist_button.isEnabled())
        lyric.setChecked(False)
        self.assertTrue(self.app.save_playlist_button.isEnabled())
        lyric.setChecked(True)
        self.assertFalse(self.app.save_playlist_button.isEnabled())
        weight.setValue(2)
        self.app.save_playlist()
        self.assertFalse(self.app.save_playlist_button.isEnabled())
        self.assertEqual(entry.weight, 2)

    def test_automatic_load_and_cancelled_switch_restore_playlist_name(self):
        atomic_text(self.library / "playlists/另一歌单.txt", "# 另一份\n测试歌曲.mp3|测试歌曲.lrc\n")
        self.app.scan()
        combo = self.app.playlist_combo
        combo.setCurrentText("测试歌单.txt")
        self.app.load_playlist()
        combo.setCurrentIndex(combo.findText("另一歌单.txt"))
        with mock.patch.object(self.app, "confirm") as confirm:
            combo.activated.emit(combo.currentIndex())
            confirm.assert_not_called()
        self.assertEqual(self.app.playlist_baseline_name, "另一歌单.txt")
        self.assertFalse(self.app.save_playlist_button.isEnabled())
        self.app.change_playlist_entry(self.app.playlist_entries[0], "weight", 2)
        combo.setCurrentIndex(combo.findText("测试歌单.txt"))
        with mock.patch.object(self.app, "confirm", return_value=False):
            combo.activated.emit(combo.currentIndex())
        self.assertEqual(combo.currentText(), "另一歌单.txt")
        self.assertEqual(self.app.playlist_entries[0].weight, 2)
        self.assertTrue(self.app.save_playlist_button.isEnabled())


    def test_playlist_check_opens_broken_file_and_repairs_only_on_request(self):
        for name in ("无歌词", "无需歌词"):
            (self.library / "music" / (name + ".mp3")).write_bytes(b"test-original")
        path = self.library / "playlists/错误歌单.txt"
        original = ("# 保留注释\n测试歌曲.mp3|测试歌曲.lrc\n测试歌曲.mp3|测试歌曲.lrc\n"
                    "失效.mp3|-\n失效.mp3|-\n不是有效行\n../outside.mp3|-\n"
                    "无歌词.mp3|找不到.lrc\n测试歌曲.mp3|-\n无需歌词.mp3|-\n")
        atomic_text(path, original)
        self.app.scan()
        self.app.playlist_combo.setCurrentText(path.name)
        self.app.load_playlist()
        self.app.show_page("playlists")
        self.assertTrue(self.app.repair_playlist_button.isVisible())
        self.assertIn("6 行错误", self.app.playlist_check_label.text())
        self.assertFalse(self.app.save_playlist_button.isEnabled())
        self.assertEqual(read_text(path), original)
        entry = next(entry for entry in self.app.playlist_entries if entry.audio == self.audio.name)
        self.app.change_playlist_entry(entry, "weight", 3)
        self.click("自动修复")
        self.assertTrue(self.app.save_playlist_button.isEnabled())
        self.assertFalse(self.app.repair_playlist_button.isVisible())
        self.assertEqual({entry.audio for entry in self.app.playlist_entries}, {self.audio.name, "无需歌词.mp3"})
        self.assertIn("未发现错误", self.app.playlist_check_label.text())
        self.assertEqual(read_text(path), original)
        self.assertIn("保存歌单后生效", self.app.status.text())
        self.click("保存歌单")
        repaired = read_text(path)
        self.assertEqual(repaired.count("测试歌曲.mp3|测试歌曲.lrc\n"), 3)
        self.assertIn("无需歌词.mp3|-\n", repaired)
        self.assertIn("# 保留注释\n", repaired)
        self.assertNotIn("失效", repaired)
        self.assertNotIn("不是有效行", repaired)
        self.assertNotIn("outside", repaired)
        backups = list((self.base / "MusicWorkshopWork/backups").glob("*/错误歌单.txt"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(read_text(backups[0]), original)
        self.assertFalse(self.app.save_playlist_button.isEnabled())
        self.assertEqual(self.audio.read_bytes(), b"unchanged-original-audio")
        self.assertEqual(read_text(self.lyric), "[00:01.00]原始歌词\n")

    def test_opening_bad_playlist_does_not_silently_change_it_or_prompt_on_switch(self):
        path = self.library / "playlists/待修复.txt"
        atomic_text(path, "# 保留\n错误格式\n失效.mp3|-\n")
        self.app.playlist_combo.setCurrentText(path.name)
        self.app.load_playlist()
        self.assertEqual(len(self.app.playlist_issues), 2)
        self.assertIn("错误格式", self.app.playlist_text())
        with mock.patch.object(self.app, "confirm") as confirm:
            self.app.playlist_combo.setCurrentText("测试歌单.txt")
            self.app.load_playlist()
            confirm.assert_not_called()
        self.assertFalse(self.app.playlist_issues)
        self.assertFalse(self.app.playlist_unparsed_lines)
        self.assertTrue(self.app.repair_playlist_button.isHidden())
        self.assertIn("未发现错误", self.app.playlist_check_label.text())
        self.assertEqual(read_text(path), "# 保留\n错误格式\n失效.mp3|-\n")
        self.assertFalse(any(button.text() == "歌单检查" for button in self.app.findChildren(QPushButton)))

    def test_repaired_playlist_still_requires_saving_before_switch(self):
        path = self.library / "playlists/格式错误.txt"
        atomic_text(path, "测试歌曲.mp3|测试歌曲.lrc\n错误格式\n")
        self.app.playlist_combo.setCurrentText(path.name)
        self.app.load_playlist()
        self.app.repair_playlist()
        self.app.playlist_combo.setCurrentText("测试歌单.txt")
        with mock.patch.object(self.app, "confirm", return_value=False) as confirm:
            self.app.load_playlist()
            confirm.assert_called_once()
        self.assertEqual(self.app.playlist_combo.currentText(), path.name)
        self.assertTrue(self.app.save_playlist_button.isEnabled())
        self.assertIn("错误格式", read_text(path))

    def test_save_rechecks_files_and_offers_repair_in_page(self):
        self.app.playlist_combo.setCurrentText("测试歌单.txt")
        self.app.load_playlist()
        self.app.change_playlist_entry(self.app.playlist_entries[0], "weight", 2)
        self.lyric.unlink()
        with mock.patch.object(self.app, "confirm") as confirm:
            self.app.save_playlist()
            confirm.assert_not_called()
        self.assertEqual(len(self.app.playlist_issues), 2)
        self.assertFalse(self.app.save_playlist_button.isEnabled())
        self.assertFalse(self.app.repair_playlist_button.isHidden())
        self.assertEqual(read_text(self.library / "playlists/测试歌单.txt"), "测试歌曲.mp3|测试歌曲.lrc\n")
        self.app.repair_playlist()
        self.assertFalse(self.app.playlist_entries)
        self.assertTrue(self.app.save_playlist_button.isEnabled())


if __name__ == "__main__":
    unittest.main()
