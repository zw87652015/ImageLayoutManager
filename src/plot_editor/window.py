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
from PyQt6.QtWidgets import (QDialog, QFileDialog, QMainWindow, QMenu,
                             QMessageBox,
                             QSizePolicy, QTabWidget, QToolBar,
                             QToolButton, QWidget)

from src.app.motion import install_button_feedback

from . import chrome, palettes, presets, theme_store
from .about_dialog import PlotEditorAboutDialog
from .actions import (ACTIONS, CHART_GROUPS, DEFAULT_CHART, EDIT_MENU,
                      EXPORT_MENU, FILE_MENU, HELP_MENU,
                      NATIVE_PLOT_FILTER, NATIVE_PLOT_SUFFIX)
from .document import PlotDocument, PlotDocumentError
from .export import EXPORT_FORMATS, export_plot, with_suffix
from .i18n import history_label, tr
from .ilm_bridge import (_is_default_document, copy_ilm_source,
                         is_ilm_store_file, write_ilm_copy)
from .plot_data import PlotSelectionError
from .plot_file import PlotFileError, load_plot_file
from .tab import PlotTab


class PlotEditorWindow(QMainWindow):
    """Top-level Plot Editor window hosting ``PlotTab`` documents."""

    action_requested = pyqtSignal(str)
    plot_requested = pyqtSignal(str, str)
    export_requested = pyqtSignal(str)

    def __init__(self, document=None, parent=None, *, for_ilm=False,
                 source_path=None):
        super().__init__()
        self.result_document = None
        self._ilm_document = document
        self._ilm_source_path = source_path
        self.current_chart = DEFAULT_CHART
        self.native_plot_filter = NATIVE_PLOT_FILTER
        self._export_dir = os.path.expanduser('~')
        self._file_dir = os.path.expanduser('~')
        self._import_dir = os.path.expanduser('~')
        self._untitled = 0
        self._theme = chrome.saved_theme()
        self._scale = chrome.saved_font_scale()
        # One preset store shared by the tabs' Style menus and the
        # Plot Style manager.
        self.preset_store = presets.PresetStore(chrome.preset_root())
        # Custom colour themes ('custom:<name>' palette refs) resolve
        # through palettes' registry, refreshed after theme edits.
        self.theme_store = theme_store.ThemeStore(chrome.theme_root())
        palettes.set_custom_themes(self.theme_store.mapping())
        self.resize(960, 640)

        self.tabs = QTabWidget()
        self.tabs.setObjectName('plotTabs')
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.setDocumentMode(True)
        self.tabs.currentChanged.connect(lambda _i: self._sync_tab())
        self.tabs.tabCloseRequested.connect(self._close_tab)
        self.setCentralWidget(self.tabs)
        self.setAcceptDrops(True)

        self.editor_actions = {}
        for key, spec in ACTIONS.items():
            action = QAction(tr('act_' + key), self)
            action.setObjectName('action_' + key)
            action.setData(key)
            if spec.shortcut:
                action.setShortcut(QKeySequence(spec.shortcut))
            if spec.icon:
                action.setIcon(chrome.themed_icon(spec.icon, self._theme))
            action.setToolTip(tr('tip_' + key))
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
                action = QAction(tr('chart_' + chart.key), self)
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
        tab = PlotTab(self._theme, self._scale, worksheet,
                      preset_store=self.preset_store,
                      open_style_manager=self._open_style_manager)
        if self.tabs.count() == 0:
            # Fresh window or last-tab replacement: plain 'Untitled',
            # and the counter restarts so it never creeps upward.
            self._untitled = 0
            tab.title = tr('untitled_plain')
        else:
            self._untitled += 1
            tab.title = tr('untitled', n=self._untitled)
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
        self.setWindowTitle(tr('window_title', name=tab.title))
        self._sync_history_actions()
        self._sync_export_actions()

    def _sync_history_actions(self):
        ws = self.worksheet
        undo = self.editor_actions['undo']
        redo = self.editor_actions['redo']
        undo.setEnabled(ws.can_undo)
        redo.setEnabled(ws.can_redo)
        undo.setToolTip(tr('undo_with', action=history_label(
            ws.undo_label)) if ws.can_undo else tr('tip_undo'))
        redo.setToolTip(tr('redo_with', action=history_label(
            ws.redo_label)) if ws.can_redo else tr('tip_redo'))

    def _sync_export_actions(self):
        tab = self.current_tab()
        ready = tab.plot is not None
        for key in EXPORT_MENU:
            self.editor_actions[key].setEnabled(ready)
        self.editor_actions['add_note'].setEnabled(ready)
        bracket_ok = False
        if ready:
            from .export import CHART_KIND
            kind = CHART_KIND.get(tab.plot.chart_key,
                                  ('line', None))[0]
            if kind in ('violin', 'stacked_column'):
                doc = tab.effective_document()
                bracket_ok = doc is not None and len(
                    doc.groups or doc.categories) >= 2
        self.editor_actions['add_bracket'].setEnabled(bracket_ok)
        self._export_button.setEnabled(ready)
        self._export_button.setIcon(chrome.themed_icon(
            'export', self._theme, 'on_accent' if ready else 'text_tert'))
        self._export_button.setToolTip(
            tr('export_ready') if ready else tr('export_needs'))

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
        elif key == 'import_data':
            self._import_data()
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
        elif key == 'style':
            self._open_style_manager()
        elif key == 'tutorials':
            self.show_tutorials()
        elif key == 'about':
            self._show_about()
        elif key == 'add_note':
            tab.add_text()
        elif key == 'add_bracket':
            tab.add_bracket()
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

    def _show_about(self):
        """Help → About Plot Editor."""
        PlotEditorAboutDialog(self._theme, self._scale, self).exec()

    def show_tutorials(self):
        """Help → Tutorials…: the lesson chooser (created lazily)."""
        if getattr(self, '_tutorials', None) is None:
            from .tutorial import TutorialController
            self._tutorials = TutorialController(self)
        self._tutorials.show_chooser()

    def _open_style_manager(self):
        from .style_manager import StyleManagerDialog
        dialog = StyleManagerDialog(self.preset_store, self.current_tab(),
                                    self._theme, self._scale, self)
        dialog.exec()

    def open_theme_editor(self):
        """Colour Theme ▸ Edit… — manage custom palettes."""
        from .theme_editor import ThemeEditorDialog
        dialog = ThemeEditorDialog(self.theme_store, self._theme, self,
                                   on_change=self._themes_changed)
        dialog.exec()

    def _themes_changed(self):
        """Reinstall the custom-theme registry and re-render open plots
        that may reference edited themes."""
        from . import style_icons
        palettes.set_custom_themes(self.theme_store.mapping())
        style_icons.clear_cache()
        for i in range(self.tabs.count()):
            tab = self.tabs.widget(i)
            if tab.plot is not None:
                try:
                    tab._render_preview()
                except Exception:
                    pass
        self._sync_tab()

    def _select_chart(self, group_key, chart_key, emit=True):
        self.current_chart = (group_key, chart_key)
        self.chart_actions[(group_key, chart_key)].setChecked(True)
        group = next(g for g in CHART_GROUPS if g.key == group_key)
        chart = next(c for c in group.charts if c.key == chart_key)
        self.editor_actions['plot'].setToolTip(tr(
            'plot_tooltip', chart=tr('chart_' + chart.key),
            group=tr('grp_' + group.key)))
        if emit:
            self.action_requested.emit('plot')
            self.plot_requested.emit(group_key, chart_key)
            self._plot(group_key, chart_key)

    def _plot(self, group_key, chart_key):
        try:
            self.current_tab().plot_current(chart_key)
        except PlotSelectionError as e:
            QMessageBox.information(self, tr('dlg_plot'), str(e))

    # ── file operations ─────────────────────────────────────────────
    def open_paths(self, paths):
        for path in paths:
            self._open_path(path)

    # ── drag & drop ─────────────────────────────────────────────────
    @staticmethod
    def _drop_plot_paths(mime_data):
        from .ilm_bridge import is_native_plot_path
        if not mime_data.hasUrls():
            return []
        return [u.toLocalFile() for u in mime_data.urls()
                if u.isLocalFile() and is_native_plot_path(u.toLocalFile())]

    @staticmethod
    def _drop_data_paths(mime_data):
        from .import_dialog import is_data_path
        if not mime_data.hasUrls():
            return []
        return [u.toLocalFile() for u in mime_data.urls()
                if u.isLocalFile() and is_data_path(u.toLocalFile())]

    def dragEnterEvent(self, event):
        if self._drop_plot_paths(event.mimeData()) \
                or self._drop_data_paths(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        self.dragEnterEvent(event)

    def dropEvent(self, event):
        paths = self._drop_plot_paths(event.mimeData())
        if paths:
            event.acceptProposedAction()
            self.open_paths(paths)
            return
        data = self._drop_data_paths(event.mimeData())
        if not data:
            event.ignore()
            return
        event.acceptProposedAction()
        self._import_path(data[0])

    # ── data import ──────────────────────────────────────────────────
    def _import_data(self):
        filters = '%s;;%s;;%s' % (tr('imp_filter_data'),
                                  tr('imp_filter_excel'),
                                  tr('imp_filter_all'))
        path, _f = QFileDialog.getOpenFileName(
            self, tr('dlg_import'), self._import_dir, filters)
        if path:
            self._import_dir = os.path.dirname(os.path.abspath(path))
            self._import_path(path)

    def _import_path(self, path):
        from .import_dialog import ImportDialog
        from .worksheet import Worksheet, WorksheetLimitError
        tab = self.current_tab()
        ws = tab.worksheet
        has_data = ws.row_count > 0 or any(
            c.long_name or c.units or c.comments for c in ws.columns)
        dialog = ImportDialog(path, has_data, self._theme, self._scale,
                              self)
        if dialog.exec() != QDialog.DialogCode.Accepted \
                or not dialog.columns:
            return
        columns = dialog.columns
        if dialog.destination == 'new_tab':
            new_tab = self._add_tab(Worksheet.from_columns(columns))
            new_tab.title = os.path.splitext(
                os.path.basename(path))[0]
            new_tab.dirty = True
            new_tab.changed.emit()
            self._sync_tab()
            return
        try:
            if dialog.destination == 'append':
                ws.append_columns(columns)
            else:
                ws.replace_all(columns)
        except (WorksheetLimitError, ValueError) as e:
            QMessageBox.warning(self, tr('dlg_import'), str(e))

    def _open_dialog(self):
        paths, _f = QFileDialog.getOpenFileNames(
            self, tr('dlg_open'), self._file_dir, NATIVE_PLOT_FILTER)
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
                self, tr('dlg_open'),
                tr('msg_open_failed', name=os.path.basename(path),
                   error=e))
            return
        tab = self._load_into_tab(pf, path)
        if pf.read_only_source:
            # The worksheet node could not be read and was rebuilt —
            # detach so the original file cannot be overwritten.
            tab.detach(tab.title)
            if pf.warnings:
                QMessageBox.information(
                    self, tr('dlg_open'), '\n'.join(pf.warnings))
        self._file_dir = os.path.dirname(os.path.abspath(path))

    def _load_into_tab(self, pf, path):
        tab = PlotTab(self._theme, self._scale, pf.worksheet,
                      preset_store=self.preset_store,
                      open_style_manager=self._open_style_manager)
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
                self, tr('dlg_open'),
                tr('msg_open_failed', name=os.path.basename(path),
                   error=e))
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
            self, tr('dlg_save_as'), start, NATIVE_PLOT_FILTER)
        if not path:
            return False
        return self._save_to(tab, with_suffix(path, 'ilmplot'))

    def _save_to(self, tab, path):
        try:
            tab.save(path)
        except PlotFileError as e:
            QMessageBox.information(self, tr('dlg_save'), str(e))
            return False
        except (OSError, PlotDocumentError, ValueError) as e:
            QMessageBox.warning(
                self, tr('dlg_save'),
                tr('msg_save_failed', error=e))
            return False
        self._file_dir = os.path.dirname(os.path.abspath(path))
        tutorials = getattr(self, '_tutorials', None)
        if tutorials is not None:
            tutorials.on_saved(tab)
        return True

    def _export(self, tab, key):
        if tab.plot is None:
            return
        dialog_filter, suffix = EXPORT_FORMATS[key]
        path, _f = QFileDialog.getSaveFileName(
            self, tr('dlg_export'),
            os.path.join(self._export_dir, 'Plot' + suffix),
            dialog_filter)
        if not path:
            return
        path = with_suffix(path, key)
        try:
            export_plot(tab.effective_document(), path, key)
        except (OSError, PlotDocumentError, ValueError) as e:
            QMessageBox.warning(
                self, tr('dlg_export'),
                tr('msg_export_failed', error=e))
            return
        self._export_dir = os.path.dirname(path)

    # ── closing ─────────────────────────────────────────────────────
    def _confirm_close(self, tab):
        if not tab.dirty:
            return True
        self.tabs.setCurrentWidget(tab)
        result = QMessageBox.question(
            self, tr('dlg_save'),
            tr('msg_unsaved', name=tab.title),
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

        self._export_menu = QMenu(tr('menu_export'), self)
        for key in EXPORT_MENU:
            self._export_menu.addAction(self.editor_actions[key])

        file_menu = bar.addMenu(tr('menu_file'))
        self._add_menu_items(file_menu, FILE_MENU,
                             export_menu=self._export_menu)

        edit_menu = bar.addMenu(tr('menu_edit'))
        self._add_menu_items(edit_menu, EDIT_MENU)

        plot_menu = bar.addMenu(tr('menu_plot'))
        plot_menu.addAction(self.editor_actions['plot'])
        plot_menu.addSeparator()
        for group in CHART_GROUPS:
            submenu = plot_menu.addMenu(tr('grp_' + group.key))
            for chart in group.charts:
                submenu.addAction(self.chart_actions[(group.key,
                                                      chart.key)])
        plot_menu.addSeparator()
        plot_menu.addAction(self.editor_actions['add_note'])
        plot_menu.addAction(self.editor_actions['add_bracket'])
        plot_menu.addSeparator()
        self._theme_menu = plot_menu.addMenu(tr('menu_colour_theme'))
        self._theme_menu.aboutToShow.connect(
            lambda: self.current_tab().fill_theme_menu(
                self._theme_menu))
        plot_menu.addSeparator()
        plot_menu.addAction(self.editor_actions['style'])

        help_menu = bar.addMenu(tr('menu_help'))
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
            submenu = self._plot_menu.addMenu(tr('grp_' + group.key))
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
        self._export_button.setText(tr('menu_export'))
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
                source = self._ilm_source_path
                if source and os.path.isfile(source) \
                        and not is_ilm_store_file(source):
                    args = args + [source]
                else:
                    if source and os.path.isfile(source):
                        try:
                            tmp = copy_ilm_source(source)
                        except OSError:
                            tmp = write_ilm_copy(doc)
                    else:
                        tmp = write_ilm_copy(doc)
                    args = args + ['--ilm-copy', tmp]
            except (OSError, PlotDocumentError) as e:
                QMessageBox.warning(
                    None, tr('app_name'),
                    tr('msg_handoff_failed', error=e))
        started, _pid = QProcess.startDetached(sys.executable, args, workdir)
        if not started:
            QMessageBox.warning(None, tr('app_name'),
                                tr('msg_launch_failed'))
        return 0
