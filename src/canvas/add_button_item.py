from PyQt6.QtWidgets import QGraphicsRectItem, QGraphicsItem
from PyQt6.QtGui import QColor, QPen, QBrush, QFont, QPainter
from PyQt6.QtCore import Qt, QRectF

from src.canvas import canvas_accent


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
        bg = canvas_accent.accent(180) if self._hovered else canvas_accent.accent(100)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QBrush(bg))
        border = QPen(canvas_accent.accent(220), 1.0)
        border.setCosmetic(True)
        painter.setPen(border)
        rad = min(r.width(), r.height()) * 0.25
        painter.drawRoundedRect(r, rad, rad)

        # Draw "+" centred, arm length based on shorter dimension
        plus = QPen(Qt.GlobalColor.white, 1.5)
        plus.setCosmetic(True)
        plus.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(plus)
        cx, cy = r.center().x(), r.center().y()
        arm = min(r.width(), r.height()) * 0.28
        painter.drawLine(QRectF(cx - arm, cy, arm * 2, 0).topLeft(),
                         QRectF(cx - arm, cy, arm * 2, 0).topRight())
        painter.drawLine(QRectF(cx, cy - arm, 0, arm * 2).topLeft(),
                         QRectF(cx, cy - arm, 0, arm * 2).bottomLeft())

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
