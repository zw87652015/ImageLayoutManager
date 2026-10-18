"""Qt-free geometry for the text-group chips.

Chip layout (left to right): colour dot, name, size field, up/down stepper
column, hover ×. ``chip_regions`` returns float ``(x, y, w, h)`` tuples;
``TextGroupChips`` wraps them in ``QRectF``.
"""

SIZE_MIN = 1.0
SIZE_MAX = 200.0
STEP_W = 14


def step_size(value: float, delta: float) -> float:
    """One stepper/wheel/arrow step: *value + delta* clamped and rounded."""
    return round(min(SIZE_MAX, max(SIZE_MIN, value + delta)), 2)


def chip_width(name_w: float, size_w: float) -> float:
    """Full chip width for a name of *name_w* and a size text of *size_w*."""
    return 12 + 10 + 6 + name_w + 10 + (size_w + 8) + 2 + STEP_W + 2 + 22


def chip_regions(left: float, top: float, width: float, height: float,
                 size_w: float) -> dict:
    """Hit/paint regions of one chip: ``x``, ``up``, ``down``, ``size``, ``name``."""
    right = left + width
    x = (right - 20, top + 6, 16, 16)
    step_x = x[0] - 2 - STEP_W
    half = (height - 6) / 2
    up = (step_x, top + 3, STEP_W, half)
    down = (step_x, top + 3 + half, STEP_W, height - 6 - half)
    size = (step_x - 2 - (size_w + 8), top + 4, size_w + 8, height - 8)
    name = (left + 28, top, max(0.0, size[0] - 2 - (left + 28)), height)
    return {"x": x, "up": up, "down": down, "size": size, "name": name}
