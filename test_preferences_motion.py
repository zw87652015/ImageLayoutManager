import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt6.QtCore import QAbstractAnimation, QEvent, QPointF, QRectF, QSettings
from PyQt6.QtGui import QColor
from PyQt6.QtTest import QSignalSpy
from PyQt6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QLabel

from src.app import motion, preferences_dialog
from src.app.i18n import current_language, set_language, tr
from src.app.inspector import CollapsibleSection, LockButton
from src.canvas.cell_item import CellItem
from src.canvas.group_label_item import GroupLabelItem


class PreferencesMotionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.settings_path = str(Path(self.temp.name) / 'preferences.ini')
        self.settings = QSettings(self.settings_path, QSettings.Format.IniFormat)
        self.settings.setFallbacksEnabled(False)
        self._patch('src.app.preferences_dialog._read_settings', return_value=self.settings)
        self._patch('src.app.motion.QSettings', return_value=self.settings)
        self._patch('src.app.motion.system_reduced_motion', return_value=False)
        self.policy = motion.MotionPolicy()
        self._patch('src.app.motion.motion_policy', return_value=self.policy)
        self.addCleanup(set_language, current_language())
        self.addCleanup(self._flush_deletions)

    def _patch(self, target, **kwargs):
        patcher = patch(target, **kwargs)
        result = patcher.start()
        self.addCleanup(patcher.stop)
        return result

    def _flush_deletions(self):
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def dialog(self, main_window=None):
        dialog = preferences_dialog.PreferencesDialog(main_window)
        self.addCleanup(dialog.deleteLater)
        self.addCleanup(dialog.close)
        return dialog

    def section(self):
        section = CollapsibleSection('Motion test')
        section._form.addRow('Value', QLabel('Content'))
        section.resize(320, section.sizeHint().height())
        section.show()
        self.app.processEvents()
        self.addCleanup(section.deleteLater)
        self.addCleanup(section.close)
        return section

    def cell(self):
        with patch('src.canvas.cell_item.get_image_proxy', return_value=Mock()):
            cell = CellItem('test-cell')
        cell.setRect(QRectF(0, 0, 80, 60))
        self.addCleanup(cell.end_ext_drag)
        return cell

    def group_label(self):
        item = GroupLabelItem('test-label')
        self.addCleanup(item.deleteLater)
        return item

    def test_default_motion_is_standard_and_opening_does_not_write(self):
        dialog = self.dialog()
        self.assertEqual(dialog._motion_combo.currentData(), 'standard')
        self.assertEqual([dialog._motion_combo.itemData(i) for i in range(3)],
                         ['standard', 'reduced', 'off'])
        self.assertFalse(dialog._apply_btn.isEnabled())
        self.assertEqual(dialog._applied_status.text(), '')
        self.assertEqual(self.settings.allKeys(), [])
        self.assertEqual(self.policy.mode, 'standard')

    def test_selection_is_staged_and_cancel_discards_it(self):
        changed = QSignalSpy(self.policy.changed)
        dialog = self.dialog()
        dialog._motion_combo.setCurrentIndex(dialog._motion_combo.findData('off'))
        self.assertTrue(dialog._apply_btn.isEnabled())
        self.assertEqual(self.policy.mode, 'standard')
        self.assertFalse(self.settings.contains('ui/motion_mode'))
        dialog.reject()
        self.assertEqual(len(changed), 0)
        self.assertEqual(self.settings.allKeys(), [])
        self.assertEqual(self.dialog()._motion_combo.currentData(), 'standard')

    def test_closing_without_apply_does_not_write(self):
        self.settings.setValue('ui/motion_mode', 'reduced')
        dialog = self.dialog()
        dialog._motion_combo.setCurrentIndex(dialog._motion_combo.findData('off'))
        dialog.close()
        self.assertEqual(self.settings.value('ui/motion_mode'), 'reduced')
        self.assertEqual(self.policy.mode, 'standard')

    def test_apply_without_main_window_persists_and_updates_policy(self):
        dialog = self.dialog()
        for mode in ('reduced', 'off', 'standard'):
            with self.subTest(mode=mode):
                dialog._motion_combo.setCurrentIndex(dialog._motion_combo.findData(mode))
                with patch.object(preferences_dialog, 'set_motion_mode',
                                  wraps=motion.set_motion_mode) as apply_mode:
                    dialog._apply_btn.click()
                    apply_mode.assert_called_once_with(mode)
                self.settings.sync()
                saved = QSettings(self.settings_path, QSettings.Format.IniFormat)
                saved.setFallbacksEnabled(False)
                self.assertEqual(saved.value('ui/motion_mode'), mode)
                self.assertEqual(self.policy.mode, mode)
                self.assertFalse(dialog._apply_btn.isEnabled())
                self.assertEqual(dialog._applied_status.text(), tr('prefs_applied'))

    def test_ok_applies_and_accepts(self):
        dialog = self.dialog()
        dialog._motion_combo.setCurrentIndex(dialog._motion_combo.findData('off'))
        buttons = dialog.findChild(QDialogButtonBox)
        buttons.button(QDialogButtonBox.StandardButton.Ok).click()
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
        self.assertEqual(self.settings.value('ui/motion_mode'), 'off')
        self.assertEqual(self.policy.mode, 'off')

    def test_cancel_after_apply_keeps_only_applied_mode(self):
        dialog = self.dialog()
        dialog._motion_combo.setCurrentIndex(dialog._motion_combo.findData('reduced'))
        dialog._apply_btn.click()
        dialog._motion_combo.setCurrentIndex(dialog._motion_combo.findData('off'))
        self.assertEqual(dialog._applied_status.text(), '')
        dialog.reject()
        self.assertEqual(self.settings.value('ui/motion_mode'), 'reduced')
        self.assertEqual(self.policy.mode, 'reduced')
        self.assertEqual(self.dialog()._motion_combo.currentData(), 'reduced')

    def test_invalid_saved_mode_falls_back_without_writing(self):
        self.settings.setValue('ui/motion_mode', 'invalid')
        dialog = self.dialog()
        self.assertEqual(dialog._motion_combo.currentData(), 'standard')
        self.assertEqual(self.settings.value('ui/motion_mode'), 'invalid')
        self.assertFalse(dialog._apply_btn.isEnabled())

    def test_other_controls_keep_apply_semantics(self):
        host = SimpleNamespace(_tabs=[], _apply_theme=Mock(), retranslate_ui=Mock())
        dialog = self.dialog(host)
        dialog._undo_spin.setValue(350)
        dialog._ocr_command.setText('  test-ocr --json {image}  ')
        self.assertTrue(dialog._apply_btn.isEnabled())
        self.assertFalse(self.settings.contains('max_history'))
        host._apply_theme.assert_not_called()
        dialog._apply_btn.click()
        self.assertEqual(self.settings.value('max_history'), 350)
        self.assertEqual(self.settings.value('ocr_command'), 'test-ocr --json {image}')
        host._apply_theme.assert_called_once_with(dialog._theme_combo.currentData())
        dialog._undo_spin.setValue(400)
        self.assertTrue(dialog._apply_btn.isEnabled())
        self.assertEqual(dialog._applied_status.text(), '')
        self.assertEqual(self.settings.value('max_history'), 350)

    def test_motion_labels_and_applied_status_use_translations(self):
        for language in ('en', 'zh'):
            with self.subTest(language=language):
                set_language(language)
                dialog = self.dialog()
                for index, mode in enumerate(('standard', 'reduced', 'off')):
                    self.assertEqual(dialog._motion_combo.itemText(index), tr('prefs_motion_' + mode))
                self.assertEqual(dialog._motion_combo.toolTip(), tr('prefs_motion_hint'))
                labels = [label.text() for label in dialog.findChildren(QLabel)]
                self.assertIn(tr('prefs_motion'), labels)
                dialog._on_apply()
                self.assertEqual(dialog._applied_status.text(), tr('prefs_applied'))

    def test_collapsible_off_and_reduced_finish_exactly(self):
        section = self.section()
        for mode in ('off', 'reduced'):
            with self.subTest(mode=mode):
                motion.set_motion_mode(mode)
                section.set_collapsed(True)
                self.assertIsNone(section._anim)
                self.assertTrue(section._body.isHidden())
                self.assertEqual(section._body.maximumHeight(), 0)
                self.assertEqual(section._chevron.text(), '\u25b8')
                section.set_collapsed(False)
                self.assertIsNone(section._anim)
                self.assertFalse(section._body.isHidden())
                self.assertEqual(section._body.maximumHeight(), 16777215)
                self.assertEqual(section._chevron.text(), '\u25be')

    def test_collapsible_rapid_reversal_ignores_stale_completion(self):
        section = self.section()
        section.set_collapsed(True)
        old = section._anim
        self.assertEqual(old.duration(), 180)
        old.setCurrentTime(80)
        section.set_collapsed(False)
        current = section._anim
        old.finished.emit()
        self.assertIs(section._anim, current)
        self.assertFalse(section._body.isHidden())
        current.setCurrentTime(current.duration())
        self.assertIsNone(section._anim)
        self.assertFalse(section._body.isHidden())
        self.assertEqual(section._body.maximumHeight(), 16777215)
        section.set_collapsed(True)
        section.set_collapsed(True, animate=False)
        self.assertIsNone(section._anim)
        self.assertTrue(section._body.isHidden())
        self.assertEqual(section._body.maximumHeight(), 0)

    def test_apply_off_settles_live_existing_animations(self):
        section = self.section()
        section.set_collapsed(True)
        section._anim.setCurrentTime(50)
        cell = self.cell()
        cell.begin_ext_drag(True)
        cell.update_ext_drag_pos(cell._pip_zone_rect().center())
        cell._pip_anim.setCurrentTime(50)
        label = self.group_label()
        target = QRectF(10, 80, 60, 10)
        label.set_band(target, None)
        label.animate_from(QRectF(0, 0, 40, 10))
        label._anim.setCurrentTime(50)
        dialog = self.dialog()
        dialog._motion_combo.setCurrentIndex(dialog._motion_combo.findData('off'))
        self.assertIsNotNone(section._anim)
        self.assertIsNotNone(cell._pip_anim)
        self.assertIsNotNone(label._anim)
        dialog._apply_btn.click()
        self.assertIsNone(section._anim)
        self.assertTrue(section._body.isHidden())
        self.assertEqual(section._body.maximumHeight(), 0)
        self.assertIsNone(cell._pip_anim)
        self.assertEqual(cell._pip_drop_indicator_t, 1.0)
        self.assertIsNone(label._anim)
        self.assertEqual(label.band_scene_rect(), target)
        self.assertEqual(label.pos(), target.topLeft())

    def test_lock_feedback_preserves_check_state_and_geometry(self):
        button = LockButton()
        button.setCheckable(True)
        button.setChecked(True)
        button.resize(28, 28)
        self.addCleanup(button.deleteLater)
        geometry = button.geometry()
        for mode in ('standard', 'reduced', 'off'):
            with self.subTest(mode=mode):
                motion.set_motion_mode(mode)
                button.play_lock_burst(QColor('#0891B2'))
                self.assertEqual(button._anim.duration(), motion.motion_duration(160))
                if mode != 'off':
                    button._anim.setCurrentTime(40)
                    button.grab()
                    motion.set_motion_mode('off')
                self.assertEqual(button.burst, 1.0)
                self.assertEqual(button._anim.state(), QAbstractAnimation.State.Stopped)
                self.assertTrue(button.isChecked())
                self.assertEqual(button.geometry(), geometry)

    def test_pip_off_hover_and_exit_have_exact_values(self):
        motion.set_motion_mode('off')
        cell = self.cell()
        cell.begin_ext_drag(True)
        cell.update_ext_drag_pos(cell._pip_zone_rect().center())
        self.assertTrue(cell._pip_zone_hovered)
        self.assertEqual(cell._pip_drop_indicator_t, 1.0)
        self.assertIsNone(cell._pip_anim)
        cell.update_ext_drag_pos(QPointF(1, 50))
        self.assertFalse(cell._pip_zone_hovered)
        self.assertEqual(cell._pip_drop_indicator_t, 0.0)
        self.assertIsNone(cell._pip_anim)
        cell.end_ext_drag()
        self.assertFalse(cell._ext_drag_active)
        self.assertEqual(cell._pip_drop_indicator_t, 0.0)

    def test_pip_reversal_and_drag_restart_cancel_old_animation(self):
        cell = self.cell()
        cell.begin_ext_drag(True)
        cell._animate_pip_indicator(True)
        old = cell._pip_anim
        old.setCurrentTime(50)
        cell._animate_pip_indicator(False)
        current = cell._pip_anim
        old.finished.emit()
        self.assertIs(cell._pip_anim, current)
        motion.set_motion_mode('reduced')
        self.assertEqual(cell._pip_drop_indicator_t, 0.0)
        self.assertIsNone(cell._pip_anim)
        cell._animate_pip_indicator(True)
        self.assertEqual(cell._pip_anim.duration(), motion.motion_duration(160))
        self.assertGreater(cell._pip_anim.duration(), 0)
        cell.begin_ext_drag(True)
        motion.set_motion_mode('off')
        self.assertEqual(cell._pip_drop_indicator_t, 0.0)
        self.assertIsNone(cell._pip_anim)

    def test_group_label_off_and_reduced_match_layout_rect(self):
        item = self.group_label()
        for mode in ('off', 'reduced'):
            with self.subTest(mode=mode):
                motion.set_motion_mode(mode)
                target = QRectF(20, 70, 50, 12)
                item.set_band(target, None)
                item.animate_from(QRectF(1, 2, 30, 10))
                self.assertIsNone(item._anim)
                self.assertEqual(item.band_scene_rect(), target)
                self.assertEqual(item.pos(), target.topLeft())
                self.assertEqual(item.local_band(), QRectF(0, 0, 50, 12))

    def test_group_label_retargeting_preserves_final_layout(self):
        item = self.group_label()
        target = QRectF(20, 70, 50, 12)
        item.set_band(target, None)
        item.animate_from(QRectF(1, 2, 30, 10))
        old = item._anim
        old.setCurrentTime(50)
        item.animate_from(item.band_scene_rect())
        current = item._anim
        old.finished.emit()
        self.assertIs(item._anim, current)
        motion.set_motion_mode('off')
        self.assertEqual(item.band_scene_rect(), target)
        motion.set_motion_mode('standard')
        item.animate_from(QRectF(1, 2, 30, 10))
        item._anim.setCurrentTime(50)
        replacement = QRectF(8, 9, 25, 15)
        item.set_band(replacement, None)
        motion.set_motion_mode('off')
        self.assertIsNone(item._anim)
        self.assertEqual(item.band_scene_rect(), replacement)
        self.assertEqual(item.pos(), replacement.topLeft())


if __name__ == '__main__':
    unittest.main()
