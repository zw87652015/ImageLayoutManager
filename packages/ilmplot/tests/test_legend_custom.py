"""Custom legend text / hidden-entry tests (``ilmplot.legend_text``)."""
import json
import unittest
from unittest import mock

import matplotlib
matplotlib.use('Agg')

from ilmplot import document as document_module
from ilmplot.document import (Band, HistOptions, LineSeries, PlotDocument,
                              PlotDocumentError, PlotVersionError, Span,
                              StackCategory, ViolinGroup,
                              required_capabilities)
from ilmplot.legend_text import (MAX_LEGEND_LINES, MAX_LEGEND_TEXT,
                                 default_template, parse_template,
                                 substitute)
from ilmplot.render import (_build_figure, element_regions,
                            render_document)


def _line_doc(**kw):
    d = PlotDocument(series=[
        LineSeries(id='s0', label='Alpha', x=[0., 1.], y=[0., 1.]),
        LineSeries(id='s1', label='Beta', x=[0., 1.], y=[1., 0.])])
    for k, v in kw.items():
        setattr(d, k, v)
    return d


def _legend_texts(doc):
    _fig, ax = _build_figure(doc, 1.0, 90., 65.)
    leg = ax.get_legend()
    return [t.get_text() for t in leg.get_texts()] \
        if leg is not None else []


class ParseTemplateTests(unittest.TestCase):

    def test_leading_run(self):
        self.assertEqual(parse_template(r'\l(1) \l(2) both'),
                         [(['1', '2'], 'both')])
        self.assertEqual(parse_template(r'\l(B2)x'), [(['B2'], 'x')])
        self.assertEqual(parse_template(r'\l(S1) %(S1)'),
                         [(['S1'], '%(S1)')])
        self.assertEqual(parse_template('  \\l(1)  x'), [(['1'], 'x')])

    def test_mid_line_literal(self):
        self.assertEqual(parse_template('a \\l(1) b'),
                         [([], 'a \\l(1) b')])
        self.assertEqual(parse_template(r'\l(x) y'), [([], r'\l(x) y')])
        self.assertEqual(parse_template(r'\\l(1) x'),
                         [([], r'\\l(1) x')])

    def test_lines_and_blanks(self):
        self.assertEqual(parse_template('a\n\nb'),
                         [([], 'a'), ([], ''), ([], 'b')])
        self.assertEqual(parse_template('\\l(1) x\nNote\n\\l(2) y'),
                         [(['1'], 'x'), ([], 'Note'), (['2'], 'y')])

    def test_refs_not_validated(self):
        # Range resolution happens at render time, not parse time.
        self.assertEqual(parse_template(r'\l(9) %(9)'),
                         [(['9'], '%(9)')])


class SubstituteTests(unittest.TestCase):

    def test_labels_and_misses(self):
        labels = {'1': 'Alpha', 'B2': 'Band'}
        self.assertEqual(substitute('%(1) %(B2) %(9) %(S1)', labels.get),
                         'Alpha Band  ')
        self.assertEqual(substitute('no refs', labels.get), 'no refs')
        self.assertEqual(substitute('%(1)', lambda r: None), '')


class DefaultTemplateTests(unittest.TestCase):

    def test_line_skips_unlabelled_and_hidden(self):
        doc = _line_doc()
        doc.series.append(LineSeries(id='s2', label='',
                                     x=[0.], y=[0.]))
        doc.series.append(LineSeries(id='s3', label='_hidden',
                                     x=[0.], y=[0.]))
        doc.legend_hidden = ['series:s1']
        self.assertEqual(default_template(doc), r'\l(1) %(1)')

    def test_bands_spans(self):
        doc = _line_doc(
            bands=[Band(id='b0', label='B', x=[0., 1.],
                        y1=[0., 0.], y2=[1., 1.]),
                   Band(id='b1', label='', x=[0., 1.],
                        y1=[0., 0.], y2=[1., 1.])],
            spans=[Span(id='p0', axis='x', lo=0., hi=1., label='S')])
        self.assertEqual(
            default_template(doc),
            '\\l(1) %(1)\n\\l(2) %(2)\n\\l(B1) %(B1)\n\\l(S1) %(S1)')

    def test_kinds_without_legend(self):
        violin = PlotDocument(
            kind='violin', series=[],
            groups=[ViolinGroup(id='g', label='G', values=[1])])
        self.assertEqual(default_template(violin), '')
        ridge = PlotDocument(
            kind='ridgeline',
            series=[LineSeries(id='s', label='L', x=[0.], y=[0.])])
        self.assertEqual(default_template(ridge), '')

    def test_stacked_and_histogram(self):
        stack = PlotDocument(
            kind='stacked_column', series=[],
            categories=[StackCategory(id='c0', label='C0',
                                      values=[1, 2]),
                        StackCategory(id='c1', label='',
                                      values=[2, 1])])
        self.assertEqual(default_template(stack), r'\l(1) %(1)')
        hist = PlotDocument(
            kind='histogram', series=[],
            groups=[ViolinGroup(id='g0', label='G0', values=[1, 2]),
                    ViolinGroup(id='g1', label='G1', values=[2, 3])],
            histogram=HistOptions())
        self.assertEqual(default_template(hist),
                         '\\l(1) %(1)\n\\l(2) %(2)')


class DocumentTests(unittest.TestCase):

    def test_round_trip(self):
        doc = _line_doc(legend_hidden=['series:s0'],
                        legend_text='\\l(1) %(1)')
        doc.validate()
        d = json.loads(json.dumps(doc.to_dict()))
        self.assertEqual(d['legend_hidden'], ['series:s0'])
        self.assertEqual(d['legend_text'], '\\l(1) %(1)')
        self.assertIn('legend_custom', d['requires'])
        back = PlotDocument.from_dict(d)
        self.assertEqual(back.legend_hidden, ['series:s0'])
        self.assertEqual(back.legend_text, '\\l(1) %(1)')
        self.assertEqual(back.to_dict(), d)

    def test_defaults_omit(self):
        d = _line_doc().to_dict()
        self.assertNotIn('legend_hidden', d)
        self.assertNotIn('legend_text', d)
        self.assertNotIn('legend_custom', d.get('requires', []))

    def test_hidden_validation(self):
        for bad in (['foo'], ['series:'], ['band:'], ['series:a', 'series:a'],
                    'series:a', [1]):
            with self.assertRaises(PlotDocumentError, msg=repr(bad)):
                _line_doc(legend_hidden=bad).validate()
        # Keys naming no plotted item are tolerated.
        _line_doc(legend_hidden=['series:nope', 'band:x1']).validate()

    def test_text_validation(self):
        for bad in ('', '   ', 'x' * (MAX_LEGEND_TEXT + 1),
                    '\n'.join(['x'] * (MAX_LEGEND_LINES + 1)), 5):
            with self.assertRaises(PlotDocumentError,
                                   msg=repr(bad)[:40]):
                _line_doc(legend_text=bad).validate()
        _line_doc(legend_text='\\l(1)').validate()

    def test_requires_and_old_reader(self):
        doc = _line_doc(legend_hidden=['series:s0'])
        self.assertIn('legend_custom', required_capabilities(doc))
        self.assertIn('legend_custom',
                      required_capabilities(_line_doc(legend_text='x')))
        d = doc.to_dict()
        old = document_module.CAPABILITIES - {'legend_custom'}
        with mock.patch.object(document_module, 'CAPABILITIES', old):
            with self.assertRaises(PlotVersionError) as cm:
                PlotDocument.from_dict(d)
        self.assertEqual(cm.exception.missing, ['legend_custom'])


class RenderTests(unittest.TestCase):

    def test_hidden_entry_dropped(self):
        doc = _line_doc(legend_hidden=['series:s0'])
        self.assertEqual(_legend_texts(doc), ['Beta'])
        regions = element_regions(doc)
        self.assertEqual(set(regions['legend_entries']),
                         {'series:s1'})

    def test_all_hidden_no_legend(self):
        doc = _line_doc(legend_hidden=['series:s0', 'series:s1'])
        _fig, ax = _build_figure(doc, 1.0, 90., 65.)
        self.assertIsNone(ax.get_legend())

    def test_template_rows(self):
        doc = _line_doc()
        doc.legend_text = '\\l(2) %(2)\nNote $\\alpha$\n' \
                          '\\l(1) \\l(2) both'
        self.assertEqual(_legend_texts(doc),
                         ['Beta', 'Note $\\alpha$', 'both'])
        regions = element_regions(doc)
        self.assertEqual(set(regions['legend_entries']),
                         {'series:s1'})

    def test_template_out_of_range(self):
        doc = _line_doc(legend_text='\\l(9) %(9) x\\l(1)y %(B1)%(S1)')
        self.assertEqual(len(_legend_texts(doc)), 1)
        self.assertFalse(element_regions(doc).get('legend_entries'))

    def test_template_stacked_and_histogram(self):
        stack = PlotDocument(
            kind='stacked_column', series=[],
            categories=[StackCategory(id='c0', label='C0',
                                      values=[1, 2]),
                        StackCategory(id='c1', label='C1',
                                      values=[2, 1])])
        stack.legend_text = '\\l(1) %(1)'
        self.assertEqual(_legend_texts(stack), ['C0'])
        hist = PlotDocument(
            kind='histogram', series=[],
            groups=[ViolinGroup(id='g0', label='G0', values=[1, 2, 3]),
                    ViolinGroup(id='g1', label='G1', values=[2, 3, 4])],
            histogram=HistOptions())
        hist.legend_text = '\\l(1) %(1)'
        self.assertEqual(_legend_texts(hist), ['G0'])

    def test_render_still_bytes_deterministic(self):
        doc = _line_doc(legend_text='\\l(1) %(1)')
        a = render_document(doc).svg
        b = render_document(doc.clone()).svg
        self.assertEqual(a, b)


if __name__ == '__main__':
    unittest.main()
