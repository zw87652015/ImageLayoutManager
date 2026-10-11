"""Heatmap native plots in the Plot Editor's non-UI paths (no Qt).

Load, effective document, re-save and reload must keep the cell grid
intact and never regenerate a heatmap from the (empty) worksheet.
"""
import os
import tempfile
import unittest

import src  # noqa: F401  -- puts packages/ilmplot/src on sys.path

from ilmplot.document import HeatmapOptions, PlotDocument
from ilmplot.render import render_document

from src.plot_editor import plot_file
from src.plot_editor.overrides import (effective_document,
                                       overrides_from_document)
from src.plot_editor.plot_data import PlotSelectionError, build_series
from src.plot_editor.worksheet import Worksheet


def _heatmap_doc():
    doc = PlotDocument(
        kind='heatmap', series=[], title='Heat', xlabel='columns',
        ylabel='rows',
        heatmap=HeatmapOptions(
            values=[[0.0, 1.0, None], [2.0, 3.0, 4.0]],
            extent=[-0.5, 2.5, 1.5, -0.5], cmap='plasma', vmin=0.5,
            colorbar_label='Value'))
    return doc.validate()


class HeatmapEditorTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name
        self.doc = _heatmap_doc()
        self.path = os.path.join(self.dir, 'h.ilmplot.svg')
        with open(self.path, 'wb') as fh:
            fh.write(render_document(self.doc).svg)

    def tearDown(self):
        self._tmp.cleanup()

    def _load(self, path=None):
        return plot_file.load_plot_file(path or self.path)

    def test_load_has_no_chart_or_worksheet(self):
        pf = self._load()
        self.assertFalse(pf.has_worksheet)
        self.assertIsNone(pf.chart_key)
        self.assertEqual(pf.document.to_dict(), self.doc.to_dict())
        self.assertEqual(plot_file.chart_from_document(pf.document), None)
        self.assertEqual(plot_file.items_from_document(pf.document), [])
        self.assertEqual(pf.worksheet.column_count,
                         Worksheet().column_count)

    def test_effective_document_is_lossless(self):
        pf = self._load()
        ov = overrides_from_document(pf.document, [], None)
        eff = effective_document(
            pf.document, [], None, pf.document.title, ov)
        self.assertEqual(eff.to_dict(), self.doc.to_dict())

    def test_title_and_limits_edit_keeps_grid(self):
        pf = self._load()
        ov = overrides_from_document(pf.document, [], None)
        ov.xlabel = 'cols'
        ov.xlim = [-1.0, 3.0]
        eff = effective_document(
            pf.document, [], None, 'New title', ov)
        self.assertEqual(eff.title, 'New title')
        self.assertEqual(eff.xlabel, 'cols')
        self.assertEqual(eff.xlim, [-1.0, 3.0])
        self.assertEqual(eff.heatmap.to_dict(), self.doc.heatmap.to_dict())
        out = os.path.join(self.dir, 'edited.ilmplot.svg')
        plot_file.save_plot_file(out, eff, pf.worksheet, pf.chart_key,
                                 pf.plot_columns, ov)
        again = self._load(out)
        self.assertEqual(again.document.title, 'New title')
        self.assertEqual(again.document.heatmap.to_dict(),
                         self.doc.heatmap.to_dict())

    def test_resave_round_trip_is_stable(self):
        pf = self._load()
        ov = overrides_from_document(pf.document, [], None)
        current = pf.document
        for i in range(2):
            eff = effective_document(
                current, [], None, current.title, ov)
            out = os.path.join(self.dir, f'r{i}.ilmplot.svg')
            plot_file.save_plot_file(out, eff, pf.worksheet, pf.chart_key,
                                     pf.plot_columns, ov)
            current = self._load(out).document
            self.assertEqual(current.to_dict(), self.doc.to_dict())

    def test_worksheet_items_not_used_for_heatmaps(self):
        # An empty sheet cannot regenerate a plot: the tab catches the
        # selection error and keeps the loaded document (see tab.load).
        with self.assertRaises(PlotSelectionError):
            build_series(Worksheet(), ())


if __name__ == '__main__':
    unittest.main()
