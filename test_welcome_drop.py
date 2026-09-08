import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt6.QtCore import QMimeData, QPoint, QPointF, Qt, QUrl
from PyQt6.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent
from PyQt6.QtWidgets import QApplication, QWidget

from src.app.i18n import current_language, set_language, tr
from src.app.main_window import MainWindow
from src.app.welcome_window import WelcomeWindow
from src.model.data_model import Project


class WelcomeDropTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.host = QWidget()
        self.host._current_theme = 'light'
        self.host._get_recent_projects = Mock(return_value=[])
        self.host._on_show_about = Mock()
        self.host._dismiss_welcome = Mock()
        self.host._on_open_project = Mock()
        self.host._is_project_drop_path = MainWindow._is_project_drop_path
        self.host._open_path_dispatch = Mock()
        self.welcome = WelcomeWindow(self.host)
        self.host.welcome_window = self.welcome
        self.welcome.show()
        self.app.processEvents()
        self.addCleanup(self.host.close)
        self.addCleanup(self.welcome.close)

    def project_file(self, name):
        path = self.root / name
        path.write_text('{}', encoding='utf-8')
        return str(path)

    def mime(self, paths):
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(path) for path in paths])
        return mime

    def drop(self, mime):
        event = QDropEvent(QPointF(10, 10), Qt.DropAction.CopyAction, mime,
                           Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        self.welcome.dropEvent(event)
        return event

    def test_saved_project_formats_route_to_existing_opener(self):
        self.assertTrue(self.welcome.acceptDrops())
        for name in ('figure.figpack', 'figure.figlayout', 'figure.json', 'Figure.FIGPACK', '图 1.figlayout'):
            with self.subTest(name=name):
                path = self.project_file(name)
                mime = self.mime([path])
                enter = QDragEnterEvent(QPoint(10, 10), Qt.DropAction.CopyAction, mime,
                                        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
                move = QDragMoveEvent(QPoint(20, 20), Qt.DropAction.CopyAction, mime,
                                      Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
                self.welcome.dragEnterEvent(enter)
                self.welcome.dragMoveEvent(move)
                self.assertTrue(enter.isAccepted())
                self.assertTrue(move.isAccepted())
                self.assertTrue(self.drop(mime).isAccepted())
                self.host._open_path_dispatch.assert_called_with(os.path.normpath(path))

    def test_multiple_projects_filter_and_deduplicate(self):
        a = self.project_file('a.figlayout')
        b = self.project_file('b.figpack')
        image = self.project_file('image.png')
        folder = self.root / 'folder.figlayout'
        folder.mkdir()
        event = self.drop(self.mime([a, image, b, a, str(folder)]))
        self.assertTrue(event.isAccepted())
        self.assertEqual([call.args[0] for call in self.host._open_path_dispatch.call_args_list], [a, b])

    def test_remote_missing_and_nonproject_drops_are_rejected(self):
        remote = QMimeData()
        remote.setUrls([QUrl('https://example.invalid/figure.figlayout')])
        text = QMimeData()
        text.setText('not a project')
        image = self.project_file('image.png')
        for mime in (remote, text, self.mime([image]), self.mime([str(self.root / 'missing.figpack')]),
                     self.mime([str(self.root)])):
            enter = QDragEnterEvent(QPoint(10, 10), Qt.DropAction.CopyAction, mime,
                                    Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
            self.welcome.dragEnterEvent(enter)
            self.assertFalse(enter.isAccepted())
            self.assertFalse(self.drop(mime).isAccepted())
        self.host._open_path_dispatch.assert_not_called()
        self.assertTrue(self.welcome.isVisible())

    def test_native_qt_drop_delivery(self):
        path = self.project_file('native.figlayout')
        mime = self.mime([path])
        enter = QDragEnterEvent(QPoint(10, 10), Qt.DropAction.CopyAction, mime,
                                Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        self.app.sendEvent(self.welcome, enter)
        self.assertTrue(enter.isAccepted())
        drop = QDropEvent(QPointF(10, 10), Qt.DropAction.CopyAction, mime,
                          Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        self.app.sendEvent(self.welcome, drop)
        self.assertTrue(drop.isAccepted())
        self.host._open_path_dispatch.assert_called_once_with(path)

    def test_existing_dismissal_reveals_host_without_quitting(self):
        path = self.project_file('legacy.figlayout')
        before = Path(path).read_bytes()
        loaded = []

        def open_project(filename):
            MainWindow._dismiss_welcome(self.host)
            loaded.append(Project.load_from_file(filename))

        self.host._open_path_dispatch.side_effect = open_project
        self.assertFalse(self.host.isVisible())
        self.drop(self.mime([path]))
        self.assertTrue(self.host.isVisible())
        self.assertFalse(self.welcome.isVisible())
        self.assertIsNone(self.host.welcome_window)
        self.assertEqual(loaded[0].name, 'legacy')
        self.assertEqual(Path(path).read_bytes(), before)

    def test_drop_hint_is_translated(self):
        original = current_language()
        self.addCleanup(set_language, original)
        for language in ('en', 'zh'):
            set_language(language)
            self.welcome.retranslate()
            self.assertEqual(self.welcome._drop_hint.text(), tr('welcome_drop_project'))


if __name__ == '__main__':
    unittest.main()
