"""Canvas item for a GroupLabel band.

Draws through :mod:`src.utils.group_label_render`, the same code the
exporters use, so the canvas is a true preview.  The band rect comes from
the layout engine, so this item never decides its own resting geometry —
it renders, handles selection, and supports drag-to-re-side:

Dragging a band fades it to a ghost that follows the cursor while the
scene shows a dashed target rect on the opposite side (top<->bottom for
spans, left<->right for row titles).  Dropping inside the target emits
``side_dropped``; dropping anywhere else snaps the ghost back.  After the
drop reflows the layout, :meth:`animate_from` tweens the band from its
old rect to the new one so the eye can track the move.
"""
from PyQt6.QtCore import (
    QEasingCurve, QPointF, QRectF, Qt, QVariantAnimation, pyqtSignal,
)
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsObject

from src.utils import group_label_render

_DRAG_THRESHOLD_MM = 1.5
_ANIM_MS = 180


class GroupLabelItem(QGraphicsObject):
    """Selectable, drag-to-re-side band. Resting geometry is owned by the layout."""

    double_clicked = pyqtSignal(str)  # group_label_id
    drag_started = pyqtSignal(str)                       # group_label_id
    drag_moved = pyqtSignal(str, QPointF)                # id, scene pos
    drag_finished = pyqtSignal(str, QPointF)             # id, scene pos

    def __init__(self, group_label_id: str, parent=None):
        super().__init__(parent)
        self.group_label_id = group_label_id
        self.model = None            # GroupLabel, refreshed by the scene
        self._band = QRectF()        # resting rect (scene coordinates)
        self._hover = False
        self._press_pos = None       # scene pos of the initial mouse press
        self._grab_offset = QPointF()
        self._dragging = False
        self._anim = None            # active QVariantAnimation, if any

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)
        # Bands sit in reserved whitespace; keep them above cell backgrounds
        # but below floating text so captions stay readable.
        self.setZValue(5)

    # ── geometry (resting rect comes from the layout engine) ────────────

    def set_band(self, band: QRectF, model) -> None:
        """Update geometry and model. Cheap no-op when nothing changed."""
        if self._anim is not None:
            self._anim.stop()
            self._anim = None
        changed = band != self._band
        if changed:
            self.prepareGeometryChange()
            self._band = QRectF(band)
            self.setPos(band.x(), band.y())
        self.model = model
        if changed:
            self.update()

    def animate_from(self, old_band: QRectF, duration_ms: int = _ANIM_MS) -> None:
        """Tween the displayed band from *old_band* to the current one."""
        target = QRectF(self._band)
        if old_band == target or duration_ms <= 0:
            return
        if self._anim is not None:
            self._anim.stop()
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(duration_ms)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.setStartValue(QRectF(old_band))
        self._anim.setEndValue(QRectF(target))
        self._anim.valueChanged.connect(self._apply_animated_band)
        self._anim.finished.connect(self._animation_done)
        self._anim.start()

    def _apply_animated_band(self, value: QRectF) -> None:
        self.prepareGeometryChange()
        self._band = QRectF(value)
        self.setPos(self._band.x(), self._band.y())
        self.update()

    def _animation_done(self) -> None:
        self._anim = None

    def band_scene_rect(self) -> QRectF:
        """Band in scene coordinates (a copy, safe to keep)."""
        return QRectF(self._band)

    def local_band(self) -> QRectF:
        """Band in item-local coordinates (origin at the band's top-left)."""
        return QRectF(0, 0, self._band.width(), self._band.height())

    def boundingRect(self) -> QRectF:
        band = self.local_band()
        if self.model is None:
            return band
        # Rotated text can spill outside the reserved band; include it so Qt
        # does not clip or leave trails when the item repaints.
        bounds = group_label_render.rotated_bounds_mm(self.model, band)
        return bounds.adjusted(-1.0, -1.0, 1.0, 1.0)

    # ── painting ────────────────────────────────────────────────────────

    def paint(self, painter: QPainter, option, widget=None) -> None:
        if self.model is None:
            return

        band = self.local_band()
        preview = bool(getattr(self.scene(), 'preview_mode', False))

        if not preview and (self.isSelected() or self._hover) and not self._dragging:
            painter.save()
            colour = QColor("#4A90D9" if self.isSelected() else "#B0B0B0")
            pen = QPen(colour, 0.3, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(band)
            painter.restore()

        # scale=1.0: scene units are already millimetres.
        group_label_render.draw(painter, self.model, band, scale=1.0)

    # ── hover / cursor feedback ─────────────────────────────────────────

    def hoverEnterEvent(self, event):
        self._hover = True
        if not bool(getattr(self.scene(), 'preview_mode', False)):
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self._hover = False
        self.unsetCursor()
        self.update()
        super().hoverLeaveEvent(event)

    # ── drag to re-side ─────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if (event.button() == Qt.MouseButton.LeftButton
                and not bool(getattr(self.scene(), 'preview_mode', False))):
            self._press_pos = event.scenePos()
            self._grab_offset = self.pos() - event.scenePos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._press_pos is not None:
            if not self._dragging:
                dist = (event.scenePos() - self._press_pos).manhattanLength()
                if dist > _DRAG_THRESHOLD_MM:
                    self._dragging = True
                    self.setOpacity(0.45)
                    self.setZValue(50)  # above cells while floating
                    self.setCursor(Qt.CursorShape.ClosedHandCursor)
                    self.drag_started.emit(self.group_label_id)
            if self._dragging:
                self.prepareGeometryChange()
                self.setPos(event.scenePos() + self._grab_offset)
                self.drag_moved.emit(self.group_label_id, event.scenePos())
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._dragging and event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            self._press_pos = None
            self.setOpacity(1.0)
            self.setZValue(5)
            self.unsetCursor()
            # Snap the ghost back; a successful drop is repositioned by the
            # relayout that follows the side-change command.
            self.setPos(self._band.x(), self._band.y())
            self.drag_finished.emit(self.group_label_id, event.scenePos())
            event.accept()
            return
        self._press_pos = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        self.double_clicked.emit(self.group_label_id)
        event.accept()
