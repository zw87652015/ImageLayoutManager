"""Dialog for choosing how raster images are encoded in a PDF export."""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QRadioButton, QButtonGroup,
    QSlider, QSpinBox, QDialogButtonBox,
)
from PyQt6.QtCore import Qt

from src.app.i18n import tr
from src.export.pdf_images import coerce_image_settings


class PdfExportOptionsDialog(QDialog):
    """Lets the user pick lossless or JPEG-compressed raster images for PDF export."""

    def __init__(self, parent=None, mode: str = "lossless", quality: int = 90):
        super().__init__(parent)
        mode, quality = coerce_image_settings(mode, quality)
        self.setWindowTitle(tr("pdf_opts_title"))
        self.setMinimumWidth(480)

        layout = QVBoxLayout(self)

        intro = QLabel(tr("pdf_opts_intro"))
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.lossless_radio = QRadioButton(tr("pdf_opts_lossless"))
        self.lossless_hint = self._hint(tr("pdf_opts_lossless_hint"))
        self.lossy_radio = QRadioButton(tr("pdf_opts_lossy"))
        self.lossy_hint = self._hint(tr("pdf_opts_lossy_hint"))
        group = QButtonGroup(self)
        group.addButton(self.lossless_radio)
        group.addButton(self.lossy_radio)
        self.lossy_radio.setChecked(mode == "lossy")
        self.lossless_radio.setChecked(mode != "lossy")
        self.lossy_radio.toggled.connect(self._update_enabled)

        self.quality_label = QLabel(tr("pdf_opts_quality"))
        self.quality_slider = QSlider(Qt.Orientation.Horizontal)
        self.quality_slider.setRange(1, 100)
        self.quality_slider.setValue(quality)
        self.quality_spin = QSpinBox()
        self.quality_spin.setRange(1, 100)
        self.quality_spin.setSuffix("%")
        self.quality_spin.setValue(quality)
        self.quality_slider.valueChanged.connect(self.quality_spin.setValue)
        self.quality_spin.valueChanged.connect(self.quality_slider.setValue)

        quality_row = QHBoxLayout()
        quality_row.addWidget(self.quality_label)
        quality_row.addWidget(self.quality_slider, 1)
        quality_row.addWidget(self.quality_spin)

        layout.addWidget(self.lossless_radio)
        layout.addWidget(self.lossless_hint)
        layout.addWidget(self.lossy_radio)
        layout.addWidget(self.lossy_hint)
        layout.addLayout(quality_row)
        self._update_enabled(self.lossy_radio.isChecked())

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _hint(text: str) -> QLabel:
        label = QLabel(text)
        label.setWordWrap(True)
        label.setStyleSheet("color: gray; font-style: italic; margin-left: 22px;")
        return label

    def _update_enabled(self, lossy: bool):
        for widget in (self.quality_label, self.quality_slider, self.quality_spin):
            widget.setEnabled(lossy)

    def selected_mode(self) -> str:
        return "lossy" if self.lossy_radio.isChecked() else "lossless"

    def selected_quality(self) -> int:
        return self.quality_spin.value()
