from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
try:
    from PyQt6.QtGui import QAction, QFileSystemModel, QKeySequence
except ImportError:
    from PyQt6.QtGui import QAction, QKeySequence
    from PyQt6.QtWidgets import QFileSystemModel
from PyQt6.QtWidgets import QAbstractItemView, QCheckBox, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMenu, QMessageBox, QPushButton, QSizePolicy, QStackedWidget, QToolButton, QTreeView, QVBoxLayout, QWidget

try:
    from .utils import SearchHit, is_markdown_file
    from .ui_icons import ui_icon
except ImportError:
    from utils import SearchHit, is_markdown_file
    from ui_icons import ui_icon

class WorkspacePanel(QWidget):
    """Sidebar containing workspace files, recent files and global search results."""

    def __init__(self, main_window: "MainWindow") -> None:
        super().__init__()
        self.main_window = main_window
        self.workspace_dir: Path | None = None
        self.section = "files"
        self.setObjectName("workspacePanel")
        self.setMinimumWidth(190)
        self.setMaximumWidth(300)

        self.model = QFileSystemModel(self)
        self.model.setNameFilters(["*.md", "*.markdown", "*.mdown", "*.mkd", "*.txt"])
        self.model.setNameFilterDisables(False)
        self.model.setReadOnly(False)

        self.root_label = QLabel("Workspace: —")
        self.root_label.setWordWrap(False)
        self.root_label.setMinimumWidth(0)
        self.root_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.root_label.setObjectName("sidebarTitle")

        self.choose_button = QToolButton()
        self.choose_button.clicked.connect(self.main_window.choose_workspace)
        self.new_note_button = QToolButton()
        self.new_note_button.clicked.connect(self.main_window.new_note_in_workspace)

        header = QHBoxLayout()
        header.setContentsMargins(12, 6, 8, 6)
        header.addWidget(self.root_label, 1)
        header.addWidget(self.new_note_button)
        header.addWidget(self.choose_button)
        header_widget = QWidget()
        header_widget.setLayout(header)
        header_widget.setFixedHeight(40)

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Cerca nel workspace…")
        self.search_box.returnPressed.connect(self.main_window.search_workspace)
        self.search_box.setMinimumWidth(0)
        self.search_box.setClearButtonEnabled(True)
        self.search_button = QPushButton("Cerca")
        self.search_button.clicked.connect(self.main_window.search_workspace)
        self.case_sensitive_box = QCheckBox("Maiuscole")

        self.tabs = QStackedWidget()

        self.tree = QTreeView()
        self.tree.setModel(self.model)
        self.tree.setSortingEnabled(True)
        self.tree.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        self.tree.doubleClicked.connect(self.on_tree_double_clicked)
        self.tree.setAlternatingRowColors(False)
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(14)
        self.tree.setUniformRowHeights(True)
        self.tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.open_tree_context_menu)
        for column in range(1, 4):
            self.tree.hideColumn(column)
        self.file_page = QWidget()
        file_layout = QVBoxLayout(self.file_page)
        file_layout.setContentsMargins(6, 0, 6, 8)
        file_layout.setSpacing(12)
        self.empty_label = QLabel()
        self.empty_label.setWordWrap(True)
        self.empty_label.setObjectName("emptyWorkspace")
        self.empty_open_button = QPushButton()
        self.empty_open_button.clicked.connect(self.main_window.choose_workspace)
        file_layout.addWidget(self.empty_label)
        file_layout.addWidget(self.empty_open_button)
        file_layout.addWidget(self.tree, 1)
        self.tabs.addWidget(self.file_page)

        self.rename_action = QAction("Rinomina", self)
        self.rename_action.setShortcut(QKeySequence("F2"))
        self.rename_action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.rename_action.triggered.connect(self.rename_selected_file)
        self.tree.addAction(self.rename_action)

        self.delete_action = QAction("Elimina", self)
        self.delete_action.setShortcut(QKeySequence.StandardKey.Delete)
        self.delete_action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.delete_action.triggered.connect(self.delete_selected_file)
        self.tree.addAction(self.delete_action)

        self.recent_list = QListWidget()
        self.recent_list.itemDoubleClicked.connect(self.on_recent_double_clicked)
        self.tabs.addWidget(self.recent_list)

        self.results_list = QListWidget()
        self.results_list.setWordWrap(True)
        self.results_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.results_list.itemDoubleClicked.connect(self.on_result_double_clicked)
        self.search_page = QWidget()
        search_layout = QVBoxLayout(self.search_page)
        search_layout.setContentsMargins(10, 0, 10, 8)
        search_layout.setSpacing(8)
        search_layout.addWidget(self.search_box)
        search_options = QHBoxLayout()
        search_options.addWidget(self.case_sensitive_box, 1)
        search_options.addWidget(self.search_button)
        search_layout.addLayout(search_options)
        search_layout.addWidget(self.results_list, 1)
        self.tabs.addWidget(self.search_page)

        self.outline_list = QListWidget()
        self.outline_list.setWordWrap(True)
        self.outline_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.outline_list.itemDoubleClicked.connect(self.on_outline_double_clicked)
        self.tabs.addWidget(self.outline_list)
        self.sections = {"files": self.file_page, "search": self.search_page, "recent": self.recent_list, "outline": self.outline_list}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(header_widget)
        layout.addWidget(self.tabs, 1)
        self.apply_theme("#64748b")

    def set_workspace(self, path: Path | None) -> None:
        self.workspace_dir = path if path and path.is_dir() else None
        if self.workspace_dir:
            root_index = self.model.setRootPath(str(self.workspace_dir))
            self.tree.setRootIndex(root_index)
        else:
            self.model.setRootPath("")
        self.tree.setVisible(self.workspace_dir is not None)
        self.empty_label.setVisible(self.workspace_dir is None)
        self.empty_open_button.setVisible(self.workspace_dir is None)
        self.show_section(self.section)

    def show_section(self, section: str) -> None:
        if section not in self.sections:
            return
        self.section = section
        self.tabs.setCurrentWidget(self.sections[section])
        self.new_note_button.setVisible(section == "files")
        self.choose_button.setVisible(section == "files")
        title = self.workspace_dir.name or str(self.workspace_dir) if self.workspace_dir else self.main_window.tr("tab_file")
        keys = {"search": "search", "outline": "tab_outline", "recent": "tab_recent"}
        self.root_label.setText(title if section == "files" else self.main_window.tr(keys[section]))
        self.root_label.setToolTip(str(self.workspace_dir) if self.workspace_dir and section == "files" else self.root_label.text())

    def apply_theme(self, color: str) -> None:
        self.choose_button.setIcon(ui_icon("folder", color))
        self.new_note_button.setIcon(ui_icon("plus", color))

    def apply_language(self) -> None:
        self.show_section(self.section)
        self.choose_button.setToolTip(self.main_window.tr("open_workspace"))
        self.choose_button.setAccessibleName(self.main_window.tr("open_workspace"))
        self.new_note_button.setToolTip(self.main_window.tr("new_note"))
        self.new_note_button.setAccessibleName(self.main_window.tr("new_note"))
        self.empty_label.setText(self.main_window.tr("workspace_welcome"))
        self.empty_open_button.setText(self.main_window.tr("open_folder"))
        self.search_box.setPlaceholderText(self.main_window.tr("search_workspace_placeholder"))
        self.search_button.setText(self.main_window.tr("search"))
        self.case_sensitive_box.setText(self.main_window.tr("case_sensitive"))
        self.rename_action.setText(self.main_window.tr("rename"))
        self.delete_action.setText(self.main_window.tr("delete"))

    def refresh_recent(self, recent_files: list[Path]) -> None:
        self.recent_list.clear()
        for path in recent_files:
            item = QListWidgetItem(path.name)
            item.setToolTip(str(path))
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            if not path.exists():
                item.setText(f"{path.name}  [{self.main_window.tr('missing')}]")
            self.recent_list.addItem(item)

    def show_search_results(self, hits: list[SearchHit], workspace_dir: Path | None) -> None:
        self.results_list.clear()
        for hit in hits:
            try:
                display_path = hit.path.relative_to(workspace_dir) if workspace_dir else hit.path
            except ValueError:
                display_path = hit.path
            item = QListWidgetItem(f"{display_path}:{hit.line_number}\n{hit.snippet}")
            item.setToolTip(str(hit.path))
            item.setData(Qt.ItemDataRole.UserRole, {"path": str(hit.path), "line": hit.line_number})
            self.results_list.addItem(item)
        self.main_window.show_sidebar_section("search", toggle=False)

    def update_outline(self, headings: list[tuple[int, str, int]]) -> None:
        self.outline_list.clear()
        if not headings:
            item = QListWidgetItem(self.main_window.tr("no_headings"))
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
            self.outline_list.addItem(item)
            return
        for level, title, line_number in headings:
            indent = "  " * max(0, level - 1)
            item = QListWidgetItem(f"{indent}{title}")
            item.setToolTip(self.main_window.tr("line_tooltip", line=line_number))
            item.setData(Qt.ItemDataRole.UserRole, line_number)
            self.outline_list.addItem(item)

    def on_tree_double_clicked(self, index) -> None:
        path = Path(self.model.filePath(index))
        if path.is_dir():
            if self.tree.isExpanded(index):
                self.tree.collapse(index)
            else:
                self.tree.expand(index)
            return
        if is_markdown_file(path):
            if self.main_window.open_file_path(path):
                self.main_window.dismiss_compact_sidebar()

    def open_tree_context_menu(self, position) -> None:
        index = self.tree.indexAt(position)
        if not index.isValid():
            return

        path = Path(self.model.filePath(index))
        if not is_markdown_file(path):
            return

        self.tree.setCurrentIndex(index.siblingAtColumn(0))
        menu = QMenu(self)
        open_action = menu.addAction(self.main_window.tr("open"))
        rename_action = menu.addAction(self.main_window.tr("rename"))
        menu.addSeparator()
        delete_action = menu.addAction(self.main_window.tr("delete"))
        chosen = menu.exec(self.tree.viewport().mapToGlobal(position))
        if chosen == open_action:
            if self.main_window.open_file_path(path):
                self.main_window.dismiss_compact_sidebar()
        elif chosen == rename_action:
            self.rename_file(path)
        elif chosen == delete_action:
            self.delete_file(path)

    def rename_selected_file(self) -> None:
        index = self.tree.currentIndex()
        if not index.isValid():
            return
        self.rename_file(Path(self.model.filePath(index.siblingAtColumn(0))))

    def delete_selected_file(self) -> None:
        index = self.tree.currentIndex()
        if not index.isValid():
            return
        self.delete_file(Path(self.model.filePath(index.siblingAtColumn(0))))

    def rename_file(self, path: Path) -> None:
        if not is_markdown_file(path):
            return

        current_path = getattr(self.main_window, "current_path", None)
        if current_path and Path(current_path) == path and self.main_window.editor.document().isModified():
            if not self.main_window.maybe_save():
                return

        dialog = QInputDialog(self)
        dialog.setWindowTitle(self.main_window.tr("rename_file"))
        dialog.setLabelText(self.main_window.tr("new_name"))
        dialog.setTextValue(path.name)
        dialog.setMinimumWidth(560)
        dialog.resize(620, 150)

        line_edit = dialog.findChild(QLineEdit)
        if line_edit is not None:
            line_edit.setMinimumWidth(440)
            line_edit.setSelection(0, len(path.stem))

        if not dialog.exec():
            return

        new_name = dialog.textValue().strip()
        if not new_name:
            return
        if "/" in new_name or "\\" in new_name:
            QMessageBox.warning(self, self.main_window.tr("invalid_name"), self.main_window.tr("invalid_name_body"))
            return

        if Path(new_name).suffix == "":
            new_name = f"{new_name}.md"

        target = path.with_name(new_name)
        if target == path:
            return
        if target.exists():
            QMessageBox.warning(
                self,
                self.main_window.tr("file_exists"),
                self.main_window.tr("file_exists_body", name=target.name),
            )
            return

        try:
            path.rename(target)
        except OSError as exc:
            QMessageBox.critical(
                self,
                self.main_window.tr("rename_error"),
                self.main_window.tr("rename_error_body", error=exc),
            )
            return

        self.main_window.on_workspace_file_renamed(path, target)

    def delete_file(self, path: Path) -> None:
        if not is_markdown_file(path):
            return

        result = QMessageBox.question(
            self,
            self.main_window.tr("delete_file"),
            self.main_window.tr("delete_file_body", name=path.name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if result != QMessageBox.StandardButton.Yes:
            return

        current_path = getattr(self.main_window, "current_path", None)
        if current_path and Path(current_path) == path and self.main_window.editor.document().isModified():
            if not self.main_window.maybe_save():
                return

        try:
            path.unlink()
        except OSError as exc:
            QMessageBox.critical(
                self,
                self.main_window.tr("delete_error"),
                self.main_window.tr("delete_error_body", error=exc),
            )
            return

        self.main_window.on_workspace_file_deleted(path)

    def on_recent_double_clicked(self, item: QListWidgetItem) -> None:
        path = Path(str(item.data(Qt.ItemDataRole.UserRole)))
        if self.main_window.open_file_path(path):
            self.main_window.dismiss_compact_sidebar()

    def on_result_double_clicked(self, item: QListWidgetItem) -> None:
        payload = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(payload, dict):
            if self.main_window.open_file_path(Path(payload["path"]), line_number=int(payload.get("line", 1))):
                self.main_window.dismiss_compact_sidebar()

    def on_outline_double_clicked(self, item: QListWidgetItem) -> None:
        line_number = item.data(Qt.ItemDataRole.UserRole)
        if line_number:
            self.main_window.goto_line(int(line_number))
            self.main_window.dismiss_compact_sidebar()
