"""Non-UI checks for multi-line annotation note text."""
import unittest

import matplotlib
matplotlib.use('Agg')

import src  # noqa: F401  -- puts packages/ilmplot/src on sys.path

from ilmplot.document import Annotation, PlotDocument, LineSeries
from ilmplot.render import element_regions, render_document
from src.plot_editor.i18n import _STRINGS, tr
from src.plot_editor.note_text import (MAX_NOTE_TEXT,
                                       expand_newline_escapes)


class EscapeTests(unittest.TestCase):

    def test_expand(self):
        f = expand_newline_escapes
        self.assertEqual(f('a\\nb'), 'a\nb')
        self.assertEqual(f('$\\nu$ and \\n x'),
                         '$\\nu$ and \n x')
        self.assertEqual(f('\\neq 3'), '\\neq 3')
        self.assertEqual(f('end\\n'), 'end\n')
        self.assertEqual(f('back\\\\n'), 'back\\\\n')
        self.assertEqual(f('plain text'), 'plain text')

    def test_max(self):
        self.assertEqual(MAX_NOTE_TEXT, 500)


class RenderTests(unittest.TestCase):

    def _doc(self, text):
        return PlotDocument(
            series=[LineSeries(id='s0')],
            annotations=[Annotation(id='n0', text=text,
                                    anchor='upper left')])

    def test_multiline_renders_and_grows(self):
        one = self._doc('Line 1')
        two = self._doc('Line 1\nLine 2')
        self.assertIn(b'ilmplot-annotation-n0',
                      render_document(two).svg)
        h1 = element_regions(one)['annotations']['n0']['bbox']
        h2 = element_regions(two)['annotations']['n0']['bbox']
        self.assertGreater(h2[3] - h2[1], h1[3] - h1[1])

    def test_from_dict_round_trip(self):
        a = Annotation(id='n0', text='Line 1\nLine 2')
        self.assertEqual(
            Annotation.from_dict(a.to_dict(), 'a').text,
            'Line 1\nLine 2')

    def test_i18n_key(self):
        entry = _STRINGS['tip_note_text']
        self.assertTrue(entry['en'] and entry['zh'])
        self.assertTrue(tr('tip_note_text'))


if __name__ == '__main__':
    unittest.main()
