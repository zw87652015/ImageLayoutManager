"""Non-UI checks for plot-element hit-testing and panel helpers."""

import unittest

from src.plot_editor import hit_test
from src.plot_editor.overrides import (PlotOverrides, SeriesOverride,
                                       parse_axis_limits, reset_element)


class RectMappingTests(unittest.TestCase):

    def test_frac_to_rect(self):
        self.assertEqual(
            hit_test.frac_to_rect((0.1, 0.2, 0.5, 0.6), 100, 200),
            (10, 40, 50, 120))

    def test_rect_hit(self):
        bbox = (0.1, 0.2, 0.5, 0.6)
        self.assertTrue(hit_test.rect_hit(bbox, 0.3, 0.4))
        self.assertTrue(hit_test.rect_hit(bbox, 0.1, 0.2))
        self.assertFalse(hit_test.rect_hit(bbox, 0.05, 0.4))
        self.assertFalse(hit_test.rect_hit(None, 0.3, 0.4))


class PriorityTests(unittest.TestCase):

    REGIONS = {
        'title': (0.3, 0.0, 0.7, 0.1),
        'xlabel': (0.3, 0.9, 0.7, 1.0),
        'ylabel': (0.0, 0.3, 0.1, 0.7),
        'xticks': (0.2, 0.8, 0.8, 0.9),
        'yticks': (0.1, 0.2, 0.2, 0.8),
        'legend': (0.6, 0.05, 0.9, 0.3),
        'frame': (0.2, 0.1, 0.8, 0.8),
        'series': {},
    }

    def test_priority_order(self):
        # Point inside both legend and title bboxes → legend wins.
        self.assertEqual(hit_test.pick(self.REGIONS, 0.65, 0.08),
                         'legend')
        # title-only point
        self.assertEqual(hit_test.pick(self.REGIONS, 0.4, 0.05), 'title')
        self.assertEqual(hit_test.pick(self.REGIONS, 0.4, 0.95), 'xlabel')
        self.assertEqual(hit_test.pick(self.REGIONS, 0.05, 0.5), 'ylabel')
        self.assertEqual(hit_test.pick(self.REGIONS, 0.5, 0.85), 'xticks')
        self.assertEqual(hit_test.pick(self.REGIONS, 0.15, 0.5), 'yticks')
        self.assertIsNone(hit_test.pick(self.REGIONS, 0.95, 0.95))

    def test_frame_fallback(self):
        self.assertEqual(hit_test.pick_frame(self.REGIONS, 0.5, 0.5),
                         'frame')
        self.assertIsNone(hit_test.pick_frame(self.REGIONS, 0.9, 0.9))
        self.assertIsNone(hit_test.pick_frame(None, 0.5, 0.5))


class PolylineTests(unittest.TestCase):

    def test_point_segment_distance(self):
        self.assertAlmostEqual(
            hit_test.point_segment_distance(0, 1, -1, 0, 1, 0), 1.0)
        self.assertAlmostEqual(
            hit_test.point_segment_distance(0, 0.5, -1, 0, 1, 0), 0.5)
        self.assertAlmostEqual(
            hit_test.point_segment_distance(2, 0, -1, 0, 1, 0), 1.0)
        # degenerate segment → point distance
        self.assertAlmostEqual(
            hit_test.point_segment_distance(3, 4, 0, 0, 0, 0), 5.0)

    def test_pick_series(self):
        series = {'s0': {'bbox': (0, 0, 10, 10),
                         'points': [(0, 0), (10, 0), (10, 10)]},
                  's1': {'bbox': (20, 20, 30, 30),
                         'points': [(20, 20)]}}
        # on the polyline
        self.assertEqual(hit_test.pick_series(series, 5, 1, 5), 's0')
        # markers-only / single point
        self.assertEqual(hit_test.pick_series(series, 21, 21, 5), 's1')
        # inside bbox but far from the line
        self.assertIsNone(hit_test.pick_series(series, 5, 9, 3))
        # outside all bboxes
        self.assertIsNone(hit_test.pick_series(series, 50, 50, 5))
        # empty/None
        self.assertIsNone(hit_test.pick_series(None, 0, 0, 5))
        self.assertIsNone(hit_test.pick_series(
            {'s2': {'bbox': None, 'points': []}}, 0, 0, 5))


class AxisLimitTests(unittest.TestCase):

    def test_parse_axis_limits(self):
        self.assertEqual(parse_axis_limits('', ''), (None, False))
        self.assertEqual(parse_axis_limits('  ', None), (None, False))
        self.assertEqual(parse_axis_limits('0', '10'), ([0.0, 10.0], False))
        self.assertEqual(parse_axis_limits('-2.5', '3'), ([-2.5, 3.0],
                                                          False))
        # errors: half-empty, non-numeric, equal, non-finite
        for lo, hi in (('0', ''), ('x', '1'), ('1', '1'),
                       ('nan', '1'), ('0', 'inf')):
            lim, err = parse_axis_limits(lo, hi)
            self.assertTrue(err, (lo, hi))
            self.assertIsNone(lim)


class ResetElementTests(unittest.TestCase):

    def _populated(self):
        o = PlotOverrides()
        o.xlabel = 'X'
        o.ylabel = 'Y'
        o.legend = True
        o.legend_location = 'upper left'
        o.grid = True
        o.xlim = [0, 1]
        o.ylim = [0, 1]
        from src.plot_editor.document import (AxisStyle, FrameStyle,
                                              GridStyle, LegendStyle,
                                              TextStyle, TitleStyle)
        o.style.title = TitleStyle(bold=True)
        o.style.xlabel = TextStyle(bold=True)
        o.style.ylabel = TextStyle(bold=True)
        o.style.xaxis = AxisStyle(rotation=30)
        o.style.yaxis = AxisStyle(rotation=30)
        o.style.legend = LegendStyle(ncols=2)
        o.style.frame = FrameStyle(hide_top=True)
        o.style.grid = GridStyle(alpha=0.9)
        o.series[3] = SeriesOverride(color='#ff0000')
        return o

    def test_reset_title(self):
        o = self._populated()
        reset_element(o, 'title')
        self.assertIsNone(o.style.title)
        self.assertIsNotNone(o.style.xlabel)

    def test_reset_axis_labels(self):
        o = self._populated()
        reset_element(o, 'xlabel')
        self.assertIsNone(o.xlabel)
        self.assertIsNone(o.style.xlabel)
        reset_element(o, 'ylabel')
        self.assertIsNone(o.ylabel)
        self.assertIsNone(o.style.ylabel)

    def test_reset_axis(self):
        o = self._populated()
        reset_element(o, 'xticks')
        self.assertIsNone(o.xlim)
        self.assertIsNone(o.style.xaxis)
        reset_element(o, 'yticks')
        self.assertIsNone(o.ylim)
        self.assertIsNone(o.style.yaxis)

    def test_reset_legend(self):
        o = self._populated()
        reset_element(o, 'legend')
        self.assertIsNone(o.legend)
        self.assertIsNone(o.legend_location)
        self.assertIsNone(o.style.legend)

    def test_reset_frame_keeps_legend(self):
        o = self._populated()
        reset_element(o, 'frame')
        self.assertIsNone(o.grid)
        self.assertIsNone(o.style.frame)
        self.assertIsNone(o.style.grid)
        self.assertTrue(o.legend)  # legend override untouched

    def test_reset_series(self):
        o = self._populated()
        reset_element(o, 'series:s0', y_column=3)
        self.assertNotIn(3, o.series)
        # no-op without a column
        o.series[4] = SeriesOverride(color='#ff0000')
        reset_element(o, 'series:s9', y_column=None)
        self.assertIn(4, o.series)


class SeriesMappingTests(unittest.TestCase):

    def test_id_to_y_column(self):
        # Mirrors PlotTab._series_y_column: doc.series[i] pairs with
        # plot.series[i].y_column.
        from src.plot_editor.export import document_from_plot
        from src.plot_editor.plot_data import Series
        series = [Series((0., 1.), (0., 1.), 'L%d' % i, 'X', 'Y',
                         None, i) for i in range(2)]
        doc = document_from_plot(series, 'pure_line')
        mapping = {s.id: series[i].y_column
                   for i, s in enumerate(doc.series)}
        self.assertEqual(mapping, {'s0': 0, 's1': 1})
        # Series without a column index stay unmapped.
        series[1] = Series((0.,), (0.,), 'L', 'X', 'Y')
        doc = document_from_plot(series, 'pure_line')
        mapping = {s.id: series[i].y_column
                   for i, s in enumerate(doc.series)}
        self.assertIsNone(mapping['s1'])


class MiscHelperTests(unittest.TestCase):

    def test_resolve_font_family(self):
        from src.plot_editor.render import resolve_font_family
        fams = ('DejaVu Sans', 'Arial', 'Times New Roman')
        self.assertEqual(resolve_font_family('', fams), (None, True))
        self.assertEqual(resolve_font_family('  ', fams), (None, True))
        self.assertEqual(resolve_font_family('arial', fams),
                         ('Arial', True))
        self.assertEqual(resolve_font_family('Times New Roman', fams),
                         ('Times New Roman', True))
        self.assertEqual(resolve_font_family('Not A Font', fams),
                         (None, False))

    def test_apply_update_rolls_back(self):
        from src.plot_editor.overrides import apply_update
        o = PlotOverrides()
        o.xlabel = 'keep'

        def bad(xo):
            xo.xlabel = 'broken'
            raise RuntimeError('boom')
        self.assertFalse(apply_update(o, bad, lambda: None))
        self.assertEqual(o.xlabel, 'keep')

        calls = []

        def failing_commit():
            calls.append(1)
            raise RuntimeError('render boom')
        self.assertFalse(apply_update(
            o, lambda xo: setattr(xo, 'ylabel', 'Y!'), failing_commit))
        self.assertIsNone(o.ylabel)
        self.assertEqual(len(calls), 2)  # failed render + restore render

        ok = []
        self.assertTrue(apply_update(
            o, lambda xo: setattr(xo, 'grid', True),
            lambda: ok.append(1)))
        self.assertTrue(o.grid)

    def test_is_native_plot_path(self):
        import os
        import tempfile
        from src.plot_editor.ilm_bridge import is_native_plot_path
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'P.ILMPLOT.SVG')
            open(p, 'wb').write(b'<svg/>')
            self.assertTrue(is_native_plot_path(p))
            self.assertFalse(is_native_plot_path(
                os.path.join(d, 'a.svg')))
            self.assertFalse(is_native_plot_path(
                os.path.join(d, 'missing.ilmplot.svg')))
            self.assertFalse(is_native_plot_path(''))
            self.assertFalse(is_native_plot_path(d))


if __name__ == '__main__':
    unittest.main()
