from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QGroupBox, QFormLayout, QHBoxLayout,
    QLabel, QSpinBox, QDoubleSpinBox, QComboBox, 
    QLineEdit, QPushButton, QCheckBox
)
from PyQt6.QtCore import pyqtSignal, Qt
from src.model.enums import FitMode

class Inspector(QWidget):
    # Signals for property changes
    cell_property_changed = pyqtSignal(dict) # {property: value}
    text_property_changed = pyqtSignal(dict) # {property: value}
    row_property_changed = pyqtSignal(dict) # {property: value}
    project_property_changed = pyqtSignal(dict) # {property: value}
    corner_label_changed = pyqtSignal(dict) # {"anchor": str, "text": str}
    apply_color_to_group = pyqtSignal(str, str) # (subtype, color_hex) - apply color to all labels in group
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        # --- Project Settings Group (Default View) ---
        self.project_group = QGroupBox("Project Settings")
        self.project_layout = QFormLayout()
        
        self.dpi_spin = QSpinBox()
        self.dpi_spin.setRange(72, 2400)
        self.dpi_spin.setValue(600)
        self.dpi_spin.setSuffix(" dpi")
        self.dpi_spin.valueChanged.connect(
            lambda v: self.project_property_changed.emit({"dpi": v})
        )
        self.project_layout.addRow("DPI:", self.dpi_spin)
        
        # Page Size Presets
        self.page_preset = QComboBox()
        self.page_preset.addItems([
            "Custom",
            "A4 (210×297mm)",
            "Letter (216×279mm)",
            "Single Column (85×120mm)",
            "1.5 Column (114×160mm)",
            "Double Column (178×240mm)"
        ])
        self.page_preset.currentTextChanged.connect(self._on_page_preset_changed)
        self.project_layout.addRow("Page Preset:", self.page_preset)
        
        # Page Size (Manual entry)
        self.page_w = QDoubleSpinBox()
        self.page_w.setRange(10, 1000)
        self.page_w.setSuffix(" mm")
        self.page_w.valueChanged.connect(
            lambda v: self.project_property_changed.emit({"page_width_mm": v})
        )
        self.project_layout.addRow("Page Width:", self.page_w)
        
        self.page_h = QDoubleSpinBox()
        self.page_h.setRange(10, 1000)
        self.page_h.setSuffix(" mm")
        self.page_h.valueChanged.connect(
            lambda v: self.project_property_changed.emit({"page_height_mm": v})
        )
        self.project_layout.addRow("Page Height:", self.page_h)
        
        # Margins
        self.m_top = self._create_spinbox(0, 100, self._emit_project_margins)
        self.m_bottom = self._create_spinbox(0, 100, self._emit_project_margins)
        self.m_left = self._create_spinbox(0, 100, self._emit_project_margins)
        self.m_right = self._create_spinbox(0, 100, self._emit_project_margins)
        
        self.project_layout.addRow("Margin Top:", self.m_top)
        self.project_layout.addRow("Margin Bottom:", self.m_bottom)
        self.project_layout.addRow("Margin Left:", self.m_left)
        self.project_layout.addRow("Margin Right:", self.m_right)
        
        # Corner Label Settings
        self.project_layout.addRow(QLabel("<b>Corner Labels</b>"))
        
        self.corner_label_font = QComboBox()
        self.corner_label_font.addItems(["Arial", "Times New Roman", "Courier New", "Verdana"])
        self.corner_label_font.currentTextChanged.connect(
            lambda t: self.project_property_changed.emit({"corner_label_font_family": t})
        )
        self.project_layout.addRow("Font:", self.corner_label_font)
        
        self.corner_label_size = QSpinBox()
        self.corner_label_size.setRange(1, 72)
        self.corner_label_size.setValue(12)
        self.corner_label_size.valueChanged.connect(
            lambda v: self.project_property_changed.emit({"corner_label_font_size": v})
        )
        self.project_layout.addRow("Size:", self.corner_label_size)
        
        self.corner_label_color = QComboBox()
        self.corner_label_color.addItems(["Black", "White"])
        self.corner_label_color.currentTextChanged.connect(self._on_corner_label_color_changed)
        self.project_layout.addRow("Color:", self.corner_label_color)
        
        # Gap between cells
        self.project_layout.addRow(QLabel("<b>Layout</b>"))
        self.gap_spin = QDoubleSpinBox()
        self.gap_spin.setRange(0, 20)
        self.gap_spin.setSingleStep(0.5)
        self.gap_spin.setSuffix(" mm")
        self.gap_spin.valueChanged.connect(
            lambda v: self.project_property_changed.emit({"gap_mm": v})
        )
        self.project_layout.addRow("Cell Gap:", self.gap_spin)
        
        self.project_group.setLayout(self.project_layout)
        self.layout.addWidget(self.project_group)
        
        # --- Cell Properties Group ---
        self.cell_group = QGroupBox("Selected Cell")
        self.cell_layout = QFormLayout()
        
        self.fit_mode_combo = QComboBox()
        self.fit_mode_combo.addItems([m.value for m in FitMode])
        self.fit_mode_combo.currentTextChanged.connect(
            lambda t: self.cell_property_changed.emit({"fit_mode": t})
        )
        self.cell_layout.addRow("Fit Mode:", self.fit_mode_combo)
        
        self.rotation_combo = QComboBox()
        self.rotation_combo.addItems(["0", "90", "180", "270"])
        self.rotation_combo.currentTextChanged.connect(
            lambda t: self.cell_property_changed.emit({"rotation": int(t)})
        )
        self.cell_layout.addRow("Rotation:", self.rotation_combo)
        
        # Alignment
        self.align_h_combo = QComboBox()
        self.align_h_combo.addItems(["left", "center", "right"])
        self.align_h_combo.currentTextChanged.connect(
            lambda t: self.cell_property_changed.emit({"align_h": t})
        )
        self.cell_layout.addRow("Align H:", self.align_h_combo)
        
        self.align_v_combo = QComboBox()
        self.align_v_combo.addItems(["top", "center", "bottom"])
        self.align_v_combo.currentTextChanged.connect(
            lambda t: self.cell_property_changed.emit({"align_v": t})
        )
        self.cell_layout.addRow("Align V:", self.align_v_combo)
        
        self.pad_top = self._create_spinbox(0, 100, self._emit_padding)
        self.pad_bottom = self._create_spinbox(0, 100, self._emit_padding)
        self.pad_left = self._create_spinbox(0, 100, self._emit_padding)
        self.pad_right = self._create_spinbox(0, 100, self._emit_padding)
        
        self.cell_layout.addRow("Pad Top (mm):", self.pad_top)
        self.cell_layout.addRow("Pad Bottom:", self.pad_bottom)
        self.cell_layout.addRow("Pad Left:", self.pad_left)
        self.cell_layout.addRow("Pad Right:", self.pad_right)

        self.corner_label_tl = QLineEdit()
        self.corner_label_tl.editingFinished.connect(
            lambda: self.corner_label_changed.emit({"anchor": "top_left_inside", "text": self.corner_label_tl.text()})
        )
        self.cell_layout.addRow("Label TL:", self.corner_label_tl)

        self.corner_label_tr = QLineEdit()
        self.corner_label_tr.editingFinished.connect(
            lambda: self.corner_label_changed.emit({"anchor": "top_right_inside", "text": self.corner_label_tr.text()})
        )
        self.cell_layout.addRow("Label TR:", self.corner_label_tr)

        self.corner_label_bl = QLineEdit()
        self.corner_label_bl.editingFinished.connect(
            lambda: self.corner_label_changed.emit({"anchor": "bottom_left_inside", "text": self.corner_label_bl.text()})
        )
        self.cell_layout.addRow("Label BL:", self.corner_label_bl)

        self.corner_label_br = QLineEdit()
        self.corner_label_br.editingFinished.connect(
            lambda: self.corner_label_changed.emit({"anchor": "bottom_right_inside", "text": self.corner_label_br.text()})
        )
        self.cell_layout.addRow("Label BR:", self.corner_label_br)

        # --- Scale Bar Controls ---
        self.cell_layout.addRow(QLabel("— Scale Bar —"))
        
        self.scale_bar_enabled = QCheckBox("Enable Scale Bar")
        self.scale_bar_enabled.stateChanged.connect(self._emit_scale_bar)
        self.cell_layout.addRow(self.scale_bar_enabled)
        
        self.scale_bar_mode = QComboBox()
        self.scale_bar_mode.addItems(["rgb", "bayer"])
        self.scale_bar_mode.currentTextChanged.connect(self._emit_scale_bar)
        self.cell_layout.addRow("Mode:", self.scale_bar_mode)
        
        self.scale_bar_length = QDoubleSpinBox()
        self.scale_bar_length.setRange(0.1, 1000.0)
        self.scale_bar_length.setSingleStep(1.0)
        self.scale_bar_length.setSuffix(" µm")
        self.scale_bar_length.valueChanged.connect(self._emit_scale_bar)
        self.cell_layout.addRow("Length:", self.scale_bar_length)
        
        self.scale_bar_color = QComboBox()
        self.scale_bar_color.addItems(["White", "Black"])
        self.scale_bar_color.currentTextChanged.connect(self._emit_scale_bar)
        self.cell_layout.addRow("Color:", self.scale_bar_color)
        
        self.scale_bar_show_text = QCheckBox("Show Text")
        self.scale_bar_show_text.stateChanged.connect(self._emit_scale_bar)
        self.cell_layout.addRow(self.scale_bar_show_text)
        
        self.scale_bar_thickness = QDoubleSpinBox()
        self.scale_bar_thickness.setRange(0.1, 5.0)
        self.scale_bar_thickness.setSingleStep(0.1)
        self.scale_bar_thickness.setSuffix(" mm")
        self.scale_bar_thickness.valueChanged.connect(self._emit_scale_bar)
        self.cell_layout.addRow("Thickness:", self.scale_bar_thickness)
        
        self.scale_bar_position = QComboBox()
        self.scale_bar_position.addItems(["bottom_left", "bottom_center", "bottom_right"])
        self.scale_bar_position.currentTextChanged.connect(self._emit_scale_bar)
        self.cell_layout.addRow("Position:", self.scale_bar_position)
        
        self.scale_bar_offset_x = QDoubleSpinBox()
        self.scale_bar_offset_x.setRange(0, 50)
        self.scale_bar_offset_x.setSingleStep(0.5)
        self.scale_bar_offset_x.valueChanged.connect(self._emit_scale_bar)
        self.cell_layout.addRow("Offset X (mm):", self.scale_bar_offset_x)
        
        self.scale_bar_offset_y = QDoubleSpinBox()
        self.scale_bar_offset_y.setRange(0, 50)
        self.scale_bar_offset_y.setSingleStep(0.5)
        self.scale_bar_offset_y.valueChanged.connect(self._emit_scale_bar)
        self.cell_layout.addRow("Offset Y (mm):", self.scale_bar_offset_y)
        
        self.cell_group.setLayout(self.cell_layout)
        self.layout.addWidget(self.cell_group)
        self.cell_group.hide()

        # --- Label Cell Properties Group ---
        self.label_cell_group = QGroupBox("Label Cell Settings")
        self.label_cell_layout = QFormLayout()

        self.label_scheme = QComboBox()
        self.label_scheme.addItems(["(a)", "(A)", "a", "A"])
        self.label_scheme.currentTextChanged.connect(
            lambda t: self.project_property_changed.emit({"label_scheme": t})
        )
        self.label_cell_layout.addRow("Scheme:", self.label_scheme)

        self.label_font = QComboBox()
        self.label_font.addItems(["Arial", "Times New Roman", "Courier New", "Verdana"])
        self.label_font.currentTextChanged.connect(
            lambda t: self.project_property_changed.emit({"label_font_family": t})
        )
        self.label_cell_layout.addRow("Font:", self.label_font)

        self.label_size = QSpinBox()
        self.label_size.setRange(1, 72)
        self.label_size.setValue(8)
        self.label_size.valueChanged.connect(
            lambda v: self.project_property_changed.emit({"label_font_size": v})
        )
        self.label_cell_layout.addRow("Size (pt):", self.label_size)

        self.label_bold = QCheckBox("Bold")
        self.label_bold.setChecked(True)
        self.label_bold.toggled.connect(
            lambda b: self.project_property_changed.emit({"label_font_weight": "bold" if b else "normal"})
        )
        self.label_cell_layout.addRow("", self.label_bold)

        self.label_color = QComboBox()
        self.label_color.addItems(["Black", "White"])
        self.label_color.currentTextChanged.connect(self._on_label_color_changed)
        self.label_cell_layout.addRow("Color:", self.label_color)

        self.label_align = QComboBox()
        self.label_align.addItems(["Left", "Center", "Right"])
        self.label_align.currentTextChanged.connect(self._on_label_align_preset_changed)
        self.label_cell_layout.addRow("Align:", self.label_align)

        self.label_offset_x = QDoubleSpinBox()
        self.label_offset_x.setRange(-100.0, 100.0)
        self.label_offset_x.setSingleStep(0.5)
        self.label_offset_x.setDecimals(1)
        self.label_offset_x.setSuffix(" mm")
        self.label_offset_x.setValue(0.0)
        self.label_offset_x.valueChanged.connect(
            lambda v: self.project_property_changed.emit({"label_offset_x": v})
        )
        self.label_cell_layout.addRow("Offset X:", self.label_offset_x)

        self.label_offset_y = QDoubleSpinBox()
        self.label_offset_y.setRange(-100.0, 100.0)
        self.label_offset_y.setSingleStep(0.5)
        self.label_offset_y.setDecimals(1)
        self.label_offset_y.setSuffix(" mm")
        self.label_offset_y.setValue(0.0)
        self.label_offset_y.valueChanged.connect(
            lambda v: self.project_property_changed.emit({"label_offset_y": v})
        )
        self.label_cell_layout.addRow("Offset Y:", self.label_offset_y)

        self.label_row_height = QDoubleSpinBox()
        self.label_row_height.setRange(0.0, 50.0)
        self.label_row_height.setSingleStep(0.5)
        self.label_row_height.setDecimals(1)
        self.label_row_height.setSuffix(" mm")
        self.label_row_height.setSpecialValueText("Auto")
        self.label_row_height.setValue(0.0)
        self.label_row_height.valueChanged.connect(
            lambda v: self.project_property_changed.emit({"label_row_height": v})
        )
        self.label_cell_layout.addRow("Row Height:", self.label_row_height)

        self.label_attach = QComboBox()
        self.label_attach.addItems(["Figure", "Grid"])
        self.label_attach.currentTextChanged.connect(
            lambda t: self.project_property_changed.emit({"label_attach_to": t.lower()})
        )
        self.label_cell_layout.addRow("Attach To:", self.label_attach)

        self.label_cell_group.setLayout(self.label_cell_layout)
        self.layout.addWidget(self.label_cell_group)
        self.label_cell_group.hide()

        # --- Row Properties Group ---
        self.row_group = QGroupBox("Row Settings")
        self.row_layout = QFormLayout()
        
        self.row_cols = QSpinBox()
        self.row_cols.setRange(1, 100)
        self.row_cols.valueChanged.connect(
            lambda v: self.row_property_changed.emit({"column_count": v})
        )
        self.row_layout.addRow("Columns:", self.row_cols)
        
        self.row_height = QDoubleSpinBox()
        self.row_height.setRange(0.1, 10.0)
        self.row_height.setSingleStep(0.1)
        self.row_height.valueChanged.connect(
            lambda v: self.row_property_changed.emit({"height_ratio": v})
        )
        self.row_layout.addRow("Height Ratio:", self.row_height)
        
        # Column ratios (comma-separated, e.g. "1,2,1" for 25%-50%-25%)
        self.col_ratios_edit = QLineEdit()
        self.col_ratios_edit.setPlaceholderText("e.g. 1,2,1 (equal if empty)")
        self.col_ratios_edit.editingFinished.connect(self._emit_column_ratios)
        self.row_layout.addRow("Col Ratios:", self.col_ratios_edit)
        
        self.row_group.setLayout(self.row_layout)
        self.layout.addWidget(self.row_group)
        self.row_group.hide()
        
        # --- Text Properties Group ---
        self.text_group = QGroupBox("Selected Text")
        self.text_layout = QFormLayout()
        
        self.text_content = QLineEdit()
        self.text_content.editingFinished.connect(
            lambda: self.text_property_changed.emit({"text": self.text_content.text()})
        )
        self.text_layout.addRow("Content:", self.text_content)
        
        self.font_family = QComboBox()
        self.font_family.addItems(["Arial", "Times New Roman", "Courier New", "Verdana"]) # Basic list
        self.font_family.currentTextChanged.connect(
            lambda t: self.text_property_changed.emit({"font_family": t})
        )
        self.text_layout.addRow("Font:", self.font_family)
        
        self.font_size = QSpinBox()
        self.font_size.setRange(1, 72)
        self.font_size.valueChanged.connect(
            lambda v: self.text_property_changed.emit({"font_size_pt": v})
        )
        self.text_layout.addRow("Size (pt):", self.font_size)
        
        self.is_bold = QCheckBox("Bold")
        self.is_bold.toggled.connect(
            lambda b: self.text_property_changed.emit({"font_weight": "bold" if b else "normal"})
        )
        self.text_layout.addRow("", self.is_bold)
        
        # Color control for individual text item
        color_row = QHBoxLayout()
        self.text_color = QComboBox()
        self.text_color.addItems(["Black", "White"])
        self.text_color.currentTextChanged.connect(self._on_text_color_changed)
        color_row.addWidget(self.text_color)
        
        self.apply_color_btn = QPushButton("Apply to All")
        self.apply_color_btn.setToolTip("Apply this color to all labels in the same group")
        self.apply_color_btn.clicked.connect(self._on_apply_color_to_group)
        color_row.addWidget(self.apply_color_btn)
        
        color_widget = QWidget()
        color_widget.setLayout(color_row)
        self.text_layout.addRow("Color:", color_widget)
        
        # Store current text item subtype for apply-to-group
        self._current_text_subtype = None
        
        # Offset controls for cell-scoped labels
        self.offset_x = QDoubleSpinBox()
        self.offset_x.setRange(0, 100)
        self.offset_x.setSingleStep(0.5)
        self.offset_x.setSuffix(" mm")
        self.offset_x.valueChanged.connect(
            lambda v: self.text_property_changed.emit({"offset_x": v})
        )
        self.text_layout.addRow("Offset X:", self.offset_x)
        
        self.offset_y = QDoubleSpinBox()
        self.offset_y.setRange(0, 100)
        self.offset_y.setSingleStep(0.5)
        self.offset_y.setSuffix(" mm")
        self.offset_y.valueChanged.connect(
            lambda v: self.text_property_changed.emit({"offset_y": v})
        )
        self.text_layout.addRow("Offset Y:", self.offset_y)
        
        self.text_group.setLayout(self.text_layout)
        self.layout.addWidget(self.text_group)
        self.text_group.hide()
        
        # --- No Selection ---
        self.no_selection_label = QLabel("No Selection")
        self.no_selection_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(self.no_selection_label)

    def _emit_project_margins(self):
        self.project_property_changed.emit({
            "margin_top_mm": self.m_top.value(),
            "margin_bottom_mm": self.m_bottom.value(),
            "margin_left_mm": self.m_left.value(),
            "margin_right_mm": self.m_right.value()
        })

    def _create_spinbox(self, min_val, max_val, callback):
        sb = QDoubleSpinBox()
        sb.setRange(min_val, max_val)
        sb.valueChanged.connect(callback)
        return sb

    def _emit_padding(self):
        self.cell_property_changed.emit({
            "padding_top": self.pad_top.value(),
            "padding_bottom": self.pad_bottom.value(),
            "padding_left": self.pad_left.value(),
            "padding_right": self.pad_right.value()
        })

    def _emit_scale_bar(self):
        """Emit all scale bar properties as a single cell property change."""
        color_text = self.scale_bar_color.currentText()
        color_hex = "#000000" if color_text == "Black" else "#FFFFFF"
        self.cell_property_changed.emit({
            "scale_bar_enabled": self.scale_bar_enabled.isChecked(),
            "scale_bar_mode": self.scale_bar_mode.currentText(),
            "scale_bar_length_um": self.scale_bar_length.value(),
            "scale_bar_color": color_hex,
            "scale_bar_show_text": self.scale_bar_show_text.isChecked(),
            "scale_bar_thickness_mm": self.scale_bar_thickness.value(),
            "scale_bar_position": self.scale_bar_position.currentText(),
            "scale_bar_offset_x": self.scale_bar_offset_x.value(),
            "scale_bar_offset_y": self.scale_bar_offset_y.value(),
        })

    def _emit_column_ratios(self):
        text = self.col_ratios_edit.text().strip()
        if not text:
            self.row_property_changed.emit({"column_ratios": []})
            return
        try:
            ratios = [float(x.strip()) for x in text.split(",") if x.strip()]
            self.row_property_changed.emit({"column_ratios": ratios})
        except ValueError:
            pass  # Invalid input, ignore

    def _on_page_preset_changed(self, preset_text: str):
        presets = {
            "A4 (210×297mm)": (210, 297),
            "Letter (216×279mm)": (216, 279),
            "Single Column (85×120mm)": (85, 120),
            "1.5 Column (114×160mm)": (114, 160),
            "Double Column (178×240mm)": (178, 240),
        }
        if preset_text in presets:
            w, h = presets[preset_text]
            self.blockSignals(True)
            self.page_w.setValue(w)
            self.page_h.setValue(h)
            self.blockSignals(False)
            self.project_property_changed.emit({"page_width_mm": w, "page_height_mm": h})

    def _on_label_color_changed(self, color_text: str):
        color_hex = "#000000" if color_text == "Black" else "#FFFFFF"
        self.project_property_changed.emit({"label_color": color_hex})

    def _on_corner_label_color_changed(self, color_text: str):
        color_hex = "#000000" if color_text == "Black" else "#FFFFFF"
        self.project_property_changed.emit({"corner_label_color": color_hex})

    def _on_label_align_preset_changed(self, text: str):
        align = text.lower()
        # Reset offsets to 0 when a preset is selected
        self.label_offset_x.blockSignals(True)
        self.label_offset_y.blockSignals(True)
        self.label_offset_x.setValue(0.0)
        self.label_offset_y.setValue(0.0)
        self.label_offset_x.blockSignals(False)
        self.label_offset_y.blockSignals(False)
        self.project_property_changed.emit({
            "label_align": align,
            "label_offset_x": 0.0,
            "label_offset_y": 0.0,
        })

    def _on_text_color_changed(self, color_text: str):
        """Handle individual text item color change."""
        color_hex = "#000000" if color_text == "Black" else "#FFFFFF"
        self.text_property_changed.emit({"color": color_hex})

    def _on_apply_color_to_group(self):
        """Apply current color to all labels in the same group (numbering or corner)."""
        color_text = self.text_color.currentText()
        color_hex = "#000000" if color_text == "Black" else "#FFFFFF"
        # Emit signal with subtype and color
        # subtype is None for numbering labels, "corner" for corner labels
        self.apply_color_to_group.emit(self._current_text_subtype or "numbering", color_hex)

    def set_selection(self, item_type, data=None, row_data=None, project_data=None):
        """
        item_type: 'cell' | 'label_cell' | 'text' | None
        data: dict of current values (for cell/text/label_cell)
        row_data: dict of row values (only if item_type is 'cell')
        project_data: dict of project values (always passed or only when item_type is None)
        """
        if item_type == 'label_cell':
            self.no_selection_label.hide()
            self.project_group.hide()
            self.cell_group.hide()
            self.row_group.hide()
            self.text_group.hide()
            self.label_cell_group.show()

            if data:
                self.blockSignals(True)
                self.label_scheme.setCurrentText(data.get("label_scheme", "(a)"))
                self.label_font.setCurrentText(data.get("label_font_family", "Arial"))
                self.label_size.setValue(data.get("label_font_size", 12))
                self.label_bold.setChecked(data.get("label_font_weight", "bold") == "bold")
                label_color_hex = data.get("label_color", "#000000")
                self.label_color.setCurrentText("White" if label_color_hex == "#FFFFFF" else "Black")
                label_align = data.get("label_align", "center")
                self.label_align.setCurrentText(label_align.capitalize())
                self.label_offset_x.setValue(data.get("label_offset_x", 0.0))
                self.label_offset_y.setValue(data.get("label_offset_y", 0.0))
                self.label_row_height.setValue(data.get("label_row_height", 0.0))
                label_attach = data.get("label_attach_to", "figure")
                self.label_attach.setCurrentText(label_attach.capitalize())
                self.blockSignals(False)
            return

        if item_type == 'cell':
            self.no_selection_label.hide()
            self.project_group.hide()
            self.text_group.hide()
            self.label_cell_group.hide()
            self.cell_group.show()
            
            # Show row group
            if row_data:
                self.row_group.show()
                self.blockSignals(True)
                self.row_cols.setValue(row_data.get("column_count", 1))
                self.row_height.setValue(row_data.get("height_ratio", 1.0))
                # Column ratios
                col_ratios = row_data.get("column_ratios", [])
                if col_ratios:
                    self.col_ratios_edit.setText(",".join(str(r) for r in col_ratios))
                else:
                    self.col_ratios_edit.setText("")
                self.blockSignals(False)
            else:
                self.row_group.hide()
            
            # Block signals to prevent feedback loop
            self.blockSignals(True)
            self.fit_mode_combo.setCurrentText(data.get("fit_mode", "contain"))
            self.rotation_combo.setCurrentText(str(data.get("rotation", 0)))
            self.align_h_combo.setCurrentText(data.get("align_h", "center"))
            self.align_v_combo.setCurrentText(data.get("align_v", "center"))
            self.pad_top.setValue(data.get("padding_top", 0))
            self.pad_bottom.setValue(data.get("padding_bottom", 0))
            self.pad_left.setValue(data.get("padding_left", 0))
            self.pad_right.setValue(data.get("padding_right", 0))

            corner_labels = data.get("corner_labels", {}) if data else {}
            self.corner_label_tl.setText(corner_labels.get("top_left_inside", ""))
            self.corner_label_tr.setText(corner_labels.get("top_right_inside", ""))
            self.corner_label_bl.setText(corner_labels.get("bottom_left_inside", ""))
            self.corner_label_br.setText(corner_labels.get("bottom_right_inside", ""))

            # Scale bar settings
            self.scale_bar_enabled.setChecked(data.get("scale_bar_enabled", False))
            self.scale_bar_mode.setCurrentText(data.get("scale_bar_mode", "rgb"))
            self.scale_bar_length.setValue(data.get("scale_bar_length_um", 10.0))
            sb_color = data.get("scale_bar_color", "#FFFFFF")
            self.scale_bar_color.setCurrentText("Black" if sb_color == "#000000" else "White")
            self.scale_bar_show_text.setChecked(data.get("scale_bar_show_text", True))
            self.scale_bar_thickness.setValue(data.get("scale_bar_thickness_mm", 0.5))
            self.scale_bar_position.setCurrentText(data.get("scale_bar_position", "bottom_right"))
            self.scale_bar_offset_x.setValue(data.get("scale_bar_offset_x", 2.0))
            self.scale_bar_offset_y.setValue(data.get("scale_bar_offset_y", 2.0))
            self.blockSignals(False)
            
        elif item_type == 'text':
            self.no_selection_label.hide()
            self.project_group.hide()
            self.cell_group.hide()
            self.row_group.hide()
            self.label_cell_group.hide()
            self.text_group.show()
            
            self.blockSignals(True)
            self.text_content.setText(data.get("text", ""))
            self.font_family.setCurrentText(data.get("font_family", "Arial"))
            self.font_size.setValue(data.get("font_size_pt", 12))
            self.is_bold.setChecked(data.get("font_weight") == "bold")
            
            # Set text color
            color_hex = data.get("color", "#000000")
            self.text_color.setCurrentText("White" if color_hex == "#FFFFFF" else "Black")
            
            # Store subtype for apply-to-group functionality
            self._current_text_subtype = data.get("subtype")
            
            # Update apply button text based on subtype
            if self._current_text_subtype == "corner":
                self.apply_color_btn.setText("Apply to All Corner")
            else:
                self.apply_color_btn.setText("Apply to All Numbering")
            
            # Show offset controls only for cell-scoped labels
            is_cell_scoped = data.get("scope") == "cell"
            self.offset_x.setVisible(is_cell_scoped)
            self.offset_y.setVisible(is_cell_scoped)
            self.text_layout.labelForField(self.offset_x).setVisible(is_cell_scoped)
            self.text_layout.labelForField(self.offset_y).setVisible(is_cell_scoped)
            
            if is_cell_scoped:
                self.offset_x.setValue(data.get("offset_x", 2.0))
                self.offset_y.setValue(data.get("offset_y", 2.0))
            self.blockSignals(False)
            
        else:
            self.cell_group.hide()
            self.row_group.hide()
            self.text_group.hide()
            self.label_cell_group.hide()
            self.no_selection_label.hide() # We show project settings instead
            
            # When item_type is None, 'data' might actually be project_data (legacy call)
            effective_project_data = project_data if project_data else data
            if effective_project_data:
                self.project_group.show()
                self.blockSignals(True)
                self.dpi_spin.setValue(effective_project_data.get("dpi", 600))
                self.page_w.setValue(effective_project_data.get("page_width_mm", 210))
                self.page_h.setValue(effective_project_data.get("page_height_mm", 297))
                self.m_top.setValue(effective_project_data.get("margin_top_mm", 10))
                self.m_bottom.setValue(effective_project_data.get("margin_bottom_mm", 10))
                self.m_left.setValue(effective_project_data.get("margin_left_mm", 10))
                self.m_right.setValue(effective_project_data.get("margin_right_mm", 10))
                
                # Corner Labels
                self.corner_label_font.setCurrentText(effective_project_data.get("corner_label_font_family", "Arial"))
                self.corner_label_size.setValue(effective_project_data.get("corner_label_font_size", 12))
                corner_label_color_hex = effective_project_data.get("corner_label_color", "#000000")
                self.corner_label_color.setCurrentText("White" if corner_label_color_hex == "#FFFFFF" else "Black")

                self.gap_spin.setValue(effective_project_data.get("gap_mm", 2.0))
                
                self.blockSignals(False)
            else:
                self.project_group.hide()
                self.no_selection_label.show()
