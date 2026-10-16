"""Explicit cleanup of known work files, without traversing links or deleting results."""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import queue
import threading


LABELS = {"temporary": "处理临时文件", "downloads": "下载缓存（安装包及未完成下载）", "backups": "历史备份（旧歌词、歌单及程序备份）"}


@dataclass(frozen=True)
class CleanupFile:
    relative: str
    category: str
    size: int
    modified: int


def category(path):
    parts = Path(path).parts
    if not parts:
        return None
    if parts[0] == "writes" or (len(parts) > 3 and parts[0] == "jobs" and parts[2] == "runs"):
        return "temporary"
    if parts[0] in {"backups", "config-backups", "program-backups"}:
        return "backups"
    if parts[0] == "downloads":
        return "backups" if len(parts) > 1 and parts[1].startswith("backup-") else "downloads"
    return None


def safe_path(work, relative):
    relative = Path(relative)
    if relative.is_absolute() or ".." in relative.parts or not category(relative):
        raise ValueError("清理路径不属于可清理的工作文件。")
    work = Path(work).absolute()
    if work.is_symlink() or work.is_junction():
        raise ValueError("工作目录是链接，已停止清理。")
    current = work
    for part in relative.parts:
        current = current / part
        if current.is_symlink() or current.is_junction():
            raise ValueError("清理路径包含链接，已跳过。")
    if not current.resolve().is_relative_to(work.resolve()):
        raise ValueError("清理路径超出工作目录。")
    return current


def collect_cleanup(work):
    work = Path(work).absolute()
    if work.is_symlink() or work.is_junction():
        raise ValueError("工作目录是链接，已停止清理。")
    files = []
    for folder, directories, names in os.walk(work, followlinks=False):
        parent = Path(folder)
        directories[:] = [name for name in directories if not (parent / name).is_symlink() and not (parent / name).is_junction()]
        for name in names:
            relative = (parent / name).relative_to(work)
            kind = category(relative)
            if kind:
                try:
                    path = safe_path(work, relative)
                    info = path.stat()
                    if path.is_file():
                        files.append(CleanupFile(relative.as_posix(), kind, info.st_size, info.st_mtime_ns))
                except (OSError, ValueError):
                    continue
    return files


def clean_files(work, files):
    count = size = skipped = 0
    for item in files:
        try:
            path = safe_path(work, item.relative)
            info = path.stat()
            if info.st_size != item.size or info.st_mtime_ns != item.modified or not path.is_file():
                skipped += 1
                continue
            # Individual checked files only; no recursive directory deletion.
            path.unlink()
            count += 1
            size += item.size
        except (OSError, ValueError):
            skipped += 1
    return count, size, skipped


def readable_size(size):
    return f"{size / 1024**3:.2f} GB" if size >= 1024**3 else f"{size / 1024**2:.1f} MB"


def show_cleanup_dialog(owner):
    from PySide6.QtCore import QTimer, Qt
    from PySide6.QtWidgets import QCheckBox, QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

    class CleanupDialog(QDialog):
        working = False

        def reject(self):
            if not self.working:
                super().reject()

        def closeEvent(self, event):
            event.ignore() if self.working else super().closeEvent(event)

    dialog = CleanupDialog(owner)
    dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
    dialog.setWindowTitle("清理临时文件")
    dialog.setModal(True)
    dialog.resize(570, 300)
    layout = QVBoxLayout(dialog)
    note = QLabel("默认只清理临时文件；任务结果、已安装工具和模型保留。\n历史备份需要单独勾选，删除后将无法恢复旧版本。")
    note.setWordWrap(True)
    layout.addWidget(note)
    options = {}
    for kind, title in LABELS.items():
        check = QCheckBox(title)
        check.setChecked(kind == "temporary")
        check.setEnabled(False)
        layout.addWidget(check)
        options[kind] = check
    status = QLabel("正在统计可清理文件…")
    layout.addWidget(status)
    actions = QHBoxLayout()
    actions.addStretch()
    close = QPushButton("关闭")
    close.clicked.connect(dialog.reject)
    actions.addWidget(close)
    clean = QPushButton("清理")
    clean.setEnabled(False)
    actions.addWidget(clean)
    layout.addLayout(actions)
    work = Path(owner.settings.work)
    results = queue.SimpleQueue()
    inventory = []

    def background(callback, event):
        def run():
            try:
                results.put((event, callback()))
            except Exception as error:
                results.put(("error", str(error)))
        threading.Thread(target=run, daemon=True).start()

    def selected():
        return [item for item in inventory if options[item.category].isChecked()]

    def update():
        items = selected()
        clean.setEnabled(bool(items) and not dialog.working)
        status.setText(f"已选 {len(items)} 个文件 · {readable_size(sum(item.size for item in items))}")

    def begin():
        items = selected()
        scope = "、".join(LABELS[kind] for kind, check in options.items() if check.isChecked())
        if not items or not owner.confirm("确认清理", f"清理{scope}？\n共 {len(items)} 个文件，{readable_size(sum(item.size for item in items))}。\n所选文件将永久删除。"):
            return
        dialog.working = True
        clean.setEnabled(False)
        close.setEnabled(False)
        for check in options.values():
            check.setEnabled(False)
        status.setText("正在清理…")
        background(lambda: clean_files(work, items), "cleaned")

    def poll():
        try:
            event, data = results.get_nowait()
        except queue.Empty:
            return
        if event == "inventory":
            inventory[:] = data
            for kind, check in options.items():
                files = [item for item in inventory if item.category == kind]
                check.setText(f"{LABELS[kind]} · {readable_size(sum(item.size for item in files))}")
                check.setEnabled(bool(files))
            update()
        else:
            dialog.working = False
            close.setEnabled(True)
            if event == "cleaned":
                count, size, skipped = data
                status.setText(f"已清理 {count} 个文件，释放 {readable_size(size)}" + (f"；{skipped} 个文件因变化或占用已跳过。" if skipped else "。"))
            else:
                status.setText("无法清理：" + data)

    for check in options.values():
        check.toggled.connect(update)
    clean.clicked.connect(begin)
    timer = QTimer(dialog)
    timer.timeout.connect(poll)
    timer.start(100)
    background(lambda: collect_cleanup(work), "inventory")
    dialog.show()
    return dialog
