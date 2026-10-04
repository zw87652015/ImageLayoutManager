"""Modal Figure Size dialog for the Plot Editor."""

import math

from PyQt6.QtCore import QSignalBlocker
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QDialog,
                             QDialogButtonBox, QDoubleSpinBox,
                             QFormLayout, QHBoxLayout, QLabel,
                             QPushButton, QVBoxLayout)

from .document import MAX_DIMENSION_MM, PlotDocumentError
from .figure_size import FigureSize
from .i18n import tr


_ASPECT_PRESETS = (
    ('size_custom', None),
    ('1:1', 1.0),
    ('4:3', 4.0 / 3.0),
    ('3:2', 3.0 / 2.0),
    ('16:9', 16.0 / 9.0),
    ('3:4', 3.0 / 4.0),
    ('1:2', 1.0 / 2.0),
)


class FigureSizeDialog(QDialog):
    """Stage width/height edits; Apply is one undoable resize."""

    def __init__(self, size, locked=False, parent=None):
        super().__init__(parent)
        self.setObjectName('plotFigureSizeDialog')
        self.setWindowTitle(tr('act_figure_size'))
        self.setModal(True)
        self._size = FigureSize(size.width_mm, size.height_mm)
        self._locked = bool(locked)

        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.width_spin = QDoubleSpinBox(self)
        self.width_spin.setObjectName('plotWidthMm')
        self.height_spin = QDoubleSpinBox(self)
        self.height_spin.setObjectName('plotHeightMm')
        for spin, value in ((self.width_spin, self._size.width_mm),
                            (self.height_spin, self._size.height_mm)):
            spin.setDecimals(6 if value < 0.01 else 2)
            spin.setRange(min(0.01, value), float(MAX_DIMENSION_MM))
            spin.setSuffix(' mm')
            spin.setKeyboardTracking(False)
            spin.setValue(value)
            form.addRow(tr('size_width')
                        if spin is self.width_spin
                        else tr('size_height'), spin)
        layout.addLayout(form)

        row = QHBoxLayout()
        self.aspect_combo = QComboBox(self)
        self.aspect_combo.setObjectName('plotAspectPreset')
        for label_key, ratio in _ASPECT_PRESETS:
            self.aspect_combo.addItem(
                tr(label_key) if ratio is None else label_key, ratio)
        self.aspect_combo.activated.connect(self._preset_chosen)
        row.addWidget(QLabel(tr('size_ratio'), self))
        row.addWidget(self.aspect_combo, 1)
        self.lock_check = QCheckBox(tr('size_lock'), self)
        self.lock_check.setObjectName('plotAspectLock')
        self.lock_check.setChecked(self._locked)
        row.addWidget(self.lock_check)
        self.swap_button = QPushButton(tr('size_swap'), self)
        self.swap_button.setObjectName('plotSizeSwap')
        self.swap_button.clicked.connect(self._swap)
        row.addWidget(self.swap_button)
        layout.addLayout(row)

        hint = QLabel(tr('figure_size_hint'), self)
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.error_label = QLabel(self)
        self.error_label.setObjectName('plotFigureSizeError')
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        layout.addWidget(self.error_label)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel, self)
        self._buttons.button(
            QDialogButtonBox.StandardButton.Ok).setText(
                tr('size_apply'))
        self._buttons.button(
            QDialogButtonBox.StandardButton.Cancel).setText(
                tr('size_cancel'))
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)

        self.width_spin.valueChanged.connect(
            lambda v: self._resize('width', v))
        self.height_spin.valueChanged.connect(
            lambda v: self._resize('height', v))
        self._sync()

    def figure_size(self):
        return self._size

    def locked(self):
        return self.lock_check.isChecked()

    # ── staged edits ─────────────────────────────────────────────────
    def _resize(self, dimension, value):
        try:
            self._size = self._size.resized(
                dimension, value, self.lock_check.isChecked())
        except (ValueError, PlotDocumentError) as e:
            self._show_error(str(e))
            return
        self.error_label.hide()
        self._sync()

    def _preset_chosen(self, index):
        ratio = self.aspect_combo.itemData(index)
        if ratio is None:
            return
        try:
            self._size = self._size.with_ratio(float(ratio))
        except (ValueError, PlotDocumentError) as e:
            self._show_error(str(e))
            return
        self.error_label.hide()
        self._sync()

    def _swap(self):
        try:
            self._size = self._size.swapped()
        except (ValueError, PlotDocumentError) as e:
            self._show_error(str(e))
            return
        self.error_label.hide()
        self._sync()

    def _show_error(self, message):
        self.error_label.setText(message)
        self.error_label.show()
        self._sync()

    def _sync(self):
        for spin in (self.width_spin, self.height_spin,
                     self.aspect_combo):
            blocker = QSignalBlocker(spin)
            if spin is self.width_spin:
                spin.setValue(self._size.width_mm)
            elif spin is self.height_spin:
                spin.setValue(self._size.height_mm)
            else:
                current = self._size.width_mm / self._size.height_mm
                index = 0
                for i in range(1, self.aspect_combo.count()):
                    ratio = self.aspect_combo.itemData(i)
                    if ratio is not None and math.isclose(
                            current, float(ratio), rel_tol=1e-4):
                        index = i
                        break
                self.aspect_combo.setCurrentIndex(index)
