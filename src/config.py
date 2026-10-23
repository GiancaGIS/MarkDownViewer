from __future__ import annotations

APP_NAME = "Markdown Studio"
ORG_NAME = "GiancaGIS"
APP_AUTHOR = "GiancaGIS"
APP_COPYRIGHT = f"Copyright © 2026 {APP_AUTHOR}"
VERSION = "1.1.0"
GITHUB_REPOSITORY = "GiancaGIS/MarkDownViewer"
GITHUB_RELEASES_URL = f"https://github.com/{GITHUB_REPOSITORY}/releases"

MARKDOWN_SUFFIXES = {".md", ".markdown", ".mdown", ".mkd", ".txt"}
MAX_RECENT_FILES = 14
MAX_SEARCH_RESULTS = 300
MAX_SEARCH_FILE_BYTES = 3 * 1024 * 1024

DEFAULT_MARKDOWN = """# Markdown Studio

Editor Markdown con anteprima live in **PyQt6**.

## Novita

- Workspace laterale con albero file
- Documenti recenti
- Ricerca globale nella cartella di note
- Creazione rapida di nuove note nel workspace
- Apertura file da risultati e recenti
- Outline del documento dagli heading
- Inserimento rapido di link, immagini e tabelle

> Ora comincia a sembrare un piccolo laboratorio Markdown personale.

```python
def hello(name: str) -> None:
    print(f"Ciao {name}!")

hello("Markdown Studio")
```

| Feature | Stato |
| --- | --- |
| Editor | OK |
| Preview | OK |
| Workspace | Nuovo |
"""

THEMES: dict[str, dict[str, str]] = {
    "light": {
        "editor_bg": "#ffffff",
        "editor_fg": "#1f2328",
        "line_bg": "#f6f8fa",
        "line_fg": "#6e7781",
        "current_line": "#f0f6ff",
        "selection": "#b6d7ff",
        "preview_bg": "#f6f7f9",
        "preview_page": "#ffffff",
        "preview_fg": "#222222",
        "preview_muted": "#4b5563",
        "preview_border": "#d8dee4",
        "preview_inline_code_bg": "#eef2f7",
        "preview_inline_code_fg": "#1f2937",
        "pygments": "default",
    },
    "dark": {
        "editor_bg": "#0d1117",
        "editor_fg": "#c9d1d9",
        "line_bg": "#161b22",
        "line_fg": "#7d8590",
        "current_line": "#172033",
        "selection": "#264f78",
        "preview_bg": "#0d1117",
        "preview_page": "#161b22",
        "preview_fg": "#c9d1d9",
        "preview_muted": "#8b949e",
        "preview_border": "#30363d",
        "preview_inline_code_bg": "#21262d",
        "preview_inline_code_fg": "#e6edf3",
        "pygments": "github-dark",
    },
}

APP_QSS = """
QMainWindow {
    background: %(window_bg)s;
}
QWidget {
    color: %(fg)s;
    background: %(window_bg)s;
}
QDialog, QMessageBox, QFileDialog, QInputDialog {
    color: %(fg)s;
    background: %(window_bg)s;
}
QMenuBar {
    background: %(toolbar_bg)s;
    color: %(fg)s;
    border-bottom: 1px solid %(border)s;
}
QMenuBar::item:selected {
    background: %(button_hover)s;
}
QMenu {
    background: %(toolbar_bg)s;
    color: %(fg)s;
    border: 1px solid %(border)s;
    padding: 5px;
    font-size: 10pt;
}
QMenu::item {
    padding: 7px 26px 7px 12px;
    min-height: 20px;
    border-radius: 4px;
}
QMenu::separator {
    height: 1px;
    background: %(border)s;
    margin: 5px 8px;
}
QMenu::item:selected {
    background: %(button_hover)s;
}
QMenu::item:disabled {
    color: %(muted)s;
}
QToolBar {
    spacing: 6px;
    padding: 6px;
    border: 0;
    border-bottom: 1px solid %(border)s;
    background: %(toolbar_bg)s;
}
QToolBar#mainToolbar {
    padding: 3px;
    spacing: 3px;
}
QToolBar#mainToolbar QToolButton {
    padding: 5px;
    min-width: 24px;
    min-height: 22px;
}
QToolButton#applicationMenu::menu-indicator {
    image: none;
}
QWidget#toolbarSpacer {
    background: transparent;
}
QToolBar#formatToolbar {
    padding: 2px;
    spacing: 2px;
}
QToolBar#formatToolbar QToolButton {
    min-width: 20px;
    padding: 2px;
    font-size: 9pt;
}
QLabel#panelCaption {
    background: %(toolbar_bg)s;
    color: %(muted)s;
    padding-left: 18px;
    font-size: 8pt;
    font-weight: 600;
    border-bottom: 1px solid %(border)s;
}
QWidget#findBar {
    background: %(toolbar_bg)s;
    border-bottom: 1px solid %(border)s;
}
QFrame#updateToast {
    background: %(toolbar_bg)s;
    border: 1px solid %(accent)s;
    border-radius: 10px;
}
QFrame#updateToast QLabel {
    background: transparent;
    border: 0;
}
QLabel#toastTitle {
    font-weight: 600;
    font-size: 11pt;
}
QLabel#toastMessage {
    font-size: 10pt;
}
QPushButton#toastAction {
    font-size: 10pt;
    color: #ffffff;
    background: #1f6feb;
    border: 1px solid #1f6feb;
}
QPushButton#toastAction:hover {
    background: #1158c7;
}
QGroupBox {
    border: 1px solid %(border)s;
    border-radius: 8px;
    margin-top: 10px;
    padding: 12px;
    padding-top: 18px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 5px;
    color: %(muted)s;
}
QComboBox, QSpinBox, QDoubleSpinBox {
    color: %(fg)s;
    background: %(input_bg)s;
    border: 1px solid %(border)s;
    border-radius: 5px;
    min-height: 24px;
    padding: 2px 6px;
}
QComboBox QAbstractItemView {
    color: %(fg)s;
    background: %(input_bg)s;
    selection-background-color: %(selection)s;
}
QToolButton:focus, QPushButton:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QLineEdit:focus {
    border: 1px solid %(selection)s;
}
QToolButton {
    color: %(fg)s;
    background: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 5px;
}
QToolButton:hover {
    background: %(button_hover)s;
    border-color: %(border)s;
}
QToolButton:pressed, QToolButton:checked {
    background: %(input_bg)s;
    border-color: %(selection)s;
}
QStatusBar {
    background: %(toolbar_bg)s;
    color: %(fg)s;
    border-top: 1px solid %(border)s;
}
QStatusBar QLabel {
    color: %(muted)s;
    padding: 0;
    padding-left: 8px;
    padding-right: 8px;
    font-size: 9pt;
}
QWidget#navigationRail {
    background: %(toolbar_bg)s;
    border-right: 1px solid %(border)s;
}
QWidget#navigationRail QToolButton {
    border: 0;
    padding: 5px;
    border-radius: 6px;
}
QWidget#navigationRail QToolButton:checked {
    background: %(selection)s;
    border-left: 2px solid %(accent)s;
}
QWidget#workspacePanel {
    background: %(window_bg)s;
}
QWidget#workspacePanel QTreeView, QWidget#workspacePanel QListWidget {
    background: transparent;
    border: 0;
    outline: 0;
}
QWidget#workspacePanel QTreeView::item, QWidget#workspacePanel QListWidget::item {
    padding: 5px 4px;
    border-radius: 4px;
}
QLabel#sidebarTitle {
    font-size: 9pt;
    font-weight: 600;
}
QLabel#emptyWorkspace {
    color: %(muted)s;
    padding: 16px 6px 0;
}
QTabBar#documentTabs {
    background: transparent;
}
QTabBar#documentTabs::tab {
    background: transparent;
    border: 0;
    padding: 4px;
    padding-left: 8px;
    padding-right: 8px;
    margin: 2px;
    border-radius: 5px;
}
QTabBar#documentTabs::tab:selected {
    background: %(button_hover)s;
    color: %(fg)s;
}
QTabBar#documentTabs QToolButton {
    padding: 0;
    min-width: 0;
    min-height: 0;
}
QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: %(border)s;
    border-radius: 4px;
    min-height: 28px;
}
QScrollBar::handle:vertical:hover {
    background: %(muted)s;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: transparent;
}
QLabel {
    color: %(fg)s;
}
QCheckBox {
    color: %(fg)s;
    spacing: 7px;
    background: transparent;
}
QCheckBox::indicator {
    width: 15px;
    height: 15px;
    border: 1px solid %(border)s;
    border-radius: 4px;
    background: %(input_bg)s;
}
QCheckBox::indicator:checked {
    background: %(selection)s;
    border-color: %(selection)s;
}
QLineEdit {
    min-width: 160px;
    padding: 6px 8px;
    border: 1px solid %(border)s;
    border-radius: 6px;
    color: %(fg)s;
    background: %(input_bg)s;
}
QLineEdit:disabled {
    color: %(muted)s;
    background: %(button_bg)s;
}
QInputDialog QLineEdit {
    min-width: 420px;
}
QPushButton {
    padding: 6px 10px;
    border: 1px solid %(border)s;
    border-radius: 6px;
    color: %(fg)s;
    background: %(button_bg)s;
}
QPushButton:hover {
    background: %(button_hover)s;
}
QPushButton:disabled {
    color: %(muted)s;
    background: %(button_bg)s;
}
QSplitter::handle {
    background: %(border)s;
}
QTabWidget::pane {
    border: 1px solid %(border)s;
    background: %(toolbar_bg)s;
}
QTabBar::tab {
    color: %(fg)s;
    background: %(button_bg)s;
    border: 0;
    border-right: 1px solid %(border)s;
    border-bottom: 2px solid transparent;
    padding: 10px 14px;
}
QTabBar::tab:selected {
    background: %(input_bg)s;
    border-bottom: 2px solid %(accent)s;
}
QTabBar::tab:hover:!selected {
    background: %(button_hover)s;
}
QTabWidget QTabBar::tab {
    padding: 8px 6px;
    font-size: 9pt;
}
QTreeView, QListWidget {
    color: %(fg)s;
    background: %(input_bg)s;
    alternate-background-color: %(button_bg)s;
    border: 1px solid %(border)s;
    selection-background-color: %(selection)s;
    selection-color: %(fg)s;
}
QTreeView::item:disabled, QListWidget::item:disabled {
    color: %(muted)s;
}
QTreeView::item, QListWidget::item {
    padding: 4px 2px;
}
QHeaderView::section {
    color: %(fg)s;
    background: %(button_bg)s;
    border: 1px solid %(border)s;
    padding: 4px;
}
QToolTip {
    color: %(tooltip_fg)s;
    background: %(tooltip_bg)s;
    border: 1px solid %(border)s;
    padding: 5px;
}
"""

APP_THEME_QSS = {
    "light": APP_QSS
    % {
        "window_bg": "#f6f8fa",
        "toolbar_bg": "#ffffff",
        "border": "#d0d7de",
        "fg": "#24292f",
        "input_bg": "#ffffff",
        "button_bg": "#f6f8fa",
        "button_hover": "#eef2f6",
        "selection": "#b6d7ff",
        "accent": "#0969da",
        "muted": "#6e7781",
        "tooltip_fg": "#24292f",
        "tooltip_bg": "#ffffff",
    },
    "dark": APP_QSS
    % {
        "window_bg": "#0d1117",
        "toolbar_bg": "#161b22",
        "border": "#30363d",
        "fg": "#c9d1d9",
        "input_bg": "#0d1117",
        "button_bg": "#21262d",
        "button_hover": "#30363d",
        "selection": "#264f78",
        "accent": "#79c0ff",
        "muted": "#8b949e",
        "tooltip_fg": "#f0f6fc",
        "tooltip_bg": "#21262d",
    },
}
