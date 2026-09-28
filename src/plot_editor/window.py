"""ILM Plot Editor window.

``PlotEditorWindow`` is a top-level QDialog used both standalone (launched by
``plot_editor_main.py`` / ``main.py --plot-editor``) and in-process from the
main ILM window (``for_ilm=True``, modal, "Apply to Figure"). It never
touches ILM project/canvas objects — the ILM boundary lives in
``src/utils/editable_plot.py`` and the command in ``src/app/commands.py``.

Editing model: all controls — including the currently displayed series data
text — are flushed by ONE draft builder (:meth:`_draft_from_controls`), so a
commit never silently drops pending edits. Widget values are only written
into the document when they differ from the last populated baseline, which
keeps full precision for untouched fields (QDoubleSpinBox rounds to its
display decimals). Uncommitted control changes are "pending": they mark the
window dirty, prompt on New/Open/Close/Esc, and are replayed onto the
widgets after undo/redo instead of being lost.
"""

from __future__ import annotations

import copy
import csv
import io
import math
import os

from PyQt6.QtCore import Qt, QTimer, QByteArray, QSettings
from PyQt6.QtGui import QColor, QUndoCommand, QUndoStack
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtSvgWidgets import QSvgWidget
from PyQt6.QtWidgets import (
    QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox,
    QDoubleSpinBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QPushButton,
    QScrollArea, QSizePolicy, QSplitter, QVBoxLayout, QWidget,
)

from src.app.i18n import tr, set_language, current_language
from src.app.theme import build_palette, apply_font_scale, LIGHT, DARK

from .document import (
    LineSeries, PlotDocument, PlotDocumentError, MAX_FILE_BYTES,
    MAX_TOTAL_POINTS, LINESTYLES, MARKERS, LEGEND_LOCATIONS, load_document,
)
from .render import render_document, save_document

_PREVIEW_DEBOUNCE_MS = 250


def _tr(key: str) -> str:
    return tr(key)


def parse_xy_text(text: str):
    """Parse two-column CSV/TSV text into (x, y) float lists.

    Only a literal ``x,y`` header row is allowed. Extra columns, empty
    cells, malformed rows and non-finite values raise PlotDocumentError
    naming the offending line — nothing is ever silently skipped.
    """
    rows = text.splitlines()
    first = next((r for r in rows if r.strip()), '')
    delimiter = '\t' if '\t' in first else ','
    x, y = [], []
    first_row = True
    try:
        reader = csv.reader(io.StringIO(text), delimiter=delimiter,
                            strict=True)
        for line_number, row in enumerate(reader, 1):
            if not row or (len(row) == 1 and not row[0].strip()):
                continue
            cells = [v.strip() for v in row]
            if first_row and [v.casefold() for v in cells] == ['x', 'y']:
                first_row = False
                continue
            first_row = False
            if len(cells) != 2 or not all(cells):
                raise PlotDocumentError(
                    _tr('pe_err_data_row').format(
                        line=line_number, text=delimiter.join(row)))
            try:
                a, b = float(cells[0]), float(cells[1])
            except ValueError as exc:
                raise PlotDocumentError(
                    _tr('pe_err_data_row').format(
                        line=line_number, text=delimiter.join(row))) from exc
            if not (math.isfinite(a) and math.isfinite(b)):
                raise PlotDocumentError(
                    _tr('pe_err_data_row').format(
                        line=line_number, text=delimiter.join(row)))
            x.append(a)
            y.append(b)
            if len(x) > MAX_TOTAL_POINTS:
                raise PlotDocumentError(_tr('pe_err_too_many_points'))
    except csv.Error as exc:
        raise PlotDocumentError(
            _tr('pe_err_data_row').format(
                line=reader.line_num, text=str(exc))) from exc
    if not x:
        raise PlotDocumentError(_tr('pe_err_data_empty'))
    return x, y


class _DocSnapshotCommand(QUndoCommand):
    """Whole-document snapshot undo entry (documents are small)."""

    def __init__(self, window: 'PlotEditorWindow', old: dict, new: dict,
                     text: str):
        super().__init__(text)
        self._w = window
        self._old = old
        self._new = new

    def redo(self):
        self._w._restore_snapshot(self._new)

    def undo(self):
        self._w._restore_snapshot(self._old)


class PlotEditorWindow(QDialog):
    """Editor for a single :class:`PlotDocument`.

    Works on its own clone of the input document; ``result_document`` is set
    only when the user accepts via "Apply to Figure" (ILM mode) — plain
    ``accept()``/Cancel leaves it ``None``.
    """

    def __init__(self, document: PlotDocument | None = None, parent=None,
                 *, for_ilm: bool = False):
        super().__init__(parent)
        self._for_ilm = for_ilm
        self.result_document: PlotDocument | None = None
        self._doc = (document.clone() if document is not None
                     else PlotDocument())
        self._saved_dict = self._doc.to_dict()
        self._series_idx = 0
        self._path: str | None = None
        self._pending = False
        self._loading = False
        self._discard_ok = False
        self._baseline: dict = {}
        self._error_source: str | None = None
        self._i18n: list = []          # [(widget, key)]
        self.undo_stack = QUndoStack(self)
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(_PREVIEW_DEBOUNCE_MS)
        self._preview_timer.timeout.connect(self._refresh_preview)
        self._build_ui()
        self._populate_all()
        self.setWindowTitle(self._title())
        self.resize(1080, 700)
        self.setMinimumSize(850, 560)
        self._schedule_preview()

    # ── public API ─────────────────────────────────────────────────
    @property
    def document(self) -> PlotDocument:
        return self._doc

    @property
    def _dirty(self) -> bool:
        return (self._doc.to_dict() != self._saved_dict) or self._pending

    def set_document(self, doc: PlotDocument, path: str | None = None):
        self._doc = doc.clone()
        self._saved_dict = self._doc.to_dict()
        self._path = path
        self._pending = False
        self.undo_stack.clear()
        self._populate_all()
        self._show_error('')
        self._schedule_preview()
        self._update_title()

    # ── UI construction ────────────────────────────────────────────
    def _row(self, form: QFormLayout, key: str, widget: QWidget):
        lab = QLabel(_tr(key))
        self._i18n.append((lab, key))
        form.addRow(lab, widget)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)

        # toolbar row
        bar = QHBoxLayout()
        self.btn_new = QPushButton()
        self.btn_open = QPushButton()
        self.btn_save = QPushButton()
        self.btn_save_as = QPushButton()
        self.btn_undo = QPushButton()
        self.btn_redo = QPushButton()
        self._i18n += [(self.btn_new, 'pe_new'), (self.btn_open, 'pe_open'),
                       (self.btn_save, 'pe_save'),
                       (self.btn_save_as, 'pe_save_as'),
                       (self.btn_undo, 'pe_undo'), (self.btn_redo, 'pe_redo')]
        self.btn_new.clicked.connect(self._on_new)
        self.btn_open.clicked.connect(self._on_open)
        self.btn_save.clicked.connect(self._on_save)
        self.btn_save_as.clicked.connect(lambda: self._on_save(save_as=True))
        self.btn_undo.clicked.connect(self._on_undo)
        self.btn_redo.clicked.connect(self._on_redo)
        self.undo_stack.canUndoChanged.connect(self.btn_undo.setEnabled)
        self.undo_stack.canRedoChanged.connect(self.btn_redo.setEnabled)
        self.btn_undo.setEnabled(False)
        self.btn_redo.setEnabled(False)
        for b in (self.btn_new, self.btn_open, self.btn_save,
                  self.btn_save_as, self.btn_undo, self.btn_redo):
            bar.addWidget(b)
        bar.addStretch(1)
        if not self._for_ilm:
            lab = QLabel()
            self._i18n.append((lab, 'pe_language'))
            self.lang_combo = QComboBox()
            self.lang_combo.addItems(['English', '中文'])
            self.lang_combo.setCurrentIndex(
                0 if current_language() == 'en' else 1)
            self.lang_combo.currentIndexChanged.connect(self._on_language)
            lab2 = QLabel()
            self._i18n.append((lab2, 'pe_theme'))
            self.theme_combo = QComboBox()
            for name, key in ((LIGHT, 'pe_theme_light'),
                              (DARK, 'pe_theme_dark')):
                self.theme_combo.addItem(_tr(key), userData=name)
            self.theme_combo.currentIndexChanged.connect(self._on_theme)
            bar.addWidget(lab)
            bar.addWidget(self.lang_combo)
            bar.addWidget(lab2)
            bar.addWidget(self.theme_combo)
        root.addLayout(bar)

        split = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(split, 1)

        # preview (left, large)
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        self.preview = QSvgWidget()
        self.preview.setMinimumSize(320, 240)
        self.preview.setSizePolicy(QSizePolicy.Policy.Expanding,
                                   QSizePolicy.Policy.Expanding)
        lv.addWidget(self.preview, 1)
        self.error_label = QLabel('')
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet('color: #b3261e;')
        lv.addWidget(self.error_label)
        split.addWidget(left)

        # controls (right, scrollable)
        controls = QWidget()
        form_root = QVBoxLayout(controls)
        form_root.setContentsMargins(4, 4, 4, 4)

        self.plot_box = QGroupBox()
        self._i18n.append((self.plot_box, 'pe_plot_group'))
        pf = QFormLayout(self.plot_box)
        self.ed_title = QLineEdit()
        self.ed_xlabel = QLineEdit()
        self.ed_ylabel = QLineEdit()
        self._row(pf, 'pe_title', self.ed_title)
        self._row(pf, 'pe_xlabel', self.ed_xlabel)
        self._row(pf, 'pe_ylabel', self.ed_ylabel)
        self.sp_width = self._spin(0.01, 1000.0, ' mm')
        self.sp_height = self._spin(0.01, 1000.0, ' mm')
        self._row(pf, 'pe_width', self.sp_width)
        self._row(pf, 'pe_height', self.sp_height)
        self.ed_family = QLineEdit()
        self._row(pf, 'pe_font_family', self.ed_family)
        self.sp_font = self._spin(0.5, 200.0, ' pt')
        self.sp_title_font = self._spin(0.5, 200.0, ' pt')
        self._row(pf, 'pe_font_size', self.sp_font)
        self._row(pf, 'pe_title_size', self.sp_title_font)
        # limits
        self.chk_xlim_auto = QCheckBox(_tr('pe_auto'))
        self.ed_xlim = QLineEdit()
        self.ed_xlim.setPlaceholderText(_tr('pe_min_max'))
        xl = QHBoxLayout()
        xl.addWidget(self.ed_xlim, 1)
        xl.addWidget(self.chk_xlim_auto)
        xw = QWidget(); xw.setLayout(xl)
        self._row(pf, 'pe_xlim', xw)
        self.chk_ylim_auto = QCheckBox(_tr('pe_auto'))
        self.ed_ylim = QLineEdit()
        self.ed_ylim.setPlaceholderText(_tr('pe_min_max'))
        yl = QHBoxLayout()
        yl.addWidget(self.ed_ylim, 1)
        yl.addWidget(self.chk_ylim_auto)
        yw = QWidget(); yw.setLayout(yl)
        self._row(pf, 'pe_ylim', yw)
        self.chk_legend = QCheckBox()
        self._i18n.append((self.chk_legend, 'pe_show_legend'))
        self.combo_legend = QComboBox()
        for loc in LEGEND_LOCATIONS:
            self.combo_legend.addItem(_tr('pe_loc_' + loc.replace(' ', '_')),
                                      userData=loc)
        self._row(pf, 'pe_legend', self.chk_legend)
        self._row(pf, 'pe_legend_loc', self.combo_legend)
        self.chk_grid = QCheckBox()
        self._i18n.append((self.chk_grid, 'pe_show_grid'))
        self._row(pf, 'pe_grid', self.chk_grid)
        form_root.addWidget(self.plot_box)

        self.series_box = QGroupBox()
        self._i18n.append((self.series_box, 'pe_series_group'))
        sf = QFormLayout(self.series_box)
        srow = QHBoxLayout()
        self.combo_series = QComboBox()
        self.btn_add_series = QPushButton()
        self.btn_del_series = QPushButton()
        self._i18n += [(self.btn_add_series, 'pe_add_series'),
                       (self.btn_del_series, 'pe_remove_series')]
        srow.addWidget(self.combo_series, 1)
        srow.addWidget(self.btn_add_series)
        srow.addWidget(self.btn_del_series)
        sw = QWidget(); sw.setLayout(srow)
        self._row(sf, 'pe_series', sw)
        self.ed_slabel = QLineEdit()
        self._row(sf, 'pe_series_label', self.ed_slabel)
        crow = QHBoxLayout()
        self.ed_color = QLineEdit()
        self.ed_color.setMaxLength(9)
        self.btn_color = QPushButton()
        self._i18n.append((self.btn_color, 'pe_pick'))
        self.btn_color.clicked.connect(self._pick_color)
        crow.addWidget(self.ed_color, 1)
        crow.addWidget(self.btn_color)
        cw = QWidget(); cw.setLayout(crow)
        self._row(sf, 'pe_color', cw)
        self.sp_lw = self._spin(0.01, 200.0, ' pt')
        self._row(sf, 'pe_linewidth', self.sp_lw)
        self.combo_ls = QComboBox()
        for ls in LINESTYLES:
            self.combo_ls.addItem(
                ls if ls else _tr('pe_line_none'), userData=ls)
        self._row(sf, 'pe_linestyle', self.combo_ls)
        self.combo_marker = QComboBox()
        for mk in MARKERS:
            self.combo_marker.addItem(
                mk if mk else _tr('pe_marker_none'), userData=mk)
        self._row(sf, 'pe_marker', self.combo_marker)
        self.sp_ms = self._spin(0.0, 200.0, ' pt')
        self._row(sf, 'pe_markersize', self.sp_ms)
        self.lab_data_hint = QLabel()
        self._i18n.append((self.lab_data_hint, 'pe_data_hint'))
        sf.addRow(self.lab_data_hint)
        self.ed_data = QPlainTextEdit()
        self.ed_data.setPlaceholderText('x, y\n0, 0\n1, 1')
        self.ed_data.setMinimumHeight(110)
        sf.addRow(self.ed_data)
        drow = QHBoxLayout()
        self.btn_data_update = QPushButton()
        self.btn_import_csv = QPushButton()
        self._i18n += [(self.btn_data_update, 'pe_update_data'),
                       (self.btn_import_csv, 'pe_import_csv')]
        self.btn_data_update.clicked.connect(self._on_update_data)
        self.btn_import_csv.clicked.connect(self._on_import_csv)
        drow.addWidget(self.btn_data_update)
        drow.addWidget(self.btn_import_csv)
        dw = QWidget(); dw.setLayout(drow)
        sf.addRow(dw)
        form_root.addWidget(self.series_box)
        form_root.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(controls)
        scroll.setMinimumWidth(340)
        split.addWidget(scroll)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        split.setSizes([680, 400])

        # bottom buttons
        btns = QHBoxLayout()
        btns.addStretch(1)
        if self._for_ilm:
            self.btn_apply = QPushButton()
            self.btn_cancel = QPushButton()
            self._i18n += [(self.btn_apply, 'pe_apply_to_figure'),
                           (self.btn_cancel, 'pe_cancel')]
            self.btn_apply.setDefault(True)
            self.btn_apply.clicked.connect(self._apply_to_figure)
            self.btn_cancel.clicked.connect(self._on_cancel)
            btns.addWidget(self.btn_apply)
            btns.addWidget(self.btn_cancel)
        else:
            self.btn_close = QPushButton()
            self._i18n.append((self.btn_close, 'pe_close'))
            self.btn_close.clicked.connect(self.close)
            btns.addWidget(self.btn_close)
        root.addLayout(btns)

        # wire change signals
        self.ed_title.editingFinished.connect(self._on_fields_changed)
        self.ed_xlabel.editingFinished.connect(self._on_fields_changed)
        self.ed_ylabel.editingFinished.connect(self._on_fields_changed)
        self.ed_family.editingFinished.connect(self._on_fields_changed)
        for le in (self.ed_title, self.ed_xlabel, self.ed_ylabel,
                   self.ed_family, self.ed_xlim, self.ed_ylim,
                   self.ed_slabel, self.ed_color):
            le.textEdited.connect(self._mark_pending)
        for sp in (self.sp_width, self.sp_height, self.sp_font,
                   self.sp_title_font):
            sp.valueChanged.connect(self._on_fields_changed)
        self.chk_xlim_auto.toggled.connect(self._on_fields_changed)
        self.chk_ylim_auto.toggled.connect(self._on_fields_changed)
        self.ed_xlim.editingFinished.connect(self._on_fields_changed)
        self.ed_ylim.editingFinished.connect(self._on_fields_changed)
        self.chk_legend.toggled.connect(self._on_fields_changed)
        self.chk_grid.toggled.connect(self._on_fields_changed)
        self.combo_legend.currentIndexChanged.connect(self._on_fields_changed)
        self.combo_series.currentIndexChanged.connect(self._on_series_switch)
        self.ed_slabel.editingFinished.connect(self._on_series_fields)
        self.ed_color.editingFinished.connect(self._on_series_fields)
        self.sp_lw.valueChanged.connect(self._on_series_fields)
        self.sp_ms.valueChanged.connect(self._on_series_fields)
        self.combo_ls.currentIndexChanged.connect(self._on_series_fields)
        self.combo_marker.currentIndexChanged.connect(self._on_series_fields)
        self.ed_data.textChanged.connect(self._on_data_text_changed)
        self.btn_add_series.clicked.connect(self._on_add_series)
        self.btn_del_series.clicked.connect(self._on_remove_series)
        self._retranslate()

    def _spin(self, lo, hi, suffix):
        sp = QDoubleSpinBox()
        sp.setRange(lo, hi)
        sp.setDecimals(2)
        sp.setSuffix(suffix)
        sp.setSingleStep(0.5)
        return sp

    # ── population / baseline ───────────────────────────────────────
    def _current_index(self) -> int:
        return min(max(self._series_idx, 0), len(self._doc.series) - 1)

    def _baseline_snapshot(self) -> dict:
        """Current widget values for every commit-relevant control."""
        return {
            'title': self.ed_title.text(),
            'xlabel': self.ed_xlabel.text(),
            'ylabel': self.ed_ylabel.text(),
            'width': self.sp_width.value(),
            'height': self.sp_height.value(),
            'family': self.ed_family.text(),
            'font': self.sp_font.value(),
            'title_font': self.sp_title_font.value(),
            'xlim_auto': self.chk_xlim_auto.isChecked(),
            'xlim': self.ed_xlim.text(),
            'ylim_auto': self.chk_ylim_auto.isChecked(),
            'ylim': self.ed_ylim.text(),
            'legend': self.chk_legend.isChecked(),
            'legend_loc': self.combo_legend.currentData(),
            'grid': self.chk_grid.isChecked(),
            'series_idx': self.combo_series.currentIndex(),
            'slabel': self.ed_slabel.text(),
            'color': self.ed_color.text(),
            'lw': self.sp_lw.value(),
            'ls': self.combo_ls.currentData(),
            'marker': self.combo_marker.currentData(),
            'ms': self.sp_ms.value(),
            'data': self.ed_data.toPlainText(),
        }

    def _populate_all(self):
        self._loading = True
        try:
            d = self._doc
            self.ed_title.setText(d.title)
            self.ed_xlabel.setText(d.xlabel)
            self.ed_ylabel.setText(d.ylabel)
            self.sp_width.setValue(d.width_mm)
            self.sp_height.setValue(d.height_mm)
            self.ed_family.setText(d.font_family)
            self.sp_font.setValue(d.font_size_pt)
            self.sp_title_font.setValue(d.title_size_pt)
            self.chk_xlim_auto.setChecked(d.xlim is None)
            self.ed_xlim.setText('' if d.xlim is None else
                                 f'{d.xlim[0]!r}, {d.xlim[1]!r}')
            self.ed_xlim.setEnabled(d.xlim is not None)
            self.chk_ylim_auto.setChecked(d.ylim is None)
            self.ed_ylim.setText('' if d.ylim is None else
                                 f'{d.ylim[0]!r}, {d.ylim[1]!r}')
            self.ed_ylim.setEnabled(d.ylim is not None)
            self.chk_legend.setChecked(d.legend)
            i = self.combo_legend.findData(d.legend_location)
            if i >= 0:
                self.combo_legend.setCurrentIndex(i)
            self.chk_grid.setChecked(d.grid)
            self._populate_series_combo(keep=self._series_idx)
            self._populate_series_fields()
            self._baseline = self._baseline_snapshot()
            self._pending = False
        finally:
            self._loading = False
        self._update_buttons()
        self._update_title()

    def _populate_series_combo(self, keep: int = -1):
        cur = self.combo_series.currentIndex() if keep < 0 else keep
        self.combo_series.blockSignals(True)
        self.combo_series.clear()
        for i, s in enumerate(self._doc.series):
            self.combo_series.addItem(f'{i + 1}: {s.label or s.id[:8]}')
        self.combo_series.setCurrentIndex(
            min(max(cur, 0), self.combo_series.count() - 1))
        self.combo_series.blockSignals(False)
        self._series_idx = self.combo_series.currentIndex()

    def _populate_series_fields(self):
        self._loading = True
        try:
            s = self._doc.series[self._current_index()]
            self.ed_slabel.setText(s.label)
            self.ed_color.setText(s.color)
            self.sp_lw.setValue(s.linewidth_pt)
            self.combo_ls.setCurrentIndex(LINESTYLES.index(s.linestyle))
            self.combo_marker.setCurrentIndex(MARKERS.index(s.marker))
            self.sp_ms.setValue(s.markersize_pt)
            # repr round-trips full precision — :g would truncate data.
            self.ed_data.setPlainText('\n'.join(
                f'{float(x)!r}, {float(y)!r}'
                for x, y in zip(s.x, s.y)))
            self.btn_del_series.setEnabled(len(self._doc.series) > 1)
        finally:
            self._loading = False

    def _restore_snapshot(self, data: dict):
        self._doc = PlotDocument.from_dict(copy.deepcopy(data))
        self._populate_all()
        self._show_error('')
        self._schedule_preview()

    # ── editing plumbing ────────────────────────────────────────────
    def _parse_limits(self, text: str, ctx: str):
        parts = [p.strip() for p in text.replace(';', ',').split(',')
                 if p.strip()]
        if len(parts) != 2:
            raise PlotDocumentError(f'{ctx}: expected "min, max"')
        vals = [float(p) for p in parts]
        if not all(math.isfinite(v) for v in vals):
            raise PlotDocumentError(f'{ctx}: limits must be finite')
        if vals[0] == vals[1]:
            raise PlotDocumentError(f'{ctx}: limits must differ')
        return vals

    def _draft_from_controls(self, series_idx: int | None = None) -> dict:
        """Build a document dict from ALL controls, including the data
        text of the series currently displayed in the editor widgets.

        Spinboxes only override the document when the user changed them —
        untouched fields keep full document precision.
        """
        si = self._series_idx if series_idx is None else series_idx
        si = min(max(si, 0), len(self._doc.series) - 1)
        d = self._doc.clone()
        b = self._baseline
        d.title = self.ed_title.text()
        d.xlabel = self.ed_xlabel.text()
        d.ylabel = self.ed_ylabel.text()
        if self.sp_width.value() != b.get('width'):
            d.width_mm = float(self.sp_width.value())
        if self.sp_height.value() != b.get('height'):
            d.height_mm = float(self.sp_height.value())
        d.font_family = self.ed_family.text().strip() or d.font_family
        if self.sp_font.value() != b.get('font'):
            d.font_size_pt = float(self.sp_font.value())
        if self.sp_title_font.value() != b.get('title_font'):
            d.title_size_pt = float(self.sp_title_font.value())
        d.xlim = None if self.chk_xlim_auto.isChecked() \
            else self._parse_limits(self.ed_xlim.text(), 'X limits')
        d.ylim = None if self.chk_ylim_auto.isChecked() \
            else self._parse_limits(self.ed_ylim.text(), 'Y limits')
        d.legend = self.chk_legend.isChecked()
        d.legend_location = self.combo_legend.currentData() or d.legend_location
        d.grid = self.chk_grid.isChecked()
        s = d.series[si]
        s.label = self.ed_slabel.text()
        s.color = self.ed_color.text().strip() or s.color
        if self.sp_lw.value() != b.get('lw'):
            s.linewidth_pt = float(self.sp_lw.value())
        ls = self.combo_ls.currentData()
        if ls is not None:
            s.linestyle = ls
        mk = self.combo_marker.currentData()
        if mk is not None:
            s.marker = mk
        if self.sp_ms.value() != b.get('ms'):
            s.markersize_pt = float(self.sp_ms.value())
        x, y = parse_xy_text(self.ed_data.toPlainText())
        s.x, s.y = x, y
        return d.to_dict()

    def _apply_validated(self, validated: PlotDocument, old: dict,
                         new: dict, label: str):
        self._doc = validated
        self.undo_stack.push(_DocSnapshotCommand(self, old, new, label))
        # redo() already repopulated; refresh the rest.
        self._show_error('')
        self._update_title()
        self._schedule_preview()

    def _commit(self, label: str, series_idx: int | None = None) -> bool:
        """Flush ALL controls into the document, pushing one undo entry."""
        try:
            new = self._draft_from_controls(series_idx=series_idx)
            validated = PlotDocument.from_dict(copy.deepcopy(new))
        except (PlotDocumentError, ValueError) as e:
            self._show_error(str(e))
            return False
        old = self._doc.to_dict()
        if old == validated.to_dict():
            self._pending = False
            self._show_error('')
            self._update_title()
            return True
        self._apply_validated(validated, old, new, label)
        return True

    def _show_error(self, msg: str, source: str = 'commit'):
        self.error_label.setText(msg)
        self._error_source = source if msg else None
        self._update_buttons()

    def _update_buttons(self):
        ok = not self.error_label.text()
        for name in ('btn_apply', 'btn_save', 'btn_save_as'):
            b = getattr(self, name, None)
            if b is not None:
                b.setEnabled(ok)

    def _mark_pending(self, *_args):
        if self._loading:
            return
        # Compare widget snapshot to baseline (excluding which series is
        # displayed) so typing then restoring the original text clears
        # the pending flag again.
        snap = self._baseline_snapshot()
        snap.pop('series_idx', None)
        base = {k: v for k, v in self._baseline.items()
                if k != 'series_idx'}
        self._pending = snap != base
        self._update_title()

    def _on_data_text_changed(self):
        if self._loading:
            return
        self._mark_pending()
        try:
            parse_xy_text(self.ed_data.toPlainText())
        except PlotDocumentError as e:
            self._show_error(str(e), source='data')
            return
        if self._error_source == 'data':
            self._show_error('')

    def _on_fields_changed(self):
        if self._loading:
            return
        self.ed_xlim.setEnabled(not self.chk_xlim_auto.isChecked())
        self.ed_ylim.setEnabled(not self.chk_ylim_auto.isChecked())
        self._commit(_tr('pe_undo_fields'))

    def _on_series_fields(self):
        if self._loading:
            return
        self._commit(_tr('pe_undo_series'))

    def _on_series_switch(self, idx: int):
        if self._loading or idx == self._series_idx:
            return
        prev = self._series_idx
        # Widgets still show the PREVIOUS series — flush them against
        # prev before switching so data is never attributed wrongly.
        # Validation happens BEFORE _series_idx changes so the repopulate
        # inside the undo push already targets the new series.
        try:
            new = self._draft_from_controls(series_idx=prev)
            validated = PlotDocument.from_dict(copy.deepcopy(new))
        except (PlotDocumentError, ValueError) as e:
            self._show_error(str(e))
            self.combo_series.blockSignals(True)
            self.combo_series.setCurrentIndex(prev)
            self.combo_series.blockSignals(False)
            self._series_idx = prev
            return
        old = self._doc.to_dict()
        self._series_idx = idx
        if old != validated.to_dict():
            self._apply_validated(validated, old, new,
                                  _tr('pe_undo_series'))
        else:
            # Plain switching is not an edit: rebuild the baseline and
            # clear any pending flag so the window stays clean.
            self._populate_series_fields()
            self._baseline = self._baseline_snapshot()
            self._pending = False
            self._update_title()
        self._show_error('')
        self._schedule_preview()

    def _on_add_series(self):
        if not self._commit(_tr('pe_undo_fields')):
            return
        old = self._doc.to_dict()
        d = self._doc.clone()
        base = ['#0891b2', '#d97706', '#059669', '#7c3aed', '#dc2626']
        ns = LineSeries(label=_tr('pe_series_default').format(
            n=len(d.series) + 1))
        ns.color = base[len(d.series) % len(base)]
        d.series.append(ns)
        try:
            validated = PlotDocument.from_dict(d.to_dict())
        except PlotDocumentError as e:
            self._show_error(str(e))
            return
        new_idx = len(validated.series) - 1
        self._series_idx = new_idx
        self._apply_validated(validated, old, validated.to_dict(),
                              _tr('pe_undo_add_series'))

    def _on_remove_series(self):
        if len(self._doc.series) <= 1:
            return
        if not self._commit(_tr('pe_undo_fields')):
            return
        old = self._doc.to_dict()
        d = self._doc.clone()
        del d.series[self._current_index()]
        validated = PlotDocument.from_dict(d.to_dict())
        self._apply_validated(validated, old, validated.to_dict(),
                              _tr('pe_undo_remove_series'))

    def _on_update_data(self):
        self._commit(_tr('pe_undo_data'))

    def _on_import_csv(self):
        path, _ = QFileDialog.getOpenFileName(
            self, _tr('pe_import_csv'), '',
            'CSV (*.csv *.tsv *.txt);;All files (*)')
        if not path:
            return
        try:
            with open(path, 'rb') as fh:
                raw = fh.read(MAX_FILE_BYTES + 1)
            if len(raw) > MAX_FILE_BYTES:
                raise PlotDocumentError(_tr('pe_err_too_many_points'))
            text = raw.decode('utf-8-sig')
        except (OSError, UnicodeError) as e:
            self._show_error(str(e))
            return
        except PlotDocumentError as e:
            self._show_error(str(e))
            return
        self.ed_data.setPlainText(text)
        self._on_update_data()

    def _pick_color(self):
        c = QColorDialog.getColor(QColor(self.ed_color.text() or '#000000'),
                                  self, _tr('pe_color'))
        if c.isValid():
            self.ed_color.setText(c.name())
            self._on_series_fields()

    # ── preview ─────────────────────────────────────────────────────
    def _schedule_preview(self):
        self._preview_timer.start()

    def _refresh_preview(self):
        try:
            render = render_document(self._doc)
        except Exception as e:
            self.error_label.setText(str(e))
            self._update_buttons()
            return
        self.preview.load(QByteArray(render.svg))
        renderer = self.preview.renderer()
        if renderer is not None:
            renderer.setAspectRatioMode(Qt.AspectRatioMode.KeepAspectRatio)
        self._update_buttons()

    # ── file actions ────────────────────────────────────────────────
    def _title(self) -> str:
        base = os.path.basename(self._path) if self._path else _tr('pe_untitled')
        return f'{base}{"*" if self._dirty else ""} — {_tr("pe_window_title")}'

    def _update_title(self):
        self.setWindowTitle(self._title())

    def _confirm_discard(self) -> bool:
        """Prompt before dropping a dirty/pending draft. True = proceed."""
        if not self._dirty:
            return True
        if self._for_ilm:
            ret = QMessageBox.question(
                self, _tr('pe_discard_title'), _tr('pe_discard_text'),
                QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel)
            return ret == QMessageBox.StandardButton.Discard
        ret = QMessageBox.question(
            self, _tr('pe_unsaved_title'), _tr('pe_unsaved_text'),
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save)
        if ret == QMessageBox.StandardButton.Cancel:
            return False
        if ret == QMessageBox.StandardButton.Save:
            return self._on_save()
        return True

    def _on_new(self):
        if not self._confirm_discard():
            return
        self.set_document(PlotDocument())

    def _on_open(self):
        if not self._confirm_discard():
            return
        self.open_path_prompt()

    def open_path_prompt(self):
        path, _ = QFileDialog.getOpenFileName(
            self, _tr('pe_open'), '',
            'ILM Plot (*.ilmplot.svg);;SVG (*.svg)')
        if path:
            self.open_path(path)

    def open_path(self, path: str) -> bool:
        try:
            doc = load_document(path)
        except (PlotDocumentError, OSError) as e:
            QMessageBox.warning(self, _tr('pe_open_error_title'), str(e))
            return False
        self.set_document(doc, path=path)
        return True

    def _on_save(self, save_as: bool = False) -> bool:
        if not self._commit(_tr('pe_undo_fields')):
            return False
        path = self._path
        if save_as or not path:
            path, _ = QFileDialog.getSaveFileName(
                self, _tr('pe_save_as'), path or '',
                'ILM Plot (*.ilmplot.svg);;SVG (*.svg)')
            if not path:
                return False
            if not path.lower().endswith('.svg'):
                path += '.ilmplot.svg'
        try:
            save_document(self._doc, path)
        except Exception as e:
            QMessageBox.warning(self, _tr('pe_save_error_title'), str(e))
            return False
        self._path = path
        self._saved_dict = self._doc.to_dict()
        self._pending = False
        self._update_title()
        return True

    # ── ILM apply / cancel ──────────────────────────────────────────
    def _apply_to_figure(self):
        """Validate and accept; ILM reads ``result_document`` afterwards."""
        if not self._commit(_tr('pe_undo_fields')):
            return
        self.result_document = self._doc.clone()
        self.accept()

    def _on_cancel(self):
        self.reject()

    def reject(self):
        """Esc/Cancel path — goes through the dirty-draft prompt."""
        if self._discard_ok:
            self._discard_ok = False
            super().reject()
            return
        if self._confirm_discard():
            super().reject()

    def closeEvent(self, event):
        if self._confirm_discard():
            self._discard_ok = True
            self.reject()
        else:
            event.ignore()

    # ── undo / redo ────────────────────────────────────────────────
    # Pending widget edits are committed as their own undo entry first —
    # never replayed onto widgets, since undo can remove the series the
    # pending data belonged to.
    def _on_undo(self):
        if self._pending and not self._commit(_tr('pe_undo_fields')):
            return  # invalid draft stays visible; history untouched
        self.undo_stack.undo()
        self._schedule_preview()

    def _on_redo(self):
        if self._pending and not self._commit(_tr('pe_undo_fields')):
            return  # the commit itself clears the redo branch anyway
        self.undo_stack.redo()
        self._schedule_preview()

    # ── standalone theme/language ───────────────────────────────────
    def _settings(self) -> QSettings:
        return QSettings('AcademicFigureLayout', 'ImageLayoutManager')

    def _retranslate(self):
        for widget, key in self._i18n:
            try:
                if isinstance(widget, QGroupBox):
                    widget.setTitle(_tr(key))
                else:
                    widget.setText(_tr(key))
            except RuntimeError:
                continue
        for i, loc in enumerate(LEGEND_LOCATIONS):
            self.combo_legend.setItemText(
                i, _tr('pe_loc_' + loc.replace(' ', '_')))
        for i, ls in enumerate(LINESTYLES):
            if not ls:
                self.combo_ls.setItemText(i, _tr('pe_line_none'))
        for i, mk in enumerate(MARKERS):
            if not mk:
                self.combo_marker.setItemText(i, _tr('pe_marker_none'))
        self.chk_xlim_auto.setText(_tr('pe_auto'))
        self.chk_ylim_auto.setText(_tr('pe_auto'))
        self.ed_xlim.setPlaceholderText(_tr('pe_min_max'))
        self.ed_ylim.setPlaceholderText(_tr('pe_min_max'))
        if not self._for_ilm:
            self.theme_combo.setItemText(0, _tr('pe_theme_light'))
            self.theme_combo.setItemText(1, _tr('pe_theme_dark'))
        self._update_title()

    def _on_language(self, idx: int):
        lang = 'en' if idx == 0 else 'zh'
        if lang == current_language():
            return
        # A switch is a content commit point — an invalid draft must not
        # be silently dropped by repopulating widgets in a new language.
        if not self._commit(_tr('pe_undo_fields')):
            self.lang_combo.blockSignals(True)
            self.lang_combo.setCurrentIndex(0 if current_language() == 'en'
                                          else 1)
            self.lang_combo.blockSignals(False)
            return
        set_language(lang)
        self._settings().setValue('language', lang)
        self._retranslate()

    def _on_theme(self, idx: int):
        theme = self.theme_combo.itemData(idx) or (LIGHT if idx == 0 else DARK)
        from PyQt6.QtWidgets import QApplication
        from src.app.theme import get_stylesheet
        a = QApplication.instance()
        try:
            scale = float(self._settings().value('ui/font_scale', 1.0))
        except (TypeError, ValueError):
            scale = 1.0
        if a is not None:
            a.setPalette(build_palette(theme))
        # Restyle this window only — a full rebuild would touch widgets
        # whose signal handlers are currently running.
        self.setStyleSheet(get_stylesheet(theme, scale))
        self._settings().setValue('theme', theme)
