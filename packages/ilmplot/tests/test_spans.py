"""Span (axvspan/axhspan) document model, rendering and bridge tests."""
import unittest

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from ilmplot.document import (MAX_SPANS, Band, LineSeries, PlotDocument,
                              PlotDocumentError, PlotVersionError, Span)
from ilmplot import document as docmod
from ilmplot.bridge import convert, savefig
from ilmplot.document import document_from_svg
from ilmplot.render import element_regions, render_document


def _doc(**kw):
    d = PlotDocument(kind='line')
    d.series = [LineSeries(id='s1', label='S1',
                           x=[0.0, 1.0, 2.0], y=[0.0, 1.0, 0.0])]
    for k, v in kw.items():
        setattr(d, k, v)
    return d


def _span(**kw):
    base = dict(id='sp1', axis='x', lo=0.5, hi=1.5,
                color='#7f7f7f40', label='')
    base.update(kw)
    return Span(**base)


class ModelTests(unittest.TestCase):

    def test_round_trip_and_requires(self):
        doc = _doc(spans=[_span(label='shade')])
        d = doc.to_dict()
        self.assertEqual(d['requires'], ['spans'])
        back = PlotDocument.from_dict(d)
        self.assertEqual(len(back.spans), 1)
        self.assertEqual(back.spans[0].axis, 'x')
        self.assertEqual(back.spans[0].lo, 0.5)

    def test_no_spans_no_keys(self):
        d = _doc().to_dict()
        self.assertNotIn('spans', d)
        self.assertNotIn('requires', d)

    def test_both_requires_sorted(self):
        doc = _doc(spans=[_span()],
                   bands=[Band(id='b1', x=[0, 1], y1=[0, 0],
                               y2=[1, 1])])
        self.assertEqual(doc.to_dict()['requires'],
                         ['bands', 'spans'])

    def test_lo_ge_hi_rejected(self):
        sp = _span(lo=1.0, hi=0.5)
        with self.assertRaises(PlotDocumentError):
            Span.from_dict(sp.to_dict())
        sp = _span(lo=1.0, hi=1.0)
        with self.assertRaises(PlotDocumentError):
            Span.from_dict(sp.to_dict())

    def test_nan_rejected(self):
        sp = _span(lo=float('nan'))
        with self.assertRaises(PlotDocumentError):
            Span.from_dict(sp.to_dict())

    def test_bad_axis_rejected(self):
        d = _span().to_dict()
        d['axis'] = 'z'
        with self.assertRaises(PlotDocumentError):
            Span.from_dict(d)

    def test_non_line_kind_rejected(self):
        doc = _doc(kind='violin', spans=[_span()])
        doc.series = []
        with self.assertRaises(PlotDocumentError):
            doc.validate()

    def test_max_spans(self):
        doc = _doc(spans=[_span(id=f's{i}') for i in
                          range(MAX_SPANS + 1)])
        with self.assertRaises(PlotDocumentError):
            doc.validate()

    def test_duplicate_ids(self):
        doc = _doc(spans=[_span(id='dup'), _span(id='dup', axis='y')])
        with self.assertRaises(PlotDocumentError):
            doc.validate()

    def test_reader_without_capability(self):
        d = _doc(spans=[_span()]).to_dict()
        saved = docmod.CAPABILITIES
        try:
            docmod.CAPABILITIES = frozenset()
            with self.assertRaises(PlotVersionError):
                PlotDocument.from_dict(d)
        finally:
            docmod.CAPABILITIES = saved


class RenderTests(unittest.TestCase):

    def _svg(self, doc):
        out = render_document(doc)
        return out.svg if isinstance(out.svg, bytes) \
            else out.svg.encode('utf-8')

    def test_gid_and_order(self):
        doc = _doc(spans=[_span()])
        svg = self._svg(doc)
        i_span = svg.find(b'ilmplot-span-sp1')
        i_series = svg.find(b'ilmplot-series-s1')
        self.assertGreater(i_span, 0)
        self.assertGreater(i_series, i_span)

    def test_x_span_full_height(self):
        doc = _doc(spans=[_span()])
        regions = element_regions(doc)
        span = regions['spans']['sp1']
        frame = regions['frame']
        # Full plot height: the region covers the frame's y extent.
        self.assertAlmostEqual(span['bbox'][1], frame[1], places=2)
        self.assertAlmostEqual(span['bbox'][3], frame[3], places=2)
        self.assertTrue(span['points'])

    def test_y_span_full_width(self):
        doc = _doc(spans=[_span(axis='y', lo=0.2, hi=0.8)])
        regions = element_regions(doc)
        span = regions['spans']['sp1']
        frame = regions['frame']
        self.assertAlmostEqual(span['bbox'][0], frame[0], places=2)
        self.assertAlmostEqual(span['bbox'][2], frame[2], places=2)

    def test_clipped_to_pinned_view(self):
        doc = _doc(spans=[_span(lo=-5.0, hi=10.0)], xlim=[0.0, 2.0])
        regions = element_regions(doc)
        frame = regions['frame']
        span = regions['spans']['sp1']
        for fx, fy in span['points']:
            self.assertGreaterEqual(fx, frame[0] - 1e-3)
            self.assertLessEqual(fx, frame[2] + 1e-3)

    def test_hidden_when_outside(self):
        doc = _doc(spans=[_span(lo=100.0, hi=200.0)], xlim=[0.0, 2.0])
        regions = element_regions(doc)
        self.assertNotIn('sp1', regions.get('spans') or {})

    def test_autoscale_includes_span(self):
        plain = element_regions(_doc())
        wide = element_regions(_doc(spans=[_span(lo=5.0, hi=8.0)]))
        span = wide['spans']['sp1']
        frame = wide['frame']
        # The span sits inside the axes and the view grew: the same
        # series (x 0..2) now ends well before the frame's right edge.
        self.assertGreater(span['bbox'][0], frame[0])
        self.assertLess(span['bbox'][2], frame[2] + 1e-3)
        self.assertLess(wide['series']['s1']['bbox'][2],
                        plain['series']['s1']['bbox'][2])
        self.assertNotIn('spans', plain)

    def test_legend_label(self):
        doc = _doc(legend=True, spans=[_span(label='ROI')])
        regions = element_regions(doc)
        self.assertIn('legend', regions)
        svg = self._svg(doc)
        self.assertIn(b'ROI', svg)

    def test_log_y_band_zero_baseline(self):
        # A band reaching y=0 on a log-y axis: no NaN/inf in the SVG,
        # the polygon is clipped to the final view and autoscale stays
        # positive.
        import numpy as np
        from ilmplot.document import AxisStyle, PlotStyle
        from ilmplot.render import _build_figure
        doc = _doc(bands=[Band(id='b1', x=[0.0, 1.0, 2.0],
                               y1=[0.0, 0.0, 0.0],
                               y2=[1.0, 2.0, 1.0])])
        st = PlotStyle()
        st.yaxis = AxisStyle(scale='log')
        doc.style = st
        doc.validate()
        svg = self._svg(doc).decode('utf-8')
        low = svg.lower()
        self.assertNotIn('nan', low)
        self.assertNotIn('inf', low)
        fig, ax = _build_figure(doc, 1.0, doc.width_mm, doc.height_mm)
        lo, hi = ax.get_ylim()
        self.assertGreater(lo, 0.0)
        poly = next(p for p in ax.patches
                    if p.get_gid() == 'ilmplot-band-b1')
        xy = np.asarray(poly.get_xy(), dtype=float)
        self.assertTrue(np.isfinite(xy).all())
        self.assertGreaterEqual(xy[:, 1].min(), lo - 1e-9)
        self.assertLessEqual(xy[:, 1].max(), hi + 1e-9)
        self.assertAlmostEqual(xy[:, 1].min(), lo)

    def test_log_x_band_clipped(self):
        import numpy as np
        from ilmplot.document import AxisStyle, PlotStyle
        from ilmplot.render import _build_figure
        doc = _doc(bands=[Band(id='b1', x=[0.0, 1.0, 2.0],
                               y1=[0.0, 0.0, 0.0],
                               y2=[1.0, 2.0, 1.0])])
        st = PlotStyle()
        st.xaxis = AxisStyle(scale='log')
        doc.style = st
        svg = self._svg(doc).decode('utf-8')
        self.assertNotIn('nan', svg.lower())
        fig, ax = _build_figure(doc, 1.0, doc.width_mm, doc.height_mm)
        lo, hi = ax.get_xlim()
        self.assertGreater(lo, 0.0)
        poly = next(p for p in ax.patches
                    if p.get_gid() == 'ilmplot-band-b1')
        xy = np.asarray(poly.get_xy(), dtype=float)
        self.assertGreaterEqual(xy[:, 0].min(), lo - 1e-9)
        self.assertLessEqual(xy[:, 0].max(), hi + 1e-9)


class BridgeTests(unittest.TestCase):

    def test_axvspan(self):
        fig, ax = plt.subplots()
        ax.plot([0, 1, 2], [0, 1, 0])
        ax.axvspan(0.5, 1.5, color='red', alpha=0.2, label='v')
        r = convert(fig)
        plt.close(fig)
        self.assertEqual(r.reasons, [])
        sp = r.document.spans[0]
        self.assertEqual((sp.axis, sp.lo, sp.hi), ('x', 0.5, 1.5))
        self.assertEqual(sp.color, '#ff000033')
        self.assertEqual(sp.label, 'v')
        self.assertIn('spans', r.document.to_dict()['requires'])

    def test_axhspan(self):
        fig, ax = plt.subplots()
        ax.plot([0, 1, 2], [0, 1, 0])
        ax.axhspan(0.2, 0.8, color='blue', alpha=0.3)
        r = convert(fig)
        plt.close(fig)
        self.assertEqual(r.reasons, [])
        sp = r.document.spans[0]
        self.assertEqual(sp.axis, 'y')
        self.assertAlmostEqual(sp.lo, 0.2)
        self.assertAlmostEqual(sp.hi, 0.8)

    def test_partial_span_reason(self):
        fig, ax = plt.subplots()
        ax.plot([0, 1, 2], [0, 1, 0])
        ax.axvspan(0.5, 1.5, ymin=0.2, ymax=0.8)
        r = convert(fig)
        plt.close(fig)
        self.assertIsNone(r.document)
        self.assertTrue(any('partial' in x for x in r.reasons))

    def test_span_plus_bars_reason(self):
        fig, ax = plt.subplots()
        ax.bar(['a', 'b'], [1, 2])
        ax.axvspan(0, 0.5)
        r = convert(fig)
        plt.close(fig)
        self.assertIsNone(r.document)
        self.assertTrue(any('spans' in x for x in r.reasons))

    def test_other_patch_still_reason(self):
        fig, ax = plt.subplots()
        ax.plot([0, 1, 2], [0, 1, 0])
        ax.fill([0, 1, 1], [0, 0, 1])
        r = convert(fig)
        plt.close(fig)
        self.assertIsNone(r.document)
        self.assertTrue(any('patches' in x for x in r.reasons))

    def test_savefig_round_trip(self):
        import os
        import tempfile
        fig, ax = plt.subplots()
        ax.plot([0, 1, 2], [0, 1, 0])
        ax.axvspan(0.5, 1.5, alpha=0.2)
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 's.ilmplot.svg')
            res = savefig(fig, path)
            plt.close(fig)
            self.assertTrue(res.native)
            with open(path, 'rb') as fh:
                doc = document_from_svg(fh.read())
            self.assertEqual(len(doc.spans), 1)
            self.assertEqual(doc.spans[0].lo, 0.5)


if __name__ == '__main__':
    unittest.main()
