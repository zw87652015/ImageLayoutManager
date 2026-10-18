"""Text frame for rotated raster text regions.

Rotated labels (e.g. the tilted axis titles of 3D surface renders) come back
from OCR as a quadrilateral, not an axis-aligned box.  To reuse the whole
axis-aligned analysis/extraction machinery, the label's geometry is rotated
into a *text frame*: a coordinate system whose x-axis runs along the text
baseline, defined as a rotation about the image origin.

Conventions
-----------
``angle`` is the baseline direction in degrees in image coordinates
(x right, y down), normalised to (-90, 90].  ``to_text`` maps an image
pixel coordinate to the text frame, ``to_image`` is its inverse; both are
the identity at ``angle == 0``.

When a region/detection carries ``angle != 0``, its ``x, y, w, h`` — and any
per-character ``chars`` boxes — are expressed in the text frame and may be
negative.  When ``angle == 0`` everything is plain image pixels, exactly as
before.  Pixel centres sit at integer-plus-0.5 coordinates in every frame.
"""

from __future__ import annotations

import math
from typing import Sequence, Tuple

# Angles within this many degrees of horizontal or vertical keep the existing
# axis-aligned / 90-degree code path unchanged.
_SNAP_DEG = 5.0


def _norm(deg: float) -> float:
    """Normalise a direction angle to (-90, 90]."""
    deg = math.fmod(deg, 180.0)
    if deg <= -90.0:
        deg += 180.0
    elif deg > 90.0:
        deg -= 180.0
    return deg


def snap_angle(deg: float) -> float:
    """0.0 for near-axis-aligned text (keeps the old code path); otherwise
    the normalised angle rounded to 0.01."""
    deg = _norm(float(deg))
    if abs(deg) <= _SNAP_DEG or abs(deg) >= 90.0 - _SNAP_DEG:
        return 0.0
    return round(deg, 2)


def to_text(px: float, py: float, angle: float) -> Tuple[float, float]:
    """Image coordinates -> text frame (rotation about the image origin)."""
    a = math.radians(angle)
    c, s = math.cos(a), math.sin(a)
    return px * c + py * s, -px * s + py * c


def to_image(u: float, v: float, angle: float) -> Tuple[float, float]:
    """Text frame -> image coordinates (inverse of ``to_text``)."""
    a = math.radians(angle)
    c, s = math.cos(a), math.sin(a)
    return u * c - v * s, u * s + v * c


def quad_angle(points: Sequence) -> float:
    """Baseline direction of an OCR quad, degrees in (-90, 90].

    *points* are the four corners in RapidOCR order (TL, TR, BR, BL); the
    first edge p0 -> p1 runs along the text baseline.
    """
    (x0, y0), (x1, y1) = (float(points[0][0]), float(points[0][1])), \
                         (float(points[1][0]), float(points[1][1]))
    return _norm(math.degrees(math.atan2(y1 - y0, x1 - x0)))


def quad_box(points: Sequence, angle: float) -> Tuple[int, int, int, int]:
    """Axis-aligned box of *points* measured in the text frame of *angle*.

    Returns ``(x, y, w, h)`` in text-frame coordinates (which may be
    negative); at ``angle == 0`` this is the plain image-pixel AABB.
    """
    us, vs = [], []
    for p in points:
        u, v = to_text(float(p[0]), float(p[1]), angle)
        # 1e-9 rounding keeps exact trig cases (90°, 45°, …) from inflating
        # the box by a noise pixel.
        us.append(round(u, 9))
        vs.append(round(v, 9))
    u0, u1 = math.floor(min(us)), math.ceil(max(us))
    v0, v1 = math.floor(min(vs)), math.ceil(max(vs))
    return int(u0), int(v0), max(1, int(u1 - u0)), max(1, int(v1 - v0))


def image_bounds(x: int, y: int, w: int, h: int, angle: float) -> Tuple[int, int, int, int]:
    """Image-pixel AABB of the text-frame box ``(x, y, w, h)``."""
    if angle == 0:
        return x, y, w, h
    xs, ys = [], []
    for u, v in ((x, y), (x + w, y), (x + w, y + h), (x, y + h)):
        px, py = to_image(u, v, angle)
        xs.append(round(px, 9))
        ys.append(round(py, 9))
    x0, x1 = math.floor(min(xs)), math.ceil(max(xs))
    y0, y1 = math.floor(min(ys)), math.ceil(max(ys))
    return int(x0), int(y0), int(x1 - x0), int(y1 - y0)
