"""Project-wide text group editor shared by the SVG and raster text inspectors.

One row per ``SvgTextGroup``: editable name | font-size spinner | delete.
Font sizes are points in the *final figure*; each inspector converts them to
its own medium (SVG user units or raster pixels).
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QDoubleSpinBox, QScrollArea, QComboBox,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont

from src.model.data_model import SvgTextGroup
from src.app.i18n import tr
from src.app.wheel_guard import install_wheel_guard
from src.app.motion import install_button_feedback


def section_label(text: str) -> QLabel:
    lbl = QLabel(text)
    f = lbl.font()
    f.setWeight(QFont.Weight.DemiBold)
    lbl.setFont(f)
    return lbl


class TextGroupsWidget(QWidget):
    """Header + scrollable group rows.  Emits ``groups_changed`` on any edit
    and ``group_added(group_id)`` after "+ New Group"."""

    groups_changed = pyqtSignal()
    group_added = pyqtSignal(str)

    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.project = project
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)

        header = QHBoxLayout()
        header.addWidget(section_label(tr("svgtxt_groups_section_label")), 1)
        self._btn_add_group = QPushButton("+ " + tr("svgtxt_add_group_btn"))
        self._btn_add_group.clicked.connect(self._on_add_group)
        header.addWidget(self._btn_add_group)
        root.addLayout(header)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        container = QWidget()
        self._vbox = QVBoxLayout(container)
        self._vbox.setContentsMargins(0, 0, 0, 0)
        self._vbox.setSpacing(3)
        self._vbox.addStretch()
        self._scroll.setWidget(container)
        root.addWidget(self._scroll, 1)
        self.refresh()
        install_button_feedback(self)

    def refresh(self):
        while self._vbox.count() > 1:
            item = self._vbox.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for g in self.project.svg_text_groups:
            self._vbox.insertWidget(self._vbox.count() - 1, self._make_row(g))

    def fill_combo(self, combo: QComboBox):
        """Populate *combo* with (name, id); keeps the current selection."""
        prev = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        for g in self.project.svg_text_groups:
            combo.addItem(g.name, g.id)
        if combo.count() == 0:
            combo.addItem(tr("svgtxt_no_groups"), None)
        idx = combo.findData(prev)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        combo.blockSignals(False)

    def _group(self, gid):
        return next((x for x in self.project.svg_text_groups if x.id == gid), None)

    def _make_row(self, group) -> QWidget:
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(6)

        name_edit = QLineEdit(group.name)
        name_edit.setPlaceholderText(tr("svgtxt_group_name_placeholder"))
        name_edit.setMinimumWidth(80)

        def _on_name_changed(text, gid=group.id):
            g = self._group(gid)
            if g:
                g.name = text.strip() or tr("svgtxt_default_group_name")
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
            g = self._group(gid)
            if g:
                g.font_size_pt = val
                self.groups_changed.emit()

        spin.valueChanged.connect(_on_size_changed)
        h.addWidget(spin)

        del_btn = QPushButton("✕")
        del_btn.setFixedWidth(28)
        del_btn.setToolTip(tr("svgtxt_delete_group_btn"))

        def _on_delete(checked=False, gid=group.id):
            self.project.svg_text_groups = [x for x in self.project.svg_text_groups if x.id != gid]
            self.refresh()
            self.groups_changed.emit()

        del_btn.clicked.connect(_on_delete)
        h.addWidget(del_btn)

        # Scrolling the group list must never retune a font size.
        install_wheel_guard(row, self._scroll)
        install_button_feedback(row)
        return row

    def _on_add_group(self):
        g = SvgTextGroup(name=tr("svgtxt_default_group_name"), font_size_pt=12.0)
        self.project.svg_text_groups.append(g)
        self.refresh()
        self.group_added.emit(g.id)
        self.groups_changed.emit()
