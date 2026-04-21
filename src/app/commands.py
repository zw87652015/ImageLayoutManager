from PyQt6.QtGui import QUndoCommand
import copy
import uuid
from src.model.data_model import RowTemplate, Cell, PiPItem


class FreeformGeometryCommand(QUndoCommand):
    """Record a freeform drag/resize of a single cell for undo/redo."""
    def __init__(self, cell: Cell, new_x, new_y, new_w, new_h, update_callback=None):
        super().__init__("Move/Resize Cell")
        self.cell = cell
        self.old_x = cell.freeform_x_mm
        self.old_y = cell.freeform_y_mm
        self.old_w = cell.freeform_w_mm
        self.old_h = cell.freeform_h_mm
        self.new_x = new_x
        self.new_y = new_y
        self.new_w = new_w
        self.new_h = new_h
        self.update_callback = update_callback

    def redo(self):
        self.cell.freeform_x_mm = self.new_x
        self.cell.freeform_y_mm = self.new_y
        self.cell.freeform_w_mm = self.new_w
        self.cell.freeform_h_mm = self.new_h
        if self.update_callback:
            self.update_callback()

    def undo(self):
        self.cell.freeform_x_mm = self.old_x
        self.cell.freeform_y_mm = self.old_y
        self.cell.freeform_w_mm = self.old_w
        self.cell.freeform_h_mm = self.old_h
        if self.update_callback:
            self.update_callback()

    def id(self):
        # Must return a value in range [-2147483648, 2147483647] (Qt 32-bit int)
        return hash(self.cell.id) & 0x7FFFFFFF

    def mergeWith(self, other):
        """Collapse consecutive moves of the same cell into a single undo step."""
        if not isinstance(other, FreeformGeometryCommand) or other.cell is not self.cell:
            return False
        self.new_x = other.new_x
        self.new_y = other.new_y
        self.new_w = other.new_w
        self.new_h = other.new_h
        return True


class FreeformLayoutModeCommand(QUndoCommand):
    """Switch project between 'grid' and 'freeform' layout modes, with baking support."""
    def __init__(self, project, new_mode: str, baked_cell_rects: dict = None, update_callback=None):
        label = "Convert to Freeform" if new_mode == "freeform" else "Switch to Grid"
        super().__init__(label)
        self.project = project
        self.old_mode = project.layout_mode
        self.new_mode = new_mode
        self.update_callback = update_callback
        # Store old freeform coords for all cells (for undo of bake)
        self.old_freeform = {
            cell.id: (cell.freeform_x_mm, cell.freeform_y_mm,
                      cell.freeform_w_mm, cell.freeform_h_mm)
            for cell in project.get_all_leaf_cells()
        }
        # New coords to apply on redo (provided when baking from grid)
        self.baked_cell_rects = baked_cell_rects or {}

    def redo(self):
        self.project.layout_mode = self.new_mode
        for cell in self.project.get_all_leaf_cells():
            if cell.id in self.baked_cell_rects:
                x, y, w, h = self.baked_cell_rects[cell.id]
                cell.freeform_x_mm = x
                cell.freeform_y_mm = y
                cell.freeform_w_mm = w
                cell.freeform_h_mm = h
        if self.update_callback:
            self.update_callback()

    def undo(self):
        self.project.layout_mode = self.old_mode
        for cell in self.project.get_all_leaf_cells():
            if cell.id in self.old_freeform:
                x, y, w, h = self.old_freeform[cell.id]
                cell.freeform_x_mm = x
                cell.freeform_y_mm = y
                cell.freeform_w_mm = w
                cell.freeform_h_mm = h
        if self.update_callback:
            self.update_callback()


class DividerDragCommand(QUndoCommand):
    """Undoable command for dragging a row-height or column-width divider.

    For 'row' dividers: records old/new height_ratio for two adjacent rows.
    For 'col' dividers: records old/new column_ratios list for one row.
    """

    def __init__(self, project, div, update_callback=None):
        kind = div.kind
        label = "Resize Row" if kind == 'row' else "Resize Column"
        super().__init__(label)
        self.project = project
        self.kind = kind
        self.update_callback = update_callback

        if kind == 'row':
            self.row_a_idx = div.row_a
            self.row_b_idx = div.row_b
            # original_ratio_* captured at drag-start before any live updates
            self.old_ratio_a = div.original_ratio_a
            self.old_ratio_b = div.original_ratio_b
            self.new_ratio_a = div.ratio_a
            self.new_ratio_b = div.ratio_b
        else:
            self.row_index = div.row_index
            self.col_a = div.col_a
            self.col_b = div.col_b
            row = next((r for r in project.rows if r.index == div.row_index), None)
            # Build old ratios from original_ratio_* (pre-drag values)
            cur_ratios = list(row.column_ratios) if (row and row.column_ratios) else (
                [1.0] * row.column_count if row else [1.0, 1.0])
            while row and len(cur_ratios) < row.column_count:
                cur_ratios.append(1.0)
            old_ratios = cur_ratios[:]
            old_ratios[div.col_a] = div.original_ratio_a
            old_ratios[div.col_b] = div.original_ratio_b
            self.old_ratios = old_ratios
            new_ratios = cur_ratios[:]
            new_ratios[div.col_a] = div.ratio_a
            new_ratios[div.col_b] = div.ratio_b
            self.new_ratios = new_ratios

    def redo(self):
        if self.kind == 'row':
            row_a = next((r for r in self.project.rows if r.index == self.row_a_idx), None)
            row_b = next((r for r in self.project.rows if r.index == self.row_b_idx), None)
            if row_a:
                row_a.height_ratio = self.new_ratio_a
            if row_b:
                row_b.height_ratio = self.new_ratio_b
        else:
            row = next((r for r in self.project.rows if r.index == self.row_index), None)
            if row:
                row.column_ratios = self.new_ratios[:]
        if self.update_callback:
            self.update_callback()

    def undo(self):
        if self.kind == 'row':
            row_a = next((r for r in self.project.rows if r.index == self.row_a_idx), None)
            row_b = next((r for r in self.project.rows if r.index == self.row_b_idx), None)
            if row_a:
                row_a.height_ratio = self.old_ratio_a
            if row_b:
                row_b.height_ratio = self.old_ratio_b
        else:
            row = next((r for r in self.project.rows if r.index == self.row_index), None)
            if row:
                row.column_ratios = self.old_ratios[:]
        if self.update_callback:
            self.update_callback()


class SetExportRegionCommand(QUndoCommand):
    """Set or replace the project's export region (x, y, w, h in mm)."""
    def __init__(self, project, new_xywh, update_callback=None, description="Set Export Region"):
        super().__init__(description)
        from src.model.data_model import ExportRegion
        self.project = project
        self.ExportRegion = ExportRegion
        # Snapshot old region (may be None)
        old = project.export_region
        self.old_xywh = (old.x_mm, old.y_mm, old.w_mm, old.h_mm) if old else None
        self.new_xywh = tuple(new_xywh)
        self.update_callback = update_callback

    def _apply(self, xywh):
        if xywh is None:
            self.project.export_region = None
        else:
            x, y, w, h = xywh
            if self.project.export_region is None:
                self.project.export_region = self.ExportRegion(x_mm=x, y_mm=y, w_mm=w, h_mm=h)
            else:
                er = self.project.export_region
                er.x_mm = x; er.y_mm = y; er.w_mm = w; er.h_mm = h
        if self.update_callback:
            self.update_callback()

    def redo(self):
        self._apply(self.new_xywh)

    def undo(self):
        self._apply(self.old_xywh)


class ClearExportRegionCommand(QUndoCommand):
    """Remove the project's export region (restore default full-page export)."""
    def __init__(self, project, update_callback=None):
        super().__init__("Clear Export Region")
        from src.model.data_model import ExportRegion
        self.project = project
        self.ExportRegion = ExportRegion
        old = project.export_region
        self.old_xywh = (old.x_mm, old.y_mm, old.w_mm, old.h_mm) if old else None
        self.update_callback = update_callback

    def redo(self):
        self.project.export_region = None
        if self.update_callback:
            self.update_callback()

    def undo(self):
        if self.old_xywh is None:
            self.project.export_region = None
        else:
            x, y, w, h = self.old_xywh
            self.project.export_region = self.ExportRegion(x_mm=x, y_mm=y, w_mm=w, h_mm=h)
        if self.update_callback:
            self.update_callback()


class ZIndexChangeCommand(QUndoCommand):
    """Change z_index of one or more cells for bring-to-front / send-to-back."""
    def __init__(self, cells: list, delta: int, update_callback=None, description="Change Z-Order"):
        super().__init__(description)
        self.cells = cells
        self.delta = delta
        self.update_callback = update_callback
        self.old_values = {cell.id: cell.z_index for cell in cells}

    def redo(self):
        for cell in self.cells:
            cell.z_index += self.delta
        if self.update_callback:
            self.update_callback()

    def undo(self):
        for cell in self.cells:
            cell.z_index = self.old_values[cell.id]
        if self.update_callback:
            self.update_callback()

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

class CreateSizeGroupCommand(QUndoCommand):
    """Create a new SizeGroup and assign the given cells to it."""
    def __init__(self, project, cells: list, name: str, update_callback=None):
        super().__init__(f"Create Size Group '{name}'")
        from src.model.data_model import SizeGroup
        self.project = project
        self.cells = list(cells)
        self.group = SizeGroup(name=name)
        self.old_group_ids = [getattr(c, 'size_group_id', None) for c in self.cells]
        self.update_callback = update_callback

    def redo(self):
        if self.group not in self.project.size_groups:
            self.project.size_groups.append(self.group)
        for c in self.cells:
            c.size_group_id = self.group.id
        if self.update_callback:
            self.update_callback()

    def undo(self):
        for c, old in zip(self.cells, self.old_group_ids):
            c.size_group_id = old
        self.project.size_groups = [g for g in self.project.size_groups if g.id != self.group.id]
        if self.update_callback:
            self.update_callback()


class DeleteSizeGroupCommand(QUndoCommand):
    """Delete a SizeGroup and unassign all its members."""
    def __init__(self, project, group_id: str, update_callback=None):
        super().__init__("Delete Size Group")
        self.project = project
        self.group_id = group_id
        self.group = project.find_size_group(group_id)
        self.member_ids = [c.id for c in project.size_group_members(group_id)]
        self.update_callback = update_callback

    def redo(self):
        if self.group is None:
            return
        for c in self.project.get_all_leaf_cells():
            if c.id in self.member_ids:
                c.size_group_id = None
        self.project.size_groups = [g for g in self.project.size_groups if g.id != self.group_id]
        if self.update_callback:
            self.update_callback()

    def undo(self):
        if self.group is None:
            return
        if self.group not in self.project.size_groups:
            self.project.size_groups.append(self.group)
        for c in self.project.get_all_leaf_cells():
            if c.id in self.member_ids:
                c.size_group_id = self.group_id
        if self.update_callback:
            self.update_callback()


class SizeGroupPropertyChangeCommand(QUndoCommand):
    """Change properties on a SizeGroup (pinned W/H, name)."""
    def __init__(self, project, group_id: str, changes: dict, update_callback=None,
                 description="Change Size Group Property"):
        super().__init__(description)
        self.project = project
        self.group_id = group_id
        self.changes = changes
        group = project.find_size_group(group_id)
        self.old_values = {k: getattr(group, k, None) for k in changes.keys()} if group else {}
        self.update_callback = update_callback

    def redo(self):
        group = self.project.find_size_group(self.group_id)
        if not group:
            return
        for k, v in self.changes.items():
            if hasattr(group, k):
                setattr(group, k, v)
        if self.update_callback:
            self.update_callback()

    def undo(self):
        group = self.project.find_size_group(self.group_id)
        if not group:
            return
        for k, v in self.old_values.items():
            if hasattr(group, k):
                setattr(group, k, v)
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
        # Delta storage: only store the new row and cells we'll create
        self.new_row = None
        self.new_cells = []

    def redo(self):
        from src.model.data_model import RowTemplate, Cell
        # Shift existing rows and their cells
        for r in self.project.rows:
            if r.index >= self.insert_index:
                r.index += 1
        for c in self.project.cells:
            if c.row_index >= self.insert_index:
                c.row_index += 1
        # Create the new row and its cells (only once on first execution)
        if self.new_row is None:
            self.new_row = RowTemplate(index=self.insert_index, column_count=self.column_count)
            for col in range(self.column_count):
                self.new_cells.append(
                    Cell(row_index=self.insert_index, col_index=col, is_placeholder=True)
                )
        else:
            # On redo after undo, restore the index
            self.new_row.index = self.insert_index
            for cell in self.new_cells:
                cell.row_index = self.insert_index
        
        self.project.rows.append(self.new_row)
        self.project.rows.sort(key=lambda r: r.index)
        self.project.cells.extend(self.new_cells)
        if self.update_callback:
            self.update_callback()

    def undo(self):
        # Remove the inserted row and cells
        if self.new_row in self.project.rows:
            self.project.rows.remove(self.new_row)
        for cell in self.new_cells:
            if cell in self.project.cells:
                self.project.cells.remove(cell)
        # Shift indices back down
        for r in self.project.rows:
            if r.index > self.insert_index:
                r.index -= 1
        for c in self.project.cells:
            if c.row_index > self.insert_index:
                c.row_index -= 1
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
        # Delta storage
        self.new_cell = None
        self.row = None

    def redo(self):
        from src.model.data_model import Cell
        self.row = next((r for r in self.project.rows if r.index == self.row_index), None)
        if not self.row:
            return
        # Shift cells in this row at col >= insert_col
        for c in self.project.cells:
            if c.row_index == self.row_index and c.col_index >= self.insert_col:
                c.col_index += 1
        # Increment column count
        self.row.column_count += 1
        # Add new placeholder cell (create only once)
        if self.new_cell is None:
            self.new_cell = Cell(row_index=self.row_index, col_index=self.insert_col, is_placeholder=True)
        self.project.cells.append(self.new_cell)
        if self.update_callback:
            self.update_callback()

    def undo(self):
        if not self.row:
            return
        # Remove the inserted cell
        if self.new_cell in self.project.cells:
            self.project.cells.remove(self.new_cell)
        # Shift cells back
        for c in self.project.cells:
            if c.row_index == self.row_index and c.col_index > self.insert_col:
                c.col_index -= 1
        # Decrement column count
        self.row.column_count -= 1
        if self.update_callback:
            self.update_callback()


class DeleteRowCommand(QUndoCommand):
    """Delete an entire row and its cells, shifting subsequent rows up."""
    def __init__(self, project, row_index, update_callback=None):
        super().__init__(f"Delete Row {row_index}")
        self.project = project
        self.row_index = row_index
        self.update_callback = update_callback
        # Delta storage: save what we're deleting
        self.deleted_row = None
        self.deleted_cells = []
        self.deleted_text_items = []

    def redo(self):
        # Save deleted items on first execution
        if self.deleted_row is None:
            self.deleted_row = next((r for r in self.project.rows if r.index == self.row_index), None)
            self.deleted_cells = [c for c in self.project.cells if c.row_index == self.row_index]
            # Collect all leaf-cell IDs in this row (including sub-cells)
            deleted_ids = set()
            for cell in self.deleted_cells:
                for leaf in cell.get_all_leaves():
                    deleted_ids.add(leaf.id)
            self.deleted_text_items = [
                t for t in self.project.text_items if t.parent_id in deleted_ids
            ]

        # Remove the row template
        if self.deleted_row in self.project.rows:
            self.project.rows.remove(self.deleted_row)
        # Remove cells in this row
        for cell in self.deleted_cells:
            if cell in self.project.cells:
                self.project.cells.remove(cell)
        # Remove orphaned text items belonging to deleted cells
        for t in self.deleted_text_items:
            if t in self.project.text_items:
                self.project.text_items.remove(t)
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
        # Shift rows and cells back down
        for r in self.project.rows:
            if r.index >= self.row_index:
                r.index += 1
        for c in self.project.cells:
            if c.row_index >= self.row_index:
                c.row_index += 1
        # Restore deleted row and cells
        if self.deleted_row:
            self.deleted_row.index = self.row_index
            self.project.rows.append(self.deleted_row)
            self.project.rows.sort(key=lambda r: r.index)
        for cell in self.deleted_cells:
            cell.row_index = self.row_index
            self.project.cells.append(cell)
        # Restore orphaned text items
        for t in self.deleted_text_items:
            if t not in self.project.text_items:
                self.project.text_items.append(t)
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
        # Collect orphaned text items for the deleted cell (and its sub-cell leaves)
        deleted_cell = next(
            (c for c in project.cells if c.row_index == row_index and c.col_index == col_index), None
        )
        deleted_ids = set()
        if deleted_cell:
            for leaf in deleted_cell.get_all_leaves():
                deleted_ids.add(leaf.id)
        self.deleted_text_items = [
            t for t in project.text_items if t.parent_id in deleted_ids
        ]

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
        # Remove orphaned text items
        for t in self.deleted_text_items:
            if t in self.project.text_items:
                self.project.text_items.remove(t)
        if self.update_callback:
            self.update_callback()

    def undo(self):
        import copy
        self.project.rows[:] = copy.deepcopy(self.old_rows)
        self.project.cells[:] = copy.deepcopy(self.old_cells)
        # Restore orphaned text items
        for t in self.deleted_text_items:
            if t not in self.project.text_items:
                self.project.text_items.append(t)
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
        self.old_count = len(project.rows)
        self.update_callback = update_callback
        
        # Delta storage: save only what will be added or removed
        self.added_rows = []
        self.added_cells = []
        self.removed_rows = []
        self.removed_cells = []

    def redo(self):
        current_count = len(self.project.rows)
        if self.new_count > current_count:
            # Add rows (save on first execution)
            if not self.added_rows:
                for i in range(current_count, self.new_count):
                    new_row = RowTemplate(index=i, column_count=2)
                    self.added_rows.append(new_row)
                    self.project.rows.append(new_row)
                    # Add cells for new rows
                    for col_idx in range(2):
                        new_cell = Cell(row_index=i, col_index=col_idx, is_placeholder=True)
                        self.added_cells.append(new_cell)
                        self.project.cells.append(new_cell)
            else:
                # Re-add previously created rows/cells
                self.project.rows.extend(self.added_rows)
                self.project.cells.extend(self.added_cells)
                
        elif self.new_count < current_count:
            # Remove rows (save on first execution)
            if not self.removed_rows:
                self.removed_rows = self.project.rows[self.new_count:]
                self.removed_cells = [c for c in self.project.cells if c.row_index >= self.new_count]
            
            # Remove excess rows and cells
            for row in self.removed_rows:
                if row in self.project.rows:
                    self.project.rows.remove(row)
            for cell in self.removed_cells:
                if cell in self.project.cells:
                    self.project.cells.remove(cell)

        if self.update_callback:
            self.update_callback()

    def undo(self):
        if self.new_count > self.old_count:
            # Undo add: remove added rows/cells
            for row in self.added_rows:
                if row in self.project.rows:
                    self.project.rows.remove(row)
            for cell in self.added_cells:
                if cell in self.project.cells:
                    self.project.cells.remove(cell)
        elif self.new_count < self.old_count:
            # Undo remove: restore removed rows/cells
            self.project.rows.extend(self.removed_rows)
            self.project.rows.sort(key=lambda r: r.index)
            self.project.cells.extend(self.removed_cells)
        
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
        self.old_text_items = copy.deepcopy(project.text_items)

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
            import copy, uuid
            old_id = cell.id
            clone = copy.deepcopy(cell)
            clone.id = str(uuid.uuid4())  # New ID to avoid collision with container
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

            # Re-point text items that referenced the original cell to the clone
            for t in self.project.text_items:
                if t.parent_id == old_id and t.scope == "cell":
                    t.parent_id = clone.id

        if self.update_callback:
            self.update_callback()

    def undo(self):
        import copy
        self.project.cells[:] = copy.deepcopy(self.old_cells)
        self.project.text_items[:] = copy.deepcopy(self.old_text_items)
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


class ChangeLabelSchemeCommand(QUndoCommand):
    """Change the label scheme and re-apply it to all existing numbering labels."""
    def __init__(self, project, new_scheme: str, update_callback=None):
        super().__init__("Change Label Scheme")
        self.project = project
        self.old_scheme = project.label_scheme
        self.new_scheme = new_scheme
        self.update_callback = update_callback

        self.old_texts = {
            t.id: t.text for t in project.text_items
            if t.scope == "cell" and t.subtype != "corner"
        }
        self.new_texts = self._compute_texts(new_scheme)

    def _compute_texts(self, scheme: str) -> dict:
        sorted_cells = sorted(
            self.project.get_all_leaf_cells(),
            key=lambda c: (c.row_index, c.col_index)
        )
        start_char = 'A' if 'A' in scheme else 'a'
        use_parens = '(' in scheme
        label_by_cell = {
            t.parent_id: t for t in self.project.text_items
            if t.scope == "cell" and t.subtype != "corner"
        }
        result = {}
        for i, cell in enumerate(sorted_cells):
            if cell.id in label_by_cell:
                char_code = ord(start_char) + i
                label_text = chr(char_code)
                if use_parens:
                    label_text = f"({label_text})"
                result[label_by_cell[cell.id].id] = label_text
        return result

    def redo(self):
        self.project.label_scheme = self.new_scheme
        for t in self.project.text_items:
            if t.id in self.new_texts:
                t.text = self.new_texts[t.id]
        if self.update_callback:
            self.update_callback()

    def undo(self):
        self.project.label_scheme = self.old_scheme
        for t in self.project.text_items:
            if t.id in self.old_texts:
                t.text = self.old_texts[t.id]
        if self.update_callback:
            self.update_callback()


class AutoLabelCommand(QUndoCommand):
    def __init__(self, project, update_callback=None):
        super().__init__("Auto Label")
        self.project = project
        self.update_callback = update_callback
        # Always produces in-cell labels regardless of current label_placement
        self.old_label_placement = getattr(project, 'label_placement', 'in_cell')
        # Delta storage: save only existing numbering labels (will be replaced)
        self.old_numbering_labels = [
            t for t in project.text_items 
            if t.scope == 'cell' and getattr(t, 'subtype', None) != 'corner'
        ]
        self.new_labels = []

    def redo(self):
        from src.utils.auto_label import AutoLabel
        # Sweep ALL numbering labels out (defensive — prevents any stale duplicates)
        self.project.text_items[:] = [
            t for t in self.project.text_items
            if not (t.scope == 'cell' and getattr(t, 'subtype', None) != 'corner')
        ]

        # Always reset to in_cell so auto-label is predictable
        self.project.label_placement = 'in_cell'

        # Generate new labels (save on first execution)
        if not self.new_labels:
            AutoLabel.generate_labels(self.project)
            self.new_labels = [
                t for t in self.project.text_items
                if t.scope == 'cell' and getattr(t, 'subtype', None) != 'corner'
            ]
        else:
            # Re-add previously generated labels
            self.project.text_items.extend(self.new_labels)
        
        if self.update_callback:
            self.update_callback()

    def undo(self):
        # Remove new labels
        for label in self.new_labels:
            if label in self.project.text_items:
                self.project.text_items.remove(label)
        # Restore old labels and previous placement mode
        self.project.text_items.extend(self.old_numbering_labels)
        self.project.label_placement = self.old_label_placement
        if self.update_callback:
            self.update_callback()

class AutoLabelOutCellCommand(QUndoCommand):
    """Auto-label all cells using a dedicated label row above each picture row."""
    def __init__(self, project, update_callback=None):
        super().__init__("Auto Label Row")
        self.project = project
        self.update_callback = update_callback
        self.old_label_placement = getattr(project, 'label_placement', 'in_cell')
        self.old_numbering_labels = [
            t for t in project.text_items
            if t.scope == 'cell' and getattr(t, 'subtype', None) != 'corner'
        ]
        self.new_labels = []

    def redo(self):
        from src.utils.auto_label import AutoLabel
        # Sweep ALL numbering labels out (defensive — prevents any stale duplicates)
        self.project.text_items[:] = [
            t for t in self.project.text_items
            if not (t.scope == 'cell' and getattr(t, 'subtype', None) != 'corner')
        ]

        self.project.label_placement = 'label_row_above'

        if not self.new_labels:
            AutoLabel.generate_labels(self.project)
            self.new_labels = [
                t for t in self.project.text_items
                if t.scope == 'cell' and getattr(t, 'subtype', None) != 'corner'
            ]
        else:
            self.project.text_items.extend(self.new_labels)

        if self.update_callback:
            self.update_callback()

    def undo(self):
        for label in self.new_labels:
            if label in self.project.text_items:
                self.project.text_items.remove(label)
        self.project.text_items.extend(self.old_numbering_labels)
        self.project.label_placement = self.old_label_placement
        if self.update_callback:
            self.update_callback()


class AutoLayoutCommand(QUndoCommand):
    def __init__(self, project, update_callback=None):
        super().__init__("Auto Layout")
        self.project = project
        self.update_callback = update_callback
        
        # Delta storage: save only the specific properties that will change
        self.old_page_height = project.page_height_mm
        self.old_row_settings = {}  # row_index -> {height_ratio, column_ratios}
        self.old_cell_ratios = {}   # cell_id -> split_ratios
        
        # Save original values
        for row in project.rows:
            self.old_row_settings[row.index] = {
                'height_ratio': row.height_ratio,
                'column_ratios': list(row.column_ratios) if row.column_ratios else []
            }
        
        # Save cell split_ratios that might be modified
        for cell in project.get_all_leaf_cells():
            parent = project.find_parent_of(cell.id)
            if parent and parent.split_ratios:
                self.old_cell_ratios[parent.id] = list(parent.split_ratios)
        
        self.new_settings = None

    def redo(self):
        from src.utils.auto_layout import AutoLayout
        
        # Calculate new layout settings (only once)
        if self.new_settings is None:
            self.new_settings = AutoLayout.optimize_layout(self.project)
        
        # Apply changes to project rows
        for i, row_data in enumerate(self.new_settings['rows']):
            if i < len(self.project.rows):
                row = self.project.rows[i]
                row.height_ratio = row_data.get('height_ratio', 1.0)
                row.column_ratios = row_data.get('column_ratios', [])
        
        # Apply optimal page height if calculated
        if 'optimal_page_height_mm' in self.new_settings:
            self.project.page_height_mm = self.new_settings['optimal_page_height_mm']
                
        if self.update_callback:
            self.update_callback()

    def undo(self):
        # Restore row settings
        for row in self.project.rows:
            if row.index in self.old_row_settings:
                settings = self.old_row_settings[row.index]
                row.height_ratio = settings['height_ratio']
                row.column_ratios = settings['column_ratios']
        
        # Restore cell split_ratios
        for cell_id, ratios in self.old_cell_ratios.items():
            cell = self.project.find_cell_by_id(cell_id)
            if cell:
                cell.split_ratios = ratios
        
        # Restore page height
        self.project.page_height_mm = self.old_page_height
        
        if self.update_callback:
            self.update_callback()


class AutoLayoutFreeformCommand(QUndoCommand):
    def __init__(self, project, update_callback=None):
        super().__init__("Auto Layout (Freeform)")
        self.project = project
        self.update_callback = update_callback
        
        # Save old cell paddings and freeform geometry
        self.old_cell_props = {}
        for cell in project.get_all_leaf_cells():
            if cell.image_path and not cell.is_placeholder:
                self.old_cell_props[cell.id] = {
                    'padding_top': cell.padding_top,
                    'padding_bottom': cell.padding_bottom,
                    'padding_left': cell.padding_left,
                    'padding_right': cell.padding_right,
                    'freeform_w_mm': cell.freeform_w_mm,
                    'freeform_h_mm': cell.freeform_h_mm
                }
                
        self.new_props = None

    def redo(self):
        if self.new_props is None:
            self.new_props = {}
            from src.utils.auto_layout import AutoLayout
            aspect_ratios = AutoLayout._get_image_aspect_ratios(self.project)
            
            for cell_id, old_props in self.old_cell_props.items():
                cell = self.project.find_cell_by_id(cell_id)
                if not cell:
                    continue
                
                ratio = aspect_ratios.get(cell.id)
                if ratio is None or ratio <= 0:
                    continue
                    
                # We want to match aspect ratio but keeping the max dimension roughly similar
                # to not blow up or shrink the image completely. Let's preserve area.
                old_w = old_props['freeform_w_mm']
                old_h = old_props['freeform_h_mm']
                old_area = old_w * old_h
                
                # new_w * new_h = old_area
                # new_w = ratio * new_h
                # ratio * new_h^2 = old_area
                import math
                new_h = math.sqrt(old_area / ratio) if ratio > 0 else old_h
                new_w = new_h * ratio
                
                self.new_props[cell.id] = {
                    'padding_top': 0.0,
                    'padding_bottom': 0.0,
                    'padding_left': 0.0,
                    'padding_right': 0.0,
                    'freeform_w_mm': new_w,
                    'freeform_h_mm': new_h
                }
                
        # Apply new props
        for cell_id, props in self.new_props.items():
            cell = self.project.find_cell_by_id(cell_id)
            if cell:
                cell.padding_top = props['padding_top']
                cell.padding_bottom = props['padding_bottom']
                cell.padding_left = props['padding_left']
                cell.padding_right = props['padding_right']
                cell.freeform_w_mm = props['freeform_w_mm']
                cell.freeform_h_mm = props['freeform_h_mm']

        if self.update_callback:
            self.update_callback()

    def undo(self):
        for cell_id, props in self.old_cell_props.items():
            cell = self.project.find_cell_by_id(cell_id)
            if cell:
                cell.padding_top = props['padding_top']
                cell.padding_bottom = props['padding_bottom']
                cell.padding_left = props['padding_left']
                cell.padding_right = props['padding_right']
                cell.freeform_w_mm = props['freeform_w_mm']
                cell.freeform_h_mm = props['freeform_h_mm']

        if self.update_callback:
            self.update_callback()


class AddPiPItemCommand(QUndoCommand):
    def __init__(self, cell: Cell, pip_item: PiPItem, update_callback=None):
        super().__init__("Add PiP Inset")
        self.cell = cell
        self.pip_item = pip_item
        self.update_callback = update_callback

    def redo(self):
        if self.pip_item not in self.cell.pip_items:
            self.cell.pip_items.append(self.pip_item)
        if self.update_callback:
            self.update_callback()

    def undo(self):
        self.cell.pip_items = [p for p in self.cell.pip_items if p.id != self.pip_item.id]
        if self.update_callback:
            self.update_callback()


class RemovePiPItemCommand(QUndoCommand):
    def __init__(self, cell: Cell, pip_item: PiPItem, update_callback=None):
        super().__init__("Remove PiP Inset")
        self.cell = cell
        self.pip_item = pip_item
        self.update_callback = update_callback

    def redo(self):
        self.cell.pip_items = [p for p in self.cell.pip_items if p.id != self.pip_item.id]
        if self.update_callback:
            self.update_callback()

    def undo(self):
        if self.pip_item not in self.cell.pip_items:
            self.cell.pip_items.append(self.pip_item)
        if self.update_callback:
            self.update_callback()


class SetPiPGeometryCommand(QUndoCommand):
    """Undo/redo for moving or resizing a PiP inset (x, y, w, h normalized)."""
    def __init__(self, pip_item: PiPItem, old_geom: tuple, new_geom: tuple, update_callback=None):
        super().__init__("Move/Resize PiP Inset")
        self.pip_item = pip_item
        self.old_geom = old_geom  # (x, y, w, h)
        self.new_geom = new_geom
        self.update_callback = update_callback

    def redo(self):
        self.pip_item.x, self.pip_item.y, self.pip_item.w, self.pip_item.h = self.new_geom
        if self.update_callback:
            self.update_callback()

    def undo(self):
        self.pip_item.x, self.pip_item.y, self.pip_item.w, self.pip_item.h = self.old_geom
        if self.update_callback:
            self.update_callback()

    def id(self):
        return hash(self.pip_item.id) & 0x7FFFFFFF

    def mergeWith(self, other):
        if not isinstance(other, SetPiPGeometryCommand) or other.pip_item is not self.pip_item:
            return False
        self.new_geom = other.new_geom
        return True


class SetPiPOriginCommand(QUndoCommand):
    """Undo/redo for editing the crop region of a zoom-type PiP inset."""
    def __init__(self, pip_item: PiPItem, old_crop: tuple, new_crop: tuple, update_callback=None):
        super().__init__("Edit PiP Zoom Region")
        self.pip_item = pip_item
        self.old_crop = old_crop  # (crop_left, crop_top, crop_right, crop_bottom)
        self.new_crop = new_crop
        self.update_callback = update_callback

    def redo(self):
        self.pip_item.crop_left, self.pip_item.crop_top, self.pip_item.crop_right, self.pip_item.crop_bottom = self.new_crop
        if self.update_callback:
            self.update_callback()

    def undo(self):
        self.pip_item.crop_left, self.pip_item.crop_top, self.pip_item.crop_right, self.pip_item.crop_bottom = self.old_crop
        if self.update_callback:
            self.update_callback()

    def id(self):
        return (hash(self.pip_item.id) + 1) & 0x7FFFFFFF

    def mergeWith(self, other):
        if not isinstance(other, SetPiPOriginCommand) or other.pip_item is not self.pip_item:
            return False
        self.new_crop = other.new_crop
        return True
