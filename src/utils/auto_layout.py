import os
from typing import List, Tuple, Dict
from PIL import Image
from PyQt6.QtSvg import QSvgRenderer
from src.model.data_model import Project, RowTemplate, Cell

class AutoLayout:
    @staticmethod
    def optimize_layout(project: Project) -> Dict[str, any]:
        """
        Calculates optimized row heights and column ratios.
        
        Strategy:
        1. Within a row, we want all images to have the SAME physical height to look neat.
           - To achieve this, column width W_i must be proportional to image aspect ratio a_i (W_i = H * a_i).
           - So, column_ratios = [a_1, a_2, ... a_n].
           
        2. Across rows, we want to respect the natural height of each row.
           - A row's natural height H_row is determined by the page width W_page.
           - W_page = Sum(W_i) = Sum(H_row * a_i) = H_row * Sum(a_i).
           - Therefore, H_row = W_page / Sum(a_i).
           - The layout engine distributes vertical space based on height_ratio.
           - So, row.height_ratio should be proportional to 1 / Sum(a_i).
        """
        
        # 1. Gather image aspect ratios
        aspect_ratios = {} # cell_id -> float (w/h)
        
        for cell in project.get_all_leaf_cells():
            if cell.image_path and os.path.exists(cell.image_path) and not cell.is_placeholder:
                try:
                    ext = os.path.splitext(cell.image_path)[1].lower()
                    if ext == '.svg':
                        # Handle SVG vector format
                        renderer = QSvgRenderer(cell.image_path)
                        if renderer.isValid():
                            size = renderer.defaultSize()
                            if size.height() > 0:
                                ratio = size.width() / size.height()
                                # Adjust ratio if rotated 90 or 270 degrees
                                if getattr(cell, 'rotation', 0) in [90, 270]:
                                    ratio = 1.0 / ratio if ratio != 0 else 0
                                aspect_ratios[cell.id] = ratio
                    elif ext == '.pdf':
                        # Handle PDF format with PyMuPDF
                        try:
                            import fitz
                            doc = fitz.open(cell.image_path)
                            if doc.page_count > 0:
                                page = doc[0]
                                rect = page.rect
                                if rect.height > 0:
                                    ratio = rect.width / rect.height
                                    # Adjust ratio if rotated 90 or 270 degrees
                                    if getattr(cell, 'rotation', 0) in [90, 270]:
                                        ratio = 1.0 / ratio if ratio != 0 else 0
                                    aspect_ratios[cell.id] = ratio
                            doc.close()
                        except ImportError:
                            pass
                    else:
                        # Handle raster formats with PIL
                        with Image.open(cell.image_path) as img:
                            w, h = img.size
                            if h > 0:
                                ratio = w / h
                                # Adjust ratio if rotated 90 or 270 degrees
                                if getattr(cell, 'rotation', 0) in [90, 270]:
                                    ratio = 1.0 / ratio if ratio != 0 else 0
                                aspect_ratios[cell.id] = ratio
                except Exception:
                    pass
        
        # 1b. Recursively optimise split_ratios for every container cell
        #     and compute composite aspect ratios bottom-up.
        def _optimise_and_composite(cell):
            """Optimise split_ratios for *cell* based on children's images,
            then return the effective w/h aspect ratio of the whole sub-tree.

            Horizontal split (children side by side, shared height):
                optimal split_ratio_i = a_i  (wider images get more width)
                composite_a = sum(a_i)
            Vertical split (children stacked, shared width):
                optimal split_ratio_i = 1/a_i  (taller images get more height)
                composite_a = 1 / sum(1/a_i)
            """
            if cell.is_leaf:
                return aspect_ratios.get(cell.id, None)

            # Recurse into children first (bottom-up)
            child_aspects = [_optimise_and_composite(c) for c in cell.children]

            if cell.split_direction == "horizontal":
                # Optimal: give each child width proportional to its aspect ratio
                new_ratios = []
                for a in child_aspects:
                    new_ratios.append(a if (a is not None and a > 0) else 1.0)
                cell.split_ratios = new_ratios
                # Composite: sum of child aspects (all share same height)
                valid = [a for a in child_aspects if a is not None and a > 0]
                composite = sum(valid) if valid else None

            elif cell.split_direction == "vertical":
                # Optimal: give each child height proportional to 1/aspect
                new_ratios = []
                for a in child_aspects:
                    new_ratios.append(1.0 / a if (a is not None and a > 0) else 1.0)
                cell.split_ratios = new_ratios
                # Composite: harmonic combination (all share same width)
                valid = [a for a in child_aspects if a is not None and a > 0]
                composite = 1.0 / sum(1.0 / a for a in valid) if valid else None
            else:
                composite = None

            if composite is not None:
                aspect_ratios[cell.id] = composite
            return composite

        # Walk all cells (at every depth) to optimise ratios and build composites
        for cell in project.cells:
            if not cell.is_leaf:
                _optimise_and_composite(cell)

        new_row_settings = []
        sorted_rows = sorted(project.rows, key=lambda r: r.index)
        
        # We need to collect all row "height demands" first to normalize them later
        row_height_demands = {} # row_index -> float
        
        for row in sorted_rows:
            # Find top-level cells in this row
            row_cells = sorted(
                [c for c in project.cells if c.row_index == row.index],
                key=lambda c: c.col_index
            )
            
            col_count = row.column_count
            if col_count <= 0:
                new_row_settings.append(row.to_dict())
                continue
                
            # Get aspect ratios for each column slot (uses composite for containers)
            row_aspects = []
            valid_aspects = []
            
            col_map = {c.col_index: c for c in row_cells}
            
            for i in range(col_count):
                cell = col_map.get(i)
                ratio = 1.0
                if cell and cell.id in aspect_ratios:
                    ratio = aspect_ratios[cell.id]
                    valid_aspects.append(ratio)
                row_aspects.append(ratio)
            
            # If no images in row (or all placeholders), assume equal distribution
            # But if there are *some* images, we should use their ratios, and average for placeholders
            if valid_aspects:
                avg_aspect = sum(valid_aspects) / len(valid_aspects)
                # Fill in placeholders with average aspect
                final_ratios = []
                for r in row_aspects:
                    if r == 1.0 and 1.0 not in valid_aspects: # If it was a default placeholder
                        final_ratios.append(avg_aspect)
                    else:
                        final_ratios.append(r)
            else:
                final_ratios = [1.0] * col_count
                
            # 1. Set Column Ratios
            # Normalize so smallest is 1.0 for readability (optional, but cleaner)
            min_r = min(final_ratios)
            norm_col_ratios = [round(r / min_r, 2) for r in final_ratios]
            
            # 2. Calculate Natural Row Height Demand
            # H_demand ~ 1 / Sum(aspects)
            total_row_aspect = sum(final_ratios)
            if total_row_aspect <= 0: total_row_aspect = 1.0
            
            height_demand = 1.0 / total_row_aspect
            row_height_demands[row.index] = height_demand
            
            # Store partial result
            r_dict = row.to_dict()
            r_dict['column_ratios'] = norm_col_ratios
            new_row_settings.append(r_dict)

        # 3. Normalize Height Ratios across all rows
        # We want the values to be nice numbers like 1.0, 1.5, etc.
        # Let's scale them so the *tallest* row (max demand) is roughly 1.0? 
        # Or just normalize so min is 1.0.
        
        if row_height_demands:
            min_h = min(row_height_demands.values())
            if min_h < 0.0001: min_h = 1.0
            
            for r_dict in new_row_settings:
                idx = r_dict['index']
                if idx in row_height_demands:
                    raw_h = row_height_demands[idx]
                    # Scale: if raw_h is 2x min_h, ratio should be 2.0
                    final_h = round(raw_h / min_h, 2)
                    r_dict['height_ratio'] = final_h

        # 4. Calculate optimal page height to fit content perfectly
        # For each row, the natural height is: H_row = W_content / sum(aspects_in_row)
        # Total natural height = sum(H_row) + gaps + margins
        
        content_width = project.page_width_mm - project.margin_left_mm - project.margin_right_mm
        gap_mm = project.gap_mm
        
        total_natural_height = 0
        for r_dict in new_row_settings:
            col_ratios = r_dict.get('column_ratios', [1.0])
            # The sum of column ratios represents the "row aspect ratio"
            # But we normalized them, so we need to use the original sum
            row_idx = r_dict['index']
            if row_idx in row_height_demands:
                # height_demand = 1 / sum(aspects), so natural_height = content_width * height_demand
                natural_row_height = content_width * row_height_demands[row_idx]
                total_natural_height += natural_row_height
        
        # Add gaps between rows
        num_rows = len(new_row_settings)
        if num_rows > 1:
            total_natural_height += (num_rows - 1) * gap_mm

        # Account for label rows if label_placement is 'label_row_above'
        label_row_above = getattr(project, "label_placement", "in_cell") == "label_row_above"
        if label_row_above:
            from src.model.layout_engine import LayoutEngine
            custom_h = getattr(project, 'label_row_height', 0.0)
            label_row_h = custom_h if custom_h > 0 else LayoutEngine._label_row_height_mm(project)

            # Find which row indices have numbering labels
            labeled_cell_ids = set()
            for t in project.text_items:
                if t.scope == 'cell' and getattr(t, 'subtype', None) != 'corner' and t.parent_id:
                    labeled_cell_ids.add(t.parent_id)
            rows_with_labels = set()
            for c in project.cells:
                if c.id in labeled_cell_ids:
                    rows_with_labels.add(c.row_index)

            num_label_rows = len(rows_with_labels)
            if num_label_rows > 0:
                total_natural_height += num_label_rows * (label_row_h + gap_mm)

        # Add margins
        optimal_page_height = total_natural_height + project.margin_top_mm + project.margin_bottom_mm
        
        return {
            "rows": new_row_settings,
            "optimal_page_height_mm": round(optimal_page_height, 1)
        }
