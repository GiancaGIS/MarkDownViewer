from PyQt6.QtCore import QSize, pyqtSignal
from PyQt6.QtWidgets import QToolButton, QVBoxLayout, QWidget

try:
    from .ui_icons import ui_icon
except ImportError:
    from ui_icons import ui_icon


class NavigationRail(QWidget):
    section_selected = pyqtSignal(str)
    preferences_requested = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("navigationRail")
        self.setFixedWidth(44)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 8, 5, 8)
        layout.setSpacing(5)
        self.buttons: dict[str, QToolButton] = {}
        for section in ("files", "search", "outline", "recent"):
            button = QToolButton()
            button.setCheckable(True)
            button.setFixedSize(34, 34)
            button.setIconSize(QSize(20, 20))
            button.clicked.connect(lambda checked=False, value=section: self.section_selected.emit(value))
            layout.addWidget(button)
            self.buttons[section] = button
        layout.addStretch(1)
        self.preferences_button = QToolButton()
        self.preferences_button.setFixedSize(34, 34)
        self.preferences_button.clicked.connect(self.preferences_requested)
        layout.addWidget(self.preferences_button)
        self.apply_theme("#64748b")

    def set_section(self, section: str | None) -> None:
        for key, button in self.buttons.items():
            button.setChecked(key == section)

    def apply_language(self, tr) -> None:
        for section, key in (("files", "tab_file"), ("search", "search_workspace"), ("outline", "tab_outline"), ("recent", "tab_recent")):
            self.buttons[section].setToolTip(tr(key))
            self.buttons[section].setAccessibleName(tr(key))
        self.preferences_button.setToolTip(tr("preferences"))
        self.preferences_button.setAccessibleName(tr("preferences"))

    def apply_theme(self, color: str) -> None:
        for section, button in self.buttons.items():
            button.setIcon(ui_icon(section, color))
        self.preferences_button.setIcon(ui_icon("settings", color))
