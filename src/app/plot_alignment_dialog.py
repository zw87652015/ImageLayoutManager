from __future__ import annotations

import copy
import os
import uuid

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QFont, QImage, QPainter, QPen
from PyQt6.QtWidgets import (
    QAbstractSpinBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
    QHeaderView, QInputDialog, QLabel, QLineEdit, QPushButton, QScrollArea, QSizePolicy, QSpinBox, QSplitter,
    QStackedWidget, QStyle, QTableWidget, QTableWidgetItem, QTabWidget, QToolButton,
    QVBoxLayout, QWidget,
)

from src.app.i18n import tr
from src.app.theme import DARK, LIGHT, get_tokens
from src.canvas.canvas_scene import CanvasScene
from src.canvas.canvas_view import CanvasView
from src.model.data_model import PlotArea, PlotAlignmentGroup
from src.model.layout_engine import LayoutEngine
from src.utils.image_proxy import ThumbnailWorker
from src.utils.plot_alignment import resolve_image_placements, source_digest


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


class PlotGuideStages(QWidget):
    stages = ("select", "mark", "match", "apply")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.labels = [tr("plot_stage_" + stage) for stage in self.stages]
        self.current_stage = "select"
        font = QFont(self.font())
        font.setWeight(QFont.Weight.Medium)
        self.setFont(font)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAccessibleName(tr("plot_guide_stages"))
        self.set_stage("select")

    def minimumSizeHint(self):
        fm = self.fontMetrics()
        return QSize(sum(fm.horizontalAdvance(label) + fm.height() + 36 for label in self.labels), fm.height() + 14)

    def sizeHint(self):
        return self.minimumSizeHint()

    def set_stage(self, stage):
        self.current_stage = stage
        index = self.stages.index(stage)
        self.setAccessibleDescription("; ".join(
            f"{i + 1} {label}: " + tr("plot_stage_current" if i == index else "plot_stage_complete" if i < index else "plot_stage_pending")
            for i, label in enumerate(self.labels)))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        tokens = get_tokens(DARK if self.palette().window().color().lightness() < 128 else LIGHT)
        fm = self.fontMetrics()
        radius = fm.height() * 0.55
        slot = self.width() / 4
        index = self.stages.index(self.current_stage)
        for i, label in enumerate(self.labels):
            color = QColor(tokens["accent"] if i == index else tokens["success"] if i < index else tokens["text_sec"])
            center = QPointF(i * slot + radius + 2, self.height() / 2)
            painter.setPen(QPen(color, 1.5))
            painter.setBrush(self.palette().base())
            painter.drawEllipse(center, radius, radius)
            if i < index:
                painter.drawLine(center + QPointF(-radius * 0.5, 0), center + QPointF(-radius * 0.1, radius * 0.4))
                painter.drawLine(center + QPointF(-radius * 0.1, radius * 0.4), center + QPointF(radius * 0.5, -radius * 0.4))
            else:
                painter.drawText(QRectF(center.x() - radius, center.y() - radius, radius * 2, radius * 2), Qt.AlignmentFlag.AlignCenter, str(i + 1))
            text_x = center.x() + radius + 7
            painter.drawText(QRectF(text_x, 0, slot - radius * 2 - 12, self.height()), Qt.AlignmentFlag.AlignVCenter, label)
            if i < 3:
                painter.setPen(QPen(QColor(tokens["border_strong"]), 1))
                start = text_x + fm.horizontalAdvance(label) + 10
                painter.drawLine(QPointF(start, center.y()), QPointF((i + 1) * slot - 6, center.y()))


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
            painter.drawText(QRectF(margin, max(line * 2.7, self.height() * 0.47) + i * line * 1.3, split - margin * 2, line * 1.3), Qt.AlignmentFlag.AlignVCenter, tr(key))
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
        painter.drawText(QRectF(graph.left(), graph.bottom() + 5, graph.width(), line), Qt.AlignmentFlag.AlignCenter, tr("plot_axis_x"))
        painter.save()
        painter.translate(graph.left() - line, graph.center().y())
        painter.rotate(-90)
        painter.drawText(QRectF(-graph.height() / 2, -line, graph.height(), line), Qt.AlignmentFlag.AlignCenter, tr("plot_axis_y"))
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
        painter.drawText(QRectF(first.left() - line, graph.top() - line * 0.2, first.width() + line * 2, line), Qt.AlignmentFlag.AlignCenter, tr("plot_reference"))
        painter.setPen(QPen(accent, 1.5))
        self._arrow(painter, QPointF(first.right() + graph.width() * 0.1, first.top()), QPointF(first.right() + graph.width() * 0.1, first.bottom()), line * 0.4, both=True)
        painter.setPen(QPen(self.palette().text().color(), 1.5, Qt.PenStyle.DashLine))
        painter.drawLine(QPointF(graph.left() - 8, first.bottom()), QPointF(graph.right() + 8, first.bottom()))


class PlotAreaView(QWidget):
    area_changed = pyqtSignal(object)

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
        self._redraw = False
        self._drawn = False
        self._guide_target = False

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
        self.fit_view()

    def set_area(self, area):
        if area is not None and hasattr(area, "left"):
            area = (area.left, area.top, area.right, area.bottom)
        self._area = tuple(area) if area is not None else None
        self._redraw = False
        self.update()

    def set_crop(self, crop):
        self._crop = crop
        self.update()

    def start_redraw(self):
        self._redraw = True
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setFocus()

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
            for x in (box.left(), box.center().x(), box.right()):
                for y in (box.top(), box.center().y(), box.bottom()):
                    if x != box.center().x() or y != box.center().y():
                        painter.drawRect(QRectF(x - 3, y - 3, 6, 6))
        self._paint_guide_border(painter)

    def _hit(self, position):
        if not self._area or self._redraw:
            return "draw"
        rect = self._box_rect(self._area)
        if not rect.adjusted(-7, -7, 7, 7).contains(position):
            return "draw"
        hit = ""
        if abs(position.x() - rect.left()) <= 7:
            hit += "l"
        elif abs(position.x() - rect.right()) <= 7:
            hit += "r"
        if abs(position.y() - rect.top()) <= 7:
            hit += "t"
        elif abs(position.y() - rect.bottom()) <= 7:
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
            self._redraw = False
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
                self.area_changed.emit(self._area)
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

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Space:
            self._space = True
            self.setCursor(Qt.CursorShape.OpenHandCursor)
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


class PlotAlignmentDialog(QDialog):
    def __init__(self, project, selected_ids=None, parent=None):
        super().__init__(parent)
        self.project = project
        self.setObjectName("plotAlignmentDialog")
        self.guidance_stage = "select"
        self.guidance_target = None
        self._guide_original_accent = None
        self.setWindowTitle(tr("action_align_plots"))
        self.resize(960, 660)
        self.setMinimumSize(700, 480)
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
        self._image_cache = {}
        self._preview_overlays = []
        self.plot_areas = {}
        self.alignment_groups = copy.deepcopy(project.plot_alignment_groups)
        self._build_ui()
        owners = [gid for gid in self._group_order if set(self._drafts[gid].cell_ids).intersection(self._selected_ids)]
        assigned = {cid for gid in self._group_order for cid in self._drafts[gid].cell_ids}
        unassigned = [cid for cid in self._selected_ids if cid not in assigned]
        if owners:
            first = next(gid for cid in self._selected_ids for gid in self._group_order if cid in self._drafts[gid].cell_ids)
            if len(owners) > 1:
                self._spans_notice = tr("plot_selection_spans").format(count=len(owners), name=self._drafts[first].name)
            group = self._drafts[first]
            for cid in unassigned:
                group.cell_ids.append(cid)
                group.row_groups.setdefault(cid, self._suggested_rows.get(cid, 1))
            self.group_combo.setCurrentIndex(self.group_combo.findData(first))
        else:
            # No group owns the selection: start with none chosen. Groups
            # only come into being through the New group button.
            self.group_combo.setCurrentIndex(-1)
        self._load_group()
        self._initialized = True

    _NO_GROUP = PlotAlignmentGroup(id="", name="", cell_ids=[], reference_id="")

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
        self.group_combo.blockSignals(True)
        self.group_combo.addItem(self._group_caption(gid), gid)
        self.group_combo.blockSignals(False)
        return gid

    def _new_group(self):
        default = self._default_group_name()
        name, ok = QInputDialog.getText(self, tr("plot_new_group"), tr("plot_group_name_prompt"), text=default)
        if not ok:
            return
        gid = self._create_group(name.strip() or default)
        self.group_combo.setCurrentIndex(self.group_combo.findData(gid))
        self.table.setFocus()

    def _delete_new_group(self, gid):
        group = self._drafts[gid]
        for cid in list(self._moved):
            if cid in group.cell_ids:
                self._restore_member(cid)
        self._group_order.remove(gid)
        self._new_ids.discard(gid)
        self._auto_removed.discard(gid)
        del self._drafts[gid]
        self.group_combo.blockSignals(True)
        self.group_combo.removeItem(self.group_combo.findData(gid))
        self.group_combo.setCurrentIndex(-1)
        self.group_combo.blockSignals(False)
        self._load_group()

    @staticmethod
    def _signature(group):
        rows = {cid: group.row_groups.get(cid) for cid in group.cell_ids} if group.baseline_mode == "custom" else None
        return (group.name, list(group.cell_ids), group.reference_id, group.sizing_mode, group.baseline_mode, rows)

    def _dropped(self):
        return self._removed | self._auto_removed

    def _owner_of(self, cid, exclude=None):
        return next((gid for gid in self._group_order
                     if gid != exclude and gid not in self._removed and cid in self._drafts[gid].cell_ids), None)

    def _member_names(self, gid):
        return [os.path.basename(self._cells[cid].image_path) if cid in self._cells else tr("plot_missing_panel").format(id=cid[:8])
                for cid in self._drafts[gid].cell_ids]

    def _group_caption(self, gid):
        names = self._member_names(gid)
        shown = ", ".join(names[:3]) + (tr("plot_more_members").format(count=len(names) - 3) if len(names) > 3 else "")
        caption = self._drafts[gid].name + (" — " + shown if shown else "")
        if gid in self._auto_removed:
            caption += tr("plot_will_remove_suffix")
        return caption

    def _refresh_group_captions(self):
        self.group_combo.blockSignals(True)
        for index in range(self.group_combo.count()):
            self.group_combo.setItemText(index, self._group_caption(self.group_combo.itemData(index)))
        self.group_combo.blockSignals(False)

    def _changed_group_ids(self):
        return [gid for gid in self._group_order
                if (gid in self._new_ids and self._drafts[gid].cell_ids and gid not in self._dropped())
                or (gid not in self._new_ids and (gid in self._dropped() or self._signature(self._drafts[gid]) != self._originals[gid]))]

    def _label(self, text):
        label = QLabel(text)
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setWordWrap(True)
        label.setMinimumWidth(0)
        label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        return label

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

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        heading = QHBoxLayout()
        heading.addWidget(QLabel(tr("plot_group")))
        self.group_combo = QComboBox()
        self.group_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.group_combo.setMinimumContentsLength(12)
        self.group_combo.setPlaceholderText(tr("plot_no_groups"))
        for gid in self._group_order:
            self.group_combo.addItem(self._group_caption(gid), gid)
        heading.addWidget(self.group_combo, 2)
        self.new_group_button = QPushButton(tr("plot_new_group"))
        self.new_group_button.setToolTip(tr("plot_new_group_tooltip"))
        heading.addWidget(self.new_group_button)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText(tr("plot_group_name_hint"))
        self.name_edit.setToolTip(tr("plot_group_name_hint"))
        self.name_edit.setAccessibleName(tr("plot_group_name_hint"))
        self.name_edit.setMaximumWidth(220)
        heading.addWidget(self.name_edit, 1)
        self.remove_button = QPushButton(tr("plot_remove"))
        heading.addWidget(self.remove_button)
        layout.addLayout(heading)
        self.stage_strip = PlotGuideStages(self)
        layout.addWidget(self.stage_strip)
        guidance = QHBoxLayout()
        self.guidance_label = self._label("")
        self.guidance_label.setObjectName("plotGuidance")
        guidance.addWidget(self.guidance_label, 1)
        self.example_button = QToolButton()
        self.example_button.setText(tr("plot_example"))
        self.example_button.setToolTip(tr("plot_example_tooltip"))
        self.example_button.setAccessibleName(tr("plot_example_tooltip"))
        self.example_button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.details_button = QToolButton()
        self.details_button.setText(tr("plot_details"))
        self.details_button.setToolTip(tr("plot_details_tooltip"))
        self.details_button.setAccessibleName(tr("plot_details_tooltip"))
        self.details_button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        guidance.addWidget(self.example_button)
        guidance.addWidget(self.details_button)
        layout.addLayout(guidance)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        left.setMinimumWidth(300)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self.table = QTableWidget(0, 4)
        self.table.setAccessibleName(tr("plot_panel"))
        self.table.setAccessibleDescription(tr("plot_guide_select"))
        self.table.setHorizontalHeaderLabels([tr("plot_panel"), tr("plot_state"), tr("plot_row"), tr("plot_group")])
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(1, max(105, self.fontMetrics().horizontalAdvance(tr("plot_does_not_fit")) + 32))
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(2, 62)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(3, 110)
        left_layout.addWidget(self.table, 1)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.reference_combo = QComboBox()
        self.sizing_combo = QComboBox()
        self.baseline_combo = QComboBox()
        for combo in (self.reference_combo, self.sizing_combo, self.baseline_combo):
            combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(10)
        self.sizing_combo.addItem(tr("plot_exact"), "reference")
        self.sizing_combo.addItem(tr("plot_fit"), "fit")
        for key, mode in (("plot_grid_rows", "grid_rows"), ("plot_single", "single"), ("plot_custom", "custom")):
            self.baseline_combo.addItem(tr(key), mode)
        form.addRow(tr("plot_reference"), self.reference_combo)
        form.addRow(tr("plot_sizing"), self.sizing_combo)
        form.addRow(tr("plot_baselines"), self.baseline_combo)
        left_layout.addLayout(form)
        self.target_label = self._label("")
        left_layout.addWidget(self.target_label)
        self.splitter.addWidget(left)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        tabs = QHBoxLayout()
        self.source_button = QPushButton(tr("plot_source"))
        self.preview_button = QPushButton(tr("plot_preview"))
        self.fit_button = QPushButton(tr("plot_fit_view"))
        self.fit_button.setToolTip(tr("plot_fit_view_tooltip"))
        tabs.addWidget(self.source_button)
        tabs.addWidget(self.preview_button)
        tabs.addStretch()
        tabs.addWidget(self.fit_button)
        right_layout.addLayout(tabs)
        self.source_label = self._label("")
        right_layout.addWidget(self.source_label)
        self.views = QStackedWidget()
        self.source_view = PlotAreaView()
        self.source_view.setAccessibleName(tr("plot_source"))
        self.source_view.setAccessibleDescription(tr("plot_source_help"))
        self.preview_scene = CanvasScene(self)
        self.preview_view = CanvasView(self.preview_scene)
        self.preview_view.setInteractive(False)
        self.preview_view.setAcceptDrops(False)
        self.views.addWidget(self.source_view)
        self.views.addWidget(self.preview_view)
        right_layout.addWidget(self.views, 1)
        controls = QHBoxLayout()
        self.redraw_button = QPushButton(tr("plot_redraw"))
        self.clear_button = QPushButton(tr("plot_clear"))
        self.next_button = QPushButton(tr("plot_mark_next"))
        for button in (self.redraw_button, self.clear_button, self.next_button):
            controls.addWidget(button)
        right_layout.addLayout(controls)
        self.source_help = self._label(tr("plot_source_help"))
        right_layout.addWidget(self.source_help)
        self.splitter.addWidget(right)
        self.splitter.setStretchFactor(0, 2)
        self.splitter.setStretchFactor(1, 3)
        self.splitter.setSizes([400, 530])
        layout.addWidget(self.splitter, 1)
        self.readiness_label = self._label("")
        layout.addWidget(self.readiness_label)
        self.membership_label = self._label("")
        self.membership_label.setObjectName("plotMembershipNotes")
        self.membership_label.hide()
        layout.addWidget(self.membership_label)
        self._build_guide_popups()
        self.buttons = QDialogButtonBox()
        self.fit_plots_button = self.buttons.addButton(tr("plot_fit_plots"), QDialogButtonBox.ButtonRole.ActionRole)
        self.fit_plots_button.setToolTip(tr("plot_fit_plots_tooltip"))
        self.fit_plots_button.clicked.connect(self._fit_plots_within_cells)
        self.apply_button = self.buttons.addButton(tr("plot_apply"), QDialogButtonBox.ButtonRole.AcceptRole)
        self.buttons.addButton(tr("plot_cancel"), QDialogButtonBox.ButtonRole.RejectRole)
        layout.addWidget(self.buttons)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self.group_combo.currentIndexChanged.connect(self._load_group)
        self.new_group_button.clicked.connect(self._new_group)
        self.name_edit.textEdited.connect(self._name_changed)
        self.name_edit.editingFinished.connect(self._name_changed)
        self.remove_button.clicked.connect(self._toggle_remove)
        self.table.itemChanged.connect(self._controls_changed)
        self.table.currentCellChanged.connect(self._select_source)
        self.reference_combo.currentIndexChanged.connect(self._controls_changed)
        self.sizing_combo.currentIndexChanged.connect(self._controls_changed)
        self.baseline_combo.currentIndexChanged.connect(self._controls_changed)
        self.source_view.area_changed.connect(self._area_changed)
        self.source_button.clicked.connect(self._show_source)
        self.preview_button.clicked.connect(self._show_preview)
        self.fit_button.clicked.connect(self._fit_view)
        self.redraw_button.clicked.connect(self._redraw)
        self.clear_button.clicked.connect(self._clear_area)
        self.next_button.clicked.connect(self._next_unmarked)
        for button in self.findChildren(QPushButton):
            button.setAutoDefault(False)

    def _build_guide_popups(self):
        self.example_dialog = QDialog(self)
        self.example_dialog.setAttribute(Qt.WidgetAttribute.WA_WindowPropagation, True)
        self.example_dialog.setWindowTitle(tr("plot_example_tooltip"))
        self.example_dialog.resize(700, 380)
        self.example_dialog.setMinimumSize(560, 300)
        example_layout = QVBoxLayout(self.example_dialog)
        self.example_tabs = QTabWidget()
        for mode, key in (("mark", "plot_example_mark"), ("alignment", "plot_example_alignment")):
            diagram = PlotGuideIllustration(mode)
            self.example_tabs.addTab(diagram, tr(key))
        example_layout.addWidget(self.example_tabs, 1)
        self.details_dialog = QDialog(self)
        self.details_dialog.setAttribute(Qt.WidgetAttribute.WA_WindowPropagation, True)
        self.details_dialog.setWindowTitle(tr("plot_details_tooltip"))
        self.details_dialog.resize(620, 440)
        details_layout = QVBoxLayout(self.details_dialog)
        self.details_scroll = QScrollArea()
        self.details_scroll.setWidgetResizable(True)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        self.help_label = self._label(tr("plot_mark_help"))
        self.notes_label = self._label("")
        self.status_label = self._label("")
        self.details_status_label = self._label("")
        self.details_source_label = self._label(tr("plot_source_help"))
        for label in (self.status_label, self.details_status_label, self.notes_label, self.help_label, self.details_source_label):
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard)
            label.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            content_layout.addWidget(label)
        content_layout.addStretch()
        self.details_scroll.setWidget(content)
        details_layout.addWidget(self.details_scroll, 1)
        for popup, popup_layout in ((self.example_dialog, example_layout), (self.details_dialog, details_layout)):
            close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
            close.button(QDialogButtonBox.StandardButton.Close).setText(tr("btn_close"))
            close.button(QDialogButtonBox.StandardButton.Close).setAutoDefault(False)
            close.rejected.connect(popup.close)
            popup_layout.addWidget(close)
        self.example_button.clicked.connect(self._open_example)
        self.details_button.clicked.connect(self._open_details)

    def _open_example(self):
        self.example_dialog.show()
        self.example_dialog.raise_()
        self.example_dialog.activateWindow()
        self.example_tabs.setFocus()

    def _open_details(self):
        self.details_dialog.show()
        self.details_dialog.raise_()
        self.details_dialog.activateWindow()
        self.details_scroll.setFocus()

    def done(self, result):
        self.example_dialog.close()
        self.details_dialog.close()
        super().done(result)

    def _set_guidance(self, stage, target, text):
        old = self.guidance_target
        if old is not target:
            if old is not None:
                old.setProperty("plotGuideTarget", False)
                if isinstance(old, QPushButton):
                    old.setProperty("accent", self._guide_original_accent)
                if old is self.source_view:
                    old.set_guide_target(False)
                old.style().unpolish(old)
                old.style().polish(old)
                old.update()
            self.guidance_target = target
            self._guide_original_accent = target.property("accent")
            target.setProperty("plotGuideTarget", True)
            if isinstance(target, QPushButton):
                target.setProperty("accent", True)
            if target is self.source_view:
                target.set_guide_target(True)
            target.style().unpolish(target)
            target.style().polish(target)
            target.update()
        self.guidance_stage = stage
        self.stage_strip.set_stage(stage)
        self.guidance_label.setText(text)
        self.guidance_label.setAccessibleName(text)

    def _repairable_mark_ids(self):
        needed = []
        issues = self._placement_result.issues
        for cid in self.checked_ids():
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

    def _refresh_guidance(self):
        if self._loading or not hasattr(self, "_placement_result"):
            return
        group = self._group()
        checked = self.checked_ids()
        removed = self._current_group_id in self._dropped()
        needed = self._repairable_mark_ids() if not removed else []
        self.next_button.setEnabled(bool(needed))
        valid = self.apply_button.isEnabled()
        active = [i for i in self._placement_result.issues if i.group_id or not i.cell_id]
        if self._current_group_id is None:
            self._set_guidance("apply" if valid else "select", self.apply_button if valid else self.new_group_button,
                               tr("plot_guide_apply_changes" if valid else "plot_guide_create_group"))
        elif removed and valid:
            self._set_guidance("apply", self.apply_button, tr("plot_guide_remove"))
        elif not removed and len(checked) < 2:
            self._set_guidance("select", self.table, tr("plot_guide_new_group").format(name=group.name) if self._current_group_id in self._new_ids else tr("plot_guide_select"))
        elif needed:
            if self._current_cell_id in needed:
                changed = any(i.cell_id == self._current_cell_id and i.code == "source_changed" for i in active)
                target = self.source_view if self.views.currentWidget() is self.source_view else self.source_button
                self._set_guidance("mark", target, tr("plot_guide_changed" if changed else "plot_guide_mark"))
            else:
                changed = any(i.cell_id in needed and i.code == "source_changed" for i in active)
                self._set_guidance("mark", self.next_button, tr("plot_guide_next_changed" if changed else "plot_guide_next"))
        elif not removed and (group.reference_id not in checked or group.reference_id not in self._cells):
            self._set_guidance("match", self.reference_combo, tr("plot_guide_reference"))
        elif not removed and self._invalid_rows(group):
            self._set_guidance("match", self.table, tr("plot_guide_rows"))
        elif not valid:
            issue = next((i for i in active if i.group_id == group.id), active[0] if active else None)
            other = removed or (issue is not None and issue.group_id and issue.group_id != group.id)
            key = "plot_guide_other" if other else "plot_guide_issue_" + issue.code if issue else "plot_guide_review"
            target = self.group_combo if other else self.baseline_combo if issue and issue.code == "no_space" else self.table
            self._set_guidance("match", target, tr(key))
        elif self.views.currentWidget() is self.preview_view:
            self._set_guidance("apply", self.apply_button, tr("plot_guide_apply"))
        else:
            name = self._panel_label(group.reference_id)
            name = self.fontMetrics().elidedText(name, Qt.TextElideMode.ElideMiddle, max(80, min(230, self.width() // 4)))
            self._set_guidance("match", self.preview_button, tr("plot_guide_preview").format(name=name))

    def checked_ids(self):
        return [self.table.item(row, 0).data(Qt.ItemDataRole.UserRole) for row in range(self.table.rowCount()) if self.table.item(row, 0).checkState() == Qt.CheckState.Checked]

    def _load_group(self, *_):
        self._loading = True
        if getattr(self, "_initialized", False):
            self._spans_notice = ""
        self._current_group_id = self.group_combo.currentData()
        has_group = self._current_group_id is not None
        group = self._group()
        self.name_edit.blockSignals(True)
        self.name_edit.setText(group.name)
        self.name_edit.blockSignals(False)
        for widget in (self.name_edit, self.reference_combo, self.sizing_combo, self.baseline_combo, self.remove_button):
            widget.setEnabled(has_group)
        ids = list(self._cells)
        ids.extend(cid for cid in group.cell_ids if cid not in ids)
        self.table.setRowCount(0)
        for row, cid in enumerate(ids):
            self.table.insertRow(row)
            item = QTableWidgetItem(self._panel_label(cid))
            item.setData(Qt.ItemDataRole.UserRole, cid)
            if has_group:
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked if cid in group.cell_ids else Qt.CheckState.Unchecked)
            else:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
            cell = self._cells.get(cid)
            item.setToolTip(cell.image_path if cell else self._panel_label(cid))
            self.table.setItem(row, 0, item)
            self.table.setItem(row, 1, QTableWidgetItem())
            self.table.setItem(row, 3, QTableWidgetItem())
            spin = QSpinBox()
            spin.setRange(-1, 999)
            spin.setSpecialValueText("—")
            # Typed entry only: the step arrows invite clicking through
            # baseline numbers, which regroups panels one accidental step
            # at a time.
            spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
            spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
            default_row = -1 if group.baseline_mode == "custom" and cid in group.cell_ids and group.id not in self._new_ids else self._suggested_rows.get(cid, 1)
            value = group.row_groups.get(cid, default_row)
            spin.setValue(value if type(value) is int and value >= 0 else -1)
            spin.valueChanged.connect(self._controls_changed)
            self.table.setCellWidget(row, 2, spin)
        self.sizing_combo.setCurrentIndex(self.sizing_combo.findData(group.sizing_mode))
        self.baseline_combo.setCurrentIndex(self.baseline_combo.findData(group.baseline_mode))
        self._update_references(group.reference_id)
        if has_group:
            self._update_remove_button()
        self._loading = False
        first = next((row for row, cid in enumerate(ids) if cid in group.cell_ids and cid in self._cells), 0)
        if ids:
            self.table.setCurrentCell(first, 0)
            self._select_source(first)
        else:
            self._select_source(-1)
        self._controls_changed()

    def _update_references(self, preferred=None):
        preferred = preferred if preferred is not None else self.reference_combo.currentData()
        self.reference_combo.blockSignals(True)
        self.reference_combo.clear()
        for cid in self.checked_ids():
            if cid in self._cells:
                self.reference_combo.addItem(self._panel_label(cid), cid)
        index = self.reference_combo.findData(preferred)
        self.reference_combo.setCurrentIndex(index if index >= 0 else (0 if not preferred else -1))
        self.reference_combo.blockSignals(False)

    def _name_changed(self, *_):
        if self._loading or self._current_group_id is None:
            return
        group = self._drafts[self._current_group_id]
        name = self.name_edit.text().strip()
        if name:
            group.name = name
        self._refresh_group_captions()
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

    def _controls_changed(self, *_):
        if self._loading:
            return
        if self._current_group_id is None:
            self._refresh_group_captions()
            self._validate()
            if self.views.currentWidget() is self.preview_view:
                self._render_preview()
            return
        self._update_references()
        group = self._drafts[self._current_group_id]
        self._apply_membership_moves(self.checked_ids())
        group.cell_ids = self.checked_ids()
        group.reference_id = self.reference_combo.currentData() or ""
        group.sizing_mode = self.sizing_combo.currentData() or "reference"
        group.baseline_mode = self.baseline_combo.currentData() or "grid_rows"
        group.row_groups = {self.table.item(row, 0).data(Qt.ItemDataRole.UserRole): self.table.cellWidget(row, 2).value() for row in range(self.table.rowCount()) if self.table.item(row, 0).checkState() == Qt.CheckState.Checked}
        for row in range(self.table.rowCount()):
            self.table.cellWidget(row, 2).setEnabled(group.baseline_mode == "custom" and self.table.item(row, 0).checkState() == Qt.CheckState.Checked)
        self._refresh_group_captions()
        self._validate()
        if self.views.currentWidget() is self.preview_view:
            self._render_preview()

    def _select_source(self, row, *_):
        self._current_cell_id = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole) if row >= 0 and self.table.item(row, 0) else None
        cell = self._cells.get(self._current_cell_id)
        self.source_view.set_image(None)
        self._loaded_digest = ""
        self.source_label.setText(self._panel_label(self._current_cell_id) if self._current_cell_id else tr("plot_need_two"))
        if cell:
            try:
                digest = source_digest(cell.image_path)
                key = (cell.image_path, digest)
                image = self._image_cache.get(key)
                if image is None:
                    worker = ThumbnailWorker(cell.image_path, 2200, None)
                    ext = os.path.splitext(cell.image_path)[1].lower()
                    image = worker._load_svg() if ext == ".svg" else worker._load_pdf() if ext in (".pdf", ".eps") else worker._load_raster()
                    self._image_cache = {key: image}
                self.source_view.set_image(image)
                self._loaded_digest = digest if not image.isNull() else ""
                self.source_view.set_area(self._areas.get(cell.id))
                self.source_view.set_crop((cell.crop_left, cell.crop_top, cell.crop_right, cell.crop_bottom))
            except Exception:
                self.source_label.setText(self._panel_label(cell.id) + " — " + tr("plot_issue_missing_source"))
        for button in (self.redraw_button, self.clear_button):
            button.setEnabled(bool(cell) and (button is self.clear_button or bool(self._loaded_digest)))
        self._show_source()

    def _area_changed(self, area):
        cid = self._current_cell_id
        cell = self._cells.get(cid)
        if not cell:
            return
        try:
            digest = source_digest(cell.image_path)
        except Exception:
            digest = ""
        if not digest or digest != self._loaded_digest:
            self._select_source(self.table.currentRow())
            self._validate()
            return
        self._areas[cid] = PlotArea(*area, source_digest=digest)
        self._controls_changed()

    def _clear_area(self):
        if self._current_cell_id in self._areas:
            self._areas[self._current_cell_id] = None
            self.source_view.set_area(None)
            self._show_source()
            self._controls_changed()

    def _redraw(self):
        self._show_source()
        self.source_view.start_redraw()

    def _next_unmarked(self):
        self._validate()
        needed = self._repairable_mark_ids()
        count = self.table.rowCount()
        for offset in range(1, count + 1):
            row = (self.table.currentRow() + offset) % count
            cid = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
            if cid in needed:
                if row == self.table.currentRow():
                    self._select_source(row)
                else:
                    self.table.setCurrentCell(row, 0)
                return

    def _update_remove_button(self):
        gid = self._current_group_id
        if gid in self._new_ids and gid not in self._auto_removed:
            self.remove_button.setText(tr("plot_delete_group"))
        else:
            self.remove_button.setText(tr("plot_restore" if gid in self._dropped() else "plot_remove"))

    def _toggle_remove(self):
        gid = self._current_group_id
        if gid in self._auto_removed:
            self._auto_removed.discard(gid)
        elif gid in self._new_ids:
            self._delete_new_group(gid)
            return
        elif gid in self._removed:
            self._removed.remove(gid)
        else:
            self._removed.add(gid)
        self._update_remove_button()
        self._controls_changed()

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

    @staticmethod
    def _invalid_rows(group):
        return group.baseline_mode == "custom" and any(type(group.row_groups.get(cid)) is not int or group.row_groups[cid] < 0 for cid in group.cell_ids)

    def _can_fit_plots(self):
        """The current exact-reference group had to shrink so nothing is
        clipped; offer to make that explicit by switching it to fit sizing."""
        group = next((g for g in self._candidate.plot_alignment_groups if g.id == self._current_group_id), None)
        if group is None or group.sizing_mode != "reference":
            return False
        return any(notice.group_id == group.id for notice in self._placement_result.notices)

    def _fit_plots_within_cells(self):
        self._validate()
        if not self.fit_plots_button.isEnabled():
            return
        self.sizing_combo.setCurrentIndex(self.sizing_combo.findData("fit"))
        self._show_preview()

    def _validate(self):
        self._candidate = self.build_candidate()
        self._placement_result = resolve_image_placements(self._candidate, strict=False)
        issues = self._placement_result.issues
        group = self._group()
        has_group = self._current_group_id is not None
        removed = self._current_group_id in self._dropped()
        checked = self.checked_ids()
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
        can_fit = valid and self._can_fit_plots()
        self.fit_plots_button.setVisible(can_fit)
        self.fit_plots_button.setEnabled(can_fit)
        self.apply_button.setEnabled(valid)
        self.readiness_label.setText(tr("plot_marked_count").format(marked=sum(self._areas.get(cid) is not None for cid in checked), selected=len(checked)))
        if not has_group:
            status = "\n".join(messages) if messages else tr("plot_no_groups_status")
        else:
            status = "\n".join(messages) if messages else tr("plot_remove_note" if removed else "plot_valid")
        info = self._membership_notes() + [
            tr("plot_issue_reduced_to_fit").format(
                name=next((g.name for g in self._candidate.plot_alignment_groups if g.id == notice.group_id), ""),
                height=f"{self._placement_result.group_heights.get(notice.group_id, 0):.2f}")
            for notice in self._placement_result.notices]
        banner = ([self._spans_notice] if self._spans_notice else []) + info
        self.membership_label.setText("\n".join(banner))
        self.membership_label.setVisible(bool(banner))
        if info:
            status += "\n" + "\n".join(info)
            details.extend(info)
        self.status_label.setText(status)
        tooltip = "\n".join(details) if details else status
        self.status_label.setToolTip(tooltip)
        self.details_status_label.setText(tooltip)
        self.apply_button.setToolTip(tooltip)
        height = self._placement_result.group_heights.get(group.id)
        self.target_label.setText(tr("plot_target").format(height=f"{height:.2f}" if height is not None else "—"))
        notes = tr("plot_fit_note" if group.sizing_mode == "fit" else "plot_exact_note")
        notes += "\n" + tr({"grid_rows": "plot_rows_note", "single": "plot_single_note", "custom": "plot_custom_note"}.get(group.baseline_mode, "plot_rows_note"))
        self.notes_label.setText(tr("plot_no_groups_status") if not has_group else tr("plot_remove_note") if removed else notes)
        self.table.blockSignals(True)
        for row in range(self.table.rowCount()):
            cid = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
            cell = self._cells.get(cid)
            area = self._areas.get(cid)
            cell_issues = [i for i in issues if i.cell_id == cid or (not i.cell_id and any(g.id == i.group_id and cid in g.cell_ids for g in self._candidate.plot_alignment_groups))]
            if cell is None:
                key = "plot_issue_missing_member"
            elif not os.path.isfile(cell.image_path):
                key = "plot_issue_missing_source"
            elif any(i.code == "source_changed" for i in cell_issues):
                key = "plot_issue_source_changed"
            elif not area:
                key = "plot_unmarked"
            elif any(i.code in ("overflow", "no_space") for i in cell_issues):
                key = "plot_does_not_fit"
            elif cell_issues:
                key = "plot_needs_attention"
            elif cid == group.reference_id:
                key = "plot_reference"
            else:
                key = "plot_ready"
            item = self.table.item(row, 1)
            item.setText(tr(key))
            icon = QStyle.StandardPixmap.SP_DialogApplyButton if key in ("plot_ready", "plot_reference") else QStyle.StandardPixmap.SP_MessageBoxWarning
            item.setIcon(self.style().standardIcon(icon))
            tooltip = alignment_issues_text(cell_issues, self._candidate, 100)
            if cid == group.reference_id:
                tooltip = tr("plot_reference") + ("\n" + tooltip if tooltip else "")
            item.setToolTip(tooltip)
            membership = self.table.item(row, 3)
            owner = self._current_group_id if cid in checked else self._owner_of(cid, exclude=self._current_group_id)
            if owner is None:
                membership.setText("—")
                membership.setToolTip("")
            else:
                name = self._drafts[owner].name
                membership.setText(name + (tr("plot_will_remove_suffix") if owner in self._auto_removed else ""))
                membership.setToolTip("" if owner == self._current_group_id else tr("plot_move_hint").format(name=name))
        self.table.blockSignals(False)
        self._refresh_guidance()
        return valid

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
        changed = self._changed_group_ids()
        if len(changed) > 1:
            names = ", ".join(self._drafts[gid].name for gid in changed)
            notes.append(tr("plot_apply_summary").format(count=len(changed), names=names))
        return notes

    def _show_source(self):
        cell = self._cells.get(self._current_cell_id)
        text = tr("plot_gesture_hint")
        details = tr("plot_source_help")
        if cell and cell.rotation:
            text += "\n" + tr("plot_rotation_hint").format(degrees=cell.rotation)
            details += "\n" + tr("plot_rotated").format(degrees=cell.rotation)
        self.source_help.setText(text)
        self.source_help.setToolTip(details)
        self.details_source_label.setText(details)
        self.views.setCurrentWidget(self.source_view)
        self.fit_button.setText(tr("plot_fit_view"))
        self.source_button.setEnabled(False)
        self.preview_button.setEnabled(True)
        if not self._loading:
            self._validate()

    def _show_preview(self):
        self._validate()
        self.views.setCurrentWidget(self.preview_view)
        self.fit_button.setText(tr("plot_fit_figure_view"))
        self.source_button.setEnabled(True)
        self.preview_button.setEnabled(False)
        self.source_help.setText(tr("plot_preview_hint"))
        self.source_help.setToolTip(tr("plot_preview_help"))
        self.details_source_label.setText(tr("plot_preview_help"))
        self._render_preview()
        self._refresh_guidance()

    def _render_preview(self):
        for item in self._preview_overlays:
            self.preview_scene.removeItem(item)
        self._preview_overlays.clear()
        self.preview_scene.set_project(self._candidate)
        self.preview_scene.set_preview_mode(True)
        tokens = get_tokens(getattr(self.parent(), "_current_theme", DARK if self.palette().window().color().lightness() < 128 else LIGHT))
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
        self.preview_view.zoom_to_fit()

    def _fit_view(self):
        if self.views.currentWidget() is self.source_view:
            self.source_view.fit_view()
        else:
            self.preview_view.zoom_to_fit()

    def accept(self):
        self._controls_changed()
        if not self._validate():
            return
        self.plot_areas = {cid: copy.deepcopy(area) for cid, area in self._areas.items() if self.project.find_cell_by_id(cid) and area != self.project.find_cell_by_id(cid).plot_area}
        self.alignment_groups = copy.deepcopy(self._candidate.plot_alignment_groups)
        super().accept()
