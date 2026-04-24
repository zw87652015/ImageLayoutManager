from typing import List
from src.model.data_model import Project, TextItem, LabelPosition
from src.model.layout_engine import LayoutEngine

class AutoLabel:
    @staticmethod
    def generate_labels(project: Project) -> None:
        """
        Generates panel labels for all cells in the project and appends them to project.text_items.
        It does NOT remove existing text items, so caller might want to clear them if replacing.
        """
        # 1. Calculate Layout to know where cells are
        layout = LayoutEngine.calculate_layout(project)

        # 2. Sort leaf cells by *spatial* position (top-to-bottom, then
        #    left-to-right). `row_index`/`col_index` only reflect the
        #    top-level row/col and are identical for every sub-cell of a
        #    split parent, which would otherwise collapse ordering inside
        #    split rows and produce scrambled labels (e.g. a, e, f, …).
        Y_TOL = 0.5  # mm; cells within this vertical gap count as same row
        def _spatial_key(c):
            rect = layout.cell_rects.get(c.id)
            if rect is None:
                # Cells outside the current layout (shouldn't happen for
                # leaves) fall to the end, ordered by index tuple.
                return (float("inf"), float("inf"), c.row_index, c.col_index)
            x, y, _w, _h = rect
            # Quantize y so tiny rounding differences don't reorder peers.
            return (round(y / Y_TOL), x)
        sorted_cells = sorted(project.get_all_leaf_cells(), key=_spatial_key)
        
        # 3. Generate labels
        start_char = 'a'
        if 'A' in project.label_scheme:
            start_char = 'A'
            
        use_parens = '(' in project.label_scheme
        
        for i, cell in enumerate(sorted_cells):
            # Skip placeholders if desired, or label them too. Usually label them.
            
            # Determine text
            char_code = ord(start_char) + i
            label_text = chr(char_code)
            if use_parens:
                label_text = f"({label_text})"
                
            # Determine Position
            # Default to Top-Left Inside with small offset
            # TODO: Use project.label_anchor preferences
            
            if cell.id in layout.cell_rects:
                x, y, w, h = layout.cell_rects[cell.id]
                
                # Offset in mm
                offset_x = 2.0
                offset_y = 2.0
                
                # If Outside, logic would differ. For v1 assume Inside Top-Left.
                
                pos_x = x + offset_x
                pos_y = y + offset_y
                
                # Create Text Item with cell-scoped anchor
                item = TextItem(
                    text=label_text,
                    font_family=project.label_font_family,
                    font_size_pt=project.label_font_size,
                    font_weight=project.label_font_weight,
                    color=project.label_color,
                    x=pos_x,
                    y=pos_y,
                    scope="cell",
                    subtype="numbering",
                    parent_id=cell.id,
                    anchor="top_left_inside",
                    offset_x=offset_x,
                    offset_y=offset_y
                )
                
                project.text_items.append(item)
