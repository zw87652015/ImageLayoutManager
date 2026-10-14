"""Text group chips shared by the SVG and raster Match Text Size windows.

One painted chip per project text group: colour dot, name, size, member count and a
hover ×. Drag a size horizontally to scrub it (0.5 pt per 4 px, Shift 0.1 pt); double-click
a size to type it or a name to rename it. A click assigns the window's selection to the
group (or shows its members when nothing is selected); "+" makes a group; "∅" removes the
selection from its groups. The windows own the membership changes (text_group_assign).
"""

from PyQt6.QtCore import QRectF, Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QBrush, QColor, QFont, QFontMetrics, QIcon, QPainter, QPalette, QPen, QPixmap
from PyQt6.QtWidgets import QApplication, QDoubleSpinBox, QLineEdit, QMenu, QWidget, QAbstractSpinBox

from src.app.i18n import tr
from src.app.plot_alignment_logic import group_color
from src.utils.text_group_assign import delete_svg_group

_CHIP_H = 28
_ROUND = 28
_GAP = 6
_PX_PER_HALF_PT = 4.0
_SIZE_MIN = 1.0
_SIZE_MAX = 200.0


def group_colour(project, group_id):
    """Hex colour of the group *group_id* (by its position in the project), or None."""
    index = next((i for i, g in enumerate(project.svg_text_groups) if g.id == group_id), None)
    return None if index is None else group_color(index)


def dot_icon(colour):
    """12 px filled colour dot, used for list rows and menu entries."""
    pixmap = QPixmap(12, 12)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(colour))
    painter.drawEllipse(QRectF(1, 1, 10, 10))
    painter.end()
    return QIcon(pixmap)


def chip_hint(selection_count: int, group_count: int) -> str:
    if selection_count > 0:
        return tr("text_chip_hint_ready").format(n=selection_count)
    if group_count > 0:
        return tr("text_chip_hint_idle")
    return tr("text_chip_hint_empty")


def chip_tooltip(group, selection_count: int) -> str:
    size = f"{group.font_size_pt:g}"
    if selection_count > 0:
        return tr("text_chip_add_tip").format(n=selection_count, name=group.name, size=size)
    return tr("text_chip_show_tip").format(name=group.name, size=size, count=len(group.members))


def populate_group_menu(menu, project, on_assign, on_new, on_remove, can_remove: bool):
    """Group actions for a text list's context menu."""
    add_menu = menu.addMenu(tr("text_menu_add_to_group"))
    groups = project.svg_text_groups
    if not groups:
        add_menu.addAction(tr("text_menu_no_groups")).setEnabled(False)
    for group in groups:
        action = add_menu.addAction(f"{group.name} · {group.font_size_pt:g} pt")
        colour = group_colour(project, group.id)
        if colour:
            action.setIcon(dot_icon(colour))
        action.triggered.connect(lambda _checked=False, gid=group.id: on_assign(gid))
    menu.addAction(tr("text_menu_new_group")).triggered.connect(lambda _checked=False: on_new())
    menu.addSeparator()
    remove = menu.addAction(tr("text_menu_remove_group"))
    remove.setEnabled(can_remove)
    remove.triggered.connect(lambda _checked=False: on_remove())


class _Editor(QLineEdit):
    committed = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._done = False

    def begin(self, text, rect):
        self._done = False
        self.setGeometry(rect)
        self.setText(text)
        self.show()
        self.setFocus()
        self.selectAll()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self._done = True
            self.cancelled.emit()
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if not self._done:
                self._done = True
                self.committed.emit(self.text())
            return
        super().keyPressEvent(event)

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        if not self._done:
            self._done = True
            self.committed.emit(self.text())


class TextGroupChips(QWidget):
    assign_requested = pyqtSignal(object)      # str group id to assign the selection, None to remove it
    new_group_requested = pyqtSignal()
    groups_changed = pyqtSignal()
    members_requested = pyqtSignal(str)

    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.project = project
        self._selection_count = 0
        self._selection_size = None
        self._hover = None
        self._layout_cache = []
        self._scrub = None
        self._pending_click = None
        self._name_editor = _Editor(self)
        self._name_editor.hide()
        self._name_editor.committed.connect(self._commit_name)
        self._name_editor.cancelled.connect(self._name_editor.hide)
        self._size_spin = QDoubleSpinBox(self)
        self._size_spin.setRange(_SIZE_MIN, _SIZE_MAX)
        self._size_spin.setDecimals(2)
        self._size_spin.setSuffix(" pt")
        self._size_spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self._size_spin.hide()
        self._size_spin.installEventFilter(self)
        self._size_spin.editingFinished.connect(self._commit_size)
        self._size_cancel = False
        self._edit_gid = None
        self._click_timer = QTimer(self)
        self._click_timer.setSingleShot(True)
        self._click_timer.timeout.connect(self._fire_pending_click)
        self.setMouseTracking(True)
        self.setAccessibleName(tr("text_chips_label"))
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.refresh()

    # ── public ───────────────────────────────────────────────────────────

    def set_selection_info(self, count, size_pt=None):
        self._selection_count = count
        self._selection_size = size_pt
        self.update()

    def refresh(self):
        self._layout_cache = self._layout()
        self.setMinimumHeight(_CHIP_H + 2 * _GAP)
        self.update()

    # ── layout ───────────────────────────────────────────────────────────

    def _group(self, gid):
        return next((g for g in self.project.svg_text_groups if g.id == gid), None)

    def _layout(self):
        fm = QFontMetrics(self.font())
        x, y = float(_GAP), float(_GAP)
        available = max(200.0, float(self.width() or 360))
        parts = []
        items = [("chip", g.id) for g in self.project.svg_text_groups] + [("none", None), ("plus", None)]
        for kind, gid in items:
            if kind == "chip":
                group = self._group(gid)
                name_w = fm.horizontalAdvance(group.name)
                size_w = fm.horizontalAdvance(f"{group.font_size_pt:g} pt")
                count_w = fm.horizontalAdvance(str(len(group.members))) + 10
                width = 12 + 10 + 6 + name_w + 10 + size_w + 8 + count_w + 22
            elif kind == "none":
                width = fm.horizontalAdvance("∅") + 24
            else:
                width = _ROUND
            if x + width > available and x > _GAP:
                x = float(_GAP)
                y += _CHIP_H + _GAP
            rect = QRectF(x, y, width, _CHIP_H if kind != "plus" else _ROUND)
            parts.append((kind, gid, rect))
            x += width + _GAP
        return parts

    def _chip_regions(self, rect, gid):
        fm = QFontMetrics(self.font())
        group = self._group(gid)
        size_text = f"{group.font_size_pt:g} pt"
        size_w = fm.horizontalAdvance(size_text) + 8
        x_rect = QRectF(rect.right() - 20, rect.top() + 6, 16, 16)
        size_rect = QRectF(rect.right() - 22 - size_w - 4, rect.top() + 4, size_w, _CHIP_H - 8)
        name_rect = QRectF(rect.left() + 28, rect.top(), max(0.0, size_rect.left() - rect.left() - 30), rect.height())
        return {"name": name_rect, "size": size_rect, "x": x_rect}

    def _hit(self, pos):
        for kind, gid, rect in self._layout_cache:
            if kind == "chip" and rect.contains(pos):
                regions = self._chip_regions(rect, gid)
                if self._hover is not None and self._hover[0] == gid and regions["x"].contains(pos):
                    return "x", gid
                for part in ("size", "name"):
                    if regions[part].contains(pos):
                        return part, gid
                return "chip", gid
            if kind == "none" and rect.contains(pos):
                return "none", None
            if kind == "plus" and rect.contains(pos):
                return "plus", None
        return None, None

    # ── painting ─────────────────────────────────────────────────────────

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = self.palette()
        text = pal.color(QPalette.ColorRole.Text)
        base = pal.color(QPalette.ColorRole.Base)
        mid = pal.color(QPalette.ColorRole.Mid)
        accent = pal.color(QPalette.ColorRole.Highlight)
        for kind, gid, rect in self._layout_cache:
            if kind == "chip":
                self._paint_chip(painter, rect, gid, text, base, mid, accent)
            elif kind == "none":
                painter.setPen(QPen(mid, 1))
                painter.setBrush(QBrush(base))
                painter.drawRoundedRect(rect, _CHIP_H / 2, _CHIP_H / 2)
                painter.setPen(text)
                painter.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), "∅")
            else:
                painter.setPen(QPen(accent, 1.4))
                painter.setBrush(QBrush(base))
                painter.drawEllipse(rect)
                cx, cy = rect.center().x(), rect.center().y()
                painter.drawLine(QRectF(cx - 5, cy, 10, 0).topLeft(), QRectF(cx - 5, cy, 10, 0).topRight())
                painter.drawLine(QRectF(cx, cy - 5, 0, 10).topLeft(), QRectF(cx, cy - 5, 0, 10).bottomLeft())
        painter.end()

    def _paint_chip(self, painter, rect, gid, text, base, mid, accent):
        group = self._group(gid)
        if group is None:
            return
        colour = QColor(group_colour(self.project, gid) or accent.name())
        selected_target = self._selection_count > 0
        painter.save()
        tint = QColor(colour)
        tint.setAlpha(40 if selected_target else 22)
        hovered = self._hover is not None and self._hover[0] == gid
        border_w = 2 if selected_target and hovered else 1
        painter.setPen(QPen(colour if selected_target else mid, border_w))
        painter.setBrush(QBrush(tint))
        painter.drawRoundedRect(rect, _CHIP_H / 2, _CHIP_H / 2)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(colour))
        painter.drawEllipse(QRectF(rect.left() + 12, rect.center().y() - 5, 10, 10))
        regions = self._chip_regions(rect, gid)
        painter.setPen(text)
        painter.drawText(regions["name"], int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
                         QFontMetrics(self.font()).elidedText(group.name, Qt.TextElideMode.ElideRight,
                                                              int(regions["name"].width())))
        painter.setPen(QColor(colour))
        painter.drawText(regions["size"], int(Qt.AlignmentFlag.AlignCenter), f"{group.font_size_pt:g} pt")
        count = str(len(group.members))
        count_rect = QRectF(regions["size"].right() + 2, rect.top() + 6, QFontMetrics(self.font()).horizontalAdvance(count) + 8,
                            _CHIP_H - 12)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(base))
        painter.drawRoundedRect(count_rect, 6, 6)
        painter.setPen(text)
        painter.drawText(count_rect, int(Qt.AlignmentFlag.AlignCenter), count)
        if self._hover is not None and self._hover[0] == gid:
            painter.setPen(QPen(mid, 1.4))
            painter.drawText(regions["x"], int(Qt.AlignmentFlag.AlignCenter), "\u00d7")
        painter.restore()

    # ── mouse ────────────────────────────────────────────────────────────

    def mouseMoveEvent(self, event):
        if self._scrub is not None:
            self._scrub_move(event)
            return
        kind, gid = self._hit(event.position())
        hover = (gid, kind) if gid is not None and kind in ("chip", "x", "name", "size") else None
        if hover != self._hover:
            self._hover = hover
            self.update()
        self.setToolTip(self._tip_for(kind, gid))
        if kind is None:
            self.unsetCursor()
        else:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        super().mouseMoveEvent(event)

    def _tip_for(self, kind, gid):
        if kind == "plus":
            return tr("text_chip_new_tip")
        if kind == "none":
            return tr("text_chip_none_tip")
        if kind == "x":
            return tr("svgtxt_delete_group_btn")
        if kind == "size":
            return tr("text_chip_size_tip")
        if kind in ("chip", "name") and gid is not None:
            return chip_tooltip(self._group(gid), self._selection_count)
        return ""

    def leaveEvent(self, event):
        self._hover = None
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        kind, gid = self._hit(event.position())
        if kind == "size":
            group = self._group(gid)
            self._scrub = {"gid": gid, "x": event.position().x(), "start": group.font_size_pt,
                           "value": group.font_size_pt, "shift": False, "moved": False}
            event.accept()
            return
        if kind == "x":
            delete_svg_group(self.project, gid)
            self.refresh()
            self.groups_changed.emit()
            return
        if kind in ("chip", "name"):
            self._pending_click = ("chip", gid)
            self._click_timer.start(QApplication.doubleClickInterval())
            event.accept()
            return
        if kind == "none":
            self.assign_requested.emit(None)
        elif kind == "plus":
            self.new_group_requested.emit()

    def mouseReleaseEvent(self, event):
        if self._scrub is None or event.button() != Qt.MouseButton.LeftButton:
            return
        scrub, self._scrub = self._scrub, None
        group = self._group(scrub["gid"])
        if group is not None and scrub["moved"] and abs(scrub["value"] - group.font_size_pt) > 1e-9:
            group.font_size_pt = scrub["value"]
            self.refresh()
            self.groups_changed.emit()

    def _scrub_move(self, event):
        scrub = self._scrub
        scrub["shift"] = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        delta_px = event.position().x() - scrub["x"]
        if abs(delta_px) >= 1:
            scrub["moved"] = True
        step = 0.1 if scrub["shift"] else 0.5
        value = scrub["start"] + (delta_px / _PX_PER_HALF_PT) * step
        scrub["value"] = round(min(_SIZE_MAX, max(_SIZE_MIN, value)), 2)
        self.setToolTip(f"{scrub['value']:g} pt")

    def mouseDoubleClickEvent(self, event):
        kind, gid = self._hit(event.position())
        if kind not in ("size", "name", "chip") or gid is None:
            return
        self._click_timer.stop()
        self._pending_click = None
        self._scrub = None
        if kind == "size":
            self._open_size_spin(gid)
        else:
            self._open_name_editor(gid)
        event.accept()

    def _fire_pending_click(self):
        if self._pending_click is None:
            return
        _kind, gid = self._pending_click
        self._pending_click = None
        if self._selection_count > 0:
            self.assign_requested.emit(gid)
        else:
            self.members_requested.emit(gid)

    # ── inline editors ───────────────────────────────────────────────────

    def _open_name_editor(self, gid):
        group = self._group(gid)
        rect = next(r for k, g, r in self._layout_cache if k == "chip" and g == gid)
        region = self._chip_regions(rect, gid)["name"]
        self._edit_gid = gid
        self._name_editor.begin(group.name, region.toRect())

    def _commit_name(self, text):
        gid = self._edit_gid
        self._name_editor.hide()
        self._edit_gid = None
        group = self._group(gid) if gid else None
        if group is not None:
            group.name = text.strip() or tr("svgtxt_default_group_name")
            self.refresh()
            self.groups_changed.emit()

    def _open_size_spin(self, gid):
        group = self._group(gid)
        rect = next(r for k, g, r in self._layout_cache if k == "chip" and g == gid)
        region = self._chip_regions(rect, gid)["size"]
        self._edit_gid = gid
        self._size_cancel = False
        self._size_spin.setValue(group.font_size_pt)
        self._size_spin.setGeometry(int(region.left() - 6), int(region.top() - 2),
                                    int(region.width() + 26), int(region.height() + 4))
        self._size_spin.show()
        self._size_spin.setFocus()
        self._size_spin.selectAll()

    def _commit_size(self):
        if not self._size_spin.isVisible():
            return
        gid = self._edit_gid
        value = min(_SIZE_MAX, max(_SIZE_MIN, self._size_spin.value()))
        self._size_spin.hide()
        if self._size_cancel or gid is None:
            self._size_cancel = False
            return
        group = self._group(gid)
        if group is not None and abs(value - group.font_size_pt) > 1e-9:
            group.font_size_pt = value
            self.refresh()
            self.groups_changed.emit()

    def eventFilter(self, obj, event):
        from PyQt6.QtCore import QEvent
        if obj is self._size_spin and event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape:
            self._size_cancel = True
            self._size_spin.hide()
            self.setFocus()
            return True
        return super().eventFilter(obj, event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.refresh()
