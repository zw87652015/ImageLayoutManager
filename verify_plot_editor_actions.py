"""Non-UI checks for the Plot Editor action/chart metadata (no Qt)."""

import dataclasses
import unittest

from src.plot_editor import actions


class ActionTableTests(unittest.TestCase):

    def test_keys_unique_and_match_spec(self):
        self.assertEqual(len(actions.ACTIONS),
                         len(set(actions.ACTIONS)))
        for key, spec in actions.ACTIONS.items():
            self.assertEqual(spec.key, key)
            self.assertTrue(spec.text)

    def test_hero_order(self):
        self.assertEqual(actions.HERO_ACTIONS,
                         ('undo', 'redo', 'new', 'open', 'save',
                          'plot', 'export'))

    def test_menu_entries_resolve(self):
        for menu in (actions.FILE_MENU, actions.EDIT_MENU,
                     actions.HELP_MENU):
            for key in menu:
                if key is None:
                    continue
                if key == 'export':
                    continue
                self.assertIn(key, actions.ACTIONS, key)
        self.assertIn('export', actions.FILE_MENU)

    def test_native_constants(self):
        self.assertEqual(actions.NATIVE_PLOT_FILTER,
                         'ILM Plot (*.ilmplot.svg)')
        self.assertEqual(actions.NATIVE_PLOT_SUFFIX, '.ilmplot.svg')

    def test_chart_groups(self):
        self.assertEqual(len(actions.CHART_GROUPS), 1)
        group = actions.CHART_GROUPS[0]
        self.assertEqual((group.key, group.text), ('line', 'Line'))
        self.assertEqual(
            [(c.key, c.text) for c in group.charts],
            [('pure_line', 'Pure Line'),
             ('pure_scatters', 'Pure Scatters'),
             ('line_scatters', 'Line + Scatters'),
             ('stacked_line', 'Stacked Line')])

    def test_default_chart_valid(self):
        group_key, chart_key = actions.DEFAULT_CHART
        group = next(g for g in actions.CHART_GROUPS
                     if g.key == group_key)
        self.assertIn(chart_key, [c.key for c in group.charts])

    def test_export_menu(self):
        self.assertEqual(actions.EXPORT_MENU,
                         ('export_ilmplot', 'export_pdf', 'export_svg',
                          'export_png', 'export_tiff', 'export_jpg'))
        for key in actions.EXPORT_MENU:
            self.assertIn(key, actions.ACTIONS)

    def test_menu_counts(self):
        self.assertEqual(len(actions.FILE_MENU), 11)
        self.assertEqual(len(actions.EDIT_MENU), 9)
        self.assertEqual(len(actions.HELP_MENU), 4)
        self.assertEqual(len(actions.EXPORT_MENU), 6)

    def test_specs_frozen(self):
        spec = actions.ACTIONS['new']
        with self.assertRaises(dataclasses.FrozenInstanceError):
            spec.text = 'x'


if __name__ == '__main__':
    unittest.main()
