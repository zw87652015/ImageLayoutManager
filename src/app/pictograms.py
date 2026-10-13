"""Pictograms for Inspector choice tiles (QtGui only, no widgets).

Every key is drawn in a 24x18 design box, scaled uniformly and centred into
the target rect. ``ink`` is the neutral foreground; ``accent`` marks the
element a choice controls. ``mirror`` flips the design horizontally.
"""

import math

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen

DESIGN_W = 24.0
DESIGN_H = 18.0
_PANEL_ALPHA = 25

INSPECTOR_PICTOGRAMS = {
    "grid_mode": ["grid_stretch", "grid_fixed"],
    "row_alignment": ["row_left", "row_center", "row_right"],
    "label_placement": ["place_in_cell", "place_row_above", "place_row_below",
                        "place_col_left", "place_col_right"],
    "label_cell_placement": ["place_inherit", "place_row_above", "place_row_below",
                             "place_col_left", "place_col_right"],
    "label_item_placement": ["place_inherit", "place_in_cell", "place_row_above",
                             "place_row_below", "place_col_left", "place_col_right"],
    "label_tier": ["tier_panel", "tier_title"],
    "gl_side": ["side_top", "side_bottom", "side_left", "side_right"],
    "gl_align": ["band_left", "band_center", "band_right"],
    "gl_bracket": ["bracket_none", "bracket_line", "bracket_bracket", "bracket_brace"],
    "scale_bar_position": ["sb_bottom_left", "sb_bottom_center", "sb_bottom_right"],
    "fit_mode": ["fit_contain", "fit_cover"],
    "rotation": ["rot_0", "rot_90", "rot_180", "rot_270"],
    "mk_stroke_style": ["line_solid", "line_dashed", "line_dotted", "line_dash_dot"],
    "mk_arrow": ["arrow_none", "arrow_triangle", "arrow_open", "arrow_stealth",
                 "arrow_circle", "arrow_bar"],
    "pip_border_style": ["border_solid", "border_dashed"],
    "align_anchor": [f"anchor_{v}_{h}" for v in ("top", "center", "bottom")
                     for h in ("left", "center", "right")],
}


def _pen(color, width=1.3, style=Qt.PenStyle.SolidLine):
    pen = QPen(color, width, style)
    pen.setCosmetic(True)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def _tint(color, alpha):
    c = QColor(color)
    c.setAlpha(alpha)
    return c


def _outline(p, x, y, w, h, ink, style=Qt.PenStyle.SolidLine, radius=1.5):
    p.setPen(_pen(ink, 1.3, style))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(x, y, w, h), radius, radius)


def _panel(p, x, y, w, h, ink, style=Qt.PenStyle.SolidLine):
    p.setPen(_pen(ink, 1.3, style))
    p.setBrush(QBrush(_tint(ink, _PANEL_ALPHA)))
    p.drawRoundedRect(QRectF(x, y, w, h), 1.5, 1.5)


def _fill(p, x, y, w, h, color, radius=0.8):
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(color))
    p.drawRoundedRect(QRectF(x, y, w, h), radius, radius)


def _line(p, x1, y1, x2, y2, color, width=1.3, style=Qt.PenStyle.SolidLine):
    p.setPen(_pen(color, width, style))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawLine(QPointF(x1, y1), QPointF(x2, y2))


def _polyline(p, points, color):
    path = QPainterPath()
    path.moveTo(QPointF(*points[0]))
    for pt in points[1:]:
        path.lineTo(QPointF(*pt))
    p.setPen(_pen(color))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(path)


def _fill_polygon(p, points, color):
    path = QPainterPath()
    path.moveTo(QPointF(*points[0]))
    for pt in points[1:]:
        path.lineTo(QPointF(*pt))
    path.closeSubpath()
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(color))
    p.drawPath(path)


# ── grid / row ───────────────────────────────────────────────────────────

def _grid_stretch(p, ink, accent):
    _outline(p, 1, 1, 22, 16, ink)
    _fill(p, 2.5, 2.5, 8.75, 13, accent)
    _fill(p, 12.75, 2.5, 8.75, 13, accent)
    _polyline(p, [(2.5, 7.8), (0.4, 9), (2.5, 10.2)], ink)
    _polyline(p, [(21.5, 7.8), (23.6, 9), (21.5, 10.2)], ink)


def _grid_fixed(p, ink, accent):
    _outline(p, 1, 1, 22, 16, ink)
    _fill(p, 3, 5.5, 7, 7, accent)
    _fill(p, 11, 5.5, 7, 7, accent)
    _outline(p, 19.5, 3.5, 2.5, 11, ink, style=Qt.PenStyle.DashLine, radius=0)


def _row_block(x0):
    def draw(p, ink, accent):
        _outline(p, 1, 1, 22, 16, ink)
        _fill(p, x0, 6, 4, 6, accent)
        _fill(p, x0 + 5.5, 6, 4, 6, accent)
    return draw


# ── label placement ──────────────────────────────────────────────────────

def _place_in_cell(p, ink, accent):
    _panel(p, 3, 2.5, 18, 13, ink)
    _fill(p, 5, 4.5, 4, 3, accent)


def _placement(side):
    # (strip rect, panel rect) for a strip on *side* of a 16x11 panel.
    layouts = {
        "above": ((4, 1.5, 16, 2.5), (4, 5.5, 16, 11)),
        "below": ((4, 14, 16, 2.5), (4, 1.5, 16, 11)),
        "left": ((2, 3.5, 2.5, 11), (6, 3.5, 16, 11)),
        "right": ((19.5, 3.5, 2.5, 11), (2, 3.5, 16, 11)),
    }

    def draw(p, ink, accent):
        strip, panel = layouts[side]
        _panel(p, *panel, ink)
        _fill(p, *strip, accent)
    return draw


def _place_inherit(p, ink, accent):
    _outline(p, 3, 2.5, 18, 13, ink, style=Qt.PenStyle.DashLine)
    cx, cy, r = 12.0, 9.0, 3.5
    rect = QRectF(cx - r, cy - r, 2 * r, 2 * r)
    path = QPainterPath()
    path.arcMoveTo(rect, 90)
    path.arcTo(rect, 90, -300)
    p.setPen(_pen(accent, 1.6))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(path)
    theta = math.radians(-210)
    tip_x = cx + r * math.cos(theta)
    tip_y = cy - r * math.sin(theta)
    dx, dy = math.sin(theta), math.cos(theta)
    px, py = -dy, dx
    head = [
        (tip_x + dx * 2.2, tip_y + dy * 2.2),
        (tip_x - dx * 0.6 + px * 1.2, tip_y - dy * 0.6 + py * 1.2),
        (tip_x - dx * 0.6 - px * 1.2, tip_y - dy * 0.6 - py * 1.2),
    ]
    _fill_polygon(p, head, accent)


# ── sides, bands, brackets, scale bar ────────────────────────────────────

def _side_top(p, ink, accent):
    _fill(p, 2, 3, 20, 2, accent)
    _panel(p, 2, 6, 9, 9, ink)
    _panel(p, 13, 6, 9, 9, ink)


def _side_bottom(p, ink, accent):
    _panel(p, 2, 3, 9, 9, ink)
    _panel(p, 13, 3, 9, 9, ink)
    _fill(p, 2, 13.5, 20, 2, accent)


def _side_left(p, ink, accent):
    _fill(p, 6, 1, 2, 16, accent)
    _panel(p, 9, 1, 9, 7, ink)
    _panel(p, 9, 10, 9, 7, ink)


def _side_right(p, ink, accent):
    _panel(p, 6, 1, 9, 7, ink)
    _panel(p, 6, 10, 9, 7, ink)
    _fill(p, 16, 1, 2, 16, accent)


def _band(x_bar):
    def draw(p, ink, accent):
        _outline(p, 1, 6, 22, 6, ink)
        _fill(p, x_bar, 8, 8, 2, accent)
    return draw


def _bracket_none(p, ink, accent):
    _panel(p, 3, 9, 8.5, 8, ink)
    _panel(p, 12.5, 9, 8.5, 8, ink)
    _fill(p, 8, 3, 8, 2, accent)


def _bracket_line(p, ink, accent):
    _bracket_none(p, ink, accent)
    _line(p, 3, 7, 21, 7, ink)


def _bracket_bracket(p, ink, accent):
    _bracket_none(p, ink, accent)
    _line(p, 3, 7, 21, 7, ink)
    _line(p, 3, 7, 3, 9.5, ink)
    _line(p, 21, 7, 21, 9.5, ink)


def _bracket_brace(p, ink, accent):
    _bracket_none(p, ink, accent)
    path = QPainterPath()
    path.moveTo(QPointF(3, 8.5))
    path.quadTo(QPointF(3, 7), QPointF(6, 7))
    path.lineTo(QPointF(9, 7))
    path.quadTo(QPointF(12, 7), QPointF(12, 5.5))
    path.quadTo(QPointF(12, 7), QPointF(15, 7))
    path.lineTo(QPointF(18, 7))
    path.quadTo(QPointF(21, 7), QPointF(21, 8.5))
    p.setPen(_pen(ink))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(path)


def _sb_bar(x_bar):
    def draw(p, ink, accent):
        _panel(p, 2, 2, 20, 14, ink)
        _fill(p, x_bar, 11.9, 6, 1.6, accent)
    return draw


# ── fit / rotation / tier ────────────────────────────────────────────────

def _fit_contain(p, ink, accent):
    _outline(p, 2, 2, 20, 14, ink)
    _fill(p, 2, 4.5, 20, 9, accent, radius=0)


def _fit_cover(p, ink, accent):
    p.save()
    p.setClipRect(QRectF(5, 2, 14, 14))
    _fill(p, 1, 2, 22, 14, accent, radius=0)
    p.restore()
    _outline(p, 1, 2, 22, 14, ink, style=Qt.PenStyle.DashLine, radius=0)
    _outline(p, 5, 2, 14, 14, ink, radius=0)


def _rotated(angle):
    def draw(p, ink, accent):
        p.save()
        p.translate(12, 9)
        p.rotate(angle)
        p.translate(-12, -9)
        _outline(p, 5, 4, 14, 10, ink, radius=1)
        _polyline(p, [(6.5, 12.5), (9.8, 8.8), (12.2, 11.2), (13.5, 9.9), (15.5, 12.5)], ink)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(accent))
        p.drawEllipse(QPointF(15.5, 6.5), 1.2, 1.2)
        p.restore()
    return draw


def _tier_panel(p, ink, accent):
    _panel(p, 3, 2.5, 18, 13, ink)
    _fill(p, 2, 1.5, 4, 4, accent)


def _tier_title(p, ink, accent):
    _panel(p, 3, 6, 18, 10, ink)
    _fill(p, 3, 2.5, 18, 2.5, accent)


# ── lines, arrows, borders, anchors ──────────────────────────────────────

def _line_style(style):
    def draw(p, ink, accent):
        _line(p, 1, 9, 23, 9, ink, width=2.0, style=style)
    return draw


def _arrow(kind):
    def draw(p, ink, accent):
        if kind == "none":
            _line(p, 2, 9, 22, 9, ink)
        elif kind == "triangle":
            _line(p, 2, 9, 18, 9, ink)
            _fill_polygon(p, [(22, 9), (17.5, 5.5), (17.5, 12.5)], ink)
        elif kind == "open":
            _line(p, 2, 9, 22, 9, ink)
            _polyline(p, [(17, 5.5), (22, 9), (17, 12.5)], ink)
        elif kind == "stealth":
            _line(p, 2, 9, 18.5, 9, ink)
            _fill_polygon(p, [(22, 9), (17, 5.5), (19, 9), (17, 12.5)], ink)
        elif kind == "circle":
            _line(p, 2, 9, 18, 9, ink)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(ink))
            p.drawEllipse(QPointF(20, 9), 2, 2)
        elif kind == "bar":
            _line(p, 2, 9, 22, 9, ink)
            _line(p, 22, 5.5, 22, 12.5, ink)
    return draw


def _border(style):
    def draw(p, ink, accent):
        _outline(p, 2, 2, 20, 14, ink, style=style, radius=0)
    return draw


def _anchor(v, h):
    x_off = {"left": 6.0, "center": 9.5, "right": 13.0}[h]
    y_off = {"top": 3.0, "center": 6.5, "bottom": 10.0}[v]

    def draw(p, ink, accent):
        _outline(p, 4, 1, 16, 16, ink, radius=2)
        _fill(p, x_off, y_off, 5, 5, accent, radius=1)
    return draw


def _unknown(p, ink, accent):
    _outline(p, 5, 2, 14, 14, ink, style=Qt.PenStyle.DotLine, radius=1)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(ink))
    p.drawEllipse(QPointF(12, 9), 1.2, 1.2)


_DRAWERS = {
    "grid_stretch": _grid_stretch,
    "grid_fixed": _grid_fixed,
    "row_left": _row_block(3.5),
    "row_center": _row_block(7.25),
    "row_right": _row_block(11.0),
    "place_in_cell": _place_in_cell,
    "place_row_above": _placement("above"),
    "place_row_below": _placement("below"),
    "place_col_left": _placement("left"),
    "place_col_right": _placement("right"),
    "place_inherit": _place_inherit,
    "side_top": _side_top,
    "side_bottom": _side_bottom,
    "side_left": _side_left,
    "side_right": _side_right,
    "band_left": _band(3),
    "band_center": _band(8),
    "band_right": _band(13),
    "bracket_none": _bracket_none,
    "bracket_line": _bracket_line,
    "bracket_bracket": _bracket_bracket,
    "bracket_brace": _bracket_brace,
    "sb_bottom_left": _sb_bar(4.5),
    "sb_bottom_center": _sb_bar(9),
    "sb_bottom_right": _sb_bar(13.5),
    "fit_contain": _fit_contain,
    "fit_cover": _fit_cover,
    "rot_0": _rotated(0),
    "rot_90": _rotated(90),
    "rot_180": _rotated(180),
    "rot_270": _rotated(270),
    "tier_panel": _tier_panel,
    "tier_title": _tier_title,
    "line_solid": _line_style(Qt.PenStyle.SolidLine),
    "line_dashed": _line_style(Qt.PenStyle.DashLine),
    "line_dotted": _line_style(Qt.PenStyle.DotLine),
    "line_dash_dot": _line_style(Qt.PenStyle.DashDotLine),
    "arrow_none": _arrow("none"),
    "arrow_triangle": _arrow("triangle"),
    "arrow_open": _arrow("open"),
    "arrow_stealth": _arrow("stealth"),
    "arrow_circle": _arrow("circle"),
    "arrow_bar": _arrow("bar"),
    "border_solid": _border(Qt.PenStyle.SolidLine),
    "border_dashed": _border(Qt.PenStyle.DashLine),
}
for _v in ("top", "center", "bottom"):
    for _h in ("left", "center", "right"):
        _DRAWERS[f"anchor_{_v}_{_h}"] = _anchor(_v, _h)

KNOWN_KEYS = frozenset(_DRAWERS)


def draw_pictogram(key, painter: QPainter, rect: QRectF, ink: QColor, accent: QColor,
                   mirror=False):
    painter.save()
    try:
        scale = min(rect.width() / DESIGN_W, rect.height() / DESIGN_H)
        painter.translate(rect.center())
        painter.scale(scale, scale)
        painter.translate(-DESIGN_W / 2, -DESIGN_H / 2)
        if mirror:
            painter.translate(DESIGN_W, 0)
            painter.scale(-1, 1)
        draw = _DRAWERS.get(key, _unknown)
        draw(painter, QColor(ink), QColor(accent))
    finally:
        painter.restore()
