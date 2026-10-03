"""Inline ``$...$`` mathtext helpers for the Plot Editor (pure Python, no Qt).

Mirrors ILM's ``src/utils/math_text.py`` rules, minus the Qt/pyplot parts:
stored text is never modified — sanitizing happens only when drawing. A
math segment matplotlib's mathtext can't parse gets its dollar signs
escaped so it renders literally instead of raising at draw time.
"""

import functools
import re

MATH_RE = re.compile(r'\$[^$\n]+\$')

# mathtext has no \kern/\raisebox, so the logos are approximated with a
# raised small A, a lowered small E and negative \hspace kerning.
TEX_LOGO = r'\mathrm{T\hspace{-0.12}_{E}\hspace{-0.1}X}'
LATEX_LOGO = (r'\mathrm{L\hspace{-0.36}^{A}\hspace{-0.15}'
              r'T\hspace{-0.12}_{E}\hspace{-0.1}X}')


def has_math(text):
    """True when *text* contains at least one ``$...$`` segment."""
    return bool(text) and bool(MATH_RE.search(text))


def preprocess(text):
    """Rewrite ``\\LaTeX``/``\\TeX`` logo macros inside math segments only."""
    def fix(seg):
        return (seg
                .replace(r'\LaTeXe', LATEX_LOGO[:-1] + r'\,2_{\epsilon}}')
                .replace(r'\LaTeX', LATEX_LOGO)
                .replace(r'\TeX', TEX_LOGO))
    return MATH_RE.sub(lambda m: fix(m.group(0)), text)


@functools.lru_cache(maxsize=1024)
def _segment_parses(seg):
    try:
        from matplotlib.font_manager import FontProperties
        from matplotlib.mathtext import MathTextParser
        MathTextParser('path').parse(seg, dpi=72, prop=FontProperties())
        return True
    except Exception:
        return False


@functools.lru_cache(maxsize=1024)
def safe_text(text):
    """``preprocess`` + escape the dollars of any math segment that fails
    to parse, so it draws literally. Stray dollars outside a ``$...$``
    segment (``'$$'``, ``'$5'``) are escaped too: otherwise matplotlib
    pairs them by count and enters math mode on garbage (``'$$'`` raised
    at draw time) or drops real segments when the count turns odd.
    Text without dollars is unchanged."""
    if '$' not in text:
        return text
    text = preprocess(text)
    out, pos = [], 0

    def strays(chunk):
        return re.sub(r'(?<!\\)\$', r'\\$', chunk)

    for m in MATH_RE.finditer(text):
        out.append(strays(text[pos:m.start()]))
        seg = m.group(0)
        out.append(seg if _segment_parses(seg) else seg.replace('$', r'\$'))
        pos = m.end()
    out.append(strays(text[pos:]))
    return ''.join(out)
