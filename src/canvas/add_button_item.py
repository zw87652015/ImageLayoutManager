from PyQt6.QtWidgets import QGraphicsRectItem, QGraphicsItem
from PyQt6.QtGui import QColor, QPen, QBrush, QPainter
from PyQt6.QtCore import Qt, QPointF, QRectF

from src.canvas import canvas_accent


def _cosmetic_pen(color, width=1.0, style=Qt.PenStyle.SolidLine) -> QPen:
    pen = QPen(color, width, style)
    pen.setCosmetic(True)
    return pen


class AddButtonItem(QGraphicsRectItem):
    """A '+' button placed on the canvas margins for adding rows/cells.

    Row buttons are wide horizontal bars; cell buttons are tall vertical bars.
    """

    def __init__(self, action: str, width: float = 0, height: float = 0,
                 row_index: int = -1, col_index: int = -1, parent=None):
        super().__init__(parent)
        self.action = action        # "row_above", "row_below", "cell_left", "cell_right"
        self.row_index = row_index
        self.col_index = col_index
        self._hovered = False

        w = width if width > 0 else 1.0
        h = height if height > 0 else 1.0
        self.setRect(0, 0, w, h)
        self.setZValue(500)
        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        if "row" in action:
            self.setToolTip("Add Row Above" if "above" in action else "Add Row Below")
        else:
            self.setToolTip("Add Cell Left" if "left" in action else "Add Cell Right")

    def paint(self, painter: QPainter, option, widget=None):
        r = self.rect()
        cx, cy = r.center().x(), r.center().y()
        accent = canvas_accent.accent()
        hovered = self._hovered
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        min_mm = min(r.width(), r.height())
        scale = abs(painter.worldTransform().m11()) or 1.0
        min_px = min_mm * scale
        half_px = 0.5 / scale
        track = r.adjusted(half_px, half_px, -half_px, -half_px)
        rad = min(track.width(), track.height()) / 2
        fill = QColor(accent)
        fill.setAlphaF(0.16 if hovered else 0.07)
        if hovered:
            pen = _cosmetic_pen(accent, 1.2)
        else:
            edge = QColor(accent)
            edge.setAlphaF(0.55)
            pen = _cosmetic_pen(edge, 1.0, Qt.PenStyle.CustomDashLine)
            pen.setDashPattern([4, 3])
        painter.setPen(pen)
        painter.setBrush(QBrush(fill))
        painter.drawRoundedRect(track, rad, rad)

        if min_px >= 10:
            d = min_mm * 0.82
            badge = QRectF(cx - d / 2, cy - d / 2, d, d)
            if hovered:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(accent))
                glyph = canvas_accent.on_accent()
            else:
                ring = QColor(accent)
                ring.setAlphaF(0.9)
                painter.setPen(_cosmetic_pen(ring, 1.2))
                painter.setBrush(QBrush(QColor(255, 255, 255)))
                glyph = accent
            painter.drawEllipse(badge)
            arm = d * 0.24
        else:
            glyph = accent
            arm = min_mm * 0.3

        glyph_pen = _cosmetic_pen(glyph, 1.8)
        glyph_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(glyph_pen)
        painter.drawLine(QPointF(cx - arm, cy), QPointF(cx + arm, cy))
        painter.drawLine(QPointF(cx, cy - arm), QPointF(cx, cy + arm))

    def hoverEnterEvent(self, event):
        self._hovered = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self._hovered = False
        self.update()
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            scene = self.scene()
            if scene and hasattr(scene, '_on_add_button_clicked'):
                scene._on_add_button_clicked(self.action, self.row_index, self.col_index)
            event.accept()
            return
        super().mousePressEvent(event)
