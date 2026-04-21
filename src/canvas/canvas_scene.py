from PyQt6.QtWidgets import QGraphicsScene, QGraphicsSceneDragDropEvent
from PyQt6.QtGui import QColor, QPen, QBrush, QPainter
from PyQt6.QtCore import Qt, pyqtSignal, QRectF

from src.model.data_model import Project, Cell
from src.canvas.cell_item import CellItem
from src.canvas.text_graphics_item import TextGraphicsItem
from src.model.layout_engine import LayoutEngine
from src.canvas.drag_manager import DragManager
from src.canvas.add_button_item import AddButtonItem
from src.canvas.divider_item import DividerItem, HIT_THICKNESS
from src.canvas.export_region_item import ExportRegionItem

class CanvasScene(QGraphicsScene):
    # Signals
    cell_dropped = pyqtSignal(str, str) # cell_id, file_path
    pip_image_dropped = pyqtSignal(str, str) # cell_id, file_path (drop landed in PiP zone)
    cell_swapped = pyqtSignal(str, str) # cell_id_1, cell_id_2
    multi_cells_swapped = pyqtSignal(list, list) # source_ids, target_ids
    new_image_dropped = pyqtSignal(str, float, float) # file_path, x, y (for creating new cells)
    project_file_dropped = pyqtSignal(str) # file_path for .figlayout files
    text_item_changed = pyqtSignal(str, dict) # text_item_id, changes_dict
    selection_changed_custom = pyqtSignal(list) # list of selected item ids
    cell_context_menu = pyqtSignal(str, bool, object) # cell_id, is_label_cell, QPointF(screen_pos)
    empty_context_menu = pyqtSignal(object, object)   # scene_pos (QPointF, in mm), screen_pos (QPoint)
    nested_layout_open_requested = pyqtSignal(str, str) # cell_id, figlayout_path
    insert_row_requested = pyqtSignal(int)   # insert at row_index
    insert_cell_requested = pyqtSignal(int, int)  # row_index, insert_col_index
    cell_freeform_geometry_changed = pyqtSignal(str, float, float, float, float) # cell_id, x, y, w, h
    divider_drag_finished = pyqtSignal(object)  # DividerItem
    # Export-region lifecycle (main_window creates undoable commands):
    #   defined   — user committed a new region by drag (x, y, w, h)
    #   edited    — user moved/resized existing region (x, y, w, h, old_x, old_y, old_w, old_h)
    #   clear_requested — user pressed Delete while region is selected
    export_region_defined = pyqtSignal(float, float, float, float)
    export_region_edited = pyqtSignal(float, float, float, float, float, float, float, float)
    export_region_clear_requested = pyqtSignal()
    cell_crop_committed = pyqtSignal(str, float, float, float, float)  # cell_id, left, top, right, bottom
    crop_mode_active = pyqtSignal(bool)  # True = entered crop mode, False = exited
    pip_geometry_changed = pyqtSignal(str, str, object, object)  # cell_id, pip_id, old_geom tuple, new_geom tuple
    pip_origin_changed = pyqtSignal(str, str, object, object)    # cell_id, pip_id, old_crop tuple, new_crop tuple
    pip_removed = pyqtSignal(str, str)  # cell_id, pip_id
    pip_context_menu = pyqtSignal(str, str, object)  # cell_id, pip_id, screen_pos (QPointF)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.project = None
        self.cell_items = {} # id -> CellItem
        self.label_cell_items = {} # "label_{cell_id}" -> CellItem (label-only cells)
        self.text_items = {} # id -> TextGraphicsItem
        self._add_buttons = [] # list of AddButtonItem
        
        # Drag manager (animated cell swap)
        self.drag_manager = DragManager(self)
        self.drag_manager.swap_requested.connect(self.cell_swapped.emit)
        self.drag_manager.multi_swap_requested.connect(self.multi_cells_swapped.emit)

        # Background — painted in drawBackground() as a dot grid
        self._canvas_bg = "#E8E8E8"
        self._grid_line = "#C7C7CC"
        self.setBackgroundBrush(QBrush(Qt.BrushStyle.NoBrush))

        # Page rect (white paper)
        self.page_rect = QRectF(0, 0, 210, 297) # Default A4
        self.page_item = self.addRect(self.page_rect, QPen(Qt.PenStyle.NoPen), QBrush(Qt.GlobalColor.white))
        self.page_item.setZValue(-100)

        # Margins rect (guide)
        self.margin_item = self.addRect(QRectF(), QPen(QColor("#DDDDDD"), 0.3, Qt.PenStyle.DashLine), QBrush(Qt.BrushStyle.NoBrush))
        self.margin_item.setZValue(-99)
        
        self._snap_line_items = []
        self._divider_items = []  # list of DividerItem
        self._drag_target_cell = None  # CellItem currently under an external file drag

        # Export region: view/editable model proxy. The item is created on-demand
        # when project.export_region is set or when user enters "defining" mode.
        self._export_region_item = None       # ExportRegionItem | None
        self._defining_export_region = False  # True while user is rubber-banding
        self._defining_start_pos = None       # QPointF (scene mm)
        self._defining_preview_item = None    # transient QGraphicsRectItem during drag

        self.preview_mode = False  # hides cell borders for export preview

        # Crop isolation veil
        self._crop_veil_item = None
        self._active_crop_cell = None

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------

    def apply_theme(self, tokens: dict) -> None:
        """Update all canvas visuals from design tokens. Call on theme switch."""
        self._canvas_bg = tokens["canvas_bg"]
        self._grid_line = tokens["grid_line"]
        self.page_item.setBrush(QBrush(QColor(tokens.get("surface", "#FFFFFF"))))
        self.margin_item.setPen(
            QPen(QColor(tokens.get("border", "#DDDDDD")), 0.3, Qt.PenStyle.DashLine)
        )
        for item in list(self.cell_items.values()) + list(self.label_cell_items.values()):
            item.apply_theme_tokens(tokens)
        self.invalidate(self.sceneRect(), QGraphicsScene.SceneLayer.BackgroundLayer)

    # ------------------------------------------------------------------
    # Background dot grid
    # ------------------------------------------------------------------

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        painter.fillRect(rect, QColor(self._canvas_bg))

    # ------------------------------------------------------------------

    def set_preview_mode(self, enabled: bool):
        if self.preview_mode == enabled:
            return
        self.preview_mode = enabled
        for btn in self._add_buttons:
            btn.setVisible(not enabled)
        # scene.update() only marks the background dirty; items must be
        # explicitly invalidated so Qt calls their paint() again.
        for item in list(self.cell_items.values()) + list(self.label_cell_items.values()):
            item.update()

    def set_project(self, project: Project):
        self.project = project
        
        # Update page geometry
        self.page_rect = QRectF(0, 0, project.page_width_mm, project.page_height_mm)
        self.page_item.setRect(self.page_rect)
        self.setSceneRect(self.page_rect.adjusted(-50, -50, 50, 50)) # Add some working space
        
        # Update margins
        m_rect = self.page_rect.adjusted(
            project.margin_left_mm, 
            project.margin_top_mm, 
            -project.margin_right_mm, 
            -project.margin_bottom_mm
        )
        self.margin_item.setRect(m_rect)
        
        self.refresh_layout()

    def refresh_layout(self):
        if not self.project:
            return
        
        # Update page geometry (in case page size changed)
        self.page_rect = QRectF(0, 0, self.project.page_width_mm, self.project.page_height_mm)
        self.page_item.setRect(self.page_rect)
        self.setSceneRect(self.page_rect.adjusted(-50, -50, 50, 50))
        
        # Update margins
        m_rect = self.page_rect.adjusted(
            self.project.margin_left_mm, 
            self.project.margin_top_mm, 
            -self.project.margin_right_mm, 
            -self.project.margin_bottom_mm
        )
        self.margin_item.setRect(m_rect)
            
        layout_result = LayoutEngine.calculate_layout(self.project)
        self._last_layout_result = layout_result
        
        # Sync Cell Items (only leaf cells are rendered on canvas)
        all_leaf_cells = self.project.get_all_leaf_cells()
        # 1. Remove cells not in project
        existing_ids = set(self.cell_items.keys())
        project_ids = set(c.id for c in all_leaf_cells)
        
        to_remove = existing_ids - project_ids
        for cid in to_remove:
            self.removeItem(self.cell_items[cid])
            del self.cell_items[cid]
            
        # 2. Add/Update cells
        for cell in all_leaf_cells:
            if cell.id not in self.cell_items:
                item = CellItem(cell.id)
                self.addItem(item)
                self.cell_items[cell.id] = item
            
            item = self.cell_items[cell.id]
            
            # Freeform mode toggle
            is_freeform = getattr(self.project, 'layout_mode', 'grid') == 'freeform'
            item.set_freeform_mode(is_freeform)

            # Geometry
            if cell.id in layout_result.cell_rects:
                x, y, w, h = layout_result.cell_rects[cell.id]
                item.setRect(0, 0, w, h)
                item.setPos(x, y)
                item.setZValue(getattr(cell, 'z_index', 0))
                
            # Content
                item.update_data(
                    cell.image_path, 
                    cell.fit_mode, 
                    {
                        'top': cell.padding_top, 
                        'right': cell.padding_right, 
                        'bottom': cell.padding_bottom, 
                        'left': cell.padding_left
                    },
                    cell.is_placeholder,
                    getattr(cell, 'rotation', 0),
                    getattr(cell, 'align_h', 'center'),
                    getattr(cell, 'align_v', 'center'),
                    getattr(cell, 'scale_bar_enabled', False),
                    getattr(cell, 'scale_bar_mode', 'rgb'),
                    getattr(cell, 'scale_bar_um_per_px', 0.1301),
                    getattr(cell, 'scale_bar_length_um', 10.0),
                    getattr(cell, 'scale_bar_color', '#FFFFFF'),
                    getattr(cell, 'scale_bar_show_text', True),
                    getattr(cell, 'scale_bar_thickness_mm', 0.5),
                    getattr(cell, 'scale_bar_position', 'bottom_right'),
                    getattr(cell, 'scale_bar_offset_x', 2.0),
                    getattr(cell, 'scale_bar_offset_y', 2.0),
                    getattr(cell, 'scale_bar_custom_text', None),
                    getattr(cell, 'scale_bar_text_size_mm', 2.0),
                    getattr(cell, 'crop_left', 0.0),
                    getattr(cell, 'crop_top', 0.0),
                    getattr(cell, 'crop_right', 1.0),
                    getattr(cell, 'crop_bottom', 1.0),
                )
                # Nested layout
                item.set_nested_layout(getattr(cell, 'nested_layout_path', None))
                # PiP insets
                item.update_pip_items(getattr(cell, 'pip_items', []))

        # Sync Label Cell Items (label rows above picture rows)
        label_rects = getattr(layout_result, 'label_rects', {})
        label_row_above = getattr(self.project, 'label_placement', 'in_cell') == 'label_row_above'

        # Build a map of cell_id -> numbering label text from existing TextItems
        numbering_texts = {}
        if label_row_above:
            for t in self.project.text_items:
                if t.scope == 'cell' and t.subtype != 'corner' and t.parent_id:
                    numbering_texts[t.parent_id] = t.text

        # Determine which label cell IDs should exist
        expected_label_ids = set()
        if label_row_above:
            for cell_id in label_rects:
                expected_label_ids.add(f"label_{cell_id}")

        # Remove stale label cells
        stale = set(self.label_cell_items.keys()) - expected_label_ids
        for lid in stale:
            self.removeItem(self.label_cell_items[lid])
            del self.label_cell_items[lid]

        # Add/Update label cells
        for cell_id, (lx, ly, lw, lh) in label_rects.items():
            lid = f"label_{cell_id}"
            if lid not in self.label_cell_items:
                litem = CellItem(lid)
                litem.is_label_cell = True
                litem.setFlag(CellItem.GraphicsItemFlag.ItemIsSelectable, True)
                litem.setAcceptDrops(False)
                self.addItem(litem)
                self.label_cell_items[lid] = litem

            litem = self.label_cell_items[lid]
            litem.setRect(0, 0, lw, lh)
            litem.setPos(lx, ly)
            litem.label_text = numbering_texts.get(cell_id, "")
            litem.label_font_family = self.project.label_font_family
            litem.label_font_size = self.project.label_font_size
            litem.label_font_weight = self.project.label_font_weight
            litem.label_color = self.project.label_color
            litem.label_align = getattr(self.project, 'label_align', 'center')
            litem.label_offset_x = getattr(self.project, 'label_offset_x', 0.0)
            litem.label_offset_y = getattr(self.project, 'label_offset_y', 0.0)
            litem.update()
            
        # Sync Text Items
        existing_text_ids = set(self.text_items.keys())
        project_text_ids = set(t.id for t in self.project.text_items)
        
        # Remove deleted
        to_remove_text = existing_text_ids - project_text_ids
        for tid in to_remove_text:
            self.removeItem(self.text_items[tid])
            del self.text_items[tid]
            
        # Add/Update
        for text_model in self.project.text_items:
            if text_model.id not in self.text_items:
                t_item = TextGraphicsItem(text_model.id, text_model.text)
                t_item.item_changed.connect(self._on_text_item_changed)
                self.addItem(t_item)
                self.text_items[text_model.id] = t_item
                
            t_item = self.text_items[text_model.id]
            # Use setHtml to support rich text
            t_item.setHtml(text_model.text)
            t_item.update_style(
                text_model.font_family, 
                text_model.font_size_pt, 
                text_model.font_weight, 
                text_model.color
            )
            
            # Position logic: cell-scoped labels follow their parent cell
            if text_model.scope == "cell" and text_model.parent_id:
                # In label_row_above mode, numbering labels are rendered by label cells directly
                # so hide the TextItem to avoid duplicate rendering
                if (
                    label_row_above
                    and text_model.subtype != 'corner'
                    and text_model.parent_id in label_rects
                ):
                    t_item.setVisible(False)
                    continue
                else:
                    t_item.setVisible(True)

                # Find parent cell's position from layout
                if text_model.parent_id in layout_result.cell_rects:
                    cx, cy, cw, ch = layout_result.cell_rects[text_model.parent_id]

                    # In previous code, 'attach_to' logic modified cx, cy, cw, ch by subtracting padding.
                    # As requested, padding should NOT affect the label position. Labels should always anchor 
                    # relative to the full cell boundaries. 
                    # We simply remove the code that adjusts cx, cy, cw, ch based on padding.
                    
                    # Calculate position based on anchor
                    anchor = text_model.anchor or "top_left_inside"
                    ox, oy = text_model.offset_x, text_model.offset_y
                    
                    # Get text bounding rect for right/bottom alignment (accounting for scale)
                    scale = t_item.scale()
                    text_width = t_item.boundingRect().width() * scale
                    text_height = t_item.boundingRect().height() * scale
                    
                    if "top" in anchor:
                        ty = cy + oy
                    elif "bottom" in anchor:
                        ty = cy + ch - oy - text_height
                    else:
                        ty = cy + (ch - text_height) / 2
                    
                    if "left" in anchor:
                        tx = cx + ox
                    elif "right" in anchor:
                        tx = cx + cw - ox - text_width
                    else:
                        tx = cx + (cw - text_width) / 2
                    
                    t_item.setPos(tx, ty)
                    t_item.setRotation(0.0)  # cell-scoped labels are never rotated

                    # Store cell bounds and anchor info for constrained dragging
                    t_item.cell_bounds = (cx, cy, cw, ch)
                    t_item.anchor = anchor
                    t_item.scope = "cell"
                else:
                    t_item.setPos(text_model.x, text_model.y)
                    t_item.scope = "cell"
            else:
                # Global (floating) text: absolute canvas position in mm.
                # Rotation is applied around the text's visual centre so that
                # setPos() still represents the unrotated top-left origin,
                # keeping drag-save math simple.
                t_item.setPos(text_model.x, text_model.y)
                br = t_item.boundingRect()
                t_item.setTransformOriginPoint(br.width() / 2, br.height() / 2)
                t_item.setRotation(getattr(text_model, "rotation", 0.0))
                t_item.scope = "global"

        # Place add-row / add-cell buttons and dividers around the layout
        self._refresh_add_buttons(layout_result)
        dragging = any(getattr(d, '_dragging', False) for d in self._divider_items)
        if getattr(self.project, 'layout_mode', 'grid') == 'grid' and not dragging:
            self._refresh_dividers(layout_result)
        elif getattr(self.project, 'layout_mode', 'grid') != 'grid':
            self._clear_dividers()

        # Sync export-region overlay
        self.refresh_export_region()

    def get_snap_lines(self, ignore_cell_id: str = None, include_page_edges: bool = False):
        """Return lists of vertical (x) and horizontal (y) coordinates for snapping."""
        v_lines = []
        h_lines = []
        m = self.margin_item.rect()
        if m.isValid():
            v_lines.extend([m.left(), m.center().x(), m.right()])
            h_lines.extend([m.top(), m.center().y(), m.bottom()])

        if include_page_edges and self.project is not None:
            pw = self.project.page_width_mm
            ph = self.project.page_height_mm
            v_lines.extend([0.0, pw / 2.0, pw])
            h_lines.extend([0.0, ph / 2.0, ph])

        for cid, item in self.cell_items.items():
            if cid == ignore_cell_id or item.is_label_cell:
                continue
            r = QRectF(item.pos().x(), item.pos().y(), item.rect().width(), item.rect().height())
            v_lines.extend([r.left(), r.center().x(), r.right()])
            h_lines.extend([r.top(), r.center().y(), r.bottom()])
            
        return v_lines, h_lines

    def show_snap_lines(self, x_coords, y_coords):
        """Draw pink dashed lines across the scene at the given coordinates."""
        self.hide_snap_lines()
        pen = QPen(QColor(255, 0, 255, 180), 0.5, Qt.PenStyle.DashLine)
        r = self.sceneRect()
        for x in x_coords:
            line = self.addLine(x, r.top(), x, r.bottom(), pen)
            line.setZValue(1000)
            self._snap_line_items.append(line)
        for y in y_coords:
            line = self.addLine(r.left(), y, r.right(), y, pen)
            line.setZValue(1000)
            self._snap_line_items.append(line)

    def hide_snap_lines(self):
        """Remove all active snap lines."""
        for item in getattr(self, '_snap_line_items', []):
            if item.scene():
                self.removeItem(item)
        self._snap_line_items = []

    def snap_rect(self, rect: QRectF, ignore_cell_id: str = None):
        """Find best snap delta for a rect and show lines. Returns (dx, dy)."""
        v_lines, h_lines = self.get_snap_lines(ignore_cell_id)
        
        best_dx = 0
        min_dx = 2.0
        snapped_x = None
        for cv in [rect.left(), rect.center().x(), rect.right()]:
            for tv in v_lines:
                diff = tv - cv
                if abs(diff) < min_dx:
                    min_dx = abs(diff)
                    best_dx = diff
                    snapped_x = tv
                    
        best_dy = 0
        min_dy = 2.0
        snapped_y = None
        for ch in [rect.top(), rect.center().y(), rect.bottom()]:
            for th in h_lines:
                diff = th - ch
                if abs(diff) < min_dy:
                    min_dy = abs(diff)
                    best_dy = diff
                    snapped_y = th
                    
        self.show_snap_lines(
            [snapped_x] if snapped_x is not None else [],
            [snapped_y] if snapped_y is not None else []
        )
        
        return best_dx, best_dy

    def reposition_cell_text_items(self, cell_id: str, cx: float, cy: float, cw: float, ch: float):
        """Reposition in-cell TextGraphicsItems for a specific cell immediately (used during freeform drag)."""
        if not self.project:
            return
        for text_model in self.project.text_items:
            if text_model.scope != "cell" or text_model.parent_id != cell_id:
                continue
            t_item = self.text_items.get(text_model.id)
            if not t_item or not t_item.isVisible():
                continue

            ex, ey, ew, eh = cx, cy, cw, ch

            anchor = text_model.anchor or "top_left_inside"
            ox, oy = text_model.offset_x, text_model.offset_y
            scale = t_item.scale()
            text_width = t_item.boundingRect().width() * scale
            text_height = t_item.boundingRect().height() * scale

            ty = ey + oy if "top" in anchor else (ey + eh - oy - text_height if "bottom" in anchor else ey + (eh - text_height) / 2)
            tx = ex + ox if "left" in anchor else (ex + ew - ox - text_width if "right" in anchor else ex + (ew - text_width) / 2)

            t_item.setPos(tx, ty)
            t_item.cell_bounds = (ex, ey, ew, eh)

    def dragEnterEvent(self, event: QGraphicsSceneDragDropEvent):
        if event.mimeData().hasUrls():
            self._drag_target_cell = None
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event: QGraphicsSceneDragDropEvent):
        if not event.mimeData().hasUrls():
            event.ignore()
            return
        event.accept()

        urls = event.mimeData().urls()
        local_path = urls[0].toLocalFile() if urls else ""
        is_image = local_path and not local_path.lower().endswith(('.figlayout', '.json'))

        pos = event.scenePos()
        target_cell = next(
            (item for item in self.items(pos)
             if isinstance(item, CellItem) and not item.is_label_cell),
            None
        )

        if target_cell is not self._drag_target_cell:
            if self._drag_target_cell is not None:
                self._drag_target_cell.end_ext_drag()
            self._drag_target_cell = target_cell
            if target_cell is not None and is_image:
                target_cell.begin_ext_drag(bool(target_cell.image_path))

        if target_cell is not None and is_image:
            target_cell.update_ext_drag_pos(target_cell.mapFromScene(pos))

    def dragLeaveEvent(self, event):
        if self._drag_target_cell is not None:
            self._drag_target_cell.end_ext_drag()
            self._drag_target_cell = None
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QGraphicsSceneDragDropEvent):
        # Handle File Drop (External only — internal cell swap is handled by DragManager)
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if not urls:
                if self._drag_target_cell is not None:
                    self._drag_target_cell.end_ext_drag()
                    self._drag_target_cell = None
                return

            local_path = urls[0].toLocalFile()
            if not local_path:
                if self._drag_target_cell is not None:
                    self._drag_target_cell.end_ext_drag()
                    self._drag_target_cell = None
                return

            # Check if it's a project file
            if local_path.lower().endswith('.figlayout') or local_path.lower().endswith('.json'):
                if self._drag_target_cell is not None:
                    self._drag_target_cell.end_ext_drag()
                    self._drag_target_cell = None
                self.project_file_dropped.emit(local_path)
                event.accept()
                return

            # Check if dropped on a cell
            pos = event.scenePos()
            target_cell = next(
                (item for item in self.items(pos)
                 if isinstance(item, CellItem) and not item.is_label_cell),
                None
            )

            # Evaluate PiP zone BEFORE clearing drag state (is_pip_drop_zone reads _ext_drag_has_image)
            is_pip = target_cell is not None and target_cell.is_pip_drop_zone(
                target_cell.mapFromScene(pos)
            )

            # Now clean up drag hover state
            if self._drag_target_cell is not None:
                self._drag_target_cell.end_ext_drag()
                self._drag_target_cell = None

            if target_cell:
                if is_pip:
                    self.pip_image_dropped.emit(target_cell.cell_id, local_path)
                else:
                    self.cell_dropped.emit(target_cell.cell_id, local_path)
            else:
                self.new_image_dropped.emit(local_path, pos.x(), pos.y())

            event.accept()
        else:
            if self._drag_target_cell is not None:
                self._drag_target_cell.end_ext_drag()
                self._drag_target_cell = None
            super().dropEvent(event)

    def _refresh_add_buttons(self, layout_result):
        """Create / reposition the '+' buttons around the layout."""
        # Remove old buttons
        for btn in self._add_buttons:
            self.removeItem(btn)
        self._add_buttons.clear()

        if not self.project or not layout_result.row_rects:
            return

        T = AddButtonItem.THICKNESS
        GAP = 1.5  # spacing between layout edge and button (mm)

        sorted_rows = sorted(layout_result.row_rects.items(), key=lambda kv: kv[0])
        content_width = self.project.page_width_mm - self.project.margin_left_mm - self.project.margin_right_mm
        margin_left = self.project.margin_left_mm

        # Row buttons: wide horizontal bars spanning content width
        row_btn_w = content_width
        row_btn_h = T

        # --- Add Row Above (above first row) ---
        if sorted_rows:
            first_y = sorted_rows[0][1][1]
            btn = AddButtonItem("row_above", width=row_btn_w, height=row_btn_h,
                                row_index=sorted_rows[0][0])
            btn.setPos(margin_left, first_y - row_btn_h - GAP)
            self.addItem(btn)
            self._add_buttons.append(btn)

        # --- Add Row Below (below last row) ---
        if sorted_rows:
            last_idx, (_, last_y, _, last_h) = sorted_rows[-1]
            btn = AddButtonItem("row_below", width=row_btn_w, height=row_btn_h,
                                row_index=last_idx)
            btn.setPos(margin_left, last_y + last_h + GAP)
            self.addItem(btn)
            self._add_buttons.append(btn)

        # --- Per-row: Add Cell Left / Right (tall vertical bars spanning row height) ---
        for row_idx, (rx, ry, rw, rh) in sorted_rows:
            row_temp = next((r for r in self.project.rows if r.index == row_idx), None)
            col_count = row_temp.column_count if row_temp else 1

            cell_btn_w = T
            cell_btn_h = rh

            # Left button
            btn_l = AddButtonItem("cell_left", width=cell_btn_w, height=cell_btn_h,
                                  row_index=row_idx, col_index=0)
            btn_l.setPos(rx - cell_btn_w - GAP, ry)
            self.addItem(btn_l)
            self._add_buttons.append(btn_l)

            # Right button
            btn_r = AddButtonItem("cell_right", width=cell_btn_w, height=cell_btn_h,
                                  row_index=row_idx, col_index=col_count)
            btn_r.setPos(rx + rw + GAP, ry)
            self.addItem(btn_r)
            self._add_buttons.append(btn_r)

    def _clear_dividers(self):
        for d in self._divider_items:
            if d.scene():
                self.removeItem(d)
        self._divider_items.clear()

    def _refresh_dividers(self, layout_result):
        """Create draggable dividers between rows and between columns."""
        self._clear_dividers()
        if not self.project:
            return

        sorted_rows = sorted(layout_result.row_rects.items(), key=lambda kv: kv[0])
        row_heights = layout_result.row_heights
        row_templates = {r.index: r for r in self.project.rows}
        content_width = (self.project.page_width_mm
                         - self.project.margin_left_mm
                         - self.project.margin_right_mm)
        gap = self.project.gap_mm
        from src.model.layout_engine import LayoutEngine

        # --- Horizontal dividers between consecutive rows ---
        for i in range(len(sorted_rows) - 1):
            idx_a, (rx_a, ry_a, rw_a, rh_a) = sorted_rows[i]
            idx_b, (rx_b, ry_b, rw_b, rh_b) = sorted_rows[i + 1]
            row_a = row_templates.get(idx_a)
            row_b = row_templates.get(idx_b)
            if row_a is None or row_b is None:
                continue

            # Position in the gap between row_a bottom and row_b top
            gap_top = ry_a + rh_a
            gap_bot = ry_b
            cy = (gap_top + gap_bot) / 2
            div_x = self.project.margin_left_mm
            div_w = content_width

            div = DividerItem(
                kind='row',
                row_a=idx_a, row_b=idx_b,
                ratio_a=row_a.height_ratio,
                ratio_b=row_b.height_ratio,
            )
            div.setRect(0, 0, div_w, HIT_THICKNESS)
            div.setPos(div_x, cy - HIT_THICKNESS / 2)
            self.addItem(div)
            self._divider_items.append(div)

        # --- Vertical dividers between columns within each row ---
        for row_idx, (rx, ry, rw, rh) in sorted_rows:
            row_temp = row_templates.get(row_idx)
            if row_temp is None or row_temp.column_count < 2:
                continue

            col_widths = LayoutEngine._compute_col_widths(row_temp, content_width, gap)
            # Determine actual row x start (may differ in fixed/alignment mode)
            row_cells = [c for c in self.project.cells if c.row_index == row_idx]
            if not row_cells:
                continue

            x_cursor = rx
            col_ratios = (row_temp.column_ratios if row_temp.column_ratios
                          else [1.0] * row_temp.column_count)
            while len(col_ratios) < row_temp.column_count:
                col_ratios.append(1.0)
            col_ratios = list(col_ratios[:row_temp.column_count])

            for ci in range(row_temp.column_count - 1):
                x_cursor += col_widths[ci]
                # gap centre
                cx = x_cursor + gap / 2

                div = DividerItem(
                    kind='col',
                    col_a=ci, col_b=ci + 1,
                    ratio_a=col_ratios[ci],
                    ratio_b=col_ratios[ci + 1],
                    row_index=row_idx,
                )
                div.setRect(0, 0, HIT_THICKNESS, rh)
                div.setPos(cx - HIT_THICKNESS / 2, ry)
                self.addItem(div)
                self._divider_items.append(div)

                x_cursor += gap

    def _divider_live_update(self, div: 'DividerItem'):
        """Apply ratio changes live (without undo) so the user sees instant feedback."""
        if not self.project:
            return
        if div.kind == 'row':
            row_a = next((r for r in self.project.rows if r.index == div.row_a), None)
            row_b = next((r for r in self.project.rows if r.index == div.row_b), None)
            if row_a and row_b:
                row_a.height_ratio = div.ratio_a
                row_b.height_ratio = div.ratio_b
        else:
            row = next((r for r in self.project.rows if r.index == div.row_index), None)
            if row:
                col_ratios = (list(row.column_ratios) if row.column_ratios
                              else [1.0] * row.column_count)
                while len(col_ratios) < row.column_count:
                    col_ratios.append(1.0)
                col_ratios[div.col_a] = div.ratio_a
                col_ratios[div.col_b] = div.ratio_b
                row.column_ratios = col_ratios
        self.refresh_layout()

    def _divider_drag_finished(self, div: 'DividerItem'):
        """Emit signal so MainWindow can push an undoable command."""
        self.divider_drag_finished.emit(div)

    # ------------------------------------------------------------------
    # Export region
    # ------------------------------------------------------------------

    def refresh_export_region(self):
        """Sync the on-canvas ExportRegionItem with project.export_region."""
        if not self.project:
            return
        er = getattr(self.project, 'export_region', None)
        if er is None:
            # Remove any existing item
            if self._export_region_item is not None and self._export_region_item.scene():
                self.removeItem(self._export_region_item)
            self._export_region_item = None
            return
        if self._export_region_item is None:
            self._export_region_item = ExportRegionItem(er.x_mm, er.y_mm, er.w_mm, er.h_mm)
            self.addItem(self._export_region_item)
        else:
            self._export_region_item.setRect(QRectF(er.x_mm, er.y_mm, er.w_mm, er.h_mm))

    def begin_define_export_region(self):
        """Enter rubber-band mode — next left-press on empty page area starts the drag."""
        self._defining_export_region = True
        self._defining_start_pos = None
        # Deselect everything to avoid interference
        self.clearSelection()

    def cancel_define_export_region(self):
        self._defining_export_region = False
        self._defining_start_pos = None
        if self._defining_preview_item is not None and self._defining_preview_item.scene():
            self.removeItem(self._defining_preview_item)
        self._defining_preview_item = None

    def _export_region_live_update(self, item: 'ExportRegionItem'):
        """Called while user drags/resizes the committed region. Keep model in sync."""
        if not self.project or not self.project.export_region:
            return
        r = item.rect()
        self.project.export_region.x_mm = r.x()
        self.project.export_region.y_mm = r.y()
        self.project.export_region.w_mm = r.width()
        self.project.export_region.h_mm = r.height()

    def _export_region_drag_finished(self, item: 'ExportRegionItem'):
        """Called on mouse-release after a move/resize of an existing region."""
        old = item.original_rect
        r = item.rect()
        if old == r:
            return
        self.export_region_edited.emit(
            r.x(), r.y(), r.width(), r.height(),
            old.x(), old.y(), old.width(), old.height(),
        )

    def _export_region_clear_requested(self):
        self.export_region_clear_requested.emit()

    def _on_add_button_clicked(self, action: str, row_index: int, col_index: int):
        """Called by AddButtonItem when clicked."""
        if action == "row_above":
            self.insert_row_requested.emit(row_index)
        elif action == "row_below":
            self.insert_row_requested.emit(row_index + 1)
        elif action == "cell_left":
            self.insert_cell_requested.emit(row_index, col_index)
        elif action == "cell_right":
            self.insert_cell_requested.emit(row_index, col_index)

    def _on_text_item_changed(self, text_item_id: str, changes: dict):
        """Forward text item changes to MainWindow via signal"""
        self.text_item_changed.emit(text_item_id, changes)

    # ------------------------------------------------------------------
    # Crop isolation veil
    # ------------------------------------------------------------------

    def show_crop_veil(self, crop_cell_item):
        """Overlay the scene with a dark veil, leaving the crop cell on top."""
        self.hide_crop_veil(_emit=False)
        veil_rect = self.sceneRect().adjusted(-500, -500, 500, 500)
        self._crop_veil_item = self.addRect(
            veil_rect,
            QPen(Qt.PenStyle.NoPen),
            QBrush(QColor(0, 0, 0, 170)),
        )
        self._crop_veil_item.setZValue(200)
        self._crop_veil_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self._active_crop_cell = crop_cell_item
        self.crop_mode_active.emit(True)

    def hide_crop_veil(self, _emit=True):
        """Remove the isolation veil."""
        was_active = self._active_crop_cell is not None
        if self._crop_veil_item is not None:
            if self._crop_veil_item.scene() is self:
                self.removeItem(self._crop_veil_item)
            self._crop_veil_item = None
        self._active_crop_cell = None
        if was_active and _emit:
            self.crop_mode_active.emit(False)

    def mousePressEvent(self, event):
        """Intercept clicks outside the active crop cell to commit and exit crop mode."""
        # Export-region defining mode — left-click starts the rubber-band.
        if self._defining_export_region and event.button() == Qt.MouseButton.LeftButton:
            self._defining_start_pos = event.scenePos()
            # Transient dashed preview rect
            from PyQt6.QtWidgets import QGraphicsRectItem as _QRI
            pen = QPen(QColor(230, 120, 40, 235))
            pen.setCosmetic(True)
            pen.setStyle(Qt.PenStyle.DashLine)
            pen.setWidthF(1.5)
            brush = QBrush(QColor(230, 120, 40, 32))
            self._defining_preview_item = _QRI()
            self._defining_preview_item.setPen(pen)
            self._defining_preview_item.setBrush(brush)
            self._defining_preview_item.setZValue(900)
            self._defining_preview_item.setRect(QRectF(self._defining_start_pos, self._defining_start_pos))
            self.addItem(self._defining_preview_item)
            event.accept()
            return

        if self._active_crop_cell is not None:
            pos = event.scenePos()
            cell_scene_rect = QRectF(
                self._active_crop_cell.pos().x(),
                self._active_crop_cell.pos().y(),
                self._active_crop_cell.rect().width(),
                self._active_crop_cell.rect().height(),
            )
            if not cell_scene_rect.contains(pos):
                cell = self._active_crop_cell  # capture before exit clears it
                cell.exit_crop_mode(commit=True)
                self.clearSelection()
                event.accept()
                return

        # Dismiss PiP selection handles when clicking anywhere (the cell's own
        # mousePressEvent deselects when clicking outside a PiP within the cell,
        # but clicks on other cells or empty space also need to dismiss).
        if event.button() == Qt.MouseButton.LeftButton:
            for item in self.cell_items.values():
                if item._selected_pip_id is not None:
                    item.deselect_pip()

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        # Update rubber-band preview while defining an export region.
        if (self._defining_export_region
                and self._defining_start_pos is not None
                and self._defining_preview_item is not None):
            p1 = self._defining_start_pos
            p2 = self._snap_rubberband_point(event.scenePos(), p1)
            r = QRectF(p1, p2).normalized()
            self._defining_preview_item.setRect(r)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        # Commit the rubber-band export-region selection.
        if (self._defining_export_region
                and self._defining_start_pos is not None
                and event.button() == Qt.MouseButton.LeftButton):
            p1 = self._defining_start_pos
            p2 = self._snap_rubberband_point(event.scenePos(), p1)
            r = QRectF(p1, p2).normalized()
            self.hide_snap_lines()
            # Discard degenerate rects
            if r.width() >= 2.0 and r.height() >= 2.0:
                self.export_region_defined.emit(r.x(), r.y(), r.width(), r.height())
            # Exit defining mode and clear preview
            self.cancel_define_export_region()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _snap_rubberband_point(self, p, anchor):
        """Snap the moving corner of the export-region rubber-band to nearby
        page/margin/cell edges. Shows pink guides and returns the snapped point.
        """
        SNAP = 2.0  # mm
        v_lines, h_lines = self.get_snap_lines(include_page_edges=True)

        new_x = p.x()
        snap_x = None
        min_dx = SNAP
        for tv in v_lines:
            diff = tv - p.x()
            if abs(diff) < min_dx:
                min_dx = abs(diff)
                new_x = tv
                snap_x = tv

        new_y = p.y()
        snap_y = None
        min_dy = SNAP
        for th in h_lines:
            diff = th - p.y()
            if abs(diff) < min_dy:
                min_dy = abs(diff)
                new_y = th
                snap_y = th

        self.show_snap_lines(
            [snap_x] if snap_x is not None else [],
            [snap_y] if snap_y is not None else [],
        )
        from PyQt6.QtCore import QPointF
        return QPointF(new_x, new_y)

    def keyPressEvent(self, event):
        """Enter/Return commits crop; Escape cancels crop or dismisses PiP handles."""
        # Escape during define-mode cancels the rubber-band without emitting.
        if self._defining_export_region and event.key() == Qt.Key.Key_Escape:
            self.cancel_define_export_region()
            event.accept()
            return

        if self._active_crop_cell is not None:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._active_crop_cell.exit_crop_mode(commit=True)
                self.clearSelection()
                event.accept()
                return
            elif event.key() == Qt.Key.Key_Escape:
                self._active_crop_cell.exit_crop_mode(commit=False)
                self.clearSelection()
                event.accept()
                return

        if event.key() == Qt.Key.Key_Escape:
            dismissed = False
            for item in self.cell_items.values():
                if item._selected_pip_id is not None:
                    item.deselect_pip()
                    dismissed = True
            if dismissed:
                event.accept()
                return

        super().keyPressEvent(event)

    def contextMenuEvent(self, event):
        """Right-click on empty scene area (not on a CellItem or TextGraphicsItem).
        Qt only calls this on the scene when no item accepts the event, so reaching
        here means the click was on blank workspace, the page background, or margins."""
        super().contextMenuEvent(event)
        if event.isAccepted():
            return  # an item handled it after all
        # Accept the event BEFORE emitting so that any nested event loop
        # (started by the menu the slot will show) can't cause Qt to
        # re-dispatch this unaccepted event and pop up the menu twice.
        event.accept()
        self.empty_context_menu.emit(event.scenePos(), event.screenPos())
