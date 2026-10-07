"""Non-UI verification for the general filled-area feature: document
spans, editor CurveFill definitions compiled to bands, hit-testing and
overrides/preset preservation.

Run from the repo root: ``python -m unittest verify_plot_fills``.
"""

import copy
import os
import tempfile
import unittest

import src  # noqa: F401  -- puts packages/ilmplot/src on sys.path

from ilmplot.document import (Band, LineSeries, PlotDocument, Span)

from src.plot_editor import hit_test, plot_file, presets
from src.plot_editor.fills import CurveFill, compute_band
from src.plot_editor.overrides import (OverridesError, PlotOverrides,
                                       effective_document,
                                       overrides_from_document,
                                       remap_series_keys, static_bands)
from src.plot_editor.plot_data import Series


def _items():
    return [Series((0., 1., 2., 3.), (0., 2., 0., 2.), 'A', 'X', 'Y',
                   y_column=1),
            Series((0., 1., 2., 3.), (1., 1., 1., 1.), 'B', 'X', 'Y',
                   y_column=2)]


class CurveFillTests(unittest.TestCase):

    def test_round_trip(self):
        o = PlotOverrides()
        o.fills = [CurveFill(id='fill-1', kind='between', a=1, b=2,
                             x_min=0.5, x_max=2.5, color='#00ff004d',
                             label='ci')]
        d = o.to_dict()
        back = PlotOverrides.from_dict(d)
        f = back.fills[0]
        self.assertEqual((f.kind, f.a, f.b, f.x_min, f.x_max,
                          f.color, f.label),
                         ('between', 1, 2, 0.5, 2.5, '#00ff004d', 'ci'))

    def test_strictness(self):
        base = CurveFill(id='f1', kind='between', a=1, b=2).to_dict()
        for mutate in (
                lambda d: d.update(kind='sideways'),
                lambda d: d.update(a='x'),
                lambda d: d.update(b=1),
                lambda d: d.update(x_min=2.0, x_max=1.0),
                lambda d: d.update(baseline='x'),
                lambda d: d.update(extra=1)):
            d = dict(base)
            mutate(d)
            with self.assertRaises(OverridesError, msg=d):
                PlotOverrides.from_dict({'fills': [d]})

    def test_compute_under(self):
        f = CurveFill(id='u1', kind='under', a=1, baseline=0.5,
                      x_min=0.5, x_max=2.5)
        b = compute_band(f, _items())
        self.assertIsNotNone(b)
        self.assertEqual(b.id, 'u1')
        # Interpolated ends inside the data range.
        self.assertEqual(b.x, [0.5, 1.0, 2.0, 2.5])
        self.assertEqual(b.y1, [0.5] * 4)
        # y = interp of (0,0),(1,2),(2,0),(3,2): 0.5→1.0, 2.5→1.0
        self.assertEqual(b.y2, [1.0, 2.0, 0.0, 1.0])

    def test_compute_between(self):
        f = CurveFill(id='bt1', kind='between', a=1, b=2,
                      x_min=0.0, x_max=4.0)
        b = compute_band(f, _items())
        self.assertIsNotNone(b)
        # B's range ends at 3 → domain clipped to the overlap.
        self.assertEqual(b.x, [0.0, 1.0, 2.0, 3.0])
        self.assertEqual(b.y2, [1.0] * 4)

    def test_compute_none_cases(self):
        items = _items()
        self.assertIsNone(compute_band(
            CurveFill(kind='under', a=99), items))
        self.assertIsNone(compute_band(
            CurveFill(kind='between', a=1, b=99), items))
        self.assertIsNone(compute_band(
            CurveFill(kind='under', a=1, x_min=10.0, x_max=12.0),
            items))
        # One point left in range → nothing.
        self.assertIsNone(compute_band(
            CurveFill(kind='under', a=1, x_min=1.0, x_max=1.0), items))


class EffectiveDocumentTests(unittest.TestCase):

    def test_spans_and_fill_bands(self):
        ov = PlotOverrides()
        ov.spans = [Span(id='sp1', axis='x', lo=0.0, hi=1.0)]
        ov.bands = [Band(id='b1', x=[0, 1], y1=[0, 0], y2=[1, 1])]
        ov.fills = [CurveFill(id='f1', kind='under', a=1)]
        doc = effective_document(None, _items(), 'pure_line', '', ov)
        self.assertEqual([s.id for s in doc.spans], ['sp1'])
        # Fill band is appended after the static ones.
        self.assertEqual([b.id for b in doc.bands], ['b1', 'f1'])
        self.assertEqual(doc.to_dict()['requires'],
                         ['bands', 'spans'])

    def test_fill_dropped_when_column_unplotted(self):
        ov = PlotOverrides()
        ov.fills = [CurveFill(id='f1', kind='under', a=7)]
        doc = effective_document(None, _items(), 'pure_line', '', ov)
        self.assertEqual(doc.bands, [])

    def test_spans_ignored_on_other_kinds(self):
        from src.plot_editor.plot_data import Group
        ov = PlotOverrides()
        ov.spans = [Span(id='sp1', axis='x', lo=0.0, hi=1.0)]
        doc = effective_document(
            None, [Group((1., 2.), 'g', 'X', 'Y', y_column=1),
                   Group((0., 4.), 'h', 'X', 'Y', y_column=2)],
            'violin', '', ov)
        self.assertEqual(doc.spans, [])

    def test_seeding_from_document(self):
        doc = effective_document(
            None, _items(), 'pure_line', '',
            PlotOverrides())
        doc.spans = [Span(id='sp1', axis='y', lo=0.0, hi=1.0)]
        ov = overrides_from_document(doc)
        self.assertEqual(ov.spans[0].id, 'sp1')


class RemapTests(unittest.TestCase):

    def test_insert_remaps_columns(self):
        ov = PlotOverrides()
        ov.fills = [CurveFill(id='f', kind='between', a=1, b=2)]
        remap_series_keys(ov, ('columns_inserted', 0, 1, True))
        self.assertEqual((ov.fills[0].a, ov.fills[0].b), (2, 3))

    def test_remove_drops_fill(self):
        ov = PlotOverrides()
        ov.fills = [CurveFill(id='f1', kind='between', a=1, b=2),
                    CurveFill(id='f2', kind='under', a=1)]
        remap_series_keys(ov, ('columns_removed', 2, 1))
        self.assertEqual([f.id for f in ov.fills], ['f2'])
        remap_series_keys(ov, ('columns_removed', 1, 1))
        self.assertIsNone(ov.fills)


class SaveLoadTests(unittest.TestCase):

    def test_round_trip(self):
        ov = PlotOverrides()
        ov.spans = [Span(id='sp1', axis='x', lo=0.0, hi=1.0)]
        ov.fills = [CurveFill(id='f1', kind='under', a=1)]
        items = _items()
        doc = effective_document(None, items, 'pure_line', 'T', ov)
        self.assertEqual(set(doc.to_dict()['requires']),
                         {'bands', 'spans'})
        ws = plot_file.worksheet_from_document(doc)
        cols = tuple(range(ws.column_count))
        payload = plot_file.worksheet_to_dict(ws, 'pure_line', cols, ov,
                                              for_save=True)
        self.assertEqual(set(payload['requires']),
                         {'bands', 'fills', 'spans'})
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'f.ilmplot.svg')
            plot_file.save_plot_file(path, doc, ws, 'pure_line', cols,
                                     ov)
            pf = plot_file.load_plot_file(path)
            self.assertEqual(pf.overrides.spans[0].id, 'sp1')
            self.assertEqual(pf.overrides.fills[0].id, 'f1')
            items2 = [
                Series(s.x, s.y, s.label, s.x_label, s.y_label,
                       y_column=s.y_column)
                for s in pf.plot_series()] if hasattr(
                    pf, 'plot_series') else None
            doc2 = effective_document(
                None, _items(), 'pure_line', pf.document.title,
                pf.overrides)
            self.assertEqual([b.id for b in doc2.bands], ['f1'])
            self.assertEqual([s.id for s in doc2.spans], ['sp1'])

    def test_no_fills_no_requires(self):
        ws_doc = effective_document(None, _items(), 'pure_line', '',
                                    PlotOverrides())
        ws = plot_file.worksheet_from_document(ws_doc)
        cols = tuple(range(ws.column_count))
        payload = plot_file.worksheet_to_dict(
            ws, 'pure_line', cols, PlotOverrides(), for_save=True)
        self.assertNotIn('requires', payload)


class PresetTests(unittest.TestCase):

    def test_capture_excludes_and_apply_keeps(self):
        ov = PlotOverrides()
        ov.series[1] = __import__(
            'src.plot_editor.overrides', fromlist=['x']
        ).SeriesOverride(color='#ff0000')
        ov.fills = [CurveFill(id='f', kind='under', a=1)]
        ov.spans = [Span(id='s', axis='x', lo=0, hi=1)]
        preset = presets.capture(ov, 'line')
        preset.name = 'probe'
        text = repr(preset.to_dict())
        self.assertNotIn('fills', text)
        self.assertNotIn('spans', text)
        presets.apply(presets.builtin_preset('line'), ov,
                      _items(), 'pure_line')
        self.assertIsNotNone(ov.fills)
        self.assertIsNotNone(ov.spans)


class ResetSemanticsTests(unittest.TestCase):

    def test_reset_carries_fills_spans_bands(self):
        # Mirrors PlotTab._reset_all_formatting's _reset helper without
        # Qt: copy every _KEYS field from a fresh overrides, except the
        # content fields which are carried over.
        o = PlotOverrides()
        o.fills = [CurveFill(id='f', kind='under', a=1)]
        o.spans = [Span(id='s', axis='x', lo=0, hi=1)]
        o.bands = [Band(id='b', x=[0, 1], y1=[0, 0], y2=[1, 1])]
        o.style.legend = __import__(
            'ilmplot.document', fromlist=['x']).LegendStyle()
        fresh = PlotOverrides()
        fresh.bands = o.bands
        fresh.spans = o.spans
        fresh.fills = o.fills
        for name in PlotOverrides._KEYS:
            setattr(o, name, getattr(fresh, name))
        self.assertEqual(o.fills[0].id, 'f')
        self.assertEqual(o.spans[0].id, 's')
        self.assertEqual(o.bands[0].id, 'b')
        self.assertIsNone(o.style.legend)


class StackedLineFillTests(unittest.TestCase):

    def test_fill_follows_drawn_series(self):
        # stacked_line bakes the cumulative offset into doc.series — a
        # fill under the 2nd series must follow the offset curve, not
        # the raw worksheet y values (1,1,1,1).
        ov = PlotOverrides()
        ov.fills = [CurveFill(id='f1', kind='under', a=2)]
        doc = effective_document(None, _items(), 'stacked_line',
                                 '', ov)
        band = next(b for b in doc.bands if b.id == 'f1')
        self.assertEqual(list(band.y2),
                         list(doc.series[1].y))
        self.assertNotEqual(list(band.y2), [1.0, 1.0, 1.0, 1.0])

    def test_between_fill_uses_drawn_series(self):
        ov = PlotOverrides()
        ov.fills = [CurveFill(id='f2', kind='between', a=1, b=2)]
        doc = effective_document(None, _items(), 'stacked_line',
                                 '', ov)
        band = next(b for b in doc.bands if b.id == 'f2')
        self.assertEqual(list(band.y2), list(doc.series[1].y))


class StaticBandsHelperTests(unittest.TestCase):

    def _setup(self):
        ov = PlotOverrides()
        ov.bands = [Band(id='b1', x=[0, 1], y1=[0, 0], y2=[1, 1],
                         label='static')]
        ov.fills = [CurveFill(id='f1', kind='under', a=1)]
        doc = effective_document(None, _items(), 'pure_line', '', ov)
        self.assertEqual([b.id for b in doc.bands], ['b1', 'f1'])
        return ov, doc

    def test_lift_excludes_fill_band(self):
        ov, doc = self._setup()
        lifted = [copy.copy(b) for b in static_bands(doc, ov)]
        self.assertEqual([b.id for b in lifted], ['b1'])
        # Simulate the panel lift path: editing the static band and
        # re-rendering must not duplicate the computed fill band.
        lifted[0].label = 'edited'
        ov.bands = lifted
        doc2 = effective_document(None, _items(), 'pure_line', '', ov)
        self.assertEqual([b.id for b in doc2.bands], ['b1', 'f1'])
        doc2.validate()

    def test_delete_static_band_keeps_fill(self):
        ov, doc = self._setup()
        lifted = [copy.copy(b) for b in static_bands(doc, ov)]
        ov.bands = [b for b in lifted if b.id != 'b1']
        doc2 = effective_document(None, _items(), 'pure_line', '', ov)
        self.assertEqual([b.id for b in doc2.bands], ['f1'])
        doc2.validate()


class LogFillRenderTests(unittest.TestCase):

    def test_log_y_under_fill_zero_baseline(self):
        import numpy as np
        from ilmplot.document import AxisStyle, PlotStyle
        from ilmplot.render import _build_figure, render_document
        ov = PlotOverrides()
        ov.fills = [CurveFill(id='f1', kind='under', a=1,
                              baseline=0.0)]
        doc = effective_document(None, _items(), 'pure_line', '', ov)
        st = PlotStyle()
        st.yaxis = AxisStyle(scale='log')
        doc.style = st
        svg = render_document(doc).svg.decode('utf-8')
        low = svg.lower()
        self.assertNotIn('nan', low)
        self.assertNotIn('inf', low)
        fig, ax = _build_figure(doc, 1.0, doc.width_mm, doc.height_mm)
        lo, hi = ax.get_ylim()
        self.assertGreater(lo, 0.0)
        poly = next(p for p in ax.patches
                    if p.get_gid() == 'ilmplot-band-f1')
        xy = np.asarray(poly.get_xy(), dtype=float)
        self.assertTrue(np.isfinite(xy).all())
        self.assertGreaterEqual(xy[:, 1].min(), lo - 1e-9)
        self.assertLessEqual(xy[:, 1].max(), hi + 1e-9)


class PickAreaTests(unittest.TestCase):

    REGIONS = {
        'bands': {'b1': {'bbox': (0.1, 0.1, 0.5, 0.5),
                         'points': [(0.1, 0.5), (0.1, 0.1),
                                    (0.4, 0.1), (0.4, 0.2)]}},
        'spans': {'s1': {'bbox': (0.0, 0.0, 1.0, 1.0),
                         'points': [(0.0, 0.0), (1.0, 0.0),
                                    (1.0, 1.0), (0.0, 1.0)]}}}

    def test_band_hit(self):
        self.assertEqual(
            hit_test.pick_area(self.REGIONS, 0.15, 0.15), 'band:b1')

    def test_band_over_span(self):
        # Inside the band polygon and the full-figure span: band wins.
        self.assertEqual(
            hit_test.pick_area(self.REGIONS, 0.3, 0.15), 'band:b1')

    def test_span_hit_below_band(self):
        # Inside the span but outside the band polygon.
        self.assertEqual(
            hit_test.pick_area(self.REGIONS, 0.8, 0.8), 'span:s1')

    def test_bbox_inside_polygon_outside(self):
        # Above the band's top edge (points max y = 0.5... the polygon
        # apex at y=0.2): x=0.45, y=0.45 is inside the bbox but outside
        # the L-shaped polygon.
        regions = {'bands': {'b1': {
            'bbox': (0.0, 0.0, 0.5, 0.5),
            'points': [(0.0, 0.5), (0.0, 0.0), (0.5, 0.0),
                       (0.5, 0.1), (0.1, 0.1), (0.1, 0.5)]}}}
        self.assertIsNone(hit_test.pick_area(regions, 0.4, 0.4))

    def test_empty(self):
        self.assertIsNone(hit_test.pick_area({}, 0.5, 0.5))
        self.assertIsNone(hit_test.pick_area(None, 0.5, 0.5))


if __name__ == '__main__':
    unittest.main()
