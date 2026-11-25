"""Function-curve columns in the Plot Editor, no Qt.

Covers the formula parser (``src.plot_editor.formula``), sheet →
series building (``build_series(functions=...)``), document generation
and re-sampling over explicit axis limits, and the worksheet-file
``function_columns`` capability.
"""
import math
import os
import tempfile
import unittest
from unittest import mock

import src  # noqa: F401  -- puts packages/ilmplot/src on sys.path

from src.plot_editor import plot_file
from src.plot_editor.export import document_from_plot
from src.plot_editor.formula import (MAX_FORMULA_CHARS, FormulaError,
                                     parse, sample)
from src.plot_editor.overrides import (PlotOverrides,
                                       effective_document)
from src.plot_editor.plot_data import (PlotSelectionError, build_series,
                                       function_text)
from src.plot_editor.plot_file import (load_plot_file, save_plot_file,
                                       worksheet_to_dict)
from src.plot_editor.worksheet import Column, Worksheet


def _sheet(designations, values):
    return Worksheet.from_columns(
        [Column(d, values=v) for d, v in zip(designations, values)])


def _fn_sheet(formula):
    return _sheet(['X', 'Y', 'Function'],
                  [[0.0, 1.0, 2.0], [1.0, 2.0, 3.0], [formula]])


class FormulaParseTests(unittest.TestCase):

    def test_eval_basic(self):
        self.assertEqual(parse('2*x+1').eval(3.0), 7.0)
        self.assertEqual(parse('2x+1').eval(3.0), 7.0)
        self.assertEqual(parse('-x^2').eval(3.0), -9.0)
        self.assertEqual(parse('2^-x').eval(1.0), 0.5)
        self.assertEqual(parse('x**2').eval(3.0), 9.0)
        self.assertEqual(parse('(x+1)(x-1)').eval(3.0), 8.0)
        self.assertAlmostEqual(parse(r'\sin(\pi/2)').eval(0.0), 1.0)
        self.assertEqual(parse(r'\sqrt{x}').eval(4.0), 2.0)
        self.assertEqual(parse(r'\log(100)').eval(0.0), 2.0)
        self.assertEqual(parse(r'\log_2(8)').eval(0.0), 3.0)
        self.assertAlmostEqual(parse(r'\ln(\e)').eval(0.0), 1.0)
        self.assertEqual(parse(r'\abs(-3)').eval(0.0), 3.0)
        self.assertAlmostEqual(parse('x\\pi').eval(1.0), math.pi)
        self.assertAlmostEqual(parse(r'\tan(\pi/4)').eval(0.0), 1.0)

    def test_axis_and_constant(self):
        f = parse('y=3')
        self.assertEqual((f.axis, f.constant), ('y', True))
        self.assertEqual(f.eval(0.0), 3.0)
        f = parse('x=2')
        self.assertEqual((f.axis, f.constant), ('x', True))
        f = parse('x=y^2')
        self.assertEqual((f.axis, f.constant), ('x', False))
        self.assertEqual(f.eval(3.0), 9.0)
        f = parse('=x')
        self.assertEqual((f.axis, f.constant), ('y', False))
        self.assertEqual(parse('3').axis, 'y')
        self.assertTrue(parse('3').constant)

    def test_errors(self):
        for bad in ('sin(x)', '2*', '(x', r'\foo(x)', r'\sin x',
                    'y', 'z', '', 'x' * (MAX_FORMULA_CHARS + 1),
                    '('*60 + '1' + ')'*60, r'\sin_2(x)',
                    r'\log_1(x)', r'\log_0(x)', 'x)', 'x='):
            with self.assertRaises(FormulaError, msg=repr(bad)[:40]):
                parse(bad)
        # The variable error names the allowed variable.
        with self.assertRaises(FormulaError) as cm:
            parse('sin(x)')
        self.assertIn("'x'", str(cm.exception))
        with self.assertRaises(FormulaError) as cm:
            parse('x=x+1')
        self.assertIn("'y'", str(cm.exception))

    def test_eval_nan(self):
        self.assertTrue(math.isnan(parse('1/x').eval(0.0)))
        self.assertTrue(math.isnan(parse(r'\ln(x)').eval(-1.0)))
        self.assertTrue(math.isnan(parse('(-8)^(1/3)').eval(0.0)))
        self.assertTrue(math.isnan(parse(r'\sqrt{x}').eval(-1.0)))

    def test_sample(self):
        xs, ys = sample(parse('y=2*x'), 0.0, 2.0, n=5)
        self.assertEqual(list(zip(xs, ys)),
                         [(0.0, 0.0), (0.5, 1.0), (1.0, 2.0),
                          (1.5, 3.0), (2.0, 4.0)])
        # Non-finite samples are dropped (pole at x = 0).
        xs, ys = sample(parse('y=1/x'), -1.0, 1.0)
        self.assertNotIn(0.0, xs)
        self.assertTrue(all(math.isfinite(v) for v in ys))
        # Constant → exactly the two range ends.
        xs, ys = sample(parse('y=3'), 0.0, 10.0)
        self.assertEqual((xs, ys), ([0.0, 10.0], [3.0, 3.0]))
        # axis 'x': the sampled variable is y.
        xs, ys = sample(parse('x=y^2'), 0.0, 2.0, n=5)
        self.assertEqual(list(zip(xs, ys)),
                         [(0.0, 0.0), (0.25, 0.5), (1.0, 1.0),
                          (2.25, 1.5), (4.0, 2.0)])
        # lo == hi widens by ±0.5.
        xs, ys = sample(parse('y=x'), 1.0, 1.0, n=3)
        self.assertEqual((xs[0], xs[-1]), (0.5, 1.5))


class BuildSeriesTests(unittest.TestCase):

    def test_function_series_basic(self):
        ws = _fn_sheet('2*x')
        a, f = build_series(ws, [0, 1, 2])
        self.assertEqual(f.y_column, 2)
        self.assertEqual(f.function, '2*x')
        self.assertEqual(f.label, '2*x')
        # Sampled over the data x-range (0..2), not the default.
        self.assertEqual((f.x[0], f.x[-1]), (0.0, 2.0))
        self.assertAlmostEqual(f.y[-1], 4.0)
        self.assertEqual((f.x_label, f.y_label), (a.x_label, a.y_label))

    def test_label_long_name_wins(self):
        ws = _fn_sheet(r'\sin(x)')
        ws.column(2).long_name = 'Fit'
        _a, f = build_series(ws, [0, 1, 2])
        self.assertEqual(f.label, 'Fit')

    def test_vertical_line_spans_y_range(self):
        ws = _sheet(['Y', 'Function'], [[1.0, 3.0], ['x=2']])
        _y, f = build_series(ws, [0, 1])
        self.assertEqual((f.x, f.y), ((2.0, 2.0), (1.0, 3.0)))

    def test_function_only_default_range(self):
        ws = _sheet(['Function'], [['y=x^2']])
        (f,) = build_series(ws, [0])
        self.assertEqual((f.x[0], f.x[-1]), (-10.0, 10.0))
        self.assertEqual((f.y_label, f.x_label), ('y', 'x'))

    def test_invalid_skipped_and_error(self):
        ws = _fn_sheet('bogus(')
        series = build_series(ws, [0, 1, 2])
        self.assertEqual(len(series), 1)
        self.assertIsNone(series[0].function)
        ws = _sheet(['Function'], [['bogus(']])
        with self.assertRaises(PlotSelectionError) as cm:
            build_series(ws, [0])
        self.assertIn('bogus', str(cm.exception))
        ws = _sheet(['Function'], [['']])
        with self.assertRaises(PlotSelectionError) as cm:
            build_series(ws, [0])
        self.assertIn('first cell', str(cm.exception))

    def test_functions_flag_off(self):
        ws = _fn_sheet('2*x')
        series = build_series(ws, [0, 1, 2], functions=False)
        self.assertEqual(len(series), 1)
        self.assertIsNone(series[0].function)

    def test_yerr_barrier(self):
        ws = _sheet(['Y', 'Function', 'yErr'],
                    [[1.0, 2.0], ['x'], [0.5, 0.5]])
        (s,) = build_series(ws, [0, 2])
        self.assertIsNone(s.yerr)

    def test_function_text_helper(self):
        col = Column('Function', values=[3.0, 'ignored'])
        self.assertEqual(function_text(col), '3')
        self.assertEqual(function_text(Column('Function')), '')


class DocumentTests(unittest.TestCase):

    def _items(self):
        return build_series(_fn_sheet('x^2'), [0, 1, 2])

    def test_scatter_keeps_function_a_line(self):
        doc = document_from_plot(self._items(), 'pure_scatters')
        data, fn = doc.series
        self.assertEqual(data.marker, 'o')
        self.assertEqual(fn.marker, '')
        self.assertEqual(fn.linestyle, '-')
        self.assertEqual(fn.drawstyle, 'default')

    def test_step_chart_function_not_steps(self):
        doc = document_from_plot(self._items(), 'step_line')
        self.assertEqual(doc.series[1].drawstyle, 'default')
        self.assertEqual(doc.series[0].drawstyle, 'steps-post')

    def test_xlim_resamples(self):
        items = self._items()
        o = PlotOverrides()
        o.xlim = [0.0, 100.0]
        doc = effective_document(None, items, 'pure_line', 'T', o)
        fn = doc.series[1]
        self.assertEqual((fn.x[0], fn.x[-1]), (0.0, 100.0))
        self.assertAlmostEqual(fn.y[-1], 10000.0)
        # Reversed limits sort before sampling.
        o.xlim = [100.0, 0.0]
        doc = effective_document(None, items, 'pure_line', 'T', o)
        self.assertEqual((doc.series[1].x[0], doc.series[1].x[-1]),
                         (0.0, 100.0))
        # No explicit limit → data range kept.
        doc = effective_document(None, items, 'pure_line', 'T',
                                 PlotOverrides())
        self.assertEqual((doc.series[1].x[0], doc.series[1].x[-1]),
                         (0.0, 2.0))

    def test_ylim_resamples_axis_x(self):
        ws = _sheet(['Y', 'Function'],
                    [[1.0, 2.0, 3.0], ['x=y^2']])
        items = build_series(ws, [0, 1])
        o = PlotOverrides()
        o.ylim = [0.0, 4.0]
        doc = effective_document(None, items, 'pure_line', 'T', o)
        fn = doc.series[1]
        self.assertEqual((fn.y[0], fn.y[-1]), (0.0, 4.0))
        self.assertAlmostEqual(fn.x[-1], 16.0)


class PlotFileTests(unittest.TestCase):

    def _doc_items(self):
        ws = _fn_sheet('2*x')
        items = build_series(ws, [0, 1, 2])
        return ws, items, document_from_plot(items, 'pure_line')

    def test_requires_function_columns(self):
        ws, _items, _doc = self._doc_items()
        d = worksheet_to_dict(ws, 'pure_line', (0, 1, 2))
        self.assertIn('function_columns', d['requires'])
        plain = Worksheet.from_columns([Column('Y')])
        d2 = worksheet_to_dict(plain, 'pure_line', (0,))
        self.assertNotIn('function_columns', d2.get('requires', []))

    def test_round_trip(self):
        ws, _items, doc = self._doc_items()
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, 'p.ilmplot.svg')
            save_plot_file(path, doc, ws, 'pure_line', (0, 1, 2),
                           PlotOverrides())
            pf = load_plot_file(path)
        self.assertTrue(pf.has_worksheet)
        self.assertEqual(pf.plot_columns, (0, 1, 2))
        col = pf.worksheet.column(2)
        self.assertEqual(col.designation, 'Function')
        self.assertEqual(function_text(col), '2*x')

    def test_old_reader_degrades(self):
        ws, _items, doc = self._doc_items()
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, 'p.ilmplot.svg')
            save_plot_file(path, doc, ws, 'pure_line', (0, 1, 2),
                           PlotOverrides())
            old = plot_file.WORKSHEET_CAPABILITIES - {'function_columns'}
            with mock.patch.object(plot_file,
                                   'WORKSHEET_CAPABILITIES', old):
                pf = load_plot_file(path)
        self.assertFalse(pf.has_worksheet)
        self.assertTrue(pf.read_only_source)
        self.assertTrue(any('function_columns' in w
                            for w in pf.warnings))


if __name__ == '__main__':
    unittest.main()
