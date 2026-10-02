"""Non-UI checks for Plot Editor file save/load (no Qt)."""

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

from src.plot_editor import document, plot_file, render
from src.plot_editor.document import PlotDocument
from src.plot_editor.export import document_from_plot
from src.plot_editor.plot_data import Series
from src.plot_editor.plot_file import (WORKSHEET_METADATA_ID,
                                       PlotFileError, chart_from_document,
                                       load_plot_file, save_plot_file,
                                       series_from_document,
                                       worksheet_from_document,
                                       worksheet_to_dict)
from src.plot_editor.worksheet import Column, Worksheet


def series(xs, ys, label='L', xl='X', yl='Y'):
    return Series(tuple(xs), tuple(ys), label, xl, yl)


SERIES = [series([0, 1, 2], [1, 4, 2], 'L', 'XL', 'YL')]


def filled_worksheet():
    ws = Worksheet()
    ws.column(0).long_name = 'Time'
    ws.column(0).units = 's'
    ws.column(0).comments = 'x axis'
    ws.column(1).designation = 'Y'
    ws.column(0).values = [1.0, 'note', None, 4.0, None, None]
    ws.column(1).values = [2.0, None]
    return ws


def save(ws=None, path=None, chart='pure_line', cols=(0, 1)):
    ws = ws or filled_worksheet()
    doc = document_from_plot(SERIES, 'pure_line')
    save_plot_file(path, doc, ws, chart, cols)
    return path


class RoundTripTests(unittest.TestCase):

    def test_save_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'p.ilmplot.svg')
            ws = filled_worksheet()
            save(ws, path, 'line_scatters', (0, 1))
            pf = load_plot_file(path)
            self.assertTrue(pf.has_worksheet)
            self.assertEqual(pf.chart_key, 'line_scatters')
            self.assertEqual(pf.plot_columns, (0, 1))
            out = pf.worksheet
            self.assertEqual(out.column_count, 2)
            c0 = out.column(0)
            self.assertEqual((c0.designation, c0.long_name, c0.units,
                              c0.comments), ('X', 'Time', 's', 'x axis'))
            # Trailing Nones trimmed; interior preserved.
            self.assertEqual(c0.values, [1.0, 'note', None, 4.0])
            self.assertEqual(out.column(1).values, [2.0])

    def test_document_payload_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'p.ilmplot.svg')
            doc = document_from_plot(SERIES, 'pure_line')
            before = doc.to_dict()
            save_plot_file(path, doc, Worksheet(), 'pure_line', (0, 1))
            loaded = document.load_document(path)
            self.assertEqual(loaded.to_dict(), before)

    def test_worksheet_node_written_once(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'p.ilmplot.svg')
            save(path=path)
            save(path=path)
            with open(path, 'rb') as fh:
                data = fh.read()
            marker = b'id="%s"' % WORKSHEET_METADATA_ID.encode()
            self.assertEqual(data.count(marker), 1)

    def test_chart_null_roundtrips(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'p.ilmplot.svg')
            save(path=path, chart=None)
            pf = load_plot_file(path)
            self.assertIsNone(pf.chart_key)


class LegacyFallbackTests(unittest.TestCase):

    def _legacy(self, tmp, doc):
        path = os.path.join(tmp, 'legacy.ilmplot.svg')
        render.save_document(doc, path)
        return path

    def test_no_worksheet_node(self):
        with tempfile.TemporaryDirectory() as d:
            doc = PlotDocument()
            doc.series = [document.LineSeries(id='a', label='s1',
                                              x=[0, 1], y=[2, 3]),
                          document.LineSeries(id='b', label='s2',
                                              x=[0, 1], y=[4, 5])]
            doc.validate()
            pf = load_plot_file(self._legacy(d, doc))
            self.assertFalse(pf.has_worksheet)
            ws = pf.worksheet
            # Shared x → X, Y, Y.
            self.assertEqual([c.designation for c in ws.columns],
                             ['X', 'Y', 'Y'])
            self.assertEqual(ws.column(0).values, [0.0, 1.0])
            self.assertEqual(ws.column(1).long_name, 's1')

    def test_different_x_gives_new_x_column(self):
        with tempfile.TemporaryDirectory() as d:
            doc = PlotDocument()
            doc.series = [document.LineSeries(id='a', x=[0, 1], y=[2, 3]),
                          document.LineSeries(id='b', x=[5, 6], y=[4, 5])]
            doc.validate()
            pf = load_plot_file(self._legacy(d, doc))
            self.assertEqual([c.designation for c in pf.worksheet.columns],
                             ['X', 'Y', 'X', 'Y'])
            self.assertEqual(pf.plot_columns, (0, 1, 2, 3))

    def test_chart_inference(self):
        cases = {('-', ''): 'pure_line', ('--', ''): 'pure_line',
                 ('', 'o'): 'pure_scatters', ('-', 'o'): 'line_scatters'}
        for (ls, mk), key in cases.items():
            doc = PlotDocument()
            doc.series = [document.LineSeries(id='a', linestyle=ls,
                                              marker=mk)]
            doc.validate()
            self.assertEqual(chart_from_document(doc), key)

    def test_series_from_document(self):
        doc = PlotDocument()
        doc.xlabel = 'XX'
        doc.ylabel = 'YY'
        (s,) = series_from_document(doc)
        self.assertEqual((s.x_label, s.y_label), ('XX', 'YY'))
        self.assertEqual(s.x, tuple(doc.series[0].x))


class StrictnessTests(unittest.TestCase):

    def _load_payload(self, tmp, payload):
        path = os.path.join(tmp, 'p.ilmplot.svg')
        doc = document_from_plot(SERIES, 'pure_line')
        save_plot_file(path, doc, Worksheet(), 'pure_line', (0, 1))
        with open(path, 'rb') as fh:
            data = fh.read()
        marker = WORKSHEET_METADATA_ID.encode()
        start = data.index(marker)
        # Replace the JSON text of the worksheet node.
        text_start = data.index(b'>', start) + 1
        text_end = data.index(b'</', text_start)
        raw = json.dumps(payload, allow_nan=False,
                         separators=(',', ':')).encode()
        data = data[:text_start] + raw + data[text_end:]
        with open(path, 'wb') as fh:
            fh.write(data)
        return path

    def _ws_dict(self, **kw):
        d = worksheet_to_dict(Worksheet(), 'pure_line', (0, 1))
        d.update(kw)
        return d

    def test_unknown_key(self):
        with tempfile.TemporaryDirectory() as d:
            path = self._load_payload(d, self._ws_dict(extra=1))
            with self.assertRaises(PlotFileError):
                load_plot_file(path)

    def test_future_schema(self):
        with tempfile.TemporaryDirectory() as d:
            path = self._load_payload(d, self._ws_dict(schema_version=99))
            with self.assertRaises(PlotFileError) as ctx:
                load_plot_file(path)
            self.assertIn('99', str(ctx.exception))

    def test_bad_designation(self):
        with tempfile.TemporaryDirectory() as d:
            payload = self._ws_dict()
            payload['columns'][0]['designation'] = 'nope'
            with self.assertRaises(PlotFileError):
                load_plot_file(self._load_payload(d, payload))

    def test_bool_value_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            payload = self._ws_dict()
            payload['columns'][0]['values'] = [True]
            with self.assertRaises(PlotFileError):
                load_plot_file(self._load_payload(d, payload))

    def test_unknown_chart(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(PlotFileError):
                load_plot_file(
                    self._load_payload(d, self._ws_dict(chart='pie')))

    def test_out_of_range_plot_columns(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(PlotFileError):
                load_plot_file(
                    self._load_payload(d, self._ws_dict(plot_columns=[7])))

    def test_nan_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = self._load_payload(d, self._ws_dict())
            with open(path, 'rb') as fh:
                data = fh.read()
            data = data.replace(b'"values":[]', b'"values":[NaN]', 1)
            with open(path, 'wb') as fh:
                fh.write(data)
            with self.assertRaises(PlotFileError):
                load_plot_file(path)

    def test_oversize_rejected_no_leftovers(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'p.ilmplot.svg')
            with patch.object(plot_file, 'MAX_FILE_BYTES', 100):
                with self.assertRaises(PlotFileError):
                    save(path=path)
            self.assertFalse(os.path.exists(path))
            self.assertEqual(
                [f for f in os.listdir(d) if f.endswith('.tmp')], [])


class FromColumnsTests(unittest.TestCase):

    def test_copies_and_empty_history(self):
        src = [Column('X', 'n', 'u', 'c', [1.0]),
               Column('Y', values=[2.0])]
        ws = Worksheet.from_columns(src)
        src[0].values.append(9.0)
        src[1].long_name = 'changed'
        self.assertEqual(ws.column(0).values, [1.0])
        self.assertEqual(ws.column(1).long_name, '')
        self.assertFalse(ws.can_undo)
        self.assertFalse(ws.can_redo)

    def test_empty_rejected(self):
        with self.assertRaises(ValueError):
            Worksheet.from_columns([])

    def test_no_pyplot_imported(self):
        self.assertNotIn('matplotlib.pyplot', sys.modules)


if __name__ == '__main__':
    unittest.main()
