"""Qt-side math rendering: ``$...$`` text → ``QPixmap`` via mathtext.

Uses a bare ``Figure`` + ``FigureCanvasAgg`` (no pyplot). Returns ``None``
on any failure so callers can fall back to plain text. Results are cached
in an LRU keyed by the text and the visual parameters.
"""

import functools

from PyQt6.QtGui import QFont, QImage, QPixmap

from .mathtext import safe_text


@functools.lru_cache(maxsize=512)
def _render_png(text, family, size_pt, weight, rgba, dpr):
    """Render *text* (already sanitized) to PNG bytes at ``96 * dpr`` dpi."""
    import io

    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg

    fig = Figure()
    FigureCanvasAgg(fig)
    fig.patch.set_alpha(0.0)
    color = ((rgba >> 16 & 0xFF) / 255, (rgba >> 8 & 0xFF) / 255,
             (rgba & 0xFF) / 255, (rgba >> 24 & 0xFF) / 255)
    fig.text(0.0, 0.5, text, fontsize=size_pt,
             fontfamily=family or 'sans-serif',
             fontweight='bold' if weight else 'normal',
             color=color, ha='left', va='center')
    buf = io.BytesIO()
    fig.savefig(buf, format='png', transparent=True, dpi=96 * dpr,
                bbox_inches='tight', pad_inches=0.02)
    fig.clear()
    return buf.getvalue()


def math_pixmap(text, font, color, dpr):
    """Render *text* with math to a ``QPixmap``, or ``None`` on failure.

    *font* supplies the family/size/weight for the non-math text (a Qt
    pixel size is converted at 72/96 to match the cell font visually).
    The pixmap's device pixel ratio is set to *dpr*.
    """
    if not text:
        return None
    size_pt = font.pointSizeF()
    if size_pt <= 0:
        # pixelSize fonts: px at 96 dpi → pt.
        px = font.pixelSize()
        size_pt = px * 72.0 / 96.0 if px > 0 else 10.0
    weight = font.weight() > QFont.Weight.Medium
    rgba = (color.alpha() << 24) | (color.red() << 16) \
        | (color.green() << 8) | color.blue()
    try:
        family = font.family()
        from .render import available_font_families
        if family not in available_font_families():
            family = None
        png = _render_png(safe_text(text), family, size_pt,
                          weight, rgba, float(dpr or 1.0))
        img = QImage.fromData(png)
        if img.isNull():
            return None
        pm = QPixmap.fromImage(img)
        pm.setDevicePixelRatio(float(dpr or 1.0))
        return pm
    except Exception:
        return None
