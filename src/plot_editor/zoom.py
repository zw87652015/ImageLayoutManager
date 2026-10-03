"""Worksheet view-zoom math (pure Python, no Qt)."""

ZOOM_MIN = 0.5
ZOOM_MAX = 3.0
ZOOM_STEP = 1.1


def next_zoom(current, steps):
    """``current * ZOOM_STEP**steps`` clamped to [ZOOM_MIN, ZOOM_MAX]."""
    return min(ZOOM_MAX,
               max(ZOOM_MIN, current * (ZOOM_STEP ** steps)))
