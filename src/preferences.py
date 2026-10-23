from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import QSettings
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFontComboBox, QFormLayout, QFrame, QGroupBox, QLabel, QScrollArea, QSpinBox, QVBoxLayout, QWidget,
)


@dataclass(frozen=True)
class Typography:
    editor_font: str = "Consolas"
    editor_size: int = 12
    preview_font: str = "Segoe UI"
    preview_size: int = 16
    preview_spacing: float = 1.65
    preview_width: int = 860

    @classmethod
    def load(cls, settings: QSettings) -> "Typography":
        defaults = cls()

        def number(key, default, minimum, maximum, convert):
            try:
                value = convert(settings.value(f"typography/{key}", default))
                return value if minimum <= value <= maximum else default
            except (TypeError, ValueError, OverflowError):
                return default

        return cls(
            editor_font=str(settings.value("typography/editor_font", defaults.editor_font)) or defaults.editor_font,
            editor_size=number("editor_size", defaults.editor_size, 9, 28, int),
            preview_font=str(settings.value("typography/preview_font", defaults.preview_font)) or defaults.preview_font,
            preview_size=number("preview_size", defaults.preview_size, 12, 28, int),
            preview_spacing=number("preview_spacing", defaults.preview_spacing, 1.2, 2.2, float),
            preview_width=number("preview_width", defaults.preview_width, 480, 1200, int),
        )

    def save(self, settings: QSettings) -> None:
        for key, value in vars(self).items():
            settings.setValue(f"typography/{key}", value)


class PreferencesDialog(QDialog):
    def __init__(self, window) -> None:
        super().__init__(window)
        tr = window.tr
        current = window.typography
        self.setWindowTitle(tr("preferences"))
        self.setMinimumWidth(460)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(18)

        writing = QGroupBox(tr("writing"))
        form = QFormLayout(writing)
        self.editor_font = QFontComboBox()
        self.editor_font.setCurrentFont(QFont(current.editor_font))
        self.editor_size = self._spin(9, 28, current.editor_size, " pt")
        form.addRow(tr("font_family"), self.editor_font)
        form.addRow(tr("font_size"), self.editor_size)
        layout.addWidget(writing)

        reading = QGroupBox(tr("reading"))
        form = QFormLayout(reading)
        self.preview_font = QFontComboBox()
        self.preview_font.setCurrentFont(QFont(current.preview_font))
        self.preview_size = self._spin(12, 28, current.preview_size, " px")
        self.preview_spacing = QDoubleSpinBox()
        self.preview_spacing.setRange(1.2, 2.2)
        self.preview_spacing.setSingleStep(0.05)
        self.preview_spacing.setValue(current.preview_spacing)
        self.preview_width = self._spin(480, 1200, current.preview_width, " px")
        self.preview_width.setSingleStep(20)
        form.addRow(tr("font_family"), self.preview_font)
        form.addRow(tr("font_size"), self.preview_size)
        form.addRow(tr("line_spacing"), self.preview_spacing)
        form.addRow(tr("page_width"), self.preview_width)
        layout.addWidget(reading)

        general = QGroupBox(tr("appearance_behavior"))
        form = QFormLayout(general)
        self.theme = QComboBox()
        self.theme.addItem(tr("light_theme"), "light")
        self.theme.addItem(tr("dark_theme"), "dark")
        self.theme.setCurrentIndex(self.theme.findData(window.theme))
        self.language = QComboBox()
        self.language.addItem("Italiano", "it")
        self.language.addItem("English", "en")
        self.language.setCurrentIndex(self.language.findData(window.language))
        self.autosave = QCheckBox(tr("autosave"))
        self.autosave.setChecked(window.autosave_enabled)
        self.wrap = QCheckBox(tr("word_wrap"))
        self.wrap.setChecked(window.actions["wrap"].isChecked())
        self.sync = QCheckBox(tr("sync_scroll"))
        self.sync.setChecked(window.sync_preview_scroll_enabled)
        self.check_updates = QCheckBox(tr("check_updates_on_startup"))
        self.check_updates.setChecked(window.check_updates_on_startup)
        form.addRow(tr("theme"), self.theme)
        form.addRow(tr("menu_language"), self.language)
        form.addRow(self.autosave)
        form.addRow(self.wrap)
        form.addRow(self.sync)
        form.addRow(self.check_updates)
        layout.addWidget(general)

        self.sample = QLabel(tr("typography_sample"))
        self.sample.setWordWrap(True)
        self.sample.setMinimumHeight(50)
        layout.addWidget(self.sample)
        self.editor_font.currentFontChanged.connect(self._update_sample)
        self.editor_size.valueChanged.connect(self._update_sample)
        self._update_sample()

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(tr("apply"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("cancel"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(body)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.addWidget(scroll, 1)
        outer.addWidget(buttons)
        self.resize(520, min(740, window.screen().availableGeometry().height() - 100))

    @staticmethod
    def _spin(minimum, maximum, value, suffix) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(minimum, maximum)
        spin.setValue(value)
        spin.setSuffix(suffix)
        return spin

    def _update_sample(self, *_args) -> None:
        font = self.editor_font.currentFont()
        font.setPointSize(self.editor_size.value())
        self.sample.setFont(font)

    def typography(self) -> Typography:
        return Typography(
            self.editor_font.currentFont().family(), self.editor_size.value(),
            self.preview_font.currentFont().family(), self.preview_size.value(),
            self.preview_spacing.value(), self.preview_width.value(),
        )
