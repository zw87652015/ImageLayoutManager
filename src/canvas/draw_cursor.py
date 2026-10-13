"""Crosshair cursor with the armed tool's icon as a badge (Draw mode)."""

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QCursor, QPainter, QPen, QPixmap

from src.app.icons import render_icon

_SIZE = 32
_CENTRE = 8.5
_HOTSPOT = 8
_cache = {}


def tool_cursor(tool: str, dpr: float) -> QCursor:
    key = (tool, round(dpr, 2))
    cursor = _cache.get(key)
    if cursor is None:
        cursor = _cache[key] = _build(tool, dpr)
    return cursor


def _build(tool, dpr):
    device = int(round(_SIZE * dpr))
    pixmap = QPixmap(device, device)
    pixmap.setDevicePixelRatio(dpr)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    c = _CENTRE
    arms = (((c - 7, c), (c - 2, c)), ((c + 2, c), (c + 7, c)),
            ((c, c - 7), (c, c - 2)), ((c, c + 2), (c, c + 7)))
    for pen in (QPen(QColor("#FFFFFF"), 3.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap),
                QPen(QColor("#000000"), 1.0)):
        painter.setPen(pen)
        for (x1, y1), (x2, y2) in arms:
            painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))
    painter.setPen(QPen(QColor("#303030"), 1.0))
    painter.setBrush(QColor("#FFFFFF"))
    painter.drawRoundedRect(QRectF(15, 15, 15, 15), 3, 3)
    render_icon(painter, f"mark_{tool}", "#202020", QRectF(16, 16, 13, 13))
    painter.end()
    return QCursor(pixmap, _HOTSPOT, _HOTSPOT)
