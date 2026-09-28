import os
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt
from PyQt6.QtGui import QMouseEvent, QWheelEvent
from PyQt6.QtWidgets import QApplication, QTabWidget, QWidget

from src.app import main_window
from src.canvas.canvas_scene import CanvasScene
from src.canvas.canvas_view import CanvasView
from src.model.data_model import Project


class CanvasPanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        env = patch.dict(os.environ, {'ILM_CANVAS_OPENGL': ''})
        env.start()
        self.addCleanup(env.stop)
        self.host = Mock()
        self.host._tabs = []
        self.host.tab_widget = QTabWidget()
        self.host._settings.value.return_value = 200
        self.host._current_theme = 'light'
        self.host._tab_title.return_value = 'Untitled'

    def tearDown(self):
        for tab in self.host._tabs:
            tab.view.close()
            tab.view.setScene(None)
        self.host.tab_widget.close()
        self.app.processEvents()

    def create_tab(self):
        return main_window.MainWindow._create_tab(self.host, Project())

    def test_default_canvas_uses_scrollable_widget_viewport(self):
        class FakeOpenGLWidget(QWidget):
            pass

        with patch.dict(os.environ, {'ILM_CANVAS_OPENGL': ''}), \
             patch.object(main_window, 'HAS_OPENGL', True), \
             patch.object(main_window, 'QOpenGLWidget', FakeOpenGLWidget):
            tab = self.create_tab()
        self.assertNotIsInstance(tab.view.viewport(), FakeOpenGLWidget)
        self.assertIs(type(tab.view.viewport()), QWidget)

    def test_opengl_viewport_is_available_when_explicitly_requested(self):
        class FakeOpenGLWidget(QWidget):
            pass

        with patch.dict(os.environ, {'ILM_CANVAS_OPENGL': '1'}), \
             patch.object(main_window, 'HAS_OPENGL', True), \
             patch.object(main_window, 'QOpenGLWidget', FakeOpenGLWidget):
            tab = self.create_tab()
        self.assertIsInstance(tab.view.viewport(), FakeOpenGLWidget)

    def test_canvas_viewport_is_opaque(self):
        tab = self.create_tab()
        self.assertTrue(tab.view.viewport().testAttribute(
            Qt.WidgetAttribute.WA_OpaquePaintEvent))

    def test_large_viewport_still_renders_the_page(self):
        scene = CanvasScene()
        scene.set_project(Project())
        view = CanvasView(scene)
        self.addCleanup(view.close)
        view.resize(1600, 900)
        view.show()
        self.app.processEvents()
        image = view.viewport().grab().toImage()
        center = view.mapFromScene(scene.page_rect.center())
        color = image.pixelColor(round(center.x() * image.devicePixelRatio()),
                                 round(center.y() * image.devicePixelRatio()))
        self.assertEqual((color.red(), color.green(), color.blue()),
                         (255, 255, 255))
        view._start_zoom(2.5, QPointF(view.viewport().rect().center()),
                         scene.page_rect.center(), animated=False)
        view.horizontalScrollBar().setValue(
            view.horizontalScrollBar().value() + 30)
        view.verticalScrollBar().setValue(
            view.verticalScrollBar().value() + 20)
        self.app.processEvents()
        image = view.viewport().grab().toImage()
        center = view.mapFromScene(scene.page_rect.center())
        ratio = image.devicePixelRatio()
        self.assertEqual(image.pixelColor(round(center.x() * ratio),
                                          round(center.y() * ratio)).name(),
                         '#ffffff')
        self.assertEqual(image.pixelColor(round(10 * ratio),
                                          round(10 * ratio)).name(),
                         scene._canvas_bg.lower())

    def test_middle_button_drag_pans_and_releases(self):
        tab = self.create_tab()
        view = tab.view
        view.scene().setSceneRect(0, 0, 2000, 2000)
        view.resize(640, 480)
        view.show()
        self.app.processEvents()
        hbar, vbar = view.horizontalScrollBar(), view.verticalScrollBar()
        hbar.setValue(500)
        vbar.setValue(500)
        press = QMouseEvent(
            QEvent.Type.MouseButtonPress, QPointF(100, 100),
            Qt.MouseButton.MiddleButton, Qt.MouseButton.MiddleButton,
            Qt.KeyboardModifier.NoModifier)
        move = QMouseEvent(
            QEvent.Type.MouseMove, QPointF(140, 125),
            Qt.MouseButton.NoButton, Qt.MouseButton.MiddleButton,
            Qt.KeyboardModifier.NoModifier)
        release = QMouseEvent(
            QEvent.Type.MouseButtonRelease, QPointF(140, 125),
            Qt.MouseButton.MiddleButton, Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(view.viewport(), press)
        QApplication.sendEvent(view.viewport(), move)
        self.assertEqual((hbar.value(), vbar.value()), (460, 475))
        QApplication.sendEvent(view.viewport(), release)
        self.assertFalse(view._pan_active)

    def test_pixel_wheel_pans_both_axes(self):
        tab = self.create_tab()
        view = tab.view
        view.scene().setSceneRect(0, 0, 2000, 2000)
        view.resize(640, 480)
        view.show()
        self.app.processEvents()
        hbar, vbar = view.horizontalScrollBar(), view.verticalScrollBar()
        hbar.setValue(200)
        vbar.setValue(200)
        event = QWheelEvent(
            QPointF(50, 50), QPointF(50, 50), QPoint(15, 20), QPoint(),
            Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.ScrollUpdate, False)
        view.wheelEvent(event)
        self.assertTrue(event.isAccepted())
        self.assertEqual((hbar.value(), vbar.value()), (185, 180))


if __name__ == '__main__':
    unittest.main()
