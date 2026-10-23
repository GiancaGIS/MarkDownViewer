from __future__ import annotations

from PyQt6.QtCore import QRegularExpression, QRect, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontDatabase, QPainter, QTextCharFormat, QTextFormat, QTextCursor, QSyntaxHighlighter
from PyQt6.QtWidgets import QPlainTextEdit, QTextEdit, QWidget

try:
    from .config import THEMES
except ImportError:
    from config import THEMES

class MarkdownHighlighter(QSyntaxHighlighter):
    """Lightweight Markdown syntax highlighter for the editor."""

    def __init__(self, document, theme: str = "light") -> None:
        super().__init__(document)
        self.theme = theme if theme in THEMES else "light"
        self._build_formats()

    def set_theme(self, theme: str) -> None:
        self.theme = theme if theme in THEMES else "light"
        self._build_formats()
        self.rehighlight()

    def _format(self, color: str, *, bold: bool = False, italic: bool = False, size_delta: int = 0) -> QTextCharFormat:
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        if bold:
            fmt.setFontWeight(QFont.Weight.Bold)
        if italic:
            fmt.setFontItalic(True)
        if size_delta:
            fmt.setFontPointSize(max(8, 11 + size_delta))
        return fmt

    def _build_formats(self) -> None:
        if self.theme == "dark":
            self.header_fmt = self._format("#79c0ff", bold=True)
            self.marker_fmt = self._format("#8b949e", bold=True)
            self.bold_fmt = self._format("#ffa657", bold=True)
            self.italic_fmt = self._format("#d2a8ff", italic=True)
            self.code_fmt = self._format("#a5d6ff")
            self.link_fmt = self._format("#7ee787")
            self.quote_fmt = self._format("#8b949e", italic=True)
            self.list_fmt = self._format("#ff7b72", bold=True)
            self.hr_fmt = self._format("#8b949e")
        else:
            self.header_fmt = self._format("#0969da", bold=True)
            self.marker_fmt = self._format("#6e7781", bold=True)
            self.bold_fmt = self._format("#953800", bold=True)
            self.italic_fmt = self._format("#8250df", italic=True)
            self.code_fmt = self._format("#0550ae")
            self.link_fmt = self._format("#116329")
            self.quote_fmt = self._format("#57606a", italic=True)
            self.list_fmt = self._format("#cf222e", bold=True)
            self.hr_fmt = self._format("#6e7781")

        self.rules: list[tuple[QRegularExpression, QTextCharFormat]] = [
            (QRegularExpression(r"^#{1,6}\s+.*$"), self.header_fmt),
            (QRegularExpression(r"(\*\*[^*]+\*\*|__[^_]+__)"), self.bold_fmt),
            (QRegularExpression(r"(?<!\*)\*[^*\n]+\*(?!\*)|(?<!_)_[^_\n]+_(?!_)"), self.italic_fmt),
            (QRegularExpression(r"`[^`\n]+`"), self.code_fmt),
            (QRegularExpression(r"!?\[[^\]]+\]\([^\)]+\)"), self.link_fmt),
            (QRegularExpression(r"^\s*>.*$"), self.quote_fmt),
            (QRegularExpression(r"^\s*([-+*]|\d+\.)\s+"), self.list_fmt),
            (QRegularExpression(r"^\s*(-{3,}|_{3,}|\*{3,})\s*$"), self.hr_fmt),
        ]
        self.fence_rule = QRegularExpression(r"^\s*(```|~~~).*$")

    def highlightBlock(self, text: str) -> None:  # noqa: N802 - Qt override
        in_code_block = self.previousBlockState() == 1
        fence_match = self.fence_rule.match(text)

        if in_code_block:
            self.setFormat(0, len(text), self.code_fmt)
            if fence_match.hasMatch():
                self.setFormat(0, len(text), self.marker_fmt)
                self.setCurrentBlockState(0)
            else:
                self.setCurrentBlockState(1)
            return

        if fence_match.hasMatch():
            self.setFormat(0, len(text), self.marker_fmt)
            self.setCurrentBlockState(1)
            return

        self.setCurrentBlockState(0)
        for pattern, fmt in self.rules:
            match_iterator = pattern.globalMatch(text)
            while match_iterator.hasNext():
                match = match_iterator.next()
                self.setFormat(match.capturedStart(), match.capturedLength(), fmt)


class LineNumberArea(QWidget):
    def __init__(self, editor: "MarkdownEditor") -> None:
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt override
        return QSize(self.editor.line_number_area_width(), 0)

    def paintEvent(self, event) -> None:  # type: ignore[override]
        self.editor.line_number_area_paint_event(event)


class MarkdownEditor(QPlainTextEdit):
    """Markdown editor with line numbers and syntax highlighting."""

    imagesDropped = pyqtSignal(list)

    def __init__(self, theme: str = "light") -> None:
        super().__init__()
        self._current_line_bg = None
        self._line_number_fg = None
        self._line_number_bg = None
        self._readable_width = False
        self._horizontal_inset = 0
        self.theme = theme if theme in THEMES else "light"
        self.line_number_area = LineNumberArea(self)

        font = QFont("Cascadia Code")
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setPointSize(11)
        self.setFont(font)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(" ") * 4)
        self.setAcceptDrops(True)

        self.highlighter = MarkdownHighlighter(self.document(), self.theme)

        self.blockCountChanged.connect(self.update_line_number_area_width)
        self.updateRequest.connect(self.update_line_number_area)
        self.cursorPositionChanged.connect(self.highlight_current_line)

        self.apply_theme(self.theme)
        self.update_line_number_area_width(0)
        self.highlight_current_line()

    def apply_typography(self, family: str, size: int) -> None:
        available = set(QFontDatabase.families())
        if family not in available:
            family = next((name for name in ("Consolas", "Menlo", "DejaVu Sans Mono") if name in available), QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont).family())
        font = QFont(family)
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setPointSize(size)
        self.setFont(font)
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(" ") * 4)
        self.update_line_number_area_width(0)

    def apply_theme(self, theme: str) -> None:
        self.theme = theme if theme in THEMES else "light"
        t = THEMES[self.theme]
        self._line_number_bg = QColor(t["line_bg"])
        self._line_number_fg = QColor(t["line_fg"])
        self._current_line_bg = QColor(t["current_line"])
        self.highlighter.set_theme(self.theme)
        self.setStyleSheet(
            f"""
            QPlainTextEdit {{
                background: {t['editor_bg']};
                color: {t['editor_fg']};
                selection-background-color: {t['selection']};
                border: 0;
                padding: 8px;
            }}
            """
        )
        self.line_number_area.update()
        self.highlight_current_line()

    def line_number_area_width(self) -> int:
        digits = max(2, len(str(max(1, self.blockCount()))))
        return 14 + self.fontMetrics().horizontalAdvance("9") * digits

    def update_line_number_area_width(self, _new_block_count: int) -> None:
        gutter = self.line_number_area_width()
        column = self.fontMetrics().horizontalAdvance("M") * 88
        self._horizontal_inset = max(0, (self.contentsRect().width() - gutter - column - 20) // 2) if self._readable_width else 0
        inset = self._horizontal_inset
        self.setViewportMargins(gutter + inset, 0, inset, 0)
        cr = self.contentsRect()
        self.line_number_area.setGeometry(QRect(cr.left() + inset, cr.top(), gutter, cr.height()))

    def set_readable_width(self, enabled: bool) -> None:
        self._readable_width = enabled
        self.update_line_number_area_width(0)

    def update_line_number_area(self, rect: QRect, dy: int) -> None:
        if dy:
            self.line_number_area.scroll(0, dy)
        else:
            self.line_number_area.update(0, rect.y(), self.line_number_area.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self.update_line_number_area_width(0)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self.update_line_number_area_width(0)

    def line_number_area_paint_event(self, event) -> None:
        painter = QPainter(self.line_number_area)
        painter.setFont(self.font())
        painter.fillRect(event.rect(), self._line_number_bg)

        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = int(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + int(self.blockBoundingRect(block).height())
        height = self.fontMetrics().height()

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(block_number + 1)
                painter.setPen(self._line_number_fg)
                painter.drawText(0, top, self.line_number_area.width() - 6, height, Qt.AlignmentFlag.AlignRight, number)
            block = block.next()
            top = bottom
            bottom = top + int(self.blockBoundingRect(block).height())
            block_number += 1

    def highlight_current_line(self) -> None:
        if self.isReadOnly():
            return
        selection = QTextEdit.ExtraSelection()
        selection.format.setBackground(self._current_line_bg)
        selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
        selection.cursor = self.textCursor()
        selection.cursor.clearSelection()
        self.setExtraSelections([selection])

    def insertFromMimeData(self, source):  # type: ignore[override]
        if source.hasText():
            self.insertPlainText(source.text())
        else:
            super().insertFromMimeData(source)

    def dragEnterEvent(self, event) -> None:  # type: ignore[override]
        if self._mime_has_images(event.mimeData()):
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:  # type: ignore[override]
        if self._mime_has_images(event.mimeData()):
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:  # type: ignore[override]
        image_paths = self._image_paths_from_mime(event.mimeData())
        if image_paths:
            self.imagesDropped.emit(image_paths)
            event.acceptProposedAction()
            return
        super().dropEvent(event)

    def _mime_has_images(self, mime_data) -> bool:
        return bool(self._image_paths_from_mime(mime_data))

    def _image_paths_from_mime(self, mime_data) -> list[str]:
        if not mime_data.hasUrls():
            return []
        suffixes = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
        paths: list[str] = []
        for url in mime_data.urls():
            if not url.isLocalFile():
                continue
            path = url.toLocalFile()
            if path and any(path.lower().endswith(suffix) for suffix in suffixes):
                paths.append(path)
        return paths
