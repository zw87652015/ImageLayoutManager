"""Panel for managing SVG text font-size groups across all SVGs in the project."""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QLabel, QDoubleSpinBox, QLineEdit, QSplitter,
    QWidget, QGroupBox, QFormLayout, QMessageBox,
)
from PyQt6.QtCore import Qt, pyqtSignal

from src.app.i18n import tr


class SvgTextGroupsPanel(QDialog):
    """Modeless dialog to create, edit, and delete SVG text font-size groups."""

    groups_changed = pyqtSignal()

    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.project = project

        self.setWindowTitle(tr("svgtxt_groups_panel_title"))
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.WindowCloseButtonHint |
            Qt.WindowType.WindowMaximizeButtonHint
        )
        self.setMinimumSize(560, 420)
        self.resize(640, 480)

        self._build_ui()
        self._populate_groups()

    # ------------------------------------------------------------------

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter)

        # Left: group list + CRUD buttons
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(QLabel(tr("svgtxt_groups_list_label")))

        self._group_list = QListWidget()
        self._group_list.currentRowChanged.connect(self._on_group_selected)
        left_layout.addWidget(self._group_list)

        btn_row = QHBoxLayout()
        self._btn_add = QPushButton(tr("svgtxt_add_group_btn"))
        self._btn_add.clicked.connect(self._on_add_group)
        btn_row.addWidget(self._btn_add)

        self._btn_delete = QPushButton(tr("svgtxt_delete_group_btn"))
        self._btn_delete.clicked.connect(self._on_delete_group)
        btn_row.addWidget(self._btn_delete)
        left_layout.addLayout(btn_row)
        splitter.addWidget(left)

        # Right: group details
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)

        props_box = QGroupBox(tr("svgtxt_group_props_box"))
        props_form = QFormLayout(props_box)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText(tr("svgtxt_group_name_placeholder"))
        props_form.addRow(tr("svgtxt_group_name_label"), self._name_edit)

        self._font_size_spin = QDoubleSpinBox()
        self._font_size_spin.setRange(1.0, 200.0)
        self._font_size_spin.setDecimals(1)
        self._font_size_spin.setSuffix(" pt")
        self._font_size_spin.setValue(12.0)
        props_form.addRow(tr("svgtxt_font_size_label"), self._font_size_spin)

        btn_save = QPushButton(tr("svgtxt_save_group_btn"))
        btn_save.clicked.connect(self._on_save_group)
        props_form.addRow("", btn_save)

        right_layout.addWidget(props_box)

        # Members list
        members_box = QGroupBox(tr("svgtxt_members_box"))
        members_layout = QVBoxLayout(members_box)
        self._members_list = QListWidget()
        self._members_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        members_layout.addWidget(self._members_list)

        btn_remove_member = QPushButton(tr("svgtxt_remove_members_btn"))
        btn_remove_member.clicked.connect(self._on_remove_members)
        members_layout.addWidget(btn_remove_member)

        right_layout.addWidget(members_box, 1)
        splitter.addWidget(right)
        splitter.setSizes([220, 380])

        self._set_detail_enabled(False)

    def _set_detail_enabled(self, enabled: bool):
        self._name_edit.setEnabled(enabled)
        self._font_size_spin.setEnabled(enabled)
        self._members_list.setEnabled(enabled)

    # ------------------------------------------------------------------

    def _populate_groups(self):
        current_row = self._group_list.currentRow()
        self._group_list.clear()
        for g in self.project.svg_text_groups:
            item = QListWidgetItem(g.name)
            item.setData(Qt.ItemDataRole.UserRole, g.id)
            self._group_list.addItem(item)
        if self._group_list.count() > 0:
            self._group_list.setCurrentRow(max(0, min(current_row, self._group_list.count() - 1)))

    def _on_group_selected(self, row: int):
        if row < 0:
            self._set_detail_enabled(False)
            self._members_list.clear()
            return
        item = self._group_list.item(row)
        if not item:
            return
        group_id = item.data(Qt.ItemDataRole.UserRole)
        group = next((g for g in self.project.svg_text_groups if g.id == group_id), None)
        if not group:
            return
        self._set_detail_enabled(True)
        self._name_edit.setText(group.name)
        self._font_size_spin.setValue(group.font_size_pt)
        self._members_list.clear()
        import os
        for m in group.members:
            fname = os.path.basename(m.svg_path)
            self._members_list.addItem(f"{fname}  —  {m.element_key}")

    def _current_group(self):
        item = self._group_list.currentItem()
        if not item:
            return None
        gid = item.data(Qt.ItemDataRole.UserRole)
        return next((g for g in self.project.svg_text_groups if g.id == gid), None)

    # ------------------------------------------------------------------

    def _on_add_group(self):
        from src.model.data_model import SvgTextGroup
        g = SvgTextGroup(name=tr("svgtxt_default_group_name"), font_size_pt=12.0)
        self.project.svg_text_groups.append(g)
        self._populate_groups()
        self._group_list.setCurrentRow(self._group_list.count() - 1)
        self.groups_changed.emit()

    def _on_delete_group(self):
        group = self._current_group()
        if not group:
            return
        reply = QMessageBox.question(
            self,
            tr("svgtxt_confirm_delete_title"),
            tr("svgtxt_confirm_delete_msg").format(name=group.name),
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.project.svg_text_groups = [g for g in self.project.svg_text_groups if g.id != group.id]
        self._populate_groups()
        if self._group_list.count() == 0:
            self._members_list.clear()
            self._set_detail_enabled(False)
        self.groups_changed.emit()

    def _on_save_group(self):
        group = self._current_group()
        if not group:
            return
        name = self._name_edit.text().strip() or tr("svgtxt_default_group_name")
        group.name = name
        group.font_size_pt = self._font_size_spin.value()
        # Refresh list item label
        item = self._group_list.currentItem()
        if item:
            item.setText(name)
        self.groups_changed.emit()

    def _on_remove_members(self):
        group = self._current_group()
        if not group:
            return
        selected_rows = sorted(
            [self._members_list.row(i) for i in self._members_list.selectedItems()],
            reverse=True,
        )
        for row in selected_rows:
            if 0 <= row < len(group.members):
                group.members.pop(row)
        self._on_group_selected(self._group_list.currentRow())
        self.groups_changed.emit()

    def refresh(self, project):
        """Refresh when project changes (e.g. after file open)."""
        self.project = project
        self._populate_groups()
        self._members_list.clear()
        self._set_detail_enabled(False)
