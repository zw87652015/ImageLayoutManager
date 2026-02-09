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

class MultiSwapCellsCommand(QUndoCommand):
    """Swap content of N source cells with N target cells pairwise."""
    SWAP_ATTRS = (
        'image_path', 'is_placeholder', 'fit_mode', 'rotation',
        'padding_top', 'padding_bottom', 'padding_left', 'padding_right',
    )

    def __init__(self, sources, targets, update_callback=None):
        super().__init__(f"Move {len(sources)} Cells")
        self.sources = sources
        self.targets = targets
        self.update_callback = update_callback

    def redo(self):
        self._swap()

    def undo(self):
        self._swap()

    def _swap(self):
        for src, tgt in zip(self.sources, self.targets):
            for attr in self.SWAP_ATTRS:
                v1 = getattr(src, attr)
                v2 = getattr(tgt, attr)
                setattr(src, attr, v2)
                setattr(tgt, attr, v1)
        if self.update_callback:
            self.update_callback()


class InsertRowCommand(QUndoCommand):
    """Insert a new row at a given index, shifting subsequent rows down."""
    def __init__(self, project, insert_index, column_count=2, update_callback=None):
        super().__init__(f"Insert Row at {insert_index}")
        self.project = project
        self.insert_index = insert_index
        self.column_count = column_count
        self.update_callback = update_callback
        import copy
        self.old_rows = copy.deepcopy(project.rows)
        self.old_cells = copy.deepcopy(project.cells)

    def redo(self):
        from src.model.data_model import RowTemplate, Cell
        # Shift existing rows and their cells
        for r in self.project.rows:
            if r.index >= self.insert_index:
                r.index += 1
        for c in self.project.cells:
            if c.row_index >= self.insert_index:
                c.row_index += 1
        # Create the new row and its cells
        new_row = RowTemplate(index=self.insert_index, column_count=self.column_count)
        self.project.rows.append(new_row)
        self.project.rows.sort(key=lambda r: r.index)
        for col in range(self.column_count):
            self.project.cells.append(
                Cell(row_index=self.insert_index, col_index=col, is_placeholder=True)
            )
        if self.update_callback:
            self.update_callback()

    def undo(self):
        import copy
        self.project.rows[:] = copy.deepcopy(self.old_rows)
        self.project.cells[:] = copy.deepcopy(self.old_cells)
        if self.update_callback:
            self.update_callback()


class InsertCellCommand(QUndoCommand):
    """Insert a new placeholder cell into a row at a given column index."""
    def __init__(self, project, row_index, insert_col, update_callback=None):
        super().__init__(f"Insert Cell at R{row_index}C{insert_col}")
        self.project = project
        self.row_index = row_index
        self.insert_col = insert_col
        self.update_callback = update_callback
        import copy
        self.old_rows = copy.deepcopy(project.rows)
        self.old_cells = copy.deepcopy(project.cells)

    def redo(self):
        from src.model.data_model import Cell
        row = next((r for r in self.project.rows if r.index == self.row_index), None)
        if not row:
            return
        # Shift cells in this row at col >= insert_col
        for c in self.project.cells:
            if c.row_index == self.row_index and c.col_index >= self.insert_col:
                c.col_index += 1
        # Increment column count
        row.column_count += 1
        # Add new placeholder cell
        self.project.cells.append(
            Cell(row_index=self.row_index, col_index=self.insert_col, is_placeholder=True)
        )
        if self.update_callback:
            self.update_callback()

    def undo(self):
        import copy
        self.project.rows[:] = copy.deepcopy(self.old_rows)
        self.project.cells[:] = copy.deepcopy(self.old_cells)
        if self.update_callback:
            self.update_callback()


class DeleteRowCommand(QUndoCommand):
    """Delete an entire row and its cells, shifting subsequent rows up."""
    def __init__(self, project, row_index, update_callback=None):
        super().__init__(f"Delete Row {row_index}")
        self.project = project
        self.row_index = row_index
        self.update_callback = update_callback
        import copy
        self.old_rows = copy.deepcopy(project.rows)
        self.old_cells = copy.deepcopy(project.cells)

    def redo(self):
        # Remove the row template
        self.project.rows[:] = [r for r in self.project.rows if r.index != self.row_index]
        # Remove cells in this row
        self.project.cells[:] = [c for c in self.project.cells if c.row_index != self.row_index]
        # Shift subsequent rows and cells up
        for r in self.project.rows:
            if r.index > self.row_index:
                r.index -= 1
        for c in self.project.cells:
            if c.row_index > self.row_index:
                c.row_index -= 1
        if self.update_callback:
            self.update_callback()

    def undo(self):
        import copy
        self.project.rows[:] = copy.deepcopy(self.old_rows)
        self.project.cells[:] = copy.deepcopy(self.old_cells)
        if self.update_callback:
            self.update_callback()


class DeleteCellCommand(QUndoCommand):
    """Delete a single cell from a row, shifting subsequent cells left."""
    def __init__(self, project, row_index, col_index, update_callback=None):
        super().__init__(f"Delete Cell R{row_index}C{col_index}")
        self.project = project
        self.row_index = row_index
        self.col_index = col_index
        self.update_callback = update_callback
        import copy
        self.old_rows = copy.deepcopy(project.rows)
        self.old_cells = copy.deepcopy(project.cells)

    def redo(self):
        row = next((r for r in self.project.rows if r.index == self.row_index), None)
        if not row or row.column_count <= 1:
            return  # Don't delete the last cell in a row
        # Remove the cell
        self.project.cells[:] = [
            c for c in self.project.cells
            if not (c.row_index == self.row_index and c.col_index == self.col_index)
        ]
        # Shift subsequent cells left
        for c in self.project.cells:
            if c.row_index == self.row_index and c.col_index > self.col_index:
                c.col_index -= 1
        row.column_count -= 1
        if self.update_callback:
            self.update_callback()

    def undo(self):
        import copy
        self.project.rows[:] = copy.deepcopy(self.old_rows)
        self.project.cells[:] = copy.deepcopy(self.old_cells)
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

class SplitCellCommand(QUndoCommand):
    """Split a leaf cell into N sub-cells in a given direction."""
    def __init__(self, project, cell_id, direction, count=2, update_callback=None):
        super().__init__(f"Split Cell {direction}")
        self.project = project
        self.cell_id = cell_id
        self.direction = direction  # "horizontal" or "vertical"
        self.count = count
        self.update_callback = update_callback
        import copy
        self.old_cells = copy.deepcopy(project.cells)

    def redo(self):
        from src.model.data_model import Cell
        cell = self.project.find_cell_by_id(self.cell_id)
        if not cell or not cell.is_leaf:
            return
        # Move current content to the first child; create empty placeholders for the rest
        first_child = Cell(
            image_path=cell.image_path,
            fit_mode=cell.fit_mode,
            rotation=cell.rotation,
            align_h=cell.align_h,
            align_v=cell.align_v,
            padding_top=cell.padding_top,
            padding_bottom=cell.padding_bottom,
            padding_left=cell.padding_left,
            padding_right=cell.padding_right,
            is_placeholder=cell.is_placeholder,
            nested_layout_path=cell.nested_layout_path,
            scale_bar_enabled=cell.scale_bar_enabled,
            scale_bar_mode=cell.scale_bar_mode,
            scale_bar_length_um=cell.scale_bar_length_um,
            scale_bar_color=cell.scale_bar_color,
            scale_bar_show_text=cell.scale_bar_show_text,
            scale_bar_thickness_mm=cell.scale_bar_thickness_mm,
            scale_bar_position=cell.scale_bar_position,
            scale_bar_offset_x=cell.scale_bar_offset_x,
            scale_bar_offset_y=cell.scale_bar_offset_y,
        )
        children = [first_child]
        for _ in range(1, self.count):
            children.append(Cell(is_placeholder=True))
        cell.children = children
        cell.split_direction = self.direction
        cell.split_ratios = [1.0] * self.count
        # Clear the parent's content (it's now a container)
        cell.image_path = None
        cell.is_placeholder = False
        cell.nested_layout_path = None
        cell.scale_bar_enabled = False
        if self.update_callback:
            self.update_callback()

    def undo(self):
        import copy
        self.project.cells[:] = copy.deepcopy(self.old_cells)
        if self.update_callback:
            self.update_callback()


class InsertSubCellCommand(QUndoCommand):
    """Insert a new placeholder sub-cell as a sibling of a given cell."""
    def __init__(self, project, cell_id, position, update_callback=None):
        super().__init__(f"Insert Sub-Cell {position}")
        self.project = project
        self.cell_id = cell_id
        self.position = position  # "before" or "after"
        self.update_callback = update_callback
        import copy
        self.old_cells = copy.deepcopy(project.cells)

    def redo(self):
        from src.model.data_model import Cell
        parent = self.project.find_parent_of(self.cell_id)
        if not parent:
            # Top-level cell: wrap it in a split
            return
        idx = next((i for i, c in enumerate(parent.children) if c.id == self.cell_id), None)
        if idx is None:
            return
        insert_at = idx if self.position == "before" else idx + 1
        new_cell = Cell(is_placeholder=True)
        parent.children.insert(insert_at, new_cell)
        # Update split_ratios: insert 1.0 at the same position
        while len(parent.split_ratios) < len(parent.children) - 1:
            parent.split_ratios.append(1.0)
        parent.split_ratios.insert(insert_at, 1.0)
        if self.update_callback:
            self.update_callback()

    def undo(self):
        import copy
        self.project.cells[:] = copy.deepcopy(self.old_cells)
        if self.update_callback:
            self.update_callback()


class DeleteSubCellCommand(QUndoCommand):
    """Delete a sub-cell from its parent's children. If only one child remains, unwrap it."""
    def __init__(self, project, cell_id, update_callback=None):
        super().__init__("Delete Sub-Cell")
        self.project = project
        self.cell_id = cell_id
        self.update_callback = update_callback
        import copy
        self.old_cells = copy.deepcopy(project.cells)

    def redo(self):
        parent = self.project.find_parent_of(self.cell_id)
        if not parent or len(parent.children) <= 1:
            return
        idx = next((i for i, c in enumerate(parent.children) if c.id == self.cell_id), None)
        if idx is None:
            return
        parent.children.pop(idx)
        if idx < len(parent.split_ratios):
            parent.split_ratios.pop(idx)
        # If only one child remains, unwrap: promote child's content to parent
        if len(parent.children) == 1:
            sole = parent.children[0]
            parent.children = sole.children
            parent.split_direction = sole.split_direction
            parent.split_ratios = sole.split_ratios
            parent.image_path = sole.image_path
            parent.is_placeholder = sole.is_placeholder
            parent.fit_mode = sole.fit_mode
            parent.rotation = sole.rotation
            parent.nested_layout_path = sole.nested_layout_path
            parent.scale_bar_enabled = sole.scale_bar_enabled
            if not parent.children:
                parent.split_direction = "none"
                parent.split_ratios = []
        if self.update_callback:
            self.update_callback()

    def undo(self):
        import copy
        self.project.cells[:] = copy.deepcopy(self.old_cells)
        if self.update_callback:
            self.update_callback()


class WrapAndInsertCommand(QUndoCommand):
    """Wrap a cell (top-level or sub-cell) in a new split and insert a sibling.
    
    Used when inserting above/below a cell that isn't already in a matching
    split direction, or when inserting left/right in a vertical split, etc.
    """
    def __init__(self, project, cell_id, direction, position, update_callback=None):
        super().__init__(f"Insert Cell {position}")
        self.project = project
        self.cell_id = cell_id
        self.direction = direction  # "horizontal" or "vertical"
        self.position = position    # "before" or "after"
        self.update_callback = update_callback
        import copy
        self.old_cells = copy.deepcopy(project.cells)

    def redo(self):
        from src.model.data_model import Cell
        cell = self.project.find_cell_by_id(self.cell_id)
        if not cell:
            return
        parent = self.project.find_parent_of(self.cell_id)

        if parent and parent.split_direction == self.direction:
            # Parent already splits in the right direction → insert sibling
            idx = next((i for i, c in enumerate(parent.children) if c.id == self.cell_id), None)
            if idx is None:
                return
            insert_at = idx if self.position == "before" else idx + 1
            new_cell = Cell(is_placeholder=True)
            parent.children.insert(insert_at, new_cell)
            while len(parent.split_ratios) < len(parent.children) - 1:
                parent.split_ratios.append(1.0)
            parent.split_ratios.insert(insert_at, 1.0)
        else:
            # Need to wrap: replace this cell in-place with a split container
            # Save current cell state into a clone
            import copy
            clone = copy.deepcopy(cell)
            new_cell = Cell(is_placeholder=True)

            if self.position == "before":
                children = [new_cell, clone]
            else:
                children = [clone, new_cell]

            # Transform `cell` into a container
            cell.children = children
            cell.split_direction = self.direction
            cell.split_ratios = [1.0, 1.0]
            cell.image_path = None
            cell.is_placeholder = False
            cell.nested_layout_path = None
            cell.scale_bar_enabled = False

        if self.update_callback:
            self.update_callback()

    def undo(self):
        import copy
        self.project.cells[:] = copy.deepcopy(self.old_cells)
        if self.update_callback:
            self.update_callback()


class ChangeSubCellRatioCommand(QUndoCommand):
    """Change the size ratio of a single sub-cell within its parent's split_ratios."""
    def __init__(self, project, cell_id, new_ratio, update_callback=None):
        super().__init__("Change Sub-Cell Ratio")
        self.project = project
        self.cell_id = cell_id
        self.new_ratio = new_ratio
        self.update_callback = update_callback
        import copy
        self.old_cells = copy.deepcopy(project.cells)

    def redo(self):
        parent = self.project.find_parent_of(self.cell_id)
        if not parent:
            return
        idx = next((i for i, c in enumerate(parent.children) if c.id == self.cell_id), None)
        if idx is None:
            return
        while len(parent.split_ratios) < len(parent.children):
            parent.split_ratios.append(1.0)
        parent.split_ratios[idx] = self.new_ratio
        if self.update_callback:
            self.update_callback()

    def undo(self):
        import copy
        self.project.cells[:] = copy.deepcopy(self.old_cells)
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

