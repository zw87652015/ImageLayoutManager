"""
Dialog for managing user-defined scale bar mappings.

Each mapping associates a human-readable name with a µm/pixel value so that
users can define the physical calibration of their own microscope(s) rather
than relying on the hard-coded defaults.
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QFormLayout, QLineEdit, QDoubleSpinBox, QDialogButtonBox,
    QLabel, QMessageBox, QWidget, QGroupBox, QComboBox
)
from PyQt6.QtCore import Qt

from src.app.scale_bar_mappings import load_mappings, save_mappings


class ScaleBarMappingsDialog(QDialog):
    """
    Modal dialog for creating, editing, and deleting scale bar mappings.

    Changes are committed to disk only when the user clicks OK.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Manage Scale Bar Mappings")
        self.setMinimumWidth(480)
        self.setMinimumHeight(360)

        # Working copy – we only persist on OK
        self._mappings = [dict(m) for m in load_mappings()]

        self._build_ui()
        self._populate_list()
        if self._mappings:
            self._list.setCurrentRow(0)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = QVBoxLayout(self)

        # Top: list + action buttons
        top = QHBoxLayout()
        root.addLayout(top)

        self._list = QListWidget()
        self._list.setAlternatingRowColors(True)
        self._list.currentRowChanged.connect(self._on_selection_changed)
        top.addWidget(self._list, stretch=2)

        btn_col = QVBoxLayout()
        btn_col.setAlignment(Qt.AlignmentFlag.AlignTop)
        top.addLayout(btn_col)

        self._btn_add = QPushButton("Add")
        self._btn_add.clicked.connect(self._add_mapping)
        btn_col.addWidget(self._btn_add)

        self._btn_delete = QPushButton("Delete")
        self._btn_delete.clicked.connect(self._delete_mapping)
        btn_col.addWidget(self._btn_delete)

        self._btn_up = QPushButton("Move Up")
        self._btn_up.clicked.connect(self._move_up)
        btn_col.addWidget(self._btn_up)

        self._btn_down = QPushButton("Move Down")
        self._btn_down.clicked.connect(self._move_down)
        btn_col.addWidget(self._btn_down)

        # Middle: edit form for the selected mapping
        edit_box = QGroupBox("Selected Mapping")
        edit_form = QFormLayout(edit_box)
        root.addWidget(edit_box)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("e.g.  10× objective")
        self._name_edit.textChanged.connect(self._on_form_changed)
        edit_form.addRow("Name:", self._name_edit)

        self._val_spin = QDoubleSpinBox()
        self._val_spin.setDecimals(6)
        self._val_spin.setRange(0.000001, 100000.0)
        self._val_spin.setSingleStep(0.001)
        self._val_spin.valueChanged.connect(self._on_form_changed)

        self._unit_combo = QComboBox()
        self._UNIT_TO_UM = {
            "m":  1e6,
            "cm": 1e4,
            "dm": 1e5,
            "mm": 1e3,
            "µm": 1.0,
            "nm": 1e-3,
            "pm": 1e-6,
            "fm": 1e-9,
        }
        self._unit_combo.addItems(list(self._UNIT_TO_UM.keys()))
        self._unit_combo.setCurrentText("µm")
        self._unit_combo.currentTextChanged.connect(self._on_form_changed)

        val_layout = QHBoxLayout()
        val_layout.setContentsMargins(0, 0, 0, 0)
        val_layout.addWidget(self._val_spin)
        val_layout.addWidget(self._unit_combo)
        val_layout.addWidget(QLabel("/ px"))

        val_widget = QWidget()
        val_widget.setLayout(val_layout)
        edit_form.addRow("Length per pixel:", val_widget)

        hint = QLabel(
            "Tip: measure a known feature in pixels and divide its physical size (µm) "
            "by that pixel count to obtain this value."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray; font-size: 11px;")
        edit_form.addRow(hint)

        # Bottom: OK / Cancel
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self._editing = False  # guard against recursive signal updates

    # ------------------------------------------------------------------
    # List population
    # ------------------------------------------------------------------

    def _populate_list(self):
        self._list.clear()
        for m in self._mappings:
            self._list.addItem(self._item_label(m))

    def _item_label(self, m: dict) -> str:
        unit = m.get("unit", "µm")
        factor = getattr(self, '_UNIT_TO_UM', {}).get(unit, 1.0)
        val = m["um_per_px"] / factor
        return f"{m['name']}  ({val:.6g} {unit}/px)"

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_selection_changed(self, row: int):
        has_sel = 0 <= row < len(self._mappings)
        self._btn_delete.setEnabled(has_sel)
        self._btn_up.setEnabled(row > 0)
        self._btn_down.setEnabled(has_sel and row < len(self._mappings) - 1)

        self._editing = True
        if has_sel:
            m = self._mappings[row]
            self._name_edit.setText(m["name"])
            unit = m.get("unit", "µm")
            self._unit_combo.setCurrentText(unit)
            factor = self._UNIT_TO_UM.get(unit, 1.0)
            self._val_spin.setValue(m["um_per_px"] / factor)
        else:
            self._name_edit.clear()
            self._unit_combo.setCurrentText("µm")
            self._val_spin.setValue(0.1301)
        self._editing = False

    def _on_form_changed(self):
        if self._editing:
            return
        row = self._list.currentRow()
        if not (0 <= row < len(self._mappings)):
            return
        self._mappings[row]["name"] = self._name_edit.text().strip()
        
        unit = self._unit_combo.currentText()
        factor = self._UNIT_TO_UM.get(unit, 1.0)
        
        self._mappings[row]["unit"] = unit
        self._mappings[row]["um_per_px"] = self._val_spin.value() * factor
        
        self._list.item(row).setText(self._item_label(self._mappings[row]))

    def _add_mapping(self):
        new = {"name": "New Mapping", "um_per_px": 0.1301, "unit": "µm"}
        self._mappings.append(new)
        self._list.addItem(self._item_label(new))
        self._list.setCurrentRow(len(self._mappings) - 1)
        self._name_edit.selectAll()
        self._name_edit.setFocus()

    def _delete_mapping(self):
        row = self._list.currentRow()
        if not (0 <= row < len(self._mappings)):
            return
        name = self._mappings[row]["name"]
        reply = QMessageBox.question(
            self, "Delete Mapping",
            f"Delete the mapping \"{name}\"?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._mappings.pop(row)
            self._list.takeItem(row)
            # Select adjacent row
            new_row = min(row, len(self._mappings) - 1)
            if new_row >= 0:
                self._list.setCurrentRow(new_row)

    def _move_up(self):
        row = self._list.currentRow()
        if row <= 0:
            return
        self._mappings[row - 1], self._mappings[row] = self._mappings[row], self._mappings[row - 1]
        self._populate_list()
        self._list.setCurrentRow(row - 1)

    def _move_down(self):
        row = self._list.currentRow()
        if row < 0 or row >= len(self._mappings) - 1:
            return
        self._mappings[row], self._mappings[row + 1] = self._mappings[row + 1], self._mappings[row]
        self._populate_list()
        self._list.setCurrentRow(row + 1)

    def _accept(self):
        # Validate: all names must be non-empty
        for m in self._mappings:
            if not m["name"].strip():
                QMessageBox.warning(self, "Invalid Mapping", "All mappings must have a non-empty name.")
                return
        save_mappings(self._mappings)
        self.accept()
