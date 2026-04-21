"""Interactive rectangle that defines the export region.

Two usage phases:
  1. "Defining" mode — scene intercepts a rubber-band drag before creating the
     final item (see CanvasScene._defining_export_region).
  2. Committed — a movable, resizable rectangle with dashed border and a small
     label "Export Region". Editing emits `export_region_edited` on the scene.

The item stores the current region as scene-space mm coordinates (the scene
already works in mm). On geometry change it calls back into the scene so the
model Project.export_region stays in sync and MainWindow can push an undoable
command on mouse release.
"""

from PyQt6.QtWidgets import QGraphicsRectItem, QGraphicsItem
from PyQt6.QtGui import QColor, QPen, QBrush, QPainter, QFont
from PyQt6.QtCore import Qt, QRectF, QPointF


# Handle half-size (mm) — square drag handles at the 4 corners + 4 mid edges.
_HANDLE = 1.5
_HIT_PAD = 1.0  # extra hit-test padding around handles (mm)


class ExportRegionItem(QGraphicsRectItem):
    """Rect overlay showing and editing the current export region.

    Coordinate convention: rect is in scene-space mm; scene origin is page (0,0).
    """

    Z = 800  # above dividers (600) and edge badges, below modal overlays

    def __init__(self, x_mm: float, y_mm: float, w_mm: float, h_mm: float, parent=None):
        super().__init__(parent)
        self.setRect(QRectF(x_mm, y_mm, w_mm, h_mm))
        self.setZValue(self.Z)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsFocusable, True)
        self.setAcceptHoverEvents(True)

        # Styling
        self._border_color = QColor(230, 120, 40, 235)  # warm orange
        self._fill_color = QColor(230, 120, 40, 32)
        self._label_bg = QColor(230, 120, 40, 220)

        self.setPen(QPen(Qt.PenStyle.NoPen))
        self.setBrush(QBrush(Qt.BrushStyle.NoBrush))

        # Drag state
        self._drag_mode = None  # None | 'move' | ('resize', dx, dy)
        self._drag_start_scene = QPointF()
        self._drag_start_rect = QRectF()

        # Original rect (for undoable command)
        self.original_rect = QRectF(self.rect())

        self.setCursor(Qt.CursorShape.SizeAllCursor)

    # ------------------------------------------------------------------
    # Paint
    # ------------------------------------------------------------------

    def paint(self, painter: QPainter, option, widget=None):
        # Suppress in preview/export
        scene = self.scene()
        if scene and getattr(scene, 'preview_mode', False):
            return

        r = self.rect()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Semi-transparent fill
        painter.fillRect(r, QBrush(self._fill_color))

        # Dashed border
        pen = QPen(self._border_color)
        pen.setCosmetic(True)
        pen.setWidthF(1.5)
        pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(r)

        # Handles — only when selected or hovered
        if self.isSelected():
            h_pen = QPen(self._border_color)
            h_pen.setCosmetic(True)
            h_pen.setWidthF(1.0)
            painter.setPen(h_pen)
            painter.setBrush(QBrush(QColor("#FFFFFF")))
            for hx, hy in self._handle_centers():
                painter.drawRect(QRectF(hx - _HANDLE, hy - _HANDLE,
                                        _HANDLE * 2, _HANDLE * 2))

        # Label "Export Region" — device-pixel sized so zoom-invariant
        transform = painter.transform()
        m = transform.m11()
        if m <= 0:
            return
        label = "Export Region"
        dev_rect = transform.mapRect(r)

        badge_h = 16
        pad_x = 6
        # Crude width estimate using font metrics; refined via actual font below.
        font = QFont("Arial")
        font.setPixelSize(10)
        font.setBold(True)
        painter.save()
        painter.resetTransform()
        painter.setFont(font)
        fm = painter.fontMetrics()
        txt_w = fm.horizontalAdvance(label) + pad_x * 2
        badge_rect = QRectF(dev_rect.left(), dev_rect.top() - badge_h,
                            txt_w, badge_h)
        painter.fillRect(badge_rect, self._label_bg)
        painter.setPen(QPen(QColor("#FFFFFF")))
        painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, label)
        painter.restore()

    # ------------------------------------------------------------------
    # Handle hit-testing
    # ------------------------------------------------------------------

    def _handle_centers(self):
        r = self.rect()
        cx = r.center().x()
        cy = r.center().y()
        return [
            (r.left(),  r.top()),     # TL
            (cx,        r.top()),     # T
            (r.right(), r.top()),     # TR
            (r.right(), cy),          # R
            (r.right(), r.bottom()),  # BR
            (cx,        r.bottom()),  # B
            (r.left(),  r.bottom()),  # BL
            (r.left(),  cy),          # L
        ]

    _HANDLE_DX_DY = [
        (-1, -1), (0, -1), (1, -1),
        (1, 0),
        (1, 1), (0, 1), (-1, 1),
        (-1, 0),
    ]

    def _hit_handle(self, pos: QPointF):
        """Return (dx, dy) resize directions for the handle under pos, else None."""
        p = _HANDLE + _HIT_PAD
        for (hx, hy), (dx, dy) in zip(self._handle_centers(), self._HANDLE_DX_DY):
            if abs(pos.x() - hx) <= p and abs(pos.y() - hy) <= p:
                return (dx, dy)
        return None

    def hoverMoveEvent(self, event):
        hit = self._hit_handle(event.pos())
        if hit:
            dx, dy = hit
            if dx != 0 and dy != 0:
                cursor = (Qt.CursorShape.SizeFDiagCursor
                          if dx * dy > 0
                          else Qt.CursorShape.SizeBDiagCursor)
            elif dx != 0:
                cursor = Qt.CursorShape.SizeHorCursor
            else:
                cursor = Qt.CursorShape.SizeVerCursor
            self.setCursor(cursor)
        else:
            self.setCursor(Qt.CursorShape.SizeAllCursor)
        super().hoverMoveEvent(event)

    # ------------------------------------------------------------------
    # Drag — move or resize
    # ------------------------------------------------------------------

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        self.setSelected(True)
        self._drag_start_scene = event.scenePos()
        self._drag_start_rect = QRectF(self.rect())
        self.original_rect = QRectF(self.rect())
        hit = self._hit_handle(event.pos())
        self._drag_mode = ('resize', *hit) if hit else 'move'
        event.accept()

    # Snap threshold in mm (same order of magnitude as snap_rect elsewhere).
    _SNAP_MM = 2.0

    def _snap_edges(self, r: QRectF, active_edges: set) -> QRectF:
        """Snap edges of `r` listed in `active_edges` to nearby page/margin/cell
        borders. Also shows pink guide lines on the scene for matched snaps.

        active_edges: subset of {'left','right','top','bottom'} whose positions
        may move. Other edges stay fixed (prevents width/height distortion
        during a corner-resize).
        """
        scene = self.scene()
        if not scene or not hasattr(scene, 'get_snap_lines'):
            return r
        v_lines, h_lines = scene.get_snap_lines(include_page_edges=True)

        # Find best horizontal snap (x-axis)
        best_dx = 0.0
        best_snap_x = None
        best_edge_x = None
        min_dx = self._SNAP_MM
        candidates_x = []
        if 'left' in active_edges:
            candidates_x.append(('left', r.left()))
        if 'right' in active_edges:
            candidates_x.append(('right', r.right()))
        # When moving (both edges active), also snap center.
        if 'left' in active_edges and 'right' in active_edges:
            candidates_x.append(('center', r.center().x()))
        for edge_name, edge_val in candidates_x:
            for tv in v_lines:
                diff = tv - edge_val
                if abs(diff) < min_dx:
                    min_dx = abs(diff)
                    best_dx = diff
                    best_snap_x = tv
                    best_edge_x = edge_name

        # Find best vertical snap (y-axis)
        best_dy = 0.0
        best_snap_y = None
        best_edge_y = None
        min_dy = self._SNAP_MM
        candidates_y = []
        if 'top' in active_edges:
            candidates_y.append(('top', r.top()))
        if 'bottom' in active_edges:
            candidates_y.append(('bottom', r.bottom()))
        if 'top' in active_edges and 'bottom' in active_edges:
            candidates_y.append(('center', r.center().y()))
        for edge_name, edge_val in candidates_y:
            for th in h_lines:
                diff = th - edge_val
                if abs(diff) < min_dy:
                    min_dy = abs(diff)
                    best_dy = diff
                    best_snap_y = th
                    best_edge_y = edge_name

        # Apply snaps
        if best_dx != 0.0:
            if self._drag_mode == 'move' or best_edge_x == 'center':
                r.translate(best_dx, 0)
            elif best_edge_x == 'left':
                r.setLeft(r.left() + best_dx)
            elif best_edge_x == 'right':
                r.setRight(r.right() + best_dx)
        if best_dy != 0.0:
            if self._drag_mode == 'move' or best_edge_y == 'center':
                r.translate(0, best_dy)
            elif best_edge_y == 'top':
                r.setTop(r.top() + best_dy)
            elif best_edge_y == 'bottom':
                r.setBottom(r.bottom() + best_dy)

        # Show guide lines for matched snaps
        if hasattr(scene, 'show_snap_lines'):
            scene.show_snap_lines(
                [best_snap_x] if best_snap_x is not None else [],
                [best_snap_y] if best_snap_y is not None else [],
            )
        return r

    def mouseMoveEvent(self, event):
        if self._drag_mode is None:
            super().mouseMoveEvent(event)
            return
        delta = event.scenePos() - self._drag_start_scene
        r = QRectF(self._drag_start_rect)
        MIN = 5.0  # minimum width/height, mm
        active_edges = set()
        if self._drag_mode == 'move':
            r.translate(delta)
            active_edges = {'left', 'right', 'top', 'bottom'}
        else:
            _, dx, dy = self._drag_mode
            if dx < 0:
                new_left = min(r.right() - MIN, r.left() + delta.x())
                r.setLeft(new_left)
                active_edges.add('left')
            elif dx > 0:
                new_right = max(r.left() + MIN, r.right() + delta.x())
                r.setRight(new_right)
                active_edges.add('right')
            if dy < 0:
                new_top = min(r.bottom() - MIN, r.top() + delta.y())
                r.setTop(new_top)
                active_edges.add('top')
            elif dy > 0:
                new_bottom = max(r.top() + MIN, r.bottom() + delta.y())
                r.setBottom(new_bottom)
                active_edges.add('bottom')

        # Apply magnetic snapping
        r = self._snap_edges(r, active_edges)

        self.setRect(r)

        # Live-update the model so repaint reflects the new rect.
        scene = self.scene()
        if scene and hasattr(scene, '_export_region_live_update'):
            scene._export_region_live_update(self)
        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or self._drag_mode is None:
            super().mouseReleaseEvent(event)
            return
        self._drag_mode = None
        scene = self.scene()
        if scene and hasattr(scene, 'hide_snap_lines'):
            scene.hide_snap_lines()
        if scene and hasattr(scene, '_export_region_drag_finished'):
            scene._export_region_drag_finished(self)
        event.accept()

    def keyPressEvent(self, event):
        # Allow Delete/Backspace to clear the region.
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            scene = self.scene()
            if scene and hasattr(scene, '_export_region_clear_requested'):
                scene._export_region_clear_requested()
                event.accept()
                return
        super().keyPressEvent(event)
