"""Pure geometry helpers for plot-element hit-testing (no Qt).

Regions come from ``render.element_regions``: figure fractions with a
top-left origin, bboxes as ``(x0, y0, x1, y1)``. Series entries are
``{id: {'bbox': bbox, 'points': [(fx, fy), ...]}}``.
"""

_PRIORITY = ('legend', 'title', 'xlabel', 'ylabel', 'xticks', 'yticks')


def frac_to_rect(bbox, width, height):
    """Fraction bbox ``(x0, y0, x1, y1)`` → pixel rect on a ``width``×
    ``height`` figure (top-left origin)."""
    x0, y0, x1, y1 = bbox
    return (x0 * width, y0 * height, x1 * width, y1 * height)


def rect_hit(bbox, x, y):
    """True when ``(x, y)`` lies inside bbox ``(x0, y0, x1, y1)``."""
    return bbox is not None \
        and bbox[0] <= x <= bbox[2] and bbox[1] <= y <= bbox[3]


def point_segment_distance(px, py, ax, ay, bx, by):
    """Distance from ``(px, py)`` to segment ``(ax, ay)-(bx, by)``."""
    dx, dy = bx - ax, by - ay
    length_sq = dx * dx + dy * dy
    if length_sq == 0:
        return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length_sq))
    cx, cy = ax + t * dx, ay + t * dy
    return ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5


def polyline_distance(points, x, y):
    """Min distance from ``(x, y)`` to the polyline/its points, or None."""
    if not points:
        return None
    if len(points) == 1:
        return ((x - points[0][0]) ** 2 + (y - points[0][1]) ** 2) ** 0.5
    return min(
        point_segment_distance(x, y, a[0], a[1], b[0], b[1])
        for a, b in zip(points, points[1:]))


def pick(regions, fx, fy):
    """Topmost text/legend element under figure-fraction ``(fx, fy)``.

    Priority: legend > title > xlabel > ylabel > xticks > yticks.
    Series and frame are handled separately (proximity / fallback).
    """
    if not regions:
        return None
    for key in _PRIORITY:
        if rect_hit(regions.get(key), fx, fy):
            return key
    return None


def pick_series(series, x, y, tol):
    """Series id whose padded bbox contains ``(x, y)`` and whose polyline
    comes within ``tol``; ``x/y/tol`` are in the caller's coords (view px).
    ``series`` maps id → ``{'bbox': view bbox, 'points': view points}``."""
    if not series:
        return None
    for sid, entry in series.items():
        bbox = entry.get('bbox')
        if bbox is not None and not (
                bbox[0] - tol <= x <= bbox[2] + tol
                and bbox[1] - tol <= y <= bbox[3] + tol):
            continue
        d = polyline_distance(entry.get('points') or [], x, y)
        if d is not None and d <= tol:
            return sid
    return None


def pick_frame(regions, fx, fy):
    """'frame' when ``(fx, fy)`` is inside the axes bbox, else None."""
    return 'frame' if rect_hit((regions or {}).get('frame'), fx, fy) \
        else None
