from __future__ import annotations

import os
import html
import re
import shutil
from pathlib import Path

from PyQt6.QtCore import QSettings, QSize, QTimer, QUrl, Qt
from PyQt6.QtGui import QAction, QActionGroup, QColor, QDesktopServices, QFont, QIcon, QKeySequence, QPainter, QPalette, QPixmap, QTextCursor, QTextDocument
from PyQt6.QtWidgets import QApplication, QCheckBox, QDialog, QFileDialog, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox, QPlainTextEdit, QPushButton, QSizePolicy, QSplitter, QStatusBar, QStyle, QToolBar, QToolButton, QVBoxLayout, QWidget
from PyQt6.QtWebEngineCore import QWebEngineSettings
from PyQt6.QtWebEngineWidgets import QWebEngineView

try:
    from .config import APP_AUTHOR, APP_COPYRIGHT, APP_NAME, APP_THEME_QSS, DEFAULT_MARKDOWN, GITHUB_RELEASES_URL, MAX_RECENT_FILES, MAX_SEARCH_FILE_BYTES, MAX_SEARCH_RESULTS, ORG_NAME, THEMES, VERSION
    from .editor import MarkdownEditor
    from .document_tabs import DocumentTabs
    from .navigation import NavigationRail
    from .ui_icons import ui_icon
    from .preferences import PreferencesDialog, Typography
    from .pdf_export import PdfExporter, PdfResult
    from .pdf_options import PdfOptionsDialog
    from .toast import UpdateToast
    from .updates import Release, UpdateChecker, UpdateResult
    from .i18n import SUPPORTED_LANGUAGES, translate
    from .renderer import MarkdownRenderer
    from .scroll_sync import ScrollSynchronizer
    from .utils import SearchHit, as_bool, coerce_splitter_sizes, is_markdown_file, read_text_file, save_settings_list, settings_list, write_text_atomic
    from .web_page import LinkInterceptorPage
    from .workspace import WorkspacePanel
except ImportError:
    from config import APP_AUTHOR, APP_COPYRIGHT, APP_NAME, APP_THEME_QSS, DEFAULT_MARKDOWN, GITHUB_RELEASES_URL, MAX_RECENT_FILES, MAX_SEARCH_FILE_BYTES, MAX_SEARCH_RESULTS, ORG_NAME, THEMES, VERSION
    from editor import MarkdownEditor
    from document_tabs import DocumentTabs
    from navigation import NavigationRail
    from ui_icons import ui_icon
    from preferences import PreferencesDialog, Typography
    from pdf_export import PdfExporter, PdfResult
    from pdf_options import PdfOptionsDialog
    from toast import UpdateToast
    from updates import Release, UpdateChecker, UpdateResult
    from i18n import SUPPORTED_LANGUAGES, translate
    from renderer import MarkdownRenderer
    from scroll_sync import ScrollSynchronizer
    from utils import SearchHit, as_bool, coerce_splitter_sizes, is_markdown_file, read_text_file, save_settings_list, settings_list, write_text_atomic
    from web_page import LinkInterceptorPage
    from workspace import WorkspacePanel

class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.settings = QSettings(ORG_NAME, APP_NAME)
        self.theme = str(self.settings.value("theme", "light"))
        if self.theme not in THEMES:
            self.theme = "light"
        self.language = str(self.settings.value("language", "it"))
        if self.language not in SUPPORTED_LANGUAGES:
            self.language = "it"
        self.autosave_enabled = as_bool(self.settings.value("autosave_enabled", True), True)
        self.sync_preview_scroll_enabled = as_bool(self.settings.value("sync_preview_scroll_enabled", True), True)
        self.typography = Typography.load(self.settings)
        self.check_updates_on_startup = as_bool(self.settings.value("check_updates_on_startup", True), True)
        self.available_release: Release | None = None
        self._manual_update_check = False
        self.view_mode = "writing"
        self._split_sizes = [650, 720]
        self._stack_sizes = [1, 1]
        self._sidebar_requested = as_bool(self.settings.value("sidebar_visible", True), True)
        self._sidebar_compact_open = False
        self._sidebar_width = 224
        self._compact_layout = False
        self.current_path: Path | None = None
        self.document_paths: dict[MarkdownEditor, Path | None] = {}
        self.document_autosave_timers: dict[MarkdownEditor, QTimer] = {}
        self.workspace_dir: Path | None = self._load_workspace_dir()
        self.recent_files: list[Path] = self._load_recent_files()
        self._loading = False
        self._last_find_text = ""

        self.renderer = MarkdownRenderer(self.theme)
        self.renderer.typography = self.typography

        self.setWindowTitle(APP_NAME)
        self.setFont(QFont("Segoe UI", 10))
        screen = self.screen().availableGeometry()
        self.resize(min(1180, screen.width() - 48), min(760, screen.height() - 48))

        self.preview = QWebEngineView()
        self.preview.setPage(LinkInterceptorPage(self.preview))
        self.preview.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        self.preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.scroll_sync = ScrollSynchronizer(
            self.preview, lambda: self.editor,
            lambda: self.sync_preview_scroll_enabled and self.view_mode == "split", self,
        )

        self.find_box = QLineEdit()
        self.find_box.setPlaceholderText("Trova nel testo...")
        self.find_box.returnPressed.connect(self.find_next)
        self.find_case_checkbox = QCheckBox("Maiuscole")

        self.update_timer = QTimer(self)
        self.update_timer.setSingleShot(True)
        self.update_timer.setInterval(220)
        self.update_timer.timeout.connect(self.update_preview)

        self.document_tabs = DocumentTabs()
        self.document_tabs.setTabsClosable(True)
        self.document_tabs.setMovable(True)
        self.document_tabs.currentChanged.connect(self.on_current_tab_changed)
        self.document_tabs.tabCloseRequested.connect(self.close_document_tab)

        self.workspace_panel = WorkspacePanel(self)
        self.workspace_panel.set_workspace(self.workspace_dir)
        self.workspace_panel.refresh_recent(self.recent_files)

        self._build_ui()
        self._create_document_tab(DEFAULT_MARKDOWN, None, modified=False)
        self._build_actions()
        self._build_statusbar()
        self.apply_language()
        self.apply_theme(self.theme)
        self.restore_ui_settings()
        self.update_preview()
        self.update_outline()
        self.update_window_title()
        self.update_status()
        self.update_toast = UpdateToast(self)
        self.update_toast.activated.connect(self.open_release_page)
        self.update_checker = UpdateChecker(self)
        self.update_checker.finished.connect(self.on_update_check_finished)
        self.update_checker.busy_changed.connect(lambda busy: self.actions["check_updates"].setEnabled(not busy))
        self.pdf_exporter = PdfExporter(self)
        self.pdf_exporter.finished.connect(self.on_pdf_export_finished)
        self.pdf_exporter.busy_changed.connect(lambda busy: self.actions["export_pdf"].setEnabled(not busy))

    def tr(self, key: str, **kwargs) -> str:
        return translate(self.language, key, **kwargs)

    @property
    def editor(self) -> MarkdownEditor:
        editor = self.document_tabs.currentWidget()
        if isinstance(editor, MarkdownEditor):
            return editor
        raise RuntimeError("No active document editor")

    def _create_document_tab(self, text: str = "", path: Path | None = None, *, modified: bool = False) -> MarkdownEditor:
        path = path.resolve() if path is not None else None
        editor = MarkdownEditor(self.theme)
        editor.apply_typography(self.typography.editor_font, self.typography.editor_size)
        editor.set_readable_width(self.view_mode == "writing")
        editor.textChanged.connect(self.on_text_changed)
        editor.cursorPositionChanged.connect(self.update_status)
        editor.verticalScrollBar().valueChanged.connect(lambda value, doc=editor: self.scroll_sync.editor_scrolled(doc))
        editor.imagesDropped.connect(self.insert_dropped_images)
        timer = QTimer(editor)
        timer.setSingleShot(True)
        timer.setInterval(1500)
        timer.timeout.connect(lambda doc=editor: self.autosave_document(doc))
        self.document_autosave_timers[editor] = timer

        self._loading = True
        editor.setPlainText(text)
        editor.document().setModified(modified)
        self._loading = False
        if isinstance(getattr(self, "actions", None), dict):
            wrap = self.actions["wrap"].isChecked()
            editor.setLineWrapMode(
                QPlainTextEdit.LineWrapMode.WidgetWidth
                if wrap
                else QPlainTextEdit.LineWrapMode.NoWrap
            )
            editor.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff if wrap else Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        self.document_paths[editor] = path
        index = self.document_tabs.addTab(editor, self._tab_title_for(editor))
        self.document_tabs.setCurrentIndex(index)
        self.current_path = path
        return editor

    def _tab_title_for(self, editor: MarkdownEditor) -> str:
        path = self.document_paths.get(editor)
        name = path.name if path else self.tr("untitled")
        return f"{name} *" if editor.document().isModified() else name

    def update_current_tab_title(self) -> None:
        self.update_tab_title(self.editor)

    def update_tab_title(self, editor: MarkdownEditor) -> None:
        index = self.document_tabs.indexOf(editor)
        if index >= 0:
            self.document_tabs.setTabText(index, self._tab_title_for(editor))
            path = self.document_paths.get(editor)
            if path:
                self.document_tabs.setTabToolTip(index, str(path))

    def set_current_path(self, path: Path | None) -> None:
        self.current_path = path
        self.document_paths[self.editor] = path
        self.update_current_tab_title()

    def on_current_tab_changed(self, _index: int) -> None:
        if not hasattr(self, "document_tabs") or self.document_tabs.count() == 0:
            return
        try:
            self.current_path = self.document_paths.get(self.editor)
        except RuntimeError:
            self.current_path = None
        if hasattr(self, "preview"):
            self.update_preview()
        if hasattr(self, "workspace_panel"):
            self.update_outline()
        if hasattr(self, "status_label"):
            self.update_window_title()
            self.update_status()

    def close_document_tab(self, index: int) -> None:
        if index < 0:
            return
        self.document_tabs.setCurrentIndex(index)
        if not self.maybe_save():
            return

        editor = self.document_tabs.widget(index)
        self.document_tabs.removeTab(index)
        if isinstance(editor, MarkdownEditor):
            timer = self.document_autosave_timers.pop(editor, None)
            if timer:
                timer.stop()
            self.document_paths.pop(editor, None)
            editor.deleteLater()

        if self.document_tabs.count() == 0:
            self._create_document_tab("", None, modified=False)
        self.on_current_tab_changed(self.document_tabs.currentIndex())

    def _load_workspace_dir(self) -> Path | None:
        raw = str(self.settings.value("workspace_dir", "") or "")
        if raw:
            path = Path(raw)
            if path.exists() and path.is_dir():
                return path
        return None

    def _load_recent_files(self) -> list[Path]:
        paths: list[Path] = []
        seen: set[str] = set()
        for value in settings_list(self.settings.value("recent_files")):
            path = Path(value)
            key = str(path.resolve()) if path.exists() else str(path)
            if key not in seen:
                paths.append(path)
                seen.add(key)
        return paths[:MAX_RECENT_FILES]

    def _build_ui(self) -> None:
        self.format_toolbar = QToolBar()
        self.format_toolbar.setObjectName("formatToolbar")
        self.format_toolbar.setMovable(False)
        self.format_toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.format_toolbar.setIconSize(QSize(16, 16))
        self.format_toolbar.setFixedHeight(32)

        self.editor_panel = QWidget()
        editor_layout = QVBoxLayout(self.editor_panel)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(0)
        editor_layout.addWidget(self.format_toolbar)
        editor_layout.addWidget(self.document_tabs.pages, 1)

        self.preview_panel = QWidget()
        preview_layout = QVBoxLayout(self.preview_panel)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(0)
        self.preview_label = QLabel(self.tr("preview"))
        self.preview_label.setObjectName("panelCaption")
        self.preview_label.setFixedHeight(32)
        preview_layout.addWidget(self.preview_label)
        preview_layout.addWidget(self.preview, 1)

        self.editor_preview_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.editor_preview_splitter.addWidget(self.editor_panel)
        self.editor_preview_splitter.addWidget(self.preview_panel)
        self.editor_preview_splitter.setChildrenCollapsible(False)
        self.editor_preview_splitter.setHandleWidth(3)
        self.editor_preview_splitter.setSizes([650, 720])

        self.find_bar = QWidget()
        self.find_bar.setObjectName("findBar")
        search_layout = QHBoxLayout(self.find_bar)
        search_layout.setContentsMargins(12, 8, 12, 8)
        search_layout.addWidget(self.find_box, 1)
        search_layout.addWidget(self.find_case_checkbox)
        self.find_prev_button = QPushButton(self.tr("previous"))
        self.find_prev_button.clicked.connect(self.find_previous)
        self.find_button = QPushButton(self.tr("next"))
        self.find_button.clicked.connect(self.find_next)
        self.find_close_button = QToolButton()
        self.find_close_button.setText("×")
        self.find_close_button.clicked.connect(self.hide_find_bar)
        search_layout.addWidget(self.find_prev_button)
        search_layout.addWidget(self.find_button)
        search_layout.addWidget(self.find_close_button)
        self.find_bar.hide()

        self.document_area = QWidget()
        content_layout = QVBoxLayout(self.document_area)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        content_layout.addWidget(self.find_bar)
        content_layout.addWidget(self.editor_preview_splitter, 1)

        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.addWidget(self.workspace_panel)
        self.main_splitter.addWidget(self.document_area)
        self.main_splitter.setStretchFactor(1, 1)
        self.main_splitter.setChildrenCollapsible(False)
        self.main_splitter.setHandleWidth(1)
        self.main_splitter.setSizes([224, 956])
        self.navigation = NavigationRail()
        self.navigation.section_selected.connect(self.show_sidebar_section)
        self.navigation.preferences_requested.connect(self.show_preferences)
        shell = QWidget()
        shell_layout = QHBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)
        shell_layout.addWidget(self.navigation)
        shell_layout.addWidget(self.main_splitter, 1)
        self.setCentralWidget(shell)
        self.main_splitter.splitterMoved.connect(self._remember_sidebar_width)

    def _document_icon(self, label: str, accent: str) -> QIcon:
        pixmap = QPixmap(36, 36)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QColor("#6b7280"))
        painter.setBrush(QColor("#ffffff"))
        painter.drawRoundedRect(7, 3, 22, 30, 4, 4)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(accent))
        painter.drawRoundedRect(9, 20, 18, 9, 2, 2)

        font = QFont()
        font.setBold(True)
        font.setPointSize(6 if len(label) > 3 else 7)
        painter.setFont(font)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(9, 20, 18, 9, Qt.AlignmentFlag.AlignCenter, label)
        painter.end()

        return QIcon(pixmap)

    def _build_actions(self) -> None:
        toolbar = QToolBar("Comandi")
        self.main_toolbar = toolbar
        toolbar.setObjectName("mainToolbar")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(18, 18))
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        toolbar.setFixedHeight(44)
        self.addToolBar(toolbar)

        def decorate(action: QAction, icon: QStyle.StandardPixmap, tooltip: str) -> None:
            action.setIcon(self.style().standardIcon(icon))
            action.setToolTip(tooltip)

        menu_file = self.menuBar().addMenu("File")
        menu_edit = self.menuBar().addMenu("Modifica")
        menu_view = self.menuBar().addMenu("Vista")
        menu_workspace = self.menuBar().addMenu("Workspace")
        menu_export = self.menuBar().addMenu("Export")
        menu_help = self.menuBar().addMenu(self.tr("menu_help"))
        menu_language = menu_view.addMenu("Lingua")
        self.menus = {
            "file": menu_file,
            "edit": menu_edit,
            "view": menu_view,
            "workspace": menu_workspace,
            "export": menu_export,
            "language": menu_language,
            "help": menu_help,
        }
        self.application_menu = QMenu(self)
        for menu in (menu_file, menu_edit, menu_view, menu_workspace, menu_export, menu_help):
            self.application_menu.addMenu(menu)
        self.application_menu_button = QToolButton()
        self.application_menu_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.application_menu_button.setMenu(self.application_menu)
        self.application_menu_button.setObjectName("applicationMenu")
        toolbar.addWidget(self.application_menu_button)
        self.menuBar().hide()
        menu_action = QAction(self)
        menu_action.setShortcut(QKeySequence("F10"))
        menu_action.triggered.connect(self.application_menu_button.showMenu)
        self.addAction(menu_action)

        new_action = QAction("Nuovo", self)
        new_action.setShortcut(QKeySequence.StandardKey.New)
        new_action.triggered.connect(self.new_file)
        decorate(new_action, QStyle.StandardPixmap.SP_FileIcon, "Nuovo documento")
        toolbar.addAction(new_action)
        menu_file.addAction(new_action)

        new_note_action = QAction("Nuova nota nel workspace", self)
        new_note_action.setShortcut(QKeySequence("Ctrl+Shift+N"))
        new_note_action.triggered.connect(self.new_note_in_workspace)
        decorate(new_note_action, QStyle.StandardPixmap.SP_FileDialogNewFolder, "Nuova nota nel workspace")
        menu_file.addAction(new_note_action)
        menu_workspace.addAction(new_note_action)

        open_action = QAction("Apri", self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self.open_file)
        decorate(open_action, QStyle.StandardPixmap.SP_DialogOpenButton, "Apri file")
        toolbar.addAction(open_action)
        menu_file.addAction(open_action)

        open_workspace_action = QAction("Apri cartella workspace", self)
        open_workspace_action.setShortcut(QKeySequence("Ctrl+Shift+O"))
        open_workspace_action.triggered.connect(self.choose_workspace)
        decorate(open_workspace_action, QStyle.StandardPixmap.SP_DirOpenIcon, "Apri workspace")
        menu_workspace.addAction(open_workspace_action)

        save_action = QAction("Salva", self)
        save_action.setShortcut(QKeySequence.StandardKey.Save)
        save_action.triggered.connect(self.save_file)
        decorate(save_action, QStyle.StandardPixmap.SP_DialogSaveButton, "Salva file")
        toolbar.addAction(save_action)
        menu_file.addAction(save_action)

        save_as_action = QAction("Salva come", self)
        save_as_action.setShortcut(QKeySequence.StandardKey.SaveAs)
        save_as_action.triggered.connect(self.save_file_as)
        menu_file.addAction(save_as_action)

        toolbar.addSeparator()
        menu_file.addSeparator()

        export_html_action = QAction("Esporta HTML", self)
        export_html_action.setShortcut(QKeySequence("Ctrl+Shift+H"))
        export_html_action.triggered.connect(self.export_html)
        export_html_action.setIcon(self._document_icon("HTML", "#2563eb"))
        export_html_action.setToolTip("Esporta il documento come HTML")
        menu_export.addAction(export_html_action)

        export_pdf_action = QAction("Esporta PDF", self)
        export_pdf_action.setShortcut(QKeySequence("Ctrl+Shift+P"))
        export_pdf_action.triggered.connect(self.export_pdf)
        export_pdf_action.setIcon(self._document_icon("PDF", "#dc2626"))
        export_pdf_action.setToolTip("Esporta il documento come PDF")
        menu_export.addAction(export_pdf_action)

        bold_action = QAction("Grassetto", self)
        bold_action.setShortcut(QKeySequence("Ctrl+B"))
        bold_action.triggered.connect(lambda: self.wrap_selection("**", "**", self.tr("text_placeholder")))
        bold_action.setToolTip("Grassetto")
        menu_edit.addAction(bold_action)

        italic_action = QAction("Corsivo", self)
        italic_action.setShortcut(QKeySequence("Ctrl+I"))
        italic_action.triggered.connect(lambda: self.wrap_selection("*", "*", self.tr("text_placeholder")))
        italic_action.setToolTip("Corsivo")
        menu_edit.addAction(italic_action)

        code_action = QAction("Codice", self)
        code_action.setShortcut(QKeySequence("Ctrl+K"))
        code_action.triggered.connect(lambda: self.wrap_selection("`", "`", self.tr("code_placeholder")))
        code_action.setToolTip("Codice inline")
        menu_edit.addAction(code_action)

        code_block_action = QAction("Blocco codice", self)
        code_block_action.setShortcut(QKeySequence("Ctrl+Shift+K"))
        code_block_action.triggered.connect(self.insert_code_block)
        code_block_action.setToolTip("Blocco codice")
        self.format_buttons: dict[str, QToolButton] = {}
        for key, action, label in (("bold", bold_action, "B"), ("italic", italic_action, "I"), ("code", code_action, "</>")):
            button = QToolButton()
            button.setText(label)
            button.clicked.connect(lambda checked=False, command=action: command.trigger())
            action.changed.connect(lambda command=action, control=button: control.setEnabled(command.isEnabled()))
            self.format_toolbar.addWidget(button)
            self.format_buttons[key] = button
        self.format_toolbar.addSeparator()
        menu_edit.addAction(code_block_action)

        heading_action = QAction("H2", self)
        heading_action.triggered.connect(lambda: self.prefix_current_line("## "))
        self.format_toolbar.addAction(heading_action)
        menu_edit.addAction(heading_action)

        list_action = QAction("Lista", self)
        list_action.triggered.connect(lambda: self.prefix_current_line("- "))
        self.format_toolbar.addAction(list_action)
        menu_edit.addAction(list_action)

        quote_action = QAction("Quote", self)
        quote_action.triggered.connect(lambda: self.prefix_current_line("> "))
        self.format_toolbar.addAction(quote_action)
        menu_edit.addAction(quote_action)

        link_action = QAction("Link", self)
        link_action.setShortcut(QKeySequence("Ctrl+Shift+L"))
        link_action.triggered.connect(self.insert_link)
        link_action.setToolTip("Inserisci link")
        menu_edit.addAction(link_action)

        image_action = QAction("Immagine", self)
        image_action.setShortcut(QKeySequence("Ctrl+Shift+I"))
        image_action.triggered.connect(self.insert_image)
        image_action.setToolTip("Inserisci immagine")
        menu_edit.addAction(image_action)

        table_action = QAction("Tabella", self)
        table_action.setShortcut(QKeySequence("Ctrl+Shift+T"))
        table_action.triggered.connect(self.insert_table)
        table_action.setToolTip("Inserisci tabella")
        menu_edit.addAction(table_action)

        self.insert_button = QToolButton()
        self.insert_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        insert_menu = QMenu(self.insert_button)
        for action in (link_action, image_action, table_action, code_block_action):
            insert_menu.addAction(action)
        self.insert_button.setMenu(insert_menu)
        self.format_toolbar.addSeparator()
        self.format_toolbar.addWidget(self.insert_button)

        self.document_tabs.setMinimumWidth(100)
        self.document_tabs.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.document_tabs.setUsesScrollButtons(True)
        toolbar.addWidget(self.document_tabs)

        self.view_group = QActionGroup(self)
        self.view_group.setExclusive(True)
        self.view_actions: dict[str, QAction] = {}
        for mode, key, shortcut in (("writing", "writing", "Ctrl+Alt+1"), ("split", "split_view", "Ctrl+Alt+2"), ("reading", "reading", "Ctrl+Alt+3")):
            action = QAction(self.tr(key), self)
            action.setCheckable(True)
            action.setChecked(mode == self.view_mode)
            action.setShortcut(QKeySequence(shortcut))
            action.triggered.connect(lambda checked, value=mode: self.set_view_mode(value) if checked else None)
            self.view_group.addAction(action)
            self.view_actions[mode] = action
            toolbar.addAction(action)
            menu_view.addAction(action)
        menu_view.addSeparator()
        toolbar.addSeparator()

        self.export_button = QToolButton()
        self.export_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.export_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.export_button.setMenu(menu_export)
        toolbar.addWidget(self.export_button)

        search_workspace_action = QAction("Cerca nel workspace", self)
        search_workspace_action.setShortcut(QKeySequence("Ctrl+Shift+F"))
        search_workspace_action.triggered.connect(self.focus_workspace_search)
        decorate(search_workspace_action, QStyle.StandardPixmap.SP_FileDialogContentsView, "Cerca nel workspace")
        menu_workspace.addAction(search_workspace_action)

        toggle_sidebar_action = QAction("Mostra/nascondi sidebar", self)
        toggle_sidebar_action.setShortcut(QKeySequence("Ctrl+Alt+S"))
        toggle_sidebar_action.triggered.connect(self.toggle_sidebar)
        menu_view.addAction(toggle_sidebar_action)

        theme_action = QAction("Tema scuro" if self.theme == "light" else "Tema chiaro", self)
        theme_action.setShortcut(QKeySequence("Ctrl+T"))
        theme_action.triggered.connect(self.toggle_theme)
        decorate(theme_action, QStyle.StandardPixmap.SP_BrowserReload, "Cambia tema")
        menu_view.addAction(theme_action)

        autosave_action = QAction("Autosave", self)
        autosave_action.setCheckable(True)
        autosave_action.setChecked(self.autosave_enabled)
        autosave_action.triggered.connect(self.toggle_autosave)
        menu_file.addAction(autosave_action)

        wrap_action = QAction("A capo automatico", self)
        wrap_action.setCheckable(True)
        wrap_action.setChecked(True)
        wrap_action.triggered.connect(self.toggle_line_wrap)
        menu_view.addAction(wrap_action)

        sync_scroll_action = QAction("Sincronizza scroll anteprima", self)
        sync_scroll_action.setCheckable(True)
        sync_scroll_action.setChecked(self.sync_preview_scroll_enabled)
        sync_scroll_action.setShortcut(QKeySequence("Ctrl+Alt+P"))
        sync_scroll_action.triggered.connect(self.toggle_preview_scroll_sync)
        menu_view.addAction(sync_scroll_action)

        self.language_group = QActionGroup(self)
        self.language_group.setExclusive(True)
        self.language_actions: dict[str, QAction] = {}
        for code, label in SUPPORTED_LANGUAGES.items():
            language_action = QAction(label, self)
            language_action.setCheckable(True)
            language_action.setChecked(code == self.language)
            language_action.triggered.connect(lambda checked, lang=code: self.set_language(lang) if checked else None)
            self.language_group.addAction(language_action)
            menu_language.addAction(language_action)
            self.language_actions[code] = language_action

        find_action = QAction(self.tr("find"), self)
        find_action.setShortcut(QKeySequence.StandardKey.Find)
        find_action.triggered.connect(self.show_find_bar)
        decorate(find_action, QStyle.StandardPixmap.SP_FileDialogContentsView, self.tr("find"))
        menu_edit.addSeparator()
        menu_edit.addAction(find_action)
        toolbar.addAction(find_action)

        find_next_action = QAction(self.tr("next"), self)
        find_next_action.setShortcut(QKeySequence("F3"))
        find_next_action.triggered.connect(self.find_next)
        menu_edit.addAction(find_next_action)
        find_previous_action = QAction(self.tr("previous"), self)
        find_previous_action.setShortcut(QKeySequence("Shift+F3"))
        find_previous_action.triggered.connect(self.find_previous)
        menu_edit.addAction(find_previous_action)
        self.close_find_action = QAction(self)
        self.close_find_action.setShortcut(QKeySequence("Escape"))
        self.close_find_action.triggered.connect(self.hide_find_bar)
        self.close_find_action.setEnabled(False)
        self.addAction(self.close_find_action)

        preferences_action = QAction(self.tr("preferences"), self)
        preferences_action.setShortcut(QKeySequence("Ctrl+,"))
        preferences_action.triggered.connect(self.show_preferences)
        menu_view.addSeparator()
        menu_view.addAction(preferences_action)

        check_updates_action = QAction(self.tr("check_updates"), self)
        check_updates_action.triggered.connect(self.check_for_updates)
        menu_help.addAction(check_updates_action)
        releases_action = QAction(self.tr("github_releases"), self)
        releases_action.triggered.connect(self.open_release_page)
        menu_help.addAction(releases_action)
        menu_help.addSeparator()
        about_action = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxInformation), self.tr("about"), self)
        about_action.triggered.connect(self.show_about)
        menu_help.addAction(about_action)

        self.actions = {
            "new": new_action,
            "new_note": new_note_action,
            "open": open_action,
            "open_workspace": open_workspace_action,
            "save": save_action,
            "save_as": save_as_action,
            "export_html": export_html_action,
            "export_pdf": export_pdf_action,
            "bold": bold_action,
            "italic": italic_action,
            "code": code_action,
            "code_block": code_block_action,
            "heading": heading_action,
            "list": list_action,
            "quote": quote_action,
            "link": link_action,
            "image": image_action,
            "table": table_action,
            "search_workspace": search_workspace_action,
            "toggle_sidebar": toggle_sidebar_action,
            "theme": theme_action,
            "autosave": autosave_action,
            "wrap": wrap_action,
            "sync_scroll": sync_scroll_action,
            "find": find_action,
            "find_next": find_next_action,
            "find_previous": find_previous_action,
            "preferences": preferences_action,
            "check_updates": check_updates_action,
            "releases": releases_action,
            "about": about_action,
        }
        for action in self.actions.values():
            self.addAction(action)
        self._apply_command_icons()

    def _build_statusbar(self) -> None:
        status = QStatusBar()
        self.setStatusBar(status)
        self.path_label = QLabel("Senza file")
        self.path_label.setMinimumWidth(0)
        self.path_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.status_label = QLabel("Pronto")
        status.setFixedHeight(24)
        status.addWidget(self.path_label, 1)
        status.addPermanentWidget(self.status_label)

    def apply_language(self) -> None:
        if hasattr(self, "menus"):
            self.menus["file"].setTitle(self.tr("menu_file"))
            self.menus["edit"].setTitle(self.tr("menu_edit"))
            self.menus["view"].setTitle(self.tr("menu_view"))
            self.menus["workspace"].setTitle(self.tr("menu_workspace"))
            self.menus["export"].setTitle(self.tr("menu_export"))
            self.menus["language"].setTitle(self.tr("menu_language"))
            self.menus["help"].setTitle(self.tr("menu_help"))

        if hasattr(self, "actions"):
            action_texts = {
                "new": "new",
                "new_note": "new_workspace_note",
                "open": "open",
                "open_workspace": "open_workspace",
                "save": "save",
                "save_as": "save_as",
                "export_html": "export_html",
                "export_pdf": "export_pdf",
                "bold": "bold",
                "italic": "italic",
                "code": "code",
                "code_block": "code_block",
                "heading": "H2",
                "list": "list",
                "quote": "quote",
                "link": "link",
                "image": "image",
                "table": "table",
                "search_workspace": "search_workspace",
                "toggle_sidebar": "toggle_sidebar",
                "autosave": "autosave",
                "wrap": "word_wrap",
                "sync_scroll": "sync_scroll",
                "find": "find",
                "find_next": "next",
                "find_previous": "previous",
                "preferences": "preferences",
                "check_updates": "check_updates",
                "releases": "github_releases",
                "about": "about",
            }
            for action_name, key in action_texts.items():
                self.actions[action_name].setText(key if key == "H2" else self.tr(key))

            self.actions["new"].setToolTip(self.tr("new_doc"))
            self.actions["new_note"].setToolTip(self.tr("new_workspace_note"))
            self.actions["open"].setToolTip(self.tr("open_file"))
            self.actions["open_workspace"].setToolTip(self.tr("open_workspace"))
            self.actions["save"].setToolTip(self.tr("save_file"))
            self.actions["export_html"].setToolTip(self.tr("export_html_tip"))
            self.actions["export_pdf"].setToolTip(self.tr("export_pdf_tip"))
            self.actions["bold"].setToolTip(self.tr("bold"))
            self.actions["italic"].setToolTip(self.tr("italic"))
            self.actions["code"].setToolTip(self.tr("inline_code"))
            self.actions["code_block"].setToolTip(self.tr("code_block"))
            self.actions["link"].setToolTip(self.tr("insert_link"))
            self.actions["image"].setToolTip(self.tr("insert_image"))
            self.actions["table"].setToolTip(self.tr("insert_table"))
            self.actions["search_workspace"].setToolTip(self.tr("search_workspace"))
            self.actions["theme"].setToolTip(self.tr("change_theme"))

        if hasattr(self, "language_actions"):
            for code, action in self.language_actions.items():
                action.setText(SUPPORTED_LANGUAGES[code])
                action.setChecked(code == self.language)

        self.find_box.setPlaceholderText(self.tr("find_placeholder"))
        self.find_case_checkbox.setText(self.tr("case_sensitive"))
        if hasattr(self, "find_button"):
            self.find_button.setText(self.tr("next"))
        if hasattr(self, "find_prev_button"):
            self.find_prev_button.setText(self.tr("previous"))
        self.main_toolbar.setWindowTitle(self.tr("commands"))
        self.format_toolbar.setWindowTitle(self.tr("formatting"))
        self.preview_label.setText(self.tr("preview"))
        self.insert_button.setText(self.tr("insert"))
        self.export_button.setText(self.tr("menu_export"))
        self.export_button.setToolTip(self.tr("menu_export"))
        self.export_button.setAccessibleName(self.tr("menu_export"))
        self.application_menu_button.setToolTip(self.tr("application_menu"))
        self.application_menu_button.setAccessibleName(self.tr("application_menu"))
        self.navigation.apply_language(self.tr)
        self.find_close_button.setToolTip(self.tr("close_search"))
        self.find_close_button.setAccessibleName(self.tr("close_search"))
        self.find_box.setAccessibleName(self.tr("find_placeholder"))
        self.document_tabs.set_close_label(self.tr("close_document"))
        for mode, key in (("writing", "writing"), ("split", "split_view"), ("reading", "reading")):
            self.view_actions[mode].setText(self.tr(key))
        for name, label in (("bold", "B"), ("italic", "I"), ("code", "</>")):
            button = self.format_buttons[name]
            if isinstance(button, QToolButton):
                button.setText(label)
                button.setAccessibleName(self.actions[name].text())
                button.setToolTip(self.actions[name].toolTip())
                font = button.font()
                font.setBold(name == "bold")
                font.setItalic(name == "italic")
                button.setFont(font)
        self.workspace_panel.apply_language()
        self.workspace_panel.refresh_recent(self.recent_files)
        self.update_outline()
        self.update_theme_action_text()
        self.update_window_title()
        self.update_status()
        self._apply_command_icons()
        if hasattr(self, "update_toast") and self.available_release is not None:
            self.update_toast.set_labels(*self._update_toast_labels())
            self.update_toast.reposition()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "view_actions"):
            self._apply_responsive_layout()
        if hasattr(self, "update_toast") and self.update_toast.isVisible():
            self.update_toast.reposition()

    def _apply_command_icons(self) -> None:
        color = THEMES[self.theme]["preview_fg"]
        for name, icon in (("new", "new"), ("open", "folder"), ("save", "save"), ("find", "search"), ("list", "list"), ("quote", "quote")):
            self.actions[name].setIcon(ui_icon(icon, color))
        for name in ("list", "quote"):
            button = self.format_toolbar.widgetForAction(self.actions[name])
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            self.actions[name].setToolTip(self.actions[name].text())
        for mode, action in self.view_actions.items():
            action.setIcon(ui_icon(mode, color))
            action.setToolTip(f"{action.text()} ({action.shortcut().toString()})")
        self.application_menu_button.setIcon(ui_icon("menu", color))
        self.export_button.setIcon(ui_icon("export", color))
        self.navigation.apply_theme(THEMES[self.theme]["preview_muted"])
        self.workspace_panel.apply_theme(THEMES[self.theme]["preview_muted"])

    def _remember_sidebar_width(self, _position: int, _index: int) -> None:
        if not self.workspace_panel.isHidden():
            self._sidebar_width = self.main_splitter.sizes()[0]
        self._apply_responsive_layout()

    def _apply_responsive_layout(self) -> None:
        compact = self.width() < 1080
        if compact and not self._compact_layout:
            self._sidebar_compact_open = False
        self._compact_layout = compact
        visible = self._sidebar_requested and (not compact or self._sidebar_compact_open)
        was_hidden = self.workspace_panel.isHidden()
        self.workspace_panel.setVisible(visible)
        if visible and was_hidden:
            self.main_splitter.setSizes([self._sidebar_width, max(1, self.main_splitter.width() - self._sidebar_width)])
        self.navigation.set_section(self.workspace_panel.section if visible else None)
        available = self.main_splitter.width() - (self._sidebar_width + 1 if visible else 0)
        orientation = Qt.Orientation.Horizontal if available >= 880 else Qt.Orientation.Vertical
        splitter = self.editor_preview_splitter
        if splitter.orientation() != orientation:
            if self.view_mode == "split":
                self._remember_document_split()
            splitter.setOrientation(orientation)
            self._restore_document_split()
        stacked = orientation == Qt.Orientation.Vertical and self.view_mode == "split"
        self.editor_panel.setMinimumHeight(140 if stacked else 0)
        self.preview_panel.setMinimumHeight(140 if stacked else 0)
        self.preview_label.setVisible(self.view_mode == "split")

    def _restore_document_split(self) -> None:
        horizontal = self.editor_preview_splitter.orientation() == Qt.Orientation.Horizontal
        saved = self._split_sizes if horizontal else self._stack_sizes
        extent = self.editor_preview_splitter.width() if horizontal else self.editor_preview_splitter.height()
        total = max(2, extent - self.editor_preview_splitter.handleWidth())
        first = round(total * saved[0] / max(1, sum(saved)))
        self.editor_preview_splitter.setSizes([first, total - first])

    def _remember_document_split(self) -> None:
        sizes = self.editor_preview_splitter.sizes()
        if all(size > 0 for size in sizes):
            if self.editor_preview_splitter.orientation() == Qt.Orientation.Horizontal:
                self._split_sizes = sizes
            else:
                self._stack_sizes = sizes

    def show_sidebar_section(self, section: str, *, toggle: bool = True) -> None:
        if toggle and not self.workspace_panel.isHidden() and self.workspace_panel.section == section:
            self._sidebar_requested = False
        else:
            self._sidebar_requested = True
            self._sidebar_compact_open = True
            self.workspace_panel.show_section(section)
        self._apply_responsive_layout()

    def dismiss_compact_sidebar(self) -> None:
        if self._compact_layout:
            self._sidebar_compact_open = False
            self._apply_responsive_layout()

    def check_startup_updates(self) -> None:
        if self.check_updates_on_startup and not self.update_checker.has_checked:
            self.update_checker.check()

    def check_for_updates(self) -> None:
        self._manual_update_check = True
        self.statusBar().showMessage(self.tr("checking_updates"), 10_000)
        self.update_checker.check()

    def _update_toast_labels(self) -> tuple[str, str, str, str]:
        return (
            self.tr("update_available"),
            self.tr("update_available_body", version=self.available_release.version, current=VERSION),
            self.tr("open_release"), self.tr("dismiss_notification"),
        )

    def on_update_check_finished(self, result: UpdateResult) -> None:
        manual, self._manual_update_check = self._manual_update_check, False
        if result.status == "available" and result.release is not None:
            self.available_release = result.release
            self.update_toast.notify(*self._update_toast_labels())
            self.statusBar().showMessage(self.tr("update_available"), 5000)
        elif manual:
            key = {"current": "updates_current", "no_release": "updates_no_release"}.get(result.status, "updates_unavailable")
            self.statusBar().showMessage(self.tr(key, version=VERSION), 8000)

    def open_release_page(self) -> None:
        url = self.available_release.url if self.available_release else GITHUB_RELEASES_URL
        QDesktopServices.openUrl(QUrl(url))

    def set_language(self, language: str) -> None:
        if language not in SUPPORTED_LANGUAGES or language == self.language:
            return
        self.language = language
        self.settings.setValue("language", language)
        self.apply_language()
        self.statusBar().showMessage(self.tr("language_changed", language=SUPPORTED_LANGUAGES[language]), 2500)

    def update_theme_action_text(self) -> None:
        if hasattr(self, "actions"):
            self.actions["theme"].setText(self.tr("dark_theme" if self.theme == "light" else "light_theme"))

    def restore_ui_settings(self) -> None:
        geometry = self.settings.value("geometry")
        if geometry is not None:
            try:
                self.restoreGeometry(geometry)
            except Exception:
                pass

        main_sizes = coerce_splitter_sizes(self.settings.value("main_splitter_sizes"), 2)
        if main_sizes:
            self._sidebar_width = max(190, min(300, main_sizes[0]))
            self.main_splitter.setSizes([self._sidebar_width, main_sizes[1]])

        editor_sizes = coerce_splitter_sizes(self.settings.value("editor_preview_splitter_sizes"), 2)
        # Backward compatibility with v0.2 key.
        if not editor_sizes:
            editor_sizes = coerce_splitter_sizes(self.settings.value("splitter_sizes"), 2)
        if editor_sizes:
            if all(size > 0 for size in editor_sizes):
                self._split_sizes = editor_sizes
        stack_sizes = coerce_splitter_sizes(self.settings.value("editor_preview_vertical_sizes"), 2)
        if stack_sizes and all(size > 0 for size in stack_sizes):
            self._stack_sizes = stack_sizes

        line_wrap = as_bool(self.settings.value("line_wrap", True), True)
        self.actions["wrap"].setChecked(line_wrap)
        self.set_line_wrap(line_wrap)

        self._sidebar_requested = as_bool(self.settings.value("sidebar_visible", True), True)
        section = str(self.settings.value("sidebar_section", "files"))
        self.workspace_panel.show_section(section)

        sync_scroll = as_bool(self.settings.value("sync_preview_scroll_enabled", True), True)
        self.sync_preview_scroll_enabled = sync_scroll
        self.actions["sync_scroll"].setChecked(sync_scroll)
        self.set_view_mode(str(self.settings.value("view_mode", "writing")))
        self._apply_responsive_layout()

    def save_ui_settings(self) -> None:
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("main_splitter_sizes", [self._sidebar_width, max(1, self.main_splitter.width() - self._sidebar_width)])
        if self.view_mode == "split":
            self._remember_document_split()
        self.settings.setValue("editor_preview_splitter_sizes", self._split_sizes)
        self.settings.setValue("editor_preview_vertical_sizes", self._stack_sizes)
        self.settings.setValue("view_mode", self.view_mode)
        self.typography.save(self.settings)
        self.settings.setValue("check_updates_on_startup", self.check_updates_on_startup)
        self.settings.setValue("theme", self.theme)
        self.settings.setValue("language", self.language)
        self.settings.setValue("autosave_enabled", self.autosave_enabled)
        self.settings.setValue("line_wrap", self.actions["wrap"].isChecked())
        self.settings.setValue("sync_preview_scroll_enabled", self.sync_preview_scroll_enabled)
        self.settings.setValue("sidebar_visible", self._sidebar_requested)
        self.settings.setValue("sidebar_section", self.workspace_panel.section)
        if self.workspace_dir:
            self.settings.setValue("workspace_dir", str(self.workspace_dir))
        if self.current_path:
            self.settings.setValue("last_dir", str(self.current_path.parent))
        save_settings_list(self.settings, "recent_files", [str(path) for path in self.recent_files])

    def on_text_changed(self) -> None:
        if self._loading:
            return
        editor = self.sender()
        if not isinstance(editor, MarkdownEditor) or editor not in self.document_paths:
            return
        self.update_tab_title(editor)
        if editor is self.editor:
            self.schedule_preview_update()
            self.update_outline()
            self.update_window_title()
            self.update_status()
        if self.autosave_enabled:
            self.document_autosave_timers[editor].start()

    def maybe_save(self) -> bool:
        if not self.editor.document().isModified():
            return True

        result = QMessageBox.question(
            self,
            self.tr("unsaved_title"),
            self.tr("unsaved_body"),
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
        )

        if result == QMessageBox.StandardButton.Save:
            return self.save_file()
        if result == QMessageBox.StandardButton.Discard:
            return True
        return False

    def new_file(self) -> None:
        self._create_document_tab("", None, modified=False)
        self.update_preview()
        self.update_outline()
        self.update_window_title()
        self.update_status()
        self.statusBar().showMessage(self.tr("new_document"), 2500)

    def new_note_in_workspace(self) -> None:
        if not self.workspace_dir:
            self.choose_workspace()
            if not self.workspace_dir:
                return
        if not self.maybe_save():
            return

        base = self.workspace_dir / "nuova-nota.md"
        candidate = base
        counter = 2
        while candidate.exists():
            candidate = self.workspace_dir / f"nuova-nota-{counter}.md"
            counter += 1

        initial = f"# {candidate.stem.replace('-', ' ').title()}\n\n"
        try:
            write_text_atomic(candidate, initial)
        except OSError as exc:
            QMessageBox.critical(self, self.tr("note_create_error"), self.tr("note_create_error_body", error=exc))
            return
        self.open_file_path(candidate)
        self.statusBar().showMessage(self.tr("note_created", name=candidate.name), 3000)

    def open_file(self) -> None:
        start_dir = str(self.current_path.parent if self.current_path else self.workspace_dir or self.settings.value("last_dir", Path.home()))
        file_name, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("open_markdown"),
            start_dir,
            "Markdown (*.md *.markdown *.mdown *.mkd *.txt);;Tutti i file (*.*)",
        )
        if not file_name:
            return
        self.open_file_path(Path(file_name))

    def open_file_path(self, path: Path, line_number: int | None = None) -> bool:
        path = Path(path).resolve()
        if not path.exists():
            QMessageBox.warning(self, self.tr("file_not_found"), self.tr("file_not_found_body", path=path))
            self.remove_recent_path(path)
            return False
        if not path.is_file():
            return False

        for index in range(self.document_tabs.count()):
            editor = self.document_tabs.widget(index)
            if isinstance(editor, MarkdownEditor) and self.document_paths.get(editor) == path:
                self.document_tabs.setCurrentIndex(index)
                if line_number:
                    self.goto_line(line_number)
                return True

        try:
            text = read_text_file(path)
        except OSError as exc:
            QMessageBox.critical(self, self.tr("open_error"), self.tr("open_error_body", error=exc))
            return False

        self._create_document_tab(text, path, modified=False)
        self.add_recent_path(path)

        if self.workspace_dir is None and path.parent.exists():
            self.set_workspace(path.parent)

        self.update_preview()
        self.update_window_title()
        self.update_status()
        if line_number:
            self.goto_line(line_number)
        self.statusBar().showMessage(self.tr("opened", name=path.name), 2500)
        return True

    def save_file(self) -> bool:
        if self.current_path is None:
            return self.save_file_as()
        return self._write_markdown(self.current_path, autosave=False)

    def save_file_as(self) -> bool:
        start_dir = str(self.current_path.parent if self.current_path else self.workspace_dir or self.settings.value("last_dir", Path.home()))
        file_name, _ = QFileDialog.getSaveFileName(
            self,
            self.tr("save_markdown"),
            start_dir,
            "Markdown (*.md);;File di testo (*.txt);;Tutti i file (*.*)",
        )
        if not file_name:
            return False

        path = Path(file_name)
        if path.suffix == "":
            path = path.with_suffix(".md")
        return self._write_markdown(path, autosave=False)

    def _write_markdown(self, path: Path, *, autosave: bool, editor: MarkdownEditor | None = None) -> bool:
        editor = editor if editor is not None else self.editor
        try:
            path = path.resolve()
            if any(other is not editor and opened == path for other, opened in self.document_paths.items()):
                raise OSError(self.tr("save_path_in_use", path=path))
            write_text_atomic(path, editor.toPlainText())
        except OSError as exc:
            if not autosave:
                QMessageBox.critical(self, self.tr("save_error"), self.tr("save_error_body", error=exc))
            else:
                self.statusBar().showMessage(self.tr("autosave_failed", error=exc), 3500)
            return False

        self.document_paths[editor] = path
        self.add_recent_path(path)
        self.document_autosave_timers[editor].stop()
        editor.document().setModified(False)
        self.update_tab_title(editor)
        if editor is self.editor:
            self.current_path = path
            self.update_window_title()
            self.update_preview()
            self.update_status()
        if autosave:
            self.statusBar().showMessage(self.tr("autosaved", name=path.name), 1800)
        else:
            self.statusBar().showMessage(self.tr("saved", name=path.name), 2500)
        return True

    def autosave_current_file(self) -> None:
        self.autosave_document(self.editor)

    def autosave_document(self, editor: MarkdownEditor) -> None:
        path = self.document_paths.get(editor)
        if not self.autosave_enabled or path is None:
            return
        if not editor.document().isModified():
            return
        self._write_markdown(path, autosave=True, editor=editor)

    def export_html(self) -> None:
        suggested = self.current_path.with_suffix(".html") if self.current_path else Path.home() / "documento.html"
        file_name, _ = QFileDialog.getSaveFileName(
            self,
            self.tr("export_html"),
            str(suggested),
            "HTML (*.html *.htm);;Tutti i file (*.*)",
        )
        if not file_name:
            return

        path = Path(file_name)
        if path.suffix == "":
            path = path.with_suffix(".html")

        title = self.current_path.stem if self.current_path else APP_NAME
        html_doc = self.renderer.to_html_document(self.editor.toPlainText(), title=title)
        try:
            path.write_text(html_doc, encoding="utf-8", newline="\n")
        except OSError as exc:
            QMessageBox.critical(self, self.tr("export_error"), self.tr("export_html_error_body", error=exc))
            return

        self.statusBar().showMessage(self.tr("html_exported", name=path.name), 3500)

    def export_pdf(self) -> None:
        if self.pdf_exporter.busy:
            return
        dialog = PdfOptionsDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        suggested = self.current_path.with_suffix(".pdf") if self.current_path else Path.home() / "documento.pdf"
        file_name, _ = QFileDialog.getSaveFileName(
            self,
            self.tr("export_pdf"),
            str(suggested),
            "PDF (*.pdf);;Tutti i file (*.*)",
        )
        if not file_name:
            return

        path = Path(file_name)
        if path.suffix == "":
            path = path.with_suffix(".pdf")

        options = dialog.options()
        options.save(self.settings)
        title = self.current_path.stem if self.current_path else APP_NAME
        self.pdf_exporter.start(self.editor.toPlainText(), title, self.document_base_url(), path, options)
        self.statusBar().showMessage(self.tr("pdf_generation", name=path.name), 3500)

    def on_pdf_export_finished(self, result: PdfResult) -> None:
        if result.success:
            self.statusBar().showMessage(self.tr("pdf_exported", name=result.path.name), 4500)
        else:
            QMessageBox.warning(self, self.tr("pdf_not_generated"), self.tr(result.error, error=result.detail))

    def choose_workspace(self) -> None:
        start_dir = str(self.current_path.parent if self.current_path else self.workspace_dir or self.settings.value("last_dir", Path.home()))
        directory = QFileDialog.getExistingDirectory(self, self.tr("choose_workspace"), start_dir)
        if not directory:
            return
        self.set_workspace(Path(directory))

    def set_workspace(self, path: Path) -> None:
        if not path.exists() or not path.is_dir():
            QMessageBox.warning(self, self.tr("invalid_workspace"), self.tr("invalid_workspace_body", path=path))
            return
        self.workspace_dir = path
        self.workspace_panel.set_workspace(path)
        self.settings.setValue("workspace_dir", str(path))
        self.statusBar().showMessage(self.tr("workspace_set", path=path), 3000)

    def search_workspace(self) -> None:
        query = self.workspace_panel.search_box.text().strip()
        if not query:
            return
        if not self.workspace_dir:
            QMessageBox.information(self, self.tr("no_workspace"), self.tr("choose_workspace_first"))
            return

        hits: list[SearchHit] = []
        case_sensitive = self.workspace_panel.case_sensitive_box.isChecked()
        needle = query if case_sensitive else query.lower()
        scanned = 0
        skipped = 0

        for path in sorted(self.workspace_dir.rglob("*")):
            if not is_markdown_file(path):
                continue
            try:
                if path.stat().st_size > MAX_SEARCH_FILE_BYTES:
                    skipped += 1
                    continue
                text = read_text_file(path)
            except OSError:
                skipped += 1
                continue

            scanned += 1
            for line_number, line in enumerate(text.splitlines(), start=1):
                haystack = line if case_sensitive else line.lower()
                if needle in haystack:
                    snippet = re.sub(r"\s+", " ", line.strip())
                    if len(snippet) > 140:
                        snippet = snippet[:137] + "..."
                    hits.append(SearchHit(path=path, line_number=line_number, snippet=snippet or "[riga vuota]"))
                    if len(hits) >= MAX_SEARCH_RESULTS:
                        break
            if len(hits) >= MAX_SEARCH_RESULTS:
                break

        self.workspace_panel.show_search_results(hits, self.workspace_dir)
        suffix = self.tr("skipped_files_suffix", skipped=skipped) if skipped else ""
        self.statusBar().showMessage(self.tr("search_status", hits=len(hits), scanned=scanned, suffix=suffix), 5000)

    def focus_workspace_search(self) -> None:
        self.show_sidebar_section("search", toggle=False)
        self.workspace_panel.search_box.setFocus()
        self.workspace_panel.search_box.selectAll()

    def toggle_sidebar(self) -> None:
        self.show_sidebar_section(self.workspace_panel.section)

    def add_recent_path(self, path: Path) -> None:
        normalized = path.resolve() if path.exists() else path
        remaining: list[Path] = []
        for item in self.recent_files:
            try:
                same = item.resolve() == normalized if item.exists() and normalized.exists() else str(item) == str(path)
            except OSError:
                same = str(item) == str(path)
            if not same:
                remaining.append(item)
        self.recent_files = [path, *remaining][:MAX_RECENT_FILES]
        self.workspace_panel.refresh_recent(self.recent_files)
        save_settings_list(self.settings, "recent_files", [str(item) for item in self.recent_files])

    def remove_recent_path(self, path: Path) -> None:
        self.recent_files = [item for item in self.recent_files if str(item) != str(path)]
        self.workspace_panel.refresh_recent(self.recent_files)
        save_settings_list(self.settings, "recent_files", [str(item) for item in self.recent_files])

    def on_workspace_file_renamed(self, old_path: Path, new_path: Path) -> None:
        for index in range(self.document_tabs.count()):
            editor = self.document_tabs.widget(index)
            if isinstance(editor, MarkdownEditor) and self.document_paths.get(editor) == old_path:
                self.document_paths[editor] = new_path
                self.document_tabs.setTabText(index, self._tab_title_for(editor))
                self.document_tabs.setTabToolTip(index, str(new_path))

        if self.current_path and Path(self.current_path) == old_path:
            self.current_path = new_path
            self.update_window_title()
            self.update_preview()
            self.update_status()

        self.recent_files = [new_path if item == old_path else item for item in self.recent_files]
        self.workspace_panel.refresh_recent(self.recent_files)
        save_settings_list(self.settings, "recent_files", [str(item) for item in self.recent_files])
        self.statusBar().showMessage(self.tr("renamed", name=new_path.name), 3000)

    def on_workspace_file_deleted(self, path: Path) -> None:
        was_current = self.current_path is not None and Path(self.current_path) == path
        self.recent_files = [item for item in self.recent_files if item != path]
        self.workspace_panel.refresh_recent(self.recent_files)
        save_settings_list(self.settings, "recent_files", [str(item) for item in self.recent_files])

        for index in reversed(range(self.document_tabs.count())):
            editor = self.document_tabs.widget(index)
            if isinstance(editor, MarkdownEditor) and self.document_paths.get(editor) == path:
                self.document_tabs.removeTab(index)
                timer = self.document_autosave_timers.pop(editor, None)
                if timer:
                    timer.stop()
                self.document_paths.pop(editor, None)
                editor.deleteLater()

        if self.document_tabs.count() == 0:
            self._create_document_tab("", None, modified=False)
        if was_current:
            self.on_current_tab_changed(self.document_tabs.currentIndex())

        self.statusBar().showMessage(self.tr("deleted", name=path.name), 3000)

    def schedule_preview_update(self) -> None:
        self.update_timer.start()

    def update_preview(self) -> None:
        title = self.current_path.stem if self.current_path else APP_NAME
        revision = self.scroll_sync.prepare(self.editor)
        html_doc = self.renderer.to_html_document(self.editor.toPlainText(), title=title)
        html_doc = html_doc.replace('<html lang="it">', f'<html lang="it" data-preview-revision="{revision}">', 1)

        self.preview.setHtml(html_doc, self.document_base_url())
        self.schedule_preview_scroll_sync()

    def document_base_url(self) -> QUrl:
        directory = self.current_path.parent if self.current_path else self.workspace_dir or Path.cwd()
        return QUrl.fromLocalFile(str(directory) + os.sep)

    def schedule_preview_scroll_sync(self) -> None:
        self.scroll_sync.schedule()

    def update_outline(self) -> None:
        headings: list[tuple[int, str, int]] = []
        for line_number, line in enumerate(self.editor.toPlainText().splitlines(), start=1):
            match = re.match(r"^(#{1,6})\s+(.+?)\s*#*\s*$", line)
            if not match:
                continue
            title = re.sub(r"[*_`]+", "", match.group(2)).strip()
            headings.append((len(match.group(1)), title, line_number))
        self.workspace_panel.update_outline(headings)

    def update_window_title(self) -> None:
        name = self.current_path.name if self.current_path else self.tr("untitled")
        dirty = " *" if self.editor.document().isModified() else ""
        self.setWindowTitle(f"{name}{dirty} - {APP_NAME} v{VERSION}")

    def update_status(self) -> None:
        if not hasattr(self, "status_label") or not hasattr(self, "path_label"):
            return
        cursor = self.editor.textCursor()
        line = cursor.blockNumber() + 1
        col = cursor.positionInBlock() + 1
        text = self.editor.toPlainText()
        words = len(text.split()) if text.strip() else 0
        chars = len(text)
        read_minutes = max(1, round(words / 220)) if words else 0
        self.status_label.setText(
            self.tr("compact_status", line=line, col=col, words=words)
        )
        self.status_label.setToolTip(self.tr("line_status", line=line, col=col, words=words, chars=chars, minutes=read_minutes))
        if self.current_path:
            state = self.tr("document_modified" if self.editor.document().isModified() else "document_saved")
            self.path_label.setText(f"{self.current_path.name} · {state}")
            self.path_label.setToolTip(str(self.current_path))
        else:
            self.path_label.setText(self.tr("unsaved_draft"))
            self.path_label.setToolTip(self.tr("no_file_status", workspace=""))

    def goto_line(self, line_number: int) -> None:
        block = self.editor.document().findBlockByNumber(max(0, line_number - 1))
        if block.isValid():
            cursor = QTextCursor(block)
            self.editor.setTextCursor(cursor)
            self.editor.centerCursor()
            self.editor.setFocus()

    def wrap_selection(self, before: str, after: str, placeholder: str) -> None:
        cursor = self.editor.textCursor()
        selected = cursor.selectedText()
        if selected:
            replacement = f"{before}{selected}{after}"
        else:
            replacement = f"{before}{placeholder}{after}"

        cursor.insertText(replacement)
        if not selected:
            start = cursor.position() - len(after) - len(placeholder)
            cursor.setPosition(start)
            cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, len(placeholder))
            self.editor.setTextCursor(cursor)

    def prefix_current_line(self, prefix: str) -> None:
        cursor = self.editor.textCursor()
        cursor.beginEditBlock()
        if cursor.hasSelection():
            start = cursor.selectionStart()
            end = cursor.selectionEnd()
            cursor.setPosition(start)
            first_block = cursor.blockNumber()
            cursor.setPosition(end)
            last_block = cursor.blockNumber()
            for block_number in range(first_block, last_block + 1):
                block = self.editor.document().findBlockByNumber(block_number)
                cursor.setPosition(block.position())
                cursor.insertText(prefix)
        else:
            cursor.movePosition(QTextCursor.MoveOperation.StartOfLine)
            cursor.insertText(prefix)
        cursor.endEditBlock()

    def insert_code_block(self) -> None:
        cursor = self.editor.textCursor()
        selected = cursor.selectedText().replace("\u2029", "\n")
        if selected:
            replacement = f"```python\n{selected}\n```"
        else:
            replacement = f"```python\n# {self.tr('code_placeholder')}\n```"
        cursor.insertText(replacement)

    def insert_link(self) -> None:
        cursor = self.editor.textCursor()
        selected = cursor.selectedText().replace("\u2029", " ").strip()
        label, ok = QInputDialog.getText(
            self,
            self.tr("insert_link"),
            self.tr("link_text"),
            text=selected or self.tr("text_placeholder"),
        )
        if not ok or not label.strip():
            return
        url, ok = QInputDialog.getText(self, self.tr("insert_link"), self.tr("link_url"), text="https://")
        if not ok or not url.strip():
            return
        cursor.insertText(f"[{label.strip()}]({url.strip()})")

    def insert_image(self) -> None:
        start_dir = str(self.current_path.parent if self.current_path else self.workspace_dir or self.settings.value("last_dir", Path.home()))
        file_name, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("insert_image"),
            start_dir,
            self.tr("image_filter"),
        )
        if not file_name:
            return
        path = Path(file_name)
        reference = self._markdown_reference_for(path)
        alt_text = path.stem.replace("-", " ").replace("_", " ").strip() or "immagine"
        self.editor.textCursor().insertText(f"![{alt_text}]({reference})")

    def insert_dropped_images(self, image_paths: list[str]) -> None:
        if not image_paths:
            return
        if self.current_path is None and not self.save_file_as():
            return

        inserted: list[str] = []
        for raw_path in image_paths:
            source = Path(raw_path)
            if not source.exists() or not source.is_file():
                continue
            target = self._copy_image_to_document_assets(source)
            reference = self._markdown_reference_for(target)
            alt_text = target.stem.replace("-", " ").replace("_", " ").strip() or self.tr("image").lower()
            inserted.append(f"![{alt_text}]({reference})")

        if inserted:
            cursor = self.editor.textCursor()
            prefix = "\n" if cursor.positionInBlock() else ""
            cursor.insertText(prefix + "\n".join(inserted) + "\n")
            self.statusBar().showMessage(self.tr("insert_image"), 1800)

    def _copy_image_to_document_assets(self, source: Path) -> Path:
        base_dir = self.current_path.parent if self.current_path else self.workspace_dir or Path.cwd()
        assets_dir = base_dir / "assets"
        assets_dir.mkdir(exist_ok=True)

        target = assets_dir / source.name
        counter = 2
        while target.exists():
            target = assets_dir / f"{source.stem}-{counter}{source.suffix}"
            counter += 1
        shutil.copy2(source, target)
        return target

    def insert_table(self) -> None:
        self.editor.textCursor().insertText(
            "\n| Colonna 1 | Colonna 2 |\n"
            "| --- | --- |\n"
            "| Valore | Valore |\n"
        )

    def _markdown_reference_for(self, path: Path) -> str:
        base_dir = self.current_path.parent if self.current_path else self.workspace_dir
        if base_dir:
            try:
                return path.relative_to(base_dir).as_posix()
            except ValueError:
                pass
        return QUrl.fromLocalFile(str(path)).toString()

    def set_view_mode(self, mode: str) -> None:
        if mode not in {"writing", "split", "reading"}:
            mode = "split"
        if self.view_mode == "split":
            self._remember_document_split()
        self.view_mode = mode
        self.editor_panel.setVisible(mode != "reading")
        self.preview_panel.setVisible(mode != "writing")
        if mode == "split":
            self._restore_document_split()
        for editor in self.document_paths:
            editor.set_readable_width(mode == "writing")
        for value, action in self.view_actions.items():
            action.setChecked(value == mode)
        for key in ("bold", "italic", "code", "code_block", "heading", "list", "quote", "link", "image", "table"):
            self.actions[key].setEnabled(mode != "reading")
        if mode == "reading":
            self.hide_find_bar()
            self.preview.setFocus()
        else:
            self.editor.setFocus()
        self._apply_responsive_layout()
        self.schedule_preview_scroll_sync()

    def show_find_bar(self) -> None:
        if self.view_mode == "reading":
            self.set_view_mode("split")
        selected = self.editor.textCursor().selectedText()
        if selected and "\u2029" not in selected:
            self.find_box.setText(selected)
        self.find_bar.show()
        self.close_find_action.setEnabled(True)
        self.find_box.setFocus()
        self.find_box.selectAll()

    def hide_find_bar(self) -> None:
        self.find_bar.hide()
        self.close_find_action.setEnabled(False)
        self.editor.setFocus()

    def show_about(self) -> None:
        version = html.escape(self.tr("about_version", version=VERSION))
        author = html.escape(self.tr("about_author", author=APP_AUTHOR))
        QMessageBox.about(
            self, self.tr("about_title", name=APP_NAME),
            f"<h3>{html.escape(APP_NAME)}</h3>"
            f"<p>{version}<br>{author}</p>"
            f"<p>{html.escape(APP_COPYRIGHT)}</p>",
        )

    def show_preferences(self) -> None:
        dialog = PreferencesDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.typography = dialog.typography()
        self.check_updates_on_startup = dialog.check_updates.isChecked()
        if not self.check_updates_on_startup and not self._manual_update_check:
            self.update_checker.cancel()
        self.renderer.typography = self.typography
        for editor in self.document_paths:
            editor.apply_typography(self.typography.editor_font, self.typography.editor_size)
        self.set_language(dialog.language.currentData())
        self.apply_theme(dialog.theme.currentData())
        for key, checked, handler in (
            ("autosave", dialog.autosave.isChecked(), self.toggle_autosave),
            ("wrap", dialog.wrap.isChecked(), self.toggle_line_wrap),
            ("sync_scroll", dialog.sync.isChecked(), self.toggle_preview_scroll_sync),
        ):
            self.actions[key].setChecked(checked)
            handler(checked)
        self.save_ui_settings()

    def find_next(self) -> None:
        self.find_in_document(backward=False)

    def find_previous(self) -> None:
        self.find_in_document(backward=True)

    def find_in_document(self, *, backward: bool) -> None:
        if not self.find_bar.isVisible() or self.view_mode == "reading":
            self.show_find_bar()
        text = self.find_box.text()
        if not text:
            return

        flags = QTextDocument.FindFlag(0)
        if self.find_case_checkbox.isChecked():
            flags |= QTextDocument.FindFlag.FindCaseSensitively
        if backward:
            flags |= QTextDocument.FindFlag.FindBackward

        found = self.editor.find(text, flags)
        if not found:
            cursor = self.editor.textCursor()
            move_to = QTextCursor.MoveOperation.End if backward else QTextCursor.MoveOperation.Start
            cursor.movePosition(move_to)
            self.editor.setTextCursor(cursor)
            found = self.editor.find(text, flags)

        if not found:
            self.statusBar().showMessage(self.tr("not_found", text=text), 2500)
        else:
            self._last_find_text = text
            direction = self.tr("previous_result" if backward else "next_result")
            self.statusBar().showMessage(self.tr("found", direction=direction, text=text), 1500)

    def toggle_theme(self) -> None:
        self.apply_theme("dark" if self.theme == "light" else "light")

    def _apply_app_palette(self) -> None:
        t = THEMES[self.theme]
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor(t["preview_bg"]))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(t["preview_fg"]))
        palette.setColor(QPalette.ColorRole.Base, QColor(t["editor_bg"]))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor(t["line_bg"]))
        palette.setColor(QPalette.ColorRole.Text, QColor(t["editor_fg"]))
        palette.setColor(QPalette.ColorRole.Button, QColor(t["line_bg"]))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor(t["preview_fg"]))
        palette.setColor(QPalette.ColorRole.Highlight, QColor(t["selection"]))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor(t["preview_fg"]))
        palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(t["preview_inline_code_bg"]))
        palette.setColor(QPalette.ColorRole.ToolTipText, QColor(t["preview_fg"]))

        muted = QColor(t["preview_muted"])
        palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, muted)
        palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, muted)
        palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, muted)

        app = QApplication.instance()
        if app is not None:
            app.setPalette(palette)

    def apply_theme(self, theme: str) -> None:
        self.theme = theme if theme in THEMES else "light"
        self._apply_app_palette()
        self.renderer.set_theme(self.theme)
        for index in range(self.document_tabs.count()):
            editor = self.document_tabs.widget(index)
            if isinstance(editor, MarkdownEditor):
                editor.apply_theme(self.theme)
        self.setStyleSheet(APP_THEME_QSS[self.theme])
        if hasattr(self, "actions"):
            self.update_theme_action_text()
            self._apply_command_icons()
        self.update_preview()

    def toggle_autosave(self, checked: bool) -> None:
        self.autosave_enabled = checked
        for editor, timer in self.document_autosave_timers.items():
            if checked and editor.document().isModified():
                timer.start()
            else:
                timer.stop()
        state = self.tr("enabled_m" if checked else "disabled_m")
        self.statusBar().showMessage(self.tr("autosave_state", state=state), 2500)

    def toggle_line_wrap(self, checked: bool) -> None:
        self.set_line_wrap(checked)
        state = self.tr("enabled_m" if checked else "disabled_m")
        self.statusBar().showMessage(self.tr("word_wrap_state", state=state), 2500)

    def toggle_preview_scroll_sync(self, checked: bool) -> None:
        self.sync_preview_scroll_enabled = checked
        state = self.tr("enabled_f" if checked else "disabled_f")
        self.scroll_sync.align()
        self.statusBar().showMessage(self.tr("sync_state", state=state), 2500)

    def set_line_wrap(self, enabled: bool) -> None:
        mode = QPlainTextEdit.LineWrapMode.WidgetWidth if enabled else QPlainTextEdit.LineWrapMode.NoWrap
        for index in range(self.document_tabs.count()):
            editor = self.document_tabs.widget(index)
            if isinstance(editor, MarkdownEditor):
                editor.setLineWrapMode(mode)
                editor.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff if enabled else Qt.ScrollBarPolicy.ScrollBarAsNeeded)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        for index in range(self.document_tabs.count()):
            self.document_tabs.setCurrentIndex(index)
            if not self.maybe_save():
                event.ignore()
                return
        self.save_ui_settings()
        self.update_checker.cancel()
        self.pdf_exporter.cancel()
        self.scroll_sync.timer.stop()
        event.accept()
