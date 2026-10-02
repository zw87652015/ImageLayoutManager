"""Non-UI checks for the Plot Editor i18n table (no Qt)."""

import os
import re
import unittest

from src.plot_editor import actions, i18n


def _used_keys():
    """Every ``tr('key')`` / ``tr("key")`` literal in src/plot_editor."""
    pat = re.compile(r"""\btr\(\s*['"]([A-Za-z0-9_]+)['"]""")
    any_key = re.compile(r"""['"]([a-z][a-z0-9_]*)['"]""")
    used = set()
    refs = set()
    here = os.path.dirname(os.path.abspath(__file__))
    folder = os.path.join(here, 'src', 'plot_editor')
    for fn in sorted(os.listdir(folder)):
        if not fn.endswith('.py') or fn == 'i18n.py':
            continue
        with open(os.path.join(folder, fn), encoding='utf-8') as fh:
            src = fh.read()
        used.update(pat.findall(src))
        refs.update(any_key.findall(src))
    return used, refs


def _placeholders(text):
    import string
    return {name for _, name, _, _ in
            string.Formatter().parse(text) if name}


class StringTableTests(unittest.TestCase):

    def test_every_entry_has_en_and_zh(self):
        for key, entry in i18n._STRINGS.items():
            self.assertTrue(entry.get('en'), key)
            self.assertTrue(entry.get('zh'), key)

    def _covered(self):
        """Keys covered by the scan: literal keys plus prefix literals
        like ``tr('act_' + key)``."""
        used, _refs = _used_keys()
        prefixes = {k for k in used if k.endswith('_')}
        plain = used - prefixes
        for p in prefixes:
            self.assertTrue(
                any(k.startswith(p) for k in i18n._STRINGS),
                'prefix %r matches nothing' % p)
        return plain, prefixes

    def test_used_keys_exist(self):
        for key in _used_keys()[0]:
            if key.endswith('_'):
                continue  # dynamic prefix (e.g. 'act_' + key)
            self.assertIn(key, i18n._STRINGS, key)

    def test_no_unused_keys(self):
        plain, prefixes = self._covered()
        _used, refs = _used_keys()
        for key in i18n._STRINGS:
            # Used as a tr literal, a dynamic prefix, referenced as a
            # string literal in a key→key mapping (_LINE_KEYS, _TITLES…),
            # or resolved by history_label() from worksheet labels.
            if (key in plain or key in refs or key.startswith('hist_')
                    or any(key.startswith(p) for p in prefixes)
                    or any(key.startswith(p) for p in refs
                           if p.endswith('_'))):
                continue
            self.fail('unused i18n key: %r' % key)

    def test_placeholders_match(self):
        for key, entry in i18n._STRINGS.items():
            self.assertEqual(_placeholders(entry['en']),
                             _placeholders(entry['zh']), key)

    def test_format_args_apply(self):
        self.assertEqual(
            i18n.tr('untitled', n=3), 'Untitled 3')
        i18n.set_language('zh')
        try:
            self.assertEqual(i18n.tr('untitled', n=3), '未命名 3')
        finally:
            i18n.set_language('en')

    def test_set_language(self):
        self.assertEqual(i18n.current_language(), 'en')
        i18n.set_language('zh')
        try:
            self.assertEqual(i18n.current_language(), 'zh')
            self.assertEqual(i18n.tr('act_new'), '新建')
        finally:
            i18n.set_language('en')
        self.assertEqual(i18n.tr('act_new'), 'New')

    def test_unknown_language_ignored(self):
        i18n.set_language('fr')
        self.assertEqual(i18n.current_language(), 'en')
        i18n.set_language(None)
        self.assertEqual(i18n.current_language(), 'en')

    def test_actions_metadata_resolves_zh(self):
        i18n.set_language('zh')
        try:
            for key in actions.ACTIONS:
                self.assertTrue(i18n.tr('act_' + key), key)
                self.assertTrue(i18n.tr('tip_' + key), key)
            for group in actions.CHART_GROUPS:
                self.assertTrue(i18n.tr('grp_' + group.key), group.key)
                for chart in group.charts:
                    self.assertTrue(i18n.tr('chart_' + chart.key),
                                    chart.key)
            self.assertEqual(i18n.tr('act_new'), '新建')
            self.assertEqual(i18n.tr('chart_stacked_line'), '堆叠折线')
        finally:
            i18n.set_language('en')

    def test_history_labels(self):
        self.assertEqual(i18n.history_label('Paste'), 'Paste')
        i18n.set_language('zh')
        try:
            self.assertEqual(i18n.history_label('Paste'), '粘贴')
            self.assertEqual(i18n.history_label('Bogus Op'),
                             'Bogus Op')
        finally:
            i18n.set_language('en')


if __name__ == '__main__':
    unittest.main()
