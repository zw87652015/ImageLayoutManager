"""Box/column+points/histogram/horizontal-bar chart-type tests."""
import unittest

import matplotlib
matplotlib.use('Agg')

from ilmplot.document import (HistOptions, PlotDocument,
                              PlotDocumentError, StackCategory,
                              StackOptions, ViolinGroup, ViolinOptions,
                              required_capabilities)
from ilmplot.render import _hist_bins, element_regions, render_document


def _groups():
    return [ViolinGroup(id='g0', label='A', values=[1, 2, 3, 4, 5, 9]),
            ViolinGroup(id='g1', label='B', values=[2, 3, 3, 4, 6])]


def _violin_doc(**kw):
    d = PlotDocument(kind='violin', series=[], groups=_groups())
    for k, v in kw.items():
        setattr(d, k, v)
    return d


def _hist_doc(**kw):
    d = PlotDocument(kind='histogram', series=[], groups=_groups(),
                     legend=True)
    for k, v in kw.items():
        setattr(d, k, v)
    return d


def _stack_doc(**kw):
    d = PlotDocument(kind='stacked_column', series=[],
                     categories=[
                         StackCategory(id='c0', label='S1',
                                       values=[1, 2, 3],
                                       yerr=[0.2, 0.1, 0.3]),
                         StackCategory(id='c1', label='S2',
                                       values=[2, 1, 2])])
    for k, v in kw.items():
        setattr(d, k, v)
    return d


class OptionsTests(unittest.TestCase):

    def test_violin_options_round_trip(self):
        o = ViolinOptions(body='none', box_width=0.4,
                          show_outliers=False, bar_width=0.5,
                          bar_error='sem')
        d = o.to_dict()
        self.assertEqual(d['body'], 'none')
        self.assertEqual(d['box_width'], 0.4)
        self.assertEqual(d['show_outliers'], False)
        self.assertEqual(d['bar_width'], 0.5)
        self.assertEqual(d['bar_error'], 'sem')
        back = ViolinOptions.from_dict(d)
        self.assertEqual(back.to_dict(), d)

    def test_violin_options_strictness(self):
        for bad in ({'body': 'blob'}, {'box_width': 0},
                    {'box_width': 1.5}, {'show_outliers': 1},
                    {'bar_width': 0}, {'bar_error': 'ci'}):
            with self.assertRaises(PlotDocumentError, msg=bad):
                ViolinOptions.from_dict(bad)

    def test_stack_horizontal_round_trip(self):
        o = StackOptions(percent=False, horizontal=True)
        self.assertEqual(o.to_dict()['horizontal'], True)
        back = StackOptions.from_dict(o.to_dict())
        self.assertTrue(back.horizontal)
        self.assertNotIn('horizontal', StackOptions().to_dict())
        with self.assertRaises(PlotDocumentError):
            StackOptions.from_dict({'horizontal': 1})

    def test_hist_options_round_trip(self):
        o = HistOptions(bins=20, density=True, style='step',
                        fill_alpha=0.8, edge_color='#112233',
                        edge_width_pt=1.5, kde=True, bandwidth=0.4)
        back = HistOptions.from_dict(o.to_dict())
        self.assertEqual(back.to_dict(), o.to_dict())

    def test_hist_options_strictness(self):
        for bad in ({'bins': 0}, {'bins': 1001}, {'bins': True},
                    {'bins': 1.5}, {'bin_width': 0}, {'bin_width': -2},
                    {'style': 'x'}, {'density': 1}, {'kde': 'y'},
                    {'edge_width_pt': 11}, {'bandwidth': 'x'},
                    {'bandwidth': -1}, {'bogus': 1}):
            with self.assertRaises(PlotDocumentError, msg=bad):
                HistOptions.from_dict(bad)
        with self.assertRaises(PlotDocumentError):
            HistOptions.from_dict({'bins': 10, 'bin_width': 0.5})

    def test_default_docs_emit_nothing(self):
        self.assertEqual(ViolinOptions().to_dict(), {})
        self.assertEqual(HistOptions().to_dict(), {})
        d = _violin_doc(violin=ViolinOptions()).to_dict()
        for key in ('body', 'box_width', 'show_outliers', 'bar_width',
                    'bar_error', 'horizontal'):
            self.assertNotIn(key, d.get('violin', {}))
            self.assertNotIn(key, d)


class CapabilityTests(unittest.TestCase):

    def test_default_stamps_nothing(self):
        self.assertEqual(required_capabilities(_violin_doc()), [])
        self.assertEqual(required_capabilities(_hist_doc()),
                         ['histogram'])
        self.assertEqual(required_capabilities(_stack_doc()), [])

    def test_box_plot(self):
        for opt in (ViolinOptions(body='none'),
                    ViolinOptions(box_width=0.5),
                    ViolinOptions(show_outliers=False)):
            doc = _violin_doc(violin=opt)
            self.assertIn('box_plot', required_capabilities(doc))
            self.assertIn('box_plot', doc.to_dict()['requires'])

    def test_column_points(self):
        for opt in (ViolinOptions(body='bar'),
                    ViolinOptions(bar_width=0.5),
                    ViolinOptions(bar_error='sem')):
            self.assertIn('column_points',
                          required_capabilities(_violin_doc(violin=opt)))

    def test_horizontal_bars(self):
        doc = _stack_doc(stacked=StackOptions(percent=False,
                                              horizontal=True))
        self.assertEqual(required_capabilities(doc),
                         ['horizontal_bars'])

    def test_histogram_kind(self):
        doc = _hist_doc(histogram=HistOptions(kde=True))
        self.assertIn('histogram', doc.to_dict()['requires'])


class ValidateTests(unittest.TestCase):

    def test_histogram_kind_rules(self):
        _hist_doc().validate()
        with self.assertRaises(PlotDocumentError):
            _hist_doc(series=[1]).validate()
        with self.assertRaises(PlotDocumentError):
            _hist_doc(x_tick_labels=[[0, 'a']]).validate()
        with self.assertRaises(PlotDocumentError):
            _hist_doc(violin=ViolinOptions()).validate()
        with self.assertRaises(PlotDocumentError):
            _hist_doc(stacked=StackOptions()).validate()
        with self.assertRaises(PlotDocumentError):
            _hist_doc(ridgeline=_ridge()).validate()
        from ilmplot.document import Bracket
        with self.assertRaises(PlotDocumentError):
            _hist_doc(brackets=[Bracket(a=0, b=1)]).validate()
        # A histogram needs groups; series stay empty.
        with self.assertRaises(PlotDocumentError):
            _hist_doc(groups=[]).validate()
        with self.assertRaises(PlotDocumentError):
            _hist_doc(categories=[StackCategory(id='c9',
                                                values=[1])]).validate()

    def test_histogram_options_on_other_kinds(self):
        with self.assertRaises(PlotDocumentError):
            _violin_doc(histogram=HistOptions()).validate()
        with self.assertRaises(PlotDocumentError):
            _stack_doc(histogram=HistOptions()).validate()
        with self.assertRaises(PlotDocumentError):
            PlotDocument(histogram=HistOptions()).validate()

    def test_from_dict_histogram(self):
        doc = _hist_doc(histogram=HistOptions(bins=7, kde=True))
        back = PlotDocument.from_dict(doc.to_dict())
        self.assertEqual(back.kind, 'histogram')
        self.assertEqual(back.histogram.bins, 7)
        self.assertTrue(back.histogram.kde)


def _ridge():
    from ilmplot.document import RidgeOptions
    return RidgeOptions()


class RenderTests(unittest.TestCase):

    def test_histogram_variants(self):
        for kw in ({}, {'style': 'step'}, {'kde': True},
                   {'density': True}, {'bin_width': 1.0}, {'bins': 5}):
            doc = _hist_doc(histogram=HistOptions(**kw))
            svg = render_document(doc).svg
            self.assertIn(b'ilmplot-hist-g0', svg, msg=kw)
            self.assertIn(b'ilmplot-hist-g1', svg, msg=kw)

    def test_histogram_constant_data(self):
        doc = PlotDocument(kind='histogram', series=[], legend=False,
                           groups=[ViolinGroup(id='g0', label='A',
                                               values=[2.0] * 5)])
        svg = render_document(doc).svg
        self.assertIn(b'ilmplot-hist-g0', svg)

    def test_histogram_pinned_limits(self):
        doc = _hist_doc(xlim=[0.0, 8.0], ylim=[0.0, 3.0],
                        histogram=HistOptions())
        self.assertIn(b'ilmplot-hist-g0', render_document(doc).svg)

    def test_box_and_bar_bodies(self):
        for opt in (ViolinOptions(body='none'),
                    ViolinOptions(body='none', show_points=False),
                    ViolinOptions(body='none', show_outliers=False,
                                  show_points=False),
                    ViolinOptions(body='bar'),
                    ViolinOptions(body='bar', bar_error='sem'),
                    ViolinOptions(body='bar', bar_error='none'),
                    ViolinOptions(body='bar', show_points=False)):
            svg = render_document(_violin_doc(violin=opt)).svg
            self.assertIn(b'ilmplot-violin-g0', svg, msg=opt.to_dict())

    def test_box_pinned_limits(self):
        doc = _violin_doc(violin=ViolinOptions(body='none'),
                          ylim=[0.0, 8.0])
        self.assertIn(b'ilmplot-violin-g0', render_document(doc).svg)

    def test_bar_log_y(self):
        from ilmplot.document import AxisStyle, PlotStyle
        doc = _violin_doc(violin=ViolinOptions(body='bar'))
        doc.style = PlotStyle()
        doc.style.yaxis = AxisStyle(scale='log')
        svg = render_document(doc).svg
        self.assertIn(b'ilmplot-violin-g0', svg)

    def test_horizontal_variants(self):
        for opt in (StackOptions(percent=False, grouped=True,
                                 horizontal=True, show_values=True),
                    StackOptions(percent=False, horizontal=True,
                                 show_values=True),
                    StackOptions(percent=True, horizontal=True,
                                 show_values=True)):
            svg = render_document(_stack_doc(stacked=opt)).svg
            self.assertIn(b'ilmplot-stack-c0', svg, msg=opt.to_dict())


class RegionTests(unittest.TestCase):

    def test_hist_regions(self):
        regions = element_regions(_hist_doc())
        self.assertIn('hists', regions)
        self.assertIn('g0', regions['hists'])
        self.assertNotIn('violins', regions)

    def test_step_legend_regions(self):
        doc = _hist_doc(histogram=HistOptions(style='step'))
        svg = render_document(doc).svg
        self.assertIn(b'ilmplot-hist-g0', svg)
        self.assertIn(b'ilmplot-hist-g1', svg)
        regions = element_regions(doc)
        self.assertIn('g0', regions['hists'])
        self.assertIn('g1', regions['hists'])
        self.assertIn('legend', regions)

    def test_box_bar_still_violins(self):
        for body in ('none', 'bar'):
            doc = _violin_doc(violin=ViolinOptions(body=body))
            regions = element_regions(doc)
            self.assertIn('violins', regions)
            self.assertIn('g0', regions['violins'])


class HistBinsTests(unittest.TestCase):

    def test_bin_width_edges(self):
        doc = PlotDocument(
            kind='histogram', series=[],
            groups=[ViolinGroup(id='g0', label='A',
                                values=[0.2, 1.5, 2.2, 3.7])],
            histogram=HistOptions(bin_width=1.0))
        edges, counts = _hist_bins(doc)
        self.assertEqual(edges, [0.0, 1.0, 2.0, 3.0, 4.0])
        self.assertEqual(list(counts[0]), [1, 1, 1, 1])

    def test_bins_edges(self):
        doc = _hist_doc(histogram=HistOptions(bins=4))
        edges, counts = _hist_bins(doc)
        self.assertEqual(len(edges), 5)
        # Groups share the pooled edges.
        self.assertEqual(len(counts), 2)
        self.assertEqual(sum(counts[0]), 6)
        self.assertEqual(sum(counts[1]), 5)


class ByteIdentityTests(unittest.TestCase):

    def test_no_new_keys_on_defaults(self):
        doc = _violin_doc()
        d = doc.to_dict()
        self.assertNotIn('violin', d)
        self.assertNotIn('histogram', d)
        self.assertNotIn('requires', d)
        d2 = _stack_doc().to_dict()
        self.assertNotIn('stacked', d2)


if __name__ == '__main__':
    unittest.main()
