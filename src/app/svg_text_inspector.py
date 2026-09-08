"""SVG text font-size manager — single dialog replacing the old two-dialog flow.

Layout
------
Left : live SVG preview (shows normalization + group overrides applied).
Right: two sections stacked vertically —
  1. Text Elements list — shows every <text> element with its current group.
     Selecting one or more elements and picking a group from the dropdown
     below assigns them immediately (one click, no "Assign" button dialog).
  2. Groups list — each group is one row: editable name | font-size spinner
     (live — updates the preview on every keystroke/spin) | Delete button.
     A footer "+ New Group" button appends a group instantly.
"""

import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QLabel, QComboBox,
    QSplitter, QWidget, QScrollArea, QFrame, QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal, QByteArray
from PyQt6.QtGui import QPixmap, QPainter, QImage
from PyQt6.QtSvg import QSvgRenderer

from src.utils.svg_text_utils import get_svg_text_elements, get_svg_override_bytes_for_cell
from src.model.data_model import SvgTextMember
from src.app.i18n import tr
from src.app.text_groups_widget import TextGroupsWidget, section_label


class SvgTextInspectorWindow(QDialog):
    """Unified SVG text manager: assign elements to groups and set font sizes."""

    groups_changed = pyqtSignal()

    def __init__(self, svg_path: str, project, cell=None, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.svg_path = svg_path
        self.project = project
        self._cell = cell

        self.setWindowTitle(tr("svgtxt_inspector_title"))
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.WindowCloseButtonHint |
            Qt.WindowType.WindowMaximizeButtonHint
        )
        self.setMinimumSize(780, 540)
        self.resize(980, 640)

        self._build_ui()
        self._refresh_all()

    # ──────────────────────────────────────────────────────────────────
    # UI construction
    # ──────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter)

        # ── Left: preview ──────────────────────────────────────────────
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(4)

        lv.addWidget(QLabel(tr("svgtxt_preview_label")))

        self._norm_label = QLabel()
        self._norm_label.setStyleSheet("color: #b07800; font-style: italic;")
        self._norm_label.setWordWrap(True)
        lv.addWidget(self._norm_label)

        self._preview_label = QLabel()
        self._preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_label.setStyleSheet("background: #f0f0f0; border: 1px solid #ccc;")
        self._preview_label.setMinimumSize(280, 280)
        scroll = QScrollArea()
        scroll.setWidget(self._preview_label)
        scroll.setWidgetResizable(True)
        lv.addWidget(scroll, 1)
        splitter.addWidget(left)

        # ── Right: elements + groups ───────────────────────────────────
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(8)

        # Section 1 — Elements list
        rv.addWidget(self._section_label(tr("svgtxt_elements_label")))

        self._elem_list = QListWidget()
        self._elem_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self._elem_list.setMinimumHeight(120)
        rv.addWidget(self._elem_list, 2)

        # Assignment row (below elements): [combo] [Assign] [Remove]
        assign_row = QHBoxLayout()
        assign_row.setSpacing(6)
        assign_row.addWidget(QLabel(tr("svgtxt_assign_to") + ":"))
        self._group_combo = QComboBox()
        self._group_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        assign_row.addWidget(self._group_combo, 1)
        self._btn_assign = QPushButton(tr("svgtxt_assign_btn"))
        self._btn_assign.clicked.connect(self._on_assign)
        assign_row.addWidget(self._btn_assign)
        self._btn_ungroup = QPushButton(tr("svgtxt_remove_from_group_btn"))
        self._btn_ungroup.clicked.connect(self._on_ungroup)
        assign_row.addWidget(self._btn_ungroup)
        rv.addLayout(assign_row)

        # Divider
        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setStyleSheet("color: #ccc;")
        rv.addWidget(div)

        # Section 2 — Groups
        self._groups_widget = TextGroupsWidget(self.project)
        self._groups_widget.groups_changed.connect(self._on_groups_edited)
        self._groups_widget.group_added.connect(self._on_group_added)
        rv.addWidget(self._groups_widget, 1)

        splitter.addWidget(right)
        splitter.setSizes([380, 500])

    _section_label = staticmethod(section_label)

    # ──────────────────────────────────────────────────────────────────
    # Refresh helpers
    # ──────────────────────────────────────────────────────────────────

    def _refresh_all(self):
        self._refresh_preview()
        self._refresh_elements()
        self._refresh_group_combo()
        self._rebuild_group_rows()

    def _refresh_preview(self):
        processed = get_svg_override_bytes_for_cell(self.project, self._cell) if self._cell else None

        if self._cell and getattr(self._cell, 'svg_normalize_text', False):
            pt = getattr(self._cell, 'svg_normalize_text_pt', 8.0)
            self._norm_label.setText(tr("svgtxt_norm_active_hint").format(pt=pt))
        else:
            self._norm_label.setText("")

        renderer = QSvgRenderer(QByteArray(processed)) if processed else QSvgRenderer(self.svg_path)
        if not renderer.isValid():
            self._preview_label.setText(tr("svgtxt_preview_failed"))
            return
        sz = renderer.defaultSize()
        if sz.isEmpty():
            sz.setWidth(400); sz.setHeight(400)
        scale = min(480 / sz.width(), 480 / sz.height(), 1.0)
        w, h = int(sz.width() * scale), int(sz.height() * scale)
        img = QImage(w, h, QImage.Format.Format_ARGB32)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        renderer.render(p)
        p.end()
        self._preview_label.setPixmap(QPixmap.fromImage(img))
        self._preview_label.resize(w, h)

    def _refresh_elements(self):
        sel_keys = {item.data(Qt.ItemDataRole.UserRole) for item in self._elem_list.selectedItems()}
        self._elem_list.blockSignals(True)
        self._elem_list.clear()
        elements = get_svg_text_elements(self.svg_path)
        key_to_group = {
            m.element_key: g.name
            for g in self.project.svg_text_groups
            for m in g.members
            if m.svg_path == self.svg_path
        }
        for el in elements:
            label = el['text'][:60]
            grp = key_to_group.get(el['key'])
            suffix = f"  [{grp}]" if grp else ""
            item = QListWidgetItem(f"{label}{suffix}")
            item.setData(Qt.ItemDataRole.UserRole, el['key'])
            self._elem_list.addItem(item)
            if el['key'] in sel_keys:
                item.setSelected(True)
        self._elem_list.blockSignals(False)

    def _refresh_group_combo(self):
        self._groups_widget.fill_combo(self._group_combo)

    def _rebuild_group_rows(self):
        self._groups_widget.refresh()

    def _on_groups_edited(self):
        # Sync combo + element list labels
        self._refresh_group_combo()
        self._refresh_elements()
        self._refresh_preview()
        self.groups_changed.emit()

    def _on_group_added(self, gid):
        # Auto-select the new group in the combo
        self._refresh_group_combo()
        idx = self._group_combo.findData(gid)
        if idx >= 0:
            self._group_combo.setCurrentIndex(idx)

    # ──────────────────────────────────────────────────────────────────
    # Slots
    # ──────────────────────────────────────────────────────────────────

    def _selected_keys(self):
        return [item.data(Qt.ItemDataRole.UserRole) for item in self._elem_list.selectedItems()
                if item.data(Qt.ItemDataRole.UserRole)]

    def _on_assign(self):
        keys = self._selected_keys()
        if not keys:
            return
        group_id = self._group_combo.currentData()
        if not group_id:
            return
        group = next((g for g in self.project.svg_text_groups if g.id == group_id), None)
        if not group:
            return
        for g in self.project.svg_text_groups:
            g.members = [m for m in g.members
                         if not (m.svg_path == self.svg_path and m.element_key in keys)]
        for key in keys:
            group.members.append(SvgTextMember(svg_path=self.svg_path, element_key=key))
        self._refresh_elements()
        self._refresh_preview()
        self.groups_changed.emit()

    def _on_ungroup(self):
        keys = self._selected_keys()
        if not keys:
            return
        for g in self.project.svg_text_groups:
            g.members = [m for m in g.members
                         if not (m.svg_path == self.svg_path and m.element_key in keys)]
        self._refresh_elements()
        self._refresh_preview()
        self.groups_changed.emit()

    def refresh(self):
        """Re-populate after external changes (e.g. project reload)."""
        self._refresh_all()
