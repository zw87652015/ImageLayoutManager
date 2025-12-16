from dataclasses import dataclass
from typing import List, Dict, Tuple
from .data_model import Project, Cell, RowTemplate

@dataclass
class LayoutResult:
    # Map cell ID to (x, y, width, height) in millimeters
    cell_rects: Dict[str, Tuple[float, float, float, float]]
    # Map row index to row height in millimeters
    row_heights: Dict[int, float]

class LayoutEngine:
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
        
        # 3. Calculate row heights
        # Strategy: Distribute content_height according to height_ratio
        # Subtract vertical gaps between rows
        total_vertical_gaps = (num_rows - 1) * gap_mm if num_rows > 1 else 0
        available_height_for_rows = content_height - total_vertical_gaps
        
        if available_height_for_rows < 0:
            available_height_for_rows = 0 # Should probably warn
            
        total_ratio = sum(r.height_ratio for r in row_templates)
        if total_ratio == 0:
            total_ratio = num_rows # Fallback to equal
        
        row_heights = {}
        current_y = project.margin_top_mm
        
        calculated_row_geometries = [] # List of (y, height, row_template)
        
        for r_temp in row_templates:
            ratio = r_temp.height_ratio if total_ratio > 0 else 1.0
            h = (ratio / total_ratio) * available_height_for_rows
            row_heights[r_temp.index] = h
            calculated_row_geometries.append((current_y, h, r_temp))
            current_y += h + gap_mm
            
        # 4. Calculate cell rectangles
        cell_rects = {}
        
        # Helper to find cell by row/col
        # We iterate through cells and place them
        # Note: Ideally the model ensures cells exist for the grid. 
        # If not, we calculate potential positions for them.
        
        # We iterate through the CALCULATED rows and place cells that belong to them.
        for y_pos, r_h, r_temp in calculated_row_geometries:
            col_count = r_temp.column_count
            if col_count <= 0:
                continue
                
            # Subtract horizontal gaps
            total_horizontal_gaps = (col_count - 1) * gap_mm if col_count > 1 else 0
            available_width_for_cols = content_width - total_horizontal_gaps
            
            # Calculate column widths based on column_ratios (if provided) or equal distribution
            col_ratios = r_temp.column_ratios if r_temp.column_ratios else [1.0] * col_count
            # Ensure we have enough ratios
            while len(col_ratios) < col_count:
                col_ratios.append(1.0)
            col_ratios = col_ratios[:col_count]
            
            total_ratio = sum(col_ratios)
            if total_ratio <= 0:
                total_ratio = col_count
            
            col_widths = [(r / total_ratio) * available_width_for_cols for r in col_ratios]
            
            # Find cells in this row
            row_cells = [c for c in project.cells if c.row_index == r_temp.index]
            
            for cell in row_cells:
                if cell.col_index >= col_count:
                    continue # Cell out of bounds of current grid definition
                
                # Calculate x position by summing previous column widths + gaps
                x_pos = project.margin_left_mm
                for i in range(cell.col_index):
                    x_pos += col_widths[i] + gap_mm
                
                col_w = col_widths[cell.col_index]
                cell_rects[cell.id] = (x_pos, y_pos, col_w, r_h)
                
        return LayoutResult(cell_rects, row_heights)
