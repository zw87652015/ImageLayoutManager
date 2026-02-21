import os
import math
from typing import Optional
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QToolBar, QPushButton, QSplitter, QFileDialog,
    QMessageBox, QSpinBox, QLabel, QComboBox,
    QLabel, QStyle, QMenu
)
from PyQt6.QtCore import Qt, QTimer, QSize
from PyQt6.QtGui import QAction, QIcon, QKeySequence, QUndoStack

# Try importing QOpenGLWidget for GPU acceleration
try:
    from PyQt6.QtOpenGLWidgets import QOpenGLWidget
    HAS_OPENGL = True
except ImportError:
    HAS_OPENGL = False

from src.model.data_model import Project, Cell, RowTemplate, TextItem
from src.canvas.canvas_scene import CanvasScene
from src.canvas.canvas_view import CanvasView
from src.app.inspector import Inspector
from src.model.enums import PageSizePreset
from src.export.pdf_exporter import PdfExporter
from src.export.image_exporter import ImageExporter
from src.utils.auto_label import AutoLabel
from src.app.commands import (
    PropertyChangeCommand, MultiPropertyChangeCommand, SwapCellsCommand, MultiSwapCellsCommand,
    DropImageCommand, ChangeRowCountCommand, InsertRowCommand, InsertCellCommand,
    DeleteRowCommand, DeleteCellCommand,
    AddTextCommand, DeleteTextCommand, AutoLabelCommand, AutoLayoutCommand,
    SplitCellCommand, InsertSubCellCommand, DeleteSubCellCommand, WrapAndInsertCommand,
    ChangeSubCellRatioCommand
)
from src.utils.image_proxy import get_image_proxy

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self._current_project_path = None
        from src.version import APP_VERSION
        self._app_version = APP_VERSION
        self.setWindowTitle(f"Academic Figure Layout v{APP_VERSION}[*]")
        self.resize(1200, 800)
        
        # Undo Stack
        self.undo_stack = QUndoStack(self)
        
        # Model
        self.project = Project()
        # Initialize with some default grid: 2 rows
        self.project.rows = [
            RowTemplate(index=0, column_count=2, height_ratio=1.0),
            RowTemplate(index=1, column_count=2, height_ratio=1.0)
        ]
        # Create initial cells for these rows
        self._ensure_cells_exist()
        
        # UI Components
        self._setup_ui()
        
        # Initialize Scene
        self.scene.set_project(self.project)
        
        # Connect Signals
        self._connect_signals()

        self._update_window_title()

    def _setup_ui(self):
        # Central Widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Toolbar
        self.toolbar = QToolBar()
        self.toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toolbar.setIconSize(QSize(16, 16))
        self.toolbar.setMovable(False)
        self.addToolBar(self.toolbar)

        # ── Menu Bar ──
        file_menu = self.menuBar().addMenu("File")
        edit_menu = self.menuBar().addMenu("Edit")
        help_menu = self.menuBar().addMenu("Help")

        about_action = QAction("About", self)
        about_action.triggered.connect(self._on_show_about)
        help_menu.addAction(about_action)

        # ── Undo / Redo ──
        undo_action = self.undo_stack.createUndoAction(self, "Undo")
        undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        undo_action.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowBack))
        redo_action = self.undo_stack.createRedoAction(self, "Redo")
        redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        redo_action.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowForward))

        edit_menu.addAction(undo_action)
        edit_menu.addAction(redo_action)
        edit_menu.addSeparator()

        self.toolbar.addAction(undo_action)
        self.toolbar.addAction(redo_action)
        self.toolbar.addSeparator()

        # ── File Actions ──
        new_action = QAction("New", self)
        new_action.setShortcut(QKeySequence.StandardKey.New)
        new_action.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon))
        new_action.triggered.connect(self._on_new_project)

        open_action = QAction("Open", self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton))
        open_action.triggered.connect(self._on_open_project)

        save_action = QAction("Save", self)
        save_action.setShortcut(QKeySequence.StandardKey.Save)
        save_action.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton))
        save_action.triggered.connect(self._on_save_project)

        save_as_action = QAction("Save As...", self)
        save_as_action.setShortcut(QKeySequence.StandardKey.SaveAs)
        save_as_action.triggered.connect(self._on_save_project_as)

        file_menu.addAction(new_action)
        file_menu.addAction(open_action)
        file_menu.addAction(save_action)
        file_menu.addAction(save_as_action)
        file_menu.addSeparator()

        # File menu — image operations
        import_action = QAction("Import Images...", self)
        import_action.triggered.connect(self._on_import_images)
        file_menu.addAction(import_action)

        open_images_grid_action = QAction("Open Images as Grid...", self)
        open_images_grid_action.triggered.connect(self._on_open_images_as_grid)
        file_menu.addAction(open_images_grid_action)

        reload_images_action = QAction("Reload Images", self)
        reload_images_action.setShortcut(QKeySequence("F5"))
        reload_images_action.triggered.connect(self._on_reload_images)
        file_menu.addAction(reload_images_action)

        file_menu.addSeparator()

        # File menu — export
        export_pdf_action = QAction("Export PDF...", self)
        export_pdf_action.triggered.connect(self._on_export_pdf)
        file_menu.addAction(export_pdf_action)

        export_tiff_action = QAction("Export TIFF...", self)
        export_tiff_action.triggered.connect(self._on_export_tiff)
        file_menu.addAction(export_tiff_action)

        export_jpg_action = QAction("Export JPG...", self)
        export_jpg_action.triggered.connect(self._on_export_jpg)
        file_menu.addAction(export_jpg_action)

        # Toolbar — file group (New, Open, Save only)
        self.toolbar.addAction(new_action)
        self.toolbar.addAction(open_action)
        self.toolbar.addAction(save_action)
        self.toolbar.addSeparator()

        # ── Edit menu — text/image/label actions ──
        add_text_action = QAction("Add Text", self)
        add_text_action.triggered.connect(self._on_add_text)
        edit_menu.addAction(add_text_action)

        delete_text_action = QAction("Delete Selected", self)
        delete_text_action.setShortcut(QKeySequence.StandardKey.Delete)
        delete_text_action.triggered.connect(self._on_delete_text)
        edit_menu.addAction(delete_text_action)

        delete_image_action = QAction("Delete Image", self)
        delete_image_action.setShortcut(QKeySequence("Ctrl+Delete"))
        delete_image_action.triggered.connect(self._on_delete_image)
        edit_menu.addAction(delete_image_action)

        edit_menu.addSeparator()

        auto_label_action = QAction("Auto Label", self)
        auto_label_action.setShortcut(QKeySequence("Ctrl+Shift+L"))
        auto_label_action.triggered.connect(self._on_auto_label)
        edit_menu.addAction(auto_label_action)

        auto_layout_action = QAction("Auto Layout", self)
        auto_layout_action.setShortcut(QKeySequence("Ctrl+Shift+A"))
        auto_layout_action.triggered.connect(self._on_auto_layout)
        edit_menu.addAction(auto_layout_action)

        # ── Toolbar — quick actions ──
        self.toolbar.addAction(auto_label_action)
        self.toolbar.addAction(auto_layout_action)
        self.toolbar.addSeparator()

        # ── Toolbar — Export dropdown button ──
        from PyQt6.QtWidgets import QToolButton
        export_button = QToolButton(self)
        export_button.setText("Export")
        export_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        export_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton))
        export_menu = QMenu(self)
        export_menu.addAction(export_pdf_action)
        export_menu.addAction(export_tiff_action)
        export_menu.addAction(export_jpg_action)
        export_button.setMenu(export_menu)
        export_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.toolbar.addWidget(export_button)

        # Splitter for Content | Inspector
        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter)
        
        # Canvas Area
        self.scene = CanvasScene()
        self.view = CanvasView(self.scene)
        
        # GPU Acceleration
        if HAS_OPENGL:
            self.view.setViewport(QOpenGLWidget())
            print("GPU Acceleration Enabled (QOpenGLWidget)")
        
        splitter.addWidget(self.view)
        
        # Inspector Area
        self.inspector = Inspector()
        splitter.addWidget(self.inspector)
        
        # Set initial sizes and stretch factors
        splitter.setSizes([900, 300])
        splitter.setStretchFactor(0, 1)   # Canvas stretches
        splitter.setStretchFactor(1, 0)   # Inspector keeps its size
        
        # Status Bar
        self.statusbar = self.statusBar()
        self.mouse_pos_label = QLabel("")
        self.selection_info_label = QLabel("")
        self.canvas_size_label = QLabel("Canvas: -")
        self.zoom_label = QLabel("Zoom: 100%")
        self.statusbar.addWidget(self.mouse_pos_label)
        self.statusbar.addWidget(self.selection_info_label)
        self.statusbar.addPermanentWidget(self.canvas_size_label)
        self.statusbar.addPermanentWidget(self.zoom_label)

    def _connect_signals(self):
        # Scene signals
        self.scene.cell_dropped.connect(self._on_cell_image_dropped)
        self.scene.cell_swapped.connect(self._on_cell_swapped)
        self.scene.multi_cells_swapped.connect(self._on_multi_cells_swapped)
        self.scene.new_image_dropped.connect(self._on_new_image_dropped)
        self.scene.project_file_dropped.connect(self._on_project_file_dropped)
        self.scene.text_item_changed.connect(self._on_text_item_drag_changed)
        self.scene.selectionChanged.connect(self._on_selection_changed)
        self.scene.cell_context_menu.connect(self._on_cell_context_menu)
        self.scene.nested_layout_open_requested.connect(self._on_open_nested_layout)
        self.scene.insert_row_requested.connect(self._on_insert_row)
        self.scene.insert_cell_requested.connect(self._on_insert_cell)
        
        # View signals
        self.view.zoom_changed.connect(self._on_zoom_changed)
        self.view.mouse_scene_pos_changed.connect(self._on_mouse_pos_changed)
        self.view.navigate_cell.connect(self._on_navigate_cell)
        self.view.swap_cell.connect(self._on_swap_cell_direction)
        
        # Inspector signals
        self.inspector.cell_property_changed.connect(self._on_cell_property_changed)
        self.inspector.text_property_changed.connect(self._on_text_property_changed)
        self.inspector.row_property_changed.connect(self._on_row_property_changed)
        self.inspector.project_property_changed.connect(self._on_project_property_changed)
        self.inspector.corner_label_changed.connect(self._on_corner_label_changed)
        self.inspector.apply_color_to_group.connect(self._on_apply_color_to_group)
        self.inspector.label_text_changed.connect(self._on_label_text_changed)
        self.inspector.subcell_ratio_changed.connect(self._on_subcell_ratio_changed)

        self.undo_stack.cleanChanged.connect(self._on_undo_clean_changed)

    def _on_zoom_changed(self, zoom_level):
        self.zoom_label.setText(f"Zoom: {int(zoom_level * 100)}%")

    def _on_mouse_pos_changed(self, x_mm, y_mm):
        self.mouse_pos_label.setText(f"  X: {x_mm:.1f} mm  Y: {y_mm:.1f} mm")

    # ------------------------------------------------------------------
    # Cell navigation helpers
    # ------------------------------------------------------------------

    def _cell_path_label(self, cell) -> str:
        """Build a compact hierarchical path label for the status bar.
        
        Top-level cell:          "R0C1"
        Sub-cell (depth 1):      "R0C1 › V1"   (vertical split, child index 1)
        Sub-cell (depth 2):      "R0C1 › V1 › H0"
        """
        # Walk up to build path segments from leaf to root
        segments = []
        current = cell
        parent = self.project.find_parent_of(current.id)
        while parent:
            idx = next((i for i, c in enumerate(parent.children) if c.id == current.id), 0)
            direction_char = "V" if parent.split_direction == "vertical" else "H"
            segments.append(f"{direction_char}{idx + 1}")
            current = parent
            parent = self.project.find_parent_of(current.id)
        # current is now the top-level cell
        root_label = f"R{current.row_index + 1}C{current.col_index + 1}"
        segments.reverse()
        if segments:
            return root_label + " › " + " › ".join(segments)
        return root_label

    def _get_selected_cell(self):
        """Return (cell_model, cell_item) for the single selected cell, or (None, None)."""
        items = self.scene.selectedItems()
        if len(items) != 1:
            return None, None
        item = items[0]
        if not hasattr(item, 'cell_id') or getattr(item, 'is_label_cell', False):
            return None, None
        cell = self.project.find_cell_by_id(item.cell_id)
        return cell, item

    def _find_neighbor_cell(self, cell, direction):
        """Find the neighboring cell in the given direction."""
        row_templates = sorted(self.project.rows, key=lambda r: r.index)
        if direction == "left":
            target_row, target_col = cell.row_index, cell.col_index - 1
        elif direction == "right":
            r = next((r for r in row_templates if r.index == cell.row_index), None)
            max_col = (r.column_count - 1) if r else 0
            target_row = cell.row_index
            target_col = min(cell.col_index + 1, max_col)
        elif direction == "up":
            target_row, target_col = cell.row_index - 1, cell.col_index
        elif direction == "down":
            target_row, target_col = cell.row_index + 1, cell.col_index
        elif direction == "next":
            r = next((r for r in row_templates if r.index == cell.row_index), None)
            max_col = (r.column_count - 1) if r else 0
            if cell.col_index < max_col:
                target_row, target_col = cell.row_index, cell.col_index + 1
            else:
                target_row, target_col = cell.row_index + 1, 0
        elif direction == "prev":
            if cell.col_index > 0:
                target_row, target_col = cell.row_index, cell.col_index - 1
            else:
                prev_row = cell.row_index - 1
                r = next((r for r in row_templates if r.index == prev_row), None)
                if r:
                    target_row, target_col = prev_row, r.column_count - 1
                else:
                    return None
        else:
            return None

        return next((c for c in self.project.cells
                     if c.row_index == target_row and c.col_index == target_col), None)

    def _select_cell_by_id(self, cell_id):
        """Select a cell on the canvas by its ID."""
        self.scene.clearSelection()
        item = self.scene.cell_items.get(cell_id)
        if item:
            item.setSelected(True)
            self.view.centerOn(item)

    def _on_navigate_cell(self, direction):
        cell, _ = self._get_selected_cell()
        if not cell:
            # If nothing selected, select the first cell
            if self.project.cells:
                first = sorted(self.project.cells, key=lambda c: (c.row_index, c.col_index))[0]
                self._select_cell_by_id(first.id)
            return
        neighbor = self._find_neighbor_cell(cell, direction)
        if neighbor:
            self._select_cell_by_id(neighbor.id)

    def _on_swap_cell_direction(self, direction):
        cell, _ = self._get_selected_cell()
        if not cell:
            return
        neighbor = self._find_neighbor_cell(cell, direction)
        if neighbor and neighbor.id != cell.id:
            cmd = SwapCellsCommand(cell, neighbor, self._refresh_and_update)
            self.undo_stack.push(cmd)
            # Keep the moved cell selected
            self._select_cell_by_id(cell.id)

    def _ensure_cells_exist(self):
        # Simple logic: ensure every slot in defined rows has a cell
        # Remove cells that are out of bounds
        
        # 1. Keep valid cells
        valid_cells = []
        existing_map = {} # (row, col) -> cell
        
        for c in self.project.cells:
            # Check if row exists
            row_temp = next((r for r in self.project.rows if r.index == c.row_index), None)
            if row_temp and c.col_index < row_temp.column_count:
                valid_cells.append(c)
                existing_map[(c.row_index, c.col_index)] = c
        
        self.project.cells = valid_cells
        
        # 2. Add missing cells
        for r in self.project.rows:
            for col_idx in range(r.column_count):
                if (r.index, col_idx) not in existing_map:
                    new_cell = Cell(row_index=r.index, col_index=col_idx, is_placeholder=True)
                    self.project.cells.append(new_cell)

    def _refresh_and_update(self):
        self.scene.refresh_layout()
        # Update Canvas Size Label
        rect = self.scene.sceneRect()
        self.canvas_size_label.setText(f"Canvas: {int(rect.width())}x{int(rect.height())}")
        
        # Check for low-res images

    def _on_undo_clean_changed(self, clean: bool):
        self.setWindowModified(not clean)
        self._update_window_title()

    def _update_window_title(self):
        if self._current_project_path:
            name = os.path.basename(self._current_project_path)
        else:
            name = "Untitled"
        self.setWindowTitle(f"Academic Figure Layout v{self._app_version} - {name}[*]")

    def _mark_dirty(self):
        if self.undo_stack.isClean():
            self.setWindowModified(True)

    def _maybe_save(self) -> bool:
        if self.undo_stack.isClean():
            return True

        ret = QMessageBox.question(
            self,
            "Unsaved Changes",
            "The project has unsaved changes. Save now?",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if ret == QMessageBox.StandardButton.Save:
            return self._on_save_project()
        if ret == QMessageBox.StandardButton.Discard:
            return True
        return False

    def _set_project(self, project: Project, path: Optional[str] = None):
        self.project = project
        self._ensure_cells_exist()
        self.scene.set_project(self.project)
        
        self.undo_stack.clear()
        self._current_project_path = path
        self.setWindowModified(False)
        self._update_window_title()
        self._refresh_and_update()
        self._check_image_resolution()
        
        # Update selection to refresh Inspector
        self._on_selection_changed()

    def _build_project_from_images(self, paths):
        project = Project()

        n = len(paths)
        if n <= 0:
            return project

        cols = int(math.ceil(math.sqrt(n)))
        rows = int(math.ceil(n / cols))

        project.rows = [RowTemplate(index=i, column_count=cols, height_ratio=1.0) for i in range(rows)]
        project.cells = []

        idx = 0
        for r in range(rows):
            for c in range(cols):
                cell = Cell(row_index=r, col_index=c, is_placeholder=True)
                if idx < n:
                    cell.image_path = paths[idx]
                    cell.is_placeholder = False
                project.cells.append(cell)
                idx += 1

        return project

    def _check_image_resolution(self):
        """Check if any images are too low resolution for the target DPI"""
        from src.model.layout_engine import LayoutEngine
        from PIL import Image
        import os
        
        warnings = []
        layout = LayoutEngine.calculate_layout(self.project)
        dpi = self.project.dpi
        
        # Guideline 9.4: enforce minimum pixels on the *shorter axis*.
        # To avoid noisy warnings, only warn when the implied upscale factor exceeds this.
        upscale_warn_threshold = 1.2

        for cell in self.project.cells:
            if not cell.image_path or cell.is_placeholder:
                continue
            if not os.path.exists(cell.image_path):
                continue
            if cell.id not in layout.cell_rects:
                continue

            x, y, w_mm, h_mm = layout.cell_rects[cell.id]
            required_w = (w_mm / 25.4) * dpi
            required_h = (h_mm / 25.4) * dpi
            required_short = min(required_w, required_h)

            try:
                with Image.open(cell.image_path) as img:
                    actual_w, actual_h = img.size
            except Exception:
                continue

            actual_short = min(actual_w, actual_h)
            if actual_short <= 0 or required_short <= 0:
                continue

            upscale_factor = required_short / actual_short
            if upscale_factor > upscale_warn_threshold:
                warnings.append(f"Cell({cell.row_index},{cell.col_index})")
        
        if warnings:
            self.statusbar.showMessage(f"⚠ Low-res images: {', '.join(warnings[:3])}{'...' if len(warnings) > 3 else ''}", 5000)
        else:
            self.statusbar.clearMessage()

    def _on_row_count_changed(self, count):
        # Prevent loop if change comes from undo/redo
        if len(self.project.rows) == count:
            return
            
        cmd = ChangeRowCountCommand(self.project, count, self._refresh_and_update)
        self.undo_stack.push(cmd)

    def _on_cell_image_dropped(self, cell_id, file_path):
        cell = self.project.find_cell_by_id(cell_id)
        if cell:
            cmd = DropImageCommand(cell, file_path, self._refresh_and_update)
            self.undo_stack.push(cmd)

    def _on_new_image_dropped(self, file_path, x, y):
        # Find first placeholder
        target_cell = None
        for cell in self.project.get_all_leaf_cells():
            if cell.is_placeholder:
                target_cell = cell
                break
        
        if target_cell:
            cmd = DropImageCommand(target_cell, file_path, self._refresh_and_update)
            self.undo_stack.push(cmd)
        else:
            print("No placeholder available for new image")

    def _on_cell_swapped(self, id1, id2):
        c1 = self.project.find_cell_by_id(id1)
        c2 = self.project.find_cell_by_id(id2)
        
        if c1 and c2:
            cmd = SwapCellsCommand(c1, c2, self._refresh_and_update)
            self.undo_stack.push(cmd)

    def _on_multi_cells_swapped(self, source_ids, target_ids):
        sources = [self.project.find_cell_by_id(sid) for sid in source_ids]
        targets = [self.project.find_cell_by_id(tid) for tid in target_ids]
        if all(sources) and all(targets) and len(sources) == len(targets):
            cmd = MultiSwapCellsCommand(sources, targets, self._refresh_and_update)
            self.undo_stack.push(cmd)

    def _on_insert_row(self, insert_index):
        # Default to 2 columns for new rows (matching ChangeRowCountCommand default)
        cmd = InsertRowCommand(self.project, insert_index, column_count=2,
                               update_callback=self._refresh_and_update)
        self.undo_stack.push(cmd)

    def _on_insert_cell(self, row_index, insert_col):
        cmd = InsertCellCommand(self.project, row_index, insert_col,
                                update_callback=self._refresh_and_update)
        self.undo_stack.push(cmd)

    def _on_delete_row(self, row_index):
        if len(self.project.rows) <= 1:
            return
        cmd = DeleteRowCommand(self.project, row_index,
                               update_callback=self._refresh_and_update)
        self.undo_stack.push(cmd)

    def _on_delete_cell(self, row_index, col_index):
        row = next((r for r in self.project.rows if r.index == row_index), None)
        if not row or row.column_count <= 1:
            return
        cmd = DeleteCellCommand(self.project, row_index, col_index,
                                update_callback=self._refresh_and_update)
        self.undo_stack.push(cmd)

    def _on_selection_changed(self):
        try:
            items = self.scene.selectedItems()
        except RuntimeError:
            return  # Scene was deleted
        if not items:
            self.selection_info_label.setText("")
            self.inspector.set_selection(None, self.project.to_dict())
            return

        # Status bar: selection info
        cell_items = [i for i in items if hasattr(i, 'cell_id') and not getattr(i, 'is_label_cell', False)]
        if len(cell_items) > 1:
            self.selection_info_label.setText(f"  {len(cell_items)} cells selected")
        elif len(cell_items) == 1:
            ci = cell_items[0]
            cell = self.project.find_cell_by_id(ci.cell_id)
            if cell:
                info = f"  {self._cell_path_label(cell)}"
                if cell.image_path and not cell.is_placeholder:
                    info += f"  |  {os.path.basename(cell.image_path)}"
                self.selection_info_label.setText(info)
            else:
                self.selection_info_label.setText("")
        else:
            self.selection_info_label.setText("")

        # Multi-cell selection
        if len(cell_items) > 1:
            first_cell = self.project.find_cell_by_id(cell_items[0].cell_id)
            multi_data = {"count": len(cell_items)}
            if first_cell:
                multi_data.update({
                    "fit_mode": first_cell.fit_mode,
                    "rotation": getattr(first_cell, 'rotation', 0),
                    "padding_top": first_cell.padding_top,
                    "padding_bottom": first_cell.padding_bottom,
                    "padding_left": first_cell.padding_left,
                    "padding_right": first_cell.padding_right,
                })
            self.inspector.set_selection('multi_cell', multi_data)
            return

        item = items[0]
        
        if hasattr(item, 'cell_id'):
            # Check if it's a label cell (id starts with "label_")
            if hasattr(item, 'is_label_cell') and item.is_label_cell:
                # Find the corresponding text item for this label cell
                parent_cell_id = item.cell_id.removeprefix("label_")
                text_obj = next(
                    (t for t in self.project.text_items
                     if t.scope == "cell" and t.subtype != "corner" and t.parent_id == parent_cell_id),
                    None
                )
                label_data = {
                    "text_item_id": text_obj.id if text_obj else None,
                    "label_text": text_obj.text if text_obj else "",
                    "label_scheme": self.project.label_scheme,
                    "label_font_family": self.project.label_font_family,
                    "label_font_size": self.project.label_font_size,
                    "label_font_weight": self.project.label_font_weight,
                    "label_color": self.project.label_color,
                    "label_align": self.project.label_align,
                    "label_offset_x": self.project.label_offset_x,
                    "label_offset_y": self.project.label_offset_y,
                    "label_row_height": getattr(self.project, 'label_row_height', 0.0),
                    "label_attach_to": self.project.label_attach_to,
                }
                self.inspector.set_selection('label_cell', label_data)
                return

            cell = self.project.find_cell_by_id(item.cell_id)
            if cell:
                # Find the top-level cell to get row data
                top_cell = cell
                parent = self.project.find_parent_of(cell.id)
                while parent:
                    top_cell = parent
                    parent = self.project.find_parent_of(parent.id)

                # Find Row Data from top-level cell
                row = next((r for r in self.project.rows if r.index == top_cell.row_index), None)
                row_data = row.to_dict() if row else None

                # Populate corner label fields from existing cell-scoped text items
                cell_dict = cell.to_dict()
                corner_labels = {}
                for t in self.project.text_items:
                    if t.scope == "cell" and t.parent_id == cell.id and t.anchor:
                        corner_labels[t.anchor] = t.text
                cell_dict["corner_labels"] = corner_labels

                # Sub-cell info: if this cell has a parent split container, provide ratio data
                cell_parent = self.project.find_parent_of(cell.id)
                if cell_parent and cell_parent.split_direction != "none":
                    idx = next((i for i, c in enumerate(cell_parent.children) if c.id == cell.id), 0)
                    ratios = cell_parent.split_ratios if cell_parent.split_ratios else [1.0] * len(cell_parent.children)
                    while len(ratios) < len(cell_parent.children):
                        ratios.append(1.0)
                    cell_dict["_subcell"] = {
                        "cell_id": cell.id,
                        "direction": cell_parent.split_direction,
                        "sibling_count": len(cell_parent.children),
                        "sibling_index": idx,
                        "ratio": ratios[idx] if idx < len(ratios) else 1.0,
                    }

                self.inspector.set_selection('cell', cell_dict, row_data)
                return
                
        if hasattr(item, 'text_item_id'):
             text = next((t for t in self.project.text_items if t.id == item.text_item_id), None)
             if text:
                 self.inspector.set_selection('text', text.to_dict())
                 return
                 
        self.inspector.set_selection(None, self.project.to_dict())

    def _on_cell_property_changed(self, changes):
        items = self.scene.selectedItems()
        if not items:
            return
        
        # Collect all selected cells
        selected_cells = []
        for item in items:
            if hasattr(item, 'cell_id'):
                cell = self.project.find_cell_by_id(item.cell_id)
                if cell:
                    selected_cells.append(cell)
        
        if not selected_cells:
            return
        
        # Apply changes to all selected cells
        if len(selected_cells) == 1:
            cmd = PropertyChangeCommand(selected_cells[0], changes, self._refresh_and_update, "Change Cell Property")
        else:
            cmd = MultiPropertyChangeCommand(selected_cells, changes, self._refresh_and_update, f"Change {len(selected_cells)} Cells")
        self.undo_stack.push(cmd)

    def _on_corner_label_changed(self, payload: dict):
        """Create/update/delete a corner label (cell-scoped anchored TextItem) for the selected cell."""
        items = self.scene.selectedItems()
        if not items or not hasattr(items[0], 'cell_id'):
            return

        cell_id = items[0].cell_id
        cell = self.project.find_cell_by_id(cell_id)
        if not cell:
            return

        anchor = payload.get("anchor")
        text = (payload.get("text") or "").strip()
        if not anchor:
            return

        existing = next(
            (
                t for t in self.project.text_items
                if t.scope == "cell" and t.parent_id == cell.id and t.anchor == anchor
            ),
            None
        )

        # Empty text means delete the label if it exists
        if text == "":
            if existing:
                cmd = DeleteTextCommand(self.project, existing, self._refresh_and_update)
                self.undo_stack.push(cmd)
            return

        # Otherwise create or update
        if existing:
            cmd = PropertyChangeCommand(existing, {"text": text}, self._refresh_and_update, "Edit Corner Label")
            self.undo_stack.push(cmd)
        else:
            from src.model.data_model import TextItem
            item = TextItem(
                text=text,
                font_family=self.project.corner_label_font_family,
                font_size_pt=self.project.corner_label_font_size,
                font_weight=self.project.corner_label_font_weight,
                color=self.project.corner_label_color,
                scope="cell",
                subtype="corner",
                parent_id=cell.id,
                anchor=anchor,
                offset_x=2.0,
                offset_y=2.0,
            )
            cmd = AddTextCommand(self.project, item, self._refresh_and_update)
            self.undo_stack.push(cmd)

    def _on_label_text_changed(self, text_item_id: str, new_text: str):
        """Handle label text edit from the Label Cell Settings panel."""
        text_obj = next((t for t in self.project.text_items if t.id == text_item_id), None)
        if not text_obj:
            return
        cmd = PropertyChangeCommand(text_obj, {"text": new_text}, self._refresh_and_update, "Edit Label Text")
        self.undo_stack.push(cmd)

    def _on_text_property_changed(self, changes):
        items = self.scene.selectedItems()
        if not items or not hasattr(items[0], 'text_item_id'):
            return
            
        text_id = items[0].text_item_id
        text_obj = next((t for t in self.project.text_items if t.id == text_id), None)
        
        if not text_obj:
            return

        style_keys = {"font_family", "font_size_pt", "font_weight"}
        style_changes = {k: v for k, v in changes.items() if k in style_keys}
        other_changes = {k: v for k, v in changes.items() if k not in style_keys}

        # If the selected text item is a label (cell-scoped), treat style edits as GLOBAL label style edits.
        if text_obj.scope == "cell" and style_changes:
            project_style_changes = {}
            
            # Determine prefix based on subtype
            prefix = "label_"
            if text_obj.subtype == "corner":
                prefix = "corner_label_"
            
            if "font_family" in style_changes:
                project_style_changes[f"{prefix}font_family"] = style_changes["font_family"]
            if "font_size_pt" in style_changes:
                project_style_changes[f"{prefix}font_size"] = style_changes["font_size_pt"]
            if "font_weight" in style_changes:
                project_style_changes[f"{prefix}font_weight"] = style_changes["font_weight"]

            if project_style_changes:
                callback = self._refresh_and_sync_labels
                if text_obj.subtype == "corner":
                    callback = self._refresh_and_sync_corner_labels
                
                cmd = PropertyChangeCommand(
                    self.project,
                    project_style_changes,
                    callback,
                    "Change Label Style"
                )
                self.undo_stack.push(cmd)

        # Non-style changes remain per-item (e.g. label color, text content, x/y, etc.)
        if other_changes:
            cmd = PropertyChangeCommand(text_obj, other_changes, self._refresh_and_update, "Change Text Property")
            self.undo_stack.push(cmd)

    def _on_text_item_drag_changed(self, text_item_id: str, changes: dict):
        """Handle text item changes from dragging or inline editing"""
        text_obj = next((t for t in self.project.text_items if t.id == text_item_id), None)
        if text_obj:
            cmd = PropertyChangeCommand(text_obj, changes, self._refresh_and_update, "Move/Edit Text")
            self.undo_stack.push(cmd)

    def _on_row_property_changed(self, changes):
        items = self.scene.selectedItems()
        if not items or not hasattr(items[0], 'cell_id'):
            return
            
        cell_id = items[0].cell_id
        cell = self.project.find_cell_by_id(cell_id)
        
        if cell:
            row = next((r for r in self.project.rows if r.index == cell.row_index), None)
            if row:
                # Special handling for column count which requires logic
                # For now, let's treat column count change as a PropertyChangeCommand? 
                # No, column count change requires ensuring cells.
                # So we should separate simple property changes from structural changes.
                
                if "column_count" in changes:
                    # Not fully implemented in commands yet for this specific path
                    # Let's fallback to direct set for complex logic or implement a Command.
                    # Since ChangeRowCountCommand does row additions, Column count is different.
                    # We need a ChangeRowColumnsCommand. 
                    # For v1, let's just do it directly without undo for this specific complex property, 
                    # OR use PropertyChangeCommand but add a callback that handles the restructuring.
                    
                    # We'll do direct execution for now to avoid complexity in this step
                    # OR better: use PropertyChangeCommand and in the callback, check structure.
                    
                    # But PropertyChangeCommand.undo needs to restore cells if they were deleted.
                    # Simple property change is insufficient for column count.
                    pass 
                
                cmd = PropertyChangeCommand(row, changes, self._handle_row_change_callback, "Change Row Property")
                self.undo_stack.push(cmd)

    def _handle_row_change_callback(self):
        # Check if we need to restructure
        self._ensure_cells_exist() # This handles column count changes safely
        self._refresh_and_update()

    def _on_project_property_changed(self, changes):
        # We need to handle PageSizePreset conversion for the command to work if we pass raw dict
        # or do it inside the command. PropertyChangeCommand simply sets attributes.
        # So we should convert values before passing to command if needed.
        
        processed_changes = {}
        for k, v in changes.items():
            if k == "page_size_preset":
                processed_changes[k] = PageSizePreset(v)
            else:
                processed_changes[k] = v
        
        # Check if label font parameters are being changed (excluding color - that's per-label now)
        label_props = {"label_font_family", "label_font_size", "label_font_weight"}
        is_label_change = bool(label_props & set(changes.keys()))

        corner_label_props = {"corner_label_font_family", "corner_label_font_size", "corner_label_font_weight"}
        is_corner_label_change = bool(corner_label_props & set(changes.keys()))
        
        if is_label_change:
            # Use callback that also syncs label styles
            cmd = PropertyChangeCommand(self.project, processed_changes, self._refresh_and_sync_labels, "Change Label Settings")
        elif is_corner_label_change:
            cmd = PropertyChangeCommand(self.project, processed_changes, self._refresh_and_sync_corner_labels, "Change Corner Label Settings")
        else:
            cmd = PropertyChangeCommand(self.project, processed_changes, self._refresh_and_update, "Change Project Settings")
        
        self.undo_stack.push(cmd)

    def _refresh_and_sync_labels(self):
        """Refresh and also sync all cell-scoped labels (numbering) to project label settings (excluding color)"""
        for text_item in self.project.text_items:
            # Sync if it's cell-scoped and NOT explicitly a corner label
            if text_item.scope == "cell" and text_item.subtype != "corner":
                text_item.font_family = self.project.label_font_family
                text_item.font_size_pt = self.project.label_font_size
                text_item.font_weight = self.project.label_font_weight
                # Color is now per-label, not auto-synced
        self._refresh_and_update()

    def _refresh_and_sync_corner_labels(self):
        """Refresh and also sync all cell-scoped corner labels to project settings (excluding color)"""
        for text_item in self.project.text_items:
            if text_item.scope == "cell" and text_item.subtype == "corner":
                text_item.font_family = self.project.corner_label_font_family
                text_item.font_size_pt = self.project.corner_label_font_size
                text_item.font_weight = self.project.corner_label_font_weight
                # Color is now per-label, not auto-synced
        self._refresh_and_update()

    def _on_apply_color_to_group(self, subtype: str, color_hex: str):
        """Apply color to all labels in the same group (numbering or corner)."""
        for text_item in self.project.text_items:
            if text_item.scope == "cell":
                if subtype == "corner" and text_item.subtype == "corner":
                    text_item.color = color_hex
                elif subtype == "numbering" and text_item.subtype != "corner":
                    text_item.color = color_hex
        self._refresh_and_update()

    def _on_add_text(self):
        item = TextItem(text="New Text", x=10, y=10, scope="global")
        cmd = AddTextCommand(self.project, item, self._refresh_and_update)
        self.undo_stack.push(cmd)

    def _on_delete_text(self):
        """Delete selected text item(s) or label cell numbering labels"""
        try:
            items = self.scene.selectedItems()
        except RuntimeError:
            return
        
        from src.canvas.cell_item import CellItem

        for item in items:
            if hasattr(item, 'text_item_id'):
                text_obj = next((t for t in self.project.text_items if t.id == item.text_item_id), None)
                if text_obj:
                    cmd = DeleteTextCommand(self.project, text_obj, self._refresh_and_update)
                    self.undo_stack.push(cmd)
            elif isinstance(item, CellItem) and item.is_label_cell:
                # Label cell ID is "label_{cell_id}" — extract the parent cell_id
                parent_cell_id = item.cell_id.removeprefix("label_")
                text_obj = next(
                    (t for t in self.project.text_items
                     if t.scope == "cell" and t.subtype != "corner" and t.parent_id == parent_cell_id),
                    None
                )
                if text_obj:
                    cmd = DeleteTextCommand(self.project, text_obj, self._refresh_and_update)
                    self.undo_stack.push(cmd)

    def _on_delete_image(self):
        """Delete image from selected cell(s)"""
        try:
            items = self.scene.selectedItems()
        except RuntimeError:
            return

        from src.canvas.cell_item import CellItem

        selected_cells = [it for it in items if isinstance(it, CellItem)]
        if not selected_cells:
            return

        # One command per cell (keeps undo/redo consistent with existing commands)
        for cell_item in selected_cells:
            cell = self.project.find_cell_by_id(cell_item.cell_id)
            if not cell:
                continue
            if cell.is_placeholder and not cell.image_path:
                continue

            cmd = PropertyChangeCommand(
                cell,
                {"image_path": None, "is_placeholder": True},
                self._refresh_and_update,
                "Delete Image",
            )
            self.undo_stack.push(cmd)

    def _on_cell_context_menu(self, cell_id: str, is_label_cell: bool, screen_pos):
        """Build and show context menu for a cell or label cell."""
        from PyQt6.QtCore import QPoint

        menu = QMenu(self)

        if is_label_cell:
            # Label cell context menu
            parent_cell_id = cell_id.removeprefix("label_")
            text_obj = next(
                (t for t in self.project.text_items
                 if t.scope == "cell" and t.subtype != "corner" and t.parent_id == parent_cell_id),
                None
            )
            if text_obj:
                delete_label_action = menu.addAction("Delete Label")
                delete_label_action.triggered.connect(
                    lambda: self._ctx_delete_numbering_label(parent_cell_id)
                )
            menu.exec(QPoint(int(screen_pos.x()), int(screen_pos.y())))
            return

        # Regular cell context menu
        cell = self.project.find_cell_by_id(cell_id)
        if not cell:
            return

        has_image = cell.image_path and not cell.is_placeholder

        # --- Import / Delete Image ---
        has_nested = bool(cell.nested_layout_path)

        import_action = menu.addAction("Import Image...")
        import_action.triggered.connect(lambda: self._ctx_import_image(cell_id))

        if has_image:
            delete_img_action = menu.addAction("Delete Image")
            delete_img_action.triggered.connect(lambda: self._ctx_delete_image(cell_id))

        menu.addSeparator()

        # --- Nested Layout ---
        import_layout_action = menu.addAction("Import Layout...")
        import_layout_action.triggered.connect(lambda: self._ctx_import_layout(cell_id))

        if has_nested:
            delete_layout_action = menu.addAction("Delete Layout")
            delete_layout_action.triggered.connect(lambda: self._ctx_delete_layout(cell_id))

        menu.addSeparator()

        # --- Label submenu ---
        label_menu = menu.addMenu("Labels")

        # Numbering label
        has_numbering = any(
            t for t in self.project.text_items
            if t.scope == "cell" and t.subtype != "corner" and t.parent_id == cell_id
        )
        if has_numbering:
            del_num_action = label_menu.addAction("Delete Label Cell")
            del_num_action.triggered.connect(lambda: self._ctx_delete_numbering_label(cell_id))
        else:
            add_num_action = label_menu.addAction("Add Label Cell")
            add_num_action.triggered.connect(lambda: self._ctx_add_numbering_label(cell_id))

        label_menu.addSeparator()

        # Corner labels
        corner_anchors = [
            ("top_left_inside", "Top Left"),
            ("top_right_inside", "Top Right"),
            ("bottom_left_inside", "Bottom Left"),
            ("bottom_right_inside", "Bottom Right"),
        ]
        for anchor, display_name in corner_anchors:
            existing = next(
                (t for t in self.project.text_items
                 if t.scope == "cell" and getattr(t, 'subtype', None) == 'corner'
                 and t.anchor == anchor and t.parent_id == cell_id),
                None
            )
            if existing:
                action = label_menu.addAction(f"Delete {display_name} Label")
                action.triggered.connect(
                    lambda checked=False, a=anchor: self._ctx_delete_corner_label(cell_id, a)
                )
            else:
                action = label_menu.addAction(f"Add {display_name} Label")
                action.triggered.connect(
                    lambda checked=False, a=anchor: self._ctx_add_corner_label(cell_id, a)
                )

        # --- Image operations (only if has image) ---
        if has_image:
            menu.addSeparator()

            # Fit Mode submenu
            fit_menu = menu.addMenu("Fit Mode")
            for mode in ["contain", "cover"]:
                action = fit_menu.addAction(mode.capitalize())
                action.setCheckable(True)
                action.setChecked(cell.fit_mode == mode)
                action.triggered.connect(
                    lambda checked=False, m=mode: self._ctx_set_cell_prop(cell_id, {"fit_mode": m})
                )

            # Rotation submenu
            rot_menu = menu.addMenu("Rotation")
            for deg in [0, 90, 180, 270]:
                action = rot_menu.addAction(f"{deg}°")
                action.setCheckable(True)
                action.setChecked(cell.rotation == deg)
                action.triggered.connect(
                    lambda checked=False, d=deg: self._ctx_set_cell_prop(cell_id, {"rotation": d})
                )

            # Scale Bar toggle
            menu.addSeparator()
            sb_action = menu.addAction("Enable Scale Bar" if not cell.scale_bar_enabled else "Disable Scale Bar")
            sb_action.triggered.connect(
                lambda: self._ctx_set_cell_prop(cell_id, {"scale_bar_enabled": not cell.scale_bar_enabled})
            )

        # --- Insert Row / Cell ---
        menu.addSeparator()
        insert_menu = menu.addMenu("Insert")

        # Find top-level cell info for row/column operations
        top_cell = cell
        parent = self.project.find_parent_of(cell_id)
        while parent:
            top_cell = parent
            parent = self.project.find_parent_of(parent.id)
        ri = top_cell.row_index
        ci = top_cell.col_index
        row_temp = next((r for r in self.project.rows if r.index == ri), None)
        col_count = row_temp.column_count if row_temp else 1

        act_row_above = insert_menu.addAction("Row Above")
        act_row_above.triggered.connect(lambda: self._on_insert_row(ri))

        act_row_below = insert_menu.addAction("Row Below")
        act_row_below.triggered.connect(lambda: self._on_insert_row(ri + 1))

        insert_menu.addSeparator()

        act_cell_left = insert_menu.addAction("Column Left")
        act_cell_left.triggered.connect(lambda: self._on_insert_cell(ri, ci))

        act_cell_right = insert_menu.addAction("Column Right")
        act_cell_right.triggered.connect(lambda: self._on_insert_cell(ri, ci + 1))

        # --- Sub-cell operations ---
        # WrapAndInsertCommand handles both cases:
        #   - If parent already splits in the requested direction → insert sibling
        #   - Otherwise → wrap this cell in a new split container
        insert_menu.addSeparator()
        sub_menu = insert_menu.addMenu("Split / Sub-Cell")
        act_sub_above = sub_menu.addAction("Cell Above")
        act_sub_above.triggered.connect(
            lambda: self._ctx_wrap_and_insert(cell_id, "vertical", "before"))
        act_sub_below = sub_menu.addAction("Cell Below")
        act_sub_below.triggered.connect(
            lambda: self._ctx_wrap_and_insert(cell_id, "vertical", "after"))
        act_sub_left = sub_menu.addAction("Cell Left")
        act_sub_left.triggered.connect(
            lambda: self._ctx_wrap_and_insert(cell_id, "horizontal", "before"))
        act_sub_right = sub_menu.addAction("Cell Right")
        act_sub_right.triggered.connect(
            lambda: self._ctx_wrap_and_insert(cell_id, "horizontal", "after"))

        cell_parent = self.project.find_parent_of(cell_id)

        # --- Delete Row / Cell ---
        delete_menu = menu.addMenu("Delete")

        act_del_row = delete_menu.addAction("This Row")
        if len(self.project.rows) <= 1:
            act_del_row.setEnabled(False)
            act_del_row.setToolTip("Cannot delete the last row")
        act_del_row.triggered.connect(lambda: self._on_delete_row(ri))

        act_del_cell = delete_menu.addAction("This Column")
        if col_count <= 1:
            act_del_cell.setEnabled(False)
            act_del_cell.setToolTip("Cannot delete the last cell in a row")
        act_del_cell.triggered.connect(lambda: self._on_delete_cell(ri, ci))

        if cell_parent and len(cell_parent.children) > 1:
            act_del_sub = delete_menu.addAction("This Sub-Cell")
            act_del_sub.triggered.connect(
                lambda: self._ctx_delete_subcell(cell_id))

        menu.exec(QPoint(int(screen_pos.x()), int(screen_pos.y())))

    def _ctx_import_image(self, cell_id: str):
        """Context menu: import image into cell."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Image", "",
            "Images (*.png *.jpg *.jpeg *.tif *.tiff *.bmp *.gif *.webp *.svg *.pdf *.eps);;All Files (*)"
        )
        if path:
            cell = self.project.find_cell_by_id(cell_id)
            if cell:
                cmd = DropImageCommand(cell, path, self._refresh_and_update)
                self.undo_stack.push(cmd)

    def _ctx_delete_image(self, cell_id: str):
        """Context menu: delete image from cell."""
        cell = self.project.find_cell_by_id(cell_id)
        if cell and (cell.image_path or not cell.is_placeholder):
            cmd = PropertyChangeCommand(
                cell, {"image_path": None, "is_placeholder": True},
                self._refresh_and_update, "Delete Image"
            )
            self.undo_stack.push(cmd)

    def _ctx_import_layout(self, cell_id: str):
        """Context menu: import a .figlayout file into a cell as a nested layout."""
        from src.model.nested_layout_utils import detect_circular_reference

        path, _ = QFileDialog.getOpenFileName(
            self, "Import Layout", "",
            "Figure Layout (*.figlayout);;All Files (*)"
        )
        if not path:
            return

        # Circular reference check
        parent_path = self._current_project_path
        if parent_path and detect_circular_reference(parent_path, path):
            QMessageBox.warning(
                self, "Circular Reference",
                "Cannot import this layout: it would create a circular reference "
                "(the selected file already references this project directly or indirectly)."
            )
            return

        cell = self.project.find_cell_by_id(cell_id)
        if cell:
            cmd = PropertyChangeCommand(
                cell, {"nested_layout_path": path},
                self._refresh_and_update, "Import Layout"
            )
            self.undo_stack.push(cmd)

    def _ctx_delete_layout(self, cell_id: str):
        """Context menu: remove the nested layout from a cell."""
        cell = self.project.find_cell_by_id(cell_id)
        if cell and cell.nested_layout_path:
            cmd = PropertyChangeCommand(
                cell, {"nested_layout_path": None},
                self._refresh_and_update, "Delete Layout"
            )
            self.undo_stack.push(cmd)

    def _ctx_add_numbering_label(self, cell_id: str):
        """Context menu: add a numbering label for a cell."""
        # Ensure label_placement is 'label_row_above' so the label cell row appears
        if self.project.label_placement != "label_row_above":
            cmd = PropertyChangeCommand(
                self.project, {"label_placement": "label_row_above"},
                self._refresh_and_update, "Switch to Label Row"
            )
            self.undo_stack.push(cmd)

        # Determine the next label text based on scheme and existing labels
        scheme = self.project.label_scheme
        existing_labels = [
            t for t in self.project.text_items
            if t.scope == "cell" and t.subtype != "corner" and t.parent_id
        ]
        idx = len(existing_labels)
        if scheme in ["(a)", "a"]:
            letter = chr(ord('a') + idx % 26)
            text = f"({letter})" if scheme == "(a)" else letter
        else:
            letter = chr(ord('A') + idx % 26)
            text = f"({letter})" if scheme == "(A)" else letter

        item = TextItem(
            text=text,
            font_family=self.project.label_font_family,
            font_size_pt=self.project.label_font_size,
            font_weight=self.project.label_font_weight,
            color=self.project.label_color,
            scope="cell",
            parent_id=cell_id,
            anchor="top_left_inside",
            offset_x=2.0,
            offset_y=2.0,
        )
        cmd = AddTextCommand(self.project, item, self._refresh_and_update)
        self.undo_stack.push(cmd)

    def _ctx_delete_numbering_label(self, cell_id: str):
        """Context menu: delete the numbering label for a cell."""
        text_obj = next(
            (t for t in self.project.text_items
             if t.scope == "cell" and t.subtype != "corner" and t.parent_id == cell_id),
            None
        )
        if text_obj:
            cmd = DeleteTextCommand(self.project, text_obj, self._refresh_and_update)
            self.undo_stack.push(cmd)

    def _ctx_add_corner_label(self, cell_id: str, anchor: str):
        """Context menu: add a corner label at the given anchor."""
        from PyQt6.QtWidgets import QInputDialog
        text, ok = QInputDialog.getText(self, "Corner Label", f"Label text for {anchor}:")
        if ok and text.strip():
            item = TextItem(
                text=text.strip(),
                font_family=self.project.corner_label_font_family,
                font_size_pt=self.project.corner_label_font_size,
                font_weight=self.project.corner_label_font_weight,
                color=self.project.corner_label_color,
                scope="cell",
                subtype="corner",
                parent_id=cell_id,
                anchor=anchor,
                offset_x=2.0,
                offset_y=2.0,
            )
            cmd = AddTextCommand(self.project, item, self._refresh_and_update)
            self.undo_stack.push(cmd)

    def _ctx_delete_corner_label(self, cell_id: str, anchor: str):
        """Context menu: delete the corner label at the given anchor."""
        text_obj = next(
            (t for t in self.project.text_items
             if t.scope == "cell" and getattr(t, 'subtype', None) == 'corner'
             and t.anchor == anchor and t.parent_id == cell_id),
            None
        )
        if text_obj:
            cmd = DeleteTextCommand(self.project, text_obj, self._refresh_and_update)
            self.undo_stack.push(cmd)

    def _on_subcell_ratio_changed(self, cell_id: str, new_ratio: float):
        """Inspector: change the size ratio of a sub-cell."""
        cmd = ChangeSubCellRatioCommand(self.project, cell_id, new_ratio,
                                         update_callback=self._refresh_and_update)
        self.undo_stack.push(cmd)

    def _ctx_wrap_and_insert(self, cell_id: str, direction: str, position: str):
        """Context menu: wrap cell in a split and insert a new sibling."""
        cmd = WrapAndInsertCommand(self.project, cell_id, direction, position,
                                    update_callback=self._refresh_and_update)
        self.undo_stack.push(cmd)

    def _ctx_insert_subcell(self, cell_id: str, position: str):
        """Context menu: insert a sibling sub-cell at the same nesting level."""
        cmd = InsertSubCellCommand(self.project, cell_id, position,
                                    update_callback=self._refresh_and_update)
        self.undo_stack.push(cmd)

    def _ctx_delete_subcell(self, cell_id: str):
        """Context menu: delete a sub-cell."""
        cmd = DeleteSubCellCommand(self.project, cell_id,
                                    update_callback=self._refresh_and_update)
        self.undo_stack.push(cmd)

    def _ctx_set_cell_prop(self, cell_id: str, changes: dict):
        """Context menu: set properties on a cell."""
        cell = self.project.find_cell_by_id(cell_id)
        if cell:
            cmd = PropertyChangeCommand(cell, changes, self._refresh_and_update, "Change Cell Property")
            self.undo_stack.push(cmd)

    def _on_auto_label(self):
        cmd = AutoLabelCommand(self.project, self._refresh_and_update)
        self.undo_stack.push(cmd)

    def _on_auto_layout(self):
        cmd = AutoLayoutCommand(self.project, self._refresh_and_update)
        self.undo_stack.push(cmd)

    def _get_export_default_dir(self) -> str:
        """Return directory of current project file, or empty string if none."""
        if self._current_project_path:
            return os.path.dirname(self._current_project_path)
        return ""

    def _on_export_pdf(self):
        default_dir = self._get_export_default_dir()
        path, _ = QFileDialog.getSaveFileName(self, "Export PDF", default_dir, "PDF Files (*.pdf)")
        if path:
            PdfExporter.export(self.project, path)
            QMessageBox.information(self, "Export", f"Exported to {path}")

    def _on_export_tiff(self):
        default_dir = self._get_export_default_dir()
        path, _ = QFileDialog.getSaveFileName(self, "Export TIFF", default_dir, "TIFF Files (*.tiff *.tif)")
        if path:
            ImageExporter.export(self.project, path, "TIFF")
            QMessageBox.information(self, "Export", f"Exported to {path}")

    def _on_export_jpg(self):
        default_dir = self._get_export_default_dir()
        path, _ = QFileDialog.getSaveFileName(self, "Export JPG", default_dir, "JPEG Files (*.jpg *.jpeg)")
        if path:
            ImageExporter.export(self.project, path, "JPG")
            QMessageBox.information(self, "Export", f"Exported to {path}")

    def _on_show_about(self):
        """Show About dialog with version information."""
        QMessageBox.about(
            self,
            "About Academic Figure Layout",
            f"<h2>Academic Figure Layout</h2>"
            f"<p><b>Version:</b> {self._app_version}</p>"
            f"<p>A tool for creating academic figure layouts with precise control.</p>"
        )

    def _on_open_nested_layout(self, cell_id: str, figlayout_path: str):
        """Open a nested layout in a separate editor window."""
        import os
        if not os.path.exists(figlayout_path):
            QMessageBox.warning(self, "Error", f"Layout file not found:\n{figlayout_path}")
            return
        try:
            project = Project.load_from_file(figlayout_path)
            child_window = MainWindow()
            child_window._set_project(project, figlayout_path)
            child_window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
            # When child saves, refresh the parent cell's thumbnail
            child_window._parent_cell_id = cell_id
            child_window._parent_window = self
            original_save = child_window._save_project_to_path

            def _save_and_refresh(path):
                result = original_save(path)
                if result:
                    self._refresh_and_update()
                return result

            child_window._save_project_to_path = _save_and_refresh
            child_window.show()
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to open nested layout: {e}")

    def closeEvent(self, event):
        if not self._maybe_save():
            event.ignore()
            return
        try:
            get_image_proxy().shutdown()
        except Exception:
            pass
        super().closeEvent(event)

    def _on_new_project(self):
        if not self._maybe_save():
            return

        project = Project()
        project.rows = [
            RowTemplate(index=0, column_count=2, height_ratio=1.0),
            RowTemplate(index=1, column_count=2, height_ratio=1.0)
        ]
        self._set_project(project, None)

    def _on_open_project(self):
        if not self._maybe_save():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Open Project", "", "Figure Layout (*.figlayout);;JSON (*.json)")
        if path:
            try:
                project = Project.load_from_file(path)
                self._set_project(project, path)
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to open project: {e}")

    def _on_save_project(self):
        if self._current_project_path:
            return self._save_project_to_path(self._current_project_path)
        return self._on_save_project_as()

    def _on_save_project_as(self) -> bool:
        path, _ = QFileDialog.getSaveFileName(self, "Save Project As", "", "Figure Layout (*.figlayout);;JSON (*.json)")
        if not path:
            return False
        return self._save_project_to_path(path)

    def _save_project_to_path(self, path: str) -> bool:
        try:
            self.project.name = os.path.splitext(os.path.basename(path))[0]
            self.project.save_to_file(path)
            self._current_project_path = path
            self.undo_stack.setClean()
            self.setWindowModified(False)
            self._update_window_title()
            return True
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to save project: {e}")
            return False

    def _on_import_images(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Import Images", "", 
            "Images (*.png *.jpg *.jpeg *.tif *.tiff *.bmp *.gif *.webp *.svg *.pdf *.eps);;All Files (*)"
        )
        if paths:
            for file_path in paths:
                # Find first placeholder
                target_cell = None
                for cell in self.project.get_all_leaf_cells():
                    if cell.is_placeholder:
                        target_cell = cell
                        break

                if target_cell:
                    cmd = DropImageCommand(target_cell, file_path, self._refresh_and_update)
                    self.undo_stack.push(cmd)
                else:
                    # No more placeholders
                    QMessageBox.information(
                        self,
                        "Import",
                        f"No more placeholder cells available. {len(paths) - paths.index(file_path)} images not imported."
                    )
                    break

    def _on_open_images_as_grid(self):
        if not self._maybe_save():
            return

        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Open Images as Grid",
            "",
            "Images (*.png *.jpg *.jpeg *.tif *.tiff *.bmp *.gif *.webp *.svg *.pdf *.eps);;All Files (*)",
        )
        if not paths:
            return

        project = self._build_project_from_images(paths)
        self._set_project(project, None)

        cmd = AutoLayoutCommand(self.project, self._refresh_and_update)
        self.undo_stack.push(cmd)

    def _on_reload_images(self):
        """Clear image cache and refresh canvas to reload all images from disk."""
        get_image_proxy().clear_cache()
        self._refresh_and_update()

    def _on_project_file_dropped(self, file_path: str):
        """Handle drag and drop of .figlayout project files."""
        if not self._maybe_save():
            return
        try:
            project = Project.load_from_file(file_path)
            self._set_project(project, file_path)
        except Exception as e:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Error", f"Failed to open project: {e}")
