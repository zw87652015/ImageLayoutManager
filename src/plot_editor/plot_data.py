"""Selection → plot series for the Plot Editor (pure Python)."""

import math
from dataclasses import dataclass

from .i18n import tr
from .worksheet import column_name, format_cell


class PlotSelectionError(ValueError):
    pass


@dataclass(frozen=True)
class Series:
    x: tuple
    y: tuple
    label: str
    x_label: str
    y_label: str
    # Categorical x ticks: label text aligned with ``x`` when the chosen
    # X column is a Label column; None for numeric x axes.
    x_ticklabels: tuple | None = None
    # Source Y column index in the worksheet (override key); None for
    # series not built from a worksheet (e.g. document fallbacks).
    y_column: int | None = None
    # Y errors aligned with ``y``; None when the sheet has no yErr
    # column for this series.
    yerr: tuple | None = None
    yerr_minus: tuple | None = None
    yerr_plus: tuple | None = None


def _error_columns(worksheet, y_col):
    """(sym, plus, minus) error column indices for a Y column: the
    first column of each role to its right before the next Y column
    (whole sheet scanned)."""
    sym = plus = minus = None
    for c in range(y_col + 1, worksheet.column_count):
        d = worksheet.column(c).designation
        if d == 'Y':
            break
        if d == 'yErr' and sym is None:
            sym = c
        elif d == 'yErrPlus' and plus is None:
            plus = c
        elif d == 'yErrMinus' and minus is None:
            minus = c
    return sym, plus, minus


def _error_value(worksheet, err_col, row):
    v = worksheet.value(err_col, row)
    return abs(v) if isinstance(v, float) and math.isfinite(v) else 0.0


def tick_label_map(series):
    """Position → tick label across all series (first series wins)."""
    out = {}
    for s in series:
        if not s.x_ticklabels:
            continue
        for pos, text in zip(s.x, s.x_ticklabels):
            out.setdefault(pos, text)
    return out


def _axis_title(column, index):
    title = column.long_name or column_name(index)
    if column.units:
        title += ' (%s)' % column.units
    return title


def _legend_text(column, index):
    comment = column.comments.strip().splitlines()
    return (comment[0].strip() if comment else '') \
        or column.long_name or column_name(index)


def _group_label(column, index):
    """Group/category label: the legend rule, then a *leading* text cell
    (a name typed above the numbers in an Origin-style wide sheet), then
    the letter. A text cell after the first number is just bad data."""
    text = _legend_text(column, index)
    if text != column_name(index):
        return text
    for v in column.values:
        if isinstance(v, str) and v.strip():
            return v
        if isinstance(v, float):
            break
    return text


def build_series(worksheet, selected_columns):
    """One ``Series`` per selected Y column (nearest X to the left)."""
    cols = sorted(set(selected_columns))
    ys = [c for c in cols
          if worksheet.column(c).designation == 'Y']
    if not ys:
        raise PlotSelectionError(tr('err_no_y'))
    xs = [c for c in cols
          if worksheet.column(c).designation in ('X', 'Label')]
    if not xs:
        xs = [i for i in range(worksheet.column_count)
              if worksheet.column(i).designation == 'X']
    series = []
    for yc in ys:
        ycol = worksheet.column(yc)
        xc = max((c for c in xs if c < yc), default=None)
        ec, ecp, ecm = _error_columns(worksheet, yc)
        asymmetric = ecp is not None or ecm is not None
        categorical = xc is not None \
            and worksheet.column(xc).designation == 'Label'
        x_values = []
        y_values = []
        yerr = [] if ec is not None and not asymmetric else None
        yerr_minus = [] if asymmetric else None
        yerr_plus = [] if asymmetric else None
        ticklabels = [] if categorical else None
        for r in range(worksheet.row_count):
            y = worksheet.value(yc, r)
            if not isinstance(y, float):
                continue
            if categorical:
                x = float(r + 1)
                ticklabels.append(format_cell(worksheet.value(xc, r)))
            else:
                x = worksheet.value(xc, r) if xc is not None \
                    else float(r + 1)
                if not isinstance(x, float):
                    continue
            x_values.append(x)
            y_values.append(y)
            if asymmetric:
                sym_v = (_error_value(worksheet, ec, r)
                         if ec is not None else 0.0)
                yerr_minus.append(
                    _error_value(worksheet, ecm, r)
                    if ecm is not None else sym_v)
                yerr_plus.append(
                    _error_value(worksheet, ecp, r)
                    if ecp is not None else sym_v)
            elif ec is not None:
                yerr.append(_error_value(worksheet, ec, r))
        if not x_values:
            continue
        y_label = _axis_title(ycol, yc)
        if xc is not None:
            x_label = _axis_title(worksheet.column(xc), xc)
        else:
            x_label = 'Row'
        series.append(Series(tuple(x_values), tuple(y_values),
                             _legend_text(ycol, yc), x_label, y_label,
                             tuple(ticklabels) if categorical else None,
                             yc,
                             tuple(yerr) if yerr is not None else None,
                             tuple(yerr_minus)
                             if yerr_minus is not None else None,
                             tuple(yerr_plus)
                             if yerr_plus is not None else None))
    if not series:
        raise PlotSelectionError(tr('err_no_numeric'))
    return series


@dataclass(frozen=True)
class Group:
    """One violin group (wide format: one Y column)."""
    values: tuple
    label: str
    x_label: str
    y_label: str
    y_column: int | None = None


@dataclass(frozen=True)
class Category:
    """One stack segment series; ``values[i]`` is its height in bar i."""
    values: tuple
    label: str
    x_label: str
    y_label: str
    bar_labels: tuple = ()
    y_column: int | None = None
    yerr: tuple | None = None
    yerr_minus: tuple | None = None
    yerr_plus: tuple | None = None


def _selected_ys(worksheet, selected_columns):
    cols = sorted({c for c in selected_columns
                   if 0 <= c < worksheet.column_count})
    ys = [c for c in cols
          if worksheet.column(c).designation == 'Y']
    if not ys:
        raise PlotSelectionError(tr('err_no_y'))
    return cols, ys


def _label_column(worksheet, cols, first_y):
    """Bar/group name column: nearest selected Label/X left of the
    first Y, else the nearest Label/X column in the sheet."""
    left = [c for c in cols if c < first_y
            and worksheet.column(c).designation in ('Label', 'X')]
    if left:
        return max(left)
    candidates = [i for i in range(worksheet.column_count)
                  if worksheet.column(i).designation in ('Label', 'X')]
    if not candidates:
        return None
    return min(candidates,
               key=lambda c: (abs(c - first_y), c > first_y))


def build_groups(worksheet, selected_columns):
    """One ``Group`` per selected Y column (violin, wide format)."""
    cols, ys = _selected_ys(worksheet, selected_columns)
    # The x title comes only from a *selected* X/Label column.
    sel = [c for c in cols
           if worksheet.column(c).designation in ('Label', 'X')]
    lc = sel[0] if sel else None
    x_label = _axis_title(worksheet.column(lc), lc) \
        if lc is not None else ''
    groups = []
    for yc in ys:
        col = worksheet.column(yc)
        values = [worksheet.value(yc, r) for r in
                  range(worksheet.row_count)]
        values = tuple(v for v in values if isinstance(v, float))
        if not values:
            continue
        groups.append(Group(values, _group_label(col, yc), x_label,
                            _axis_title(col, yc), yc))
    if not groups:
        raise PlotSelectionError(tr('err_no_numeric'))
    return groups


def build_categories(worksheet, selected_columns):
    """One ``Category`` per selected Y column (stacked column charts).

    Bars are rows where any selected Y is numeric; non-numeric cells
    count as 0 and negatives are clamped to 0.
    """
    cols, ys = _selected_ys(worksheet, selected_columns)
    lc = _label_column(worksheet, cols, ys[0])
    rows = [r for r in range(worksheet.row_count)
            if any(isinstance(worksheet.value(yc, r), float)
                   for yc in ys)]
    if not rows:
        raise PlotSelectionError(tr('err_no_numeric'))
    if lc is not None:
        bar_labels = tuple(format_cell(worksheet.value(lc, r))
                           for r in rows)
        x_label = _axis_title(worksheet.column(lc), lc)
    else:
        bar_labels = tuple(str(i) for i in range(len(rows)))
        x_label = ''
    y_label = _axis_title(worksheet.column(ys[0]), ys[0])
    categories = []
    for yc in ys:
        col = worksheet.column(yc)
        ec, ecp, ecm = _error_columns(worksheet, yc)
        asymmetric = ecp is not None or ecm is not None
        values = []
        yerr = [] if ec is not None and not asymmetric else None
        yerr_minus = [] if asymmetric else None
        yerr_plus = [] if asymmetric else None
        for r in rows:
            v = worksheet.value(yc, r)
            values.append(max(v, 0.0) if isinstance(v, float) else 0.0)
            if asymmetric:
                sym_v = (_error_value(worksheet, ec, r)
                         if ec is not None else 0.0)
                yerr_minus.append(
                    _error_value(worksheet, ecm, r)
                    if ecm is not None else sym_v)
                yerr_plus.append(
                    _error_value(worksheet, ecp, r)
                    if ecp is not None else sym_v)
            elif ec is not None:
                yerr.append(_error_value(worksheet, ec, r))
        categories.append(Category(
            tuple(values), _group_label(col, yc), x_label,
            y_label, bar_labels, yc,
            tuple(yerr) if yerr is not None else None,
            tuple(yerr_minus) if yerr_minus is not None else None,
            tuple(yerr_plus) if yerr_plus is not None else None))
    return categories
