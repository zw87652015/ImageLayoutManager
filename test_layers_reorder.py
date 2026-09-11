"""Drag-and-drop Z-stack reordering in the Layers panel.

Covers the model-level commands (ReorderZIndexCommand, ReorderPipItemsCommand),
the tree's drag/drop compatibility rules (_BranchlessTree), and the
MainWindow handler that turns a panel drag into an undoable command —
an alternative to Bring to Front / Send to Back for the common
"grab this and put it exactly where I want" case.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PyQt6.QtCore import QCoreApplication, QEvent, QSettings, Qt
from PyQt6.QtGui import QUndoStack
from PyQt6.QtWidgets import QApplication

from src.app import main_window
from src.app.commands import ReorderPipItemsCommand, ReorderZIndexCommand
from src.app.layers_panel import (
    LayersPanel, _BranchlessTree, _ROLE_ID, _ROLE_TYPE, _ROLE_ZIDX,
)
from src.model.data_model import Cell, PiPItem, Project, RowTemplate


# ── command-level tests (no GUI needed) ─────────────────────────────────────

class ReorderZIndexCommandTests(unittest.TestCase):
    def setUp(self):
        self.cells = [Cell(row_index=0, col_index=i) for i in range(4)]
        self.project = Project(layout_mode='freeform', cells=self.cells)
        self.calls = 0

    def _bump(self):
        self.calls += 1

    def test_drop_above_places_dragged_directly_in_front_of_target(self):
        a, b, c, d = self.cells
        cmd = ReorderZIndexCommand(self.project, a.id, c.id, True, self._bump)
        cmd.redo()
        self.assertEqual(self.calls, 1)
        # a is now immediately in front of (higher z than) c, everything
        # else keeps its relative order: b, c, a, d
        ranked = sorted(self.cells, key=lambda cell: cell.z_index)
        self.assertEqual([cell.id for cell in ranked], [b.id, c.id, a.id, d.id])

    def test_drop_below_places_dragged_directly_behind_target(self):
        a, b, c, d = self.cells
        cmd = ReorderZIndexCommand(self.project, d.id, b.id, False, self._bump)
        cmd.redo()
        ranked = sorted(self.cells, key=lambda cell: cell.z_index)
        self.assertEqual([cell.id for cell in ranked], [a.id, d.id, b.id, c.id])

    def test_undo_restores_original_z_index(self):
        a, b, c, d = self.cells
        original = {cell.id: cell.z_index for cell in self.cells}
        cmd = ReorderZIndexCommand(self.project, a.id, c.id, True, self._bump)
        cmd.redo()
        cmd.undo()
        self.assertEqual({cell.id: cell.z_index for cell in self.cells}, original)

    def test_repeated_drags_keep_z_index_compact_unlike_plain_increment(self):
        """Unlike ZIndexChangeCommand's raw +1/-1, dragging renumbers the
        whole stack each time so values never drift unbounded."""
        a, b, c, d = self.cells
        ReorderZIndexCommand(self.project, a.id, d.id, True, None).redo()
        ReorderZIndexCommand(self.project, b.id, d.id, True, None).redo()
        values = sorted(cell.z_index for cell in self.cells)
        self.assertEqual(values, [0, 1, 2, 3])

    def test_missing_ids_are_a_safe_no_op(self):
        a = self.cells[0]
        original = {cell.id: cell.z_index for cell in self.cells}
        cmd = ReorderZIndexCommand(self.project, a.id, 'does-not-exist', True, self._bump)
        cmd.redo()
        self.assertEqual({cell.id: cell.z_index for cell in self.cells}, original)


class ReorderPipItemsCommandTests(unittest.TestCase):
    def setUp(self):
        self.cell = Cell(row_index=0, col_index=0)
        self.p1 = PiPItem(pip_type='external', image_path='a.png')
        self.p2 = PiPItem(pip_type='external', image_path='b.png')
        self.p3 = PiPItem(pip_type='external', image_path='c.png')
        self.cell.pip_items = [self.p1, self.p2, self.p3]

    def test_redo_applies_new_order_and_undo_restores_old_order(self):
        new_order = [self.p3.id, self.p1.id, self.p2.id]
        cmd = ReorderPipItemsCommand(self.cell, new_order, update_callback=None)
        cmd.redo()
        self.assertEqual([p.id for p in self.cell.pip_items], new_order)
        cmd.undo()
        self.assertEqual([p.id for p in self.cell.pip_items],
                          [self.p1.id, self.p2.id, self.p3.id])

    def test_last_in_list_is_frontmost_by_convention(self):
        # Dragging p1 to sit "above" (in front of) p3 means p1 ends up last.
        new_order = [self.p2.id, self.p3.id, self.p1.id]
        ReorderPipItemsCommand(self.cell, new_order).redo()
        self.assertEqual(self.cell.pip_items[-1].id, self.p1.id)


# ── tree drag-compatibility rules ───────────────────────────────────────────

class BranchlessTreeCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tree = _BranchlessTree()

    def _item(self, item_type, parent=None):
        from PyQt6.QtWidgets import QTreeWidgetItem
        it = QTreeWidgetItem(parent or self.tree, ['x'])
        it.setData(0, _ROLE_TYPE, item_type)
        return it

    def test_two_cells_are_compatible_regardless_of_parent(self):
        row1 = self._item('row')
        row2 = self._item('row')
        cell_a = self._item('cell_filled', row1)
        cell_b = self._item('cell_empty', row2)
        self.assertTrue(self.tree._compatible_target(cell_a, cell_b))

    def test_pip_items_require_same_parent_cell(self):
        cell1 = self._item('cell_filled')
        cell2 = self._item('cell_filled')
        pip_a = self._item('pip_item', cell1)
        pip_b = self._item('pip_item', cell1)
        pip_c = self._item('pip_item', cell2)
        self.assertTrue(self.tree._compatible_target(pip_a, pip_b))
        self.assertFalse(self.tree._compatible_target(pip_a, pip_c))

    def test_mismatched_kinds_are_incompatible(self):
        cell = self._item('cell_filled')
        pip = self._item('pip_item', cell)
        self.assertFalse(self.tree._compatible_target(cell, pip))

    def test_structural_rows_and_text_are_never_draggable(self):
        row = self._item('row')
        split = self._item('split')
        text_leaf = self._item('text_leaf')
        cell = self._item('cell_filled')
        for non_draggable in (row, split, text_leaf):
            with self.subTest(kind=non_draggable.data(0, _ROLE_TYPE)):
                self.assertIsNone(self.tree._drag_kind(non_draggable))
                self.assertFalse(self.tree._compatible_target(non_draggable, cell))

    def test_dragging_an_item_onto_itself_is_incompatible(self):
        cell = self._item('cell_filled')
        self.assertFalse(self.tree._compatible_target(cell, cell))


# ── LayersPanel tree construction ──────────────────────────────────────────

class LayersPanelTreeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.panel = LayersPanel()
        self.cells = [Cell(row_index=0, col_index=i) for i in range(2)]
        self.cells[0].z_index = 3
        self.cells[0].pip_items = [PiPItem(pip_type='external', image_path='x.png')]
        self.project = Project(cells=self.cells)
        self.project.rows = [RowTemplate(index=0, column_count=2)]
        self.panel.set_project(self.project)

    def tearDown(self):
        self.panel.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def _find(self, item_id):
        from PyQt6.QtWidgets import QTreeWidgetItemIterator
        it = QTreeWidgetItemIterator(self.panel.tree)
        while it.value():
            if it.value().data(0, _ROLE_ID) == item_id:
                return it.value()
            it += 1
        return None

    def test_cell_with_nonzero_z_index_carries_the_badge_role(self):
        item = self._find(self.cells[0].id)
        self.assertEqual(item.data(0, _ROLE_ZIDX), 3)

    def test_cell_with_default_z_index_has_no_badge_role(self):
        item = self._find(self.cells[1].id)
        self.assertIsNone(item.data(0, _ROLE_ZIDX))

    def test_leaf_cells_are_drag_and_drop_enabled(self):
        item = self._find(self.cells[1].id)
        self.assertTrue(bool(item.flags() & Qt.ItemFlag.ItemIsDragEnabled))
        self.assertTrue(bool(item.flags() & Qt.ItemFlag.ItemIsDropEnabled))

    def test_pip_items_are_drag_and_drop_enabled(self):
        pip_id = self.cells[0].pip_items[0].id
        item = self._find(pip_id)
        self.assertTrue(bool(item.flags() & Qt.ItemFlag.ItemIsDragEnabled))
        self.assertTrue(bool(item.flags() & Qt.ItemFlag.ItemIsDropEnabled))

    def test_tree_reorder_signal_bubbles_to_panel_signal(self):
        received = []
        self.panel.reorder_requested.connect(lambda a, b, above: received.append((a, b, above)))
        self.panel.tree.reorder_requested.emit('dragged', 'target', True)
        self.assertEqual(received, [('dragged', 'target', True)])


# ── MainWindow integration ──────────────────────────────────────────────────

class LayersReorderIntegrationTests(unittest.TestCase):
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
        project = Project(layout_mode='freeform', page_width_mm=160, page_height_mm=80)
        project.rows = [RowTemplate(index=0, column_count=3)]
        project.cells = [Cell(row_index=0, col_index=i) for i in range(3)]
        self.window._set_project(project, None)
        self.project = project
        self.window.undo_stack.setClean()

    def test_drag_two_cells_pushes_undoable_reorder_command(self):
        a, b, c = self.project.cells
        self.window._on_layers_reorder_requested(a.id, c.id, True)
        ranked = sorted(self.project.cells, key=lambda cell: cell.z_index)
        self.assertEqual([cell.id for cell in ranked], [b.id, c.id, a.id])
        self.assertTrue(self.window.undo_stack.canUndo())
        self.window.undo_stack.undo()
        self.assertTrue(all(cell.z_index == 0 for cell in self.project.cells))

    def test_drag_pip_onto_pip_of_the_same_cell_reorders_insets(self):
        cell = self.project.cells[0]
        p1 = PiPItem(pip_type='external', image_path='a.png')
        p2 = PiPItem(pip_type='external', image_path='b.png')
        cell.pip_items = [p1, p2]
        self.window._on_layers_reorder_requested(p1.id, p2.id, False)
        self.assertEqual([p.id for p in cell.pip_items], [p1.id, p2.id])
        self.window.undo_stack.undo()
        self.assertEqual([p.id for p in cell.pip_items], [p1.id, p2.id])

        # Moving the *front* item behind the other actually changes order.
        cell.pip_items = [p1, p2]
        self.window._on_layers_reorder_requested(p2.id, p1.id, False)
        self.assertEqual([p.id for p in cell.pip_items], [p2.id, p1.id])

    def test_dragging_a_cell_onto_itself_does_nothing(self):
        a = self.project.cells[0]
        before = {cell.id: cell.z_index for cell in self.project.cells}
        self.window._on_layers_reorder_requested(a.id, a.id, True)
        self.assertEqual({cell.id: cell.z_index for cell in self.project.cells}, before)
        self.assertFalse(self.window.undo_stack.canUndo())

    def test_layers_panel_signal_reaches_the_window_handler(self):
        a, b, c = self.project.cells
        self.window.layers_panel.reorder_requested.emit(a.id, b.id, False)
        ranked = sorted(self.project.cells, key=lambda cell: cell.z_index)
        self.assertEqual(ranked[0].id, a.id)


if __name__ == '__main__':
    unittest.main()
