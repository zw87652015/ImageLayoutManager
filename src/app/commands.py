from PyQt6.QtGui import QUndoCommand

class PropertyChangeCommand(QUndoCommand):
    def __init__(self, target, changes: dict, update_callback=None, description="Change Property"):
        super().__init__(description)
        self.target = target
        self.changes = changes
        self.old_values = {}
        self.update_callback = update_callback
        
        # Capture old values
        for k in changes.keys():
            if hasattr(target, k):
                self.old_values[k] = getattr(target, k)

    def redo(self):
        for k, v in self.changes.items():
            if hasattr(self.target, k):
                setattr(self.target, k, v)
        if self.update_callback:
            self.update_callback()

    def undo(self):
        for k, v in self.old_values.items():
            if hasattr(self.target, k):
                setattr(self.target, k, v)
        if self.update_callback:
            self.update_callback()

class MultiPropertyChangeCommand(QUndoCommand):
    """Apply the same property changes to multiple targets (e.g., multiple cells)."""
    def __init__(self, targets: list, changes: dict, update_callback=None, description="Change Properties"):
        super().__init__(description)
        self.targets = targets
        self.changes = changes
        self.old_values = []  # List of dicts, one per target
        self.update_callback = update_callback
        
        # Capture old values for each target
        for target in targets:
            old = {}
            for k in changes.keys():
                if hasattr(target, k):
                    old[k] = getattr(target, k)
            self.old_values.append(old)

    def redo(self):
        for target in self.targets:
            for k, v in self.changes.items():
                if hasattr(target, k):
                    setattr(target, k, v)
        if self.update_callback:
            self.update_callback()

    def undo(self):
        for target, old in zip(self.targets, self.old_values):
            for k, v in old.items():
                if hasattr(target, k):
                    setattr(target, k, v)
        if self.update_callback:
            self.update_callback()

class SwapCellsCommand(QUndoCommand):
    def __init__(self, c1, c2, update_callback=None):
        super().__init__("Swap Cells")
        self.c1 = c1
        self.c2 = c2
        self.update_callback = update_callback

    def redo(self):
        self._swap()

    def undo(self):
        self._swap()

    def _swap(self):
        # Swap content attributes
        self.c1.image_path, self.c2.image_path = self.c2.image_path, self.c1.image_path
        self.c1.is_placeholder, self.c2.is_placeholder = self.c2.is_placeholder, self.c1.is_placeholder
        self.c1.fit_mode, self.c2.fit_mode = self.c2.fit_mode, self.c1.fit_mode
        self.c1.rotation, self.c2.rotation = self.c2.rotation, self.c1.rotation
        
        # Swap padding too
        self.c1.padding_top, self.c2.padding_top = self.c2.padding_top, self.c1.padding_top
        self.c1.padding_bottom, self.c2.padding_bottom = self.c2.padding_bottom, self.c1.padding_bottom
        self.c1.padding_left, self.c2.padding_left = self.c2.padding_left, self.c1.padding_left
        self.c1.padding_right, self.c2.padding_right = self.c2.padding_right, self.c1.padding_right
        
        if self.update_callback:
            self.update_callback()

class DropImageCommand(QUndoCommand):
    def __init__(self, cell, new_path, update_callback=None):
        super().__init__("Drop Image")
        self.cell = cell
        self.new_path = new_path
        self.old_path = cell.image_path
        self.old_is_placeholder = cell.is_placeholder
        self.update_callback = update_callback

    def redo(self):
        self.cell.image_path = self.new_path
        self.cell.is_placeholder = False
        if self.update_callback:
            self.update_callback()

    def undo(self):
        self.cell.image_path = self.old_path
        self.cell.is_placeholder = self.old_is_placeholder
        if self.update_callback:
            self.update_callback()

class ChangeRowCountCommand(QUndoCommand):
    def __init__(self, project, new_count, update_callback=None):
        super().__init__(f"Change Rows to {new_count}")
        self.project = project
        self.new_count = new_count
        self.update_callback = update_callback
        
        # Snapshot state
        import copy
        self.old_rows = copy.deepcopy(project.rows)
        self.old_cells = copy.deepcopy(project.cells)

    def redo(self):
        # Logic duplicated/moved from MainWindow._on_row_count_changed
        from src.model.data_model import RowTemplate, Cell
        
        current_count = len(self.project.rows)
        if self.new_count > current_count:
            # Add rows
            for i in range(current_count, self.new_count):
                self.project.rows.append(RowTemplate(index=i, column_count=2))
        elif self.new_count < current_count:
            # Remove rows
            self.project.rows[:] = self.project.rows[:self.new_count]
            
        # Ensure cells exist (simplified logic from MainWindow)
        # We need to access the logic or replicate it. 
        # Replicating strictly for the command to be self-contained or passing a helper.
        # For simplicity, we'll replicate the essential "ensure" logic here.
        
        # 1. Keep valid cells
        valid_cells = []
        existing_map = {} 
        for c in self.project.cells:
            row_temp = next((r for r in self.project.rows if r.index == c.row_index), None)
            if row_temp and c.col_index < row_temp.column_count:
                valid_cells.append(c)
                existing_map[(c.row_index, c.col_index)] = c
        self.project.cells[:] = valid_cells
        
        # 2. Add missing cells
        for r in self.project.rows:
            for col_idx in range(r.column_count):
                if (r.index, col_idx) not in existing_map:
                    new_cell = Cell(row_index=r.index, col_index=col_idx, is_placeholder=True)
                    self.project.cells.append(new_cell)

        if self.update_callback:
            self.update_callback()

    def undo(self):
        # Restore state
        import copy
        self.project.rows[:] = copy.deepcopy(self.old_rows)
        self.project.cells[:] = copy.deepcopy(self.old_cells)
        if self.update_callback:
            self.update_callback()

class AddTextCommand(QUndoCommand):
    def __init__(self, project, item, update_callback=None):
        super().__init__("Add Text")
        self.project = project
        self.item = item
        self.update_callback = update_callback

    def redo(self):
        self.project.text_items.append(self.item)
        if self.update_callback:
            self.update_callback()

    def undo(self):
        if self.item in self.project.text_items:
            self.project.text_items.remove(self.item)
        if self.update_callback:
            self.update_callback()

class DeleteTextCommand(QUndoCommand):
    def __init__(self, project, item, update_callback=None):
        super().__init__("Delete Text")
        self.project = project
        self.item = item
        self.update_callback = update_callback

    def redo(self):
        if self.item in self.project.text_items:
            self.project.text_items.remove(self.item)
        if self.update_callback:
            self.update_callback()

    def undo(self):
        self.project.text_items.append(self.item)
        if self.update_callback:
            self.update_callback()

class AutoLabelCommand(QUndoCommand):
    def __init__(self, project, update_callback=None):
        super().__init__("Auto Label")
        self.project = project
        self.update_callback = update_callback
        # Snapshot text items
        import copy
        self.old_text_items = copy.deepcopy(project.text_items)

    def redo(self):
        from src.utils.auto_label import AutoLabel
        AutoLabel.generate_labels(self.project)
        if self.update_callback:
            self.update_callback()

    def undo(self):
        import copy
        self.project.text_items[:] = copy.deepcopy(self.old_text_items)
        if self.update_callback:
            self.update_callback()

class AutoLayoutCommand(QUndoCommand):
    def __init__(self, project, update_callback=None):
        super().__init__("Auto Layout")
        self.project = project
        self.update_callback = update_callback
        
        # Snapshot rows settings and page height
        import copy
        self.old_rows = copy.deepcopy(project.rows)
        self.old_page_height = project.page_height_mm

    def redo(self):
        from src.utils.auto_layout import AutoLayout
        # Calculate new layout settings
        new_settings = AutoLayout.optimize_layout(self.project)
        
        # Apply changes to project rows
        for i, row_data in enumerate(new_settings['rows']):
            if i < len(self.project.rows):
                row = self.project.rows[i]
                row.height_ratio = row_data.get('height_ratio', 1.0)
                row.column_ratios = row_data.get('column_ratios', [])
        
        # Apply optimal page height if calculated
        if 'optimal_page_height_mm' in new_settings:
            self.project.page_height_mm = new_settings['optimal_page_height_mm']
                
        if self.update_callback:
            self.update_callback()

    def undo(self):
        import copy
        self.project.rows[:] = copy.deepcopy(self.old_rows)
        self.project.page_height_mm = self.old_page_height
        if self.update_callback:
            self.update_callback()

