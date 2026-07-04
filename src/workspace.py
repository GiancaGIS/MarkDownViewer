from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
try:
    from PyQt6.QtGui import QAction, QFileSystemModel, QKeySequence
except ImportError:
    from PyQt6.QtGui import QAction, QKeySequence
    from PyQt6.QtWidgets import QFileSystemModel
from PyQt6.QtWidgets import QAbstractItemView, QCheckBox, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMenu, QMessageBox, QPushButton, QTabWidget, QTreeView, QVBoxLayout, QWidget

try:
    from .utils import SearchHit, is_markdown_file
except ImportError:
    from utils import SearchHit, is_markdown_file

class WorkspacePanel(QWidget):
    """Sidebar containing workspace files, recent files and global search results."""

    def __init__(self, main_window: "MainWindow") -> None:
        super().__init__()
        self.main_window = main_window
        self.workspace_dir: Path | None = None

        self.model = QFileSystemModel(self)
        self.model.setNameFilters(["*.md", "*.markdown", "*.mdown", "*.mkd", "*.txt"])
        self.model.setNameFilterDisables(False)
        self.model.setReadOnly(False)

        self.root_label = QLabel("Workspace: —")
        self.root_label.setWordWrap(True)

        self.choose_button = QPushButton("Cartella…")
        self.choose_button.clicked.connect(self.main_window.choose_workspace)
        self.new_note_button = QPushButton("Nuova nota")
        self.new_note_button.clicked.connect(self.main_window.new_note_in_workspace)

        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.addWidget(self.choose_button)
        buttons.addWidget(self.new_note_button)

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Cerca nel workspace…")
        self.search_box.returnPressed.connect(self.main_window.search_workspace)
        self.search_button = QPushButton("Cerca")
        self.search_button.clicked.connect(self.main_window.search_workspace)
        self.case_sensitive_box = QCheckBox("Maiuscole")

        search_row = QHBoxLayout()
        search_row.setContentsMargins(0, 0, 0, 0)
        search_row.addWidget(self.search_box, 1)
        search_row.addWidget(self.search_button)

        self.tabs = QTabWidget()

        self.tree = QTreeView()
        self.tree.setModel(self.model)
        self.tree.setSortingEnabled(True)
        self.tree.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        self.tree.doubleClicked.connect(self.on_tree_double_clicked)
        self.tree.setAlternatingRowColors(True)
        self.tree.setHeaderHidden(False)
        self.tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.open_tree_context_menu)
        for column in range(1, 4):
            self.tree.hideColumn(column)
        self.tabs.addTab(self.tree, "File")

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
        self.tabs.addTab(self.recent_list, "Recenti")

        self.results_list = QListWidget()
        self.results_list.itemDoubleClicked.connect(self.on_result_double_clicked)
        self.tabs.addTab(self.results_list, "Risultati")

        self.outline_list = QListWidget()
        self.outline_list.itemDoubleClicked.connect(self.on_outline_double_clicked)
        self.tabs.addTab(self.outline_list, "Outline")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        layout.addWidget(self.root_label)
        layout.addLayout(buttons)
        layout.addLayout(search_row)
        layout.addWidget(self.case_sensitive_box)
        layout.addWidget(self.tabs, 1)

    def set_workspace(self, path: Path | None) -> None:
        self.workspace_dir = path if path and path.exists() else None
        if self.workspace_dir:
            root_index = self.model.setRootPath(str(self.workspace_dir))
            self.tree.setRootIndex(root_index)
            self.root_label.setText(self.main_window.tr("workspace_label", path=self.workspace_dir))
        else:
            root_index = self.model.setRootPath(str(Path.home()))
            self.tree.setRootIndex(root_index)
            self.root_label.setText(self.main_window.tr("workspace_empty"))

    def apply_language(self) -> None:
        self.root_label.setText(
            self.main_window.tr("workspace_label", path=self.workspace_dir)
            if self.workspace_dir
            else self.main_window.tr("workspace_empty")
        )
        self.choose_button.setText(self.main_window.tr("folder"))
        self.new_note_button.setText(self.main_window.tr("new_note"))
        self.search_box.setPlaceholderText(self.main_window.tr("search_workspace_placeholder"))
        self.search_button.setText(self.main_window.tr("search"))
        self.case_sensitive_box.setText(self.main_window.tr("case_sensitive"))
        self.tabs.setTabText(self.tabs.indexOf(self.tree), self.main_window.tr("tab_file"))
        self.tabs.setTabText(self.tabs.indexOf(self.recent_list), self.main_window.tr("tab_recent"))
        self.tabs.setTabText(self.tabs.indexOf(self.results_list), self.main_window.tr("tab_results"))
        self.tabs.setTabText(self.tabs.indexOf(self.outline_list), self.main_window.tr("tab_outline"))
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
            item = QListWidgetItem(f"{display_path}:{hit.line_number} — {hit.snippet}")
            item.setToolTip(str(hit.path))
            item.setData(Qt.ItemDataRole.UserRole, {"path": str(hit.path), "line": hit.line_number})
            self.results_list.addItem(item)
        self.tabs.setCurrentWidget(self.results_list)

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
            self.main_window.open_file_path(path)

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
            self.main_window.open_file_path(path)
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
        self.main_window.open_file_path(path)

    def on_result_double_clicked(self, item: QListWidgetItem) -> None:
        payload = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(payload, dict):
            self.main_window.open_file_path(Path(payload["path"]), line_number=int(payload.get("line", 1)))

    def on_outline_double_clicked(self, item: QListWidgetItem) -> None:
        line_number = item.data(Qt.ItemDataRole.UserRole)
        if line_number:
            self.main_window.goto_line(int(line_number))
