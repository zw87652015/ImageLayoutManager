"""Non-UI checks for Plot Editor inline mathtext (no Qt)."""

import unittest

from src.plot_editor import render
from src.plot_editor.document import PlotDocument
from src.plot_editor.mathtext import (LATEX_LOGO, TEX_LOGO, has_math,
                                      preprocess, safe_text)
from src.plot_editor.plot_data import Series
from src.plot_editor.plotting import figure_svg, make_figure


class HasMathTests(unittest.TestCase):

    def test_detection(self):
        self.assertTrue(has_math('a $x^2$ b'))
        self.assertFalse(has_math('plain'))
        self.assertFalse(has_math('lone $5'))
        self.assertFalse(has_math(''))
        self.assertFalse(has_math('multi\n$not across\nlines$'))


class PreprocessTests(unittest.TestCase):

    def test_macros_rewritten_inside_math(self):
        self.assertEqual(preprocess(r'$\LaTeXe$'),
                         '$' + LATEX_LOGO[:-1] + r'\,2_{\epsilon}}$')
        self.assertEqual(preprocess(r'$\LaTeX$'), '$' + LATEX_LOGO + '$')
        self.assertEqual(preprocess(r'$\TeX$'), '$' + TEX_LOGO + '$')

    def test_order_latexe_first(self):
        # \LaTeXe must win over the \LaTeX prefix.
        out = preprocess(r'$\LaTeXe$')
        self.assertNotIn(LATEX_LOGO + 'e', out)

    def test_logos_parse(self):
        for t in (r'$\LaTeX$', r'$\LaTeXe$', r'$\TeX$', r'a $\LaTeX$ b'):
            self.assertEqual(safe_text(t), preprocess(t))

    def test_outside_math_untouched(self):
        self.assertEqual(preprocess(r'plain \LaTeX text'), r'plain \LaTeX text')


class SafeTextTests(unittest.TestCase):

    def test_valid_math_unchanged(self):
        self.assertEqual(safe_text(r'$\alpha$ decay'), r'$\alpha$ decay')

    def test_invalid_math_escaped(self):
        bad = r'$\frac{$'
        out = safe_text(bad)
        self.assertEqual(out, r'\$\frac{\$')

    def test_latex_macro_renderable(self):
        self.assertEqual(safe_text(r'$\LaTeX$'), '$' + LATEX_LOGO + '$')

    def test_lone_dollar_escaped(self):
        self.assertEqual(safe_text('costs $5 today'), r'costs \$5 today')

    def test_stray_dollars_never_reach_mathtext(self):
        self.assertEqual(safe_text('$$'), r'\$\$')
        self.assertEqual(safe_text('$x$ costs $5'), r'$x$ costs \$5')
        doc = PlotDocument()
        for t in ('$', '$$', '$ $', '$x$ $', 'a $$ b'):
            doc.title = doc.xlabel = t
            doc.series[0].label = t
            self.assertIn(b'<svg', render.render_document(doc).svg)

    def test_mixed_valid_and_invalid(self):
        out = safe_text(r'$x^2$ and $\frac{$')
        self.assertEqual(out, r'$x^2$ and \$\frac{\$')

    def test_no_math_unchanged(self):
        self.assertEqual(safe_text('plain text'), 'plain text')


def cat_series():
    return [Series((1.0, 2.0), (1.0, 2.0), r'L $\frac{$', r'X $\frac{$',
                   r'Y $\frac{$', (r'$\frac{$', 'b'))]


class FigureTests(unittest.TestCase):

    def test_invalid_math_everywhere_renders(self):
        svg = figure_svg(make_figure(cat_series(), 'pure_line',
                                     title=r'$\frac{$ bad'))
        self.assertIn(b'<svg', svg)

    def test_render_document_invalid_math_no_raise(self):
        doc = PlotDocument()
        doc.title = r'$\frac{$'
        doc.xlabel = r'$\LaTeX$'
        doc.ylabel = 'ok'
        doc.series[0].label = r'$\frac{$'
        doc.x_tick_labels = [[1.0, r'$\frac{$'], [2.0, 'b']]
        svg = render.render_document(doc).svg
        self.assertIn(b'<svg', svg)
        self.assertEqual(doc.title, r'$\frac{$')  # stored text stays raw

    def test_valid_math_title_renders(self):
        doc = PlotDocument()
        doc.title = r'$\alpha$ decay'
        svg = render.render_document(doc).svg
        self.assertIn(b'<svg', svg)
        self.assertIn(b'decay', svg)

    def test_math_run_survives_prepare(self):
        # A math title goes through _flatten_positioned_runs/_precise_text
        # without error and keeps its runs in the prepared SVG.
        doc = PlotDocument()
        doc.title = r'$\alpha$ decay'
        out = render._prepare_svg(_raw_svg(doc), doc.font_family)
        self.assertIn(b'ilmplot-title', out)
        self.assertIn(b'decay', out)


def _raw_svg(doc):
    import io
    from src.plot_editor.render import _build_figure
    fig, _ax = _build_figure(doc, 1.0, doc.width_mm, doc.height_mm)
    buf = io.BytesIO()
    fig.savefig(buf, format='svg')
    fig.clear()
    return buf.getvalue()


if __name__ == '__main__':
    unittest.main()
