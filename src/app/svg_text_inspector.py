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
from PyQt6.QtGui import QPixmap, QPainter, QImage, QColor, QPen
from PyQt6.QtSvg import QSvgRenderer

from src.utils.svg_text_utils import (format_text_size, get_svg_text_elements,
                                      svg_text_preview_source, svg_text_rows,
                                      text_preview_rects)
from src.utils.editable_plot import plot_reflows
from ilmplot.document import has_plot_metadata
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
        self._sizes = {}
        self._preview_base = None
        self._preview_rects = {}

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

        self._size_hint = QLabel()
        self._size_hint.setWordWrap(True)
        self._size_hint.setStyleSheet("color: #666;")
        rv.addWidget(self._size_hint)

        self._elem_list = QListWidget()
        self._elem_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self._elem_list.setMinimumHeight(120)
        self._elem_list.itemSelectionChanged.connect(self._update_size_button)
        self._elem_list.itemSelectionChanged.connect(self._update_highlight)
        rv.addWidget(self._elem_list, 2)

        # Assignment row (below elements): [combo] [Assign] [Remove]
        assign_row = QHBoxLayout()
        assign_row.setSpacing(6)
        assign_row.addWidget(QLabel(tr("svgtxt_assign_to") + ":"))
        self._group_combo = QComboBox()
        self._group_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._group_combo.setMinimumContentsLength(8)
        self._group_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        assign_row.addWidget(self._group_combo, 1)
        self._btn_assign = QPushButton(tr("svgtxt_assign_btn"))
        self._btn_assign.clicked.connect(self._on_assign)
        assign_row.addWidget(self._btn_assign)
        rv.addLayout(assign_row)
        action_row = QHBoxLayout()
        action_row.setSpacing(6)
        self._btn_ungroup = QPushButton(tr("svgtxt_remove_from_group_btn"))
        self._btn_ungroup.clicked.connect(self._on_ungroup)
        action_row.addWidget(self._btn_ungroup)
        self._btn_size_group = QPushButton(tr("svgtxt_new_group_size_btn"))
        self._btn_size_group.clicked.connect(self._on_new_group_at_size)
        action_row.addWidget(self._btn_size_group)
        action_row.addStretch(1)
        rv.addLayout(action_row)

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
        splitter.setChildrenCollapsible(False)
        left.setMinimumWidth(300)
        right.setMinimumWidth(380)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([480, 500])

    _section_label = staticmethod(section_label)

    # ──────────────────────────────────────────────────────────────────
    # Refresh helpers
    # ──────────────────────────────────────────────────────────────────

    def _refresh_all(self):
        self._refresh_preview()
        self._refresh_size_hint()
        self._refresh_elements()
        self._refresh_group_combo()
        self._rebuild_group_rows()

    def _refresh_size_hint(self):
        native = self._cell is not None and has_plot_metadata(self.svg_path)
        self._size_hint.setVisible(native)
        if native:
            on = plot_reflows(self.project, self._cell)
            self._size_hint.setText(tr("svgtxt_size_reflow_on" if on
                                       else "svgtxt_size_reflow_off"))

    def _element_rows(self):
        if self._cell is None:
            return [{'key': e['key'], 'text': e['text'], 'size_pt': None}
                    for e in get_svg_text_elements(self.svg_path)]
        return svg_text_rows(self.project, self._cell)

    def _update_size_button(self):
        keys = self._selected_keys()
        self._btn_size_group.setEnabled(
            bool(keys) and self._sizes.get(keys[0]) is not None)

    def _svg_file_bytes(self):
        try:
            with open(self.svg_path, 'rb') as fh:
                return fh.read()
        except OSError:
            return None

    def _refresh_preview(self):
        source = svg_text_preview_source(self.project, self._cell) if self._cell else None
        if source is not None:
            key_bytes, positioned, processed = source
        else:
            key_bytes, positioned, processed = self._svg_file_bytes(), False, None

        if self._cell and getattr(self._cell, 'svg_normalize_text', False):
            pt = getattr(self._cell, 'svg_normalize_text_pt', 8.0)
            self._norm_label.setText(tr("svgtxt_norm_active_hint").format(pt=pt))
        else:
            self._norm_label.setText("")

        renderer = QSvgRenderer(QByteArray(processed)) if processed else QSvgRenderer(self.svg_path)
        if not renderer.isValid():
            self._preview_label.setText(tr("svgtxt_preview_failed"))
            self._preview_base = None
            self._preview_rects = {}
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
        self._preview_base = img
        self._preview_rects = (text_preview_rects(key_bytes, None, w, h, positioned)
                               if key_bytes else {})
        self._update_highlight()
        self._preview_label.resize(w, h)

    def _update_highlight(self):
        """Repaint the cached preview with the selected texts outlined.

        Uses the base image and element rects from the last ``_refresh_preview``,
        so selection changes never re-render the SVG.
        """
        if self._preview_base is None:
            return
        img = self._preview_base.copy()
        keys = self._selected_keys()
        if keys:
            painter = QPainter(img)
            painter.setPen(QPen(QColor(217, 72, 15), 2))
            painter.setBrush(QColor(255, 120, 0, 90))
            for key in keys:
                rect = self._preview_rects.get(key)
                if rect is not None:
                    painter.drawRect(rect.adjusted(-2, -2, 2, 2))
            painter.end()
        self._preview_label.setPixmap(QPixmap.fromImage(img))

    def _refresh_elements(self):
        sel_keys = {item.data(Qt.ItemDataRole.UserRole) for item in self._elem_list.selectedItems()}
        self._elem_list.blockSignals(True)
        self._elem_list.clear()
        key_to_group = {
            m.element_key: g.name
            for g in self.project.svg_text_groups
            for m in g.members
            if m.svg_path == self.svg_path
        }
        self._sizes = {}
        for el in self._element_rows():
            label = el['text'][:60]
            if el['size_pt'] is not None:
                self._sizes[el['key']] = round(el['size_pt'], 1)
                label = f"{label} · {format_text_size(el['size_pt'])} pt"
            grp = key_to_group.get(el['key'])
            suffix = f"  [{grp}]" if grp else ""
            item = QListWidgetItem(f"{label}{suffix}")
            item.setData(Qt.ItemDataRole.UserRole, el['key'])
            self._elem_list.addItem(item)
            if el['key'] in sel_keys:
                item.setSelected(True)
        self._elem_list.blockSignals(False)
        self._update_size_button()
        self._update_highlight()

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

    def _on_new_group_at_size(self):
        keys = self._selected_keys()
        size = self._sizes.get(keys[0]) if keys else None
        if size is None:
            return
        self._groups_widget.add_group(
            name=tr("svgtxt_plot_group_name").format(
                pt=format_text_size(size)),
            font_size_pt=size)

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
