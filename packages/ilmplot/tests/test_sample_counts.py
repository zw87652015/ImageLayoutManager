"""Per-group sample-size marks (show_n / n_position / n_format)."""
import unittest

import matplotlib
matplotlib.use('Agg')

from ilmplot.document import (HistOptions, PlotDocument,
                              PlotDocumentError, ViolinGroup,
                              ViolinOptions, required_capabilities)
from ilmplot.render import (_build_figure, element_regions,
                            render_document)


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


class OptionsTests(unittest.TestCase):

    def test_violin_round_trip(self):
        for opt in (ViolinOptions(show_n=True),
                    ViolinOptions(show_n=True, n_position='top'),
                    ViolinOptions(show_n=True, n_position='bottom',
                                  n_format='count {n}')):
            d = opt.to_dict()
            self.assertEqual(ViolinOptions.from_dict(d), opt)
            self.assertEqual(ViolinOptions.from_dict(
                d, ctx='x').n_position, opt.n_position)

    def test_hist_round_trip(self):
        for opt in (HistOptions(show_n=True),
                    HistOptions(show_n=True, n_format='N:{n}')):
            self.assertEqual(HistOptions.from_dict(opt.to_dict()), opt)

    def test_strictness(self):
        with self.assertRaises(PlotDocumentError):
            ViolinOptions.from_dict({'n_position': 'left'})
        for bad in ('no placeholder', 'n = {m}', 'x' * 41):
            with self.assertRaises(PlotDocumentError, msg=bad):
                ViolinOptions.from_dict({'n_format': bad})
            with self.assertRaises(PlotDocumentError, msg=bad):
                HistOptions.from_dict({'n_format': bad})
        with self.assertRaises(PlotDocumentError):
            ViolinOptions.from_dict({'show_n': 1})
        with self.assertRaises(PlotDocumentError):
            HistOptions.from_dict({'show_n': 'yes'})
        for bad in (0, 73, 'x'):
            with self.assertRaises(PlotDocumentError, msg=repr(bad)):
                ViolinOptions.from_dict({'n_size_pt': bad})
        with self.assertRaises(PlotDocumentError):
            ViolinOptions.from_dict({'n_color': 'not a colour'})

    def test_size_color_round_trip(self):
        opt = ViolinOptions(show_n=True, n_size_pt=8.5,
                            n_color='#ff0000')
        self.assertEqual(ViolinOptions.from_dict(opt.to_dict()), opt)

    def test_defaults_emit_nothing(self):
        self.assertNotIn('show_n', ViolinOptions().to_dict())
        self.assertNotIn('n_position', ViolinOptions().to_dict())
        self.assertNotIn('n_format', ViolinOptions().to_dict())
        self.assertNotIn('n_size_pt', ViolinOptions().to_dict())
        self.assertNotIn('n_color', ViolinOptions().to_dict())
        self.assertNotIn('show_n', HistOptions().to_dict())
        self.assertNotIn('n_format', HistOptions().to_dict())


class CapabilityTests(unittest.TestCase):

    def test_stamps(self):
        for opt, key in ((ViolinOptions(show_n=True), 'show_n'),
                         (ViolinOptions(n_position='top'),
                          'n_position'),
                         (ViolinOptions(n_format='n:{n}'),
                          'n_format'),
                         (ViolinOptions(n_size_pt=8), 'n_size_pt'),
                         (ViolinOptions(n_color='#ff0000'),
                          'n_color')):
            caps = required_capabilities(
                _violin_doc(violin=opt))
            self.assertIn('sample_counts', caps, msg=key)
        caps = required_capabilities(
            _hist_doc(histogram=HistOptions(show_n=True)))
        self.assertIn('sample_counts', caps)
        caps = required_capabilities(
            _hist_doc(histogram=HistOptions(n_format='N{n}')))
        self.assertIn('sample_counts', caps)

    def test_defaults_stamp_nothing(self):
        self.assertEqual(
            required_capabilities(
                _violin_doc(violin=ViolinOptions())), [])
        self.assertNotIn(
            'sample_counts',
            required_capabilities(
                _hist_doc(histogram=HistOptions())))


class RenderTests(unittest.TestCase):

    def test_tick_position(self):
        doc = _violin_doc(violin=ViolinOptions(show_n=True))
        svg = render_document(doc).svg
        self.assertIn(b'n = 6', svg)
        self.assertIn(b'n = 5', svg)
        fig, ax = _build_figure(doc, 1.0, 90., 65.)
        labels = [t.get_text() for t in ax.get_xticklabels()]
        self.assertIn('A\nn = 6', labels)
        self.assertIn('B\nn = 5', labels)
        fig.clear()

    def test_top_and_bottom(self):
        for pos in ('top', 'bottom'):
            doc = _violin_doc(
                violin=ViolinOptions(show_n=True, n_position=pos))
            svg = render_document(doc).svg
            self.assertIn(b'n = 6', svg, msg=pos)
            regions = element_regions(doc)
            self.assertIn('g0', regions['violins'], msg=pos)

    def test_top_and_bottom_positions(self):
        for pos, low in (('top', False), ('bottom', True)):
            doc = _violin_doc(
                violin=ViolinOptions(show_n=True, n_position=pos))
            fig, ax = _build_figure(doc, 1.0, 90., 65.)
            texts = [t for t in ax.findobj(matplotlib.text.Text)
                     if (t.get_gid() or '') == 'ilmplot-violin-g1']
            self.assertEqual(len(texts), 1, msg=pos)
            y = texts[0].get_position()[1]
            ylim = ax.get_ylim()
            mid = sum(ylim) / 2.0
            if low:
                self.assertLess(y, mid)
            else:
                self.assertGreater(y, mid)
            fig.clear()

    def test_box_and_bar_bodies(self):
        for body in ('none', 'bar'):
            doc = _violin_doc(violin=ViolinOptions(
                body=body, show_n=True, n_position='top'))
            self.assertIn(b'n = 6', render_document(doc).svg,
                          msg=body)

    def test_histogram_legend(self):
        doc = _hist_doc(histogram=HistOptions(show_n=True))
        svg = render_document(doc).svg
        self.assertIn(b'(n = 6)', svg)
        doc = _hist_doc(histogram=HistOptions(show_n=True,
                                              style='step'))
        self.assertIn(b'(n = 6)', render_document(doc).svg)

    def test_n_text_style(self):
        doc = _violin_doc(violin=ViolinOptions(
            show_n=True, n_position='top', n_size_pt=6,
            n_color='#ff0000'))
        fig, ax = _build_figure(doc, 1.0, 90., 65.)
        t = next(x for x in ax.findobj(matplotlib.text.Text)
                 if (x.get_gid() or '') == 'ilmplot-violin-g1')
        self.assertEqual(t.get_fontsize(), 6)
        self.assertEqual(t.get_color(), '#ff0000')
        fig.clear()
        doc = _violin_doc(violin=ViolinOptions(show_n=True,
                                               n_position='top'))
        fig, ax = _build_figure(doc, 1.0, 90., 65.)
        t = next(x for x in ax.findobj(matplotlib.text.Text)
                 if (x.get_gid() or '') == 'ilmplot-violin-g1')
        self.assertEqual(t.get_fontsize(), doc.font_size_pt)
        self.assertEqual(t.get_color(), '#333333')
        fig.clear()

    def test_custom_format(self):
        doc = _violin_doc(violin=ViolinOptions(
            show_n=True, n_format='count={n}'))
        self.assertIn(b'count=6', render_document(doc).svg)


if __name__ == '__main__':
    unittest.main()
