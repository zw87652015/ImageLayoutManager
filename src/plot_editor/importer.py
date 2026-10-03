"""Stdlib data-file importers for the Plot Editor (Qt-free).

Delimited text (CSV/TSV/TXT/DAT) and ``.xlsx`` workbooks are read into
``Table`` objects of ``str | float | None`` cells, then ``build_columns``
maps leading header rows onto worksheet meta fields and produces
``worksheet.Column`` objects ready for ``replace_all``/``append_columns``
or ``Worksheet.from_columns``.
"""

import csv
import io
import os
import re
import zipfile
from dataclasses import dataclass, field
from xml.etree import ElementTree as ET

from .i18n import tr
from .worksheet import (MAX_COLUMNS, MAX_PASTE_CELLS, Column,
                        WorksheetLimitError, format_cell, parse_cell)

MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_XLSX_UNCOMPRESSED = 200 * 1024 * 1024
MAX_XLSX_ENTRIES = 10_000
SNIFF_BYTES = 64 * 1024
DELIMITERS = (',', '\t', ';', '|')
WHITESPACE = 'whitespace'
ROLE_ORDER = ('long_name', 'units', 'comments')
_META_SET = frozenset(ROLE_ORDER)

_NS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
_NS_REL = '{http://schemas.openxmlformats.org/officeDocument/2006/' \
          'relationships}'
_NS_PKG_REL = ('{http://schemas.openxmlformats.org/package/2006/'
               'relationships}')
_WS_SPLIT = re.compile(r'[ \t]+')
_CELL_REF = re.compile(r'([A-Za-z]+)(\d+)')


class ImportFileError(ValueError):
    """A data file could not be read; message is translated."""


@dataclass
class Table:
    rows: list = field(default_factory=list)
    sheet_names: tuple = ()
    encoding: str = ''
    delimiter: str = ''


# ── delimited text ─────────────────────────────────────────────────────

def _read_bytes(path, cap):
    try:
        size = os.path.getsize(path)
    except OSError as e:
        raise ImportFileError(tr('err_import_read', error=e)) from e
    if size > cap:
        raise ImportFileError(tr('err_file_too_large',
                                 max='%d MiB' % (cap // 1048576)))
    try:
        with open(path, 'rb') as fh:
            return fh.read(cap + 1)
    except OSError as e:
        raise ImportFileError(tr('err_import_read', error=e)) from e


def _decode(raw, encoding):
    if encoding is not None:
        return raw.decode(encoding), encoding
    for name in ('utf-8-sig', 'gb18030', 'latin-1'):
        try:
            return raw.decode(name), name
        except UnicodeDecodeError:
            continue
    return raw.decode('latin-1', errors='replace'), 'latin-1'


def _ws_columns(lines):
    """Whitespace-split column count, 0 when rows disagree."""
    counts = {len(_WS_SPLIT.split(ln.strip())) for ln in lines}
    return counts.pop() if len(counts) == 1 else 0


def _split_rows(text, delimiter):
    """Split text into raw string rows; returns (rows, used_delimiter)."""
    lines = [ln for ln in text.splitlines() if ln.strip() != '']
    cleaned = '\n'.join(lines)
    used = delimiter
    if used is None:
        try:
            dialect = csv.Sniffer().sniff(cleaned[:SNIFF_BYTES],
                                          delimiters=''.join(DELIMITERS))
            used = dialect.delimiter
        except csv.Error:
            used = WHITESPACE if _ws_columns(lines) >= 2 else ','
        else:
            trial = [r for r in csv.reader(
                io.StringIO(cleaned[:SNIFF_BYTES]), delimiter=used)]
            if all(len(r) <= 1 for r in trial if r) \
                    and _ws_columns(lines) >= 2:
                used = WHITESPACE
    if used == WHITESPACE:
        return [_WS_SPLIT.split(ln.strip()) for ln in lines], used
    return [r for r in csv.reader(io.StringIO(cleaned),
                                  delimiter=used)], used


def _shape(rows):
    """Pad ragged rows, drop trailing empty columns, parse cells."""
    width = max((len(r) for r in rows), default=0)
    while width and all(len(r) < width or r[width - 1].strip() == ''
                        for r in rows):
        width -= 1
    if width > MAX_COLUMNS:
        raise WorksheetLimitError(
            tr('err_too_many_cols', max=MAX_COLUMNS))
    if width * len(rows) > MAX_PASTE_CELLS:
        raise WorksheetLimitError(
            tr('err_paste_cells', max='{:,}'.format(MAX_PASTE_CELLS)))
    out = []
    for r in rows:
        cells = [r[c] if c < len(r) else '' for c in range(width)]
        out.append([parse_cell(c) for c in cells])
    return out


def read_text_table(path, encoding=None, delimiter=None, skip=0):
    raw = _read_bytes(path, MAX_FILE_BYTES)
    text, used_encoding = _decode(raw, encoding)
    lines = text.splitlines()
    if skip:
        lines = lines[max(0, skip):]
    rows, used_delim = _split_rows('\n'.join(lines), delimiter)
    return Table(rows=_shape(rows), encoding=used_encoding,
                 delimiter=used_delim or '')


# ── xlsx ───────────────────────────────────────────────────────────────

def _col_index(letters):
    idx = 0
    for ch in letters:
        idx = idx * 26 + ord(ch.upper()) - 64
    return idx - 1


def _xlsx_shared(zf):
    if 'xl/sharedStrings.xml' not in zf.namelist():
        return []
    root = ET.fromstring(zf.read('xl/sharedStrings.xml'))
    return [''.join(t.text or '' for t in si.iter(_NS + 't'))
            for si in root.findall(_NS + 'si')]


def _xlsx_sheets(zf):
    wb = ET.fromstring(zf.read('xl/workbook.xml'))
    rels = ET.fromstring(zf.read('xl/_rels/workbook.xml.rels'))
    targets = {}
    for rel in rels.findall(_NS_PKG_REL + 'Relationship'):
        target = rel.get('Target', '')
        path = target.lstrip('/') if target.startswith('/') \
            else 'xl/' + target
        targets[rel.get('Id')] = path
    return [(sh.get('name', ''), targets[sh.get(_NS_REL + 'id')])
            for sh in wb.iter(_NS + 'sheet')
            if sh.get(_NS_REL + 'id') in targets]


def _xlsx_cell(c, shared):
    t = c.get('t')
    v = c.find(_NS + 'v')
    if t == 'inlineStr':
        is_ = c.find(_NS + 'is')
        if is_ is None:
            return None
        return parse_cell(''.join(x.text or ''
                                  for x in is_.iter(_NS + 't')))
    if v is None or v.text is None:
        return None
    text = v.text
    if t == 's':
        try:
            return parse_cell(shared[int(text)])
        except (IndexError, ValueError):
            return text
    if t == 'str':
        return parse_cell(text)
    if t == 'b':
        return 'TRUE' if text.strip() in ('1', 'true') else 'FALSE'
    if t == 'e':
        return text
    try:
        return float(text)
    except ValueError:
        return text


def read_xlsx_table(path, sheet=None):
    _read_bytes(path, MAX_FILE_BYTES)
    try:
        zf = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as e:
        raise ImportFileError(tr('err_xls_old')) from e
    with zf:
        infos = zf.infolist()
        if len(infos) > MAX_XLSX_ENTRIES or sum(
                i.file_size for i in infos) > MAX_XLSX_UNCOMPRESSED:
            raise ImportFileError(tr('err_zip_unsafe'))
        try:
            sheets = _xlsx_sheets(zf)
        except (KeyError, ET.ParseError) as e:
            raise ImportFileError(tr('err_import_read', error=e)) from e
        if not sheets:
            raise ImportFileError(tr('err_no_sheets'))
        names = [n for n, _p in sheets]
        if sheet is None:
            target = sheets[0][1]
        else:
            match = [p for n, p in sheets if n == sheet]
            if not match:
                raise ImportFileError(tr('err_unknown_sheet',
                                         value=sheet))
            target = match[0]
        shared = _xlsx_shared(zf)
        try:
            root = ET.fromstring(zf.read(target))
        except (KeyError, ET.ParseError) as e:
            raise ImportFileError(tr('err_import_read', error=e)) from e
    grid = {}
    max_row = max_col = -1
    for c in root.iter(_NS + 'c'):
        ref = c.get('r')
        if not ref:
            continue
        m = _CELL_REF.fullmatch(ref)
        if not m:
            continue
        ci, ri = _col_index(m.group(1)), int(m.group(2)) - 1
        value = _xlsx_cell(c, shared)
        if value is None:
            continue
        grid[(ri, ci)] = value
        max_row = max(max_row, ri)
        max_col = max(max_col, ci)
    width = max_col + 1
    if width > MAX_COLUMNS:
        raise WorksheetLimitError(
            tr('err_too_many_cols', max=MAX_COLUMNS))
    if width * (max_row + 1) > MAX_PASTE_CELLS:
        raise WorksheetLimitError(
            tr('err_paste_cells', max='{:,}'.format(MAX_PASTE_CELLS)))
    rows = [[grid.get((r, c)) for c in range(width)]
            for r in range(max_row + 1)]
    return Table(rows=rows, sheet_names=tuple(names))


# ── header / column mapping ────────────────────────────────────────────

def _mostly_text(row):
    cells = [c for c in row if c not in (None, '')]
    if not cells:
        return False
    return sum(1 for c in cells if isinstance(c, str)) * 2 > len(cells)


def guess_header_rows(rows):
    count = 0
    for row in rows[:3]:
        if not _mostly_text(row):
            break
        count += 1
    return count


def default_roles(n):
    return list(ROLE_ORDER[:n])


def _meta_text(value):
    if value is None:
        return ''
    return value if isinstance(value, str) else format_cell(value)


def build_columns(table, header_rows=0, roles=None, first_column='auto',
                  skip=0):
    rows = table.rows[max(0, skip):]
    header_rows = min(header_rows, len(rows))
    roles = list(roles or [])[:header_rows]
    data = rows[header_rows:]
    width = max((len(r) for r in rows), default=0)
    columns = []
    for ci in range(width):
        col = Column()
        for hr, role in enumerate(roles):
            if role not in _META_SET:
                continue
            value = rows[hr][ci] if ci < len(rows[hr]) else None
            setattr(col, role, _meta_text(value))
        col.values = [None if ci >= len(r) or r[ci] in (None, '')
                      else r[ci] for r in data]
        while col.values and col.values[-1] is None:
            col.values.pop()
        if not col.values:
            continue
        columns.append(col)
    if len(columns) > MAX_COLUMNS:
        raise WorksheetLimitError(
            tr('err_too_many_cols', max=MAX_COLUMNS))
    if not columns:
        raise ImportFileError(tr('err_import_empty'))
    if first_column == 'auto':
        first = columns[0]
        first.designation = 'Label' if first.values and all(
            isinstance(v, str) for v in first.values) else 'X'
    elif first_column in ('X', 'Label', 'Y'):
        columns[0].designation = first_column
    return columns


def read_table(path, sheet=None, encoding=None, delimiter=None, skip=0):
    """Dispatch on extension: xlsx workbooks vs delimited text."""
    if os.path.splitext(path)[1].lower() == '.xlsx':
        return read_xlsx_table(path, sheet=sheet)
    return read_text_table(path, encoding=encoding, delimiter=delimiter,
                           skip=skip)
