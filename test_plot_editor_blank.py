"""Standalone Plot Editor shell and native-format preservation tests."""

import hashlib
import os
import runpy
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt6.QtWidgets import (QMainWindow, QSplitter, QStatusBar,
                             QTabWidget, QToolBar, QToolButton, QWidget)

ROOT = os.path.dirname(os.path.abspath(__file__))
PYTHON = sys.executable


def assert_tabbed_workspace(tc, window, view=None):
    """Central widget is a tab bar; each tab is a plotWorkspace splitter."""
    tabs = window.centralWidget()
    tc.assertIsInstance(tabs, QTabWidget)
    tc.assertEqual(tabs.objectName(), 'plotTabs')
    tc.assertGreaterEqual(tabs.count(), 1)
    ws = tabs.currentWidget()
    assert_split_workspace(tc, ws, view)
    return ws


def assert_split_workspace(tc, ws, view=None):
    from PyQt6.QtCore import Qt
    tc.assertIsInstance(ws, QSplitter)
    tc.assertEqual(ws.objectName(), 'plotWorkspace')
    tc.assertEqual(ws.orientation(), Qt.Orientation.Horizontal)
    tc.assertEqual(ws.count(), 2)
    tc.assertEqual([ws.widget(i).objectName() for i in range(2)],
                   ['plotLeftArea', 'plotRightArea'])
    left, right = ws.widget(0), ws.widget(1)
    if view is None:
        tc.assertEqual(left.children(), [])
        tc.assertIsNone(left.layout())
    else:
        from src.plot_editor.worksheet_view import WorksheetView
        tc.assertIsInstance(view, WorksheetView)
        tc.assertIs(view.parentWidget(), left)
    tc.assertIsNotNone(right.findChild(QWidget, 'plotCanvas'))


def _app():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


class BlankWindowTests(unittest.TestCase):

    def setUp(self):
        self._qt_app = _app()
        from src.plot_editor.window import PlotEditorWindow
        self.cls = PlotEditorWindow

    def test_top_level_even_with_legacy_parent_and_document(self):
        parent = QWidget()
        doc = object()
        win = self.cls(doc, parent=parent, for_ilm=True)
        self.assertIsNone(win.parent())
        self.assertIsNone(win.parentWidget())
        self.assertTrue(win.isWindow())
        self.assertIsNone(win.result_document)
        win.deleteLater()

    def test_shell_structure_and_empty_workspace(self):
        win = self.cls()
        self.assertIsInstance(win, QMainWindow)
        assert_tabbed_workspace(self, win, win.worksheet_view)
        self.assertEqual(win.findChildren(QStatusBar), [])
        self.assertFalse(hasattr(win, 'document'))
        self.assertFalse(hasattr(win, 'undo_stack'))
        self.assertFalse(hasattr(win, 'undoStack'))
        self.assertIsNone(win.result_document)
        win.deleteLater()

    def test_menu_labels_and_hero_toolbar_order(self):
        win = self.cls()
        titles = [a.text() for a in win.menuBar().actions()]
        self.assertEqual(titles, ['File', 'Edit', 'Plot', 'Help'])
        toolbar = win.findChild(QToolBar, 'plotToolbar')
        self.assertIsNotNone(toolbar)
        order = []
        for action in toolbar.actions():
            if action.isSeparator():
                continue
            widget = toolbar.widgetForAction(action)
            if action.data() in win.editor_actions:
                order.append(action.data())
            elif widget is win._plot_button:
                order.append('plot')
            elif widget is win._export_button:
                order.append('export')
            else:
                order.append('spacer')
        self.assertEqual(order, ['undo', 'redo', 'new', 'open', 'save',
                                 'plot', 'spacer', 'export'])
        win.deleteLater()

    def test_chart_choices_and_request_signals(self):
        win = self.cls()
        seen = []
        plots = []
        exports = []
        win.action_requested.connect(seen.append)
        win.plot_requested.connect(lambda g, c: plots.append((g, c)))
        win.export_requested.connect(exports.append)

        self.assertEqual(win.current_chart, ('line', 'pure_line'))
        chart = win.chart_actions[('line', 'stacked_line')]
        with patch('src.plot_editor.window.QMessageBox.information'):
            chart.trigger()
        self.assertEqual(win.current_chart, ('line', 'stacked_line'))
        self.assertTrue(chart.isChecked())
        self.assertEqual(seen, ['plot'])
        self.assertEqual(plots, [('line', 'stacked_line')])

        with patch('src.plot_editor.window.QMessageBox.information'):
            win.editor_actions['plot'].trigger()
        self.assertEqual(seen, ['plot', 'plot'])
        self.assertEqual(plots[-1], ('line', 'stacked_line'))

        # Export stays disabled until a plot exists.
        win.editor_actions['export_png'].trigger()
        self.assertEqual(exports, [])

        closed = []
        win.close = lambda: closed.append(True)
        win.editor_actions['quit'].trigger()
        self.assertEqual(seen[-1], 'quit')
        self.assertEqual(closed, [True])
        win.deleteLater()

    def test_zoom_scales_sheet(self):
        win = self.cls()
        view = win.worksheet_view
        labels = view._labels
        col_w = view.columnWidth(0)
        row_h = view.rowHeight(3)
        view.set_zoom(2.0)
        self.assertEqual(view.columnWidth(0), 2 * col_w)
        self.assertGreater(view.rowHeight(3), row_h)
        self.assertEqual(labels.height(), 3 * view._row_height())
        self.assertEqual(labels.rowHeight(0), view.rowHeight(3))
        view.set_zoom(1.0)
        self.assertAlmostEqual(view.columnWidth(0), col_w, delta=1)
        self.assertEqual(view.rowHeight(3), row_h)
        self.assertFalse(win.current_tab().dirty)
        win.deleteLater()

    def test_title_and_size(self):
        win = self.cls()
        self.assertTrue(win.windowTitle().endswith('— Plot Editor'))
        self.assertGreaterEqual(win.width(), 1)
        self.assertGreaterEqual(win.height(), 1)
        win.deleteLater()


class ExecCompatTests(unittest.TestCase):

    def setUp(self):
        self._qt_app = _app()
        from src.plot_editor.window import PlotEditorWindow
        self.win = PlotEditorWindow()

    def tearDown(self):
        self.win.deleteLater()

    def test_exec_source_launch_args_and_rejection(self):
        calls = []

        def fake(exe, args, workdir):
            calls.append((exe, args, workdir))
            return True, 4321

        from src.plot_editor.document import PlotDocument
        doc = PlotDocument()
        doc.validate()
        before = doc.to_dict()
        win = type(self.win)(doc)
        with patch('src.plot_editor.window.QProcess.startDetached',
                   side_effect=fake) as m:
            rc = win.exec()
        self.assertEqual(rc, 0)
        self.assertEqual(doc.to_dict(), before)
        m.assert_called_once()
        exe, args, workdir = calls[0]
        self.assertEqual(exe, sys.executable)
        script = os.path.join(ROOT, 'main.py')
        self.assertEqual(args, [script, '--plot-editor'])
        self.assertEqual(workdir, ROOT)
        self.assertFalse(win.isVisible())
        self.assertIsNone(win.result_document)
        win.deleteLater()

    def test_exec_non_default_document_passes_ilm_copy(self):
        calls = []

        def fake(exe, args, workdir):
            calls.append((exe, args, workdir))
            return True, 4321

        from src.plot_editor.document import PlotDocument
        doc = PlotDocument()
        doc.title = 'Modified'
        doc.validate()
        win = type(self.win)(doc)
        try:
            with patch('src.plot_editor.window.QProcess.startDetached',
                       side_effect=fake):
                rc = win.exec()
            self.assertEqual(rc, 0)
            _exe, args, _workdir = calls[0]
            self.assertIn('--ilm-copy', args)
            tmp = args[args.index('--ilm-copy') + 1]
            from src.plot_editor.ilm_bridge import is_ilm_copy_path
            self.assertTrue(is_ilm_copy_path(tmp))
            self.assertTrue(os.path.isfile(tmp))
            with open(tmp, 'rb') as f:
                self.assertIn(b'ilm-plot-document', f.read())
            os.unlink(tmp)
        finally:
            win.deleteLater()

    def test_exec_frozen_launch_args(self):
        calls = []

        def fake(exe, args, workdir):
            calls.append((exe, args, workdir))
            return True, 1

        with patch.object(sys, 'frozen', True, create=True), \
                patch('src.plot_editor.window.QProcess.startDetached',
                      side_effect=fake):
            rc = self.win.exec()
        self.assertEqual(rc, 0)
        exe, args, workdir = calls[0]
        self.assertEqual(exe, sys.executable)
        self.assertEqual(args, ['--plot-editor'])
        self.assertEqual(workdir, os.path.dirname(sys.executable))
        self.assertFalse(self.win.isVisible())

    def test_exec_failed_launch_warns_and_rejects(self):
        with patch('src.plot_editor.window.QProcess.startDetached',
                   return_value=(False, None)), \
                patch('src.plot_editor.window.QMessageBox.warning') as warn:
            rc = self.win.exec()
        self.assertEqual(rc, 0)
        warn.assert_called_once()
        self.assertFalse(self.win.isVisible())
        self.assertIsNone(self.win.result_document)


class AppMainTests(unittest.TestCase):

    def setUp(self):
        self.qt_app = _app()
        from src.plot_editor.window import PlotEditorWindow
        self.cls = PlotEditorWindow

    def _run_main(self, argv):
        from src.plot_editor import app as app_mod
        shown = []
        real_show = self.cls.show

        def record(self):
            shown.append(self)
            real_show(self)

        with patch.object(self.cls, 'show', record), \
                patch.object(type(self.qt_app), 'exec', return_value=0):
            rc = app_mod.main(argv)
        return rc, shown

    def test_main_shows_single_blank_window(self):
        rc, shown = self._run_main([])
        self.assertEqual(rc, 0)
        self.assertEqual(len(shown), 1)
        win = shown[0]
        self.assertIsNone(win.parent())
        assert_tabbed_workspace(self, win, win.worksheet_view)
        self.assertTrue(win.windowTitle().endswith('— Plot Editor'))
        win.deleteLater()

    def test_main_positional_file_opens_in_tab(self):
        from src.plot_editor.document import PlotDocument
        from src.plot_editor.render import save_document
        doc = PlotDocument()
        doc.validate()
        with tempfile.NamedTemporaryFile(suffix='.ilmplot.svg',
                                         delete=False) as f:
            path = f.name
        try:
            save_document(doc, path)
            with open(path, 'rb') as f:
                before = f.read()
            rc, shown = self._run_main([path])
            self.assertEqual(rc, 0)
            self.assertEqual(len(shown), 1)
            win = shown[0]
            tab = assert_tabbed_workspace(self, win, win.worksheet_view)
            self.assertEqual(
                os.path.normcase(os.path.abspath(tab.path)),
                os.path.normcase(os.path.abspath(path)))
            with open(path, 'rb') as f:
                self.assertEqual(f.read(), before)
            win.deleteLater()
        finally:
            os.unlink(path)

    def test_main_imports_no_ilm_app_modules(self):
        code = (
            "import os, sys\n"
            "os.environ['QT_QPA_PLATFORM'] = 'offscreen'\n"
            "sys.path.insert(0, %r)\n" % ROOT +
            "from unittest.mock import patch\n"
            "from PyQt6.QtWidgets import QApplication\n"
            "app = QApplication([])\n"
            "from src.plot_editor import app as app_mod\n"
            "with patch.object(QApplication, 'exec', return_value=0):\n"
            "    rc = app_mod.main([])\n"
            "assert 'src.app.main_window' not in sys.modules\n"
            "assert rc == 0\n"
        )
        proc = subprocess.run([PYTHON, '-c', code], cwd=ROOT,
                              capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr)


class StartupSmokeTests(unittest.TestCase):

    def test_plot_editor_main_help(self):
        proc = subprocess.run(
            [PYTHON, 'plot_editor_main.py', '--help'], cwd=ROOT,
            capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn('Plot Editor', proc.stdout)

    def test_main_py_plot_editor_help(self):
        proc = subprocess.run(
            [PYTHON, 'main.py', '--plot-editor', '--help'], cwd=ROOT,
            capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn('Plot Editor', proc.stdout)


class OffscreenStartupTests(unittest.TestCase):
    """Run each real launch path under QTimer so the loop closes cleanly."""

    def setUp(self):
        self.qt_app = _app()
        from src.plot_editor.window import PlotEditorWindow
        self.cls = PlotEditorWindow

    def _run_launcher(self, path, argv):
        from PyQt6.QtCore import QTimer
        from PyQt6.QtWidgets import QApplication
        seen = []

        def check():
            for w in QApplication.topLevelWidgets():
                if isinstance(w, self.cls):
                    seen.append(w)
            QApplication.quit()

        old_argv = sys.argv
        sys.argv = argv
        try:
            QTimer.singleShot(300, check)
            with self.assertRaises(SystemExit) as cm:
                runpy.run_path(path, run_name='__main__')
            code = cm.exception.code
            self.assertIn(code, (0, None))
        finally:
            sys.argv = old_argv
        return seen

    def test_plot_editor_main_blank_startup(self):
        seen = self._run_launcher(
            os.path.join(ROOT, 'plot_editor_main.py'),
            ['plot_editor_main.py'])
        self.assertEqual(len(seen), 1)
        win = seen[0]
        self.assertTrue(win.windowTitle().endswith('— Plot Editor'))
        assert_tabbed_workspace(self, win, win.worksheet_view)
        win.deleteLater()

    def test_main_py_plot_editor_blank_startup(self):
        seen = self._run_launcher(
            os.path.join(ROOT, 'main.py'),
            ['main.py', '--plot-editor'])
        self.assertEqual(len(seen), 1)
        win = seen[0]
        self.assertTrue(win.windowTitle().endswith('— Plot Editor'))
        assert_tabbed_workspace(self, win, win.worksheet_view)
        win.deleteLater()


class NativeFormatPreservationTests(unittest.TestCase):

    def test_render_load_roundtrip_and_content_addressing(self):
        from src.plot_editor.document import PlotDocument, load_document
        from src.plot_editor.render import render_document
        from src.utils.editable_plot import store_plot_document

        doc = PlotDocument()
        doc.validate()
        render = render_document(doc)
        self.assertTrue(render.svg.startswith(b'<?xml') or b'<svg' in render.svg)

        with tempfile.TemporaryDirectory() as tmp:
            svg_path = os.path.join(tmp, 'doc.ilmplot.svg')
            with open(svg_path, 'wb') as f:
                f.write(render.svg)
            loaded = load_document(svg_path)
            loaded.validate()
            self.assertEqual(loaded.to_dict(), doc.to_dict())

            path1, r1 = store_plot_document(doc, root=tmp)
            path2, r2 = store_plot_document(loaded, root=tmp)
            self.assertEqual(path1, path2)
            self.assertEqual(r1.svg, r2.svg)
            digest = hashlib.sha256(render.svg).hexdigest()
            self.assertEqual(os.path.basename(path1),
                             f'plot-{digest}.ilmplot.svg')
            with open(path1, 'rb') as f:
                self.assertEqual(f.read(), render.svg)


if __name__ == '__main__':
    unittest.main()
