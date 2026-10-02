"""matplotlib figure building for the Plot Editor (no Qt, no pyplot)."""

import io

from matplotlib.figure import Figure
from matplotlib.backends.backend_svg import FigureCanvasSVG

from .mathtext import safe_text
from .plot_data import tick_label_map

_CHART_KEYS = {'pure_line', 'pure_scatters', 'line_scatters',
               'stacked_line'}


def stack_offsets(series):
    """Per-series vertical offsets so each curve sits above the previous."""
    offsets = [0.0]
    for i in range(1, len(series)):
        offsets.append(max(series[i - 1].y) + offsets[i - 1]
                       - min(series[i].y))
    return offsets


def make_figure(series, chart_key, title=''):
    """Render ``series`` as the named chart; returns a ``Figure``."""
    if chart_key not in _CHART_KEYS:
        raise ValueError('Unknown chart type %r' % chart_key)
    fig = Figure()
    FigureCanvasSVG(fig)
    ax = fig.add_subplot(111)
    offsets = stack_offsets(series)
    for i, s in enumerate(series):
        y = s.y
        if chart_key == 'stacked_line' and i > 0:
            y = tuple(v + offsets[i] for v in y)
        label = s.label if len(series) > 1 else None
        if label is not None:
            label = safe_text(label)
        if chart_key == 'pure_scatters':
            ax.scatter(s.x, y, label=label)
        elif chart_key == 'line_scatters':
            ax.plot(s.x, y, marker='o', label=label)
        else:
            ax.plot(s.x, y, label=label)
    ticks = tick_label_map(series)
    if ticks:
        positions = sorted(ticks)
        ax.set_xticks(positions,
                      [safe_text(ticks[p]) for p in positions])
    ax.set_xlabel(safe_text(series[0].x_label))
    ax.set_ylabel(safe_text(series[0].y_label))
    if title:
        ax.set_title(safe_text(title))
    if len(series) > 1:
        ax.legend()
    return fig


def figure_svg(fig):
    """Serialize ``fig`` to SVG bytes without touching pyplot."""
    buf = io.BytesIO()
    fig.savefig(buf, format='svg')
    return buf.getvalue()
