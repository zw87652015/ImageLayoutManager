"""Qt-free geometry helpers for vector marks.

All points are (x, y) pairs in millimetres, the same units as the canvas
scene. Used by the draw tools, the canvas item's handle drags, and tests.
"""
import math
from typing import List, Sequence

MIN_SIZE_MM = 0.3

BOX_HANDLES = ("tl", "t", "tr", "r", "br", "b", "bl", "l")


def _xy(p):
    return float(p[0]), float(p[1])


def snap_angle(anchor, p, step_deg: float = 45.0):
    """Project *p* onto the nearest ray at a multiple of *step_deg* from
    *anchor*, preserving the distance |p - anchor|."""
    ax, ay = _xy(anchor)
    px, py = _xy(p)
    dx, dy = px - ax, py - ay
    dist = math.hypot(dx, dy)
    if dist == 0:
        return [ax, ay]
    angle = math.atan2(dy, dx)
    step = math.radians(step_deg)
    snapped = round(angle / step) * step
    return [ax + dist * math.cos(snapped), ay + dist * math.sin(snapped)]


def normalize_box(points):
    """Return [[x0, y0], [x1, x1]] with top-left first."""
    (x0, y0), (x1, y1) = (_xy(points[0]), _xy(points[1]))
    return [[min(x0, x1), min(y0, y1)], [max(x0, x1), max(y0, y1)]]


def constrain_box(anchor, p, square: bool, from_center: bool):
    """Normalized [[x0,y0],[x1,y1]] box from *anchor* to *p*.

    square: side = max(|dx|, |dy|), keeping the drag direction's sign per
    axis. from_center: *anchor* is the centre and *p* a corner.
    """
    ax, ay = _xy(anchor)
    px, py = _xy(p)
    dx, dy = px - ax, py - ay
    if square:
        side = max(abs(dx), abs(dy))
        dx = math.copysign(side, dx) if dx else side
        dy = math.copysign(side, dy) if dy else side
    if from_center:
        return normalize_box([[ax - dx, ay - dy], [ax + dx, ay + dy]])
    return normalize_box([[ax, ay], [ax + dx, ay + dy]])


def box_handle_points(points):
    """Handle scene positions for a (normalized) box, in BOX_HANDLES order."""
    (x0, y0), (x1, y1) = normalize_box(points)
    mx, my = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    return {
        "tl": (x0, y0), "t": (mx, y0), "tr": (x1, y0), "r": (x1, my),
        "br": (x1, y1), "b": (mx, y1), "bl": (x0, y1), "l": (x0, my),
    }


_OPPOSITE = {"tl": "br", "t": "b", "tr": "bl", "r": "l",
             "br": "tl", "b": "t", "bl": "tr", "l": "r"}


def resize_box(points, handle, p, keep_aspect):
    """Resize the box by dragging *handle* to *p*; opposite edge/corner fixed.

    keep_aspect only affects corner handles: the original w/h ratio is kept,
    the size driven by the larger relative change. Flipping is allowed.
    """
    hp = box_handle_points(points)
    if handle not in hp:
        raise ValueError(f"unknown box handle: {handle}")
    (x0, y0), (x1, y1) = normalize_box(points)
    fix = hp[_OPPOSITE[handle]]
    px, py = _xy(p)

    if keep_aspect and handle in ("tl", "tr", "br", "bl"):
        w, h = x1 - x0, y1 - y0
        if w > 0 and h > 0:
            dx = abs(px - fix[0]) / w
            dy = abs(py - fix[1]) / h
            scale = max(dx, dy)
            new_w, new_h = w * scale, h * scale
            sign_x = 1.0 if px >= fix[0] else -1.0
            sign_y = 1.0 if py >= fix[1] else -1.0
            px = fix[0] + sign_x * new_w
            py = fix[1] + sign_y * new_h
    return normalize_box([[fix[0], fix[1]], [px, py]])


def move_vertex(points, index, p, shift: bool, closed: bool):
    """Move vertex *index* to *p*; Shift snaps to 45° relative to a neighbour."""
    pts = [list(_xy(pt)) for pt in points]
    if not 0 <= index < len(pts):
        raise ValueError(f"vertex index out of range: {index}")
    if shift and len(pts) > 1:
        if index > 0:
            neighbour = pts[index - 1]
        elif closed:
            neighbour = pts[-1]
        else:
            neighbour = pts[1]
        pts[index] = snap_angle(neighbour, p)
    else:
        pts[index] = list(_xy(p))
    return pts


def translate(points, dx, dy, shift: bool):
    """Translate all points; Shift keeps only the dominant axis."""
    if shift:
        if abs(dx) >= abs(dy):
            dy = 0.0
        else:
            dx = 0.0
    return [[x + dx, y + dy] for x, y in points]


def _span(values):
    return max(values) - min(values) if values else 0.0


def is_degenerate(kind, points, closed=True):
    """True when the shape would be invisible or invalid."""
    pts = [list(_xy(p)) for p in points]
    if kind == "dot":
        return len(pts) != 1
    if kind == "line":
        return len(pts) != 2 or math.hypot(
            pts[1][0] - pts[0][0], pts[1][1] - pts[0][1]) < MIN_SIZE_MM
    if kind in ("rect", "ellipse"):
        if len(pts) != 2:
            return True
        (x0, y0), (x1, y1) = normalize_box(pts)
        return x1 - x0 < MIN_SIZE_MM or y1 - y0 < MIN_SIZE_MM
    if kind == "polygon":
        need = 3 if closed else 2
        return (len(pts) < need or _span([p[0] for p in pts]) < MIN_SIZE_MM
                and _span([p[1] for p in pts]) < MIN_SIZE_MM)
    return True


def snap_rotation(rad: float, step_deg: float = 15.0) -> float:
    """Snap an angle (radians) to the nearest multiple of step_deg."""
    step = math.radians(step_deg)
    return round(rad / step) * step


def regular_polygon_points(cx, cy, radius, sides: int, rotation_rad):
    """Vertices of a regular polygon: vertex k sits at
    ``rotation_rad + k*2π/sides`` (scene y grows downward, so
    rotation = -π/2 puts a vertex straight up)."""
    cx, cy, radius = float(cx), float(cy), float(radius)
    step = 2.0 * math.pi / sides
    return [[cx + radius * math.cos(rotation_rad + k * step),
             cy + radius * math.sin(rotation_rad + k * step)]
            for k in range(sides)]


def regular_polygon_params(points):
    """Return ``(cx, cy, radius, rotation_rad)`` if *points* form a regular
    polygon, else None. Regularity means: n >= 3, all centroid distances
    equal within 1e-3 relative, and equal consecutive angular steps of
    2π/n (same winding direction) within 1e-3 rad. Translation-safe."""
    pts = [list(_xy(p)) for p in points]
    n = len(pts)
    if n < 3:
        return None
    cx = sum(p[0] for p in pts) / n
    cy = sum(p[1] for p in pts) / n
    radii = [math.hypot(p[0] - cx, p[1] - cy) for p in pts]
    radius = sum(radii) / n
    if radius <= 0 or max(radii) - min(radii) > 1e-3 * radius:
        return None
    angles = [math.atan2(p[1] - cy, p[0] - cx) for p in pts]
    step = 2.0 * math.pi / n
    two_pi = 2.0 * math.pi
    # Signed step between consecutive vertices; each diff is unwrapped
    # relative to the first so orientation (cw/ccw) must be consistent.
    diffs = [angles[(i + 1) % n] - angles[i] for i in range(n)]
    # Wrap the reference step into (-π, π]: atan2 jumps at ±π, so e.g. a
    # +120° triangle step can read as -240°. |2π/n| <= 120° for n >= 3.
    s0 = math.remainder(diffs[0], two_pi)
    if abs(s0 - step) > 1e-3 and abs(s0 + step) > 1e-3:
        return None
    for d in diffs:
        d -= round((d - s0) / two_pi) * two_pi
        if abs(d - s0) > 1e-3:
            return None
    return (cx, cy, radius, angles[0])
