from __future__ import annotations

from PyQt6.QtCore import QTimer, Qt, pyqtSignal
from PyQt6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QPushButton, QToolButton, QVBoxLayout, QWidget


class UpdateToast(QFrame):
    """An actionable notification that leaves the document's keyboard focus alone."""

    activated = pyqtSignal()

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("updateToast")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(10)
        header = QHBoxLayout()
        self.title_label = QLabel()
        self.title_label.setObjectName("toastTitle")
        self.title_label.setTextFormat(Qt.TextFormat.PlainText)
        self.title_label.setWordWrap(True)
        self.close_button = QToolButton()
        self.close_button.setText("×")
        self.close_button.clicked.connect(self.hide)
        header.addWidget(self.title_label, 1)
        header.addWidget(self.close_button)
        layout.addLayout(header)
        self.message_label = QLabel()
        self.message_label.setObjectName("toastMessage")
        self.message_label.setTextFormat(Qt.TextFormat.PlainText)
        self.message_label.setWordWrap(True)
        layout.addWidget(self.message_label)
        actions = QHBoxLayout()
        actions.addStretch(1)
        self.open_button = QPushButton()
        self.open_button.setObjectName("toastAction")
        self.open_button.clicked.connect(self._activate)
        actions.addWidget(self.open_button)
        layout.addLayout(actions)
        self._timer = QTimer(self)
        self._timer.setInterval(20_000)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._expire)
        self.hide()

    def notify(self, title: str, message: str, action: str, close: str) -> None:
        self.set_labels(title, message, action, close)
        self.reposition()
        self.show()
        self.raise_()
        self._timer.start(20_000)

    def set_labels(self, title: str, message: str, action: str, close: str) -> None:
        self.title_label.setText(title)
        self.message_label.setText(message)
        self.open_button.setText(action)
        self.close_button.setToolTip(close)
        self.close_button.setAccessibleName(close)
        self.setAccessibleName(title)

    def reposition(self) -> None:
        window = self.parentWidget()
        area = window.centralWidget().geometry()
        self.setFixedWidth(min(420, max(240, area.width() - 32)))
        self.adjustSize()
        self.move(max(area.left() + 16, area.right() - self.width() - 15), max(area.top() + 16, area.bottom() - self.height() - 15))

    def _activate(self) -> None:
        self.hide()
        self.activated.emit()

    def _expire(self) -> None:
        focus = QApplication.focusWidget()
        if self.underMouse() or (focus is not None and self.isAncestorOf(focus)) or not self.window().isActiveWindow():
            self._timer.start(2000)
        else:
            self.hide()

    def hideEvent(self, event) -> None:
        self._timer.stop()
        super().hideEvent(event)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._timer.start(20_000)
