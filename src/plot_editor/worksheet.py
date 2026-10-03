"""In-memory worksheet model for the Plot Editor (pure Python, no Qt)."""

import csv
import io
import math
import re
from dataclasses import dataclass, field

from .i18n import tr

META_FIELDS = ('long_name', 'units', 'comments')
META_LABELS = ('Long Name', 'Units', 'Comments')
META_ROWS = 3
MIN_DATA_ROWS = 32
DESIGNATIONS = ('X', 'Y', 'Z', 'xErr', 'yErr', 'yErrPlus', 'yErrMinus',
                'Label', 'Disregard')
SUFFIX = {'X': 'X', 'Y': 'Y', 'Z': 'Z', 'xErr': 'xEr±', 'yErr': 'yEr±',
          'yErrPlus': 'yEr+', 'yErrMinus': 'yEr-',
          'Label': 'L', 'Disregard': ''}
DESIGNATION_TEXT = {'X': 'X', 'Y': 'Y', 'Z': 'Z', 'xErr': 'X Error',
                    'yErr': 'Y Error', 'yErrPlus': 'Y Error +',
                    'yErrMinus': 'Y Error -', 'Label': 'Label',
                    'Disregard': 'Disregard'}
MAX_COLUMNS = 1024
MAX_PASTE_CELLS = 5_000_000
HISTORY_LIMIT = 1000

_NUMERIC = re.compile(r'[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?')


class WorksheetLimitError(ValueError):
    pass


def column_letters(i):
    """0→A, 25→Z, 26→AA, 701→ZZ, 702→AAA."""
    s = ''
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def parse_cell(text):
    """float for finite numerics, original text otherwise, '' → None."""
    s = text.strip()
    if s == '':
        return None
    if _NUMERIC.fullmatch(s):
        v = float(s)
        if math.isfinite(v):
            return v
    return text


def format_cell(v):
    if v is None:
        return ''
    if isinstance(v, str):
        return v
    if v.is_integer() and abs(v) < 1e16:
        return str(int(v))
    return repr(v)


def column_name(col):
    return column_letters(col)


def parse_tsv(text):
    if text == '':
        return []
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    if text.endswith('\n'):
        text = text[:-1]
    rows = [row for row in csv.reader(io.StringIO(text), delimiter='\t',
                                    quotechar='"')]
    width = max((len(r) for r in rows), default=0)
    for r in rows:
        r.extend([''] * (width - len(r)))
    return rows


def to_tsv(rows):
    out = []
    for row in rows:
        cells = []
        for v in row:
            if any(c in v for c in '\t\n\r"'):
                v = '"' + v.replace('"', '""') + '"'
            cells.append(v)
        out.append('\t'.join(cells))
    return '\n'.join(out)


@dataclass
class Column:
    designation: str = 'Y'
    long_name: str = ''
    units: str = ''
    comments: str = ''
    values: list = field(default_factory=list)


class _CellEdit:
    """Cell patches plus any columns appended by the same edit."""

    def __init__(self, label, patches, appended, appended_at, rect):
        self.label = label
        self.patches = patches
        self.appended = appended
        self.appended_at = appended_at
        self.rect = rect

    def apply(self, ws):
        ws._columns.extend(self.appended)
        for ci, g, _old, new in self.patches:
            ws._raw_set(ci, g, new)

    def revert(self, ws):
        for ci, g, old, _new in self.patches:
            ws._raw_set(ci, g, old)
        if self.appended:
            del ws._columns[len(ws._columns) - len(self.appended):]

    def apply_events(self):
        events = []
        if self.appended:
            events.append(('columns_inserted', self.appended_at,
                           len(self.appended), False))
        events.append(('cells',) + self.rect)
        return events

    def revert_events(self):
        events = []
        if self.appended:
            events.append(('columns_removed', self.appended_at,
                           len(self.appended)))
            c1 = min(self.rect[2], self.appended_at - 1)
            if c1 >= self.rect[0]:
                events.append(('cells', self.rect[0], self.rect[1],
                               c1, self.rect[3]))
        else:
            events.append(('cells',) + self.rect)
        return events


class _RowsInsert:
    def __init__(self, label, at, count, rect):
        self.label = label
        self.at = at
        self.count = count
        self.rect = rect

    def apply(self, ws):
        for col in ws._columns:
            col.values[self.at:self.at] = [None] * self.count
            ws._trim(col)

    def revert(self, ws):
        for col in ws._columns:
            del col.values[self.at:self.at + self.count]

    def apply_events(self):
        return [('rows_inserted', self.at, self.count)]

    def revert_events(self):
        return [('rows_removed', self.at, self.count)]


class _RowsRemove:
    def __init__(self, label, at, count, removed, rect):
        self.label = label
        self.at = at
        self.count = count
        self.removed = removed
        self.rect = rect

    def apply(self, ws):
        for col in ws._columns:
            del col.values[self.at:self.at + self.count]
            ws._trim(col)

    def revert(self, ws):
        for col, chunk in zip(ws._columns, self.removed):
            if chunk:
                while len(col.values) < self.at:
                    col.values.append(None)
                col.values[self.at:self.at] = chunk

    def apply_events(self):
        return [('rows_removed', self.at, self.count)]

    def revert_events(self):
        return [('rows_inserted', self.at, self.count)]


class _ColsInsert:
    def __init__(self, label, at, cols, rect):
        self.label = label
        self.at = at
        self.cols = cols
        self.rect = rect

    def apply(self, ws):
        ws._columns[self.at:self.at] = self.cols

    def revert(self, ws):
        del ws._columns[self.at:self.at + len(self.cols)]

    def apply_events(self):
        return [('columns_inserted', self.at, len(self.cols), True)]

    def revert_events(self):
        return [('columns_removed', self.at, len(self.cols))]


class _ColsRemove:
    def __init__(self, label, removed, rect):
        self.label = label
        self.removed = removed
        self.rect = rect

    def apply(self, ws):
        for i in sorted((i for i, _c in self.removed), reverse=True):
            ws._columns.pop(i)

    def revert(self, ws):
        for i, col in sorted(self.removed):
            ws._columns.insert(i, col)

    def _runs(self):
        runs = []
        for i, _col in self.removed:
            if runs and i == runs[-1][-1] + 1:
                runs[-1].append(i)
            else:
                runs.append([i])
        return runs

    def apply_events(self):
        return [('columns_removed', run[0], len(run))
                for run in reversed(self._runs())]

    def revert_events(self):
        return [('columns_inserted', run[0], len(run), True)
                for run in self._runs()]


class _ReplaceAll:
    """Swap the whole column list (Import → Replace)."""

    def __init__(self, label, old, new, rect):
        self.label = label
        self.old = old
        self.new = new
        self.rect = rect

    def apply(self, ws):
        ws._columns = self.new

    def revert(self, ws):
        ws._columns = self.old

    def apply_events(self):
        return self._events(self.old, self.new)

    def revert_events(self):
        return self._events(self.new, self.old)

    @staticmethod
    def _events(out, into):
        events = []
        if out:
            events.append(('columns_removed', 0, len(out)))
        events.append(('columns_inserted', 0, len(into), True))
        last = max(len(out), len(into)) - 1
        if last >= 0:
            events.append(('header', 0, last))
        return events


class _SetDesignation:
    def __init__(self, label, indices, olds, new, rect):
        self.label = label
        self.indices = indices
        self.olds = olds
        self.new = new
        self.rect = rect

    def apply(self, ws):
        for i in self.indices:
            ws._columns[i].designation = self.new

    def revert(self, ws):
        for i, old in zip(self.indices, self.olds):
            ws._columns[i].designation = old

    def apply_events(self):
        return [('header', min(self.indices), max(self.indices))]

    revert_events = apply_events


class Worksheet:
    """Editable in-memory grid: 3 meta header rows over data rows."""

    def __init__(self):
        self._columns = [Column('X'), Column('Y')]
        self._listeners = []
        self._undo = []
        self._redo = []

    @classmethod
    def from_columns(cls, columns):
        """New worksheet from (copied) ``Column`` objects; empty history."""
        if not columns:
            raise ValueError('A worksheet needs at least one column')
        ws = cls()
        ws._columns = [Column(c.designation, c.long_name, c.units,
                              c.comments, list(c.values))
                       for c in columns]
        return ws

    def column(self, i):
        return self._columns[i]

    @property
    def columns(self):
        return list(self._columns)

    @property
    def column_count(self):
        return len(self._columns)

    @property
    def row_count(self):
        return max((len(c.values) for c in self._columns), default=0)

    def display_rows(self):
        return META_ROWS + max(MIN_DATA_ROWS, self.row_count + 1)

    def value(self, col, row):
        vs = self._columns[col].values
        return vs[row] if row < len(vs) else None

    def header_label(self, col):
        name = column_name(col)
        suffix = SUFFIX[self._columns[col].designation]
        return '%s(%s)' % (name, suffix) if suffix else name

    def grid_text(self, col, g):
        v = self._raw_get(col, g)
        if g < META_ROWS:
            return v
        return format_cell(v)

    def _raw_get(self, ci, g):
        col = self._columns[ci]
        if g < META_ROWS:
            return getattr(col, META_FIELDS[g])
        return self.value(ci, g - META_ROWS)

    def _raw_set(self, ci, g, v):
        col = self._columns[ci]
        if g < META_ROWS:
            setattr(col, META_FIELDS[g], v)
            return
        r = g - META_ROWS
        vs = col.values
        while len(vs) <= r:
            vs.append(None)
        vs[r] = v
        self._trim(col)

    @staticmethod
    def _trim(col):
        while col.values and col.values[-1] is None:
            col.values.pop()

    def add_listener(self, fn):
        self._listeners.append(fn)

    def _emit(self, *events):
        for ev in events:
            for fn in list(self._listeners):
                fn(ev)

    def _record(self, command):
        command.apply(self)
        self._undo.append(command)
        del self._undo[:max(0, len(self._undo) - HISTORY_LIMIT)]
        self._redo.clear()
        self._emit(*command.apply_events(), ('history',))
        return command.rect

    def _fresh_columns(self, count):
        return [Column() for _ in range(count)]

    def set_block(self, col, g, block, label='Edit'):
        if not block:
            return None
        width = max(len(r) for r in block)
        height = len(block)
        if width * height > MAX_PASTE_CELLS:
            raise WorksheetLimitError(
                tr('err_paste_cells', max='{:,}'.format(MAX_PASTE_CELLS)))
        needed = max(0, col + width - self.column_count)
        if self.column_count + needed > MAX_COLUMNS:
            raise WorksheetLimitError(
                tr('err_too_many_cols', max=MAX_COLUMNS))
        appended = self._fresh_columns(needed)
        self._columns.extend(appended)
        patches = []
        for dr, row in enumerate(block):
            for dc in range(width):
                ci = col + dc
                gi = g + dr
                text = row[dc] if dc < len(row) else ''
                new = text if gi < META_ROWS else parse_cell(text)
                old = self._raw_get(ci, gi)
                if new != old:
                    patches.append((ci, gi, old, new))
        if needed:
            del self._columns[len(self._columns) - needed:]
        if not patches and not appended:
            return None
        appended_at = self.column_count
        rect = (col, g, col + width - 1, g + height - 1)
        return self._record(_CellEdit(label, patches, appended,
                                      appended_at, rect))

    def fill(self, rect, text, label='Paste'):
        c0, g0, c1, g1 = rect
        patches = []
        for ci in range(c0, c1 + 1):
            for gi in range(g0, g1 + 1):
                new = text if gi < META_ROWS else parse_cell(text)
                old = self._raw_get(ci, gi)
                if new != old:
                    patches.append((ci, gi, old, new))
        if not patches:
            return None
        return self._record(_CellEdit(label, patches, [], 0, rect))

    def clear(self, rects, label='Clear'):
        patches = []
        for rect in rects:
            c0, g0, c1, g1 = rect
            for ci in range(c0, c1 + 1):
                for gi in range(g0, g1 + 1):
                    old = self._raw_get(ci, gi)
                    new = '' if gi < META_ROWS else None
                    if new != old:
                        patches.append((ci, gi, old, new))
        if not patches:
            return None
        c0 = min(r[0] for r in rects)
        g0 = min(r[1] for r in rects)
        c1 = max(r[2] for r in rects)
        g1 = max(r[3] for r in rects)
        return self._record(_CellEdit(label, patches, [], 0,
                                      (c0, g0, c1, g1)))

    def insert_rows(self, at, count, label='Insert Rows'):
        if count <= 0 or not any(len(c.values) > at for c in self._columns):
            return None
        rect = (0, META_ROWS + at, self.column_count - 1,
                META_ROWS + at + count - 1)
        return self._record(_RowsInsert(label, at, count, rect))

    def remove_rows(self, at, count, label='Delete Rows'):
        if count <= 0 or not any(len(c.values) > at for c in self._columns):
            return None
        removed = [c.values[at:at + count] for c in self._columns]
        rect = (0, META_ROWS + at, self.column_count - 1,
                META_ROWS + at)
        return self._record(_RowsRemove(label, at, count, removed, rect))

    def insert_columns(self, at, count, label='Insert Column'):
        if count <= 0:
            return None
        if self.column_count + count > MAX_COLUMNS:
            raise WorksheetLimitError(
                tr('err_too_many_cols', max=MAX_COLUMNS))
        at = max(0, min(at, self.column_count))
        cols = self._fresh_columns(count)
        rect = (at, 0, at + count - 1, self.display_rows() - 1)
        return self._record(_ColsInsert(label, at, cols, rect))

    def remove_columns(self, indices, label='Delete Column'):
        indices = sorted(set(indices))
        if not indices:
            return None
        if len(indices) >= self.column_count:
            raise ValueError(tr('err_remove_every'))
        removed = [(i, self._columns[i]) for i in indices]
        rect = (indices[0], 0, self.column_count - len(indices) - 1,
                self.display_rows() - 1)
        return self._record(_ColsRemove(label, removed, rect))

    def replace_all(self, columns, label='Import'):
        """Undoably replace every column (import → current sheet)."""
        if not columns:
            raise ValueError(tr('err_remove_every'))
        if len(columns) > MAX_COLUMNS:
            raise WorksheetLimitError(
                tr('err_too_many_cols', max=MAX_COLUMNS))
        new = [Column(c.designation, c.long_name, c.units, c.comments,
                      list(c.values)) for c in columns]
        rows = max((len(c.values) for c in new), default=0)
        rect = (0, 0, len(new) - 1,
                META_ROWS + max(MIN_DATA_ROWS, rows + 1) - 1)
        return self._record(_ReplaceAll(label, self._columns, new, rect))

    def append_columns(self, columns, label='Import'):
        """Undoably append columns to the right of the sheet."""
        if not columns:
            return None
        if self.column_count + len(columns) > MAX_COLUMNS:
            raise WorksheetLimitError(
                tr('err_too_many_cols', max=MAX_COLUMNS))
        cols = [Column(c.designation, c.long_name, c.units, c.comments,
                       list(c.values)) for c in columns]
        at = self.column_count
        rect = (at, 0, at + len(cols) - 1, self.display_rows() - 1)
        return self._record(_ColsInsert(label, at, cols, rect))

    def set_designation(self, cols, designation, label='Set As'):
        if designation not in DESIGNATIONS:
            raise ValueError(
                tr('err_unknown_designation', value=repr(designation)))
        indices = [c for c in cols
                   if self._columns[c].designation != designation]
        if not indices:
            return None
        olds = [self._columns[c].designation for c in indices]
        rect = (min(indices), 0, max(indices), META_ROWS - 1)
        return self._record(_SetDesignation(label, indices, olds,
                                            designation, rect))

    @property
    def can_undo(self):
        return bool(self._undo)

    @property
    def can_redo(self):
        return bool(self._redo)

    @property
    def undo_label(self):
        return self._undo[-1].label if self._undo else ''

    @property
    def redo_label(self):
        return self._redo[-1].label if self._redo else ''

    def undo(self):
        if not self._undo:
            return None
        command = self._undo.pop()
        command.revert(self)
        self._redo.append(command)
        self._emit(*command.revert_events(), ('history',))
        return command.rect

    def redo(self):
        if not self._redo:
            return None
        command = self._redo.pop()
        command.apply(self)
        self._undo.append(command)
        self._emit(*command.apply_events(), ('history',))
        return command.rect
