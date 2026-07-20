from __future__ import annotations

import os
import json
import re
import shutil
from pathlib import Path

from PyQt6.QtCore import QEvent, QSettings, QSize, QTimer, QUrl, Qt
from PyQt6.QtGui import QAction, QActionGroup, QColor, QFont, QIcon, QKeySequence, QPainter, QPalette, QPixmap, QTextCursor, QTextDocument
from PyQt6.QtWidgets import QApplication, QCheckBox, QFileDialog, QInputDialog, QLabel, QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit, QPushButton, QSizePolicy, QSplitter, QStatusBar, QStyle, QTabWidget, QToolBar, QVBoxLayout, QWidget
from PyQt6.QtWebEngineCore import QWebEngineSettings
from PyQt6.QtWebEngineWidgets import QWebEngineView

try:
    from .config import APP_NAME, APP_THEME_QSS, DEFAULT_MARKDOWN, MAX_RECENT_FILES, MAX_SEARCH_FILE_BYTES, MAX_SEARCH_RESULTS, ORG_NAME, THEMES, VERSION
    from .editor import MarkdownEditor
    from .i18n import SUPPORTED_LANGUAGES, translate
    from .renderer import MarkdownRenderer
    from .utils import SearchHit, as_bool, coerce_splitter_sizes, is_markdown_file, read_text_file, save_settings_list, settings_list
    from .web_page import LinkInterceptorPage
    from .workspace import WorkspacePanel
except ImportError:
    from config import APP_NAME, APP_THEME_QSS, DEFAULT_MARKDOWN, MAX_RECENT_FILES, MAX_SEARCH_FILE_BYTES, MAX_SEARCH_RESULTS, ORG_NAME, THEMES, VERSION
    from editor import MarkdownEditor
    from i18n import SUPPORTED_LANGUAGES, translate
    from renderer import MarkdownRenderer
    from utils import SearchHit, as_bool, coerce_splitter_sizes, is_markdown_file, read_text_file, save_settings_list, settings_list
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
        self.current_path: Path | None = None
        self.document_paths: dict[MarkdownEditor, Path | None] = {}
        self.workspace_dir: Path | None = self._load_workspace_dir()
        self.recent_files: list[Path] = self._load_recent_files()
        self._loading = False
        self._last_find_text = ""
        self._pending_pdf_path: Path | None = None
        self._pending_pdf_retries = 0
        self._syncing_preview_from_editor = False
        self._syncing_editor_from_preview = False

        self.renderer = MarkdownRenderer(self.theme)

        self.setWindowTitle(APP_NAME)
        self.resize(1480, 880)

        self.preview = QWebEngineView()
        self.preview.setPage(LinkInterceptorPage(self.preview))
        self.preview.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        self.preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.preview.installEventFilter(self)
        try:
            self.preview.page().pdfPrintingFinished.connect(self.on_pdf_printing_finished)
        except Exception:
            pass
        self.preview.loadFinished.connect(self.on_preview_load_finished)

        self.find_box = QLineEdit()
        self.find_box.setPlaceholderText("Trova nel testo...")
        self.find_box.returnPressed.connect(self.find_next)
        self.find_case_checkbox = QCheckBox("Maiuscole")

        self.update_timer = QTimer(self)
        self.update_timer.setSingleShot(True)
        self.update_timer.setInterval(220)
        self.update_timer.timeout.connect(self.update_preview)

        self.autosave_timer = QTimer(self)
        self.autosave_timer.setSingleShot(True)
        self.autosave_timer.setInterval(1500)
        self.autosave_timer.timeout.connect(self.autosave_current_file)

        self.preview_scroll_timer = QTimer(self)
        self.preview_scroll_timer.setSingleShot(True)
        self.preview_scroll_timer.setInterval(35)
        self.preview_scroll_timer.timeout.connect(self.sync_preview_scroll)

        self.editor_scroll_timer = QTimer(self)
        self.editor_scroll_timer.setSingleShot(True)
        self.editor_scroll_timer.setInterval(80)
        self.editor_scroll_timer.timeout.connect(self.sync_editor_scroll_from_preview)

        self.document_tabs = QTabWidget()
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

    def tr(self, key: str, **kwargs) -> str:
        return translate(self.language, key, **kwargs)

    def eventFilter(self, watched, event) -> bool:  # type: ignore[override]
        is_preview_widget = watched is self.preview or (
            hasattr(self, "preview") and isinstance(watched, QWidget) and self.preview.isAncestorOf(watched)
        )
        if is_preview_widget and self.sync_preview_scroll_enabled:
            if event.type() in {
                QEvent.Type.Wheel,
                QEvent.Type.KeyRelease,
                QEvent.Type.MouseButtonRelease,
            }:
                self.schedule_editor_scroll_sync_from_preview()
        return super().eventFilter(watched, event)

    def on_preview_load_finished(self, _ok: bool) -> None:
        self.install_preview_event_filters()
        self.schedule_preview_scroll_sync()
        if self._pending_pdf_path:
            self._pending_pdf_retries = 0
            self.wait_for_preview_before_pdf()

    def install_preview_event_filters(self) -> None:
        self.preview.installEventFilter(self)
        for child in self.preview.findChildren(QWidget):
            child.installEventFilter(self)

    @property
    def editor(self) -> MarkdownEditor:
        editor = self.document_tabs.currentWidget()
        if isinstance(editor, MarkdownEditor):
            return editor
        raise RuntimeError("No active document editor")

    def _create_document_tab(self, text: str = "", path: Path | None = None, *, modified: bool = False) -> MarkdownEditor:
        editor = MarkdownEditor(self.theme)
        editor.textChanged.connect(self.on_text_changed)
        editor.cursorPositionChanged.connect(self.update_status)
        editor.verticalScrollBar().valueChanged.connect(self.schedule_preview_scroll_sync)
        editor.imagesDropped.connect(self.insert_dropped_images)

        self._loading = True
        editor.setPlainText(text)
        editor.document().setModified(modified)
        self._loading = False
        if isinstance(getattr(self, "actions", None), dict):
            editor.setLineWrapMode(
                QPlainTextEdit.LineWrapMode.WidgetWidth
                if self.actions["wrap"].isChecked()
                else QPlainTextEdit.LineWrapMode.NoWrap
            )

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
        editor = self.editor
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
        self.editor_preview_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.editor_preview_splitter.addWidget(self.document_tabs)
        self.editor_preview_splitter.addWidget(self.preview)
        self.editor_preview_splitter.setSizes([650, 720])

        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.addWidget(self.workspace_panel)
        self.main_splitter.addWidget(self.editor_preview_splitter)
        self.main_splitter.setSizes([315, 1165])
        self.setCentralWidget(self.main_splitter)

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
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(24, 24))
        self.addToolBar(toolbar)

        def decorate(action: QAction, icon: QStyle.StandardPixmap, tooltip: str) -> None:
            action.setIcon(self.style().standardIcon(icon))
            action.setToolTip(tooltip)

        menu_file = self.menuBar().addMenu("File")
        menu_edit = self.menuBar().addMenu("Modifica")
        menu_view = self.menuBar().addMenu("Vista")
        menu_workspace = self.menuBar().addMenu("Workspace")
        menu_export = self.menuBar().addMenu("Export")
        menu_language = menu_view.addMenu("Lingua")
        self.menus = {
            "file": menu_file,
            "edit": menu_edit,
            "view": menu_view,
            "workspace": menu_workspace,
            "export": menu_export,
            "language": menu_language,
        }

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
        toolbar.addAction(open_workspace_action)
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
        toolbar.addAction(export_html_action)
        menu_export.addAction(export_html_action)

        export_pdf_action = QAction("Esporta PDF", self)
        export_pdf_action.setShortcut(QKeySequence("Ctrl+Shift+P"))
        export_pdf_action.triggered.connect(self.export_pdf)
        export_pdf_action.setIcon(self._document_icon("PDF", "#dc2626"))
        export_pdf_action.setToolTip("Esporta il documento come PDF")
        toolbar.addAction(export_pdf_action)
        menu_export.addAction(export_pdf_action)

        toolbar.addSeparator()

        bold_action = QAction("Grassetto", self)
        bold_action.setShortcut(QKeySequence("Ctrl+B"))
        bold_action.triggered.connect(lambda: self.wrap_selection("**", "**", self.tr("text_placeholder")))
        bold_action.setToolTip("Grassetto")
        toolbar.addAction(bold_action)
        menu_edit.addAction(bold_action)

        italic_action = QAction("Corsivo", self)
        italic_action.setShortcut(QKeySequence("Ctrl+I"))
        italic_action.triggered.connect(lambda: self.wrap_selection("*", "*", self.tr("text_placeholder")))
        italic_action.setToolTip("Corsivo")
        toolbar.addAction(italic_action)
        menu_edit.addAction(italic_action)

        code_action = QAction("Codice", self)
        code_action.setShortcut(QKeySequence("Ctrl+K"))
        code_action.triggered.connect(lambda: self.wrap_selection("`", "`", self.tr("code_placeholder")))
        code_action.setToolTip("Codice inline")
        toolbar.addAction(code_action)
        menu_edit.addAction(code_action)

        code_block_action = QAction("Blocco codice", self)
        code_block_action.setShortcut(QKeySequence("Ctrl+Shift+K"))
        code_block_action.triggered.connect(self.insert_code_block)
        code_block_action.setToolTip("Blocco codice")
        toolbar.addAction(code_block_action)
        menu_edit.addAction(code_block_action)

        heading_action = QAction("H2", self)
        heading_action.triggered.connect(lambda: self.prefix_current_line("## "))
        toolbar.addAction(heading_action)
        menu_edit.addAction(heading_action)

        list_action = QAction("Lista", self)
        list_action.triggered.connect(lambda: self.prefix_current_line("- "))
        toolbar.addAction(list_action)
        menu_edit.addAction(list_action)

        quote_action = QAction("Quote", self)
        quote_action.triggered.connect(lambda: self.prefix_current_line("> "))
        toolbar.addAction(quote_action)
        menu_edit.addAction(quote_action)

        link_action = QAction("Link", self)
        link_action.setShortcut(QKeySequence("Ctrl+Shift+L"))
        link_action.triggered.connect(self.insert_link)
        link_action.setToolTip("Inserisci link")
        toolbar.addAction(link_action)
        menu_edit.addAction(link_action)

        image_action = QAction("Immagine", self)
        image_action.setShortcut(QKeySequence("Ctrl+Shift+I"))
        image_action.triggered.connect(self.insert_image)
        image_action.setToolTip("Inserisci immagine")
        toolbar.addAction(image_action)
        menu_edit.addAction(image_action)

        table_action = QAction("Tabella", self)
        table_action.setShortcut(QKeySequence("Ctrl+Shift+T"))
        table_action.triggered.connect(self.insert_table)
        table_action.setToolTip("Inserisci tabella")
        toolbar.addAction(table_action)
        menu_edit.addAction(table_action)

        toolbar.addSeparator()

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

        toolbar.addSeparator()
        toolbar.addWidget(QLabel("  "))
        toolbar.addWidget(self.find_box)
        toolbar.addWidget(self.find_case_checkbox)

        self.find_button = QPushButton("Trova")
        self.find_button.clicked.connect(self.find_next)
        toolbar.addWidget(self.find_button)

        self.find_prev_button = QPushButton("Precedente")
        self.find_prev_button.clicked.connect(self.find_previous)
        toolbar.addWidget(self.find_prev_button)

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
        }

    def _build_statusbar(self) -> None:
        status = QStatusBar()
        self.setStatusBar(status)
        self.path_label = QLabel("Senza file")
        self.status_label = QLabel("Pronto")
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
            self.find_button.setText(self.tr("find"))
        if hasattr(self, "find_prev_button"):
            self.find_prev_button.setText(self.tr("previous"))
        self.workspace_panel.apply_language()
        self.workspace_panel.refresh_recent(self.recent_files)
        self.update_outline()
        self.update_theme_action_text()
        self.update_window_title()
        self.update_status()

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
            self.main_splitter.setSizes(main_sizes)

        editor_sizes = coerce_splitter_sizes(self.settings.value("editor_preview_splitter_sizes"), 2)
        # Backward compatibility with v0.2 key.
        if not editor_sizes:
            editor_sizes = coerce_splitter_sizes(self.settings.value("splitter_sizes"), 2)
        if editor_sizes:
            self.editor_preview_splitter.setSizes(editor_sizes)

        line_wrap = as_bool(self.settings.value("line_wrap", True), True)
        self.actions["wrap"].setChecked(line_wrap)
        self.set_line_wrap(line_wrap)

        sidebar_visible = as_bool(self.settings.value("sidebar_visible", True), True)
        self.workspace_panel.setVisible(sidebar_visible)

        sync_scroll = as_bool(self.settings.value("sync_preview_scroll_enabled", True), True)
        self.sync_preview_scroll_enabled = sync_scroll
        self.actions["sync_scroll"].setChecked(sync_scroll)

    def save_ui_settings(self) -> None:
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("main_splitter_sizes", self.main_splitter.sizes())
        self.settings.setValue("editor_preview_splitter_sizes", self.editor_preview_splitter.sizes())
        self.settings.setValue("theme", self.theme)
        self.settings.setValue("language", self.language)
        self.settings.setValue("autosave_enabled", self.autosave_enabled)
        self.settings.setValue("line_wrap", self.actions["wrap"].isChecked())
        self.settings.setValue("sync_preview_scroll_enabled", self.sync_preview_scroll_enabled)
        self.settings.setValue("sidebar_visible", self.workspace_panel.isVisible())
        if self.workspace_dir:
            self.settings.setValue("workspace_dir", str(self.workspace_dir))
        if self.current_path:
            self.settings.setValue("last_dir", str(self.current_path.parent))
        save_settings_list(self.settings, "recent_files", [str(path) for path in self.recent_files])

    def on_text_changed(self) -> None:
        if self._loading:
            return
        self.schedule_preview_update()
        self.update_outline()
        self.update_current_tab_title()
        self.update_window_title()
        self.update_status()
        if not self._loading and self.autosave_enabled:
            self.autosave_timer.start()

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
            candidate.write_text(initial, encoding="utf-8", newline="\n")
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
        path = Path(path)
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

    def _write_markdown(self, path: Path, *, autosave: bool) -> bool:
        try:
            path.write_text(self.editor.toPlainText(), encoding="utf-8", newline="\n")
        except OSError as exc:
            if not autosave:
                QMessageBox.critical(self, self.tr("save_error"), self.tr("save_error_body", error=exc))
            else:
                self.statusBar().showMessage(self.tr("autosave_failed", error=exc), 3500)
            return False

        self.set_current_path(path)
        self.add_recent_path(path)
        self.editor.document().setModified(False)
        self.update_current_tab_title()
        self.update_window_title()
        self.update_preview()
        self.update_status()
        if autosave:
            self.statusBar().showMessage(self.tr("autosaved", name=path.name), 1800)
        else:
            self.statusBar().showMessage(self.tr("saved", name=path.name), 2500)
        return True

    def autosave_current_file(self) -> None:
        if not self.autosave_enabled or self.current_path is None:
            return
        if not self.editor.document().isModified():
            return
        self._write_markdown(self.current_path, autosave=True)

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

        self._pending_pdf_path = path
        self.update_preview()
        self.statusBar().showMessage(self.tr("pdf_generation", name=path.name), 3500)

    def wait_for_preview_before_pdf(self) -> None:
        if not self._pending_pdf_path:
            return

        script = """
(() => {
  const hasMermaid = Boolean(document.querySelector("pre.mermaid, .mermaid[data-processed='true']"));
  return !hasMermaid || Boolean(window.markdownStudioMermaidReady);
})();
"""
        try:
            self.preview.page().runJavaScript(script, self.print_pending_pdf_if_ready)
        except RuntimeError:
            self.print_pending_pdf_if_ready(True)

    def print_pending_pdf_if_ready(self, ready) -> None:
        path = self._pending_pdf_path
        if not path:
            return

        if not ready and self._pending_pdf_retries < 50:
            self._pending_pdf_retries += 1
            QTimer.singleShot(100, self.wait_for_preview_before_pdf)
            return

        self._pending_pdf_path = None
        self._pending_pdf_retries = 0
        try:
            self.preview.page().printToPdf(str(path))
        except Exception as exc:
            QMessageBox.critical(self, self.tr("export_pdf_error"), self.tr("export_pdf_error_body", error=exc))

    def on_pdf_printing_finished(self, file_path: str, success: bool) -> None:
        if success:
            self.statusBar().showMessage(self.tr("pdf_exported", name=Path(file_path).name), 4500)
        else:
            QMessageBox.warning(self, self.tr("pdf_not_generated"), self.tr("pdf_not_generated_body", path=file_path))

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
        if not self.workspace_panel.isVisible():
            self.workspace_panel.setVisible(True)
        self.workspace_panel.tabs.setCurrentWidget(self.workspace_panel.results_list)
        self.workspace_panel.search_box.setFocus()
        self.workspace_panel.search_box.selectAll()

    def toggle_sidebar(self) -> None:
        self.workspace_panel.setVisible(not self.workspace_panel.isVisible())

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
        html_doc = self.renderer.to_html_document(self.editor.toPlainText(), title=title)

        if self.current_path:
            base_url = QUrl.fromLocalFile(str(self.current_path.parent) + os.sep)
        elif self.workspace_dir:
            base_url = QUrl.fromLocalFile(str(self.workspace_dir) + os.sep)
        else:
            base_url = QUrl.fromLocalFile(str(Path.cwd()) + os.sep)

        self.preview.setHtml(html_doc, base_url)
        self.schedule_preview_scroll_sync()

    def schedule_preview_scroll_sync(self) -> None:
        if self.sync_preview_scroll_enabled and not self._syncing_editor_from_preview:
            self.preview_scroll_timer.start()

    def schedule_editor_scroll_sync_from_preview(self) -> None:
        if self.sync_preview_scroll_enabled and not self._syncing_preview_from_editor:
            self.editor_scroll_timer.start()

    def sync_preview_scroll(self) -> None:
        if not self.sync_preview_scroll_enabled:
            return

        text_lines = self.editor.toPlainText().splitlines() or [""]
        total_lines = len(text_lines)
        top_line = max(1, min(total_lines, self.editor.firstVisibleBlock().blockNumber() + 1))
        line_ratio = 0.0 if total_lines <= 1 else (top_line - 1) / (total_lines - 1)
        payload = {
            "line": top_line,
            "totalLines": total_lines,
            "ratio": max(0.0, min(1.0, line_ratio)),
        }

        script = f"""
(() => {{
  const doc = document.documentElement;
  const body = document.body;
  const scrollHeight = Math.max(
    doc ? doc.scrollHeight : 0,
    body ? body.scrollHeight : 0
  );
  const maxScroll = Math.max(0, scrollHeight - window.innerHeight);
  const payload = {json.dumps(payload)};

  const anchors = Array.from(document.querySelectorAll("[data-source-line]"))
    .map((element) => {{
      const line = Number(element.getAttribute("data-source-line"));
      return {{
        line,
        y: element.getBoundingClientRect().top + window.scrollY,
      }};
    }})
    .filter((anchor) => Number.isFinite(anchor.line) && Number.isFinite(anchor.y))
    .sort((a, b) => a.line - b.line || a.y - b.y);

  if (anchors.length) {{
    const sourceLine = Math.max(1, Math.min(payload.totalLines || 1, payload.line || 1));
    let previous = {{ line: 1, y: 0 }};
    let next = {{ line: payload.totalLines || sourceLine, y: maxScroll }};

    for (const anchor of anchors) {{
      if (anchor.line <= sourceLine) {{
        previous = anchor;
      }} else {{
        next = anchor;
        break;
      }}
    }}

    if (sourceLine <= anchors[0].line) {{
      previous = {{ line: 1, y: 0 }};
      next = anchors[0];
    }} else if (sourceLine >= anchors[anchors.length - 1].line) {{
      previous = anchors[anchors.length - 1];
      next = {{ line: payload.totalLines || previous.line, y: maxScroll }};
    }}

    const lineSpan = Math.max(1, next.line - previous.line);
    const progress = Math.max(0, Math.min(1, (sourceLine - previous.line) / lineSpan));
    const target = previous.y + (next.y - previous.y) * progress;
    window.scrollTo(0, Math.max(0, Math.min(maxScroll, target)));
    return;
  }}

  window.scrollTo(0, maxScroll * (payload.ratio || 0));
}})();
"""
        try:
            self._syncing_preview_from_editor = True
            self.preview.page().runJavaScript(script)
            QTimer.singleShot(120, lambda: setattr(self, "_syncing_preview_from_editor", False))
        except RuntimeError:
            self._syncing_preview_from_editor = False
            pass

    def sync_editor_scroll_from_preview(self) -> None:
        if not self.sync_preview_scroll_enabled or self._syncing_preview_from_editor:
            return

        script = """
(() => {
  const doc = document.documentElement;
  const body = document.body;
  const scrollTop = window.scrollY || (doc ? doc.scrollTop : 0) || (body ? body.scrollTop : 0) || 0;
  const scrollHeight = Math.max(
    doc ? doc.scrollHeight : 0,
    body ? body.scrollHeight : 0
  );
  const maxScroll = Math.max(0, scrollHeight - window.innerHeight);
  const ratio = maxScroll <= 0 ? 0 : Math.max(0, Math.min(1, scrollTop / maxScroll));
  const anchors = Array.from(document.querySelectorAll("[data-source-line]"))
    .map((element) => {
      const line = Number(element.getAttribute("data-source-line"));
      return {
        line,
        y: element.getBoundingClientRect().top + window.scrollY,
      };
    })
    .filter((anchor) => Number.isFinite(anchor.line) && Number.isFinite(anchor.y))
    .sort((a, b) => a.line - b.line || a.y - b.y);

  if (!anchors.length) {
    return { mode: "ratio", ratio };
  }

  const viewportLine = scrollTop + 10;
  let previous = { line: 1, y: 0 };
  let next = null;
  for (const anchor of anchors) {
    if (anchor.y <= viewportLine) {
      previous = anchor;
    } else {
      next = anchor;
      break;
    }
  }
  if (!next) {
    next = { line: null, y: maxScroll };
  }

  const span = Math.max(1, next.y - previous.y);
  const progress = Math.max(0, Math.min(1, (viewportLine - previous.y) / span));
  return {
    mode: "sourceLines",
    previousLine: previous.line,
    nextLine: next.line,
    progress,
    ratio,
  };
})();
"""

        try:
            self.preview.page().runJavaScript(script, self.apply_preview_scroll_to_editor)
        except RuntimeError:
            pass

    def apply_preview_scroll_to_editor(self, payload) -> None:
        if not self.sync_preview_scroll_enabled or not isinstance(payload, dict):
            return

        text_lines = self.editor.toPlainText().splitlines() or [""]
        total_lines = len(text_lines)

        if payload.get("mode") == "sourceLines":
            previous_line = int(payload.get("previousLine", 1) or 1)
            next_line_value = payload.get("nextLine")
            next_line = int(next_line_value) if next_line_value else total_lines
            previous_line = max(1, min(total_lines, previous_line))
            next_line = max(previous_line, min(total_lines, next_line))
            progress = float(payload.get("progress", 0.0) or 0.0)
            target_line = round(previous_line + (next_line - previous_line) * max(0.0, min(1.0, progress)))
        else:
            ratio = float(payload.get("ratio", 0.0) or 0.0)
            target_line = round(1 + (total_lines - 1) * max(0.0, min(1.0, ratio)))

        scrollbar = self.editor.verticalScrollBar()
        target_value = max(0, min(scrollbar.maximum(), target_line - 1))
        self._syncing_editor_from_preview = True
        scrollbar.setValue(target_value)
        QTimer.singleShot(120, lambda: setattr(self, "_syncing_editor_from_preview", False))

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
        workspace = self.tr("workspace_suffix", path=self.workspace_dir) if self.workspace_dir else ""
        self.status_label.setText(
            self.tr("line_status", line=line, col=col, words=words, chars=chars, minutes=read_minutes)
        )
        if self.current_path:
            self.path_label.setText(f"{self.current_path}{workspace}")
        else:
            self.path_label.setText(self.tr("no_file_status", workspace=workspace))

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

    def find_next(self) -> None:
        self.find_in_document(backward=False)

    def find_previous(self) -> None:
        self.find_in_document(backward=True)

    def find_in_document(self, *, backward: bool) -> None:
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
        self.update_preview()

    def toggle_autosave(self, checked: bool) -> None:
        self.autosave_enabled = checked
        state = self.tr("enabled_m" if checked else "disabled_m")
        self.statusBar().showMessage(self.tr("autosave_state", state=state), 2500)

    def toggle_line_wrap(self, checked: bool) -> None:
        self.set_line_wrap(checked)
        state = self.tr("enabled_m" if checked else "disabled_m")
        self.statusBar().showMessage(self.tr("word_wrap_state", state=state), 2500)

    def toggle_preview_scroll_sync(self, checked: bool) -> None:
        self.sync_preview_scroll_enabled = checked
        state = self.tr("enabled_f" if checked else "disabled_f")
        if checked:
            self.schedule_preview_scroll_sync()
        self.statusBar().showMessage(self.tr("sync_state", state=state), 2500)

    def set_line_wrap(self, enabled: bool) -> None:
        mode = QPlainTextEdit.LineWrapMode.WidgetWidth if enabled else QPlainTextEdit.LineWrapMode.NoWrap
        for index in range(self.document_tabs.count()):
            editor = self.document_tabs.widget(index)
            if isinstance(editor, MarkdownEditor):
                editor.setLineWrapMode(mode)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        for index in range(self.document_tabs.count()):
            self.document_tabs.setCurrentIndex(index)
            if not self.maybe_save():
                event.ignore()
                return
        self.save_ui_settings()
        event.accept()
