"""Raster text size matching dialog.

Left : preview of the panel as it will render (regions re-scaled to their
       group size) with rounded text envelopes and translucent accent fill.
       Selected or hovered envelopes have stronger borders; inactive ones fade.
Right: Detect button + OCR status, region list (checkbox = enabled), per-region
       size/anchor controls, group assignment and the shared group editor.
"""

import os
from copy import deepcopy
from threading import Event, Lock

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem, QPushButton,
    QLabel, QComboBox, QDoubleSpinBox, QCheckBox, QSplitter, QWidget,
    QFrame, QSizePolicy, QMessageBox, QMenu, QToolButton,
)
from PyQt6.QtCore import (
    Qt, pyqtSignal, pyqtSlot, QRectF, QItemSelectionModel, QObject, QRunnable, QThreadPool,
)
from PyQt6.QtGui import QKeySequence, QPainter, QImage, QPen, QColor, QPalette, QShortcut, QTransform
from PIL import Image

from src.app.help_dialog import show_context_help
from src.app.i18n import tr
from src.app.motion import MotionTween, install_button_feedback
from src.app.text_groups_widget import section_label
from src.app.text_group_chips import TextGroupChips, chip_hint, group_colour, populate_group_menu
from src.utils.text_group_assign import assign_raster, new_svg_group, ungroup_raster
from src.utils.raster_text_ocr import configured_backend, detect_text, OcrUnavailable, backend_status
from src.utils.raster_text_utils import (
    apply_raster_text_overrides, build_raster_override_spec, regions_from_detections,
    get_raster_text_mask, raster_pt_per_px, ANCHORS,
)
from src.utils.raster_text_frame import image_bounds
from src.utils.svg_text_utils import format_text_size
from src.utils.text_match import RASTER_REL_TOL, format_size, raster_summary, size_clusters
from src.app.commands import TextMatchSessionCommand
from src.app.inspector import CollapsibleSection
from src.app.raster_text_overlay import text_envelope_path
from src.app.preview_zoom import ZoomPan
from src.app.raster_text_region_delegate import RasterTextRegionDelegate, REGION_DETAILS_ROLE
from src.app.text_match_session import (
    SessionRecorder, capture, restore, scoped_revert)


class RasterTextPreview(QWidget):
    region_selected = pyqtSignal(str, bool)
    view_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._image = QImage()
        self._overlays = []
        self._selected = set()
        self._hovered = None
        self._feedback = {}
        self._feedback_targets = {}
        self._zoom = ZoomPan()
        self._pan_drag = None        # widget pos where a pan drag started
        self._space = False
        self.setMinimumSize(280, 220)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.setAccessibleName(tr('rastertxt_preview_label'))

    def set_content(self, image, overlays):
        if (not image.isNull() and not self._image.isNull()
                and (image.width(), image.height()) != (self._image.width(), self._image.height())):
            self._zoom.reset()
            self.view_changed.emit()
        self._image = image
        self._overlays = overlays
        self._hovered = None
        self.setToolTip('')
        self.unsetCursor()
        ids = {o['id'] for o in overlays}
        for rid in self._feedback.keys() - ids:
            self._feedback_targets.pop(rid, None)
            for tween in self._feedback.pop(rid):
                tween.updated.disconnect(self._feedback_updated)
                tween.set_target(tween.value, ms=0)
                tween.deleteLater()
        self._sync_feedback()

    def set_selected(self, ids):
        self._selected = set(ids)
        self._sync_feedback()

    @pyqtSlot(float)
    def _feedback_updated(self, _value):
        self.update()

    def _sync_feedback(self):
        for overlay in self._overlays:
            rid = overlay['id']
            selected, hovered = rid in self._selected, rid == self._hovered
            fill = 55 if selected else 40 if hovered else 22 if overlay['enabled'] else 8
            border = 255 if selected or hovered else 170 if overlay['enabled'] else 85
            if rid not in self._feedback:
                self._feedback[rid] = tuple(MotionTween(self, value=value) for value in (fill, border))
                for tween in self._feedback[rid]:
                    tween.updated.connect(self._feedback_updated)
            elif self._feedback_targets.get(rid) != (fill, border):
                for tween, target in zip(self._feedback[rid], (fill, border)):
                    tween.set_target(target, ms=100)
            self._feedback_targets[rid] = (fill, border)
        self.update()

    def image_transform(self):
        transform = QTransform()
        if self._image.isNull():
            return transform
        scale, left, top = self._zoom.transform(
            self.width(), self.height(), self._image.width(), self._image.height())
        transform.translate(left, top)
        transform.scale(scale, scale)
        return transform

    def _zoom_pan_args(self):
        return self.width(), self.height(), self._image.width(), self._image.height()

    def wheelEvent(self, event):
        if self._image.isNull():
            event.ignore()
            return
        self._zoom.zoom_at(event.position().x(), event.position().y(),
                           event.angleDelta().y() / 120.0, *self._zoom_pan_args())
        self.view_changed.emit()
        self.update()
        event.accept()

    def _pan_to(self, pos):
        if self._pan_drag is None:
            return
        dx, dy = pos.x() - self._pan_drag.x(), pos.y() - self._pan_drag.y()
        self._pan_drag = pos
        self._zoom.pan_by(dx, dy, *self._zoom_pan_args())
        self.view_changed.emit()
        self.update()

    def resizeEvent(self, event):
        if not self._image.isNull():
            self._zoom.pan_by(0, 0, *self._zoom_pan_args())   # re-clamp
        super().resizeEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space = True
            if self._pan_drag is None:
                self.setCursor(Qt.CursorShape.OpenHandCursor)
            event.accept()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space = False
            if self._pan_drag is None:
                self.unsetCursor()
            event.accept()
            return
        super().keyReleaseEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), self.palette().color(QPalette.ColorRole.AlternateBase))
        if self._image.isNull():
            painter.setPen(self.palette().color(QPalette.ColorRole.Text))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, tr('svgtxt_preview_failed'))
            return
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        transform = self.image_transform()
        if transform.m11() * self.devicePixelRatioF() < 2.0:
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        image_rect = transform.mapRect(QRectF(0, 0, self._image.width(), self._image.height()))
        painter.drawImage(image_rect, self._image)
        painter.setClipRect(image_rect)
        accent = self.palette().color(QPalette.ColorRole.Highlight)
        for overlay in sorted(self._overlays, key=lambda o: o['id'] in self._selected):
            selected = overlay['id'] in self._selected
            hovered = overlay['id'] == self._hovered
            fill_tween, border_tween = self._feedback[overlay['id']]
            tint = QColor(overlay['color']) if overlay.get('color') else accent
            fill = QColor(tint)
            fill.setAlpha(round(fill_tween.value))
            border = QColor(tint)
            border.setAlpha(round(border_tween.value))
            pen = QPen(border, 3.0 if selected or hovered else 2.0)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            path = transform.map(overlay['path'])
            painter.save()
            painter.setClipPath(path, Qt.ClipOperation.IntersectClip)
            painter.setPen(pen)
            painter.setBrush(fill)
            painter.drawPath(path)
            painter.restore()
        painter.end()

    def _hit_test(self, point):
        inverse, valid = self.image_transform().inverted()
        if not valid:
            return None
        source = inverse.map(point)
        ordered = sorted(self._overlays, key=lambda o: o['id'] in self._selected)
        return next((o for o in reversed(ordered) if o['path'].contains(source)), None)

    def mouseMoveEvent(self, event):
        if self._pan_drag is not None:
            self._pan_to(event.position())
            return
        overlay = self._hit_test(event.position())
        hovered = overlay['id'] if overlay else None
        if hovered != self._hovered:
            self._hovered = hovered
            self.setToolTip(overlay['tooltip'] if overlay else '')
            if not self._space:
                self.setCursor(Qt.CursorShape.PointingHandCursor if overlay else Qt.CursorShape.ArrowCursor)
            self._sync_feedback()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self._hovered = None
        self.setToolTip('')
        self.unsetCursor()
        self._sync_feedback()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton or (
                event.button() == Qt.MouseButton.LeftButton and self._space):
            self.setFocus()
            self._pan_drag = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            overlay = self._hit_test(event.position())
            self.region_selected.emit(overlay['id'] if overlay else '',
                                      bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier))
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if self._pan_drag is not None and event.button() in (
                Qt.MouseButton.MiddleButton, Qt.MouseButton.LeftButton):
            self._pan_drag = None
            self.setCursor(Qt.CursorShape.OpenHandCursor if self._space
                           else Qt.CursorShape.ArrowCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)


def _iou(a, b):
    ax, ay, aw, ah = image_bounds(a.x, a.y, a.w, a.h, getattr(a, 'angle', 0.0) or 0.0)
    bx, by, bw, bh = image_bounds(b.x, b.y, b.w, b.h, getattr(b, 'angle', 0.0) or 0.0)
    ax1, ay1 = ax + aw, ay + ah
    bx1, by1 = bx + bw, by + bh
    iw = max(0, min(ax1, bx1) - max(ax, bx))
    ih = max(0, min(ay1, by1) - max(ay, by))
    inter = iw * ih
    union = aw * ah + bw * bh - inter
    return inter / union if union else 0.0


_DETECTION_LOCK = Lock()


class _DetectionSignals(QObject):
    finished = pyqtSignal(object, object, object)


class _DetectionTask(QRunnable):
    def __init__(self, image, backend, context):
        super().__init__()
        self.image, self.backend, self.context = image, backend, context
        self.cancelled = Event()
        self.signals = _DetectionSignals()

    def run(self):
        results, error = [], None
        try:
            while not self.cancelled.is_set():
                if not _DETECTION_LOCK.acquire(timeout=0.05):
                    continue
                try:
                    if self.cancelled.is_set():
                        return
                    detections = detect_text(self.image, backend=self.backend)
                finally:
                    _DETECTION_LOCK.release()
                if not self.cancelled.is_set():
                    results = regions_from_detections(self.image, self._remaining(detections))
                break
        except Exception as exc:
            error = exc
        finally:
            self.image = None
            self.signals.finished.emit(self, results, error)

    def _remaining(self, detections):
        for detection in detections:
            if self.cancelled.is_set():
                break
            yield detection


class RasterTextInspectorWindow(QDialog):
    groups_changed = pyqtSignal()

    def __init__(self, image_path: str, project, cell, parent=None,
                 undo_stack=None, on_change=None, baseline=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.image_path = image_path
        self.project = project
        self._cell = cell
        self._report = {}              # region id -> status
        self._updating = False
        self._detection = None
        self._closed = False
        self.setWindowTitle(tr("rastertxt_inspector_title"))
        QShortcut(QKeySequence(Qt.Key.Key_F1), self, activated=lambda: show_context_help(self, "text_sizes"))
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowCloseButtonHint |
                            Qt.WindowType.WindowMaximizeButtonHint)
        self.setMinimumSize(820, 560)
        self.resize(1180, 720)
        self._build_ui()
        self._cell_id = getattr(cell, 'id', None)
        self._recorder = SessionRecorder(
            project, self._cell_id, undo_stack,
            lambda before, after: TextMatchSessionCommand(
                project, self._cell_id, before, after, on_change),
            open_state=baseline)
        self._baseline = baseline if baseline is not None else self._recorder.open_state
        self._kept_names = []
        self._refresh_all()
        install_button_feedback(self)

    # ── UI ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter)

        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 8, 0)   # keep content clear of the divider
        head = QHBoxLayout()
        head.addWidget(section_label(tr("rastertxt_preview_label")), 1)
        self._btn_fit = QPushButton(tr("preview_fit"))
        self._btn_fit.setToolTip(tr("preview_fit_tip"))
        self._btn_fit.setEnabled(False)
        self._btn_fit.clicked.connect(self._on_fit)
        head.addWidget(self._btn_fit)
        self._chk_original = QCheckBox(tr("rastertxt_show_original"))
        self._chk_original.toggled.connect(self._on_preview_mode_changed)
        head.addWidget(self._chk_original)
        lv.addLayout(head)
        self._preview_label = RasterTextPreview()
        self._preview_label.region_selected.connect(self._on_preview_selected)
        self._preview_label.view_changed.connect(
            lambda: self._btn_fit.setEnabled(not self._preview_label._zoom.fitted))
        lv.addWidget(self._preview_label, 1)
        self._legend = QLabel(tr("rastertxt_legend"))
        self._legend.setWordWrap(True)
        self._legend.setForegroundRole(QPalette.ColorRole.PlaceholderText)
        lv.addWidget(self._legend)
        splitter.addWidget(left)

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(8, 0, 0, 0)
        rv.setSpacing(8)

        detect_row = QHBoxLayout()
        self._btn_detect = QPushButton(tr("rastertxt_detect_btn"))
        self._btn_detect.clicked.connect(self._on_detect)
        detect_row.addWidget(self._btn_detect)
        self._btn_cancel = QPushButton(tr('rastertxt_cancel'))
        self._btn_cancel.clicked.connect(self._cancel_detection)
        self._btn_cancel.hide()
        detect_row.addWidget(self._btn_cancel)
        self._ocr_status = QLabel()
        self._ocr_status.setStyleSheet("color: palette(link);")
        self._ocr_status.setWordWrap(True)
        detect_row.addWidget(self._ocr_status, 1)
        rv.addLayout(detect_row)

        summary_row = QHBoxLayout()
        self._summary_label = QLabel()
        self._summary_label.setWordWrap(True)
        summary_row.addWidget(self._summary_label, 1)
        self._btn_filter = QPushButton()
        self._btn_filter.setCheckable(True)
        self._btn_filter.toggled.connect(lambda _on: self._refresh_list())
        self._btn_filter.hide()
        summary_row.addWidget(self._btn_filter)
        rv.addLayout(summary_row)

        self._suggest_label = section_label(tr("textmatch_suggest_label"))
        self._suggest_label.hide()
        rv.addWidget(self._suggest_label)
        self._suggest_box = QWidget()
        self._suggest_lay = QVBoxLayout(self._suggest_box)
        self._suggest_lay.setContentsMargins(0, 0, 0, 0)
        self._suggest_lay.setSpacing(2)
        self._suggest_box.hide()
        rv.addWidget(self._suggest_box)

        rv.addWidget(section_label(tr("text_chips_label")))
        self._chip_hint = QLabel()
        self._chip_hint.setWordWrap(True)
        rv.addWidget(self._chip_hint)
        self._groups_widget = TextGroupChips(self.project)
        self._groups_widget.assign_requested.connect(self._on_chip_assign)
        self._groups_widget.new_group_requested.connect(self._on_chip_new_group)
        self._groups_widget.groups_changed.connect(self._on_groups_edited)
        self._groups_widget.members_requested.connect(self._on_chip_members)
        rv.addWidget(self._groups_widget)

        rv.addWidget(section_label(tr("rastertxt_regions_label")))
        self._list = QListWidget()
        self._list.setItemDelegate(RasterTextRegionDelegate(self._list))
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self._list.setMouseTracking(True)
        self._list.setAccessibleName(tr('rastertxt_regions_label'))
        self._list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._on_list_context_menu)
        self._list.itemChanged.connect(self._on_item_toggled)
        self._list.itemSelectionChanged.connect(self._sync_region_controls)
        rv.addWidget(self._list, 2)

        self._adjust_section = CollapsibleSection(tr("textmatch_adjust_label"))
        form = self._adjust_section._form
        self._size_spin = QDoubleSpinBox()
        self._size_spin.setRange(1.0, 5000.0)
        self._size_spin.setDecimals(1)
        self._size_spin.setSuffix(" px")
        self._size_spin.valueChanged.connect(self._on_size_changed)
        form.addRow(tr("rastertxt_size_px"), self._size_spin)
        self._anchor_combo = QComboBox()
        for a in ANCHORS:
            self._anchor_combo.addItem(tr("rastertxt_anchor_" + a), a)
        self._anchor_combo.currentIndexChanged.connect(self._on_anchor_changed)
        form.addRow(tr("rastertxt_anchor"), self._anchor_combo)
        self._chk_vertical = QCheckBox(tr("rastertxt_vertical"))
        self._chk_vertical.toggled.connect(self._on_vertical_toggled)
        form.addRow("", self._chk_vertical)
        self._btn_remove = QPushButton(tr("rastertxt_remove_btn"))
        self._btn_remove.clicked.connect(self._on_remove)
        form.addRow("", self._btn_remove)
        self._adjust_section.set_collapsed(True, animate=False)
        rv.addWidget(self._adjust_section)

        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        rv.addWidget(div)
        self._status_label = QLabel()
        self._status_label.setWordWrap(True)
        self._status_label.setForegroundRole(QPalette.ColorRole.PlaceholderText)
        rv.addWidget(self._status_label)
        footer = QHBoxLayout()
        footer.addStretch(1)
        self._btn_revert = QPushButton(tr("textmatch_revert"))
        self._btn_revert.setToolTip(tr("textmatch_revert_tip"))
        self._btn_revert.clicked.connect(self._on_revert)
        footer.addWidget(self._btn_revert)
        self._btn_done = QPushButton(tr("textmatch_done"))
        self._btn_done.setToolTip(tr("textmatch_done_tip"))
        self._btn_done.clicked.connect(self.close)
        footer.addWidget(self._btn_done)
        rv.addLayout(footer)

        splitter.addWidget(right)
        splitter.setChildrenCollapsible(False)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setSizes([800, 360])
        # Enter in a field (e.g. the size spin box) must not close the window.
        for button in self.findChildren(QPushButton):
            button.setAutoDefault(False)

    # ── Refresh ─────────────────────────────────────────────────────────

    def refresh(self):
        self._recorder.rebase()
        self._refresh_all()

    def _refresh_all(self):
        if self._detection and self._detection.context != self._detection_context():
            self._cancel_detection()
        else:
            self._refresh_ocr_status()
        self._refresh_preview()
        self._refresh_list()
        self._groups_widget.refresh()
        self._update_chip_selection()

    def _refresh_ocr_status(self):
        busy = self._detection is not None
        self._btn_cancel.setVisible(busy)
        if busy:
            self._btn_detect.setEnabled(False)
            self._ocr_status.setText(tr('rastertxt_detecting'))
            return
        from src.app.preferences_dialog import get_pref
        from src.utils.raster_text_ocr import DEFAULT_BACKEND
        reason = backend_status(get_pref("ocr_backend", DEFAULT_BACKEND), get_pref("ocr_command", ""))
        self._btn_detect.setEnabled(reason is None)
        self._ocr_status.setText("" if reason is None else tr("rastertxt_ocr_unavailable").format(reason=reason))

    def _load_image(self):
        try:
            with Image.open(self.image_path) as im:
                return im.convert("RGBA")
        except Exception:
            return None

    def _refresh_preview(self):
        img = self._load_image()
        self._report = {}
        if img is None:
            self._preview_label.set_content(QImage(), [])
            return
        source = img
        masks = {}
        spec = build_raster_override_spec(self.project, self._cell)
        if spec and not self._chk_original.isChecked():
            img, report = apply_raster_text_overrides(img, spec, overlay_masks=masks)
            self._report = {r['id']: r['status'] for r in report}
        overlays = []
        for region in self._cell.raster_text_regions:
            mask = masks.get(region.id)
            if mask is None:
                alpha, foreign, origin = get_raster_text_mask(source, region)
                mask = {'alpha': alpha, 'origin': origin,
                        'protected_mask': foreign, 'protected_origin': origin}
            path = text_envelope_path(mask['alpha'], mask['origin'], mask['protected_mask'],
                                      mask['protected_origin'], vertical=region.vertical)
            status = self._report.get(region.id)
            tooltip = region.text
            if status and status != 'applied':
                tooltip += '\n' + tr('rastertxt_status_' + status)
            elif region.warning:
                tooltip += '\n' + tr('rastertxt_reason_' + region.warning)
            overlays.append({'id': region.id, 'path': path, 'tooltip': tooltip,
                             'enabled': region.enabled and (status is None or status == 'applied'),
                             'color': group_colour(self.project, region.group_id) if region.group_id else None})
        data = img.tobytes('raw', 'RGBA')
        qimg = QImage(data, img.width, img.height, QImage.Format.Format_RGBA8888).copy()
        self._preview_label.set_content(qimg, overlays)
        self._preview_label.set_selected(r.id for r in self._selected_regions())

    def _on_fit(self):
        self._preview_label._zoom.reset()
        self._preview_label.view_changed.emit()
        self._preview_label.update()

    def _on_preview_mode_changed(self):
        self._refresh_preview()
        self._refresh_list()

    def _on_preview_selected(self, region_id, additive):
        self._list.blockSignals(True)
        if not additive:
            self._list.clearSelection()
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == region_id:
                item.setSelected(not item.isSelected() if additive else True)
                self._list.scrollToItem(item)
                break
        self._list.blockSignals(False)
        self._sync_region_controls()

    def _refresh_list(self):
        selected = {i.data(Qt.ItemDataRole.UserRole) for i in self._list.selectedItems()}
        current = self._list.currentItem()
        current_id = current.data(Qt.ItemDataRole.UserRole) if current else None
        self._updating = True
        self._list.clear()
        groups = {g.id: g for g in self.project.svg_text_groups}
        pt_per_px = raster_pt_per_px(self.project, self._cell)
        only_review = self._btn_filter.isChecked()

        def sort_key(r):
            # Source estimate, not the group target, so rows stay put while
            # a group's size is being stepped.
            if r.font_size_px > 0:
                size = r.font_size_px * pt_per_px if pt_per_px else r.font_size_px
            else:
                size = None
            bx, by, _w, _h = image_bounds(r.x, r.y, r.w, r.h,
                                          getattr(r, 'angle', 0.0) or 0.0)
            return (size is None, -(size or 0.0), by, bx)

        for region in sorted(self._cell.raster_text_regions, key=sort_key):
            label = region.text or tr('rastertxt_untitled')
            grp = groups.get(region.group_id)
            status = self._report.get(region.id)
            review = bool(region.warning) or status not in (None, 'applied')
            if not region.enabled:
                state_text = tr('rastertxt_paused_status')
            elif not grp:
                state_text = tr('rastertxt_assign_status')
            elif status and status != 'applied':
                state_text = tr('rastertxt_result_' + status)
            elif status == 'applied':
                state_text = tr('rastertxt_applied_status')
            elif self._chk_original.isChecked():
                state_text = tr('rastertxt_original_status')
            else:
                state_text = tr('rastertxt_ready_status')
            if pt_per_px is not None and region.font_size_px > 0:
                size_text = format_size(region.font_size_px * pt_per_px,
                                        grp.font_size_pt if grp else None,
                                        approx=True)
            else:
                size_text = tr('rastertxt_source_size').format(
                    size=f'{region.font_size_px:.1f}')
            parts = [label,
                     tr('rastertxt_group_badge').format(name=grp.name) if grp
                     else tr('rastertxt_ungrouped'),
                     size_text, state_text]
            if region.warning:
                parts.append(tr('rastertxt_review_status')
                             .format(reason=tr('rastertxt_reason_' + region.warning)))
                parts.append(tr('rastertxt_review_tip'))
            if region.foreign_excluded:
                parts.append(tr('rastertxt_foreign_tip'))
            summary = '\n'.join(parts)
            details = {
                'text': label,
                'colour': group_colour(self.project, grp.id) if grp else None,
                'size': size_text,
                'checkable': True, 'checked': region.enabled,
                'muted': not region.enabled,
                'warning': review,
                'tooltip': summary,
            }
            item = QListWidgetItem()
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if region.enabled else Qt.CheckState.Unchecked)
            item.setData(Qt.ItemDataRole.UserRole, region.id)
            item.setData(REGION_DETAILS_ROLE, details)
            item.setData(Qt.ItemDataRole.AccessibleTextRole, summary)
            item.setToolTip(summary)
            item.setHidden(only_review and not review)
            self._list.addItem(item)
            if region.id in selected:
                item.setSelected(True)
            if region.id == current_id:
                self._list.setCurrentItem(item, QItemSelectionModel.SelectionFlag.NoUpdate)
        self._updating = False
        self._sync_region_controls()
        self._refresh_summary()
        self._refresh_suggest(pt_per_px)
        self._update_footer()

    def _refresh_summary(self):
        summary = raster_summary(self._cell.raster_text_regions, self._report)
        self._summary_label.setText(tr('textmatch_summary_raster').format(
            n=summary['total'], resizing=summary['resizing'],
            review=summary['review']))
        self._btn_filter.blockSignals(True)
        self._btn_filter.setText(tr('textmatch_filter_review').format(n=summary['review']))
        self._btn_filter.setVisible(summary['review'] > 0)
        if summary['review'] == 0:
            self._btn_filter.setChecked(False)
        self._btn_filter.blockSignals(False)

    def _refresh_suggest(self, pt_per_px):
        while self._suggest_lay.count():
            widget = self._suggest_lay.takeAt(0).widget()
            if widget is not None:
                widget.deleteLater()
        items = [] if pt_per_px is None else [
            {'id': r.id, 'size_pt': r.font_size_px * pt_per_px,
             'text': r.text or '', 'flagged': bool(r.warning)}
            for r in self._cell.raster_text_regions
            if not r.group_id and r.font_size_px > 0]
        clusters = size_clusters(items, RASTER_REL_TOL)
        self._suggest_label.setVisible(bool(clusters))
        self._suggest_box.setVisible(bool(clusters))
        for cluster in clusters:
            self._suggest_lay.addWidget(self._suggest_row(cluster))

    def _suggest_row(self, cluster):
        ids = list(cluster['ids'])
        row = QWidget()
        row.setToolTip(tr('textmatch_suggest_tip'))
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        pt = round(cluster['size_pt'], 1)
        title = tr('textmatch_suggest_row').format(
            n=cluster['count'], pt=format_text_size(pt))
        if cluster['flagged']:
            title += ' · ' + tr('textmatch_suggest_review').format(n=cluster['flagged'])
        lbl = QLabel(title)
        font = lbl.font()
        font.setBold(True)
        lbl.setFont(font)
        lay.addWidget(lbl)
        samples = QLabel(', '.join(cluster['samples']))
        samples.setWordWrap(True)
        samples.setForegroundRole(QPalette.ColorRole.PlaceholderText)
        lay.addWidget(samples, 1)
        btn = QToolButton()
        btn.setText(tr('textmatch_assign_btn'))
        btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        btn.setAutoRaise(True)
        menu = QMenu(btn)
        populate_group_menu(
            menu, self.project,
            lambda gid, _ids=ids: self._assign_cluster(gid, _ids),
            lambda _ids=ids, _pt=cluster['size_pt']: self._cluster_new_group(_ids, _pt),
            lambda: None, can_remove=False)
        actions = menu.actions()
        if actions:
            menu.removeAction(actions[-1])           # Remove-from-group
            if len(actions) > 1 and actions[-2].isSeparator():
                menu.removeAction(actions[-2])
        btn.setMenu(menu)
        lay.addWidget(btn)
        row.mousePressEvent = lambda _e, _ids=ids: self._select_region_ids(_ids)
        return row

    def _select_region_ids(self, ids):
        self._list.blockSignals(True)
        self._list.clearSelection()
        first = None
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) in ids:
                item.setSelected(True)
                if first is None:
                    first = item
        self._list.blockSignals(False)
        if first is not None:
            self._list.scrollToItem(first)
        self._sync_region_controls()

    def _assign_cluster(self, group_id, ids):
        wanted = set(ids)
        regions = [r for r in self._cell.raster_text_regions if r.id in wanted]
        if assign_raster(regions, group_id, enable_flagged=False):
            self._changed()

    def _cluster_new_group(self, ids, size_pt):
        size = round(size_pt * 2) / 2
        gid = new_svg_group(self.project,
                            tr('svgtxt_plot_group_name').format(pt=format_text_size(size)),
                            size)
        self._assign_cluster(gid, ids)

    def _other_refs(self):
        return {r.group_id
                for c in self.project.get_all_leaf_cells()
                if c.id != self._cell_id
                for r in c.raster_text_regions if r.group_id}

    def _live_cell(self):
        return self.project.find_cell_by_id(self._cell_id) or self._cell

    def _revert_target(self):
        return scoped_revert(capture(self.project, self._live_cell()),
                             self._baseline,
                             {"kind": "raster", "cell_id": self._cell_id},
                             self._other_refs())

    def _update_footer(self):
        new_state, _kept = self._revert_target()
        changed = new_state != capture(self.project, self._live_cell())
        text = tr('textmatch_changed_status' if changed
                  else 'textmatch_live_status')
        if self._kept_names:
            text += ' ' + tr('textmatch_revert_kept').format(
                names=', '.join(self._kept_names))
            self._kept_names = []
        self._status_label.setText(text)
        self._btn_revert.setEnabled(changed)

    def _on_revert(self):
        new_state, kept = self._revert_target()
        restore(self.project, self._cell_id, new_state)
        self._kept_names = kept
        self._changed()

    def _selected_regions(self):
        ids = {i.data(Qt.ItemDataRole.UserRole) for i in self._list.selectedItems()}
        return [r for r in self._cell.raster_text_regions if r.id in ids]

    def _sync_region_controls(self):
        if self._updating:
            return
        self._update_chip_selection()
        regions = self._selected_regions()
        self._preview_label.set_selected(r.id for r in regions)
        self._adjust_section.set_title(
            tr("textmatch_adjust_label") + (f" ({len(regions)})" if regions else ""))
        enabled = bool(regions)
        for w in (self._size_spin, self._anchor_combo, self._chk_vertical, self._btn_remove):
            w.setEnabled(enabled)
        # The vertical toggle only applies to axis-aligned text; arbitrary
        # angles are described by region.angle.
        if enabled and any(getattr(r, 'angle', 0.0) for r in regions):
            self._chk_vertical.setEnabled(False)
        if not regions:
            return
        self._updating = True
        r = regions[0]
        self._size_spin.setValue(r.font_size_px)
        self._anchor_combo.setCurrentIndex(max(0, self._anchor_combo.findData(r.anchor)))
        self._chk_vertical.setChecked(r.vertical)
        self._updating = False

    def _changed(self):
        self._recorder.record()
        self._cancel_detection()
        self.groups_changed.emit()
        self._refresh_preview()
        self._refresh_list()
        self._groups_widget.refresh()
        self._update_chip_selection()

    def _update_chip_selection(self):
        count = len(self._selected_regions())
        self._groups_widget.set_selection_info(count, None)
        self._chip_hint.setText(chip_hint(count, len(self.project.svg_text_groups)))

    # ── Slots ───────────────────────────────────────────────────────────

    def _detection_context(self):
        try:
            stat = os.stat(self.image_path)
            stamp = (stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size)
        except OSError:
            stamp = None
        return (id(self.project), id(self._cell), self.image_path, stamp,
                id(self.project.find_cell_by_id(self._cell.id)), deepcopy(self._cell.to_dict()))

    def _on_detect(self):
        if self._closed or self._detection is not None:
            return
        try:
            context = self._detection_context()
            img = self._load_image()
            if img is None:
                self._refresh_ocr_status()
                self._ocr_status.setText(tr('svgtxt_preview_failed'))
                return
            backend = configured_backend()
            if backend is None:
                raise OcrUnavailable('No OCR backend is configured')
            if context != self._detection_context():
                self._ocr_status.setText(tr('rastertxt_detection_cancelled'))
                return
            task = _DetectionTask(img, backend, context)
            task.signals.finished.connect(self._detection_finished, Qt.ConnectionType.QueuedConnection)
            self.destroyed.connect(lambda _=None, cancelled=task.cancelled: cancelled.set())
            self._detection = task
            self._refresh_ocr_status()
            QThreadPool.globalInstance().start(task)
        except Exception as exc:
            self._detection = None
            self._refresh_ocr_status()
            self._detection_error(exc)

    def _detection_error(self, error):
        message = str(error) if isinstance(error, OcrUnavailable) else tr('rastertxt_ocr_failed').format(error=error)
        QMessageBox.warning(self, tr('rastertxt_inspector_title'), message)

    def _cancel_detection(self):
        if self._detection is None:
            return
        self._detection.cancelled.set()
        self._detection = None
        self._refresh_ocr_status()
        self._ocr_status.setText(tr('rastertxt_detection_cancelled'))

    def done(self, result):
        self._closed = True
        self._cancel_detection()
        super().done(result)

    def closeEvent(self, event):
        self._closed = True
        self._cancel_detection()
        super().closeEvent(event)

    @pyqtSlot(object, object, object)
    def _detection_finished(self, task, results, error):
        if self._closed or task is not self._detection:
            return
        self._detection = None
        self._refresh_ocr_status()
        if task.cancelled.is_set() or task.context != self._detection_context():
            self._ocr_status.setText(tr('rastertxt_detection_cancelled'))
            return
        if error is not None:
            self._detection_error(error)
            return
        # Keep regions the user already assigned; refresh the rest. Flagged
        # detections are kept too (unticked) so the user can judge them.
        existing = self._cell.raster_text_regions
        kept = [r for r in existing if r.group_id]
        unmatched = [r for r in existing if not r.group_id]
        for region, _reason in results:
            if any(_iou(region, k) > 0.3 for k in kept):
                continue
            match = max(unmatched, key=lambda r: _iou(region, r), default=None)
            if match is not None and _iou(region, match) > 0.3:
                unmatched.remove(match)
                region.id = match.id
                # An old axis-aligned match must not overwrite the new
                # rotated analysis (or vice versa) — same angle only.
                if getattr(match, 'angle', 0.0) == getattr(region, 'angle', 0.0):
                    region.enabled = match.enabled
                    region.font_size_px, region.anchor = match.font_size_px, match.anchor
                    region.vertical = match.vertical
            kept.append(region)
        self._cell.raster_text_regions = kept
        self._changed()
        if not results:
            QMessageBox.information(self, tr('rastertxt_inspector_title'), tr('rastertxt_none_found'))

    def _on_item_toggled(self, item):
        if self._updating:
            return
        rid = item.data(Qt.ItemDataRole.UserRole)
        region = next((r for r in self._cell.raster_text_regions if r.id == rid), None)
        if region:
            region.enabled = item.checkState() == Qt.CheckState.Checked
            self._changed()

    def _on_size_changed(self, val):
        if self._updating:
            return
        for r in self._selected_regions():
            r.font_size_px = val
        self._changed()

    def _on_anchor_changed(self, _idx):
        if self._updating:
            return
        for r in self._selected_regions():
            r.anchor = self._anchor_combo.currentData()
        self._changed()

    def _on_vertical_toggled(self, on):
        if self._updating:
            return
        for r in self._selected_regions():
            if getattr(r, 'angle', 0.0):
                continue
            r.vertical = on
        self._changed()

    def _on_remove(self):
        ids = {r.id for r in self._selected_regions()}
        self._cell.raster_text_regions = [r for r in self._cell.raster_text_regions if r.id not in ids]
        self._changed()

    def _on_chip_assign(self, group_id):
        regions = self._selected_regions()
        if group_id is None:
            ungroup_raster(regions)
        else:
            assign_raster(regions, group_id)
        self._changed()

    def _on_chip_new_group(self):
        regions = self._selected_regions()
        gid = new_svg_group(self.project, tr("svgtxt_default_group_name"), 12.0)
        assign_raster(regions, gid)
        self._changed()

    def _on_list_context_menu(self, pos):
        item = self._list.itemAt(pos)
        if item is not None and not item.isSelected():
            self._list.clearSelection()
            item.setSelected(True)
        regions = self._selected_regions()
        if not regions:
            return
        menu = QMenu(self)
        populate_group_menu(
            menu, self.project, self._on_chip_assign, self._on_chip_new_group,
            lambda: self._on_chip_assign(None),
            can_remove=any(r.group_id for r in regions),
        )
        menu.exec(self._list.viewport().mapToGlobal(pos))

    def _on_chip_members(self, group_id):
        for index in range(self._list.count()):
            item = self._list.item(index)
            region = next((r for r in self._cell.raster_text_regions
                           if r.id == item.data(Qt.ItemDataRole.UserRole)), None)
            item.setSelected(region is not None and region.group_id == group_id)

    def _on_groups_edited(self):
        self._groups_widget.refresh()
        self._changed()
