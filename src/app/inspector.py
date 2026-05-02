from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QGroupBox, QFormLayout, QHBoxLayout, QGridLayout,
    QLabel, QSpinBox, QDoubleSpinBox, QComboBox, QFontComboBox,
    QLineEdit, QPushButton, QToolButton, QButtonGroup, QCheckBox,
    QScrollArea, QColorDialog, QFrame
)
from PyQt6.QtCore import pyqtSignal, Qt, QPropertyAnimation, QEasingCurve, pyqtProperty
from PyQt6.QtGui import QColor, QPainter, QPen
from typing import Optional
import math
from src.model.enums import FitMode
from src.app.scale_bar_mappings import load_mappings, mapping_names
from src.app.i18n import tr


class LockButton(QToolButton):
    """QToolButton that plays a brief radial-burst animation when locked."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._burst = 0.0
        self._burst_color = QColor("#888888")
        self._anim = QPropertyAnimation(self, b"burst", self)
        self._anim.setDuration(320)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def play_lock_burst(self, color: QColor):
        self._burst_color = color
        self._anim.stop()
        self._anim.start()

    @pyqtProperty(float)
    def burst(self) -> float:
        return self._burst

    @burst.setter
    def burst(self, value: float):
        self._burst = value
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._burst <= 0.0:
            return
        # Burst lines radiate from just above the icon centre (shackle area)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx = self.width() / 2
        cy = self.height() / 2 - self.height() * 0.12  # slightly above centre
        # opacity: full for first 40%, then fade out
        t = self._burst
        opacity = (1.0 - (t - 0.4) / 0.6) if t > 0.4 else 1.0
        opacity = max(0.0, min(1.0, opacity))
        # line length grows then shrinks
        max_r = self.width() * 0.55
        inner = max_r * 0.18 + max_r * 0.22 * t
        outer = inner + max_r * 0.35 * min(t * 2, 1.0)
        color = QColor(self._burst_color)
        color.setAlphaF(opacity * 0.85)
        pen = QPen(color, 1.4)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        n_lines = 6
        angle_offset = -15  # degrees, so lines don't land on icon edges
        for i in range(n_lines):
            angle = math.radians(angle_offset + i * 360 / n_lines)
            x1 = cx + inner * math.cos(angle)
            y1 = cy + inner * math.sin(angle)
            x2 = cx + outer * math.cos(angle)
            y2 = cy + outer * math.sin(angle)
            painter.drawLine(int(x1), int(y1), int(x2), int(y2))
        painter.end()


class ColorPickerWidget(QWidget):
    """Drop-in replacement for a two-item Black/White QComboBox.
    Keeps Black and White as quick presets; a swatch button opens QColorDialog
    for any arbitrary color."""

    colorChanged = pyqtSignal(str)  # hex string, e.g. "#FF0000"

    _PRESETS = [("#000000", "opt_color_black"),
                ("#FFFFFF", "opt_color_white")]

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)

        self._color = "#000000"

        self._combo = QComboBox()
        for hex_val, key in self._PRESETS:
            self._combo.addItem(tr(key), hex_val)
        self._combo.addItem(tr("opt_color_custom"), None)   # always-visible Custom entry
        self._combo.currentIndexChanged.connect(self._on_combo_changed)
        layout.addWidget(self._combo, stretch=1)

        self._swatch = QPushButton()
        self._swatch.setFixedWidth(26)
        self._swatch.setToolTip(tr("color_custom_tooltip"))
        self._swatch.clicked.connect(self._open_dialog)
        layout.addWidget(self._swatch)

        self._refresh_swatch()

    # ── public API ──────────────────────────────────────────────────

    def get_color(self) -> str:
        return self._color

    def set_color(self, hex_color: str):
        c = (hex_color or "#000000").upper()
        self._color = c
        self._sync_combo()
        self._refresh_swatch()

    def retranslate_ui(self):
        """Re-apply translated labels to preset items, preserving current color."""
        self._combo.blockSignals(True)
        for i, (_, key) in enumerate(self._PRESETS):
            self._combo.setItemText(i, tr(key))
        self._combo.setItemText(len(self._PRESETS), tr("opt_color_custom"))
        self._combo.blockSignals(False)
        self._sync_combo()

    # ── internals ───────────────────────────────────────────────────

    def _sync_combo(self):
        """Update the combo selection to match _color without emitting signals."""
        self._combo.blockSignals(True)
        custom_idx = self._combo.count() - 1
        for i in range(custom_idx):
            if (self._combo.itemData(i) or "").upper() == self._color:
                self._combo.setCurrentIndex(i)
                self._combo.blockSignals(False)
                return
        self._combo.setCurrentIndex(custom_idx)
        self._combo.blockSignals(False)

    def _refresh_swatch(self):
        # Single f-string so {{ and }} escape to literal braces in the CSS.
        self._swatch.setStyleSheet(
            f"QPushButton {{ background-color: {self._color}; border: 1px solid #888; border-radius: 2px; }}"
        )

    def _on_combo_changed(self, index: int):
        hex_val = self._combo.itemData(index)
        if hex_val:                          # preset selected
            self._color = hex_val.upper()
            self._refresh_swatch()
            self.colorChanged.emit(self._color)
        else:                                # "Custom" selected from dropdown
            self._open_dialog()

    def _open_dialog(self):
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtGui import QPalette

        # Build a palette-matched stylesheet for the dialog.
        # This is necessary because the app stylesheet contains
        # "QGroupBox QWidget { background: transparent }" — a descendant
        # selector that matches the dialog (which is parented to a widget
        # inside a GroupBox) and makes its background transparent.
        # Setting the dialog's own stylesheet overrides that rule.
        pal = QApplication.instance().palette()
        win   = pal.color(QPalette.ColorRole.Window).name()
        text  = pal.color(QPalette.ColorRole.WindowText).name()
        base  = pal.color(QPalette.ColorRole.Base).name()
        btn    = pal.color(QPalette.ColorRole.Button).name()
        btn_tx = pal.color(QPalette.ColorRole.ButtonText).name()
        hi     = pal.color(QPalette.ColorRole.Highlight).name()
        hi_tx  = pal.color(QPalette.ColorRole.HighlightedText).name()
        border = pal.color(QPalette.ColorRole.Mid).name()

        dlg = QColorDialog(QColor(self._color), self)
        dlg.setOption(QColorDialog.ColorDialogOption.DontUseNativeDialog)
        dlg.setWindowTitle(tr("color_dialog_title"))
        dlg.setStyleSheet(
            f"QWidget {{ background-color: {win}; color: {text}; }}"
            f"QLineEdit, QSpinBox, QDoubleSpinBox {{"
            f"  background-color: {base}; color: {text};"
            f"  border: 1px solid {border}; border-radius: 3px; }}"
            f"QPushButton {{"
            f"  background-color: {btn}; color: {btn_tx};"
            f"  border: 1px solid {border}; border-radius: 3px; padding: 4px 10px; }}"
            f"QPushButton:hover {{ background-color: {hi}; color: {hi_tx}; }}"
            f"QLabel {{ background: transparent; color: {text}; }}"
        )

        if not dlg.exec():
            self._sync_combo()
            return
        color = dlg.currentColor()
        if not color.isValid():
            self._sync_combo()
            return
        self._color = color.name().upper()
        self._sync_combo()
        self._refresh_swatch()
        self.colorChanged.emit(self._color)


class CollapsibleSection(QWidget):
    """Inspector panel section: clickable uppercase header + collapsible body."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setObjectName("collapsibleSection")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._header = QWidget()
        self._header.setObjectName("sectionHead")
        self._header.setCursor(Qt.CursorShape.PointingHandCursor)
        self._header.setFixedHeight(34)
        h_lay = QHBoxLayout(self._header)
        h_lay.setContentsMargins(14, 0, 14, 0)
        h_lay.setSpacing(6)

        self._chevron = QLabel("▾")
        self._chevron.setObjectName("sectionChevron")
        self._chevron.setFixedWidth(12)
        h_lay.addWidget(self._chevron)

        self._title_lbl = QLabel()
        self._title_lbl.setObjectName("sectionTitle")
        self.set_title(title)
        h_lay.addWidget(self._title_lbl, 1)

        outer.addWidget(self._header)

        self._body = QWidget()
        self._body.setObjectName("sectionBody")
        self._form = QFormLayout(self._body)
        self._form.setVerticalSpacing(8)
        self._form.setHorizontalSpacing(10)
        self._form.setContentsMargins(14, 4, 14, 14)
        self._form.setLabelAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self._form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow
        )
        outer.addWidget(self._body)

        sep = QFrame()
        sep.setObjectName("sectionDivider")
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(1)
        outer.addWidget(sep)

        self._collapsed = False
        self._header.mousePressEvent = lambda e: self._toggle()

    def set_title(self, title: str) -> None:
        self._title_lbl.setText(title.upper())

    def _toggle(self) -> None:
        self._collapsed = not self._collapsed
        self._body.setVisible(not self._collapsed)
        self._chevron.setText("▸" if self._collapsed else "▾")


class Inspector(QWidget):
    # Signals for property changes
    cell_property_changed = pyqtSignal(dict) # {property: value}
    text_property_changed = pyqtSignal(dict) # {property: value}
    row_property_changed = pyqtSignal(dict) # {property: value}
    project_property_changed = pyqtSignal(dict) # {property: value}
    corner_label_changed = pyqtSignal(dict) # {"anchor": str, "text": str}
    apply_color_to_group = pyqtSignal(str, str) # (subtype, color_hex) - apply color to all labels in group
    label_text_changed = pyqtSignal(str, str) # (text_item_id, new_text)
    subcell_ratio_changed = pyqtSignal(str, float) # (cell_id, new_ratio) - change a sub-cell's size ratio
    pip_property_changed = pyqtSignal(dict) # {property: value} for selected PiP
    pip_delete_requested = pyqtSignal()     # user clicked Delete PiP button
    # Size Group signals
    size_group_create_requested = pyqtSignal()                     # create new group & assign current selection
    size_group_pinned_changed = pyqtSignal(str, float, float)      # (group_id, w_mm, h_mm) — 0 = auto
    size_group_rename_requested = pyqtSignal(str, str)             # (group_id, new_name)
    size_group_delete_requested = pyqtSignal(str)                  # group_id
    
    def __init__(self, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        outer.addWidget(scroll)

        self._lbl_registry: list[tuple[str, QLabel]] = []

        container = QWidget()
        self.layout = QVBoxLayout(container)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.layout.setSpacing(4)
        self.layout.setContentsMargins(4, 4, 4, 4)
        scroll.setWidget(container)

        self.setMinimumWidth(300)
        
        # --- Project Settings Group (Default View) ---
        self.project_group = CollapsibleSection("Project Settings")
        self.project_layout = self.project_group._form
        
        self.dpi_spin = QSpinBox()
        self.dpi_spin.setRange(72, 2400)
        self.dpi_spin.setValue(600)
        self.dpi_spin.setSuffix(" dpi")
        self.dpi_spin.valueChanged.connect(
            lambda v: self.project_property_changed.emit({"dpi": v})
        )
        self.project_layout.addRow(self._fl("lbl_dpi"), self.dpi_spin)
        
        # Page Size Presets
        self.page_preset = QComboBox()
        self._page_preset_options = [
            "opt_page_custom",
            "opt_page_a4",
            "opt_page_letter",
            "opt_page_single",
            "opt_page_1_5",
            "opt_page_double",
            "opt_page_nature_single",
            "opt_page_nature_double",
            "opt_page_cell_single",
            "opt_page_cell_double",
            "opt_page_science_single",
            "opt_page_science_double",
            "opt_page_pnas_single",
            "opt_page_pnas_double",
        ]
        self.page_preset.addItems([tr(k) for k in self._page_preset_options])
        self.page_preset.currentTextChanged.connect(self._on_page_preset_changed)
        self.project_layout.addRow(self._fl("lbl_page_preset"), self.page_preset)
        
        # Page Size (Manual entry)
        self.page_w = QDoubleSpinBox()
        self.page_w.setRange(10, 1000)
        self.page_w.setSuffix(" mm")
        self.page_w.valueChanged.connect(
            lambda v: self.project_property_changed.emit({"page_width_mm": v})
        )
        self.project_layout.addRow(self._fl("lbl_page_width"), self.page_w)
        
        self.page_h = QDoubleSpinBox()
        self.page_h.setRange(10, 1000)
        self.page_h.setSuffix(" mm")
        self.page_h.valueChanged.connect(
            lambda v: self.project_property_changed.emit({"page_height_mm": v})
        )
        self.project_layout.addRow(self._fl("lbl_page_height"), self.page_h)
        
        # Margins
        self.m_top = self._create_spinbox(0, 100, self._emit_project_margins)
        self.m_bottom = self._create_spinbox(0, 100, self._emit_project_margins)
        self.m_left = self._create_spinbox(0, 100, self._emit_project_margins)
        self.m_right = self._create_spinbox(0, 100, self._emit_project_margins)
        
        self.project_layout.addRow(self._fl("lbl_margin_top"),    self.m_top)
        self.project_layout.addRow(self._fl("lbl_margin_bottom"), self.m_bottom)
        self.project_layout.addRow(self._fl("lbl_margin_left"),   self.m_left)
        self.project_layout.addRow(self._fl("lbl_margin_right"),  self.m_right)
        
        # Grid Settings
        self._sec_grid = QLabel("<b>Grid Settings</b>")
        self.project_layout.addRow(self._sec_grid)
        
        self.grid_mode = QComboBox()
        self.grid_mode.addItems([tr("opt_grid_stretch"), tr("opt_grid_fixed")])
        self.grid_mode.currentIndexChanged.connect(self._on_grid_mode_changed)
        self.project_layout.addRow(self._fl("lbl_grid_mode"), self.grid_mode)

        self.row_alignment = QComboBox()
        self.row_alignment.addItems([tr("opt_row_left"), tr("opt_row_center"), tr("opt_row_right")])
        self.row_alignment.currentIndexChanged.connect(self._on_row_alignment_changed)
        self.project_layout.addRow(self._fl("lbl_row_align"), self.row_alignment)
        
        # Corner Label Settings
        self._sec_corner = QLabel("<b>Corner Labels</b>")
        self.project_layout.addRow(self._sec_corner)
        
        self.corner_label_font = QFontComboBox()
        self.corner_label_font.setFontFilters(QFontComboBox.FontFilter.ScalableFonts)
        self.corner_label_font.currentTextChanged.connect(
            lambda t: self.project_property_changed.emit({"corner_label_font_family": t})
        )
        self.project_layout.addRow(self._fl("lbl_font"), self.corner_label_font)
        
        self.corner_label_size = QSpinBox()
        self.corner_label_size.setRange(1, 72)
        self.corner_label_size.setValue(12)
        self.corner_label_size.valueChanged.connect(
            lambda v: self.project_property_changed.emit({"corner_label_font_size": v})
        )
        self.project_layout.addRow(self._fl("lbl_size"), self.corner_label_size)
        
        self.corner_label_color = ColorPickerWidget()
        self.corner_label_color.colorChanged.connect(self._on_corner_label_color_changed)
        self.project_layout.addRow(self._fl("lbl_color"), self.corner_label_color)
        
        # Label Placement (out-of-cell variants: above/below/left/right or in_cell)
        self._sec_label_placement = QLabel(tr("sec_label_placement"))
        self.project_layout.addRow(self._sec_label_placement)

        self.label_placement_combo = QComboBox()
        # (i18n_key, value)
        self._label_placement_options = [
            ("placement_in_cell",   "in_cell"),
            ("placement_row_above", "label_row_above"),
            ("placement_row_below", "label_row_below"),
            ("placement_col_left",  "label_col_left"),
            ("placement_col_right", "label_col_right"),
        ]
        for key, _val in self._label_placement_options:
            self.label_placement_combo.addItem(tr(key))
        self.label_placement_combo.currentIndexChanged.connect(
            lambda i: self.project_property_changed.emit(
                {"label_placement": self._label_placement_options[i][1]}
            )
        )
        self.project_layout.addRow(self._fl("lbl_label_placement"), self.label_placement_combo)

        self.label_col_width_spin = QDoubleSpinBox()
        self.label_col_width_spin.setRange(1.0, 200.0)
        self.label_col_width_spin.setSingleStep(0.5)
        self.label_col_width_spin.setDecimals(1)
        self.label_col_width_spin.setSuffix(" mm")
        self.label_col_width_spin.valueChanged.connect(
            lambda v: self.project_property_changed.emit({"label_col_width": float(v)})
        )
        self.project_layout.addRow(self._fl("lbl_label_col_width"), self.label_col_width_spin)

        # Gap between cells
        self._sec_layout = QLabel("<b>Layout</b>")
        self.project_layout.addRow(self._sec_layout)
        self.gap_spin = QDoubleSpinBox()
        self.gap_spin.setRange(0, 20)
        self.gap_spin.setSingleStep(0.5)
        self.gap_spin.setSuffix(" mm")
        self.gap_spin.valueChanged.connect(
            lambda v: self.project_property_changed.emit({"gap_mm": v})
        )
        self.project_layout.addRow(self._fl("lbl_cell_gap"), self.gap_spin)
        
        self.layout.addWidget(self.project_group)
        
        # --- Cell Properties Group ---
        self.cell_group = CollapsibleSection("Selected Cell")
        self.cell_layout = self.cell_group._form
        
        self.fit_mode_combo = QComboBox()
        self.fit_mode_combo.addItems([m.value for m in FitMode])
        self.fit_mode_combo.currentTextChanged.connect(
            lambda t: self.cell_property_changed.emit({"fit_mode": t})
        )
        self.cell_layout.addRow(self._fl("lbl_fit_mode"), self.fit_mode_combo)
        
        self.rotation_combo = QComboBox()
        self.rotation_combo.addItems(["0", "90", "180", "270"])
        self.rotation_combo.currentTextChanged.connect(
            lambda t: self.cell_property_changed.emit({"rotation": int(t)})
        )
        self.cell_layout.addRow(self._fl("lbl_rotation"), self.rotation_combo)
        
        # Alignment — 3x3 grid of checkable arrow buttons (PowerPoint-style).
        # Each cell maps to a (align_h, align_v) pair; clicking emits both properties together.
        self.align_grid_widget = QWidget()
        _align_grid = QGridLayout(self.align_grid_widget)
        _align_grid.setContentsMargins(0, 0, 0, 0)
        _align_grid.setHorizontalSpacing(2)
        _align_grid.setVerticalSpacing(2)

        self.align_button_group = QButtonGroup(self)
        self.align_button_group.setExclusive(True)
        self._align_buttons: dict[tuple[str, str], QToolButton] = {}

        # (row, col) -> ((align_h, align_v), glyph, tooltip_key)
        _ALIGN_CELLS = [
            (0, 0, "left",   "top",    "↖", "tip_align_tl"),
            (0, 1, "center", "top",    "↑", "tip_align_tc"),
            (0, 2, "right",  "top",    "↗", "tip_align_tr"),
            (1, 0, "left",   "center", "←", "tip_align_ml"),
            (1, 1, "center", "center", "•", "tip_align_mc"),
            (1, 2, "right",  "center", "→", "tip_align_mr"),
            (2, 0, "left",   "bottom", "↙", "tip_align_bl"),
            (2, 1, "center", "bottom", "↓", "tip_align_bc"),
            (2, 2, "right",  "bottom", "↘", "tip_align_br"),
        ]
        for r, c, h, v, glyph, tip_key in _ALIGN_CELLS:
            btn = QToolButton()
            btn.setText(glyph)
            btn.setCheckable(True)
            btn.setAutoRaise(False)
            btn.setFixedSize(26, 26)
            btn.setToolTip(tr(tip_key))
            btn.clicked.connect(
                lambda _checked=False, _h=h, _v=v:
                    self.cell_property_changed.emit({"align_h": _h, "align_v": _v})
            )
            _align_grid.addWidget(btn, r, c)
            self.align_button_group.addButton(btn)
            self._align_buttons[(h, v)] = btn

        self.cell_layout.addRow(self._fl("lbl_alignment"), self.align_grid_widget)
        
        self.freeform_section_label = QLabel("— Freeform Geometry —")
        self.cell_layout.addRow(self.freeform_section_label)

        self.freeform_x = self._create_spinbox(-1000, 1000, self._emit_freeform)
        self.freeform_y = self._create_spinbox(-1000, 1000, self._emit_freeform)
        self.freeform_w = self._create_spinbox(1, 1000, self._emit_freeform)
        self.freeform_h = self._create_spinbox(1, 1000, self._emit_freeform)

        self.cell_layout.addRow(self._fl("lbl_pos_x"),    self.freeform_x)
        self.cell_layout.addRow(self._fl("lbl_pos_y"),    self.freeform_y)
        self.cell_layout.addRow(self._fl("lbl_width_mm"),  self.freeform_w)
        self.cell_layout.addRow(self._fl("lbl_height_mm"), self.freeform_h)

        self._sec_grid_override = QLabel("— Grid Size Override (0=Auto) —")
        self.cell_layout.addRow(self._sec_grid_override)
        self.override_w = self._create_spinbox(0, 1000, self._on_override_w_changed)
        self.override_h = self._create_spinbox(0, 1000, self._on_override_h_changed)
        self.cell_layout.addRow(self._fl("lbl_width_mm"),  self.override_w)
        self.aspect_lock_btn = LockButton()
        self.aspect_lock_btn.setCheckable(True)
        self.aspect_lock_btn.setChecked(False)
        self.aspect_lock_btn.setToolTip(tr("tooltip_aspect_lock"))
        self.aspect_lock_btn.toggled.connect(self._on_aspect_lock_toggled)
        self.cell_layout.addRow(self._fl("lbl_aspect_lock"), self.aspect_lock_btn)
        self.cell_layout.addRow(self._fl("lbl_height_mm"), self.override_h)

        # --- Size Group section -------------------------------------------
        self._sec_size_group = QLabel(tr("sec_size_group"))
        self.cell_layout.addRow(self._sec_size_group)

        # Dropdown: None | <each group> | + Create New Group
        self.size_group_combo = QComboBox()
        self.size_group_combo.currentIndexChanged.connect(self._on_size_group_combo_changed)
        self.cell_layout.addRow(self._fl("lbl_size_group"), self.size_group_combo)

        # Group name (rename)
        self.size_group_name_edit = QLineEdit()
        self.size_group_name_edit.editingFinished.connect(self._emit_size_group_rename)
        self.cell_layout.addRow(self._fl("lbl_size_group_name"), self.size_group_name_edit)

        # Pinned shared W/H
        self.size_group_pinned_w = self._create_spinbox(0, 1000, self._emit_size_group_pinned)
        self.size_group_pinned_h = self._create_spinbox(0, 1000, self._emit_size_group_pinned)
        self.cell_layout.addRow(self._fl("lbl_size_group_pinned_w"), self.size_group_pinned_w)
        self.cell_layout.addRow(self._fl("lbl_size_group_pinned_h"), self.size_group_pinned_h)

        # Members summary + Delete button
        self.size_group_members_label = QLabel("")
        self.cell_layout.addRow(self.size_group_members_label)
        self.size_group_delete_btn = QPushButton()
        self.size_group_delete_btn.clicked.connect(self._emit_size_group_delete)
        self.cell_layout.addRow(self.size_group_delete_btn)

        # Internal state
        self._current_size_group_id: Optional[str] = None
        self._size_groups_cache: list = []  # list of group dicts

        self._sec_padding = QLabel("— Padding —")
        self.cell_layout.addRow(self._sec_padding)
        self.pad_top = self._create_spinbox(-100, 100, self._emit_padding)
        self.pad_bottom = self._create_spinbox(-100, 100, self._emit_padding)
        self.pad_left = self._create_spinbox(-100, 100, self._emit_padding)
        self.pad_right = self._create_spinbox(-100, 100, self._emit_padding)
        
        self.cell_layout.addRow(self._fl("lbl_pad_top"),    self.pad_top)
        self.cell_layout.addRow(self._fl("lbl_pad_bottom"), self.pad_bottom)
        self.cell_layout.addRow(self._fl("lbl_pad_left"),   self.pad_left)
        self.cell_layout.addRow(self._fl("lbl_pad_right"),  self.pad_right)

        self.corner_label_tl = QLineEdit()
        self.corner_label_tl.editingFinished.connect(
            lambda: self.corner_label_changed.emit({"anchor": "top_left_inside", "text": self.corner_label_tl.text()})
        )
        self.cell_layout.addRow(self._fl("lbl_corner_tl"), self.corner_label_tl)

        self.corner_label_tr = QLineEdit()
        self.corner_label_tr.editingFinished.connect(
            lambda: self.corner_label_changed.emit({"anchor": "top_right_inside", "text": self.corner_label_tr.text()})
        )
        self.cell_layout.addRow(self._fl("lbl_corner_tr"), self.corner_label_tr)

        self.corner_label_bl = QLineEdit()
        self.corner_label_bl.editingFinished.connect(
            lambda: self.corner_label_changed.emit({"anchor": "bottom_left_inside", "text": self.corner_label_bl.text()})
        )
        self.cell_layout.addRow(self._fl("lbl_corner_bl"), self.corner_label_bl)

        self.corner_label_br = QLineEdit()
        self.corner_label_br.editingFinished.connect(
            lambda: self.corner_label_changed.emit({"anchor": "bottom_right_inside", "text": self.corner_label_br.text()})
        )
        self.cell_layout.addRow(self._fl("lbl_corner_br"), self.corner_label_br)

        # --- Scale Bar Group ---
        self.scale_bar_group = CollapsibleSection(tr("grp_scale_bar"))
        self.scale_bar_layout = self.scale_bar_group._form
        
        self.scale_bar_enabled = QCheckBox(tr("chk_scale_enabled"))
        self.scale_bar_enabled.stateChanged.connect(self._emit_scale_bar)
        self.scale_bar_layout.addRow(self.scale_bar_enabled)
        
        mapping_row = QHBoxLayout()
        self.scale_bar_mode = QComboBox()
        self._refresh_mapping_combo()
        self.scale_bar_mode.currentTextChanged.connect(self._on_scale_bar_mode_changed)
        mapping_row.addWidget(self.scale_bar_mode, stretch=1)
        self._manage_btn = QPushButton(tr("btn_manage"))
        self._manage_btn.setFixedWidth(90)
        self._manage_btn.clicked.connect(self._open_mappings_dialog)
        mapping_row.addWidget(self._manage_btn)
        self.scale_bar_layout.addRow(self._fl("lbl_mapping"), mapping_row)

        length_row = QHBoxLayout()
        self.scale_bar_length = QDoubleSpinBox()
        self.scale_bar_length.setRange(1e-9, 1e9)
        self.scale_bar_length.setDecimals(6)
        self.scale_bar_length.setSingleStep(1.0)
        self.scale_bar_length.valueChanged.connect(self._emit_scale_bar)
        length_row.addWidget(self.scale_bar_length, stretch=1)

        self.scale_bar_unit = QComboBox()
        self._UNITS = ["m", "cm", "dm", "mm", "µm", "nm", "pm", "fm"]
        self.scale_bar_unit.addItems(self._UNITS)
        self.scale_bar_unit.setCurrentText("µm")
        self.scale_bar_unit.setFixedWidth(65)
        self.scale_bar_unit.currentTextChanged.connect(self._on_scale_bar_unit_changed)
        length_row.addWidget(self.scale_bar_unit)

        length_widget = QWidget()
        length_widget.setLayout(length_row)
        self.scale_bar_layout.addRow(self._fl("lbl_length"), length_widget)
        
        self.scale_bar_color = ColorPickerWidget()
        self.scale_bar_color.set_color("#FFFFFF")
        self.scale_bar_color.colorChanged.connect(self._emit_scale_bar)
        self.scale_bar_layout.addRow(self._fl("lbl_color"), self.scale_bar_color)
        
        self.scale_bar_show_text = QCheckBox(tr("chk_scale_text"))
        self.scale_bar_show_text.stateChanged.connect(self._emit_scale_bar)
        self.scale_bar_layout.addRow(self.scale_bar_show_text)
        
        self.scale_bar_custom_text = QLineEdit()
        self.scale_bar_custom_text.setPlaceholderText(tr("placeholder_scale_bar_text"))
        self.scale_bar_custom_text.editingFinished.connect(self._emit_scale_bar)
        self.scale_bar_layout.addRow(self._fl("lbl_custom_text"), self.scale_bar_custom_text)
        
        self.scale_bar_text_size = QDoubleSpinBox()
        self.scale_bar_text_size.setRange(0.5, 10.0)
        self.scale_bar_text_size.setSingleStep(0.1)
        self.scale_bar_text_size.setSuffix(" mm")
        self.scale_bar_text_size.setValue(2.0)
        self.scale_bar_text_size.valueChanged.connect(self._emit_scale_bar)
        self.scale_bar_layout.addRow(self._fl("lbl_text_size"), self.scale_bar_text_size)
        
        self.scale_bar_thickness = QDoubleSpinBox()
        self.scale_bar_thickness.setRange(0.1, 5.0)
        self.scale_bar_thickness.setSingleStep(0.1)
        self.scale_bar_thickness.setSuffix(" mm")
        self.scale_bar_thickness.valueChanged.connect(self._emit_scale_bar)
        self.scale_bar_layout.addRow(self._fl("lbl_thickness"), self.scale_bar_thickness)
        
        self.scale_bar_position = QComboBox()
        self.scale_bar_position.addItems(["bottom_left", "bottom_center", "bottom_right"])
        self.scale_bar_position.currentTextChanged.connect(self._emit_scale_bar)
        self.scale_bar_layout.addRow(self._fl("lbl_position"), self.scale_bar_position)
        
        self.scale_bar_offset_x = QDoubleSpinBox()
        self.scale_bar_offset_x.setRange(0, 50)
        self.scale_bar_offset_x.setSingleStep(0.5)
        self.scale_bar_offset_x.valueChanged.connect(self._emit_scale_bar)
        self.scale_bar_layout.addRow(self._fl("lbl_offset_x_mm"), self.scale_bar_offset_x)
        
        self.scale_bar_offset_y = QDoubleSpinBox()
        self.scale_bar_offset_y.setRange(0, 50)
        self.scale_bar_offset_y.setSingleStep(0.5)
        self.scale_bar_offset_y.valueChanged.connect(self._emit_scale_bar)
        self.scale_bar_layout.addRow(self._fl("lbl_offset_y_mm"), self.scale_bar_offset_y)

        self.layout.addWidget(self.cell_group)
        self.layout.addWidget(self.scale_bar_group)
        self.cell_group.hide()
        self.scale_bar_group.hide()

        # --- Label Cell Properties Group ---
        self.label_cell_group = CollapsibleSection("Label Cell Settings")
        self.label_cell_layout = self.label_cell_group._form

        self._current_label_text_id = None  # Track which text item is being edited
        self.label_text_edit = QLineEdit()
        self.label_text_edit.setPlaceholderText(tr("placeholder_label_text"))
        self.label_text_edit.editingFinished.connect(self._on_label_text_edited)
        self.label_cell_layout.addRow(self._fl("lbl_text"), self.label_text_edit)

        self.label_scheme = QComboBox()
        self.label_scheme.addItems(["(a)", "(A)", "a", "A"])
        self.label_scheme.currentTextChanged.connect(
            lambda t: self.project_property_changed.emit({"label_scheme": t})
        )
        self.label_cell_layout.addRow(self._fl("lbl_scheme"), self.label_scheme)

        self.label_font = QFontComboBox()
        self.label_font.setFontFilters(QFontComboBox.FontFilter.ScalableFonts)
        self.label_font.currentTextChanged.connect(
            lambda t: self.project_property_changed.emit({"label_font_family": t})
        )
        self.label_cell_layout.addRow(self._fl("lbl_font"), self.label_font)

        self.label_size = QSpinBox()
        self.label_size.setRange(1, 72)
        self.label_size.setValue(8)
        self.label_size.valueChanged.connect(
            lambda v: self.project_property_changed.emit({"label_font_size": v})
        )
        self.label_cell_layout.addRow(self._fl("lbl_size_pt"), self.label_size)

        self.label_bold = QCheckBox(tr("chk_bold"))
        self.label_bold.setChecked(True)
        self.label_bold.toggled.connect(
            lambda b: self.project_property_changed.emit({"label_font_weight": "bold" if b else "normal"})
        )
        self.label_cell_layout.addRow("", self.label_bold)

        self.label_color = ColorPickerWidget()
        self.label_color.colorChanged.connect(self._on_label_color_changed)
        self.label_cell_layout.addRow(self._fl("lbl_color"), self.label_color)

        self.label_align = QComboBox()
        self.label_align.addItems([tr("opt_align_left"), tr("opt_align_center"), tr("opt_align_right")])
        self.label_align.currentIndexChanged.connect(self._on_label_align_preset_changed)
        self.label_cell_layout.addRow(self._fl("lbl_align"), self.label_align)

        self.label_offset_x = QDoubleSpinBox()
        self.label_offset_x.setRange(-100.0, 100.0)
        self.label_offset_x.setSingleStep(0.5)
        self.label_offset_x.setDecimals(1)
        self.label_offset_x.setSuffix(" mm")
        self.label_offset_x.setValue(0.0)
        self.label_offset_x.valueChanged.connect(
            lambda v: self.project_property_changed.emit({"label_offset_x": v})
        )
        self.label_cell_layout.addRow(self._fl("lbl_offset_x"), self.label_offset_x)

        self.label_offset_y = QDoubleSpinBox()
        self.label_offset_y.setRange(-100.0, 100.0)
        self.label_offset_y.setSingleStep(0.5)
        self.label_offset_y.setDecimals(1)
        self.label_offset_y.setSuffix(" mm")
        self.label_offset_y.setValue(0.0)
        self.label_offset_y.valueChanged.connect(
            lambda v: self.project_property_changed.emit({"label_offset_y": v})
        )
        self.label_cell_layout.addRow(self._fl("lbl_offset_y"), self.label_offset_y)

        self.label_row_height = QDoubleSpinBox()
        self.label_row_height.setRange(0.0, 50.0)
        self.label_row_height.setSingleStep(0.5)
        self.label_row_height.setDecimals(1)
        self.label_row_height.setSuffix(" mm")
        self.label_row_height.setSpecialValueText(tr("special_auto"))
        self.label_row_height.setValue(0.0)
        self.label_row_height.valueChanged.connect(
            lambda v: self.project_property_changed.emit({"label_row_height": v})
        )
        self.label_cell_layout.addRow(self._fl("lbl_row_height"), self.label_row_height)

        self.layout.addWidget(self.label_cell_group)
        self.label_cell_group.hide()

        # --- Row Properties Group ---
        self.row_group = CollapsibleSection("Row Settings")
        self.row_layout = self.row_group._form
        
        self.row_height = QDoubleSpinBox()
        self.row_height.setRange(0.1, 10.0)
        self.row_height.setSingleStep(0.1)
        self.row_height.valueChanged.connect(
            lambda v: self.row_property_changed.emit({"height_ratio": v})
        )
        self.row_layout.addRow(self._fl("lbl_height_ratio"), self.row_height)
        
        # Column ratios (comma-separated, e.g. "1,2,1" for 25%-50%-25%)
        self.col_ratios_edit = QLineEdit()
        self.col_ratios_edit.setPlaceholderText(tr("placeholder_col_ratios"))
        self.col_ratios_edit.editingFinished.connect(self._emit_column_ratios)
        self.row_layout.addRow(self._fl("lbl_col_ratios"), self.col_ratios_edit)
        
        self.layout.addWidget(self.row_group)
        self.row_group.hide()
        
        # --- Sub-Cell Settings Group ---
        self.subcell_group = CollapsibleSection("Sub-Cell Settings")
        self.subcell_layout = self.subcell_group._form

        self._subcell_id = None        # Track which sub-cell is selected
        self._subcell_direction = None  # "horizontal" or "vertical"

        self.subcell_info_label = QLabel("")
        self.subcell_layout.addRow(self.subcell_info_label)

        self.subcell_ratio = QDoubleSpinBox()
        self.subcell_ratio.setRange(0.1, 20.0)
        self.subcell_ratio.setSingleStep(0.1)
        self.subcell_ratio.setDecimals(2)
        self.subcell_ratio.valueChanged.connect(self._emit_subcell_ratio)
        self.subcell_layout.addRow(self._fl("lbl_size_ratio"), self.subcell_ratio)

        self.subcell_fixed_size = QDoubleSpinBox()
        self.subcell_fixed_size.setRange(0.0, 2000.0)
        self.subcell_fixed_size.setSingleStep(1.0)
        self.subcell_fixed_size.setDecimals(2)
        self.subcell_fixed_size.setSuffix(" mm")
        self.subcell_fixed_size.setSpecialValueText(tr("special_auto_ratio"))
        self.subcell_fixed_size.valueChanged.connect(self._emit_subcell_fixed_size)
        self._subcell_fixed_size_label = QLabel(tr("lbl_fixed_width"))
        self.subcell_layout.addRow(self._subcell_fixed_size_label, self.subcell_fixed_size)

        self.layout.addWidget(self.subcell_group)
        self.subcell_group.hide()

        # --- PiP Properties Group ---
        self.pip_group = CollapsibleSection("Selected PiP")
        self.pip_layout = self.pip_group._form

        # Geometry controls (values are 0-100 %, model stores 0.0-1.0)
        self.pip_x = QDoubleSpinBox()
        self.pip_x.setRange(0.0, 100.0)
        self.pip_x.setDecimals(1)
        self.pip_x.setSingleStep(0.5)
        self.pip_x.setSuffix(" %")
        self.pip_x.valueChanged.connect(
            lambda v: self.pip_property_changed.emit({"x": v / 100.0})
        )
        self.pip_layout.addRow(self._fl("lbl_pip_x"), self.pip_x)

        self.pip_y = QDoubleSpinBox()
        self.pip_y.setRange(0.0, 100.0)
        self.pip_y.setDecimals(1)
        self.pip_y.setSingleStep(0.5)
        self.pip_y.setSuffix(" %")
        self.pip_y.valueChanged.connect(
            lambda v: self.pip_property_changed.emit({"y": v / 100.0})
        )
        self.pip_layout.addRow(self._fl("lbl_pip_y"), self.pip_y)

        self.pip_w = QDoubleSpinBox()
        self.pip_w.setRange(1.0, 100.0)
        self.pip_w.setDecimals(1)
        self.pip_w.setSingleStep(0.5)
        self.pip_w.setSuffix(" %")
        self.pip_w.valueChanged.connect(
            lambda v: self.pip_property_changed.emit({"w": v / 100.0})
        )
        self.pip_layout.addRow(self._fl("lbl_pip_w"), self.pip_w)

        self.pip_h = QDoubleSpinBox()
        self.pip_h.setRange(1.0, 100.0)
        self.pip_h.setDecimals(1)
        self.pip_h.setSingleStep(0.5)
        self.pip_h.setSuffix(" %")
        self.pip_h.valueChanged.connect(
            lambda v: self.pip_property_changed.emit({"h": v / 100.0})
        )
        self.pip_layout.addRow(self._fl("lbl_pip_h"), self.pip_h)

        self.pip_border_enabled = QCheckBox(tr("chk_border_enabled"))
        self.pip_border_enabled.toggled.connect(
            lambda b: self.pip_property_changed.emit({"border_enabled": b})
        )
        self.pip_layout.addRow(self.pip_border_enabled)

        self.pip_border_style = QComboBox()
        self.pip_border_style.addItems([tr("opt_border_solid"), tr("opt_border_dashed")])
        self.pip_border_style.currentTextChanged.connect(
            lambda t: self.pip_property_changed.emit({"border_style": t})
        )
        self.pip_layout.addRow(self._fl("lbl_border_style"), self.pip_border_style)

        self.pip_border_width = QDoubleSpinBox()
        self.pip_border_width.setRange(0.1, 10.0)
        self.pip_border_width.setSingleStep(0.1)
        self.pip_border_width.setDecimals(1)
        self.pip_border_width.setSuffix(" pt")
        self.pip_border_width.valueChanged.connect(
            lambda v: self.pip_property_changed.emit({"border_width_pt": v})
        )
        self.pip_layout.addRow(self._fl("lbl_thickness"), self.pip_border_width)

        self.pip_border_color = ColorPickerWidget()
        self.pip_border_color.colorChanged.connect(
            lambda c: self.pip_property_changed.emit({"border_color": c})
        )
        self.pip_layout.addRow(self._fl("lbl_color"), self.pip_border_color)

        self.pip_delete_btn = QPushButton(self._fl("btn_delete_pip"))
        self.pip_delete_btn.clicked.connect(self.pip_delete_requested)
        self.pip_layout.addRow(self.pip_delete_btn)

        self.layout.addWidget(self.pip_group)
        self.pip_group.hide()

        # --- Text Properties Group ---
        self.text_group = CollapsibleSection("Selected Text")
        self.text_layout = self.text_group._form
        
        self.text_content = QLineEdit()
        self.text_content.editingFinished.connect(
            lambda: self.text_property_changed.emit({"text": self.text_content.text()})
        )
        self.text_layout.addRow(self._fl("lbl_content"), self.text_content)
        
        self.font_family = QFontComboBox()
        self.font_family.setFontFilters(QFontComboBox.FontFilter.ScalableFonts)
        self.font_family.currentTextChanged.connect(
            lambda t: self.text_property_changed.emit({"font_family": t})
        )
        self.text_layout.addRow(self._fl("lbl_font"), self.font_family)
        
        self.font_size = QSpinBox()
        self.font_size.setRange(1, 72)
        self.font_size.valueChanged.connect(
            lambda v: self.text_property_changed.emit({"font_size_pt": v})
        )
        self.text_layout.addRow(self._fl("lbl_size_pt"), self.font_size)
        
        self.is_bold = QCheckBox("Bold")
        self.is_bold.toggled.connect(
            lambda b: self.text_property_changed.emit({"font_weight": "bold" if b else "normal"})
        )
        self.text_layout.addRow("", self.is_bold)
        
        # Color control for individual text item
        color_row = QHBoxLayout()
        self.text_color = ColorPickerWidget()
        self.text_color.colorChanged.connect(self._on_text_color_changed)
        color_row.addWidget(self.text_color)
        
        self.apply_color_btn = QPushButton("Apply to All")
        self.apply_color_btn.setToolTip("Apply this color to all labels in the same group")
        self.apply_color_btn.clicked.connect(self._on_apply_color_to_group)
        color_row.addWidget(self.apply_color_btn)
        
        color_widget = QWidget()
        color_widget.setLayout(color_row)
        self.text_layout.addRow(self._fl("lbl_color"), color_widget)
        
        # Store current text item subtype for apply-to-group
        self._current_text_subtype = None

        # ── Floating (global) text controls ─────────────────────────
        # Absolute canvas position in MM (independent of cells; robust to
        # page/DPI changes because scene coords are already in mm).
        self.text_pos_x = QDoubleSpinBox()
        self.text_pos_x.setRange(-10000.0, 10000.0)
        self.text_pos_x.setSingleStep(0.5)
        self.text_pos_x.setDecimals(2)
        self.text_pos_x.setSuffix(" mm")
        self.text_pos_x.valueChanged.connect(
            lambda v: self.text_property_changed.emit({"x": v})
        )
        self.text_layout.addRow(self._fl("lbl_pos_x"), self.text_pos_x)

        self.text_pos_y = QDoubleSpinBox()
        self.text_pos_y.setRange(-10000.0, 10000.0)
        self.text_pos_y.setSingleStep(0.5)
        self.text_pos_y.setDecimals(2)
        self.text_pos_y.setSuffix(" mm")
        self.text_pos_y.valueChanged.connect(
            lambda v: self.text_property_changed.emit({"y": v})
        )
        self.text_layout.addRow(self._fl("lbl_pos_y"), self.text_pos_y)

        self.text_rotation = QDoubleSpinBox()
        self.text_rotation.setRange(-360.0, 360.0)
        self.text_rotation.setSingleStep(15.0)  # convenient for 90° snaps
        self.text_rotation.setDecimals(1)
        self.text_rotation.setSuffix(" °")
        self.text_rotation.setWrapping(True)
        self.text_rotation.valueChanged.connect(
            lambda v: self.text_property_changed.emit({"rotation": float(v)})
        )
        self.text_layout.addRow(self._fl("lbl_rotation"), self.text_rotation)

        # Offset controls for cell-scoped labels
        self.offset_x = QDoubleSpinBox()
        self.offset_x.setRange(0, 100)
        self.offset_x.setSingleStep(0.5)
        self.offset_x.setSuffix(" mm")
        self.offset_x.valueChanged.connect(
            lambda v: self.text_property_changed.emit({"offset_x": v})
        )
        self.text_layout.addRow(self._fl("lbl_offset_x"), self.offset_x)
        
        self.offset_y = QDoubleSpinBox()
        self.offset_y.setRange(0, 100)
        self.offset_y.setSingleStep(0.5)
        self.offset_y.setSuffix(" mm")
        self.offset_y.valueChanged.connect(
            lambda v: self.text_property_changed.emit({"offset_y": v})
        )
        self.text_layout.addRow(self._fl("lbl_offset_y"), self.offset_y)

        # ── Background box (for dark-image label aesthetics) ────────────
        self.text_bg_enabled = QCheckBox("Background Box")
        self.text_bg_enabled.toggled.connect(
            lambda b: self.text_property_changed.emit({"bg_enabled": bool(b)})
        )
        self.text_layout.addRow("", self.text_bg_enabled)

        self.text_bg_color = ColorPickerWidget()
        self.text_bg_color.colorChanged.connect(
            lambda c: self.text_property_changed.emit({"bg_color": c or "#FFFFFF"})
        )
        self.text_layout.addRow(self._fl("lbl_bg_color"), self.text_bg_color)

        self.text_bg_padding = QDoubleSpinBox()
        self.text_bg_padding.setRange(0.0, 20.0)
        self.text_bg_padding.setSingleStep(0.2)
        self.text_bg_padding.setDecimals(2)
        self.text_bg_padding.setSuffix(" mm")
        self.text_bg_padding.valueChanged.connect(
            lambda v: self.text_property_changed.emit({"bg_padding_mm": float(v)})
        )
        self.text_layout.addRow(self._fl("lbl_bg_padding"), self.text_bg_padding)

        # Scheme selector — only shown for in-cell numbering labels (not corner labels)
        self._incell_scheme = QComboBox()
        self._incell_scheme.addItems(["(a)", "(A)", "a", "A"])
        self._incell_scheme.currentTextChanged.connect(
            lambda t: self.project_property_changed.emit({"label_scheme": t})
        )
        self._incell_scheme_label = self._fl("lbl_scheme")
        self.text_layout.addRow(self._incell_scheme_label, self._incell_scheme)

        self.layout.addWidget(self.text_group)
        self.text_group.hide()
        
        # --- No Selection ---
        self.no_selection_label = QLabel(tr("no_selection"))
        self.no_selection_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(self.no_selection_label)

        # --- Multi-selection info ---
        self.multi_label = QLabel("")
        self.multi_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.multi_label.hide()
        self.layout.addWidget(self.multi_label)

        # Make main groups collapsible
        self._make_collapsible(self.project_group)
        self._make_collapsible(self.cell_group)
        self._make_collapsible(self.row_group)

    def _fl(self, key: str) -> QLabel:
        """Create a form-row QLabel, register it for retranslation, and return it."""
        lbl = QLabel(tr(key))
        self._lbl_registry.append((key, lbl))
        return lbl

    def retranslate_ui(self):
        """Update all visible translatable strings to the current language."""
        self.project_group.set_title(tr("grp_project"))
        self.cell_group.set_title(tr("grp_cell"))
        self.label_cell_group.set_title(tr("grp_label_cell"))
        self.row_group.set_title(tr("grp_row"))
        self.subcell_group.set_title(tr("grp_subcell"))
        self.text_group.set_title(tr("grp_text"))
        self.pip_group.set_title(tr("grp_pip"))

        self._sec_grid.setText(tr("sec_grid"))
        self._sec_corner.setText(tr("sec_corner_labels"))
        self._sec_label_placement.setText(tr("sec_label_placement"))
        self._sec_layout.setText(tr("sec_layout"))
        self.freeform_section_label.setText(tr("sec_freeform"))
        self._sec_grid_override.setText(tr("sec_grid_override"))
        self._sec_padding.setText(tr("sec_padding"))
        self.scale_bar_group.set_title(tr("grp_scale_bar"))

        self.scale_bar_enabled.setText(tr("chk_scale_enabled"))
        self.scale_bar_show_text.setText(tr("chk_scale_text"))
        self._manage_btn.setText(tr("btn_manage"))
        self.pip_border_enabled.setText(tr("chk_border_enabled"))
        self.label_bold.setText(tr("chk_bold"))
        self.is_bold.setText(tr("chk_bold"))
        self._subcell_fixed_size_label.setText(tr("lbl_fixed_width"))

        for key, lbl in self._lbl_registry:
            lbl.setText(tr(key))

        self.no_selection_label.setText(tr("no_selection"))

        # Retranslate combo-box items (block signals so no spurious property changes)
        def _retranslate_combo(combo, items):
            idx = combo.currentIndex()
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(items)
            combo.setCurrentIndex(max(0, idx))
            combo.blockSignals(False)

        _retranslate_combo(self.grid_mode,         [tr("opt_grid_stretch"), tr("opt_grid_fixed")])
        _retranslate_combo(self.row_alignment,      [tr("opt_row_left"),     tr("opt_row_center"),    tr("opt_row_right")])
        _retranslate_combo(self.label_align,        [tr("opt_align_left"),   tr("opt_align_center"),  tr("opt_align_right")])
        _retranslate_combo(self.label_placement_combo, [tr(key) for key, _ in self._label_placement_options])
        _retranslate_combo(self.page_preset,        [tr(k) for k in self._page_preset_options])
        _retranslate_combo(self.pip_border_style,   [tr("opt_border_solid"), tr("opt_border_dashed")])
        
        self.scale_bar_custom_text.setPlaceholderText(tr("placeholder_scale_bar_text"))
        self.label_text_edit.setPlaceholderText(tr("placeholder_label_text"))
        self.label_row_height.setSpecialValueText(tr("special_auto"))
        self.col_ratios_edit.setPlaceholderText(tr("placeholder_col_ratios"))
        self.subcell_fixed_size.setSpecialValueText(tr("special_auto_ratio"))

        self.corner_label_color.retranslate_ui()
        self.scale_bar_color.retranslate_ui()
        self.label_color.retranslate_ui()
        self.text_color.retranslate_ui()

    def apply_theme(self, tokens: dict) -> None:
        """Update theme-sensitive icons (called by main window on theme change)."""
        from src.app.icons import make_icon
        color = tokens.get("text", "#333333")
        self._icon_theme_color = color
        self._icon_lock_closed = make_icon("lock_closed", color, 16)
        self._icon_lock_open   = make_icon("lock_open",   color, 16)
        locked = self.aspect_lock_btn.isChecked()
        self.aspect_lock_btn.setIcon(self._icon_lock_closed if locked else self._icon_lock_open)
        self.aspect_lock_btn.setIconSize(__import__('PyQt6.QtCore', fromlist=['QSize']).QSize(16, 16))

        # Refresh dynamic apply-button text if a text item is currently selected
        if self.text_group.isVisible():
            if self._current_text_subtype == "corner":
                self.apply_color_btn.setText(tr("btn_apply_all_corner"))
            else:
                self.apply_color_btn.setText(tr("btn_apply_all_numbering"))
        else:
            self.apply_color_btn.setText(tr("btn_apply_all"))

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

    def _on_grid_mode_changed(self, index: int):
        mode = "stretch" if index == 0 else "fixed"
        self.row_alignment.setEnabled(mode == "fixed")
        self.project_property_changed.emit({"grid_mode": mode})

    def _on_row_alignment_changed(self, index: int):
        values = ["left", "center", "right"]
        self.project_property_changed.emit({"row_alignment": values[index]})

    def _make_collapsible(self, section) -> None:
        pass  # CollapsibleSection handles this natively

    def _emit_padding(self):
        self.cell_property_changed.emit({
            "padding_top": self.pad_top.value(),
            "padding_bottom": self.pad_bottom.value(),
            "padding_left": self.pad_left.value(),
            "padding_right": self.pad_right.value()
        })

    def _set_freeform_visible(self, visible: bool):
        """Show or hide the Freeform Geometry section in the cell inspector."""
        self.freeform_section_label.setVisible(visible)
        for widget in (self.freeform_x, self.freeform_y, self.freeform_w, self.freeform_h):
            widget.setVisible(visible)
            label = self.cell_layout.labelForField(widget)
            if label:
                label.setVisible(visible)

    def _emit_freeform(self):
        self.cell_property_changed.emit({
            "freeform_x_mm": self.freeform_x.value(),
            "freeform_y_mm": self.freeform_y.value(),
            "freeform_w_mm": self.freeform_w.value(),
            "freeform_h_mm": self.freeform_h.value()
        })

    def _set_alignment_buttons(self, align_h: str, align_v: str):
        """Check the single alignment button matching (align_h, align_v); uncheck others.

        Temporarily disables exclusivity so we can toggle without emitting signals
        (Qt's blockSignals already blocks click emission, but exclusivity flips state).
        """
        btn = self._align_buttons.get((align_h, align_v))
        # Uncheck all (exclusive group requires disabling exclusivity first)
        self.align_button_group.setExclusive(False)
        for b in self._align_buttons.values():
            b.setChecked(False)
        if btn:
            btn.setChecked(True)
        self.align_button_group.setExclusive(True)

    def _emit_override_size(self):
        self.cell_property_changed.emit({
            "override_width_mm": self.override_w.value(),
            "override_height_mm": self.override_h.value(),
            "aspect_ratio_locked": self.aspect_lock_btn.isChecked(),
        })

    def _on_override_w_changed(self):
        if self.aspect_lock_btn.isChecked():
            ar = self._current_aspect_ratio()
            if ar and ar > 0 and self.override_w.value() > 0:
                self.override_h.blockSignals(True)
                self.override_h.setValue(round(self.override_w.value() / ar, 2))
                self.override_h.blockSignals(False)
        self._emit_override_size()

    def _on_override_h_changed(self):
        if self.aspect_lock_btn.isChecked():
            ar = self._current_aspect_ratio()
            if ar and ar > 0 and self.override_h.value() > 0:
                self.override_w.blockSignals(True)
                self.override_w.setValue(round(self.override_h.value() * ar, 2))
                self.override_w.blockSignals(False)
        self._emit_override_size()

    def _on_aspect_lock_toggled(self, locked: bool):
        icon = getattr(self, '_icon_lock_closed', None) if locked else getattr(self, '_icon_lock_open', None)
        if icon:
            self.aspect_lock_btn.setIcon(icon)
        if locked:
            burst_color = QColor(getattr(self, '_icon_theme_color', "#888888"))
            self.aspect_lock_btn.play_lock_burst(burst_color)
        if locked:
            # Snap height to match current width using image aspect ratio
            ar = self._current_aspect_ratio()
            if ar and ar > 0 and self.override_w.value() > 0:
                self.override_h.blockSignals(True)
                self.override_h.setValue(round(self.override_w.value() / ar, 2))
                self.override_h.blockSignals(False)
            elif ar and ar > 0 and self.override_h.value() > 0:
                self.override_w.blockSignals(True)
                self.override_w.setValue(round(self.override_h.value() * ar, 2))
                self.override_w.blockSignals(False)
        self._emit_override_size()

    def _current_aspect_ratio(self) -> Optional[float]:
        """Return w/h aspect ratio of the currently selected cell's image, or None."""
        ar = getattr(self, "_current_cell_aspect_ratio", None)
        return ar

    # --- Size Group handlers ---
    _SG_DATA_ROLE = Qt.ItemDataRole.UserRole

    def _populate_size_group_section(self, current_group_id: Optional[str], size_groups: list):
        """Populate the Size Group section from project state.

        size_groups: list of dicts {id, name, pinned_width_mm, pinned_height_mm, member_count}.
        """
        self._size_groups_cache = size_groups or []
        self._current_size_group_id = current_group_id

        # Rebuild combo (blocked to avoid re-emitting during setup)
        self.size_group_combo.blockSignals(True)
        self.size_group_combo.clear()
        # Index 0 = None
        self.size_group_combo.addItem(tr("size_group_none"), userData="")
        for g in self._size_groups_cache:
            self.size_group_combo.addItem(g.get("name", "Group"), userData=g.get("id"))
        # Last entry = create new
        self.size_group_combo.addItem(tr("size_group_new"), userData="__new__")

        # Select current
        idx = 0
        if current_group_id:
            for i in range(self.size_group_combo.count()):
                if self.size_group_combo.itemData(i) == current_group_id:
                    idx = i
                    break
        self.size_group_combo.setCurrentIndex(idx)
        self.size_group_combo.blockSignals(False)

        # Show/hide group-specific widgets
        in_group = bool(current_group_id)
        g_data = next((g for g in self._size_groups_cache if g.get("id") == current_group_id), None) if in_group else None

        for w in (self.size_group_name_edit,
                  self.size_group_pinned_w, self.size_group_pinned_h,
                  self.size_group_members_label, self.size_group_delete_btn):
            w.setVisible(in_group)
            lbl = self.cell_layout.labelForField(w) if w not in (self.size_group_members_label, self.size_group_delete_btn) else None
            if lbl:
                lbl.setVisible(in_group)

        if g_data:
            self.size_group_name_edit.blockSignals(True)
            self.size_group_name_edit.setText(g_data.get("name", "Group"))
            self.size_group_name_edit.blockSignals(False)
            self.size_group_pinned_w.blockSignals(True)
            self.size_group_pinned_h.blockSignals(True)
            self.size_group_pinned_w.setValue(g_data.get("pinned_width_mm", 0.0))
            self.size_group_pinned_h.setValue(g_data.get("pinned_height_mm", 0.0))
            self.size_group_pinned_w.blockSignals(False)
            self.size_group_pinned_h.blockSignals(False)
            n = g_data.get("member_count", 0)
            self.size_group_members_label.setText(tr("size_group_members").format(n=n))
            self.size_group_delete_btn.setText(tr("size_group_delete"))

    def _on_size_group_combo_changed(self, idx: int):
        if idx < 0:
            return
        data = self.size_group_combo.itemData(idx)
        if data == "__new__":
            # Create new group and assign current selection
            self.size_group_create_requested.emit()
            return
        # Assign via cell property change (empty -> ungroup)
        new_gid = data if data else None
        if new_gid == self._current_size_group_id:
            return
        self.cell_property_changed.emit({"size_group_id": new_gid})

    def _emit_size_group_pinned(self):
        if not self._current_size_group_id:
            return
        self.size_group_pinned_changed.emit(
            self._current_size_group_id,
            self.size_group_pinned_w.value(),
            self.size_group_pinned_h.value(),
        )

    def _emit_size_group_rename(self):
        if not self._current_size_group_id:
            return
        new_name = self.size_group_name_edit.text().strip()
        if not new_name:
            return
        self.size_group_rename_requested.emit(self._current_size_group_id, new_name)

    def _emit_size_group_delete(self):
        if not self._current_size_group_id:
            return
        self.size_group_delete_requested.emit(self._current_size_group_id)

    # µm per unit — multiply display value by this to get µm
    _UNIT_TO_UM = {
        "m":  1e6,
        "cm": 1e4,
        "dm": 1e5,
        "mm": 1e3,
        "µm": 1.0,
        "nm": 1e-3,
        "pm": 1e-6,
        "fm": 1e-9,
    }

    def _on_scale_bar_mode_changed(self, mode_name: str):
        from src.app.scale_bar_mappings import load_mappings
        mappings = load_mappings()
        for m in mappings:
            if m["name"] == mode_name:
                unit = m.get("unit", "µm")
                if self.scale_bar_unit.currentText() != unit:
                    self._skip_unit_conversion = True
                    self.scale_bar_unit.setCurrentText(unit)
                    self._skip_unit_conversion = False
                    return
                break
        self._emit_scale_bar()

    def _emit_scale_bar(self):
        """Emit all scale bar properties as a single cell property change."""
        from src.app.scale_bar_mappings import get_um_per_px
        color_hex = self.scale_bar_color.get_color()
        # Custom text: empty string means use auto-generated text
        custom_text = self.scale_bar_custom_text.text().strip()
        mapping_name = self.scale_bar_mode.currentText()
        # Convert displayed value from selected unit to µm
        unit = self.scale_bar_unit.currentText()
        factor = self._UNIT_TO_UM.get(unit, 1.0)
        length_um = self.scale_bar_length.value() * factor
        properties = {
            "scale_bar_enabled": self.scale_bar_enabled.isChecked(),
            "scale_bar_mode": mapping_name,
            "scale_bar_um_per_px": get_um_per_px(mapping_name),
            "scale_bar_length_um": length_um,
            "scale_bar_unit": unit,
            "scale_bar_color": color_hex,
            "scale_bar_show_text": self.scale_bar_show_text.isChecked(),
            "scale_bar_thickness_mm": self.scale_bar_thickness.value(),
            "scale_bar_position": self.scale_bar_position.currentText(),
            "scale_bar_offset_x": self.scale_bar_offset_x.value(),
            "scale_bar_offset_y": self.scale_bar_offset_y.value(),
            "scale_bar_custom_text": custom_text if custom_text else None,
            "scale_bar_text_size_mm": self.scale_bar_text_size.value(),
        }
        if getattr(self, "_current_item_type", None) == "pip":
            self.pip_property_changed.emit(properties)
        else:
            self.cell_property_changed.emit(properties)

    def _on_scale_bar_unit_changed(self, new_unit: str):
        """When the unit changes, recalculate the spinbox value so physical length stays constant."""
        old_unit = getattr(self, '_prev_scale_bar_unit', 'µm')
        self._prev_scale_bar_unit = new_unit
        if old_unit == new_unit:
            return

        if getattr(self, "_skip_unit_conversion", False):
            self._emit_scale_bar()
            return

        old_factor = self._UNIT_TO_UM.get(old_unit, 1.0)
        new_factor = self._UNIT_TO_UM.get(new_unit, 1.0)
        old_val = self.scale_bar_length.value()
        # Convert: old_val * old_factor µm / new_factor = new display value
        new_val = old_val * old_factor / new_factor
        self.scale_bar_length.blockSignals(True)
        self.scale_bar_length.setValue(new_val)
        self.scale_bar_length.blockSignals(False)
        self._emit_scale_bar()

    def _refresh_mapping_combo(self):
        """Reload the mapping combo from disk (called on init and after the dialog)."""
        current = self.scale_bar_mode.currentText()
        self.scale_bar_mode.blockSignals(True)
        self.scale_bar_mode.clear()
        self.scale_bar_mode.addItems(mapping_names())
        # Restore previously selected item if still present
        idx = self.scale_bar_mode.findText(current)
        if idx >= 0:
            self.scale_bar_mode.setCurrentIndex(idx)
        self.scale_bar_mode.blockSignals(False)

    def _open_mappings_dialog(self):
        """Open the scale bar mappings management dialog."""
        from src.app.scale_bar_mappings_dialog import ScaleBarMappingsDialog
        dlg = ScaleBarMappingsDialog(self)
        if dlg.exec():
            self._refresh_mapping_combo()
            self._emit_scale_bar()

    def _emit_subcell_ratio(self, value):
        if self._subcell_id:
            self.subcell_ratio_changed.emit(self._subcell_id, value)

    def _emit_subcell_fixed_size(self, value):
        if self._subcell_id and self._subcell_direction:
            key = "override_height_mm" if self._subcell_direction == "vertical" else "override_width_mm"
            self.cell_property_changed.emit({key: value})

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
        _preset_sizes = {
            "opt_page_a4":             (210, 297),
            "opt_page_letter":         (216, 279),
            "opt_page_single":         (85,  120),
            "opt_page_1_5":            (114, 160),
            "opt_page_double":         (178, 240),
            "opt_page_nature_single":  (89,  247),
            "opt_page_nature_double":  (183, 247),
            "opt_page_cell_single":    (85,  228),
            "opt_page_cell_double":    (174, 228),
            "opt_page_science_single": (90,  245),
            "opt_page_science_double": (180, 245),
            "opt_page_pnas_single":    (87,  246),
            "opt_page_pnas_double":    (178, 246),
        }
        idx = self.page_preset.currentIndex()
        if idx < 0 or idx >= len(self._page_preset_options):
            return
        key = self._page_preset_options[idx]
        if key not in _preset_sizes:
            return
        w, h = _preset_sizes[key]
        self.blockSignals(True)
        self.page_w.setValue(w)
        self.page_h.setValue(h)
        self.blockSignals(False)
        self.project_property_changed.emit({"page_width_mm": w, "page_height_mm": h})

    def _on_label_color_changed(self, color_hex: str = None):
        self.project_property_changed.emit({"label_color": color_hex or self.label_color.get_color()})

    def _on_corner_label_color_changed(self, color_hex: str = None):
        self.project_property_changed.emit({"corner_label_color": color_hex or self.corner_label_color.get_color()})

    def _on_label_align_preset_changed(self, index: int = None):
        align = ["left", "center", "right"][self.label_align.currentIndex()]
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

    def _on_text_color_changed(self, color_hex: str = None):
        """Handle individual text item color change."""
        self.text_property_changed.emit({"color": color_hex or self.text_color.get_color()})

    def _on_apply_color_to_group(self):
        """Apply current color to all labels in the same group (numbering or corner)."""
        self.apply_color_to_group.emit(self._current_text_subtype or "numbering", self.text_color.get_color())

    def _on_label_text_edited(self):
        """Handle label text edit in the Label Cell Settings panel."""
        if self._current_label_text_id:
            self.label_text_changed.emit(self._current_label_text_id, self.label_text_edit.text())

    def set_selection(self, item_type, data=None, row_data=None, project_data=None):
        """
        item_type: 'cell' | 'label_cell' | 'text' | 'pip' | 'multi_cell' | None
        """
        self._current_item_type = item_type
        self.multi_label.hide()

        if item_type == 'multi_cell':
            self.no_selection_label.hide()
            self.project_group.hide()
            self.text_group.hide()
            self.label_cell_group.hide()
            self.row_group.hide()
            self.subcell_group.hide()
            self.pip_group.hide()
            self.scale_bar_group.hide()
            if data:
                self.blockSignals(True)
                self.fit_mode_combo.setCurrentText(data.get("fit_mode", "contain"))
                self.rotation_combo.setCurrentText(str(data.get("rotation", 0)))
                self.pad_top.setValue(data.get("padding_top", 0))
                self.pad_bottom.setValue(data.get("padding_bottom", 0))
                self.pad_left.setValue(data.get("padding_left", 0))
                self.pad_right.setValue(data.get("padding_right", 0))
                self.freeform_x.setValue(data.get("freeform_x_mm", 0.0))
                self.freeform_y.setValue(data.get("freeform_y_mm", 0.0))
                self.freeform_w.setValue(data.get("freeform_w_mm", 50.0))
                self.freeform_h.setValue(data.get("freeform_h_mm", 50.0))
                self.override_w.setValue(data.get("override_width_mm", 0.0))
                self.override_h.setValue(data.get("override_height_mm", 0.0))
                # Size group: show current only if all selected share one; still allow assignment
                self._populate_size_group_section(
                    data.get("size_group_id"),
                    data.get("_size_groups", []),
                )
                self.blockSignals(False)
            return

        if item_type == 'label_cell':
            self.no_selection_label.hide()
            self.project_group.hide()
            self.cell_group.hide()
            self.pip_group.hide()
            self.row_group.hide()
            self.text_group.hide()
            self.subcell_group.hide()
            self.scale_bar_group.hide()
            self.label_cell_group.show()

            if data:
                self.blockSignals(True)
                self._current_label_text_id = data.get("text_item_id")
                self.label_text_edit.setText(data.get("label_text", ""))
                self.label_scheme.setCurrentText(data.get("label_scheme", "(a)"))
                self.label_font.setCurrentText(data.get("label_font_family", "Arial"))
                self.label_size.setValue(data.get("label_font_size", 12))
                self.label_bold.setChecked(data.get("label_font_weight", "bold") == "bold")
                label_color_hex = data.get("label_color", "#000000")
                self.label_color.set_color(label_color_hex)
                label_align = data.get("label_align", "center")
                align_map = {"left": 0, "center": 1, "right": 2}
                self.label_align.setCurrentIndex(align_map.get(label_align, 1))
                self.label_offset_x.setValue(data.get("label_offset_x", 0.0))
                self.label_offset_y.setValue(data.get("label_offset_y", 0.0))
                self.label_row_height.setValue(data.get("label_row_height", 0.0))
                self.blockSignals(False)
            return

        if item_type == 'cell':
            self.no_selection_label.hide()
            self.project_group.hide()
            self.text_group.hide()
            self.pip_group.hide()
            self.label_cell_group.hide()
            self.cell_group.show()
            self._set_freeform_visible(data.get("layout_mode") == "freeform" if data else False)

            # Show row group
            if row_data:
                self.row_group.show()
                self.blockSignals(True)
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

            # Show sub-cell settings if this cell is inside a split parent
            subcell_data = data.get("_subcell") if data else None
            if subcell_data:
                self.subcell_group.show()
                self.blockSignals(True)
                self._subcell_id = subcell_data.get("cell_id")
                direction = subcell_data.get("direction", "")
                self._subcell_direction = direction
                sibling_count = subcell_data.get("sibling_count", 0)
                sibling_index = subcell_data.get("sibling_index", 0)
                dim = "Height" if direction == "vertical" else "Width"
                self.subcell_info_label.setText(
                    f"Split: {direction}  |  {sibling_index + 1} of {sibling_count}")
                self.subcell_ratio.setValue(subcell_data.get("ratio", 1.0))
                # Update labels to reflect H vs V dimension
                ratio_label = self.subcell_layout.labelForField(self.subcell_ratio)
                if ratio_label:
                    ratio_label.setText(f"{dim} Ratio:")
                self._subcell_fixed_size_label.setText(f"Fixed {dim}:")
                fixed_key = "override_height_mm" if direction == "vertical" else "override_width_mm"
                self.subcell_fixed_size.setValue(subcell_data.get(fixed_key, 0.0))
                self.blockSignals(False)
            else:
                self.subcell_group.hide()
                self._subcell_id = None
                self._subcell_direction = None
            
            # Block signals to prevent feedback loop
            self.blockSignals(True)
            self.fit_mode_combo.setCurrentText(data.get("fit_mode", "contain"))
            self.rotation_combo.setCurrentText(str(data.get("rotation", 0)))
            self._set_alignment_buttons(
                data.get("align_h", "center"),
                data.get("align_v", "center"),
            )
            self.pad_top.setValue(data.get("padding_top", 0))
            self.pad_bottom.setValue(data.get("padding_bottom", 0))
            self.pad_left.setValue(data.get("padding_left", 0))
            self.pad_right.setValue(data.get("padding_right", 0))
            self.freeform_x.setValue(data.get("freeform_x_mm", 0.0))
            self.freeform_y.setValue(data.get("freeform_y_mm", 0.0))
            self.freeform_w.setValue(data.get("freeform_w_mm", 50.0))
            self.freeform_h.setValue(data.get("freeform_h_mm", 50.0))
            self.override_w.setValue(data.get("override_width_mm", 0.0))
            self.override_h.setValue(data.get("override_height_mm", 0.0))
            locked = data.get("aspect_ratio_locked", False)
            self.aspect_lock_btn.setChecked(locked)
            icon = getattr(self, '_icon_lock_closed', None) if locked else getattr(self, '_icon_lock_open', None)
            if icon:
                self.aspect_lock_btn.setIcon(icon)
            self._current_cell_aspect_ratio = data.get("_image_aspect_ratio")
            # Size group section
            self._populate_size_group_section(
                data.get("size_group_id"),
                data.get("_size_groups", []),
            )

            corner_labels = data.get("corner_labels", {}) if data else {}
            self.corner_label_tl.setText(corner_labels.get("top_left_inside", ""))
            self.corner_label_tr.setText(corner_labels.get("top_right_inside", ""))
            self.corner_label_bl.setText(corner_labels.get("bottom_left_inside", ""))
            self.corner_label_br.setText(corner_labels.get("bottom_right_inside", ""))

            self.scale_bar_offset_y.setValue(data.get("scale_bar_offset_y", 2.0))
            
            # Populate shared scale bar section
            self._populate_scale_bar_section(data)
            
            self.blockSignals(False)
            
        elif item_type == 'text':
            self.no_selection_label.hide()
            self.project_group.hide()
            self.cell_group.hide()
            self.pip_group.hide()
            self.row_group.hide()
            self.label_cell_group.hide()
            self.subcell_group.hide()
            self.scale_bar_group.hide()
            self.text_group.show()
            
            self.blockSignals(True)
            self.text_content.setText(data.get("text", ""))
            self.font_family.setCurrentText(data.get("font_family", "Arial"))
            self.font_size.setValue(data.get("font_size_pt", 12))
            self.is_bold.setChecked(data.get("font_weight") == "bold")
            
            # Set text color
            color_hex = data.get("color", "#000000")
            self.text_color.set_color(color_hex)
            
            # Store subtype for apply-to-group functionality
            self._current_text_subtype = data.get("subtype")
            
            # Show/hide scheme combo
            if self._current_text_subtype != "corner":
                self._incell_scheme_label.show()
                self._incell_scheme.show()
                self._incell_scheme.setCurrentText(data.get("label_scheme", "(a)"))
            else:
                self._incell_scheme_label.hide()
                self._incell_scheme.hide()
            
            # Update apply button text based on subtype
            if self._current_text_subtype == "corner":
                self.apply_color_btn.setText(tr("btn_apply_all_corner"))
            else:
                self.apply_color_btn.setText(tr("btn_apply_all_numbering"))
            
            # Show offset controls only for cell-scoped labels;
            # show floating-text controls only for global-scoped items.
            is_cell_scoped = data.get("scope") == "cell"
            is_global = not is_cell_scoped

            for w in (self.offset_x, self.offset_y):
                w.setVisible(is_cell_scoped)
                lbl = self.text_layout.labelForField(w)
                if lbl is not None:
                    lbl.setVisible(is_cell_scoped)

            for w in (self.text_pos_x, self.text_pos_y, self.text_rotation):
                w.setVisible(is_global)
                lbl = self.text_layout.labelForField(w)
                if lbl is not None:
                    lbl.setVisible(is_global)

            if is_cell_scoped:
                self.offset_x.setValue(data.get("offset_x", 2.0))
                self.offset_y.setValue(data.get("offset_y", 2.0))
            else:
                self.text_pos_x.setValue(float(data.get("x", 0.0)))
                self.text_pos_y.setValue(float(data.get("y", 0.0)))
                self.text_rotation.setValue(float(data.get("rotation", 0.0)))

            # Background-box fields
            self.text_bg_enabled.setChecked(bool(data.get("bg_enabled", False)))
            self.text_bg_color.set_color(data.get("bg_color", "#FFFFFF"))
            self.text_bg_padding.setValue(float(data.get("bg_padding_mm", 0.6)))

            self.blockSignals(False)
            
        elif item_type == 'pip':
            self.no_selection_label.hide()
            self.project_group.hide()
            self.cell_group.hide()
            self.row_group.hide()
            self.subcell_group.hide()
            self.text_group.hide()
            self.label_cell_group.hide()
            self.pip_group.show()

            self.blockSignals(True)
            self.pip_x.setValue(float(data.get("x", 0.0)) * 100.0)
            self.pip_y.setValue(float(data.get("y", 0.0)) * 100.0)
            self.pip_w.setValue(float(data.get("w", 0.25)) * 100.0)
            self.pip_h.setValue(float(data.get("h", 0.25)) * 100.0)
            self.pip_border_enabled.setChecked(data.get("border_enabled", True))
            self.pip_border_style.setCurrentText(data.get("border_style", "solid"))
            self.pip_border_width.setValue(float(data.get("border_width_pt", 1.5)))
            self.pip_border_color.set_color(data.get("border_color", "#FFFFFF"))
            
            self.scale_bar_offset_y.setValue(data.get("scale_bar_offset_y", 2.0))
            
            # Populate shared scale bar section
            self._populate_scale_bar_section(data)
            
            self.blockSignals(False)

        else:
            self.cell_group.hide()
            self.row_group.hide()
            self.subcell_group.hide()
            self.text_group.hide()
            self.label_cell_group.hide()
            self.pip_group.hide()
            self.scale_bar_group.hide()
            self.no_selection_label.hide() # We show project settings instead
            
            # When item_type is None, 'data' might actually be project_data (legacy call)
            effective_project_data = project_data if project_data else data
            if effective_project_data:
                self.project_group.show()
                self.blockSignals(True)
                self.dpi_spin.setValue(effective_project_data.get("dpi", 600))
                self.page_w.setValue(effective_project_data.get("page_width_mm", 210))
                self.page_h.setValue(effective_project_data.get("page_height_mm", 297))
                self.m_top.setValue(effective_project_data.get("margin_top_mm", 0))
                self.m_bottom.setValue(effective_project_data.get("margin_bottom_mm", 0))
                self.m_left.setValue(effective_project_data.get("margin_left_mm", 0))
                self.m_right.setValue(effective_project_data.get("margin_right_mm", 0))
                
                # Grid Settings
                grid_mode = effective_project_data.get("grid_mode", "stretch")
                self.grid_mode.setCurrentIndex(1 if grid_mode == "fixed" else 0)
                self.row_alignment.setEnabled(grid_mode == "fixed")
                row_align_map = {"left": 0, "center": 1, "right": 2}
                self.row_alignment.setCurrentIndex(row_align_map.get(effective_project_data.get("row_alignment", "center"), 1))

                # Corner Labels
                self.corner_label_font.setCurrentText(effective_project_data.get("corner_label_font_family", "Arial"))
                self.corner_label_size.setValue(effective_project_data.get("corner_label_font_size", 12))
                corner_label_color_hex = effective_project_data.get("corner_label_color", "#000000")
                self.corner_label_color.set_color(corner_label_color_hex)

                self.gap_spin.setValue(effective_project_data.get("gap_mm", 2.0))

                # Label placement
                placement_val = effective_project_data.get("label_placement", "in_cell")
                idx_found = 0
                for i, (_t, val) in enumerate(self._label_placement_options):
                    if val == placement_val:
                        idx_found = i
                        break
                self.label_placement_combo.setCurrentIndex(idx_found)
                self.label_col_width_spin.setValue(
                    float(effective_project_data.get("label_col_width", 10.0))
                )

                self.blockSignals(False)
            else:
                self.project_group.hide()
                self.no_selection_label.show()
    def _populate_scale_bar_section(self, data: dict):
        """Populate the collapsible scale bar group with data from a Cell or PiPItem."""
        if not data:
            self.scale_bar_group.hide()
            return
            
        self.scale_bar_enabled.setChecked(data.get("scale_bar_enabled", False))
        self._refresh_mapping_combo()
        mapping_name = data.get("scale_bar_mode", "rgb")
        idx = self.scale_bar_mode.findText(mapping_name)
        self.scale_bar_mode.setCurrentIndex(idx if idx >= 0 else 0)
        
        unit = data.get("scale_bar_unit", "µm")
        self._prev_scale_bar_unit = unit
        self.scale_bar_unit.setCurrentText(unit)
        
        length_um = data.get("scale_bar_length_um", 10.0)
        factor = self._UNIT_TO_UM.get(unit, 1.0)
        self.scale_bar_length.setValue(length_um / factor)
        
        sb_color = data.get("scale_bar_color", "#FFFFFF")
        self.scale_bar_color.set_color(sb_color)
        self.scale_bar_show_text.setChecked(data.get("scale_bar_show_text", True))
        self.scale_bar_custom_text.setText(data.get("scale_bar_custom_text", "") or "")
        self.scale_bar_text_size.setValue(data.get("scale_bar_text_size_mm", 2.0))
        self.scale_bar_thickness.setValue(data.get("scale_bar_thickness_mm", 0.5))
        self.scale_bar_position.setCurrentText(data.get("scale_bar_position", "bottom_right"))
        self.scale_bar_offset_x.setValue(data.get("scale_bar_offset_x", 2.0))
        self.scale_bar_offset_y.setValue(data.get("scale_bar_offset_y", 2.0))
        
        self.scale_bar_group.show()
