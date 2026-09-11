import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PyQt6.QtCore import QSettings, QCoreApplication, QEvent, Qt, QRect, QRectF, QPoint
from PyQt6.QtGui import QFontDatabase
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QPushButton, QDoubleSpinBox
from src.app import main_window, tutorials
from src.app.i18n import current_language, set_language
from src.app.motion import set_motion_mode
from src.model.data_model import Project, SvgTextGroup, SvgTextMember, RasterTextRegion


def _control_rect_in_host(highlight):
    """The highlighted control's rect in the highlight's own coordinates."""
    top_left = highlight.target.mapTo(highlight.host, highlight._rect.topLeft()) - highlight.pos()
    return QRectF(QRect(top_left, highlight._rect.size()))


def _rendered_text_mm(text_item):
    """Text box in millimetres, using the same 24-unit reference the
    exporter and canvas use, so the assertion reflects the printed figure."""
    from PyQt6.QtWidgets import QGraphicsTextItem
    from PyQt6.QtGui import QFont
    item = QGraphicsTextItem()
    item.setHtml(text_item.text)
    font = QFont(text_item.font_family, 24)
    font.setBold(text_item.font_weight == 'bold')
    item.setFont(font)
    rect = item.boundingRect()
    scale = text_item.font_size_pt / 24
    return rect.width() * scale, rect.height() * scale


class TutorialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)
        for font in ('arial.ttf', 'msyh.ttc'):
            QFontDatabase.addApplicationFont(os.path.join(os.environ.get('WINDIR', 'C:\\Windows'), 'Fonts', font))

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        settings = QSettings(str(Path(self.temp.name) / 'test.ini'), QSettings.Format.IniFormat)
        settings.setValue('language', 'en')
        settings.setValue('ui/motion_mode', 'off')
        settings.setValue('autosave_interval_s', 0)
        self.old_language = current_language()
        self.addCleanup(set_language, self.old_language)
        for target, value in (
            ('src.app.main_window.HAS_OPENGL', False),
            ('src.app.main_window.QSettings', lambda *args: settings),
            ('src.app.main_window.MainWindow._start_update_check', lambda self: None),
            ('src.app.tutorials.QStandardPaths.writableLocation', lambda kind: self.temp.name),
        ):
            mock = patch(target, value)
            mock.start()
            self.addCleanup(mock.stop)
        self.window = main_window.MainWindow()
        self.window._on_show_tutorials()
        self.controller = self.window._tutorial_controller
        self.original_tab = self.window._tabs[0]
        self.original = self.original_tab.project.to_dict()

    def tearDown(self):
        self.controller.stop()
        for tab in self.window._tabs:
            self.window._close_svg_text_inspectors(tab.project)
            tab.undo_stack.setClean()
        with patch.object(main_window.get_image_proxy(), 'shutdown'):
            self.window.close()
        if self.window.welcome_window:
            self.window.welcome_window.hide()
        self.window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()

    def go_to(self, key):
        self.controller.index = next(i for i, step in enumerate(tutorials.LESSONS[self.controller.lesson]) if step.key == key)
        self.controller.refresh()

    def _complete_first_figure_setup(self):
        """Walk the grid-building steps (delete the second row, add a third
        cell) and load the three samples — the one-row-of-three state every
        later first_figure step assumes. Must follow ``start('first_figure')``."""
        self.go_to('delete_row')
        self.controller.perform_action()
        self.go_to('add_cell')
        self.controller.perform_action()
        self.go_to('load')
        self.controller.perform_action()

    def test_start_exit_replay_preserves_existing_project(self):
        self.controller.start('first_figure')
        practice = self.controller.tab
        self.assertEqual(len(self.window._tabs), 2)
        self.assertIsNot(practice.project, self.original_tab.project)
        self.assertIn('Practice', self.window._tab_title(practice))
        self.assertFalse(practice.undo_stack.isClean())
        self.controller.stop()
        self.assertIs(self.window.project, self.original_tab.project)
        self.assertIn(practice, self.window._tabs)
        self.assertFalse(self.controller.timer.isActive())
        self.assertIsNone(self.controller.highlight)
        self.assertEqual(self.original_tab.project.to_dict(), self.original)
        self.controller.start('first_figure')
        self.assertIsNot(self.controller.tab, practice)
        self.assertEqual(len(self.window._tabs), 3)

    def test_first_figure_actions_and_save_cancellation(self):
        self.controller.start('first_figure')
        self.controller.next()
        self.assertEqual(self.controller.step.key, 'delete_row')
        self.assertFalse(self.controller.ready())
        self.controller.perform_action()
        self.assertTrue(self.controller.ready())
        self.controller.next()
        self.assertEqual(self.controller.step.key, 'add_cell')
        self.assertFalse(self.controller.ready())
        self.controller.perform_action()
        self.assertTrue(self.controller.ready())
        self.controller.next()
        self.assertEqual(self.controller.step.key, 'load')
        self.assertFalse(self.controller.ready())
        self.controller.perform_action()
        self.assertTrue(self.controller.ready())
        self.assertEqual(self.controller.tab.undo_stack.count(), 3)
        self.controller.next()
        self.assertFalse(self.controller.ready())
        self.window._act_auto_layout.trigger()
        self.assertTrue(self.controller.ready())
        self.controller.next()
        self.window._act_auto_label_incell.trigger()
        self.assertTrue(self.controller.ready())
        self.controller.next()
        self.assertEqual(self.controller.step.key, 'label_size')
        self.controller.perform_action()
        self.assertTrue(self.controller.ready())
        self.controller.next()
        self.assertEqual(self.controller.step.key, 'save')
        with patch('src.app.main_window.QFileDialog.getSaveFileName', return_value=('', '')):
            self.window._act_save.trigger()
        self.assertFalse(self.controller.ready())
        path = str(Path(self.temp.name) / 'practice.figlayout')
        with patch('src.app.main_window.QFileDialog.getSaveFileName', return_value=(path, 'Figure Layout (*.figlayout)')):
            self.window._act_save.trigger()
        self.assertTrue(Path(path).is_file())
        self.assertTrue(self.controller.ready())
        self.controller.next()
        self.window._act_preview_mode.trigger()
        self.assertTrue(self.controller.ready())
        self.controller.next()
        self.controller.next()
        self.assertEqual(self.window._settings.value('tutorials/v1/first_figure'), 'completed')

    def test_first_figure_starts_as_a_plain_new_project_grid(self):
        """The lesson starts exactly like File → New (a 2x2 grid of empty
        placeholders), not a pre-built row — its own first steps teach
        getting from there to one row of three panels."""
        self.controller.start('first_figure')
        project = self.controller.tab.project
        self.assertEqual(len(project.rows), 2)
        self.assertEqual([r.column_count for r in project.rows], [2, 2])
        self.assertEqual(len(project.cells), 4)
        self.assertTrue(all(c.is_placeholder and not c.image_path for c in project.cells))
        self.assertEqual(self.controller.step.key, 'intro')
        self.assertTrue(self.controller.ready())

    def test_first_figure_matches_all_normal_new_project_defaults(self):
        self.window._on_new_project()
        normal = self.window.project.to_dict()
        self.controller.start('first_figure')
        practice = self.controller.tab.project.to_dict()
        for data in (normal, practice):
            for cell in data['cells']:
                cell.pop('id')
        self.assertEqual(practice, normal)
        self._complete_first_figure_setup()
        self.window._act_auto_label_incell.trigger()
        labels = [item for item in self.controller.tab.project.text_items if item.subtype == 'numbering']
        self.assertEqual(len(labels), 3)
        self.assertTrue(all(label.font_size_pt == normal['label_font_size'] for label in labels))

    def test_delete_row_and_add_cell_steps_reach_one_row_of_three(self):
        self.controller.start('first_figure')
        project = self.controller.tab.project
        self.controller.next()
        self.assertEqual(self.controller.step.key, 'delete_row')
        self.assertFalse(self.controller.ready())
        self.controller.perform_action()
        self.assertEqual(len(project.rows), 1)
        self.assertEqual(len(project.cells), 2)
        self.assertTrue(self.controller.ready())
        # The tutorial must not treat the shrunk cell set as an invalid
        # practice project and stop itself.
        self.controller.refresh()
        self.assertIsNotNone(self.controller.tab)
        self.assertTrue(self.controller.card.isVisible())

        self.controller.next()
        self.assertEqual(self.controller.step.key, 'add_cell')
        self.assertFalse(self.controller.ready())
        self.controller.perform_action()
        self.assertEqual(len(project.cells), 3)
        self.assertEqual([c.col_index for c in project.cells], [0, 1, 2])
        self.assertTrue(all(c.row_index == 0 for c in project.cells))
        self.assertTrue(self.controller.ready())
        self.controller.refresh()
        self.assertIsNotNone(self.controller.tab)

        self.controller.next()
        self.assertEqual(self.controller.step.key, 'load')
        self.controller.perform_action()
        self.assertEqual([c.image_path for c in project.cells], self.controller.paths)

    def test_delete_row_and_add_cell_accept_manual_completion(self):
        """Doing the real right-click / + button actions must satisfy the
        step just like the guided helper buttons do."""
        self.controller.start('first_figure')
        project = self.controller.tab.project
        self.controller.next()
        self.assertEqual(self.controller.step.key, 'delete_row')
        self.window._on_delete_row(1)
        self.assertEqual(len(project.rows), 1)
        self.assertTrue(self.controller.ready())

        self.controller.next()
        self.assertEqual(self.controller.step.key, 'add_cell')
        row = next(r for r in project.rows if r.index == 0)
        self.window._on_insert_cell(0, row.column_count)
        self.assertEqual(len(project.cells), 3)
        self.assertTrue(self.controller.ready())

    def test_tab_switch_pauses_actions(self):
        self.controller.start('first_figure')
        self.go_to('load')
        practice = self.controller.tab
        self.window._activate_tab(0)
        self.controller.refresh()
        self.assertFalse(self.controller.card.next.isEnabled())
        self.assertFalse(self.controller.card.action.isEnabled())
        self.assertIsNone(self.controller.highlight)
        self.controller.perform_action()
        self.assertTrue(all(cell.image_path is None for cell in practice.project.cells))
        self.assertEqual(self.original_tab.project.to_dict(), self.original)
        self.controller.resume()
        self.assertIs(self.window.project, practice.project)
        self.assertTrue(self.controller.card.action.isEnabled())

    def test_tab_replacement_and_close_stop_cleanly(self):
        self.controller.start('first_figure')
        self.controller.tab.project = Project()
        self.controller.refresh()
        self.assertIsNone(self.controller.tab)
        self.controller.start('first_figure')
        index = self.window._tabs.index(self.controller.tab)
        self.window._remove_tab(index)
        self.controller.refresh()
        self.assertIsNone(self.controller.tab)
        self.assertFalse(self.controller.card.isVisible())

    def test_skip_back_and_completion_are_distinguished(self):
        self.controller.start('text_sizes')
        self.controller.next()
        self.controller.skip()
        self.controller.back()
        self.assertEqual(self.controller.step.key, 'svg_open')
        while self.controller.step.key != 'finish':
            self.controller.skip()
        self.controller.next()
        self.assertEqual(self.window._settings.value('tutorials/v1/text_sizes'), 'explored')

    def test_svg_inspector_can_be_closed_and_reopened(self):
        self.controller.start('text_sizes')
        self.controller.next()
        self.controller.perform_action()
        self.assertTrue(self.controller.ready())
        cell = self.controller.tab.project.cells[0]
        inspector = self.controller._inspector(cell)
        inspector.close()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.controller.refresh()
        self.assertFalse(self.controller.ready())
        self.controller.perform_action()
        self.assertTrue(self.controller.ready())

    def test_group_recognition_and_raster_review(self):
        self.controller.start('text_sizes')
        project = self.controller.tab.project
        self.go_to('svg_assign')
        group = SvgTextGroup(font_size_pt=9, members=[SvgTextMember(project.cells[0].image_path, 'time')])
        project.svg_text_groups.append(group)
        self.assertTrue(self.controller.ready())
        self.controller.next()
        self.assertFalse(self.controller.ready())
        group.members.append(SvgTextMember(project.cells[1].image_path, 'time'))
        self.assertTrue(self.controller.ready())
        self.controller.next()
        self.assertFalse(self.controller.ready())
        region = RasterTextRegion(x=635, y=817, w=100, h=47, text='Time', font_size_px=40, group_id=group.id)
        project.cells[2].raster_text_regions.append(region)
        self.assertTrue(self.controller.ready())
        self.controller.next()
        self.assertTrue(self.controller.ready())
        region.enabled = False
        self.assertFalse(self.controller.ready())
        region.enabled = True
        self.controller.next()
        self.controller.perform_action()
        inspector = self.controller._inspector(project.cells[2])
        self.assertFalse(self.controller.ready())
        inspector._chk_original.setChecked(True)
        self.assertFalse(self.controller.ready())
        inspector._chk_original.setChecked(False)
        self.assertTrue(self.controller.ready())

    def test_bilingual_center_and_motion_modes(self):
        for language in ('en', 'zh'):
            set_language(language)
            self.controller.show_center()
            captions = [b.text() for b in self.controller.center.findChildren(QPushButton)]
            self.assertIn(tutorials.lesson_title('first_figure'), captions)
            self.controller.start('first_figure')
            for mode in ('standard', 'reduced', 'off'):
                set_motion_mode(mode)
                self.controller.refresh()
                highlight = self.controller.highlight
                self.assertTrue(highlight.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents))
                self.assertEqual(highlight.geometry(), highlight.parentWidget().rect())
                self.assertIn(tutorials.text(*self.controller.step.title), self.controller.card.heading.text())
            self.controller.stop()

    def test_real_svg_assignment_controls_complete_steps(self):
        self.controller.start('text_sizes')
        self.go_to('svg_assign')
        self.controller.perform_action()
        inspector = self.controller._inspector(self.controller.tab.project.cells[0])
        inspector._groups_widget._btn_add_group.click()
        inspector._groups_widget.findChild(QDoubleSpinBox).setValue(9)
        for row in range(inspector._elem_list.count()):
            item = inspector._elem_list.item(row)
            if item.data(Qt.ItemDataRole.UserRole) == 'time':
                item.setSelected(True)
        inspector._btn_assign.click()
        self.assertTrue(self.controller.ready())
        self.controller.next()
        self.controller.perform_action()
        inspector = self.controller._inspector(self.controller.tab.project.cells[1])
        for row in range(inspector._elem_list.count()):
            item = inspector._elem_list.item(row)
            if item.data(Qt.ItemDataRole.UserRole) == 'time':
                item.setSelected(True)
        inspector._btn_assign.click()
        self.assertTrue(self.controller.ready())
        self.assertEqual(self.original_tab.project.to_dict(), self.original)

    def test_ocr_unavailable_is_skippable_and_does_not_complete_detection(self):
        self.controller.start('text_sizes')
        self.go_to('raster_detect')
        with patch('src.app.raster_text_inspector.backend_status', return_value='OCR unavailable'):
            self.controller.perform_action()
        self.assertFalse(self.controller.ready())
        self.controller.skip()
        self.assertIn('raster_detect', self.controller.skipped)

    def test_replay_does_not_erase_completed_progress(self):
        self.window._settings.setValue('tutorials/v1/first_figure', 'completed')
        self.controller.start('first_figure')
        while self.controller.step.key != 'finish':
            self.controller.skip()
        self.controller.next()
        self.assertEqual(self.window._settings.value('tutorials/v1/first_figure'), 'completed')

    def test_welcome_and_guide_entry_points(self):
        self.window.welcome_window._btn_learn.click()
        buttons = self.controller.center.findChildren(QPushButton)
        next(button for button in buttons if button.text() == tutorials.lesson_title('first_figure')).click()
        self.assertEqual(self.controller.lesson, 'first_figure')
        self.assertEqual(self.original_tab.project.to_dict(), self.original)
        from src.app.help_dialog import HelpDialog
        from src.app.i18n import tr
        guide = HelpDialog(self.window)
        requests = []
        guide.tutorial_requested.connect(requests.append)
        next(button for button in guide.findChildren(QPushButton) if button.text() == tr('tutorials_try_text')).click()
        self.assertEqual(requests, ['text_sizes'])
        guide.deleteLater()

    def test_card_text_is_scrollable_at_large_font_sizes(self):
        self.controller.start('text_sizes')
        self.go_to('svg_assign')
        card = self.controller.card
        font = card.body.font()
        font.setPointSize(22)
        card.body.setFont(font)
        card.resize(380, 300)
        self.app.processEvents()
        self.assertGreaterEqual(card.body.height(), card.body.heightForWidth(card.body.width()))
        self.assertGreater(card.scroll.verticalScrollBar().maximum(), 0)
        self.assertTrue(card.exit.isVisible())
        card.reject()
        self.assertIsNone(self.controller.tab)

    def test_button_highlight_fades_and_contracts_without_clipping(self):
        with patch('src.app.motion.system_reduced_motion', return_value=False):
            set_motion_mode('standard')
        self.controller.start('first_figure')
        self.go_to('layout')
        highlight = self.controller.highlight
        button = self.window.toolbar.widgetForAction(self.window._act_auto_layout)
        original = button.geometry()
        self.assertIs(highlight.target, button)
        self.assertIs(highlight.parentWidget(), button.window())
        initial = highlight.outline_rect()
        self.assertLess(highlight.strength.value, 1)
        self.assertTrue(QRectF(highlight.rect()).contains(initial))
        self.assertTrue(initial.contains(_control_rect_in_host(highlight)),
                        'the entrance must start outside the control, never across it')
        highlight.strength._animation.setCurrentTime(90)
        highlight.settle._animation.setCurrentTime(90)
        middle = highlight.outline_rect()
        self.assertGreater(initial.width(), middle.width())
        self.assertGreater(highlight.strength.value, 0)
        self.controller.refresh()
        self.assertIs(self.controller.highlight, highlight)
        self.assertEqual(highlight.strength._animation.currentTime(), 90)
        set_motion_mode('off')
        final = highlight.outline_rect()
        self.assertGreater(middle.width(), final.width())
        self.assertEqual(highlight.strength.value, 1)
        self.assertEqual(highlight.settle.value, 1)
        self.assertEqual(button.geometry(), original)
        # Settled, the ring surrounds the control instead of tracing its
        # border, which would vanish on the filled accent buttons.
        control = _control_rect_in_host(highlight)
        self.assertEqual(final, control.adjusted(-highlight.GAP, -highlight.GAP, highlight.GAP, highlight.GAP))
        self.assertTrue(QRectF(highlight.rect()).contains(final))

    def test_reduced_highlight_only_fades_and_tracks_button_resize(self):
        set_motion_mode('reduced')
        self.controller.start('first_figure')
        self.go_to('layout')
        highlight = self.controller.highlight
        self.assertEqual(highlight.settle.value, 1)
        self.assertLessEqual(highlight.strength._animation.duration(), 70)
        before = highlight.outline_rect()
        self.window.resize(self.window.width() + 80, self.window.height())
        self.app.processEvents()
        self.controller.refresh()
        self.assertEqual(highlight.outline_rect().size(), before.size())
        self.assertEqual(highlight.outline_rect(),
                         _control_rect_in_host(highlight).adjusted(
                             -highlight.GAP, -highlight.GAP, highlight.GAP, highlight.GAP))

    def test_completion_feedback_triggers_once_and_clears_on_undo(self):
        with patch('src.app.motion.system_reduced_motion', return_value=False):
            set_motion_mode('standard')
        self.controller.start('first_figure')
        self.controller.next()
        status = self.controller.card.status
        self.assertFalse(status.success)
        self.controller.perform_action()
        self.assertTrue(status.success)
        self.assertIn('Step complete', status.text())
        status.reveal._animation.setCurrentTime(60)
        self.controller.refresh()
        self.assertEqual(status.reveal._animation.currentTime(), 60)
        self.window._activate_tab(0)
        self.controller.refresh()
        self.assertFalse(status.success)
        self.controller.resume()
        self.assertTrue(status.success)
        self.assertEqual(status.reveal.value, 1)
        self.controller.tab.undo_stack.undo()
        self.controller.refresh()
        self.assertFalse(status.success)
        self.assertFalse(self.controller.card.next.isEnabled())
        self.controller.tab.undo_stack.redo()
        self.controller.refresh()
        self.assertTrue(status.success)
        set_motion_mode('off')
        self.assertEqual(status.reveal.value, 1)
        set_language('zh')
        self.controller.refresh()
        self.assertIn('已完成', status.text())
        self.controller.next()
        self.assertFalse(status.success)
        self.controller.stop()
        self.assertEqual(status.reveal.value, 0)

    def test_highlight_finishes_naturally_and_does_not_block_clicks(self):
        with patch('src.app.motion.system_reduced_motion', return_value=False):
            set_motion_mode('standard')
        self.controller.start('first_figure')
        self.go_to('layout')
        before = self.controller.tab.project.to_dict()
        highlight = self.controller.highlight
        QTest.qWait(240)
        self.assertEqual(highlight.strength.value, 1)
        self.assertEqual(highlight.settle.value, 1)
        self.assertEqual(before, self.controller.tab.project.to_dict())
        QTest.mouseClick(highlight.target, Qt.MouseButton.LeftButton)
        self.assertTrue(self.controller.card.status.success)
        QTest.qWait(200)
        self.assertEqual(self.controller.card.status.reveal.value, 1)
        self.assertTrue(self.controller.card.next.isEnabled())

    def test_label_size_step_reveals_the_inspector_size_field(self):
        self.controller.start('first_figure')
        self._complete_first_figure_setup()
        self.window._act_auto_label_incell.trigger()
        self.go_to('label_size')
        inspector = self.window.inspector
        inspector.text_group.set_collapsed(True, animate=False)
        self.controller.refresh()
        self.assertFalse(self.controller.ready(), 'the step is not done until the field is on screen')
        self.controller.perform_action()
        self.assertEqual(inspector._current_item_type, 'text')
        self.assertFalse(inspector.text_group._collapsed)
        self.assertTrue(inspector.font_size.isVisible())
        self.assertTrue(self.controller.ready())
        self.assertIs(self.controller.highlight.target, inspector.font_size)
        self.assertTrue(self.controller.highlight.compact)
        self.assertIs(self.controller.highlight.parentWidget(), inspector.window())
        self.assertTrue(self.controller.card.status.success)
        label = next(item for item in self.controller.tab.project.text_items
                     if item.subtype == 'numbering')
        self.assertEqual(inspector.font_size.value(), label.font_size_pt)
        before = self.controller.tab.project.to_dict()
        self.controller.refresh()
        self.assertEqual(self.controller.tab.project.to_dict(), before,
                         'guidance must not change the figure')

    def test_menu_only_action_points_at_its_button_then_its_menu_row(self):
        self.controller.start('first_figure')
        self.go_to('preview')
        action = self.window._act_preview_mode
        self.assertIsNone(self.window.toolbar.widgetForAction(action),
                          'Export Preview has no toolbar button, so the step must resolve its menu owner')
        export_button = self.window._export_button
        self.assertIs(self.controller.highlight.target, export_button)
        self.assertIsNot(self.controller.highlight.target, self.window.view.viewport())

        menu = export_button.menu()
        menu.popup(self.window.mapToGlobal(QPoint(80, 80)))
        self.app.processEvents()
        self.controller.refresh()
        highlight = self.controller.highlight
        self.assertIs(highlight.target, menu)
        self.assertIs(highlight.parentWidget(), menu)
        self.assertTrue(highlight.compact)
        row = menu.actionGeometry(action)
        self.assertTrue(row.contains(highlight.geometry().center()))
        self.assertTrue(menu.rect().contains(highlight.geometry()))

        menu.close()
        self.app.processEvents()
        self.controller.refresh()
        self.assertIs(self.controller.highlight.target, export_button)
        action.trigger()
        self.assertTrue(self.controller.ready())

    def test_view_menu_only_action_falls_back_to_the_menu_bar(self):
        self.controller.start('first_figure')
        self.window.toolbar.hide()
        self.app.processEvents()
        widget, rect, compact = self.controller._action_target(self.window._act_preview_mode)
        self.assertIs(widget, self.window.menuBar())
        self.assertTrue(compact)
        view_entry = next(entry for entry in self.window.menuBar().actions()
                          if entry.menu() is self.window._view_menu)
        self.assertEqual(rect, self.window.menuBar().actionGeometry(view_entry))
        self.assertIsNone(self.controller._action_target(None)[0])

    def test_informational_and_skipped_steps_do_not_celebrate(self):
        self.controller.start('first_figure')
        self.assertFalse(self.controller.card.status.success)
        self.controller.skip()
        self.controller.skip()
        self.assertFalse(self.controller.card.status.success)
        self.go_to('finish')
        self.assertFalse(self.controller.card.status.success)

    def test_samples_mix_formats_and_are_reused_without_overwriting(self):
        from src.utils.image_proxy import image_format_name, is_supported_image
        samples = tutorials.make_samples()
        self.assertEqual(set(samples), set(tutorials.LESSONS))
        formats = {lesson: [image_format_name(path) for path in paths] for lesson, paths in samples.items()}
        self.assertEqual(formats['first_figure'], ['SVG', 'PNG', 'TIFF'])
        self.assertEqual(formats['text_sizes'], ['SVG', 'SVG', 'PNG'])
        every = [path for paths in samples.values() for path in paths]
        self.assertTrue(all(is_supported_image(path) and Path(path).is_file() for path in every))
        self.assertFalse(any(Path(path).name.endswith('.part') for path in Path(every[0]).parent.iterdir()))
        contents = {path: Path(path).read_bytes() for path in every}
        self.assertIn(b'synthetic data', contents[samples['first_figure'][0]])
        self.assertEqual(tutorials.make_samples(), samples)
        self.assertEqual(contents, {path: Path(path).read_bytes() for path in every})

    def test_format_is_reported_in_layers_inspector_and_status_bar(self):
        from src.app.i18n import tr
        from src.app.layers_panel import _ROLE_META
        self.controller.start('first_figure')
        self._complete_first_figure_setup()
        project = self.controller.tab.project
        self.window.layers_panel.refresh()
        badges = []
        root = self.window.layers_panel.tree.topLevelItem(0)
        for row in range(root.childCount()):
            badges.append(root.child(row).data(0, _ROLE_META))
        self.assertEqual(badges, ['SVG', 'PNG', 'TIFF'])

        inspector = self.window.inspector
        expected = {'.svg': 'SVG · vector', '.png': 'PNG · 1440×960 px', '.tiff': 'TIFF · 1440×960 px'}
        for cell in project.cells:
            item = self.controller.tab.scene.cell_items[cell.id]
            self.controller.tab.scene.clearSelection()
            item.setSelected(True)
            self.window._on_selection_changed()
            suffix = Path(cell.image_path).suffix.lower()
            self.assertEqual(inspector.format_value.text(), expected[suffix])
            self.assertTrue(inspector.format_value.toolTip())
            status = self.window.selection_info_label.text()
            self.assertIn(Path(cell.image_path).name, status)
            self.assertIn(expected[suffix].split(' · ')[0], status)

        set_language('zh')
        self.window.retranslate_ui()
        self.assertIn('位图', inspector.format_value.toolTip())
        self.assertIn('1440×960', inspector.format_value.text())
        inspector._populate_format_row(project.cells[0].to_dict())
        self.assertIn('矢量', inspector.format_value.text())
        self.assertEqual(inspector._sec_size_group.text(), tr('sec_size_group'))
        self.assertEqual(inspector._format_row_label.text(), tr('lbl_image_format'))

    def test_new_lessons_appear_in_center_both_languages(self):
        for language in ('en', 'zh'):
            set_language(language)
            self.controller.show_center()
            captions = [b.text() for b in self.controller.center.findChildren(QPushButton)]
            for key in ('first_figure', 'text_sizes', 'arrange_panels',
                        'labels_titles', 'publication',
                        'insets_scale_bars', 'size_groups'):
                self.assertIn(tutorials.lesson_title(key), captions)
            self.controller.center.close()
        set_language('en')

    def test_new_lessons_open_practice_tabs_with_samples_loaded(self):
        for key in ('arrange_panels', 'labels_titles', 'publication',
                    'insets_scale_bars', 'size_groups'):
            self.controller.start(key)
            practice = self.controller.tab
            self.assertIsNot(practice.project, self.original_tab.project)
            self.assertTrue(all(cell.image_path for cell in practice.project.cells))
            self.assertEqual(self.original_tab.project.to_dict(), self.original)
            self.controller.stop()
            index = self.window._tabs.index(practice)
            self.window._remove_tab(index)

    def test_arrange_panels_flow(self):
        self.controller.start('arrange_panels')
        project = self.controller.tab.project
        self.controller.next()
        self.assertEqual(self.controller.step.key, 'split')
        self.controller.perform_action()
        self.assertEqual(len(project.cells[2].children), 2)
        self.assertTrue(self.controller.ready())
        self.controller.next()

        self.assertEqual(self.controller.step.key, 'ratio')
        self.controller.perform_action()
        inspector = self.window.inspector
        self.assertTrue(inspector.subcell_group.isVisible())
        self.assertFalse(inspector.subcell_group._collapsed)
        self.assertTrue(inspector.subcell_ratio.isVisible())
        self.assertIs(self.controller.highlight.target, inspector.subcell_ratio)
        self.assertFalse(self.controller.ready())
        inspector.subcell_ratio.setValue(2.0)
        self.assertTrue(self.controller.ready())
        self.controller.next()

        self.assertEqual(self.controller.step.key, 'swap')
        first, second = project.cells[0].image_path, project.cells[1].image_path
        self.controller.perform_action()
        self.assertEqual(project.cells[0].image_path, second)
        self.assertEqual(project.cells[1].image_path, first)
        self.assertTrue(self.controller.ready())
        self.controller.perform_action()
        self.assertTrue(self.controller.ready(), 'a second click must not swap back')
        self.controller.next()

        self.assertEqual(self.controller.step.key, 'crop')
        self.assertFalse(self.controller.ready())
        cropped_cell = project.cells[0]
        # The crop-to-aspect helper needs the pixmap's real dimensions
        # (falls back to a 1:1 assumption otherwise, which is a no-op for a
        # square crop); the proxy loads it asynchronously.
        from src.utils.image_proxy import get_image_proxy
        proxy = get_image_proxy()
        for _ in range(100):
            if proxy.get_pixmap(cropped_cell.image_path) is not None:
                break
            self.app.processEvents()
            QTest.qWait(10)
        self.controller.perform_action()
        self.assertNotEqual(
            (cropped_cell.crop_left, cropped_cell.crop_top, cropped_cell.crop_right, cropped_cell.crop_bottom),
            (0.0, 0.0, 1.0, 1.0))
        self.assertTrue(self.controller.ready())
        self.controller.next()

        self.assertEqual(self.controller.step.key, 'fit_mode')
        self.controller.perform_action()
        self.assertTrue(inspector.fit_mode_combo.isVisible())
        self.assertIs(self.controller.highlight.target, inspector.fit_mode_combo)
        self.assertFalse(self.controller.ready())
        inspector.fit_mode_combo.setCurrentText('cover')
        self.assertTrue(self.controller.ready())
        self.controller.next()

        self.assertEqual(self.controller.step.key, 'freeform')
        self.window._act_bake.trigger()
        self.assertEqual(project.layout_mode, 'freeform')
        self.assertTrue(self.controller.ready())
        self.controller.next()

        self.assertEqual(self.controller.step.key, 'reposition')
        self.controller.perform_action()
        self.assertFalse(inspector.cell_group._collapsed)
        self.assertTrue(inspector.freeform_x.isVisible())
        self.assertFalse(self.controller.ready())
        inspector.freeform_x.setValue(inspector.freeform_x.value() + 5)
        self.assertTrue(self.controller.ready())
        self.controller.next()
        self.controller.next()
        self.assertEqual(self.window._settings.value('tutorials/v1/arrange_panels'), 'completed')
        self.assertEqual(self.original_tab.project.to_dict(), self.original)

    def test_reposition_accepts_manual_moves(self):
        self.controller.start('arrange_panels')
        project = self.controller.tab.project
        self.window._act_bake.trigger()
        self.go_to('reposition')
        self.assertFalse(self.controller.ready())
        project.cells[0].freeform_x_mm += 4
        self.assertTrue(self.controller.ready())

    def test_insets_scale_bars_practice_project_has_no_letterboxing(self):
        """The panels are dark end-to-end, so a light letterboxed margin
        would swallow the (default white) scale bar just as badly as a
        light panel background would."""
        from src.model.layout_engine import LayoutEngine
        from PyQt6.QtSvg import QSvgRenderer
        self.controller.start('insets_scale_bars')
        project = self.controller.tab.project
        self.assertTrue(project.rows[0].column_ratios, 'Auto Layout must have run to size columns to the images')
        rects = LayoutEngine.calculate_layout(project).cell_rects
        for cell in project.cells:
            renderer = QSvgRenderer(cell.image_path)
            size = renderer.defaultSize()
            image_ratio = size.width() / size.height()
            _x, _y, w, h = rects[cell.id]
            # Auto Layout rounds its intermediate ratios for cleaner numbers,
            # so this is a "close enough to avoid a visible margin" check,
            # not a floating-point-exact one.
            self.assertAlmostEqual(w / h, image_ratio, delta=0.1,
                                  msg='cell content must match the image aspect ratio — a mismatch is letterboxing')

    def test_default_pip_border_is_black_and_inset_content_is_bold(self):
        from src.model.data_model import PiPItem
        self.assertEqual(PiPItem().border_color, '#000000')
        self.controller.start('insets_scale_bars')
        self.controller.next()
        self.controller.perform_action()
        pip = next(p for c in self.controller.tab.project.cells for p in c.pip_items
                  if p.pip_type == 'external')
        self.assertEqual(pip.border_color, '#000000')
        self.assertEqual(pip.image_path, tutorials.pip_icon_path())
        self.assertNotIn(pip.image_path, self.controller.paths,
                         'the inset sample must not be the same hard-to-shrink line chart used elsewhere')

    def test_insets_scale_bars_flow(self):
        self.controller.start('insets_scale_bars')
        project = self.controller.tab.project
        self.controller.next()
        self.assertEqual(self.controller.step.key, 'add_inset')
        self.assertFalse(self.controller.ready())
        self.controller.perform_action()
        pip = next((p for c in project.cells for p in c.pip_items if p.pip_type == 'external'), None)
        self.assertIsNotNone(pip)
        self.assertEqual(pip.image_path, tutorials.pip_icon_path())
        self.assertTrue(self.controller.ready())
        self.controller.next()

        self.assertEqual(self.controller.step.key, 'resize_inset')
        self.controller.perform_action()
        inspector = self.window.inspector
        self.assertTrue(inspector.pip_group.isVisible())
        self.assertFalse(inspector.pip_group._collapsed)
        self.assertTrue(inspector.pip_w.isVisible())
        self.assertIs(self.controller.highlight.target, inspector.pip_w)
        self.assertFalse(self.controller.ready())
        inspector.pip_w.setValue(inspector.pip_w.value() + 5)
        self.assertTrue(self.controller.ready())
        self.controller.next()

        self.assertEqual(self.controller.step.key, 'scale_bar')
        self.controller.perform_action()
        self.assertEqual(self.window.inspector._current_item_type, 'cell')
        self.assertTrue(inspector.scale_bar_group.isVisible())
        self.assertFalse(inspector.scale_bar_group._collapsed)
        self.assertIs(self.controller.highlight.target, inspector.scale_bar_enabled)
        self.assertFalse(self.controller.ready())
        inspector.scale_bar_enabled.setChecked(True)
        self.assertTrue(project.cells[0].scale_bar_enabled)
        self.assertTrue(self.controller.ready())
        self.controller.next()
        self.controller.next()
        self.assertEqual(self.window._settings.value('tutorials/v1/insets_scale_bars'), 'completed')
        self.assertEqual(self.original_tab.project.to_dict(), self.original)

    def test_resize_inset_accepts_manual_moves(self):
        self.controller.start('insets_scale_bars')
        self.go_to('add_inset')
        self.controller.perform_action()
        self.go_to('resize_inset')
        self.assertFalse(self.controller.ready())
        pip = next(p for c in self.controller.tab.project.cells for p in c.pip_items
                  if p.pip_type == 'external')
        pip.w += 0.05
        self.assertTrue(self.controller.ready())

    def test_size_groups_flow(self):
        self.controller.start('size_groups')
        project = self.controller.tab.project
        self.controller.next()
        self.assertEqual(self.controller.step.key, 'create_group')
        self.assertFalse(self.controller.ready())
        self.controller.perform_action()
        self.assertEqual(len(project.size_groups), 1)
        group = project.size_groups[0]
        self.assertEqual(project.cells[0].size_group_id, group.id)
        self.assertEqual(project.cells[1].size_group_id, group.id)
        self.assertIsNone(project.cells[2].size_group_id)
        self.assertTrue(self.controller.ready())
        self.controller.next()

        self.assertEqual(self.controller.step.key, 'pin_size')
        self.controller.perform_action()
        inspector = self.window.inspector
        self.assertTrue(inspector.cell_group.isVisible())
        self.assertFalse(inspector.cell_group._collapsed)
        self.assertTrue(inspector.size_group_pinned_w.isVisible())
        self.assertIs(self.controller.highlight.target, inspector.size_group_pinned_w)
        self.assertFalse(self.controller.ready())
        inspector.size_group_pinned_w.setValue(40.0)
        self.assertGreater(group.pinned_width_mm, 0)
        self.assertTrue(self.controller.ready())
        self.controller.next()

        self.assertEqual(self.controller.step.key, 'add_member')
        self.controller.perform_action()
        self.assertEqual(project.cells[2].size_group_id, group.id)
        self.assertTrue(self.controller.ready())
        self.controller.next()
        self.controller.next()
        self.assertEqual(self.window._settings.value('tutorials/v1/size_groups'), 'completed')
        self.assertEqual(self.original_tab.project.to_dict(), self.original)

    def test_labels_titles_flow(self):
        self.controller.start('labels_titles')
        project = self.controller.tab.project
        self.controller.next()
        self.assertEqual(self.controller.step.key, 'panel_letters')
        self.window._act_auto_label_incell.trigger()
        self.assertTrue(self.controller.ready())
        self.controller.next()

        self.assertEqual(self.controller.step.key, 'shared_top')
        self.controller.perform_action()
        self.window._sync_group_label_menu()
        top_action = self.window._group_label_actions[0]
        self.assertTrue(top_action.isEnabled())
        top_action.trigger()
        self.assertTrue(any(g.side == 'top' for g in project.group_labels))
        self.assertTrue(self.controller.ready())
        self.controller.next()

        self.assertEqual(self.controller.step.key, 'shared_row')
        self.controller.perform_action()
        self.window._sync_group_label_menu()
        left_action = self.window._group_label_actions[2]
        self.assertTrue(left_action.isEnabled())
        left_action.trigger()
        self.assertTrue(any(g.side == 'left' for g in project.group_labels))
        self.assertTrue(self.controller.ready())
        self.controller.next()

        self.assertEqual(self.controller.step.key, 'rename')
        self.controller.perform_action()
        inspector = self.window.inspector
        self.assertFalse(inspector.group_label_group._collapsed)
        self.assertTrue(inspector.gl_text_edit.isVisible())
        self.assertIs(self.controller.highlight.target, inspector.gl_text_edit)
        self.assertFalse(self.controller.ready())
        inspector.gl_text_edit.setText('Day 7')
        inspector.gl_text_edit.editingFinished.emit()
        label = next(g for g in project.group_labels if g.side == 'top')
        self.assertEqual(label.text, 'Day 7')
        self.assertTrue(self.controller.ready())
        self.controller.next()
        self.controller.next()
        self.assertEqual(self.window._settings.value('tutorials/v1/labels_titles'), 'completed')
        self.assertEqual(self.original_tab.project.to_dict(), self.original)

    def test_group_label_targets_point_at_the_edit_menu(self):
        self.controller.start('labels_titles')
        self.go_to('shared_top')
        self.controller.perform_action()
        self.controller.refresh()
        highlight = self.controller.highlight
        self.assertIsNot(highlight.target, self.window.view.viewport())
        # The action lives in a submenu, so the highlight lands on the
        # menubar entry whose menu chain contains it — the Edit menu.
        self.assertIs(highlight.target, self.window.menuBar())
        edit_entry = next(entry for entry in self.window.menuBar().actions()
                          if entry.menu() is not None and
                          self.controller._menu_holds(entry.menu(), self.window._group_label_actions[0]))
        self.assertTrue(edit_entry.menu().title())

    def test_publication_flow(self):
        self.controller.start('publication')
        project = self.controller.tab.project
        self.assertEqual(project.dpi, 300)
        self.controller.next()

        self.assertEqual(self.controller.step.key, 'dpi')
        inspector = self.window.inspector
        inspector.project_group.set_collapsed(True, animate=False)
        self.controller.perform_action()
        self.assertFalse(inspector.project_group._collapsed)
        self.assertTrue(inspector.dpi_spin.isVisible())
        self.assertIs(self.controller.highlight.target, inspector.dpi_spin)
        self.assertFalse(self.controller.ready())
        inspector.dpi_spin.setValue(600)
        self.assertEqual(project.dpi, 600)
        self.assertTrue(self.controller.ready())
        self.controller.next()

        self.assertEqual(self.controller.step.key, 'export_region')
        self.assertIsNone(project.export_region)
        self.window._act_set_export_region.trigger()
        self.assertIsNotNone(project.export_region)
        self.assertTrue(self.controller.ready())
        self.controller.next()

        self.assertEqual(self.controller.step.key, 'export')
        with patch('src.app.main_window.QFileDialog.getSaveFileName', return_value=('', '')):
            self.window._act_export_pdf.trigger()
        self.assertTrue(self.controller.ready(), 'cancelling the dialog still counts — the step teaches the menu')
        self.controller.next()

        self.assertEqual(self.controller.step.key, 'verify')
        self.window._act_preview_mode.trigger()
        self.assertTrue(self.controller.tab.scene.preview_mode)
        self.assertTrue(self.controller.ready())
        self.controller.next()
        self.controller.next()
        self.assertEqual(self.window._settings.value('tutorials/v1/publication'), 'completed')
        self.assertEqual(self.original_tab.project.to_dict(), self.original)

    def test_dpi_step_survives_an_active_cell_selection(self):
        self.controller.start('publication')
        self.go_to('dpi')
        self.controller._select_cells(0)
        self.controller.refresh()
        # A selected cell hides Project Settings entirely; the highlight
        # cannot point at the field until the section is back on screen.
        self.assertIsNot(self.controller.highlight.target,
                         self.window.inspector.dpi_spin)
        self.controller.perform_action()
        self.assertTrue(self.window.inspector.dpi_spin.isVisible())
        self.assertIs(self.controller.highlight.target, self.window.inspector.dpi_spin)

    def test_format_row_handles_missing_and_empty_panels(self):
        self.controller.start('text_sizes')
        project = self.controller.tab.project
        inspector = self.window.inspector
        missing = project.cells[2]
        missing.image_path = str(Path(self.temp.name) / 'gone.png')
        inspector._populate_format_row(missing.to_dict())
        self.assertIn('PNG', inspector.format_value.text())
        self.assertIn('not found', inspector.format_value.text())
        inspector._populate_format_row({'image_path': None, 'is_placeholder': True})
        self.assertEqual(inspector.format_value.text(), 'No image')
        inspector._populate_format_row({'image_path': 'diagram.unknownext'})
        self.assertIn('UNKNOWNEXT', inspector.format_value.text())

    def test_raster_samples_open_as_declared_formats(self):
        from PIL import Image
        samples = tutorials.make_samples()
        expected = {'.png': 'PNG', '.tiff': 'TIFF'}
        checked = 0
        for path in {path for paths in samples.values() for path in paths}:
            suffix = Path(path).suffix.lower()
            if suffix in expected:
                with Image.open(path) as image:
                    self.assertEqual(image.format, expected[suffix])
                    self.assertEqual(image.size, (1440, 960))
                checked += 1
        self.assertEqual(checked, 3)

    def test_practice_labels_are_small_relative_to_the_panels(self):
        from src.model.layout_engine import LayoutEngine
        self.controller.start('arrange_panels')
        project = self.controller.tab.project
        self.assertLess(project.label_font_size, Project().label_font_size)
        self.assertEqual(len(project.cells), 3)
        self.window._act_auto_label_incell.trigger()
        labels = [item for item in project.text_items if item.subtype == 'numbering']
        self.assertEqual(len(labels), 3)
        self.assertTrue(all(label.font_size_pt == project.label_font_size for label in labels))
        rects = LayoutEngine.calculate_layout(project).cell_rects
        for label in labels:
            _x, _y, panel_w, panel_h = rects[label.parent_id]
            width_mm, height_mm = _rendered_text_mm(label)
            self.assertLess(height_mm, panel_h * 0.12, 'panel letters should not dominate the panel')
            self.assertLess(width_mm, panel_w * 0.12)
            self.assertGreater(height_mm, 2.0, 'panel letters must stay legible in print')

    def test_default_label_size_would_overpower_the_practice_panels(self):
        from src.model.layout_engine import LayoutEngine
        self.controller.start('arrange_panels')
        project = self.controller.tab.project
        project.label_font_size = Project().label_font_size
        self.window._act_auto_label_incell.trigger()
        label = next(item for item in project.text_items if item.subtype == 'numbering')
        _x, _y, _w, panel_h = LayoutEngine.calculate_layout(project).cell_rects[label.parent_id]
        self.assertGreater(_rendered_text_mm(label)[1], panel_h * 0.3)


if __name__ == '__main__':
    unittest.main()
