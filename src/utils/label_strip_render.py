"""Single source of truth for drawing strip (label-cell) labels.

The canvas (``CellItem._draw_label_cell``), the raster exporter and the PDF
exporter all call :func:`draw_strip_label` so a strip label looks identical
on screen and on paper.  Callers supply the strip rect in the painter's
current coordinate space (device pixels on the canvas after
``resetTransform``, page dots in the exporters).

Alignment is resolved INSIDE the rotated drawing frame: each 90° clockwise
painter rotation maps device-top -> rotated-left, device-bottom ->
rotated-right, device-left -> rotated-bottom, device-right -> rotated-top
(Qt is y-down: ``rotate(90)`` sends +x to +y).  A side effect worth noting:
a non-centred label in a horizontal strip rotated 90° previously slid to
the top/bottom end of the strip; it now stays visually left/right.
"""
from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QPainter

_CW = {"h": {"top": "left", "center": "center", "bottom": "right"},   # device v -> rotated h
       "v": {"left": "bottom", "center": "center", "right": "top"}}   # device h -> rotated v


def strip_text_alignment(vertical: bool, align: str, valign: str,
                         rotation: float) -> tuple[str, str]:
    """(h, v) alignment to use INSIDE the rotated drawing frame so the text
    lands at the requested device-space edge. Horizontal strips use `align`
    with v=center; vertical strips use `valign` with h=center. Each 90°
    clockwise painter rotation maps the axes per the module docstring."""
    h, v = ("center", valign or "center") if vertical else (align or "center", "center")
    for _ in range(int(round((rotation or 0.0) / 90.0)) % 4):
        h, v = _CW["h"][v], _CW["v"][h]
    return h, v


_H_FLAGS = {"left": Qt.AlignmentFlag.AlignLeft,
            "center": Qt.AlignmentFlag.AlignHCenter,
            "right": Qt.AlignmentFlag.AlignRight}
_V_FLAGS = {"top": Qt.AlignmentFlag.AlignTop,
            "center": Qt.AlignmentFlag.AlignVCenter,
            "bottom": Qt.AlignmentFlag.AlignBottom}


def draw_strip_label(painter: QPainter, rect: QRectF, text: str, font: QFont,
                     color: QColor, vertical: bool, align: str, valign: str,
                     rotation: float) -> None:
    """Draw *text* inside *rect*, honouring the strip orientation, the
    effective align/valign and a rotation applied about the rect's centre.

    For odd quarter turns the text is drawn into a rect with swapped
    width/height centred on the same point, so the text box matches the
    strip's footprint after rotation.
    """
    painter.save()
    painter.setFont(font)
    painter.setPen(color)
    turns = int(round((rotation or 0.0) / 90.0)) % 4
    centre = rect.center()
    if rotation:
        painter.translate(centre)
        painter.rotate(rotation)
        painter.translate(-centre)
    box = rect if turns % 2 == 0 else QRectF(
        centre.x() - rect.height() / 2, centre.y() - rect.width() / 2,
        rect.height(), rect.width())
    h, v = strip_text_alignment(vertical, align, valign, rotation)
    painter.drawText(box, _H_FLAGS[h] | _V_FLAGS[v], text)
    painter.restore()
