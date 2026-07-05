from __future__ import annotations

APP_NAME = "Markdown Studio"
ORG_NAME = "GiancaGIS"
VERSION = "1.0.1"

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
        "current_line": "#fff8c5",
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
    border: 1px solid %(border)s;
    padding: 7px 9px;
}
QTabBar::tab:selected {
    background: %(input_bg)s;
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
        "muted": "#8b949e",
        "tooltip_fg": "#f0f6fc",
        "tooltip_bg": "#21262d",
    },
}
