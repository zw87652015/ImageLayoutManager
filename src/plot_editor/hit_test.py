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


def _pick_map(mapping, fx, fy, prefix):
    """First id in ``{id: bbox}`` whose bbox contains (fx, fy)."""
    for rid, entry in (mapping or {}).items():
        bbox = entry.get('bbox') if isinstance(entry, dict) else entry
        if rect_hit(bbox, fx, fy):
            return prefix + rid
    return None


def pick(regions, fx, fy):
    """Topmost element under figure-fraction ``(fx, fy)``.

    Priority: annotation > bracket > legend > title > xlabel > ylabel
    > xticks > yticks > violin/stack bboxes. Series (proximity) and
    frame (fallback) are handled separately.
    """
    if not regions:
        return None
    hit = _pick_map(regions.get('annotations'), fx, fy, 'annotation:')
    if hit:
        return hit
    hit = _pick_map(regions.get('brackets'), fx, fy, 'bracket:')
    if hit:
        return hit
    for key in _PRIORITY:
        if rect_hit(regions.get(key), fx, fy):
            return key
    hit = _pick_map(regions.get('violins'), fx, fy, 'violin:')
    if hit:
        return hit
    hit = _pick_map(regions.get('stacks'), fx, fy, 'stack:')
    if hit:
        return hit
    return _pick_map(regions.get('hists'), fx, fy, 'hist:')


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


def _point_in_polygon(points, fx, fy):
    """Ray-casting point-in-polygon over ``[(x, y), ...]``."""
    if not points or len(points) < 3:
        return False
    inside = False
    j = len(points) - 1
    for i, (xi, yi) in enumerate(points):
        xj, yj = points[j]
        if (yi > fy) != (yj > fy) \
                and fx < (xj - xi) * (fy - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def pick_area(regions, fx, fy):
    """``'band:<id>'`` / ``'span:<id>'`` under figure-fraction ``(fx, fy)``
    using point-in-polygon on each region's ``points`` (bands checked
    before spans; last-drawn first). ``None`` on a miss — including a
    point inside the bbox but outside the polygon."""
    if not regions:
        return None
    for coll, prefix in (('bands', 'band:'), ('spans', 'span:')):
        entries = regions.get(coll) or {}
        for rid, entry in reversed(list(entries.items())):
            if _point_in_polygon(entry.get('points'), fx, fy):
                return prefix + rid
    return None


def pick_frame(regions, fx, fy):
    """'frame' when ``(fx, fy)`` is inside the axes bbox, else None."""
    return 'frame' if rect_hit((regions or {}).get('frame'), fx, fy) \
        else None


def figure_to_axes(regions, fx, fy):
    """Figure fraction (top-left origin) → axes fraction (bottom-left
    origin, matplotlib's transAxes). ``None`` without a frame region."""
    bbox = (regions or {}).get('frame')
    if not bbox:
        return None
    x0, y0, x1, y1 = bbox
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0:
        return None
    return (fx - x0) / w, 1.0 - (fy - y0) / h


def axes_to_figure(regions, ax_, ay):
    """Axes fraction → figure fraction; ``None`` without a frame."""
    bbox = (regions or {}).get('frame')
    if not bbox:
        return None
    x0, y0, x1, y1 = bbox
    return x0 + ax_ * (x1 - x0), y0 + (1.0 - ay) * (y1 - y0)
