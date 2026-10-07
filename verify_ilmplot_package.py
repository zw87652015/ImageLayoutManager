"""Non-UI verification for the ilmplot package move and bridge.

Run from the repo root: ``python -m unittest verify_ilmplot_package``.
"""

import json
import os
import sys
import tempfile
import unittest

import src  # noqa: F401  -- puts packages/ilmplot/src on sys.path

import ilmplot.document
import ilmplot.render
import ilmplot.stats
import ilmplot.mathtext
import ilmplot.bridge


ROOT = os.path.dirname(os.path.abspath(__file__))


class AliasTests(unittest.TestCase):

    def test_document_alias(self):
        import src.plot_editor.document as alias
        self.assertIs(alias, ilmplot.document)

    def test_render_alias(self):
        import src.plot_editor.render as alias
        self.assertIs(alias, ilmplot.render)

    def test_stats_alias(self):
        import src.plot_editor.stats as alias
        self.assertIs(alias, ilmplot.stats)

    def test_mathtext_alias(self):
        import src.plot_editor.mathtext as alias
        self.assertIs(alias, ilmplot.mathtext)

    def test_matplotlib_bridge_alias(self):
        import src.plot_editor.matplotlib_bridge as alias
        self.assertIs(alias, ilmplot.bridge)

    def test_private_names_reachable(self):
        import src.plot_editor.document as d
        import src.plot_editor.render as r
        self.assertTrue(callable(d._err))
        self.assertTrue(callable(r._register_namespaces))
        self.assertTrue(callable(r._canonical))


class BootstrapTests(unittest.TestCase):

    def test_in_repo_ilmplot_path_is_first(self):
        import subprocess
        probe = subprocess.check_output(
            [sys.executable, '-c',
             'import sys; sys.path.insert(0, %r); import src; '
             'print(sys.path[0])' % ROOT], text=True).strip()
        self.assertEqual(
            os.path.normcase(os.path.normpath(probe)),
            os.path.normcase(os.path.normpath(
                os.path.join(ROOT, 'packages', 'ilmplot', 'src'))))

    def test_ilmplot_importable_from_repo(self):
        self.assertTrue(ilmplot.__version__)


class BridgeIntegrationTests(unittest.TestCase):

    def test_bridge_output_is_loadable(self):
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        from src.utils.editable_plot import plot_is_loadable
        fig, ax = plt.subplots()
        ax.plot([0, 1, 2], [1, 4, 2], label='a')
        ax.legend()
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'a.ilmplot.svg')
            result = ilmplot.savefig(fig, path)
            self.assertTrue(result.native)
            self.assertTrue(plot_is_loadable(path))
        plt.close(fig)

    def _band_figure(self):
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots()
        ax.plot([0, 1, 2, 3], [1, 2, 1, 2], label='m')
        ax.fill_between([0, 1, 2, 3], [0, 1, 0, 1], [2, 3, 2, 3],
                        alpha=0.3, label='ci')
        return fig, plt

    def test_bridge_band_output_is_loadable(self):
        from src.utils.editable_plot import plot_is_loadable
        fig, plt = self._band_figure()
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'band.ilmplot.svg')
            result = ilmplot.savefig(fig, path)
            plt.close(fig)
            self.assertTrue(result.native)
            self.assertTrue(plot_is_loadable(path))
            with open(path, 'rb') as fh:
                doc = ilmplot.document.document_from_svg(fh.read())
            self.assertEqual(len(doc.bands), 1)
            self.assertEqual(doc.to_dict()['requires'], ['bands'])

    def test_band_editor_round_trip_without_qt(self):
        from src.plot_editor import plot_file
        from src.plot_editor.overrides import (
            effective_document, overrides_from_document)
        from src.utils.editable_plot import plot_is_loadable
        fig, plt = self._band_figure()
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'band.ilmplot.svg')
            result = ilmplot.savefig(fig, path)
            plt.close(fig)
            self.assertTrue(result.native)
            self.assertTrue(plot_is_loadable(path))
            pf = plot_file.load_plot_file(path)
            items = plot_file.series_from_document(pf.document)
            ov = overrides_from_document(pf.document)
            self.assertTrue(ov.bands)
            doc = effective_document(
                pf.document, items, pf.chart_key or 'pure_line',
                pf.document.title, ov)
            expected = [b.to_dict() for b in pf.document.bands]
            self.assertEqual([b.to_dict() for b in doc.bands], expected)
            out = os.path.join(d, 'saved.ilmplot.svg')
            plot_file.save_plot_file(
                out, doc, pf.worksheet, pf.chart_key or 'pure_line',
                pf.plot_columns, ov)
            pf2 = plot_file.load_plot_file(out)
            self.assertTrue(pf2.has_worksheet)
            self.assertTrue(pf2.overrides.bands)
            # Regenerated-document path (legacy_base=False) keeps bands.
            doc2 = effective_document(
                None, items, 'pure_line', pf.document.title,
                pf2.overrides)
            self.assertEqual([b.to_dict() for b in doc2.bands],
                             expected)
            payload = plot_file.worksheet_to_dict(
                pf2.worksheet, 'pure_line', pf2.plot_columns,
                pf2.overrides, for_save=True)
            self.assertIn('bands', payload['requires'])

    def test_zh_translation_reaches_plot_version_error(self):
        from src.plot_editor import i18n
        from ilmplot.document import PlotVersionError
        payload = {'format': 'ilm-plot', 'schema_version': 99}
        svg = (b'<svg xmlns="http://www.w3.org/2000/svg">'
               b'<metadata id="ilm-plot-document">'
               + json.dumps(payload).encode('utf-8')
               + b'</metadata></svg>')
        i18n.set_language('zh')
        try:
            with self.assertRaises(PlotVersionError) as cm:
                ilmplot.document.document_from_svg(svg)
            self.assertNotIn('newer version of the Plot Editor',
                             str(cm.exception))
            self.assertTrue(str(cm.exception).strip())
        finally:
            i18n.set_language('en')


if __name__ == '__main__':
    unittest.main()
