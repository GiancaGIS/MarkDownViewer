from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QStackedWidget, QTabBar, QToolButton, QWidget


class DocumentTabs(QTabBar):
    """Document tabs whose pages can share a layout with the preview."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.pages = QStackedWidget()
        self.setObjectName("documentTabs")
        self._close_label = "Close document"
        self.setExpanding(False)
        self.setDocumentMode(True)
        self.setDrawBase(False)
        self.setElideMode(Qt.TextElideMode.ElideRight)
        self.currentChanged.connect(self._activate_page)

    def addTab(self, page: QWidget, title: str) -> int:
        self.pages.addWidget(page)
        previous = self.currentIndex()
        blocked = self.blockSignals(True)
        index = super().addTab(title)
        self.setTabData(index, page)
        close = QToolButton(self)
        close.setText("×")
        close.setToolTip(self._close_label)
        close.setAccessibleName(self._close_label)
        close.setAutoRaise(True)
        close.setFixedSize(22, 22)
        close.clicked.connect(lambda checked=False, document=page: self.tabCloseRequested.emit(self.indexOf(document)))
        self.setTabButton(index, QTabBar.ButtonPosition.RightSide, close)
        self.blockSignals(blocked)
        if previous == -1:
            self._activate_page(index)
            if not blocked:
                self.currentChanged.emit(index)
        return index

    def widget(self, index: int) -> QWidget | None:
        return self.tabData(index) if 0 <= index < self.count() else None

    def currentWidget(self) -> QWidget | None:
        return self.widget(self.currentIndex())

    def indexOf(self, page: QWidget) -> int:
        return next((index for index in range(self.count()) if self.widget(index) is page), -1)

    def removeTab(self, index: int) -> None:
        page = self.widget(index)
        super().removeTab(index)
        if page is not None:
            self.pages.removeWidget(page)

    def _activate_page(self, index: int) -> None:
        page = self.widget(index)
        if page is not None:
            self.pages.setCurrentWidget(page)

    def set_close_label(self, label: str) -> None:
        self._close_label = label
        for index in range(self.count()):
            button = self.tabButton(index, QTabBar.ButtonPosition.RightSide)
            if button is not None:
                button.setToolTip(label)
                button.setAccessibleName(label)
