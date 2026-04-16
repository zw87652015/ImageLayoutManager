import os
from src.app.i18n import tr
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QTreeWidget, QTreeWidgetItem,
    QTreeWidgetItemIterator
)
from PyQt6.QtGui import QColor
from PyQt6.QtCore import Qt, pyqtSignal


class LayersPanel(QWidget):
    item_selected = pyqtSignal(str)  # emits cell_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(200)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 10, 8, 8)
        layout.setSpacing(6)

        # Header
        self.header_label = QLabel(tr("layers_header"))
        self.header_label.setStyleSheet(
            "font-weight: bold; color: #888888; font-size: 11px; letter-spacing: 1px;"
        )
        layout.addWidget(self.header_label)

        # Tree
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)
        self.tree.setIndentation(14)
        self.tree.setStyleSheet("""
            QTreeWidget {
                background-color: transparent;
                border: none;
                outline: none;
            }
            QTreeWidget::item {
                padding: 3px 2px;
            }
            QTreeWidget::item:selected {
                background-color: #2A3F5F;
                color: #4A90E2;
                border-radius: 4px;
            }
            QTreeWidget::item:hover:!selected {
                background-color: #2D2D2D;
            }
            QTreeWidget::branch {
                background: transparent;
            }
        """)

        self.tree.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self.tree)

        self._project = None
        self._is_updating = False

    def set_project(self, project):
        self._project = project
        self.refresh()

    def refresh(self):
        if not self._project:
            return

        self._is_updating = True
        self.tree.clear()

        # Sort rows by index
        sorted_rows = sorted(self._project.rows, key=lambda r: r.index)

        for r in sorted_rows:
            row_item = QTreeWidgetItem(self.tree, [f"{tr('layers_row')} {r.index + 1}"])
            row_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            row_item.setForeground(0, QColor("#888888"))

            # Find and sort cells for this row by col_index
            cells_in_row = sorted(
                [c for c in self._project.cells if c.row_index == r.index],
                key=lambda c: c.col_index
            )
            for c in cells_in_row:
                self._add_cell_tree_item(row_item, c, col_label=f"C{c.col_index + 1}")

            row_item.setExpanded(True)

        # Text items section (global scope only)
        global_texts = [t for t in self._project.text_items if t.scope == "global"]
        if global_texts:
            text_root = QTreeWidgetItem(self.tree, [tr("layers_text_items")])
            text_root.setFlags(Qt.ItemFlag.ItemIsEnabled)
            text_root.setForeground(0, QColor("#888888"))
            for t in global_texts:
                preview = (t.text[:16] + "…") if len(t.text) > 16 else t.text
                t_item = QTreeWidgetItem(text_root, [f'"{preview}"'])
                t_item.setData(0, Qt.ItemDataRole.UserRole, t.id)
                t_item.setForeground(0, QColor("#CCCCCC"))
            text_root.setExpanded(True)

        self._is_updating = False

    def _add_cell_tree_item(self, parent_item, cell, col_label=""):
        """Recursively add a cell and its sub-cells to the tree."""
        if cell.split_direction != "none" and cell.children:
            # Container cell — show it as a group node
            split_label = tr("layers_split_v") if cell.split_direction == "vertical" else tr("layers_split_h")
            node = QTreeWidgetItem(parent_item, [f"{col_label}  {split_label}"])
            node.setData(0, Qt.ItemDataRole.UserRole, cell.id)
            node.setForeground(0, QColor("#AAAAAA"))
            for i, child in enumerate(cell.children):
                self._add_cell_tree_item(node, child, col_label=f"{tr('layers_sub')} {i + 1}")
            node.setExpanded(True)
        else:
            # Leaf cell
            if cell.image_path and not cell.is_placeholder:
                name = os.path.basename(cell.image_path)
                label = f"{col_label}  {name}"
                color = QColor("#E0E0E0")
            else:
                label = f"{col_label}  {tr('layers_empty')}"
                color = QColor("#555555")

            tree_item = QTreeWidgetItem(parent_item, [label])
            tree_item.setData(0, Qt.ItemDataRole.UserRole, cell.id)
            tree_item.setForeground(0, color)

    def select_item(self, target_id):
        """Programmatically select a tree item by cell/text ID.
        Passing None clears the selection."""
        self._is_updating = True
        self.tree.clearSelection()

        if target_id is not None:
            # Strip label_ prefix — label cells are virtual overlays; highlight parent cell instead
            lookup_id = target_id.removeprefix("label_")
            it = QTreeWidgetItemIterator(self.tree)
            while it.value():
                item = it.value()
                if item.data(0, Qt.ItemDataRole.UserRole) == lookup_id:
                    item.setSelected(True)
                    self.tree.scrollToItem(item)
                    break
                it += 1

        self._is_updating = False

    def retranslate_ui(self):
        self.header_label.setText(tr("layers_header"))
        self.refresh()

    def _on_selection_changed(self):
        if self._is_updating:
            return
        selected = self.tree.selectedItems()
        if selected:
            item_id = selected[0].data(0, Qt.ItemDataRole.UserRole)
            if item_id:
                self.item_selected.emit(item_id)
