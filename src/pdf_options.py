from __future__ import annotations

from dataclasses import dataclass
import math

from PyQt6.QtCore import QMarginsF, QSettings
from PyQt6.QtGui import QFont, QPageLayout, QPageSize
from PyQt6.QtWebEngineCore import qWebEngineChromiumVersion
from PyQt6.QtWidgets import QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFontComboBox, QFormLayout, QFrame, QGridLayout, QGroupBox, QLabel, QScrollArea, QVBoxLayout, QWidget


def supports_page_numbers() -> bool:
    # CSS page margin boxes were introduced in Chromium 131.
    return int(qWebEngineChromiumVersion().split(".")[0]) >= 131


@dataclass(frozen=True)
class PdfOptions:
    paper: str = "A4"
    landscape: bool = False
    top: float = 20
    right: float = 18
    bottom: float = 20
    left: float = 18
    font: str = "Segoe UI"
    font_size: float = 11
    line_height: float = 1.5
    page_numbers: bool = True

    @classmethod
    def load(cls, settings: QSettings) -> "PdfOptions":
        default = cls()

        def number(key, minimum, maximum):
            try:
                value = float(settings.value(f"pdf/{key}", getattr(default, key)))
                return value if math.isfinite(value) and minimum <= value <= maximum else getattr(default, key)
            except (TypeError, ValueError):
                return getattr(default, key)

        def boolean(key, fallback):
            value = settings.value(f"pdf/{key}", fallback)
            return value is True or str(value).lower() in {"1", "true", "yes"}

        paper = str(settings.value("pdf/paper", default.paper))
        return cls(
            paper=paper if paper in {"A4", "Letter"} else default.paper,
            landscape=boolean("landscape", False),
            top=number("top", 10, 35), right=number("right", 10, 35),
            bottom=number("bottom", 10, 35), left=number("left", 10, 35),
            font=str(settings.value("pdf/font", default.font)) or default.font,
            font_size=number("font_size", 8, 16), line_height=number("line_height", 1.2, 1.8),
            page_numbers=boolean("page_numbers", True) and supports_page_numbers(),
        )

    def save(self, settings: QSettings) -> None:
        for key, value in vars(self).items():
            settings.setValue(f"pdf/{key}", value)

    def page_layout(self) -> QPageLayout:
        paper = QPageSize.PageSizeId.A4 if self.paper == "A4" else QPageSize.PageSizeId.Letter
        orientation = QPageLayout.Orientation.Landscape if self.landscape else QPageLayout.Orientation.Portrait
        return QPageLayout(QPageSize(paper), orientation, QMarginsF(self.left, self.top, self.right, self.bottom), QPageLayout.Unit.Millimeter)


class PdfOptionsDialog(QDialog):
    def __init__(self, window) -> None:
        super().__init__(window)
        tr = window.tr
        options = PdfOptions.load(window.settings)
        self.setWindowTitle(tr("pdf_options"))
        self.setMinimumWidth(420)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(14)
        page = QGroupBox(tr("pdf_page"))
        form = QFormLayout(page)
        self.paper = QComboBox()
        self.paper.addItems(["A4", "Letter"])
        self.paper.setCurrentText(options.paper)
        self.orientation = QComboBox()
        self.orientation.addItem(tr("pdf_portrait"), False)
        self.orientation.addItem(tr("pdf_landscape"), True)
        self.orientation.setCurrentIndex(int(options.landscape))
        form.addRow(tr("pdf_paper"), self.paper)
        form.addRow(tr("pdf_orientation"), self.orientation)
        layout.addWidget(page)

        margins = QGroupBox(tr("pdf_margins"))
        grid = QGridLayout(margins)
        self.margins = {}
        for index, key in enumerate(("top", "bottom", "left", "right")):
            spin = self._number(10, 35, getattr(options, key), 1, " mm")
            self.margins[key] = spin
            row, column = divmod(index, 2)
            grid.addWidget(QLabel(tr(f"pdf_{key}")), row * 2, column)
            grid.addWidget(spin, row * 2 + 1, column)
        layout.addWidget(margins)

        text = QGroupBox(tr("pdf_typography"))
        form = QFormLayout(text)
        self.font_box = QFontComboBox()
        self.font_box.setCurrentFont(QFont(options.font))
        self.font_size = self._number(8, 16, options.font_size, 0.5, " pt")
        self.line_height = self._number(1.2, 1.8, options.line_height, 0.05)
        form.addRow(tr("font_family"), self.font_box)
        form.addRow(tr("font_size"), self.font_size)
        form.addRow(tr("line_spacing"), self.line_height)
        layout.addWidget(text)
        self.numbers = QCheckBox(tr("pdf_page_numbers"))
        self.numbers.setChecked(options.page_numbers)
        self.numbers.setEnabled(supports_page_numbers())
        if not supports_page_numbers():
            self.numbers.setToolTip(tr("pdf_numbers_unavailable"))
        layout.addWidget(self.numbers)
        hint = QLabel(tr("pdf_style_hint"))
        hint.setWordWrap(True)
        layout.addWidget(hint)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(tr("export_pdf"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("cancel"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(body)
        outer = QVBoxLayout(self)
        outer.addWidget(scroll, 1)
        outer.addWidget(buttons)
        self.resize(470, min(730, window.screen().availableGeometry().height() - 80))

    @staticmethod
    def _number(minimum, maximum, value, step, suffix=""):
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setValue(value)
        spin.setSingleStep(step)
        spin.setSuffix(suffix)
        return spin

    def options(self) -> PdfOptions:
        return PdfOptions(
            paper=self.paper.currentText(), landscape=self.orientation.currentData(),
            **{key: spin.value() for key, spin in self.margins.items()},
            font=self.font_box.currentFont().family(), font_size=self.font_size.value(),
            line_height=self.line_height.value(), page_numbers=self.numbers.isChecked(),
        )
