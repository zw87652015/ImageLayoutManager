"""Plot export: native ILM Plot documents and matplotlib formats (no Qt)."""

import os
import tempfile

from matplotlib.colors import to_hex

from .document import LineSeries, PlotDocument
from .i18n import tr
from .plot_data import tick_label_map
from .plotting import stack_offsets
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


def document_from_plot(series, chart_key, title=''):
    """Build a validated ``PlotDocument`` from plot ``series``."""
    if chart_key not in _STYLE:
        raise ValueError(tr('err_unknown_chart', value=repr(chart_key)))
    linestyle, marker = _STYLE[chart_key]
    offsets = stack_offsets(series)
    doc = PlotDocument()
    doc.title = title
    doc.xlabel = series[0].x_label
    doc.ylabel = series[0].y_label
    ticks = tick_label_map(series)
    doc.x_tick_labels = [[p, ticks[p]] for p in sorted(ticks)] or None
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


def export_plot(document, path, key):
    """Atomically write *document* in format *key* to *path*.

    Everything goes through the native renderer: ``ilmplot`` embeds the
    document metadata; other formats use ``render.export_document`` so
    exports match the preview exactly.
    """
    if key == 'ilmplot':
        render.save_document(document, path)
        return
    if key not in EXPORT_FORMATS:
        raise ValueError(tr('err_unknown_export', value=repr(key)))
    fmt = 'jpeg' if key == 'jpg' else key
    render.export_document(document, path, fmt, dpi=RASTER_DPI)
