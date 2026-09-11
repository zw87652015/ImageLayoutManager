import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt6.QtCore import QMimeData, QPointF, QUrl, Qt
from PyQt6.QtGui import QDropEvent
from PyQt6.QtWidgets import QApplication
from PIL import Image

from src.utils.image_proxy import collect_importable_images


class MemorySettings:
    def __init__(self):
        self.data = {'language': 'en', 'theme': 'light', 'autosave_interval_s': 0}

    def value(self, key, default=None, **_):
        return self.data.get(key, default)

    def setValue(self, key, value):
        self.data[key] = value

    def contains(self, key):
        return key in self.data

    def remove(self, key):
        self.data.pop(key, None)

    def sync(self):
        pass


def make_images(folder, names):
    paths = []
    for name in names:
        p = Path(folder) / name
        p.parent.mkdir(parents=True, exist_ok=True)
        Image.new('RGB', (40, 30), 'white').save(p)
        paths.append(str(p))
    return paths


class CollectTests(unittest.TestCase):
    def test_folder_expansion_natural_sort_and_filtering(self):
        with tempfile.TemporaryDirectory() as d:
            make_images(d, ['fig10.png', 'fig2.PNG', 'fig1.jpg', 'sub/fig3.tif', '.hidden/x.png'])
            (Path(d) / 'notes.txt').write_text('x')
            (Path(d) / 'proj.figlayout').write_text('{}')
            found = collect_importable_images([d])
            self.assertEqual([os.path.basename(p) for p in found], ['fig1.jpg', 'fig2.PNG', 'fig3.tif', 'fig10.png'])
            self.assertEqual(collect_importable_images([d, found[0], str(Path(d) / 'notes.txt')]), found)
            self.assertEqual(collect_importable_images([str(Path(d) / 'proj.figlayout')]), [])


class DropTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        import src.app.main_window as mw
        self.mw = mw
        self.settings = MemorySettings()
        self.patches = [
            patch.object(mw, 'QSettings', return_value=self.settings),
            patch.object(mw, 'SnapshotStore', return_value=MagicMock()),
            patch.object(mw, 'cleanup_orphans'),
            patch.object(mw, 'register_pre_delete_hook'),
            patch.object(mw, 'HAS_OPENGL', False),
            patch.object(mw.MainWindow, '_start_update_check'),
            patch.object(mw.QMessageBox, 'information'),
        ]
        for p in self.patches:
            p.start()
        self.window = mw.MainWindow()
        self.window._autosave_timer.stop()
        self.temp = tempfile.TemporaryDirectory()

    def tearDown(self):
        from src.utils.image_proxy import get_image_proxy
        get_image_proxy().shutdown()
        if self.window.welcome_window is not None:
            self.window.welcome_window.hide()
        self.window.close()
        self.app.processEvents()
        for p in self.patches:
            p.stop()
        self.temp.cleanup()

    def drop(self, paths):
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(p) for p in paths])
        event = QDropEvent(QPointF(10, 10), Qt.DropAction.CopyAction, mime,
                           Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        self.window.dropEvent(event)
        self.app.processEvents()

    def filled_paths(self):
        return [os.path.normpath(c.image_path) for c in self.window.project.get_all_leaf_cells()
                if not c.is_placeholder]

    def test_folder_drop_opens_auto_layout_in_clean_tab(self):
        paths = make_images(self.temp.name, [f'panel{i}.png' for i in range(1, 6)])
        self.drop([self.temp.name])
        self.assertEqual(len(self.window._tabs), 1)
        self.assertEqual(sorted(self.filled_paths()), sorted(paths))
        self.assertEqual(len(self.window.project.get_all_leaf_cells()), 5)   # auto layout trimmed the grid
        self.assertEqual(self.window.undo_stack.undoText(), 'Auto Layout')
        self.assertFalse(self.window.welcome_window.isVisible())

    def test_multi_file_drop_on_dirty_tab_opens_new_tab(self):
        paths = make_images(self.temp.name, ['a.png', 'b.png', 'c.png'])
        self.window._on_new_image_dropped(paths[0], 0, 0)          # dirty the first tab
        self.drop(paths[1:])
        self.assertEqual(len(self.window._tabs), 2)
        self.assertEqual(sorted(self.filled_paths()), sorted(paths[1:]))

    def test_single_image_drop_fills_first_placeholder(self):
        paths = make_images(self.temp.name, ['single.png'])
        self.drop(paths)
        self.assertEqual(self.filled_paths(), paths)
        self.assertEqual(len(self.window.project.get_all_leaf_cells()), 4)    # default 2x2 grid untouched

    def test_mixed_project_and_images(self):
        paths = make_images(self.temp.name, ['a.png', 'b.png'])
        (Path(self.temp.name) / 'readme.txt').write_text('x')
        self.drop(paths + [str(Path(self.temp.name) / 'readme.txt')])
        self.assertEqual(sorted(self.filled_paths()), sorted(paths))

    def test_no_images_shows_message(self):
        (Path(self.temp.name) / 'readme.txt').write_text('x')
        self.drop([str(Path(self.temp.name) / 'readme.txt')])
        self.assertEqual(self.filled_paths(), [])

    def test_canvas_scene_batch_signal(self):
        paths = make_images(self.temp.name, ['a.png', 'b.png', 'c.png'])
        received = []
        self.window.scene.images_batch_dropped.connect(received.append)
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(p) for p in paths])
        event = MagicMock()
        event.mimeData.return_value = mime
        event.scenePos.return_value = QPointF(5, 5)
        self.window.scene.dropEvent(event)
        self.assertEqual([[os.path.normpath(p) for p in batch] for batch in received], [paths])
        event.accept.assert_called()


if __name__ == '__main__':
    unittest.main()
