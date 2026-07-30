"""Single source of truth for drawing GroupLabel bands.

The canvas, raster exporter and PDF exporter all call :func:`draw` so a
band looks identical on screen and on paper.  Geometry is computed in
millimetres; callers supply the mm-to-device *scale* (the canvas passes
1.0 because its scene units are already mm).

Text is measured through ``QGraphicsTextItem`` at a fixed ``BASE_PT`` and
then scaled, matching how the existing label/text renderers size glyphs.
"""
from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QGraphicsTextItem, QStyleOptionGraphicsItem

#: Font size the measuring item is built at; real size comes from scaling.
BASE_PT = 24

#: 1 pt in mm, for converting bracket line widths into scene units.
_PT_TO_MM = 25.4 / 72.0


def _font(group_label) -> QFont:
    font = QFont(group_label.font_family, BASE_PT)
    if group_label.font_weight == "bold":
        font.setBold(True)
    return font


def _text_item(group_label) -> QGraphicsTextItem:
    item = QGraphicsTextItem()
    item.setPlainText(group_label.text or "")
    item.setFont(_font(group_label))
    item.setDefaultTextColor(QColor(group_label.color))
    return item


def measure_mm(group_label) -> tuple:
    """Natural (width_mm, height_mm) of the label's text."""
    item = _text_item(group_label)
    rect = item.boundingRect()
    scale = group_label.font_size_pt / BASE_PT
    return rect.width() * scale, rect.height() * scale


def _bracket_depth(group_label) -> float:
    """Space the bracket occupies on the artwork-facing edge of the band."""
    if group_label.bracket_style == "none":
        return 0.0
    return group_label.bracket_gap_mm + group_label.bracket_tick_mm


def split_band(group_label, band: QRectF) -> tuple:
    """Divide the band into ``(text_area, bracket_area)``.

    The bracket always hugs the artwork-facing edge and the text takes the
    remainder, so a band reads as "caption, then rule, then picture".
    """
    depth = _bracket_depth(group_label)
    if depth <= 0:
        return QRectF(band), QRectF()

    side = group_label.side
    if side == "top":
        text = QRectF(band.x(), band.y(), band.width(), band.height() - depth)
        bracket = QRectF(band.x(), band.bottom() - depth, band.width(), depth)
    elif side == "bottom":
        text = QRectF(band.x(), band.y() + depth, band.width(), band.height() - depth)
        bracket = QRectF(band.x(), band.y(), band.width(), depth)
    elif side == "left":
        text = QRectF(band.x(), band.y(), band.width() - depth, band.height())
        bracket = QRectF(band.right() - depth, band.y(), depth, band.height())
    else:  # right
        text = QRectF(band.x() + depth, band.y(), band.width() - depth, band.height())
        bracket = QRectF(band.x(), band.y(), depth, band.height())
    return text, bracket


def text_origin_mm(group_label, text_area: QRectF) -> tuple:
    """Top-left mm position for the unrotated text box inside *text_area*.

    Rotation is applied later around the text's centre, so alignment is
    resolved on the upright box: horizontal bands align along x, vertical
    bands align along y.
    """
    tw, th = measure_mm(group_label)
    align = group_label.align
    horizontal = group_label.side in ("top", "bottom")

    if horizontal:
        if align == "left":
            x = text_area.x()
        elif align == "right":
            x = text_area.right() - tw
        else:
            x = text_area.x() + (text_area.width() - tw) / 2.0
        y = text_area.y() + (text_area.height() - th) / 2.0
    else:
        x = text_area.x() + (text_area.width() - tw) / 2.0
        if align == "top":
            y = text_area.y()
        elif align == "bottom":
            y = text_area.bottom() - th
        else:
            y = text_area.y() + (text_area.height() - th) / 2.0

    return x + group_label.offset_x, y + group_label.offset_y


def bracket_path_mm(group_label, bracket_area: QRectF) -> QPainterPath:
    """Build the rule / bracket / brace path in mm, or an empty path."""
    path = QPainterPath()
    style = group_label.bracket_style
    if style == "none" or bracket_area.isEmpty():
        return path

    tick = group_label.bracket_tick_mm
    side = group_label.side
    horizontal = side in ("top", "bottom")
    # The spine sits on the artwork-facing edge; ticks point towards it.
    if side == "top":
        spine_y = bracket_area.bottom()
        tick_dir = -1.0
    elif side == "bottom":
        spine_y = bracket_area.y()
        tick_dir = 1.0
    elif side == "left":
        spine_x = bracket_area.right()
        tick_dir = -1.0
    else:  # right
        spine_x = bracket_area.x()
        tick_dir = 1.0

    if horizontal:
        x0, x1 = bracket_area.x(), bracket_area.right()
        if style == "line":
            path.moveTo(x0, spine_y)
            path.lineTo(x1, spine_y)
        elif style == "bracket":
            path.moveTo(x0, spine_y + tick * tick_dir)
            path.lineTo(x0, spine_y)
            path.lineTo(x1, spine_y)
            path.lineTo(x1, spine_y + tick * tick_dir)
        else:  # brace
            mid = (x0 + x1) / 2.0
            base = spine_y + tick * tick_dir
            path.moveTo(x0, base)
            path.quadTo(x0, spine_y, mid, spine_y)
            path.quadTo(x1, spine_y, x1, base)
    else:
        y0, y1 = bracket_area.y(), bracket_area.bottom()
        if style == "line":
            path.moveTo(spine_x, y0)
            path.lineTo(spine_x, y1)
        elif style == "bracket":
            path.moveTo(spine_x + tick * tick_dir, y0)
            path.lineTo(spine_x, y0)
            path.lineTo(spine_x, y1)
            path.lineTo(spine_x + tick * tick_dir, y1)
        else:  # brace
            mid = (y0 + y1) / 2.0
            base = spine_x + tick * tick_dir
            path.moveTo(base, y0)
            path.quadTo(spine_x, y0, spine_x, mid)
            path.quadTo(spine_x, y1, base, y1)

    return path


def draw(painter: QPainter, group_label, band: QRectF, scale: float = 1.0) -> None:
    """Render *group_label* into *band* (mm) on a painter scaled by *scale*."""
    if band is None or band.isEmpty():
        return

    text_area, bracket_area = split_band(group_label, band)

    path = bracket_path_mm(group_label, bracket_area)
    if not path.isEmpty():
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pen = QPen(QColor(group_label.bracket_color))
        pen.setWidthF(max(0.05, group_label.bracket_width_pt * _PT_TO_MM) * scale)
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.scale(scale, scale)
        painter.drawPath(path)
        painter.restore()

    if not (group_label.text or "").strip():
        return

    item = _text_item(group_label)
    x_mm, y_mm = text_origin_mm(group_label, text_area)
    text_scale = group_label.font_size_pt / BASE_PT
    rotation = group_label.auto_rotation()

    painter.save()
    if rotation:
        # Rotate about the text's own centre so alignment stays predictable.
        tw, th = measure_mm(group_label)
        cx, cy = x_mm + tw / 2.0, y_mm + th / 2.0
        painter.translate(cx * scale, cy * scale)
        painter.rotate(rotation)
        painter.translate(-(tw / 2.0) * scale, -(th / 2.0) * scale)
    else:
        painter.translate(x_mm * scale, y_mm * scale)
    painter.scale(text_scale * scale, text_scale * scale)
    item.paint(painter, QStyleOptionGraphicsItem(), None)
    painter.restore()


def rotated_bounds_mm(group_label, band: QRectF) -> QRectF:
    """Union of band and rotated text extents, for canvas bounding rects."""
    bounds = QRectF(band)
    if not (group_label.text or "").strip():
        return bounds
    text_area, _bracket = split_band(group_label, band)
    tw, th = measure_mm(group_label)
    x_mm, y_mm = text_origin_mm(group_label, text_area)
    rotation = group_label.auto_rotation()
    if not rotation:
        return bounds.united(QRectF(x_mm, y_mm, tw, th))
    # A rotated box never exceeds a square of its diagonal about its centre.
    cx, cy = x_mm + tw / 2.0, y_mm + th / 2.0
    half = (tw * tw + th * th) ** 0.5 / 2.0
    return bounds.united(QRectF(cx - half, cy - half, half * 2, half * 2))
