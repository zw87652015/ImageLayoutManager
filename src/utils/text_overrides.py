"""Shared entry-point for exporters: per-cell SVG / raster text overrides."""

from typing import Optional, Tuple


def overrides_for_cell(project, cell, layout_result, content_size_mm: Optional[Tuple[float, float]] = None):
    """Return ``(svg_override_bytes, raster_override_spec)`` for *cell*.

    Either value is None when the corresponding pipeline has nothing to do.
    """
    path = getattr(cell, 'image_path', None) or ''
    if path.lower().endswith('.svg'):
        from src.utils.svg_text_utils import get_svg_override_bytes_for_cell
        return get_svg_override_bytes_for_cell(project, cell, layout_result, content_size_mm), None
    from src.utils.raster_text_utils import build_raster_override_spec
    return None, build_raster_override_spec(project, cell, layout_result, content_size_mm)
