"""Plot → Plot Style… manager dialog.

Left: a tree of presets grouped by plot type (chart group). Right: a
rendered preview of the selected preset on a fixed three-series sample
document, a short read-only summary, and the management buttons. The
dialog uses the window's shared ``PresetStore`` and applies presets
through the current tab's ``update_overrides``.
"""

from __future__ import annotations

import math
import os

from PyQt6.QtCore import QUrl, Qt
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtSvgWidgets import QSvgWidget
from PyQt6.QtWidgets import (QDialog, QHBoxLayout, QInputDialog, QLabel,
                             QMessageBox, QPushButton, QTreeWidget,
                             QTreeWidgetItem, QVBoxLayout, QWidget)

from . import presets
from .actions import CHART_GROUPS
from .document import LineSeries, PlotDocument, PlotDocumentError
from .i18n import tr
from .overrides import PlotOverrides, effective_document
from .plot_data import Category, Group, Series
from .render import render_document

# Eight items per sample so a colour theme shows its full range.
_SAMPLE_N = 8
_SAMPLE_X = [float(i) for i in range(11)]
_SAMPLE_Y = tuple(
    [round(0.8 * k + 0.5 * math.sin(0.6 * x + 0.7 * k), 2)
     for x in _SAMPLE_X]
    for k in range(_SAMPLE_N))


def sample_document():
    """Fixed eight-series sample used by the line group's preview."""
    doc = PlotDocument(
        title='Sample', xlabel='X', ylabel='Y', legend=True,
        series=[LineSeries(label='Series %d' % (i + 1),
                           x=list(_SAMPLE_X), y=list(y))
                for i, y in enumerate(_SAMPLE_Y)])
    return doc


def _sample_items(plot_type):
    """Worksheet-item stand-ins appropriate to each chart group."""
    if plot_type == 'violin':
        import numpy as np
        rng = np.random.default_rng(7)
        return [Group(tuple(rng.normal(i * 0.5, 0.6, 40)),
                      'G%d' % (i + 1), 'X', 'Y', y_column=i)
                for i in range(_SAMPLE_N)]
    if plot_type == 'column':
        return [Category(tuple(float(10 + (3 * i + 5 * b) % 17)
                               for b in range(3)),
                         'Series %d' % (i + 1),
                         'X', 'Y', y_column=i)
                for i in range(_SAMPLE_N)]
    return _sample_plot_series(sample_document())


def _sample_plot_series(doc):
    """Lightweight worksheet-series stand-ins for ``effective_document``."""
    return [Series(tuple(s.x), tuple(s.y), s.label, 'X', 'Y', None, i)
            for i, s in enumerate(doc.series)]


def _preview_overrides(preset, chart_key, items):
    overrides = PlotOverrides()
    presets.apply(preset, overrides, items, chart_key)
    return overrides


class StyleManagerDialog(QDialog):
    def __init__(self, store, current_tab, theme, scale=1.0,
                 parent=None):
        super().__init__(parent)
        self.store = store
        self.tab = current_tab
        self.theme = theme
        self.scale = scale
        self.setObjectName('plotStyleManager')
        self.setWindowTitle(tr('style_mgr_title'))
        self.resize(900, 540)

        self.tree = QTreeWidget(self)
        self.tree.setHeaderHidden(True)
        self.tree.setMinimumWidth(240)
        self.tree.currentItemChanged.connect(self._on_select)

        right = QWidget(self)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        self.errors_label = QLabel(self)
        self.errors_label.setWordWrap(True)
        self.errors_label.setVisible(False)
        right_layout.addWidget(self.errors_label)
        self.preview = QSvgWidget(self)
        self.preview.setMinimumSize(360, 260)
        right_layout.addWidget(self.preview, 1)
        self.summary = QLabel(self)
        self.summary.setTextFormat(Qt.TextFormat.RichText)
        self.summary.setWordWrap(True)
        right_layout.addWidget(self.summary)

        buttons = QHBoxLayout()
        self.btn_new = QPushButton(tr('btn_new_from_plot'), self)
        self.btn_new.clicked.connect(self._new_from_plot)
        self.btn_dup = QPushButton(tr('btn_duplicate'), self)
        self.btn_dup.clicked.connect(self._duplicate)
        self.btn_rename = QPushButton(tr('btn_rename'), self)
        self.btn_rename.clicked.connect(self._rename)
        self.btn_delete = QPushButton(tr('btn_delete'), self)
        self.btn_delete.clicked.connect(self._delete)
        self.btn_default = QPushButton(tr('btn_set_default'), self)
        self.btn_default.clicked.connect(self._set_default)
        self.btn_apply = QPushButton(tr('btn_apply'), self)
        self.btn_apply.clicked.connect(self._apply)
        self.btn_folder = QPushButton(tr('btn_open_folder'), self)
        self.btn_folder.clicked.connect(self._open_folder)
        for b in (self.btn_new, self.btn_dup, self.btn_rename,
                  self.btn_delete, self.btn_default, self.btn_apply,
                  self.btn_folder):
            buttons.addWidget(b)
        right_layout.addLayout(buttons)

        main = QHBoxLayout(self)
        main.addWidget(self.tree, 2)
        main.addWidget(right, 3)
        self.reload()

    # ── data ─────────────────────────────────────────────────────────
    def _chart_key(self, plot_type):
        for group in CHART_GROUPS:
            if group.key == plot_type and group.charts:
                return group.charts[0].key
        return CHART_GROUPS[0].charts[0].key

    def reload(self):
        self.tree.clear()
        for group in CHART_GROUPS:
            node = QTreeWidgetItem([tr('grp_' + group.key)])
            node.setFlags(Qt.ItemFlag.ItemIsEnabled)
            node.setData(0, Qt.ItemDataRole.UserRole,
                         (group.key, None))
            self.tree.addTopLevelItem(node)
            default = self.store.default_name(group.key)
            for preset in self.store.list(group.key):
                label = preset.name
                if preset.builtin:
                    label += ' ' + tr('preset_builtin')
                if preset.name == default:
                    label += ' ' + tr('preset_default')
                item = QTreeWidgetItem([label])
                item.setData(0, Qt.ItemDataRole.UserRole,
                             (group.key, preset.name))
                if preset.name == default:
                    font = item.font(0)
                    font.setBold(True)
                    item.setFont(0, font)
                node.addChild(item)
            node.setExpanded(True)
        # Select the current tab's default preset when possible.
        ptype = None
        if self.tab is not None and self.tab.plot is not None:
            ptype = self.tab._plot_type()
        self._select_preset(ptype, self.store.default_name(ptype)
                            if ptype else None)
        self._show_errors()

    def _select_preset(self, plot_type, name):
        if plot_type is None:
            # No plot open: show the first group's first preset rather
            # than its header, so the preview is never blank on open.
            node = self.tree.topLevelItem(0)
            self.tree.setCurrentItem(node.child(0) or node)
            return
        for i in range(self.tree.topLevelItemCount()):
            node = self.tree.topLevelItem(i)
            if node.data(0, Qt.ItemDataRole.UserRole)[0] != plot_type:
                continue
            for j in range(node.childCount()):
                item = node.child(j)
                if item.data(0, Qt.ItemDataRole.UserRole)[1] == name:
                    self.tree.setCurrentItem(item)
                    return
            self.tree.setCurrentItem(node.child(0) or node)
            return

    def _show_errors(self):
        if self.store.errors:
            self.errors_label.setText(tr(
                'preset_errors',
                files=', '.join(fn for fn, _e in self.store.errors)))
            self.errors_label.setVisible(True)
        else:
            self.errors_label.setVisible(False)

    # ── selection / preview ──────────────────────────────────────────
    def _selected(self):
        item = self.tree.currentItem()
        if item is None:
            return None, None
        ptype, name = item.data(0, Qt.ItemDataRole.UserRole)
        if name is None:
            return ptype, None
        return ptype, self.store.get(ptype, name)

    def _on_select(self, current, _previous):
        ptype, preset = self._selected()
        if preset is None:
            self.btn_dup.setEnabled(False)
            self.btn_rename.setEnabled(False)
            self.btn_delete.setEnabled(False)
            self.btn_default.setEnabled(False)
            self.btn_apply.setEnabled(False)
            self.summary.setText('')
            return
        builtin = preset.builtin
        self.btn_dup.setEnabled(True)
        self.btn_rename.setEnabled(not builtin)
        self.btn_delete.setEnabled(not builtin)
        self.btn_default.setEnabled(True)
        self.btn_apply.setEnabled(self._tab_compatible(ptype))
        # Summary first so a preview failure message isn't overwritten.
        self._render_summary(preset)
        self._render_preview(ptype, preset)

    def _tab_compatible(self, ptype):
        return (self.tab is not None and self.tab.plot is not None
                and self.tab._plot_type() == ptype)

    def _render_preview(self, ptype, preset):
        chart_key = self._chart_key(ptype)
        try:
            items = _sample_items(ptype)
            overrides = _preview_overrides(preset, chart_key, items)
            # Every preview regenerates from its sample items so the
            # chart's own colour theme and markers apply.
            doc = effective_document(None, items,
                                     chart_key, 'Sample', overrides)
            svg = render_document(doc).svg
            self.preview.load(svg if isinstance(svg, bytes)
                              else svg.encode('utf-8'))
            self.preview.renderer().setAspectRatioMode(
                Qt.AspectRatioMode.KeepAspectRatio)
            self.preview.update()
        except (PlotDocumentError, ValueError) as e:
            self.summary.setText(str(e))

    def _render_summary(self, preset):
        parts = []
        family = _preset_family(preset.style)
        parts.append(tr('sum_font', value=family or tr('sum_inherit')))
        if preset.legend is False:
            loc = tr('sum_off')
        else:
            key = 'loc_' + (preset.legend_location or 'best')
            loc = tr(key) if key in _loc_keys() \
                else (preset.legend_location or tr('sum_default'))
        parts.append(tr('sum_legend', value=loc))
        grid = (tr('sum_on') if preset.grid else
                tr('sum_off') if preset.grid is False
                else tr('sum_inherit'))
        parts.append(tr('sum_grid', value=grid))
        text = '<br>'.join(parts)
        if preset.series.colors:
            swatches = ' '.join(
                '<span style="background-color:{c};color:{c}">■</span>'
                .format(c=c) for c in preset.series.colors)
            text += '<br>' + tr('sum_colors') + ' ' + swatches
        self.summary.setText(text)

    # ── buttons ──────────────────────────────────────────────────────
    def _open_folder(self):
        # The folder only exists once a preset is saved; create it so the
        # shell doesn't fail with "path not found".
        root = os.path.normpath(self.store.root)
        try:
            os.makedirs(root, exist_ok=True)
            if os.name == 'nt':
                os.startfile(root)  # Explorer, no URL round-trip
                return
        except OSError as e:
            QMessageBox.warning(self, tr('style_mgr_title'),
                                '%s\n%s' % (root, e))
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(root))

    def _prompt_name(self, title, prompt, initial=''):
        name, ok = QInputDialog.getText(self, title, prompt,
                                        text=initial)
        return name.strip() if ok else None

    def _save_capture(self, ptype, name, base=None):
        try:
            preset = base if base is not None else presets.capture(
                self.tab.overrides, ptype)
            # Name first: to_dict() validates it, and capture() leaves
            # it empty.
            preset.name = name
            preset = presets.StylePreset.from_dict(preset.to_dict())
            self.store.save(preset)
            return True
        except presets.PresetError as e:
            msg = str(e)
            if 'already exists' in msg:
                msg = tr('preset_duplicate', name=name)
            elif 'name' in msg.lower():
                msg = tr('preset_invalid_name')
            QMessageBox.warning(self, tr('style_mgr_title'), msg)
            return False

    def _new_from_plot(self):
        item = self.tree.currentItem()
        ptype = item.data(0, Qt.ItemDataRole.UserRole)[0] \
            if item is not None else CHART_GROUPS[0].key
        if not self._tab_compatible(ptype):
            return
        name = self._prompt_name(tr('preset_save_title'),
                                 tr('preset_save_prompt'))
        if not name:
            return
        if self._save_capture(ptype, name):
            self.reload()

    def _duplicate(self):
        ptype, preset = self._selected()
        if preset is None:
            return
        try:
            self.store.duplicate(ptype, preset.name)
        except presets.PresetError as e:
            QMessageBox.warning(self, tr('style_mgr_title'), str(e))
            return
        self.reload()

    def _rename(self):
        ptype, preset = self._selected()
        if preset is None or preset.builtin:
            return
        name = self._prompt_name(tr('preset_name_title'),
                                 tr('preset_rename_prompt'),
                                 preset.name)
        if not name or name == preset.name:
            return
        try:
            self.store.rename(ptype, preset.name, name)
        except presets.PresetError as e:
            msg = str(e)
            if 'already exists' in msg:
                msg = tr('preset_duplicate', name=name)
            elif 'name' in msg.lower():
                msg = tr('preset_invalid_name')
            QMessageBox.warning(self, tr('style_mgr_title'), msg)
            return
        self.reload()

    def _delete(self):
        ptype, preset = self._selected()
        if preset is None or preset.builtin:
            return
        if QMessageBox.question(
                self, tr('style_mgr_title'),
                tr('preset_delete_confirm', name=preset.name)) \
                != QMessageBox.StandardButton.Yes:
            return
        try:
            self.store.delete(ptype, preset.name)
        except presets.PresetError as e:
            QMessageBox.warning(self, tr('style_mgr_title'), str(e))
            return
        self.reload()

    def _set_default(self):
        ptype, preset = self._selected()
        if preset is None:
            return
        try:
            self.store.set_default(ptype, preset.name)
        except presets.PresetError as e:
            QMessageBox.warning(self, tr('style_mgr_title'), str(e))
            return
        self.reload()

    def _apply(self):
        ptype, preset = self._selected()
        if preset is None or not self._tab_compatible(ptype):
            return
        tab = self.tab

        def fn(o):
            presets.apply(preset, o, tab.plot.series,
                          tab.plot.chart_key)
        tab.update_overrides(fn)


def _loc_keys():
    from .i18n import _STRINGS
    return {k for k in _STRINGS if k.startswith('loc_')}


def _preset_family(style):
    """First font family the preset pins down, else None."""
    for part in (style.title, style.xlabel, style.ylabel):
        if part is not None and part.family:
            return part.family
    for part in (style.xaxis, style.yaxis):
        if part is not None and part.ticks is not None \
                and part.ticks.family:
            return part.ticks.family
    if style.legend is not None and style.legend.text is not None \
            and style.legend.text.family:
        return style.legend.text.family
    return None
