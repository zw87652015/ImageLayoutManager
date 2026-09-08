"""Physical scale of a cell's image content on the page."""

from typing import Optional, Tuple


def panel_mm_per_unit(project, cell, unit_w: float, unit_h: float,
                      layout_result=None,
                      content_size_mm: Optional[Tuple[float, float]] = None) -> float:
    """Millimetres on the page covered by one image unit (pixel / SVG px).

    Mirrors the fit/crop/rotation maths in the exporters and ``CellItem`` so
    text size compensation stays in sync with what is actually drawn.  Falls
    back to 1.0 when the cell has no geometry yet.
    """
    from src.model.layout_engine import LayoutEngine

    if content_size_mm is None:
        if layout_result is None:
            layout_result = LayoutEngine.calculate_layout(project)
        rect = layout_result.cell_rects.get(cell.id)
        if rect is None:
            return 1.0
        width, height = rect[2:]
        if project.layout_mode != 'freeform':
            width -= cell.padding_left + cell.padding_right
            height -= cell.padding_top + cell.padding_bottom
    else:
        width, height = content_size_mm
    if width <= 0 or height <= 0 or unit_w <= 0 or unit_h <= 0:
        return 1.0

    crop_w = unit_w * max(0.001, cell.crop_right - cell.crop_left)
    crop_h = unit_h * max(0.001, cell.crop_bottom - cell.crop_top)
    if cell.rotation in (90, 270):
        crop_w, crop_h = crop_h, crop_w
    fit = min if cell.fit_mode == 'contain' else max
    return fit(width / crop_w, height / crop_h)
