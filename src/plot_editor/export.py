"""Plot export: native ILM Plot documents and matplotlib formats (no Qt)."""

import os
import tempfile

from matplotlib.colors import to_hex

from .document import LineSeries, PlotDocument
from .plotting import make_figure, stack_offsets
from . import render

EXPORT_FORMATS = {
    'ilmplot': ('ILM Plot (*.ilmplot.svg)', '.ilmplot.svg'),
    'pdf': ('PDF (*.pdf)', '.pdf'),
    'svg': ('SVG (*.svg)', '.svg'),
    'png': ('PNG (*.png)', '.png'),
    'tiff': ('TIFF (*.tif *.tiff)', '.tif'),
    'jpg': ('JPEG (*.jpg *.jpeg)', '.jpg'),
}
RASTER_DPI = 300

_ACCEPTED = {
    'ilmplot': ('.ilmplot.svg',),
    'pdf': ('.pdf',),
    'svg': ('.svg',),
    'png': ('.png',),
    'tiff': ('.tif', '.tiff'),
    'jpg': ('.jpg', '.jpeg'),
}

_STYLE = {
    'pure_line': ('-', ''),
    'pure_scatters': ('', 'o'),
    'line_scatters': ('-', 'o'),
    'stacked_line': ('-', ''),
}


def with_suffix(path, key):
    """Return *path* with the format's suffix appended when missing."""
    accepted = _ACCEPTED[key]
    lower = path.lower()
    if not lower.endswith(accepted):
        if key == 'ilmplot' and lower.endswith('.svg'):
            path = path[:-4]
        path += EXPORT_FORMATS[key][1]
    return path


def document_from_plot(series, chart_key):
    """Build a validated ``PlotDocument`` from plot ``series``."""
    if chart_key not in _STYLE:
        raise ValueError('Unknown chart type %r' % chart_key)
    linestyle, marker = _STYLE[chart_key]
    offsets = stack_offsets(series)
    doc = PlotDocument()
    doc.xlabel = series[0].x_label
    doc.ylabel = series[0].y_label
    doc.legend = len(series) > 1
    doc.series = []
    for i, s in enumerate(series):
        y = s.y
        if chart_key == 'stacked_line' and i > 0:
            y = tuple(v + offsets[i] for v in y)
        doc.series.append(LineSeries(
            id='s%d' % i, label=s.label,
            x=list(s.x), y=list(y),
            color=to_hex('C%d' % (i % 10)),
            linewidth_pt=1.5, linestyle=linestyle, marker=marker,
            markersize_pt=6.0))
    return doc.validate()


def _atomic_write(path, write):
    """Write to a temp sibling, fsync, then ``os.replace`` into place."""
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=parent,
                               prefix='.' + os.path.basename(path),
                               suffix='.tmp')
    try:
        with os.fdopen(fd, 'wb') as fh:
            write(fh)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def export_plot(series, chart_key, path, key):
    """Atomically write the plot in format *key* to *path*."""
    if key == 'ilmplot':
        render.save_document(document_from_plot(series, chart_key), path)
        return
    if key not in EXPORT_FORMATS:
        raise ValueError('Unknown export format %r' % key)
    fig = make_figure(series, chart_key)
    if key in ('pdf', 'svg'):
        kwargs = {'format': key, 'metadata': {'Date': None}}
    else:
        fmt = 'jpeg' if key == 'jpg' else key
        kwargs = {'format': fmt, 'dpi': RASTER_DPI}

    def _write(fh):
        fig.savefig(fh, **kwargs)

    _atomic_write(path, _write)
