"""Unit tests for ilmplot "error as band" (LineSeries.error_style).

Runs standalone: ``python -m unittest discover -s tests`` from the
package root with ``packages/ilmplot/src`` on PYTHONPATH.
"""

import unittest

import matplotlib
matplotlib.use('Agg')
import numpy as np                       # noqa: E402

from ilmplot import document             # noqa: E402
from ilmplot.document import (           # noqa: E402
    AxisStyle, Band, LineSeries, PlotDocument, PlotDocumentError,
    PlotVersionError, PlotStyle, required_capabilities)
from ilmplot.render import render_document  # noqa: E402


def err_doc(style='bars', alpha=0.3, yerr=True):
    doc = PlotDocument()
    s = LineSeries(x=[0., 1., 2., 3.], y=[1., 2., 1., 2.],
                   label='m')
    if yerr:
        s.yerr = [0.2, 0.4, 0.3, 0.5]
    s.error_style = style
    s.error_alpha = alpha
    doc.series = [s]
    return doc.validate()


class TestErrorBandSchema(unittest.TestCase):
    def test_round_trip(self):
        doc = err_doc('band', 0.5)
        doc2 = PlotDocument.from_dict(doc.to_dict())
        s = doc2.series[0]
        self.assertEqual(s.error_style, 'band')
        self.assertEqual(s.error_alpha, 0.5)

    def test_omission_rules(self):
        d = err_doc('bars', 0.5).to_dict()
        self.assertNotIn('error_style', d['series'][0])
        self.assertNotIn('error_alpha', d['series'][0])
        d = err_doc('band', 0.3).to_dict()['series'][0]
        self.assertEqual(d['error_style'], 'band')
        self.assertNotIn('error_alpha', d)
        d = err_doc('band', 0.8).to_dict()['series'][0]
        self.assertEqual(d['error_alpha'], 0.8)

    def test_requires_combinations(self):
        self.assertEqual(required_capabilities(err_doc('band')),
                         ['error_band'])
        doc = err_doc('band')
        doc.bands = [Band(x=[0., 1.], y1=[0., 0.], y2=[1., 1.])]
        doc.validate()
        self.assertEqual(required_capabilities(doc),
                         ['bands', 'error_band'])
        self.assertEqual(doc.to_dict()['requires'],
                         ['bands', 'error_band'])
        self.assertEqual(required_capabilities(err_doc('bars')), [])

    def test_invalid_values_rejected(self):
        for style, alpha in (('fill', 0.3), ('band', 0.0),
                             ('band', 1.5), ('band', float('nan'))):
            s = err_doc('band').series[0]
            d = s.to_dict()
            d['error_style'] = style
            d['error_alpha'] = alpha
            with self.assertRaises(PlotDocumentError, msg=(style, alpha)):
                LineSeries.from_dict(d)

    def test_band_without_yerr_valid(self):
        doc = err_doc('band', yerr=False)
        doc.validate()
        self.assertEqual(doc.series[0].error_style, 'band')

    def test_missing_capability_rejected(self):
        d = err_doc('band').to_dict()
        saved = document.CAPABILITIES
        try:
            document.CAPABILITIES = frozenset()
            with self.assertRaises(PlotVersionError):
                PlotDocument.from_dict(d)
        finally:
            document.CAPABILITIES = saved


def _series_poly(fig_ax, sid):
    fig, ax = fig_ax
    polys = [p for p in ax.patches
             if p.get_gid() == 'ilmplot-series-' + sid]
    return polys[0] if polys else None


class TestErrorBandRender(unittest.TestCase):
    def _build(self, doc):
        from ilmplot.render import _build_figure
        return _build_figure(doc, 1.0, doc.width_mm, doc.height_mm)

    def test_band_drawn_no_bar_collection(self):
        doc = err_doc('band')
        fig, ax = self._build(doc)
        self.assertEqual(len(ax.collections), 0)
        poly = _series_poly((fig, ax), doc.series[0].id)
        self.assertIsNotNone(poly)
        svg = render_document(doc).svg.decode('utf-8')
        self.assertIn('ilmplot-series-' + doc.series[0].id, svg)

    def test_bars_style_unchanged(self):
        doc = err_doc('bars')
        fig, ax = self._build(doc)
        self.assertIsNone(_series_poly((fig, ax), doc.series[0].id))
        self.assertEqual(len(ax.collections), 1)   # error-bar LineCollection

    def test_pinned_ylim_clips(self):
        doc = err_doc('band')
        doc.xlim = [0., 3.]
        doc.ylim = [0.5, 2.5]
        fig, ax = self._build(doc)
        poly = _series_poly((fig, ax), doc.series[0].id)
        xy = np.asarray(poly.get_xy(), dtype=float)
        self.assertTrue((xy[:, 1] >= 0.5 - 1e-9).all()
                        and (xy[:, 1] <= 2.5 + 1e-9).all())

    def test_log_y_lower_bound(self):
        doc = err_doc('band')
        doc.series[0].yerr = [5.0] * 4   # y - err <= 0 everywhere
        st = PlotStyle()
        st.yaxis = AxisStyle(scale='log')
        doc.style = st
        fig, ax = self._build(doc)
        poly = _series_poly((fig, ax), doc.series[0].id)
        ys = np.asarray(poly.get_xy())[:, 1]
        self.assertAlmostEqual(min(ys), min(doc.series[0].y) / 10.0)

    def test_alpha_multiplies(self):
        doc = err_doc('band', 0.5)
        doc.series[0].color = '#ff0000'
        fig, ax = self._build(doc)
        poly = _series_poly((fig, ax), doc.series[0].id)
        self.assertAlmostEqual(poly.get_facecolor()[3], 0.5)
        doc = err_doc('band', 0.5)
        doc.series[0].color = '#ff000066'   # alpha 0.4
        fig, ax = self._build(doc)
        poly = _series_poly((fig, ax), doc.series[0].id)
        self.assertAlmostEqual(poly.get_facecolor()[3], 0.4 * 0.5,
                               places=6)


if __name__ == '__main__':
    unittest.main()
