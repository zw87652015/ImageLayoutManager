import os
from typing import List, Tuple, Dict
from PIL import Image
from PyQt6.QtSvg import QSvgRenderer
from src.model.data_model import Project, RowTemplate, Cell

class AutoLayout:
    @staticmethod
    def _get_image_aspect_ratios(project: Project) -> Dict[str, float]:
        """Extracts the native w/h aspect ratio for all images in the project."""
        aspect_ratios = {}
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
                                crop_w = max(0.001, getattr(cell, 'crop_right', 1.0) - getattr(cell, 'crop_left', 0.0))
                                crop_h = max(0.001, getattr(cell, 'crop_bottom', 1.0) - getattr(cell, 'crop_top', 0.0))
                                ratio = (w * crop_w) / (h * crop_h)
                                if getattr(cell, 'rotation', 0) in [90, 270]:
                                    ratio = 1.0 / ratio if ratio != 0 else 0
                                aspect_ratios[cell.id] = ratio
                except Exception:
                    pass
        return aspect_ratios

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
                                crop_w = max(0.001, getattr(cell, 'crop_right', 1.0) - getattr(cell, 'crop_left', 0.0))
                                crop_h = max(0.001, getattr(cell, 'crop_bottom', 1.0) - getattr(cell, 'crop_top', 0.0))
                                ratio = (w * crop_w) / (h * crop_h)
                                # Adjust ratio if rotated 90 or 270 degrees
                                if getattr(cell, 'rotation', 0) in [90, 270]:
                                    ratio = 1.0 / ratio if ratio != 0 else 0
                                aspect_ratios[cell.id] = ratio
                except Exception:
                    pass
        
        # 1a-group. Size-group aware aspect bucketing.
        # Cells that belong to the same size group must end up with the same W/H.
        # Using the MIN aspect of the group ensures the shared size fits every member.
        groups = getattr(project, 'size_groups', []) or []
        if groups:
            for g in groups:
                member_ids = [c.id for c in project.get_all_leaf_cells() if c.size_group_id == g.id]
                aspects = [aspect_ratios[mid] for mid in member_ids if mid in aspect_ratios]
                if aspects:
                    shared_aspect = min(aspects)
                    for mid in member_ids:
                        aspect_ratios[mid] = shared_aspect

        # 1b. Recursively optimise split_ratios for every container cell and
        #     compute the cell's natural (width, height) bottom-up, accounting
        #     for gaps at each split level so the composite aspect fed upward is
        #     accurate and leaf images fill their cells without letterbox space.
        #
        # We propagate (w, h) natural sizes using the content width as a reference.
        # This matters because gaps are absolute (mm), so their fractional effect
        # differs at each nesting level and cannot be captured by a pure ratio.
        ref_w = (project.page_width_mm
                 - project.margin_left_mm
                 - project.margin_right_mm)
        gap = project.gap_mm

        # Determine which cells have a label strip reserved above them
        _label_row_above = getattr(project, "label_placement", "in_cell") == "label_row_above"
        _label_row_h = 0.0
        _labeled_cell_ids: set = set()
        if _label_row_above:
            from src.model.layout_engine import LayoutEngine
            _custom_h = getattr(project, 'label_row_height', 0.0)
            _label_row_h = _custom_h if _custom_h > 0 else LayoutEngine._label_row_height_mm(project)
            for t in project.text_items:
                if t.scope == 'cell' and getattr(t, 'subtype', None) != 'corner' and t.parent_id:
                    _labeled_cell_ids.add(t.parent_id)

        def _optimise_and_composite(cell, parent_w: float):
            """Return (w, total_h, img_h) for *cell* at width *parent_w*.

            total_h includes any label-strip overhead reserved above this cell
            (so the parent can allocate enough space).  img_h is the pure image
            content height, used for split_ratios — the layout engine handles the
            label strips separately and must not double-count them.

            Horizontal split: children share height H, placed side by side.
                split_ratio_i = img_aspect_i  (= img_w_i / img_h)
                H = available_w / sum(img_aspects)
                img_h = H   (label strip is uniform across all siblings, handled by engine)

            Vertical split: children stacked, sharing width parent_w.
                split_ratio_i = img_h_i  (proportional to image-only height)
                total_natural_h = sum(total_h_i) + (n-1)*gap + fixed_heights
                img_h = total_natural_h - own_label_overhead
            """
            if cell.is_leaf:
                a = aspect_ratios.get(cell.id)
                if a and a > 0:
                    img_h = parent_w / a
                    label_overhead = (_label_row_h + gap) if (_label_row_above and cell.id in _labeled_cell_ids) else 0.0
                    return (parent_w, img_h + label_overhead, img_h)
                return None

            children = cell.children
            n = len(children)
            if n == 0:
                return None

            # Recurse first (bottom-up), passing estimated child widths
            if cell.split_direction == "horizontal":
                child_w_est = max(1.0, (parent_w - (n - 1) * gap) / n)
                child_sizes = [_optimise_and_composite(c, child_w_est) for c in children]
            else:
                child_sizes = [_optimise_and_composite(c, parent_w) for c in children]

            if cell.split_direction == "horizontal":
                new_ratios = list(cell.split_ratios) if cell.split_ratios else [1.0] * n
                fixed_w_total = 0.0
                valid_img_aspects = []
                for i, (child, sz) in enumerate(zip(children, child_sizes)):
                    ow = getattr(child, 'override_width_mm', 0.0)
                    if ow > 0:
                        fixed_w_total += ow
                        continue
                    # Use img_h (sz[2]) for aspect ratio so label overhead doesn't distort ratios
                    if sz is not None and len(sz) > 2 and sz[2] > 0:
                        img_h = sz[2]
                    elif sz is not None and sz[1] > 0:
                        img_h = sz[1]
                    else:
                        img_h = None
                    a = (sz[0] / img_h) if (img_h and img_h > 0) else None
                    new_ratios[i] = a if (a is not None and a > 0) else 1.0
                    if a is not None and a > 0:
                        valid_img_aspects.append(a)
                cell.split_ratios = new_ratios

                if valid_img_aspects:
                    available = max(1.0, parent_w - (n - 1) * gap - fixed_w_total)
                    H = available / sum(valid_img_aspects)
                    # Label overhead for a horizontal split is uniform across all siblings
                    # and is handled by the engine; img_h = H for this container
                    label_overhead = (_label_row_h + gap) if (_label_row_above and cell.id in _labeled_cell_ids) else 0.0
                    composite_size = (parent_w, H + label_overhead, H)
                else:
                    composite_size = None

            elif cell.split_direction == "vertical":
                new_ratios = list(cell.split_ratios) if cell.split_ratios else [1.0] * n
                fixed_h_total = 0.0
                total_h_sum = 0.0  # sum of each child's total_h (includes their label overheads)
                has_valid = False
                for i, (child, sz) in enumerate(zip(children, child_sizes)):
                    oh = getattr(child, 'override_height_mm', 0.0)
                    if oh > 0:
                        fixed_h_total += oh
                        continue
                    # sz[1] = total_h (with label overhead), sz[2] = img_h (without)
                    if sz is not None and len(sz) > 2 and sz[2] > 0:
                        child_img_h = sz[2]
                    elif sz is not None and sz[1] > 0:
                        child_img_h = sz[1]
                    else:
                        child_img_h = None
                    child_total_h = sz[1] if (sz is not None and sz[1] > 0) else None
                    if child_img_h and child_img_h > 0:
                        # split_ratios reflect image-only height so engine doesn't double-count labels
                        new_ratios[i] = child_img_h
                        total_h_sum += child_total_h

                        has_valid = True
                    else:
                        new_ratios[i] = 1.0
                cell.split_ratios = new_ratios

                if has_valid:
                    natural_h = total_h_sum + (n - 1) * gap + fixed_h_total
                    label_overhead = (_label_row_h + gap) if (_label_row_above and cell.id in _labeled_cell_ids) else 0.0
                    composite_size = (parent_w, natural_h + label_overhead, natural_h)
                else:
                    composite_size = None
            else:
                composite_size = None

            if composite_size is not None:
                # Store aspect based on img_h so composite fed to parent is correct
                img_h_for_aspect = composite_size[2] if composite_size[2] > 0 else composite_size[1]
                aspect_ratios[cell.id] = composite_size[0] / img_h_for_aspect
            return composite_size

        # Walk all cells (at every depth) to optimise ratios and build composites
        for cell in project.cells:
            if not cell.is_leaf:
                _optimise_and_composite(cell, ref_w)

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
