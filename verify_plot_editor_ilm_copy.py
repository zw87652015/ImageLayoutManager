"""Non-UI checks for the ILM → Plot Editor copy hand-off (no Qt)."""

import os
import sys
import tempfile
import unittest
from unittest.mock import patch

from src.plot_editor.document import PlotDocument
from src.plot_editor.ilm_bridge import (_is_default_document,
                                        copy_ilm_source, is_ilm_copy_path,
                                        is_ilm_store_file, write_ilm_copy)
from src.plot_editor.plot_file import load_plot_file


class DefaultDocumentTests(unittest.TestCase):

    def test_plain_default(self):
        self.assertTrue(_is_default_document(PlotDocument()))

    def test_default_with_changed_size_and_ids(self):
        doc = PlotDocument()
        doc.width_mm = 120.0
        doc.height_mm = 80.0
        doc.series[0].id = 'abc123'
        doc.validate()
        self.assertTrue(_is_default_document(doc))

    def test_not_default(self):
        for mutate in (
                lambda d: setattr(d.series[0], 'label', 'other'),
                lambda d: setattr(d.series[0], 'y', [9., 8., 7., 6.]),
                lambda d: setattr(d, 'title', 'T')):
            doc = PlotDocument()
            mutate(doc)
            doc.validate()
            self.assertFalse(_is_default_document(doc))

    def test_not_a_document(self):
        self.assertFalse(_is_default_document(object()))
        self.assertFalse(_is_default_document(None))


class IlmCopyPathTests(unittest.TestCase):

    def test_inside_subdir(self):
        sub = os.path.join(tempfile.gettempdir(), 'ilm-plot-editor')
        self.assertTrue(is_ilm_copy_path(
            os.path.join(sub, 'x.ilmplot.svg')))

    def test_outside_rejected(self):
        sub = os.path.join(tempfile.gettempdir(), 'ilm-plot-editor')
        self.assertFalse(is_ilm_copy_path(
            os.path.join(tempfile.gettempdir(), 'x.ilmplot.svg')))
        self.assertFalse(is_ilm_copy_path(
            os.path.join(sub, 'sub', 'x.ilmplot.svg')))
        self.assertFalse(is_ilm_copy_path(
            os.path.join(sub, '..', 'x.ilmplot.svg')))
        self.assertFalse(is_ilm_copy_path('x.ilmplot.svg'))


class StoreFileTests(unittest.TestCase):

    def test_inside_store_root(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'plot-abc.ilmplot.svg')
            with open(path, 'wb') as fh:
                fh.write(b'<svg/>')
            with patch('src.utils.editable_plot.plot_documents_root',
                       return_value=d):
                self.assertTrue(is_ilm_store_file(path))
                self.assertFalse(is_ilm_store_file(
                    os.path.join(tempfile.gettempdir(), 'x.svg')))

    def test_root_lookup_failure_defaults_true(self):
        with patch('src.utils.editable_plot.plot_documents_root',
                   side_effect=OSError('nope')):
            self.assertTrue(is_ilm_store_file('anywhere.svg'))


class WriteIlmCopyTests(unittest.TestCase):

    def test_writes_loadable_file_in_temp_subdir(self):
        doc = PlotDocument()
        doc.title = 'Handed off'
        doc.validate()
        path = write_ilm_copy(doc)
        try:
            self.assertTrue(is_ilm_copy_path(path))
            pf = load_plot_file(path)
            self.assertEqual(pf.document.to_dict(), doc.to_dict())
            self.assertFalse(pf.has_worksheet)
        finally:
            os.unlink(path)

    def test_copy_ilm_source_preserves_worksheet_node(self):
        from src.plot_editor.export import document_from_plot
        from src.plot_editor.plot_data import Series
        from src.plot_editor.plot_file import save_plot_file
        from src.plot_editor.worksheet import Worksheet
        ws = Worksheet()
        ws.column(0).long_name = 'Time'
        ws.column(0).units = 's'
        doc = document_from_plot(
            [Series((0., 1.), (0., 1.), 'L', 'Time (s)', 'Signal (V)')],
            'pure_line')
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, 'cell.ilmplot.svg')
            save_plot_file(src, doc, ws, 'pure_line', (0, 1))
            with open(src, 'rb') as fh:
                raw = fh.read()
            tmp = copy_ilm_source(src)
            try:
                self.assertTrue(is_ilm_copy_path(tmp))
                with open(tmp, 'rb') as fh:
                    self.assertEqual(fh.read(), raw)
                pf = load_plot_file(tmp)
                self.assertTrue(pf.has_worksheet)
                self.assertEqual(pf.worksheet.column(0).units, 's')
            finally:
                os.unlink(tmp)

    def test_no_pyplot_imported(self):
        self.assertNotIn('matplotlib.pyplot', sys.modules)


if __name__ == '__main__':
    unittest.main()
