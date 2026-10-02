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

from PyQt6.QtCore import QEvent, QObject, QPoint, Qt
from PyQt6.QtGui import QColor, QDoubleValidator, QGuiApplication, \
    QIntValidator, QPalette
from PyQt6.QtWidgets import (QApplication, QCheckBox, QColorDialog,
                             QComboBox, QCompleter, QDoubleSpinBox,
                             QFormLayout, QFrame, QHBoxLayout, QLabel,
                             QLineEdit, QPushButton, QSpinBox,
                             QToolButton, QVBoxLayout, QWidget)

from src.app import theme as app_theme

from . import render
from .chrome import element_panel_stylesheet, themed_icon
from .i18n import tr
from .document import (LEGEND_LOCATIONS, LINESTYLES, MARKERS,
                       AxisStyle, FrameStyle, GridStyle, LegendStyle,
                       TextStyle, TitleStyle)
from .overrides import (SeriesOverride, parse_axis_limits,
                        reset_element)

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

_TITLES = {'title': 'panel_title', 'xlabel': 'panel_xlabel',
           'ylabel': 'panel_ylabel', 'xticks': 'panel_xticks',
           'yticks': 'panel_yticks', 'legend': 'panel_legend',
           'frame': 'panel_frame'}


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
        key = _TITLES.get(self._key)
        return tr(key) if key is not None else self._key

    def _doc(self):
        return self._tab.effective_document()

    def _series_y_column(self, sid):
        tab = self._tab
        doc = self._doc()
        if doc is None or tab.plot is None:
            return None
        for i, s in enumerate(doc.series):
            if s.id == sid:
                return tab.plot.series[i].y_column
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
        y_col = self._series_y_column(self._key[7:]) \
            if self._key.startswith('series:') else None
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

    def _combo(self, labels, values, current, set_fn):
        combo = QComboBox()
        for label, value in zip(labels, values):
            combo.addItem(label, value)
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

    def _section(self, text):
        head = QLabel(text)
        head.setObjectName('plotElementPanelSection')
        self._body.addRow(head)

    def _color_row(self, label, color, set_fn, reset_color, is_set=None):
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
        self._body.addRow(label, row)
        return swatch

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
        elif key == 'legend':
            self._build_legend(form)
        elif key == 'frame':
            self._build_frame(form)
        elif key.startswith('series:'):
            self._build_series(form, key[7:])

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
                  and axis_stored().length_pt != 3.0,
                  reset=lambda xo: setattr(get(xo), 'length_pt', 3.0),
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
            cur_ls, lambda o, v: setattr(get(o), 'linestyle', v)))

        cur_mk = (so().marker if so() and so().marker is not None
                  else (ds.marker if ds else ''))
        form.addRow(tr('row_marker'), self._combo(
            [tr(_MARKER_KEYS[k]) for k in MARKERS], list(MARKERS),
            cur_mk, lambda o, v: setattr(get(o), 'marker', v)))

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
            lambda xo, v: setattr(gget(xo), 'linestyle', v)))
        gw = self._spin(grid.linewidth_pt, 0.1, 20, step=0.1)
        gw.valueChanged.connect(lambda v: self._apply_now(
            lambda xo: setattr(gget(xo), 'linewidth_pt', v)))
        self._row(form, tr('row_width'), gw,
                  is_set=lambda: gr_stored() is not None
                  and gr_stored().linewidth_pt != 0.5,
                  reset=lambda xo: setattr(gget(xo), 'linewidth_pt', 0.5),
                  sync=lambda: self._respin(gw, eff_gr().linewidth_pt))
        alpha = self._spin(grid.alpha, 0.0, 1.0, step=0.05, decimals=2)
        alpha.valueChanged.connect(lambda v: self._apply_now(
            lambda xo: setattr(gget(xo), 'alpha', v)))
        self._row(form, tr('row_opacity'), alpha,
                  is_set=lambda: gr_stored() is not None
                  and gr_stored().alpha != 0.4,
                  reset=lambda xo: setattr(gget(xo), 'alpha', 0.4),
                  sync=lambda: self._respin(alpha, eff_gr().alpha))

        form.addRow(self._checkbox(
            tr('row_show_legend'),
            o.legend if o.legend is not None else doc.legend,
            lambda xo, v: setattr(xo, 'legend', v)))
