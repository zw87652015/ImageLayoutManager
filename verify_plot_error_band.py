"""Non-UI verification for the 'error as band' feature and the
legacy-file series-look seeding fix.

Run from the repo root: ``python -m unittest verify_plot_error_band``.
"""

import os
import tempfile
import unittest

import src  # noqa: F401  -- puts packages/ilmplot/src on sys.path

import ilmplot
from ilmplot.document import LineSeries, PlotDocument

from src.plot_editor import plot_file, presets
from src.plot_editor.overrides import (OverridesError, PlotOverrides,
                                       SeriesOverride,
                                       effective_document,
                                       overrides_from_document)
from src.plot_editor.plot_data import Series, build_series


def _items(yerr=True):
    return [Series((0., 1., 2.), (1., 2., 1.), 'S1', 'X', 'Y',
                   y_column=1,
                   yerr=(0.2, 0.3, 0.4) if yerr else None)]


class SeriesOverrideTests(unittest.TestCase):

    def test_round_trip(self):
        o = PlotOverrides()
        o.series[1] = SeriesOverride(error_style='band',
                                     error_alpha=0.5)
        d = o.to_dict()
        self.assertEqual(d['series']['1']['error_style'], 'band')
        o2 = PlotOverrides.from_dict(d)
        self.assertEqual(o2.series[1].error_style, 'band')
        self.assertEqual(o2.series[1].error_alpha, 0.5)

    def test_strictness(self):
        for field, value in (('error_style', 'fill'),
                             ('error_alpha', 0.0),
                             ('error_alpha', 1.5),
                             ('error_alpha', 'x')):
            o = PlotOverrides()
            o.series[1] = SeriesOverride(**{field: value})
            with self.assertRaises(OverridesError,
                                   msg=(field, value)):
                PlotOverrides.from_dict(o.to_dict())

    def test_is_empty(self):
        s = SeriesOverride()
        self.assertTrue(s.is_empty())
        s.error_style = 'band'
        self.assertFalse(s.is_empty())


class EffectiveDocumentTests(unittest.TestCase):

    def test_error_fields_applied_per_y_column(self):
        ov = PlotOverrides()
        ov.series[1] = SeriesOverride(error_style='band',
                                      error_alpha=0.6)
        doc = effective_document(None, _items(), 'pure_line', '', ov)
        self.assertEqual(doc.series[0].error_style, 'band')
        self.assertEqual(doc.series[0].error_alpha, 0.6)

    def test_no_override_keeps_bars(self):
        doc = effective_document(None, _items(), 'pure_line', '',
                                 PlotOverrides())
        self.assertEqual(doc.series[0].error_style, 'bars')

    def test_save_load_keeps_error_band(self):
        ov = PlotOverrides()
        ov.series[1] = SeriesOverride(error_style='band')
        doc = effective_document(None, _items(), 'pure_line', '', ov)
        ws = plot_file.worksheet_from_document(doc)
        cols = tuple(range(ws.column_count))
        payload = plot_file.worksheet_to_dict(ws, 'pure_line', cols, ov,
                                              for_save=True)
        self.assertIn('error_band', payload['requires'])
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'err.ilmplot.svg')
            plot_file.save_plot_file(path, doc, ws, 'pure_line', cols,
                                     ov)
            pf = plot_file.load_plot_file(path)
            self.assertTrue(pf.has_worksheet)
            self.assertEqual(pf.overrides.series[1].error_style,
                             'band')


class PresetTests(unittest.TestCase):

    def test_capture_excludes_error_fields(self):
        ov = PlotOverrides()
        ov.series[1] = SeriesOverride(color='#ff0000',
                                      error_style='band',
                                      error_alpha=0.5)
        preset = presets.capture(ov, 'line')
        preset.name = 'probe'
        text = repr(preset.to_dict())
        self.assertNotIn('error_style', text)
        self.assertNotIn('error_alpha', text)

    def test_apply_keeps_error_fields(self):
        ov = PlotOverrides()
        ov.series[1] = SeriesOverride(error_style='band',
                                      error_alpha=0.5)
        preset = presets.builtin_preset('line')
        presets.apply(preset, ov, _items(), 'pure_line')
        self.assertEqual(ov.series[1].error_style, 'band')
        self.assertEqual(ov.series[1].error_alpha, 0.5)


class LegacyLookSeedingTests(unittest.TestCase):

    def _bridge_fig(self, **line_kw):
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots()
        ax.plot([0, 1, 2], [1, 2, 1], label='S1', **line_kw)
        return fig, plt

    def test_legacy_file_keeps_series_look(self):
        fig, plt = self._bridge_fig(color='red', linestyle='--')
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'legacy.ilmplot.svg')
            self.assertTrue(ilmplot.savefig(fig, path).native)
            plt.close(fig)
            pf = plot_file.load_plot_file(path)
            self.assertFalse(pf.has_worksheet)
            items = build_series(pf.worksheet, pf.plot_columns)
            ov = overrides_from_document(
                pf.document, items, pf.chart_key or 'pure_line')
            self.assertIn(1, ov.series)
            self.assertEqual(ov.series[1].color, '#ff0000')
            self.assertEqual(ov.series[1].linestyle, '--')
            doc = effective_document(pf.document, items,
                                     'pure_line', pf.document.title, ov)
            out = os.path.join(d, 'saved.ilmplot.svg')
            plot_file.save_plot_file(out, doc, pf.worksheet,
                                     pf.chart_key or 'pure_line',
                                     pf.plot_columns, ov)
            pf2 = plot_file.load_plot_file(out)
            items2 = build_series(pf2.worksheet, pf2.plot_columns)
            doc2 = effective_document(None, items2, 'pure_line',
                                      pf2.document.title,
                                      pf2.overrides)
            s = doc2.series[0]
            self.assertEqual(s.color, '#ff0000')
            self.assertEqual(s.linestyle, '--')

    def test_default_styled_file_seeds_nothing(self):
        from ilmplot.render import save_document
        from src.plot_editor.export import document_from_plot
        items = _items()
        doc = document_from_plot(items, 'pure_line')
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'plain.ilmplot.svg')
            save_document(doc, path)   # document node only → legacy path
            pf = plot_file.load_plot_file(path)
            self.assertFalse(pf.has_worksheet)
            items = build_series(pf.worksheet, pf.plot_columns)
            ov = overrides_from_document(
                pf.document, items, pf.chart_key or 'pure_line')
            self.assertFalse(any(not s.is_empty()
                                 for s in ov.series.values()))


if __name__ == '__main__':
    unittest.main()
