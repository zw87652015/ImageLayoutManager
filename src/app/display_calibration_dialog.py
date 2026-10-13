"""Per-monitor "Actual Size" calibration.

The user measures a drawn reference bar with a physical ruler, enters the
length they read, and the monitor's correction factor is updated so that
100% zoom matches real size. The factor is saved per screen by
``src.canvas.display_scale.set_screen_calibration`` on Save.
"""

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt
from PyQt6.QtGui import QPainter, QPalette, QPen
from PyQt6.QtWidgets import (
    QApplication, QDialog, QDialogButtonBox, QDoubleSpinBox, QHBoxLayout,
    QLabel, QPushButton, QVBoxLayout, QWidget,
)

from src.app.i18n import tr
from src.canvas import display_scale

NOMINAL_MM = 100
FALLBACK_NOMINAL_MM = 50
_BAR_MARGIN_PX = 120
_BAR_TOP = 22


class _ReferenceBar(QWidget):
    """Horizontal ruler drawn at the pending px-per-mm (true size when calibrated)."""

    def __init__(self, available_width: int, parent=None):
        super().__init__(parent)
        self._available_width = available_width
        self._px_per_mm = 4.0
        self.nominal_mm = NOMINAL_MM
        self.setMinimumHeight(56)

    def set_px_per_mm(self, px_per_mm: float):
        self._px_per_mm = px_per_mm
        if NOMINAL_MM * px_per_mm <= self._available_width - _BAR_MARGIN_PX:
            self.nominal_mm = NOMINAL_MM
        else:
            self.nominal_mm = FALLBACK_NOMINAL_MM
        self.updateGeometry()
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(int(self.nominal_mm * self._px_per_mm) + 40, 56)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = self.palette()
        fg = pal.color(QPalette.ColorRole.WindowText)
        accent = pal.color(QPalette.ColorRole.Highlight)
        x0 = 20.0
        bar_px = self.nominal_mm * self._px_per_mm

        painter.setPen(QPen(accent, 2))
        painter.drawLine(QPointF(x0, _BAR_TOP), QPointF(x0 + bar_px, _BAR_TOP))
        painter.setPen(QPen(fg, 1))
        for mm in range(0, self.nominal_mm + 1, 10):
            x = x0 + mm * self._px_per_mm
            length = 12 if mm % 50 == 0 else 6
            painter.drawLine(QPointF(x, _BAR_TOP), QPointF(x, _BAR_TOP + length))

        label_rect_y = _BAR_TOP + 16
        label_h = 16
        painter.drawText(QRectF(x0 - 30, label_rect_y, 60, label_h),
                         int(Qt.AlignmentFlag.AlignCenter), "0")
        painter.drawText(QRectF(x0 + bar_px - 40, label_rect_y, 80, label_h),
                         int(Qt.AlignmentFlag.AlignCenter), f"{self.nominal_mm} mm")
        painter.end()


class DisplayCalibrationDialog(QDialog):
    def __init__(self, screen, parent=None):
        super().__init__(parent)
        screen = screen or QApplication.primaryScreen()
        self._screen = screen
        self.setWindowTitle(tr("calib_title"))

        report = display_scale.screen_report(screen)
        self._base = report["base_px_per_mm"]
        self._pending = report["calibration"]

        instructions = QLabel(tr("calib_instructions"))
        instructions.setWordWrap(True)

        self._bar = _ReferenceBar(screen.availableGeometry().width())
        self._bar.set_px_per_mm(self._base * self._pending)

        self._spin = QDoubleSpinBox()
        self._spin.setRange(10.0, 400.0)
        self._spin.setDecimals(1)
        self._spin.setSuffix(" mm")
        self._spin.setValue(self._bar.nominal_mm)
        apply_btn = QPushButton(tr("calib_apply_measurement"))
        apply_btn.clicked.connect(self._on_apply_measurement)
        measure_row = QHBoxLayout()
        measure_row.addWidget(QLabel(tr("calib_measured")))
        measure_row.addWidget(self._spin)
        measure_row.addWidget(apply_btn)

        info = QLabel(
            tr("calib_monitor").format(
                model=report["model"], dpi=report["physical_dpi"],
                w=report["physical_w_mm"], h=report["physical_h_mm"])
            + " " + tr(f"calib_source_{report['source']}"))
        info.setWordWrap(True)

        self._factor_label = QLabel()
        reset_btn = QPushButton(tr("calib_reset"))
        reset_btn.clicked.connect(self._on_reset)
        factor_row = QHBoxLayout()
        factor_row.addWidget(self._factor_label)
        factor_row.addStretch(1)
        factor_row.addWidget(reset_btn)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(instructions)
        layout.addWidget(self._bar)
        layout.addLayout(measure_row)
        layout.addWidget(info)
        layout.addLayout(factor_row)
        layout.addWidget(buttons)
        self._refresh_factor()

    def _refresh_factor(self):
        self._bar.set_px_per_mm(self._base * self._pending)
        self._factor_label.setText(tr("calib_factor").format(pct=self._pending * 100))
        self._spin.setValue(self._bar.nominal_mm)

    def _on_apply_measurement(self):
        self._pending = display_scale.calibration_after_measurement(
            self._pending, self._bar.nominal_mm, self._spin.value())
        self._refresh_factor()

    def _on_reset(self):
        self._pending = 1.0
        self._refresh_factor()

    def _on_save(self):
        display_scale.set_screen_calibration(self._screen, self._pending)
        self.accept()
