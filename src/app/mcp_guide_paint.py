"""Paints the MCP setup flow diagram (QtGui only, no widgets)."""

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QFontMetrics, QPainter, QPen, QPolygonF

_BOX_H = 40.0
_RADIUS = 8.0
_GAP = 60.0
_CAPTIONS = ("stdio", "WebSocket")


def paint_flow(painter, rect, labels, colors):
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    box_w = (rect.width() - 2 * _GAP) / 3.0
    top = rect.top() + (rect.height() - _BOX_H) / 2.0
    boxes = [QRectF(rect.left() + i * (box_w + _GAP), top, box_w, _BOX_H) for i in range(3)]
    font = QFont(painter.font())
    font.setPixelSize(11)
    small = QFont(painter.font())
    small.setPixelSize(9)
    muted = QColor(colors["muted"])
    for index, box in enumerate(boxes):
        last = index == 2
        painter.setPen(QPen(QColor(colors["accent"] if last else colors["border"]), 1.0))
        painter.setBrush(QBrush(QColor(colors["surface"])))
        painter.drawRoundedRect(box.adjusted(0.5, 0.5, -0.5, -0.5), _RADIUS, _RADIUS)
        painter.setFont(font)
        painter.setPen(QColor(colors["accent"] if last else colors["text"]))
        label = QFontMetrics(font).elidedText(labels[index], Qt.TextElideMode.ElideRight, int(box.width()) - 12)
        painter.drawText(box, Qt.AlignmentFlag.AlignCenter, label)
    mid = top + _BOX_H / 2.0
    painter.setFont(small)
    for index in range(2):
        x1 = boxes[index].right() + 4.0
        x2 = boxes[index + 1].left() - 4.0
        painter.setPen(QPen(muted, 1.0))
        painter.drawLine(QPointF(x1, mid), QPointF(x2 - 5.0, mid))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(muted))
        painter.drawPolygon(QPolygonF([QPointF(x2, mid), QPointF(x2 - 6.0, mid - 3.0),
                                       QPointF(x2 - 6.0, mid + 3.0)]))
        painter.setPen(muted)
        painter.drawText(QRectF(boxes[index].right(), mid + 5.0, _GAP, 12.0),
                         Qt.AlignmentFlag.AlignCenter, _CAPTIONS[index])
    painter.restore()
