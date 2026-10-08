"""Per-tab worksheet + plot canvas for the Plot Editor."""

from __future__ import annotations

import copy
import os
from dataclasses import dataclass

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QInputDialog, QMenu, QMessageBox,
                             QSplitter, QToolButton, QVBoxLayout,
                             QWidget)

from . import presets
from .i18n import tr
from .overrides import (PlotOverrides, assign_palette,
                        assign_palette_reverse, effective_document,
                        hold_baked_colours, overrides_from_document,
                        remap_series_keys, record_overrides_edit,
                        static_bands)
from .plot_canvas import PlotCanvas
from .export import CHART_KIND
from .plot_data import (PlotSelectionError, build_categories,
                        build_groups, build_series)
from .plot_file import (PlotFileError, chart_from_document,
                        items_from_document, save_plot_file)
from ilmplot.document import PlotDocumentError
from .figure_size import FigureSize
from ilmplot.render import element_regions, render_document
from .chrome import reset_all_stylesheet, themed_icon
from .title_field import PlotTitleField
from .worksheet import Worksheet
from .worksheet_view import WorksheetView

_SUFFIX = '.ilmplot.svg'


def _build_items(worksheet, columns, chart_key):
    """Series/Group/Category items for ``chart_key`` from the sheet."""
    kind = CHART_KIND.get(chart_key, ('line', None))[0]
    if kind in ('violin', 'histogram'):
        return build_groups(worksheet, columns)
    if kind == 'stacked_column':
        return build_categories(worksheet, columns)
    return build_series(worksheet, columns)


@dataclass
class PlotState:
    series: list   # Series / Group / Category items for the chart kind
    chart_key: 'str | None'
    plot_columns: tuple
    document: object = None
    # True when ``document`` came from a file with no worksheet node and
    # the plot hasn't been regenerated since — it stays the render base
    # so legacy colours/settings survive.
    legacy_base: bool = False


def _shift_columns(columns, event):
    """Remap a column tuple for insert/remove events (same rule as
    ``remap_series_keys``)."""
    name, at, count = event[0], event[1], event[2]
    out = []
    for c in columns:
        if name == 'columns_inserted':
            out.append(c + count if c >= at else c)
        elif at <= c < at + count:
            continue
        else:
            out.append(c - count if c >= at + count else c)
    return tuple(out)


class PlotTab(QSplitter):
    """One editor tab: worksheet (left) and zoomable plot canvas (right)."""

    changed = pyqtSignal()

    def __init__(self, theme, scale=1.0, worksheet=None, parent=None,
                 preset_store=None, open_style_manager=None):
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.setObjectName('plotWorkspace')
        self.setChildrenCollapsible(False)
        self.theme = theme
        self.scale = scale
        self.preset_store = preset_store
        self._open_style_manager_cb = open_style_manager
        self.worksheet = worksheet if worksheet is not None else Worksheet()
        self.worksheet_view = WorksheetView(self.worksheet, theme, scale)
        left = QWidget()
        left.setObjectName('plotLeftArea')
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)
        left_layout.addWidget(self.worksheet_view)
        self.plot_canvas = PlotCanvas(theme)
        self.title_field = PlotTitleField(theme, scale)
        right = QWidget()
        right.setObjectName('plotRightArea')
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        right_layout.addWidget(self.title_field)
        right_layout.addWidget(self.plot_canvas)
        self.addWidget(left)
        self.addWidget(right)
        # Overall "Reset formatting" overlay: bottom-right of the plot
        # area, positioned relative to the window (not the scene).
        self._right_area = right
        self.reset_all = QToolButton(right)
        self.reset_all.setObjectName('plotResetAll')
        self.reset_all.setIcon(themed_icon('reset', theme, 'text_sec'))
        self.reset_all.setText(tr('reset_all'))
        self.reset_all.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.reset_all.setStyleSheet(reset_all_stylesheet(theme, scale))
        self.reset_all.setVisible(False)
        self.reset_all.clicked.connect(self._reset_all_formatting)
        # "Style" preset picker directly left of the reset button.
        self.style_presets = QToolButton(right)
        self.style_presets.setObjectName('plotStylePresets')
        self.style_presets.setIcon(themed_icon('style', theme,
                                               'text_sec'))
        self.style_presets.setText(tr('btn_style'))
        self.style_presets.setToolTip(tr('tip_style_presets'))
        self.style_presets.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.style_presets.setPopupMode(
            QToolButton.ToolButtonPopupMode.InstantPopup)
        self.style_presets.setStyleSheet(
            reset_all_stylesheet(theme, scale))
        self.style_presets.setVisible(False)
        self._preset_menu = QMenu(self.style_presets)
        self._preset_menu.aboutToShow.connect(
            self._rebuild_preset_menu)
        self.style_presets.setMenu(self._preset_menu)
        # "Size" figure-size dialog button, left of the Style button.
        self.figure_size_button = QToolButton(right)
        self.figure_size_button.setObjectName('plotFigureSize')
        self.figure_size_button.setText(tr('btn_figure_size'))
        self.figure_size_button.setToolTip(tr('tip_figure_size'))
        self.figure_size_button.setAccessibleName(
            tr('act_figure_size'))
        self.figure_size_button.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.figure_size_button.setStyleSheet(
            reset_all_stylesheet(theme, scale))
        self.figure_size_button.setVisible(False)
        self.figure_size_button.clicked.connect(self.edit_figure_size)
        right.installEventFilter(self)
        self.changed.connect(self._update_reset_all)
        # Dropped files belong to the window: children must not swallow
        # them (QGraphicsView/QTableView accept drops by default).
        for w in (self.plot_canvas, self.worksheet_view,
                  getattr(self.worksheet_view, '_labels', None)):
            if w is not None:
                w.setAcceptDrops(False)
                if w.viewport() is not None:
                    w.viewport().setAcceptDrops(False)
        self.path = None
        self.title = tr('untitled', n=0)
        self.dirty = False
        self.plot = None
        self.plot_title = ''
        self.overrides = PlotOverrides()
        self.figure_size = FigureSize()
        self._figure_size_locked = False
        self.regions = None
        self.title_field.title_changed.connect(self._on_title_changed)
        self.plot_canvas.element_activated.connect(self._open_element_panel)
        self.plot_canvas.context_requested.connect(
            self._on_canvas_context)
        self.plot_canvas.element_moved.connect(self._on_element_moved)
        self.plot_canvas.element_delete_requested.connect(
            self._delete_element)
        self.worksheet.add_listener(self._on_worksheet_event)

    def _on_title_changed(self, text):
        self.set_plot_title(text)

    def set_plot_title(self, text):
        """Update the title (from the field or the element panel).

        Undoable like worksheet edits: one 'Edit Title' history entry
        per commit; unchanged text records nothing.
        """
        if text == self.plot_title:
            return
        old = self.plot_title

        def _set(title):
            self.plot_title = title
            if self.title_field.title() != title:
                self.title_field.set_title(title)
            self._render_preview()
        self.worksheet.record_external_edit(
            'Edit Title',
            apply=lambda: _set(text), revert=lambda: _set(old))
        self.dirty = True
        self.changed.emit()

    def _open_element_panel(self, key, global_pos):
        from .element_panel import ElementPanel
        ElementPanel.open_for(self, key, global_pos)

    def effective_document(self):
        """The styled ``PlotDocument`` for preview/save/export, or None."""
        if self.plot is None:
            return None
        base = self.plot.document if self.plot.legacy_base else None
        return effective_document(base, self.plot.series,
                                  self.plot.chart_key, self.plot_title,
                                  self.overrides,
                                  figure_size=self.figure_size)

    def update_overrides(self, fn):
        """Apply ``fn(self.overrides)``, undoably, then mark dirty.

        The single entry point for in-place style edits (the element
        panels). Each successful non-no-op edit lands in the
        worksheet's undo history as 'Edit Plot', chronological with
        cell edits. Crash-safe: on any failure the pre-edit overrides
        are restored and re-rendered, and the traceback goes to stderr
        — a slot exception must never reach Qt (PyQt6 aborts on those).
        """
        if not record_overrides_edit(
                self.worksheet, self.overrides, fn,
                self._render_preview, label='Edit Plot'):
            return
        self.dirty = True
        self.changed.emit()

    def _render_preview(self, keep_view=True):
        if self.plot is None:
            return
        doc = self.effective_document()
        try:
            svg = render_document(doc).svg
            self.regions = element_regions(doc)
        except PlotDocumentError as e:
            # Keep the previous canvas; the window shows its info dialog.
            raise PlotSelectionError(str(e)) from e
        self.plot_canvas.show_svg(svg, keep_view=keep_view)
        self.plot_canvas.set_regions(self.regions)

    def eventFilter(self, obj, event):
        from PyQt6.QtCore import QEvent
        if obj is self._right_area \
                and event.type() == QEvent.Type.Resize:
            self._position_reset_all()
        return super().eventFilter(obj, event)

    def _position_reset_all(self):
        area = self._right_area
        self.reset_all.adjustSize()
        self.style_presets.adjustSize()
        self.figure_size_button.adjustSize()
        self.reset_all.move(area.width() - self.reset_all.width() - 12,
                            area.height() - self.reset_all.height() - 12)
        self.style_presets.move(
            self.reset_all.x() - self.style_presets.width() - 6,
            self.reset_all.y())
        self.figure_size_button.move(
            self.style_presets.x() - self.figure_size_button.width() - 6,
            self.reset_all.y())
        self.reset_all.raise_()
        self.style_presets.raise_()
        self.figure_size_button.raise_()

    def _update_reset_all(self):
        self.reset_all.setVisible(self.plot is not None)
        self.reset_all.setEnabled(not self.overrides.is_empty())
        self.style_presets.setVisible(self.plot is not None)
        self.figure_size_button.setVisible(self.plot is not None)
        if self.plot is not None:
            self._position_reset_all()

    # ── figure size ──────────────────────────────────────────────────

    def set_figure_size(self, size):
        if self.plot is None or size == self.figure_size:
            return False
        # Validate even if called outside the dialog.
        size = FigureSize(size.width_mm, size.height_mm)
        old = self.figure_size
        self.worksheet.record_external_edit(
            'Resize Plot',
            lambda: setattr(self, 'figure_size', size),
            lambda: setattr(self, 'figure_size', old))
        return True

    def edit_figure_size(self):
        if self.plot is None:
            return
        from .figure_size_dialog import FigureSizeDialog
        dialog = FigureSizeDialog(self.figure_size,
                                  self._figure_size_locked, self)
        if dialog.exec() == dialog.DialogCode.Accepted:
            self._figure_size_locked = dialog.locked()
            self.set_figure_size(dialog.figure_size())

    # ── Style presets ────────────────────────────────────────────────

    def _plot_type(self):
        return presets.plot_type_for_chart(self.plot.chart_key) \
            if self.plot is not None else None

    def _rebuild_preset_menu(self):
        menu = self._preset_menu
        menu.clear()
        if self.plot is None or self.preset_store is None:
            return
        ptype = self._plot_type()
        header = menu.addAction(tr('grp_' + ptype))
        header.setEnabled(False)
        default = self.preset_store.default_name(ptype)
        for preset in self.preset_store.list(ptype):
            label = preset.name
            if preset.name == default:
                label += ' ' + tr('preset_default')
            action = menu.addAction(label)
            action.triggered.connect(
                lambda checked=False, p=preset: self._apply_preset(p))
        menu.addSeparator()
        menu.addAction(tr('preset_save'), self._save_preset_dialog)
        manage = menu.addAction(tr('preset_manage'))
        if self._open_style_manager_cb is not None:
            manage.triggered.connect(self._open_style_manager_cb)
        else:
            manage.setEnabled(False)

    def _apply_preset(self, preset):
        def fn(o):
            presets.apply(preset, o, self.plot.series,
                          self.plot.chart_key)
        self.update_overrides(fn)

    def _save_preset_dialog(self):
        if self.plot is None or self.preset_store is None:
            return
        name, ok = QInputDialog.getText(
            self, tr('preset_save_title'), tr('preset_save_prompt'))
        if not ok:
            return
        name = name.strip()
        try:
            preset = presets.capture(self.overrides, self._plot_type())
            preset.name = name
            self.preset_store.save(preset)
        except presets.PresetError as e:
            msg = str(e)
            if 'already exists' in msg:
                msg = tr('preset_duplicate', name=name)
            elif 'name' in msg.lower():
                msg = tr('preset_invalid_name')
            else:
                msg = tr('preset_save_failed', error=e)
            QMessageBox.warning(self, tr('preset_save_title'), msg)

    def _reset_all_formatting(self):
        box = QMessageBox.question(
            self, tr('reset_all'),
            tr('reset_all_confirm'))
        if box == QMessageBox.StandardButton.Yes:
            fresh = PlotOverrides()

            def _reset(o):
                # Fills, spans and bands are data, not formatting —
                # carry them over (annotations/brackets unchanged).
                fresh.bands = o.bands
                fresh.spans = o.spans
                fresh.fills = o.fills
                self._copy_overrides(o, fresh)
            self.update_overrides(_reset)

    # ── annotations / brackets ────────────────────────────────────────

    def _new_item_id(self, prefix, existing):
        used = {a.id for a in existing}
        n = 1
        while f'{prefix}-{n}' in used:
            n += 1
        return f'{prefix}-{n}'

    def add_annotation(self, x=None, y=None, at=None):
        """Append a note and open its element panel. ``x``/``y`` are an
        axes-fraction centre (floating text); without them the note
        anchors to the upper-right corner."""
        if self.plot is None:
            return
        from ilmplot.document import Annotation
        hold = {}
        def fn(o):
            if o.annotations is None:
                o.annotations = []
            aid = self._new_item_id('note', o.annotations)
            o.annotations.append(
                Annotation(id=aid, text=tr('note_default'),
                           anchor='upper right', x=x, y=y))
            hold['key'] = 'annotation:' + aid
        self.update_overrides(fn)
        key = hold.get('key')
        if key is not None:
            if at is not None:
                self._open_element_panel(key, at)
            else:
                self._open_at_center(key)

    def add_text(self):
        """"Add Text" menu action: a floating note at the axes centre."""
        self.add_annotation(x=0.5, y=0.5)

    def brackets_allowed(self):
        """Significance brackets need ≥2 violin groups/stacked bars."""
        if self.plot is None:
            return False
        kind = CHART_KIND.get(self.plot.chart_key,
                              ('line', None))[0]
        return kind in ('violin', 'stacked_column') \
            and len(self.plot.series) >= 2

    def _add_text_at(self, frac, global_pos):
        from .hit_test import figure_to_axes
        axes = figure_to_axes(self.regions, *frac) if frac else None
        if axes is None:
            self.add_annotation(at=global_pos)
            return
        x = max(-0.5, min(1.5, axes[0]))
        y = max(-0.5, min(1.5, axes[1]))
        self.add_annotation(x=x, y=y, at=global_pos)

    def _on_element_moved(self, key, ax, ay):
        """Commit a dragged annotation's axes-fraction centre."""
        aid = key[len('annotation:'):]
        ax = max(-0.5, min(1.5, ax))
        ay = max(-0.5, min(1.5, ay))

        def fn(o):
            if o.annotations is None:
                doc = self.effective_document()
                o.annotations = [copy.copy(a)
                                 for a in doc.annotations or ()]
            target = next((a for a in o.annotations if a.id == aid),
                          None)
            if target is not None:
                target.x = ax
                target.y = ay

        self.update_overrides(fn)

    def _delete_element(self, key):
        if key.startswith('annotation:'):
            aid = key[len('annotation:'):]
            def fn(o):
                if o.annotations is None:
                    doc = self.effective_document()
                    o.annotations = [copy.copy(a)
                                     for a in doc.annotations or ()]
                o.annotations = [a for a in o.annotations
                                 if a.id != aid] or None
        elif key.startswith('bracket:'):
            bid = key[len('bracket:'):]
            def fn(o):
                if o.brackets is None:
                    doc = self.effective_document()
                    o.brackets = [copy.copy(b)
                                  for b in doc.brackets or ()]
                o.brackets = [b for b in o.brackets
                              if b.id != bid] or None
        elif key.startswith('span:'):
            sid = key[len('span:'):]
            def fn(o):
                if o.spans is None:
                    doc = self.effective_document()
                    o.spans = [copy.copy(s)
                               for s in getattr(doc, 'spans', None)
                               or ()]
                o.spans = [s for s in o.spans
                           if s.id != sid] or None
        elif key.startswith('band:'):
            bid = key[len('band:'):]
            def fn(o):
                # A curve fill (editor-created) or a static document band.
                if o.fills and any(f.id == bid for f in o.fills):
                    o.fills = [f for f in o.fills
                               if f.id != bid] or None
                    return
                if o.bands is None:
                    doc = self.effective_document()
                    o.bands = [copy.copy(b)
                               for b in static_bands(doc, o)]
                o.bands = [b for b in o.bands
                           if b.id != bid] or None
        else:
            return
        self.update_overrides(fn)

    def _on_canvas_context(self, key, global_pos, frac):
        menu = QMenu(self)
        if self.plot is None:
            empty = menu.addAction(tr('ctx_create_first'))
            empty.setEnabled(False)
            menu.exec(global_pos)
            return
        menu.addAction(tr('ctx_add_text_here'),
                       lambda: self._add_text_at(frac, global_pos))
        if self.brackets_allowed():
            menu.addAction(tr('act_add_bracket'), self.add_bracket)
        if self.plot is not None and CHART_KIND.get(
                self.plot.chart_key, ('line', None))[0] == 'line':
            menu.addAction(tr('act_add_fill'), self.add_fill)
        menu.addSeparator()
        theme_menu = menu.addMenu(tr('menu_colour_theme'))
        self.fill_theme_menu(theme_menu)
        menu.addSeparator()
        if key and key != 'frame':
            menu.addAction(
                tr('ctx_edit'),
                lambda: self._open_element_panel(key, global_pos))
            if key.startswith(('annotation:', 'bracket:', 'span:',
                               'band:')):
                menu.addAction(tr('btn_delete'),
                               lambda: self._delete_element(key))
            menu.addSeparator()
        menu.addAction(tr('reset_all'), self._reset_all_formatting)
        menu.exec(global_pos)

    # ── colour themes ─────────────────────────────────────────────────

    def effective_theme(self):
        """The palette ref in force: override, else the chart default."""
        if self.plot is None:
            return 'default'
        from .palettes import default_theme
        return self.overrides.palette or default_theme(
            self.plot.chart_key, len(self.plot.series))

    def fill_theme_menu(self, menu):
        """Theme checkable actions + Reverse + Edit…, for the canvas
        context menu and the window's Plot ▸ Colour Theme submenu."""
        from .palettes import THEMES, custom_theme_names, \
            theme_display_name
        from .style_icons import palette_strip
        menu.clear()
        if self.plot is None:
            return
        current = self.effective_theme()
        for name in list(THEMES):
            act = menu.addAction(palette_strip(name),
                                 theme_display_name(name))
            act.setCheckable(True)
            act.setChecked(name == current)
            act.triggered.connect(
                lambda _c=False, n=name: self._set_palette(n))
        custom = custom_theme_names()
        if custom:
            menu.addSeparator()
            for cn in custom:
                ref = 'custom:' + cn
                act = menu.addAction(palette_strip(ref),
                                     theme_display_name(ref))
                act.setCheckable(True)
                act.setChecked(ref == current)
                act.triggered.connect(
                    lambda _c=False, r=ref: self._set_palette(r))
        # A file can name a theme this machine does not have. Keep it
        # checked so the menu shows the name the colours came from.
        if (isinstance(current, str) and current.startswith('custom:')
                and current[7:] not in custom):
            if not custom:
                menu.addSeparator()
            swatch = (self.overrides.palette_colors
                      or self.overrides.baked_item_colors)
            act = menu.addAction(
                palette_strip(current, colors=swatch),
                theme_display_name(current))
            act.setCheckable(True)
            act.setChecked(True)
            act.triggered.connect(
                lambda _c=False, r=current: self._set_palette(r))
        menu.addSeparator()
        rev = menu.addAction(tr('row_reverse_colours'))
        rev.setCheckable(True)
        rev.setChecked(bool(self.overrides.palette_reverse))
        rev.triggered.connect(self._set_palette_reverse)
        menu.addSeparator()
        menu.addAction(tr('menu_edit_themes'),
                       self._open_theme_editor)

    def _set_palette(self, name):
        self.update_overrides(lambda o: assign_palette(o, name))

    def _set_palette_reverse(self, checked):
        self.update_overrides(
            lambda o: assign_palette_reverse(o, checked))

    def _open_theme_editor(self):
        window = self.window()
        opener = getattr(window, 'open_theme_editor', None)
        if opener is not None:
            opener()

    def add_bracket(self):
        """Append a significance bracket over the first two items."""
        if self.plot is None:
            return
        doc = self.effective_document()
        n = len(doc.groups or doc.categories)
        if n < 2:
            return
        from ilmplot.document import Bracket
        hold = {}
        def fn(o):
            if o.brackets is None:
                o.brackets = []
            bid = self._new_item_id('bracket', o.brackets)
            o.brackets.append(Bracket(id=bid, a=0, b=1, text='*'))
            hold['key'] = 'bracket:' + bid
        self.update_overrides(fn)
        self._open_at_center(hold.get('key'))

    def add_fill(self):
        """"Add Fill…" menu action: a span or a curve fill dialog."""
        if self.plot is None:
            return
        doc = self.effective_document()
        if doc is None or doc.kind != 'line':
            return
        from .fill_dialog import AddFillDialog
        dialog = AddFillDialog(self.plot.series, doc, parent=self)
        if dialog.exec() != AddFillDialog.DialogCode.Accepted:
            return
        result = dialog.result_item()

        from ilmplot.document import MAX_BANDS, MAX_SPANS
        n_spans = len(self.overrides.spans
                      if self.overrides.spans is not None
                      else doc.spans)
        n_bands = len(self.overrides.bands
                      if self.overrides.bands is not None
                      else doc.bands) \
            + len(self.overrides.fills or ())
        if result['type'] in ('xspan', 'yspan') \
                and n_spans + 1 > MAX_SPANS \
                or result['type'] in ('under', 'between') \
                and n_bands + 1 > MAX_BANDS:
            QMessageBox.warning(
                self, tr('act_add_fill'),
                tr('fill_limit', n=max(MAX_SPANS, MAX_BANDS)))
            return

        hold = {}
        def fn(o):
            if result['type'] in ('xspan', 'yspan'):
                from ilmplot.document import Span
                if o.spans is None:
                    o.spans = [copy.copy(s) for s in doc.spans]
                sid = self._new_item_id('span', o.spans)
                o.spans.append(Span(
                    id=sid,
                    axis='x' if result['type'] == 'xspan' else 'y',
                    lo=result['lo'], hi=result['hi'],
                    color=result['color'], label=result['label']))
                hold['key'] = 'span:' + sid
            else:
                from .fills import CurveFill
                if o.fills is None:
                    o.fills = []
                fid = self._new_item_id(
                    'fill', list(o.fills)
                    + list(o.bands if o.bands is not None else doc.bands))
                o.fills.append(CurveFill(
                    id=fid, kind=result['type'],
                    a=result['a'], b=result.get('b'),
                    baseline=result.get('baseline', 0.0),
                    x_min=result.get('x_min'), x_max=result.get('x_max'),
                    color=result['color'], label=result['label']))
                hold['key'] = 'band:' + fid
        self.update_overrides(fn)
        self._open_at_center(hold.get('key'))

    def _open_at_center(self, key):
        if key is None:
            return
        pos = self.plot_canvas.viewport().rect().center()
        self._open_element_panel(
            key, self.plot_canvas.viewport().mapToGlobal(pos))

    @staticmethod
    def _copy_overrides(target, source):
        target.xlabel = source.xlabel
        target.ylabel = source.ylabel
        target.legend = source.legend
        target.legend_location = source.legend_location
        target.grid = source.grid
        target.xlim = source.xlim
        target.ylim = source.ylim
        target.style = source.style
        target.series = source.series
        target.palette = source.palette
        target.palette_reverse = source.palette_reverse
        target.palette_colors = source.palette_colors
        target.baked_item_colors = source.baked_item_colors
        target.violin = source.violin
        target.ridgeline = source.ridgeline
        target.stacked = source.stacked
        target.histogram = source.histogram
        target.annotations = source.annotations
        target.brackets = source.brackets
        target.bands = source.bands
        target.bar_labels = source.bar_labels

    def _on_worksheet_event(self, event):
        if event == ('history',):
            self.dirty = True
            self.changed.emit()
        if event[0] in ('columns_inserted', 'columns_removed'):
            remap_series_keys(self.overrides, event)
            if self.plot is not None:
                self.plot.plot_columns = _shift_columns(
                    self.plot.plot_columns, event)
        if event == ('history',) and self.plot is not None:
            self._refresh_from_sheet()

    def _refresh_from_sheet(self):
        """Re-plot the current columns after a committed worksheet edit.

        History events fire only for finished edits (Enter / focus loss,
        paste, structural ops, undo/redo), never while typing. A sheet that
        no longer yields a plottable selection keeps the previous preview.
        """
        try:
            self.plot.series = _build_items(
                self.worksheet, list(self.plot.plot_columns),
                self.plot.chart_key)
            self._render_preview()
        except PlotSelectionError:
            pass

    def _set_path(self, path):
        self.path = path
        name = os.path.basename(path)
        self.title = (name[:-len(_SUFFIX)]
                      if name.lower().endswith(_SUFFIX)
                      else os.path.splitext(name)[0])

    def detach(self, title):
        """Unlink this tab from its file: Save As prompts, close warns."""
        self.path = None
        self.title = title
        self.dirty = True
        self.changed.emit()

    def is_pristine(self):
        return (self.path is None and not self.dirty
                and self.plot is None and not self.worksheet.can_undo)

    def plot_current(self, chart_key):
        """Plot the current selection; PlotSelectionError propagates."""
        columns = tuple(self.worksheet_view.selected_columns())
        series = _build_items(self.worksheet, columns, chart_key)
        self.plot = PlotState(series, chart_key, columns, None)
        # Fresh plot: apply the type's default preset when it isn't the
        # Standard built-in. Loaded files never take this path.
        if self.preset_store is not None:
            try:
                preset = self.preset_store.default_preset(
                    presets.plot_type_for_chart(chart_key))
            except presets.PresetError:
                preset = None
            if presets.should_auto_apply(self.overrides, preset):
                presets.apply(preset, self.overrides, series, chart_key)
        self._render_preview(keep_view=False)
        self.dirty = True
        self.changed.emit()

    def load(self, pf, path):
        """Fill this (fresh) tab with a loaded ``PlotFile``."""
        self.plot_canvas.show_svg(pf.svg)
        if pf.has_worksheet:
            columns = tuple(pf.plot_columns)
        else:
            columns = tuple(range(self.worksheet.column_count))
        chart = pf.chart_key or chart_from_document(pf.document)
        try:
            series = _build_items(self.worksheet, list(columns), chart)
        except PlotSelectionError:
            series = items_from_document(pf.document)
        self.plot = PlotState(series, chart, columns, pf.document,
                              legacy_base=not pf.has_worksheet)
        # Node v2 carries the overrides; older/ILM files seed them from
        # the document (style cloned; only fields differing from defaults).
        self.overrides = pf.overrides if pf.overrides is not None \
            else overrides_from_document(pf.document, series, chart)
        hold_baked_colours(self.overrides, pf.document)
        self.regions = None
        self._set_path(path)
        self.plot_title = pf.document.title or ''
        # Geometry comes from the actual native document, even when the
        # file carries a v2 overrides node.
        self.figure_size = FigureSize.from_document(pf.document)
        self.title_field.set_title(self.plot_title)
        # Preview uses the same native effective document that save and
        # ILM rendering consume; if it can't render, keep the file's SVG.
        try:
            self._render_preview()
        except PlotSelectionError:
            pass
        self.dirty = False
        self.changed.emit()

    def save(self, path):
        """Write this tab as ``*.ilmplot.svg``; raises PlotFileError."""
        if self.plot is None:
            raise PlotFileError(tr('msg_no_plot'))
        save_plot_file(path, self.effective_document(), self.worksheet,
                       self.plot.chart_key, self.plot.plot_columns,
                       self.overrides)
        self._set_path(path)
        self.dirty = False
        self.changed.emit()
