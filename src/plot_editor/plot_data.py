"""Selection → plot series for the Plot Editor (pure Python)."""

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
        categorical = xc is not None \
            and worksheet.column(xc).designation == 'Label'
        x_values = []
        y_values = []
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
                             yc))
    if not series:
        raise PlotSelectionError(tr('err_no_numeric'))
    return series
