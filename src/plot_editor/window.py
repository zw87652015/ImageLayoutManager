"""Standalone ILM Plot Editor window.

``PlotEditorWindow`` is a top-level ``QMainWindow`` shown by the standalone
entry points (``plot_editor_main.py`` / ``main.py --plot-editor``). It
carries the File/Edit/Plot/Help menu bar and a hero toolbar with
Undo/Redo/New/Open/Save plus the split Plot chart dropdown and the
primary Export button. The central widget is a ``QTabWidget`` of
``PlotTab``s; each tab owns its own worksheet and plot canvas, saved as a
self-contained ``*.ilmplot.svg`` (plot SVG plus the embedded worksheet).

Its ``exec()`` method remains only as a compatibility adapter for
unchanged ILM callers: it launches the standalone app in a separate
process and returns ``QDialog.Rejected`` immediately without showing a
local window.
"""

from __future__ import annotations

import os
import sys

from PyQt6.QtCore import QProcess, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QActionGroup, QKeySequence
from PyQt6.QtWidgets import (QFileDialog, QMainWindow, QMenu, QMessageBox,
                             QSizePolicy, QTabWidget, QToolBar,
                             QToolButton, QWidget)

from src.app.motion import install_button_feedback

from . import chrome
from .actions import (ACTIONS, CHART_GROUPS, DEFAULT_CHART, EDIT_MENU,
                      EXPORT_MENU, FILE_MENU, HELP_MENU,
                      NATIVE_PLOT_FILTER, NATIVE_PLOT_SUFFIX)
from .document import PlotDocument, PlotDocumentError
from .export import EXPORT_FORMATS, export_plot, with_suffix
from .ilm_bridge import (_is_default_document, write_ilm_copy)
from .plot_data import PlotSelectionError
from .plot_file import PlotFileError, load_plot_file
from .tab import PlotTab


class PlotEditorWindow(QMainWindow):
    """Top-level Plot Editor window hosting ``PlotTab`` documents."""

    action_requested = pyqtSignal(str)
    plot_requested = pyqtSignal(str, str)
    export_requested = pyqtSignal(str)

    def __init__(self, document=None, parent=None, *, for_ilm=False):
        super().__init__()
        self.result_document = None
        self._ilm_document = document
        self.current_chart = DEFAULT_CHART
        self.native_plot_filter = NATIVE_PLOT_FILTER
        self._export_dir = os.path.expanduser('~')
        self._file_dir = os.path.expanduser('~')
        self._untitled = 0
        self._theme = chrome.saved_theme()
        self._scale = chrome.saved_font_scale()
        self.resize(960, 640)

        self.tabs = QTabWidget()
        self.tabs.setObjectName('plotTabs')
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.setDocumentMode(True)
        self.tabs.currentChanged.connect(lambda _i: self._sync_tab())
        self.tabs.tabCloseRequested.connect(self._close_tab)
        self.setCentralWidget(self.tabs)

        self.editor_actions = {}
        for key, spec in ACTIONS.items():
            action = QAction(spec.text, self)
            action.setObjectName('action_' + key)
            action.setData(key)
            if spec.shortcut:
                action.setShortcut(QKeySequence(spec.shortcut))
            if spec.icon:
                action.setIcon(chrome.themed_icon(spec.icon, self._theme))
            action.setToolTip(spec.tooltip)
            action.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
            action.setMenuRole(QAction.MenuRole.NoRole)
            if key in ('new', 'open', 'save', 'save_as'):
                action.setProperty('fileFilter', NATIVE_PLOT_FILTER)
            action.triggered.connect(
                lambda checked=False, k=key: self._request_action(k))
            self.editor_actions[key] = action
        self.editor_actions['redo'].setShortcuts(
            [QKeySequence('Ctrl+Shift+Z'), QKeySequence('Ctrl+Y')])

        self._chart_group = QActionGroup(self)
        self._chart_group.setExclusive(True)
        self.chart_actions = {}
        for group in CHART_GROUPS:
            for chart in group.charts:
                action = QAction(chart.text, self)
                action.setCheckable(True)
                action.setData('%s:%s' % (group.key, chart.key))
                action.triggered.connect(
                    lambda checked=False, g=group.key, c=chart.key:
                        self._select_chart(g, c))
                self._chart_group.addAction(action)
                self.chart_actions[(group.key, chart.key)] = action
        self._select_chart(*DEFAULT_CHART, emit=False)

        self._build_menus()
        self._build_toolbar()
        self._add_tab()

    # ── tabs ────────────────────────────────────────────────────────
    def current_tab(self):
        return self.tabs.currentWidget()

    @property
    def worksheet(self):
        return self.current_tab().worksheet

    @property
    def worksheet_view(self):
        return self.current_tab().worksheet_view

    @property
    def plot_canvas(self):
        return self.current_tab().plot_canvas

    def _add_tab(self, worksheet=None):
        tab = PlotTab(self._theme, self._scale, worksheet)
        self._untitled += 1
        tab.title = 'Untitled %d' % self._untitled
        tab.changed.connect(self._sync_tab)
        self.tabs.addTab(tab, tab.title)
        self.tabs.setCurrentWidget(tab)
        self._sync_tab()
        return tab

    def _sync_tab(self):
        tab = self.current_tab()
        if tab is None:
            return
        index = self.tabs.indexOf(tab)
        self.tabs.setTabText(
            index, tab.title + (' *' if tab.dirty else ''))
        self.tabs.setTabToolTip(index, tab.path or '')
        self.setWindowTitle('%s — Plot Editor' % tab.title)
        self._sync_history_actions()
        self._sync_export_actions()

    def _sync_history_actions(self):
        ws = self.worksheet
        undo = self.editor_actions['undo']
        redo = self.editor_actions['redo']
        undo.setEnabled(ws.can_undo)
        redo.setEnabled(ws.can_redo)
        undo.setToolTip('Undo ' + ws.undo_label if ws.can_undo
                        else 'Nothing to undo')
        redo.setToolTip('Redo ' + ws.redo_label if ws.can_redo
                        else 'Nothing to redo')

    def _sync_export_actions(self):
        ready = self.current_tab().plot is not None
        for key in EXPORT_MENU:
            self.editor_actions[key].setEnabled(ready)
        self._export_button.setEnabled(ready)
        self._export_button.setIcon(chrome.themed_icon(
            'export', self._theme, 'on_accent' if ready else 'text_tert'))
        self._export_button.setToolTip(
            'Export the plot' if ready else 'Create a plot to export')

    # ── actions ─────────────────────────────────────────────────────
    def _request_action(self, key):
        self.action_requested.emit(key)
        tab = self.current_tab()
        view = tab.worksheet_view
        if key == 'new':
            self._add_tab()
        elif key == 'open':
            self._open_dialog()
        elif key == 'save':
            self._save(tab)
        elif key == 'save_as':
            self._save_as(tab)
        elif key == 'undo':
            view.undo()
        elif key == 'redo':
            view.redo()
        elif key == 'cut':
            view.cut()
        elif key == 'copy':
            view.copy()
        elif key == 'paste':
            view.paste()
        elif key == 'delete':
            view.clear_selection_contents()
        elif key == 'select_all':
            view.select_all()
        elif key == 'plot':
            self.plot_requested.emit(*self.current_chart)
            self._plot(*self.current_chart)
        elif key.startswith('export_'):
            fmt = key.split('_', 1)[1]
            self.export_requested.emit(fmt)
            if fmt == 'ilmplot':
                self._save_as(tab)
            else:
                self._export(tab, fmt)
        if key == 'close':
            self._close_tab(self.tabs.indexOf(tab))
        elif key == 'quit':
            self.close()

    def _select_chart(self, group_key, chart_key, emit=True):
        self.current_chart = (group_key, chart_key)
        self.chart_actions[(group_key, chart_key)].setChecked(True)
        group = next(g for g in CHART_GROUPS if g.key == group_key)
        chart = next(c for c in group.charts if c.key == chart_key)
        self.editor_actions['plot'].setToolTip(
            'Plot — %s (%s)' % (chart.text, group.text))
        if emit:
            self.action_requested.emit('plot')
            self.plot_requested.emit(group_key, chart_key)
            self._plot(group_key, chart_key)

    def _plot(self, group_key, chart_key):
        try:
            self.current_tab().plot_current(chart_key)
        except PlotSelectionError as e:
            QMessageBox.information(self, 'Plot', str(e))

    # ── file operations ─────────────────────────────────────────────
    def open_paths(self, paths):
        for path in paths:
            self._open_path(path)

    def _open_dialog(self):
        paths, _f = QFileDialog.getOpenFileNames(
            self, 'Open', self._file_dir, NATIVE_PLOT_FILTER)
        self.open_paths(paths)

    def _open_path(self, path):
        norm = os.path.normcase(os.path.abspath(path))
        for i in range(self.tabs.count()):
            tab = self.tabs.widget(i)
            if tab.path is not None and \
                    os.path.normcase(os.path.abspath(tab.path)) == norm:
                self.tabs.setCurrentIndex(i)
                return
        try:
            pf = load_plot_file(path)
        except (OSError, PlotDocumentError, PlotFileError) as e:
            QMessageBox.warning(
                self, 'Open',
                'Could not open %s:\n%s' % (os.path.basename(path), e))
            return
        self._load_into_tab(pf, path)
        self._file_dir = os.path.dirname(os.path.abspath(path))

    def _load_into_tab(self, pf, path):
        tab = PlotTab(self._theme, self._scale, pf.worksheet)
        tab.changed.connect(self._sync_tab)
        tab.load(pf, path)
        current = self.current_tab()
        if current is not None and current.is_pristine():
            index = self.tabs.indexOf(current)
            self.tabs.insertTab(index, tab, tab.title)
            self.tabs.removeTab(index + 1)
            current.deleteLater()
        else:
            self.tabs.addTab(tab, tab.title)
        self.tabs.setCurrentWidget(tab)
        self._sync_tab()
        return tab

    def open_copy(self, path, title='Plot'):
        """Open *path* as a detached copy: Save asks for a location."""
        try:
            pf = load_plot_file(path)
        except (OSError, PlotDocumentError, PlotFileError) as e:
            QMessageBox.warning(
                self, 'Open',
                'Could not open %s:\n%s' % (os.path.basename(path), e))
            return
        tab = self._load_into_tab(pf, path)
        tab.detach(title)

    def _save(self, tab):
        """Save *tab*; returns True only when a file was written."""
        if tab.path is not None:
            return self._save_to(tab, tab.path)
        return self._save_as(tab)

    def _save_as(self, tab):
        start = tab.path or os.path.join(
            self._file_dir, tab.title + NATIVE_PLOT_SUFFIX)
        path, _f = QFileDialog.getSaveFileName(
            self, 'Save As', start, NATIVE_PLOT_FILTER)
        if not path:
            return False
        return self._save_to(tab, with_suffix(path, 'ilmplot'))

    def _save_to(self, tab, path):
        try:
            tab.save(path)
        except PlotFileError as e:
            QMessageBox.information(self, 'Save', str(e))
            return False
        except (OSError, PlotDocumentError, ValueError) as e:
            QMessageBox.warning(
                self, 'Save',
                'Could not save the plot:\n' + str(e))
            return False
        self._file_dir = os.path.dirname(os.path.abspath(path))
        return True

    def _export(self, tab, key):
        if tab.plot is None:
            return
        dialog_filter, suffix = EXPORT_FORMATS[key]
        path, _f = QFileDialog.getSaveFileName(
            self, 'Export',
            os.path.join(self._export_dir, 'Plot' + suffix),
            dialog_filter)
        if not path:
            return
        path = with_suffix(path, key)
        try:
            export_plot(tab.plot.series, tab.plot.chart_key, path, key)
        except (OSError, PlotDocumentError, ValueError) as e:
            QMessageBox.warning(
                self, 'Export',
                'Could not export the plot:\n' + str(e))
            return
        self._export_dir = os.path.dirname(path)

    # ── closing ─────────────────────────────────────────────────────
    def _confirm_close(self, tab):
        if not tab.dirty:
            return True
        self.tabs.setCurrentWidget(tab)
        result = QMessageBox.question(
            self, 'Save',
            'Save changes to "%s" before closing?' % tab.title,
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save)
        if result == QMessageBox.StandardButton.Save:
            return self._save(tab)
        return result == QMessageBox.StandardButton.Discard

    def _close_tab(self, index):
        tab = self.tabs.widget(index)
        if tab is None or not self._confirm_close(tab):
            return
        self.tabs.removeTab(index)
        tab.deleteLater()
        if self.tabs.count() == 0:
            self._add_tab()
        else:
            self._sync_tab()

    def closeEvent(self, event):
        for i in range(self.tabs.count()):
            tab = self.tabs.widget(i)
            if tab.dirty and not self._confirm_close(tab):
                event.ignore()
                return
        event.accept()

    def _add_menu_items(self, menu, keys, export_menu=None):
        for key in keys:
            if key is None:
                menu.addSeparator()
            elif key == 'export':
                menu.addMenu(export_menu)
            else:
                menu.addAction(self.editor_actions[key])

    def _build_menus(self):
        bar = self.menuBar()

        self._export_menu = QMenu('Export', self)
        for key in EXPORT_MENU:
            self._export_menu.addAction(self.editor_actions[key])

        file_menu = bar.addMenu('File')
        self._add_menu_items(file_menu, FILE_MENU,
                             export_menu=self._export_menu)

        edit_menu = bar.addMenu('Edit')
        self._add_menu_items(edit_menu, EDIT_MENU)

        plot_menu = bar.addMenu('Plot')
        plot_menu.addAction(self.editor_actions['plot'])
        plot_menu.addSeparator()
        for group in CHART_GROUPS:
            submenu = plot_menu.addMenu(group.text)
            for chart in group.charts:
                submenu.addAction(self.chart_actions[(group.key,
                                                      chart.key)])
        plot_menu.addSeparator()
        for key in ('edit_data', 'axes', 'legend', 'style'):
            plot_menu.addAction(self.editor_actions[key])

        help_menu = bar.addMenu('Help')
        self._add_menu_items(help_menu, HELP_MENU)

    def _build_toolbar(self):
        toolbar = QToolBar(self)
        toolbar.setObjectName('plotToolbar')
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        toolbar.setContextMenuPolicy(Qt.ContextMenuPolicy.PreventContextMenu)
        toolbar.toggleViewAction().setEnabled(False)
        toolbar.setIconSize(QSize(20, 20))
        toolbar.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon)

        toolbar.addAction(self.editor_actions['undo'])
        toolbar.addAction(self.editor_actions['redo'])
        toolbar.addSeparator()
        toolbar.addAction(self.editor_actions['new'])
        toolbar.addAction(self.editor_actions['open'])
        toolbar.addAction(self.editor_actions['save'])
        toolbar.addSeparator()

        self._plot_menu = QMenu(self)
        for group in CHART_GROUPS:
            submenu = self._plot_menu.addMenu(group.text)
            for chart in group.charts:
                submenu.addAction(self.chart_actions[(group.key,
                                                      chart.key)])
        self._plot_button = QToolButton(self)
        self._plot_button.setPopupMode(
            QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self._plot_button.setDefaultAction(self.editor_actions['plot'])
        self._plot_button.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._plot_button.setMenu(self._plot_menu)
        toolbar.addWidget(self._plot_button)

        spacer = QWidget(self)
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding,
                             QSizePolicy.Policy.Preferred)
        spacer.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        spacer.setStyleSheet('background: transparent;')
        toolbar.addWidget(spacer)

        self._export_button = QToolButton(self)
        self._export_button.setPopupMode(
            QToolButton.ToolButtonPopupMode.InstantPopup)
        self._export_button.setText('Export')
        self._export_button.setIcon(
            chrome.themed_icon('export', self._theme, 'on_accent'))
        self._export_button.setProperty('primary', True)
        self._export_button.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._export_button.setMenu(self._export_menu)
        toolbar.addWidget(self._export_button)

        self.addToolBar(toolbar)
        install_button_feedback(toolbar)

    def exec(self) -> int:
        """Compatibility adapter: launch the standalone process, reject."""
        if getattr(sys, 'frozen', False):
            args = ['--plot-editor']
            workdir = os.path.dirname(sys.executable)
        else:
            script = os.path.join(os.path.dirname(os.path.dirname(
                os.path.dirname(os.path.abspath(__file__)))), 'main.py')
            args = [script, '--plot-editor']
            workdir = os.path.dirname(script)
        doc = self._ilm_document
        if isinstance(doc, PlotDocument) and not _is_default_document(doc):
            try:
                args = args + ['--ilm-copy', write_ilm_copy(doc)]
            except (OSError, PlotDocumentError) as e:
                QMessageBox.warning(
                    None, 'Plot Editor',
                    'Unable to pass the plot to Plot Editor:\n' + str(e))
        started, _pid = QProcess.startDetached(sys.executable, args, workdir)
        if not started:
            QMessageBox.warning(None, 'Plot Editor',
                                'Unable to launch Plot Editor.')
        return 0
