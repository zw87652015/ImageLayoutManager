"""
PyQt6 GUI for Violin Plot Generator
Simple desktop interface for generating Nature Communications-compliant violin plots.
"""
import sys
from pathlib import Path

import pandas as pd
import numpy as np
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QLineEdit, QFileDialog,
    QGroupBox, QCheckBox, QSpinBox, QDoubleSpinBox, QMessageBox,
    QTextEdit, QSplitter, QScrollArea, QListWidget, QSizePolicy,
    QRadioButton, QButtonGroup,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QColor, QPainter

import matplotlib
matplotlib.use('QtAgg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from violin_plot_generator import NatureViolinPlot
from ncplot_project import ProjectMixin


class SwatchLabel(QLabel):
    """A small colored rectangle to show the theme palette."""
    def __init__(self, theme_name):
        super().__init__()
        self.setFixedSize(120, 16)
        self.theme_name = theme_name
        from violin_plot_generator import THEMES
        self.colors = THEMES[theme_name]

    def paintEvent(self, event):
        painter = QPainter(self)
        w = self.width() / len(self.colors)
        for i, c in enumerate(self.colors):
            painter.fillRect(int(i * w), 0, int(w) + 1, self.height(), QColor(c))


class ViolinPlotGUI(ProjectMixin, QMainWindow):
    """Main window for violin plot generator."""

    PLOTTER_TYPE = "violin_plot"

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Violin Plot Generator — Nature Communications Style")
        self.setMinimumSize(1000, 650)

        self.generator = NatureViolinPlot()
        self.df = None
        self.current_figure = None
        self._project_path = None
        self._csv_path = None
        self._auto_preview_timer = QTimer(self)
        self._auto_preview_timer.setSingleShot(True)
        self._auto_preview_timer.setInterval(250)
        self._auto_preview_timer.timeout.connect(self._generate_preview)

        self._build_ui()
        self._build_project_menu(self.menuBar())

    def _build_ui(self):
        """Build the user interface."""
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)

        # Left panel: Controls
        left_panel = self._build_left_panel()
        left_scroll = QScrollArea()
        left_scroll.setWidget(left_panel)
        left_scroll.setWidgetResizable(True)
        left_scroll.setMinimumWidth(320)
        left_scroll.setMaximumWidth(400)

        # Right panel: Preview
        right_panel = self._build_right_panel()

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left_scroll)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 5)

        main_layout.addWidget(splitter)

    def _build_left_panel(self):
        """Build the left control panel."""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setSpacing(8)

        # --- File Input ---
        file_group = QGroupBox("1. Load CSV File")
        file_layout = QVBoxLayout(file_group)

        file_row = QHBoxLayout()
        self.file_label = QLabel("No file selected")
        self.file_label.setWordWrap(True)
        self.file_label.setStyleSheet("color: #666; font-style: italic;")
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_file)
        file_row.addWidget(self.file_label, 1)
        file_row.addWidget(browse_btn)
        file_layout.addLayout(file_row)

        # CSV options
        csv_opts = QHBoxLayout()
        csv_opts.addWidget(QLabel("Delimiter:"))
        self.delimiter_combo = QComboBox()
        self.delimiter_combo.addItems(["Comma (,)", "Semicolon (;)", "Tab", "Space"])
        csv_opts.addWidget(self.delimiter_combo)
        csv_opts.addWidget(QLabel("Skip rows:"))
        self.skiprows_spin = QSpinBox()
        self.skiprows_spin.setRange(0, 100)
        csv_opts.addWidget(self.skiprows_spin)
        file_layout.addLayout(csv_opts)

        layout.addWidget(file_group)

        # --- Column Selection ---
        col_group = QGroupBox("2. Select Data Columns")
        col_layout = QVBoxLayout(col_group)
        
        info_label = QLabel("Select one or more columns to plot as separate violins:")
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #666; font-size: 11px;")
        col_layout.addWidget(info_label)

        self.columns_list = QListWidget()
        self.columns_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        self.columns_list.setMinimumHeight(120)
        self.columns_list.setToolTip("Hold Ctrl (or Cmd) to select multiple columns")
        col_layout.addWidget(self.columns_list)

        btn_row = QHBoxLayout()
        select_all_btn = QPushButton("Select All")
        select_all_btn.clicked.connect(self.columns_list.selectAll)
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self.columns_list.clearSelection)
        btn_row.addWidget(select_all_btn)
        btn_row.addWidget(clear_btn)
        col_layout.addLayout(btn_row)

        layout.addWidget(col_group)

        # --- Color Theme ---
        theme_group = QGroupBox("Color Theme")
        theme_layout = QVBoxLayout(theme_group)
        self.theme_btn_group = QButtonGroup(self)
        
        # Wong
        wong_row = QHBoxLayout()
        self.theme_wong_rb = QRadioButton("Default (Wong)")
        self.theme_wong_rb.setChecked(True)
        self.theme_wong_rb.setProperty("theme", "wong")
        self.theme_btn_group.addButton(self.theme_wong_rb)
        wong_row.addWidget(self.theme_wong_rb)
        wong_row.addStretch()
        wong_row.addWidget(SwatchLabel('wong'))
        theme_layout.addLayout(wong_row)
        
        # Blue-Pink
        bp_row = QHBoxLayout()
        self.theme_bp_rb = QRadioButton("Blue-Pink")
        self.theme_bp_rb.setProperty("theme", "blue-pink")
        self.theme_btn_group.addButton(self.theme_bp_rb)
        bp_row.addWidget(self.theme_bp_rb)
        bp_row.addStretch()
        bp_row.addWidget(SwatchLabel('blue-pink'))
        theme_layout.addLayout(bp_row)
        
        # Blue-Red
        br_row = QHBoxLayout()
        self.theme_br_rb = QRadioButton("Blue-Red")
        self.theme_br_rb.setProperty("theme", "blue-red")
        self.theme_btn_group.addButton(self.theme_br_rb)
        br_row.addWidget(self.theme_br_rb)
        br_row.addStretch()
        br_row.addWidget(SwatchLabel('blue-red'))
        theme_layout.addLayout(br_row)
        
        # Blue-Red (Preserve Ends)
        brpe_row = QHBoxLayout()
        self.theme_brpe_rb = QRadioButton("Blue-Red (Preserve Ends)")
        self.theme_brpe_rb.setProperty("theme", "blue-red-preserve-ends")
        self.theme_btn_group.addButton(self.theme_brpe_rb)
        brpe_row.addWidget(self.theme_brpe_rb)
        brpe_row.addStretch()
        brpe_row.addWidget(SwatchLabel('blue-red-preserve-ends'))
        theme_layout.addLayout(brpe_row)
        
        # Purple-Brown
        pb_row = QHBoxLayout()
        self.theme_pb_rb = QRadioButton("Purple-Brown")
        self.theme_pb_rb.setProperty("theme", "purple-brown")
        self.theme_btn_group.addButton(self.theme_pb_rb)
        pb_row.addWidget(self.theme_pb_rb)
        pb_row.addStretch()
        pb_row.addWidget(SwatchLabel('purple-brown'))
        theme_layout.addLayout(pb_row)
        
        layout.addWidget(theme_group)

        # --- Plot Options ---
        opts_group = QGroupBox("Display Options")
        opts_layout = QVBoxLayout(opts_group)

        fs_row = QHBoxLayout()
        fs_row.addWidget(QLabel("Canvas W×H (in):"))
        self.fw_spin = QDoubleSpinBox()
        self.fw_spin.setRange(1.0, 20.0)
        self.fw_spin.setValue(2.76)
        self.fw_spin.setSingleStep(0.5)
        self.fh_spin = QDoubleSpinBox()
        self.fh_spin.setRange(1.0, 20.0)
        self.fh_spin.setValue(2.76)
        self.fh_spin.setSingleStep(0.5)
        fs_row.addWidget(self.fw_spin)
        fs_row.addWidget(QLabel("×"))
        fs_row.addWidget(self.fh_spin)
        opts_layout.addLayout(fs_row)

        self.points_cb = QCheckBox("Show data points (scatter)")
        self.points_cb.setChecked(True)
        opts_layout.addWidget(self.points_cb)

        self.points_beside_cb = QCheckBox("Draw data dots beside violin")
        self.points_beside_cb.setChecked(False)
        opts_layout.addWidget(self.points_beside_cb)

        self.contrast_cb = QCheckBox("Enhance contrast for bright colors")
        self.contrast_cb.setChecked(True)
        self.contrast_cb.setToolTip("Adds a dark outline and makes pale colors more opaque for visibility on white background.")
        opts_layout.addWidget(self.contrast_cb)

        self.show_box_cb = QCheckBox("Show inner median/IQR box")
        self.show_box_cb.setChecked(True)
        opts_layout.addWidget(self.show_box_cb)

        self.show_stats_cb = QCheckBox("Show n and statistics")
        self.show_stats_cb.setChecked(True)
        opts_layout.addWidget(self.show_stats_cb)

        self.horizontal_cb = QCheckBox("Horizontal orientation")
        self.horizontal_cb.setChecked(False)
        opts_layout.addWidget(self.horizontal_cb)

        layout.addWidget(opts_group)

        # --- Labels ---
        label_group = QGroupBox("Axis Labels & Title")
        label_layout = QVBoxLayout(label_group)
        
        for attr, lbl, ph in [
            ('xlabel_edit', 'X-axis:', '(auto)'),
            ('ylabel_edit', 'Y-axis:', '(auto)'),
            ('title_edit',  'Title:',  '(none)'),
        ]:
            row = QHBoxLayout()
            row.addWidget(QLabel(lbl))
            w = QLineEdit()
            w.setPlaceholderText(ph)
            setattr(self, attr, w)
            row.addWidget(w)
            label_layout.addLayout(row)
            
        note_row = QHBoxLayout()
        note_row.addWidget(QLabel("Top Right Note:"))
        self.note_edit = QLineEdit()
        self.note_edit.setPlaceholderText("e.g. $N=10$, or use \\n for break")
        note_row.addWidget(self.note_edit)
        label_layout.addLayout(note_row)
        
        nfs_row = QHBoxLayout()
        nfs_row.addWidget(QLabel("Note Font Size:"))
        self.note_fs_spin = QDoubleSpinBox()
        self.note_fs_spin.setRange(4.0, 20.0)
        self.note_fs_spin.setValue(6.5)
        self.note_fs_spin.setSingleStep(0.5)
        nfs_row.addWidget(self.note_fs_spin)
        label_layout.addLayout(nfs_row)

        xfs_row = QHBoxLayout()
        xfs_row.addWidget(QLabel("X Label Font Size:"))
        self.xlabel_fs_spin = QDoubleSpinBox()
        self.xlabel_fs_spin.setRange(4.0, 24.0)
        self.xlabel_fs_spin.setValue(7.0)
        self.xlabel_fs_spin.setSingleStep(0.5)
        xfs_row.addWidget(self.xlabel_fs_spin)
        label_layout.addLayout(xfs_row)

        yfs_row = QHBoxLayout()
        yfs_row.addWidget(QLabel("Y Label Font Size:"))
        self.ylabel_fs_spin = QDoubleSpinBox()
        self.ylabel_fs_spin.setRange(4.0, 24.0)
        self.ylabel_fs_spin.setValue(7.0)
        self.ylabel_fs_spin.setSingleStep(0.5)
        yfs_row.addWidget(self.ylabel_fs_spin)
        label_layout.addLayout(yfs_row)

        tfs_row = QHBoxLayout()
        tfs_row.addWidget(QLabel("Title Font Size:"))
        self.title_fs_spin = QDoubleSpinBox()
        self.title_fs_spin.setRange(4.0, 24.0)
        self.title_fs_spin.setValue(7.0)
        self.title_fs_spin.setSingleStep(0.5)
        tfs_row.addWidget(self.title_fs_spin)
        label_layout.addLayout(tfs_row)

        layout.addWidget(label_group)

        # --- Significance Brackets ---
        sig_group = QGroupBox("Significance Brackets (Optional)")
        sig_layout = QVBoxLayout(sig_group)
        
        sig_info = QLabel("Add asterisk brackets between groups. One per line:")
        sig_info.setWordWrap(True)
        sig_info.setStyleSheet("color: #666; font-size: 11px;")
        sig_layout.addWidget(sig_info)
        
        self.sig_text = QTextEdit()
        self.sig_text.setMaximumHeight(80)
        self.sig_text.setPlaceholderText("0,1,*,0.05\n0,2,**,0.12")
        self.sig_text.setToolTip("Format: group1_idx,group2_idx,text,y_offset\nExample: 0,1,*,0.05 draws * between groups 0 and 1")
        self.sig_text.setFont(QFont("Courier New", 9))
        sig_layout.addWidget(self.sig_text)
        
        sig_hint = QLabel("Format: group1,group2,text,y_offset (e.g., 0,1,*,0.05)")
        sig_hint.setStyleSheet("color: #888; font-size: 10px; font-style: italic;")
        sig_layout.addWidget(sig_hint)
        
        layout.addWidget(sig_group)

        # --- Actions ---
        action_group = QGroupBox("Actions")
        action_layout = QVBoxLayout(action_group)

        export_btn = QPushButton("💾 Export Figure...")
        export_btn.clicked.connect(self._export_figure)
        action_layout.addWidget(export_btn)

        layout.addWidget(action_group)

        # --- Statistics Output ---
        stats_group = QGroupBox("Statistics Summary")
        stats_layout = QVBoxLayout(stats_group)
        self.stats_text = QTextEdit()
        self.stats_text.setReadOnly(True)
        self.stats_text.setMaximumHeight(150)
        self.stats_text.setFont(QFont("Courier New", 8))
        stats_layout.addWidget(self.stats_text)
        layout.addWidget(stats_group)

        layout.addStretch()
        self._setup_auto_preview()
        return panel

    def _build_right_panel(self):
        """Build the right preview panel."""
        panel = QWidget()
        layout = QVBoxLayout(panel)

        title = QLabel("Plot Preview")
        title.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        preview_btn = QPushButton("🔄 Generate Preview")
        preview_btn.setStyleSheet("font-weight: bold; padding: 8px;")
        preview_btn.clicked.connect(lambda: self._generate_preview(silent=False))
        layout.addWidget(preview_btn)

        # Matplotlib canvas with fixed size policy
        self.canvas = FigureCanvasQTAgg(Figure(figsize=(6, 5)))
        self.canvas.figure.patch.set_facecolor('#f5f5f5')
        # Prevent canvas from resizing - keep plot at fixed size
        from PyQt6.QtWidgets import QSizePolicy
        self.canvas.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.canvas.setMinimumSize(600, 500)
        self.canvas.setMaximumSize(600, 500)
        
        # Center the canvas in a container
        canvas_container = QWidget()
        canvas_layout = QHBoxLayout(canvas_container)
        canvas_layout.addStretch()
        canvas_layout.addWidget(self.canvas)
        canvas_layout.addStretch()
        layout.addWidget(canvas_container)

        hint = QLabel("Load a CSV file and click 'Generate Preview' to see your violin plot.")
        hint.setWordWrap(True)
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet("color: #888; font-style: italic; padding: 10px;")
        layout.addWidget(hint)

        return panel

    # ------------------------------------------------------------------
    # File handling
    # ------------------------------------------------------------------

    def _browse_file(self):
        """Open file dialog to select CSV."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Select CSV File", "",
            "CSV Files (*.csv *.tsv *.txt);;All Files (*)"
        )
        if not path:
            return

        try:
            delim = self._get_delimiter()
            skiprows = self.skiprows_spin.value()
            self.df = pd.read_csv(path, sep=delim, skiprows=skiprows)
            self._csv_path = path

            self.file_label.setText(Path(path).name)
            self.file_label.setStyleSheet("color: #000; font-weight: bold;")

            # Populate column combos
            self._populate_columns()

            QMessageBox.information(
                self, "File Loaded",
                f"Loaded {len(self.df)} rows × {len(self.df.columns)} columns."
            )
            self._schedule_auto_preview()

        except Exception as e:
            QMessageBox.critical(self, "Load Error", f"Failed to load CSV:\n{e}")

    def _get_delimiter(self):
        """Get delimiter from combo."""
        text = self.delimiter_combo.currentText()
        if "Comma" in text:
            return ','
        elif "Semicolon" in text:
            return ';'
        elif "Tab" in text:
            return '\t'
        else:
            return ' '

    def _populate_columns(self):
        """Populate column selection list."""
        if self.df is None:
            return

        self.columns_list.clear()

        for col in self.df.columns:
            self.columns_list.addItem(col)

        # Auto-select all numeric columns
        numeric_cols = self.df.select_dtypes(include=[np.number]).columns
        for i in range(self.columns_list.count()):
            item = self.columns_list.item(i)
            if item.text() in numeric_cols:
                item.setSelected(True)

    # ------------------------------------------------------------------
    # Preview generation
    # ------------------------------------------------------------------

    def _get_theme(self):
        for btn in self.theme_btn_group.buttons():
            if btn.isChecked():
                return btn.property("theme")
        return "wong"

    def _schedule_auto_preview(self):
        self._auto_preview_timer.start()

    def _setup_auto_preview(self):
        self.delimiter_combo.currentIndexChanged.connect(self._schedule_auto_preview)
        self.skiprows_spin.valueChanged.connect(self._schedule_auto_preview)
        self.columns_list.itemSelectionChanged.connect(self._schedule_auto_preview)

        for btn in self.theme_btn_group.buttons():
            btn.toggled.connect(self._schedule_auto_preview)

        for widget in [
            self.fw_spin,
            self.fh_spin,
            self.note_fs_spin,
            self.xlabel_fs_spin,
            self.ylabel_fs_spin,
            self.title_fs_spin,
        ]:
            widget.valueChanged.connect(self._schedule_auto_preview)

        for widget in [
            self.points_cb,
            self.points_beside_cb,
            self.contrast_cb,
            self.show_box_cb,
            self.show_stats_cb,
            self.horizontal_cb,
        ]:
            widget.toggled.connect(self._schedule_auto_preview)

        for widget in [
            self.xlabel_edit,
            self.ylabel_edit,
            self.title_edit,
            self.note_edit,
        ]:
            widget.textChanged.connect(self._schedule_auto_preview)

        self.sig_text.textChanged.connect(self._schedule_auto_preview)

    def _generate_preview(self, silent: bool = True):
        """Generate and display the violin plot."""
        if self.df is None:
            if not silent:
                QMessageBox.warning(self, "No Data", "Please load a CSV file first.")
            return

        selected_items = self.columns_list.selectedItems()
        value_cols = [item.text() for item in selected_items]
        
        if not value_cols:
            if not silent:
                QMessageBox.warning(self, "No Columns", "Please select at least one column to plot.")
            return

        try:
            # Close previous figure to prevent pyplot figure accumulation
            if self.current_figure is not None:
                plt.close(self.current_figure)

            # Check if selected columns have numeric data
            valid_cols = []
            for col in value_cols:
                numeric_data = pd.to_numeric(self.df[col], errors='coerce')
                if not numeric_data.dropna().empty:
                    valid_cols.append(col)
            
            if not valid_cols:
                if not silent:
                    QMessageBox.warning(self, "Invalid Data", "None of the selected columns contain valid numeric data.")
                return

            # Generate statistics summary
            self._update_statistics(valid_cols)

            # Parse significance brackets
            sig_brackets = self._parse_significance_brackets()

            # Generate plot
            fig = self.generator.generate_violin_plot_wide(
                self.df,
                value_cols=valid_cols,
                x_label=self.xlabel_edit.text(),
                y_label=self.ylabel_edit.text(),
                title=self.title_edit.text(),
                x_label_fontsize=self.xlabel_fs_spin.value(),
                y_label_fontsize=self.ylabel_fs_spin.value(),
                title_fontsize=self.title_fs_spin.value(),
                show_points=self.points_cb.isChecked(),
                show_points_beside=self.points_beside_cb.isChecked(),
                show_box=self.show_box_cb.isChecked(),
                show_stats=self.show_stats_cb.isChecked(),
                kde_bandwidth='scott',
                orientation='horizontal' if self.horizontal_cb.isChecked() else 'vertical',
                significance_brackets=sig_brackets,
                theme=self._get_theme(),
                fig_width=self.fw_spin.value(),
                fig_height=self.fh_spin.value(),
                ur_note=self.note_edit.text().replace('\\n', '\n'),
                ur_note_fontsize=self.note_fs_spin.value(),
                enhance_contrast=self.contrast_cb.isChecked()
            )

            # Display in canvas
            self.canvas.figure.clear()
            self.canvas.figure = fig
            self.canvas.draw()
            self.current_figure = fig

        except Exception as e:
            if not silent:
                QMessageBox.critical(self, "Plot Error", f"Failed to generate plot:\n{e}")

    def _parse_significance_brackets(self):
        """Parse significance bracket text input into list of dicts."""
        brackets = []
        text = self.sig_text.toPlainText().strip()
        
        if not text:
            return None
        
        for line in text.split('\n'):
            line = line.strip()
            if not line:
                continue
            
            try:
                parts = [p.strip() for p in line.split(',')]
                if len(parts) < 3:
                    continue
                
                group1 = int(parts[0])
                group2 = int(parts[1])
                bracket_text = parts[2]
                y_offset = float(parts[3]) if len(parts) > 3 else 0.05
                
                brackets.append({
                    'group1': group1,
                    'group2': group2,
                    'text': bracket_text,
                    'y_offset': y_offset
                })
            except (ValueError, IndexError):
                continue
        
        return brackets if brackets else None

    def _update_statistics(self, value_cols: list[str]):
        """Update statistics text box."""
        try:
            lines = []
            lines.append("Statistical Summary")
            lines.append("-" * 50)

            for col in value_cols:
                data = self.df[col].dropna().values
                data = pd.to_numeric(data, errors='coerce')
                data = data[~np.isnan(data)]

                if len(data) == 0:
                    lines.append(f"  Column: {col} (No valid numeric data)")
                    lines.append("")
                    continue

                q1, med, q3 = np.percentile(data, [25, 50, 75])
                lines.append(f"  Column: {col}")
                lines.append(f"    n      = {len(data)}")
                lines.append(f"    Mean   = {np.mean(data):.4f}")
                lines.append(f"    Median = {med:.4f}")
                lines.append(f"    SD     = {np.std(data, ddof=1):.4f}")
                lines.append(f"    IQR    = {q1:.4f} – {q3:.4f}")
                lines.append(f"    Range  = {np.min(data):.4f} – {np.max(data):.4f}")
                lines.append("")

            self.stats_text.setPlainText("\n".join(lines))

        except Exception as e:
            self.stats_text.setPlainText(f"Error computing statistics:\n{e}")

    # ------------------------------------------------------------------
    # Project save / load
    # ------------------------------------------------------------------

    def _collect_state(self) -> dict:
        selected_cols = [item.text() for item in self.columns_list.selectedItems()]
        return {
            "csv_path": self._csv_path,
            "delimiter": self.delimiter_combo.currentText(),
            "skiprows": self.skiprows_spin.value(),
            "y_columns": selected_cols,
            "theme": self._get_theme(),
            "fig_width": self.fw_spin.value(),
            "fig_height": self.fh_spin.value(),
            "show_points": self.points_cb.isChecked(),
            "points_beside": self.points_beside_cb.isChecked(),
            "enhance_contrast": self.contrast_cb.isChecked(),
            "show_box": self.show_box_cb.isChecked(),
            "show_stats": self.show_stats_cb.isChecked(),
            "horizontal": self.horizontal_cb.isChecked(),
            "xlabel": self.xlabel_edit.text(),
            "ylabel": self.ylabel_edit.text(),
            "title": self.title_edit.text(),
            "note": self.note_edit.text(),
            "note_fs": self.note_fs_spin.value(),
            "xlabel_fs": self.xlabel_fs_spin.value(),
            "ylabel_fs": self.ylabel_fs_spin.value(),
            "title_fs": self.title_fs_spin.value(),
            "significance": self.sig_text.toPlainText(),
        }

    def _apply_state(self, state: dict) -> None:
        csv_path = state.get("csv_path")
        if csv_path and Path(csv_path).exists():
            try:
                delim_text = state.get("delimiter", "Comma (,)")
                self._combo_text_to_index(self.delimiter_combo, delim_text)
                skiprows = state.get("skiprows", 0)
                self.skiprows_spin.setValue(skiprows)
                delim = self._get_delimiter()
                self.df = pd.read_csv(csv_path, sep=delim, skiprows=skiprows)
                self._csv_path = csv_path
                self.file_label.setText(Path(csv_path).name)
                self.file_label.setStyleSheet("color: #000; font-weight: bold;")
                self._populate_columns()
                y_cols = state.get("y_columns", [])
                self._restore_list_selection(self.columns_list, y_cols)
            except Exception:
                pass
        self._set_radio_by_property(self.theme_btn_group, "theme", state.get("theme", "wong"))
        self.fw_spin.setValue(state.get("fig_width", 2.76))
        self.fh_spin.setValue(state.get("fig_height", 2.76))
        self.points_cb.setChecked(state.get("show_points", True))
        self.points_beside_cb.setChecked(state.get("points_beside", False))
        self.contrast_cb.setChecked(state.get("enhance_contrast", True))
        self.show_box_cb.setChecked(state.get("show_box", True))
        self.show_stats_cb.setChecked(state.get("show_stats", True))
        self.horizontal_cb.setChecked(state.get("horizontal", False))
        self.xlabel_edit.setText(state.get("xlabel", ""))
        self.ylabel_edit.setText(state.get("ylabel", ""))
        self.title_edit.setText(state.get("title", ""))
        self.note_edit.setText(state.get("note", ""))
        self.note_fs_spin.setValue(state.get("note_fs", 6.5))
        self.xlabel_fs_spin.setValue(state.get("xlabel_fs", 7.0))
        self.ylabel_fs_spin.setValue(state.get("ylabel_fs", 7.0))
        self.title_fs_spin.setValue(state.get("title_fs", 7.0))
        self.sig_text.setPlainText(state.get("significance", ""))

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def _export_figure(self):
        """Export the current figure to file."""
        if self.current_figure is None:
            QMessageBox.warning(self, "No Plot", "Generate a preview first.")
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Export Figure", "",
            "PDF (*.pdf);;PNG (*.png);;SVG (*.svg);;EPS (*.eps);;TIFF (*.tiff)"
        )
        if not path:
            return

        try:
            fmt = Path(path).suffix.lstrip('.').lower()
            dpi = 1200 if fmt in ('png', 'tiff') else 300

            save_kwargs = {'dpi': dpi, 'bbox_inches': 'tight', 'pad_inches': 0.02}
            if fmt == 'tiff':
                save_kwargs['pil_kwargs'] = {'compression': 'tiff_lzw'}

            self.current_figure.savefig(path, format=fmt, **save_kwargs)

            QMessageBox.information(
                self, "Export Success",
                f"Figure saved to:\n{path}\n\nFormat: {fmt.upper()}, "
                f"DPI: {'vector' if fmt in ('pdf', 'svg', 'eps') else dpi}"
            )

        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to save figure:\n{e}")


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Violin Plot Generator")
    app.setFont(QFont("Arial", 9))

    # Apply stylesheet
    app.setStyleSheet("""
        QMainWindow { background: #f5f5f5; }
        QGroupBox {
            font-weight: bold;
            border: 1px solid #cccccc;
            border-radius: 4px;
            margin-top: 8px;
            padding-top: 14px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 8px;
            padding: 0 4px;
        }
        QPushButton {
            padding: 6px 12px;
            border: 1px solid #bbb;
            border-radius: 3px;
            background: #ffffff;
        }
        QPushButton:hover { background: #e8e8e8; }
        QPushButton:pressed { background: #d0d0d0; }
        QComboBox, QLineEdit, QSpinBox {
            padding: 3px 6px;
            border: 1px solid #bbb;
            border-radius: 3px;
        }
    """)

    window = ViolinPlotGUI()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
