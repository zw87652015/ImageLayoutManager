import copy
import os
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt6.QtCore import QAbstractAnimation, QEvent, QPoint, QPointF, Qt, QEasingCurve
from PyQt6.QtGui import QFontDatabase, QKeyEvent, QMouseEvent, QUndoStack, QWheelEvent
from PyQt6.QtTest import QSignalSpy, QTest
from PyQt6.QtWidgets import QApplication

from src.app.commands import MultiSwapCellsCommand, SwapCellsCommand
from src.app.motion import motion_duration, motion_policy, set_motion_mode
from src.canvas.canvas_scene import CanvasScene
from src.canvas.canvas_view import CanvasView
from src.model.data_model import Cell, Project
from src.model.layout_engine import LayoutEngine


class CanvasMotionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        if not QFontDatabase.families() and os.name == 'nt':
            QFontDatabase.addApplicationFont(str(Path(os.environ['WINDIR']) / 'Fonts' / 'arial.ttf'))

    def setUp(self):
        self.policy = motion_policy()
        self.saved_mode = self.policy.mode
        self.saved_system_reduced = self.policy.system_reduced
        self.os_motion = patch('src.app.motion.system_reduced_motion', return_value=False)
        self.os_motion.start()
        set_motion_mode('standard')
        self.cells = [Cell(row_index=i // 2, col_index=i % 2,
                           freeform_x_mm=10.1256789 + (i % 2) * 75.25,
                           freeform_y_mm=12.8754321 + (i // 2) * 75.25,
                           freeform_w_mm=40.1234567, freeform_h_mm=30.9876543,
                           padding_left=1.23456789 + i,
                           crop_left=0.0123456789, crop_right=0.987654321)
                      for i in range(4)]
        self.project = Project(layout_mode='freeform', cells=self.cells)
        self.scene = CanvasScene()
        self.scene.set_project(self.project)
        self.view = CanvasView(self.scene)
        self.view.resize(800, 600)
        self.view.show()
        self.app.processEvents()
        self.manager = self.scene.drag_manager
        self.stack = QUndoStack()
        self.scene.cell_swapped.connect(self.commit_single)
        self.scene.multi_cells_swapped.connect(self.commit_multi)
        self.swaps = QSignalSpy(self.scene.cell_swapped)
        self.multi_swaps = QSignalSpy(self.scene.multi_cells_swapped)
        self.geometry_changes = QSignalSpy(self.scene.cell_freeform_geometry_changed)

    def tearDown(self):
        self.manager._cleanup()
        self.view._cancel_zoom()
        self.view.close()
        self.view.deleteLater()
        self.scene.deleteLater()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        set_motion_mode(self.saved_mode)
        self.policy.system_reduced = self.saved_system_reduced
        self.os_motion.stop()

    def commit_single(self, source, target):
        self.stack.push(SwapCellsCommand(self.project.find_cell_by_id(source),
                                        self.project.find_cell_by_id(target),
                                        self.project, self.scene.refresh_layout))

    def commit_multi(self, sources, targets):
        self.stack.push(MultiSwapCellsCommand(
            [self.project.find_cell_by_id(cid) for cid in sources],
            [self.project.find_cell_by_id(cid) for cid in targets],
            self.project, self.scene.refresh_layout))

    def item(self, index):
        return self.scene.cell_items[self.cells[index].id]

    def center(self, index):
        return self.item(index).mapToScene(self.item(index).rect().center())

    def start_drag(self, index=0):
        source = self.item(index)
        position = source.pos() + QPointF(2.3456789, 5.4321987)
        source.grabMouse()
        self.manager.start_drag(source, position)
        return position

    def assert_point(self, actual, expected, places=9):
        self.assertAlmostEqual(actual.x(), expected.x(), places=places)
        self.assertAlmostEqual(actual.y(), expected.y(), places=places)

    def assert_idle(self):
        self.assertFalse(self.manager.is_active)
        self.assertFalse(self.manager._animating)
        self.assertIsNone(self.manager._anim)
        self.assertIsNone(self.manager._ghost)
        self.assertFalse(self.manager._timer.isActive())
        for name in ('_lift_anims', '_highlight_anims', '_highlights',
                     '_retiring_highlights', '_swap_slide_anims', '_swap_slide_pairs',
                     '_swap_target_opacities'):
            self.assertEqual(getattr(self.manager, name), [], name)
        for item in self.scene.cell_items.values():
            self.assertEqual(item.opacity(), 1.0)
        self.assertIsNone(self.manager._view)
        self.assertTrue(self.view.viewport().updatesEnabled())

    def finish_zoom(self):
        anim = self.view._zoom_anim
        if anim is not None:
            anim.setCurrentTime(anim.duration())
        self.assertIsNone(self.view._zoom_anim)

    def wheel(self, angle=120, pixels=None, control=True, phase=Qt.ScrollPhase.NoScrollPhase,
              anchor=QPointF(231.125, 187.875)):
        event = QWheelEvent(anchor, anchor, pixels or QPoint(), QPoint(0, angle),
                            Qt.MouseButton.NoButton,
                            Qt.KeyboardModifier.ControlModifier if control else Qt.KeyboardModifier.NoModifier,
                            phase, False)
        self.view.wheelEvent(event)
        self.assertTrue(event.isAccepted())

    def test_policy_durations(self):
        for mode, feedback, spatial in [('standard', 140, 140), ('reduced', 70, 0), ('off', 0, 0)]:
            with self.subTest(mode=mode):
                set_motion_mode(mode)
                self.assertEqual(motion_duration(140), feedback)
                self.assertEqual(motion_duration(140, spatial=True), spatial)

    def test_ghost_tracks_original_grab_point_without_lift_or_tilt(self):
        before = copy.deepcopy(self.project.to_dict())
        layout = LayoutEngine.calculate_layout(self.project)
        for mode in ('standard', 'reduced', 'off'):
            with self.subTest(mode=mode):
                set_motion_mode(mode)
                initial = self.start_drag()
                ghost = self.manager._ghost
                grabbed = ghost.mapFromScene(initial)
                start_pos = ghost.pos()
                for delta in (QPointF(0.0001234, 0.0005678), QPointF(75.1234567, -12.7654321),
                              QPointF(-25.9876543, 30.1234567)):
                    self.manager._on_mouse_move(initial + delta)
                    self.assert_point(ghost.pos(), start_pos + delta)
                    self.assert_point(ghost.mapToScene(grabbed), initial + delta)
                    self.assertEqual(ghost.scale(), self.manager._base_scale)
                    self.assertEqual(self.manager._ghost_scale_factor, 1.0)
                    self.assertEqual(ghost.rotation(), 0.0)
                    self.assertFalse(self.manager._timer.isActive())
                for anim in list(self.manager._lift_anims):
                    anim.setCurrentTime(anim.duration())
                self.assertEqual(self.manager._lift_anims, [])
                self.assertEqual(ghost.opacity(), self.manager.GHOST_OPACITY)
                self.assertEqual(self.project.to_dict(), before)
                self.assertEqual(LayoutEngine.calculate_layout(self.project).cell_rects, layout.cell_rects)
                self.manager._cleanup()
                self.assert_idle()
        self.assertEqual(self.stack.count(), 0)
        self.assertEqual(len(self.geometry_changes), 0)

    def test_drop_commits_once_in_all_modes_and_undo_restores_precision(self):
        for mode in ('standard', 'reduced', 'off'):
            with self.subTest(mode=mode):
                set_motion_mode(mode)
                before = copy.deepcopy(self.project.to_dict())
                positions = {cid: QPointF(item.pos()) for cid, item in self.scene.cell_items.items()}
                swap_count = len(self.swaps)
                self.start_drag()
                self.manager._on_mouse_release(self.center(1))
                anim = self.manager._anim
                if mode == 'standard':
                    self.assertIsNotNone(anim)
                    finished = QSignalSpy(anim.finished)
                    self.assertEqual(anim.easingCurve().type(), QEasingCurve.Type.OutCubic)
                    for slide in self.manager._swap_slide_anims:
                        slide.setCurrentTime(slide.duration() // 2)
                    anim.setCurrentTime(anim.duration() // 2)
                    self.assertEqual(self.project.to_dict(), before)
                    self.assertEqual(len(self.swaps), swap_count)
                    for cid, point in positions.items():
                        self.assert_point(self.scene.cell_items[cid].pos(), point)
                    self.assertTrue(all(snapshot not in self.scene.cell_items.values()
                                        for snapshot, _ in self.manager._swap_slide_pairs))
                    anim.setCurrentTime(anim.duration())
                    self.assertEqual(len(finished), 1)
                    anim.finished.emit()
                self.assert_idle()
                self.manager._on_mouse_release(self.center(1))
                self.manager._on_drop_finished([self.cells[0].id], [self.cells[1].id])
                self.assertEqual(len(self.swaps), swap_count + 1)
                self.assertEqual(self.stack.count(), 1)
                self.assertNotEqual(self.project.to_dict(), before)
                for cid, point in positions.items():
                    self.assert_point(self.scene.cell_items[cid].pos(), point)
                self.stack.undo()
                self.assertEqual(self.project.to_dict(), before)
                self.stack.clear()
        self.assertEqual(len(self.geometry_changes), 0)

    def test_multi_drop_is_one_undo_command(self):
        for mode in ('standard', 'reduced', 'off'):
            with self.subTest(mode=mode):
                set_motion_mode(mode)
                self.scene.clearSelection()
                self.item(0).setSelected(True)
                self.item(1).setSelected(True)
                before = copy.deepcopy(self.project.to_dict())
                count = len(self.multi_swaps)
                self.start_drag()
                self.manager._on_mouse_release(self.center(2))
                if self.manager._anim is not None:
                    self.manager._anim.setCurrentTime(self.manager._anim.duration())
                self.assert_idle()
                self.assertEqual(len(self.multi_swaps), count + 1)
                self.assertEqual(self.stack.count(), 1)
                self.assertEqual(self.multi_swaps[-1],
                                 [[self.cells[0].id, self.cells[1].id],
                                  [self.cells[2].id, self.cells[3].id]])
                self.stack.undo()
                self.assertEqual(self.project.to_dict(), before)
                self.stack.clear()

    def test_cancel_is_nonovershooting_and_never_commits(self):
        before = copy.deepcopy(self.project.to_dict())
        for mode in ('standard', 'reduced', 'off'):
            with self.subTest(mode=mode):
                set_motion_mode(mode)
                self.start_drag()
                self.manager._on_mouse_release(QPointF(-123.456789, -98.7654321))
                anim = self.manager._anim
                if anim is not None:
                    finished = QSignalSpy(anim.finished)
                    self.assertEqual(anim.easingCurve().type(), QEasingCurve.Type.OutCubic)
                    start, end = self.manager._anim_start, self.manager._anim_end
                    for fraction in (0.1, 0.4, 0.8, 0.95):
                        anim.setCurrentTime(int(anim.duration() * fraction))
                        point = self.manager._ghost.pos()
                        self.assertTrue(min(start.x(), end.x()) <= point.x() <= max(start.x(), end.x()))
                        self.assertTrue(min(start.y(), end.y()) <= point.y() <= max(start.y(), end.y()))
                    anim.setCurrentTime(anim.duration())
                    self.assertEqual(len(finished), 1)
                self.assert_idle()
                self.assertEqual(self.project.to_dict(), before)
        self.assertEqual(len(self.swaps), 0)
        self.assertEqual(self.stack.count(), 0)

    def test_escape_on_view_cancels_and_live_policy_finishes_once(self):
        for mode in ('reduced', 'off'):
            with self.subTest(mode=mode):
                set_motion_mode('standard')
                self.start_drag()
                self.manager._on_mouse_move(self.center(1))
                QTest.keyClick(self.view, Qt.Key.Key_Escape)
                self.assertTrue(self.manager._animating)
                anim = self.manager._anim
                finished = QSignalSpy(anim.finished)
                set_motion_mode(mode)
                self.assertEqual(len(finished), 1)
                self.assert_idle()
                set_motion_mode('standard')
                self.assertEqual(len(finished), 1)
                self.assertEqual(self.stack.count(), 0)

    def test_live_policy_finishes_drop_once(self):
        for mode in ('reduced', 'off'):
            with self.subTest(mode=mode):
                set_motion_mode('standard')
                self.start_drag()
                self.manager._on_mouse_release(self.center(1))
                anim = self.manager._anim
                finished = QSignalSpy(anim.finished)
                set_motion_mode(mode)
                self.assertEqual(len(finished), 1)
                self.assert_idle()
                self.assertEqual(self.stack.count(), 1)
                set_motion_mode('standard')
                self.assertEqual(len(finished), 1)
                self.stack.undo()
                self.stack.clear()

    def test_interrupted_highlight_fades_leave_no_scene_items(self):
        for mode in ('standard', 'reduced', 'off'):
            with self.subTest(mode=mode):
                set_motion_mode(mode)
                before = set(self.scene.items())
                self.start_drag()
                self.manager._on_mouse_move(self.center(1))
                self.manager._on_mouse_move(self.center(2))
                self.manager._on_mouse_move(self.center(1))
                self.manager._on_mouse_release(QPointF(-100, -100))
                if self.manager._anim is not None:
                    self.manager._anim.setCurrentTime(self.manager._anim.duration())
                self.assert_idle()
                self.assertEqual(set(self.scene.items()), before)

    def test_zoom_retargets_one_animation_and_anchors_exactly(self):
        before = copy.deepcopy(self.project.to_dict())
        scene_rect = self.scene.sceneRect()
        anchor = QPointF(231.125, 187.875)
        fixed = self.view._scene_at(anchor)
        self.view._apply_zoom(1.2, anchor)
        first = self.view._zoom_anim
        self.assertEqual(first.duration(), 140)
        first.setCurrentTime(50)
        current = self.view._zoom_level
        self.assertTrue(1.0 < current < 1.2)
        self.assert_point(self.view._scene_at(anchor), fixed)
        self.view._apply_zoom(1.2, anchor)
        second = self.view._zoom_anim
        self.assertIsNot(second, first)
        self.assertEqual(first.state(), QAbstractAnimation.State.Stopped)
        self.assertAlmostEqual(self.view._zoom_level, current)
        self.assertAlmostEqual(self.view._zoom_target, 1.44)
        first.finished.emit()
        self.assertIs(self.view._zoom_anim, second)
        for time in (20, 80, 130):
            second.setCurrentTime(time)
            self.assert_point(self.view._scene_at(anchor), fixed)
        self.finish_zoom()
        self.assertAlmostEqual(self.view._zoom_level, 1.44)
        self.assert_point(self.view._scene_at(anchor), fixed)
        self.assertEqual(self.project.to_dict(), before)
        self.assertEqual(self.scene.sceneRect(), scene_rect)
        self.assertEqual(self.stack.count(), 0)
        self.assertEqual(len(self.geometry_changes), 0)

    def test_zoom_retarget_to_new_cursor_and_live_mode_completion(self):
        for mode in ('reduced', 'off'):
            with self.subTest(mode=mode):
                set_motion_mode('standard')
                self.view._apply_zoom(1.2, QPointF(100, 200))
                self.view._zoom_anim.setCurrentTime(40)
                anchor = QPointF(511.56789, 123.4321)
                fixed = self.view._scene_at(anchor)
                self.view._apply_zoom(1.2, anchor)
                anim = self.view._zoom_anim
                target = self.view._zoom_target
                finished = QSignalSpy(anim.finished)
                set_motion_mode(mode)
                self.assertEqual(len(finished), 1)
                self.assertIsNone(self.view._zoom_anim)
                self.assertEqual(self.view._zoom_level, target)
                self.assert_point(self.view._scene_at(anchor), fixed)
                set_motion_mode('standard')
                self.assertEqual(len(finished), 1)

    def test_fit_and_100_percent_in_all_modes(self):
        before = copy.deepcopy(self.project.to_dict())
        for mode in ('standard', 'reduced', 'off'):
            with self.subTest(mode=mode):
                set_motion_mode(mode)
                self.view.zoom_to_fit()
                if mode != 'standard':
                    self.assertIsNone(self.view._zoom_anim)
                self.finish_zoom()
                viewport = self.view.viewport().rect()
                expected = min((viewport.width() - 4) / self.scene.page_rect.width(),
                               (viewport.height() - 4) / self.scene.page_rect.height())
                self.assertAlmostEqual(self.view._zoom_level, expected)
                self.assert_point(self.view._scene_at(QPointF(viewport.center())), self.scene.page_rect.center())
                self.view.zoom_to_100()
                self.finish_zoom()
                self.assertEqual(self.view._zoom_level, 1.0)
        self.assertEqual(self.project.to_dict(), before)
        self.assertEqual(self.stack.count(), 0)

    def test_zoom_bounds_and_round_trip_have_no_anchor_drift(self):
        set_motion_mode('off')
        anchor = QPointF(312.1234567, 214.9876543)
        fixed = self.view._scene_at(anchor)
        for _ in range(60):
            self.view._apply_zoom(1.1, anchor)
            self.view._apply_zoom(1 / 1.1, anchor)
        self.assertAlmostEqual(self.view._zoom_level, 1.0, places=12)
        self.assert_point(self.view._scene_at(anchor), fixed)
        self.view._apply_zoom(1e9, anchor)
        self.assertEqual(self.view._zoom_level, self.view.MAX_ZOOM)
        self.assert_point(self.view._scene_at(anchor), fixed)
        self.view._apply_zoom(1e-12, anchor)
        self.assertEqual(self.view._zoom_level, self.view.MIN_ZOOM)
        self.assert_point(self.view._scene_at(anchor), fixed)
        for factor in (float('nan'), float('inf'), 0, -1):
            self.view._apply_zoom(factor, anchor)
            self.assertEqual(self.view._zoom_level, self.view.MIN_ZOOM)

    def test_trackpad_zoom_and_pan_are_immediate_and_cancel_pending_zoom(self):
        self.wheel()
        first = self.view._zoom_anim
        first.setCurrentTime(50)
        current = self.view._zoom_level
        self.wheel(angle=0, pixels=QPoint(0, 20), phase=Qt.ScrollPhase.ScrollUpdate)
        self.assertIsNone(self.view._zoom_anim)
        self.assertEqual(first.state(), QAbstractAnimation.State.Stopped)
        self.assertAlmostEqual(self.view._zoom_level, current * 1.1 ** 0.5)
        self.wheel()
        self.view._zoom_anim.setCurrentTime(30)
        current = self.view._zoom_level
        x, y = self.view.horizontalScrollBar().value(), self.view.verticalScrollBar().value()
        self.wheel(angle=0, pixels=QPoint(7, -9), control=False, phase=Qt.ScrollPhase.ScrollUpdate)
        self.assertIsNone(self.view._zoom_anim)
        self.assertEqual(self.view._zoom_level, current)
        self.assertEqual(self.view.horizontalScrollBar().value(), x - 7)
        self.assertEqual(self.view.verticalScrollBar().value(), y + 9)
        self.wheel(angle=0)
        self.assertIsNone(self.view._zoom_anim)
        self.assertEqual(self.stack.count(), 0)

    def test_middle_pan_interrupts_zoom_and_tracks_pixels(self):
        self.wheel()
        self.view._zoom_anim.setCurrentTime(30)
        current = self.view._zoom_level
        start, end = QPointF(200, 200), QPointF(217, 189)
        press = QMouseEvent(QEvent.Type.MouseButtonPress, start, start,
                            Qt.MouseButton.MiddleButton, Qt.MouseButton.MiddleButton,
                            Qt.KeyboardModifier.NoModifier)
        self.view.mousePressEvent(press)
        self.assertIsNone(self.view._zoom_anim)
        x, y = self.view.horizontalScrollBar().value(), self.view.verticalScrollBar().value()
        move = QMouseEvent(QEvent.Type.MouseMove, end, end, Qt.MouseButton.NoButton,
                           Qt.MouseButton.MiddleButton, Qt.KeyboardModifier.NoModifier)
        self.view.mouseMoveEvent(move)
        self.assertEqual(self.view.horizontalScrollBar().value(), x - 17)
        self.assertEqual(self.view.verticalScrollBar().value(), y + 11)
        self.assertEqual(self.view._zoom_level, current)
        release = QMouseEvent(QEvent.Type.MouseButtonRelease, end, end,
                              Qt.MouseButton.MiddleButton, Qt.MouseButton.NoButton,
                              Qt.KeyboardModifier.NoModifier)
        self.view.mouseReleaseEvent(release)
        self.assertFalse(self.view._pan_active)
        self.assertEqual(self.stack.count(), 0)

    def test_zoom_and_drop_finish_naturally_without_queued_work(self):
        self.start_drag()
        self.manager._on_mouse_release(self.center(1))
        self.view._apply_zoom(1.2, QPointF(234.567, 123.456))
        QTest.qWait(260)
        self.assert_idle()
        self.assertIsNone(self.view._zoom_anim)
        self.assertEqual(len(self.swaps), 1)
        self.assertEqual(self.stack.count(), 1)
        self.assertAlmostEqual(self.view._zoom_level, 1.2)
        QTest.qWait(60)
        self.assertEqual(len(self.swaps), 1)
        self.assertEqual(self.stack.count(), 1)

    def test_page_bounds_change_cancels_zoom_and_updates_view_only_extent(self):
        self.view._apply_zoom(1.2, QPointF(234.567, 123.456))
        self.view._zoom_anim.setCurrentTime(40)
        zoom = self.view._zoom_level
        center = QPointF(self.view.viewport().rect().center())
        fixed = self.view._scene_at(center)
        new_rect = self.scene.sceneRect().adjusted(-200, -300, 700, 800)
        self.scene.setSceneRect(new_rect)
        self.assertIsNone(self.view._zoom_anim)
        self.assertEqual(self.view._zoom_level, zoom)
        self.assert_point(self.view._scene_at(center), fixed)
        self.assertTrue(self.view.sceneRect().contains(new_rect))
        self.assertEqual(self.scene.sceneRect(), new_rect)
        self.assertEqual(self.stack.count(), 0)

    def test_canvas_ctrl_shortcuts_and_alt_font_variant_do_not_overlap(self):
        set_motion_mode('off')
        QTest.keyClick(self.view, Qt.Key.Key_Plus, Qt.KeyboardModifier.ControlModifier)
        self.assertAlmostEqual(self.view._zoom_level, 1.2)
        QTest.keyClick(self.view, Qt.Key.Key_Minus, Qt.KeyboardModifier.ControlModifier)
        self.assertAlmostEqual(self.view._zoom_level, 1.0)
        event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Plus,
                          Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier)
        self.view.keyPressEvent(event)
        self.assertAlmostEqual(self.view._zoom_level, 1.0)
        self.assertEqual(self.stack.count(), 0)


if __name__ == '__main__':
    unittest.main()
