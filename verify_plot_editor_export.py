"""Non-UI checks for the Plot Editor export pipeline (no Qt)."""

import os
import sys
import tempfile
import unittest

from src.plot_editor import document
from src.plot_editor.document import PlotDocumentError
from src.plot_editor.export import (EXPORT_FORMATS, RASTER_DPI,
                                    document_from_plot, export_plot,
                                    with_suffix)
from src.plot_editor.plot_data import Series


def series(xs, ys, label='L', xl='X', yl='Y'):
    return Series(tuple(xs), tuple(ys), label, xl, yl)


ONE = [series([0, 1, 2], [1, 4, 2], 'L', 'XL', 'YL')]
THREE = [series([0, 1], [1, 4], 'A'),
         series([0, 1], [5, 7], 'B'),
         series([0, 1], [0, 1], 'C')]


class WithSuffixTests(unittest.TestCase):

    def test_adds_suffixes(self):
        self.assertEqual(with_suffix('a', 'pdf'), 'a.pdf')
        self.assertEqual(with_suffix('a', 'svg'), 'a.svg')
        self.assertEqual(with_suffix('a', 'png'), 'a.png')
        self.assertEqual(with_suffix('a', 'tiff'), 'a.tif')
        self.assertEqual(with_suffix('a', 'jpg'), 'a.jpg')
        self.assertEqual(with_suffix('a', 'ilmplot'), 'a.ilmplot.svg')

    def test_keeps_accepted_case_insensitive(self):
        self.assertEqual(with_suffix('a.TIFF', 'tiff'), 'a.TIFF')
        self.assertEqual(with_suffix('a.jpeg', 'jpg'), 'a.jpeg')
        self.assertEqual(with_suffix('a.ilmplot.svg', 'ilmplot'),
                         'a.ilmplot.svg')
        self.assertEqual(with_suffix('a.PDF', 'pdf'), 'a.PDF')

    def test_ilmplot_strips_plain_svg(self):
        self.assertEqual(with_suffix('a.svg', 'ilmplot'), 'a.ilmplot.svg')


class DocumentFromPlotTests(unittest.TestCase):

    def test_style_map(self):
        expected = {'pure_line': ('-', ''),
                    'pure_scatters': ('', 'o'),
                    'line_scatters': ('-', 'o'),
                    'stacked_line': ('-', '')}
        for key, (ls, mk) in expected.items():
            doc = document_from_plot(ONE, key)
            self.assertEqual(doc.series[0].linestyle, ls, key)
            self.assertEqual(doc.series[0].marker, mk, key)

    def test_stacked_bakes_offsets(self):
        doc = document_from_plot(THREE, 'stacked_line')
        self.assertEqual(doc.series[0].y, [1, 4])
        self.assertEqual(doc.series[1].y, [4, 6])
        self.assertEqual(doc.series[2].y, [6, 7])

    def test_colors_labels_legend(self):
        from matplotlib.colors import to_hex
        doc = document_from_plot(THREE, 'pure_line')
        self.assertEqual(doc.series[0].color, to_hex('C0'))
        self.assertEqual(doc.series[1].color, to_hex('C1'))
        self.assertTrue(doc.legend)
        self.assertEqual(doc.xlabel, 'X')
        doc = document_from_plot(ONE, 'pure_line')
        self.assertFalse(doc.legend)

    def test_ids_and_geometry(self):
        doc = document_from_plot(THREE, 'pure_line')
        self.assertEqual([s.id for s in doc.series],
                         ['s0', 's1', 's2'])
        self.assertEqual(doc.series[0].linewidth_pt, 1.5)
        self.assertEqual(doc.series[0].markersize_pt, 6.0)

    def test_too_many_series_raises(self):
        many = [series([0, 1], [0, 1], 's%d' % i) for i in range(101)]
        with self.assertRaises(PlotDocumentError):
            document_from_plot(many, 'pure_line')

    def test_title(self):
        doc = document_from_plot(ONE, 'pure_line', title='Results')
        self.assertEqual(doc.title, 'Results')
        self.assertEqual(document_from_plot(ONE, 'pure_line').title, '')

    def test_unknown_key_raises(self):
        with self.assertRaises(ValueError):
            document_from_plot(ONE, 'nope')

    def test_x_tick_labels_set(self):
        cat = Series((1.0, 2.0), (3.0, 4.0), 'L', 'X', 'Y',
                     ('a', 'b'))
        doc = document_from_plot([cat], 'pure_line')
        self.assertEqual(doc.x_tick_labels, [[1.0, 'a'], [2.0, 'b']])
        self.assertIsNone(document_from_plot(ONE, 'pure_line')
                          .x_tick_labels)


class ExportPlotTests(unittest.TestCase):

    def test_writes_all_formats(self):
        with tempfile.TemporaryDirectory() as d:
            for key in EXPORT_FORMATS:
                path = os.path.join(d, 'plot' + EXPORT_FORMATS[key][1])
                export_plot(document_from_plot(ONE, 'pure_line',
                                               title='Ttl'),
                            path, key)
                self.assertTrue(os.path.isfile(path), key)
                with open(path, 'rb') as fh:
                    head = fh.read(20)
                if key == 'ilmplot':
                    doc = document.load_document(path)
                    self.assertEqual(doc.series[0].x, [0.0, 1.0, 2.0])
                    self.assertEqual(doc.series[0].y, [1.0, 4.0, 2.0])
                    self.assertEqual(doc.series[0].linestyle, '-')
                    self.assertEqual(doc.series[0].marker, '')
                elif key == 'svg':
                    self.assertTrue(head.startswith(b'<?xml'))
                    with open(path, 'rb') as fh:
                        data = fh.read()
                    self.assertNotIn(b'ilm-plot-document', data)
                    self.assertIn(b'Ttl', data)  # styled/native render
                elif key == 'pdf':
                    self.assertTrue(head.startswith(b'%PDF'))
                elif key == 'png':
                    self.assertTrue(head.startswith(b'\x89PNG'))
                elif key == 'tiff':
                    self.assertTrue(head[:4] in (b'II*\x00', b'MM\x00*'))
                elif key == 'jpg':
                    self.assertTrue(head.startswith(b'\xff\xd8'))
            leftovers = [f for f in os.listdir(d) if f.endswith('.tmp')]
            self.assertEqual(leftovers, [])

    def test_png_dpi(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'plot.png')
            export_plot(document_from_plot(ONE, 'pure_line'),
                        path, 'png')
            with open(path, 'rb') as fh:
                data = fh.read(24)
            width = int.from_bytes(data[16:20], 'big')
            # Native figure size: document width_mm (90 mm) at RASTER_DPI.
            self.assertAlmostEqual(width, 90.0 / 25.4 * RASTER_DPI,
                                   delta=2)

    def test_scatter_marker_in_document(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'plot.ilmplot.svg')
            export_plot(document_from_plot(ONE, 'line_scatters'),
                        path, 'ilmplot')
            doc = document.load_document(path)
            self.assertEqual(doc.series[0].linestyle, '-')
            self.assertEqual(doc.series[0].marker, 'o')

    def test_failed_write_raises_and_cleans_up(self):
        with tempfile.TemporaryDirectory() as d:
            blocker = os.path.join(d, 'blocker')
            with open(blocker, 'wb') as fh:
                fh.write(b'x')
            path = os.path.join(blocker, 'plot.png')
            with self.assertRaises(OSError):
                export_plot(document_from_plot(ONE, 'pure_line'),
                            path, 'png')
            self.assertFalse(os.path.exists(path))
            leftovers = [f for f in os.listdir(d) if f.endswith('.tmp')]
            self.assertEqual(leftovers, [])

    def test_no_pyplot_imported(self):
        self.assertNotIn('matplotlib.pyplot', sys.modules)


if __name__ == '__main__':
    unittest.main()
