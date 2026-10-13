from __future__ import annotations

import copy
import math
import os
import uuid
from collections import OrderedDict

from PyQt6.QtCore import QEvent, QPointF, QRectF, QSize, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import (
    QBrush, QColor, QFont, QFontMetrics, QImage, QKeySequence, QPainter, QPainterPath, QPalette, QPen, QShortcut,
)
from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea, QSizePolicy,
    QSplitter, QTabWidget, QToolButton, QVBoxLayout, QWidget,
)

from src.app.help_dialog import show_context_help
from src.app.i18n import tr
from src.app.pictogram_combo import PictogramCombo
from src.app.plot_alignment_logic import (
    MarkHistory, card_order, card_status, cycle_row, group_color, next_needed, nudge_box, plan_initial_group, progress,
)
from src.app.theme import DARK, LIGHT, get_tokens, token_color
from src.canvas.canvas_scene import CanvasScene
from src.canvas.canvas_view import CanvasView
from src.model.data_model import PlotArea, PlotAlignmentGroup
from src.model.layout_engine import LayoutEngine
from src.utils.image_proxy import ThumbnailWorker
from src.utils.plot_alignment import resolve_image_placements, source_digest
from src.utils.plot_area_detect import suggest_plot_area


def alignment_issue_text(issue, project=None):
    text = tr("plot_issue_" + issue.code)
    cell = project.find_cell_by_id(issue.cell_id) if project and issue.cell_id else None
    if cell and cell.image_path:
        text = os.path.basename(cell.image_path) + ": " + text
    return text


def alignment_issues_text(issues, project=None, limit=3):
    messages = list(dict.fromkeys(alignment_issue_text(i, project) for i in issues))
    shown = messages[:limit]
    if len(messages) > limit:
        shown.append(tr("plot_more_issues").format(count=len(messages) - limit))
    return "\n".join(shown)


class PlotGuideIllustration(QWidget):
    def __init__(self, mode="mark", parent=None):
        super().__init__(parent)
        self.mode = mode
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAccessibleName(tr("plot_example_mark" if mode == "mark" else "plot_example_alignment"))
        self.setAccessibleDescription(tr("plot_diagram_" + mode + "_description"))
        self.setToolTip(self.accessibleDescription())

    def sizeHint(self):
        return QSize(520, 260)

    @staticmethod
    def _arrow(painter, start, end, size=6, both=False):
        painter.drawLine(start, end)
        delta = end - start
        length = max(1, (delta.x() ** 2 + delta.y() ** 2) ** 0.5)
        unit = delta / length
        normal = QPointF(-unit.y(), unit.x())
        for tip, direction in ((end, -1), (start, 1)) if both else ((end, -1),):
            base = tip + unit * (direction * size)
            painter.drawLine(tip, base + normal * (size * 0.5))
            painter.drawLine(tip, base - normal * (size * 0.5))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        palette = self.palette()
        tokens = get_tokens(DARK if palette.window().color().lightness() < 128 else LIGHT)
        accent = QColor(tokens["accent"])
        painter.fillRect(self.rect(), palette.base())
        painter.setPen(QPen(QColor(tokens["border"]), 1))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 5, 5)
        fm = self.fontMetrics()
        line = fm.height()
        margin = max(10, line * 0.65)
        text_width = max(fm.horizontalAdvance(tr("plot_example_caption")), fm.horizontalAdvance(tr("plot_box_plot")), fm.horizontalAdvance(tr("plot_keep_labels"))) + margin
        split = max(text_width + margin, self.width() * 0.44)
        painter.setPen(palette.text().color())
        font = QFont(self.font())
        font.setWeight(QFont.Weight.Medium)
        painter.setFont(font)
        painter.drawText(QRectF(margin, margin, split - margin * 2, line * 2), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap, tr("plot_example_caption"))
        painter.setFont(self.font())
        captions = ("plot_box_plot", "plot_keep_labels") if self.mode == "mark" else ("plot_same_height", "plot_same_bottom")
        for i, key in enumerate(captions):
            painter.drawText(QRectF(margin, max(line * 2.7, self.height() * 0.47) + i * line * 1.3, split - margin * 2, line * 1.3), Qt.AlignmentFlag.AlignVCenter,
                             painter.fontMetrics().elidedText(tr(key), Qt.TextElideMode.ElideRight, int(split - margin * 2)))
        graph = QRectF(split + line * 2, margin + line * 0.5, max(50, self.width() - split - line * 2 - margin * 2), max(25, self.height() - margin * 2 - line * 2.5))
        tint = QColor(accent)
        tint.setAlpha(45)
        if self.mode == "mark":
            self._paint_mark(painter, graph, accent, tint, line)
        else:
            self._paint_alignment(painter, graph, accent, tint, line)

    def _paint_mark(self, painter, graph, accent, tint, line):
        painter.setBrush(tint)
        painter.setPen(QPen(accent, 1.5))
        painter.drawRect(graph)
        painter.setPen(QPen(self.palette().text().color(), 1))
        painter.drawLine(graph.topLeft(), graph.bottomLeft())
        painter.drawLine(graph.bottomLeft(), graph.bottomRight())
        for fraction in (0.25, 0.5, 0.75):
            x = graph.left() + graph.width() * fraction
            y = graph.bottom() - graph.height() * fraction
            painter.drawLine(QPointF(x, graph.bottom()), QPointF(x, graph.bottom() + 4))
            painter.drawLine(QPointF(graph.left(), y), QPointF(graph.left() - 4, y))
        painter.drawText(QRectF(graph.left(), graph.bottom() + 5, graph.width(), line), Qt.AlignmentFlag.AlignCenter,
                         painter.fontMetrics().elidedText(tr("plot_axis_x"), Qt.TextElideMode.ElideRight, int(graph.width())))
        painter.save()
        painter.translate(graph.left() - line, graph.center().y())
        painter.rotate(-90)
        painter.drawText(QRectF(-graph.height() / 2, -line, graph.height(), line), Qt.AlignmentFlag.AlignCenter,
                         painter.fontMetrics().elidedText(tr("plot_axis_y"), Qt.TextElideMode.ElideRight, int(graph.height())))
        painter.restore()
        points = [QPointF(graph.left() + graph.width() * x, graph.top() + graph.height() * y) for x, y in ((0.12, 0.8), (0.35, 0.45), (0.55, 0.6), (0.87, 0.2))]
        for start, end in zip(points, points[1:]):
            painter.drawLine(start, end)
        painter.setPen(QPen(accent, 1.5))
        radius = line * 0.55
        delta = graph.bottomRight() - graph.topLeft()
        inset = delta * ((radius + 3) / max(1, (delta.x() ** 2 + delta.y() ** 2) ** 0.5))
        self._arrow(painter, graph.topLeft() + inset, graph.bottomRight() - inset, line * 0.45)
        painter.setBrush(self.palette().base())
        for number, point in enumerate((graph.topLeft(), graph.bottomRight()), 1):
            painter.drawEllipse(point, radius, radius)
            painter.drawText(QRectF(point.x() - radius, point.y() - radius, radius * 2, radius * 2), Qt.AlignmentFlag.AlignCenter, str(number))

    def _paint_alignment(self, painter, graph, accent, tint, line):
        first = QRectF(graph.left(), graph.top() + line, graph.width() * 0.32, graph.height() - line)
        second = QRectF(graph.left() + graph.width() * 0.52, first.top(), graph.width() * 0.48, first.height())
        painter.setPen(QPen(accent, 1.5))
        painter.setBrush(tint)
        painter.drawRect(first)
        painter.drawRect(second)
        painter.setPen(self.palette().text().color())
        painter.drawText(QRectF(first.left() - line, graph.top() - line * 0.2, first.width() + line * 2, line), Qt.AlignmentFlag.AlignCenter,
                         painter.fontMetrics().elidedText(tr("plot_reference"), Qt.TextElideMode.ElideRight, int(first.width() + line * 2)))
        painter.setPen(QPen(accent, 1.5))
        self._arrow(painter, QPointF(first.right() + graph.width() * 0.1, first.top()), QPointF(first.right() + graph.width() * 0.1, first.bottom()), line * 0.4, both=True)
        painter.setPen(QPen(self.palette().text().color(), 1.5, Qt.PenStyle.DashLine))
        painter.drawLine(QPointF(graph.left() - 8, first.bottom()), QPointF(graph.right() + 8, first.bottom()))


class PlotAreaView(QWidget):
    area_changed = pyqtSignal(object, str)   # (area, "draw" | "edit" | "nudge")
    suggestion_dismissed = pyqtSignal()
    clear_requested = pyqtSignal()
    confirm_requested = pyqtSignal()

    _HANDLE = 8
    _HIT = 9
    _ARROWS = {
        Qt.Key.Key_Left: (-1, 0), Qt.Key.Key_Right: (1, 0),
        Qt.Key.Key_Up: (0, -1), Qt.Key.Key_Down: (0, 1),
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(160, 120)
        self._image = QImage()
        self._area = None
        self._crop = None
        self._scale = 1.0
        self._offset = QPointF()
        self._fitted = True
        self._space = False
        self._drag = None
        self._drawn = False
        self._guide_target = False
        self._suggestion = None   # (box, label): a hint, never the area
        self._empty_hint = False

    def set_guide_target(self, targeted):
        self._guide_target = targeted
        self.update()

    def _paint_guide_border(self, painter):
        if self._guide_target:
            tokens = get_tokens(DARK if self.palette().window().color().lightness() < 128 else LIGHT)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(tokens["accent"]), 2))
            painter.drawRect(QRectF(self.rect()).adjusted(1, 1, -1, -1))

    @property
    def area(self):
        return self._area

    def set_image(self, image):
        self._image = image.toImage() if hasattr(image, "toImage") else QImage(image) if image is not None else QImage()
        self._area = None
        self._crop = None
        self._drag = None
        self._suggestion = None
        self.fit_view()

    def set_area(self, area):
        if area is not None and hasattr(area, "left"):
            area = (area.left, area.top, area.right, area.bottom)
        self._area = tuple(area) if area is not None else None
        self.update()

    def set_suggestion(self, box, label=""):
        self._suggestion = (tuple(box), label) if box is not None else None
        self.update()

    def set_empty_hint(self, shown):
        self._empty_hint = bool(shown)
        self.update()

    def set_crop(self, crop):
        self._crop = crop
        self.update()

    def fit_view(self):
        self._fitted = True
        if not self._image.isNull():
            self._scale = max(0.001, min((self.width() - 24) / self._image.width(), (self.height() - 24) / self._image.height()))
            self._offset = QPointF((self.width() - self._image.width() * self._scale) / 2, (self.height() - self._image.height() * self._scale) / 2)
        self.update()

    def resizeEvent(self, event):
        if self._fitted:
            self.fit_view()
        super().resizeEvent(event)

    def image_rect(self):
        return QRectF(self._offset, self._image.size().toSizeF() * self._scale)

    def normalized_at(self, position):
        rect = self.image_rect()
        if rect.isEmpty():
            return QPointF()
        return QPointF(min(1.0, max(0.0, (position.x() - rect.left()) / rect.width())), min(1.0, max(0.0, (position.y() - rect.top()) / rect.height())))

    def point_for_area(self, x, y):
        rect = self.image_rect()
        return QPointF(rect.left() + x * rect.width(), rect.top() + y * rect.height())

    def _box_rect(self, box):
        return QRectF(self.point_for_area(box[0], box[1]), self.point_for_area(box[2], box[3]))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.fillRect(self.rect(), self.palette().window())
        if self._image.isNull():
            self._paint_guide_border(painter)
            return
        rect = self.image_rect()
        painter.fillRect(rect, Qt.GlobalColor.white)
        painter.drawImage(rect, self._image)
        if self._crop and self._crop != (0, 0, 1, 1):
            painter.setPen(QPen(self.palette().text().color(), 1, Qt.PenStyle.DashLine))
            painter.drawRect(self._box_rect(self._crop))
        if self._area:
            box = self._box_rect(self._area)
            color = self.palette().highlight().color()
            painter.setPen(QPen(color, 2))
            tint = QColor(color)
            tint.setAlpha(28)
            painter.setBrush(tint)
            painter.drawRect(box)
            painter.setBrush(self.palette().base())
            half = self._HANDLE / 2
            for x in (box.left(), box.center().x(), box.right()):
                for y in (box.top(), box.center().y(), box.bottom()):
                    if x != box.center().x() or y != box.center().y():
                        painter.drawRect(QRectF(x - half, y - half, self._HANDLE, self._HANDLE))
        if self._suggestion:
            box_rect = self._box_rect(self._suggestion[0])
            highlight = self.palette().highlight().color()
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(highlight, 1.5, Qt.PenStyle.DashLine))
            painter.drawRect(box_rect)
            label = self._suggestion[1]
            if label:
                metrics = QFontMetrics(painter.font())
                tag = QRectF(box_rect.left() + 4, box_rect.top() + 4,
                             metrics.horizontalAdvance(label) + 12, metrics.height() + 4)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(highlight)
                painter.drawRoundedRect(tag, 3, 3)
                painter.setPen(QPen(self.palette().highlightedText().color()))
                painter.drawText(tag, int(Qt.AlignmentFlag.AlignCenter), label)
        if self._empty_hint and not self._area and not self._suggestion:
            self._paint_empty_hint(painter)
        self._paint_guide_border(painter)

    def _paint_empty_hint(self, painter):
        rect = self.image_rect()
        if rect.isEmpty():
            return
        box = QRectF(rect.center().x() - rect.width() * 0.2, rect.center().y() - rect.height() * 0.15,
                     rect.width() * 0.4, rect.height() * 0.3)
        ghost = QColor(self.palette().highlight().color())
        ghost.setAlpha(120)
        painter.setPen(QPen(ghost, 1.5, Qt.PenStyle.DashLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(box)
        start = QPointF(box.left() - 8, box.bottom() + 18)
        end = QPointF(box.right() + 8, box.top() - 18)
        painter.setPen(QPen(ghost, 2))
        painter.drawLine(start, end)
        painter.drawLine(QPointF(end.x() - 9, end.y()), end)
        painter.drawLine(QPointF(end.x(), end.y() + 9), end)
        cursor = QPainterPath()
        cursor.moveTo(QPointF(box.right() - 4, box.bottom() - 4))
        cursor.lineTo(QPointF(box.right() - 4, box.bottom() + 12))
        cursor.lineTo(QPointF(box.right() + 1, box.bottom() + 9))
        cursor.closeSubpath()
        painter.setBrush(QBrush(ghost))
        painter.drawPath(cursor)

    def _hit(self, position):
        if not self._area:
            return "draw"
        rect = self._box_rect(self._area)
        if not rect.adjusted(-self._HIT, -self._HIT, self._HIT, self._HIT).contains(position):
            return "draw"
        hit = ""
        if abs(position.x() - rect.left()) <= self._HIT:
            hit += "l"
        elif abs(position.x() - rect.right()) <= self._HIT:
            hit += "r"
        if abs(position.y() - rect.top()) <= self._HIT:
            hit += "t"
        elif abs(position.y() - rect.bottom()) <= self._HIT:
            hit += "b"
        return hit or "move"

    def mousePressEvent(self, event):
        self.setFocus()
        if self._image.isNull():
            return
        pos = event.position()
        if event.button() == Qt.MouseButton.MiddleButton or (event.button() == Qt.MouseButton.LeftButton and self._space):
            self._drag = ("pan", pos, self._offset)
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        elif event.button() == Qt.MouseButton.LeftButton and self.image_rect().contains(pos):
            mode = self._hit(pos)
            self._drag = (mode, self.normalized_at(pos), self._area)
            self._drawn = False
        event.accept()

    def mouseMoveEvent(self, event):
        if not self._drag:
            hit = self._hit(event.position())
            cursors = {"move": Qt.CursorShape.SizeAllCursor, "l": Qt.CursorShape.SizeHorCursor, "r": Qt.CursorShape.SizeHorCursor, "t": Qt.CursorShape.SizeVerCursor, "b": Qt.CursorShape.SizeVerCursor, "lt": Qt.CursorShape.SizeFDiagCursor, "rb": Qt.CursorShape.SizeFDiagCursor, "rt": Qt.CursorShape.SizeBDiagCursor, "lb": Qt.CursorShape.SizeBDiagCursor}
            self.setCursor(cursors.get(hit, Qt.CursorShape.CrossCursor))
            return
        mode, start, original = self._drag
        if mode == "pan":
            self._offset = original + event.position() - start
            self._fitted = False
        else:
            end = self.normalized_at(event.position())
            epsilon = 0.0001
            if mode == "draw":
                l, r = sorted((start.x(), end.x()))
                t, b = sorted((start.y(), end.y()))
                if r - l >= epsilon and b - t >= epsilon:
                    self._area = (l, t, r, b)
                    self._drawn = True
            elif mode == "move":
                l, t, r, b = original
                dx = min(1 - r, max(-l, end.x() - start.x()))
                dy = min(1 - b, max(-t, end.y() - start.y()))
                self._area = (l + dx, t + dy, r + dx, b + dy)
            else:
                l, t, r, b = original
                if "l" in mode:
                    l = min(r - epsilon, end.x())
                if "r" in mode:
                    r = max(l + epsilon, end.x())
                if "t" in mode:
                    t = min(b - epsilon, end.y())
                if "b" in mode:
                    b = max(t + epsilon, end.y())
                self._area = (l, t, r, b)
        self.update()
        event.accept()

    def mouseReleaseEvent(self, event):
        if self._drag:
            self.mouseMoveEvent(event)
            mode, start, original = self._drag
            self._drag = None
            if mode != "pan" and self._area is not None and (self._area != original or mode == "draw" and self._drawn):
                self.area_changed.emit(self._area, "draw" if mode == "draw" else "edit")
            self.unsetCursor()
        event.accept()

    def wheelEvent(self, event):
        if self._image.isNull():
            return
        pos = event.position()
        factor = 1.2 ** (event.angleDelta().y() / 120)
        scale = min(100.0, max(0.005, self._scale * factor))
        self._offset = pos - (pos - self._offset) * (scale / self._scale)
        self._scale = scale
        self._fitted = False
        self.update()
        event.accept()

    def _nudge(self, key, modifiers):
        if self._area is None or self._image.isNull():
            return
        rect = self.image_rect()
        if rect.width() <= 0 or rect.height() <= 0:
            return
        sx, sy = self._ARROWS[key]
        factor = 10 if modifiers & Qt.KeyboardModifier.ShiftModifier else 1
        dx = sx * factor / rect.width()
        dy = sy * factor / rect.height()
        resize = bool(modifiers & Qt.KeyboardModifier.ControlModifier)
        new_area = nudge_box(self._area, dx, dy, resize=resize)
        if new_area != self._area:
            self._area = new_area
            self.update()
            self.area_changed.emit(new_area, "nudge")

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key.Key_Space:
            self._space = True
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            event.accept()
        elif key == Qt.Key.Key_Escape:
            if self._drag and self._drag[0] != "pan":
                _mode, _start, original = self._drag
                self._area = original
                self._drag = None
                self._drawn = False
                self.update()
            elif self._suggestion is not None:
                self.suggestion_dismissed.emit()
            event.accept()
        elif key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.clear_requested.emit()
            event.accept()
        elif key in (Qt.Key.Key_Enter, Qt.Key.Key_Return):
            self.confirm_requested.emit()
            event.accept()
        elif key in self._ARROWS:
            self._nudge(key, event.modifiers())
            event.accept()
        else:
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key.Key_Space:
            self._space = False
            self.unsetCursor()
            event.accept()
        else:
            super().keyReleaseEvent(event)

    def focusOutEvent(self, event):
        self._space = False
        self._drag = None
        super().focusOutEvent(event)


CARD_W = 132
CARD_H = 112
CARD_GAP = 8
CARD_MARGIN = 8
THUMB_PAD = 6
THUMB_H = 84
ACCEPT_W = 60
THUMB_MAX = 240
NEEDS_AMBER = "#D97706"


def _star_path(cx, cy, outer, inner):
    path = QPainterPath()
    for i in range(10):
        radius = outer if i % 2 == 0 else inner
        angle = -math.pi / 2 + i * math.pi / 5
        point = QPointF(cx + radius * math.cos(angle), cy + radius * math.sin(angle))
        path.moveTo(point) if i == 0 else path.lineTo(point)
    path.closeSubpath()
    return path


def _check_path(cx, cy, size):
    path = QPainterPath()
    path.moveTo(QPointF(cx - size * 0.45, cy))
    path.lineTo(QPointF(cx - size * 0.1, cy + size * 0.35))
    path.lineTo(QPointF(cx + size * 0.5, cy - size * 0.4))
    return path


class ProgressRing(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(30, 30)
        self._fraction = 0.0
        self._text = "0/0"
        self._danger = False
        self._accent = QColor(get_tokens(LIGHT)["accent"])
        self._danger_color = QColor(get_tokens(LIGHT)["danger"])

    def set_state(self, fraction, text, danger, tokens):
        self._fraction = fraction
        self._text = text
        self._danger = danger
        self._accent = QColor(tokens["accent"])
        self._danger_color = QColor(tokens["danger"])
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(3, 3, -3, -3)
        pen = QPen(self.palette().color(QPalette.ColorRole.Mid), 3)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(rect)
        arc_color = self._danger_color if self._danger else self._accent
        painter.setPen(QPen(arc_color, 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        if self._fraction > 0:
            painter.drawArc(rect, 90 * 16, -int(self._fraction * 360 * 16))
        font = QFont(self.font())
        font.setPixelSize(10)
        painter.setFont(font)
        painter.setPen(self.palette().color(QPalette.ColorRole.Text))
        painter.drawText(self.rect(), int(Qt.AlignmentFlag.AlignCenter), self._text)


class _ChipEditor(QLineEdit):
    committed = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._done = False

    def begin(self, text):
        self._done = False
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


class GroupChipBar(QWidget):
    select_requested = pyqtSignal(str)
    rename_requested = pyqtSignal(str, str)
    delete_requested = pyqtSignal(str)
    restore_requested = pyqtSignal(str)
    create_requested = pyqtSignal()
    example_requested = pyqtSignal()

    CHIP_H = 26
    ROUND = 28

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFixedHeight(self.CHIP_H + 10)
        self._chips = []
        self._hover = None
        self._tokens = get_tokens(LIGHT)
        self._editor = _ChipEditor(self)
        self._editor.hide()
        self._editor.committed.connect(self._commit_rename)
        self._editor.cancelled.connect(self._editor.hide)
        self._edit_gid = None
        self._plus = None
        self._help = None
        self._rects = []

    def set_chips(self, chips, tokens):
        self._chips = chips
        self._tokens = tokens
        self.update()

    def _layout(self):
        fm = self.fontMetrics()
        x = 4.0
        y = 5.0
        out = []
        for chip in self._chips:
            text_w = fm.horizontalAdvance(chip["name"])
            width = 12 + 10 + 6 + text_w + 26
            rect = QRectF(x, y, width, self.CHIP_H)
            xrect = QRectF(rect.right() - 20, y + 5, 16, 16)
            out.append(("chip", chip["gid"], rect, xrect))
            x += width + 6
        self._plus = QRectF(x + 2, 5, self.ROUND, self.ROUND)
        out.append(("plus", None, self._plus, self._plus))
        self._help = QRectF(self.width() - self.ROUND - 4, 5, self.ROUND, self.ROUND)
        out.append(("help", None, self._help, self._help))
        return out

    def _hit(self, pos):
        for kind, gid, rect, xrect in self._layout():
            if kind == "chip" and rect.contains(pos):
                hovered = self._hover is not None and self._hover[0] == gid
                if hovered and xrect.contains(pos):
                    return ("x", gid)
                return ("chip", gid)
            if kind in ("plus", "help") and rect.contains(pos):
                return (kind, None)
        return (None, None)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        tokens = self._tokens
        pal = self.palette()
        text_color = pal.color(QPalette.ColorRole.Text)
        text_sec = QColor(tokens["text_sec"])
        accent = QColor(tokens["accent"])
        tint = token_color(tokens["accent_tint"])
        chips = {chip["gid"]: chip for chip in self._chips}
        for kind, gid, rect, xrect in self._layout():
            if kind == "chip":
                chip = chips[gid]
                painter.save()
                painter.setOpacity(0.5 if chip["removed"] else 1.0)
                painter.setPen(QPen(accent if chip["current"] else pal.color(QPalette.ColorRole.Mid), 1))
                painter.setBrush(QBrush(tint if chip["current"] else pal.color(QPalette.ColorRole.Base)))
                painter.drawRoundedRect(rect, 13, 13)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(QColor(chip["color"])))
                painter.drawEllipse(QRectF(rect.left() + 12, rect.center().y() - 5, 10, 10))
                font = QFont(self.font())
                font.setStrikeOut(chip["removed"] or chip["auto_removed"])
                painter.setFont(font)
                painter.setPen(text_color)
                chip_text = QFontMetrics(font).elidedText(chip["name"], Qt.TextElideMode.ElideRight,
                                                        int(rect.width() - 46))
                painter.drawText(QRectF(rect.left() + 28, rect.top(), rect.width() - 46, rect.height()),
                                 int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
                                 chip_text)
                if self._hover is not None and self._hover[0] == gid:
                    painter.setPen(QPen(text_sec, 1.4))
                    glyph = "\u21ba" if chip["removed"] else "\u00d7"
                    painter.setFont(self.font())
                    painter.drawText(xrect, int(Qt.AlignmentFlag.AlignCenter), glyph)
                painter.restore()
            elif kind == "plus":
                painter.setPen(QPen(accent, 1.4))
                painter.setBrush(QBrush(tint))
                painter.drawEllipse(rect)
                cx, cy = rect.center().x(), rect.center().y()
                painter.drawLine(QPointF(cx - 5, cy), QPointF(cx + 5, cy))
                painter.drawLine(QPointF(cx, cy - 5), QPointF(cx, cy + 5))
            elif kind == "help":
                painter.setPen(QPen(pal.color(QPalette.ColorRole.Mid), 1))
                painter.setBrush(QBrush(pal.color(QPalette.ColorRole.Base)))
                painter.drawEllipse(rect)
                painter.setPen(text_sec)
                painter.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), "?")
        painter.end()

    def mouseMoveEvent(self, event):
        kind, gid = self._hit(event.position())
        hover = (gid, kind) if gid is not None and kind in ("chip", "x") else None
        if hover != self._hover:
            self._hover = hover
            self.update()
        tip = ""
        if kind == "plus":
            tip = tr("plot_new_group_tooltip")
        elif kind == "x":
            tip = tr("plot_undo") if next(c for c in self._chips if c["gid"] == gid)["removed"] else tr("plot_delete_group")
        elif kind == "help":
            tip = tr("plot_example_tooltip")
        elif kind in ("chip", "x") and gid is not None:
            chip = next(c for c in self._chips if c["gid"] == gid)
            tip = chip["tooltip"]
        self.setToolTip(tip)
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self._hover = None
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        kind, gid = self._hit(event.position())
        if kind == "x":
            chip = next(c for c in self._chips if c["gid"] == gid)
            if chip["removed"]:
                self.restore_requested.emit(gid)
            else:
                self.delete_requested.emit(gid)
        elif kind == "chip":
            self.select_requested.emit(gid)
        elif kind == "plus":
            self.create_requested.emit()
        elif kind == "help":
            self.example_requested.emit()

    def mouseDoubleClickEvent(self, event):
        kind, gid = self._hit(event.position())
        if kind != "chip":
            return
        chip = next(c for c in self._chips if c["gid"] == gid)
        if chip["removed"] or chip["auto_removed"]:
            return
        rect = next(r for k, g, r, _x in self._layout() if k == "chip" and g == gid)
        self._edit_gid = gid
        self._editor.setGeometry(int(rect.left() + 26), int(rect.top() + 2),
                                 int(rect.width() - 46), int(rect.height() - 4))
        self._editor.begin(chip["name"])

    def _commit_rename(self, text):
        gid = self._edit_gid
        self._editor.hide()
        self._edit_gid = None
        if gid is not None:
            self.rename_requested.emit(gid, text)


class CardStrip(QWidget):
    card_clicked = pyqtSignal(str)
    check_clicked = pyqtSignal(str)
    star_clicked = pyqtSignal(str)
    row_clicked = pyqtSignal(str)
    accept_all_clicked = pyqtSignal()
    step_requested = pyqtSignal(int)

    def __init__(self, provider, parent=None):
        super().__init__(parent)
        self._provider = provider
        self._order = []
        self._current = None
        self._accept_count = 0
        self._hover = None
        self._tokens = get_tokens(LIGHT)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setFixedHeight(CARD_H + 2 * CARD_MARGIN)
        self._resize_to_content()

    def set_tokens(self, tokens):
        self._tokens = tokens
        self.update()

    def set_order(self, order, current):
        self._order = list(order)
        self._current = current
        self._resize_to_content()
        self.update()

    def set_current(self, cid):
        self._current = cid
        self.update()

    def set_accept_count(self, count):
        self._accept_count = count
        self._resize_to_content()
        self.update()

    def refresh(self):
        self.update()

    def current_index(self):
        return self._order.index(self._current) if self._current in self._order else -1

    def _resize_to_content(self):
        width = CARD_MARGIN * 2 + len(self._order) * (CARD_W + CARD_GAP)
        if self._accept_count:
            width += ACCEPT_W
        self.setFixedWidth(max(width, 1))

    def _card_rect(self, index):
        return QRectF(CARD_MARGIN + index * (CARD_W + CARD_GAP), CARD_MARGIN, CARD_W, CARD_H)

    def _accept_rect(self):
        x = CARD_MARGIN + len(self._order) * (CARD_W + CARD_GAP) + 6
        return QRectF(x, CARD_MARGIN + CARD_H / 2 - 22, 44, 44)

    @staticmethod
    def _parts(rect):
        thumb = QRectF(rect.x() + THUMB_PAD, rect.y() + THUMB_PAD, rect.width() - 2 * THUMB_PAD, THUMB_H)
        return {
            "thumb": thumb,
            "check": QRectF(rect.right() - 6 - 22, rect.y() + 6, 22, 22),
            "star": QRectF(rect.x() + 6, rect.y() + 6, 18, 18),
            "row": QRectF(thumb.x() + 4, thumb.bottom() - 18, 22, 16),
            "status": QRectF(thumb.right() - 12, thumb.bottom() - 12, 8, 8),
            "caption": QRectF(rect.x() + 6, thumb.bottom() + 4, rect.width() - 12, 14),
        }

    def _hit(self, pos):
        if self._accept_count and self._accept_rect().contains(pos):
            return "accept", None
        for index, cid in enumerate(self._order):
            rect = self._card_rect(index)
            if not rect.contains(pos):
                continue
            parts = self._parts(rect)
            for part in ("check", "star", "row"):
                if parts[part].contains(pos):
                    return part, cid
            return "card", cid
        return None, None

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        for index, cid in enumerate(self._order):
            self._paint_card(painter, self._card_rect(index), cid, self._provider(cid))
        if self._accept_count:
            self._paint_accept(painter)
        painter.end()

    def _paint_card(self, p, rect, cid, st):
        pal = self.palette()
        tokens = self._tokens
        group_color = QColor(st["group_color"] or tokens["accent"])
        member = st["member"]
        p.save()
        p.setOpacity(1.0 if member else 0.55)
        current = cid == self._current
        border = QPen(QColor(tokens["accent"]), 2) if current else QPen(pal.color(QPalette.ColorRole.Mid), 1)
        p.setPen(border)
        p.setBrush(QBrush(pal.color(QPalette.ColorRole.Base)))
        p.drawRoundedRect(rect, 8, 8)
        parts = self._parts(rect)
        thumb = parts["thumb"]
        p.save()
        p.setClipRect(thumb)
        image_rect = thumb
        image = st["thumb"]
        if image is not None and not image.isNull():
            scale = min(thumb.width() / image.width(), thumb.height() / image.height())
            w, h = image.width() * scale, image.height() * scale
            image_rect = QRectF(thumb.center().x() - w / 2, thumb.center().y() - h / 2, w, h)
            p.drawImage(image_rect, image)
        if st["area"] is not None:
            a = st["area"]
            box = QRectF(image_rect.left() + a[0] * image_rect.width(), image_rect.top() + a[1] * image_rect.height(),
                         (a[2] - a[0]) * image_rect.width(), (a[3] - a[1]) * image_rect.height())
            fill = QColor(group_color)
            fill.setAlpha(31)
            p.setPen(QPen(group_color, 1.5))
            p.setBrush(QBrush(fill))
            p.drawRect(box)
        elif st["suggestion"] is not None:
            a = st["suggestion"]
            box = QRectF(image_rect.left() + a[0] * image_rect.width(), image_rect.top() + a[1] * image_rect.height(),
                         (a[2] - a[0]) * image_rect.width(), (a[3] - a[1]) * image_rect.height())
            p.setPen(QPen(QColor(tokens["accent"]), 1.4, Qt.PenStyle.DashLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(box)
        p.restore()
        check = parts["check"]
        if member:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(group_color))
            p.drawEllipse(check)
            p.setPen(QPen(QColor("#FFFFFF"), 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(_check_path(check.center().x(), check.center().y(), 11))
        else:
            ring = QColor(st["other_color"]) if st["other_color"] else pal.color(QPalette.ColorRole.Mid)
            p.setPen(QPen(ring, 1.5))
            p.setBrush(QBrush(pal.color(QPalette.ColorRole.Base)))
            p.drawEllipse(check)
        if member:
            star = parts["star"]
            if st["reference"]:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(QColor(tokens["accent"])))
                p.drawPath(_star_path(star.center().x(), star.center().y(), 8, 3.6))
            elif self._hover == ("star", cid):
                p.setPen(QPen(QColor(tokens["text_sec"]), 1.2))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawPath(_star_path(star.center().x(), star.center().y(), 8, 3.6))
        if st["row"] is not None:
            badge = parts["row"]
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(group_color))
            p.drawRoundedRect(badge, 4, 4)
            p.setPen(QColor("#FFFFFF"))
            p.drawText(badge, int(Qt.AlignmentFlag.AlignCenter), str(st["row"]))
        if st["status"] is not None:
            color = {"ok": tokens["success"], "needs": NEEDS_AMBER, "problem": tokens["danger"]}[st["status"]]
            p.setPen(QPen(pal.color(QPalette.ColorRole.Base), 1.2))
            p.setBrush(QBrush(QColor(color)))
            p.drawEllipse(parts["status"])
        font = QFont(self.font())
        font.setPixelSize(10)
        p.setFont(font)
        p.setPen(QColor(tokens["text_sec"]))
        caption = QFontMetrics(font).elidedText(st["caption"], Qt.TextElideMode.ElideMiddle,
                                                int(parts["caption"].width()))
        p.drawText(parts["caption"], int(Qt.AlignmentFlag.AlignCenter), caption)
        p.restore()

    def _paint_accept(self, p):
        rect = self._accept_rect()
        accent = QColor(self._tokens["accent"])
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(accent))
        p.drawEllipse(rect)
        cx, cy = rect.center().x(), rect.center().y()
        p.setPen(QPen(QColor("#FFFFFF"), 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(_check_path(cx - 4, cy, 12))
        p.drawPath(_check_path(cx + 5, cy, 12))
        badge = QRectF(rect.right() - 16, rect.top() - 2, 18, 18)
        p.setPen(QPen(QColor(self._tokens["danger"]), 1))
        p.setBrush(QBrush(QColor("#FFFFFF")))
        p.drawEllipse(badge)
        p.setPen(QColor(self._tokens["text"]))
        p.drawText(badge, int(Qt.AlignmentFlag.AlignCenter), str(self._accept_count))

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        kind, cid = self._hit(event.position())
        if kind == "check":
            self.check_clicked.emit(cid)
        elif kind == "star":
            self.star_clicked.emit(cid)
        elif kind == "row":
            self.row_clicked.emit(cid)
        elif kind == "card":
            self.card_clicked.emit(cid)
        elif kind == "accept":
            self.accept_all_clicked.emit()
        self.setFocus()

    def mouseMoveEvent(self, event):
        kind, cid = self._hit(event.position())
        hover = (kind, cid) if kind in ("star",) else None
        if hover != self._hover:
            self._hover = hover
            self.update()
        tip = ""
        if kind == "accept":
            tip = tr("plot_accept_all").format(count=self._accept_count)
        elif kind == "card" and cid is not None:
            tip = self._provider(cid)["tooltip"]
        elif kind == "check" and cid is not None:
            tip = self._provider(cid)["check_tip"]
        elif kind == "star" and cid is not None:
            tip = tr("plot_reference_star_tooltip") if self._provider(cid)["reference"] else tr("plot_star_tooltip")
        elif kind == "row" and cid is not None:
            tip = self._provider(cid)["row_tip"]
        self.setToolTip(tip)
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self._hover = None
        self.update()
        super().leaveEvent(event)

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key.Key_Left:
            self.step_requested.emit(-1)
        elif key == Qt.Key.Key_Right:
            self.step_requested.emit(1)
        elif key == Qt.Key.Key_Space and self._current is not None:
            self.check_clicked.emit(self._current)
        elif key == Qt.Key.Key_S and self._current is not None:
            self.star_clicked.emit(self._current)
        else:
            super().keyPressEvent(event)


class _MarkerFrame(QWidget):
    def __init__(self, view, parent=None):
        super().__init__(parent)
        self.view = view
        view.setParent(self)
        self.prev_button = self._round(36, "\u2039", tr("plot_prev_panel"))
        self.next_button = self._round(36, "\u203a", tr("plot_next_panel"))
        self.accept_button = self._round(44, "\u2713", tr("plot_use_suggestion"))
        self.accept_button.setObjectName("plotAcceptSuggestion")
        self.accept_button.setProperty("accent", True)
        self.fit_button = self._round(28, "\u2922", tr("plot_fit_view_tooltip"))
        self.clear_button = self._round(28, "\u2715", tr("plot_clear"))
        self.accept_button.hide()

    @staticmethod
    def _round(size, text, tip):
        button = QToolButton()
        button.setText(text)
        button.setToolTip(tip)
        button.setAccessibleName(tip)
        button.setFixedSize(size, size)
        button.setStyleSheet(f"QToolButton {{ border-radius: {size // 2}px; }}")
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        return button

    def resizeEvent(self, event):
        w, h = self.width(), self.height()
        self.view.setGeometry(0, 0, w, h)
        self.prev_button.move(6, (h - 36) // 2)
        self.next_button.move(w - 42, (h - 36) // 2)
        self.accept_button.move((w - 44) // 2, h - 56)
        self.fit_button.move(w - 34, 6)
        self.clear_button.move(w - 66, 6)
        super().resizeEvent(event)


class PlotAlignmentDialog(QDialog):
    _VIEW_MODES = ("source", "preview", "both")
    _NO_GROUP = PlotAlignmentGroup(id="", name="", cell_ids=[], reference_id="")

    def __init__(self, project, selected_ids=None, parent=None):
        super().__init__(parent)
        self.project = project
        self.setObjectName("plotAlignmentDialog")
        self.setWindowTitle(tr("action_align_plots"))
        QShortcut(QKeySequence(Qt.Key.Key_F1), self, activated=lambda: show_context_help(self, "align_plots"))
        self.resize(1100, 720)
        self.setMinimumSize(820, 560)
        self._loading = True
        self._cells = {c.id: c for c in project.get_all_leaf_cells() if c.image_path and not c.is_placeholder}
        self._areas = {cid: copy.deepcopy(c.plot_area) for cid, c in self._cells.items()}
        self._drafts = {g.id: copy.deepcopy(g) for g in project.plot_alignment_groups}
        self._group_order = [g.id for g in project.plot_alignment_groups]
        self._originals = {g.id: self._signature(g) for g in project.plot_alignment_groups}
        self._removed = set()
        self._auto_removed = set()
        self._moved = {}
        self._spans_notice = ""
        self._selected_ids = [cid for cid in dict.fromkeys(selected_ids or []) if cid in self._cells]
        self._new_ids = set()
        self._suggested_rows = self._suggest_rows()
        self._current_group_id = None
        self._current_cell_id = None
        self._loaded_digest = ""
        self._image_cache = OrderedDict()
        self._thumb_cache = OrderedDict()
        self._suggestion_cache = {}
        self._dismissed_suggestions = set()
        self._current_suggestion = None
        self._cell_issues = {}
        self._card_order = []
        self._history = MarkHistory()
        self._preview_overlays = []
        self._status_text = ""
        self._status_tooltip = ""
        self._tokens = get_tokens(self._theme_name())
        self.plot_areas = {}
        self.alignment_groups = copy.deepcopy(project.plot_alignment_groups)
        self._build_ui()
        groups = [(gid, list(self._drafts[gid].cell_ids)) for gid in self._group_order]
        decision = plan_initial_group(self._selected_ids, groups, set(self._cells))
        if decision[0] == "open":
            first, unassigned = decision[1], decision[2]
            owners = [gid for gid in self._group_order if set(self._drafts[gid].cell_ids).intersection(self._selected_ids)]
            if len(owners) > 1:
                self._spans_notice = tr("plot_selection_spans").format(count=len(owners), name=self._drafts[first].name)
            group = self._drafts[first]
            for cid in unassigned:
                group.cell_ids.append(cid)
                group.row_groups.setdefault(cid, self._suggested_rows.get(cid, 1))
            start = first
        elif decision[0] == "create":
            ids = decision[1]
            start = self._create_group(self._default_group_name())
            group = self._drafts[start]
            group.cell_ids = list(ids)
            group.reference_id = ids[0]
            for cid in ids:
                group.row_groups.setdefault(cid, self._suggested_rows.get(cid, 1))
        else:
            start = None
        self._select_group(start)
        self._initialized = True

    # ── small helpers ────────────────────────────────────────────────────

    def _theme_name(self):
        parent = self.parent()
        if parent is not None and hasattr(parent, "_current_theme"):
            return parent._current_theme
        return LIGHT

    def _group(self):
        return self._drafts.get(self._current_group_id, self._NO_GROUP)

    def _default_group_name(self):
        n = len(self._group_order) + 1
        names = {g.name for g in self._drafts.values()}
        while tr("plot_group_name").format(n=n) in names:
            n += 1
        return tr("plot_group_name").format(n=n)

    def _create_group(self, name):
        gid = str(uuid.uuid4())
        self._drafts[gid] = PlotAlignmentGroup(
            id=gid, name=name, cell_ids=[], reference_id="",
            baseline_mode="custom" if self.project.layout_mode == "freeform" else "grid_rows")
        self._group_order.append(gid)
        self._new_ids.add(gid)
        return gid

    def _group_index(self, gid):
        return self._group_order.index(gid) if gid in self._group_order else 0

    @staticmethod
    def _signature(group):
        rows = {cid: group.row_groups.get(cid) for cid in group.cell_ids} if group.baseline_mode == "custom" else None
        return (group.name, list(group.cell_ids), group.reference_id, group.sizing_mode, group.baseline_mode, rows)

    def _dropped(self):
        return self._removed | self._auto_removed

    def _owner_of(self, cid, exclude=None):
        return next((gid for gid in self._group_order
                     if gid != exclude and gid not in self._removed and cid in self._drafts[gid].cell_ids), None)

    def _changed_group_ids(self):
        return [gid for gid in self._group_order
                if (gid in self._new_ids and self._drafts[gid].cell_ids and gid not in self._dropped())
                or (gid not in self._new_ids and (gid in self._dropped() or self._signature(self._drafts[gid]) != self._originals[gid]))]

    def _panel_label(self, cid):
        cell = self._cells.get(cid)
        if cell is None:
            return tr("plot_missing_panel").format(id=cid[:8])
        parent = self.parent()
        if parent and hasattr(parent, "_cell_path_label"):
            address = parent._cell_path_label(cell)
        else:
            segments = []
            root = cell
            ancestor = self.project.find_parent_of(root.id)
            while ancestor:
                segments.insert(0, str(ancestor.children.index(root) + 1))
                root = ancestor
                ancestor = self.project.find_parent_of(root.id)
            address = f"R{root.row_index + 1}C{root.col_index + 1}" + (" › " + " › ".join(segments) if segments else "")
        return os.path.basename(cell.image_path) + " · " + address

    def _suggest_rows(self):
        layout = LayoutEngine.calculate_layout(copy.deepcopy(self.project))
        self._layout_rects = dict(layout.cell_rects)
        rows = {}
        anchors = []
        for cid, rect in sorted(layout.cell_rects.items(), key=lambda pair: pair[1][1]):
            if cid not in self._cells:
                continue
            y, h = rect[1], rect[3]
            row = next((i for i, (ay, ah) in enumerate(anchors) if abs(y - ay) <= max(1, min(h, ah) * 0.25)), None)
            if row is None:
                row = len(anchors)
                anchors.append((y, h))
            rows[cid] = row + 1
        return rows

    @staticmethod
    def _invalid_rows(group):
        return group.baseline_mode == "custom" and any(type(group.row_groups.get(cid)) is not int or group.row_groups[cid] < 0 for cid in group.cell_ids)

    # ── layout ───────────────────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self.chip_bar = GroupChipBar()
        self.chip_bar.setAccessibleName(tr("plot_group"))
        self.chip_bar.select_requested.connect(self._select_group)
        self.chip_bar.rename_requested.connect(self._rename_group)
        self.chip_bar.delete_requested.connect(self._on_delete_group)
        self.chip_bar.restore_requested.connect(self._restore_group)
        self.chip_bar.create_requested.connect(self._new_group)
        self.chip_bar.example_requested.connect(self._open_example)
        layout.addWidget(self.chip_bar)

        self.cards = CardStrip(self._card_state)
        self.cards.card_clicked.connect(self._show_cid)
        self.cards.check_clicked.connect(self._toggle_member)
        self.cards.star_clicked.connect(self._set_reference)
        self.cards.row_clicked.connect(self._cycle_row)
        self.cards.accept_all_clicked.connect(self._accept_all_suggestions)
        self.cards.step_requested.connect(self._step_card)
        self.cards.setAccessibleName(tr("plot_panel"))
        self.card_scroll = QScrollArea()
        self.card_scroll.setWidget(self.cards)
        self.card_scroll.setWidgetResizable(False)
        self.card_scroll.setFixedHeight(CARD_H + 2 * CARD_MARGIN + 16)
        self.card_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.card_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.card_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        layout.addWidget(self.card_scroll)

        self.split = QSplitter(Qt.Orientation.Horizontal)
        self.source_view = PlotAreaView()
        self.source_view.setAccessibleName(tr("plot_source"))
        self.marker = _MarkerFrame(self.source_view)
        self.marker.prev_button.clicked.connect(lambda: self._step_member(-1))
        self.marker.next_button.clicked.connect(lambda: self._step_member(1))
        self.marker.accept_button.clicked.connect(lambda *_: self._accept_current_suggestion())
        self.marker.fit_button.clicked.connect(lambda *_: self.source_view.fit_view())
        self.marker.clear_button.clicked.connect(lambda *_: self._clear_area())
        self.marker.setMinimumWidth(320)
        self.split.addWidget(self.marker)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)
        self.preview_title = QLabel(tr("plot_preview_title"))
        right_layout.addWidget(self.preview_title)
        self.preview_scene = CanvasScene(self)
        self.preview_view = CanvasView(self.preview_scene)
        self.preview_view.setInteractive(False)
        self.preview_view.setAcceptDrops(False)
        self.preview_view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.preview_view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        right_layout.addWidget(self.preview_view, 1)
        controls = QGridLayout()
        controls.setHorizontalSpacing(10)
        controls.setVerticalSpacing(6)
        size_label_row = QHBoxLayout()
        size_label_row.setContentsMargins(0, 0, 0, 0)
        size_label_row.addWidget(QLabel(tr("plot_size_label")), 0,
                                 Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.fit_dot = QToolButton()
        self.fit_dot.setFixedSize(12, 12)
        self.fit_dot.setStyleSheet("QToolButton { border: none; border-radius: 6px; background: " + NEEDS_AMBER + "; }")
        self.fit_dot.setToolTip(tr("plot_fit_plots_tooltip"))
        self.fit_dot.setAccessibleName(tr("plot_fit_plots"))
        self.fit_dot.clicked.connect(lambda *_: self._fit_plots_within_cells())
        self.fit_dot.hide()
        size_label_row.addWidget(self.fit_dot)
        size_label_row.addStretch()
        controls.addLayout(size_label_row, 0, 0)
        self.sizing_combo = PictogramCombo(["size_exact", "size_fit"])
        self.sizing_combo.addItem(tr("plot_exact"), "reference")
        self.sizing_combo.addItem(tr("plot_fit"), "fit")
        self.sizing_combo.setAccessibleName(tr("plot_size_label"))
        controls.addWidget(self.sizing_combo, 0, 1)
        controls.addWidget(QLabel(tr("plot_baseline_label")), 1, 0,
                           Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.baseline_combo = PictogramCombo(["baseline_rows", "baseline_single", "baseline_custom"])
        for key, mode in (("plot_grid_rows", "grid_rows"), ("plot_single", "single"), ("plot_custom", "custom")):
            self.baseline_combo.addItem(tr(key), mode)
        self.baseline_combo.setAccessibleName(tr("plot_baseline_label"))
        controls.addWidget(self.baseline_combo, 1, 1)
        controls.setColumnStretch(1, 1)
        right_layout.addLayout(controls)
        self.split.addWidget(right)
        self.split.setStretchFactor(0, 3)
        self.split.setStretchFactor(1, 2)
        self.split.setChildrenCollapsible(False)
        right.setMinimumWidth(280)
        self.split.setSizes([640, 420])
        layout.addWidget(self.split, 1)

        footer = QHBoxLayout()
        self.ring = ProgressRing()
        footer.addWidget(self.ring)
        footer.addSpacing(8)
        self.toast = QFrame()
        self.toast.setObjectName("plotToast")
        toast_layout = QHBoxLayout(self.toast)
        toast_layout.setContentsMargins(8, 2, 6, 2)
        self.toast_label = QLabel("")
        toast_layout.addWidget(self.toast_label)
        self.toast_undo = QToolButton()
        self.toast_undo.setText(tr("plot_undo"))
        self.toast_undo.clicked.connect(lambda *_: self._undo_last_delete())
        toast_layout.addWidget(self.toast_undo)
        self.toast.hide()
        self._toast_timer = QTimer(self)
        self._toast_timer.setSingleShot(True)
        self._toast_timer.timeout.connect(self.toast.hide)
        self._deleted_group = None
        footer.addWidget(self.toast, 1)
        footer.addStretch()
        self.buttons = QDialogButtonBox()
        self.apply_button = self.buttons.addButton(tr("plot_apply"), QDialogButtonBox.ButtonRole.AcceptRole)
        self.apply_button.setProperty("accent", True)
        self.apply_button.style().unpolish(self.apply_button)
        self.apply_button.style().polish(self.apply_button)
        self.buttons.addButton(tr("plot_cancel"), QDialogButtonBox.ButtonRole.RejectRole)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        footer.addWidget(self.buttons)
        layout.addLayout(footer)

        self._build_example_popup()
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(120)
        self._preview_timer.timeout.connect(self._render_preview)
        self._preview_fit_timer = QTimer(self)
        self._preview_fit_timer.setSingleShot(True)
        self._preview_fit_timer.setInterval(0)
        self._preview_fit_timer.timeout.connect(self._fit_preview)
        self.preview_view.installEventFilter(self)
        self.split.splitterMoved.connect(lambda *_: self._fit_preview())

        self.sizing_combo.currentIndexChanged.connect(self._on_modes_changed)
        self.baseline_combo.currentIndexChanged.connect(self._on_modes_changed)
        self.source_view.area_changed.connect(self._area_changed)
        self.source_view.clear_requested.connect(self._clear_area)
        self.source_view.confirm_requested.connect(self._advance)
        self.source_view.suggestion_dismissed.connect(self._dismiss_suggestion)
        for sequence, handler in (("Ctrl+Z", self._undo), ("Ctrl+Shift+Z", self._redo), ("Ctrl+Y", self._redo)):
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.activated.connect(handler)
        for button in self.findChildren(QPushButton):
            button.setAutoDefault(False)
        self.setTabOrder(self.cards, self.apply_button)

    def _build_example_popup(self):
        self.example_dialog = QDialog(self)
        self.example_dialog.setAttribute(Qt.WidgetAttribute.WA_WindowPropagation, True)
        self.example_dialog.setWindowTitle(tr("plot_example_tooltip"))
        self.example_dialog.resize(700, 380)
        self.example_dialog.setMinimumSize(560, 300)
        example_layout = QVBoxLayout(self.example_dialog)
        self.example_tabs = QTabWidget()
        for mode, key in (("mark", "plot_example_mark"), ("alignment", "plot_example_alignment")):
            self.example_tabs.addTab(PlotGuideIllustration(mode), tr(key))
        example_layout.addWidget(self.example_tabs, 1)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.button(QDialogButtonBox.StandardButton.Close).setText(tr("btn_close"))
        close.button(QDialogButtonBox.StandardButton.Close).setAutoDefault(False)
        close.rejected.connect(self.example_dialog.close)
        example_layout.addWidget(close)

    def _open_example(self):
        self.example_dialog.show()
        self.example_dialog.raise_()
        self.example_dialog.activateWindow()
        self.example_tabs.setFocus()

    def done(self, result):
        self.example_dialog.close()
        super().done(result)

    # ── groups ───────────────────────────────────────────────────────────

    def _chip_states(self):
        chips = []
        for index, gid in enumerate(self._group_order):
            group = self._drafts[gid]
            removed = gid in self._removed
            auto = gid in self._auto_removed
            if removed:
                tip = tr("plot_banner_deleted").format(name=group.name)
            elif auto:
                tip = tr("plot_banner_auto_removed").format(name=group.name)
            else:
                tip = group.name
            chips.append({"gid": gid, "name": group.name, "color": group_color(index),
                          "current": gid == self._current_group_id, "removed": removed,
                          "auto_removed": auto, "tooltip": tip})
        return chips

    def _select_group(self, gid):
        self._current_group_id = gid if gid in self._drafts else None
        group = self._group()
        all_ids = list(self._cells)
        all_ids.extend(cid for cid in group.cell_ids if cid not in all_ids)
        members = list(group.cell_ids) if self._current_group_id else []
        self._card_order = card_order(all_ids, members)
        self._loading = True
        self.sizing_combo.setCurrentIndex(self.sizing_combo.findData(group.sizing_mode))
        self.baseline_combo.setCurrentIndex(self.baseline_combo.findData(group.baseline_mode))
        self._loading = False
        first = next((cid for cid in self._card_order if cid in members and cid in self._cells), None)
        if self._current_cell_id not in members:
            self._current_cell_id = None
        self.cards.set_order(self._card_order, self._current_cell_id)
        self._show_cid(self._current_cell_id or first)
        self._refresh_enabled()
        self._validate()

    def _refresh_enabled(self):
        group = self._current_group_id
        removed = group in self._removed
        has = group is not None
        self.cards.setEnabled(not removed)
        self.sizing_combo.setEnabled(has and not removed)
        self.baseline_combo.setEnabled(has and not removed)

    def _new_group(self):
        gid = self._create_group(self._default_group_name())
        self._select_group(gid)
        self.cards.setFocus()

    def _rename_group(self, gid, text):
        name = text.strip()
        if gid in self._drafts and name:
            self._drafts[gid].name = name
        self._validate()

    def _on_delete_group(self, gid):
        if gid not in self._drafts:
            return
        if gid in self._new_ids and gid not in self._auto_removed:
            self._delete_new_group(gid)
            return
        self._removed.add(gid)
        self._deleted_group = gid
        self.toast_label.setText(tr("plot_toast_deleted").format(name=self._drafts[gid].name))
        self.toast.show()
        self._toast_timer.start(6000)
        if self._current_group_id == gid:
            self._refresh_enabled()
        self._validate()

    def _restore_group(self, gid):
        self._removed.discard(gid)
        if self._deleted_group == gid:
            self._deleted_group = None
            self.toast.hide()
        self._refresh_enabled()
        self._validate()

    def _undo_last_delete(self):
        if self._deleted_group is not None:
            self._restore_group(self._deleted_group)

    def _delete_new_group(self, gid):
        group = self._drafts[gid]
        for cid in list(self._moved):
            if cid in group.cell_ids:
                self._restore_member(cid)
        self._group_order.remove(gid)
        self._new_ids.discard(gid)
        self._auto_removed.discard(gid)
        del self._drafts[gid]
        next_gid = self._group_order[0] if self._group_order else None
        self._select_group(next_gid if self._current_group_id == gid or self._current_group_id is None else self._current_group_id)

    def _on_modes_changed(self, *_):
        if self._loading or self._current_group_id is None:
            return
        group = self._group()
        group.sizing_mode = self.sizing_combo.currentData() or "reference"
        group.baseline_mode = self.baseline_combo.currentData() or "grid_rows"
        if group.baseline_mode == "custom":
            for cid in group.cell_ids:
                group.row_groups.setdefault(cid, self._suggested_rows.get(cid, 1))
        self._validate()

    # ── membership ───────────────────────────────────────────────────────

    def _toggle_member(self, cid):
        if cid not in self._cells:
            return
        if self._current_group_id is None:
            gid = self._create_group(self._default_group_name())
            group = self._drafts[gid]
            group.cell_ids = [cid]
            group.reference_id = cid
            group.row_groups[cid] = self._suggested_rows.get(cid, 1)
            self._select_group(gid)
            return
        group = self._group()
        members = list(group.cell_ids)
        new = [c for c in members if c != cid] if cid in members else members + [cid]
        self._apply_membership_moves(new)
        group.cell_ids = new
        if cid in new:
            group.row_groups.setdefault(cid, self._suggested_rows.get(cid, 1))
        else:
            group.row_groups.pop(cid, None)
        self._update_references()
        self._validate()

    def _update_references(self):
        if self._current_group_id is None:
            return
        group = self._group()
        checked = [cid for cid in group.cell_ids if cid in self._cells]
        if group.reference_id not in checked:
            group.reference_id = checked[0] if checked else ""

    def _set_reference(self, cid):
        if self._current_group_id is None or cid not in self._group().cell_ids:
            return
        self._group().reference_id = cid
        self._validate()

    def _cycle_row(self, cid):
        if self._current_group_id is None or cid not in self._group().cell_ids:
            return
        group = self._group()
        group.row_groups[cid] = cycle_row(group.row_groups.get(cid, 1), len(group.cell_ids))
        self._validate()

    def _apply_membership_moves(self, checked):
        """Checking a panel owned by another alignment moves it here (a panel
        belongs to one group only); unchecking a moved panel puts it back."""
        group = self._drafts[self._current_group_id]
        for cid in checked:
            if cid in group.cell_ids:
                continue
            owner = self._owner_of(cid, exclude=self._current_group_id)
            if owner is None:
                continue
            donor = self._drafts[owner]
            self._moved[cid] = (owner, donor.cell_ids.index(cid), donor.row_groups.get(cid))
            donor.cell_ids.remove(cid)
            donor.row_groups.pop(cid, None)
            if len(donor.cell_ids) < 2:
                self._auto_removed.add(owner)
        for cid in list(self._moved):
            if cid in checked or cid not in group.cell_ids:
                continue
            self._restore_member(cid)

    def _restore_member(self, cid):
        owner, index, row = self._moved.pop(cid)
        donor = self._drafts[owner]
        if cid not in donor.cell_ids:
            donor.cell_ids.insert(min(index, len(donor.cell_ids)), cid)
            if row is not None:
                donor.row_groups[cid] = row
        if len(donor.cell_ids) >= 2:
            self._auto_removed.discard(owner)

    def _member_order(self):
        members = set(self._group().cell_ids) if self._current_group_id else set()
        return [cid for cid in self._card_order if cid in members and cid in self._cells]

    def _step_member(self, delta):
        order = self._member_order()
        if not order:
            return
        if self._current_cell_id in order:
            index = (order.index(self._current_cell_id) + delta) % len(order)
        else:
            index = 0
        self._show_cid(order[index])

    def _step_card(self, delta):
        if not self._card_order:
            return
        index = self._card_order.index(self._current_cell_id) if self._current_cell_id in self._card_order else -1
        self._show_cid(self._card_order[(index + delta) % len(self._card_order)])

    # ── marking ──────────────────────────────────────────────────────────

    def _show_cid(self, cid):
        if cid is not None and cid not in self._cells:
            cid = None
        self._current_cell_id = cid
        cell = self._cells.get(cid)
        self.source_view.set_image(None)
        self._loaded_digest = ""
        if cell:
            try:
                digest = source_digest(cell.image_path)
                image = self._load_image(cell, digest)
                self.source_view.set_image(image)
                self._loaded_digest = digest if not image.isNull() else ""
                self.source_view.set_area(self._areas.get(cell.id))
                self.source_view.set_crop((cell.crop_left, cell.crop_top, cell.crop_right, cell.crop_bottom))
            except Exception:
                self._loaded_digest = ""
        self.source_view.setToolTip(tr("plot_rotation_hint").format(degrees=cell.rotation) if cell and cell.rotation else "")
        self.cards.set_current(cid)
        self._refresh_suggestion()
        self._update_marker_controls()
        self.cards.setAccessibleDescription(self._card_description(cid))
        self._refresh_footer_status()

    def _card_description(self, cid):
        if cid is None or cid not in self._cells:
            return ""
        return tr("plot_card_access").format(name=self._panel_label(cid), status=self._status_word(cid))

    def _status_word(self, cid):
        state = self._card_state(cid)
        key = {"ok": "plot_status_marked", "needs": "plot_status_needs_mark", "problem": "plot_needs_attention"}.get(state["status"])
        return tr(key) if key else tr("plot_status_none")

    def _update_marker_controls(self):
        members = self._member_order()
        many = len(members) > 1
        self.marker.prev_button.setEnabled(many)
        self.marker.next_button.setEnabled(many)
        self.marker.clear_button.setEnabled(bool(self._current_cell_id) and self._current_cell_id in self._areas)
        self.source_view.set_empty_hint(self._current_cell_id is not None and self._areas.get(self._current_cell_id) is None
                                        and self._current_suggestion is None)
        self.marker.accept_button.setVisible(self._current_suggestion is not None)

    def _load_image(self, cell, digest):
        key = (cell.image_path, digest)
        image = self._image_cache.get(key)
        if image is not None:
            self._image_cache.move_to_end(key)
            return image
        worker = ThumbnailWorker(cell.image_path, 2200, None)
        ext = os.path.splitext(cell.image_path)[1].lower()
        image = worker._load_svg() if ext == ".svg" else worker._load_pdf() if ext in (".pdf", ".eps") else worker._load_raster()
        self._image_cache[key] = image
        while len(self._image_cache) > 8:
            self._image_cache.popitem(last=False)
        return image

    def _thumbnail(self, cid):
        cell = self._cells.get(cid)
        if cell is None:
            return None
        try:
            digest = source_digest(cell.image_path)
        except Exception:
            return None
        key = (cell.image_path, digest)
        thumb = self._thumb_cache.get(key)
        if thumb is None:
            try:
                full = self._load_image(cell, digest)
            except Exception:
                return None
            if full.isNull():
                return None
            thumb = full.scaled(THUMB_MAX, THUMB_MAX, Qt.AspectRatioMode.KeepAspectRatio,
                                Qt.TransformationMode.SmoothTransformation)
            self._thumb_cache[key] = thumb
            while len(self._thumb_cache) > 48:
                self._thumb_cache.popitem(last=False)
        return thumb

    def _suggestion_for(self, cid):
        cell = self._cells.get(cid)
        if cell is None:
            return None
        try:
            digest = source_digest(cell.image_path)
        except Exception:
            return None
        key = (cell.image_path, digest)
        if key not in self._suggestion_cache:
            try:
                image = self._load_image(cell, digest)
            except Exception:
                image = None
            self._suggestion_cache[key] = suggest_plot_area(cell.image_path, image)
        return self._suggestion_cache[key]

    def _digest_of(self, cid):
        cell = self._cells.get(cid)
        try:
            return source_digest(cell.image_path) if cell else ""
        except Exception:
            return ""

    def _pending_suggestion(self, cid):
        if (cid, self._digest_of(cid)) in self._dismissed_suggestions:
            return None
        return self._suggestion_for(cid)

    def _suggestion_label(self, suggestion):
        return tr("plot_suggest_native") if suggestion.source == "native" else tr("plot_suggest_axes")

    def _refresh_suggestion(self):
        cid = self._current_cell_id
        self._current_suggestion = None
        if cid is not None and cid in self._cells and cid not in self._areas_marked() and self._loaded_digest:
            suggestion = self._pending_suggestion(cid)
            if suggestion is not None:
                self._current_suggestion = suggestion
        if self._current_suggestion is None:
            self.source_view.set_suggestion(None)
        else:
            self.source_view.set_suggestion(self._current_suggestion.box, self._suggestion_label(self._current_suggestion))

    def _areas_marked(self):
        return {cid for cid, area in self._areas.items() if area is not None}

    def _suggested_area(self, cid, suggestion):
        digest = source_digest(self._cells[cid].image_path)
        return PlotArea(*suggestion.box, source_digest=digest)

    def _accept_suggestion(self, cid, suggestion):
        old = copy.deepcopy(self._areas.get(cid))
        new = self._suggested_area(cid, suggestion)
        self._areas[cid] = new
        self._history.push([(cid, old, copy.deepcopy(new))])
        self._dismissed_suggestions.discard((cid, self._loaded_digest))
        self._validate()

    def _accept_current_suggestion(self):
        if self._current_suggestion is None or self._current_cell_id is None:
            return
        self._accept_suggestion(self._current_cell_id, self._current_suggestion)
        self._show_cid(self._current_cell_id)

    def _accept_all_suggestions(self):
        entries = []
        for cid in self._needs_mark_ids():
            suggestion = self._suggestion_for(cid)
            if suggestion is None or (cid, self._digest_of(cid)) in self._dismissed_suggestions:
                continue
            old = copy.deepcopy(self._areas.get(cid))
            new = self._suggested_area(cid, suggestion)
            self._areas[cid] = new
            entries.append((cid, old, copy.deepcopy(new)))
        if entries:
            self._history.push(entries)
            self._show_cid(self._current_cell_id)
            self._validate()

    def _dismiss_suggestion(self):
        if self._current_cell_id is None:
            return
        self._dismissed_suggestions.add((self._current_cell_id, self._loaded_digest))
        self._refresh_suggestion()
        self._validate()

    def _advance(self):
        cid = self._current_cell_id
        if cid is not None and cid in self._needs_mark_ids() and self._current_suggestion is not None:
            self._accept_current_suggestion()
        needed = set(self._needs_mark_ids())
        nxt = next_needed(self._member_order(), self._current_cell_id, needed)
        if nxt is not None:
            self._show_cid(nxt)

    def _area_changed(self, area, kind="edit"):
        cid = self._current_cell_id
        cell = self._cells.get(cid)
        if not cell:
            return
        try:
            digest = source_digest(cell.image_path)
        except Exception:
            digest = ""
        if not digest or digest != self._loaded_digest:
            self._show_cid(cid)
            self._validate()
            return
        old = copy.deepcopy(self._areas.get(cid))
        new = PlotArea(*area, source_digest=digest)
        self._areas[cid] = new
        self._history.push([(cid, old, copy.deepcopy(new))],
                           coalesce_key=("nudge", cid) if kind == "nudge" else None)
        self._validate()

    def _clear_area(self):
        cid = self._current_cell_id
        if cid is None or cid not in self._areas:
            return
        old = copy.deepcopy(self._areas.get(cid))
        if old is not None:
            self._history.push([(cid, old, None)])
        self._areas[cid] = None
        self.source_view.set_area(None)
        self._show_cid(cid)
        self._validate()

    def _apply_history(self, entries, restore_old):
        for cid, old, new in entries:
            self._areas[cid] = copy.deepcopy(old if restore_old else new)
        self._show_cid(entries[-1][0])
        self._validate()

    def _undo(self):
        entries = self._history.undo()
        if entries:
            self._apply_history(entries, restore_old=True)

    def _redo(self):
        entries = self._history.redo()
        if entries:
            self._apply_history(entries, restore_old=False)

    # ── per-card state ───────────────────────────────────────────────────

    def _card_state(self, cid):
        group = self._drafts.get(self._current_group_id)
        member = group is not None and cid in group.cell_ids
        owner = None if member else self._owner_of(cid, exclude=self._current_group_id)
        cell = self._cells.get(cid)
        missing = cell is None or not os.path.isfile(cell.image_path)
        area = self._areas.get(cid)
        has_area = area is not None
        suggestion = None if has_area or missing else self._pending_suggestion(cid)
        issues = self._cell_issues.get(cid, [])
        status = card_status(member, has_area, suggestion is not None, bool(issues) or missing)
        check_tip = tr("plot_check_remove") if member else (
            tr("plot_in_group").format(name=self._drafts[owner].name) if owner else tr("plot_check_add"))
        tooltip = self._panel_label(cid)
        if issues:
            tooltip += "\n" + alignment_issues_text(issues, self._candidate if hasattr(self, "_candidate") else self.project, 100)
        row = None
        if member and group.baseline_mode == "custom":
            value = group.row_groups.get(cid)
            row = value if type(value) is int else None
        basename = os.path.basename(cell.image_path) if cell else tr("plot_missing_panel").format(id=cid[:8])
        return {
            "member": member,
            "group_color": group_color(self._group_index(self._current_group_id)) if group else None,
            "other_color": group_color(self._group_index(owner)) if owner else None,
            "area": (area.left, area.top, area.right, area.bottom) if has_area else None,
            "suggestion": suggestion.box if suggestion is not None else None,
            "status": status,
            "reference": member and group.reference_id == cid,
            "row": row,
            "thumb": None if missing else self._thumbnail(cid),
            "caption": basename,
            "tooltip": tooltip,
            "check_tip": check_tip,
            "row_tip": tr("plot_row_badge").format(row=row) if row is not None else "",
        }

    # ── validation and footer ────────────────────────────────────────────

    def _validate(self):
        if not hasattr(self, "cards"):
            return False
        self._candidate = self.build_candidate()
        self._placement_result = resolve_image_placements(self._candidate, strict=False)
        issues = self._placement_result.issues
        group = self._group()
        has_group = self._current_group_id is not None
        removed = self._current_group_id in self._dropped()
        checked = list(group.cell_ids) if has_group else []
        missing = sum(self._areas.get(cid) is None for cid in checked if cid in self._cells)
        messages = []
        too_few_members = any(len(g.cell_ids) < 2 for g in self._candidate.plot_alignment_groups)
        if not has_group:
            if too_few_members:
                messages.append(tr("plot_need_two"))
        elif (not removed and len(checked) < 2) or too_few_members:
            messages.append(tr("plot_need_two"))
        elif not removed and missing:
            messages.append(tr("plot_need_marks").format(count=missing))
        invalid_rows = any(self._invalid_rows(g) for g in self._candidate.plot_alignment_groups)
        if invalid_rows:
            messages.append(tr("plot_issue_invalid_rows"))
        details = messages[:]
        if issues:
            details.append(alignment_issues_text(issues, self._candidate, 100))
        visible_issues = [i for i in issues if not ((missing or invalid_rows) and i.code == "invalid_area")]
        if visible_issues:
            messages.append(alignment_issues_text(visible_issues, self._candidate))
        active_issues = [i for i in issues if i.group_id or not i.cell_id]
        if has_group:
            valid = not active_issues and not invalid_rows and not too_few_members and (removed or (len(checked) >= 2 and not missing))
        else:
            valid = not active_issues and not invalid_rows and not too_few_members and bool(self._changed_group_ids())
        self._cell_issues = {}
        for issue in issues:
            if issue.cell_id:
                self._cell_issues.setdefault(issue.cell_id, []).append(issue)
        for gid in self._group_order:
            for cid in self._drafts[gid].cell_ids:
                for issue in issues:
                    if not issue.cell_id and issue.group_id == gid:
                        self._cell_issues.setdefault(cid, []).append(issue)
        can_fit = valid and self._can_fit_plots()
        self.fit_dot.setVisible(can_fit)
        self.apply_button.setEnabled(valid)
        needs_mark = self._needs_mark_ids()
        suggestable = [cid for cid in needs_mark if (cid, self._digest_of(cid)) not in self._dismissed_suggestions and self._suggestion_for(cid) is not None]
        self.cards.set_accept_count(len(suggestable))
        changed_ids = self._changed_group_ids()
        if not has_group:
            summary = tr("plot_no_groups_status")
        elif removed:
            summary = tr("plot_remove_note")
        elif valid and len(changed_ids) > 1:
            summary = tr("plot_apply_summary").format(count=len(changed_ids), names=", ".join(self._drafts[gid].name for gid in changed_ids))
        else:
            summary = tr("plot_valid")
        blocking = messages[0] if messages else summary
        marked = sum(self._areas.get(cid) is not None for cid in checked if cid in self._cells)
        fraction, text = progress(marked, len(checked))
        danger = bool(active_issues or invalid_rows) and not missing
        info = self._membership_notes()
        info += [tr("plot_issue_reduced_to_fit").format(
            name=next((g.name for g in self._candidate.plot_alignment_groups if g.id == notice.group_id), ""),
            height=f"{self._placement_result.group_heights.get(notice.group_id, 0):.2f}")
            for notice in self._placement_result.notices]
        details.extend(info)
        self._status_text = blocking
        self._status_tooltip = "\n".join(details) if details else blocking
        self._status_tooltip = "\n".join(([self._spans_notice] if self._spans_notice else []) + [self._status_tooltip])
        self.ring.set_state(fraction, text, danger, self._tokens)
        self.ring.setToolTip(self._status_tooltip)
        self.apply_button.setToolTip(self._status_tooltip)
        self.chip_bar.set_chips(self._chip_states(), self._tokens)
        self.cards.refresh()
        self._update_marker_controls()
        self._refresh_suggestion()
        self._refresh_footer_status()
        self._preview_timer.start()
        return valid

    def _refresh_footer_status(self):
        self.ring.setToolTip(self._status_tooltip)

    def _membership_notes(self):
        notes = []
        by_donor = {}
        for cid, (owner, _index, _row) in self._moved.items():
            by_donor.setdefault(owner, []).append(os.path.basename(self._cells[cid].image_path) if cid in self._cells else cid[:8])
        for owner, panels in by_donor.items():
            notes.append(tr("plot_moved_from").format(panels=", ".join(panels), name=self._drafts[owner].name))
        for gid in self._group_order:
            if gid in self._auto_removed:
                notes.append(tr("plot_auto_removed").format(name=self._drafts[gid].name))
        return notes

    def _repairable_mark_ids(self):
        needed = []
        issues = self._placement_result.issues
        for cid in self._group().cell_ids if self._current_group_id else []:
            cell = self._cells.get(cid)
            if cell is None or not os.path.isfile(cell.image_path) or any(i.cell_id == cid and i.code == "missing_source" for i in issues):
                continue
            area = self._areas.get(cid)
            invalid = area is None
            if area is not None:
                try:
                    area.to_dict()
                except (ValueError, TypeError, AttributeError):
                    invalid = True
            if invalid or any(i.cell_id == cid and i.code == "source_changed" for i in issues):
                needed.append(cid)
        return needed

    def _needs_mark_ids(self):
        if hasattr(self, "_placement_result"):
            return self._repairable_mark_ids()
        return [cid for cid in (self._group().cell_ids if self._current_group_id else []) if self._areas.get(cid) is None]

    def build_candidate(self):
        candidate = copy.deepcopy(self.project)
        for cid, area in self._areas.items():
            cell = candidate.find_cell_by_id(cid)
            if cell:
                cell.plot_area = copy.deepcopy(area)
        candidate.plot_alignment_groups = [
            copy.deepcopy(self._drafts[gid]) for gid in self._group_order
            if gid not in self._dropped() and (gid not in self._new_ids or self._drafts[gid].cell_ids)]
        return candidate

    def _can_fit_plots(self):
        """The current exact-reference group had to shrink so nothing is
        clipped; offer to make that explicit by switching it to fit sizing."""
        group = next((g for g in self._candidate.plot_alignment_groups if g.id == self._current_group_id), None)
        if group is None or group.sizing_mode != "reference":
            return False
        return any(notice.group_id == group.id for notice in self._placement_result.notices)

    def _fit_plots_within_cells(self):
        self._validate()
        if not self.apply_button.isEnabled():
            return
        self.sizing_combo.setCurrentIndex(self.sizing_combo.findData("fit"))

    # ── preview ──────────────────────────────────────────────────────────

    def _render_preview(self):
        if not hasattr(self, "_placement_result"):
            return
        for item in self._preview_overlays:
            self.preview_scene.removeItem(item)
        self._preview_overlays.clear()
        self.preview_scene.set_project(self._candidate)
        self.preview_scene.set_preview_mode(True)
        tokens = self._tokens
        self.preview_scene.apply_theme(tokens)
        result = self._placement_result
        affected = {i.cell_id for i in result.issues if i.cell_id}
        bad_groups = {i.group_id for i in result.issues if not i.cell_id}
        for cid, rect in result.plot_rects.items():
            bad = cid in affected or any(g.id in bad_groups and cid in g.cell_ids for g in self._candidate.plot_alignment_groups)
            color = QColor(tokens["danger"] if bad else tokens["success"])
            pen = QPen(color, 1.5)
            pen.setCosmetic(True)
            item = self.preview_scene.addRect(QRectF(*rect), pen, QBrush(Qt.BrushStyle.NoBrush))
            item.setZValue(10000)
            self._preview_overlays.append(item)
            pen.setStyle(Qt.PenStyle.DashLine)
            x, y, w, h = rect
            item = self.preview_scene.addLine(x - 2, y + h, x + w + 2, y + h, pen)
            item.setZValue(10000)
            self._preview_overlays.append(item)
        self._fit_preview()

    def eventFilter(self, obj, event):
        if obj is self.preview_view and event.type() in (QEvent.Type.Resize, QEvent.Type.Show):
            self._preview_fit_timer.start()
        return super().eventFilter(obj, event)

    def _fit_preview(self):
        viewport = self.preview_view.viewport().rect()
        if viewport.width() < 40 or viewport.height() < 40:
            return
        members = self._group().cell_ids if self._current_group_id else []
        rects = [self._layout_rects[cid] for cid in members if cid in self._layout_rects]
        if rects:
            left = min(r[0] for r in rects)
            top = min(r[1] for r in rects)
            right = max(r[0] + r[2] for r in rects)
            bottom = max(r[1] + r[3] for r in rects)
            margin_x = (right - left) * 0.1
            margin_y = (bottom - top) * 0.1
            target = QRectF(left - margin_x, top - margin_y,
                            right - left + 2 * margin_x, bottom - top + 2 * margin_y)
        else:
            target = QRectF(getattr(self.preview_scene, 'page_rect', self.preview_scene.sceneRect()))
        if target.isEmpty():
            return
        # Go through CanvasView's own zoom path (not QGraphicsView.fitInView)
        # so its zoom state and the scene's view scale stay in sync; no
        # animation, since the preview refits after every edit.
        zoom = min(max(1, viewport.width() - 4) / target.width(),
                   max(1, viewport.height() - 4) / target.height())
        self.preview_view._start_zoom(zoom, QPointF(viewport.center()), target.center(), animated=False)

    def accept(self):
        if not self._validate():
            return
        self.plot_areas = {cid: copy.deepcopy(area) for cid, area in self._areas.items() if self.project.find_cell_by_id(cid) and area != self.project.find_cell_by_id(cid).plot_area}
        self.alignment_groups = copy.deepcopy(self._candidate.plot_alignment_groups)
        super().accept()
