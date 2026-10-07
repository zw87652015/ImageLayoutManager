"""Non-UI verification for the box/column+points/histogram/bar charts.

Run from the repo root: ``python -m unittest verify_plot_chart_types``.
"""

import unittest

import src  # noqa: F401  -- puts packages/ilmplot/src on sys.path

from ilmplot.document import HistOptions, PlotDocument, ViolinOptions

from src.plot_editor import hit_test, plot_file, presets
from src.plot_editor.actions import CHART_GROUPS
from src.plot_editor.export import (CHART_KIND, GROUPED_CHARTS,
                                    HORIZONTAL_CHARTS, VIOLIN_BODY,
                                    document_from_plot)
from src.plot_editor.i18n import _STRINGS
from src.plot_editor.overrides import (PlotOverrides,
                                       effective_document,
                                       reset_element)
from src.plot_editor.plot_data import Category, Group
from src.plot_editor.worksheet import Column, Worksheet


def _groups():
    return [Group((1., 2., 3., 4., 5., 9.), 'A', 'Dose', 'Resp',
                  y_column=1),
            Group((2., 3., 3., 4., 6.), 'B', 'Dose', 'Resp',
                  y_column=2)]


def _cats():
    return [Category((1., 2., 3.), 'S1', 'Group', 'Resp',
                     ('a', 'b', 'c'), y_column=1),
            Category((2., 1., 2.), 'S2', 'Group', 'Resp',
                     ('a', 'b', 'c'), y_column=2)]


class ChartTableTests(unittest.TestCase):

    def test_every_chart_has_kind_and_text(self):
        for group in CHART_GROUPS:
            for chart in group.charts:
                self.assertIn(chart.key, CHART_KIND)
                for key in ('chart_' + chart.key, 'grp_' + group.key):
                    entry = _STRINGS[key]
                    self.assertTrue(entry['en'] and entry['zh'])


class PanelKeyTests(unittest.TestCase):

    def test_new_i18n_keys(self):
        for key in ('panel_box', 'panel_column_points',
                    'sec_box', 'sec_column_points'):
            entry = _STRINGS[key]
            self.assertTrue(entry['en'] and entry['zh'], key)
        self.assertIn('{name}', _STRINGS['panel_box']['en'])
        self.assertIn('{name}', _STRINGS['panel_column_points']['en'])
        self.assertIn('{name}', _STRINGS['panel_violin']['en'])

    def test_violin_panel_keys(self):
        from src.plot_editor.element_panel import violin_panel_keys
        self.assertEqual(violin_panel_keys('violin'),
                         ('panel_violin', 'sec_violin'))
        self.assertEqual(violin_panel_keys(None),
                         ('panel_violin', 'sec_violin'))
        self.assertEqual(violin_panel_keys('none'),
                         ('panel_box', 'sec_box'))
        self.assertEqual(violin_panel_keys('bar'),
                         ('panel_column_points', 'sec_column_points'))


class DocumentFromPlotTests(unittest.TestCase):

    def test_box(self):
        doc = document_from_plot(_groups(), 'box')
        self.assertEqual(doc.kind, 'violin')
        self.assertEqual(doc.violin.body, 'none')
        self.assertFalse(doc.violin.show_points)
        self.assertTrue(doc.violin.show_box)
        self.assertIn('box_plot', doc.to_dict()['requires'])

    def test_column_points(self):
        doc = document_from_plot(_groups(), 'column_points')
        self.assertEqual(doc.violin.body, 'bar')
        self.assertFalse(doc.violin.show_box)
        self.assertTrue(doc.violin.show_points)
        self.assertIn('column_points', doc.to_dict()['requires'])

    def test_plain_violin_unchanged(self):
        doc = document_from_plot(_groups(), 'violin')
        self.assertIsNone(doc.violin)
        self.assertNotIn('violin', doc.to_dict())

    def test_histogram(self):
        doc = document_from_plot(_groups(), 'histogram')
        self.assertEqual(doc.kind, 'histogram')
        self.assertEqual(doc.series, [])
        self.assertEqual(len(doc.groups), 2)
        self.assertEqual(doc.xlabel, 'Resp')
        self.assertEqual(doc.ylabel, 'Count')
        self.assertTrue(doc.legend)
        self.assertIsNone(doc.histogram)

    def test_horizontal_charts(self):
        for key, pct, grouped in (('bar', False, True),
                                  ('stacked_bar_pct', True, False),
                                  ('stacked_bar', False, False)):
            doc = document_from_plot(_cats(), key)
            self.assertEqual(doc.kind, 'stacked_column')
            self.assertEqual(doc.stacked.percent, pct)
            self.assertEqual(doc.stacked.grouped, grouped)
            self.assertTrue(doc.stacked.horizontal)
            # Axis titles swap: the value title goes on x.
            self.assertEqual(doc.ylabel, 'Group')
            self.assertEqual(doc.xlabel,
                             'Percentage (%)' if pct else 'Resp')
            self.assertIn('horizontal_bars', doc.to_dict()['requires'])

    def test_vertical_column_unchanged(self):
        doc = document_from_plot(_cats(), 'column')
        self.assertTrue(doc.stacked.grouped)
        self.assertFalse(doc.stacked.horizontal)
        self.assertNotIn('requires', doc.to_dict())


class EffectiveDocumentTests(unittest.TestCase):

    def test_body_forced_from_chart_key(self):
        # Overrides may carry a different body; the chart key wins.
        o = PlotOverrides()
        o.violin = ViolinOptions(body='violin', fill_alpha=0.7)
        doc = effective_document(None, _groups(), 'box', '', o)
        self.assertEqual(doc.violin.body, 'none')
        self.assertEqual(doc.violin.fill_alpha, 0.7)
        o.violin = ViolinOptions(body='none')
        doc = effective_document(None, _groups(), 'violin', '', o)
        self.assertEqual(doc.violin.body, 'violin')

    def test_plain_violin_no_overrides_stays_none(self):
        doc = effective_document(None, _groups(), 'violin', '',
                                 PlotOverrides())
        self.assertIsNone(doc.violin)

    def test_horizontal_forced(self):
        o = PlotOverrides()
        from ilmplot.document import StackOptions
        o.stacked = StackOptions(percent=False, horizontal=False)
        doc = effective_document(None, _cats(), 'bar', '', o)
        self.assertTrue(doc.stacked.horizontal)
        self.assertTrue(doc.stacked.grouped)
        o2 = PlotOverrides()
        o2.stacked = StackOptions(percent=False, horizontal=True)
        doc = effective_document(None, _cats(), 'column', '', o2)
        self.assertFalse(doc.stacked.horizontal)
        self.assertTrue(doc.stacked.grouped)

    def test_histogram_overrides_and_density_title(self):
        o = PlotOverrides()
        o.histogram = HistOptions(bins=9, density=True)
        doc = effective_document(None, _groups(), 'histogram', '', o)
        self.assertEqual(doc.histogram.bins, 9)
        self.assertEqual(doc.ylabel, 'Density')
        self.assertEqual(doc.xlabel, 'Resp')

    def test_ylabel_override_wins(self):
        o = PlotOverrides()
        o.ylabel = 'Custom'
        doc = effective_document(None, _groups(), 'histogram', '', o)
        self.assertEqual(doc.ylabel, 'Custom')


class ChartRoundTripTests(unittest.TestCase):

    def test_chart_from_document_round_trip(self):
        for key, items in (('box', _groups()),
                           ('column_points', _groups()),
                           ('violin', _groups()),
                           ('histogram', _groups()),
                           ('bar', _cats()),
                           ('stacked_bar_pct', _cats()),
                           ('stacked_bar', _cats()),
                           ('column', _cats()),
                           ('stacked_column', _cats()),
                           ('stacked_column_pct', _cats())):
            doc = document_from_plot(items, key)
            self.assertEqual(plot_file.chart_from_document(doc), key,
                             msg=key)


class WorksheetTests(unittest.TestCase):

    def _ws(self):
        return Worksheet.from_columns(
            [Column('Label', 'Grp', '', '', ['a', 'b']),
             Column('Y', 'Resp', '', '', [1.0, 2.0]),
             Column('Y', 'Resp', '', '', [3.0, 4.0])])

    def test_requires_per_chart(self):
        cases = {'box': 'box_plot', 'column_points': 'column_points',
                 'histogram': 'histogram', 'bar': 'horizontal_bars',
                 'stacked_bar': 'horizontal_bars',
                 'stacked_bar_pct': 'horizontal_bars'}
        for key, cap in cases.items():
            d = plot_file.worksheet_to_dict(self._ws(), key, (0, 1, 2))
            self.assertIn(cap, d.get('requires', ()), msg=key)
            # No overrides → schema stays v1.
            self.assertEqual(d['schema_version'], 1)
        d = plot_file.worksheet_to_dict(self._ws(), 'pure_line', (0, 1))
        self.assertNotIn('requires', d)

    def test_violin_option_overrides_stamp(self):
        o = PlotOverrides()
        o.violin = ViolinOptions(body='none')
        d = plot_file.worksheet_to_dict(self._ws(), 'violin', (1, 2),
                                        overrides=o)
        self.assertIn('box_plot', d['requires'])
        o2 = PlotOverrides()
        o2.violin = ViolinOptions(body='bar')
        d = plot_file.worksheet_to_dict(self._ws(), 'violin', (1, 2),
                                        overrides=o2)
        self.assertIn('column_points', d['requires'])
        o3 = PlotOverrides()
        o3.histogram = HistOptions(bins=5)
        d = plot_file.worksheet_to_dict(self._ws(), 'violin', (1, 2),
                                        overrides=o3)
        self.assertIn('histogram', d['requires'])
        # Round-trips through the strict reader.
        ws, chart, cols, _o = plot_file.worksheet_from_dict(d)
        self.assertEqual(chart, 'violin')

    def test_sample_counts_stamp(self):
        for key in ('row_show_n', 'row_n_position', 'n_pos_tick',
                    'n_pos_top', 'n_pos_bottom', 'row_n_format',
                    'tip_n_format', 'row_n_size', 'row_n_colour',
                    'hint_n_tick_size'):
            entry = _STRINGS[key]
            self.assertTrue(entry['en'] and entry['zh'], key)
        o = PlotOverrides()
        o.violin = ViolinOptions(show_n=True)
        d = plot_file.worksheet_to_dict(self._ws(), 'violin', (1, 2),
                                        overrides=o)
        self.assertIn('sample_counts', d['requires'])
        o2 = PlotOverrides()
        o2.histogram = HistOptions(show_n=True)
        d = plot_file.worksheet_to_dict(self._ws(), 'violin', (1, 2),
                                        overrides=o2)
        self.assertIn('sample_counts', d['requires'])
        o3 = PlotOverrides()
        o3.violin = ViolinOptions(n_format='count {n}')
        d = plot_file.worksheet_to_dict(self._ws(), 'violin', (1, 2),
                                        overrides=o3)
        self.assertIn('sample_counts', d['requires'])
        o4 = PlotOverrides()
        o4.violin = ViolinOptions(n_size_pt=8)
        d = plot_file.worksheet_to_dict(self._ws(), 'violin', (1, 2),
                                        overrides=o4)
        self.assertIn('sample_counts', d['requires'])
        plain = plot_file.worksheet_to_dict(self._ws(), 'violin',
                                            (1, 2))
        self.assertNotIn('sample_counts', plain.get('requires', ()))

    def test_worksheet_from_histogram_document(self):
        doc = document_from_plot(_groups(), 'histogram')
        ws = plot_file.worksheet_from_document(doc)
        self.assertEqual(ws.column_count, 2)
        self.assertTrue(all(c.designation == 'Y'
                            for c in ws.columns))
        self.assertEqual(ws.column(0).long_name, 'Resp')
        items = plot_file.items_from_document(doc)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].y_label, 'Resp')
        self.assertEqual(items[0].x_label, '')


class OverridePresetTests(unittest.TestCase):

    def test_overrides_histogram_round_trip(self):
        o = PlotOverrides()
        o.histogram = HistOptions(bins=12, kde=True)
        back = PlotOverrides.from_dict(o.to_dict())
        self.assertEqual(back.histogram.bins, 12)
        self.assertTrue(back.histogram.kde)

    def test_preset_histogram_round_trip(self):
        p = presets.StylePreset(name='p1', plot_type='violin')
        p.histogram = HistOptions(style='step', density=True)
        back = presets.StylePreset.from_dict(p.to_dict())
        self.assertEqual(back.histogram.style, 'step')
        self.assertTrue(back.histogram.density)

    def test_preset_capture_apply(self):
        o = PlotOverrides()
        o.histogram = HistOptions(bins=30)
        p = presets.capture(o, 'violin')
        self.assertEqual(p.histogram.bins, 30)
        target = PlotOverrides()
        presets.apply(p, target, _groups(), 'histogram')
        self.assertEqual(target.histogram.bins, 30)
        std = presets.builtin_preset('violin')
        presets.apply(std, target, _groups(), 'histogram')
        self.assertIsNone(target.histogram)


class HitTestTests(unittest.TestCase):

    def test_hist_pick(self):
        regions = {'hists': {'g7': {'bbox': (0.1, 0.1, 0.5, 0.5)}},
                   'frame': (0.0, 0.0, 1.0, 1.0)}
        self.assertEqual(hit_test.pick(regions, 0.3, 0.3), 'hist:g7')
        self.assertIsNone(hit_test.pick(regions, 0.9, 0.9))

    def test_reset_element_hist(self):
        o = PlotOverrides()
        from src.plot_editor.overrides import SeriesOverride
        o.series[3] = SeriesOverride(color='#ff0000')
        reset_element(o, 'hist:x', y_column=3)
        self.assertNotIn(3, o.series)


if __name__ == '__main__':
    unittest.main()
