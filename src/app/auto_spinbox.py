"""QDoubleSpinBox whose minimum value means "Auto".

The special text shows the effective value in use ("Auto (12.3 mm)"), and the
first wheel/arrow step from Auto starts from that value instead of the minimum.
"""

import math

from PyQt6.QtWidgets import QAbstractSpinBox, QDoubleSpinBox

from src.utils.auto_value import auto_label, auto_step_target


class AutoDoubleSpinBox(QDoubleSpinBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._auto_value = None
        self._auto_base = ""

    def set_auto_value(self, value):
        try:
            number = float(value)
        except (TypeError, ValueError):
            number = math.nan
        self._auto_value = number if math.isfinite(number) else None
        self._apply_special_text()

    def _apply_special_text(self):
        if not self._auto_base:
            return
        label = auto_label(self._auto_base, self._auto_value, self.decimals(), self.suffix())
        super().setSpecialValueText(label)

    def setSpecialValueText(self, text):
        self._auto_base = text
        self._apply_special_text()

    def setSuffix(self, suffix):
        super().setSuffix(suffix)
        self._apply_special_text()

    def setDecimals(self, decimals):
        super().setDecimals(decimals)
        self._apply_special_text()

    def stepBy(self, steps):
        target = auto_step_target(self.value(), self.minimum(), self.maximum(),
                                  self._auto_value, self.singleStep(), steps,
                                  self.decimals())
        if target is None:
            super().stepBy(steps)
        else:
            self.setValue(target)

    def stepEnabled(self):
        at_minimum = abs(self.value() - self.minimum()) < 10 ** -(self.decimals() + 1)
        if (self._auto_value is not None and at_minimum
                and self._auto_value > self.minimum()):
            return (QAbstractSpinBox.StepEnabledFlag.StepUpEnabled
                    | QAbstractSpinBox.StepEnabledFlag.StepDownEnabled)
        return super().stepEnabled()
