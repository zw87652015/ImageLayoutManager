from dataclasses import dataclass, field
from typing import List, Dict, Tuple
from .data_model import Project, Cell, RowTemplate

@dataclass
class LayoutResult:
    cell_rects: Dict[str, Tuple[float, float, float, float]]
    row_heights: Dict[int, float]
    figure_rects: Dict[str, Tuple[float, float, float, float]] = field(default_factory=dict)
    label_rects: Dict[str, Tuple[float, float, float, float]] = field(default_factory=dict)
    row_rects: Dict[int, Tuple[float, float, float, float]] = field(default_factory=dict)  # row_index -> (x, y, w, h)

class LayoutEngine:
    @staticmethod
    def _label_row_height_mm(project: Project) -> float:
        """Height of a label row based on label font settings.
        
        QGraphicsTextItem uses 72 DPI internally, so 1pt = 1 scene unit (mm).
        The row height should accommodate the font at this scale.
        """
        h = project.label_font_size * 1.2 + 2.0
        return max(5.0, min(50.0, h))

    @staticmethod
    def _compute_col_widths(r_temp: RowTemplate, content_width: float, gap_mm: float) -> List[float]:
        """Compute column widths for a row template."""
        col_count = r_temp.column_count
        if col_count <= 0:
            return []
        total_horizontal_gaps = (col_count - 1) * gap_mm if col_count > 1 else 0
        available_width = content_width - total_horizontal_gaps

        col_ratios = r_temp.column_ratios if r_temp.column_ratios else [1.0] * col_count
        while len(col_ratios) < col_count:
            col_ratios.append(1.0)
        col_ratios = col_ratios[:col_count]

        total_ratio = sum(col_ratios)
        if total_ratio <= 0:
            total_ratio = col_count
        return [(r / total_ratio) * available_width for r in col_ratios]

    @staticmethod
    def calculate_freeform_layout(project: Project) -> LayoutResult:
        """Freeform pipeline: cells use their own absolute position/size fields."""
        cell_rects: Dict[str, Tuple[float, float, float, float]] = {}
        for cell in project.cells:
            # Only top-level leaf cells contribute directly
            if cell.is_leaf:
                cell_rects[cell.id] = (
                    cell.freeform_x_mm,
                    cell.freeform_y_mm,
                    cell.freeform_w_mm,
                    cell.freeform_h_mm,
                )
            else:
                # Split cells: use freeform rect as parent, then sub-layout children
                from src.model.layout_engine import LayoutEngine
                sub_rects: Dict[str, Tuple[float, float, float, float]] = {}
                sub_label: Dict[str, Tuple[float, float, float, float]] = {}
                parent_rect = (cell.freeform_x_mm, cell.freeform_y_mm,
                               cell.freeform_w_mm, cell.freeform_h_mm)
                LayoutEngine._layout_subcells(cell, parent_rect, project.gap_mm,
                                              sub_rects, sub_label, set(), False, 0.0)
                cell_rects.update(sub_rects)
        return LayoutResult(cell_rects=cell_rects, row_heights={}, figure_rects=dict(cell_rects))

    @staticmethod
    def calculate_layout(project: Project) -> LayoutResult:
        """
        Calculates the geometry for all cells in the project.
        All units are in millimeters.
        """
        if getattr(project, 'layout_mode', 'grid') == 'freeform':
            return LayoutEngine.calculate_freeform_layout(project)

        gap_mm = project.gap_mm
        
        # 1. Calculate content area
        content_width = project.page_width_mm - project.margin_left_mm - project.margin_right_mm
        content_height = project.page_height_mm - project.margin_top_mm - project.margin_bottom_mm
        
        if content_width <= 0 or content_height <= 0:
            return LayoutResult({}, {})

        # 2. Determine number of rows
        row_templates = sorted(project.rows, key=lambda r: r.index)
        if not row_templates:
            return LayoutResult({}, {})
            
        num_rows = len(row_templates)
        label_row_above = getattr(project, "label_placement", "in_cell") == "label_row_above"
        if label_row_above:
            custom_h = getattr(project, 'label_row_height', 0.0)
            label_row_h = custom_h if custom_h > 0 else LayoutEngine._label_row_height_mm(project)
        else:
            label_row_h = 0.0

        # Build set of cell_ids that have numbering labels and determine
        # which row indices need a label row.
        labeled_cell_ids: set = set()
        rows_with_labels: set = set()
        if label_row_above:
            for t in project.text_items:
                if t.scope == 'cell' and getattr(t, 'subtype', None) != 'corner' and t.parent_id:
                    labeled_cell_ids.add(t.parent_id)
            # Map cell_id -> row_index
            for c in project.cells:
                if c.id in labeled_cell_ids:
                    rows_with_labels.add(c.row_index)

        # 3. Calculate row heights
        # Subtract vertical gaps between rows.
        # Only rows that actually have labels get a label row above them.
        num_label_rows = len(rows_with_labels) if label_row_above else 0
        total_vertical_gaps = (num_rows - 1) * gap_mm if num_rows > 1 else 0
        if num_label_rows > 0:
            total_vertical_gaps += num_label_rows * gap_mm
            total_label_height = num_label_rows * label_row_h
        else:
            total_label_height = 0.0

        available_height_for_rows = content_height - total_vertical_gaps - total_label_height
        
        if available_height_for_rows < 0:
            available_height_for_rows = 0
            
        total_ratio = sum(r.height_ratio for r in row_templates)
        if total_ratio == 0:
            total_ratio = num_rows
        
        row_heights = {}
        current_y = project.margin_top_mm
        
        calculated_row_geometries = [] # List of (label_y, label_h, pic_y, pic_h, row_template)
        
        for r_temp in row_templates:
            ratio = r_temp.height_ratio if total_ratio > 0 else 1.0
            pic_h = (ratio / total_ratio) * available_height_for_rows
            row_heights[r_temp.index] = pic_h

            if label_row_above and r_temp.index in rows_with_labels:
                lbl_y = current_y
                pic_y = current_y + label_row_h + gap_mm
                calculated_row_geometries.append((lbl_y, label_row_h, pic_y, pic_h, r_temp))
                current_y = pic_y + pic_h + gap_mm
            else:
                calculated_row_geometries.append((None, 0, current_y, pic_h, r_temp))
                current_y += pic_h + gap_mm
            
        # 4. Handle grid mode configuration
        grid_mode = getattr(project, "grid_mode", "stretch")
        row_alignment = getattr(project, "row_alignment", "center")
        
        # Calculate standard column width for fixed grid mode
        max_col_count = max((r.column_count for r in row_templates), default=1)
        standard_col_widths = []
        if grid_mode == "fixed" and max_col_count > 0:
            # Create a dummy row template with max columns to compute standard widths
            # We assume all rows in fixed mode share the column ratios of the widest row
            # If multiple rows have the same max width but different ratios, we just use the first one
            widest_row = next(r for r in row_templates if r.column_count == max_col_count)
            standard_col_widths = LayoutEngine._compute_col_widths(widest_row, content_width, gap_mm)
            
        # 5. Calculate cell rectangles and label cell rectangles
        cell_rects = {}
        label_rects: Dict[str, Tuple[float, float, float, float]] = {}
        
        for lbl_y, lbl_h, pic_y, pic_h, r_temp in calculated_row_geometries:
            col_count = r_temp.column_count
            if col_count <= 0:
                continue

            if grid_mode == "fixed" and max_col_count > 0:
                # Use standard column widths up to this row's column count
                col_widths = standard_col_widths[:col_count]
                row_width = sum(col_widths) + (col_count - 1) * gap_mm if col_count > 1 else sum(col_widths)
                
                # Apply row alignment offset
                if row_alignment == "left":
                    x_offset = project.margin_left_mm
                elif row_alignment == "right":
                    x_offset = project.margin_left_mm + content_width - row_width
                else: # center (default)
                    x_offset = project.margin_left_mm + (content_width - row_width) / 2.0
            else:
                # Stretch mode (default behavior)
                col_widths = LayoutEngine._compute_col_widths(r_temp, content_width, gap_mm)
                x_offset = project.margin_left_mm
                row_width = content_width

            row_cells = [c for c in project.cells if c.row_index == r_temp.index]
            
            for cell in row_cells:
                if cell.col_index >= col_count:
                    continue
                
                x_pos = x_offset
                for i in range(cell.col_index):
                    x_pos += col_widths[i] + gap_mm
                
                col_w = col_widths[cell.col_index]
                cell_rects[cell.id] = (x_pos, pic_y, col_w, pic_h)

                # Label cell rect: for top-level cells (leaf or container) that have a numbering label
                if label_row_above and lbl_y is not None and cell.id in labeled_cell_ids:
                    label_rects[cell.id] = (x_pos, lbl_y, col_w, lbl_h)

                # Recursively layout sub-cells
                if not cell.is_leaf:
                    LayoutEngine._layout_subcells(
                        cell, (x_pos, pic_y, col_w, pic_h),
                        gap_mm, cell_rects, label_rects,
                        labeled_cell_ids, label_row_above, label_row_h
                    )

        figure_rects: Dict[str, Tuple[float, float, float, float]] = dict(cell_rects)

        # Apply grid size overrides (including size-group resolution)
        if getattr(project, 'layout_mode', 'grid') == 'grid':
            # Resolve per-cell effective overrides. Size groups take precedence over per-cell overrides.
            effective_overrides = LayoutEngine._resolve_group_overrides(project, cell_rects)
            for cell in project.get_all_leaf_cells():
                if cell.id in cell_rects:
                    sx, sy, sw, sh = cell_rects[cell.id]
                    eff_ow, eff_oh = effective_overrides.get(
                        cell.id,
                        (getattr(cell, 'override_width_mm', 0.0),
                         getattr(cell, 'override_height_mm', 0.0))
                    )
                    ow = eff_ow
                    oh = eff_oh

                    if ow > 0 or oh > 0:
                        fw = ow if ow > 0 else sw
                        fh = oh if oh > 0 else sh
                        
                        align_h = getattr(cell, 'align_h', 'center')
                        align_v = getattr(cell, 'align_v', 'center')
                        
                        if align_h == 'left':
                            fx = sx
                        elif align_h == 'right':
                            fx = sx + sw - fw
                        else:
                            fx = sx + (sw - fw) / 2.0
                            
                        if align_v == 'top':
                            fy = sy
                        elif align_v == 'bottom':
                            fy = sy + sh - fh
                        else:
                            fy = sy + (sh - fh) / 2.0
                            
                        cell_rects[cell.id] = (fx, fy, fw, fh)
                        figure_rects[cell.id] = (fx, fy, fw, fh)

        # Compute row bounding rects (include label row above if present)
        row_rects: Dict[int, Tuple[float, float, float, float]] = {}
        for _lbl_y, _lbl_h, pic_y, pic_h, r_temp in calculated_row_geometries:
            col_count = r_temp.column_count
            
            # Re-calculate x_offset and row_width for bounding rect
            if grid_mode == "fixed" and max_col_count > 0:
                col_widths = standard_col_widths[:col_count]
                row_width = sum(col_widths) + (col_count - 1) * gap_mm if col_count > 1 else sum(col_widths)
                if row_alignment == "left":
                    x_offset = project.margin_left_mm
                elif row_alignment == "right":
                    x_offset = project.margin_left_mm + content_width - row_width
                else: # center
                    x_offset = project.margin_left_mm + (content_width - row_width) / 2.0
            else:
                x_offset = project.margin_left_mm
                row_width = content_width

            if _lbl_y is not None:
                # Label row sits above picture row; include both in the bounding rect
                top_y = _lbl_y
                total_h = (pic_y - _lbl_y) + pic_h
                row_rects[r_temp.index] = (x_offset, top_y, row_width, total_h)
            else:
                row_rects[r_temp.index] = (x_offset, pic_y, row_width, pic_h)

        return LayoutResult(cell_rects, row_heights, figure_rects=figure_rects, label_rects=label_rects, row_rects=row_rects)

    @staticmethod
    def _resolve_group_overrides(
        project: 'Project',
        natural_cell_rects: Dict[str, Tuple[float, float, float, float]],
    ) -> Dict[str, Tuple[float, float]]:
        """Resolve each cell's effective (override_w, override_h) accounting for size groups.

        Rules:
        - Ungrouped cell: return its own (override_width_mm, override_height_mm).
        - Cell in a group:
            * If group.pinned_width_mm  > 0: effective width  = pinned_width.
              Else: effective width  = min of natural widths of members (program-controlled shared).
            * Same for height independently.
          Per-cell override_width_mm / override_height_mm are ignored for grouped cells
          (the group owns the shared size).
        """
        result: Dict[str, Tuple[float, float]] = {}
        groups = getattr(project, 'size_groups', []) or []
        if not groups:
            # No groups: just return per-cell overrides.
            for cell in project.get_all_leaf_cells():
                result[cell.id] = (
                    getattr(cell, 'override_width_mm', 0.0),
                    getattr(cell, 'override_height_mm', 0.0),
                )
            return result

        # Pre-compute natural sizes per group (for program-controlled shared sizing).
        group_natural_min_w: Dict[str, float] = {}
        group_natural_min_h: Dict[str, float] = {}
        for g in groups:
            members = [c for c in project.get_all_leaf_cells() if c.size_group_id == g.id]
            ws, hs = [], []
            for m in members:
                if m.id in natural_cell_rects:
                    _, _, nw, nh = natural_cell_rects[m.id]
                    if nw > 0:
                        ws.append(nw)
                    if nh > 0:
                        hs.append(nh)
            group_natural_min_w[g.id] = min(ws) if ws else 0.0
            group_natural_min_h[g.id] = min(hs) if hs else 0.0

        # Resolve per-cell effective overrides.
        for cell in project.get_all_leaf_cells():
            gid = getattr(cell, 'size_group_id', None)
            if gid:
                g = next((x for x in groups if x.id == gid), None)
                if g is None:
                    # Orphan reference: fall back to per-cell.
                    result[cell.id] = (
                        getattr(cell, 'override_width_mm', 0.0),
                        getattr(cell, 'override_height_mm', 0.0),
                    )
                    continue
                eff_w = g.pinned_width_mm if g.pinned_width_mm > 0 else group_natural_min_w.get(g.id, 0.0)
                eff_h = g.pinned_height_mm if g.pinned_height_mm > 0 else group_natural_min_h.get(g.id, 0.0)
                result[cell.id] = (eff_w, eff_h)
            else:
                result[cell.id] = (
                    getattr(cell, 'override_width_mm', 0.0),
                    getattr(cell, 'override_height_mm', 0.0),
                )
        return result

    @staticmethod
    def _layout_subcells(
        parent_cell: 'Cell',
        parent_rect: Tuple[float, float, float, float],
        gap_mm: float,
        cell_rects: Dict[str, Tuple[float, float, float, float]],
        label_rects: Dict[str, Tuple[float, float, float, float]],
        labeled_cell_ids: set,
        label_row_above: bool,
        label_row_h: float,
    ):
        """Recursively compute geometry for sub-cells within a parent cell."""
        children = parent_cell.children
        if not children:
            return

        px, py, pw, ph = parent_rect
        n = len(children)
        ratios = list(parent_cell.split_ratios) if parent_cell.split_ratios else [1.0] * n
        while len(ratios) < n:
            ratios.append(1.0)
        ratios = ratios[:n]
        total_ratio = sum(ratios)
        if total_ratio <= 0:
            total_ratio = float(n)

        total_gap = (n - 1) * gap_mm if n > 1 else 0.0

        if parent_cell.split_direction == "vertical":
            # --- Vertical stacking: divide height ---
            # Account for label rows above leaf children and fixed-height children.
            label_space = 0.0
            fixed_h_total = 0.0
            ratio_sum = 0.0
            for i, child in enumerate(children):
                if label_row_above and child.is_leaf and child.id in labeled_cell_ids:
                    label_space += label_row_h + gap_mm
                oh = getattr(child, 'override_height_mm', 0.0)
                if oh > 0:
                    fixed_h_total += oh
                else:
                    ratio_sum += ratios[i]
            if ratio_sum <= 0:
                ratio_sum = 1.0

            available = ph - total_gap - label_space - fixed_h_total
            if available < 0:
                available = 0
            current_y = py
            for i, child in enumerate(children):
                # Label rect for this child (above it)
                if label_row_above and child.is_leaf and child.id in labeled_cell_ids:
                    label_rects[child.id] = (px, current_y, pw, label_row_h)
                    current_y += label_row_h + gap_mm

                oh = getattr(child, 'override_height_mm', 0.0)
                child_h = oh if oh > 0 else (ratios[i] / ratio_sum) * available
                child_rect = (px, current_y, pw, child_h)
                cell_rects[child.id] = child_rect

                if not child.is_leaf:
                    LayoutEngine._layout_subcells(
                        child, child_rect, gap_mm, cell_rects,
                        label_rects, labeled_cell_ids, label_row_above, label_row_h
                    )
                current_y += child_h + gap_mm

        elif parent_cell.split_direction == "horizontal":
            # --- Horizontal stacking: divide width ---
            # Account for fixed-width children; ratio children share the remainder.
            fixed_w_total = 0.0
            ratio_sum = 0.0
            for i, child in enumerate(children):
                ow = getattr(child, 'override_width_mm', 0.0)
                if ow > 0:
                    fixed_w_total += ow
                else:
                    ratio_sum += ratios[i]
            if ratio_sum <= 0:
                ratio_sum = 1.0

            available = max(0.0, pw - total_gap - fixed_w_total)

            # If any direct leaf child is labeled, reserve a label strip at the
            # top of the shared height band.  All children must start at the same
            # y, so the overhead applies to every child once any one needs it.
            any_labeled_leaf = label_row_above and any(
                child.is_leaf and child.id in labeled_cell_ids for child in children
            )
            label_overhead = (label_row_h + gap_mm) if any_labeled_leaf else 0.0
            img_py = py + label_overhead
            img_ph = max(0.0, ph - label_overhead)

            current_x = px
            for i, child in enumerate(children):
                ow = getattr(child, 'override_width_mm', 0.0)
                child_w = ow if ow > 0 else (ratios[i] / ratio_sum) * available

                # Label rect: spans the child's width, sits in the reserved strip
                if label_row_above and child.is_leaf and child.id in labeled_cell_ids:
                    label_rects[child.id] = (current_x, py, child_w, label_row_h)

                child_rect = (current_x, img_py, child_w, img_ph)
                cell_rects[child.id] = child_rect

                if not child.is_leaf:
                    LayoutEngine._layout_subcells(
                        child, child_rect, gap_mm, cell_rects,
                        label_rects, labeled_cell_ids, label_row_above, label_row_h
                    )
                current_x += child_w + gap_mm
