"""Qt Widgets layouts for the independent music manager."""
from pathlib import Path
from . import theme
from PySide6.QtCore import Qt, QSignalBlocker, QEvent, QItemSelectionModel, QSize
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox,
    QDoubleSpinBox, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QCompleter, QListWidget, QPlainTextEdit, QProgressBar, QPushButton, QScrollArea, QSpinBox, QSplitter, QStackedWidget,
    QTabWidget, QTreeWidget, QVBoxLayout, QWidget, QSizePolicy, QDialog, QStyledItemDelegate, QStyle, QStyleOptionSlider, QSlider, QListView, QProxyStyle)

LANGUAGES = {"中文": "zh", "自动检测": "auto", "英语": "en", "日语": "ja", "韩语": "ko",
    "粤语": "yue", "法语": "fr", "德语": "de", "西班牙语": "es", "俄语": "ru",
    "意大利语": "it", "葡萄牙语": "pt"}
PAGES = {"library": "歌曲资料", "import": "处理歌曲", "playlists": "歌单管理",
         "tasks": "任务记录", "settings": "参数设置"}
PROCESSING_FIELDS = {1: "process_convert", 2: "process_recognize", 3: "process_ai", 4: "allow_repetition"}
PROCESSING_ACTIVE_ROLE = Qt.ItemDataRole.UserRole + 1
PROCESSING_EXISTING_ROLE = Qt.ItemDataRole.UserRole + 2


class ProcessingTree(QTreeWidget):
    def selectionCommand(self, index, event=None):
        # Editing a step must not shrink an already selected batch to just this song.
        if index.column() in PROCESSING_FIELDS and event is not None and event.type() in {
                QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease, QEvent.Type.MouseButtonDblClick}:
            return QItemSelectionModel.SelectionFlag.NoUpdate
        return super().selectionCommand(index, event)


class ProcessingStepDelegate(QStyledItemDelegate):
    @staticmethod
    def enabled(index):
        if index.column() not in PROCESSING_FIELDS:
            return True
        identity = index.siblingAtColumn(0)
        if identity.data(PROCESSING_ACTIVE_ROLE):
            return False
        if index.column() == 1 and identity.data(PROCESSING_EXISTING_ROLE):
            return False
        if index.column() == 4:
            return index.siblingAtColumn(2).data(Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Checked.value
        return True

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        if not self.enabled(index):
            option.state &= ~QStyle.StateFlag.State_Enabled

    def editorEvent(self, event, model, option, index):
        return super().editorEvent(event, model, option, index) if self.enabled(index) else False


class ComboPopupStyle(QProxyStyle):
    def styleHint(self, hint, option=None, widget=None, returnData=None):
        if hint == QStyle.StyleHint.SH_ComboBox_Popup:
            return 0
        if hint == QStyle.StyleHint.SH_ComboBox_PopupFrameStyle:
            return QFrame.Shape.NoFrame.value
        return super().styleHint(hint, option, widget, returnData)


class ComboBox(QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.popup_style = ComboPopupStyle("Fusion")
        self.popup_style.setParent(self)
        self.setStyle(self.popup_style)
        view = QListView(self)
        view.setFrameShape(QFrame.Shape.NoFrame)
        view.setSpacing(0)
        view.setUniformItemSizes(True)
        view.setItemDelegate(SongItemDelegate(view))
        self.setView(view)
        view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setMaxVisibleItems(12)


class SongPicker(ComboBox):
    def showPopup(self):
        self.completer().setCompletionPrefix(self.currentText())
        self.completer().complete()


class SongItemDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        size.setHeight(32)
        return size


class SeekSlider(QSlider):
    """Click the track to seek, with one committed change on mouse release."""
    def __init__(self, parent=None):
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.track_drag = False

    def position_value(self, position):
        option = QStyleOptionSlider()
        self.initStyleOption(option)
        groove = self.style().subControlRect(QStyle.ComplexControl.CC_Slider, option, QStyle.SubControl.SC_SliderGroove, self)
        handle = self.style().subControlRect(QStyle.ComplexControl.CC_Slider, option, QStyle.SubControl.SC_SliderHandle, self)
        span = max(0, groove.width() - handle.width())
        offset = round(position.x() - groove.x() - handle.width() / 2)
        return QStyle.sliderValueFromPosition(self.minimum(), self.maximum(), offset, span, option.upsideDown)

    def mousePressEvent(self, event):
        option = QStyleOptionSlider()
        self.initStyleOption(option)
        handle = self.style().subControlRect(QStyle.ComplexControl.CC_Slider, option, QStyle.SubControl.SC_SliderHandle, self)
        if event.button() == Qt.MouseButton.LeftButton and not handle.contains(event.position().toPoint()):
            self.track_drag = True
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            self.setSliderDown(True)
            self.setValue(self.position_value(event.position()))
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.track_drag:
            self.setValue(self.position_value(event.position()))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.track_drag and event.button() == Qt.MouseButton.LeftButton:
            self.setValue(self.position_value(event.position()))
            self.track_drag = False
            self.setSliderDown(False)
            event.accept()
            return
        super().mouseReleaseEvent(event)


class LyricEditorDialog(QDialog):
    def reject(self):
        owner = self.parentWidget()
        if owner.ready_to_close or owner.guard(owner.prompt_dirty):
            owner.stop_preview()
            super().reject()


class WorkshopUi:
    def build_shell(self):
        shell = QWidget()
        self.setCentralWidget(shell)
        layout = QVBoxLayout(shell)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        header = QFrame()
        header.setObjectName("header")
        row = QHBoxLayout(header)
        row.setContentsMargins(24, 18, 24, 18)
        logo = QLabel()
        logo.setObjectName("logo")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setFixedSize(42, 42)
        logo.setPixmap(self.windowIcon().pixmap(QSize(42, 42), self.devicePixelRatioF()))
        row.addWidget(logo)
        brand = QVBoxLayout()
        brand.setSpacing(2)
        self.label(brand, "音乐管理", "brand").setWordWrap(False)
        self.label(brand, "ON SCREEN MUSIC  /  MusicWorkshop", "muted").setWordWrap(False)
        row.addLayout(brand, 1)
        row.addStretch()
        layout.addWidget(header)
        body = QHBoxLayout()
        body.setSpacing(0)
        navigation = QFrame()
        navigation.setObjectName("navigation")
        navigation.setFixedWidth(170)
        nav = QVBoxLayout(navigation)
        nav.setContentsMargins(14, 22, 14, 18)
        nav.setSpacing(8)
        self.nav_buttons = {}
        for page, label in PAGES.items():
            button = self.button(nav, label, lambda p=page: self.show_page(p))
            button.setObjectName("navButton")
            button.setCheckable(True)
            button.setIcon(theme.navigation_icon(page, self.settings.theme))
            button.setIconSize(QSize(18, 18))
            self.nav_buttons[page] = button
        nav.addStretch()
        body.addWidget(navigation)
        self.content = QStackedWidget()
        self.frames, self.layouts = {}, {}
        for page in PAGES:
            frame = QWidget()
            page_layout = QVBoxLayout(frame)
            page_layout.setContentsMargins(24, 20, 24, 18)
            page_layout.setSpacing(12)
            self.frames[page], self.layouts[page] = frame, page_layout
            self.content.addWidget(frame)
        body.addWidget(self.content, 1)
        layout.addLayout(body, 1)
        footer = QFrame()
        footer.setObjectName("footer")
        row = QHBoxLayout(footer)
        row.setContentsMargins(22, 9, 22, 9)
        self.status = self.label(row, "选择歌曲，或导入新素材。", "muted")
        layout.addWidget(footer)

    def label(self, layout, text, role=""):
        widget = QLabel(text)
        if role:
            widget.setObjectName(role)
        widget.setWordWrap(True)
        layout.addWidget(widget)
        return widget

    def button(self, layout, text, callback, primary=False):
        button = QPushButton(text)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        if primary:
            button.setObjectName("primaryButton")
        button.clicked.connect(lambda _: self.guard(callback))
        layout.addWidget(button)
        return button

    def row(self, layout):
        row = QHBoxLayout()
        row.setSpacing(8)
        layout.addLayout(row)
        return row

    def make_text(self, readonly=False):
        widget = QPlainTextEdit()
        widget.setReadOnly(readonly)
        widget.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        widget.setTabStopDistance(32)
        return widget

    def make_tree(self, headers, tree_type=QTreeWidget):
        tree = tree_type()
        tree.setHeaderLabels(headers)
        tree.setRootIsDecorated(False)
        tree.setAlternatingRowColors(True)
        tree.setUniformRowHeights(True)
        tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        tree.header().setStretchLastSection(False)
        tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for index in range(1, len(headers)):
            tree.header().setSectionResizeMode(index, QHeaderView.ResizeMode.ResizeToContents)
        return tree

    @staticmethod
    def tree_ids(tree):
        return [item.data(0, Qt.ItemDataRole.UserRole) for item in tree.selectedItems()]

    @staticmethod
    def select_ids(tree, ids):
        wanted = set(ids)
        for index in range(tree.topLevelItemCount()):
            item = tree.topLevelItem(index)
            item.setSelected(item.data(0, Qt.ItemDataRole.UserRole) in wanted)

    @staticmethod
    def put(widget, text, readonly=None):
        with QSignalBlocker(widget):
            widget.setPlainText(text)
            widget.document().setModified(False)
        if readonly is not None:
            widget.setReadOnly(readonly)

    @staticmethod
    def get(widget):
        return widget.toPlainText()

    def build_library(self):
        layout = self.layouts["library"]
        row = self.row(layout)
        self.label(row, "歌曲资料库", "title")
        row.addStretch()
        self.button(row, "刷新资料", self.scan)
        self.library_root_label = self.label(layout, self.settings.library, "muted")
        row = self.row(layout)
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索歌曲…")
        row.addWidget(self.search, 1)
        self.library_summary = self.label(layout, "", "muted")
        self.song_tree = self.make_tree(["歌曲", ""])
        self.song_tree.setStyleSheet("QTreeWidget::item { padding: 0 8px; }")
        self.song_tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.song_tree.setColumnWidth(1, 118)
        layout.addWidget(self.song_tree, 1)

    def build_lyric_editor(self):
        self.lyric_dialog = LyricEditorDialog(self)
        self.lyric_dialog.setWindowTitle("编辑歌词")
        self.lyric_dialog.resize(860, 690)
        self.lyric_dialog.setMinimumSize(640, 520)
        details = QVBoxLayout(self.lyric_dialog)
        details.setContentsMargins(20, 18, 20, 18)
        details.setSpacing(9)
        self.song_title = self.label(details, "请选择歌曲", "section")
        self.lyric_file_label = self.label(details, "", "muted")
        controls = self.row(details)
        self.preview_play_button = self.button(controls, "播放", self.toggle_preview)
        self.preview_play_button.setEnabled(False)
        self.preview_slider = SeekSlider()
        self.preview_slider.setEnabled(False)
        controls.addWidget(self.preview_slider, 1)
        self.preview_time = self.label(controls, "00:00 / 00:00", "muted")
        self.preview_time.setWordWrap(False)
        self.preview_slider.valueChanged.connect(lambda value: self.guard(lambda: self.seek_preview(value)))
        self.preview_slider.sliderReleased.connect(lambda: self.guard(lambda: self.seek_preview(self.preview_slider.value())))
        volume = self.row(details)
        self.label(volume, "音量", "muted")
        self.preview_volume = QSlider(Qt.Orientation.Horizontal)
        self.preview_volume.setRange(0, 100)
        self.preview_volume.setValue(20)
        self.preview_volume.setFixedWidth(110)
        self.preview_volume.valueChanged.connect(lambda value: self.guard(lambda: self.preview.set_volume(value)))
        volume.addWidget(self.preview_volume)
        volume.addStretch()
        self.preview_message = self.label(details, "", "muted")
        self.preview_message.hide()
        self.editor = self.make_text()
        self.editor.setPlaceholderText("在这里编辑 LRC 歌词文字与时间标签…")
        details.addWidget(self.editor, 1)
        controls = self.row(details)
        self.label(controls, "整体偏移 / 秒")
        self.offset = QDoubleSpinBox()
        self.offset.setRange(-3600, 3600)
        self.offset.setDecimals(3)
        self.offset.setSingleStep(0.1)
        self.offset.setMaximumWidth(105)
        controls.addWidget(self.offset)
        self.button(controls, "应用偏移", self.offset_lyrics)
        controls.addStretch()
        self.button(controls, "标为纯音乐", self.mark_instrumental)
        actions = self.row(details)
        actions.addStretch()
        self.lyric_save_button = self.button(actions, "保存", self.save_lyrics, True)
        self.lyric_save_button.setEnabled(False)
        self.button(actions, "关闭", self.lyric_dialog.reject)

    def build_import(self):
        layout = self.layouts["import"]
        self.label(layout, "处理歌曲", "title")
        self.label(layout, "逐首选择处理步骤；参考歌词通过行内按钮单独编辑。", "muted")
        row = self.row(layout)
        self.button(row, "添加文件", lambda: self.add_sources(False))
        self.button(row, "添加文件夹", lambda: self.add_sources(True))
        self.button(row, "选择现有歌曲", self.choose_existing_songs)
        row.addStretch()
        self.label(row, "识别语言")
        self.processing_language = ComboBox()
        self.processing_language.addItems(list(LANGUAGES))
        row.addWidget(self.processing_language)
        self.remove_all_processing_button = self.button(row, "移除全部", self.remove_all_processing_jobs)
        self.remove_all_processing_button.setEnabled(False)
        self.remove_all_processing_button.setToolTip("移除所有未在处理的条目，保留原文件、结果和任务记录。")
        self.processing_hint = self.label(layout, "现有歌曲保留原音频；识别和校对成功后自动更新歌词。", "muted")
        self.import_tree = self.make_tree(["歌曲", "格式响度", "识别歌词", "AI 校对", "允许重复", "参考歌词", "状态", ""], ProcessingTree)
        self.import_tree.setStyleSheet("QTreeWidget::item { padding: 0 6px; }")
        self.import_tree.setItemDelegate(ProcessingStepDelegate(self.import_tree))
        for column, width in enumerate([90, 82, 76, 90, 94, 110, 36], 1):
            self.import_tree.header().setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
            self.import_tree.setColumnWidth(column, width)
        for column, text in {1: "统一格式与响度，现有歌曲保留原音频。", 2: "本地识别歌词，不上传音频。",
                             3: "使用本首歌曲的参考歌词进行 AI 校对。",
                             4: "允许大量重复歌词；确认重复内容属于歌曲原词时勾选，仅本地识别时生效。"}.items():
            self.import_tree.headerItem().setToolTip(column, text)
        layout.addWidget(self.import_tree, 1)
        actions = self.row(layout)
        self.start_processing_button = self.button(actions, "开始所选处理", self.start_import, True)
        self.start_processing_button.setEnabled(False)
        actions.addStretch()
        self.label(layout, "整项处理成功后，最终歌词自动写入资料库；失败或终止保留原歌词。", "muted")

    def build_playlists(self):
        layout = self.layouts["playlists"]
        self.label(layout, "歌单管理", "title")
        row = self.row(layout)
        self.playlist_combo = ComboBox()
        self.playlist_combo.setEditable(True)
        self.playlist_combo.setPlaceholderText("选择或输入歌单名.txt")
        row.addWidget(self.playlist_combo, 1)
        self.save_playlist_button = self.button(row, "保存歌单", self.save_playlist, True)
        self.save_playlist_button.setEnabled(False)
        self.delete_playlist_button = self.button(row, "删除歌单", self.delete_playlist)
        self.delete_playlist_button.setEnabled(False)
        self.button(row, "新歌单", self.new_playlist)
        self.button(row, "导入 DPL", self.import_dpl)
        check_row = self.row(layout)
        self.playlist_check_label = self.label(check_row, "打开歌单后自动检查。", "muted")
        self.playlist_check_label.setWordWrap(False)
        check_row.setStretch(0, 1)
        self.repair_playlist_button = self.button(check_row, "自动修复", self.repair_playlist)
        self.repair_playlist_button.setToolTip("移除格式错误、缺失文件或歌词配置冲突的行，保存歌单后生效。")
        self.repair_playlist_button.hide()
        self.playlist_summary = self.label(layout, "选择歌单，逐首调整权重和歌词。", "muted")
        self.playlist_list = QListWidget()
        self.playlist_list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.playlist_list.setSpacing(0)
        self.playlist_list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        layout.addWidget(self.playlist_list, 1)
        self.song_dialog = QDialog(self)
        self.song_dialog.setWindowTitle("添加歌曲")
        self.song_dialog.setModal(True)
        self.song_dialog.resize(640, 260)
        dialog_layout = QVBoxLayout(self.song_dialog)
        dialog_layout.setContentsMargins(20, 18, 20, 18)
        self.label(dialog_layout, "选择一首歌曲", "section")
        self.song_picker = SongPicker()
        self.song_picker.setEditable(True)
        self.song_picker.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.song_picker.lineEdit().setPlaceholderText("输入歌名开头，或从列表选择…")
        self.song_picker.setMinimumWidth(280)
        self.song_completer = QCompleter(self)
        self.song_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.song_completer.setFilterMode(Qt.MatchFlag.MatchStartsWith)
        self.song_completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.song_completer.setMaxVisibleItems(12)
        popup = self.song_completer.popup()
        popup.setFont(self.font())
        popup.setItemDelegate(SongItemDelegate(popup))
        popup.setUniformItemSizes(True)
        popup.setStyleSheet(theme.colors(theme.POPUP_STYLESHEET, self.settings.theme))
        self.song_picker.setCompleter(self.song_completer)
        dialog_layout.addWidget(self.song_picker)
        row = self.row(dialog_layout)
        self.label(row, "权重")
        self.add_weight = QSpinBox()
        self.add_weight.setRange(1, 10000)
        row.addWidget(self.add_weight)
        self.add_lyrics = QCheckBox("加载歌词")
        self.add_lyrics.setChecked(True)
        row.addWidget(self.add_lyrics)
        row.addStretch()
        self.button(row, "取消", self.song_dialog.reject)
        self.add_song_button = self.button(row, "添加", self.add_playlist_song, True)
        self.add_song_button.setEnabled(False)
        self.song_picker.currentTextChanged.connect(self.update_song_choice)
        row = self.row(dialog_layout)
        self.song_choice_hint = self.label(row, "输入完整歌名或选择匹配项；同一首歌只能添加一次。", "muted")
        self.playlist_combo.currentTextChanged.connect(lambda _: self.update_playlist_save_state())
        self.playlist_combo.lineEdit().textEdited.connect(self.edit_playlist_name)
        self.playlist_combo.lineEdit().returnPressed.connect(lambda: self.guard(self.load_typed_playlist))

    def build_tasks(self):
        layout = self.layouts["tasks"]
        self.label(layout, "任务记录", "title")
        self.task_summary = self.label(layout, "暂无任务", "muted")
        self.task_list = QListWidget()
        self.task_list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.task_list.setSpacing(8)
        layout.addWidget(self.task_list, 1)
        self.label(layout, "× 终止进行中的任务 · ⌫ 删除已结束的任务记录", "muted")

    def build_settings(self):
        layout = self.layouts["settings"]
        self.label(layout, "参数设置", "title")
        self.label(layout, "资料随软件所在文件夹一起使用，移动整个文件夹即可。", "muted")
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        panel = QWidget()
        box = QVBoxLayout(panel)
        box.setContentsMargins(0, 0, 8, 0)
        box.setSpacing(14)
        self.setting_vars = {}
        self.setting_save_buttons, self.setting_status_labels = {}, {}
        for field, label in [("ffmpeg", "FFmpeg"), ("whisper", "本地识别程序"),
                              ("model", "本地识别模型 · large-v3（下载约 3.1 GB）"), ("api_key", "DeepSeek 接口密钥")]:
            self.label(box, label, "section")
            row = self.row(box)
            edit = QLineEdit(self.setting_text(field))
            if field == "api_key":
                edit.setEchoMode(QLineEdit.EchoMode.Password)
                edit.setPlaceholderText("仅保存在本机统一配置中")
            self.setting_vars[field] = edit
            row.addWidget(edit, 1)
            if field != "api_key":
                self.button(row, "选择文件", lambda f=field: self.choose_tool(f))
            self.setting_save_buttons[field] = self.button(row, "保存", lambda f=field: self.save_setting(f))
            self.setting_save_buttons[field].setEnabled(False)
            if field != "api_key":
                actions = self.row(box)
                self.button(actions, "自动查找", lambda f=field: self.detect_tool(f))
                self.button(actions, "下载", lambda f=field: self.download_tool(f))
                self.setting_status_labels[field] = self.label(actions, "", "muted")
                actions.setStretch(2, 1)
            edit.textChanged.connect(lambda _, f=field: self.update_setting_state(f))
            self.update_setting_state(field)
        self.label(box, "工作文件固定保存在同目录的 MusicWorkshopWork。", "muted")
        cleanup_row = self.row(box)
        self.button(cleanup_row, "清理临时文件", self.cleanup_files)
        cleanup_hint = self.label(cleanup_row, "查看占用并选择清理范围。", "muted")
        cleanup_hint.setWordWrap(False)
        cleanup_row.addStretch()
        box.addStretch()
        scroll.setWidget(panel)
        layout.addWidget(scroll, 1)
        self.label(layout, "播放器与音乐管理共用 OnScreenMusic.ini。密钥仅保存在本机；本地识别不上传音频。", "muted")
        links = self.row(layout)
        help_button = self.button(links, "使用说明", self.help)
        about_button = self.button(links, "关于", self.about)
        help_button.setFixedWidth(140)
        about_button.setFixedWidth(140)
        self.theme_button = self.button(links, "切换浅色" if self.settings.theme == "dark" else "切换深色", self.toggle_theme)
        self.theme_button.setFixedWidth(140)
        links.addStretch()

    def make_task_row(self, job):
        widget = QFrame()
        widget.setObjectName("taskRow")
        row = QHBoxLayout(widget)
        row.setContentsMargins(18, 14, 14, 14)
        info = QVBoxLayout()
        info.setSpacing(5)
        name = self.label(info, job.stem, "section")
        name.setWordWrap(False)
        name.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        description = self.label(info, "", "muted")
        description.setWordWrap(False)
        description.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        row.addLayout(info, 1)
        progress_box = QVBoxLayout()
        stage = self.label(progress_box, "", "muted")
        stage.setWordWrap(False)
        progress = QProgressBar()
        progress.setFixedWidth(210)
        progress.setTextVisible(False)
        progress_box.addWidget(progress)
        row.addLayout(progress_box)
        action = self.button(row, "×", lambda j=job: self.task_action(j))
        action.setObjectName("rowAction")
        action.setFixedSize(36, 36)
        return widget, description, stage, progress, action

    def make_playlist_row(self, entry):
        widget = QFrame()
        widget.setObjectName("playlistRow")
        row = QHBoxLayout(widget)
        row.setContentsMargins(10, 1, 6, 1)
        name = self.label(row, Path(entry.audio).stem, "section")
        name.setWordWrap(False)
        name.setToolTip(entry.audio)
        name.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        row.setStretch(0, 1)
        weight = QSpinBox()
        weight.setRange(1, 10000)
        weight.setValue(entry.weight)
        weight.setPrefix("权重  ")
        weight.setFixedWidth(128)
        weight.setFixedHeight(24)
        weight.valueChanged.connect(lambda value, e=entry: self.change_playlist_entry(e, "weight", value))
        row.addWidget(weight)
        lyric = QCheckBox("加载歌词")
        lyric.setChecked(entry.use_lyrics)
        lyric.setToolTip(entry.lyric)
        lyric.toggled.connect(lambda value, e=entry: self.change_playlist_entry(e, "use_lyrics", value))
        row.addWidget(lyric)
        action = self.button(row, "×", lambda e=entry: self.remove_playlist_song(e))
        action.setObjectName("rowAction")
        action.setToolTip("从歌单移除这首歌")
        action.setFixedSize(26, 26)
        return widget

    def make_playlist_add_row(self):
        widget = QWidget()
        row = QHBoxLayout(widget)
        row.setContentsMargins(0, 3, 0, 3)
        self.playlist_add_button = self.button(row, "＋", self.show_song_dialog)
        self.playlist_add_button.setObjectName("playlistAddButton")
        self.playlist_add_button.setToolTip("添加一首歌曲")
        self.playlist_add_button.setAccessibleName("添加一首歌曲")
        return widget
