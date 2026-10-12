"""Canvas rulers for CanvasView — QWidget overlays laid out by the view.

Scene units are millimetres and the page starts at scene (0,0), so ruler
zero is the page top-left and positions off the page read negative.
"""

from PyQt6.QtWidgets import QWidget, QMenu
from PyQt6.QtCore import Qt, QPointF, QRectF
from PyQt6.QtGui import QPainter, QPen, QFont, QActionGroup

from src.app.i18n import tr
from src.app.theme import token_color
from src.canvas.ruler_math import (
    MM_PER_UNIT, UNITS, choose_steps, ticks, format_label,
)


def _unit_menu(parent, current_unit, callback):
    """Shared unit picker used by both rulers and the corner square."""
    menu = QMenu(parent)
    group = QActionGroup(menu)
    group.setExclusive(True)
    for u in UNITS:
        act = menu.addAction(tr(f"ruler_unit_{u}"))
        act.setCheckable(True)
        act.setChecked(u == current_unit)
        group.addAction(act)
        act.triggered.connect(lambda _c=False, u=u: callback(u))
    return menu


class CanvasRuler(QWidget):
    """One ruler strip; ruler-local coordinate along its axis equals the
    viewport coordinate, so the view only has to align geometry."""

    def __init__(self, orientation: Qt.Orientation, view, parent=None):
        super().__init__(view if parent is None else parent)
        self._orientation = orientation
        self._view = view
        self._unit = "mm"
        self._tokens = {}
        self._cursor = None            # px along ruler axis, or None
        self._selection = None         # (start_px, end_px) or None
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setAccessibleName(
            tr("ruler_horizontal")
            if orientation == Qt.Orientation.Horizontal
            else tr("ruler_vertical"))
        self.setMouseTracking(True)

    # -- configuration --------------------------------------------------

    def thickness(self) -> int:
        """Logical-pixel thickness the view should reserve for this ruler."""
        return max(18, self.fontMetrics().height() + 6)

    def set_unit(self, unit: str):
        if unit in MM_PER_UNIT and unit != self._unit:
            self._unit = unit
            self.update()

    def set_tokens(self, tokens: dict):
        self._tokens = tokens or {}
        self.update()

    def set_cursor(self, px):
        self._cursor = px

    def set_selection_range(self, rng):
        self._selection = rng

    def contextMenuEvent(self, event):
        menu = _unit_menu(self, self._unit,
                          self._view.ruler_unit_requested.emit)
        menu.exec(event.globalPos())

    # -- painting --------------------------------------------------------

    def _ruler_font(self) -> QFont:
        f = QFont(self.font())
        if f.pointSizeF() > 0:
            f.setPointSizeF(f.pointSizeF() * 0.85)
        else:
            f.setPixelSize(max(1, int(f.pixelSize() * 0.85)))
        return f

    def _snap(self, px: float, dpr: float) -> float:
        return (round(px * dpr) + 0.5) / dpr

    def paintEvent(self, event):
        horizontal = self._orientation == Qt.Orientation.Horizontal
        length = self.width() if horizontal else self.height()
        thick = self.height() if horizontal else self.width()
        if length <= 0 or thick <= 0:
            return

        tk = self._tokens
        bg = token_color(tk.get("panel", "#F5F5F5"))
        border = token_color(tk.get("border", "#D8D8D8"))
        fg = token_color(tk.get("text_sec", "#6E6E73"))
        accent = token_color(tk.get("accent", "#0891B2"))
        tint = token_color(tk.get("accent_tint", "rgba(8,145,178,0.12)"))

        p = QPainter(self)
        p.fillRect(self.rect(), bg)
        font = self._ruler_font()
        p.setFont(font)
        fm = p.fontMetrics()

        m = self._view.viewportTransform()
        scale = (m.m11() if horizontal else m.m22()) * MM_PER_UNIT[self._unit]
        offset = m.dx() if horizontal else m.dy()
        if scale == 0:
            p.end()
            return
        # value(px) in display units
        start = (0 - offset) / scale
        end = (length - offset) / scale

        px_per_unit = abs(scale)
        step, sub = choose_steps(px_per_unit, self._unit, 48)
        widest = max(
            fm.horizontalAdvance(format_label(start, step)),
            fm.horizontalAdvance(format_label(end, step)),
        )
        step, sub = choose_steps(px_per_unit, self._unit,
                                 max(48, widest + 10))

        dpr = self.devicePixelRatioF()
        inner = thick  # edge facing the canvas (bottom / right)

        # Selection extent between the two edges.
        if self._selection is not None:
            a, b = self._selection
            a, b = min(a, b), max(a, b)
            p.fillRect(QRectF(a, 0, b - a, thick) if horizontal
                       else QRectF(0, a, thick, b - a), tint)
            edge_pen = QPen(accent, 0)
            edge_pen.setCosmetic(True)
            p.setPen(edge_pen)
            for e in (self._snap(a, dpr), self._snap(b, dpr)):
                if horizontal:
                    p.drawLine(QPointF(e, 0), QPointF(e, thick))
                else:
                    p.drawLine(QPointF(0, e), QPointF(thick, e))

        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        tick_pen = QPen(fg, 0)
        tick_pen.setCosmetic(True)
        lengths = {"major": 0.6, "half": 0.4, "minor": 0.25}
        label_pen = QPen(fg, 0)
        for value, kind in ticks(start, end, step, sub):
            px = self._snap(offset + value * scale, dpr)
            ln = lengths[kind] * thick
            if horizontal:
                p.setPen(tick_pen)
                p.drawLine(QPointF(px, inner), QPointF(px, inner - ln))
            else:
                p.setPen(tick_pen)
                p.drawLine(QPointF(inner, px), QPointF(inner - ln, px))
            if kind == "major":
                p.setPen(label_pen)
                text = format_label(value, step)
                if horizontal:
                    p.drawText(QPointF(px + 3, fm.ascent() + 1), text)
                else:
                    p.save()
                    p.translate(fm.ascent() + 2, px - 3)
                    p.rotate(-90)
                    p.drawText(QPointF(0, 0), text)
                    p.restore()

        # Cursor marker.
        if self._cursor is not None:
            c = self._snap(self._cursor, dpr)
            cur_pen = QPen(accent, 0)
            cur_pen.setCosmetic(True)
            p.setPen(cur_pen)
            if horizontal:
                p.drawLine(QPointF(c, 0), QPointF(c, thick))
            else:
                p.drawLine(QPointF(0, c), QPointF(thick, c))

        # Separator on the inner edge.
        sep = QPen(border, 0)
        sep.setCosmetic(True)
        p.setPen(sep)
        e = self._snap(thick - 1, dpr)
        if horizontal:
            p.drawLine(QPointF(0, e), QPointF(length, e))
        else:
            p.drawLine(QPointF(e, 0), QPointF(e, length))
        p.end()


class RulerCorner(QWidget):
    """Square at the top-left of the ruler pair; shows the unit and opens
    the unit picker on either mouse button."""

    def __init__(self, view, parent=None):
        super().__init__(view if parent is None else parent)
        self._view = view
        self._unit = "mm"
        self._tokens = {}

    def set_unit(self, unit: str):
        if unit in MM_PER_UNIT and unit != self._unit:
            self._unit = unit
            self.update()
        self.setToolTip(tr("ruler_corner_tip").format(unit=self._unit))

    def set_tokens(self, tokens: dict):
        self._tokens = tokens or {}
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() in (Qt.MouseButton.LeftButton,
                              Qt.MouseButton.RightButton):
            menu = _unit_menu(self, self._unit,
                              self._view.ruler_unit_requested.emit)
            menu.exec(event.globalPosition().toPoint())
            return
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        tk = self._tokens
        bg = token_color(tk.get("panel", "#F5F5F5"))
        border = token_color(tk.get("border", "#D8D8D8"))
        fg = token_color(tk.get("text_sec", "#6E6E73"))
        p = QPainter(self)
        p.fillRect(self.rect(), bg)
        f = QFont(self.font())
        if f.pointSizeF() > 0:
            f.setPointSizeF(f.pointSizeF() * 0.8)
        else:
            f.setPixelSize(max(1, int(f.pixelSize() * 0.8)))
        p.setFont(f)
        p.setPen(fg)
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._unit)
        pen = QPen(border, 0)
        pen.setCosmetic(True)
        p.setPen(pen)
        dpr = self.devicePixelRatioF()
        w, h = self.width(), self.height()
        x = (round((w - 1) * dpr) + 0.5) / dpr
        y = (round((h - 1) * dpr) + 0.5) / dpr
        p.drawLine(QPointF(0, y), QPointF(w, y))   # inner edge: bottom
        p.drawLine(QPointF(x, 0), QPointF(x, h))   # inner edge: right
        p.end()
