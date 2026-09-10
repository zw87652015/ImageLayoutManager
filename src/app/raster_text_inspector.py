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
    QLabel, QComboBox, QDoubleSpinBox, QCheckBox, QSplitter, QWidget, QScrollArea,
    QFrame, QSizePolicy, QMessageBox,
)
from PyQt6.QtCore import (
    Qt, pyqtSignal, pyqtSlot, QRectF, QItemSelectionModel, QObject, QRunnable, QThreadPool,
)
from PyQt6.QtGui import QPainter, QImage, QPen, QColor, QPalette, QTransform
from PIL import Image

from src.app.i18n import tr
from src.app.motion import MotionTween, install_button_feedback
from src.app.text_groups_widget import TextGroupsWidget, section_label
from src.utils.raster_text_ocr import configured_backend, detect_text, OcrUnavailable, backend_status
from src.utils.raster_text_utils import (
    apply_raster_text_overrides, build_raster_override_spec, regions_from_detections,
    get_raster_text_mask, ANCHORS,
)
from src.app.raster_text_overlay import text_envelope_path
from src.app.raster_text_region_delegate import RasterTextRegionDelegate, REGION_DETAILS_ROLE


class RasterTextPreview(QWidget):
    region_selected = pyqtSignal(str, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._image = QImage()
        self._overlays = []
        self._selected = set()
        self._hovered = None
        self._feedback = {}
        self._feedback_targets = {}
        self.setMinimumSize(280, 220)
        self.setMouseTracking(True)
        self.setAccessibleName(tr('rastertxt_preview_label'))

    def set_content(self, image, overlays):
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
        bounds = QRectF(self.rect()).adjusted(8, 8, -8, -8)
        scale = min(bounds.width() / self._image.width(), bounds.height() / self._image.height())
        transform.translate(bounds.center().x() - self._image.width() * scale / 2,
                            bounds.center().y() - self._image.height() * scale / 2)
        transform.scale(scale, scale)
        return transform

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), self.palette().color(QPalette.ColorRole.AlternateBase))
        if self._image.isNull():
            painter.setPen(self.palette().color(QPalette.ColorRole.Text))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, tr('svgtxt_preview_failed'))
            return
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        transform = self.image_transform()
        image_rect = transform.mapRect(QRectF(0, 0, self._image.width(), self._image.height()))
        painter.drawImage(image_rect, self._image)
        painter.setClipRect(image_rect)
        accent = self.palette().color(QPalette.ColorRole.Highlight)
        for overlay in sorted(self._overlays, key=lambda o: o['id'] in self._selected):
            selected = overlay['id'] in self._selected
            hovered = overlay['id'] == self._hovered
            fill_tween, border_tween = self._feedback[overlay['id']]
            fill = QColor(accent)
            fill.setAlpha(round(fill_tween.value))
            border = QColor(accent)
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
        overlay = self._hit_test(event.position())
        hovered = overlay['id'] if overlay else None
        if hovered != self._hovered:
            self._hovered = hovered
            self.setToolTip(overlay['tooltip'] if overlay else '')
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
        if event.button() == Qt.MouseButton.LeftButton:
            overlay = self._hit_test(event.position())
            self.region_selected.emit(overlay['id'] if overlay else '',
                                      bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier))
            event.accept()
            return
        super().mousePressEvent(event)


def _iou(a, b):
    ax1, ay1 = a.x + a.w, a.y + a.h
    bx1, by1 = b.x + b.w, b.y + b.h
    iw = max(0, min(ax1, bx1) - max(a.x, b.x))
    ih = max(0, min(ay1, by1) - max(a.y, b.y))
    inter = iw * ih
    union = a.w * a.h + b.w * b.h - inter
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

    def __init__(self, image_path: str, project, cell, parent=None):
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
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowCloseButtonHint |
                            Qt.WindowType.WindowMaximizeButtonHint)
        self.setMinimumSize(820, 560)
        self.resize(1040, 680)
        self._build_ui()
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
        lv.setContentsMargins(0, 0, 0, 0)
        head = QHBoxLayout()
        head.addWidget(section_label(tr("rastertxt_preview_label")), 1)
        self._chk_original = QCheckBox(tr("rastertxt_show_original"))
        self._chk_original.toggled.connect(self._on_preview_mode_changed)
        head.addWidget(self._chk_original)
        lv.addLayout(head)
        self._preview_label = RasterTextPreview()
        self._preview_label.region_selected.connect(self._on_preview_selected)
        scroll = QScrollArea()
        scroll.setWidget(self._preview_label)
        scroll.setWidgetResizable(True)
        lv.addWidget(scroll, 1)
        self._legend = QLabel(tr("rastertxt_legend"))
        self._legend.setWordWrap(True)
        self._legend.setForegroundRole(QPalette.ColorRole.PlaceholderText)
        lv.addWidget(self._legend)
        splitter.addWidget(left)

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
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
        self._ocr_status.setStyleSheet("color: #b07800;")
        self._ocr_status.setWordWrap(True)
        detect_row.addWidget(self._ocr_status, 1)
        rv.addLayout(detect_row)

        rv.addWidget(section_label(tr("rastertxt_regions_label")))
        self._list = QListWidget()
        self._list.setItemDelegate(RasterTextRegionDelegate(self._list))
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self._list.setMouseTracking(True)
        self._list.setAccessibleName(tr('rastertxt_regions_label'))
        self._list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self._list.itemChanged.connect(self._on_item_toggled)
        self._list.itemSelectionChanged.connect(self._sync_region_controls)
        rv.addWidget(self._list, 2)

        ctl = QHBoxLayout()
        ctl.addWidget(QLabel(tr("rastertxt_size_px") + ":"))
        self._size_spin = QDoubleSpinBox()
        self._size_spin.setRange(1.0, 5000.0)
        self._size_spin.setDecimals(1)
        self._size_spin.setSuffix(" px")
        self._size_spin.valueChanged.connect(self._on_size_changed)
        ctl.addWidget(self._size_spin)
        ctl.addWidget(QLabel(tr("rastertxt_anchor") + ":"))
        self._anchor_combo = QComboBox()
        for a in ANCHORS:
            self._anchor_combo.addItem(tr("rastertxt_anchor_" + a), a)
        self._anchor_combo.currentIndexChanged.connect(self._on_anchor_changed)
        ctl.addWidget(self._anchor_combo)
        self._chk_vertical = QCheckBox(tr("rastertxt_vertical"))
        self._chk_vertical.toggled.connect(self._on_vertical_toggled)
        ctl.addWidget(self._chk_vertical)
        self._btn_remove = QPushButton(tr("rastertxt_remove_btn"))
        self._btn_remove.clicked.connect(self._on_remove)
        ctl.addWidget(self._btn_remove)
        rv.addLayout(ctl)

        assign_row = QHBoxLayout()
        assign_row.addWidget(QLabel(tr("svgtxt_assign_to") + ":"))
        self._group_combo = QComboBox()
        self._group_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        assign_row.addWidget(self._group_combo, 1)
        btn_assign = QPushButton(tr("svgtxt_assign_btn"))
        btn_assign.clicked.connect(self._on_assign)
        assign_row.addWidget(btn_assign)
        btn_ungroup = QPushButton(tr("svgtxt_remove_from_group_btn"))
        btn_ungroup.clicked.connect(self._on_ungroup)
        assign_row.addWidget(btn_ungroup)
        rv.addLayout(assign_row)

        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setStyleSheet("color: #ccc;")
        rv.addWidget(div)

        self._groups_widget = TextGroupsWidget(self.project)
        self._groups_widget.groups_changed.connect(self._on_groups_edited)
        self._groups_widget.group_added.connect(self._on_group_added)
        rv.addWidget(self._groups_widget, 1)

        splitter.addWidget(right)
        splitter.setSizes([520, 500])

    # ── Refresh ─────────────────────────────────────────────────────────

    def refresh(self):
        self._refresh_all()

    def _refresh_all(self):
        if self._detection and self._detection.context != self._detection_context():
            self._cancel_detection()
        else:
            self._refresh_ocr_status()
        self._refresh_preview()
        self._refresh_list()
        self._groups_widget.fill_combo(self._group_combo)
        self._groups_widget.refresh()

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
                             'enabled': region.enabled and (status is None or status == 'applied')})
        data = img.tobytes('raw', 'RGBA')
        qimg = QImage(data, img.width, img.height, QImage.Format.Format_RGBA8888).copy()
        self._preview_label.set_content(qimg, overlays)
        self._preview_label.set_selected(r.id for r in self._selected_regions())

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
        groups = {g.id: g.name for g in self.project.svg_text_groups}
        for region in self._cell.raster_text_regions:
            label = region.text or tr('rastertxt_untitled')
            grp = groups.get(region.group_id)
            status = self._report.get(region.id)
            severity = 'info'
            if not region.enabled:
                state_text = tr('rastertxt_paused_status')
            elif not grp:
                state_text = tr('rastertxt_assign_status')
            elif status and status != 'applied':
                state_text = tr('rastertxt_result_' + status)
                severity = 'warning'
            elif status == 'applied':
                state_text = tr('rastertxt_applied_status')
                severity = 'applied'
            elif self._chk_original.isChecked():
                state_text = tr('rastertxt_original_status')
            else:
                state_text = tr('rastertxt_ready_status')
            details = {
                'text': label, 'group': grp,
                'size': tr('rastertxt_source_size').format(size=f'{region.font_size_px:.1f}'),
                'status': state_text, 'severity': severity,
                'warning': tr('rastertxt_reason_' + region.warning) if region.warning else '',
                'note': tr('rastertxt_preserved_status') if region.foreign_excluded else '',
            }
            parts = [label, tr('rastertxt_group_badge').format(name=grp) if grp else tr('rastertxt_ungrouped'),
                     details['size'], state_text]
            if details['warning']:
                parts.append(tr('rastertxt_review_status').format(reason=details['warning']))
                parts.append(tr('rastertxt_review_tip'))
            if details['note']:
                parts.append(tr('rastertxt_foreign_tip'))
            summary = '\n'.join(parts)
            item = QListWidgetItem(summary)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if region.enabled else Qt.CheckState.Unchecked)
            item.setData(Qt.ItemDataRole.UserRole, region.id)
            item.setData(REGION_DETAILS_ROLE, details)
            item.setData(Qt.ItemDataRole.AccessibleTextRole, summary)
            item.setToolTip(summary)
            self._list.addItem(item)
            if region.id in selected:
                item.setSelected(True)
            if region.id == current_id:
                self._list.setCurrentItem(item, QItemSelectionModel.SelectionFlag.NoUpdate)
        self._list.itemDelegate().set_regions({r.id: groups.get(r.group_id)
                                               for r in self._cell.raster_text_regions})
        self._updating = False
        self._sync_region_controls()

    def _selected_regions(self):
        ids = {i.data(Qt.ItemDataRole.UserRole) for i in self._list.selectedItems()}
        return [r for r in self._cell.raster_text_regions if r.id in ids]

    def _sync_region_controls(self):
        if self._updating:
            return
        regions = self._selected_regions()
        self._preview_label.set_selected(r.id for r in regions)
        enabled = bool(regions)
        for w in (self._size_spin, self._anchor_combo, self._chk_vertical, self._btn_remove):
            w.setEnabled(enabled)
        if not regions:
            return
        self._updating = True
        r = regions[0]
        self._size_spin.setValue(r.font_size_px)
        self._anchor_combo.setCurrentIndex(max(0, self._anchor_combo.findData(r.anchor)))
        self._chk_vertical.setChecked(r.vertical)
        self._updating = False

    def _changed(self):
        self._cancel_detection()
        self.groups_changed.emit()
        self._refresh_preview()
        self._refresh_list()

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
                region.id, region.enabled = match.id, match.enabled
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
            r.vertical = on
        self._changed()

    def _on_remove(self):
        ids = {r.id for r in self._selected_regions()}
        self._cell.raster_text_regions = [r for r in self._cell.raster_text_regions if r.id not in ids]
        self._changed()

    def _on_assign(self):
        gid = self._group_combo.currentData()
        regions = self._selected_regions()
        if not gid or not regions:
            return
        for r in regions:
            r.group_id = gid
            r.enabled = True
        self._changed()

    def _on_ungroup(self):
        for r in self._selected_regions():
            r.group_id = None
        self._changed()

    def _on_groups_edited(self):
        self._groups_widget.fill_combo(self._group_combo)
        self._changed()

    def _on_group_added(self, gid):
        self._groups_widget.fill_combo(self._group_combo)
        idx = self._group_combo.findData(gid)
        if idx >= 0:
            self._group_combo.setCurrentIndex(idx)
