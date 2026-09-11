"""Label styling must behave the same way for every property.

Font, size, weight and colour all edit the selected label only; "Apply Style
to All" is the single explicit way to restyle a whole group.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PyQt6.QtCore import QCoreApplication, QEvent, QSettings
from PyQt6.QtWidgets import QApplication

from src.app import main_window
from src.model.data_model import Cell, Project, RowTemplate, TextItem


class LabelStyleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        settings = QSettings(str(Path(self.temp.name) / 'test.ini'), QSettings.Format.IniFormat)
        settings.setValue('language', 'en')
        settings.setValue('ui/motion_mode', 'off')
        settings.setValue('autosave_interval_s', 0)
        for target, value in (
            ('src.app.main_window.HAS_OPENGL', False),
            ('src.app.main_window.QSettings', lambda *args: settings),
            ('src.app.main_window.MainWindow._start_update_check', lambda self: None),
        ):
            mock = patch(target, value)
            mock.start()
            self.addCleanup(mock.stop)
        self.window = main_window.MainWindow()
        self.window._dismiss_welcome()
        self._load_project()

    def tearDown(self):
        for tab in self.window._tabs:
            tab.undo_stack.setClean()
        with patch.object(main_window.get_image_proxy(), 'shutdown'):
            self.window.close()
        self.window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()

    def _load_project(self):
        project = Project(page_width_mm=160, page_height_mm=80, dpi=300)
        project.rows = [RowTemplate(index=0, column_count=3)]
        project.cells = [Cell(row_index=0, col_index=i) for i in range(3)]
        self.window._set_project(project, None)
        self.window._act_auto_label_incell.trigger()
        self.labels = [t for t in project.text_items if t.subtype == 'numbering']
        self.assertEqual(len(self.labels), 3)
        self.project = project
        self.window.undo_stack.setClean()

    def _select(self, text_item):
        graphics = self.window.scene.text_items[text_item.id]
        self.window.scene.clearSelection()
        graphics.setSelected(True)
        self.window._on_selection_changed()
        return graphics

    def _add_corner(self, cell, text='x'):
        item = TextItem(text=text, scope='cell', subtype='corner', parent_id=cell.id,
                        anchor='top_right_inside',
                        font_family=self.project.corner_label_font_family,
                        font_size_pt=self.project.corner_label_font_size,
                        font_weight=self.project.corner_label_font_weight,
                        color=self.project.corner_label_color)
        self.project.text_items.append(item)
        self.window._refresh_and_update()
        return item

    # ── individual edits ────────────────────────────────────────────────
    def test_every_style_property_edits_only_the_selected_label(self):
        first, second, third = self.labels
        self._select(first)
        original = (second.font_size_pt, second.font_family, second.font_weight, second.color)
        defaults = (self.project.label_font_size, self.project.label_font_family,
                    self.project.label_font_weight)

        for changes, attr, value in (
            ({'font_size_pt': 5}, 'font_size_pt', 5),
            ({'font_family': 'Georgia'}, 'font_family', 'Georgia'),
            ({'font_weight': 'normal'}, 'font_weight', 'normal'),
            ({'color': '#AA0000'}, 'color', '#AA0000'),
        ):
            with self.subTest(changes=changes):
                self.window._on_text_property_changed(changes)
                self.assertEqual(getattr(first, attr), value)
                self.assertEqual(
                    (second.font_size_pt, second.font_family, second.font_weight, second.color),
                    original, 'other labels must not change')
                self.assertEqual(
                    (third.font_size_pt, third.font_family, third.font_weight, third.color),
                    original)
        self.assertEqual((self.project.label_font_size, self.project.label_font_family,
                          self.project.label_font_weight), defaults,
                         'a per-label edit must not rewrite the group default')

    def test_font_edit_locks_the_label_against_the_global_sync(self):
        first, second = self.labels[0], self.labels[1]
        self._select(first)
        self.window._on_text_property_changed({'font_size_pt': 5})
        self.assertTrue(first.style_locked)
        self.assertFalse(second.style_locked)
        # A later group-wide change from Global Project Settings must respect it.
        self.window._on_project_property_changed({'label_font_size': 9})
        self.assertEqual(first.font_size_pt, 5)
        self.assertEqual(second.font_size_pt, 9)

    def test_colour_alone_does_not_lock_the_label(self):
        first = self.labels[0]
        self._select(first)
        self.window._on_text_property_changed({'color': '#123456'})
        self.assertEqual(first.color, '#123456')
        self.assertFalse(first.style_locked)

    def test_individual_edit_is_one_undo_step(self):
        first, second = self.labels[0], self.labels[1]
        self._select(first)
        before = self.window.undo_stack.index()
        self.window._on_text_property_changed({'font_size_pt': 6})
        self.assertEqual(self.window.undo_stack.index(), before + 1)
        self.window.undo_stack.undo()
        self.assertEqual(first.font_size_pt, second.font_size_pt)
        self.assertFalse(first.style_locked)

    # ── apply to all ────────────────────────────────────────────────────
    def test_apply_style_to_all_matches_group_and_sets_the_default(self):
        first = self.labels[0]
        self._select(first)
        self.window._on_text_property_changed({'font_size_pt': 5})
        self.window._on_text_property_changed({'color': '#AA0000'})
        self.window._on_text_property_changed({'font_family': 'Georgia'})
        self.window._on_text_property_changed({'font_weight': 'normal'})
        before = self.window.undo_stack.index()

        self.window.inspector.apply_style_btn.click()

        for label in self.labels:
            self.assertEqual(label.font_size_pt, 5)
            self.assertEqual(label.color, '#AA0000')
            self.assertEqual(label.font_family, 'Georgia')
            self.assertEqual(label.font_weight, 'normal')
            self.assertFalse(label.style_locked, 'a uniform group follows its default again')
        self.assertEqual(self.project.label_font_size, 5)
        self.assertEqual(self.project.label_color, '#AA0000')
        self.assertEqual(self.project.label_font_family, 'Georgia')
        self.assertEqual(self.project.label_font_weight, 'normal')

        self.assertEqual(self.window.undo_stack.index(), before + 1, 'one undo step')
        self.window.undo_stack.undo()
        self.assertEqual(self.labels[1].font_size_pt, self.labels[2].font_size_pt)
        self.assertNotEqual(self.labels[1].font_size_pt, 5)
        self.assertEqual(self.project.label_font_size, 12)
        self.assertTrue(self.labels[0].style_locked)

    def test_apply_style_to_all_is_a_no_op_when_already_uniform(self):
        self._select(self.labels[0])
        self.window.inspector.apply_style_btn.click()
        before = self.window.undo_stack.index()
        self.window.inspector.apply_style_btn.click()
        self.assertEqual(self.window.undo_stack.index(), before)

    def test_new_labels_follow_the_applied_default(self):
        self._select(self.labels[0])
        self.window._on_text_property_changed({'font_size_pt': 4})
        self.window.inspector.apply_style_btn.click()
        self.window._on_insert_cell(0, 3)
        self.window._act_auto_label_incell.trigger()
        labels = [t for t in self.project.text_items if t.subtype == 'numbering']
        self.assertEqual(len(labels), 4)
        self.assertTrue(all(label.font_size_pt == 4 for label in labels))

    # ── tiers and corner labels stay separate ───────────────────────────
    def test_tiers_are_independent(self):
        title, panel = self.labels[0], self.labels[1]
        title.label_tier = 'title'
        self.window._refresh_and_update()
        self._select(title)
        self.window._on_text_property_changed({'font_size_pt': 3})
        self.window.inspector.apply_style_btn.click()
        self.assertEqual(self.project.title_label_font_size, 3)
        self.assertEqual(self.project.label_font_size, 12, 'panel tier untouched')
        self.assertNotEqual(panel.font_size_pt, 3)

    def test_corner_labels_are_their_own_group_and_respect_locks(self):
        corner_a = self._add_corner(self.project.cells[0], 'x')
        corner_b = self._add_corner(self.project.cells[1], 'y')
        self._select(corner_a)
        self.window._on_text_property_changed({'font_size_pt': 5})
        self.assertTrue(corner_a.style_locked)
        self.assertNotEqual(corner_b.font_size_pt, 5)
        self.assertNotEqual(self.labels[0].font_size_pt, 5, 'numbering labels untouched')
        # The corner sync must leave the individually styled label alone.
        self.window._on_project_property_changed({'corner_label_font_size': 8})
        self.assertEqual(corner_a.font_size_pt, 5)
        self.assertEqual(corner_b.font_size_pt, 8)
        self._select(corner_a)
        self.window.inspector.apply_style_btn.click()
        self.assertEqual(corner_b.font_size_pt, 5)
        self.assertEqual(self.project.corner_label_font_size, 5)
        self.assertNotEqual(self.labels[0].font_size_pt, 5)

    def test_floating_text_is_unaffected_and_never_locked(self):
        self.window._on_add_text()
        floating = next(t for t in self.project.text_items if t.scope == 'global')
        self._select(floating)
        self.window._on_text_property_changed({'font_size_pt': 20})
        self.assertEqual(floating.font_size_pt, 20)
        self.assertFalse(floating.style_locked)
        self.assertEqual(self.project.label_font_size, 12)
        self.assertTrue(all(label.font_size_pt != 20 for label in self.labels))

    def test_inspector_button_reports_the_group_it_will_restyle(self):
        from src.app.i18n import tr
        self._select(self.labels[0])
        self.assertEqual(self.window.inspector.apply_style_btn.text(),
                         tr('btn_apply_all_numbering'))
        corner = self._add_corner(self.project.cells[2], 'z')
        self._select(corner)
        self.assertEqual(self.window.inspector.apply_style_btn.text(),
                         tr('btn_apply_all_corner'))
        self.assertTrue(self.window.inspector.apply_style_btn.toolTip())


if __name__ == '__main__':
    unittest.main()
