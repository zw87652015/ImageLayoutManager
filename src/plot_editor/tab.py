"""Per-tab worksheet + plot canvas for the Plot Editor."""

from __future__ import annotations

import os
from dataclasses import dataclass

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QSplitter, QVBoxLayout, QWidget

from .export import document_from_plot
from .plot_canvas import PlotCanvas
from .plot_data import PlotSelectionError, build_series
from .plot_file import (PlotFileError, chart_from_document,
                        save_plot_file, series_from_document)
from .plotting import figure_svg, make_figure
from .worksheet import Worksheet
from .worksheet_view import WorksheetView

_SUFFIX = '.ilmplot.svg'


@dataclass
class PlotState:
    series: list
    chart_key: 'str | None'
    plot_columns: tuple
    document: object = None


class PlotTab(QSplitter):
    """One editor tab: worksheet (left) and zoomable plot canvas (right)."""

    changed = pyqtSignal()

    def __init__(self, theme, scale=1.0, worksheet=None, parent=None):
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.setObjectName('plotWorkspace')
        self.setChildrenCollapsible(False)
        self.worksheet = worksheet if worksheet is not None else Worksheet()
        self.worksheet_view = WorksheetView(self.worksheet, theme, scale)
        left = QWidget()
        left.setObjectName('plotLeftArea')
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)
        left_layout.addWidget(self.worksheet_view)
        self.plot_canvas = PlotCanvas(theme)
        right = QWidget()
        right.setObjectName('plotRightArea')
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        right_layout.addWidget(self.plot_canvas)
        self.addWidget(left)
        self.addWidget(right)
        self.path = None
        self.title = 'Untitled'
        self.dirty = False
        self.plot = None
        self.worksheet.add_listener(self._on_worksheet_event)

    def _on_worksheet_event(self, event):
        if event == ('history',):
            self.dirty = True
            self.changed.emit()

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
        self.plot_canvas.show_svg(
            figure_svg(make_figure(series, chart_key)))
        self.plot = PlotState(series, chart_key, columns, None)
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
        self.plot = PlotState(series, chart, columns, pf.document)
        self._set_path(path)
        self.dirty = False
        self.changed.emit()

    def save(self, path):
        """Write this tab as ``*.ilmplot.svg``; raises PlotFileError."""
        if self.plot is None:
            raise PlotFileError('Create a plot before saving.')
        doc = self.plot.document
        if doc is None:
            doc = document_from_plot(self.plot.series,
                                     self.plot.chart_key)
        save_plot_file(path, doc, self.worksheet,
                       self.plot.chart_key, self.plot.plot_columns)
        self._set_path(path)
        self.dirty = False
        self.changed.emit()
