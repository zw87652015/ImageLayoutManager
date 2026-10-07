"""Floating per-element style panel for the Plot Editor.

A small frameless tool window opened by double-clicking a plot element.
Every change goes through ``PlotTab.update_overrides``; text fields
commit on ``editingFinished`` only (Enter / focus loss — never per
keystroke, so a partially typed ``$`` never reaches the renderer),
spin boxes use ``setKeyboardTracking(False)``, and toggles/combos apply
immediately. Optional rows get a reset button that restores the
inherited/default value.
"""

from __future__ import annotations

import copy
import math

from PyQt6.QtCore import QEvent, QObject, QPoint, QSize, Qt
from PyQt6.QtGui import QColor, QDoubleValidator, QGuiApplication, \
    QIntValidator, QPalette
from PyQt6.QtWidgets import (QApplication, QCheckBox, QColorDialog,
                             QComboBox, QCompleter, QDoubleSpinBox,
                             QFormLayout, QFrame, QHBoxLayout, QLabel,
                             QLineEdit, QPushButton, QSpinBox,
                             QToolButton, QVBoxLayout, QWidget)

from src.app import theme as app_theme

import ilmplot.render as render
from .chrome import element_panel_stylesheet, themed_icon
from .i18n import tr
from .style_icons import palette_strip, style_icon
from ilmplot.document import (LEGEND_LOCATIONS, LINESTYLES, MARKERS,
                       ANNOTATION_ANCHORS, AxisStyle, FrameStyle,
                       GridStyle, HistOptions, LegendStyle,
                       RidgeOptions, StackOptions, TextStyle,
                       TitleStyle, ViolinOptions)
from . import palettes
from .palettes import THEMES, theme_display_key
from .overrides import (SeriesOverride, parse_axis_limits,
                        reset_element, static_bands)

_PANEL_WIDTH = 300

_LINE_KEYS = {'-': 'line_solid', '--': 'line_dashed',
              '-.': 'line_dashdot', ':': 'line_dotted',
              '': 'line_none'}
_MARKER_KEYS = {'': 'marker_none', 'o': 'marker_circle',
                's': 'marker_square', '^': 'marker_tri_up',
                'v': 'marker_tri_down', 'D': 'marker_diamond',
                '+': 'marker_plus', 'x': 'marker_cross',
                '.': 'marker_point'}
_LOCATION_KEYS = {loc: 'loc_' + loc.replace(' ', '_')
                  for loc in LEGEND_LOCATIONS}
_DIRECTION_KEYS = {'out': 'dir_out', 'in': 'dir_in',
                   'inout': 'dir_both'}
_GRID_AXIS_KEYS = {'both': 'grid_axis_both', 'x': 'grid_axis_x',
                   'y': 'grid_axis_y'}
_GRID_WHICH_KEYS = {'major': 'grid_which_major',
                    'both': 'grid_which_both'}
_GRID_LINESTYLES = [k for k in LINESTYLES if k]

_VIOLIN_BODY_KEYS = {'none': ('panel_box', 'sec_box'),
                     'bar': ('panel_column_points', 'sec_column_points')}


def violin_panel_keys(body):
    """(title key, section key) for a violin element by body mode."""
    return _VIOLIN_BODY_KEYS.get(
        body, ('panel_violin', 'sec_violin'))

_TITLES = {'title': 'panel_title', 'xlabel': 'panel_xlabel',
           'ylabel': 'panel_ylabel', 'xticks': 'panel_xticks',
           'yticks': 'panel_yticks', 'legend': 'panel_legend',
           'frame': 'panel_frame'}
_ANCHOR_KEYS = {a: 'anchor_' + a.replace(' ', '_')
                for a in ANNOTATION_ANCHORS}


class _Swatch(QPushButton):
    """Small colour swatch; opens a palette-styled QColorDialog."""

    def __init__(self, border, panel):
        super().__init__()
        self._color = None
        self._border = border
        self._panel = panel
        self.setFixedWidth(28)
        self.setToolTip(tr('tip_choose_colour'))
        self.clicked.connect(self._open)

    def color(self):
        return self._color

    def set_color(self, hex_color, fallback='#000000'):
        self._color = hex_color
        self.setStyleSheet(
            'QPushButton { background-color: %s;'
            ' border: 1px solid %s; border-radius: 2px; }'
            % (hex_color or fallback, self._border))

    def _open(self):
        pal = self._panel.palette()
        win = pal.color(QPalette.ColorRole.Window).name()
        text = pal.color(QPalette.ColorRole.WindowText).name()
        base = pal.color(QPalette.ColorRole.Base).name()
        btn = pal.color(QPalette.ColorRole.Button).name()
        btn_tx = pal.color(QPalette.ColorRole.ButtonText).name()
        hi = pal.color(QPalette.ColorRole.Highlight).name()
        dlg = QColorDialog(QColor(self._color or '#000000'), self._panel)
        dlg.setOption(QColorDialog.ColorDialogOption.DontUseNativeDialog)
        dlg.setStyleSheet(
            f"QWidget {{ background-color: {win}; color: {text}; }}"
            f"QLineEdit, QSpinBox, QDoubleSpinBox {{"
            f"  background-color: {base}; color: {text};"
            f"  border: 1px solid {self._border}; border-radius: 3px; }}"
            f"QPushButton {{ background-color: {btn}; color: {btn_tx};"
            f"  border: 1px solid {self._border}; border-radius: 4px;"
            f"  padding: 3px 10px; }}"
            f"QPushButton:hover {{ border-color: {hi}; }}")
        if dlg.exec() == QColorDialog.DialogCode.Accepted:
            # Parented to the panel: the panel stays open, apply live.
            self.set_color(dlg.selectedColor().name())
            fn = getattr(self, '_color_fn', None)
            if fn is not None:
                self._panel._apply_now(lambda o: fn(o, self._color))


class TextStyleEditor(QWidget):
    """Text/font/size/B-I-U/colour rows editing a ``TextStyle``.

    ``get_style(overrides)`` returns the style object to mutate,
    creating it inside the update fn. Every optional row has a reset
    button; text commits on ``editingFinished`` only.
    """

    def __init__(self, panel, *, get_style, eff_style,
                 text_row=False, text_get=None, text_set=None,
                 default_text='', default_family='', default_size=8.0):
        """``eff_style`` returns the effective (fallback-resolved) style."""
        super().__init__()
        self._panel = panel
        self._get = get_style
        self._eff = eff_style
        self._text_set = text_set
        form = QFormLayout(self)
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(8)
        form.setVerticalSpacing(6)
        self._form = form

        if text_row:
            self.text_edit = QLineEdit(text_get() or '')
            self.text_edit.setPlaceholderText(default_text)
            # editingFinished only — a half-typed '$' never applies.
            self.text_edit.editingFinished.connect(
                lambda: panel._apply_now(
                    lambda o: text_set(o, self.text_edit.text())))
            panel._row(form, tr('row_text'), self.text_edit,
                       is_set=lambda: text_get() is not None,
                       reset=lambda o: text_set(o, None),
                       sync=lambda: self.text_edit.setText(
                           text_get() or ''),
                       reset_tip=tr('tip_reset_text'))

        # Font family — editable combo with contains-completer.
        self.family = QComboBox()
        self.family.setEditable(True)
        self.family.addItem(tr('font_default', family=default_family),
                            None)
        self._families = render.available_font_families()
        for name in self._families:
            self.family.addItem(name, name)
        completer = QCompleter(list(self._families), self.family)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.family.setCompleter(completer)
        self.family.activated.connect(
            lambda _i: self._commit_family())
        self.family.lineEdit().editingFinished.connect(
            self._commit_family)
        panel._row(form, tr('row_font'), self.family,
                   is_set=lambda: (self._style() is not None
                                   and self._style().family is not None),
                   reset=lambda o: setattr(get_style(o), 'family', None),
                   sync=self._sync_family)

        # Size — spin shows the effective pt size; reset restores None.
        self.size = QDoubleSpinBox()
        self.size.setRange(1.0, 72.0)
        self.size.setSingleStep(0.5)
        self.size.setDecimals(1)
        self.size.setKeyboardTracking(False)
        self.size.setValue(default_size)
        self.size.valueChanged.connect(
            lambda v: panel._apply_now(
                lambda o: setattr(get_style(o), 'size_pt', v)))
        panel._row(form, tr('row_size'), self.size,
                   is_set=lambda: (self._style() is not None
                                   and self._style().size_pt is not None),
                   reset=lambda o: setattr(get_style(o), 'size_pt', None),
                   sync=self._sync_size)
        self._default_size = default_size

        # B / I / U + colour swatch + colour reset.
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(4)
        self._flags = {}
        for name, icon, tip in (('bold', 'bold', tr('tip_bold')),
                                ('italic', 'italic', tr('tip_italic')),
                                ('underline', 'underline',
                                 tr('tip_underline'))):
            b = QToolButton()
            b.setIcon(panel.icon(icon))
            b.setToolTip(tip)
            b.setCheckable(True)
            b.setAutoRaise(True)
            b.toggled.connect(
                lambda on, n=name: panel._apply_now(
                    lambda o: setattr(get_style(o), n, on)))
            self._flags[name] = b
            h.addWidget(b)
        h.addStretch(1)
        self.swatch = _Swatch(panel.border, panel)
        self.swatch._color_fn = lambda o, c: setattr(
            get_style(o), 'color', c or '#000000')
        h.addWidget(self.swatch)
        clr = QToolButton()
        clr.setIcon(panel.icon('reset'))
        clr.setToolTip(tr('tip_reset_default'))
        clr.setAutoRaise(True)
        clr.clicked.connect(lambda: panel._apply_now(
            lambda o: setattr(get_style(o), 'color', '#000000')))
        h.addWidget(clr)
        self._color_reset = clr
        panel._syncs.append(self._sync_flags)
        panel._reset_buttons.append((
            lambda: (self._style() is not None
                     and self._style().color != '#000000'), clr))
        form.addRow(tr('row_style'), row)

    def _style(self):
        """Current stored override style (may be None)."""
        return self._stored() if hasattr(self, '_stored') else None

    def _commit_family(self):
        text = self.family.lineEdit().text()
        fam, ok = render.resolve_font_family(text, self._families)
        self._set_invalid(self.family.lineEdit(), not ok)
        if not ok:
            return
        self._panel._apply_now(
            lambda o: setattr(self._get(o), 'family', fam))

    @staticmethod
    def _set_invalid(widget, bad):
        widget.setProperty('invalid', bad)
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    def _sync_family(self):
        style = self._style()
        fam = style.family if style else None
        self.family.blockSignals(True)
        if fam is None:
            self.family.setCurrentIndex(0)
        else:
            i = self.family.findData(fam)
            if i >= 0:
                self.family.setCurrentIndex(i)
            else:
                self.family.setCurrentText(fam)
        self.family.blockSignals(False)
        self._set_invalid(self.family.lineEdit(), False)

    def _sync_size(self):
        style = self._style()
        eff = self._eff() or TextStyle()
        self.size.blockSignals(True)
        self.size.setValue((style.size_pt if style else None)
                           or eff.size_pt or self._default_size)
        self.size.blockSignals(False)

    def _sync_flags(self):
        style = self._style()
        eff = self._eff() or TextStyle()
        for name, b in self._flags.items():
            val = getattr(style, name) if style else getattr(eff, name)
            b.blockSignals(True)
            b.setChecked(bool(val))
            b.blockSignals(False)
        shown = (style.color if style else None) or eff.color
        self.swatch.set_color(shown)


class _OutsideClickFilter(QObject):
    """Closes the panel on clicks outside it; modal dialogs (colour
    picker) and combo popups keep it alive."""

    def __init__(self, panel):
        super().__init__(panel)
        self._panel = panel

    def eventFilter(self, obj, event):
        panel = self._panel
        if panel is None:
            return False
        et = event.type()
        if et == QEvent.Type.MouseButtonPress:
            if QApplication.activeModalWidget() is not None \
                    or QApplication.activePopupWidget() is not None:
                return False
            if not panel.geometry().contains(
                    event.globalPosition().toPoint()):
                panel.close()
        elif et == QEvent.Type.Hide and obj is panel._tab:
            panel.close()
        elif et == QEvent.Type.WindowDeactivate and obj is panel:
            # Defer: a modal child also deactivates the panel transiently.
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(0, self._maybe_close)
        return False

    def _maybe_close(self):
        panel = self._panel
        if panel is None:
            return
        if QApplication.activeModalWidget() is not None \
                or QApplication.activePopupWidget() is not None \
                or panel.isActiveWindow():
            return
        panel.close()


class ElementPanel(QFrame):
    """Floating tool window editing one plot element's overrides.

    ``Qt.Tool | FramelessWindowHint`` (not ``Popup`` — a modal
    ``QColorDialog`` would close a Popup before its colour is applied).
    ``_OutsideClickFilter`` handles outside clicks/Esc/tab-hide.
    """

    def __init__(self, tab, key, theme, scale):
        super().__init__(tab.window(),
                         Qt.WindowType.Tool
                         | Qt.WindowType.FramelessWindowHint)
        self.setObjectName('plotElementPanel')
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self._tab = tab
        self._key = key
        self._theme = theme
        self._scale = scale
        self.border = app_theme.get_tokens(theme)['border']
        self._syncs = []
        self._reset_buttons = []
        self._filter = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 8, 10, 8)
        outer.setSpacing(6)
        title = QLabel(self._element_title())
        title.setObjectName('plotElementPanelTitle')
        outer.addWidget(title)

        body = QFormLayout()
        body.setHorizontalSpacing(8)
        body.setVerticalSpacing(6)
        outer.addLayout(body)
        self._body = body
        self._build(body)

        footer = QHBoxLayout()
        footer.addStretch(1)
        reset = QPushButton(tr('btn_reset'))
        reset.setObjectName('plotElementPanelReset')
        reset.setFlat(True)
        reset.setCursor(Qt.CursorShape.PointingHandCursor)
        reset.clicked.connect(self._reset_element)
        footer.addWidget(reset)
        outer.addLayout(footer)

        self.setStyleSheet(element_panel_stylesheet(theme, scale))
        self.setFixedWidth(round(_PANEL_WIDTH * scale))
        self._refresh()
        # Undo/redo of overrides lands on the same object — re-sync
        # from it; a removed element (undo of Add Note/Fill/…) closes
        # the panel.
        tab.changed.connect(self._on_tab_changed)

    def _element_exists(self):
        """False when undo/redo removed the element this panel edits."""
        tab = self._tab
        if tab.plot is None:
            return False
        key = self._key
        doc = tab.effective_document()
        for prefix, attr in (('series:', 'series'), ('violin:', 'groups'),
                             ('hist:', 'groups'),
                             ('stack:', 'categories'),
                             ('annotation:', 'annotations'),
                             ('bracket:', 'brackets'),
                             ('span:', 'spans'), ('band:', 'bands')):
            if key.startswith(prefix):
                coll = getattr(doc, attr, None) if doc is not None \
                    else None
                iid = key[len(prefix):]
                return any(getattr(it, 'id', None) == iid
                           for it in (coll or ()))
        return True

    def _on_tab_changed(self):
        if not self._element_exists():
            self.close()
            return
        self._refresh()

    # ── entry point / lifecycle ───────────────────────────────────────

    @classmethod
    def open_for(cls, tab, key, global_pos):
        panel = cls(tab, key, tab.theme, tab.scale)
        pos = QPoint(global_pos) + QPoint(8, 8)
        screen = QGuiApplication.screenAt(global_pos) \
            or QGuiApplication.primaryScreen()
        avail = screen.availableGeometry()
        panel.adjustSize()
        pos.setX(min(pos.x(), avail.right() - panel.width()))
        pos.setY(min(pos.y(), avail.bottom() - panel.height()))
        pos.setX(max(pos.x(), avail.left()))
        pos.setY(max(pos.y(), avail.top()))
        panel.move(pos)
        panel.show()
        return panel

    def icon(self, name):
        return themed_icon(name, self._theme)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        if self._filter is None:
            self._filter = _OutsideClickFilter(self)
            QApplication.instance().installEventFilter(self._filter)

    def closeEvent(self, event):
        if self._filter is not None:
            app = QApplication.instance()
            if app is not None:
                app.removeEventFilter(self._filter)
            self._filter = None
        super().closeEvent(event)

    def _element_title(self):
        if self._key.startswith('series:'):
            sid = self._key[7:]
            label = ''
            doc = self._doc()
            if doc is not None:
                for s in doc.series:
                    if s.id == sid:
                        label = s.label
                        break
            return tr('panel_series', name=label or sid)
        for prefix, coll_name, title_key in (
                ('violin:', 'groups', None),
                ('hist:', 'groups', 'panel_hist'),
                ('stack:', 'categories', 'panel_stack')):
            if self._key.startswith(prefix):
                iid = self._key[len(prefix):]
                label = ''
                doc = self._doc()
                if doc is not None:
                    for item in getattr(doc, coll_name, ()):
                        if item.id == iid:
                            label = item.label
                            break
                if title_key is None:
                    body = doc.violin.body if doc is not None \
                        and doc.violin is not None else None
                    title_key = violin_panel_keys(body)[0]
                return tr(title_key, name=label or iid)
        if self._key.startswith('annotation:'):
            return tr('panel_annotation')
        if self._key.startswith('bracket:'):
            return tr('panel_bracket')
        if self._key.startswith('span:'):
            iid = self._key[len('span:'):]
            sp = self._content_item('spans', iid)
            axis = getattr(sp, 'axis', 'x')
            return tr('panel_span_x' if axis == 'x' else 'panel_span_y')
        if self._key.startswith('band:'):
            iid = self._key[len('band:'):]
            fills = getattr(self._tab.overrides, 'fills', None) or ()
            if any(f.id == iid for f in fills):
                return tr('panel_fill')
            return tr('panel_band')
        key = _TITLES.get(self._key)
        return tr(key) if key is not None else self._key

    def _doc(self):
        return self._tab.effective_document()

    def _series_y_column(self, sid):
        return self._item_y_column('series', sid)

    def _item_y_column(self, coll_name, iid):
        """Y column of the doc item ``iid`` in series/groups/categories."""
        tab = self._tab
        doc = self._doc()
        if doc is None or tab.plot is None:
            return None
        coll = doc.series if coll_name == 'series' \
            else getattr(doc, coll_name, ())
        for i, entry in enumerate(coll):
            if entry.id == iid and i < len(tab.plot.series):
                return getattr(tab.plot.series[i], 'y_column', None)
        return None

    # ── apply plumbing ────────────────────────────────────────────────

    def _apply_now(self, fn, after=None):
        self._tab.update_overrides(fn)
        self._refresh()
        if after is not None:
            after()

    def _refresh(self):
        for sync in self._syncs:
            sync()
        for is_set, btn in self._reset_buttons:
            btn.setEnabled(bool(is_set()))

    def _reset_element(self):
        y_col = None
        for prefix, coll in (('series:', 'series'), ('violin:', 'groups'),
                             ('hist:', 'groups'),
                             ('stack:', 'categories')):
            if self._key.startswith(prefix):
                y_col = self._item_y_column(
                    coll, self._key[len(prefix):])
        self._tab.update_overrides(
            lambda o: reset_element(o, self._key, y_col))
        self.close()

    # ── row helpers ───────────────────────────────────────────────────

    def _row(self, form, label, widget, *, is_set=None, reset=None,
             sync=None, reset_tip=None):
        """Add ``label: widget [reset]``; the reset button is enabled only
        while the value is overridden and restores the default."""
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(4)
        h.addWidget(widget, 1)
        if reset is not None:
            btn = QToolButton()
            btn.setIcon(self.icon('reset'))
            btn.setToolTip(reset_tip or tr('tip_reset_default'))
            btn.setAutoRaise(True)
            btn.clicked.connect(lambda: self._apply_now(reset))
            h.addWidget(btn)
            if is_set is not None:
                self._reset_buttons.append((is_set, btn))
        form.addRow(label, row)
        if sync is not None:
            self._syncs.append(sync)

    @staticmethod
    def _set_invalid(widget, bad):
        widget.setProperty('invalid', bad)
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    def _checkbox(self, label, checked, set_fn):
        cb = QCheckBox(label)
        cb.setChecked(bool(checked))
        cb.toggled.connect(
            lambda on: self._apply_now(lambda o: set_fn(o, on)))
        return cb

    def _style_icons(self, kind, codes):
        """Icon-only glyphs in the palette text colour."""
        color = self.palette().color(QPalette.ColorRole.WindowText)
        dpr = self.devicePixelRatioF()
        return [style_icon(kind, code, color, dpr) for code in codes]

    def _combo(self, labels, values, current, set_fn, icons=None):
        combo = QComboBox()
        for i, (label, value) in enumerate(zip(labels, values)):
            if icons is not None:
                combo.addItem(icons[i], '', value)
                combo.setItemData(i, label,
                                  Qt.ItemDataRole.ToolTipRole)
                combo.setItemData(i, label,
                                  Qt.ItemDataRole.AccessibleTextRole)
            else:
                combo.addItem(label, value)
        if icons is not None:
            combo.setIconSize(QSize(44, 14))
        combo.setCurrentIndex(
            values.index(current) if current in values else 0)
        combo.currentIndexChanged.connect(
            lambda idx: self._apply_now(
                lambda o: set_fn(o, combo.itemData(idx))))
        return combo

    def _spin(self, value, lo, hi, step=1.0, decimals=1):
        s = QDoubleSpinBox()
        s.setRange(lo, hi)
        s.setSingleStep(step)
        s.setDecimals(decimals)
        s.setKeyboardTracking(False)
        s.setValue(value)
        return s

    def _section(self, text, form=None):
        head = QLabel(text)
        head.setObjectName('plotElementPanelSection')
        (form or self._body).addRow(head)

    def _color_row(self, label, color, set_fn, reset_color, is_set=None,
                   form=None):
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(4)
        swatch = _Swatch(self.border, self)
        swatch.set_color(color)
        swatch._color_fn = lambda o, c: set_fn(o, c)
        h.addWidget(swatch)
        if reset_color is not None or is_set is not None:
            rst = QToolButton()
            rst.setIcon(self.icon('reset'))
            rst.setToolTip(tr('tip_reset_default'))
            rst.setAutoRaise(True)
            rst.clicked.connect(lambda: self._apply_now(
                lambda o: set_fn(o, reset_color)))
            h.addWidget(rst)
            if is_set is not None:
                self._reset_buttons.append((is_set, rst))
        h.addStretch(1)
        (form or self._body).addRow(label, row)
        return swatch

    def _subform(self, form, visible_fn):
        """Sub-form whose rows show/hide as a block on refresh."""
        widget = QWidget()
        sub = QFormLayout(widget)
        sub.setContentsMargins(0, 0, 0, 0)
        sub.setHorizontalSpacing(8)
        sub.setVerticalSpacing(6)
        form.addRow(widget)

        def sync():
            visible = bool(visible_fn())
            if widget.isVisibleTo(self) != visible:
                widget.setVisible(visible)
                # The floating panel only grows on its own; shrink it
                # back when a block folds away.
                if self.isVisible():
                    self.adjustSize()
        self._syncs.append(sync)
        sync()
        return widget, sub

    # ── style accessors (run inside update_overrides fns) ─────────────

    def _ensure_o(self, o, name, cls):
        obj = getattr(o.style, name)
        if obj is None:
            obj = cls()
            setattr(o.style, name, obj)
        return obj

    def _style_fn(self, name, cls):
        return lambda o: self._ensure_o(o, name, cls)

    def _text_editor(self, form, name, cls=TextStyle, *,
                     text_row=False, text_get=None, text_set=None,
                     default_text='', eff=None):
        """A synced TextStyleEditor for ``overrides.style.<name>``."""
        doc = self._doc()
        tab = self._tab
        get = self._style_fn(name, cls)
        default_size = (doc.title_size_pt if name == 'title'
                        else doc.font_size_pt)
        stored = lambda: getattr(tab.overrides.style, name)
        if eff is None:
            eff = stored
        editor = TextStyleEditor(
            self, get_style=get, eff_style=eff,
            text_row=text_row, text_get=text_get, text_set=text_set,
            default_text=default_text,
            default_family=doc.font_family,
            default_size=default_size)
        editor._stored = stored
        self._syncs.append(editor._sync_family)
        self._syncs.append(editor._sync_size)
        form.addRow(editor)
        return editor

    # ── per-element builders ──────────────────────────────────────────

    def _build(self, form):
        key = self._key
        if key == 'title':
            self._build_title(form)
        elif key in ('xlabel', 'ylabel'):
            self._build_axis_label(form, key)
        elif key in ('xticks', 'yticks'):
            axis = 'xaxis' if key == 'xticks' else 'yaxis'
            lim = 'xlim' if key == 'xticks' else 'ylim'
            doc = self._doc()
            self._build_axis(form, axis, lim,
                             categorical=bool(
                                 key == 'xticks'
                                 and doc is not None
                                 and doc.x_tick_labels))
            if key == 'xticks' and doc is not None:
                if doc.kind == 'violin':
                    self._build_group_labels(form, doc)
                elif doc.categories:
                    self._build_bar_labels(form, doc)
        elif key == 'legend':
            self._build_legend(form)
        elif key == 'frame':
            self._build_frame(form)
        elif key.startswith('series:'):
            self._build_series(form, key[7:])
        elif key.startswith('violin:'):
            self._build_violin_item(form, key[len('violin:'):])
        elif key.startswith('hist:'):
            self._build_hist_item(form, key[len('hist:'):])
        elif key.startswith('stack:'):
            self._build_stack_item(form, key[len('stack:'):])
        elif key.startswith('annotation:'):
            self._build_annotation(form, key[len('annotation:'):])
        elif key.startswith('bracket:'):
            self._build_bracket(form, key[len('bracket:'):])
        elif key.startswith('span:'):
            self._build_span(form, key[len('span:'):])
        elif key.startswith('band:'):
            self._build_band(form, key[len('band:'):])

    def _build_title(self, form):
        tab = self._tab
        doc = self._doc()
        editor = self._text_editor(
            form, 'title', TitleStyle, text_row=True,
            text_get=lambda: None,
            text_set=lambda o, t: None,
            eff=lambda: doc.style.title)
        # Title text is not an override — commit straight to the title
        # field on editingFinished so the two stay in sync, and drop the
        # spreadsheet-reset button (there is none for a title).
        e = editor.text_edit
        e.editingFinished.disconnect()
        e.setText(tab.plot_title)
        e.setPlaceholderText('')
        e.editingFinished.connect(
            lambda: tab.set_plot_title(e.text()))
        for b in e.parentWidget().findChildren(QToolButton):
            b.hide()

        current = (tab.overrides.style.title.align
                   if tab.overrides.style.title else 'center')
        align_row = QWidget()
        h = QHBoxLayout(align_row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(2)
        self._align_btns = {}
        for value, icon in (('left', 'align_left'),
                            ('center', 'align_center'),
                            ('right', 'align_right')):
            b = QToolButton()
            b.setIcon(self.icon(icon))
            b.setCheckable(True)
            b.setAutoRaise(True)
            b.setProperty('segmentedButton', True)
            b.setChecked(value == current)
            b.setToolTip(tr('tip_align_' + value))
            b.clicked.connect(lambda _c=False, v=value:
                              self._set_align(v))
            self._align_btns[value] = b
            h.addWidget(b)
        h.addStretch(1)
        self._body.addRow(tr('row_align'), align_row)

    def _set_align(self, value):
        for v, b in self._align_btns.items():
            b.blockSignals(True)
            b.setChecked(v == value)
            b.blockSignals(False)
        self._apply_now(lambda o: setattr(
            self._ensure_o(o, 'title', TitleStyle), 'align', value))

    def _build_axis_label(self, form, key):
        tab = self._tab
        base = ''
        if tab.plot is not None and tab.plot.series:
            base = (tab.plot.series[0].x_label if key == 'xlabel'
                    else tab.plot.series[0].y_label)
        doc = self._doc()
        self._text_editor(
            form, key, TextStyle, text_row=True,
            text_get=lambda: getattr(tab.overrides, key),
            text_set=lambda o, t: setattr(o, key, t or None),
            default_text=base,
            eff=lambda: getattr(doc.style, key))

    def _build_axis(self, form, style_name, lim_name, categorical):
        o = self._tab.overrides
        doc = self._doc()
        axis_stored = lambda: getattr(o.style, style_name)

        def get(xo):
            return self._ensure_o(xo, style_name, AxisStyle)

        def ticks(xo):
            a = get(xo)
            if a.ticks is None:
                a.ticks = TextStyle()
            return a.ticks

        def eff_axis():
            return axis_stored() or AxisStyle()

        self._section(tr('sec_labels'))
        editor = TextStyleEditor(
            self, get_style=ticks, eff_style=lambda: eff_axis().ticks,
            default_family=doc.font_family,
            default_size=doc.font_size_pt)
        editor._stored = lambda: eff_axis().ticks
        self._syncs += [editor._sync_family, editor._sync_size]
        form.addRow(editor)

        axis = eff_axis()
        rot = self._spin(axis.rotation, -90, 90, step=15)
        rot.valueChanged.connect(lambda v: self._apply_now(
            lambda xo: setattr(get(xo), 'rotation', v)))
        self._row(form, tr('row_rotation'), rot,
                  is_set=lambda: axis_stored() is not None
                  and axis_stored().rotation != 0,
                  reset=lambda xo: setattr(get(xo), 'rotation', 0.0),
                  sync=lambda: self._respin(rot, eff_axis().rotation))

        for label, field in ((tr('row_prefix'), 'prefix'),
                             (tr('row_suffix'), 'suffix')):
            e = QLineEdit(getattr(axis, field))
            e.editingFinished.connect(
                lambda f=field, w=e: self._apply_now(
                    lambda xo: setattr(get(xo), f, w.text())))
            self._row(form, label, e,
                      is_set=lambda f=field: axis_stored() is not None
                      and bool(getattr(axis_stored(), f)),
                      reset=lambda xo, f=field: setattr(get(xo), f, ''),
                      sync=lambda f=field, w=e: w.setText(
                          getattr(eff_axis(), f)))

        dec = QLineEdit('' if axis.decimals is None
                        else str(axis.decimals))
        dec.setPlaceholderText(tr('auto_placeholder'))
        dec.setValidator(QIntValidator(0, 10))
        dec.setMaximumWidth(90)

        def commit_dec():
            t = dec.text().strip()
            if not t:
                self._apply_now(
                    lambda xo: setattr(get(xo), 'decimals', None))
                return
            try:
                v = int(t)
            except ValueError:
                self._set_invalid(dec, True)
                return
            if not 0 <= v <= 10:
                self._set_invalid(dec, True)
                return
            self._set_invalid(dec, False)
            self._apply_now(
                lambda xo: setattr(get(xo), 'decimals', v))
        dec.editingFinished.connect(commit_dec)
        self._row(form, tr('row_decimals'), dec,
                  is_set=lambda: axis_stored() is not None
                  and axis_stored().decimals is not None,
                  reset=lambda xo: setattr(get(xo), 'decimals', None),
                  sync=lambda: dec.setText(
                      '' if eff_axis().decimals is None
                      else str(eff_axis().decimals)))

        self._section(tr('sec_ticks'))
        step = QLineEdit('' if axis.step is None else '%g' % axis.step)
        step.setPlaceholderText(tr('auto_placeholder'))
        step.setValidator(QDoubleValidator(1e-9, 1e12, 9))
        step.setMaximumWidth(90)
        step.setToolTip(tr('tip_tick_spacing'))

        def commit_step():
            t = step.text().strip()
            if not t:
                self._apply_now(
                    lambda xo: setattr(get(xo), 'step', None))
                return
            try:
                v = float(t)
            except ValueError:
                self._set_invalid(step, True)
                return
            if not (0 < v and v == v):
                self._set_invalid(step, True)
                return
            self._set_invalid(step, False)
            self._apply_now(lambda xo: setattr(get(xo), 'step', v))
        step.editingFinished.connect(commit_step)
        self._row(form, tr('row_tick_spacing'), step,
                  is_set=lambda: axis_stored() is not None
                  and axis_stored().step is not None,
                  reset=lambda xo: setattr(get(xo), 'step', None),
                  sync=lambda: step.setText(
                      '' if eff_axis().step is None
                      else '%g' % eff_axis().step))

        form.addRow(self._checkbox(
            tr('row_minor_ticks'), axis.minor,
            lambda xo, v: setattr(get(xo), 'minor', v)))
        form.addRow(tr('row_direction'), self._combo(
            [tr(_DIRECTION_KEYS[k]) for k in _DIRECTION_KEYS],
            list(_DIRECTION_KEYS),
            axis.direction,
            lambda xo, v: setattr(get(xo), 'direction', v)))
        length = self._spin(axis.length_pt, 0, 20)
        length.valueChanged.connect(lambda v: self._apply_now(
            lambda xo: setattr(get(xo), 'length_pt', v)))
        self._row(form, tr('row_tick_len'), length,
                  is_set=lambda: axis_stored() is not None
                  and axis_stored().length_pt != 3.5,
                  reset=lambda xo: setattr(get(xo), 'length_pt', 3.5),
                  sync=lambda: self._respin(length, eff_axis().length_pt))

        self._section(tr('sec_scale'))
        lim = getattr(o, lim_name)
        lo_e = QLineEdit('' if lim is None else '%g' % lim[0])
        hi_e = QLineEdit('' if lim is None else '%g' % lim[1])
        for e, placeholder in ((lo_e, tr('auto_placeholder')),
                               (hi_e, tr('auto_placeholder'))):
            e.setMaximumWidth(90)
            e.setPlaceholderText(placeholder)
        lo_e.editingFinished.connect(
            lambda: self._limits_changed(lo_e, hi_e, lim_name))
        hi_e.editingFinished.connect(
            lambda: self._limits_changed(lo_e, hi_e, lim_name))
        for label, e in ((tr('row_min'), lo_e),
                         (tr('row_max'), hi_e)):
            self._row(form, label, e,
                      is_set=lambda: getattr(o, lim_name) is not None,
                      reset=lambda xo: setattr(xo, lim_name, None),
                      sync=lambda w=e, i=(0 if e is lo_e else 1):
                      self._sync_lim(w, lim_name, i))
        if not categorical:
            form.addRow(self._checkbox(
                tr('row_log_scale'), axis.scale == 'log',
                lambda xo, v: setattr(get(xo), 'scale',
                                      'log' if v else 'linear')))
        form.addRow(self._checkbox(
            tr('row_reversed'), axis.reversed,
            lambda xo, v: setattr(get(xo), 'reversed', v)))

    def _sync_lim(self, widget, lim_name, i):
        lim = getattr(self._tab.overrides, lim_name)
        widget.setText('' if lim is None else '%g' % lim[i])
        self._set_invalid(widget, False)

    def _respin(self, widget, value):
        widget.blockSignals(True)
        widget.setValue(value)
        widget.blockSignals(False)

    def _limits_changed(self, lo_e, hi_e, lim_name):
        limits, error = parse_axis_limits(lo_e.text(), hi_e.text())
        for e in (lo_e, hi_e):
            self._set_invalid(e, error)
        if error:
            return
        self._apply_now(lambda o: setattr(o, lim_name, limits))

    def _build_series(self, form, sid):
        tab = self._tab
        y_col = self._series_y_column(sid)
        if y_col is None:
            note = QLabel(tr('panel_series_detached'))
            note.setWordWrap(True)
            form.addRow(note)
            return
        doc = self._doc()
        ds = next((s for s in doc.series if s.id == sid), None)

        def get(xo):
            s = xo.series.get(y_col)
            if s is None:
                s = SeriesOverride()
                xo.series[y_col] = s
            return s

        def so():
            return tab.overrides.series.get(y_col)

        e = QLineEdit((so().label if so() else None)
                      or (ds.label if ds else ''))
        e.setPlaceholderText(ds.label if ds else '')
        e.editingFinished.connect(lambda: self._apply_now(
            lambda o: setattr(get(o), 'label', e.text() or None)))
        self._row(form, tr('row_label'), e,
                  is_set=lambda: so() is not None
                  and so().label is not None,
                  reset=lambda o: setattr(get(o), 'label', None),
                  reset_tip=tr('tip_reset_text'),
                  sync=lambda: e.setText(
                      (so().label if so() and so().label is not None
                       else (ds.label if ds else ''))))

        swatch = self._color_row(
            tr('row_colour'),
            (so().color if so() else None) or (ds.color if ds
                                             else '#000000'),
            lambda o, c: setattr(get(o), 'color', c), None,
            is_set=lambda: so() is not None and so().color is not None)
        self._syncs.append(lambda: swatch.set_color(
            (so().color if so() and so().color is not None
             else (ds.color if ds else '#000000'))))

        lw = self._spin(
            (so().linewidth_pt if so() and so().linewidth_pt is not None
             else (ds.linewidth_pt if ds else 1.5)),
            0.1, 20, step=0.5)
        lw.valueChanged.connect(lambda v: self._apply_now(
            lambda o: setattr(get(o), 'linewidth_pt', v)))
        self._row(form, tr('row_line_width'), lw,
                  is_set=lambda: so() is not None
                  and so().linewidth_pt is not None,
                  reset=lambda o: setattr(get(o), 'linewidth_pt', None),
                  sync=lambda: self._respin(
                      lw, (so().linewidth_pt if so() and
                           so().linewidth_pt is not None
                           else (ds.linewidth_pt if ds else 1.5))))

        cur_ls = (so().linestyle if so() and so().linestyle is not None
                  else (ds.linestyle if ds else '-'))
        form.addRow(tr('row_line_style'), self._combo(
            [tr(_LINE_KEYS[k]) for k in LINESTYLES], list(LINESTYLES),
            cur_ls, lambda o, v: setattr(get(o), 'linestyle', v),
            icons=self._style_icons('line', LINESTYLES)))

        cur_mk = (so().marker if so() and so().marker is not None
                  else (ds.marker if ds else ''))
        form.addRow(tr('row_marker'), self._combo(
            [tr(_MARKER_KEYS[k]) for k in MARKERS], list(MARKERS),
            cur_mk, lambda o, v: setattr(get(o), 'marker', v),
            icons=self._style_icons('marker', MARKERS)))

        ms = self._spin(
            (so().markersize_pt if so() and so().markersize_pt is not None
             else (ds.markersize_pt if ds else 6.0)),
            0, 30)
        ms.valueChanged.connect(lambda v: self._apply_now(
            lambda o: setattr(get(o), 'markersize_pt', v)))
        self._row(form, tr('row_marker_size'), ms,
                  is_set=lambda: so() is not None
                  and so().markersize_pt is not None,
                  reset=lambda o: setattr(get(o), 'markersize_pt', None),
                  sync=lambda: self._respin(
                      ms, (so().markersize_pt if so() and
                           so().markersize_pt is not None
                           else (ds.markersize_pt if ds else 6.0))))

        if ds is not None and doc is not None and doc.kind == 'line' \
                and (ds.yerr is not None
                     or ds.yerr_minus is not None):
            cur_es = (so().error_style
                      if so() and so().error_style is not None
                      else ds.error_style)
            es_combo = self._combo(
                [tr('err_display_bars'), tr('err_display_band')],
                ['bars', 'band'], cur_es,
                lambda o, v: setattr(get(o), 'error_style', v))
            form.addRow(tr('row_error_display'), es_combo)

            ap = self._spin(
                (so().error_alpha
                 if so() and so().error_alpha is not None
                 else ds.error_alpha),
                0.05, 1.0, step=0.05, decimals=2)
            ap.valueChanged.connect(lambda v: self._apply_now(
                lambda o: setattr(get(o), 'error_alpha', v)))
            self._row(form, tr('row_band_opacity'), ap,
                      is_set=lambda: so() is not None
                      and so().error_alpha is not None,
                      reset=lambda o: setattr(get(o), 'error_alpha',
                                              None),
                      sync=lambda: self._respin(
                          ap, (so().error_alpha if so() and
                               so().error_alpha is not None
                               else ds.error_alpha)))
            last = form.rowCount() - 1
            ap_widgets = []
            for role in (QFormLayout.ItemRole.LabelRole,
                         QFormLayout.ItemRole.FieldRole):
                it = form.itemAt(last, role)
                if it is not None and it.widget() is not None:
                    ap_widgets.append(it.widget())

            def _err_vis():
                eff_es = (so().error_style
                          if so() and so().error_style is not None
                          else ds.error_style)
                for w in ap_widgets:
                    w.setVisible(eff_es == 'band')

            _err_vis()
            self._syncs.append(_err_vis)

        if doc is not None and doc.kind == 'ridgeline':
            self._build_ridgeline_section(form)

    def _build_ridgeline_section(self, form):
        """Ridgeline option rows bound to ``overrides.ridgeline``."""
        o = self._tab.overrides
        stored = lambda: o.ridgeline

        def get(xo):
            if xo.ridgeline is None:
                xo.ridgeline = RidgeOptions()
            return xo.ridgeline

        def eff():
            doc = self._doc()
            return (doc.ridgeline if doc is not None
                    and doc.ridgeline is not None else RidgeOptions())

        self._section(tr('sec_ridgeline'))
        off = QLineEdit('' if eff().offset is None
                        else '%g' % eff().offset)
        off.setPlaceholderText(tr('auto_placeholder'))
        off.setValidator(QDoubleValidator(1e-9, 1e12, 9))
        off.setMaximumWidth(90)

        def commit_off():
            t = off.text().strip()
            if not t:
                self._apply_now(
                    lambda xo: setattr(get(xo), 'offset', None))
                return
            try:
                v = float(t)
            except ValueError:
                self._set_invalid(off, True)
                return
            if not (0 < v and v == v):
                self._set_invalid(off, True)
                return
            self._set_invalid(off, False)
            self._apply_now(lambda xo: setattr(get(xo), 'offset', v))
        off.editingFinished.connect(commit_off)
        self._row(form, tr('row_offset'), off,
                  is_set=lambda: stored() is not None
                  and stored().offset is not None,
                  reset=lambda xo: setattr(get(xo), 'offset', None),
                  sync=lambda: off.setText(
                      '' if eff().offset is None
                      else '%g' % eff().offset))
        alpha = self._spin(eff().fill_alpha, 0.0, 1.0,
                           step=0.05, decimals=2)
        alpha.valueChanged.connect(lambda v: self._apply_now(
            lambda xo: setattr(get(xo), 'fill_alpha', v)))
        self._row(form, tr('row_fill_opacity'), alpha,
                  is_set=lambda: stored() is not None
                  and stored().fill_alpha != 0.22,
                  reset=lambda xo: setattr(get(xo), 'fill_alpha', 0.22),
                  sync=lambda: self._respin(alpha, eff().fill_alpha))
        form.addRow(self._checkbox(
            tr('row_reverse_order'), eff().reverse,
            lambda xo, v: setattr(get(xo), 'reverse', v)))
        sw = self._color_row(
            tr('row_baseline_colour'), eff().baseline_color,
            lambda xo, c: setattr(get(xo), 'baseline_color', c),
            '#444444',
            is_set=lambda: stored() is not None
            and stored().baseline_color != '#444444')
        self._syncs.append(
            lambda: sw.set_color(eff().baseline_color))
        bw = self._spin(eff().baseline_width_pt, 0, 10, step=0.1)
        bw.valueChanged.connect(lambda v: self._apply_now(
            lambda xo: setattr(get(xo), 'baseline_width_pt', v)))
        self._row(form, tr('row_baseline_width'), bw,
                  is_set=lambda: stored() is not None
                  and stored().baseline_width_pt != 0.6,
                  reset=lambda xo: setattr(get(xo),
                                           'baseline_width_pt', 0.6),
                  sync=lambda: self._respin(bw, eff().baseline_width_pt))
        form.addRow(self._checkbox(
            tr('row_show_labels'), eff().labels,
            lambda xo, v: setattr(get(xo), 'labels', v)))

    def _build_legend(self, form):
        o = self._tab.overrides
        doc = self._doc()
        leg_stored = lambda: o.style.legend

        def get(xo):
            return self._ensure_o(xo, 'legend', LegendStyle)

        def eff_leg():
            return leg_stored() or LegendStyle()

        def text_style(xo):
            l = get(xo)
            if l.text is None:
                l.text = TextStyle()
            return l.text

        leg = eff_leg()
        form.addRow(self._checkbox(
            tr('row_show_legend'),
            o.legend if o.legend is not None else doc.legend,
            lambda xo, v: setattr(xo, 'legend', v)))
        form.addRow(tr('row_location'), self._combo(
            [tr(_LOCATION_KEYS[l]) for l in LEGEND_LOCATIONS],
            list(LEGEND_LOCATIONS),
            o.legend_location or doc.legend_location,
            lambda xo, v: setattr(xo, 'legend_location', v)))
        form.addRow(self._checkbox(
            tr('row_frame'), leg.frame,
            lambda xo, v: setattr(get(xo), 'frame', v)))
        sw = self._color_row(
            tr('row_frame_colour'), leg.frame_color,
            lambda xo, c: setattr(get(xo), 'frame_color', c), '#cccccc',
            is_set=lambda: leg_stored() is not None
            and leg_stored().frame_color != '#cccccc')
        self._syncs.append(lambda: sw.set_color(eff_leg().frame_color))
        ncol = QSpinBox()
        ncol.setRange(1, 10)
        ncol.setKeyboardTracking(False)
        ncol.setValue(leg.ncols)
        ncol.valueChanged.connect(lambda v: self._apply_now(
            lambda xo: setattr(get(xo), 'ncols', v)))
        self._row(form, tr('row_columns'), ncol,
                  is_set=lambda: leg_stored() is not None
                  and leg_stored().ncols != 1,
                  reset=lambda xo: setattr(get(xo), 'ncols', 1),
                  sync=lambda: self._respin(ncol, eff_leg().ncols))

        editor = TextStyleEditor(
            self, get_style=text_style,
            eff_style=lambda: eff_leg().text,
            default_family=doc.font_family,
            default_size=doc.font_size_pt)
        editor._stored = lambda: eff_leg().text
        self._syncs += [editor._sync_family, editor._sync_size]
        form.addRow(editor)

    def _build_frame(self, form):
        o = self._tab.overrides
        doc = self._doc()
        fr_stored = lambda: o.style.frame
        gr_stored = lambda: o.style.grid

        def fget(xo):
            return self._ensure_o(xo, 'frame', FrameStyle)

        def gget(xo):
            return self._ensure_o(xo, 'grid', GridStyle)

        def eff_fr():
            return fr_stored() or FrameStyle()

        def eff_gr():
            return gr_stored() or GridStyle()

        frame = eff_fr()
        grid = eff_gr()

        self._section(tr('sec_frame'))
        sw = self._color_row(
            tr('row_colour'), frame.color,
            lambda xo, c: setattr(fget(xo), 'color', c), '#000000',
            is_set=lambda: fr_stored() is not None
            and fr_stored().color != '#000000')
        self._syncs.append(lambda: sw.set_color(eff_fr().color))
        fw = self._spin(frame.linewidth_pt, 0, 20, step=0.1)
        fw.valueChanged.connect(lambda v: self._apply_now(
            lambda xo: setattr(fget(xo), 'linewidth_pt', v)))
        self._row(form, tr('row_width'), fw,
                  is_set=lambda: fr_stored() is not None
                  and fr_stored().linewidth_pt != 0.8,
                  reset=lambda xo: setattr(fget(xo), 'linewidth_pt', 0.8),
                  sync=lambda: self._respin(fw, eff_fr().linewidth_pt))
        form.addRow(self._checkbox(
            tr('row_hide_top'), frame.hide_top,
            lambda xo, v: setattr(fget(xo), 'hide_top', v)))
        form.addRow(self._checkbox(
            tr('row_hide_right'), frame.hide_right,
            lambda xo, v: setattr(fget(xo), 'hide_right', v)))
        form.addRow(self._checkbox(
            tr('row_hide_left'), frame.hide_left,
            lambda xo, v: setattr(fget(xo), 'hide_left', v)))
        form.addRow(self._checkbox(
            tr('row_hide_bottom'), frame.hide_bottom,
            lambda xo, v: setattr(fget(xo), 'hide_bottom', v)))

        self._section(tr('sec_theme'))
        names = list(THEMES) + ['custom:' + n
                                for n in palettes.custom_theme_names()]
        labels = [palettes.theme_display_name(n) for n in names]
        dpr = self.devicePixelRatioF()
        theme_combo = QComboBox()
        for i, n in enumerate(names):
            theme_combo.addItem(palette_strip(n, dpr=dpr), labels[i], n)
        theme_combo.setIconSize(QSize(44, 14))
        theme_combo.setCurrentIndex(
            names.index(o.palette) if o.palette in names else 0)
        theme_combo.currentIndexChanged.connect(
            lambda idx: self._apply_now(
                lambda xo: setattr(xo, 'palette',
                                   theme_combo.itemData(idx))))
        theme_row = QWidget()
        th = QHBoxLayout(theme_row)
        th.setContentsMargins(0, 0, 0, 0)
        th.setSpacing(4)
        th.addWidget(theme_combo, 1)
        theme_edit = QToolButton()
        theme_edit.setText(tr('btn_edit'))
        theme_edit.setToolTip(tr('tip_edit_themes'))
        theme_edit.setAutoRaise(True)
        theme_edit.clicked.connect(self._open_theme_editor)
        th.addWidget(theme_edit)
        self._row(form, tr('row_theme'), theme_row,
                  is_set=lambda: o.palette is not None,
                  reset=lambda xo: setattr(xo, 'palette', None),
                  sync=lambda: theme_combo.setCurrentIndex(
                      names.index(o.palette)
                      if o.palette in names else 0))
        form.addRow(self._checkbox(
            tr('row_reverse_colours'), bool(o.palette_reverse),
            lambda xo, v: setattr(xo, 'palette_reverse',
                                  True if v else None)))

        self._section(tr('sec_grid'))
        form.addRow(self._checkbox(
            tr('row_show_grid'),
            o.grid if o.grid is not None else doc.grid,
            lambda xo, v: setattr(xo, 'grid', v)))
        form.addRow(tr('row_axis'), self._combo(
            [tr(_GRID_AXIS_KEYS[k]) for k in _GRID_AXIS_KEYS],
            list(_GRID_AXIS_KEYS),
            grid.axis, lambda xo, v: setattr(gget(xo), 'axis', v)))
        form.addRow(tr('row_lines'), self._combo(
            [tr(_GRID_WHICH_KEYS[k]) for k in _GRID_WHICH_KEYS],
            list(_GRID_WHICH_KEYS),
            grid.which, lambda xo, v: setattr(gget(xo), 'which', v)))
        sw = self._color_row(
            tr('row_grid_colour'), grid.color,
            lambda xo, c: setattr(gget(xo), 'color', c), '#b0b0b0',
            is_set=lambda: gr_stored() is not None
            and gr_stored().color != '#b0b0b0')
        self._syncs.append(lambda: sw.set_color(eff_gr().color))
        form.addRow(tr('row_style'), self._combo(
            [tr(_LINE_KEYS[k]) for k in _GRID_LINESTYLES],
            _GRID_LINESTYLES, grid.linestyle,
            lambda xo, v: setattr(gget(xo), 'linestyle', v),
            icons=self._style_icons('line', _GRID_LINESTYLES)))
        gw = self._spin(grid.linewidth_pt, 0.1, 20, step=0.1)
        gw.valueChanged.connect(lambda v: self._apply_now(
            lambda xo: setattr(gget(xo), 'linewidth_pt', v)))
        self._row(form, tr('row_width'), gw,
                  is_set=lambda: gr_stored() is not None
                  and gr_stored().linewidth_pt != 0.8,
                  reset=lambda xo: setattr(gget(xo), 'linewidth_pt', 0.8),
                  sync=lambda: self._respin(gw, eff_gr().linewidth_pt))
        alpha = self._spin(grid.alpha, 0.0, 1.0, step=0.05, decimals=2)
        alpha.valueChanged.connect(lambda v: self._apply_now(
            lambda xo: setattr(gget(xo), 'alpha', v)))
        self._row(form, tr('row_opacity'), alpha,
                  is_set=lambda: gr_stored() is not None
                  and gr_stored().alpha != 1.0,
                  reset=lambda xo: setattr(gget(xo), 'alpha', 1.0),
                  sync=lambda: self._respin(alpha, eff_gr().alpha))

        form.addRow(self._checkbox(
            tr('row_show_legend'),
            o.legend if o.legend is not None else doc.legend,
            lambda xo, v: setattr(xo, 'legend', v)))

    def _open_theme_editor(self):
        window = self._tab.window()
        opener = getattr(window, 'open_theme_editor', None)
        if opener is not None:
            opener()

    def _build_group_labels(self, form, doc):
        """Violin xticks panel: one editable label per group, writing
        ``overrides.series[y_column].label`` like the violin panel."""
        tab = self._tab
        items = tab.plot.series if tab.plot is not None else []
        self._section(tr('sec_group_labels'))
        for i, grp in enumerate(doc.groups):
            y_col = getattr(items[i], 'y_column', None) \
                if i < len(items) else None
            if y_col is None:
                continue
            sheet_label = getattr(items[i], 'label', '') or grp.label

            def get(xo, yc=y_col):
                s = xo.series.get(yc)
                if s is None:
                    s = SeriesOverride()
                    xo.series[yc] = s
                return s

            def stored(yc=y_col):
                s = tab.overrides.series.get(yc)
                return s.label if s else None

            e = QLineEdit(stored() or grp.label)
            e.setPlaceholderText(sheet_label)
            e.editingFinished.connect(
                lambda e=e, get=get: self._apply_now(
                    lambda o: setattr(get(o), 'label',
                                      e.text() or None)))
            self._row(form, tr('row_label_n', n=i + 1), e,
                      is_set=lambda st=stored: st() is not None,
                      reset=lambda o, get=get:
                          setattr(get(o), 'label', None),
                      reset_tip=tr('tip_reset_text'),
                      sync=lambda e=e, st=stored, g=grp:
                          e.setText(st() or g.label))

    def _build_bar_labels(self, form, doc):
        """Stacked xticks panel: one editable label per bar, writing
        ``overrides.bar_labels[index]``."""
        tab = self._tab
        entries = doc.x_tick_labels or []
        cats = tab.plot.series if tab.plot is not None else []
        base = getattr(cats[0], 'bar_labels', ()) if cats else ()
        self._section(tr('sec_bar_labels'))
        for x, text in entries:
            idx = int(x)
            sheet_label = base[idx] if idx < len(base) else str(idx)

            def current(i=idx, t=text):
                m = tab.overrides.bar_labels
                return m.get(i, t) if m else t

            def commit(e, i=idx):
                def fn(o):
                    m = dict(o.bar_labels or {})
                    if e.text():
                        m[i] = e.text()
                    else:
                        m.pop(i, None)
                    o.bar_labels = m or None
                self._apply_now(fn)

            e = QLineEdit(current())
            e.setPlaceholderText(sheet_label)
            e.editingFinished.connect(lambda e=e: commit(e))
            self._row(form, tr('row_label_n', n=idx + 1), e,
                      is_set=lambda i=idx:
                          bool(tab.overrides.bar_labels)
                          and i in tab.overrides.bar_labels,
                      reset=lambda o, i=idx:
                          setattr(o, 'bar_labels', {
                              k: v for k, v
                              in (o.bar_labels or {}).items()
                              if k != i} or None),
                      reset_tip=tr('tip_reset_text'),
                      sync=lambda e=e, c=current: e.setText(c()))

    # ── group-item panels (violin / stacked column) ──────────────────

    def _item_label_color(self, form, coll_name, iid):
        """Label + colour rows; returns (get, so, item) or None."""
        tab = self._tab
        y_col = self._item_y_column(coll_name, iid)
        doc = self._doc()
        if y_col is None:
            note = QLabel(tr('panel_series_detached'))
            note.setWordWrap(True)
            form.addRow(note)
            return None
        coll = getattr(doc, coll_name)
        item = next((x for x in coll if x.id == iid), None)

        def get(xo):
            s = xo.series.get(y_col)
            if s is None:
                s = SeriesOverride()
                xo.series[y_col] = s
            return s

        def so():
            return tab.overrides.series.get(y_col)

        e = QLineEdit((so().label if so() else None)
                      or (item.label if item else ''))
        e.setPlaceholderText(item.label if item else '')
        e.editingFinished.connect(lambda: self._apply_now(
            lambda o: setattr(get(o), 'label', e.text() or None)))
        self._row(form, tr('row_label'), e,
                  is_set=lambda: so() is not None
                  and so().label is not None,
                  reset=lambda o: setattr(get(o), 'label', None),
                  reset_tip=tr('tip_reset_text'),
                  sync=lambda: e.setText(
                      (so().label if so() and so().label is not None
                       else (item.label if item else ''))))

        swatch = self._color_row(
            tr('row_colour'),
            (so().color if so() else None) or (item.color if item
                                             else '#000000'),
            lambda o, c: setattr(get(o), 'color', c), None,
            is_set=lambda: so() is not None and so().color is not None)
        self._syncs.append(lambda: swatch.set_color(
            (so().color if so() and so().color is not None
             else (item.color if item else '#000000'))))
        return get, so, item

    def _bandwidth_row(self, form, get, eff, stored):
        """Bandwidth combo + custom-factor edit (violin/histogram)."""
        bw_row = QWidget()
        bh = QHBoxLayout(bw_row)
        bh.setContentsMargins(0, 0, 0, 0)
        bh.setSpacing(4)
        bw_combo = QComboBox()
        bw_combo.addItem(tr('bw_scott'), 'scott')
        bw_combo.addItem(tr('bw_silverman'), 'silverman')
        bw_combo.addItem(tr('bw_custom'), 'custom')
        bw_edit = QLineEdit()
        bw_edit.setValidator(QDoubleValidator(1e-9, 1e9, 9))
        bw_edit.setMaximumWidth(80)
        bw_edit.setPlaceholderText(tr('bw_factor'))
        bh.addWidget(bw_combo, 1)
        bh.addWidget(bw_edit)

        def bw_eff():
            return eff().bandwidth

        def bw_commit_edit():
            t = bw_edit.text().strip()
            try:
                v = float(t)
            except ValueError:
                self._set_invalid(bw_edit, True)
                return
            if not (0 < v and v == v):
                self._set_invalid(bw_edit, True)
                return
            self._set_invalid(bw_edit, False)
            self._apply_now(
                lambda xo: setattr(get(xo), 'bandwidth', v))

        def bw_combo_changed(idx):
            v = bw_combo.itemData(idx)
            if v == 'custom':
                if isinstance(bw_eff(), str):
                    bw_edit.setText('0.3')
                self._set_invalid(bw_edit, False)
                bw_commit_edit()
                return
            self._apply_now(
                lambda xo: setattr(get(xo), 'bandwidth', v))

        bw_combo.currentIndexChanged.connect(bw_combo_changed)
        bw_edit.editingFinished.connect(bw_commit_edit)

        def bw_sync():
            cur = bw_eff()
            bw_combo.blockSignals(True)
            if cur == 'scott':
                bw_combo.setCurrentIndex(0)
            elif cur == 'silverman':
                bw_combo.setCurrentIndex(1)
            else:
                bw_combo.setCurrentIndex(2)
                bw_edit.setText('%g' % cur if isinstance(
                    cur, (int, float)) else '')
            bw_combo.blockSignals(False)
            bw_edit.setVisible(bw_combo.currentIndex() == 2)

        bw_sync()
        self._syncs.append(bw_sync)
        self._row(form, tr('row_bandwidth'), bw_row,
                  is_set=lambda: stored() is not None
                  and stored().bandwidth != 'scott',
                  reset=lambda xo: setattr(get(xo), 'bandwidth',
                                           'scott'))

    def _build_violin_item(self, form, iid):
        o = self._tab.overrides
        res = self._item_label_color(form, 'groups', iid)
        if res is None:
            return
        item = res[2]
        stored = lambda: o.violin

        def get(xo):
            if xo.violin is None:
                # Seed from the effective options so body/box defaults
                # of box/column_points charts survive the first edit.
                xo.violin = copy.deepcopy(eff())
            return xo.violin

        def eff():
            doc = self._doc()
            return (doc.violin if doc is not None
                    and doc.violin is not None else ViolinOptions())

        def opt_row(spin, label, field, default, target=None):
            spin.valueChanged.connect(lambda v: self._apply_now(
                lambda xo: setattr(get(xo), field, v)))
            self._row(target or form, label, spin,
                      is_set=lambda: stored() is not None
                      and getattr(stored(), field) != default,
                      reset=lambda xo: setattr(get(xo), field, default),
                      sync=lambda: self._respin(
                          spin, getattr(eff(), field)))

        def sync_cb(cb, field):
            self._syncs.append(lambda: (
                cb.blockSignals(True),
                cb.setChecked(bool(getattr(eff(), field))),
                cb.blockSignals(False)))

        def eff_box_width():
            v = eff().box_width
            if v is not None:
                return v
            return 0.5 if eff().body == 'none' else 0.16

        def box_width_row(target):
            boxw = self._spin(eff_box_width(), 0.05, 1.0, step=0.05,
                              decimals=2)
            boxw.valueChanged.connect(lambda v: self._apply_now(
                lambda xo: setattr(get(xo), 'box_width', v)))
            self._row(target, tr('row_box_width'), boxw,
                      is_set=lambda: stored() is not None
                      and stored().box_width is not None,
                      reset=lambda xo: setattr(get(xo), 'box_width',
                                               None),
                      sync=lambda: self._respin(boxw, eff_box_width()))

        def edge_rows(target):
            opt_row(self._spin(eff().edge_width_pt, 0, 10, step=0.1),
                    tr('row_edge_width_none'), 'edge_width_pt', 1.0,
                    target)
            edge_fb = item.color if item is not None else '#000000'
            swe = self._color_row(
                tr('row_edge_colour'),
                eff().edge_color or edge_fb,
                lambda xo, c: setattr(get(xo), 'edge_color', c), None,
                is_set=lambda: stored() is not None
                and stored().edge_color is not None, form=target)
            self._syncs.append(lambda: swe.set_color(
                eff().edge_color or edge_fb))

        def point_rows(target, beside=True):
            if beside:
                target.addRow(self._checkbox(
                    tr('row_points_beside'), eff().points_beside,
                    lambda xo, v: setattr(get(xo), 'points_beside',
                                           v)))
            opt_row(self._spin(eff().point_size_pt, 0, 20, step=0.5),
                    tr('row_point_size'), 'point_size_pt', 6.0, target)
            opt_row(self._spin(eff().point_alpha, 0.0, 1.0, step=0.05),
                    tr('row_point_opacity'), 'point_alpha', 1.0, target)
            pedge_fb = item.color if item is not None else '#000000'
            spe = self._color_row(
                tr('row_point_edge_colour'),
                eff().point_edge_color or pedge_fb,
                lambda xo, c: setattr(get(xo), 'point_edge_color', c),
                None,
                is_set=lambda: stored() is not None
                and stored().point_edge_color is not None,
                form=target)
            self._syncs.append(lambda: spe.set_color(
                eff().point_edge_color or pedge_fb))
            opt_row(self._spin(eff().point_edge_width_pt, 0, 10,
                               step=0.1),
                    tr('row_point_edge_width'), 'point_edge_width_pt',
                    1.0, target)

        def fill_row(target):
            opt_row(self._spin(eff().fill_alpha, 0.0, 1.0, step=0.05),
                    tr('row_fill_opacity'), 'fill_alpha', 0.3, target)

        body = eff().body
        self._section(tr(violin_panel_keys(body)[1]))

        if body == 'bar':
            opt_row(self._spin(eff().bar_width, 0.05, 1.0, step=0.05,
                               decimals=2),
                    tr('row_bar_width'), 'bar_width', 0.6)
            self._row(form, tr('row_bar_error'),
                      self._combo(
                          [tr('err_sd'), tr('err_sem'),
                           tr('err_none')],
                          ['sd', 'sem', 'none'], eff().bar_error,
                          lambda xo, v: setattr(get(xo),
                                                'bar_error', v)))
            fill_row(form)
            edge_rows(form)
            cb_points = self._checkbox(
                tr('row_show_points'), eff().show_points,
                lambda xo, v: setattr(get(xo), 'show_points', v))
            sync_cb(cb_points, 'show_points')
            form.addRow(cb_points)
            _w, sub = self._subform(
                form, lambda: eff().show_points)
            point_rows(sub)
            cb_box = self._checkbox(
                tr('row_show_box'), eff().show_box,
                lambda xo, v: setattr(get(xo), 'show_box', v))
            sync_cb(cb_box, 'show_box')
            form.addRow(cb_box)
            _w, sub = self._subform(form, lambda: eff().show_box)
            box_width_row(sub)
            form.addRow(self._checkbox(
                tr('row_enhance_contrast'), eff().enhance_contrast,
                lambda xo, v: setattr(get(xo), 'enhance_contrast', v)))
        elif body == 'none':
            form.addRow(self._checkbox(
                tr('row_show_box'), eff().show_box,
                lambda xo, v: setattr(get(xo), 'show_box', v)))
            box_width_row(form)
            fill_row(form)
            cb_points = self._checkbox(
                tr('row_show_points'), eff().show_points,
                lambda xo, v: setattr(get(xo), 'show_points', v))
            sync_cb(cb_points, 'show_points')
            form.addRow(cb_points)
            _w, sub = self._subform(
                form, lambda: not eff().show_points)
            sub.addRow(self._checkbox(
                tr('row_show_outliers'), eff().show_outliers,
                lambda xo, v: setattr(get(xo), 'show_outliers', v)))
            _w, sub = self._subform(form, lambda: eff().show_points)
            point_rows(sub)
        else:
            form.addRow(self._checkbox(
                tr('row_show_box'), eff().show_box,
                lambda xo, v: setattr(get(xo), 'show_box', v)))
            form.addRow(self._checkbox(
                tr('row_show_points'), eff().show_points,
                lambda xo, v: setattr(get(xo), 'show_points', v)))
            form.addRow(self._checkbox(
                tr('row_points_beside'), eff().points_beside,
                lambda xo, v: setattr(get(xo), 'points_beside', v)))
            box_width_row(form)
            self._bandwidth_row(form, get, eff, stored)
            fill_row(form)
            edge_rows(form)
            point_rows(form, beside=False)
            form.addRow(self._checkbox(
                tr('row_enhance_contrast'), eff().enhance_contrast,
                lambda xo, v: setattr(get(xo), 'enhance_contrast',
                                       v)))

    def _build_hist_item(self, form, iid):
        o = self._tab.overrides
        res = self._item_label_color(form, 'groups', iid)
        if res is None:
            return
        item = res[2]
        stored = lambda: o.histogram

        def get(xo):
            if xo.histogram is None:
                xo.histogram = copy.deepcopy(eff())
            return xo.histogram

        def eff():
            doc = self._doc()
            return (doc.histogram if doc is not None
                    and doc.histogram is not None else HistOptions())

        def opt_row(spin, label, field, default):
            spin.valueChanged.connect(lambda v: self._apply_now(
                lambda xo: setattr(get(xo), field, v)))
            self._row(form, label, spin,
                      is_set=lambda: stored() is not None
                      and getattr(stored(), field) != default,
                      reset=lambda xo: setattr(get(xo), field, default),
                      sync=lambda: self._respin(
                          spin, getattr(eff(), field)))

        self._section(tr('sec_histogram'))
        # Bins/bin_width are exclusive: setting one clears the other.
        bins = QSpinBox()
        bins.setRange(0, 1000)
        bins.setSpecialValueText(tr('bins_auto'))
        bins.setKeyboardTracking(False)
        bins.setValue(eff().bins or 0)
        bins.valueChanged.connect(lambda v: self._apply_now(
            lambda xo: (setattr(get(xo), 'bins', int(v) or None),
                        setattr(get(xo), 'bin_width', None))))
        self._row(form, tr('row_bins'), bins,
                  is_set=lambda: stored() is not None
                  and stored().bins is not None,
                  reset=lambda xo: setattr(get(xo), 'bins', None),
                  sync=lambda: self._respin(bins, eff().bins or 0))
        binw = QLineEdit()
        binw.setValidator(QDoubleValidator(1e-9, 1e18, 9))
        binw.setText('' if eff().bin_width is None
                     else '%g' % eff().bin_width)

        def binw_commit():
            t = binw.text().strip()
            if not t:
                self._set_invalid(binw, False)
                self._apply_now(
                    lambda xo: setattr(get(xo), 'bin_width', None))
                return
            try:
                v = float(t)
            except ValueError:
                self._set_invalid(binw, True)
                return
            if not (0 < v and math.isfinite(v)):
                self._set_invalid(binw, True)
                return
            self._set_invalid(binw, False)
            self._apply_now(
                lambda xo: (setattr(get(xo), 'bin_width', v),
                            setattr(get(xo), 'bins', None)))

        binw.editingFinished.connect(binw_commit)
        self._row(form, tr('row_bin_width'), binw,
                  is_set=lambda: stored() is not None
                  and stored().bin_width is not None,
                  reset=lambda xo: setattr(get(xo), 'bin_width', None),
                  sync=lambda: binw.setText(
                      '' if eff().bin_width is None
                      else '%g' % eff().bin_width))
        form.addRow(self._checkbox(
            tr('row_density'), eff().density,
            lambda xo, v: setattr(get(xo), 'density', v)))
        self._row(form, tr('row_hist_style'),
                  self._combo([tr('hist_bars'), tr('hist_step')],
                              ['bars', 'step'], eff().style,
                              lambda xo, v: setattr(get(xo),
                                                    'style', v)))
        opt_row(self._spin(eff().fill_alpha, 0.0, 1.0, step=0.05),
                tr('row_fill_opacity'), 'fill_alpha', 0.5)
        opt_row(self._spin(eff().edge_width_pt, 0, 10, step=0.1),
                tr('row_edge_width_none'), 'edge_width_pt', 0.0)
        edge_fb = item.color if item is not None else '#000000'
        swe = self._color_row(
            tr('row_edge_colour'),
            eff().edge_color or edge_fb,
            lambda xo, c: setattr(get(xo), 'edge_color', c), None,
            is_set=lambda: stored() is not None
            and stored().edge_color is not None)
        self._syncs.append(lambda: swe.set_color(
            eff().edge_color or edge_fb))
        form.addRow(self._checkbox(
            tr('row_show_kde'), eff().kde,
            lambda xo, v: setattr(get(xo), 'kde', v)))
        self._bandwidth_row(form, get, eff, stored)

    def _build_stack_item(self, form, iid):
        o = self._tab.overrides
        if self._item_label_color(form, 'categories', iid) is None:
            return
        stored = lambda: o.stacked

        def get(xo):
            if xo.stacked is None:
                xo.stacked = StackOptions()
            return xo.stacked

        def eff():
            doc = self._doc()
            return (doc.stacked if doc is not None
                    and doc.stacked is not None else StackOptions())

        def opt_row(spin, label, field, default):
            spin.valueChanged.connect(lambda v: self._apply_now(
                lambda xo: setattr(get(xo), field, v)))
            self._row(form, label, spin,
                      is_set=lambda: stored() is not None
                      and getattr(stored(), field) != default,
                      reset=lambda xo: setattr(get(xo), field, default),
                      sync=lambda: self._respin(
                          spin, getattr(eff(), field)))

        self._section(tr('sec_columns'))
        opt_row(self._spin(eff().bar_width, 0.05, 1.0, step=0.05,
                           decimals=2),
                tr('row_bar_width'), 'bar_width', 0.8)
        form.addRow(self._checkbox(
            tr('row_show_values'), eff().show_values,
            lambda xo, v: setattr(get(xo), 'show_values', v)))
        if not eff().grouped:
            opt_row(self._spin(eff().value_threshold, 0, 100, step=1),
                    tr('row_value_threshold'), 'value_threshold', 5.0)
        dec = QSpinBox()
        dec.setRange(0, 4)
        dec.setKeyboardTracking(False)
        dec.setValue(eff().value_decimals)
        dec.valueChanged.connect(lambda v: self._apply_now(
            lambda xo: setattr(get(xo), 'value_decimals', int(v))))
        self._row(form, tr('row_decimals'), dec,
                  is_set=lambda: stored() is not None
                  and stored().value_decimals != 1,
                  reset=lambda xo: setattr(get(xo), 'value_decimals', 1),
                  sync=lambda: self._respin(dec, eff().value_decimals))
        sw = self._color_row(
            tr('row_value_colour'), eff().value_color,
            lambda xo, c: setattr(get(xo), 'value_color', c),
            '#ffffff',
            is_set=lambda: stored() is not None
            and stored().value_color != '#ffffff')
        self._syncs.append(lambda: sw.set_color(eff().value_color))
        form.addRow(self._checkbox(
            tr('row_bold_values'), eff().value_bold,
            lambda xo, v: setattr(get(xo), 'value_bold', v)))
        doc = self._doc()
        vs = self._spin(
            eff().value_size_pt if eff().value_size_pt is not None
            else doc.font_size_pt * 6 / 7, 1, 72)
        vs.valueChanged.connect(lambda v: self._apply_now(
            lambda xo: setattr(get(xo), 'value_size_pt', v)))
        self._row(form, tr('row_value_size'), vs,
                  is_set=lambda: stored() is not None
                  and stored().value_size_pt is not None,
                  reset=lambda xo: setattr(get(xo), 'value_size_pt',
                                           None),
                  sync=lambda: self._respin(
                      vs, eff().value_size_pt
                      if eff().value_size_pt is not None
                      else doc.font_size_pt * 6 / 7))
        sw2 = self._color_row(
            tr('row_edge_colour'), eff().edge_color,
            lambda xo, c: setattr(get(xo), 'edge_color', c),
            '#ffffff',
            is_set=lambda: stored() is not None
            and stored().edge_color != '#ffffff')
        self._syncs.append(lambda: sw2.set_color(eff().edge_color))
        opt_row(self._spin(eff().edge_width_pt, 0, 10, step=0.1),
                tr('row_edge_width'), 'edge_width_pt', 0.0)

    # ── annotation / bracket panels ──────────────────────────────────

    def _lift_content(self, o, name):
        """Ensure ``o.<name>`` mirrors the document's list; return it."""
        items = getattr(o, name)
        if items is None:
            doc = self._doc()
            items = [copy.copy(a)
                     for a in getattr(doc, name, None) or ()]
            setattr(o, name, items)
        return items

    def _content_item(self, name, iid):
        items = getattr(self._tab.overrides, name) \
            or getattr(self._doc(), name, None) or ()
        return next((x for x in items if x.id == iid), None)

    def _build_annotation(self, form, aid):
        ann = self._content_item('annotations', aid)
        if ann is None:
            form.addRow(QLabel(tr('panel_series_detached')))
            return

        def get(xo):
            items = self._lift_content(xo, 'annotations')
            return next(x for x in items if x.id == aid)

        e = QLineEdit(ann.text)
        e.editingFinished.connect(lambda: self._apply_now(
            lambda o: setattr(get(o), 'text', e.text() or ann.text)))
        form.addRow(tr('row_text'), e)

        anchors = list(ANNOTATION_ANCHORS)
        pos_labels = [tr(_ANCHOR_KEYS[a]) for a in anchors]
        pos_values = anchors
        pos_current = ann.anchor
        if ann.x is not None and ann.y is not None:
            pos_labels = pos_labels + [tr('anchor_free')]
            pos_values = anchors + ['free']
            pos_current = 'free'

        def set_pos(o, v):
            a = get(o)
            if v == 'free':
                return
            a.anchor = v
            a.x = None
            a.y = None

        form.addRow(tr('row_position'), self._combo(
            pos_labels, pos_values, pos_current, set_pos))

        def style_get(o):
            a = get(o)
            if a.style is None:
                a.style = TextStyle()
            return a.style

        doc = self._doc()
        editor = TextStyleEditor(
            self, get_style=style_get,
            eff_style=lambda: ann.style or TextStyle(),
            default_family=doc.font_family,
            default_size=doc.font_size_pt)
        editor._stored = lambda: (self._content_item(
            'annotations', aid) or ann).style
        self._syncs += [editor._sync_family, editor._sync_size]
        form.addRow(editor)

        form.addRow(self._checkbox(
            tr('row_box'), ann.box,
            lambda o, v: setattr(get(o), 'box', v)))

        delete = QPushButton(tr('btn_delete'))
        delete.setObjectName('plotElementPanelDelete')
        delete.clicked.connect(lambda: self._apply_now(
            lambda o: setattr(o, 'annotations', [
                a for a in self._lift_content(o, 'annotations')
                if a.id != aid] or None),
            after=self.close))
        form.addRow(delete)

    def _build_bracket(self, form, bid):
        bracket = self._content_item('brackets', bid)
        if bracket is None:
            form.addRow(QLabel(tr('panel_series_detached')))
            return
        doc = self._doc()
        items = doc.groups or doc.categories
        labels = [it.label or str(i) for i, it in enumerate(items)]

        def get(xo):
            lst = self._lift_content(xo, 'brackets')
            return next(x for x in lst if x.id == bid)

        form.addRow(tr('row_from'), self._combo(
            labels, list(range(len(items))), int(bracket.a),
            lambda o, v: setattr(get(o), 'a', float(v))))
        form.addRow(tr('row_to'), self._combo(
            labels, list(range(len(items))), int(bracket.b),
            lambda o, v: setattr(get(o), 'b', float(v))))

        e = QLineEdit(bracket.text)
        e.editingFinished.connect(lambda: self._apply_now(
            lambda o: setattr(get(o), 'text',
                              e.text() or bracket.text)))
        form.addRow(tr('row_text'), e)

        off = self._spin(bracket.offset, 0.0, 1.0, step=0.01,
                         decimals=2)
        off.valueChanged.connect(lambda v: self._apply_now(
            lambda o: setattr(get(o), 'offset', v)))
        form.addRow(tr('row_offset'), off)

        def style_get(o):
            b = get(o)
            if b.style is None:
                b.style = TextStyle()
            return b.style

        editor = TextStyleEditor(
            self, get_style=style_get,
            eff_style=lambda: bracket.style or TextStyle(),
            default_family=doc.font_family,
            default_size=8.0)
        editor._stored = lambda: (self._content_item(
            'brackets', bid) or bracket).style
        self._syncs += [editor._sync_family, editor._sync_size]
        form.addRow(editor)

        delete = QPushButton(tr('btn_delete'))
        delete.setObjectName('plotElementPanelDelete')
        delete.clicked.connect(lambda: self._apply_now(
            lambda o: setattr(o, 'brackets', [
                b for b in self._lift_content(o, 'brackets')
                if b.id != bid] or None),
            after=self.close))
        form.addRow(delete)

    # ── spans / fills (shaded areas) ──────────────────────────────────

    @staticmethod
    def _split_alpha(hex_color):
        """'#rrggbbaa' → ('#rrggbb', alpha 0..1); opaque otherwise."""
        if isinstance(hex_color, str) and len(hex_color) == 9:
            return hex_color[:7], int(hex_color[7:9], 16) / 255.0
        return hex_color or '#7f7f7f', 1.0

    @staticmethod
    def _join_alpha(rgb, alpha):
        return (rgb or '#7f7f7f') + '%02x' % max(
            0, min(255, int(round(alpha * 255))))

    def _area_rows(self, form, get, item, coll_name, iid):
        """Colour/Opacity/Label/Delete rows shared by spans and bands."""
        rgb, alpha = self._split_alpha(item.color)

        def set_color(o, c):
            # Read the live alpha so a colour pick never reverts a
            # later Opacity change.
            get(o).color = self._join_alpha(
                c, self._split_alpha(get(o).color)[1])

        self._color_row(tr('row_colour'), rgb, set_color, None)
        op = self._spin(alpha, 0.05, 1.0, step=0.05, decimals=2)
        op.valueChanged.connect(lambda v: self._apply_now(
            lambda o: setattr(get(o), 'color', self._join_alpha(
                self._split_alpha(get(o).color)[0], v))))
        form.addRow(tr('row_opacity'), op)

        e = QLineEdit(item.label)
        e.setPlaceholderText(tr('auto_placeholder'))
        e.editingFinished.connect(lambda: self._apply_now(
            lambda o: setattr(get(o), 'label', e.text())))
        form.addRow(tr('row_label'), e)

        delete = QPushButton(tr('btn_delete'))
        delete.setObjectName('plotElementPanelDelete')

        def do_delete(o):
            if coll_name == 'fills':
                o.fills = [f for f in (o.fills or ())
                           if f.id != iid] or None
            else:
                items = self._lift_bands(o) if coll_name == 'bands' \
                    else self._lift_content(o, coll_name)
                setattr(o, coll_name, [
                    x for x in items if x.id != iid] or None)
        delete.clicked.connect(
            lambda: self._apply_now(do_delete, after=self.close))
        form.addRow(delete)

    def _num_field(self, form, label, value, apply_fn,
                   placeholder=None):
        """An optional numeric QLineEdit committing on editingFinished;
        ``apply_fn`` gets the parsed value (``None`` when blank)."""
        e = QLineEdit('' if value is None else '%g' % value)
        e.setPlaceholderText(placeholder or tr('auto_placeholder'))
        e.setMaximumWidth(90)

        def commit():
            t = e.text().strip()
            if not t:
                self._set_invalid(e, False)
                apply_fn(None)
                return
            try:
                v = float(t)
            except ValueError:
                self._set_invalid(e, True)
                return
            if not math.isfinite(v):
                self._set_invalid(e, True)
                return
            self._set_invalid(e, False)
            apply_fn(v)
        e.editingFinished.connect(commit)
        form.addRow(label, e)
        return e

    def _lift_bands(self, o):
        """``o.bands`` mirroring only the document's *static* bands —
        bands computed from ``o.fills`` are never lifted (they would
        duplicate on the next ``effective_document``)."""
        items = o.bands
        if items is None:
            items = [copy.copy(b)
                     for b in static_bands(self._doc(), o)]
            o.bands = items
        return items

    def _build_span(self, form, sid):
        sp = self._content_item('spans', sid)
        if sp is None:
            form.addRow(QLabel(tr('panel_series_detached')))
            return

        def get(o):
            items = self._lift_content(o, 'spans')
            return next(x for x in items if x.id == sid)

        lo = self._spin(sp.lo, -1e9, 1e9, decimals=6)
        hi = self._spin(sp.hi, -1e9, 1e9, decimals=6)

        def commit_span(o):
            # An inverted range is normalised (sorted) instead of
            # writing an invalid span.
            get(o).lo, get(o).hi = sorted(
                (lo.value(), hi.value()))
        for w in (lo, hi):
            w.valueChanged.connect(lambda _v: self._apply_now(
                commit_span, after=self._respan))
        form.addRow(tr('row_from'), lo)
        form.addRow(tr('row_to'), hi)
        self._span_widgets = (sid, lo, hi)
        self._area_rows(form, get, sp, 'spans', sid)

    def _respan(self):
        sid, lo, hi = self._span_widgets
        cur = self._content_item('spans', sid)
        if cur is not None:
            self._respin(lo, cur.lo)
            self._respin(hi, cur.hi)

    def _build_band(self, form, bid):
        tab = self._tab
        fill = next((f for f in (tab.overrides.fills or ())
                     if f.id == bid), None)
        if fill is not None:
            self._build_fill(form, fill)
            return
        band = self._content_item('bands', bid)
        if band is None:
            form.addRow(QLabel(tr('panel_series_detached')))
            return

        def get(o):
            items = self._lift_bands(o)
            return next(x for x in items if x.id == bid)

        self._area_rows(form, get, band, 'bands', bid)

    def _build_fill(self, form, fill):
        fid = fill.id

        def get(o):
            items = self._lift_content(o, 'fills')
            return next(x for x in items if x.id == fid)

        def set_field(field, value, widget=None):
            # Never apply an invalid fill: validate the candidate with
            # the strict parser first (covers Series A == B, x_min >=
            # x_max, a 'between' fill losing its second series).
            from .fills import CurveFill
            cur = self._content_item('fills', fid)
            cand = copy.copy(cur)
            setattr(cand, field, value)
            try:
                CurveFill.from_dict(cand.to_dict())
            except Exception:
                if widget is not None:
                    self._set_invalid(widget, True)
                return
            if widget is not None:
                self._set_invalid(widget, False)
            self._apply_now(
                lambda o: setattr(get(o), field, value))

        def series_combo(label, field, current):
            tab = self._tab
            items = tab.plot.series if tab.plot is not None else []
            pairs = [(s.label or s.y_label or str(i),
                      getattr(s, 'y_column', None))
                     for i, s in enumerate(items)]
            pairs = [(l, v) for l, v in pairs if v is not None]
            if not pairs:
                return
            combo = QComboBox()
            for l, v in pairs:
                combo.addItem(l, v)
            if current in [v for _l, v in pairs]:
                combo.setCurrentIndex(
                    [v for _l, v in pairs].index(current))
            combo.currentIndexChanged.connect(
                lambda idx, c=combo, f=field:
                set_field(f, c.itemData(idx), c))
            form.addRow(label, combo)

        series_combo(tr('row_series_a'), 'a', fill.a)
        if fill.kind == 'between':
            series_combo(tr('row_series_b'), 'b', fill.b)
        if fill.kind == 'under':
            self._num_field(form, tr('row_baseline'), fill.baseline,
                            lambda v: self._apply_now(
                                lambda o: setattr(
                                    get(o), 'baseline',
                                    0.0 if v is None else v)))
        e_lo = self._num_field(form, tr('row_x_from'), fill.x_min,
                               lambda v: set_field('x_min', v, e_lo))
        e_hi = self._num_field(form, tr('row_x_to'), fill.x_max,
                               lambda v: set_field('x_max', v, e_hi))
        self._area_rows(form, get, fill, 'fills', fid)
