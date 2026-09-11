import os
import tempfile
import threading
import time
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PIL import Image, ImageDraw
from PyQt6 import sip
from PyQt6.QtCore import QCoreApplication, QEvent, QPointF, QThreadPool, QTimer, Qt
from PyQt6.QtGui import QImage, QPainterPath
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from src.app.i18n import tr
from src.app.motion import motion_duration, motion_policy, set_motion_mode
from src.app.raster_text_inspector import RasterTextInspectorWindow, RasterTextPreview
from src.app.raster_text_region_delegate import REGION_DETAILS_ROLE
from src.model.data_model import Cell, Project, RasterTextRegion, SvgTextGroup
from src.utils.raster_text_ocr import DetectedText, OcrUnavailable
from src.utils.raster_text_utils import regions_from_detections


class FakeBackend:
    def __init__(self, detections=(), error=None):
        self.detections, self.error = detections, error
        self.started, self.release = threading.Event(), threading.Event()
        self.thread = None
        self.pixels = None

    def detect(self, image):
        self.thread = threading.get_ident()
        self.pixels = image.tobytes()
        self.started.set()
        if not self.release.wait(3):
            raise TimeoutError('Test backend was not released')
        if self.error:
            raise self.error
        return self.detections


class TextMotionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        for name, kwargs in (
            ('src.app.motion.QSettings', {}),
            ('src.app.motion.system_reduced_motion', {'return_value': False}),
            ('src.app.preferences_dialog.get_pref', {'side_effect': lambda key, default: default}),
            ('src.app.raster_text_inspector.backend_status', {'return_value': None}),
        ):
            mock = patch(name, **kwargs)
            value = mock.start()
            if name.endswith('QSettings'):
                value.return_value.value.side_effect = lambda key, default: default
            self.addCleanup(mock.stop)
        policy = motion_policy()
        self.saved_policy = policy.mode, policy.system_reduced
        self.addCleanup(self.restore_policy)
        set_motion_mode('standard')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'panel.png'
        self.image = Image.new('RGBA', (200, 100), 'white')
        draw = ImageDraw.Draw(self.image)
        draw.rectangle((20, 25, 27, 43), fill='black')
        draw.rectangle((32, 32, 40, 43), fill='black')
        draw.rectangle((110, 25, 118, 43), fill='black')
        self.image.save(self.path)
        self.region = RasterTextRegion(x=17, y=22, w=27, h=25, text='Aa',
                                       font_size_px=27, background='#ffffff')
        self.group = SvgTextGroup(name='Labels', font_size_pt=12)
        self.cell = Cell(image_path=str(self.path), raster_text_regions=[self.region])
        self.project = Project(cells=[self.cell], svg_text_groups=[self.group])
        self.widgets, self.backends = [], []

    def restore_policy(self):
        policy = motion_policy()
        set_motion_mode(self.saved_policy[0])
        policy.system_reduced = self.saved_policy[1]

    def tearDown(self):
        for widget in self.widgets:
            if not sip.isdeleted(widget):
                widget.close()
        for backend in self.backends:
            backend.release.set()
        self.assertTrue(QThreadPool.globalInstance().waitForDone(4000))
        self.app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def wait_for(self, predicate, timeout=2):
        deadline = time.monotonic() + timeout
        while not predicate() and time.monotonic() < deadline:
            QTest.qWait(10)
        self.assertTrue(predicate(), 'Timed out waiting for UI/worker state')

    def dialog(self):
        dialog = RasterTextInspectorWindow(str(self.path), self.project, self.cell)
        self.widgets.append(dialog)
        dialog.show()
        self.app.processEvents()
        return dialog

    def preview(self):
        preview = RasterTextPreview()
        self.widgets.append(preview)
        image = QImage(200, 100, QImage.Format.Format_RGB32)
        image.fill(Qt.GlobalColor.white)
        path = QPainterPath()
        path.addRoundedRect(20, 20, 40, 30, 3, 3)
        preview.set_content(image, [{'id': 'r', 'path': path, 'enabled': True, 'tooltip': 'Aa'}])
        preview.show()
        self.app.processEvents()
        return preview, image, path

    def start_detection(self, dialog, detections=None, error=None):
        backend = FakeBackend(detections if detections is not None else [DetectedText(17, 22, 27, 25, 'Aa')], error)
        self.backends.append(backend)
        with patch('src.app.raster_text_inspector.configured_backend', return_value=backend):
            dialog._on_detect()
        self.wait_for(backend.started.is_set)
        return backend, dialog._detection

    def test_overlay_feedback_changes_only_alpha_and_identity_is_immediate(self):
        preview, image, path = self.preview()
        fill, border = preview._feedback['r']
        preview.set_selected(['r'])
        self.assertEqual(preview._selected, {'r'})
        self.assertEqual(fill.value, 22)
        self.assertEqual(preview._overlays[0]['path'], path)
        self.assertEqual(preview._image, image)
        QTest.qWait(35)
        self.assertGreater(fill.value, 22)
        self.assertLess(fill.value, 55)
        self.assertGreater(border.value, 170)
        QTest.qWait(100)
        self.assertEqual(fill.value, 55)
        self.assertEqual(border.value, 255)
        self.assertEqual(preview._overlays[0]['path'], path)
        preview.set_selected([])
        QTest.qWait(20)
        preview.set_selected(['r'])
        QTest.qWait(130)
        self.assertEqual(fill.value, 55)

    def test_policy_off_reduced_and_live_changes(self):
        preview, _, _ = self.preview()
        fill = preview._feedback['r'][0]
        set_motion_mode('off')
        preview.set_selected(['r'])
        self.assertEqual(fill.value, 55)
        preview.set_selected([])
        self.assertEqual(fill.value, 22)
        set_motion_mode('reduced')
        self.assertLessEqual(motion_duration(100), 70)
        preview.set_selected(['r'])
        self.assertEqual(fill._animation.duration(), 70)
        QTest.qWait(90)
        self.assertEqual(fill.value, 55)
        set_motion_mode('standard')
        preview.set_selected([])
        set_motion_mode('off')
        self.assertEqual(fill.value, 22)

    def test_replacement_content_and_geometry_are_final_and_deleted_tweens_are_freed(self):
        preview, image, _ = self.preview()
        preview.set_selected(['r'])
        tween = preview._feedback['r'][0]
        next_image = image.copy()
        next_image.fill(Qt.GlobalColor.red)
        next_path = QPainterPath()
        next_path.addRect(100, 20, 30, 30)
        preview.set_content(next_image, [{'id': 'r', 'path': next_path, 'enabled': True, 'tooltip': ''}])
        self.assertEqual(preview._image, next_image)
        self.assertEqual(preview._overlays[0]['path'], next_path)
        self.assertIsNone(preview._hit_test(preview.image_transform().map(QPointF(30, 30))))
        self.assertEqual(preview._hit_test(preview.image_transform().map(QPointF(110, 30)))['id'], 'r')
        preview.set_content(next_image, [])
        self.assertEqual(preview._feedback, {})
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.assertTrue(sip.isdeleted(tween))

    def test_selection_hover_resize_and_motion_do_not_process_content(self):
        dialog = self.dialog()
        preview = dialog._preview_label
        with patch.object(dialog, '_load_image') as load, \
                patch('src.app.raster_text_inspector.detect_text') as detect, \
                patch('src.app.raster_text_inspector.apply_raster_text_overrides') as apply, \
                patch('src.app.raster_text_inspector.get_raster_text_mask') as mask:
            dialog._list.item(0).setSelected(True)
            self.assertEqual(preview._selected, {self.region.id})
            point = preview.image_transform().map(QPointF(24, 35)).toPoint()
            QTest.mouseMove(preview, point)
            self.assertEqual(preview._hovered, self.region.id)
            dialog.resize(1150, 720)
            QTest.qWait(140)
            for mock in (load, detect, apply, mask):
                mock.assert_not_called()

    def test_rows_badges_and_check_states_are_immediate_with_retained_feedback(self):
        dialog = self.dialog()
        delegate = dialog._list.itemDelegate()
        item = dialog._list.item(0)
        item.setSelected(True)
        dialog._list.viewport().grab()
        selection = delegate._feedback[self.region.id][0]
        self.assertLess(selection.value, 1)
        QTest.qWait(140)
        self.assertEqual(selection.value, 1)
        dialog._group_combo.setCurrentIndex(dialog._group_combo.findData(self.group.id))
        dialog._on_assign()
        self.assertEqual(dialog._list.item(0).data(REGION_DETAILS_ROLE)['group'], self.group.name)
        self.assertIs(delegate._feedback[self.region.id][0], selection)
        self.assertGreater(delegate._feedback[self.region.id][3].value, 0)
        set_motion_mode('off')
        self.assertEqual(delegate._feedback[self.region.id][3].value, 0)
        dialog._list.item(0).setCheckState(Qt.CheckState.Unchecked)
        self.assertFalse(self.region.enabled)
        dialog._on_remove()
        self.assertEqual(delegate._feedback, {})
        self.assertEqual(dialog._preview_label._feedback, {})
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.assertTrue(sip.isdeleted(selection))

    def test_detection_and_analysis_are_async_snapshotted_and_commit_on_ui_thread(self):
        self.region.group_id, self.region.enabled = self.group.id, False
        dialog = self.dialog()
        before = deepcopy(self.cell.to_dict())
        analysis_threads, delivery_threads, heartbeat = [], [], []
        dialog.groups_changed.connect(lambda: delivery_threads.append(threading.get_ident()))

        def analyze(image, detections):
            analysis_threads.append(threading.get_ident())
            return regions_from_detections(image, detections)

        with patch('src.app.raster_text_inspector.regions_from_detections', side_effect=analyze):
            backend, task = self.start_detection(dialog, [DetectedText(17, 22, 27, 25, 'Aa'),
                                                           DetectedText(107, 22, 15, 25, 'B')])
            QTimer.singleShot(0, lambda: heartbeat.append(True))
            self.wait_for(lambda: heartbeat)
            self.assertEqual(self.cell.to_dict(), before)
            self.assertFalse(dialog._btn_detect.isEnabled())
            self.assertTrue(dialog._btn_cancel.isVisible())
            self.assertEqual(dialog._ocr_status.text(), tr('rastertxt_detecting'))
            self.assertEqual(backend.pixels, self.image.tobytes())
            backend.release.set()
            self.wait_for(lambda: dialog._detection is None)
        self.assertNotEqual(backend.thread, threading.get_ident())
        self.assertEqual(analysis_threads, [backend.thread])
        self.assertEqual(delivery_threads, [threading.get_ident()])
        self.assertEqual(len(self.cell.raster_text_regions), 2)
        self.assertIs(self.cell.raster_text_regions[0], self.region)
        self.assertFalse(self.region.enabled)
        self.assertEqual(self.region.group_id, self.group.id)
        self.assertEqual(self.project.svg_text_groups, [self.group])
        self.assertTrue(dialog._btn_detect.isEnabled())
        self.assertFalse(dialog._btn_cancel.isVisible())
        self.assertEqual(dialog._ocr_status.text(), '')

    def test_redetection_preserves_matching_unassigned_enable_and_manual_states(self):
        self.region.enabled, self.region.anchor = False, 'right'
        dialog = self.dialog()
        backend, _ = self.start_detection(dialog)
        backend.release.set()
        self.wait_for(lambda: dialog._detection is None)
        current = self.cell.raster_text_regions[0]
        self.assertEqual((current.id, current.enabled, current.anchor, current.font_size_px),
                         (self.region.id, False, 'right', 27))

    def test_cancel_is_immediate_and_late_work_cannot_replace_retry(self):
        dialog = self.dialog()
        before = deepcopy(self.cell.to_dict())
        backend, task = self.start_detection(dialog)
        QTest.mouseClick(dialog._btn_cancel, Qt.MouseButton.LeftButton)
        self.assertIsNone(dialog._detection)
        self.assertTrue(task.cancelled.is_set())
        self.assertTrue(dialog._btn_detect.isEnabled())
        self.assertFalse(dialog._btn_cancel.isVisible())
        self.assertEqual(dialog._ocr_status.text(), tr('rastertxt_detection_cancelled'))
        retry = FakeBackend([DetectedText(107, 22, 15, 25, 'New')])
        self.backends.append(retry)
        with patch('src.app.raster_text_inspector.configured_backend', return_value=retry):
            dialog._on_detect()
        current_task = dialog._detection
        backend.release.set()
        self.wait_for(retry.started.is_set)
        self.app.processEvents()
        self.assertIs(dialog._detection, current_task)
        self.assertEqual(self.cell.to_dict(), before)
        retry.release.set()
        self.wait_for(lambda: dialog._detection is None)
        self.assertEqual([r.text for r in self.cell.raster_text_regions], ['New'])

    def test_cancel_during_analysis_and_edits_do_not_apply_partial_results(self):
        dialog = self.dialog()
        started, release = threading.Event(), threading.Event()
        candidate = deepcopy(self.region)
        candidate.text = 'Obsolete'

        def analyze(image, detections):
            started.set()
            if not release.wait(3):
                raise TimeoutError('Test analysis was not released')
            return [(candidate, None)]

        try:
            with patch('src.app.raster_text_inspector.regions_from_detections', side_effect=analyze):
                backend, task = self.start_detection(dialog)
                backend.release.set()
                self.wait_for(started.is_set)
                dialog._list.item(0).setCheckState(Qt.CheckState.Unchecked)
                self.assertTrue(task.cancelled.is_set())
                self.assertIsNone(dialog._detection)
                self.assertFalse(self.region.enabled)
                release.set()
                self.assertTrue(QThreadPool.globalInstance().waitForDone(2000))
                self.app.processEvents()
                self.assertIs(self.cell.raster_text_regions[0], self.region)
                self.assertEqual(self.region.text, 'Aa')
        finally:
            release.set()

    def test_missing_image_unavailable_backend_and_duplicate_requests_are_safe(self):
        dialog = self.dialog()
        with patch.object(dialog, '_load_image', return_value=None), \
                patch('src.app.raster_text_inspector.configured_backend') as backend:
            dialog._on_detect()
            backend.assert_not_called()
            self.assertIsNone(dialog._detection)
            self.assertEqual(dialog._ocr_status.text(), tr('svgtxt_preview_failed'))
        with patch('src.app.raster_text_inspector.configured_backend', return_value=None), \
                patch('src.app.raster_text_inspector.QMessageBox.warning') as warning:
            dialog._on_detect()
            warning.assert_called_once()
            self.assertTrue(dialog._btn_detect.isEnabled())
            self.assertFalse(dialog._btn_cancel.isVisible())
        _, task = self.start_detection(dialog)
        with patch('src.app.raster_text_inspector.configured_backend') as backend:
            dialog._on_detect()
            backend.assert_not_called()
            self.assertIs(dialog._detection, task)

    def test_stale_image_cell_and_removed_cell_results_are_ignored(self):
        for change in ('file', 'path', 'cell_path', 'cell_state', 'removed', 'replaced'):
            with self.subTest(change=change):
                self.image.save(self.path)
                self.cell = Cell(image_path=str(self.path), raster_text_regions=[self.region])
                self.project.cells = [self.cell]
                original_cell = self.cell
                dialog = self.dialog()
                backend, _ = self.start_detection(dialog)
                if change == 'file':
                    Image.new('RGBA', (201, 100), 'red').save(self.path)
                elif change == 'path':
                    dialog.image_path = str(self.path) + '.changed'
                elif change == 'cell_path':
                    self.cell.image_path = 'changed.png'
                elif change == 'cell_state':
                    self.cell.rotation = 90
                elif change == 'removed':
                    self.project.cells.clear()
                else:
                    dialog._cell = Cell(image_path=str(self.path))
                backend.release.set()
                self.wait_for(lambda: dialog._detection is None)
                self.assertEqual(original_cell.raster_text_regions, [self.region])
                self.assertEqual(dialog._ocr_status.text(), tr('rastertxt_detection_cancelled'))
                self.assertTrue(dialog._btn_detect.isEnabled())
                dialog.close()

    def test_worker_errors_and_empty_results_clear_busy_controls(self):
        for error in (OcrUnavailable('Unavailable'), RuntimeError('Backend failed'), 'analysis', None):
            with self.subTest(error=error), \
                    patch('src.app.raster_text_inspector.QMessageBox.warning') as warning, \
                    patch('src.app.raster_text_inspector.QMessageBox.information') as information:
                dialog = self.dialog()
                analyzer = patch('src.app.raster_text_inspector.regions_from_detections',
                                 side_effect=RuntimeError('Analysis failed')) if error == 'analysis' else patch(
                                     'src.app.raster_text_inspector.regions_from_detections', wraps=regions_from_detections)
                with analyzer:
                    backend, _ = self.start_detection(dialog, [], error if isinstance(error, Exception) else None)
                    backend.release.set()
                    self.wait_for(lambda: dialog._detection is None)
                self.assertTrue(dialog._btn_detect.isEnabled())
                self.assertFalse(dialog._btn_cancel.isVisible())
                self.assertEqual(dialog._ocr_status.text(), '')
                self.assertEqual(warning.call_count, int(error is not None))
                self.assertEqual(information.call_count, int(error is None))
                dialog.close()

    def test_close_reject_and_direct_deletion_do_not_wait_or_deliver(self):
        for close in ('close', 'reject', 'deleteLater'):
            with self.subTest(close=close), patch('src.app.raster_text_inspector.QMessageBox.warning') as warning:
                dialog = self.dialog()
                before = deepcopy(self.cell.to_dict())
                backend, task = self.start_detection(dialog, error=RuntimeError('Late error'))
                getattr(dialog, close)()
                QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
                self.assertTrue(task.cancelled.is_set())
                self.assertFalse(backend.release.is_set())
                backend.release.set()
                self.assertTrue(QThreadPool.globalInstance().waitForDone(2000))
                self.app.processEvents()
                self.assertEqual(self.cell.to_dict(), before)
                warning.assert_not_called()


if __name__ == '__main__':
    unittest.main()
