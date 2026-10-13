"""Vector icons for the User Guide task cards (QtGui only).

Each icon is a small scene of 2-5 shapes drawn in unit coordinates and scaled to the
target rect. Colours come from the dialog's palette: ink, muted, accent, base, surface.
Unknown keys draw a neutral placeholder.
"""

import math

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QPainter, QPen

ICON_KEYS = (
    "first_figure", "add", "swap", "rows", "auto", "margins", "crop", "inset",
    "label", "titles", "scale_bar", "marks", "text_aa", "align", "equal",
    "floating", "export", "package", "wrench", "tour", "shortcuts",
)


def _color(colors, name, fallback):
    value = colors.get(name, fallback)
    return value if isinstance(value, QColor) else QColor(value)


class _Scene:
    def __init__(self, painter, rect, colors):
        self.p = painter
        self.r = QRectF(rect)
        self.ink = _color(colors, "ink", "#222222")
        self.muted = _color(colors, "muted", "#888888")
        self.accent = _color(colors, "accent", "#4F5BD5")
        self.base = _color(colors, "base", "#FFFFFF")
        self.surface = _color(colors, "surface", "#EEEEEE")
        self.stroke = max(1.4, min(self.r.width(), self.r.height()) / 45.0)

    def pt(self, x, y):
        return QPointF(self.r.left() + x * self.r.width(), self.r.top() + y * self.r.height())

    def box(self, x, y, w, h):
        return QRectF(self.r.left() + x * self.r.width(), self.r.top() + y * self.r.height(),
                      w * self.r.width(), h * self.r.height())

    def tint(self, color, alpha):
        out = QColor(color)
        out.setAlpha(alpha)
        return out

    def rect(self, x, y, w, h, line=None, fill=None, dashed=False, radius=0.06, width=None):
        self.p.save()
        pen = QPen(line or self.ink, width or self.stroke)
        if dashed:
            pen.setStyle(Qt.PenStyle.DashLine)
        self.p.setPen(pen if line is not None or dashed else Qt.PenStyle.NoPen)
        self.p.setBrush(QBrush(fill) if fill is not None else Qt.BrushStyle.NoBrush)
        radius_px = radius * min(self.r.width(), self.r.height())
        self.p.drawRoundedRect(self.box(x, y, w, h), radius_px, radius_px)
        self.p.restore()

    def line(self, x1, y1, x2, y2, color=None, width=None, dashed=False):
        self.p.save()
        pen = QPen(color or self.ink, width or self.stroke, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        if dashed:
            pen.setStyle(Qt.PenStyle.DashLine)
        self.p.setPen(pen)
        self.p.drawLine(self.pt(x1, y1), self.pt(x2, y2))
        self.p.restore()

    def dot(self, x, y, radius, color):
        self.p.save()
        self.p.setPen(Qt.PenStyle.NoPen)
        self.p.setBrush(QBrush(color))
        r = radius * min(self.r.width(), self.r.height())
        c = self.pt(x, y)
        self.p.drawEllipse(c, r, r)
        self.p.restore()

    def ring(self, x, y, radius, color):
        self.p.save()
        self.p.setPen(QPen(color, self.stroke))
        self.p.setBrush(Qt.BrushStyle.NoBrush)
        r = radius * min(self.r.width(), self.r.height())
        self.p.drawEllipse(self.pt(x, y), r, r)
        self.p.restore()

    def arrow(self, x1, y1, x2, y2, color=None):
        self.line(x1, y1, x2, y2, color)
        angle = math.atan2(y2 - y1, x2 - x1)
        for turn in (2.6, -2.6):
            self.line(x2, y2, x2 + 0.08 * math.cos(angle + turn), y2 + 0.08 * math.sin(angle + turn), color)

    def plus(self, x, y, size, color):
        self.line(x - size, y, x + size, y, color, self.stroke * 1.2)
        self.line(x, y - size, x, y + size, color, self.stroke * 1.2)


def _first_figure(s):
    s.rect(0.15, 0.08, 0.7, 0.84, line=s.ink, fill=s.base)
    for x, y in ((0.22, 0.16), (0.52, 0.16), (0.22, 0.52), (0.52, 0.52)):
        s.rect(x, y, 0.24, 0.3, fill=s.tint(s.accent, 70), line=s.accent, radius=0.04)


def _add(s):
    s.rect(0.08, 0.22, 0.52, 0.56, line=s.muted, dashed=True, fill=s.base)
    s.dot(0.78, 0.3, 0.13, s.accent)
    s.plus(0.78, 0.3, 0.06, s.base)


def _swap(s):
    s.rect(0.06, 0.25, 0.38, 0.5, line=s.ink, fill=s.tint(s.accent, 60))
    s.rect(0.56, 0.25, 0.38, 0.5, line=s.ink, fill=s.base)
    s.arrow(0.44, 0.42, 0.56, 0.42, s.accent)
    s.arrow(0.56, 0.6, 0.44, 0.6, s.accent)


def _rows(s):
    for y, cells in ((0.12, 3), (0.42, 2), (0.72, 4)):
        width = 0.88 / cells
        for i in range(cells):
            s.rect(0.06 + i * width + 0.01, y, width - 0.02, 0.2, line=s.ink, fill=s.base, radius=0.04)


def _auto(s):
    for x, top, h in ((0.08, 0.3, 0.4), (0.38, 0.18, 0.52), (0.68, 0.36, 0.34)):
        s.rect(x, top, 0.24, h, line=s.ink, fill=s.tint(s.accent, 55), radius=0.04)
    s.line(0.1, 0.9, 0.9, 0.9, s.accent, s.stroke * 1.4)


def _margins(s):
    s.rect(0.12, 0.05, 0.76, 0.9, line=s.ink, fill=s.base, radius=0.03)
    s.rect(0.24, 0.17, 0.52, 0.7, line=s.muted, dashed=True, radius=0.02)
    s.rect(0.3, 0.3, 0.4, 0.4, line=s.accent, fill=s.tint(s.accent, 60), radius=0.03)


def _crop(s):
    s.rect(0.12, 0.12, 0.76, 0.76, line=s.ink, fill=s.tint(s.muted, 70))
    s.rect(0.3, 0.3, 0.4, 0.4, line=s.accent, dashed=True, radius=0.02, width=s.stroke * 1.2)
    for x, y in ((0.3, 0.3), (0.7, 0.3), (0.3, 0.7), (0.7, 0.7)):
        s.dot(x, y, 0.035, s.accent)


def _inset(s):
    s.rect(0.1, 0.12, 0.8, 0.76, line=s.ink, fill=s.base, radius=0.03)
    s.rect(0.55, 0.2, 0.3, 0.26, line=s.accent, fill=s.tint(s.accent, 90), radius=0.04, width=s.stroke * 1.2)


def _label(s):
    s.rect(0.1, 0.1, 0.8, 0.8, line=s.ink, fill=s.base, radius=0.04)
    s.rect(0.14, 0.14, 0.24, 0.24, fill=s.accent, radius=0.2)
    s.ring(0.26, 0.26, 0.06, s.base)


def _titles(s):
    s.rect(0.1, 0.1, 0.8, 0.18, line=s.accent, fill=s.tint(s.accent, 70), radius=0.2)
    s.rect(0.1, 0.36, 0.38, 0.52, line=s.ink, fill=s.base, radius=0.04)
    s.rect(0.52, 0.36, 0.38, 0.52, line=s.ink, fill=s.base, radius=0.04)


def _scale_bar(s):
    s.rect(0.1, 0.1, 0.8, 0.62, line=s.ink, fill=s.tint(s.muted, 60), radius=0.03)
    s.line(0.2, 0.84, 0.56, 0.84, s.accent, s.stroke * 1.8)
    s.line(0.2, 0.78, 0.2, 0.9, s.accent)
    s.line(0.56, 0.78, 0.56, 0.9, s.accent)


def _marks(s):
    s.rect(0.08, 0.1, 0.3, 0.24, line=s.muted, dashed=True, radius=0.03)
    s.arrow(0.2, 0.74, 0.82, 0.26, s.accent)


def _text_aa(s):
    for x, y in ((0.1, 0.18), (0.52, 0.5)):
        s.rect(x, y, 0.38, 0.3, line=s.accent, fill=s.base, radius=0.3)
        s.line(x + 0.1, y + 0.15, x + 0.28, y + 0.15, s.ink, s.stroke * 1.2)
        s.line(x + 0.1, y + 0.21, x + 0.22, y + 0.21, s.ink, s.stroke * 1.2)


def _align(s):
    s.line(0.06, 0.78, 0.94, 0.78, s.muted, dashed=True)
    s.rect(0.12, 0.3, 0.3, 0.48, line=s.accent, fill=s.tint(s.accent, 50), radius=0.03)
    s.rect(0.58, 0.45, 0.3, 0.33, line=s.accent, fill=s.tint(s.accent, 50), radius=0.03)


def _equal(s):
    s.rect(0.08, 0.25, 0.36, 0.5, line=s.ink, fill=s.base, radius=0.04)
    s.rect(0.56, 0.25, 0.36, 0.5, line=s.ink, fill=s.base, radius=0.04)
    s.line(0.46, 0.44, 0.54, 0.44, s.accent, s.stroke * 1.3)
    s.line(0.46, 0.56, 0.54, 0.56, s.accent, s.stroke * 1.3)


def _floating(s):
    s.rect(0.14, 0.12, 0.44, 0.4, line=s.muted, fill=s.base, radius=0.04, dashed=True)
    s.rect(0.4, 0.42, 0.46, 0.42, line=s.accent, fill=s.tint(s.accent, 70), radius=0.04)


def _export(s):
    s.rect(0.1, 0.22, 0.52, 0.66, line=s.ink, fill=s.base, radius=0.03)
    s.arrow(0.42, 0.6, 0.86, 0.14, s.accent)


def _package(s):
    s.rect(0.18, 0.32, 0.64, 0.5, line=s.ink, fill=s.base, radius=0.05)
    s.rect(0.18, 0.46, 0.64, 0.1, fill=s.accent, radius=0.02)
    s.line(0.18, 0.32, 0.5, 0.18, s.ink)
    s.line(0.82, 0.32, 0.5, 0.18, s.ink)


def _wrench(s):
    s.ring(0.5, 0.45, 0.3, s.accent)
    s.dot(0.5, 0.68, 0.045, s.accent)
    s.line(0.5, 0.45, 0.5, 0.56, s.accent, s.stroke * 1.2)


def _tour(s):
    s.rect(0.04, 0.08, 0.92, 0.84, fill=s.tint(s.ink, 110), radius=0.05)
    s.rect(0.3, 0.3, 0.4, 0.34, line=s.accent, fill=s.base, radius=0.1, width=s.stroke * 1.6)
    s.line(0.36, 0.78, 0.64, 0.78, s.muted)


def _shortcuts(s):
    for x in (0.08, 0.38, 0.68):
        s.rect(x, 0.3, 0.24, 0.4, line=s.ink, fill=s.base, radius=0.15)
        s.dot(x + 0.12, 0.5, 0.05, s.accent)


def _placeholder(s):
    s.rect(0.1, 0.1, 0.8, 0.8, line=s.muted, dashed=True, radius=0.1)
    s.dot(0.3, 0.5, 0.05, s.muted)
    s.dot(0.5, 0.5, 0.05, s.muted)
    s.dot(0.7, 0.5, 0.05, s.muted)


_SCENES = {
    "first_figure": _first_figure, "add": _add, "swap": _swap, "rows": _rows,
    "auto": _auto, "margins": _margins, "crop": _crop, "inset": _inset,
    "label": _label, "titles": _titles, "scale_bar": _scale_bar, "marks": _marks,
    "text_aa": _text_aa, "align": _align, "equal": _equal, "floating": _floating,
    "export": _export, "package": _package, "wrench": _wrench, "tour": _tour,
    "shortcuts": _shortcuts,
}


def draw_topic(key, painter, rect, palette_colors):
    """Paint the icon for *key* into *rect*. Unknown keys draw a neutral placeholder."""
    scene = _Scene(painter, rect, palette_colors or {})
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    try:
        _SCENES.get(key, _placeholder)(scene)
    finally:
        painter.restore()


def draw_tour(painter, rect, palette_colors):
    draw_topic("tour", painter, rect, palette_colors)


def draw_shortcuts(painter, rect, palette_colors):
    draw_topic("shortcuts", painter, rect, palette_colors)
