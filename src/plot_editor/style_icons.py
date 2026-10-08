"""Pixmap icons for line styles and markers (element-panel combos).

Drawn with QPainter at the target device pixel ratio in the palette
text colour; cached per (kind, code, colour, dpr). ``'None'`` codes get
a dimmed diagonal slash.
"""

from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (QColor, QIcon, QPainter, QPainterPath, QPen,
                         QPixmap, QPolygonF)

# Dash patterns in px at the 44×14 logical size (on, off, ...).
DASHES = {
    '-': (1e5, 0),
    '--': (6.0, 3.0),
    '-.': (6.0, 3.0, 1.6, 3.0),
    ':': (1.6, 3.0),
}
NONE_CODE = ''
MARKER_CODES = ('', 'o', 's', '^', 'v', 'D', '+', 'x', '.')

W, H = 44, 14

_cache = {}


def style_icon(kind, code, color, dpr=1.0):
    """``kind`` is 'line' or 'marker'; *color* a QColor or hex str."""
    c = color if isinstance(color, QColor) else QColor(color)
    key = (kind, code, c.name(), round(dpr, 2))
    icon = _cache.get(key)
    if icon is None:
        pm = QPixmap(round(W * dpr), round(H * dpr))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if code == NONE_CODE:
            _draw_none(p, c)
        elif kind == 'line':
            _draw_line(p, code, c)
        else:
            _draw_marker(p, code, c)
        p.end()
        icon = QIcon(pm)
        _cache[key] = icon
    return icon


def clear_cache():
    _cache.clear()


def palette_strip(name, w=44, h=14, dpr=1.0, colors=None):
    """Icon of equal-width colour swatches for theme ``name``.

    ``colors`` draws that list instead of looking the theme up, so a
    file whose custom theme is not installed still shows its own swatches.
    """
    shown = tuple(colors) if colors else None
    key = ('palette', name, w, h, round(float(dpr), 2), shown)
    icon = _cache.get(key)
    if icon is None:
        from .palettes import theme_colors_list
        if shown is None:
            colors = theme_colors_list(name) or theme_colors_list(
                'default')
        else:
            colors = list(shown)
        pm = QPixmap(round(w * dpr), round(h * dpr))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        n = len(colors)
        sw = w / n
        for i, hexcolor in enumerate(colors):
            p.fillRect(QRectF(i * sw, 2, sw + 0.5, h - 4),
                       QColor(hexcolor))
        p.end()
        icon = QIcon(pm)
        _cache[key] = icon
    return icon


def _draw_none(p, color):
    dim = QColor(color)
    dim.setAlpha(110)
    pen = QPen(dim, 1.4)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    p.drawLine(QPointF(16, 9.5), QPointF(28, 4.5))


def _draw_line(p, code, color):
    pen = QPen(color, 1.6)
    pen.setCapStyle(Qt.PenCapStyle.FlatCap)
    pattern = DASHES.get(code, (1e5, 0))
    pen.setDashPattern(list(pattern))
    p.setPen(pen)
    p.drawLine(QPointF(2, H / 2), QPointF(W - 2, H / 2))


def _draw_marker(p, code, color):
    cx, cy, r = W / 2, H / 2, 4.2
    pen = QPen(color, 1.4)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    path = QPainterPath()
    filled = True
    if code == 'o':
        path.addEllipse(QPointF(cx, cy), r, r)
    elif code == 's':
        path.addRect(QRectF(cx - r, cy - r, 2 * r, 2 * r))
    elif code == '^':
        path.addPolygon(QPolygonF([
            QPointF(cx, cy - r), QPointF(cx + r, cy + r),
            QPointF(cx - r, cy + r), QPointF(cx, cy - r)]))
    elif code == 'v':
        path.addPolygon(QPolygonF([
            QPointF(cx, cy + r), QPointF(cx + r, cy - r),
            QPointF(cx - r, cy - r), QPointF(cx, cy + r)]))
    elif code == 'D':
        path.addPolygon(QPolygonF([
            QPointF(cx, cy - r), QPointF(cx + r, cy),
            QPointF(cx, cy + r), QPointF(cx - r, cy),
            QPointF(cx, cy - r)]))
    elif code == '+':
        path.moveTo(cx, cy - r)
        path.lineTo(cx, cy + r)
        path.moveTo(cx - r, cy)
        path.lineTo(cx + r, cy)
        filled = False
    elif code == 'x':
        path.moveTo(cx - r, cy - r)
        path.lineTo(cx + r, cy + r)
        path.moveTo(cx + r, cy - r)
        path.lineTo(cx - r, cy + r)
        filled = False
    elif code == '.':
        path.addEllipse(QPointF(cx, cy), 1.8, 1.8)
    else:
        return
    p.setPen(pen)
    p.setBrush(color if filled else Qt.BrushStyle.NoBrush)
    p.drawPath(path)
