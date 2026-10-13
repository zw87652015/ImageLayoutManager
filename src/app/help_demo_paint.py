"""Paints a help_demos.Frame (QtGui only, no widgets).

The stage is scaled uniformly into the target rect and centred. Colours are
passed in by role (ink, muted, accent, base, surface, mid); mock pictures and
the arrow cursor use fixed colours so they read the same in both themes.
"""

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QFontMetrics, QPainter, QPen, QPolygonF

from src.app.help_demos import MIN_TEXT, STAGE_H, STAGE_W, Shape, Text
from src.app.i18n import translate
from src.app.icons import render_icon
from src.app.pictograms import draw_pictogram

_FALLBACK = {
    "ink": "#222222",
    "muted": "#9A968F",
    "accent": "#4F5BD5",
    "base": "#FFFFFF",
    "surface": "#EEEEEE",
    "mid": "#CFCCC6",
    "on_accent": "#FFFFFF",
    "chrome": "#F6F5F3",
    "canvas": "#E9EAED",
}

_CURSOR = [(0.0, 0.0), (0.0, 10.5), (2.8, 8.2), (4.7, 12.4), (6.3, 11.7), (4.5, 7.5), (8.0, 7.5)]


def _role(colors, name):
    return QColor(colors.get(name, _FALLBACK.get(name, "#888888")))


def _text_value(value, lang):
    if isinstance(value, tuple):
        return value[1] if lang == "zh" else value[0]
    return translate(value, lang)


def _cosmetic_pen(color, width=1.0):
    pen = QPen(color, width)
    pen.setCosmetic(True)
    return pen


def _draw_cursor(painter, x, y, colors):
    polygon = QPolygonF([QPointF(x + px, y + py) for px, py in _CURSOR])
    painter.setPen(_cosmetic_pen(QColor("#FFFFFF")))
    painter.setBrush(QBrush(QColor("#000000")))
    painter.drawPolygon(polygon)


def _draw_crosshair(painter, rect, colors):
    x, y, w, h = rect
    cx, cy = x + w / 2.0, y + h / 2.0
    arms = (((cx - 5, cy), (cx - 1.5, cy)), ((cx + 1.5, cy), (cx + 5, cy)),
            ((cx, cy - 5), (cx, cy - 1.5)), ((cx, cy + 1.5), (cx, cy + 5)))
    for pen in (_cosmetic_pen(QColor("#FFFFFF"), 2.2), _cosmetic_pen(_role(colors, "ink"), 1.0)):
        painter.setPen(pen)
        for (x1, y1), (x2, y2) in arms:
            painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))


def _draw_mouse(painter, x, y, w, h, colors, right_on):
    rect = QRectF(x, y, w, h)
    painter.setPen(_cosmetic_pen(_role(colors, "ink")))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(rect, w / 2, w / 2)
    painter.drawLine(QPointF(x + w / 2, y), QPointF(x + w / 2, y + h * 0.45))
    if right_on:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(_role(colors, "accent")))
        painter.drawRect(QRectF(x + w / 2, y + 0.5, w / 2 - 0.5, h * 0.42))


def _draw_picture(painter, kind, rect, colors):
    x, y, w, h = rect
    if kind == "chart":
        painter.setPen(_cosmetic_pen(_role(colors, "ink")))
        painter.drawLine(QPointF(x + w * 0.1, y + h * 0.85), QPointF(x + w * 0.1, y + h * 0.1))
        painter.drawLine(QPointF(x + w * 0.1, y + h * 0.85), QPointF(x + w * 0.92, y + h * 0.85))
        pts = [(0.15, 0.7), (0.3, 0.45), (0.45, 0.55), (0.6, 0.25), (0.75, 0.4), (0.9, 0.2)]
        painter.setPen(_cosmetic_pen(QColor("#4F5BD5"), 1.6))
        painter.drawPolyline(QPolygonF([QPointF(x + px * w, y + py * h) for px, py in pts]))
    elif kind == "bars":
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor("#4F5BD5")))
        for index, height in enumerate((0.55, 0.8, 0.4, 0.7)):
            bw = w * 0.14
            bx = x + w * (0.14 + index * 0.2)
            painter.drawRect(QRectF(bx, y + h * (0.9 - height * 0.8), bw, h * height * 0.8))
        painter.setPen(_cosmetic_pen(_role(colors, "ink")))
        painter.drawLine(QPointF(x + w * 0.08, y + h * 0.9), QPointF(x + w * 0.94, y + h * 0.9))
    elif kind == "micro":
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor("#1B1D22")))
        painter.drawRect(QRectF(x, y, w, h))
        painter.setBrush(QBrush(QColor("#9AA0B4")))
        for row in range(4):
            for col in range(6):
                if (row * 3 + col * 5) % 7 < 4:
                    cx = x + w * (0.1 + col * 0.16)
                    cy = y + h * (0.15 + row * 0.22)
                    painter.drawEllipse(QPointF(cx, cy), w * 0.035, w * 0.035)
    elif kind == "photo":
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor("#CFE3F5")))
        painter.drawRect(QRectF(x, y, w, h))
        painter.setBrush(QBrush(QColor("#9DB0A0")))
        far = QPolygonF([QPointF(x, y + h), QPointF(x + w * 0.3, y + h * 0.42),
                         QPointF(x + w * 0.6, y + h * 0.7), QPointF(x + w, y + h * 0.35),
                         QPointF(x + w, y + h)])
        painter.drawPolygon(far)
        painter.setBrush(QBrush(QColor("#6F8A6B")))
        near = QPolygonF([QPointF(x, y + h), QPointF(x + w * 0.2, y + h * 0.7),
                          QPointF(x + w * 0.55, y + h * 0.85), QPointF(x + w, y + h * 0.6),
                          QPointF(x + w, y + h)])
        painter.drawPolygon(near)
    elif kind == "missing":
        painter.setPen(_cosmetic_pen(_role(colors, "mid")))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        pen = _cosmetic_pen(_role(colors, "mid"))
        pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.drawRect(QRectF(x, y, w, h))
        painter.setPen(_cosmetic_pen(_role(colors, "muted"), 1.4))
        painter.drawPolyline(QPolygonF([QPointF(x + w * 0.4, y + h * 0.3), QPointF(x + w * 0.5, y + h * 0.5),
                                        QPointF(x + w * 0.42, y + h * 0.62), QPointF(x + w * 0.55, y + h * 0.75)]))
    else:
        painter.setPen(_cosmetic_pen(_role(colors, "mid")))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(QRectF(x, y, w, h))


def _draw_glyph(painter, name, rect, colors):
    x, y, w, h = rect
    painter.setPen(_cosmetic_pen(_role(colors, "ink"), 1.2))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    if name == "plus":
        cx, cy = x + w / 2, y + h / 2
        painter.setPen(_cosmetic_pen(_role(colors, "base"), 1.4))
        painter.drawLine(QPointF(cx - w * 0.3, cy), QPointF(cx + w * 0.3, cy))
        painter.drawLine(QPointF(cx, cy - h * 0.3), QPointF(cx, cy + h * 0.3))

def _draw_file(painter, rect, colors):
    x, y, w, h = rect
    painter.setPen(_cosmetic_pen(_role(colors, "ink")))
    painter.setBrush(QBrush(_role(colors, "base")))
    painter.drawRect(QRectF(x + w * 0.2, y, w * 0.6, h))
    painter.drawLine(QPointF(x + w * 0.3, y + h * 0.3), QPointF(x + w * 0.7, y + h * 0.3))
    painter.drawLine(QPointF(x + w * 0.3, y + h * 0.5), QPointF(x + w * 0.7, y + h * 0.5))


def _paint_shape(painter, shape, colors):
    kind = shape.kind
    rect = shape.rect
    if kind == "rect":
        x, y, w, h = rect
        if shape.fill:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(_role(colors, shape.fill)))
        else:
            painter.setBrush(Qt.BrushStyle.NoBrush)
        width = shape.extra[0] if shape.extra else 1.0
        if shape.line:
            pen = _cosmetic_pen(_role(colors, shape.line), 1.0) if not shape.extra else QPen(_role(colors, shape.line), width)
            if shape.extra:
                pen.setCosmetic(False)
            if shape.dashed:
                pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
        else:
            painter.setPen(Qt.PenStyle.NoPen)
        if shape.radius:
            painter.drawRoundedRect(QRectF(x, y, w, h), shape.radius, shape.radius)
        else:
            painter.drawRect(QRectF(x, y, w, h))
    elif kind == "line":
        import math
        x1, y1, x2, y2 = rect
        pen = _cosmetic_pen(_role(colors, shape.line or "mid"), 1.4 if shape.extra else 1.0)
        if shape.dashed:
            pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))
        if shape.extra and shape.extra[0] == "arrow" and math.hypot(x2 - x1, y2 - y1) > 1.0:
            angle = math.atan2(y2 - y1, x2 - x1)
            for side in (-0.45, 0.45):
                ax = x2 - 4.0 * math.cos(angle + side)
                ay = y2 - 4.0 * math.sin(angle + side)
                painter.drawLine(QPointF(x2, y2), QPointF(ax, ay))
    elif kind == "cursor":
        if shape.name == "cross":
            _draw_crosshair(painter, rect, colors)
        else:
            _draw_cursor(painter, rect[0], rect[1], colors)
    elif kind == "mouse":
        x, y, w, h = rect
        _draw_mouse(painter, x, y, w, h, colors, "right" in shape.extra)
    elif kind == "ring":
        x, y, w, h = rect
        pen = _cosmetic_pen(_role(colors, shape.line or "accent"), 1.6)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QRectF(x, y, w, h))
    elif kind == "picture":
        rot, clip = (tuple(shape.extra) + (0, None))[:2] if shape.extra else (0, None)
        painter.save()
        if clip:
            painter.setClipRect(QRectF(*clip))
        if rot:
            x, y, w, h = rect
            painter.translate(x + w / 2.0, y + h / 2.0)
            painter.rotate(rot)
            _draw_picture(painter, shape.name, (-w / 2.0, -h / 2.0, w, h), colors)
        else:
            _draw_picture(painter, shape.name, rect, colors)
        painter.restore()
    elif kind == "pictogram":
        draw_pictogram(shape.name, painter, QRectF(*rect), _role(colors, "ink"), _role(colors, "accent"))
    elif kind == "chevron":
        x, y, w, h = rect
        pts = {"right": [(x, y), (x + w, y + h / 2.0), (x, y + h)],
               "down": [(x, y), (x + w / 2.0, y + h), (x + w, y)],
               "left": [(x + w, y), (x, y + h / 2.0), (x + w, y + h)]}[shape.name or "right"]
        painter.setPen(_cosmetic_pen(_role(colors, shape.fill or "ink"), 1.3))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPolyline(QPolygonF([QPointF(px, py) for px, py in pts]))
    elif kind == "check":
        x, y, w, h = rect
        painter.setPen(_cosmetic_pen(_role(colors, shape.fill or shape.line or "accent"), 1.6))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPolyline(QPolygonF([QPointF(x + w * 0.15, y + h * 0.5), QPointF(x + w * 0.42, y + h * 0.82),
                                        QPointF(x + w * 0.88, y + h * 0.15)]))
    elif kind == "star":
        import math
        x, y, w, h = rect
        cx, cy, outer, inner = x + w / 2.0, y + h / 2.0, min(w, h) / 2.0, min(w, h) / 5.0
        pts = []
        for i in range(10):
            radius = outer if i % 2 == 0 else inner
            angle = -math.pi / 2 + i * math.pi / 5
            pts.append(QPointF(cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(_role(colors, shape.fill or "accent")))
        painter.drawPolygon(QPolygonF(pts))
    elif kind == "cross":
        x, y, w, h = rect
        painter.setPen(_cosmetic_pen(_role(colors, shape.fill or shape.line or "ink"), 1.4))
        painter.drawLine(QPointF(x, y), QPointF(x + w, y + h))
        painter.drawLine(QPointF(x + w, y), QPointF(x, y + h))
    elif kind == "file":
        _draw_file(painter, rect, colors)
    elif kind == "folder":
        x, y, w, h = rect
        painter.setPen(_cosmetic_pen(_role(colors, "ink")))
        painter.setBrush(QBrush(_role(colors, "mid")))
        painter.drawRect(QRectF(x, y, w * 0.4, h * 0.25))
        painter.setBrush(QBrush(_role(colors, "surface")))
        painter.drawRect(QRectF(x, y + h * 0.2, w, h * 0.8))
    elif kind == "package":
        x, y, w, h = rect
        painter.setPen(_cosmetic_pen(_role(colors, "ink"), 1.2))
        painter.setBrush(QBrush(_role(colors, "surface")))
        painter.drawRoundedRect(QRectF(x, y + h * 0.1, w, h * 0.9), 3.0, 3.0)
        painter.drawLine(QPointF(x + 2.0, y + h * 0.5), QPointF(x + w - 2.0, y + h * 0.5))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(_role(colors, "accent")))
        painter.drawRect(QRectF(x + w * 0.38, y, w * 0.24, h * 0.22))
    elif kind == "ghost":
        if shape.name == "file":
            _draw_file(painter, rect, colors)
        else:
            _draw_picture(painter, shape.name, rect, colors)
            painter.setPen(_cosmetic_pen(_role(colors, "ink")))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(QRectF(*rect))
    elif kind == "glyph":
        _draw_glyph(painter, shape.name, rect, colors)
    elif kind == "icon":
        render_icon(painter, shape.name, _role(colors, shape.fill or "ink").name(), QRectF(*rect))


def _alignment(align):
    if align == "center":
        return Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
    if align == "right":
        return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
    return Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter


def _paint_text(painter, item, colors, lang, font):
    font.setPixelSize(int(max(round(item.size), round(MIN_TEXT))))
    painter.setFont(font)
    painter.setPen(_role(colors, item.role))
    x, y, w, h = item.rect
    text = _text_value(item.value, lang)
    metrics = QFontMetrics(font)
    if metrics.horizontalAdvance(text) > w:
        text = metrics.elidedText(text, Qt.TextElideMode.ElideRight, max(1, int(w)))
    painter.drawText(QRectF(x, y, w, h), _alignment(item.align), text)


def paint_frame(painter, rect, frame, colors, lang):
    """Draw *frame* into *rect* (widget coordinates), scaled and centred."""
    target = QRectF(rect)
    scale = min(target.width() / STAGE_W, target.height() / STAGE_H)
    if scale <= 0:
        return
    origin_x = target.left() + (target.width() - STAGE_W * scale) / 2.0
    origin_y = target.top() + (target.height() - STAGE_H * scale) / 2.0
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.translate(origin_x, origin_y)
    painter.scale(scale, scale)
    painter.setClipRect(QRectF(0, 0, STAGE_W, STAGE_H))
    font = QFont(painter.font())
    for item in sorted(frame.shapes + frame.texts, key=lambda entry: entry.order):
        painter.setOpacity(max(0.0, min(1.0, item.alpha)))
        if isinstance(item, Text):
            _paint_text(painter, item, colors, lang, font)
        else:
            _paint_shape(painter, item, colors)
    painter.setOpacity(1.0)
    painter.restore()
