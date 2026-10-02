"""Pure-Python checks for the Plot Editor plot pipeline."""

import sys
import unittest

from src.plot_editor.actions import CHART_GROUPS
from src.plot_editor.plot_data import (PlotSelectionError, build_series)
from src.plot_editor.plotting import figure_svg, make_figure
from src.plot_editor.worksheet import Worksheet


def make_ws(designations):
    ws = Worksheet()
    while ws.column_count < len(designations):
        ws.insert_columns(ws.column_count, 1)
    for i, d in enumerate(designations):
        ws.set_designation([i], d)
    return ws


def fill(ws, col, values):
    ws._columns[col].values = list(values)


class BuildSeriesTests(unittest.TestCase):

    def test_y_only_uses_row_index(self):
        ws = make_ws(['Y'])
        fill(ws, 0, [1.0, 2.0])
        (s,) = build_series(ws, [0])
        self.assertEqual(s.x, (1.0, 2.0))
        self.assertEqual(s.y, (1.0, 2.0))
        self.assertEqual(s.x_label, 'Row')

    def test_y_only_no_x_in_sheet(self):
        ws = make_ws(['Y', 'Y'])
        fill(ws, 0, [1.0])
        fill(ws, 1, [2.0])
        series = build_series(ws, [0, 1])
        self.assertEqual(len(series), 2)
        self.assertEqual(series[1].x_label, 'Row')

    def test_nearest_left_among_selected_xs(self):
        ws = make_ws(['X', 'Y', 'X', 'Y'])
        fill(ws, 0, [10.0])
        fill(ws, 2, [20.0])
        fill(ws, 3, [5.0])
        # Selecting 0,1,3: col 2 is not selected, so col 3 uses X col 0.
        (s,) = build_series(ws, [0, 1, 3])
        self.assertEqual(s.x, (10.0,))
        # Selecting 0,2,3: nearest selected X left of 3 is 2.
        (s,) = build_series(ws, [0, 2, 3])
        self.assertEqual(s.x, (20.0,))

    def test_unselected_x_falls_back_to_sheet(self):
        ws = make_ws(['X', 'X', 'Y'])
        fill(ws, 0, [1.0])
        fill(ws, 1, [2.0])
        fill(ws, 2, [3.0])
        (s,) = build_series(ws, [2])
        self.assertEqual(s.x, (2.0,))

    def test_y_left_of_every_x_uses_rows(self):
        ws = make_ws(['Y', 'X'])
        fill(ws, 0, [4.0, 5.0])
        fill(ws, 1, [9.0, 9.0])
        (s,) = build_series(ws, [0])
        self.assertEqual(s.x, (1.0, 2.0))
        self.assertEqual(s.x_label, 'Row')

    def test_non_numeric_rows_skipped(self):
        ws = make_ws(['X', 'Y'])
        fill(ws, 0, [1.0, 'bad', 3.0])
        fill(ws, 1, [7.0, 8.0, None])
        (s,) = build_series(ws, [0, 1])
        self.assertEqual(s.x, (1.0,))
        self.assertEqual(s.y, (7.0,))

    def test_labels_use_long_name_and_units(self):
        ws = make_ws(['X', 'Y'])
        ws.column(0).long_name = 'Time'
        ws.column(0).units = 's'
        ws.column(1).units = 'V'
        fill(ws, 0, [0.0])
        fill(ws, 1, [1.0])
        (s,) = build_series(ws, [0, 1])
        self.assertEqual(s.x_label, 'Time (s)')
        self.assertEqual(s.y_label, 'B (V)')
        self.assertEqual(s.label, 'B')

    def test_legend_prefers_comment_then_long_name(self):
        ws = make_ws(['X', 'Y', 'Y', 'Y'])
        ws.column(1).comments = '\n Sample A \nsecond line'
        ws.column(1).long_name = 'Current'
        ws.column(2).long_name = 'Current'
        ws.column(2).units = 'mA'
        for c in range(4):
            fill(ws, c, [1.0])
        a, b, c = build_series(ws, [0, 1, 2, 3])
        self.assertEqual(a.label, 'Sample A')
        self.assertEqual(b.label, 'Current')
        self.assertEqual(b.y_label, 'Current (mA)')
        self.assertEqual(c.label, 'D')

    def test_label_column_gives_categorical_x(self):
        ws = make_ws(['Label', 'Y'])
        ws.column(0).long_name = 'Group'
        fill(ws, 0, ['a', 'b', 'c'])
        fill(ws, 1, [1.0, 2.0, 3.0])
        (s,) = build_series(ws, [0, 1])
        self.assertEqual(s.x, (1.0, 2.0, 3.0))
        self.assertEqual(s.x_ticklabels, ('a', 'b', 'c'))
        self.assertEqual(s.x_label, 'Group')

    def test_label_column_keeps_row_numbers_when_y_skipped(self):
        ws = make_ws(['Label', 'Y'])
        fill(ws, 0, ['a', 'b', 'c'])
        fill(ws, 1, [1.0, None, 3.0])
        (s,) = build_series(ws, [0, 1])
        self.assertEqual(s.x, (1.0, 3.0))
        self.assertEqual(s.x_ticklabels, ('a', 'c'))

    def test_label_column_formats_cell_text(self):
        ws = make_ws(['Label', 'Y'])
        fill(ws, 0, [2.0, 'text', None])
        fill(ws, 1, [1.0, 2.0, 3.0])
        (s,) = build_series(ws, [0, 1])
        self.assertEqual(s.x_ticklabels, ('2', 'text', ''))

    def test_nearest_pool_column_wins(self):
        # X nearer to Y than the Label column → numeric axis.
        ws = make_ws(['Label', 'X', 'Y'])
        fill(ws, 0, ['a'])
        fill(ws, 1, [5.0])
        fill(ws, 2, [9.0])
        (s,) = build_series(ws, [0, 1, 2])
        self.assertEqual(s.x, (5.0,))
        self.assertIsNone(s.x_ticklabels)
        # Label nearer to Y than the X column → categorical axis.
        ws = make_ws(['X', 'Label', 'Y'])
        fill(ws, 0, [5.0])
        fill(ws, 1, ['a'])
        fill(ws, 2, [9.0])
        (s,) = build_series(ws, [0, 1, 2])
        self.assertEqual(s.x, (1.0,))
        self.assertEqual(s.x_ticklabels, ('a',))

    def test_unselected_label_not_used(self):
        ws = make_ws(['Label', 'Y'])
        fill(ws, 0, ['a', 'b'])
        fill(ws, 1, [1.0, 2.0])
        (s,) = build_series(ws, [1])
        self.assertEqual(s.x, (1.0, 2.0))
        self.assertIsNone(s.x_ticklabels)
        self.assertEqual(s.x_label, 'Row')

    def test_no_y_raises(self):
        ws = make_ws(['X'])
        fill(ws, 0, [1.0])
        with self.assertRaises(PlotSelectionError) as ctx:
            build_series(ws, [0])
        self.assertIn('Y column', str(ctx.exception))

    def test_all_non_numeric_raises(self):
        ws = make_ws(['X', 'Y'])
        fill(ws, 0, ['a'])
        fill(ws, 1, ['b'])
        with self.assertRaises(PlotSelectionError) as ctx:
            build_series(ws, [0, 1])
        self.assertIn('no numeric', str(ctx.exception))


def series(xs, ys, label='L', xl='X', yl='Y'):
    from src.plot_editor.plot_data import Series
    return Series(tuple(xs), tuple(ys), label, xl, yl)


def one_series():
    return [series([0, 1, 2], [1, 4, 2], 'L', 'XL', 'YL')]


class MakeFigureTests(unittest.TestCase):

    def ax(self, fig):
        return fig.axes[0]

    def test_all_chart_keys_covered(self):
        for group in CHART_GROUPS:
            for chart in group.charts:
                fig = make_figure(one_series(), chart.key)
                self.assertEqual(len(fig.axes), 1)

    def test_pure_line(self):
        fig = make_figure(one_series(), 'pure_line')
        ax = self.ax(fig)
        self.assertEqual(len(ax.lines), 1)
        self.assertEqual(len(ax.collections), 0)

    def test_pure_scatters(self):
        fig = make_figure(one_series(), 'pure_scatters')
        ax = self.ax(fig)
        self.assertEqual(len(ax.collections), 1)
        self.assertEqual(len(ax.lines), 0)

    def test_line_scatters(self):
        fig = make_figure(one_series(), 'line_scatters')
        ax = self.ax(fig)
        self.assertEqual(len(ax.lines), 1)
        self.assertEqual(ax.lines[0].get_marker(), 'o')

    def test_legend_only_for_multiple_series(self):
        fig = make_figure(one_series(), 'pure_line')
        self.assertIsNone(self.ax(fig).get_legend())
        two = one_series() + [series([0, 1], [2, 3], 'M')]
        fig = make_figure(two, 'pure_line')
        self.assertIsNotNone(self.ax(fig).get_legend())

    def test_stacked_offsets(self):
        a = series([0, 1], [1, 4], 'A')
        b = series([0, 1], [5, 7], 'B')
        c = series([0, 1], [0, 1], 'C')
        fig = make_figure([a, b, c], 'stacked_line')
        lines = self.ax(fig).lines
        self.assertEqual(tuple(lines[0].get_ydata()), (1, 4))
        # offset_1 = (4 + 0) - 5 = -1 → y2 = (4, 6)
        self.assertEqual(tuple(lines[1].get_ydata()), (4, 6))
        # offset_2 = (7 + -1) - 0 = 6 → y3 = (6, 7)
        self.assertEqual(tuple(lines[2].get_ydata()), (6, 7))
        self.assertTrue(lines[2].get_ydata()[0] > lines[1].get_ydata()[0])

    def test_title(self):
        fig = make_figure(one_series(), 'pure_line', title='My Plot')
        self.assertEqual(self.ax(fig).get_title(), 'My Plot')
        fig = make_figure(one_series(), 'pure_line')
        self.assertEqual(self.ax(fig).get_title(), '')

    def test_axis_labels_from_first_series(self):
        fig = make_figure(one_series(), 'pure_line')
        ax = self.ax(fig)
        self.assertEqual(ax.get_xlabel(), 'XL')
        self.assertEqual(ax.get_ylabel(), 'YL')

    def test_x_ticklabels_applied(self):
        s = series([1, 2, 3], [1, 4, 2])
        s = s.__class__(s.x, s.y, s.label, s.x_label, s.y_label,
                        ('low', 'mid', 'high'))
        fig = make_figure([s], 'pure_line')
        ax = self.ax(fig)
        self.assertEqual([t.get_text() for t in ax.get_xticklabels()],
                         ['low', 'mid', 'high'])
        self.assertEqual(list(ax.get_xticks()), [1, 2, 3])

    def test_no_ticklabels_keeps_numeric_ticks(self):
        from matplotlib.ticker import FixedLocator
        fig = make_figure(one_series(), 'pure_line')
        ax = self.ax(fig)
        self.assertNotIsInstance(ax.xaxis.get_major_locator(),
                                 FixedLocator)

    def test_unknown_key_raises(self):
        with self.assertRaises(ValueError):
            make_figure(one_series(), 'nope')

    def test_figure_svg(self):
        data = figure_svg(make_figure(one_series(), 'pure_line'))
        self.assertTrue(data.startswith(b'<?xml'))
        self.assertIn(b'<svg', data)

    def test_no_pyplot_imported(self):
        self.assertNotIn('matplotlib.pyplot', sys.modules)


if __name__ == '__main__':
    unittest.main()
