"""Non-UI verification: plot style edits go into the Plot Editor's
Undo/Redo stack, chronological with worksheet cell edits.

Run from the repo root: ``python -m unittest verify_plot_overrides_undo``.
"""

import unittest

import src  # noqa: F401  -- puts packages/ilmplot/src on sys.path

from ilmplot.document import Band

from src.plot_editor.fills import CurveFill
from src.plot_editor.overrides import (PlotOverrides, SeriesOverride,
                                       record_overrides_edit)
from src.plot_editor.worksheet import META_ROWS, Worksheet


class _Fixture(unittest.TestCase):

    def setUp(self):
        self.ws = Worksheet()
        self.ov = PlotOverrides()
        self.commits = [0]

        def commit():
            self.commits[0] += 1
        self.commit = commit

    def edit(self, fn, label='Edit Plot'):
        return record_overrides_edit(
            self.ws, self.ov, fn, self.commit, label)


class BasicsTests(_Fixture):

    def test_undo_redo_restores(self):
        self.assertTrue(self.edit(lambda o: o.series.__setitem__(
            1, SeriesOverride(color='#ff0000'))))
        self.assertEqual(self.ov.series[1].color, '#ff0000')
        self.ws.undo()
        self.assertNotIn(1, self.ov.series)
        self.ws.redo()
        self.assertEqual(self.ov.series[1].color, '#ff0000')

    def test_object_identity_never_changes(self):
        # Open panels and the tab hold this exact object — restore must
        # mutate it in place.
        ref = self.ov
        self.edit(lambda o: o.series.__setitem__(
            1, SeriesOverride(color='#ff0000')))
        self.ws.undo()
        self.ws.redo()
        self.assertIs(self.ov, ref)
        self.assertEqual(self.ov.series[1].color, '#ff0000')

    def test_noop_records_nothing(self):
        self.assertFalse(self.edit(lambda o: None))
        self.assertFalse(self.ws.can_undo)

    def test_failure_rolls_back_and_records_nothing(self):
        def boom(o):
            o.series[1] = SeriesOverride(color='#ff0000')
            raise RuntimeError('bad edit')
        self.assertFalse(self.edit(boom))
        self.assertNotIn(1, self.ov.series)
        self.assertFalse(self.ws.can_undo)

    def test_undo_label(self):
        self.edit(lambda o: o.series.__setitem__(
            1, SeriesOverride(color='#ff0000')))
        self.assertEqual(self.ws.undo_label, 'Edit Plot')

    def test_restore_calls_commit(self):
        before = self.commits[0]
        self.edit(lambda o: o.series.__setitem__(
            1, SeriesOverride(color='#ff0000')))
        self.ws.undo()
        self.assertGreater(self.commits[0], before + 1)


class ChronologyTests(_Fixture):

    def test_interleaved_with_cell_edits(self):
        self.ws.set_block(1, META_ROWS, [['5']])
        self.edit(lambda o: o.series.__setitem__(
            1, SeriesOverride(color='#ff0000')))
        self.ws.set_block(1, META_ROWS + 1, [['7']])
        self.assertEqual(len(self.ws._undo), 3)
        # Undo order is reverse-chronological: cell, style, cell.
        self.ws.undo()
        self.assertIsNone(self.ws.value(1, 1))
        self.assertIn(1, self.ov.series)
        self.ws.undo()
        self.assertNotIn(1, self.ov.series)
        self.assertEqual(self.ws.value(1, 0), 5.0)
        self.ws.undo()
        self.assertIsNone(self.ws.value(1, 0))
        self.assertFalse(self.ws.can_undo)
        self.ws.redo()
        self.ws.redo()
        self.ws.redo()
        self.assertEqual(self.ws.value(1, 0), 5.0)
        self.assertEqual(self.ws.value(1, 1), 7.0)
        self.assertEqual(self.ov.series[1].color, '#ff0000')


class ContentEditsTests(_Fixture):

    def test_delete_fill_is_undoable(self):
        self.ov.fills = [CurveFill(id='f', kind='under', a=1)]
        self.edit(lambda o: setattr(
            o, 'fills', [f for f in o.fills if f.id != 'f']))
        self.assertFalse(self.ov.fills)
        self.ws.undo()
        self.assertEqual([f.id for f in self.ov.fills], ['f'])
        self.ws.redo()
        self.assertFalse(self.ov.fills)

    def test_reset_formatting_style_undoes_fully(self):
        self.ov.bands = [Band(id='b1', x=[0, 1], y1=[0, 0],
                              y2=[1, 1])]
        self.ov.series[1] = SeriesOverride(color='#00ff00')

        def reset(o):
            # Mirrors PlotTab._reset_all_formatting: fresh overrides
            # with the content fields carried over.
            fresh = PlotOverrides()
            fresh.bands = o.bands
            for name in PlotOverrides._KEYS:
                setattr(o, name, getattr(fresh, name))
        self.edit(reset)
        self.assertFalse(self.ov.series)
        self.assertEqual(self.ov.bands[0].id, 'b1')
        self.ws.undo()
        self.assertEqual(self.ov.series[1].color, '#00ff00')
        self.assertEqual(self.ov.bands[0].id, 'b1')


if __name__ == '__main__':
    unittest.main()
