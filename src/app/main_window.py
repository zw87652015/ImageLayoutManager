import os
import math
from typing import Optional
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QToolBar, QPushButton, QSplitter, QFileDialog,
    QMessageBox, QSpinBox, QLabel, QComboBox,
    QLabel, QStyle
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
    PropertyChangeCommand, MultiPropertyChangeCommand, SwapCellsCommand, DropImageCommand,
    ChangeRowCountCommand, AddTextCommand, DeleteTextCommand, AutoLabelCommand, AutoLayoutCommand
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
        self.toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.toolbar.setIconSize(QSize(18, 18))
        self.addToolBar(self.toolbar)

        # Menu
        file_menu = self.menuBar().addMenu("File")

        # Help menu
        help_menu = self.menuBar().addMenu("Help")
        about_action = QAction("About", self)
        about_action.triggered.connect(self._on_show_about)
        help_menu.addAction(about_action)

        # Undo/Redo Actions
        undo_action = self.undo_stack.createUndoAction(self, "Undo")
        undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        undo_action.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowBack))
        undo_action.setToolTip("Undo")
        redo_action = self.undo_stack.createRedoAction(self, "Redo")
        redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        redo_action.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowForward))
        redo_action.setToolTip("Redo")
        
        self.toolbar.addAction(undo_action)
        self.toolbar.addAction(redo_action)
        self.toolbar.addSeparator()
        
        # File Actions
        new_action = QAction("New", self)
        new_action.setShortcut(QKeySequence.StandardKey.New)
        new_action.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon))
        new_action.setToolTip("New")
        new_action.triggered.connect(self._on_new_project)
        self.toolbar.addAction(new_action)

        file_menu.addAction(new_action)
        
        open_action = QAction("Open", self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton))
        open_action.setToolTip("Open")
        open_action.triggered.connect(self._on_open_project)
        self.toolbar.addAction(open_action)

        file_menu.addAction(open_action)
        
        save_action = QAction("Save", self)
        save_action.setShortcut(QKeySequence.StandardKey.Save)
        save_action.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton))
        save_action.setToolTip("Save")
        save_action.triggered.connect(self._on_save_project)
        self.toolbar.addAction(save_action)

        file_menu.addAction(save_action)

        save_as_action = QAction("Save As...", self)
        save_as_action.setShortcut(QKeySequence.StandardKey.SaveAs)
        save_as_action.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton))
        save_as_action.triggered.connect(self._on_save_project_as)
        file_menu.addAction(save_as_action)

        open_images_grid_action = QAction("Open Images as Grid...", self)
        open_images_grid_action.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogContentsView))
        open_images_grid_action.triggered.connect(self._on_open_images_as_grid)
        file_menu.addAction(open_images_grid_action)
        
        self.toolbar.addSeparator()
        
        import_action = QAction("Import Images", self)
        import_action.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon))
        import_action.setToolTip("Import Images")
        import_action.triggered.connect(self._on_import_images)
        self.toolbar.addAction(import_action)

        open_images_grid_tb_action = QAction("Open Images as Grid", self)
        open_images_grid_tb_action.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogContentsView))
        open_images_grid_tb_action.setToolTip("Open Images as Grid")
        open_images_grid_tb_action.triggered.connect(self._on_open_images_as_grid)
        self.toolbar.addAction(open_images_grid_tb_action)
        
        reload_images_action = QAction("Reload Images", self)
        reload_images_action.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload))
        reload_images_action.setToolTip("Reload all images from disk (refresh cache)")
        reload_images_action.setShortcut(QKeySequence("F5"))
        reload_images_action.triggered.connect(self._on_reload_images)
        self.toolbar.addAction(reload_images_action)
        
        self.toolbar.addSeparator()
        
        # Toolbar Actions
        # Grid Controls
        self.toolbar.addWidget(QLabel(" Rows: "))
        self.row_spin = QSpinBox()
        self.row_spin.setRange(1, 100)
        self.row_spin.setValue(len(self.project.rows))
        self.row_spin.valueChanged.connect(self._on_row_count_changed)
        self.toolbar.addWidget(self.row_spin)
        
        self.toolbar.addSeparator()
        
        add_text_action = QAction("Add Text", self)
        add_text_action.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView))
        add_text_action.setToolTip("Add Text")
        add_text_action.triggered.connect(self._on_add_text)
        self.toolbar.addAction(add_text_action)
        
        delete_text_action = QAction("Delete Text", self)
        delete_text_action.setShortcut(QKeySequence.StandardKey.Delete)
        delete_text_action.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_TrashIcon))
        delete_text_action.setToolTip("Delete Text")
        delete_text_action.triggered.connect(self._on_delete_text)
        self.toolbar.addAction(delete_text_action)

        delete_image_action = QAction("Delete Image", self)
        delete_image_action.setShortcut(QKeySequence("Ctrl+Delete"))
        delete_image_action.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_TrashIcon))
        delete_image_action.setToolTip("Delete Image from selected cell(s)")
        delete_image_action.triggered.connect(self._on_delete_image)
        self.toolbar.addAction(delete_image_action)
        
        auto_label_action = QAction("Auto Label", self)
        auto_label_action.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogApplyButton))
        auto_label_action.setToolTip("Auto Label")
        auto_label_action.triggered.connect(self._on_auto_label)
        self.toolbar.addAction(auto_label_action)
        
        auto_layout_action = QAction("Auto Layout", self)
        auto_layout_action.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload))
        auto_layout_action.setToolTip("Auto Layout")
        auto_layout_action.triggered.connect(self._on_auto_layout)
        self.toolbar.addAction(auto_layout_action)
        
        self.toolbar.addSeparator()
        
        export_action = QAction("Export PDF", self)
        export_action.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DriveFDIcon))
        export_action.setToolTip("Export PDF")
        export_action.triggered.connect(self._on_export_pdf)
        self.toolbar.addAction(export_action)
        
        export_tiff_action = QAction("Export TIFF", self)
        export_tiff_action.setToolTip("Export as TIFF image")
        export_tiff_action.triggered.connect(self._on_export_tiff)
        self.toolbar.addAction(export_tiff_action)
        
        export_jpg_action = QAction("Export JPG", self)
        export_jpg_action.setToolTip("Export as JPG image")
        export_jpg_action.triggered.connect(self._on_export_jpg)
        self.toolbar.addAction(export_jpg_action)

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
        
        # Set initial sizes
        splitter.setSizes([900, 300])
        
        # Status Bar
        self.statusbar = self.statusBar()
        self.zoom_label = QLabel("Zoom: 100%")
        self.canvas_size_label = QLabel("Canvas: -")
        self.statusbar.addPermanentWidget(self.canvas_size_label)
        self.statusbar.addPermanentWidget(self.zoom_label)

    def _connect_signals(self):
        # Scene signals
        self.scene.cell_dropped.connect(self._on_cell_image_dropped)
        self.scene.cell_swapped.connect(self._on_cell_swapped)
        self.scene.new_image_dropped.connect(self._on_new_image_dropped)
        self.scene.project_file_dropped.connect(self._on_project_file_dropped)
        self.scene.text_item_changed.connect(self._on_text_item_drag_changed)
        self.scene.selectionChanged.connect(self._on_selection_changed)
        
        # View signals
        self.view.zoom_changed.connect(self._on_zoom_changed)
        
        # Inspector signals
        self.inspector.cell_property_changed.connect(self._on_cell_property_changed)
        self.inspector.text_property_changed.connect(self._on_text_property_changed)
        self.inspector.row_property_changed.connect(self._on_row_property_changed)
        self.inspector.project_property_changed.connect(self._on_project_property_changed)
        self.inspector.corner_label_changed.connect(self._on_corner_label_changed)
        self.inspector.apply_color_to_group.connect(self._on_apply_color_to_group)

        self.undo_stack.cleanChanged.connect(self._on_undo_clean_changed)

    def _on_zoom_changed(self, zoom_level):
        self.zoom_label.setText(f"Zoom: {int(zoom_level * 100)}%")

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
        self.row_spin.setValue(len(self.project.rows))
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
        cell = next((c for c in self.project.cells if c.id == cell_id), None)
        if cell:
            cmd = DropImageCommand(cell, file_path, self._refresh_and_update)
            self.undo_stack.push(cmd)

    def _on_new_image_dropped(self, file_path, x, y):
        # Find first placeholder
        target_cell = None
        for cell in self.project.cells:
            if cell.is_placeholder:
                target_cell = cell
                break
        
        if target_cell:
            cmd = DropImageCommand(target_cell, file_path, self._refresh_and_update)
            self.undo_stack.push(cmd)
        else:
            print("No placeholder available for new image")

    def _on_cell_swapped(self, id1, id2):
        c1 = next((c for c in self.project.cells if c.id == id1), None)
        c2 = next((c for c in self.project.cells if c.id == id2), None)
        
        if c1 and c2:
            cmd = SwapCellsCommand(c1, c2, self._refresh_and_update)
            self.undo_stack.push(cmd)

    def _on_selection_changed(self):
        try:
            items = self.scene.selectedItems()
        except RuntimeError:
            return  # Scene was deleted
        if not items:
            self.inspector.set_selection(None, self.project.to_dict())
            return
            
        item = items[0]
        
        if hasattr(item, 'cell_id'):
            cell = next((c for c in self.project.cells if c.id == item.cell_id), None)
            if cell:
                # Find Row Data
                row = next((r for r in self.project.rows if r.index == cell.row_index), None)
                row_data = row.to_dict() if row else None

                # Populate corner label fields from existing cell-scoped text items
                cell_dict = cell.to_dict()
                corner_labels = {}
                for t in self.project.text_items:
                    if t.scope == "cell" and t.parent_id == cell.id and t.anchor:
                        corner_labels[t.anchor] = t.text
                cell_dict["corner_labels"] = corner_labels

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
                cell = next((c for c in self.project.cells if c.id == item.cell_id), None)
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
        cell = next((c for c in self.project.cells if c.id == cell_id), None)
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
        cell = next((c for c in self.project.cells if c.id == cell_id), None)
        
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
            cell = next((c for c in self.project.cells if c.id == cell_item.cell_id), None)
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

    def _on_auto_label(self):
        cmd = AutoLabelCommand(self.project, self._refresh_and_update)
        self.undo_stack.push(cmd)

    def _on_auto_layout(self):
        cmd = AutoLayoutCommand(self.project, self._refresh_and_update)
        self.undo_stack.push(cmd)

    def _on_export_pdf(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export PDF", "", "PDF Files (*.pdf)")
        if path:
            PdfExporter.export(self.project, path)
            QMessageBox.information(self, "Export", f"Exported to {path}")

    def _on_export_tiff(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export TIFF", "", "TIFF Files (*.tiff *.tif)")
        if path:
            ImageExporter.export(self.project, path, "TIFF")
            QMessageBox.information(self, "Export", f"Exported to {path}")

    def _on_export_jpg(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export JPG", "", "JPEG Files (*.jpg *.jpeg)")
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
                for cell in self.project.cells:
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
