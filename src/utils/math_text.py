"""
Render text containing $...$ LaTeX math expressions to QImage using matplotlib's
built-in mathtext engine (no external LaTeX installation required).

Usage:
    from src.utils.math_text import has_math, render_math_to_qimage, strip_html

    if has_math(text):
        result = render_math_to_qimage(text, font_size_pt=12, ...)
        if result:
            img, width_mm, height_mm = result
"""

import re
from typing import Optional, Tuple

_MATH_RE = re.compile(r'\$[^$\n]+\$')
_HTML_TAG_RE = re.compile(r'<[^>]+>')

# DPI used for canvas thumbnail renders. Export renders use project DPI.
MATH_RENDER_DPI = 200


def strip_html(html: str) -> str:
    """Strip HTML tags and decode common entities to recover plain text."""
    text = _HTML_TAG_RE.sub('', html)
    text = text.replace('&lt;', '<').replace('&gt;', '>')
    text = text.replace('&amp;', '&').replace('&nbsp;', ' ')
    return text.strip()


def has_math(text: str) -> bool:
    """Return True if the plain text contains at least one $...$ expression."""
    return bool(_MATH_RE.search(strip_html(text)))


def render_math_to_qimage(
    text: str,
    font_size_pt: float,
    font_family: str,
    font_weight: str,
    color_hex: str,
    dpi: int = MATH_RENDER_DPI,
) -> Optional[Tuple]:
    """
    Render *text* (which may contain $...$ math) to a QImage.

    Returns (QImage, width_mm, height_mm) on success, or None on failure
    (matplotlib not installed, or empty string).

    width_mm / height_mm are the physical dimensions corresponding to the
    returned image at *dpi* dots-per-inch, so that callers can compute
    correct scene / canvas positions without a second render pass.
    """
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        from io import BytesIO
    except ImportError:
        return None

    plain = strip_html(text)
    if not plain:
        return None

    # --- colour -----------------------------------------------------------
    hex_c = color_hex.lstrip('#')
    if len(hex_c) == 6:
        r = int(hex_c[0:2], 16) / 255.0
        g = int(hex_c[2:4], 16) / 255.0
        b = int(hex_c[4:6], 16) / 255.0
    else:
        r = g = b = 0.0

    # --- render -----------------------------------------------------------
    try:
        fig = plt.figure()
        fig.patch.set_alpha(0.0)

        mpl_family = font_family or 'sans-serif'
        mpl_weight = 'bold' if font_weight == 'bold' else 'normal'

        fig.text(
            0.0, 0.5, plain,
            fontsize=font_size_pt,
            fontfamily=mpl_family,
            fontweight=mpl_weight,
            color=(r, g, b),
            ha='left',
            va='center',
        )

        buf = BytesIO()
        fig.savefig(
            buf,
            format='png',
            transparent=True,
            dpi=dpi,
            bbox_inches='tight',
            pad_inches=0.04,
        )
        plt.close(fig)
        buf.seek(0)

    except Exception as exc:
        print(f"[math_text] render failed: {exc}")
        try:
            plt.close('all')
        except Exception:
            pass
        return None

    from PyQt6.QtGui import QImage
    img = QImage.fromData(bytes(buf.read()))
    if img.isNull():
        return None

    w_mm = img.width() * 25.4 / dpi
    h_mm = img.height() * 25.4 / dpi
    return img, w_mm, h_mm
