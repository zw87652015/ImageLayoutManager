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
_STYLE_RE = re.compile(r'<style[^>]*>.*?</style>', re.IGNORECASE | re.DOTALL)
_HTML_TAG_RE = re.compile(r'<[^>]+>')

# DPI used for canvas thumbnail renders. Export renders use project DPI.
MATH_RENDER_DPI = 200


def strip_html(html: str) -> str:
    """Strip HTML tags and decode common entities to recover plain text."""
    text = _STYLE_RE.sub('', html)
    text = _HTML_TAG_RE.sub('', text)
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
        # Emit a one-time warning so silent fallback is discoverable.
        global _MPL_WARNED
        try:
            _MPL_WARNED  # type: ignore[name-defined]
        except NameError:
            _MPL_WARNED = True
            import sys
            print(
                "[math_text] matplotlib is not installed — LaTeX $...$ math "
                "rendering is disabled. Install with: pip install matplotlib",
                file=sys.stderr,
            )
        return None

    plain = strip_html(text)
    if not plain:
        return None

    # mathtext (matplotlib's built-in parser) supports a subset of LaTeX and
    # doesn't know a few common "logo" macros. Rewrite them inside $...$
    # segments so typing $\LaTeX$ doesn't explode.
    def _preprocess_math(s: str) -> str:
        def fix(seg: str) -> str:
            return (seg
                    .replace(r'\LaTeXe', r'\mathrm{LaTeX\,2\epsilon}')
                    .replace(r'\LaTeX',  r'\mathrm{LaTeX}')
                    .replace(r'\TeX',    r'\mathrm{TeX}'))
        return _MATH_RE.sub(lambda m: fix(m.group(0)), s)

    plain = _preprocess_math(plain)

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
        # mathtext couldn't parse — retry once with math markers stripped so
        # the user gets a readable (if un-formatted) fallback rather than
        # losing the entire text item.
        print(f"[math_text] render failed: {exc} — retrying without math mode")
        try:
            plt.close('all')
        except Exception:
            pass
        fallback = _MATH_RE.sub(lambda m: m.group(0).strip('$'), plain)
        try:
            fig = plt.figure()
            fig.patch.set_alpha(0.0)
            fig.text(
                0.0, 0.5, fallback,
                fontsize=font_size_pt,
                fontfamily=mpl_family,
                fontweight=mpl_weight,
                color=(r, g, b),
                ha='left',
                va='center',
            )
            buf = BytesIO()
            fig.savefig(buf, format='png', transparent=True, dpi=dpi,
                        bbox_inches='tight', pad_inches=0.04)
            plt.close(fig)
            buf.seek(0)
        except Exception as exc2:
            print(f"[math_text] fallback render failed: {exc2}")
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


def render_math_to_pdf_bytes(
    text: str,
    font_size_pt: float,
    font_family: str,
    font_weight: str,
    color_hex: str,
) -> Optional[Tuple[bytes, float, float]]:
    """
    Render *text* (which may contain $...$ math) to a one-page PDF as bytes
    using matplotlib's native PDF backend.

    Returns (pdf_bytes, width_mm, height_mm) on success or None on failure.

    This is what the violin_plot_generator script uses under the hood
    (fig.savefig(..., format='pdf')) — it produces fully-vector text/paths
    including mathtext glyphs outlined via pdf.fonttype=42.
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

    # Same \LaTeX / \TeX preprocessing used elsewhere
    def _preprocess_math(s: str) -> str:
        def fix(seg: str) -> str:
            return (seg
                    .replace(r'\LaTeXe', r'\mathrm{LaTeX\,2\epsilon}')
                    .replace(r'\LaTeX',  r'\mathrm{LaTeX}')
                    .replace(r'\TeX',    r'\mathrm{TeX}'))
        return _MATH_RE.sub(lambda m: fix(m.group(0)), s)

    plain = _preprocess_math(plain)

    # --- colour -----------------------------------------------------------
    hex_c = color_hex.lstrip('#')
    if len(hex_c) == 6:
        r = int(hex_c[0:2], 16) / 255.0
        g = int(hex_c[2:4], 16) / 255.0
        b = int(hex_c[4:6], 16) / 255.0
    else:
        r = g = b = 0.0

    mpl_family = font_family or 'sans-serif'
    mpl_weight = 'bold' if font_weight == 'bold' else 'normal'

    # pdf.fonttype = 42 -> TrueType font embedding (vector glyphs)
    rc_params = {'pdf.fonttype': 42, 'text.usetex': False}

    def _render(body: str) -> Optional[bytes]:
        try:
            with plt.rc_context(rc_params):
                fig = plt.figure()
                fig.patch.set_alpha(0.0)
                fig.text(
                    0.0, 0.5, body,
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
                    format='pdf',
                    transparent=True,
                    bbox_inches='tight',
                    pad_inches=0.02,
                )
                plt.close(fig)
                return buf.getvalue()
        except Exception as exc:
            print(f"[math_text] pdf render failed: {exc}")
            try:
                plt.close('all')
            except Exception:
                pass
            return None

    pdf_bytes = _render(plain)
    if pdf_bytes is None:
        # Retry with math mode stripped
        fallback = _MATH_RE.sub(lambda m: m.group(0).strip('$'), plain)
        pdf_bytes = _render(fallback)
        if pdf_bytes is None:
            return None

    # Measure page size via PyMuPDF
    try:
        import fitz
        doc = fitz.open(stream=pdf_bytes, filetype='pdf')
        rect = doc[0].rect
        w_pt = rect.width
        h_pt = rect.height
        doc.close()
    except Exception as exc:
        print(f"[math_text] pdf measure failed: {exc}")
        return None

    w_mm = w_pt * 25.4 / 72.0
    h_mm = h_pt * 25.4 / 72.0
    return pdf_bytes, w_mm, h_mm


def render_math_to_svg(
    text: str,
    font_size_pt: float,
    font_family: str,
    font_weight: str,
    color_hex: str,
) -> Optional[Tuple[bytes, float, float]]:
    """
    Render *text* (which may contain $...$ math) to SVG bytes.

    Returns (svg_bytes, width_mm, height_mm) on success, or None on failure.
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

    def _preprocess_math(s: str) -> str:
        def fix(seg: str) -> str:
            return (seg
                    .replace(r'\LaTeXe', r'\mathrm{LaTeX\,2\epsilon}')
                    .replace(r'\LaTeX',  r'\mathrm{LaTeX}')
                    .replace(r'\TeX',    r'\mathrm{TeX}'))
        return _MATH_RE.sub(lambda m: fix(m.group(0)), s)

    plain = _preprocess_math(plain)

    hex_c = color_hex.lstrip('#')
    if len(hex_c) == 6:
        r = int(hex_c[0:2], 16) / 255.0
        g = int(hex_c[2:4], 16) / 255.0
        b = int(hex_c[4:6], 16) / 255.0
    else:
        r = g = b = 0.0

    mpl_family = font_family or 'sans-serif'
    mpl_weight = 'bold' if font_weight == 'bold' else 'normal'

    rc_params = {'svg.fonttype': 'path', 'text.usetex': False}

    try:
        with plt.rc_context(rc_params):
            fig = plt.figure()
            fig.patch.set_alpha(0.0)
    
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
                format='svg',
                transparent=True,
                bbox_inches='tight',
                pad_inches=0.04,
            )
            plt.close(fig)
            buf.seek(0)
    except Exception as exc:
        print(f"[math_text] svg render failed: {exc} — retrying without math mode")
        try:
            plt.close('all')
        except Exception:
            pass
        fallback = _MATH_RE.sub(lambda m: m.group(0).strip('$'), plain)
        try:
            with plt.rc_context(rc_params):
                fig = plt.figure()
                fig.patch.set_alpha(0.0)
                fig.text(
                    0.0, 0.5, fallback,
                    fontsize=font_size_pt,
                    fontfamily=mpl_family,
                    fontweight=mpl_weight,
                    color=(r, g, b),
                    ha='left',
                    va='center',
                )
                buf = BytesIO()
                fig.savefig(buf, format='svg', transparent=True,
                            bbox_inches='tight', pad_inches=0.04)
                plt.close(fig)
                buf.seek(0)
        except Exception as exc2:
            print(f"[math_text] fallback svg render failed: {exc2}")
            try:
                plt.close('all')
            except Exception:
                pass
            return None

    svg_bytes = buf.read()
    
    import re

    svg_str = svg_bytes.decode('utf-8')

    # 1. Qt's QSvgRenderer strictly requires valid path commands. Matplotlib
    # often generates empty paths (d="") or omits d entirely for space glyphs
    # (e.g. #ArialMT-20), causing Qt to throw "Invalid path data" and spam
    # "link #… is undefined!" warnings. Normalise both cases to d="M0,0".
    svg_str = re.sub(r'd="\s*"', 'd="M0,0"', svg_str)
    def _inject_d(m):
        tag = m.group(0)
        return tag if ' d="' in tag else tag[:-2] + ' d="M0,0"/>'
    svg_str = re.sub(r'<path\b[^/>]*/>', _inject_d, svg_str)

    # 2. Qt's QSvgRenderer fails to parse scientific notation (e.g. 1.2e-05)
    # inside SVG path 'd' or 'transform' attributes. Find and format all such 
    # numbers to fixed-point.
    def _fix_sci(m):
        return re.sub(r'[-+]?(?:\d*\.\d+|\d+\.?)[eE][-+]?\d+',
                      lambda sm: f"{float(sm.group(0)):.6f}", m.group(0))
    svg_str = re.sub(r'(?:d|transform)="[^"]+"', _fix_sci, svg_str)

    # 3. Remove <use xlink:href="#id"/> references whose target <symbol id="…">
    # or <path id="…"> is never defined. Matplotlib's mathtext SVG output emits
    # <use> references for space glyphs (e.g. #ArialMT-20, #Arial-BoldMT-20)
    # without a corresponding <symbol> definition, causing Qt to log
    # "link #ArialMT-20 is undefined!" repeatedly.
    defined_ids = set(re.findall(r'\bid="([^"]+)"', svg_str))
    def _strip_orphan_use(m):
        ref = m.group(1)
        return '' if ref not in defined_ids else m.group(0)
    svg_str = re.sub(
        r'<use [^>]*?xlink:href="#([^"]+)"[^/>]*/>',
        _strip_orphan_use,
        svg_str,
    )
    svg_bytes = svg_str.encode('utf-8')

    w_match = re.search(rb'width="([0-9.]+)pt"', svg_bytes)
    h_match = re.search(rb'height="([0-9.]+)pt"', svg_bytes)
    if w_match and h_match:
        w_pt = float(w_match.group(1))
        h_pt = float(h_match.group(1))
        w_mm = w_pt * 25.4 / 72.0
        h_mm = h_pt * 25.4 / 72.0
    else:
        return None

    return svg_bytes, w_mm, h_mm
