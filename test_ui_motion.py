import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw
from PyQt6.QtCore import QEvent, Qt, QVariantAnimation
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QPushButton, QWidget

from src.app.motion import (
    MotionPolicy, MotionTween, install_button_feedback, motion_duration,
    motion_policy, set_motion_mode, show_layout_transition, start_animation,
)


class MotionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.old_policy = getattr(self.app, '_ilm_motion_policy', None)
        self.system = patch('src.app.motion.system_reduced_motion', return_value=False)
        self.system.start()
        self.policy = MotionPolicy(self.app)
        self.app._ilm_motion_policy = self.policy
        set_motion_mode('standard')

    def tearDown(self):
        set_motion_mode('off')
        self.app.processEvents()
        self.app._ilm_motion_policy = self.old_policy
        self.policy.deleteLater()
        self.system.stop()

    def test_durations_and_os_preference(self):
        self.assertEqual(motion_duration(180, spatial=True), 180)
        set_motion_mode('reduced')
        self.assertEqual(motion_duration(180, spatial=True), 0)
        self.assertEqual(motion_duration(120), 70)
        set_motion_mode('off')
        self.assertEqual(motion_duration(120), 0)
        with patch('src.app.motion.system_reduced_motion', return_value=True):
            set_motion_mode('standard')
        self.assertEqual(self.policy.effective_mode, 'reduced')
        self.assertEqual(motion_duration(140, spatial=True), 0)

    def test_off_settles_inflight_animation_exactly_once(self):
        animation = QVariantAnimation()
        animation.setStartValue(0.0)
        animation.setEndValue(1.0)
        finished = []
        animation.finished.connect(lambda: finished.append(True))
        start_animation(animation, 180, spatial=True)
        animation.setCurrentTime(45)
        set_motion_mode('off')
        self.assertEqual(animation.currentValue(), 1.0)
        self.assertEqual(finished, [True])
        set_motion_mode('off')
        self.assertEqual(finished, [True])

    def test_tween_retargets_without_queue_and_repeated_target_does_not_restart(self):
        tween = MotionTween()
        tween.set_target(1, 100)
        tween._animation.setCurrentTime(50)
        current = tween.value
        tween.set_target(1, 100)
        self.assertEqual(tween._animation.currentTime(), 50)
        tween.set_target(0, 100)
        self.assertAlmostEqual(tween._animation.startValue(), current)
        tween._animation.setCurrentTime(100)
        self.assertEqual(tween.value, 0)
        set_motion_mode('off')
        tween.set_target(1)
        self.assertEqual(tween.value, 1)

    def test_button_feedback_preserves_geometry_and_click(self):
        root = QWidget()
        button = QPushButton('Open', root)
        button.setGeometry(10, 10, 120, 35)
        root.show()
        self.addCleanup(root.close)
        install_button_feedback(root)
        first = button._motion_feedback
        install_button_feedback(root)
        self.assertIs(button._motion_feedback, first)
        rect = button.geometry()
        clicked = []
        button.clicked.connect(lambda: clicked.append(True))
        self.app.sendEvent(button, QEvent(QEvent.Type.Enter))
        first._strength._animation.setCurrentTime(110)
        self.assertEqual(first._strength.value, 1)
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        self.assertEqual(clicked, [True])
        self.assertEqual(button.geometry(), rect)

    def test_splitter_modes_and_interrupted_toggle(self):
        from src.app.main_window import CollapsibleSplitter
        splitter = CollapsibleSplitter(Qt.Orientation.Horizontal)
        for _ in range(3):
            child = QWidget()
            child.setMinimumWidth(100)
            splitter.addWidget(child)
        splitter.resize(900, 250)
        splitter.setSizes([200, 500, 200])
        splitter.show()
        self.addCleanup(splitter.close)
        self.app.processEvents()
        splitter.animate_sizes([0, 700, 200])
        self.assertEqual(splitter.target_sizes()[0], 0)
        splitter.animate_sizes([200, 500, 200])
        splitter.finish_transition()
        self.assertIsNone(splitter._panel_animation)
        self.assertGreater(splitter.sizes()[0], 0)
        self.assertEqual(splitter.widget(0).minimumWidth(), 100)
        for mode in ('reduced', 'off'):
            set_motion_mode(mode)
            splitter.animate_sizes([0, 700, 200])
            self.assertEqual(splitter.sizes()[0], 0)
            self.assertIsNone(splitter._panel_animation)
            splitter.animate_sizes([200, 500, 200])
            self.assertGreater(splitter.sizes()[0], 0)
        set_motion_mode('standard')
        splitter.animate_sizes([0, 700, 200])
        set_motion_mode('off')
        self.assertEqual(splitter.sizes()[0], 0)
        self.assertFalse(splitter._saved_constraints)

    def test_layout_feedback_never_changes_scene_or_export(self):
        from src.canvas.canvas_scene import CanvasScene
        from src.canvas.canvas_view import CanvasView
        from src.export.image_exporter import ImageExporter
        from src.model.data_model import Cell, Project
        from src.utils.image_proxy import get_image_proxy
        with tempfile.TemporaryDirectory() as folder:
            asset = Path(folder) / 'panel.png'
            image = Image.new('RGB', (80, 60), 'white')
            ImageDraw.Draw(image).rectangle((4, 10, 40, 45), fill='red')
            image.save(asset)
            cell = Cell(image_path=str(asset), freeform_x_mm=20, freeform_y_mm=10,
                        freeform_w_mm=30, freeform_h_mm=25)
            project = Project(layout_mode='freeform', cells=[cell], dpi=96,
                              page_width_mm=80, page_height_mm=60)
            scene = CanvasScene()
            scene.set_project(project)
            view = CanvasView(scene)
            view.resize(500, 400)
            view.show()
            try:
                before = {cell.id: (0, 0, 20, 20)}
                after = dict(scene._last_layout_result.cell_rects)
                reference = ImageExporter.render_to_qimage(project)
                state = project.to_dict()
                count = len(scene.items())
                show_layout_transition(view, before, after)
                overlay = view._layout_motion_overlay
                self.assertIsNotNone(overlay)
                overlay._progress._animation.setCurrentTime(80)
                self.assertEqual(len(scene.items()), count)
                self.assertEqual(project.to_dict(), state)
                self.assertEqual(ImageExporter.render_to_qimage(project), reference)
                set_motion_mode('off')
                self.assertIsNone(view._layout_motion_overlay)
                self.assertEqual(ImageExporter.render_to_qimage(project), reference)
            finally:
                get_image_proxy().shutdown()
                view.close()
                scene.clear()
                self.app.processEvents()


if __name__ == '__main__':
    unittest.main()
