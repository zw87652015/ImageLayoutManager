from PyQt6.QtWidgets import QGraphicsRectItem, QStyleOptionGraphicsItem, QGraphicsItem, QGraphicsTextItem
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QPixmap, QFont, QCursor
from PyQt6.QtCore import Qt, QRectF, QRect, QPointF, pyqtSignal, QVariantAnimation, QEasingCurve, QTimer

from src.model.enums import FitMode
from src.utils.image_proxy import get_image_proxy


class ResizeHandleItem(QGraphicsRectItem):
    """An 8-directional resize handle placed around a CellItem in freeform mode."""
    HANDLE_SIZE = 6.0  # scene units (mm)

    # Anchors: (col, row) each in {0=left/top, 1=center, 2=right/bottom}
    ANCHORS = [
        (0, 0), (1, 0), (2, 0),
        (0, 1),          (2, 1),
        (0, 2), (1, 2), (2, 2),
    ]
    CURSORS = [
        Qt.CursorShape.SizeFDiagCursor, Qt.CursorShape.SizeVerCursor,  Qt.CursorShape.SizeBDiagCursor,
        Qt.CursorShape.SizeHorCursor,                                   Qt.CursorShape.SizeHorCursor,
        Qt.CursorShape.SizeBDiagCursor, Qt.CursorShape.SizeVerCursor,  Qt.CursorShape.SizeFDiagCursor,
    ]

    def __init__(self, anchor_col, anchor_row, cell_item):
        super().__init__(cell_item)
        self.anchor_col = anchor_col
        self.anchor_row = anchor_row
        self.cell_item = cell_item
        self._dragging = False
        self._drag_start_scene = None
        self._drag_start_rect = None

        s = self.HANDLE_SIZE
        self.setRect(-s / 2, -s / 2, s, s)
        self.setBrush(QBrush(QColor("#007ACC")))
        self.setPen(QPen(Qt.PenStyle.NoPen))
        self.setZValue(1000)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, False)
        self.setAcceptHoverEvents(True)
        idx = self.ANCHORS.index((anchor_col, anchor_row))
        self.setCursor(self.CURSORS[idx])

    def update_position(self):
        r = self.cell_item.rect()
        xs = [r.left(), r.center().x(), r.right()]
        ys = [r.top(), r.center().y(), r.bottom()]
        self.setPos(xs[self.anchor_col], ys[self.anchor_row])

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_start_scene = event.scenePos()
            # Store the cell's bounding rect in SCENE coordinates at the start of the drag
            cell_pos = self.cell_item.pos()
            cell_rect = self.cell_item.rect()
            self._drag_start_rect = QRectF(
                cell_pos.x(), cell_pos.y(),
                cell_rect.width(), cell_rect.height()
            )
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not self._dragging:
            return
        delta = event.scenePos() - self._drag_start_scene
        # Work entirely in scene space from the original rect
        r = QRectF(self._drag_start_rect)
        dx, dy = delta.x(), delta.y()

        # Handle aspect ratio lock (Shift key or corners)
        # We always lock aspect ratio in freeform mode when resizing from corners
        # to ensure images don't get squished.
        is_corner = (self.anchor_col in [0, 2] and self.anchor_row in [0, 2])
        lock_aspect = is_corner or (event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        
        if lock_aspect and self._drag_start_rect.height() > 0:
            aspect = self._drag_start_rect.width() / self._drag_start_rect.height()
            
            # If dragging a corner, prioritize the larger movement to determine scale
            if is_corner:
                # Determine sign based on which corner is dragged
                sign_x = -1 if self.anchor_col == 0 else 1
                sign_y = -1 if self.anchor_row == 0 else 1
                
                # Effective delta taking direction into account
                eff_dx = dx * sign_x
                eff_dy = dy * sign_y
                
                # Use the axis with the largest proportional change
                if abs(eff_dx) > abs(eff_dy * aspect):
                    # X dominates, adjust Y
                    dy = (eff_dx / aspect) * sign_y
                else:
                    # Y dominates, adjust X
                    dx = (eff_dy * aspect) * sign_x
            else:
                # Dragging an edge, adjust the other axis
                if self.anchor_col != 1: # Dragging left/right edge
                    sign_y = 1 # Expand bottom by default
                    eff_dx = dx * (-1 if self.anchor_col == 0 else 1)
                    dy = (eff_dx / aspect) * sign_y
                    # When dragging edge with aspect lock, we need to artificially set anchor_row to apply the dy
                    temp_anchor_row = 2 
                elif self.anchor_row != 1: # Dragging top/bottom edge
                    sign_x = 1 # Expand right by default
                    eff_dy = dy * (-1 if self.anchor_row == 0 else 1)
                    dx = (eff_dy * aspect) * sign_x
                    temp_anchor_col = 2

        # Apply X changes
        active_col = self.anchor_col if not (lock_aspect and self.anchor_col == 1) else temp_anchor_col
        if active_col == 0:
            r.setLeft(r.left() + dx)
        elif active_col == 2:
            r.setRight(r.right() + dx)

        # Apply Y changes
        active_row = self.anchor_row if not (lock_aspect and self.anchor_row == 1) else temp_anchor_row
        if active_row == 0:
            r.setTop(r.top() + dy)
        elif active_row == 2:
            r.setBottom(r.bottom() + dy)

        # Minimum size: 2 scene units (mm)
        min_size = 2.0
        if r.width() < min_size:
            if active_col == 0:
                r.setLeft(r.right() - min_size)
            else:
                r.setRight(r.left() + min_size)
        if r.height() < min_size:
            if active_row == 0:
                r.setTop(r.bottom() - min_size)
            else:
                r.setBottom(r.top() + min_size)

        # Apply Snapping (disable snapping when aspect locked to avoid fighting the lock)
        if not lock_aspect:
            scene = self.scene()
            if scene and hasattr(scene, 'snap_rect'):
                # Build a rect matching exactly what is being dragged (only snap the active edge/corner)
                snap_r = QRectF(r)
                if active_col == 1: # Center horizontally -> no X snapping
                    snap_r.setLeft(r.center().x())
                    snap_r.setRight(r.center().x())
                if active_row == 1: # Center vertically -> no Y snapping
                    snap_r.setTop(r.center().y())
                    snap_r.setBottom(r.center().y())
                    
                sdx, sdy = scene.snap_rect(snap_r, self.cell_item.cell_id)
                
                if sdx != 0:
                    if active_col == 0:
                        r.setLeft(r.left() + sdx)
                    elif active_col == 2:
                        r.setRight(r.right() + sdx)
                if sdy != 0:
                    if active_row == 0:
                        r.setTop(r.top() + sdy)
                    elif active_row == 2:
                        r.setBottom(r.bottom() + sdy)

        # Re-check minimum size after snap
        if r.width() < min_size:
            if active_col == 0:
                r.setLeft(r.right() - min_size)
            else:
                r.setRight(r.left() + min_size)
        if r.height() < min_size:
            if active_row == 0:
                r.setTop(r.bottom() - min_size)
            else:
                r.setBottom(r.top() + min_size)

        # r.topLeft() is the new scene-space origin; rect is always (0,0,w,h)
        self.cell_item.setPos(r.topLeft())
        self.cell_item.setRect(QRectF(0, 0, r.width(), r.height()))
        self.cell_item._update_handle_positions()
        self.cell_item._reposition_labels_live()
        event.accept()

    def mouseReleaseEvent(self, event):
        if self._dragging and event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            scene = self.scene()
            if scene and hasattr(scene, 'hide_snap_lines'):
                scene.hide_snap_lines()
            self.cell_item._emit_freeform_geometry()
            event.accept()
        else:
            super().mouseReleaseEvent(event)

class CropHandleItem(QGraphicsItem):
    """PowerPoint-style L-bracket crop handle. Children of a CellItem."""

    ARM = 4.0    # arm length in scene mm
    THICK = 1.4  # line width in scene mm
    HIT = 1.5    # hit-test extension beyond visible arm

    ANCHORS = [
        (0, 0), (1, 0), (2, 0),
        (0, 1),          (2, 1),
        (0, 2), (1, 2), (2, 2),
    ]
    CURSORS = [
        Qt.CursorShape.SizeFDiagCursor, Qt.CursorShape.SizeVerCursor,  Qt.CursorShape.SizeBDiagCursor,
        Qt.CursorShape.SizeHorCursor,                                    Qt.CursorShape.SizeHorCursor,
        Qt.CursorShape.SizeBDiagCursor, Qt.CursorShape.SizeVerCursor,  Qt.CursorShape.SizeFDiagCursor,
    ]

    def __init__(self, anchor_col, anchor_row, cell_item):
        super().__init__(cell_item)
        self.anchor_col = anchor_col
        self.anchor_row = anchor_row
        self.cell_item = cell_item
        self._dragging = False
        self._drag_start_scene = None
        self._drag_start_crop = None

        self.setZValue(2000)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setAcceptHoverEvents(True)
        idx = self.ANCHORS.index((anchor_col, anchor_row))
        self.setCursor(self.CURSORS[idx])

    def _get_dims(self):
        """Calculate dynamic dimensions based on zoom and crop box size."""
        scale = self.cell_item._pip_scene_scale()
        # Target sizes in screen pixels
        arm_px = 18.0
        thick_px = 3.5
        hit_px = 6.0
        
        # Convert to scene units
        A = arm_px / max(scale, 0.01)
        T = thick_px / max(scale, 0.01)
        H = hit_px / max(scale, 0.01)
        
        # Safeguard: Ensure handles don't cover more than 30% of the crop area
        crop_rect = self.cell_item._get_crop_canvas_rect()
        if crop_rect and crop_rect.width() > 0 and crop_rect.height() > 0:
            max_arm = min(crop_rect.width(), crop_rect.height()) * 0.25
            A = min(A, max_arm)
        else:
            # Fallback if crop_rect is invalid or zero
            A = min(A, 2.0) 
            
        return A, T, H

    def boundingRect(self):
        A, _, H = self._get_dims()
        ac, ar = self.anchor_col, self.anchor_row
        
        # Each arm starts at (0,0) and extends inward along the crop border.
        if ac == 0:
            x_min, x_max = -H, A + H
        elif ac == 2:
            x_min, x_max = -(A + H), H
        else: # col 1 (middle)
            x_min, x_max = -(A * 0.5 + H), A * 0.5 + H
            
        if ar == 0:
            y_min, y_max = -H, A + H
        elif ar == 2:
            y_min, y_max = -(A + H), H
        else: # row 1 (middle)
            y_min, y_max = -(A * 0.5 + H), A * 0.5 + H
            
        return QRectF(x_min, y_min, x_max - x_min, y_max - y_min)

    def paint(self, painter: QPainter, option, widget):
        A, T, _ = self._get_dims()
        painter.save()
        
        # Set pen to dynamic thickness
        pen = QPen(QColor("#000000"))
        pen.setWidthF(T)
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        ac, ar = self.anchor_col, self.anchor_row

        # Corners: two perpendicular arms; edges: single bar
        if ac == 0 and ar == 0:   # top-left
            painter.drawLine(QPointF(0, 0), QPointF(A, 0))
            painter.drawLine(QPointF(0, 0), QPointF(0, A))
        elif ac == 1 and ar == 0: # top-center
            painter.drawLine(QPointF(-A * 0.5, 0), QPointF(A * 0.5, 0))
        elif ac == 2 and ar == 0: # top-right
            painter.drawLine(QPointF(0, 0), QPointF(-A, 0))
            painter.drawLine(QPointF(0, 0), QPointF(0, A))
        elif ac == 0 and ar == 1: # mid-left
            painter.drawLine(QPointF(0, -A * 0.5), QPointF(0, A * 0.5))
        elif ac == 2 and ar == 1: # mid-right
            painter.drawLine(QPointF(0, -A * 0.5), QPointF(0, A * 0.5))
        elif ac == 0 and ar == 2: # bottom-left
            painter.drawLine(QPointF(0, 0), QPointF(A, 0))
            painter.drawLine(QPointF(0, 0), QPointF(0, -A))
        elif ac == 1 and ar == 2: # bottom-center
            painter.drawLine(QPointF(-A * 0.5, 0), QPointF(A * 0.5, 0))
        elif ac == 2 and ar == 2: # bottom-right
            painter.drawLine(QPointF(0, 0), QPointF(-A, 0))
            painter.drawLine(QPointF(0, 0), QPointF(0, -A))

        painter.restore()

    def update_position(self):
        crop_rect = self.cell_item._get_crop_canvas_rect()
        if crop_rect is None:
            return
        xs = [crop_rect.left(), crop_rect.center().x(), crop_rect.right()]
        ys = [crop_rect.top(), crop_rect.center().y(), crop_rect.bottom()]
        self.setPos(xs[self.anchor_col], ys[self.anchor_row])

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_start_scene = event.scenePos()
            self._drag_start_crop = (
                self.cell_item.crop_left, self.cell_item.crop_top,
                self.cell_item.crop_right, self.cell_item.crop_bottom,
            )
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not self._dragging:
            return
        delta = event.scenePos() - self._drag_start_scene
        full_rect = self.cell_item._get_full_image_rect()
        if full_rect is None or full_rect.width() <= 0 or full_rect.height() <= 0:
            return

        dfx = delta.x() / full_rect.width()
        dfy = delta.y() / full_rect.height()

        cl, ct, cr, cb = self._drag_start_crop
        MIN_FRAC = 0.05

        is_corner = (self.anchor_col in [0, 2] and self.anchor_row in [0, 2])
        shift_held = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)

        if is_corner and shift_held:
            pix = self.cell_item._pixmap
            pix_w = pix.width() if pix and not pix.isNull() else 1
            pix_h = pix.height() if pix and not pix.isNull() else 1

            w0 = cr - cl
            h0 = cb - ct

            # Candidate new size from each axis independently (from drag origin)
            cand_w = max(MIN_FRAC, w0 - dfx if self.anchor_col == 0 else w0 + dfx)
            cand_h = max(MIN_FRAC, h0 - dfy if self.anchor_row == 0 else h0 + dfy)

            # Use the axis with the larger pixel displacement to drive the scale
            if abs(cand_w - w0) * pix_w >= abs(cand_h - h0) * pix_h:
                target_scale = cand_w / w0
            else:
                target_scale = cand_h / h0

            new_w = w0 * target_scale
            new_h = h0 * target_scale

            # Apply from the fixed (opposite) corner
            if self.anchor_col == 0:
                cl = max(0.0, cr - new_w)
            else:
                cr = min(1.0, cl + new_w)

            if self.anchor_row == 0:
                ct = max(0.0, cb - new_h)
            else:
                cb = min(1.0, ct + new_h)
        else:
            if self.anchor_col == 0:
                cl = max(0.0, min(cr - MIN_FRAC, cl + dfx))
            elif self.anchor_col == 2:
                cr = min(1.0, max(cl + MIN_FRAC, cr + dfx))

            if self.anchor_row == 0:
                ct = max(0.0, min(cb - MIN_FRAC, ct + dfy))
            elif self.anchor_row == 2:
                cb = min(1.0, max(ct + MIN_FRAC, cb + dfy))

        self.cell_item.crop_left = cl
        self.cell_item.crop_top = ct
        self.cell_item.crop_right = cr
        self.cell_item.crop_bottom = cb
        self.cell_item._update_crop_handle_positions()
        self.cell_item.update()
        event.accept()

    def mouseReleaseEvent(self, event):
        if self._dragging and event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            event.accept()
        else:
            super().mouseReleaseEvent(event)


class CellItem(QGraphicsRectItem):
    def __init__(self, cell_id: str, parent=None):
        super().__init__(parent)
        self.cell_id = cell_id
        # ... existing init code ...
        self.image_path = None
        self.fit_mode = FitMode.CONTAIN
        self.align_h = "center"  # left, center, right
        self.align_v = "center"  # top, center, bottom
        self.padding = (2, 2, 2, 2) # top, right, bottom, left
        self.rotation = 0
        self.is_placeholder = False
        
        # Nested layout
        self.nested_layout_path = None
        self._nested_pixmap = None  # cached thumbnail of nested layout

        # Label cell mode
        self.is_label_cell = False
        self.label_text = ""
        self.label_font_family = "Arial"
        self.label_font_size = 12
        self.label_font_weight = "bold"
        self.label_color = "#000000"
        self.label_align = "center"  # "left", "center", "right"
        self.label_offset_x = 0.0  # mm
        self.label_offset_y = 0.0  # mm
        
        # Scale bar properties
        self.scale_bar_enabled = False
        self.scale_bar_mode = "rgb"
        self.scale_bar_um_per_px = 0.1301
        self.scale_bar_length_um = 10.0
        self.scale_bar_color = "#FFFFFF"
        self.scale_bar_show_text = True
        self.scale_bar_thickness_mm = 0.5
        self.scale_bar_position = "bottom_right"
        self.scale_bar_offset_x = 2.0
        self.scale_bar_offset_y = 2.0
        self.scale_bar_custom_text = None
        self.scale_bar_text_size_mm = 2.0
        self.scale_bar_unit = "µm"
        
        # Visual settings
        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setAcceptDrops(True)
        
        self.proxy = get_image_proxy()
        self.proxy.thumbnail_ready.connect(self.on_thumbnail_ready)
        
        self._pixmap = None

        # Crop (normalized fractions 0.0–1.0 of original image, before rotation)
        self.crop_left = 0.0
        self.crop_top = 0.0
        self.crop_right = 1.0
        self.crop_bottom = 1.0

        # Crop mode state
        self._in_crop_mode = False
        self._crop_mode_start = (0.0, 0.0, 1.0, 1.0)
        self._crop_handles = []
        self._pre_crop_z = 0.0
        self._crop_pan_start = None  # (QPointF scene_pos, (cl, ct, cr, cb))

        # Style
        self.border_pen = QPen(QColor("#CCCCCC"))
        self.border_pen.setWidth(1)
        self.border_pen.setCosmetic(True)

        self.placeholder_pen = QPen(QColor("#AEAEB2"), 1, Qt.PenStyle.DashLine)
        self.placeholder_pen.setCosmetic(True)
        self.placeholder_pen.setDashPattern([4.0, 4.0])

        self.selected_pen = QPen(QColor("#0891B2"))
        self.selected_pen.setWidth(2)
        self.selected_pen.setCosmetic(True)

        self.hover_brush = QBrush(QColor(8, 145, 178, 25))
        self.normal_brush = QBrush(Qt.GlobalColor.white)
        self.placeholder_brush = QBrush(QColor("#F5F5F5"))
        
        self.is_hovered = False
        self._drag_start_pos = None
        self._freeform = False  # Whether this item is in freeform interactive mode
        self._resize_handles = []  # ResizeHandleItem instances

        # External file drag-over state (for PiP drop zone UI)
        self._ext_drag_active = False
        self._ext_drag_has_image = False  # True only if cell already has an image
        self._pip_zone_hovered = False
        self._pip_drop_indicator_t = 0.0  # 0.0 = replace border, 1.0 = PiP zone border
        self._pip_anim = None
        self._accent_color = "#0891B2"

        # PiP inset state
        self._pip_items = []          # list of PiPItem data objects
        self._selected_pip_id = None  # id of the currently selected PiP
        self._pip_resize_active = False  # True only when user explicitly enters resize mode
        self._pip_drag_mode = None    # "move"|"resize_nw"|…|"origin_move"|"origin_resize_nw"|…
        self._pip_drag_id = None      # id of the pip being dragged (separate from selection)
        self._pip_drag_start_item_pos = None
        self._pip_drag_old_geom = None   # (x, y, w, h) saved at drag start
        self._pip_drag_old_crop = None   # (cl, ct, cr, cb) saved at drag start

    # ---------- Freeform mode helpers ----------

    def set_freeform_mode(self, enabled: bool):
        """Enable/disable freeform drag-move and resize handles."""
        if self._freeform == enabled:
            return
        self._freeform = enabled
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, enabled and not self.is_label_cell)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, enabled)

        if enabled:
            for ac, ar in ResizeHandleItem.ANCHORS:
                handle = ResizeHandleItem(ac, ar, self)
                handle.setVisible(self.isSelected())
                self._resize_handles.append(handle)
            self._update_handle_positions()
        else:
            for h in self._resize_handles:
                if h.scene():
                    h.scene().removeItem(h)
            self._resize_handles.clear()

    def _update_handle_positions(self):
        for h in self._resize_handles:
            h.update_position()

    def _emit_freeform_geometry(self):
        """Notify the scene that this item's freeform geometry changed."""
        scene = self.scene()
        if scene and hasattr(scene, 'cell_freeform_geometry_changed'):
            pos = self.pos()
            rect = self.rect()
            scene.cell_freeform_geometry_changed.emit(
                self.cell_id, pos.x(), pos.y(), rect.width(), rect.height()
            )

    def itemChange(self, change, value):
        if (change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged
                and self._freeform and not self.is_label_cell):
            self._update_handle_positions()
            self._reposition_labels_live()
        elif change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            is_selected = bool(value)
            for h in self._resize_handles:
                h.setVisible(is_selected)
            if not is_selected and self._in_crop_mode:
                self.exit_crop_mode(commit=True)
        return super().itemChange(change, value)

    def _reposition_labels_live(self):
        """Move in-cell text labels together with the cell during freeform drag."""
        scene = self.scene()
        if scene and hasattr(scene, 'reposition_cell_text_items'):
            pos = self.pos()
            rect = self.rect()
            scene.reposition_cell_text_items(
                self.cell_id, pos.x(), pos.y(), rect.width(), rect.height()
            )

    # ---------- Crop mode ----------

    def enter_crop_mode(self):
        """Enter interactive crop mode (PowerPoint-style)."""
        if self._in_crop_mode or not self._pixmap or self._pixmap.isNull():
            return
        self._in_crop_mode = True
        self._crop_mode_start = (self.crop_left, self.crop_top, self.crop_right, self.crop_bottom)
        self._pre_crop_z = self.zValue()
        self.setZValue(300)
        scene = self.scene()
        if scene and hasattr(scene, 'show_crop_veil'):
            scene.show_crop_veil(self)
            views = scene.views()
            if views:
                QTimer.singleShot(0, views[0].setFocus)
        for ac, ar in CropHandleItem.ANCHORS:
            handle = CropHandleItem(ac, ar, self)
            self._crop_handles.append(handle)
        self._update_crop_handle_positions()
        self.update()

    def exit_crop_mode(self, commit=True):
        """Exit crop mode. If commit=False, restores the original crop."""
        if not self._in_crop_mode:
            return
        self._in_crop_mode = False
        self._crop_pan_start = None
        self.setZValue(self._pre_crop_z)
        self.unsetCursor()
        scene = self.scene()
        if scene and hasattr(scene, 'hide_crop_veil'):
            scene.hide_crop_veil()
        if not commit:
            self.crop_left, self.crop_top, self.crop_right, self.crop_bottom = self._crop_mode_start
        for h in self._crop_handles:
            h_scene = h.scene()
            if h_scene:
                h_scene.removeItem(h)
        self._crop_handles.clear()
        self.update()
        # Emit committed crop through the scene so main_window can undo/redo it
        new_crop = (self.crop_left, self.crop_top, self.crop_right, self.crop_bottom)
        if commit and new_crop != self._crop_mode_start:
            if scene and hasattr(scene, 'cell_crop_committed'):
                scene.cell_crop_committed.emit(
                    self.cell_id,
                    self.crop_left, self.crop_top,
                    self.crop_right, self.crop_bottom,
                )

    def _get_full_image_rect(self):
        """Item-local rect where the FULL (uncropped) image would be drawn."""
        if not self._pixmap or self._pixmap.isNull():
            return None
        rect = self.rect()
        content_rect = rect if self._freeform else rect.adjusted(
            self.padding[3], self.padding[0], -self.padding[1], -self.padding[2]
        )
        if content_rect.width() <= 0 or content_rect.height() <= 0:
            return None
        pix_w = self._pixmap.width()
        pix_h = self._pixmap.height()
        is_sideways = self.rotation in [90, 270]
        eff_w = pix_h if is_sideways else pix_w
        eff_h = pix_w if is_sideways else pix_h
        if self.fit_mode == FitMode.CONTAIN:
            ratio = min(content_rect.width() / eff_w, content_rect.height() / eff_h)
        else:
            ratio = max(content_rect.width() / eff_w, content_rect.height() / eff_h)
        new_w = eff_w * ratio
        new_h = eff_h * ratio
        x = content_rect.left() + (content_rect.width() - new_w) / 2
        y = content_rect.top() + (content_rect.height() - new_h) / 2
        return QRectF(x, y, new_w, new_h)

    def _get_crop_canvas_rect(self):
        """Item-local rect of the currently visible (cropped) region."""
        full = self._get_full_image_rect()
        if full is None:
            return None
        return QRectF(
            full.left() + self.crop_left * full.width(),
            full.top() + self.crop_top * full.height(),
            (self.crop_right - self.crop_left) * full.width(),
            (self.crop_bottom - self.crop_top) * full.height(),
        )

    def _update_crop_handle_positions(self):
        for h in self._crop_handles:
            h.update_position()

    def apply_crop_preset(self, aspect_w: float, aspect_h: float):
        """Crop to a given aspect ratio, centred on the current crop region."""
        if not self._pixmap or self._pixmap.isNull():
            return
        pix_w = self._pixmap.width()
        pix_h = self._pixmap.height()
        if pix_w <= 0 or pix_h <= 0:
            return
        # Current crop in pixel coords
        cur_w = (self.crop_right - self.crop_left) * pix_w
        cur_h = (self.crop_bottom - self.crop_top) * pix_h
        target_ratio = aspect_w / aspect_h
        if cur_w / cur_h > target_ratio:
            # Too wide — reduce width
            new_w = cur_h * target_ratio
            new_h = cur_h
        else:
            # Too tall — reduce height
            new_w = cur_w
            new_h = cur_w / target_ratio
        # Centre within current crop
        cx = (self.crop_left + self.crop_right) * 0.5
        cy = (self.crop_top + self.crop_bottom) * 0.5
        hw = (new_w / pix_w) * 0.5
        hh = (new_h / pix_h) * 0.5
        self.crop_left = max(0.0, cx - hw)
        self.crop_right = min(1.0, cx + hw)
        self.crop_top = max(0.0, cy - hh)
        self.crop_bottom = min(1.0, cy + hh)
        self._update_crop_handle_positions()
        self.update()

    def mouseReleaseEvent(self, event):
        if self._in_crop_mode:
            self._crop_pan_start = None
            event.accept()
            return
        # PiP drag release — emit undo signal
        drag_pip_id = self._pip_drag_id or self._selected_pip_id
        if self._pip_drag_mode and drag_pip_id and event.button() == Qt.MouseButton.LeftButton:
            pip = next((p for p in self._pip_items if p.id == drag_pip_id), None)
            scene = self.scene()
            if pip and scene:
                is_origin_drag = self._pip_drag_mode.startswith("origin_")
                if is_origin_drag:
                    new_crop = (pip.crop_left, pip.crop_top, pip.crop_right, pip.crop_bottom)
                    if new_crop != self._pip_drag_old_crop and hasattr(scene, 'pip_origin_changed'):
                        scene.pip_origin_changed.emit(self.cell_id, pip.id, self._pip_drag_old_crop, new_crop)
                else:
                    new_geom = (pip.x, pip.y, pip.w, pip.h)
                    if new_geom != self._pip_drag_old_geom and hasattr(scene, 'pip_geometry_changed'):
                        scene.pip_geometry_changed.emit(self.cell_id, pip.id, self._pip_drag_old_geom, new_geom)
            self._pip_drag_mode = None
            self._pip_drag_id = None
            self._pip_drag_start_item_pos = None
            self._pip_drag_old_geom = None
            self._pip_drag_old_crop = None
            event.accept()
            return

        was_moved = self._freeform and self._drag_start_pos is not None
        self._drag_start_pos = None
        super().mouseReleaseEvent(event)
        scene = self.scene()
        if scene and hasattr(scene, 'hide_snap_lines'):
            scene.hide_snap_lines()
        if was_moved:
            self._emit_freeform_geometry()

    def mouseDoubleClickEvent(self, event):
        if self.nested_layout_path and not self.is_label_cell:
            scene = self.scene()
            if scene and hasattr(scene, 'nested_layout_open_requested'):
                scene.nested_layout_open_requested.emit(self.cell_id, self.nested_layout_path)
                event.accept()
                return
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event):
        if self._in_crop_mode:
            if event.button() == Qt.MouseButton.LeftButton:
                crop_rect = self._get_crop_canvas_rect()
                if crop_rect and crop_rect.contains(event.pos()):
                    self._crop_pan_start = (
                        event.scenePos(),
                        (self.crop_left, self.crop_top, self.crop_right, self.crop_bottom),
                    )
            event.accept()
            return
        if self.is_label_cell:
            super().mousePressEvent(event)
            return

        # PiP interaction:
        #   - Click PiP body: select it (highlight) and start a move drag.
        #   - Resize handles only appear after "Resize" from context menu.
        #   - While resize mode active, clicking a handle starts a resize drag.
        #   - Clicking outside any PiP exits resize mode and deselects.
        if self._pip_items and event.button() == Qt.MouseButton.LeftButton:
            pip_id, mode = self._pip_hit_test(event.pos())
            if pip_id:
                pip = next((p for p in self._pip_items if p.id == pip_id), None)
                if pip:
                    if pip_id != self._selected_pip_id:
                        # Newly clicked PiP: select it, clear resize mode
                        self._selected_pip_id = pip_id
                        self._pip_resize_active = False
                        self.update()
                        scene = self.scene()
                        if scene and hasattr(scene, "selection_changed_custom"):
                            scene.selection_changed_custom.emit([self.cell_id, pip_id])
                        # mode here is always "move" since handles aren't shown yet
                        mode = "move"
                    # Ensure the parent CellItem is selected in the Qt scene so
                    # _on_selection_changed can find it via selectedItems() and
                    # read _selected_pip_id to populate the Inspector.
                    if not self.isSelected():
                        scene = self.scene()
                        if scene:
                            scene.clearSelection()
                        self.setSelected(True)
                    # mode may be a handle mode if resize is active
                    self._pip_drag_mode = mode
                    self._pip_drag_id = pip_id
                    self._pip_drag_start_item_pos = event.pos()
                    self._pip_drag_old_geom = (pip.x, pip.y, pip.w, pip.h)
                    self._pip_drag_old_crop = (pip.crop_left, pip.crop_top, pip.crop_right, pip.crop_bottom)
                event.accept()
                return
            elif self._selected_pip_id:
                # Clicked outside any PiP — exit resize mode and deselect
                self._selected_pip_id = None
                self._pip_resize_active = False
                self._pip_drag_mode = None
                self._pip_drag_id = None
                self.update()
                scene = self.scene()
                if scene and hasattr(scene, "selection_changed_custom"):
                    scene.selection_changed_custom.emit([self.cell_id])

        if event.button() == Qt.MouseButton.LeftButton:
            # Shift+Click: range select between last selected and this cell
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                scene = self.scene()
                if scene and hasattr(scene, 'cell_items'):
                    self._do_shift_select(scene)
                    event.accept()
                    return
            self._drag_start_pos = event.screenPos()
        elif event.button() == Qt.MouseButton.RightButton and self.isSelected():
            # Right-click on a cell that's already part of a (possibly multi-) selection:
            # do NOT delegate to super(), which would clear other selected items.
            # Accept the press so contextMenuEvent still fires with the full selection intact.
            event.accept()
            return
        super().mousePressEvent(event)

    def _do_shift_select(self, scene):
        """Select all cells between the last selected cell and this cell in row-major order."""
        from src.canvas.cell_item import CellItem
        # Get currently selected cell items (non-label)
        selected = [i for i in scene.selectedItems()
                    if isinstance(i, CellItem) and not i.is_label_cell]
        if not selected:
            self.setSelected(True)
            return

        # Build sorted list of all cell items by (row, col) from their cell_id
        all_items = sorted(
            [i for i in scene.cell_items.values() if not i.is_label_cell],
            key=lambda i: (i.pos().y(), i.pos().x())
        )
        id_to_idx = {i.cell_id: idx for idx, i in enumerate(all_items)}

        # Find the anchor (first selected) and this cell in the sorted order
        anchor_idx = id_to_idx.get(selected[0].cell_id, 0)
        this_idx = id_to_idx.get(self.cell_id, 0)

        lo, hi = min(anchor_idx, this_idx), max(anchor_idx, this_idx)

        # Select the range
        scene.clearSelection()
        for idx in range(lo, hi + 1):
            all_items[idx].setSelected(True)

    def mouseMoveEvent(self, event):
        if self._in_crop_mode:
            if self._crop_pan_start is not None:
                start_pos, (cl0, ct0, cr0, cb0) = self._crop_pan_start
                delta = event.scenePos() - start_pos
                full_rect = self._get_full_image_rect()
                if full_rect and full_rect.width() > 0 and full_rect.height() > 0:
                    dfx = delta.x() / full_rect.width()
                    dfy = delta.y() / full_rect.height()
                    w = cr0 - cl0
                    h = cb0 - ct0
                    new_cl = max(0.0, min(1.0 - w, cl0 + dfx))
                    new_ct = max(0.0, min(1.0 - h, ct0 + dfy))
                    self.crop_left = new_cl
                    self.crop_top = new_ct
                    self.crop_right = new_cl + w
                    self.crop_bottom = new_ct + h
                    self._update_crop_handle_positions()
                    self.update()
            event.accept()
            return
        if self.is_label_cell:
            event.ignore()
            return

        # PiP drag handling
        drag_pip_id = self._pip_drag_id or self._selected_pip_id
        if self._pip_drag_mode and drag_pip_id:
            pip = next((p for p in self._pip_items if p.id == drag_pip_id), None)
            if pip:
                self._apply_pip_drag(pip, event.pos())
                self.update()
                event.accept()
                return

        if self._drag_start_pos and not self._freeform:
            dist = (event.screenPos() - self._drag_start_pos).manhattanLength()
            if dist > 10: # Drag threshold
                scene = self.scene()
                if scene and hasattr(scene, 'drag_manager'):
                    scene.drag_manager.start_drag(self, event.scenePos())
                self._drag_start_pos = None
                return
        elif self._drag_start_pos and self._freeform:
            # We are dragging in freeform mode. Handle snapping.
            super().mouseMoveEvent(event) # Let QGraphicsItem update pos
            scene = self.scene()
            if scene and hasattr(scene, 'snap_rect'):
                r = QRectF(self.pos().x(), self.pos().y(), self.rect().width(), self.rect().height())
                dx, dy = scene.snap_rect(r, self.cell_id)
                if dx != 0 or dy != 0:
                    new_pos = QPointF(self.pos().x() + dx, self.pos().y() + dy)
                    self.setPos(new_pos)
            return
            
        super().mouseMoveEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            if self._pip_resize_active:
                # First Esc: exit resize mode but keep PiP selected
                self._pip_resize_active = False
                self._pip_drag_mode = None
                self._pip_drag_id = None
                self.update()
                event.accept()
                return
            if self._selected_pip_id:
                # Second Esc (or Esc when not in resize): deselect PiP
                self.deselect_pip()
                event.accept()
                return
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace) and self._selected_pip_id:
            scene = self.scene()
            if scene and hasattr(scene, 'pip_removed'):
                scene.pip_removed.emit(self.cell_id, self._selected_pip_id)
                event.accept()
                return
        super().keyPressEvent(event)

    def contextMenuEvent(self, event):
        scene = self.scene()
        if not scene:
            super().contextMenuEvent(event)
            return
        # Check if right-click landed on a PiP inset — show PiP menu, don't auto-select
        if self._pip_items and hasattr(scene, 'pip_context_menu'):
            pip_id, _ = self._pip_hit_test(event.pos())
            if pip_id:
                scene.pip_context_menu.emit(self.cell_id, pip_id, event.screenPos())
                event.accept()
                return
        if hasattr(scene, 'cell_context_menu'):
            scene.cell_context_menu.emit(self.cell_id, self.is_label_cell, event.screenPos())
            event.accept()
            return
        super().contextMenuEvent(event)

    def apply_theme_tokens(self, tokens: dict) -> None:
        """Recolour pens/brushes from design tokens. Called on theme switch."""
        self.border_pen.setColor(QColor(tokens.get("border", "#CCCCCC")))
        self.placeholder_pen.setColor(QColor(tokens.get("placeholder", "#AEAEB2")))
        self.selected_pen.setColor(QColor(tokens.get("accent", "#0891B2")))
        self.normal_brush.setColor(QColor(tokens.get("surface", "#FFFFFF")))
        accent = QColor(tokens.get("accent", "#0891B2"))
        self._accent_color = tokens.get("accent", "#0891B2")
        self.hover_brush.setColor(QColor(accent.red(), accent.green(), accent.blue(), 25))
        self.update()

    def update_data(self, image_path, fit_mode, padding, is_placeholder, rotation=0, align_h="center", align_v="center",
                     scale_bar_enabled: bool = False,
                     scale_bar_mode: str = "rgb",
                     scale_bar_um_per_px: float = 0.0,  # 0.0 means inherit from parent if zoom type
                     scale_bar_length_um: float = 10.0,
                     scale_bar_color="#FFFFFF", scale_bar_show_text=True, scale_bar_thickness_mm=0.5,
                     scale_bar_position="bottom_right", scale_bar_offset_x=2.0, scale_bar_offset_y=2.0,
                     scale_bar_custom_text=None, scale_bar_text_size_mm=2.0, scale_bar_unit="µm",
                     crop_left=0.0, crop_top=0.0, crop_right=1.0, crop_bottom=1.0):
        self.image_path = image_path
        self.fit_mode = FitMode(fit_mode)
        self.rotation = rotation
        self.align_h = align_h
        self.align_v = align_v
        self.padding = (padding['top'], padding['right'], padding['bottom'], padding['left'])
        self.is_placeholder = is_placeholder
        # Only update crop when not actively editing, to avoid fighting the user's drag
        if not self._in_crop_mode:
            self.crop_left = crop_left
            self.crop_top = crop_top
            self.crop_right = crop_right
            self.crop_bottom = crop_bottom
        
        # Scale bar
        self.scale_bar_enabled = scale_bar_enabled
        self.scale_bar_mode = scale_bar_mode
        self.scale_bar_um_per_px = scale_bar_um_per_px
        self.scale_bar_length_um = scale_bar_length_um
        self.scale_bar_color = scale_bar_color
        self.scale_bar_show_text = scale_bar_show_text
        self.scale_bar_thickness_mm = scale_bar_thickness_mm
        self.scale_bar_position = scale_bar_position
        self.scale_bar_offset_x = scale_bar_offset_x
        self.scale_bar_offset_y = scale_bar_offset_y
        self.scale_bar_custom_text = scale_bar_custom_text
        self.scale_bar_text_size_mm = scale_bar_text_size_mm
        self.scale_bar_unit = scale_bar_unit
        
        if self.image_path:
            import os
            if os.path.exists(self.image_path):
                self._pixmap = self.proxy.get_pixmap(self.image_path)
            else:
                self._pixmap = None
        else:
            self._pixmap = None
            
        self.update()

    def on_thumbnail_ready(self, path):
        if path == self.image_path:
            import os
            if os.path.exists(path):
                self._pixmap = self.proxy.get_pixmap(path)
                self.update()

    # ── PiP inset support ────────────────────────────────────────────────────

    def update_pip_items(self, pip_items):
        self._pip_items = list(pip_items)
        if self._selected_pip_id and not any(p.id == self._selected_pip_id for p in self._pip_items):
            self._selected_pip_id = None
            self._pip_resize_active = False
            self._pip_drag_mode = None
            self._pip_drag_id = None
        self.update()

    def select_pip(self, pip_id: str, resize: bool = False):
        """Select a PiP inset.
        resize=False (default): highlight + move only, no resize handles.
        resize=True: also show resize handles (called from context menu)."""
        changed = pip_id != self._selected_pip_id
        self._selected_pip_id = pip_id
        if resize:
            self._pip_resize_active = True
        elif changed:
            self._pip_resize_active = False
        self.update()
        scene = self.scene()
        if scene and hasattr(scene, "selection_changed_custom"):
            scene.selection_changed_custom.emit([self.cell_id, pip_id])

    def deselect_pip(self):
        """Deselect the currently selected PiP inset."""
        if self._selected_pip_id is not None:
            self._selected_pip_id = None
            self._pip_resize_active = False
            self._pip_drag_mode = None
            self._pip_drag_id = None
            self.update()
            scene = self.scene()
            if scene and hasattr(scene, "selection_changed_custom"):
                scene.selection_changed_custom.emit([self.cell_id])

    def _pip_content_rect(self) -> QRectF:
        """The cell content area where PiP positions are relative to."""
        r = self.rect()
        return r if self._freeform else r.adjusted(
            self.padding[3], self.padding[0], -self.padding[1], -self.padding[2]
        )

    def _pip_inset_rect(self, pip, content_rect: QRectF) -> QRectF:
        cr = content_rect
        return QRectF(
            cr.x() + pip.x * cr.width(),
            cr.y() + pip.y * cr.height(),
            pip.w * cr.width(),
            pip.h * cr.height(),
        )

    def _get_pip_intrinsic_aspect_ratio(self, pip) -> float:
        """Return the physical aspect ratio (W/H) of the PiP image content."""
        import os
        if pip.pip_type == "external":
            if pip.image_path and os.path.exists(pip.image_path):
                # Try cache
                pix = self.proxy.get_pixmap(pip.image_path)
                if pix and not pix.isNull():
                    return pix.width() / pix.height()
                # Fallback to PIL
                try:
                    from PIL import Image
                    with Image.open(pip.image_path) as img:
                        return img.width / img.height
                except:
                    pass
        elif pip.pip_type == "zoom":
            if self._pixmap and not self._pixmap.isNull():
                img_w = self._pixmap.width()
                img_h = self._pixmap.height()
                crop_w = max(0.001, pip.crop_right - pip.crop_left)
                crop_h = max(0.001, pip.crop_bottom - pip.crop_top)
                return (crop_w * img_w) / (crop_h * img_h) if crop_h > 0 and img_h > 0 else 1.0
        return 1.0

    def _sync_pip_height_from_width(self, pip, content_rect: QRectF):
        """Update pip.h to match pip.w based on intrinsic aspect ratio."""
        R = self._get_pip_intrinsic_aspect_ratio(pip)
        if R <= 0 or content_rect.width() <= 0 or content_rect.height() <= 0:
            return
        # R = (w * cw) / (h * ch)  =>  h = (w * cw) / (R * ch)
        cw, ch = content_rect.width(), content_rect.height()
        pip.h = (pip.w * cw) / (R * ch)

    def _pip_origin_rect(self, pip, content_rect: QRectF) -> QRectF:
        """Origin box on parent image (zoom type only), in item coords."""
        cr = content_rect
        return QRectF(
            cr.x() + pip.crop_left * cr.width(),
            cr.y() + pip.crop_top * cr.height(),
            (pip.crop_right - pip.crop_left) * cr.width(),
            (pip.crop_bottom - pip.crop_top) * cr.height(),
        )

    def _pip_handle_rects(self, inset_rect: QRectF, scene_scale: float = 1.0, hit: bool = False):
        """Return dict of mode -> QRectF for the 8 resize handles (item coords).
        scene_scale is device-pixels-per-scene-unit so handles stay a fixed pixel size.
        hit=True returns a larger grab area (8 device-px radius) for reliable mouse picking."""
        r = inset_rect
        cx, cy = r.center().x(), r.center().y()
        draw_px = 5.0
        hit_px  = 16.0  # generous grab radius
        s = (hit_px if hit else draw_px) / max(scene_scale, 0.01)
        positions = {
            "resize_nw": QPointF(r.left(), r.top()),
            "resize_n":  QPointF(cx, r.top()),
            "resize_ne": QPointF(r.right(), r.top()),
            "resize_e":  QPointF(r.right(), cy),
            "resize_se": QPointF(r.right(), r.bottom()),
            "resize_s":  QPointF(cx, r.bottom()),
            "resize_sw": QPointF(r.left(), r.bottom()),
            "resize_w":  QPointF(r.left(), cy),
        }
        return {k: QRectF(p.x() - s, p.y() - s, s * 2, s * 2) for k, p in positions.items()}

    def _pip_origin_handle_rects(self, origin_rect: QRectF, scene_scale: float = 1.0, hit: bool = False):
        """Return dict of mode -> QRectF for the 4 origin box corner handles (item coords)."""
        r = origin_rect
        s = (8.0 if hit else 4.0) / max(scene_scale, 0.01)
        return {
            "origin_resize_nw": QRectF(r.left() - s, r.top() - s, s * 2, s * 2),
            "origin_resize_ne": QRectF(r.right() - s, r.top() - s, s * 2, s * 2),
            "origin_resize_sw": QRectF(r.left() - s, r.bottom() - s, s * 2, s * 2),
            "origin_resize_se": QRectF(r.right() - s, r.bottom() - s, s * 2, s * 2),
        }

    def _pip_scene_scale(self) -> float:
        """Current device-pixels-per-scene-unit (zoom level) for fixed-pixel handle sizing."""
        scene = self.scene()
        if scene:
            views = scene.views()
            if views:
                return views[0].transform().m11()
        return 1.0

    def _pip_hit_test(self, item_pos: QPointF):
        """Returns (pip_id, drag_mode) or (None, None).
        Handles are prioritized over PiP bodies to ensure reliable resizing."""
        cr = self._pip_content_rect()
        scale = self._pip_scene_scale()
        
        # Pass 1: Check handles of the SELECTED PiP (highest priority)
        if self._selected_pip_id and self._pip_resize_active:
            pip = next((p for p in self._pip_items if p.id == self._selected_pip_id), None)
            if pip:
                inset_rect = self._pip_inset_rect(pip, cr)
                # Resize handles
                for mode, hrect in self._pip_handle_rects(inset_rect, scale, hit=True).items():
                    if hrect.contains(item_pos):
                        return pip.id, mode
                # Origin box handles (zoom type only)
                if pip.pip_type == "zoom" and pip.show_origin_box:
                    origin_rect = self._pip_origin_rect(pip, cr)
                    for mode, hrect in self._pip_origin_handle_rects(origin_rect, scale, hit=True).items():
                        if hrect.contains(item_pos):
                            return pip.id, mode
                    if origin_rect.contains(item_pos):
                        return pip.id, "origin_move"

        # Pass 2: Check bodies of all PiPs (Z-order picks topmost first)
        for pip in reversed(self._pip_items):
            inset_rect = self._pip_inset_rect(pip, cr)
            if inset_rect.contains(item_pos):
                return pip.id, "move"
        return None, None

    def _draw_pip_items(self, painter: QPainter, rect: QRectF):
        import os
        cr = self._pip_content_rect()
        scale = painter.transform().m11()
        for pip in self._pip_items:
            inset_rect = self._pip_inset_rect(pip, cr)
            is_sel = pip.id == self._selected_pip_id

            # Draw origin box (zoom type)
            if pip.pip_type == "zoom" and pip.show_origin_box:
                origin_rect = self._pip_origin_rect(pip, cr)
                pen = QPen(QColor(pip.origin_box_color))
                # Convert points to mm (canvas units are mm)
                pen.setWidthF(pip.origin_box_width_pt * (25.4 / 72.0))
                pen.setCosmetic(False)
                if pip.origin_box_style == "dashed":
                    pen.setStyle(Qt.PenStyle.DashLine)
                else:
                    pen.setStyle(Qt.PenStyle.SolidLine)
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(origin_rect)

            # Draw inset image
            painter.save()
            painter.setClipRect(inset_rect)
            if pip.pip_type == "zoom" and self._pixmap and not self._pixmap.isNull():
                img_w, img_h = self._pixmap.width(), self._pixmap.height()
                src_rect = QRectF(
                    pip.crop_left * img_w,
                    pip.crop_top * img_h,
                    (pip.crop_right - pip.crop_left) * img_w,
                    (pip.crop_bottom - pip.crop_top) * img_h
                )
                # Use containment logic to ensure tight wrapping even if inset_rect is off by a hair
                if src_rect.width() > 0 and src_rect.height() > 0:
                    ratio = min(inset_rect.width() / src_rect.width(), inset_rect.height() / src_rect.height())
                    dw = src_rect.width() * ratio
                    dh = src_rect.height() * ratio
                    dest = QRectF(
                        inset_rect.x() + (inset_rect.width() - dw) / 2,
                        inset_rect.y() + (inset_rect.height() - dh) / 2,
                        dw, dh
                    )
                    painter.drawPixmap(dest, self._pixmap, src_rect)
            elif pip.pip_type == "external" and pip.image_path:
                ext_pix = self.proxy.get_pixmap(pip.image_path) if os.path.exists(pip.image_path) else None
                if ext_pix and not ext_pix.isNull():
                    ratio = min(inset_rect.width() / ext_pix.width(), inset_rect.height() / ext_pix.height())
                    dw = ext_pix.width() * ratio
                    dh = ext_pix.height() * ratio
                    dest = QRectF(
                        inset_rect.x() + (inset_rect.width() - dw) / 2,
                        inset_rect.y() + (inset_rect.height() - dh) / 2,
                        dw, dh,
                    )
                    painter.drawPixmap(dest, ext_pix, QRectF(ext_pix.rect()))
            painter.restore()

            # Draw inset border
            if pip.border_enabled:
                bpen = QPen(QColor(pip.border_color))
                # Convert points to mm
                bpen.setWidthF(pip.border_width_pt * (25.4 / 72.0))
                bpen.setCosmetic(False)
                if getattr(pip, "border_style", "solid") == "dashed":
                    bpen.setStyle(Qt.PenStyle.DashLine)
                else:
                    bpen.setStyle(Qt.PenStyle.SolidLine)
                painter.setPen(bpen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(inset_rect)

            # Draw PiP scale bar if enabled
            pip_params = self._get_scale_bar_params(pip)
            if pip_params["enabled"]:
                # If it's a zoom PiP, it should inherit um_per_px from parent if not set
                if pip.pip_type == "zoom" and pip_params["um_per_px"] <= 0:
                    pip_params["um_per_px"] = self.scale_bar_um_per_px
                
                # If still 0, use legacy default
                if pip_params["um_per_px"] <= 0:
                    pip_params["um_per_px"] = 0.1301
                
                # Determine the image path and crop for scale calculation
                pip_path = pip.image_path if pip.pip_type == "external" else self.image_path
                
                # For zoom type, use the PiP's crop. For external, usually full image.
                if pip.pip_type == "zoom":
                    pip_crop = (pip.crop_left, pip.crop_top, pip.crop_right, pip.crop_bottom)
                    pip_fit = "stretch"  # Zoom PiPs are stretched to the inset rect
                else:
                    pip_crop = (0, 0, 1, 1)
                    pip_fit = FitMode.CONTAIN # External PiPs use CONTAIN
                
                # Draw scale bar relative to the inset
                self._draw_scale_bar_logic(painter, inset_rect, pip_params, pip_path, pip_crop, 0, pip_fit)

            # Draw selection highlight; resize handles only when resize mode is active
            if is_sel:
                self._draw_pip_selection_highlight(painter, inset_rect)
                if self._pip_resize_active:
                    self._draw_pip_selection_handles(painter, inset_rect, scale)
                    if pip.pip_type == "zoom" and pip.show_origin_box:
                        origin_rect = self._pip_origin_rect(pip, cr)
                        self._draw_pip_origin_handles(painter, origin_rect, scale)

    def _draw_pip_selection_highlight(self, painter: QPainter, inset_rect: QRectF):
        """Draw a dashed accent border around the selected PiP (no handles)."""
        painter.save()
        accent = QColor(self._accent_color)
        sel_pen = QPen(accent)
        sel_pen.setCosmetic(True)
        sel_pen.setWidthF(1.5)
        sel_pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(sel_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(inset_rect)
        painter.restore()

    def _draw_pip_selection_handles(self, painter: QPainter, inset_rect: QRectF, scale: float = 1.0):
        """Draw resize handles (only when resize mode is active)."""
        painter.save()
        accent = QColor(self._accent_color)
        # Draw handles in device space for zoom-independent fixed pixel size
        transform = painter.transform()
        painter.resetTransform()
        bpen = QPen(accent)
        bpen.setWidthF(1.0)
        for hrect in self._pip_handle_rects(inset_rect, scale, hit=False).values():
            dev_rect = transform.mapRect(hrect)
            painter.fillRect(dev_rect, QColor("#FFFFFF"))
            painter.setPen(bpen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(dev_rect)
        painter.restore()

    def _draw_pip_origin_handles(self, painter: QPainter, origin_rect: QRectF, scale: float = 1.0):
        painter.save()
        orange = QColor("#FF9500")
        transform = painter.transform()
        painter.resetTransform()
        for hrect in self._pip_origin_handle_rects(origin_rect, scale).values():
            painter.fillRect(transform.mapRect(hrect), orange)
        painter.restore()

    def _apply_pip_drag(self, pip, item_pos: QPointF):
        """Update pip geometry in-place based on current drag position."""
        cr = self._pip_content_rect()
        if cr.width() <= 0 or cr.height() <= 0:
            return
        start = self._pip_drag_start_item_pos
        dx_norm = (item_pos.x() - start.x()) / cr.width()
        dy_norm = (item_pos.y() - start.y()) / cr.height()
        MIN_SIZE = 0.05

        mode = self._pip_drag_mode
        ox, oy, ow, oh = self._pip_drag_old_geom

        if mode == "move":
            new_x = max(0.0, min(1.0 - ow, ox + dx_norm))
            new_y = max(0.0, min(1.0 - oh, oy + dy_norm))
            pip.x, pip.y = new_x, new_y
        elif mode.startswith("resize_"):
            dir_part = mode.split("_")[1] if "_" in mode else ""
            R = self._get_pip_intrinsic_aspect_ratio(pip)
            cw, ch = cr.width(), cr.height()
            
            w, h = ow, oh
            if "w" in dir_part:
                w = max(MIN_SIZE, ow - dx_norm)
            elif "e" in dir_part:
                w = max(MIN_SIZE, ow + dx_norm)
            
            if "n" in dir_part:
                h = max(MIN_SIZE, oh - dy_norm)
            elif "s" in dir_part:
                h = max(MIN_SIZE, oh + dy_norm)
                
            # Enforce aspect ratio lock R = (w*cw) / (h*ch)
            if len(dir_part) == 2: # Corner
                if abs(w - ow)/max(0.001, ow) > abs(h - oh)/max(0.001, oh):
                    h = (w * cw) / (R * ch) if ch > 0 and R > 0 else oh
                else:
                    w = (h * ch * R) / cw if cw > 0 else ow
            elif dir_part in ("e", "w"):
                h = (w * cw) / (R * ch) if ch > 0 and R > 0 else oh
            elif dir_part in ("n", "s"):
                w = (h * ch * R) / cw if cw > 0 else ow
            
            x, y = ox, oy
            if "w" in dir_part:
                x = ox + ow - w
            if "n" in dir_part:
                y = oy + oh - h
            
            pip.x, pip.y, pip.w, pip.h = x, y, w, h
        elif mode == "origin_move":
            ocl, oct, ocr, ocb = self._pip_drag_old_crop
            ow_crop = ocr - ocl
            oh_crop = ocb - oct
            new_cl = max(0.0, min(1.0 - ow_crop, ocl + dx_norm))
            new_ct = max(0.0, min(1.0 - oh_crop, oct + dy_norm))
            pip.crop_left = new_cl
            pip.crop_top = new_ct
            pip.crop_right = new_cl + ow_crop
            pip.crop_bottom = new_ct + oh_crop
            self._sync_pip_height_from_width(pip, cr)
        elif mode.startswith("origin_resize_"):
            ocl, oct, ocr, ocb = self._pip_drag_old_crop
            MIN_CROP = 0.05
            dir_part = mode.split("_")[-1] if "_" in mode else ""
            if "w" in dir_part:
                pip.crop_left = max(0.0, min(ocr - MIN_CROP, ocl + dx_norm))
            elif "e" in dir_part:
                pip.crop_right = min(1.0, max(ocl + MIN_CROP, ocr + dx_norm))
            if "n" in dir_part:
                pip.crop_top = max(0.0, min(ocb - MIN_CROP, oct + dy_norm))
            elif "s" in dir_part:
                pip.crop_bottom = min(1.0, max(oct + MIN_CROP, ocb + dy_norm))
            self._sync_pip_height_from_width(pip, cr)

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget):
        # Draw background
        rect = self.rect()
        
        if self.is_label_cell:
            self._draw_label_cell(painter, rect)
            return
        
        if self.is_placeholder:
            painter.fillRect(rect, self.placeholder_brush)
        else:
            painter.fillRect(rect, self.normal_brush)
            
        if self.is_hovered:
            painter.fillRect(rect, self.hover_brush)
            
        # Draw nested layout or image
        import os
        if self.nested_layout_path:
            self._draw_nested_layout(painter, rect)
        elif self.image_path and not os.path.exists(self.image_path) and not self.is_placeholder:
             self._draw_missing_file_icon(painter, rect)
        elif self._pixmap and not self._pixmap.isNull():
            self._draw_image(painter, rect)
        elif self.is_placeholder:
            self._draw_placeholder_icon(painter, rect)

        # Draw PiP insets
        if self._pip_items:
            self._draw_pip_items(painter, rect)

        # Draw Scale Bar (if enabled and has image)
        if self.scale_bar_enabled and self._pixmap and not self._pixmap.isNull():
            self._draw_scale_bar(painter, rect)

        # Draw PiP drop zone during external file drag
        if self._ext_drag_active:
            self._draw_pip_drop_zone(painter, rect)

        # Draw Size Group badge (small color chip in top-left corner).
        # Suppressed in preview/export.
        scene = self.scene()
        if scene and not getattr(scene, 'preview_mode', False):
            project = getattr(scene, 'project', None)
            if project is not None:
                cell = project.find_cell_by_id(self.cell_id)
                gid = getattr(cell, 'size_group_id', None) if cell else None
                if gid:
                    self._draw_size_group_badge(painter, rect, gid)

        # Draw Border (suppressed in preview mode)
        if not (scene and getattr(scene, 'preview_mode', False)):
            if self.isSelected():
                glow_color = QColor(self.selected_pen.color())
                glow_color.setAlpha(55)
                glow_pen = QPen(glow_color)
                glow_pen.setCosmetic(True)
                glow_pen.setWidth(5)
                painter.setPen(glow_pen)
                painter.drawRect(rect)
                painter.setPen(self.selected_pen)
                painter.drawRect(rect)
            elif self.is_placeholder:
                painter.setPen(self.placeholder_pen)
                painter.drawRect(rect)
            else:
                painter.setPen(self.border_pen)
                painter.drawRect(rect)

    def _draw_size_group_badge(self, painter: QPainter, rect: QRectF, group_id: str):
        """Draw a small color-coded chip in the top-left of the cell indicating group membership."""
        # Hash group id -> HSL hue for stable per-group color
        h = abs(hash(group_id)) % 360
        color = QColor.fromHsl(h, 180, 150)

        # Work in device pixels so the badge size is consistent regardless of zoom
        transform = painter.transform()
        m = transform.m11()
        if m <= 0:
            return
        scene = self.scene()
        project = getattr(scene, 'project', None) if scene else None
        group = project.find_size_group(group_id) if project else None
        label = (group.name if group else "G")[:3]

        # Badge rect: ~12x12 device px, top-left with small margin
        size_px = 14
        pad_px = 4
        dev_rect = transform.mapRect(rect)

        badge_rect = QRectF(
            dev_rect.left() + pad_px,
            dev_rect.top() + pad_px,
            size_px * max(1.0, len(label) * 0.7),
            size_px,
        )

        painter.save()
        painter.resetTransform()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        # Filled rounded rect
        painter.setBrush(color)
        painter.setPen(QPen(QColor(0, 0, 0, 140), 1))
        painter.drawRoundedRect(badge_rect, 3, 3)
        # Group name text (first 3 chars)
        font = QFont("Arial")
        font.setPixelSize(max(8, size_px - 4))
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QPen(QColor("#FFFFFF")))
        painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, label)
        painter.restore()

    def _draw_label_cell(self, painter: QPainter, rect: QRectF):
        """Draw a label-only cell with centered text."""
        painter.fillRect(rect, self.normal_brush)
        scene = self.scene()
        if not (scene and getattr(scene, 'preview_mode', False)):
            painter.setPen(self.border_pen)
            painter.drawRect(rect)
        
        if self.label_text:
            # QGraphicsTextItem uses 72 DPI internally, so 1pt = 1 scene unit.
            # To match TextGraphicsItem rendering, use font_size_pt directly
            # as the scene-coordinate size (not pt-to-mm converted).
            font_size_scene = self.label_font_size  # 1pt = 1 scene unit
            transform = painter.transform()
            m11 = transform.m11()  # device pixels per scene unit (includes zoom)

            # Map rect and offsets to device pixels
            dev_rect = transform.mapRect(rect)
            dev_ox = self.label_offset_x * m11
            dev_oy = self.label_offset_y * abs(transform.m22())
            dev_text_rect = dev_rect.adjusted(dev_ox, dev_oy, dev_ox, dev_oy)

            device_font_size = max(1, int(font_size_scene * m11))
            font = QFont(self.label_font_family)
            font.setPixelSize(device_font_size)
            if self.label_font_weight == "bold":
                font.setBold(True)

            painter.save()
            painter.resetTransform()
            painter.setFont(font)
            painter.setPen(QPen(QColor(self.label_color)))
            h_align = Qt.AlignmentFlag.AlignHCenter
            if self.label_align == "left":
                h_align = Qt.AlignmentFlag.AlignLeft
            elif self.label_align == "right":
                h_align = Qt.AlignmentFlag.AlignRight
            painter.drawText(dev_text_rect, h_align | Qt.AlignmentFlag.AlignVCenter, self.label_text)
            painter.restore()
            
    def set_nested_layout(self, path):
        """Set the nested layout path and generate a thumbnail."""
        if path == self.nested_layout_path and self._nested_pixmap is not None:
            return
        self.nested_layout_path = path
        self._nested_pixmap = None
        if path:
            self._generate_nested_thumbnail()
        self.update()

    def _generate_nested_thumbnail(self):
        """Render the nested layout to a QPixmap thumbnail for canvas display."""
        import os
        if not self.nested_layout_path or not os.path.exists(self.nested_layout_path):
            self._nested_pixmap = None
            return
        try:
            from src.model.data_model import Project
            from src.model.layout_engine import LayoutEngine
            from src.export.image_exporter import ImageExporter

            sub_project = Project.load_from_file(self.nested_layout_path)
            # Render at a moderate resolution for preview (screen DPI)
            preview_dpi = 150
            orig_dpi = sub_project.dpi
            sub_project.dpi = preview_dpi
            qimage = ImageExporter.render_to_qimage(sub_project)
            sub_project.dpi = orig_dpi
            if qimage and not qimage.isNull():
                self._nested_pixmap = QPixmap.fromImage(qimage)
            else:
                self._nested_pixmap = None
        except Exception as e:
            print(f"Failed to generate nested layout thumbnail: {e}")
            self._nested_pixmap = None

    def _draw_nested_layout(self, painter: QPainter, rect: QRectF):
        """Draw the nested layout thumbnail inside the cell."""
        content_rect = rect.adjusted(
            self.padding[3], self.padding[0],
            -self.padding[1], -self.padding[2]
        )
        if content_rect.width() <= 0 or content_rect.height() <= 0:
            return

        if self._nested_pixmap and not self._nested_pixmap.isNull():
            pix_w = self._nested_pixmap.width()
            pix_h = self._nested_pixmap.height()
            ratio = min(content_rect.width() / pix_w, content_rect.height() / pix_h)
            new_w = pix_w * ratio
            new_h = pix_h * ratio
            x = content_rect.left() + (content_rect.width() - new_w) / 2
            y = content_rect.top() + (content_rect.height() - new_h) / 2
            target = QRectF(x, y, new_w, new_h)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            painter.drawPixmap(target.toRect(), self._nested_pixmap)
        else:
            # Fallback: draw a badge indicating nested layout
            painter.setPen(QPen(QColor("#888888")))
            painter.drawText(content_rect, Qt.AlignmentFlag.AlignCenter, "Nested Layout\n(not found)")

        # Draw a small badge in the top-right corner
        import os
        badge_text = os.path.basename(self.nested_layout_path) if self.nested_layout_path else ""
        if badge_text:
            transform = painter.transform()
            m11 = transform.m11()
            badge_font = QFont("Arial")
            badge_font.setPixelSize(max(1, int(2.5 * m11)))
            dev_rect = transform.mapRect(rect)

            painter.save()
            painter.resetTransform()
            painter.setFont(badge_font)

            fm = painter.fontMetrics()
            text_w = fm.horizontalAdvance(badge_text) + 6
            text_h = fm.height() + 2
            badge_rect = QRectF(
                dev_rect.right() - text_w - 2,
                dev_rect.top() + 2,
                text_w, text_h
            )
            painter.fillRect(badge_rect, QColor(0, 0, 0, 140))
            painter.setPen(QPen(QColor("#FFFFFF")))
            painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, badge_text)
            painter.restore()

    def _draw_missing_file_icon(self, painter: QPainter, rect: QRectF):
        # Draw red cross or "Missing" text
        painter.setPen(QPen(QColor("#FF4444"), 2))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "Image Not Found")
        
        # Red border
        pen = QPen(QColor("#FF4444"))
        pen.setWidth(2)
        pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.drawRect(rect)

    def _draw_image(self, painter: QPainter, rect: QRectF):
        content_rect = rect if self._freeform else rect.adjusted(
            self.padding[3], self.padding[0], -self.padding[1], -self.padding[2]
        )
        if content_rect.width() <= 0 or content_rect.height() <= 0:
            return

        if self._in_crop_mode:
            self._draw_image_crop_mode(painter, content_rect)
            return

        pix_w = self._pixmap.width()
        pix_h = self._pixmap.height()

        # Crop source rect (in pixmap pixel coords)
        src_x = self.crop_left * pix_w
        src_y = self.crop_top * pix_h
        src_w = max(1.0, (self.crop_right - self.crop_left) * pix_w)
        src_h = max(1.0, (self.crop_bottom - self.crop_top) * pix_h)
        src_rect = QRectF(src_x, src_y, src_w, src_h)

        # Effective pixel dimensions after crop (and rotation)
        is_sideways = self.rotation in [90, 270]
        eff_pix_w = src_h if is_sideways else src_w
        eff_pix_h = src_w if is_sideways else src_h

        if self.fit_mode == FitMode.CONTAIN:
            ratio = min(content_rect.width() / eff_pix_w, content_rect.height() / eff_pix_h)
            new_w = eff_pix_w * ratio
            new_h = eff_pix_h * ratio
            if self.align_h == "left":
                x = content_rect.left()
            elif self.align_h == "right":
                x = content_rect.right() - new_w
            else:
                x = content_rect.left() + (content_rect.width() - new_w) / 2
            if self.align_v == "top":
                y = content_rect.top()
            elif self.align_v == "bottom":
                y = content_rect.bottom() - new_h
            else:
                y = content_rect.top() + (content_rect.height() - new_h) / 2
            target_rect = QRectF(x, y, new_w, new_h)
        else:  # COVER
            ratio = max(content_rect.width() / eff_pix_w, content_rect.height() / eff_pix_h)
            new_w = eff_pix_w * ratio
            new_h = eff_pix_h * ratio
            x = content_rect.left() + (content_rect.width() - new_w) / 2
            y = content_rect.top() + (content_rect.height() - new_h) / 2
            target_rect = QRectF(x, y, new_w, new_h)
            painter.setClipRect(content_rect)

        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        if self.rotation != 0:
            painter.save()
            painter.translate(target_rect.center())
            painter.rotate(self.rotation)
            draw_rect = QRectF(-src_w * ratio / 2, -src_h * ratio / 2, src_w * ratio, src_h * ratio)
            painter.drawPixmap(draw_rect.toRect(), self._pixmap, src_rect.toRect())
            painter.restore()
        else:
            painter.drawPixmap(target_rect.toRect(), self._pixmap, src_rect.toRect())

        painter.setClipping(False)

    def _draw_image_crop_mode(self, painter: QPainter, content_rect: QRectF):
        """Crop-edit display: full image with dark ghost on the trimmed areas."""
        pix_w = self._pixmap.width()
        pix_h = self._pixmap.height()
        is_sideways = self.rotation in [90, 270]
        eff_w = pix_h if is_sideways else pix_w
        eff_h = pix_w if is_sideways else pix_h

        if self.fit_mode == FitMode.CONTAIN:
            ratio = min(content_rect.width() / eff_w, content_rect.height() / eff_h)
        else:
            ratio = max(content_rect.width() / eff_w, content_rect.height() / eff_h)

        new_w = eff_w * ratio
        new_h = eff_h * ratio
        x = content_rect.left() + (content_rect.width() - new_w) / 2
        y = content_rect.top() + (content_rect.height() - new_h) / 2
        full_rect = QRectF(x, y, new_w, new_h)

        painter.save()
        if self.fit_mode == FitMode.COVER:
            painter.setClipRect(content_rect)

        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        # Draw the full (uncropped) image
        if self.rotation != 0:
            painter.save()
            painter.translate(full_rect.center())
            painter.rotate(self.rotation)
            draw_rect = QRectF(-pix_w * ratio / 2, -pix_h * ratio / 2, pix_w * ratio, pix_h * ratio)
            painter.drawPixmap(draw_rect.toRect(), self._pixmap)
            painter.restore()
        else:
            painter.drawPixmap(full_rect.toRect(), self._pixmap)

        # Ghost overlay outside the crop window (within the image area)
        crop_rect = QRectF(
            full_rect.left() + self.crop_left * full_rect.width(),
            full_rect.top() + self.crop_top * full_rect.height(),
            (self.crop_right - self.crop_left) * full_rect.width(),
            (self.crop_bottom - self.crop_top) * full_rect.height(),
        )
        ghost = QColor(0, 0, 0, 130)
        painter.setClipRect(full_rect)
        # Top
        if crop_rect.top() > full_rect.top():
            painter.fillRect(QRectF(full_rect.left(), full_rect.top(),
                                    full_rect.width(), crop_rect.top() - full_rect.top()), ghost)
        # Bottom
        if crop_rect.bottom() < full_rect.bottom():
            painter.fillRect(QRectF(full_rect.left(), crop_rect.bottom(),
                                    full_rect.width(), full_rect.bottom() - crop_rect.bottom()), ghost)
        # Left (middle band)
        if crop_rect.left() > full_rect.left():
            painter.fillRect(QRectF(full_rect.left(), crop_rect.top(),
                                    crop_rect.left() - full_rect.left(), crop_rect.height()), ghost)
        # Right (middle band)
        if crop_rect.right() < full_rect.right():
            painter.fillRect(QRectF(crop_rect.right(), crop_rect.top(),
                                    full_rect.right() - crop_rect.right(), crop_rect.height()), ghost)

        painter.restore()

    def _draw_placeholder_icon(self, painter: QPainter, rect: QRectF):
        # Scale elements based on cell size for proper display at all dimensions
        min_dimension = min(rect.width(), rect.height())
        
        # Scale the + mark size (20% of smaller dimension, clamped between 10 and 40)
        s = max(10, min(40, min_dimension * 0.2))
        
        # Scale line width (proportional to mark size, clamped between 1 and 4)
        line_width = max(1, min(4, s / 10))
        
        painter.setPen(QPen(QColor("#AAAAAA"), line_width))
        c = rect.center()
        painter.drawLine(int(c.x() - s), int(c.y()), int(c.x() + s), int(c.y()))
        painter.drawLine(int(c.x()), int(c.y() - s), int(c.x()), int(c.y() + s))
        
        # Draw text "Drop Image Here" with dynamic font size
        painter.setPen(QPen(QColor("#888888")))
        font = painter.font()
        
        # Calculate font size based on cell dimensions (8% of smaller dimension, clamped between 8 and 16)
        font_size = max(8, min(16, int(min_dimension * 0.08)))
        font.setPointSize(font_size)
        painter.setFont(font)
        
        # Position text with padding from bottom
        text_rect = rect.adjusted(5, 0, -5, -s * 1.5)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignBottom, "Drop Image Here")

    def _get_scale_bar_params(self, obj):
        """Helper to get scale bar params from either a CellItem or a PiPItem-like dict/object."""
        return {
            "enabled": getattr(obj, "scale_bar_enabled", False),
            "um_per_px": getattr(obj, "scale_bar_um_per_px", 0.1301),
            "length_um": getattr(obj, "scale_bar_length_um", 10.0),
            "unit": getattr(obj, "scale_bar_unit", "µm"),
            "color": getattr(obj, "scale_bar_color", "#FFFFFF"),
            "show_text": getattr(obj, "scale_bar_show_text", True),
            "custom_text": getattr(obj, "scale_bar_custom_text", None),
            "text_size_mm": getattr(obj, "scale_bar_text_size_mm", 2.0),
            "thickness_mm": getattr(obj, "scale_bar_thickness_mm", 0.5),
            "position": getattr(obj, "scale_bar_position", "bottom_right"),
            "offset_x": getattr(obj, "scale_bar_offset_x", 2.0),
            "offset_y": getattr(obj, "scale_bar_offset_y", 2.0),
        }

    def _draw_scale_bar_logic(self, painter: QPainter, rect: QRectF, params: dict, 
                              img_path: str, crop: tuple, rotation: int, fit_mode, padding: tuple = (0,0,0,0)):
        """Shared logic for scale bar rendering. 
        fit_mode can be FitMode instance or "stretch".
        """
        if not params["enabled"]:
            return

        # Calculate content rect (inside padding)
        content_rect = rect.adjusted(
            padding[3], padding[0], 
            -padding[1], -padding[2]
        )
        
        if content_rect.width() <= 0 or content_rect.height() <= 0:
            return
        
        # µm per pixel
        um_per_px = params["um_per_px"] if params["um_per_px"] > 0 else 0.1301
        
        # Calculate bar length in pixels (source image pixels)
        bar_length_px = params["length_um"] / um_per_px
        
        # Get ORIGINAL image dimensions
        from PIL import Image
        import os
        try:
            if img_path and os.path.exists(img_path):
                with Image.open(img_path) as img:
                    orig_w, orig_h = img.size
            else:
                # Fallback to a placeholder size if image missing
                orig_w, orig_h = 1000, 1000
        except Exception:
            orig_w, orig_h = 1000, 1000
        
        # Apply crop
        cl, ct, cr, cb = crop
        crop_w_frac = max(0.001, cr - cl)
        crop_h_frac = max(0.001, cb - ct)
        eff_orig_w = orig_w * crop_w_frac
        eff_orig_h = orig_h * crop_h_frac

        # Adjust dimensions if rotated
        is_sideways = rotation in [90, 270]
        eff_pix_w = eff_orig_h if is_sideways else eff_orig_w
        eff_pix_h = eff_orig_w if is_sideways else eff_orig_h

        # Calculate actual image rectangle and scale factor
        # Safety: avoid division by zero or extreme overflows for tiny crops
        safe_pix_w = max(0.1, eff_pix_w)
        safe_pix_h = max(0.1, eff_pix_h)

        if fit_mode == "stretch":
            scale_ratio = content_rect.width() / safe_pix_w
            img_rect = content_rect
        elif fit_mode == FitMode.CONTAIN:
            scale_ratio = min(content_rect.width() / safe_pix_w, content_rect.height() / safe_pix_h)
            new_w = eff_pix_w * scale_ratio
            new_h = eff_pix_h * scale_ratio
            img_rect = QRectF(
                content_rect.left() + (content_rect.width() - new_w) / 2,
                content_rect.top() + (content_rect.height() - new_h) / 2,
                new_w, new_h
            )
        else:  # COVER
            scale_ratio = max(content_rect.width() / safe_pix_w, content_rect.height() / safe_pix_h)
            new_w = eff_pix_w * scale_ratio
            new_h = eff_pix_h * scale_ratio
            img_rect = QRectF(
                content_rect.left() + (content_rect.width() - new_w) / 2,
                content_rect.top() + (content_rect.height() - new_h) / 2,
                new_w, new_h
            )
        
        # Clamp scale ratio to avoid extreme bar lengths that could crash renderer
        scale_ratio = min(scale_ratio, 100000.0)
        
        # Bar length in mm
        bar_length_mm = bar_length_px * scale_ratio
        bar_thickness = params["thickness_mm"]
        
        ox, oy = params["offset_x"], params["offset_y"]
        bar_y = img_rect.bottom() - oy - bar_thickness
        
        if params["position"] == "bottom_left":
            bar_x = img_rect.left() + ox
        elif params["position"] == "bottom_center":
            bar_x = img_rect.left() + (img_rect.width() - bar_length_mm) / 2
        else:  # bottom_right
            bar_x = img_rect.right() - ox - bar_length_mm
        
        # Draw the bar
        painter.fillRect(QRectF(bar_x, bar_y, bar_length_mm, bar_thickness), QColor(params["color"]))
        
        # Draw text
        if params["show_text"]:
            if params["custom_text"]:
                text = params["custom_text"]
            else:
                unit = params["unit"]
                factor = {"m": 1e6, "cm": 1e4, "dm": 1e5, "mm": 1e3, "µm": 1.0, "nm": 1e-3, "pm": 1e-6, "fm": 1e-9}.get(unit, 1.0)
                display_val = params["length_um"] / factor
                text = f"{display_val:.0f} {unit}" if display_val >= 1 or display_val == 0 else f"{display_val:.2f} {unit}"

            base_pt = 24
            text_scale = params["text_size_mm"] / base_pt

            temp_item = QGraphicsTextItem()
            temp_item.setPlainText(text)
            temp_item.setFont(QFont("Arial", base_pt))
            temp_item.setDefaultTextColor(QColor(params["color"]))

            br = temp_item.boundingRect()
            tw_mm = br.width() * text_scale
            th_mm = br.height() * text_scale

            tx = bar_x + (bar_length_mm - tw_mm) / 2
            ty = bar_y - th_mm

            painter.save()
            painter.translate(tx, ty)
            painter.scale(text_scale, text_scale)
            option = QStyleOptionGraphicsItem()
            temp_item.paint(painter, option, None)
            painter.restore()

    def _draw_scale_bar(self, painter: QPainter, rect: QRectF):
        """Draw scale bar on the main image."""
        params = self._get_scale_bar_params(self)
        crop = (self.crop_left, self.crop_top, self.crop_right, self.crop_bottom)
        self._draw_scale_bar_logic(painter, rect, params, self.image_path, crop, self.rotation, self.fit_mode, self.padding)

    def _update_tooltip(self):
        """Build tooltip from image metadata."""
        import os
        if self.is_label_cell:
            self.setToolTip(f"Label: {self.label_text}" if self.label_text else "Label Cell")
            return
        if self.nested_layout_path:
            name = os.path.basename(self.nested_layout_path) if self.nested_layout_path else ""
            self.setToolTip(f"Nested Layout: {name}")
            return
        if not self.image_path or self.is_placeholder:
            self.setToolTip("")
            return
        try:
            name = os.path.basename(self.image_path)
            parts = [name]
            if self._pixmap and not self._pixmap.isNull():
                parts.append(f"{self._pixmap.width()}×{self._pixmap.height()} px")
            if os.path.exists(self.image_path):
                size_bytes = os.path.getsize(self.image_path)
                if size_bytes >= 1_048_576:
                    parts.append(f"{size_bytes / 1_048_576:.1f} MB")
                else:
                    parts.append(f"{size_bytes / 1024:.0f} KB")
            self.setToolTip("\n".join(parts))
        except Exception:
            self.setToolTip("")

    # ---------- External file drag / PiP drop zone ----------

    def _pip_zone_rect(self) -> QRectF:
        """Top-right corner zone — releasing here creates a PiP inset instead of replacing."""
        r = self.rect()
        zone_w = max(r.width() * 0.30, 10.0)
        zone_h = max(r.height() * 0.22, 6.0)
        margin = 1.5
        return QRectF(r.right() - zone_w - margin, r.top() + margin, zone_w, zone_h)

    def begin_ext_drag(self, has_image: bool):
        """Called by CanvasScene when an external image file starts hovering over this cell."""
        self._ext_drag_active = True
        self._ext_drag_has_image = has_image
        self._pip_zone_hovered = False
        self._pip_drop_indicator_t = 0.0
        self.update()

    def end_ext_drag(self):
        """Called by CanvasScene when the external drag leaves or is dropped."""
        self._ext_drag_active = False
        self._ext_drag_has_image = False
        self._pip_zone_hovered = False
        if self._pip_anim is not None:
            self._pip_anim.stop()
            self._pip_anim = None
        self._pip_drop_indicator_t = 0.0
        self.update()

    def update_ext_drag_pos(self, item_pos: QPointF):
        """Update cursor position during an external drag to switch the indicator target."""
        if not self._ext_drag_active or not self._ext_drag_has_image:
            return
        in_pip = self._pip_zone_rect().contains(item_pos)
        if in_pip != self._pip_zone_hovered:
            self._pip_zone_hovered = in_pip
            self._animate_pip_indicator(to_pip=in_pip)

    def _animate_pip_indicator(self, to_pip: bool):
        if self._pip_anim is not None:
            self._pip_anim.stop()
        anim = QVariantAnimation()
        anim.setStartValue(float(self._pip_drop_indicator_t))
        anim.setEndValue(1.0 if to_pip else 0.0)
        anim.setDuration(160)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.valueChanged.connect(self._on_pip_anim_value)
        anim.start()
        self._pip_anim = anim

    def _on_pip_anim_value(self, value):
        self._pip_drop_indicator_t = float(value)
        self.update()

    def is_pip_drop_zone(self, item_pos: QPointF) -> bool:
        """Return True if item_pos is inside the PiP drop zone and the cell has an image."""
        return self._ext_drag_has_image and self._pip_zone_rect().contains(item_pos)

    def _draw_pip_drop_zone(self, painter: QPainter, rect: QRectF):
        """Draw the PiP zone hint and animated drop indicator during an external file drag."""
        pip_zone = self._pip_zone_rect()

        # --- PiP zone: semi-transparent dark background + dashed white border ---
        painter.save()
        transform = painter.transform()
        m11 = transform.m11()
        dev_pip = transform.mapRect(pip_zone)
        dev_rect = transform.mapRect(rect)

        painter.resetTransform()

        # Background fill
        bg_color = QColor(0, 0, 0, 140) if self._pip_zone_hovered else QColor(0, 0, 0, 90)
        painter.fillRect(dev_pip, bg_color)

        # Dashed border around PiP zone
        dash_pen = QPen(QColor(255, 255, 255, 200), 1.0)
        dash_pen.setStyle(Qt.PenStyle.DashLine)
        dash_pen.setDashPattern([4.0, 3.0])
        painter.setPen(dash_pen)
        painter.drawRect(dev_pip.adjusted(0.5, 0.5, -0.5, -0.5))

        # "PiP / 以子图插入" label
        font = QFont()
        font.setPixelSize(max(7, int(2.8 * m11)))
        font.setBold(True)
        painter.setFont(font)
        text_color = QColor(255, 255, 255, 230) if self._pip_zone_hovered else QColor(255, 255, 255, 170)
        painter.setPen(QPen(text_color))
        from src.app.i18n import tr
        painter.drawText(dev_pip, Qt.AlignmentFlag.AlignCenter, tr("pip_zone_label"))

        # --- Animated accent-color indicator border ---
        t = self._pip_drop_indicator_t
        # Interpolate rect from full cell → PiP zone (device pixel coords)
        ind_left   = dev_rect.left()   + (dev_pip.left()   - dev_rect.left())   * t
        ind_top    = dev_rect.top()    + (dev_pip.top()    - dev_rect.top())    * t
        ind_right  = dev_rect.right()  + (dev_pip.right()  - dev_rect.right())  * t
        ind_bottom = dev_rect.bottom() + (dev_pip.bottom() - dev_rect.bottom()) * t
        ind_rect = QRectF(ind_left, ind_top, ind_right - ind_left, ind_bottom - ind_top)

        accent = QColor(self._accent_color)
        accent_pen = QPen(accent, 2.5)
        accent_pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
        painter.setPen(accent_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(ind_rect.adjusted(1, 1, -1, -1))

        painter.restore()

    def boundingRect(self) -> QRectF:
        """Extend bounding box to include PiP resize handles that might stick out."""
        r = self.rect()
        if self._selected_pip_id and self._pip_resize_active:
            scale = self._pip_scene_scale()
            # Grab radius in mm (scene units). Needs to be >= hit_px in _pip_handle_rects
            s = 20.0 / max(scale, 0.01)
            return r.adjusted(-s, -s, s, s)
        return r

    def hoverEnterEvent(self, event):
        self.is_hovered = True
        self._update_tooltip()
        self.update()
        super().hoverEnterEvent(event)

    def hoverMoveEvent(self, event):
        # 1. Crop mode cursor logic
        if self._in_crop_mode:
            crop_rect = self._get_crop_canvas_rect()
            if crop_rect and crop_rect.contains(event.pos()):
                self.setCursor(Qt.CursorShape.SizeAllCursor)
            else:
                self.unsetCursor()
            super().hoverMoveEvent(event)
            return

        # 2. PiP handle cursor logic
        if self._selected_pip_id and self._pip_resize_active:
            _, mode = self._pip_hit_test(event.pos())
            if mode:
                cursors = {
                    "resize_nw": Qt.CursorShape.SizeFDiagCursor,
                    "resize_n":  Qt.CursorShape.SizeVerCursor,
                    "resize_ne": Qt.CursorShape.SizeBDiagCursor,
                    "resize_e":  Qt.CursorShape.SizeHorCursor,
                    "resize_se": Qt.CursorShape.SizeFDiagCursor,
                    "resize_s":  Qt.CursorShape.SizeVerCursor,
                    "resize_sw": Qt.CursorShape.SizeBDiagCursor,
                    "resize_w":  Qt.CursorShape.SizeHorCursor,
                    "origin_resize_nw": Qt.CursorShape.SizeFDiagCursor,
                    "origin_resize_ne": Qt.CursorShape.SizeBDiagCursor,
                    "origin_resize_sw": Qt.CursorShape.SizeBDiagCursor,
                    "origin_resize_se": Qt.CursorShape.SizeFDiagCursor,
                    "origin_move": Qt.CursorShape.SizeAllCursor,
                }
                if mode in cursors:
                    self.setCursor(cursors[mode])
                    super().hoverMoveEvent(event)
                    return
        
        # 3. Default cursor
        self.unsetCursor()
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event):
        self.is_hovered = False
        if self._in_crop_mode:
            self.unsetCursor()
        self.update()
        super().hoverLeaveEvent(event)
