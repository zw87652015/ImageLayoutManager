"""Single source of truth for drawing vector marks.

The canvas item, raster exporter, SVG export and PDF exporter all call
:func:`draw`, so a mark looks identical on screen and on paper. Geometry is
computed in millimetres; callers supply the mm-to-device *scale* (the canvas
passes 1.0 because its scene units are already mm).
"""
import math
from typing import List, Tuple

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import (
    QColor, QPainter, QPainterPath, QPainterPathStroker, QPen, QTransform,
)

from src.utils.mark_geometry import normalize_box

PT_TO_MM = 25.4 / 72.0

_QT_STYLES = {
    "solid": Qt.PenStyle.SolidLine,
    "dashed": Qt.PenStyle.DashLine,
    "dotted": Qt.PenStyle.DotLine,
    "dash_dot": Qt.PenStyle.DashDotLine,
}


def stroke_mm(mark) -> float:
    return max(0.0, float(mark.stroke_width_pt)) * PT_TO_MM


def _open(mark) -> bool:
    return mark.kind == "line" or (mark.kind == "polygon" and not mark.closed)


def geometry_path(mark) -> QPainterPath:
    """Full unshortened outline of the mark in mm."""
    path = QPainterPath()
    pts = mark.points
    if not pts:
        return path
    if mark.kind == "dot":
        r = mark.dot_diameter_mm / 2.0
        path.addEllipse(pts[0][0] - r, pts[0][1] - r, 2 * r, 2 * r)
    elif mark.kind in ("rect", "ellipse"):
        (x0, y0), (x1, y1) = normalize_box(pts)
        if mark.kind == "rect":
            path.addRect(x0, y0, x1 - x0, y1 - y0)
        else:
            path.addEllipse(x0, y0, x1 - x0, y1 - y0)
    else:
        path.moveTo(pts[0][0], pts[0][1])
        for x, y in pts[1:]:
            path.lineTo(x, y)
        if mark.kind == "polygon" and mark.closed:
            path.closeSubpath()
    return path


def _shorten_for(style, length_mm, width_mm) -> float:
    """How much of the end segment an arrowhead covers (small overlap so the
    stroke does not show an antialiasing gap under filled heads)."""
    if style == "triangle":
        return 0.9 * length_mm
    if style == "stealth":
        return 0.6 * length_mm
    if style == "circle":
        return width_mm / 2.0
    return 0.0


def _shorten(p0, p1, amount) -> Tuple[float, float]:
    """Point on segment p0→p1, *amount* mm back from p1 (clamped, no inversion)."""
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    seg = math.hypot(dx, dy)
    if seg <= 0:
        return p1[0], p1[1]
    amount = min(max(amount, 0.0), seg)
    t = amount / seg
    return p1[0] - dx * t, p1[1] - dy * t


def stroke_path(mark) -> QPainterPath:
    """Path to stroke; open shapes are shortened where arrowheads sit."""
    if not _open(mark):
        return geometry_path(mark)
    pts = [list(p) for p in mark.points]
    if len(pts) < 2:
        return geometry_path(mark)
    if mark.arrow_start != "none" and _shorten_for(
            mark.arrow_start, mark.arrow_start_length_mm,
            mark.arrow_start_width_mm):
        pts[0] = list(_shorten(pts[1], pts[0], _shorten_for(
            mark.arrow_start, mark.arrow_start_length_mm,
            mark.arrow_start_width_mm)))
    if mark.arrow_end != "none" and _shorten_for(
            mark.arrow_end, mark.arrow_end_length_mm,
            mark.arrow_end_width_mm):
        pts[-1] = list(_shorten(pts[-2], pts[-1], _shorten_for(
            mark.arrow_end, mark.arrow_end_length_mm,
            mark.arrow_end_width_mm)))
    path = QPainterPath()
    path.moveTo(pts[0][0], pts[0][1])
    for x, y in pts[1:]:
        path.lineTo(x, y)
    return path


def _head_shape(style, length_mm, width_mm) -> Tuple[QPainterPath, bool]:
    """Arrowhead geometry for a tip at (0, 0) pointing along +x."""
    path = QPainterPath()
    L, W = length_mm, width_mm
    if style == "triangle":
        path.moveTo(0, 0)
        path.lineTo(-L, -W / 2.0)
        path.lineTo(-L, W / 2.0)
        path.closeSubpath()
        return path, True
    if style == "open":
        path.moveTo(0, 0)
        path.lineTo(-L, -W / 2.0)
        path.moveTo(0, 0)
        path.lineTo(-L, W / 2.0)
        return path, False
    if style == "stealth":
        path.moveTo(0, 0)
        path.lineTo(-L, -W / 2.0)
        path.lineTo(-0.6 * L, 0)
        path.lineTo(-L, W / 2.0)
        path.closeSubpath()
        return path, True
    if style == "circle":
        path.addEllipse(-W / 2.0, -W / 2.0, W, W)
        return path, True
    if style == "bar":
        path.moveTo(0, -W / 2.0)
        path.lineTo(0, W / 2.0)
        return path, False
    return path, True


def arrowheads(mark) -> List[Tuple[QPainterPath, bool]]:
    """(path, filled) head shapes in mm; only lines and open polylines."""
    heads: List[Tuple[QPainterPath, bool]] = []
    if not _open(mark) or len(mark.points) < 2:
        return heads
    pts = mark.points
    for style, length_mm, width_mm, tip, prev in (
        (mark.arrow_start, mark.arrow_start_length_mm,
         mark.arrow_start_width_mm, pts[0], pts[1]),
        (mark.arrow_end, mark.arrow_end_length_mm,
         mark.arrow_end_width_mm, pts[-1], pts[-2]),
    ):
        if style == "none":
            continue
        dx, dy = tip[0] - prev[0], tip[1] - prev[1]
        if math.hypot(dx, dy) <= 0:
            continue
        angle = math.degrees(math.atan2(dy, dx))
        shape, filled = _head_shape(style, length_mm, width_mm)
        xf = QTransform().translate(tip[0], tip[1]).rotate(angle)
        heads.append((xf.map(shape), filled))
    return heads


def make_pen(mark) -> QPen:
    pen = QPen(QColor(mark.stroke_color))
    pen.setWidthF(stroke_mm(mark))
    pen.setStyle(_QT_STYLES.get(mark.stroke_style, Qt.PenStyle.SolidLine))
    pen.setCapStyle(Qt.PenCapStyle.FlatCap)
    pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
    return pen


def _fill_brush(mark):
    colour = QColor(mark.fill_color)
    colour.setAlphaF(min(1.0, max(0.0, mark.fill_opacity)))
    return colour


def draw(painter: QPainter, mark, scale: float = 1.0) -> None:
    """Render *mark* on *painter*; *scale* converts mm to device units."""
    painter.save()
    painter.scale(scale, scale)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    fillable = mark.kind == "dot" or (mark.kind in ("rect", "ellipse", "polygon")
                                      and mark.closed)
    if fillable and mark.fill_enabled:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(_fill_brush(mark))
        painter.drawPath(geometry_path(mark))

    if mark.stroke_enabled or _open(mark):
        painter.setPen(make_pen(mark))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(stroke_path(mark))

    heads = arrowheads(mark)
    if heads:
        head_pen = QPen(QColor(mark.stroke_color))
        head_pen.setWidthF(stroke_mm(mark))
        head_pen.setStyle(Qt.PenStyle.SolidLine)
        head_pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        head_pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
        for path, filled in heads:
            if filled:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(mark.stroke_color))
            else:
                painter.setPen(head_pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)
    painter.restore()


def bounds_mm(mark) -> QRectF:
    """Bounding rect in mm including heads and a mitered stroke allowance."""
    bounds = geometry_path(mark).controlPointRect()
    for path, _filled in arrowheads(mark):
        bounds = bounds.united(path.controlPointRect())
    pad = stroke_mm(mark) + 0.05
    return bounds.adjusted(-pad, -pad, pad, pad)


def hit_path_mm(mark, tolerance_mm: float) -> QPainterPath:
    """Pick outline: stroked silhouette ∪ fill region ∪ head shapes."""
    stroker = QPainterPathStroker()
    stroker.setWidth(max(stroke_mm(mark), 2.0 * tolerance_mm))
    area = stroker.createStroke(geometry_path(mark))
    fillable = mark.kind == "dot" or (mark.kind in ("rect", "ellipse", "polygon")
                                      and mark.closed)
    if fillable and mark.fill_enabled:
        area = area.united(geometry_path(mark))
    for path, _filled in arrowheads(mark):
        area = area.united(path)
    return area
