"""Undo history rendered as a vertical timeline.

A :class:`QUndoView` subclass with a custom delegate: every undoable step
gets a node on a left-hand rail. Steps already applied are filled, the
current position is marked with a halo and an accent pill, and undone steps
are dashed and hollow. The clean (saved) state carries a success dot.
Clicking any node jumps the stack to that index (native QUndoView behaviour).
"""

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QFontMetrics, QPainter, QPen
from PyQt6.QtWidgets import QStyle, QStyledItemDelegate, QUndoView

from src.app.theme import token_color


class _TimelineDelegate(QStyledItemDelegate):
    ROW_H = 28
    RAIL_X = 16
    TEXT_X = 30

    def __init__(self, view: "HistoryTimeline"):
        super().__init__(view)
        self._view = view

    def sizeHint(self, option, index):
        return QSize(option.rect.width(), self.ROW_H)

    def paint(self, painter: QPainter, option, index):
        colors = self._view._colors

        def c(key):
            return token_color(colors[key])

        stack = self._view.stack()
        current = stack.index() if stack is not None else 0
        clean = stack.cleanIndex() if stack is not None else -1
        row = index.row()
        count = index.model().rowCount()
        r = QRectF(option.rect)
        rail_x = r.left() + self.RAIL_X
        cy = r.top() + r.height() / 2

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        pill = r.adjusted(4, 2, -4, -2)
        if row == current:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(c("accent_tint")))
            painter.drawRoundedRect(pill, 6, 6)
        elif option.state & QStyle.StateFlag.State_MouseOver:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(c("hover")))
            painter.drawRoundedRect(pill, 6, 6)

        applied_color = c("accent")
        applied_color.setAlphaF(0.45)
        applied = QPen(applied_color, 1.5)
        applied.setCapStyle(Qt.PenCapStyle.FlatCap)
        future = QPen(c("border_strong"), 1.2, Qt.PenStyle.CustomDashLine)
        future.setDashPattern([2, 2.5])

        if row > 0:
            painter.setPen(applied if row <= current else future)
            painter.drawLine(QPointF(rail_x, r.top()), QPointF(rail_x, cy))
        if row < count - 1:
            painter.setPen(applied if row < current else future)
            painter.drawLine(QPointF(rail_x, cy), QPointF(rail_x, r.bottom() + 1))

        accent = c("accent")
        centre = QPointF(rail_x, cy)
        if row == current:
            halo = QColor(accent)
            halo.setAlphaF(0.18)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(halo))
            painter.drawEllipse(centre, 6, 6)
            painter.setBrush(QBrush(accent))
            painter.drawEllipse(centre, 3.5, 3.5)
        elif row == 0:
            painter.setPen(QPen(c("text_sec"), 1.4))
            painter.setBrush(QBrush(c("panel")))
            painter.drawEllipse(centre, 3.5, 3.5)
        elif row < current:
            dot = QColor(accent)
            dot.setAlphaF(0.55)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(dot))
            painter.drawEllipse(centre, 3, 3)
        else:
            painter.setPen(QPen(c("border_strong"), 1.2))
            painter.setBrush(QBrush(c("panel")))
            painter.drawEllipse(centre, 3, 3)

        font = QFont(option.font)
        if row == current:
            font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)
        painter.setPen(c("text") if row <= current else c("text_tert"))
        text_left = r.left() + self.TEXT_X
        right = r.right() - 6 - (14 if row == clean else 0)
        text_rect = QRectF(text_left, r.top(), max(0.0, right - text_left), r.height())
        text = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        elided = QFontMetrics(font).elidedText(
            text, Qt.TextElideMode.ElideRight, int(text_rect.width()))
        painter.drawText(
            text_rect,
            int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
            elided)

        if row == clean:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(c("success")))
            painter.drawEllipse(QPointF(r.right() - 10, cy), 2.5, 2.5)
        painter.restore()


class HistoryTimeline(QUndoView):
    """QUndoView with timeline visuals and theme-aware colours."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._colors = {
            "accent": "#4F5BD5", "accent_tint": "rgba(79, 91, 213, 0.10)",
            "hover": "rgba(31, 30, 28, 0.05)", "border_strong": "#CFCCC6",
            "panel": "#FBFAF9", "success": "#2F8F5B", "text": "#1F1E1C",
            "text_sec": "#6B6862", "text_tert": "#9A968F",
        }
        self.setItemDelegate(_TimelineDelegate(self))
        self.setUniformItemSizes(True)
        self.setFrameShape(QUndoView.Shape.NoFrame)

    def apply_theme(self, tokens: dict):
        for key in self._colors:
            if key in tokens:
                self._colors[key] = tokens[key]
        self.viewport().update()
