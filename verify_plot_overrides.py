"""Non-UI checks for the Plot Editor override model (no Qt)."""

import os
import tempfile
import unittest

from src.plot_editor import render
from src.plot_editor.document import (AxisStyle, PlotDocument,
                                      PlotDocumentError, PlotStyle,
                                      TextStyle)
from src.plot_editor.export import (EXPORT_FORMATS, document_from_plot,
                                    export_plot)
from src.plot_editor.overrides import (OverridesError, PlotOverrides,
                                       SeriesOverride,
                                       effective_document,
                                       overrides_from_document,
                                       remap_series_keys)
from src.plot_editor.plot_data import Series
from src.plot_editor.plot_file import (load_plot_file, save_plot_file,
                                       worksheet_to_dict,
                                       worksheet_from_dict)
from src.plot_editor.worksheet import Column, Worksheet


def ser(n=1):
    return [Series((0., 1.), (0., 1.), 'L%d' % i, 'X', 'Y', None, i)
            for i in range(n)]


class OverridesSchemaTests(unittest.TestCase):

    def test_empty_omitted(self):
        o = PlotOverrides()
        self.assertTrue(o.is_empty())
        self.assertEqual(o.to_dict(), {})

    def test_roundtrip(self):
        o = PlotOverrides()
        o.xlabel = 'Time'
        o.ylabel = 'V'
        o.legend = False
        o.legend_location = 'upper left'
        o.grid = True
        o.xlim = [0, 5]
        o.ylim = [-1, 2]
        o.style = PlotStyle()
        o.style.title = TextStyle(bold=True)
        o.series = {3: SeriesOverride(label='S', color='#ff0000',
                                      linewidth_pt=2.0, linestyle='--',
                                      marker='o', markersize_pt=5.0)}
        d = o.to_dict()
        self.assertEqual(d['series'], {'3': dict(
            label='S', color='#ff0000', linewidth_pt=2.0,
            linestyle='--', marker='o', markersize_pt=5.0)})
        out = PlotOverrides.from_dict(d)
        self.assertEqual(out.to_dict(), d)

    def test_strictness(self):
        cases = [
            7,
            {'bogus': 1},
            {'xlabel': 5},
            {'legend': 'yes'},
            {'legend_location': 'nowhere'},
            {'xlim': [1]},
            {'xlim': [0, 0]},
            {'xlim': [float('nan'), 1]},
            {'style': {'title': {'align': 'middle'}}},
            {'series': ['a']},
            {'series': {'x': {}}},
            {'series': {'-1': {}}},
            {'series': {'2': {'bogus': 1}}},
            {'series': {'2': {'color': 'zzzz'}}},
            {'series': {'2': {'linewidth_pt': 0}}},
            {'series': {'2': {'linestyle': '~~'}}},
            {'series': {'2': {'marker': '*'}}},
            {'series': {'2': {'markersize_pt': -1}}},
        ]
        for d in cases:
            with self.assertRaises(OverridesError, msg=repr(d)):
                PlotOverrides.from_dict(d)


class EffectiveDocumentTests(unittest.TestCase):

    def test_xlabel_override_wins_and_none_falls_back(self):
        o = PlotOverrides()
        o.xlabel = 'Forced'
        doc = effective_document(None, ser(), 'pure_line', 'T', o)
        self.assertEqual(doc.xlabel, 'Forced')
        self.assertEqual(doc.ylabel, 'Y')
        self.assertEqual(doc.title, 'T')
        self.assertIsNone(overrides_xlim(o))

    def test_series_override_by_y_column(self):
        o = PlotOverrides()
        o.series[0] = SeriesOverride(color='#ff0000', label='Hot')
        s = ser(2)
        doc = effective_document(None, s, 'pure_line', '', o)
        self.assertEqual(doc.series[0].label, 'Hot')
        self.assertEqual(doc.series[0].color, '#ff0000')
        self.assertEqual(doc.series[1].label, 'L1')

    def test_remap_insert_and_remove(self):
        o = PlotOverrides()
        o.series = {0: SeriesOverride(label='a'),
                    3: SeriesOverride(label='b'),
                    5: SeriesOverride(label='c')}
        remap_series_keys(o, ('columns_inserted', 2, 2, True))
        self.assertEqual(sorted(o.series), [0, 5, 7])
        remap_series_keys(o, ('columns_removed', 0, 1))
        self.assertEqual(sorted(o.series), [4, 6])
        remap_series_keys(o, ('columns_removed', 4, 2))
        self.assertEqual(sorted(o.series), [4])
        self.assertEqual(o.series[4].label, 'c')
        # Non-column events are no-ops.
        remap_series_keys(o, ('cells', 0, 0, 1, 1))
        remap_series_keys(o, ('header', 0, 1))
        self.assertEqual(sorted(o.series), [4])

    def test_style_copy_no_alias(self):
        o = PlotOverrides()
        o.style = PlotStyle()
        o.style.title = TextStyle(bold=True)
        doc = effective_document(None, ser(), 'pure_line', '', o)
        self.assertTrue(doc.style.title.bold)
        doc.style.title.bold = False
        self.assertTrue(o.style.title.bold)

    def test_legacy_base_keeps_colors(self):
        base = PlotDocument()
        base.series[0].color = '#123456'
        base.series[0].label = 'DocLabel'
        o = PlotOverrides()
        doc = effective_document(base, ser(), 'pure_line', '', o)
        self.assertEqual(doc.series[0].color, '#123456')
        self.assertEqual(doc.series[0].label, 'L0')  # sheet label wins
        regen = effective_document(None, ser(), 'pure_line', '',
                                   PlotOverrides())
        self.assertNotEqual(regen.series[0].color, '#123456')

    def test_legacy_base_takes_sheet_data(self):
        base = PlotDocument()
        base.series[0].color = '#123456'
        s = [Series((5., 6., 7.), (1., 2., 3.), 'L', 'X', 'Y',
                    ('a', 'b', 'c'), 0)]
        doc = effective_document(base, s, 'pure_line', '', PlotOverrides())
        self.assertEqual(doc.series[0].x, [5., 6., 7.])
        self.assertEqual(doc.series[0].y, [1., 2., 3.])
        self.assertEqual(doc.series[0].color, '#123456')
        self.assertEqual(doc.x_tick_labels,
                         [[5., 'a'], [6., 'b'], [7., 'c']])

    def test_series_count_mismatch_falls_back(self):
        base = PlotDocument()
        base.series[0].color = '#123456'
        doc = effective_document(base, ser(2), 'pure_line', '',
                                 PlotOverrides())
        self.assertEqual(len(doc.series), 2)
        self.assertNotEqual(doc.series[0].color, '#123456')

    def test_overrides_applied(self):
        o = PlotOverrides()
        o.legend = True
        o.legend_location = 'lower right'
        o.grid = True
        o.xlim = [0, 9]
        o.ylim = [-2, 9]
        o.xlabel = 'XL!'
        doc = effective_document(None, ser(), 'pure_line', 'MyT', o)
        self.assertTrue(doc.legend)
        self.assertEqual(doc.legend_location, 'lower right')
        self.assertTrue(doc.grid)
        self.assertEqual(doc.xlim, [0, 9])
        self.assertEqual(doc.ylim, [-2, 9])
        self.assertEqual(doc.title, 'MyT')


def overrides_xlim(o):
    return o.xlim


class NodeTests(unittest.TestCase):

    def test_plain_file_stays_v1(self):
        d = worksheet_to_dict(Worksheet(), 'pure_line', (0, 1))
        self.assertEqual(d['schema_version'], 1)
        self.assertNotIn('overrides', d)

    def test_overrides_write_v2(self):
        o = PlotOverrides()
        o.xlabel = 'X!'
        d = worksheet_to_dict(Worksheet(), 'pure_line', (0, 1), o)
        self.assertEqual(d['schema_version'], 2)
        self.assertEqual(d['overrides'], {'xlabel': 'X!'})

    def test_v1_read_and_v3_rejected(self):
        base = worksheet_to_dict(Worksheet(), 'pure_line', (0, 1))
        _ws, chart, cols, o = worksheet_from_dict(dict(base))
        self.assertIsNone(o)
        with self.assertRaises(Exception):
            worksheet_from_dict(dict(base, schema_version=3))
        # v1 file carrying 'overrides' is rejected as unknown.
        with self.assertRaises(Exception):
            worksheet_from_dict(dict(base, overrides={}))

    def test_save_load_roundtrip_with_overrides(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'p.ilmplot.svg')
            ws = Worksheet()
            ws.column(0).values = [1.0]
            ws.column(1).values = [2.0]
            o = PlotOverrides()
            o.ylabel = 'Volt'
            o.series[1] = SeriesOverride(color='#00ff00')
            series = [Series((1.,), (2.,), 'L', 'X', 'Y', None, 1)]
            doc = effective_document(None, series, 'pure_line', '', o)
            save_plot_file(path, doc, ws, 'pure_line', (0, 1), o)
            pf = load_plot_file(path)
            self.assertIsNotNone(pf.overrides)
            self.assertEqual(pf.overrides.ylabel, 'Volt')
            self.assertEqual(pf.overrides.series[1].color, '#00ff00')
            self.assertEqual(pf.document.series[0].color, '#00ff00')
            self.assertEqual(pf.document.ylabel, 'Volt')

    def test_save_without_overrides_loads_none(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'p.ilmplot.svg')
            doc = document_from_plot(ser(), 'pure_line')
            save_plot_file(path, doc, Worksheet(), 'pure_line', (0, 1))
            pf = load_plot_file(path)
            self.assertIsNone(pf.overrides)


class ExportTests(unittest.TestCase):

    def test_export_all_formats_native(self):
        doc = document_from_plot(ser(), 'pure_line', title='Exp T')
        with tempfile.TemporaryDirectory() as d:
            for key, magic in (('ilmplot', b'<svg'), ('pdf', b'%PDF'),
                               ('svg', b'<?xml'), ('png', b'\x89PNG'),
                               ('tiff', b'II'), ('jpg', b'\xff\xd8')):
                path = os.path.join(d, 'o' + EXPORT_FORMATS[key][1])
                export_plot(doc, path, key)
                with open(path, 'rb') as fh:
                    self.assertTrue(fh.read(8).startswith(magic), key)
            svg = open(os.path.join(d, 'o.svg'), 'rb').read()
            self.assertIn(b'Exp T', svg)


if __name__ == '__main__':
    unittest.main()
