"""Axis-title / plot-title wrapping at draw time."""
import os
import unittest

import matplotlib
matplotlib.use('Agg')
from matplotlib.backends.backend_agg import FigureCanvasAgg

from ilmplot.document import (LineSeries, PlotDocument, ViolinGroup)
from ilmplot.render import (MIN_AXES_FRACTION, _build_figure,
                            _fit_axes, _fit_figure, _titles_overflow,
                            render_document)

_BASE = os.path.join(os.path.dirname(__file__), '..', '..', '..',
                     'build', 'baseline_svgs_orig')

LONG_Y = ('Normalized fluorescence intensity relative to the '
          'untreated control after 24 hours of exposure (a.u.)')


def _fit(doc, w=90., h=65.):
    fig, ax = _build_figure(doc, 1.0, w, h)
    _fit_figure(doc, fig, ax)
    canvas = FigureCanvasAgg(fig)
    canvas.draw()
    return fig, ax, canvas.get_renderer()


def _line(**kw):
    return PlotDocument(series=[LineSeries(id='s0')], **kw)


class WrapTests(unittest.TestCase):

    def test_long_ylabel_wraps_and_stays_inside(self):
        doc = _line(ylabel=LONG_Y)
        fig, ax, renderer = _fit(doc)
        lab = ax.yaxis.label
        self.assertIn('\n', lab.get_text())
        bb = lab.get_window_extent(renderer)
        H = fig.get_figheight() * fig.dpi
        self.assertGreaterEqual(bb.y0, -0.5)
        self.assertLessEqual(bb.y1, H + 0.5)
        pos = ax.get_window_extent(renderer)
        self.assertGreaterEqual(pos.height,
                                MIN_AXES_FRACTION * H - 0.5)

    def test_long_xlabel_and_title_wrap(self):
        doc = _line(xlabel='A very long horizontal axis title ' * 6,
                    title='An extremely long plot title that '
                          'cannot fit on a single line ' * 3)
        fig, ax, renderer = _fit(doc)
        W = fig.get_figwidth() * fig.dpi
        self.assertIn('\n', ax.xaxis.label.get_text())
        self.assertIn('\n', ax.title.get_text())
        for artist in (ax.xaxis.label, ax.title):
            bb = artist.get_window_extent(renderer)
            self.assertGreaterEqual(bb.x0, -0.5)
            self.assertLessEqual(bb.x1, W + 0.5)

    def test_short_labels_unchanged_and_byte_identical(self):
        doc = _line(xlabel='Time (s)', ylabel='Signal (mV)',
                    title='Sample')
        fig, ax = _build_figure(doc, 1.0, 90., 65.)
        self.assertFalse(_titles_overflow(fig, ax))
        self.assertEqual(ax.yaxis.label.get_text(), 'Signal (mV)')
        self.assertEqual(ax.title.get_text(), 'Sample')
        fig.clear()
        baseline = os.path.join(_BASE, 'line_default.svg')
        if os.path.exists(baseline):
            with open(baseline, 'rb') as fh:
                self.assertEqual(render_document(doc).svg, fh.read())

    def test_math_token_stays_atomic(self):
        math_tok = r'$\mathrm{k_{obs}\ s^{-1}}$'
        doc = _line(ylabel='Rate ' + math_tok + ' of the ' +
                           'very long reaction name ' * 4)
        fig, ax, renderer = _fit(doc)
        lab = ax.yaxis.label
        self.assertIn('\n', lab.get_text())
        self.assertIn(math_tok, lab.get_text())
        for ln in lab.get_text().split('\n'):
            if math_tok in ln:
                break
        else:
            self.fail('math token line missing')

    def test_existing_hard_break_preserved(self):
        doc = _line(ylabel='Line one\nLine two')
        fig, ax, renderer = _fit(doc)
        self.assertEqual(ax.yaxis.label.get_text(),
                         'Line one\nLine two')

    def test_fitted_small_figure(self):
        doc = _line(ylabel=LONG_Y)
        fig, ax = _build_figure(doc, 1.0, 40., 30.)
        _fit_axes(fig, ax, 2.0)
        canvas = FigureCanvasAgg(fig)
        canvas.draw()
        renderer = canvas.get_renderer()
        bb = ax.yaxis.label.get_window_extent(renderer)
        H = fig.get_figheight() * fig.dpi
        self.assertGreaterEqual(bb.y0, -0.5)
        self.assertLessEqual(bb.y1, H + 0.5)
        fig.clear()

    def test_unbreakable_token(self):
        doc = _line(ylabel='x' * 200)
        fig, ax, renderer = _fit(doc)
        text = ax.yaxis.label.get_text()
        self.assertNotIn('\n', text.replace('x' * 200, ''))
        pos = ax.get_window_extent(renderer)
        H = fig.get_figheight() * fig.dpi
        self.assertGreaterEqual(
            pos.height, MIN_AXES_FRACTION * H - 0.5)

    def test_violin_long_ylabel(self):
        doc = PlotDocument(
            kind='violin', series=[], ylabel=LONG_Y,
            groups=[ViolinGroup(id='g0', label='A',
                                values=[1, 2, 3, 4, 5, 9])])
        fig, ax, renderer = _fit(doc)
        bb = ax.yaxis.label.get_window_extent(renderer)
        H = fig.get_figheight() * fig.dpi
        self.assertGreaterEqual(bb.y0, -0.5)
        self.assertLessEqual(bb.y1, H + 0.5)


if __name__ == '__main__':
    unittest.main()
