"""ILM Plot Editor — standalone editable line-plot documents.

The native document is a self-contained SVG (``*.ilmplot.svg``) that embeds
a versioned JSON payload inside ``<metadata id="ilm-plot-document">`` so the
same file is both the vector snapshot and the editable source of truth.

Core modules (:mod:`document`, :mod:`render`, :mod:`matplotlib_bridge`)
have no Qt or ILM project dependencies. UI modules live in
:mod:`src.plot_editor.window` / :mod:`src.plot_editor.app`.
"""
