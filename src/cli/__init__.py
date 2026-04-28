"""Command-line entry points for ImageLayoutManager.

The CLI reuses the GUI's exporters verbatim (PdfExporter, ImageExporter)
so output is byte-for-byte identical to File > Export. It runs Qt under
the ``offscreen`` platform plugin — no display server required.
"""
