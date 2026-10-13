"""Stepping and labels for spin boxes whose minimum value means "Auto".

Qt-free: the Inspector's AutoDoubleSpinBox and the payload helpers use these.
"""

import math
from typing import Optional, Tuple


def _finite(value) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def auto_step_target(value, minimum, maximum, auto_value, single_step, steps, decimals) -> Optional[float]:
    """Target value for stepping an Auto (minimum) spin box, or None.

    From Auto, the first step starts at the effective auto value rather than
    at the minimum; stepping far enough down returns to the minimum.
    """
    auto = _finite(auto_value)
    if auto is None or auto <= minimum:
        return None
    if abs(value - minimum) >= 10 ** -(decimals + 1):
        return None
    target = round(auto, decimals) + steps * single_step
    target = min(maximum, max(minimum, target))
    return round(target, decimals)


def auto_label(base_label, auto_value, decimals, suffix) -> str:
    auto = _finite(auto_value)
    if auto is None:
        return base_label
    return f"{base_label} ({auto:.{decimals}f}{suffix})"


def effective_cell_size(layout, cell_id) -> Tuple[Optional[float], Optional[float]]:
    """Laid-out (w, h) of a cell box, or (None, None) when unavailable.

    ``cell_rects`` holds the box after grid overrides and size groups are
    applied (``figure_rects`` is an identical copy in grid mode), so with an
    Auto override this is the size the engine actually uses.
    """
    rects = getattr(layout, 'cell_rects', None) or {}
    rect = rects.get(cell_id)
    if rect is None:
        return None, None
    return rect[2], rect[3]


def effective_subcell_size(layout, cell_id, direction) -> Optional[float]:
    """Laid-out size of a split child along its parent's split axis."""
    w, h = effective_cell_size(layout, cell_id)
    if w is None:
        return None
    return h if direction == "vertical" else w
