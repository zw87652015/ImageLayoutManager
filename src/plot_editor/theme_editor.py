"""Colour theme editor dialog for the Plot Editor.

Built-ins are listed read-only; custom themes (``ThemeStore``) are
editable — colour/name edits save immediately and notify ``on_change``
so the window can refresh ``palettes``' custom registry and re-render
open plots that use the theme.
"""

import os

from PyQt6.QtCore import QSize, Qt, QUrl
from PyQt6.QtGui import QColor, QDesktopServices, QIcon, QPixmap
from PyQt6.QtWidgets import (QColorDialog, QDialog, QHBoxLayout,
                             QInputDialog, QLabel, QLineEdit,
                             QListWidget, QListWidgetItem, QMessageBox,
                             QPushButton, QVBoxLayout)

from .chrome import style_tokens
from .i18n import tr
from .theme_store import Theme, ThemeError

_STRIP_W, _STRIP_H = 120, 16
_SWATCH = 18


def _strip_icon(colors, w, h, dpr=1.0):
    """Equal-width colour swatches, like ``style_icons.palette_strip``
    but for a raw colour list."""
    pm = QPixmap(round(w * dpr), round(h * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.GlobalColor.transparent)
    n = len(colors)
    if n:
        sw = w / n
        from PyQt6.QtGui import QPainter
        from PyQt6.QtCore import QRectF
        p = QPainter(pm)
        for i, c in enumerate(colors):
            p.fillRect(QRectF(i * sw, 2, sw + 0.5, h - 4), QColor(c))
        p.end()
    return QIcon(pm)


def _swatch(hex_color):
    pm = QPixmap(_SWATCH, _SWATCH)
    pm.fill(QColor(hex_color))
    return QIcon(pm)


class ThemeEditorDialog(QDialog):
    """List of themes on the left, editable colour list on the right."""

    def __init__(self, store, theme, parent=None, on_change=None):
        super().__init__(parent)
        self._store = store
        self._on_change = on_change
        self._theme = theme
        self._tokens = style_tokens(theme, 1.0)
        self._current = None
        self._loading = False

        self.setWindowTitle(tr('te_title'))
        self.resize(560, 340)
        root = QHBoxLayout(self)

        self.list = QListWidget(self)
        self.list.setMaximumWidth(180)
        self.list.currentRowChanged.connect(self._load_row)
        root.addWidget(self.list)

        right = QVBoxLayout()
        self.name_edit = QLineEdit(self)
        self.name_edit.setPlaceholderText(tr('te_name'))
        self.name_edit.editingFinished.connect(self._commit_name)
        right.addWidget(self.name_edit)

        self.colors = QListWidget(self)
        self.colors.itemDoubleClicked.connect(
            lambda _it: self._edit_color())
        right.addWidget(self.colors, 1)

        self.preview = QLabel(self)
        self.preview.setFixedHeight(_STRIP_H + 6)
        right.addWidget(self.preview)

        self.hint = QLabel(tr('te_builtin_hint'), self)
        self.hint.setStyleSheet('color: %s;' % self._tokens['text_tert'])
        right.addWidget(self.hint)

        edit_row = QHBoxLayout()
        self.btn_add = QPushButton(tr('te_add_colour'), self)
        self.btn_edit = QPushButton(tr('btn_edit'), self)
        self.btn_remove = QPushButton(tr('btn_remove'), self)
        self.btn_up = QPushButton(tr('btn_up'), self)
        self.btn_down = QPushButton(tr('btn_down'), self)
        for b in (self.btn_add, self.btn_edit, self.btn_remove,
                  self.btn_up, self.btn_down):
            edit_row.addWidget(b)
        self.btn_add.clicked.connect(self._add_color)
        self.btn_edit.clicked.connect(self._edit_color)
        self.btn_remove.clicked.connect(self._remove_color)
        self.btn_up.clicked.connect(lambda: self._move_color(-1))
        self.btn_down.clicked.connect(lambda: self._move_color(1))
        right.addLayout(edit_row)
        root.addLayout(right, 1)

        bottom = QVBoxLayout()
        row = QHBoxLayout()
        self.btn_new = QPushButton(tr('btn_new'), self)
        self.btn_dup = QPushButton(tr('btn_duplicate'), self)
        self.btn_ren = QPushButton(tr('btn_rename'), self)
        self.btn_del = QPushButton(tr('btn_delete'), self)
        self.btn_open = QPushButton(tr('btn_open_folder'), self)
        self.btn_close = QPushButton(tr('btn_close'), self)
        for b in (self.btn_new, self.btn_dup, self.btn_ren,
                  self.btn_del, self.btn_open, self.btn_close):
            row.addWidget(b)
        self.btn_new.clicked.connect(self._new_theme)
        self.btn_dup.clicked.connect(self._duplicate_theme)
        self.btn_ren.clicked.connect(self._rename_theme)
        self.btn_del.clicked.connect(self._delete_theme)
        self.btn_open.clicked.connect(self._open_folder)
        self.btn_close.clicked.connect(self.close)
        bottom.addLayout(row)
        right.addLayout(bottom)

        self._reload()

    # ── data ─────────────────────────────────────────────────────────

    def _reload(self, select_name=None):
        self._loading = True
        self.list.clear()
        self._themes = self._store.list()
        sel = 0
        for i, t in enumerate(self._themes):
            label = t.name + ((' ' + tr('te_builtin'))
                              if t.builtin else '')
            item = QListWidgetItem(
                _strip_icon(t.colors, 60, 12,
                            self.devicePixelRatioF()), label)
            item.setData(Qt.ItemDataRole.UserRole, i)
            self.list.addItem(item)
            if select_name is not None and t.name == select_name:
                sel = i
        self._loading = False
        if self._themes:
            self.list.setCurrentRow(sel)

    def _load_row(self, row):
        if self._loading or not (0 <= row < len(self._themes)):
            return
        t = self._themes[row]
        self._current = t
        self.name_edit.setText(t.name)
        self.name_edit.setEnabled(not t.builtin)
        self.colors.clear()
        dpr = self.devicePixelRatioF()
        for c in t.colors:
            QListWidgetItem(_swatch(c), c, self.colors)
        self.preview.setPixmap(_strip_icon(
            t.colors, _STRIP_W, _STRIP_H, dpr).pixmap(
                QSize(_STRIP_W, _STRIP_H)))
        editable = not t.builtin
        self.hint.setVisible(t.builtin)
        for b in (self.btn_add, self.btn_edit, self.btn_remove,
                  self.btn_up, self.btn_down):
            b.setEnabled(editable)
        self.btn_dup.setEnabled(True)
        self.btn_ren.setEnabled(editable)
        self.btn_del.setEnabled(editable)

    def _changed(self, select_name=None):
        self._reload(select_name)
        if self._on_change is not None:
            self._on_change()

    def _save_current(self):
        if self._current is None or self._current.builtin:
            return
        try:
            self._store.save(self._current, overwrite=True)
        except ThemeError as e:
            QMessageBox.warning(self, tr('te_title'), str(e))
            return
        self._changed(self._current.name)

    # ── colour edits ──────────────────────────────────────────────────

    def _pick_color(self, initial):
        return QColorDialog.getColor(
            QColor(initial), self, tr('tip_choose_colour'),
            options=QColorDialog.ColorDialogOption.DontUseNativeDialog)

    def _add_color(self):
        c = self._pick_color('#000000')
        if c.isValid():
            self._current.colors.append(c.name())
            self._save_current()

    def _edit_color(self):
        row = self.colors.currentRow()
        t = self._current
        if t is None or t.builtin or not (0 <= row < len(t.colors)):
            return
        c = self._pick_color(t.colors[row])
        if c.isValid():
            t.colors[row] = c.name()
            self._save_current()

    def _remove_color(self):
        row = self.colors.currentRow()
        t = self._current
        if t is None or t.builtin or not (0 <= row < len(t.colors)):
            return
        if len(t.colors) <= 1:
            QMessageBox.warning(self, tr('te_title'),
                                tr('te_err_min_colors'))
            return
        del t.colors[row]
        self._save_current()

    def _move_color(self, delta):
        row = self.colors.currentRow()
        t = self._current
        if t is None or t.builtin:
            return
        new = row + delta
        if 0 <= row < len(t.colors) and 0 <= new < len(t.colors):
            t.colors[row], t.colors[new] = t.colors[new], t.colors[row]
            self._save_current()
            self.colors.setCurrentRow(new)

    # ── theme ops ────────────────────────────────────────────────────

    def _unique_name(self, base):
        taken = {t.name for t in self._themes}
        if base not in taken:
            return base
        n = 2
        while '%s (%d)' % (base, n) in taken:
            n += 1
        return '%s (%d)' % (base, n)

    def _new_theme(self):
        from .palettes import THEMES
        name = self._unique_name(tr('te_new_name'))
        t = Theme(name, list(THEMES['default'][:4]))
        try:
            self._store.save(t)
        except ThemeError as e:
            QMessageBox.warning(self, tr('te_title'), str(e))
            return
        self._changed(name)

    def _duplicate_theme(self):
        t = self._current
        if t is None:
            return
        try:
            copy_t = self._store.duplicate(t.name)
        except ThemeError as e:
            QMessageBox.warning(self, tr('te_title'), str(e))
            return
        self._changed(copy_t.name)

    def _rename_theme(self):
        t = self._current
        if t is None or t.builtin:
            return
        name, ok = QInputDialog.getText(
            self, tr('te_title'), tr('te_rename_prompt'), text=t.name)
        if not ok or not name.strip() or name.strip() == t.name:
            return
        old = t.name
        try:
            self._store.rename(old, name.strip())
        except ThemeError as e:
            QMessageBox.warning(self, tr('te_title'), str(e))
            return
        self._changed(name.strip())

    def _commit_name(self):
        t = self._current
        if t is None or t.builtin:
            return
        name = self.name_edit.text().strip()
        if not name or name == t.name:
            self.name_edit.setText(t.name)
            return
        try:
            self._store.rename(t.name, name)
        except ThemeError as e:
            QMessageBox.warning(self, tr('te_title'), str(e))
            self.name_edit.setText(t.name)
            return
        self._changed(name)

    def _delete_theme(self):
        t = self._current
        if t is None or t.builtin:
            return
        box = QMessageBox.question(
            self, tr('te_title'), tr('te_delete_confirm', name=t.name))
        if box != QMessageBox.StandardButton.Yes:
            return
        try:
            self._store.delete(t.name)
        except ThemeError as e:
            QMessageBox.warning(self, tr('te_title'), str(e))
            return
        self._changed()

    def _open_folder(self):
        os.makedirs(self._store.root, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(self._store.root))
