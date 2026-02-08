from dataclasses import dataclass, field
from typing import List, Dict, Tuple
from .data_model import Project, Cell, RowTemplate

@dataclass
class LayoutResult:
    cell_rects: Dict[str, Tuple[float, float, float, float]]
    row_heights: Dict[int, float]
    figure_rects: Dict[str, Tuple[float, float, float, float]] = field(default_factory=dict)
    label_rects: Dict[str, Tuple[float, float, float, float]] = field(default_factory=dict)

class LayoutEngine:
    @staticmethod
    def _label_row_height_mm(project: Project) -> float:
        """Height of a label row based on label font settings."""
        pt_to_mm = 0.3528
        h = project.label_font_size * pt_to_mm * 1.2 + 2.0
        return max(3.0, min(15.0, h))

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
    def calculate_layout(project: Project) -> LayoutResult:
        """
        Calculates the geometry for all cells in the project.
        All units are in millimeters.
        """
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
            
        # 4. Calculate cell rectangles and label cell rectangles
        cell_rects = {}
        label_rects: Dict[str, Tuple[float, float, float, float]] = {}
        
        for lbl_y, lbl_h, pic_y, pic_h, r_temp in calculated_row_geometries:
            col_widths = LayoutEngine._compute_col_widths(r_temp, content_width, gap_mm)
            col_count = r_temp.column_count
            if col_count <= 0:
                continue

            row_cells = [c for c in project.cells if c.row_index == r_temp.index]
            
            for cell in row_cells:
                if cell.col_index >= col_count:
                    continue
                
                x_pos = project.margin_left_mm
                for i in range(cell.col_index):
                    x_pos += col_widths[i] + gap_mm
                
                col_w = col_widths[cell.col_index]
                cell_rects[cell.id] = (x_pos, pic_y, col_w, pic_h)

                # Label cell rect: only for cells that have a numbering label
                if label_row_above and lbl_y is not None and cell.id in labeled_cell_ids:
                    label_rects[cell.id] = (x_pos, lbl_y, col_w, lbl_h)

        figure_rects: Dict[str, Tuple[float, float, float, float]] = dict(cell_rects)

        return LayoutResult(cell_rects, row_heights, figure_rects=figure_rects, label_rects=label_rects)
