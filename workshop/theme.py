"""Light and dark Qt colors; fonts and layouts use device-independent coordinates."""
from pathlib import Path
import re
from PySide6.QtGui import QColor, QFont, QPalette, QIcon, QPixmap
from PySide6.QtWidgets import QApplication

STYLESHEET = """
QWidget { color: #263247; background: #ffffff; font-size: 13px; }
QFrame#header { border-bottom: 1px solid #e3e8ef; }
QFrame#navigation { background: #f5f7fa; border-right: 1px solid #e3e8ef; }
QFrame#navigation QLabel { background: transparent; }
QFrame#footer { background: #f8fafc; border-top: 1px solid #e3e8ef; }
QFrame#footer QLabel { background: transparent; }
QFrame#card { background: #f8fafc; border: 1px solid #e3e8ef; border-radius: 10px; }
QFrame#taskRow { border: 1px solid #e3e8ef; border-radius: 9px; background: white; }
QFrame#playlistRow { border: 0; border-bottom: 1px solid #f0f3f7; background: white; }
QFrame#playlistRow QLabel#section { font-size: 13px; font-weight: 400; }
QFrame#playlistRow QSpinBox { padding: 1px 8px; border-radius: 4px; }
QFrame#playlistRow QCheckBox { padding: 0; }
QPushButton#playlistAddButton { color: #326ce5; background: #f5f8fe; border: 0;
    border-radius: 4px; padding: 0; font-size: 25px; }
QPushButton#playlistAddButton:hover { background: #e7eefc; }
QPushButton#rowAction { padding: 0; border-color: transparent; background: transparent; font-size: 20px; color: #738198; }
QPushButton#rowAction:hover { color: #c74646; background: #fff0f0; border-color: #ffe1e1; }
QListWidget { border: 0; background: transparent; outline: 0; }
QProgressBar { border: 0; background: #edf1f7; border-radius: 4px; height: 8px; max-height: 8px; }
QProgressBar::chunk { background: #7da7f4; border-radius: 4px; }
QAbstractItemView { selection-background-color: #dceaff; selection-color: #183d78; }
QLabel#brand { font-size: 21px; font-weight: 600; color: #182a43; }
QLabel#title { font-size: 22px; font-weight: 600; color: #182a43; }
QLabel#section { font-size: 14px; font-weight: 600; }
QLabel#muted { color: #738198; font-size: 12px; background: transparent; }
QLabel#badge { color: #4872a8; background: #edf3fb; padding: 7px 12px; border-radius: 12px; }
QPushButton { border: 1px solid #dce3ed; border-radius: 7px; padding: 8px 12px; background: #ffffff; }
QPushButton:hover { background: #f0f5fd; border-color: #a6c2ee; }
QPushButton:pressed { background: #e5eefc; border-color: #759edf; }
QPushButton:focus { border-color: #326ce5; }
QPushButton#compactButton { padding: 3px 10px; }
QPushButton:disabled { color: #9ca7b8; background: #f5f7fa; border-color: #e4e9f0; }
QPushButton#primaryButton { background: #326ce5; border-color: #326ce5; color: white; }
QPushButton#primaryButton:hover { background: #2860d4; border-color: #2860d4; }
QPushButton#primaryButton:pressed { background: #2054c1; border-color: #2054c1; }
QPushButton#primaryButton:disabled { color: #a1acc0; background: #e4e9f0; border-color: #e4e9f0; }
QPushButton#navButton { text-align: left; background: transparent; color: #627189;
    padding: 12px 15px; border: 1px solid transparent; font-size: 14px; }
QPushButton#navButton:hover { background: #edf2fa; }
QPushButton#navButton:checked { background: #e7eefc; color: #245cca; font-weight: 600; }
QPushButton#navButton:focus { border-color: #a6c2ee; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox { border: 1px solid #dce3ed; border-radius: 6px;
    padding: 7px 9px; background: #ffffff; selection-background-color: #dceaff; selection-color: #183d78; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus { border-color: #326ce5; }
QComboBox { padding-right: 24px; }
QComboBox::drop-down { border: 0; width: 24px; }
QComboBox::down-arrow { image: url("@ICONS@/down.svg"); width: 12px; height: 12px; }
QComboBox QAbstractItemView { border: 1px solid #dce3ed; outline: 0; selection-background-color: #e7eefc; selection-color: #183d78; }
QComboBox QAbstractItemView::item { padding: 0 10px; border: 0; }
QComboBox QAbstractItemView::item:selected { background: #e7eefc; color: #183d78; border: 0; }
QPlainTextEdit { border: 1px solid #dce3ed; border-radius: 7px; padding: 9px;
    font-size: 14px; background: #ffffff; selection-background-color: #dceaff; selection-color: #183d78; }
QPlainTextEdit:focus { border-color: #326ce5; }
QPlainTextEdit:read-only { background: #fafbfd; }
QTreeWidget { border: 1px solid #e3e8ef; border-radius: 7px; background: #ffffff;
    alternate-background-color: #fafbfd; outline: 0; }
QTreeWidget::item { padding: 9px 6px; border-bottom: 1px solid #f2f4f8; }
QTreeWidget::item:selected { background: #e7eefc; color: #245cca; }
QTreeWidget::item:hover:!selected { background: #f3f6fb; }
QHeaderView::section { background: #f5f7fa; color: #738198; border: 0;
    border-bottom: 1px solid #e3e8ef; padding: 9px 6px; font-size: 12px; }
QTabWidget::pane { border: 1px solid #e3e8ef; border-radius: 7px; top: -1px; }
QTabBar::tab { border: 1px solid transparent; padding: 10px 13px; color: #738198; }
QTabBar::tab:selected { color: #245cca; background: #edf3fc; border-radius: 6px; }
QTabBar::tab:hover:!selected { background: #f5f7fa; }
QCheckBox { spacing: 8px; padding: 3px 0; background: transparent; }
QCheckBox:disabled { color: #9ca7b8; }
QCheckBox::indicator, QTreeWidget::indicator { width: 15px; height: 15px; border: 1px solid #b8c6da;
    border-radius: 3px; background: white; }
QCheckBox::indicator:checked, QTreeWidget::indicator:checked { background: #326ce5; border-color: #326ce5; image: url("@ICONS@/check.svg"); }
QCheckBox::indicator:hover, QTreeWidget::indicator:hover { border-color: #326ce5; }
QCheckBox::indicator:disabled, QTreeWidget::indicator:disabled { background: #f1f4f8; border-color: #dfe5ef; }
QSpinBox::up-button, QDoubleSpinBox::up-button { subcontrol-origin: border; subcontrol-position: top right;
    width: 18px; border: 0; }
QSpinBox::down-button, QDoubleSpinBox::down-button { subcontrol-origin: border; subcontrol-position: bottom right;
    width: 18px; border: 0; }
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow { image: url("@ICONS@/up.svg"); width: 10px; height: 10px; }
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow { image: url("@ICONS@/down.svg"); width: 10px; height: 10px; }
QSplitter::handle { background: transparent; }
QSplitter::handle:hover { background: #e3e8ef; }
QScrollArea { background: transparent; }
QScrollBar:vertical { width: 10px; background: #f6f8fb; margin: 0; }
QScrollBar:horizontal { height: 10px; background: #f6f8fb; margin: 0; }
QScrollBar::handle { background: #c7d2e2; border-radius: 4px; min-height: 24px; min-width: 24px; }
QScrollBar::handle:hover { background: #aebed3; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
"""


POPUP_STYLESHEET = """QListView { background: white; color: #263247; border: 1px solid #dce3ed;
    outline: 0; selection-background-color: #dceaff; selection-color: #183d78; }
    QListView::item { padding: 0 10px; }"""

NAVIGATION_PATHS = {
    "library": '<path d="M9 17V5l11-2v12M9 8l11-2"/><ellipse cx="6" cy="17" rx="3" ry="2.5"/><ellipse cx="17" cy="15" rx="3" ry="2.5"/>',
    "import": '<path d="M4 6h16M4 12h16M4 18h16"/><circle cx="8" cy="6" r="2"/><circle cx="16" cy="12" r="2"/><circle cx="10" cy="18" r="2"/>',
    "playlists": '<path d="M8 5h12M8 12h12M8 19h12M3 5h.1M3 12h.1M3 19h.1"/>',
    "tasks": '<rect x="4" y="3" width="16" height="18" rx="3"/><path d="m8 12 3 3 5-6"/>',
    "settings": '<polygon points="10,2 14,2 15,5 17,6 20,5 22,9 20,11 20,13 22,15 20,19 17,18 15,19 14,22 10,22 9,19 7,18 4,19 2,15 4,13 4,11 2,9 4,5 7,6 9,5"/><circle cx="12" cy="12" r="3"/>',
}


def navigation_icon(page, mode="light"):
    icon = QIcon()
    for state, shade in ((QIcon.State.Off, "#627189"), (QIcon.State.On, "#245cca")):
        color = colors(shade, mode)
        for size in (18, 36, 54):
            svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 24 24">'
                   f'<g fill="none" stroke="{color}" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">'
                   + NAVIGATION_PATHS[page] + '</g></svg>')
            pixmap = QPixmap()
            pixmap.loadFromData(svg.encode("utf-8"), "SVG")
            icon.addPixmap(pixmap, QIcon.Mode.Normal, state)
    return icon

# One mapping also covers the local HTML guide and small widget-specific styles.
DARK_COLORS = {
    "white": "#202735", "#ffffff": "#202735", "#263247": "#e5eaf3",
    "#e3e8ef": "#354154", "#f5f7fa": "#191f2a", "#f8fafc": "#191f2a",
    "#fafbfd": "#1c2330", "#f0f3f7": "#303b4e", "#f5f8fe": "#26364d",
    "#326ce5": "#477fe8", "#e7eefc": "#304969", "#738198": "#a2aec2",
    "#c74646": "#ff9b9b", "#fff0f0": "#482c36", "#ffe1e1": "#70404c",
    "#edf1f7": "#303b4e", "#7da7f4": "#8db5ff", "#dceaff": "#304969",
    "#183d78": "#eef4ff", "#182a43": "#f0f4fa", "#4872a8": "#b3ccf9",
    "#edf3fb": "#283a54", "#dce3ed": "#3c495e", "#f0f5fd": "#2c3b52",
    "#a6c2ee": "#6b94d8", "#e5eefc": "#344969", "#759edf": "#8db5ff",
    "#9ca7b8": "#7e8aa0", "#e4e9f0": "#293243", "#2860d4": "#548bed",
    "#2054c1": "#326bce", "#a1acc0": "#7e8aa0", "#627189": "#b4bfd1",
    "#edf2fa": "#26364d", "#245cca": "#a7c7ff", "#f2f4f8": "#303b4e",
    "#f3f6fb": "#28374e", "#edf3fc": "#283a54", "#b8c6da": "#74839c",
    "#f1f4f8": "#293243", "#dfe5ef": "#3c495e", "#f6f8fb": "#191f2a",
    "#c7d2e2": "#53637d", "#aebed3": "#7488a7", "#a85818": "#f3ba7f",
    "#f3f7fe": "#283a54",
}


def colors(text, mode="light"):
    if mode != "dark":
        return text
    text = re.sub(r"(?<![-\w])color:\s*(?:white|#ffffff)\b", "color: #f5f8ff", text)
    return re.sub(r"#[0-9a-fA-F]{6}\b|\bwhite\b", lambda match: DARK_COLORS.get(match[0].lower(), match[0]), text)


def apply_theme(window, mode="light"):
    application = QApplication.instance()
    palette = application.style().standardPalette()
    for role, value in {
        "Window": "#f8fafc", "WindowText": "#263247", "Base": "#ffffff",
        "AlternateBase": "#fafbfd", "Text": "#263247", "Button": "#ffffff",
        "ButtonText": "#263247", "Highlight": "#dceaff", "HighlightedText": "#183d78",
        "ToolTipBase": "#ffffff", "ToolTipText": "#263247", "PlaceholderText": "#738198",
        "Link": "#245cca", "LinkVisited": "#4872a8",
    }.items():
        palette.setColor(getattr(QPalette.ColorRole, role), QColor(colors(value, mode)))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.WindowText, QPalette.ColorRole.ButtonText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(colors("#9ca7b8", mode)))
    application.setPalette(palette)
    window.setFont(QFont("Microsoft YaHei UI", 10))
    window.setStyleSheet(colors(STYLESHEET, mode).replace("@ICONS@", (Path(__file__).parent / "icons").resolve().as_posix()))
