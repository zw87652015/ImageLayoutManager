"""Mathtext + non-math glyph coverage (``ilmplot.mathtext``)."""
import unittest
from unittest import mock

import matplotlib
matplotlib.use('Agg')

from ilmplot.document import LineSeries, PlotDocument
from ilmplot import render as render_module
from ilmplot.mathtext import math_font_family
from ilmplot.render import render_document


def _cjk_family():
    """A family covering CJK, or None when the machine has none."""
    return math_font_family('面积 $x$', ('DejaVu Sans',))


class MathFontFamilyTests(unittest.TestCase):

    def test_no_math_returns_none(self):
        self.assertIsNone(math_font_family('plain text', ('DejaVu Sans',)))
        self.assertIsNone(math_font_family('', ('DejaVu Sans',)))
        self.assertIsNone(math_font_family(None, ('DejaVu Sans',)))

    def test_ascii_math_covered_returns_none(self):
        self.assertIsNone(
            math_font_family('label $x^2$', ('DejaVu Sans',)))
        self.assertIsNone(math_font_family('$x$', ()))

    def test_cjk_math_returns_covering_family(self):
        fam = _cjk_family()
        if fam is None:
            self.skipTest('no CJK-capable font installed')
        from matplotlib import font_manager
        path = font_manager.findfont(
            font_manager.FontProperties(family=[fam]))
        font = font_manager.get_font(path)
        for ch in '面积':
            self.assertNotEqual(font.get_char_index(ord(ch)), 0, ch)

    def test_escaped_dollar_is_plain_text(self):
        # '\\$' never opens math; the '$' still needs a glyph, which
        # DejaVu Sans has — so still None, but via the text path.
        self.assertIsNone(
            math_font_family(r'cost \$5 $x$', ('DejaVu Sans',)))


class MathFontRenderTests(unittest.TestCase):

    def _doc(self, **kw):
        d = PlotDocument(series=[
            LineSeries(id='s0', label='电流 $I_0$',
                       x=[0., 1., 2.], y=[0., 1., 0.])],
            xlabel='面积 $\\mathrm{A}$', legend=True)
        for k, v in kw.items():
            setattr(d, k, v)
        return d

    def test_cjk_math_renders_real_glyphs(self):
        fam = _cjk_family()
        if fam is None:
            self.skipTest('no CJK-capable font installed')
        svg = render_document(self._doc()).svg.decode('utf-8')
        body = svg[svg.rfind('</metadata>'):]
        # mathtext emits one positioned <text> run per glyph, so the
        # characters never appear as a contiguous substring.
        for ch in '面积电流':
            self.assertIn('>%s<' % ch, body)
        self.assertNotIn('¤', body)
        self.assertIn("font-family: '%s'" % fam, body)

    def test_ascii_math_byte_identical_without_pass(self):
        doc = PlotDocument(series=[
            LineSeries(id='s0', label='plain $x^2$',
                       x=[0., 1., 2.], y=[0., 1., 0.])],
            xlabel='time $t$', legend=True)
        render_module._render_cache.clear()
        with_pass = render_document(doc).svg
        render_module._render_cache.clear()
        with mock.patch.object(render_module, '_fix_math_text_fonts',
                               lambda fig: None):
            without = render_document(doc).svg
        self.assertEqual(with_pass, without)


if __name__ == '__main__':
    unittest.main()
