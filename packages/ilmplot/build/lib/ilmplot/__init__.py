"""ilmplot — Qt-free core for ILM's editable ``*.ilmplot.svg`` plots.

A ``*.ilmplot.svg`` is a standard SVG carrying a versioned JSON
:class:`PlotDocument` in ``<metadata id="ilm-plot-document">`` — both the
vector snapshot and the editable source of truth.

This package deliberately keeps import-time cost low: importing
``ilmplot`` pulls in only :mod:`ilmplot.document` (which itself imports
matplotlib lazily). The renderer (:mod:`ilmplot.render`), statistics
helpers (:mod:`ilmplot.stats`), mathtext helpers
(:mod:`ilmplot.mathtext`) and the matplotlib figure bridge
(:mod:`ilmplot.bridge`) load on demand.
"""

from __future__ import annotations

from .document import (
    SCHEMA_VERSION, PlotDocument, PlotDocumentError, load_document,
)

__version__ = '0.1.0'

_LAZY = {
    'save_document': '.render',
    'render_document': '.render',
    'savefig': '.bridge',
    'convert': '.bridge',
    'ConversionResult': '.bridge',
    'SaveResult': '.bridge',
    'UnsupportedFigureError': '.bridge',
    'FallbackWarning': '.bridge',
}


def __getattr__(name):
    target = _LAZY.get(name)
    if target is None:
        raise AttributeError(
            f"module {__name__!r} has no attribute {name!r}")
    import importlib
    value = getattr(importlib.import_module(target, __name__), name)
    globals()[name] = value
    return value


def __dir__():
    return sorted(set(globals()) | set(_LAZY))
