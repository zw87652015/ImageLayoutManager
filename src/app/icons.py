"""Theme-aware SVG icons loaded from ``assets/icons/``.

Each ``.svg`` file uses ``stroke="currentColor"``, which is valid SVG and
renders correctly in browsers and vector editors.  ``make_icon`` replaces
``currentColor`` with a hex colour string, then wraps the result in a custom
``QIconEngine`` that re-renders the SVG on every paint call using the
widget's own ``QPainter``.

Why QIconEngine instead of pre-baked QPixmaps
----------------------------------------------
``QIconEngine.paint()`` receives the *widget's painter*, which already has
the device-pixel-ratio transform applied by Qt.  Rendering into that painter
is therefore automatically correct for DPR 1.0 (100 % Windows), 1.25, 1.5,
2.0 (macOS Retina / 200 % Windows), or any other value — including when the
window moves between monitors with different DPRs.  No screen-DPR query is
needed at icon-creation time.

``QIconEngine.pixmap()`` is used by menus and other callers that need a
standalone pixmap; it queries the current application DPR at that moment and
renders at the exact physical resolution required.
"""
from __future__ import annotations

import os
import sys

from PyQt6.QtCore import Qt, QByteArray, QRectF, QSize
from PyQt6.QtGui import QIcon, QIconEngine, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer


# ── path helper ──────────────────────────────────────────────────────────────

def _icons_dir() -> str:
    """Absolute path to ``assets/icons/``, works in dev and PyInstaller."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base = sys._MEIPASS
    else:
        base = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "..")
        )
    return os.path.join(base, "assets", "icons")


# ── engine ───────────────────────────────────────────────────────────────────

class _SvgIconEngine(QIconEngine):
    """Renders a recoloured SVG on demand using the caller's painter."""

    def __init__(self, svg_bytes: bytes) -> None:
        super().__init__()
        self._data = QByteArray(svg_bytes)

    # Called when Qt draws an icon inside a widget (toolbar, button, etc.).
    # The painter already has the correct DPR scale transform applied.
    def paint(self, painter: QPainter, rect, mode, state) -> None:
        renderer = QSvgRenderer(self._data)
        renderer.render(painter, QRectF(rect))

    # Called when a standalone pixmap is needed (menus, drag-and-drop, etc.).
    def pixmap(self, size: QSize, mode, state) -> QPixmap:
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance()
        dpr = app.devicePixelRatio() if app else 1.0

        phys_w = max(1, round(size.width()  * dpr))
        phys_h = max(1, round(size.height() * dpr))
        pm = QPixmap(phys_w, phys_h)
        pm.fill(Qt.GlobalColor.transparent)
        pm.setDevicePixelRatio(dpr)

        painter = QPainter(pm)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        renderer = QSvgRenderer(self._data)
        # Render into logical coordinates; the painter scales to physical.
        renderer.render(painter, QRectF(0, 0, size.width(), size.height()))
        painter.end()
        return pm

    def clone(self) -> _SvgIconEngine:
        return _SvgIconEngine(bytes(self._data))


# ── public API ────────────────────────────────────────────────────────────────

def make_icon(name: str, color: str, size: int = 20) -> QIcon:
    """Return a recoloured ``QIcon`` for the named SVG.

    ``name`` must match a file in ``assets/icons/`` (without ``.svg``).
    ``currentColor`` in the file is replaced with ``color`` at call time.

    ``size`` is the logical pixel size passed to ``setIconSize``; with the
    ``-2 -2 20 20`` viewBox the visible glyph is ``size × 0.8`` px (16 px
    for the default ``size=20``).
    """
    svg_path = os.path.join(_icons_dir(), f"{name}.svg")
    try:
        with open(svg_path, "r", encoding="utf-8") as fh:
            svg_text = fh.read()
    except FileNotFoundError:
        return QIcon()

    svg_text = svg_text.replace("currentColor", color)
    return QIcon(_SvgIconEngine(svg_text.encode("utf-8")))


def available_icons() -> list[str]:
    """Names of all icons found in ``assets/icons/``."""
    d = _icons_dir()
    try:
        return [f[:-4] for f in os.listdir(d) if f.endswith(".svg")]
    except OSError:
        return []
