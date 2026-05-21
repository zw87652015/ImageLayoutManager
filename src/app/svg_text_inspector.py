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
    QPushButton, QLabel, QComboBox, QDoubleSpinBox, QLineEdit,
    QSplitter, QWidget, QScrollArea, QFrame, QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal, QByteArray
from PyQt6.QtGui import QPixmap, QPainter, QImage, QFont
from PyQt6.QtSvg import QSvgRenderer

from src.utils.svg_text_utils import get_svg_text_elements, get_svg_override_bytes_for_cell
from src.model.data_model import SvgTextGroup, SvgTextMember
from src.app.i18n import tr


class SvgTextInspectorWindow(QDialog):
    """Unified SVG text manager: assign elements to groups and set font sizes."""

    groups_changed = pyqtSignal()

    def __init__(self, svg_path: str, project, cell=None, parent=None):
        super().__init__(parent)
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
        groups_header = QHBoxLayout()
        groups_header.addWidget(self._section_label(tr("svgtxt_groups_section_label")), 1)
        self._btn_add_group = QPushButton("+ " + tr("svgtxt_add_group_btn"))
        self._btn_add_group.clicked.connect(self._on_add_group)
        groups_header.addWidget(self._btn_add_group)
        rv.addLayout(groups_header)

        # Scrollable group rows container
        self._groups_scroll = QScrollArea()
        self._groups_scroll.setWidgetResizable(True)
        self._groups_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._groups_container = QWidget()
        self._groups_vbox = QVBoxLayout(self._groups_container)
        self._groups_vbox.setContentsMargins(0, 0, 0, 0)
        self._groups_vbox.setSpacing(3)
        self._groups_vbox.addStretch()
        self._groups_scroll.setWidget(self._groups_container)
        rv.addWidget(self._groups_scroll, 1)

        splitter.addWidget(right)
        splitter.setSizes([380, 500])

    @staticmethod
    def _section_label(text: str) -> QLabel:
        lbl = QLabel(text)
        f = lbl.font()
        f.setWeight(QFont.Weight.DemiBold)
        lbl.setFont(f)
        return lbl

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
            if el['key'] in sel_keys:
                item.setSelected(True)
            self._elem_list.addItem(item)
        self._elem_list.blockSignals(False)

    def _refresh_group_combo(self):
        prev_id = self._group_combo.currentData()
        self._group_combo.blockSignals(True)
        self._group_combo.clear()
        for g in self.project.svg_text_groups:
            self._group_combo.addItem(g.name, g.id)
        if self._group_combo.count() == 0:
            self._group_combo.addItem(tr("svgtxt_no_groups"), None)
        # Restore previous selection if still present
        idx = self._group_combo.findData(prev_id)
        if idx >= 0:
            self._group_combo.setCurrentIndex(idx)
        self._group_combo.blockSignals(False)

    def _rebuild_group_rows(self):
        """Rebuild the inline group list (name + font-size spinner + delete)."""
        # Remove all widgets except the trailing stretch
        while self._groups_vbox.count() > 1:
            item = self._groups_vbox.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for g in self.project.svg_text_groups:
            row = self._make_group_row(g)
            self._groups_vbox.insertWidget(self._groups_vbox.count() - 1, row)

    def _make_group_row(self, group) -> QWidget:
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(6)

        name_edit = QLineEdit(group.name)
        name_edit.setPlaceholderText(tr("svgtxt_group_name_placeholder"))
        name_edit.setMinimumWidth(80)

        def _on_name_changed(text, gid=group.id):
            g = next((x for x in self.project.svg_text_groups if x.id == gid), None)
            if g:
                g.name = text.strip() or tr("svgtxt_default_group_name")
                # Sync combo + element list labels
                self._refresh_group_combo()
                self._refresh_elements()
                self.groups_changed.emit()

        name_edit.textChanged.connect(_on_name_changed)
        h.addWidget(name_edit, 1)

        spin = QDoubleSpinBox()
        spin.setRange(1.0, 200.0)
        spin.setDecimals(1)
        spin.setSuffix(" pt")
        spin.setValue(group.font_size_pt)
        spin.setFixedWidth(80)

        def _on_size_changed(val, gid=group.id):
            g = next((x for x in self.project.svg_text_groups if x.id == gid), None)
            if g:
                g.font_size_pt = val
                self._refresh_preview()
                self.groups_changed.emit()

        spin.valueChanged.connect(_on_size_changed)
        h.addWidget(spin)

        del_btn = QPushButton("✕")
        del_btn.setFixedWidth(28)
        del_btn.setToolTip(tr("svgtxt_delete_group_btn"))

        def _on_delete(gid=group.id):
            self.project.svg_text_groups = [x for x in self.project.svg_text_groups if x.id != gid]
            self._refresh_all()
            self.groups_changed.emit()

        del_btn.clicked.connect(_on_delete)
        h.addWidget(del_btn)

        return row

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

    def _on_add_group(self):
        g = SvgTextGroup(name=tr("svgtxt_default_group_name"), font_size_pt=12.0)
        self.project.svg_text_groups.append(g)
        self._refresh_group_combo()
        self._rebuild_group_rows()
        # Auto-select the new group in the combo
        idx = self._group_combo.findData(g.id)
        if idx >= 0:
            self._group_combo.setCurrentIndex(idx)
        self.groups_changed.emit()

    def refresh(self):
        """Re-populate after external changes (e.g. project reload)."""
        self._refresh_all()
