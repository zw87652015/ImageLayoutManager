"""Modal "Add Fill…" dialog for the Plot Editor.

Four fill types: a vertical span (X=a→b, full plot height), a
horizontal span (Y=a→b, full width), a fill under a curve (baseline →
one series, optional X range) and a fill between two curves (optional
X range). Accepting produces a plain dict consumed by
``PlotTab.add_fill`` — the dialog itself touches no overrides.
"""

from __future__ import annotations

import math

from PyQt6.QtCore import QSignalBlocker
from PyQt6.QtGui import QColor, QDoubleValidator, QPalette
from PyQt6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox,
                             QDoubleSpinBox, QFormLayout, QLabel,
                             QLineEdit, QPushButton, QStackedWidget,
                             QColorDialog, QVBoxLayout, QWidget)

from .i18n import tr

_TYPES = ('xspan', 'yspan', 'under', 'between')


def _join_alpha(rgb, alpha):
    return rgb + '%02x' % max(0, min(255, int(round(alpha * 255))))


class _ColorButton(QPushButton):
    """Swatch button + QColorDialog; keeps a '#rrggbb' value."""

    def __init__(self, color, on_pick=None, parent=None):
        super().__init__(parent)
        self.setObjectName('plotFillColor')
        self.setFixedWidth(28)
        self.setToolTip(tr('tip_choose_colour'))
        self._color = color
        self._on_pick = on_pick
        self.clicked.connect(self._open)
        self._paint()

    def color(self):
        return self._color

    def set_color(self, color):
        self._color = color
        self._paint()

    def _paint(self):
        border = self.palette().color(QPalette.ColorRole.Mid).name()
        self.setStyleSheet(
            'QPushButton { background-color: %s; border: 1px solid %s;'
            ' border-radius: 2px; }' % (self._color, border))

    def _open(self):
        dlg = QColorDialog(QColor(self._color), self)
        dlg.setOption(QColorDialog.ColorDialogOption.DontUseNativeDialog)
        if dlg.exec() == QColorDialog.DialogCode.Accepted:
            self.set_color(dlg.selectedColor().name())
            if self._on_pick is not None:
                self._on_pick()


class AddFillDialog(QDialog):
    """Collect one fill definition; ``result_item()`` after accept."""

    def __init__(self, series, document, parent=None):
        """``series``: plotted Series objects; ``document``: the current
        effective PlotDocument (view range + series colours)."""
        super().__init__(parent)
        self.setObjectName('plotAddFillDialog')
        self.setWindowTitle(tr('act_add_fill'))
        self.setModal(True)
        self._series = list(series or ())
        self._doc = document
        pairs = [(s.label or s.y_label or str(i),
                  getattr(s, 'y_column', None))
                 for i, s in enumerate(self._series)]
        self._series_pairs = [(l, v) for l, v in pairs
                              if v is not None]

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.type_combo = QComboBox(self)
        self.type_combo.setObjectName('plotFillType')
        for t in _TYPES:
            self.type_combo.addItem(tr('fill_type_' + t), t)
        self.type_combo.currentIndexChanged.connect(self._type_changed)
        form.addRow(tr('fill_type'), self.type_combo)
        layout.addLayout(form)

        self._pages = QStackedWidget(self)
        # ── span page ──
        span_page = QWidget(self)
        span_form = QFormLayout(span_page)
        xr = self._view_range('x')
        yr = self._view_range('y')
        self.span_lo = self._num_spin(self._third(xr)[0])
        self.span_hi = self._num_spin(self._third(xr)[1])
        self._span_lo_label = QLabel(tr('row_x_from'), span_page)
        self._span_hi_label = QLabel(tr('row_x_to'), span_page)
        span_form.addRow(self._span_lo_label, self.span_lo)
        span_form.addRow(self._span_hi_label, self.span_hi)
        self._pages.addWidget(span_page)
        # ── under page ──
        under_page = QWidget(self)
        under_form = QFormLayout(under_page)
        self.under_series = QComboBox(self)
        for label, col in self._series_pairs:
            self.under_series.addItem(label, col)
        under_form.addRow(tr('row_series'), self.under_series)
        self.baseline = self._num_spin(0.0)
        under_form.addRow(tr('row_baseline'), self.baseline)
        self.under_lo = self._range_edit()
        self.under_hi = self._range_edit()
        under_form.addRow(tr('row_x_from'), self.under_lo)
        under_form.addRow(tr('row_x_to'), self.under_hi)
        self._pages.addWidget(under_page)
        # ── between page ──
        between_page = QWidget(self)
        between_form = QFormLayout(between_page)
        self.between_a = QComboBox(self)
        self.between_b = QComboBox(self)
        for label, col in self._series_pairs:
            self.between_a.addItem(label, col)
            self.between_b.addItem(label, col)
        if self.between_b.count() > 1:
            self.between_b.setCurrentIndex(1)
        between_form.addRow(tr('row_series_a'), self.between_a)
        between_form.addRow(tr('row_series_b'), self.between_b)
        self.between_lo = self._range_edit()
        self.between_hi = self._range_edit()
        between_form.addRow(tr('row_x_from'), self.between_lo)
        between_form.addRow(tr('row_x_to'), self.between_hi)
        self._pages.addWidget(between_page)
        layout.addWidget(self._pages)

        common = QFormLayout()
        self._color_dirty = False
        self.color_btn = _ColorButton(
            self._default_color(_TYPES[0]),
            on_pick=self._color_picked, parent=self)
        common.addRow(tr('row_colour'), self.color_btn)
        self.opacity = QDoubleSpinBox(self)
        self.opacity.setObjectName('plotFillOpacity')
        self.opacity.setRange(0.05, 1.0)
        self.opacity.setSingleStep(0.05)
        self.opacity.setDecimals(2)
        self.opacity.setKeyboardTracking(False)
        self.opacity.setValue(0.25)
        common.addRow(tr('row_opacity'), self.opacity)
        self.label_edit = QLineEdit(self)
        self.label_edit.setPlaceholderText(tr('auto_placeholder'))
        common.addRow(tr('row_label'), self.label_edit)
        layout.addLayout(common)

        self.error_label = QLabel(self)
        self.error_label.setObjectName('plotFillError')
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        layout.addWidget(self.error_label)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel, self)
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)

        for w in (self.span_lo, self.span_hi, self.baseline,
                  self.under_series, self.between_a, self.between_b):
            if isinstance(w, QDoubleSpinBox):
                w.valueChanged.connect(lambda _v: self._sync())
            else:
                w.currentIndexChanged.connect(lambda _i: self._sync())
        for e in (self.under_lo, self.under_hi,
                  self.between_lo, self.between_hi):
            e.textChanged.connect(lambda _t: self._sync())
        self.under_series.currentIndexChanged.connect(
            self._maybe_follow_color)
        self.between_a.currentIndexChanged.connect(
            self._maybe_follow_color)
        self._type_changed(0)

    # ── helpers ──────────────────────────────────────────────────────
    def _view_range(self, axis):
        doc = self._doc
        lim = getattr(doc, 'xlim' if axis == 'x' else 'ylim', None) \
            if doc is not None else None
        if lim is not None:
            return float(lim[0]), float(lim[1])
        vals = []
        for s in (doc.series if doc is not None else ()):
            vals += (s.x if axis == 'x' else s.y)
        if vals:
            lo, hi = min(vals), max(vals)
            if lo == hi:
                return lo - 1.0, hi + 1.0
            return lo, hi
        return 0.0, 1.0

    @staticmethod
    def _third(rng):
        lo, hi = rng
        d = (hi - lo) / 3.0
        return lo + d, hi - d

    def _num_spin(self, value):
        s = QDoubleSpinBox(self)
        s.setRange(-1e12, 1e12)
        s.setDecimals(6)
        s.setKeyboardTracking(False)
        s.setValue(value)
        return s

    def _range_edit(self):
        e = QLineEdit(self)
        e.setPlaceholderText(tr('fill_full_range'))
        e.setValidator(QDoubleValidator(self))
        e.setMaximumWidth(90)
        return e

    def _series_color(self, y_col):
        """The effective document colour of the series drawn for
        ``y_col`` (plotted-item order matches ``doc.series``)."""
        doc = self._doc
        if doc is None:
            return None
        for i, s in enumerate(self._series):
            if getattr(s, 'y_column', None) == y_col \
                    and i < len(doc.series):
                return doc.series[i].color[:7]
        return None

    def _default_color(self, ftype):
        if ftype in ('under', 'between'):
            combo = self.under_series if ftype == 'under' \
                else self.between_a
            c = self._series_color(combo.currentData())
            if c is not None:
                return c
            doc = self._doc
            if doc is not None and doc.series:
                return doc.series[0].color[:7]
        return '#7f7f7f'

    def _color_picked(self):
        # A manual pick stops the colour following the Series A combo.
        self._color_dirty = True

    def _maybe_follow_color(self, _i=None):
        if not self._color_dirty:
            self.color_btn.set_color(
                self._default_color(
                    _TYPES[self.type_combo.currentIndex()]))

    # ── state ────────────────────────────────────────────────────────
    def _type_changed(self, index):
        ftype = _TYPES[index]
        is_span = ftype in ('xspan', 'yspan')
        self._pages.setCurrentIndex(
            0 if is_span else 1 if ftype == 'under' else 2)
        if is_span:
            axis = 'x' if ftype == 'xspan' else 'y'
            self._span_lo_label.setText(
                tr('row_x_from' if axis == 'x' else 'row_y_from'))
            self._span_hi_label.setText(
                tr('row_x_to' if axis == 'x' else 'row_y_to'))
            # From/To prefill the middle third of the current view range.
            lo, hi = self._third(self._view_range(axis))
            for spin, v in ((self.span_lo, lo), (self.span_hi, hi)):
                blocker = QSignalBlocker(spin)
                spin.setValue(v)
        self._maybe_follow_color()
        blocker = QSignalBlocker(self.opacity)
        self.opacity.setValue(0.25 if is_span else 0.3)
        self._sync()

    def _range_value(self, edit):
        t = edit.text().strip()
        if not t:
            return None, True
        try:
            v = float(t)
        except ValueError:
            return None, False
        return v, math.isfinite(v)

    def _sync(self):
        ok = True
        ftype = _TYPES[self.type_combo.currentIndex()]
        if ftype in ('xspan', 'yspan'):
            ok = self.span_lo.value() != self.span_hi.value()
        else:
            if not self._series_pairs:
                ok = False
            if ftype == 'between':
                ok = ok and (self.between_a.currentData()
                             != self.between_b.currentData())
            lo_e = self.under_lo if ftype == 'under' \
                else self.between_lo
            hi_e = self.under_hi if ftype == 'under' \
                else self.between_hi
            lo, ok_lo = self._range_value(lo_e)
            hi, ok_hi = self._range_value(hi_e)
            ok = ok and ok_lo and ok_hi
            if ok and lo is not None and hi is not None:
                ok = lo < hi
        self.error_label.hide()
        self._buttons.button(
            QDialogButtonBox.StandardButton.Ok).setEnabled(ok)

    # ── result ───────────────────────────────────────────────────────
    def result_item(self):
        ftype = _TYPES[self.type_combo.currentIndex()]
        color = _join_alpha(self.color_btn.color(),
                            self.opacity.value())
        out = {'type': ftype, 'color': color,
               'label': self.label_edit.text().strip()}
        if ftype in ('xspan', 'yspan'):
            lo, hi = sorted((self.span_lo.value(),
                             self.span_hi.value()))
            out.update(lo=lo, hi=hi)
            return out
        if ftype == 'under':
            lo, ok = self._range_value(self.under_lo)
            hi, _ok = self._range_value(self.under_hi)
            out.update(a=self.under_series.currentData(),
                       baseline=self.baseline.value(),
                       x_min=lo, x_max=hi)
            return out
        lo, _a = self._range_value(self.between_lo)
        hi, _b = self._range_value(self.between_hi)
        out.update(a=self.between_a.currentData(),
                   b=self.between_b.currentData(),
                   x_min=lo, x_max=hi)
        return out
