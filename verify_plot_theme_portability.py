"""Custom colour themes travel inside the plot file.

A ``custom:`` theme lives in the user's theme folder. Saving a plot or a
style preset stores that colour list; opening the file on a machine
without the theme still draws those colours. Files saved before the
snapshot keep the colours already baked into the document.

Run from the repo root: ``python -m unittest verify_plot_theme_portability``.
"""

import os
import tempfile
import unittest

import src  # noqa: F401  -- puts packages/ilmplot/src on sys.path

from src.plot_editor import palettes, plot_file, presets
from src.plot_editor.overrides import (OverridesError, PlotOverrides,
                                       assign_palette,
                                       assign_palette_reverse,
                                       effective_document,
                                       hold_baked_colours)
from src.plot_editor.plot_data import Series


def _items(n=2):
    return [Series(tuple(float(i) for i in range(4)),
                   tuple(float(i + k) for i in range(4)),
                   'S%d' % k, 'X', 'Y', y_column=k + 1)
            for k in range(n)]


def _colors(doc):
    return [s.color for s in doc.series]


class ThemeSnapshotTests(unittest.TestCase):

    def setUp(self):
        self._saved = dict(palettes._CUSTOM)

    def tearDown(self):
        palettes.set_custom_themes(self._saved)

    def test_missing_theme_uses_saved_list(self):
        palettes.set_custom_themes(
            {'Lab': ['#112233', '#445566']})
        o = PlotOverrides()
        o.palette = 'custom:Lab'
        o.palette_colors = ['#112233', '#445566']
        palettes.set_custom_themes({})
        doc = effective_document(None, _items(), 'pure_line', '', o)
        self.assertEqual(_colors(doc), ['#112233', '#445566'])

    def test_installed_theme_wins_over_stale_snapshot(self):
        o = PlotOverrides()
        o.palette = 'custom:Lab'
        o.palette_colors = ['#111111', '#222222']
        palettes.set_custom_themes(
            {'Lab': ['#abcdef', '#fedcba']})
        doc = effective_document(None, _items(), 'pure_line', '', o)
        self.assertEqual(_colors(doc), ['#abcdef', '#fedcba'])

    def test_reverse_applies_to_snapshot(self):
        o = PlotOverrides()
        o.palette = 'custom:Lab'
        o.palette_colors = ['#112233', '#445566']
        o.palette_reverse = True
        palettes.set_custom_themes({})
        doc = effective_document(None, _items(), 'pure_line', '', o)
        self.assertEqual(_colors(doc), ['#445566', '#112233'])

    def test_builtin_ignores_snapshot(self):
        o = PlotOverrides()
        o.palette = 'wong'
        o.palette_colors = ['#111111', '#222222']
        doc = effective_document(None, _items(), 'pure_line', '', o)
        plain = effective_document(
            None, _items(), 'pure_line', '',
            _palette('wong'))
        self.assertEqual(_colors(doc), _colors(plain))
        palettes.stamp_palette_colors(o)
        self.assertIsNone(o.palette_colors)
        self.assertNotIn('palette_colors', o.to_dict())

    def test_save_embeds_colours_and_reopens_without_theme(self):
        palettes.set_custom_themes(
            {'Lab': ['#112233', '#445566']})
        o = PlotOverrides()
        o.palette = 'custom:Lab'
        items = _items()
        doc = effective_document(None, items, 'pure_line', 'T', o)
        saved = _colors(doc)
        ws = plot_file.worksheet_from_document(doc)
        cols = tuple(range(ws.column_count))
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'p.ilmplot.svg')
            plot_file.save_plot_file(path, doc, ws, 'pure_line', cols, o)
            self.assertEqual(o.palette_colors, ['#112233', '#445566'])
            palettes.set_custom_themes({})
            pf = plot_file.load_plot_file(path)
        self.assertEqual(pf.overrides.palette, 'custom:Lab')
        self.assertEqual(pf.overrides.palette_colors,
                         ['#112233', '#445566'])
        self.assertEqual(_colors(pf.document), saved)
        again = effective_document(
            None, items, 'pure_line', 'T', pf.overrides)
        self.assertEqual(_colors(again), saved)

    def test_old_file_keeps_baked_colours(self):
        palettes.set_custom_themes(
            {'Lab': ['#112233', '#445566']})
        o = PlotOverrides()
        o.palette = 'custom:Lab'
        doc = effective_document(None, _items(), 'pure_line', '', o)
        saved = _colors(doc)
        o.palette_colors = None
        palettes.set_custom_themes({})
        slipped = effective_document(None, _items(), 'pure_line', '', o)
        self.assertNotEqual(_colors(slipped), saved)
        hold_baked_colours(o, doc)
        held = effective_document(None, _items(), 'pure_line', '', o)
        self.assertEqual(_colors(held), saved)

    def test_baked_colours_are_not_reversed_again(self):
        # The file was saved with Reverse on, so the document colours
        # are already reversed and ``palette_reverse`` is still true.
        # Using them as a theme list would flip them a second time.
        o = PlotOverrides()
        o.palette = 'custom:Lab'
        o.palette_reverse = True
        o.baked_item_colors = ['#112233', '#445566']
        doc = effective_document(None, _items(), 'pure_line', '', o)
        self.assertEqual(_colors(doc), ['#112233', '#445566'])

    def test_changing_theme_drops_baked_colours(self):
        o = PlotOverrides()
        o.palette = 'custom:Lab'
        o.baked_item_colors = ['#112233', '#445566']
        assign_palette(o, 'custom:Lab')
        self.assertEqual(o.baked_item_colors, ['#112233', '#445566'])
        assign_palette(o, 'wong')
        self.assertIsNone(o.baked_item_colors)

    def test_reverse_flips_baked_list_once(self):
        o = PlotOverrides()
        o.palette = 'custom:Lab'
        o.baked_item_colors = ['#112233', '#445566']
        assign_palette_reverse(o, True)
        doc = effective_document(None, _items(), 'pure_line', '', o)
        self.assertEqual(_colors(doc), ['#445566', '#112233'])

    def test_rejects_bad_palette_colors(self):
        with self.assertRaises(OverridesError):
            PlotOverrides.from_dict(
                {'palette': 'custom:Lab', 'palette_colors': []})
        with self.assertRaises(OverridesError):
            PlotOverrides.from_dict(
                {'palette': 'custom:Lab',
                 'palette_colors': ['not-a-color']})

    def test_old_overrides_without_snapshot_still_parse(self):
        o = PlotOverrides.from_dict({'palette': 'custom:Lab'})
        self.assertEqual(o.palette, 'custom:Lab')
        self.assertIsNone(o.palette_colors)


def _palette(name):
    o = PlotOverrides()
    o.palette = name
    return o


class PresetSnapshotTests(unittest.TestCase):

    def setUp(self):
        self._saved = dict(palettes._CUSTOM)

    def tearDown(self):
        palettes.set_custom_themes(self._saved)

    def test_preset_carries_custom_colours(self):
        palettes.set_custom_themes(
            {'Lab': ['#112233', '#445566']})
        src = PlotOverrides()
        src.palette = 'custom:Lab'
        preset = presets.capture(src, 'line')
        preset.name = 'Lab look'
        self.assertEqual(preset.palette_colors, ['#112233', '#445566'])
        restored = presets.StylePreset.from_dict(preset.to_dict())
        palettes.set_custom_themes({})
        dest = PlotOverrides()
        presets.apply(restored, dest, _items(), 'pure_line')
        doc = effective_document(None, _items(), 'pure_line', '', dest)
        self.assertEqual(_colors(doc), ['#112233', '#445566'])
        self.assertEqual(dest.palette, 'custom:Lab')

    def test_capture_uses_baked_colours_when_theme_is_missing(self):
        src = PlotOverrides()
        src.palette = 'custom:Lab'
        src.palette_reverse = True
        src.baked_item_colors = ['#445566', '#112233']
        preset = presets.capture(src, 'line')
        preset.name = 'Held'
        self.assertEqual(preset.palette_colors, ['#112233', '#445566'])
        dest = PlotOverrides()
        presets.apply(preset, dest, _items(), 'pure_line')
        doc = effective_document(None, _items(), 'pure_line', '', dest)
        self.assertEqual(_colors(doc), ['#445566', '#112233'])


if __name__ == '__main__':
    unittest.main()
