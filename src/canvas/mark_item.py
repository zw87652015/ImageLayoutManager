"""Canvas item for a persistent vector Mark.

Scene units are millimetres and the item sits at pos (0, 0), so local and
scene coordinates coincide. Painting goes through
:mod:`src.utils.mark_render`, the same code the exporters use. During drags
the item paints a transient ``_preview_points`` copy — the model is only
mutated afterwards, by the undo command the scene emits on release.
"""
import copy
import math

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsObject

from src.utils import mark_geometry, mark_render

_ACCENT = "#4A90D9"


class MarkItem(QGraphicsObject):
    """Selectable mark; handles reshape, vertex edits, and multi-mark moves."""

    HANDLE_PX = 7
    HIT_PX = 4
    MIN_MOVE_MM = 0.05

    def __init__(self, mark, preview: bool = False, parent=None):
        super().__init__(parent)
        self.mark_id = mark.id
        self.model = None
        self.preview = preview
        self._preview_points = None  # transient points while dragging
        self._handle = None          # active reshape handle
        self._press_scene = None     # QPointF of a body press
        self._moving = False
        self._move_set = {}          # MarkItem -> old points (body move)
        self._old_points = None      # own points at press time

        self._interactive = False
        if preview:
            self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            self.setZValue(95)
        else:
            # Non-interactive by default; the scene flips this with Draw mode.
            self.set_interactive(False)

    def set_interactive(self, on: bool) -> None:
        """Enable/disable press, hover and selection (Draw mode gate)."""
        self._interactive = on
        if self.preview:
            return
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, on)
        self.setAcceptedMouseButtons(
            Qt.MouseButton.LeftButton | Qt.MouseButton.RightButton
            if on else Qt.MouseButton.NoButton)
        self.setAcceptHoverEvents(on)
        self.update()

    # ── model / display state ─────────────────────────────────────────

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            self.update()
        return super().itemChange(change, value)

    def set_model(self, mark, z: float) -> None:
        self.prepareGeometryChange()
        # The item keeps its own snapshot: undo commands mutate the project
        # mark BEFORE the refresh callback runs, and Qt must still see the
        # old bounds when prepareGeometryChange() reindexes this item.
        self.model = copy.deepcopy(mark)
        self._preview_points = None
        self.setZValue(z)
        self.update()

    def set_preview_points(self, points) -> None:
        self.prepareGeometryChange()
        self._preview_points = [list(p) for p in points] if points is not None else None
        self.update()

    def _disp(self):
        """Mark used for painting (preview points replace model points)."""
        m = copy.copy(self.model)
        if self._preview_points is not None:
            m.points = self._preview_points
        return m

    def _points(self):
        return self._preview_points if self._preview_points is not None else (
            self.model.points if self.model is not None else [])

    def _px_mm(self, px: float) -> float:
        scene = self.scene()
        if scene is not None and hasattr(scene, 'px_to_mm'):
            return scene.px_to_mm(px)
        return px * 0.5

    # ── handles ───────────────────────────────────────────────────────

    def _handles_visible(self) -> bool:
        scene = self.scene()
        if (self.preview or not self.isSelected() or scene is None
                or getattr(scene, 'preview_mode', False)
                or not getattr(scene, 'draw_mode', False)
                or getattr(scene, 'draw_tool', None)):
            return False
        marks = [i for i in scene.selectedItems() if isinstance(i, MarkItem)]
        return len(marks) == 1 and marks[0] is self

    def _handle_rects(self):
        """{handle_id: QRectF} in local mm; vertex ids are ints."""
        if not self._handles_visible() or self.model is None:
            return {}
        half = self._px_mm(self.HANDLE_PX) / 2.0
        pts = self._points()
        rects = {}
        if self.model.kind in ("rect", "ellipse"):
            for hid, (hx, hy) in mark_geometry.box_handle_points(pts).items():
                rects[hid] = QRectF(hx - half, hy - half, 2 * half, 2 * half)
        elif self.model.kind in ("line", "polygon"):
            for i, (px, py) in enumerate(pts):
                rects[i] = QRectF(px - half, py - half, 2 * half, 2 * half)
        return rects

    def _selection_rects(self):
        """Paint-only selection markers for every selected mark.

        A single editable mark keeps its real ``_handle_rects``; everything
        else gets non-interactive square markers on its control points:
        line/arrow endpoints, polygon/polyline vertices, the dot centre,
        a rect's four corners, an ellipse's four cardinal points.
        """
        if (self.model is None or not self.isSelected()
                or not self._can_edit()):
            return {}
        handles = self._handle_rects()
        if handles:
            return handles
        half = self._px_mm(self.HANDLE_PX) / 2.0
        pts = self._points()
        centres = []
        if self.model.kind == "rect":
            box = mark_geometry.box_handle_points(pts)
            centres = [box[k] for k in ("tl", "tr", "br", "bl")]
        elif self.model.kind == "ellipse":
            box = mark_geometry.box_handle_points(pts)
            centres = [box[k] for k in ("t", "r", "b", "l")]
        else:  # line, dot, polygon/polyline: every point
            centres = list(pts)
        return {i: QRectF(cx - half, cy - half, 2 * half, 2 * half)
                for i, (cx, cy) in enumerate(centres)}

    def _handle_at(self, pos: QPointF):
        for hid, rect in self._handle_rects().items():
            if rect.contains(pos):
                return hid
        return None

    # ── geometry ──────────────────────────────────────────────────────

    def boundingRect(self) -> QRectF:
        if self.model is None:
            return QRectF()
        rect = mark_render.bounds_mm(self._disp())
        # Constant pad: handle rects live inside shape() only, so the bounds
        # never change when handle visibility toggles (no stale BSP trails).
        pad = self._px_mm(self.HANDLE_PX / 2.0 + 2)
        return rect.adjusted(-pad, -pad, pad, pad)

    def shape(self) -> QPainterPath:
        path = mark_render.hit_path_mm(self._disp(), self._px_mm(self.HIT_PX))
        for r in self._handle_rects().values():
            path.addRect(r)
        return path

    # ── painting ──────────────────────────────────────────────────────

    def paint(self, painter: QPainter, option, widget=None) -> None:
        if self.model is None:
            return
        disp = self._disp()
        mark_render.draw(painter, disp, scale=1.0)

        if self.preview:
            return
        scene = self.scene()
        preview_mode = bool(getattr(scene, 'preview_mode', False))
        if preview_mode or not self.isSelected():
            return

        # Selection markers: real handles for a single editable mark,
        # non-interactive squares on the control points of every other
        # selected mark (multi-selection included).
        for rect in self._selection_rects().values():
            painter.save()
            pen = QPen(QColor(_ACCENT), 0)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(QColor("#FFFFFF"))
            painter.drawRect(rect)
            painter.restore()

    # ── interaction ───────────────────────────────────────────────────

    def _can_edit(self) -> bool:
        scene = self.scene()
        return (not self.preview and scene is not None
                and not getattr(scene, 'preview_mode', False)
                and getattr(scene, 'draw_mode', False)
                and not getattr(scene, 'draw_tool', None))

    def _selected_mark_items(self):
        scene = self.scene()
        if scene is None:
            return [self]
        marks = [i for i in scene.selectedItems()
                 if isinstance(i, MarkItem) and not i.preview]
        return marks or [self]

    def mousePressEvent(self, event):
        # Handle hit detection runs before super() (handles only exist while
        # this item is already selected); the body move-set must be built
        # AFTER super() so it reflects the post-press selection.
        handle = None
        if event.button() == Qt.MouseButton.LeftButton and self._can_edit():
            handle = self._handle_at(event.pos())
            if handle is not None:
                self._handle = handle
                self._old_points = [list(p) for p in self._points()]
        super().mousePressEvent(event)
        if (event.button() == Qt.MouseButton.LeftButton and self._can_edit()
                and handle is None and self.isSelected()):
            self._press_scene = QPointF(event.scenePos())
            self._move_set = {i: [list(p) for p in i._points()]
                              for i in self._selected_mark_items()}

    def mouseMoveEvent(self, event):
        if not self._can_edit():
            super().mouseMoveEvent(event)
            return
        shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        if self._handle is not None:
            p = [event.pos().x(), event.pos().y()]
            params = None
            if self.model.kind == "polygon" and self.model.closed:
                params = mark_geometry.regular_polygon_params(
                    self._old_points)
            if params is not None:
                # Regular polygon: vertex drags rotate/scale it about its
                # centre so vertex k follows the cursor; Shift snaps to 15°.
                cx, cy, _r, _rot = params
                n = len(self._old_points)
                dx, dy = p[0] - cx, p[1] - cy
                radius = math.hypot(dx, dy)
                rot = math.atan2(dy, dx) - self._handle * 2.0 * math.pi / n
                if shift:
                    rot = mark_geometry.snap_rotation(rot)
                new_pts = mark_geometry.regular_polygon_points(
                    cx, cy, radius, n, rot)
            elif self.model.kind in ("rect", "ellipse"):
                new_pts = mark_geometry.resize_box(
                    self._old_points, self._handle, p, keep_aspect=shift)
            else:
                new_pts = mark_geometry.move_vertex(
                    self._old_points, self._handle, p, shift,
                    closed=self.model.closed)
            self.set_preview_points(new_pts)
            event.accept()
            return
        if self._press_scene is not None:
            delta = event.scenePos() - self._press_scene
            if self._moving or delta.manhattanLength() > 0:
                self._moving = True
                for item, old in self._move_set.items():
                    item.set_preview_points(
                        mark_geometry.translate(old, delta.x(), delta.y(), shift))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if (event.button() == Qt.MouseButton.LeftButton and self._can_edit()
                and (self._handle is not None or self._moving)):
            changed = []
            moved_items = list(self._move_set.items()) or [(self, self._old_points)]
            if self._handle is not None:
                old, new = self._old_points, self._points()
                if old != new:
                    changed.append((self.mark_id, old, [list(p) for p in new]))
            else:
                for item, old in moved_items:
                    new = item._points()
                    moved = math.hypot(
                        new[0][0] - old[0][0], new[0][1] - old[0][1]) if new and old else 0
                    if moved >= self.MIN_MOVE_MM:
                        changed.append((item.mark_id, old, [list(p) for p in new]))
            self._handle = None
            self._press_scene = None
            self._moving = False
            self._move_set = {}
            if changed:
                self.scene().marks_geometry_changed.emit(changed)
            else:
                for item, _old in moved_items:
                    item.set_preview_points(None)
            event.accept()
            return
        self._handle = None
        self._press_scene = None
        self._moving = False
        self._move_set = {}
        super().mouseReleaseEvent(event)

    def hoverMoveEvent(self, event):
        if self._can_edit():
            if self._handle_at(event.pos()) is not None:
                self.setCursor(Qt.CursorShape.CrossCursor)
            else:
                self.setCursor(Qt.CursorShape.SizeAllCursor)
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event):
        self.unsetCursor()
        super().hoverLeaveEvent(event)

    def contextMenuEvent(self, event):
        scene = self.scene()
        if (scene is not None and not self.preview
                and getattr(scene, 'draw_mode', False)
                and not getattr(scene, 'draw_tool', None)):
            scene.mark_context_menu.emit(self.mark_id, event.screenPos())
            event.accept()
            return
        super().contextMenuEvent(event)
