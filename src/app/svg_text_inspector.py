"""Stand-alone window for selecting SVG text elements and assigning them to groups."""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QLabel, QComboBox, QDoubleSpinBox, QLineEdit,
    QSplitter, QWidget, QGroupBox, QFormLayout, QMessageBox, QScrollArea,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap, QPainter
from PyQt6.QtSvg import QSvgRenderer

from src.utils.svg_text_utils import get_svg_text_elements
from src.app.i18n import tr


class SvgTextInspectorWindow(QDialog):
    """Window for selecting SVG text elements and assigning them to font-size groups."""

    groups_changed = pyqtSignal()  # emitted when any group data changes

    def __init__(self, svg_path: str, project, parent=None):
        super().__init__(parent)
        self.svg_path = svg_path
        self.project = project

        self.setWindowTitle(tr("svgtxt_inspector_title"))
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.WindowCloseButtonHint |
            Qt.WindowType.WindowMaximizeButtonHint
        )
        self.setMinimumSize(720, 500)
        self.resize(860, 580)

        self._build_ui()
        self._populate()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter)

        # Left: SVG preview
        preview_widget = QWidget()
        preview_layout = QVBoxLayout(preview_widget)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.addWidget(QLabel(tr("svgtxt_preview_label")))
        self._preview_label = QLabel()
        self._preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_label.setStyleSheet("background: #f0f0f0; border: 1px solid #ccc;")
        self._preview_label.setMinimumSize(300, 300)
        scroll = QScrollArea()
        scroll.setWidget(self._preview_label)
        scroll.setWidgetResizable(True)
        preview_layout.addWidget(scroll)
        splitter.addWidget(preview_widget)

        # Right: controls
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)

        # Text element list
        right_layout.addWidget(QLabel(tr("svgtxt_elements_label")))
        self._elem_list = QListWidget()
        self._elem_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        right_layout.addWidget(self._elem_list, 2)

        # Group assignment box
        assign_box = QGroupBox(tr("svgtxt_assign_group_box"))
        assign_form = QFormLayout(assign_box)

        self._group_combo = QComboBox()
        assign_form.addRow(tr("svgtxt_group_label"), self._group_combo)

        new_group_row = QHBoxLayout()
        self._new_group_name = QLineEdit()
        self._new_group_name.setPlaceholderText(tr("svgtxt_new_group_placeholder"))
        new_group_row.addWidget(self._new_group_name)
        btn_create = QPushButton(tr("svgtxt_create_group_btn"))
        btn_create.clicked.connect(self._on_create_group)
        new_group_row.addWidget(btn_create)
        assign_form.addRow(tr("svgtxt_new_group_label"), new_group_row)

        btn_assign = QPushButton(tr("svgtxt_assign_btn"))
        btn_assign.clicked.connect(self._on_assign_to_group)
        assign_form.addRow("", btn_assign)

        btn_remove = QPushButton(tr("svgtxt_remove_from_group_btn"))
        btn_remove.clicked.connect(self._on_remove_from_group)
        assign_form.addRow("", btn_remove)

        right_layout.addWidget(assign_box)

        # Group font-size editor
        font_box = QGroupBox(tr("svgtxt_font_size_box"))
        font_form = QFormLayout(font_box)

        self._font_size_spin = QDoubleSpinBox()
        self._font_size_spin.setRange(1.0, 200.0)
        self._font_size_spin.setDecimals(1)
        self._font_size_spin.setSuffix(" pt")
        self._font_size_spin.setValue(12.0)
        font_form.addRow(tr("svgtxt_font_size_label"), self._font_size_spin)

        btn_apply_size = QPushButton(tr("svgtxt_apply_size_btn"))
        btn_apply_size.clicked.connect(self._on_apply_font_size)
        font_form.addRow("", btn_apply_size)

        right_layout.addWidget(font_box)
        right_layout.addStretch()

        splitter.addWidget(right)
        splitter.setSizes([380, 440])

    # ------------------------------------------------------------------
    # Population
    # ------------------------------------------------------------------

    def _populate(self):
        self._render_preview()
        self._populate_elements()
        self._populate_group_combo()

    def _render_preview(self):
        renderer = QSvgRenderer(self.svg_path)
        if not renderer.isValid():
            self._preview_label.setText(tr("svgtxt_preview_failed"))
            return
        sz = renderer.defaultSize()
        if sz.isEmpty():
            sz.setWidth(400)
            sz.setHeight(400)
        scale = min(480 / sz.width(), 480 / sz.height(), 1.0)
        w, h = int(sz.width() * scale), int(sz.height() * scale)
        from PyQt6.QtGui import QImage
        from PyQt6.QtCore import Qt as _Qt
        img = QImage(w, h, QImage.Format.Format_ARGB32)
        img.fill(_Qt.GlobalColor.transparent)
        p = QPainter(img)
        renderer.render(p)
        p.end()
        self._preview_label.setPixmap(QPixmap.fromImage(img))
        self._preview_label.resize(w, h)

    def _populate_elements(self):
        self._elem_list.clear()
        elements = get_svg_text_elements(self.svg_path)
        # Build a fast look-up: key -> group name
        key_to_group = {}
        for g in self.project.svg_text_groups:
            for m in g.members:
                if m.svg_path == self.svg_path:
                    key_to_group[m.element_key] = g.name
        for el in elements:
            label = el['text'][:60]
            group_name = key_to_group.get(el['key'])
            suffix = f"  [{group_name}]" if group_name else ""
            item = QListWidgetItem(f"{label}{suffix}")
            item.setData(Qt.ItemDataRole.UserRole, el['key'])
            self._elem_list.addItem(item)

    def _populate_group_combo(self):
        self._group_combo.clear()
        for g in self.project.svg_text_groups:
            self._group_combo.addItem(g.name, g.id)
        if self._group_combo.count() == 0:
            self._group_combo.addItem(tr("svgtxt_no_groups"), None)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _selected_keys(self):
        keys = []
        for item in self._elem_list.selectedItems():
            k = item.data(Qt.ItemDataRole.UserRole)
            if k:
                keys.append(k)
        return keys

    def _on_create_group(self):
        name = self._new_group_name.text().strip()
        if not name:
            name = tr("svgtxt_default_group_name")
        from src.model.data_model import SvgTextGroup
        g = SvgTextGroup(name=name, font_size_pt=12.0)
        self.project.svg_text_groups.append(g)
        self._new_group_name.clear()
        self._populate_group_combo()
        # Select the newly created group
        idx = self._group_combo.findData(g.id)
        if idx >= 0:
            self._group_combo.setCurrentIndex(idx)
        self.groups_changed.emit()

    def _on_assign_to_group(self):
        keys = self._selected_keys()
        if not keys:
            QMessageBox.information(self, tr("svgtxt_info_title"), tr("svgtxt_select_elements_hint"))
            return
        group_id = self._group_combo.currentData()
        if not group_id:
            QMessageBox.information(self, tr("svgtxt_info_title"), tr("svgtxt_select_group_hint"))
            return
        group = next((g for g in self.project.svg_text_groups if g.id == group_id), None)
        if not group:
            return
        from src.model.data_model import SvgTextMember
        # Remove existing membership in any group for these keys/path
        for g in self.project.svg_text_groups:
            g.members = [m for m in g.members
                         if not (m.svg_path == self.svg_path and m.element_key in keys)]
        # Add to selected group
        for key in keys:
            group.members.append(SvgTextMember(svg_path=self.svg_path, element_key=key))
        self._populate_elements()
        self.groups_changed.emit()

    def _on_remove_from_group(self):
        keys = self._selected_keys()
        if not keys:
            return
        for g in self.project.svg_text_groups:
            g.members = [m for m in g.members
                         if not (m.svg_path == self.svg_path and m.element_key in keys)]
        self._populate_elements()
        self.groups_changed.emit()

    def _on_apply_font_size(self):
        group_id = self._group_combo.currentData()
        if not group_id:
            QMessageBox.information(self, tr("svgtxt_info_title"), tr("svgtxt_select_group_hint"))
            return
        group = next((g for g in self.project.svg_text_groups if g.id == group_id), None)
        if not group:
            return
        group.font_size_pt = self._font_size_spin.value()
        self.groups_changed.emit()

    def refresh(self):
        """Re-populate after external changes."""
        self._populate_elements()
        self._populate_group_combo()
