"""Import Data dialog for the Plot Editor.

Previews a delimited-text or ``.xlsx`` file through the Qt-free readers
in ``importer.py``, lets the user map header rows onto worksheet meta
fields, and applies the result as Replace / Append / New tab.
"""

import os

from PyQt6.QtCore import QAbstractTableModel, QModelIndex, QTimer, Qt
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox,
                             QFormLayout, QGroupBox, QHBoxLayout,
                             QLabel, QRadioButton, QSpinBox,
                             QTableView, QVBoxLayout)

from . import importer
from .chrome import style_tokens
from .i18n import tr
from .worksheet import column_name, format_cell

_DATA_EXTENSIONS = ('.csv', '.tsv', '.txt', '.dat', '.xlsx')
_PREVIEW_ROWS = 50
_DELIMS = (None, ',', '\t', ';', '|', importer.WHITESPACE)
_DELIM_KEYS = (None, 'imp_delim_comma', 'imp_delim_tab',
               'imp_delim_semicolon', 'imp_delim_pipe',
               'imp_delim_whitespace')
_ENCODINGS = (None, 'utf-8', 'gb18030', 'latin-1')
_FIRST_COL = ('auto', 'X', 'Label', 'Y')
_ROLES = ('long_name', 'units', 'comments', 'ignore')
_ROLE_KEYS = ('meta_long_name', 'meta_units', 'meta_comments',
              'role_ignore')


def is_data_path(path):
    return os.path.splitext(path)[1].lower() in _DATA_EXTENSIONS


class _PreviewModel(QAbstractTableModel):
    """First ``_PREVIEW_ROWS`` rows; header rows drawn muted."""

    def __init__(self, muted, parent=None):
        super().__init__(parent)
        self._rows = []
        self._header_rows = 0
        self._muted = QBrush(QColor(muted))

    def set_data(self, rows, header_rows):
        self.beginResetModel()
        self._rows = rows
        self._header_rows = header_rows
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else min(len(self._rows),
                                              _PREVIEW_ROWS)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else max(
            (len(r) for r in self._rows), default=0)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            row = self._rows[index.row()]
            value = row[index.column()] if index.column() < len(row) \
                else None
            return '' if value is None else format_cell(value) \
                if not isinstance(value, str) else value
        if role == Qt.ItemDataRole.ForegroundRole \
                and index.row() < self._header_rows:
            return self._muted
        return None

    def headerData(self, section, orientation, role=None):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return column_name(section)
        return str(section + 1)


class ImportDialog(QDialog):
    """Pick import options, preview the result, choose a destination.

    On accept, ``columns`` holds the imported ``Column`` list and
    ``destination`` is 'replace' | 'append' | 'new_tab'.
    """

    def __init__(self, path, has_data, theme, scale, parent=None):
        super().__init__(parent)
        self.path = path
        self.columns = None
        self.destination = 'replace'
        self._tokens = style_tokens(theme, scale)
        self._is_xlsx = os.path.splitext(path)[1].lower() == '.xlsx'
        self._table = importer.Table()
        self._role_combos = []
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(150)
        self._debounce.timeout.connect(self._reload)

        self.setWindowTitle(tr('dlg_import'))
        layout = QVBoxLayout(self)
        form = QFormLayout()

        if self._is_xlsx:
            self.sheet_combo = QComboBox(self)
            self.sheet_combo.setToolTip(tr('imp_xlsx_note'))
            self.sheet_combo.currentIndexChanged.connect(
                self._schedule)
            form.addRow(tr('imp_sheet'), self.sheet_combo)
        else:
            self.delim_combo = QComboBox(self)
            self.delim_combo.addItem(tr('imp_auto', value='—'))
            for key in _DELIM_KEYS[1:]:
                self.delim_combo.addItem(tr(key))
            self.delim_combo.currentIndexChanged.connect(self._schedule)
            form.addRow(tr('imp_delimiter'), self.delim_combo)
            self.encoding_combo = QComboBox(self)
            self.encoding_combo.addItem(tr('imp_auto', value='—'))
            for name in ('UTF-8', 'GB18030', 'Latin-1'):
                self.encoding_combo.addItem(name)
            self.encoding_combo.currentIndexChanged.connect(
                self._schedule)
            form.addRow(tr('imp_encoding'), self.encoding_combo)

        self.skip_spin = QSpinBox(self)
        self.skip_spin.setRange(0, 1000)
        if self._is_xlsx:
            self.skip_spin.setVisible(False)
        else:
            self.skip_spin.valueChanged.connect(self._schedule)
            form.addRow(tr('imp_skip_lines'), self.skip_spin)

        self.header_spin = QSpinBox(self)
        self.header_spin.setRange(0, 3)
        self.header_spin.valueChanged.connect(self._header_changed)
        form.addRow(tr('imp_header_rows'), self.header_spin)

        self._role_box = QGroupBox(self)
        self._role_layout = QHBoxLayout(self._role_box)
        self._role_layout.setContentsMargins(0, 0, 0, 0)
        form.addRow(self._role_box)
        self._role_box.hide()

        self.first_col_combo = QComboBox(self)
        for i, value in enumerate(_FIRST_COL):
            label = tr('imp_auto', value='—') if value == 'auto' \
                else tr('design_label') if value == 'Label' else value
            self.first_col_combo.addItem(label, value)
        form.addRow(tr('imp_first_column'), self.first_col_combo)

        layout.addLayout(form)

        self.preview = QTableView(self)
        self.preview.setObjectName('importPreview')
        self._model = _PreviewModel(self._tokens['text_tert'], self)
        self.preview.setModel(self._model)
        layout.addWidget(self.preview)

        self.error_label = QLabel(self)
        self.error_label.setStyleSheet(
            'color: %s;' % self._tokens['danger'])
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        layout.addWidget(self.error_label)

        dest_box = QGroupBox(tr('imp_destination'), self)
        dest_layout = QVBoxLayout(dest_box)
        self.dest_replace = QRadioButton(tr('imp_dest_replace'), dest_box)
        self.dest_append = QRadioButton(tr('imp_dest_append'), dest_box)
        self.dest_new_tab = QRadioButton(tr('imp_dest_new_tab'), dest_box)
        for radio in (self.dest_replace, self.dest_append,
                      self.dest_new_tab):
            dest_layout.addWidget(radio)
        (self.dest_new_tab if has_data else self.dest_replace
         ).setChecked(True)
        layout.addWidget(dest_box)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel, self)
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)

        self._reload(initial=True)

    # ── option plumbing ──────────────────────────────────────────────
    def _schedule(self, *_args):
        self._debounce.start()

    def _header_changed(self, *_args):
        self._refresh_roles()
        self._refresh_preview()

    def _encoding_value(self):
        if self._is_xlsx:
            return None
        return _ENCODINGS[self.encoding_combo.currentIndex()]

    def _delimiter_value(self):
        if self._is_xlsx:
            return None
        return _DELIMS[self.delim_combo.currentIndex()]

    def _sheet_value(self):
        if not self._is_xlsx:
            return None
        return self.sheet_combo.currentText()

    # ── file reading / preview ───────────────────────────────────────
    def _reload(self, initial=False):
        try:
            self._table = importer.read_table(
                self.path, sheet=self._sheet_value() if not initial
                else None,
                encoding=self._encoding_value(),
                delimiter=self._delimiter_value(),
                skip=0 if self._is_xlsx else self.skip_spin.value())
        except (importer.ImportFileError, ValueError, OSError) as e:
            self._table = importer.Table()
            self._show_error(str(e))
            return
        self._show_error('')
        if initial:
            if self._is_xlsx:
                self.sheet_combo.clear()
                self.sheet_combo.addItems(self._table.sheet_names)
            self.header_spin.setValue(
                importer.guess_header_rows(self._table.rows))
            self._set_default_roles()
        else:
            self._update_auto_items()
        self._refresh_roles()
        self._refresh_preview()

    def _update_auto_items(self):
        if self._is_xlsx:
            return
        delim = self._table.delimiter
        label = {',': tr('imp_delim_comma'), '\t': tr('imp_delim_tab'),
                 ';': tr('imp_delim_semicolon'), '|': tr('imp_delim_pipe'),
                 importer.WHITESPACE: tr('imp_delim_whitespace')
                 }.get(delim, '—')
        self.delim_combo.setItemText(0, tr('imp_auto', value=label))
        enc = {'utf-8-sig': 'UTF-8', 'gb18030': 'GB18030',
               'latin-1': 'Latin-1'}.get(self._table.encoding, '—')
        self.encoding_combo.setItemText(0, tr('imp_auto', value=enc))

    def _set_default_roles(self):
        for i, role in enumerate(
                importer.default_roles(self.header_spin.value())):
            if i < len(self._role_combos):
                self._role_combos[i][1].setCurrentIndex(
                    _ROLES.index(role))

    def _refresh_roles(self):
        count = self.header_spin.value()
        while len(self._role_combos) < count:
            i = len(self._role_combos)
            caption = QLabel(tr('imp_header_role', n=i + 1),
                             self._role_box)
            combo = QComboBox(self._role_box)
            for key in _ROLE_KEYS:
                combo.addItem(tr(key))
            combo.currentIndexChanged.connect(self._refresh_preview)
            self._role_layout.addWidget(caption)
            self._role_layout.addWidget(combo)
            self._role_combos.append((caption, combo))
        for i, (caption, combo) in enumerate(self._role_combos):
            caption.setVisible(i < count)
            combo.setVisible(i < count)
        self._role_box.setVisible(count > 0)

    def _show_error(self, text):
        self.error_label.setText(text)
        self.error_label.setVisible(bool(text))
        self._buttons.button(
            QDialogButtonBox.StandardButton.Ok).setEnabled(not text)

    def _refresh_preview(self):
        self._model.set_data(self._table.rows, self.header_spin.value())

    # ── accept ───────────────────────────────────────────────────────
    def accept(self):
        roles = [_ROLES[c.currentIndex()] for _cap, c in
                 self._role_combos[:self.header_spin.value()]]
        try:
            columns = importer.build_columns(
                self._table,
                header_rows=self.header_spin.value(),
                roles=roles,
                first_column=self.first_col_combo.currentData())
        except (importer.ImportFileError, ValueError) as e:
            self._show_error(str(e))
            return
        self.columns = columns
        if self.dest_append.isChecked():
            self.destination = 'append'
        elif self.dest_new_tab.isChecked():
            self.destination = 'new_tab'
        else:
            self.destination = 'replace'
        super().accept()
