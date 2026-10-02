"""Per-tab worksheet + plot canvas for the Plot Editor."""

from __future__ import annotations

import os
from dataclasses import dataclass

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QMessageBox, QSplitter, QToolButton,
                             QVBoxLayout, QWidget)

from .i18n import tr
from .overrides import (PlotOverrides, apply_update,
                        effective_document,
                        overrides_from_document, remap_series_keys)
from .plot_canvas import PlotCanvas
from .plot_data import PlotSelectionError, build_series
from .plot_file import (PlotFileError, chart_from_document,
                        save_plot_file, series_from_document)
from .document import PlotDocumentError
from .render import element_regions, render_document
from .chrome import reset_all_stylesheet, themed_icon
from .title_field import PlotTitleField
from .worksheet import Worksheet
from .worksheet_view import WorksheetView

_SUFFIX = '.ilmplot.svg'


@dataclass
class PlotState:
    series: list
    chart_key: 'str | None'
    plot_columns: tuple
    document: object = None
    # True when ``document`` came from a file with no worksheet node and
    # the plot hasn't been regenerated since — it stays the render base
    # so legacy colours/settings survive.
    legacy_base: bool = False


def _shift_columns(columns, event):
    """Remap a column tuple for insert/remove events (same rule as
    ``remap_series_keys``)."""
    name, at, count = event[0], event[1], event[2]
    out = []
    for c in columns:
        if name == 'columns_inserted':
            out.append(c + count if c >= at else c)
        elif at <= c < at + count:
            continue
        else:
            out.append(c - count if c >= at + count else c)
    return tuple(out)


class PlotTab(QSplitter):
    """One editor tab: worksheet (left) and zoomable plot canvas (right)."""

    changed = pyqtSignal()

    def __init__(self, theme, scale=1.0, worksheet=None, parent=None):
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.setObjectName('plotWorkspace')
        self.setChildrenCollapsible(False)
        self.theme = theme
        self.scale = scale
        self.worksheet = worksheet if worksheet is not None else Worksheet()
        self.worksheet_view = WorksheetView(self.worksheet, theme, scale)
        left = QWidget()
        left.setObjectName('plotLeftArea')
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)
        left_layout.addWidget(self.worksheet_view)
        self.plot_canvas = PlotCanvas(theme)
        self.title_field = PlotTitleField(theme, scale)
        right = QWidget()
        right.setObjectName('plotRightArea')
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        right_layout.addWidget(self.title_field)
        right_layout.addWidget(self.plot_canvas)
        self.addWidget(left)
        self.addWidget(right)
        # Overall "Reset formatting" overlay: bottom-right of the plot
        # area, positioned relative to the window (not the scene).
        self._right_area = right
        self.reset_all = QToolButton(right)
        self.reset_all.setObjectName('plotResetAll')
        self.reset_all.setIcon(themed_icon('reset', theme, 'text_sec'))
        self.reset_all.setText(tr('reset_all'))
        self.reset_all.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.reset_all.setStyleSheet(reset_all_stylesheet(theme, scale))
        self.reset_all.setVisible(False)
        self.reset_all.clicked.connect(self._reset_all_formatting)
        right.installEventFilter(self)
        self.changed.connect(self._update_reset_all)
        # Dropped files belong to the window: children must not swallow
        # them (QGraphicsView/QTableView accept drops by default).
        for w in (self.plot_canvas, self.worksheet_view,
                  getattr(self.worksheet_view, '_labels', None)):
            if w is not None:
                w.setAcceptDrops(False)
                if w.viewport() is not None:
                    w.viewport().setAcceptDrops(False)
        self.path = None
        self.title = tr('untitled', n=0)
        self.dirty = False
        self.plot = None
        self.plot_title = ''
        self.overrides = PlotOverrides()
        self.regions = None
        self.title_field.title_changed.connect(self._on_title_changed)
        self.plot_canvas.element_activated.connect(self._open_element_panel)
        self.worksheet.add_listener(self._on_worksheet_event)

    def _on_title_changed(self, text):
        self.plot_title = text
        self._render_preview()
        self.dirty = True
        self.changed.emit()

    def set_plot_title(self, text):
        """Update the title (from the field or the element panel)."""
        self.plot_title = text
        if self.title_field.title() != text:
            self.title_field.set_title(text)
        self._render_preview()
        self.dirty = True
        self.changed.emit()

    def _open_element_panel(self, key, global_pos):
        from .element_panel import ElementPanel
        ElementPanel.open_for(self, key, global_pos)

    def effective_document(self):
        """The styled ``PlotDocument`` for preview/save/export, or None."""
        if self.plot is None:
            return None
        base = self.plot.document if self.plot.legacy_base else None
        return effective_document(base, self.plot.series,
                                  self.plot.chart_key, self.plot_title,
                                  self.overrides)

    def update_overrides(self, fn):
        """Apply ``fn(self.overrides)`` then re-render + mark dirty.

        The single entry point for in-place style edits (the element
        panels). Crash-safe: on any failure the pre-edit overrides are
        restored and re-rendered, and the traceback goes to stderr — a
        slot exception must never reach Qt (PyQt6 aborts on those).
        """
        if not apply_update(self.overrides, fn, self._render_preview):
            return
        self.dirty = True
        self.changed.emit()

    def _render_preview(self, keep_view=True):
        if self.plot is None:
            return
        doc = self.effective_document()
        try:
            svg = render_document(doc).svg
            self.regions = element_regions(doc)
        except PlotDocumentError as e:
            # Keep the previous canvas; the window shows its info dialog.
            raise PlotSelectionError(str(e)) from e
        self.plot_canvas.show_svg(svg, keep_view=keep_view)
        self.plot_canvas.set_regions(self.regions)

    def eventFilter(self, obj, event):
        from PyQt6.QtCore import QEvent
        if obj is self._right_area \
                and event.type() == QEvent.Type.Resize:
            self._position_reset_all()
        return super().eventFilter(obj, event)

    def _position_reset_all(self):
        area = self._right_area
        self.reset_all.adjustSize()
        self.reset_all.move(area.width() - self.reset_all.width() - 12,
                            area.height() - self.reset_all.height() - 12)
        self.reset_all.raise_()

    def _update_reset_all(self):
        self.reset_all.setVisible(self.plot is not None)
        self.reset_all.setEnabled(not self.overrides.is_empty())
        if self.plot is not None:
            self._position_reset_all()

    def _reset_all_formatting(self):
        box = QMessageBox.question(
            self, tr('reset_all'),
            tr('reset_all_confirm'))
        if box == QMessageBox.StandardButton.Yes:
            fresh = PlotOverrides()
            self.update_overrides(lambda o: self._copy_overrides(o, fresh))

    @staticmethod
    def _copy_overrides(target, source):
        target.xlabel = source.xlabel
        target.ylabel = source.ylabel
        target.legend = source.legend
        target.legend_location = source.legend_location
        target.grid = source.grid
        target.xlim = source.xlim
        target.ylim = source.ylim
        target.style = source.style
        target.series = source.series

    def _on_worksheet_event(self, event):
        if event == ('history',):
            self.dirty = True
            self.changed.emit()
        if event[0] in ('columns_inserted', 'columns_removed'):
            remap_series_keys(self.overrides, event)
            if self.plot is not None:
                self.plot.plot_columns = _shift_columns(
                    self.plot.plot_columns, event)
        if event == ('history',) and self.plot is not None:
            self._refresh_from_sheet()

    def _refresh_from_sheet(self):
        """Re-plot the current columns after a committed worksheet edit.

        History events fire only for finished edits (Enter / focus loss,
        paste, structural ops, undo/redo), never while typing. A sheet that
        no longer yields a plottable selection keeps the previous preview.
        """
        try:
            self.plot.series = build_series(self.worksheet,
                                            list(self.plot.plot_columns))
            self._render_preview()
        except PlotSelectionError:
            pass

    def _set_path(self, path):
        self.path = path
        name = os.path.basename(path)
        self.title = (name[:-len(_SUFFIX)]
                      if name.lower().endswith(_SUFFIX)
                      else os.path.splitext(name)[0])

    def detach(self, title):
        """Unlink this tab from its file: Save As prompts, close warns."""
        self.path = None
        self.title = title
        self.dirty = True
        self.changed.emit()

    def is_pristine(self):
        return (self.path is None and not self.dirty
                and self.plot is None and not self.worksheet.can_undo)

    def plot_current(self, chart_key):
        """Plot the current selection; PlotSelectionError propagates."""
        columns = tuple(self.worksheet_view.selected_columns())
        series = build_series(self.worksheet, columns)
        self.plot = PlotState(series, chart_key, columns, None)
        self._render_preview(keep_view=False)
        self.dirty = True
        self.changed.emit()

    def load(self, pf, path):
        """Fill this (fresh) tab with a loaded ``PlotFile``."""
        self.plot_canvas.show_svg(pf.svg)
        if pf.has_worksheet:
            columns = tuple(pf.plot_columns)
        else:
            columns = tuple(range(self.worksheet.column_count))
        chart = pf.chart_key or chart_from_document(pf.document)
        try:
            series = build_series(self.worksheet, list(columns))
        except PlotSelectionError:
            series = series_from_document(pf.document)
        self.plot = PlotState(series, chart, columns, pf.document,
                              legacy_base=not pf.has_worksheet)
        # Node v2 carries the overrides; older/ILM files seed them from
        # the document (style cloned; only fields differing from defaults).
        self.overrides = pf.overrides if pf.overrides is not None \
            else overrides_from_document(pf.document)
        self.regions = None
        self._set_path(path)
        self.plot_title = pf.document.title or ''
        self.title_field.set_title(self.plot_title)
        # Preview uses the same native effective document that save and
        # ILM rendering consume; if it can't render, keep the file's SVG.
        try:
            self._render_preview()
        except PlotSelectionError:
            pass
        self.dirty = False
        self.changed.emit()

    def save(self, path):
        """Write this tab as ``*.ilmplot.svg``; raises PlotFileError."""
        if self.plot is None:
            raise PlotFileError(tr('msg_no_plot'))
        save_plot_file(path, self.effective_document(), self.worksheet,
                       self.plot.chart_key, self.plot.plot_columns,
                       self.overrides)
        self._set_path(path)
        self.dirty = False
        self.changed.emit()
