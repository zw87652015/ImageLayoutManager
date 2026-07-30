"""Undo history rendered as a vertical timeline.

A :class:`QUndoView` subclass with a custom delegate: every undoable step
gets a node on a left-hand rail. Nodes above the current position (already
applied) are filled, the current position is ringed in the accent colour,
and steps that have been undone are hollow — so the "time axis" of the
project is readable at a glance. Clicking any node jumps the stack to that
index (native QUndoView behaviour).
"""

from PyQt6.QtCore import QRectF, QSize, Qt
from PyQt6.QtGui import QPainter, QPen
from PyQt6.QtWidgets import QStyle, QStyledItemDelegate, QUndoView

from src.app.theme import token_color

_RAIL_X = 12        # rail centre, px from the item's left edge
_DOT_R = 3.5        # normal node radius
_CUR_R = 5.0        # current-node radius
_ROW_H = 22


class _TimelineDelegate(QStyledItemDelegate):
    def __init__(self, view: "HistoryTimeline"):
        super().__init__(view)
        self._view = view

    def sizeHint(self, option, index):
        return QSize(option.rect.width(), _ROW_H)

    def paint(self, painter: QPainter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        colors = self._view._colors
        stack = self._view.stack()
        current = stack.index() if stack else 0
        row = index.row()
        r = option.rect
        rail_x = r.left() + _RAIL_X
        cy = r.center().y()

        # Selection / hover wash
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(r, token_color(colors["hover"]))
        elif option.state & QStyle.StateFlag.State_MouseOver:
            wash = token_color(colors["hover"])
            if wash.alpha() > 80:
                wash.setAlpha(80)
            painter.fillRect(r, wash)

        # Rail segments: up to previous row, down to next row
        rail_pen = QPen(token_color(colors["border"]))
        rail_pen.setWidthF(1.0)
        painter.setPen(rail_pen)
        if row > 0:
            painter.drawLine(int(rail_x), r.top(), int(rail_x), int(cy))
        painter.drawLine(int(rail_x), int(cy), int(rail_x), r.bottom() + 1)

        # Node
        if row == 0:
            # Clean state — keep the classic save icon instead of a dot
            icon = self._view.cleanIcon()
            if not icon.isNull():
                icon.paint(painter, int(rail_x - 6), int(cy - 6), 12, 12)
        else:
            if row == current:
                painter.setPen(QPen(token_color(colors["accent"]), 1.6))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(QRectF(rail_x - _CUR_R, cy - _CUR_R,
                                           _CUR_R * 2, _CUR_R * 2))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(token_color(colors["accent"]))
                painter.drawEllipse(QRectF(rail_x - 2, cy - 2, 4, 4))
            elif row < current:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(token_color(colors["text_sec"]))
                painter.drawEllipse(QRectF(rail_x - _DOT_R, cy - _DOT_R,
                                           _DOT_R * 2, _DOT_R * 2))
            else:
                # Undone (future) step — hollow, muted
                painter.setPen(QPen(token_color(colors["border"]), 1.2))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(QRectF(rail_x - _DOT_R, cy - _DOT_R,
                                           _DOT_R * 2, _DOT_R * 2))

        # Text — undone steps render muted
        text = index.data(Qt.ItemDataRole.DisplayRole) or ""
        if row > current:
            painter.setPen(token_color(colors["text_tert"]))
        else:
            painter.setPen(token_color(colors["text"]))
        text_rect = r.adjusted(_RAIL_X + 10, 0, -6, 0)
        painter.drawText(text_rect,
                         Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                         text)
        painter.restore()


class HistoryTimeline(QUndoView):
    """QUndoView with timeline visuals and theme-aware colours."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._colors = {
            "accent": "#0891B2", "text": "#1F2328", "text_sec": "#6E7781",
            "text_tert": "#8C959F", "border": "#D0D7DE", "hover": "#F0F3F6",
        }
        self.setItemDelegate(_TimelineDelegate(self))
        self.setUniformItemSizes(True)
        self.setFrameShape(QUndoView.Shape.NoFrame)

    def apply_theme(self, tokens: dict):
        for key in self._colors:
            if key in tokens:
                self._colors[key] = tokens[key]
        self.viewport().update()
