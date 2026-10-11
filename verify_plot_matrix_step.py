"""Heatmap (matrix) and step-line creation in the Plot Editor, no Qt.

Covers the Qt-free pieces the creation UI relies on: sheet → matrix and
series items, document/chart-key mapping, overrides (parse, reset,
effective document) and the save → load → re-plot cycle.
"""
import os
import tempfile
import unittest
from unittest import mock

import src  # noqa: F401  -- puts packages/ilmplot/src on sys.path

from ilmplot.document import (HEATMAP_CMAPS, PlotDocument,
                              required_capabilities)
from ilmplot.render import render_document, render_document_fitted

from src.plot_editor import actions, export, plot_file
from src.plot_editor.i18n import _STRINGS
from src.plot_editor.overrides import (HeatmapOverride, OverridesError,
                                       PlotOverrides, SeriesOverride,
                                       effective_document,
                                       overrides_from_document,
                                       reset_element)
from src.plot_editor.plot_data import (PlotSelectionError, Series,
                                       build_matrix, build_series)
from src.plot_editor.worksheet import Column, Worksheet


def _matrix_sheet():
    return Worksheet.from_columns([
        Column('Label', long_name='Sample', values=['a', 'b', 'c']),
        Column('Y', comments='T1', values=[1.0, 2.0, 3.0]),
        Column('Y', comments='T2', values=[4.0, 'x', 6.0]),
    ])


def _step_sheet(y=(1.0, 3.0, 2.0)):
    return Worksheet.from_columns([
        Column('X', long_name='t', values=[0.0, 1.0, 2.0]),
        Column('Y', comments='s', values=list(y)),
    ])


def _step_series(ws=None):
    return build_series(ws or _step_sheet(), (0, 1))


class MatrixDataTests(unittest.TestCase):

    def test_rows_labels_and_blank_cells(self):
        m = build_matrix(_matrix_sheet(), (0, 1, 2))
        self.assertEqual(m.rows, ((1.0, 4.0), (2.0, None), (3.0, 6.0)))
        self.assertEqual(m.row_labels, ('a', 'b', 'c'))
        self.assertEqual(m.col_labels, ('T1', 'T2'))
        self.assertEqual(m.y_label, 'Sample')
        self.assertEqual(m.x_label, '')
        self.assertEqual(m.y_columns, (1, 2))

    def test_numbered_rows_without_label_column(self):
        ws = Worksheet.from_columns([
            Column('Y', comments='T1', values=[1.0, 2.0])])
        m = build_matrix(ws, (0,))
        self.assertEqual(m.row_labels, ('1', '2'))
        self.assertEqual(m.y_label, '')

    def test_rows_without_numbers_are_skipped(self):
        ws = Worksheet.from_columns([
            Column('Label', values=['a', 'b']),
            Column('Y', comments='T1', values=['x', 'y'])])
        with self.assertRaises(PlotSelectionError):
            build_matrix(ws, (0, 1))

    def test_row_and_column_limits(self):
        tall = Worksheet.from_columns([
            Column('Y', comments='T1', values=[float(i) for i in range(501)])])
        with self.assertRaisesRegex(PlotSelectionError, '500'):
            build_matrix(tall, (0,))
        wide = Worksheet.from_columns([
            Column('Y', comments=str(i), values=[1.0] * 400)
            for i in range(300)])
        with self.assertRaisesRegex(PlotSelectionError, '100000|cells'):
            build_matrix(wide, tuple(range(300)))


class ExportTests(unittest.TestCase):

    def test_heatmap_document_validates_and_renders(self):
        items = [build_matrix(_matrix_sheet(), (0, 1, 2))]
        doc = export.document_from_plot(items, 'heatmap', title='T')
        self.assertEqual(doc.kind, 'heatmap')
        self.assertEqual(doc.heatmap.x_cell_labels, ['T1', 'T2'])
        self.assertEqual(doc.heatmap.y_cell_labels, ['a', 'b', 'c'])
        self.assertEqual(required_capabilities(doc), ['heatmap'])
        self.assertIn(b'ilmplot-heatmap-image',
                      render_document(doc).svg)
        render_document_fitted(doc, 90.0, 65.0)

    def test_step_document_uses_post_steps(self):
        doc = export.document_from_plot(_step_series(), 'step_line')
        self.assertEqual(doc.series[0].drawstyle, 'steps-post')
        self.assertEqual(required_capabilities(doc), ['step_lines'])
        render_document(doc)
        render_document_fitted(doc, 90.0, 65.0)

    def test_chart_keys_are_registered(self):
        groups = {g.key: [c.key for c in g.charts] for g in actions.CHART_GROUPS}
        self.assertIn('step_line', groups['line'])
        self.assertEqual(groups['matrix'], ['heatmap'])
        self.assertEqual(export.CHART_KIND['step_line'], ('line', None))
        self.assertEqual(export.CHART_KIND['heatmap'], ('heatmap', None))


class ChartKeyTests(unittest.TestCase):

    def test_chart_from_document(self):
        step = export.document_from_plot(_step_series(), 'step_line')
        self.assertEqual(plot_file.chart_from_document(step), 'step_line')
        pure = export.document_from_plot(_step_series(), 'pure_line')
        self.assertEqual(plot_file.chart_from_document(pure), 'pure_line')
        heat = export.document_from_plot(
            [build_matrix(_matrix_sheet(), (0, 1, 2))], 'heatmap')
        self.assertIsNone(plot_file.chart_from_document(heat))
        marked = export.document_from_plot(_step_series(), 'line_scatters')
        marked.series[0].drawstyle = 'steps-pre'
        self.assertEqual(plot_file.chart_from_document(marked),
                         'line_scatters')


class OverrideTests(unittest.TestCase):

    def test_series_drawstyle_parse_and_strictness(self):
        so = SeriesOverride.from_dict({'drawstyle': 'steps-pre'}, 'ctx')
        self.assertEqual(so.drawstyle, 'steps-pre')
        self.assertEqual(so.to_dict(), {'drawstyle': 'steps-pre'})
        with self.assertRaises(OverridesError):
            SeriesOverride.from_dict({'drawstyle': 'steps'}, 'ctx')

    def test_reset_clears_series_drawstyle(self):
        ov = PlotOverrides()
        ov.series[1] = SeriesOverride(drawstyle='steps-mid')
        reset_element(ov, 'series:s0', 1)
        self.assertNotIn(1, ov.series)

    def test_heatmap_override_parse_and_strictness(self):
        data = {'cmap': 'magma_r', 'vmin': 0.5, 'vmax': 2.0,
                'aspect': 'equal', 'colorbar': False,
                'colorbar_label': 'v', 'mask_color': '#000000'}
        self.assertEqual(HeatmapOverride.from_dict(data).to_dict(), data)
        bad = [{'cmap': 'cubehelix'}, {'vmin': 2.0, 'vmax': 1.0},
               {'colorbar': 'yes'}, {'aspect': 'big'}, {'zz': 1}]
        for data in bad:
            with self.subTest(data=data):
                with self.assertRaises(OverridesError):
                    HeatmapOverride.from_dict(data)

    def test_overrides_round_trip_and_reset(self):
        ov = PlotOverrides()
        ov.heatmap = HeatmapOverride()
        ov.heatmap.cmap = 'plasma'
        d = ov.to_dict()
        self.assertEqual(d['heatmap'], {'cmap': 'plasma'})
        self.assertEqual(PlotOverrides.from_dict(d).to_dict(), d)
        reset_element(ov, 'heatmap')
        self.assertIsNone(ov.heatmap)
        self.assertTrue(ov.is_empty())

    def test_heatmap_override_applies_to_created_document(self):
        items = [build_matrix(_matrix_sheet(), (0, 1, 2))]
        ov = PlotOverrides()
        ov.heatmap = HeatmapOverride()
        ov.heatmap.cmap = 'magma_r'
        ov.heatmap.vmin = 0.5
        eff = effective_document(None, items, 'heatmap', 'T', ov)
        self.assertEqual(eff.heatmap.cmap, 'magma_r')
        self.assertEqual(eff.heatmap.vmin, 0.5)
        self.assertEqual(eff.heatmap.values, [list(r) for r in
                                              items[0].rows])

    def test_step_band_guard_keeps_document_valid(self):
        items = [Series(x=(0.0, 1.0), y=(1.0, 2.0), label='s',
                        x_label='t', y_label='y', y_column=1,
                        yerr=(0.1, 0.1))]
        ov = PlotOverrides()
        ov.series[1] = SeriesOverride(error_style='band',
                                      drawstyle='steps-pre')
        eff = effective_document(None, items, 'step_line', 'P', ov)
        self.assertEqual(eff.series[0].error_style, 'band')
        self.assertEqual(eff.series[0].drawstyle, 'default')

    def test_step_override_applies_when_not_banded(self):
        items = [Series(x=(0.0, 1.0), y=(1.0, 2.0), label='s',
                        x_label='t', y_label='y', y_column=1)]
        ov = PlotOverrides()
        ov.series[1] = SeriesOverride(drawstyle='steps-mid')
        eff = effective_document(None, items, 'pure_line', 'P', ov)
        self.assertEqual(eff.series[0].drawstyle, 'steps-mid')

    def test_legacy_seed_keeps_step_look(self):
        items = [Series(x=(0.0, 1.0), y=(1.0, 2.0), label='s',
                        x_label='t', y_label='y', y_column=1)]
        doc = export.document_from_plot(items, 'pure_line')
        doc.series[0].drawstyle = 'steps-post'
        ov = overrides_from_document(doc, items, 'pure_line')
        self.assertEqual(ov.series[1].drawstyle, 'steps-post')


class WorksheetRoundTripTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def _save_load(self, name, eff, ws, chart, cols, ov):
        path = os.path.join(self.dir, name)
        plot_file.save_plot_file(path, eff, ws, chart, cols, ov)
        return plot_file.load_plot_file(path)

    def test_created_heatmap_round_trip_and_data_edit(self):
        ws = _matrix_sheet()
        cols = (0, 1, 2)
        items = [build_matrix(ws, cols)]
        ov = PlotOverrides()
        ov.heatmap = HeatmapOverride()
        ov.heatmap.cmap = 'magma'
        ov.heatmap.vmin = 0.5
        eff = effective_document(None, items, 'heatmap', 'Plot', ov)
        pf = self._save_load('h.ilmplot.svg', eff, ws, 'heatmap', cols, ov)
        self.assertTrue(pf.has_worksheet)
        self.assertEqual(pf.chart_key, 'heatmap')
        self.assertEqual(tuple(pf.plot_columns), cols)
        again = effective_document(
            None, [build_matrix(pf.worksheet, pf.plot_columns)],
            pf.chart_key, pf.document.title, pf.overrides)
        self.assertEqual(again.to_dict(), eff.to_dict())
        edited = Worksheet.from_columns([
            Column('Label', long_name='Sample', values=['a', 'b', 'c']),
            Column('Y', comments='T1', values=[9.0, 2.0, 3.0]),
            Column('Y', comments='T2', values=[4.0, 'x', 6.0])])
        replot = effective_document(
            None, [build_matrix(edited, cols)], 'heatmap', 'Plot',
            pf.overrides)
        self.assertEqual(replot.heatmap.values[0][0], 9.0)
        self.assertEqual(replot.heatmap.cmap, 'magma')

    def test_created_step_round_trip(self):
        ws = _step_sheet()
        cols = (0, 1)
        series = _step_series(ws)
        ov = PlotOverrides()
        ov.series[series[0].y_column] = SeriesOverride(drawstyle='steps-mid')
        eff = effective_document(None, series, 'step_line', 'P', ov)
        pf = self._save_load('s.ilmplot.svg', eff, ws, 'step_line', cols,
                             ov)
        self.assertEqual(pf.chart_key, 'step_line')
        self.assertEqual(pf.document.series[0].drawstyle, 'steps-mid')
        payload = plot_file.worksheet_to_dict(ws, 'step_line', cols, ov)
        self.assertIn('step_lines', payload['requires'])
        again = effective_document(
            None, build_series(pf.worksheet, pf.plot_columns),
            pf.chart_key, pf.document.title, pf.overrides)
        self.assertEqual(again.to_dict(), eff.to_dict())

    def test_heatmap_requires_stamped(self):
        ws = _matrix_sheet()
        payload = plot_file.worksheet_to_dict(ws, 'heatmap', (0, 1, 2))
        self.assertIn('heatmap', payload['requires'])

    def test_old_reader_rebuilds_read_only(self):
        ws = _step_sheet()
        cols = (0, 1)
        series = _step_series(ws)
        ov = PlotOverrides()
        ov.series[series[0].y_column] = SeriesOverride(drawstyle='steps-pre')
        eff = effective_document(None, series, 'step_line', 'P', ov)
        path = os.path.join(self.dir, 'old.ilmplot.svg')
        plot_file.save_plot_file(path, eff, ws, 'step_line', cols, ov)
        old = plot_file.WORKSHEET_CAPABILITIES - {'step_lines'}
        with mock.patch.object(plot_file, 'WORKSHEET_CAPABILITIES', old):
            pf = plot_file.load_plot_file(path)
        self.assertFalse(pf.has_worksheet)
        self.assertTrue(pf.read_only_source)
        self.assertTrue(pf.warnings)
        self.assertIn('step_lines', pf.warnings[0])


class HitTests(unittest.TestCase):

    def test_heatmap_regions_pick_image_and_colorbar(self):
        from ilmplot.render import element_regions
        from src.plot_editor import hit_test
        doc = export.document_from_plot(
            [build_matrix(_matrix_sheet(), (0, 1, 2))], 'heatmap')
        regions = element_regions(doc)
        self.assertEqual(set(regions['heatmaps']), {'image', 'colorbar'})
        x0, y0, x1, y1 = regions['heatmaps']['image']['bbox']
        self.assertEqual(hit_test.pick(regions, (x0 + x1) / 2,
                                       (y0 + y1) / 2), 'heatmap')
        cx0, cy0, cx1, cy1 = regions['heatmaps']['colorbar']['bbox']
        self.assertEqual(hit_test.pick(regions, (cx0 + cx1) / 2,
                                       (cy0 + cy1) / 2), 'heatmap')
        box = hit_test.heatmap_bbox(regions)
        self.assertLessEqual(box[0], x0)
        self.assertGreaterEqual(box[2], cx1)
        self.assertIsNone(hit_test.heatmap_bbox({}))


class StringTests(unittest.TestCase):

    NEW_KEYS = ('grp_matrix', 'chart_step_line', 'chart_heatmap',
                'panel_heatmap', 'row_colormap', 'row_reverse',
                'row_value_min', 'row_value_max', 'row_auto_range',
                'row_aspect', 'aspect_fill', 'aspect_equal',
                'row_colorbar', 'row_colorbar_label', 'row_blank_colour',
                'row_step_style', 'step_off', 'step_pre', 'step_mid',
                'step_post', 'tip_step_band', 'err_matrix_size',
                'err_matrix_cells')

    def test_new_keys_are_bilingual(self):
        for key in self.NEW_KEYS:
            with self.subTest(key=key):
                entry = _STRINGS[key]
                self.assertTrue(entry.get('en'), key)
                self.assertTrue(entry.get('zh'), key)

    def test_placeholders_match_between_languages(self):
        for key in ('err_matrix_size', 'err_matrix_cells'):
            en = set(part.split('}')[0] for part in
                     _STRINGS[key]['en'].split('{')[1:])
            zh = set(part.split('}')[0] for part in
                     _STRINGS[key]['zh'].split('{')[1:])
            self.assertEqual(en, zh, key)

    def test_colormap_whitelist_matches_document(self):
        self.assertIn('viridis', HEATMAP_CMAPS)


if __name__ == '__main__':
    unittest.main()
