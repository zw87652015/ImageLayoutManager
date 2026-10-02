"""Selection → plot series for the Plot Editor (pure Python)."""

from dataclasses import dataclass

from .worksheet import column_name


class PlotSelectionError(ValueError):
    pass


@dataclass(frozen=True)
class Series:
    x: tuple
    y: tuple
    label: str
    x_label: str
    y_label: str


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
        raise PlotSelectionError(
            'Select at least one Y column to plot.')
    xs = [c for c in cols
          if worksheet.column(c).designation == 'X']
    if not xs:
        xs = [i for i in range(worksheet.column_count)
              if worksheet.column(i).designation == 'X']
    series = []
    for yc in ys:
        ycol = worksheet.column(yc)
        xc = max((c for c in xs if c < yc), default=None)
        x_values = []
        y_values = []
        for r in range(worksheet.row_count):
            y = worksheet.value(yc, r)
            if not isinstance(y, float):
                continue
            x = worksheet.value(xc, r) if xc is not None else float(r + 1)
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
                             _legend_text(ycol, yc), x_label, y_label))
    if not series:
        raise PlotSelectionError(
            'The selected columns contain no numeric data.')
    return series
