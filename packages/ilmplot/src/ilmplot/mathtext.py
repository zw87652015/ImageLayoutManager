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


# Families tried first when a math-bearing text needs a font that also
# covers its non-math (e.g. CJK) characters; remaining installed families
# follow in name order.
MATH_FONT_PREFERENCE = (
    'Microsoft YaHei', 'SimHei', 'SimSun', 'PingFang SC',
    'Hiragino Sans GB', 'Heiti SC', 'Noto Sans CJK SC',
    'Noto Sans SC', 'Source Han Sans SC', 'WenQuanYi Micro Hei',
    'Arial Unicode MS', 'Malgun Gothic', 'Yu Gothic', 'MS Gothic',
    'Meiryo')


def _outside_math(text):
    """The characters of *text* outside ``$...$`` segments.

    ``\\$`` is a literal dollar (never a delimiter), matching
    ``safe_text``/matplotlib. Like ``cbook.is_math_text`` an odd number
    of unescaped dollars means the whole string is plain text.
    """
    n = len(text)
    dollars = 0
    i = 0
    while i < n:
        if text[i] == '\\' and i + 1 < n and text[i + 1] == '$':
            i += 2
            continue
        if text[i] == '$':
            dollars += 1
        i += 1
    if dollars % 2:
        return text
    out = []
    in_math = False
    i = 0
    while i < n:
        ch = text[i]
        if ch == '\\' and i + 1 < n and text[i + 1] == '$':
            if not in_math:
                out.append('$')
            i += 2
            continue
        if ch == '$':
            in_math = not in_math
        elif not in_math:
            out.append(ch)
        i += 1
    return ''.join(out)


@functools.lru_cache(maxsize=1024)
def _resolve_font_path(families):
    """matplotlib's resolved font file for a family-name tuple."""
    from matplotlib import font_manager
    try:
        return font_manager.findfont(
            font_manager.FontProperties(family=list(families)))
    except Exception:
        return None


@functools.lru_cache(maxsize=256)
def _ft2_font(path):
    from matplotlib import font_manager
    try:
        return font_manager.get_font(path)
    except Exception:
        return None


@functools.lru_cache(maxsize=512)
def _family_covers(family, chars):
    """True when the installed font *family* has a glyph for every char."""
    path = _resolve_font_path((family,))
    font = _ft2_font(path) if path is not None else None
    return font is not None and all(
        font.get_char_index(ord(ch)) for ch in chars)


@functools.lru_cache(maxsize=256)
def _default_covers(families, chars):
    """True when the artist's own resolved font covers every char."""
    path = _resolve_font_path(families)
    font = _ft2_font(path) if path is not None else None
    if font is None:
        return True  # cannot resolve — leave the text untouched
    return all(font.get_char_index(ord(ch)) for ch in chars)


@functools.lru_cache(maxsize=1)
def _font_family_names():
    from matplotlib import font_manager
    return tuple(sorted({f.name
                         for f in font_manager.fontManager.ttflist}))


def _candidate_families():
    """Preference list first (canonical names), then the rest sorted."""
    names = _font_family_names()
    lowered = {n.lower(): n for n in names}
    ordered = []
    seen = set()
    for pref in MATH_FONT_PREFERENCE:
        canon = lowered.get(pref.lower())
        if canon is not None and canon not in seen:
            seen.add(canon)
            ordered.append(canon)
    ordered.extend(n for n in names if n not in seen)
    return ordered


@functools.lru_cache(maxsize=512)
def _math_font_family(text, families):
    if not has_math(text):
        return None
    chars = frozenset(c for c in _outside_math(text) if not c.isspace())
    if not chars or _default_covers(families, chars):
        return None
    for name in _candidate_families():
        if _family_covers(name, chars):
            return name
    return None


def math_font_family(text, families):
    """A font family covering the non-math characters of *text*, or None.

    Mathtext draws a ``$...$`` string entirely with the Text's single
    resolved font for the non-math runs, so a CJK label next to math
    renders missing glyphs (``¤``). When the artist's own *families*
    cannot cover those characters this returns the name of the first
    installed family that can — prepend it via ``set_fontfamily``.
    Returns None when there is no math, nothing needs covering, the
    default font already covers everything, or no font does.
    """
    if not text:
        return None
    if isinstance(families, str):
        families = (families,)
    return _math_font_family(text, tuple(families or ()))
