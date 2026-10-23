"""Small, consistently sized stroke icons painted by Qt at any display scale."""
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap, QPolygonF


def ui_icon(name: str, color: str = "#64748b") -> QIcon:
    pixmap = QPixmap(40, 40)
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor(color), 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))

    def line(*points):
        painter.drawPolyline(QPolygonF([QPointF(x, y) for x, y in points]))

    def box(x, y, width, height):
        painter.drawRoundedRect(QRectF(x, y, width, height), 1.5, 1.5)

    if name == "menu":
        for y in (5, 10, 15):
            line((4, y), (16, y))
    elif name in {"file", "new", "files"}:
        if name == "files":
            line((5, 4), (3, 4), (3, 17), (13, 17))
        line((6, 3), (12, 3), (16, 7), (16, 16), (6, 16), (6, 3))
        line((12, 3), (12, 7), (16, 7))
        if name == "new":
            line((9, 11), (13, 11))
            line((11, 9), (11, 13))
    elif name == "folder":
        line((2, 6), (8, 6), (10, 8), (18, 8), (16, 16), (2, 16), (2, 6))
        line((2, 6), (2, 4), (8, 4), (10, 6), (17, 6), (17, 8))
    elif name == "save":
        line((3, 3), (15, 3), (17, 5), (17, 17), (3, 17), (3, 3))
        box(6, 3, 7, 5)
        box(6, 12, 8, 5)
    elif name == "search":
        painter.drawEllipse(QRectF(3, 3, 10, 10))
        line((12, 12), (17, 17))
    elif name == "recent":
        painter.drawEllipse(QRectF(3, 3, 14, 14))
        line((10, 6), (10, 10), (13, 12))
    elif name == "outline":
        for y, x in ((5, 4), (10, 7), (15, 7)):
            line((x, y), (16, y))
        line((3, 10), (3, 15))
    elif name in {"writing", "split", "reading"}:
        box(2.5, 3.5, 15, 13)
        if name == "split":
            line((10, 4), (10, 16))
            line((5, 7), (7, 7))
            line((5, 10), (7, 10))
        else:
            for y, end in ((7, 14), (10, 14), (13, 11)):
                line((6, y), (end, y))
            if name == "writing":
                line((4, 4), (4, 16))
    elif name == "export":
        line((3, 12), (3, 17), (17, 17), (17, 12))
        line((10, 13), (10, 3))
        line((6, 7), (10, 3), (14, 7))
    elif name == "settings":
        for x, center in ((5, 7), (10, 13), (15, 6)):
            line((x, 3), (x, center - 2))
            line((x, center + 2), (x, 17))
            painter.drawEllipse(QRectF(x - 2, center - 2, 4, 4))
    elif name == "plus":
        line((10, 4), (10, 16))
        line((4, 10), (16, 10))
    elif name == "list":
        for y in (5, 10, 15):
            line((7, y), (16, y))
            line((3, y), (3.5, y))
    elif name == "quote":
        line((4, 4), (4, 16))
        line((8, 6), (16, 6))
        line((8, 10), (16, 10))
        line((8, 14), (13, 14))
    painter.end()
    return QIcon(pixmap)
