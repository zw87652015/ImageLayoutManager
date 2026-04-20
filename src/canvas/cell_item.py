from PyQt6.QtWidgets import QGraphicsRectItem, QStyleOptionGraphicsItem, QGraphicsItem, QGraphicsTextItem
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QPixmap, QFont, QCursor
from PyQt6.QtCore import Qt, QRectF, QPointF, pyqtSignal

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
        
        # Visual settings
        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setAcceptDrops(True)
        
        self.proxy = get_image_proxy()
        self.proxy.thumbnail_ready.connect(self.on_thumbnail_ready)
        
        self._pixmap = None
        
        # Style
        self.border_pen = QPen(QColor("#CCCCCC"))
        self.border_pen.setWidth(1)
        self.border_pen.setCosmetic(True) # Width stays constant on zoom
        
        self.selected_pen = QPen(QColor("#007ACC"))
        self.selected_pen.setWidth(2)
        self.selected_pen.setCosmetic(True)
        
        self.hover_brush = QBrush(QColor(0, 122, 204, 30))
        self.normal_brush = QBrush(Qt.GlobalColor.white)
        self.placeholder_brush = QBrush(QColor("#F0F0F0"))
        
        self.is_hovered = False
        self._drag_start_pos = None
        self._freeform = False  # Whether this item is in freeform interactive mode
        self._resize_handles = []  # ResizeHandleItem instances

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

    def mouseReleaseEvent(self, event):
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
        if self.is_label_cell:
            super().mousePressEvent(event)
            return
        if event.button() == Qt.MouseButton.LeftButton:
            # Shift+Click: range select between last selected and this cell
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                scene = self.scene()
                if scene and hasattr(scene, 'cell_items'):
                    self._do_shift_select(scene)
                    event.accept()
                    return
            self._drag_start_pos = event.screenPos()
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
        if self.is_label_cell:
            event.ignore()
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

    def contextMenuEvent(self, event):
        scene = self.scene()
        if scene and hasattr(scene, 'cell_context_menu'):
            scene.cell_context_menu.emit(self.cell_id, self.is_label_cell, event.screenPos())
            event.accept()
            return
        super().contextMenuEvent(event)

    def update_data(self, image_path, fit_mode, padding, is_placeholder, rotation=0, align_h="center", align_v="center",
                     scale_bar_enabled=False, scale_bar_mode="rgb", scale_bar_um_per_px=0.1301, scale_bar_length_um=10.0,
                     scale_bar_color="#FFFFFF", scale_bar_show_text=True, scale_bar_thickness_mm=0.5,
                     scale_bar_position="bottom_right", scale_bar_offset_x=2.0, scale_bar_offset_y=2.0,
                     scale_bar_custom_text=None, scale_bar_text_size_mm=2.0):
        self.image_path = image_path
        self.fit_mode = FitMode(fit_mode)
        self.rotation = rotation
        self.align_h = align_h
        self.align_v = align_v
        self.padding = (padding['top'], padding['right'], padding['bottom'], padding['left'])
        self.is_placeholder = is_placeholder
        
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

        # Draw Scale Bar (if enabled and has image)
        if self.scale_bar_enabled and self._pixmap and not self._pixmap.isNull():
            self._draw_scale_bar(painter, rect)

        # Draw Border (suppressed in preview mode)
        scene = self.scene()
        if not (scene and getattr(scene, 'preview_mode', False)):
            if self.isSelected():
                painter.setPen(self.selected_pen)
                painter.drawRect(rect)
            else:
                painter.setPen(self.border_pen)
                painter.drawRect(rect)

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
        # Calculate content rect with padding (ignore padding in freeform mode)
        if self._freeform:
            content_rect = rect
        else:
            content_rect = rect.adjusted(
                self.padding[3], self.padding[0], 
                -self.padding[1], -self.padding[2]
            )
        
        if content_rect.width() <= 0 or content_rect.height() <= 0:
            return

        pix_w = self._pixmap.width()
        pix_h = self._pixmap.height()

        # Adjust dimensions if rotated 90 or 270 degrees
        is_sideways = self.rotation in [90, 270]
        eff_pix_w = pix_h if is_sideways else pix_w
        eff_pix_h = pix_w if is_sideways else pix_h
        
        target_rect = QRectF()
        
        if self.fit_mode == FitMode.CONTAIN:
            # Aspect ratio scaling
            ratio = min(content_rect.width() / eff_pix_w, content_rect.height() / eff_pix_h)
            new_w = eff_pix_w * ratio
            new_h = eff_pix_h * ratio
            
            # Alignment
            if self.align_h == "left":
                x = content_rect.left()
            elif self.align_h == "right":
                x = content_rect.right() - new_w
            else:  # center
                x = content_rect.left() + (content_rect.width() - new_w) / 2
            
            if self.align_v == "top":
                y = content_rect.top()
            elif self.align_v == "bottom":
                y = content_rect.bottom() - new_h
            else:  # center
                y = content_rect.top() + (content_rect.height() - new_h) / 2
            
            target_rect = QRectF(x, y, new_w, new_h)
            
        elif self.fit_mode == FitMode.COVER:
            # Aspect ratio scaling to fill
            ratio = max(content_rect.width() / eff_pix_w, content_rect.height() / eff_pix_h)
            new_w = eff_pix_w * ratio
            new_h = eff_pix_h * ratio
            
            # Center and clip
            x = content_rect.left() + (content_rect.width() - new_w) / 2
            y = content_rect.top() + (content_rect.height() - new_h) / 2
            
            target_rect = QRectF(x, y, new_w, new_h)
            painter.setClipRect(content_rect)
            
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        
        # Apply rotation
        if self.rotation != 0:
            painter.save()
            painter.translate(target_rect.center())
            painter.rotate(self.rotation)
            # When rotated, target_rect needs to be relative to the new origin (center)
            # The pixmap itself always has pix_w x pix_h
            rotated_draw_rect = QRectF(-pix_w * ratio / 2, -pix_h * ratio / 2, pix_w * ratio, pix_h * ratio)
            painter.drawPixmap(rotated_draw_rect.toRect(), self._pixmap)
            painter.restore()
        else:
            painter.drawPixmap(target_rect.toRect(), self._pixmap)
            
        painter.setClipping(False)

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

    def _draw_scale_bar(self, painter: QPainter, rect: QRectF):
        """Draw scale bar on the image."""
        # Calculate content rect (inside padding)
        content_rect = rect.adjusted(
            self.padding[3], self.padding[0], 
            -self.padding[1], -self.padding[2]
        )
        
        if content_rect.width() <= 0 or content_rect.height() <= 0:
            return
        
        # µm per pixel — value stored on the cell (set by the user via the inspector)
        um_per_px = self.scale_bar_um_per_px if self.scale_bar_um_per_px > 0 else 0.1301
        
        # Calculate bar length in pixels (source image pixels)
        bar_length_px = self.scale_bar_length_um / um_per_px
        
        # Get ORIGINAL image dimensions (not thumbnail) for accurate scale calculation
        from PIL import Image
        try:
            with Image.open(self.image_path) as img:
                orig_w, orig_h = img.size
        except Exception:
            # Fallback to pixmap if PIL fails
            orig_w = self._pixmap.width()
            orig_h = self._pixmap.height()
        
        # Adjust dimensions if rotated 90 or 270 degrees
        is_sideways = self.rotation in [90, 270]
        eff_pix_w = orig_h if is_sideways else orig_w
        eff_pix_h = orig_w if is_sideways else orig_h

        if self.fit_mode == FitMode.CONTAIN:
            scale_ratio = min(content_rect.width() / eff_pix_w, content_rect.height() / eff_pix_h)
        else:  # COVER
            scale_ratio = max(content_rect.width() / eff_pix_w, content_rect.height() / eff_pix_h)
        
        # Bar length in mm (canvas units)
        bar_length_mm = bar_length_px * scale_ratio
        
        # Bar thickness in mm
        bar_thickness = self.scale_bar_thickness_mm
        
        # Calculate position based on scale_bar_position and offsets
        ox = self.scale_bar_offset_x
        oy = self.scale_bar_offset_y
        
        # Y position (always at bottom)
        bar_y = content_rect.bottom() - oy - bar_thickness
        
        # X position based on horizontal alignment
        if self.scale_bar_position == "bottom_left":
            bar_x = content_rect.left() + ox
        elif self.scale_bar_position == "bottom_center":
            bar_x = content_rect.left() + (content_rect.width() - bar_length_mm) / 2
        else:  # bottom_right
            bar_x = content_rect.right() - ox - bar_length_mm
        
        # Draw the bar
        bar_rect = QRectF(bar_x, bar_y, bar_length_mm, bar_thickness)
        painter.fillRect(bar_rect, QColor(self.scale_bar_color))
        
        # Draw text if enabled
        if self.scale_bar_show_text:
            # Use custom text if provided, otherwise auto-generate from length
            if self.scale_bar_custom_text:
                text = self.scale_bar_custom_text
            else:
                text = f"{self.scale_bar_length_um:.0f} µm" if self.scale_bar_length_um >= 1 else f"{self.scale_bar_length_um:.2f} µm"

            # Render via QGraphicsTextItem at a large base point size and then
            # scale DOWN to the target mm size. This matches how labels render
            # in the exporters and avoids Qt's minimum-rendered-pixel-size floor
            # (~6-8 px) that would otherwise make the small scale-bar text
            # appear oversized relative to the bar at normal zoom levels.
            base_pt = 24
            text_scale = self.scale_bar_text_size_mm / base_pt

            temp_item = QGraphicsTextItem()
            temp_item.setPlainText(text)
            font = QFont("Arial", base_pt)
            temp_item.setFont(font)
            temp_item.setDefaultTextColor(QColor(self.scale_bar_color))

            br = temp_item.boundingRect()
            tw_mm = br.width() * text_scale
            th_mm = br.height() * text_scale

            # Horizontally centre the text on the bar; sit it just above the bar.
            tx_mm = bar_x + (bar_length_mm - tw_mm) / 2
            ty_mm = bar_y - th_mm

            painter.save()
            painter.translate(tx_mm, ty_mm)
            painter.scale(text_scale, text_scale)
            option = QStyleOptionGraphicsItem()
            temp_item.paint(painter, option, None)
            painter.restore()

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

    def hoverEnterEvent(self, event):
        self.is_hovered = True
        self._update_tooltip()
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.is_hovered = False
        self.update()
        super().hoverLeaveEvent(event)
