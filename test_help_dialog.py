import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from html.parser import HTMLParser
import unittest

from PyQt6.QtWidgets import QApplication, QLabel, QScrollArea, QTabWidget, QTableWidget
from src.app import help_dialog
from src.app.i18n import current_language, set_language, tr


class _MarkupChecker(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []

    def handle_starttag(self, tag, attrs):
        if tag not in ('br', 'hr', 'img'):
            self.stack.append(tag)
        if tag == 'a':
            raise AssertionError('Guide should work offline without external links')

    def handle_endtag(self, tag):
        assert self.stack and self.stack.pop() == tag, f'Unbalanced HTML: {tag}'


class HelpDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_all_pages_render_in_both_languages(self):
        original = current_language()
        self.addCleanup(set_language, original)
        keys = ('start', 'images', 'cells', 'labels', 'typography', 'export', 'advanced', 'shortcuts')
        for language in ('en', 'zh'):
            with self.subTest(language=language):
                set_language(language)
                dialog = help_dialog.HelpDialog()
                try:
                    dialog.show()
                    tabs = dialog.findChild(QTabWidget)
                    self.assertEqual(tabs.count(), len(keys))
                    for index, key in enumerate(keys):
                        title = tr('help_tab_' + key)
                        self.assertNotEqual(title, 'help_tab_' + key)
                        self.assertEqual(tabs.tabText(index), title)
                        tabs.setCurrentIndex(index)
                        self.app.processEvents()
                        page = tabs.widget(index)
                        if isinstance(page, QScrollArea):
                            label = page.widget()
                            self.assertIsInstance(label, QLabel)
                            self.assertIn('<h2', label.text())
                            parser = _MarkupChecker()
                            parser.feed(label.text())
                            parser.close()
                            self.assertEqual(parser.stack, [])
                            self.assertGreater(label.height(), 0)
                    table = dialog.findChild(QTableWidget)
                    self.assertGreater(table.rowCount(), 25)
                finally:
                    dialog.close()
                    dialog.deleteLater()
                    self.app.processEvents()

    def test_shortcuts_match_current_canvas_controls(self):
        en = dict(help_dialog._SHORTCUTS_EN)
        zh = dict(help_dialog._SHORTCUTS_ZH)
        self.assertEqual(list(en), list(zh))
        for key in ('Ctrl + Wheel', 'Ctrl + 0', 'Ctrl + 1', 'Ctrl + Arrow', 'Ctrl + ,', 'F1'):
            self.assertIn(key, en)
        self.assertNotIn('Shift + Arrow', en)
        self.assertIn('Navigate', en['Arrow keys'])

    def test_typography_covers_review_and_final_figure_units(self):
        en = help_dialog._TYPOGRAPHY_HTML_EN
        zh = help_dialog._TYPOGRAPHY_HTML_ZH
        for term in ('Edit SVG Text Groups', 'Match Raster Text Size', 'RapidOCR', 'Show original', 'final figure', 'source files'):
            self.assertIn(term, en)
        for term in ('编辑 SVG 文字组', '匹配位图文字大小', 'RapidOCR', '显示原图', '最终图', '源文件'):
            self.assertIn(term, zh)
        self.assertNotIn('View → SVG Text Groups', en)


if __name__ == '__main__':
    unittest.main()
