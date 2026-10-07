"""Unit tests for ilmplot shaded bands (fill_between/stackplot).

Runs standalone: ``python -m unittest discover -s tests`` from the
package root with ``packages/ilmplot/src`` on PYTHONPATH.
"""

import os
import tempfile
import unittest

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt          # noqa: E402
import numpy as np                       # noqa: E402

import ilmplot                           # noqa: E402
from ilmplot import bridge               # noqa: E402
from ilmplot import document             # noqa: E402
from ilmplot.document import (           # noqa: E402
    MAX_BANDS, Band, LineSeries, PlotDocument, PlotDocumentError,
    PlotVersionError, document_from_svg, required_capabilities)
from ilmplot.render import render_document  # noqa: E402


def band_doc(**kw):
    doc = PlotDocument()
    doc.series = [LineSeries(x=[0, 1, 2, 3], y=[1, 2, 1, 2],
                             label='line')]
    doc.bands = [Band(label=kw.pop('label', 'band'),
                      x=[0., 1., 2., 3.],
                      y1=[0., 1., 0., 1.],
                      y2=[2., 3., 2., 3.],
                      **kw)]
    return doc.validate()


class TestBandSchema(unittest.TestCase):
    def test_round_trip(self):
        doc = band_doc()
        d = doc.to_dict()
        self.assertIn('bands', d)
        doc2 = PlotDocument.from_dict(d)
        self.assertEqual(len(doc2.bands), 1)
        b = doc2.bands[0]
        self.assertEqual(b.x, [0., 1., 2., 3.])
        self.assertEqual(b.y1, [0., 1., 0., 1.])
        self.assertEqual(b.y2, [2., 3., 2., 3.])
        self.assertEqual(b.color, '#1f77b44d')
        self.assertEqual(b.label, 'band')

    def test_requires_stamped(self):
        self.assertEqual(required_capabilities(band_doc()), ['bands'])
        self.assertEqual(band_doc().to_dict()['requires'], ['bands'])

    def test_no_band_no_keys(self):
        doc = PlotDocument()
        doc.series = [LineSeries(x=[0, 1], y=[0, 1])]
        doc.validate()
        d = doc.to_dict()
        self.assertNotIn('bands', d)
        self.assertNotIn('requires', d)

    def test_length_mismatch_rejected(self):
        b = Band(x=[0., 1., 2.], y1=[0., 1.], y2=[1., 2.])
        with self.assertRaises(PlotDocumentError):
            Band.from_dict(b.to_dict())
        doc = band_doc()
        doc.bands[0].y1 = [0., 1.]
        with self.assertRaises(PlotDocumentError):
            doc.validate()

    def test_nan_rejected(self):
        b = Band(x=[0., float('nan')], y1=[0., 1.], y2=[1., 2.])
        with self.assertRaises(PlotDocumentError):
            Band.from_dict(b.to_dict())

    def test_too_few_points_rejected(self):
        b = Band(x=[0.], y1=[0.], y2=[1.])
        with self.assertRaises(PlotDocumentError):
            Band.from_dict(b.to_dict())

    def test_duplicate_x_allowed(self):
        b = Band(x=[0., 0.5, 0.5, 1.], y1=[0., 0., 1., 1.],
                 y2=[1., 1., 2., 2.])
        Band.from_dict(b.to_dict())   # step bands share x values

    def test_bands_on_other_kinds_rejected(self):
        for kind in ('violin', 'stacked_column'):
            doc = PlotDocument(kind=kind)
            if kind == 'violin':
                from ilmplot.document import ViolinGroup
                doc.series = []
                doc.groups = [ViolinGroup(values=[1., 2.])]
            else:
                from ilmplot.document import StackCategory
                doc.series = []
                doc.categories = [StackCategory(values=[1., 2.])]
            doc.bands = [Band()]
            with self.assertRaises(PlotDocumentError):
                doc.validate()

    def test_max_bands(self):
        doc = band_doc()
        doc.bands = [Band() for _ in range(MAX_BANDS + 1)]
        with self.assertRaises(PlotDocumentError):
            doc.validate()

    def test_duplicate_band_ids_rejected(self):
        doc = band_doc()
        doc.bands.append(Band(id=doc.bands[0].id))
        with self.assertRaises(PlotDocumentError):
            doc.validate()

    def test_band_only_document_rejected(self):
        doc = PlotDocument()
        doc.series = []
        doc.bands = [Band()]
        with self.assertRaises(PlotDocumentError):
            doc.validate()
        with self.assertRaises(PlotDocumentError):
            PlotDocument.from_dict(doc.to_dict())

    def test_missing_capability_rejected(self):
        d = band_doc().to_dict()
        saved = document.CAPABILITIES
        try:
            document.CAPABILITIES = frozenset()
            with self.assertRaises(PlotVersionError):
                PlotDocument.from_dict(d)
        finally:
            document.CAPABILITIES = saved


class TestBandRender(unittest.TestCase):
    def test_band_drawn_before_series(self):
        doc = band_doc()
        svg = render_document(doc).svg.decode('utf-8')
        bi = svg.index('ilmplot-band-' + doc.bands[0].id)
        si = svg.index('ilmplot-series-' + doc.series[0].id)
        self.assertLess(bi, si)

    def test_band_label_in_legend(self):
        svg = render_document(band_doc(label='95% CI')).svg.decode(
            'utf-8')
        self.assertIn('95% CI', svg)

    def test_band_clipped_to_pinned_view(self):
        from ilmplot.render import _build_figure
        doc = band_doc()
        doc.xlim = [0., 3.]
        doc.ylim = [0.5, 2.5]   # band y1 reaches 0, y2 reaches 3
        fig, ax = _build_figure(doc, 1.0, doc.width_mm, doc.height_mm)
        polys = [p for p in ax.patches
                 if p.get_gid() == 'ilmplot-band-' + doc.bands[0].id]
        self.assertEqual(len(polys), 1)
        xy = np.asarray(polys[0].get_xy(), dtype=float)
        self.assertTrue((xy[:, 0] >= -1e-9).all()
                        and (xy[:, 0] <= 3 + 1e-9).all())
        self.assertTrue((xy[:, 1] >= 0.5 - 1e-9).all()
                        and (xy[:, 1] <= 2.5 + 1e-9).all())

    def test_no_band_render_unchanged_shape(self):
        svg = render_document(PlotDocument()).svg
        self.assertIn(b'ilm-plot-document', svg)
        self.assertNotIn(b'ilmplot-band-', svg)


class TestBandBridge(unittest.TestCase):
    def test_alpha_band_exact(self):
        fig, ax = plt.subplots(figsize=(4, 3))
        ax.plot([0, 1, 2, 3], [1, 2, 1, 2], label='m')
        ax.fill_between([0, 1, 2, 3], [0, 1, 0, 1], [2, 3, 2, 3],
                        alpha=0.3, label='ci')
        r = bridge.convert(fig)
        plt.close(fig)
        self.assertFalse(r.reasons, r.reasons)
        doc = r.document
        self.assertEqual(len(doc.bands), 1)
        b = doc.bands[0]
        self.assertEqual(b.x, [0., 1., 2., 3.])
        self.assertEqual(b.y1, [0., 1., 0., 1.])
        self.assertEqual(b.y2, [2., 3., 2., 3.])
        self.assertEqual(b.color, '#1f77b44d')
        self.assertEqual(b.label, 'ci')
        self.assertEqual(len(doc.series), 1)
        doc.validate()

    def test_where_split(self):
        fig, ax = plt.subplots(figsize=(4, 3))
        ax.plot([0, 1, 2, 3, 4], [1, 2, 1, 2, 1])
        ax.fill_between([0, 1, 2, 3, 4], [0] * 5, [1, 2, 1, 2, 1],
                        where=[True, True, False, True, True],
                        label='seg')
        r = bridge.convert(fig)
        plt.close(fig)
        self.assertFalse(r.reasons, r.reasons)
        self.assertEqual(len(r.document.bands), 2)
        self.assertEqual(r.document.bands[0].label, 'seg')
        self.assertEqual(r.document.bands[1].label, '')
        self.assertEqual(r.document.bands[0].color,
                         r.document.bands[1].color)

    def test_step_mid_native(self):
        fig, ax = plt.subplots(figsize=(4, 3))
        ax.plot([0, 1, 2], [0.5, 1.5, 0.5])
        ax.fill_between([0, 1, 2], [0, 1, 0], [1, 2, 1], step='mid')
        r = bridge.convert(fig)
        plt.close(fig)
        self.assertFalse(r.reasons, r.reasons)
        b = r.document.bands[0]
        # step='mid' inserts duplicated boundary x values
        self.assertIn(0.5, b.x)
        self.assertEqual(b.x.count(0.5), 2)

    def test_fill_betweenx_reason(self):
        fig, ax = plt.subplots(figsize=(4, 3))
        ax.plot([0, 1, 2], [0, 1, 0])
        ax.fill_betweenx([0, 1, 2], 0, 1)
        r = bridge.convert(fig)
        plt.close(fig)
        self.assertTrue(any('fill_betweenx' in s for s in r.reasons),
                        r.reasons)
        self.assertIsNone(r.document)

    def test_stackplot_with_line_native(self):
        fig, ax = plt.subplots(figsize=(4, 3))
        ax.plot([0, 1, 2], [1, 2, 1], label='m')
        ax.stackplot([0, 1, 2], [1, 2, 1], [0, 1, 0])
        r = bridge.convert(fig)
        plt.close(fig)
        self.assertFalse(r.reasons, r.reasons)
        self.assertEqual(len(r.document.bands), 2)
        self.assertEqual(r.document.bands[1].y1,
                         r.document.bands[0].y2)

    def test_bare_stackplot_reason(self):
        fig, ax = plt.subplots(figsize=(4, 3))
        ax.stackplot([0, 1, 2], [1, 2, 1], [0, 1, 0])
        r = bridge.convert(fig)
        plt.close(fig)
        self.assertTrue(any(
            'bands need at least one line or scatter series' in s
            for s in r.reasons), r.reasons)
        self.assertIsNone(r.document)

    def test_distinct_edge_note(self):
        fig, ax = plt.subplots(figsize=(4, 3))
        ax.plot([0, 1], [0, 1])
        ax.fill_between([0, 1], [0, 0], [1, 1], edgecolor='red',
                        linewidth=1.5)
        r = bridge.convert(fig)
        plt.close(fig)
        self.assertFalse(r.reasons, r.reasons)
        self.assertTrue(any('band outlines dropped' in s
                            for s in r.notes), r.notes)

    def test_histogram_reason(self):
        rng = np.random.default_rng(0)
        fig, ax = plt.subplots(figsize=(4, 3))
        ax.hist(rng.normal(size=500), bins=30)
        r = bridge.convert(fig)
        plt.close(fig)
        self.assertTrue(any(
            'histogram-style bars (touching bars on a numeric axis) '
            'are not supported' in s for s in r.reasons), r.reasons)
        self.assertIsNone(r.document)

    def test_categorical_bars_native(self):
        fig, ax = plt.subplots(figsize=(4, 3))
        ax.bar(['A', 'B', 'C'], [1, 2, 3], width=0.8)
        r = bridge.convert(fig)
        plt.close(fig)
        self.assertFalse(r.reasons, r.reasons)
        self.assertEqual(r.document.kind, 'stacked_column')

    def test_numeric_bars_width_08_native(self):
        fig, ax = plt.subplots(figsize=(4, 3))
        ax.bar([1, 2, 3], [1, 2, 3], width=0.8)
        r = bridge.convert(fig)
        plt.close(fig)
        self.assertFalse(r.reasons, r.reasons)

    def test_bars_with_band_reason(self):
        fig, ax = plt.subplots(figsize=(4, 3))
        ax.bar(['A', 'B'], [1, 2], width=0.8)
        ax.fill_between([0, 1], [0, 0], [1, 1])
        r = bridge.convert(fig)
        plt.close(fig)
        self.assertTrue(r.reasons)

    def test_savefig_band_loads(self):
        fig, ax = plt.subplots(figsize=(4, 3))
        ax.plot([0, 1, 2, 3], [1, 2, 1, 2], label='m')
        ax.fill_between([0, 1, 2, 3], [0, 1, 0, 1], [2, 3, 2, 3],
                        alpha=0.3, label='ci')
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, 'band.ilmplot.svg')
            res = bridge.savefig(fig, path)
            plt.close(fig)
            self.assertTrue(res.native)
            with open(path, 'rb') as fh:
                doc = document_from_svg(fh.read())
            self.assertEqual(len(doc.bands), 1)
            self.assertEqual(doc.bands[0].label, 'ci')
            self.assertEqual(doc.to_dict()['requires'], ['bands'])


if __name__ == '__main__':
    unittest.main()
