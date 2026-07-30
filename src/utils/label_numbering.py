"""Panel-label numbering schemes.

A *scheme* is a sample string that shows the desired output for the first
item, e.g. ``"(a)"``, ``"A"``, ``"1."``, ``"(iv)"``.  The first character
belonging to the alphabet table below selects the numbering style; anything
before it becomes a literal prefix and anything after it a literal suffix.

    "(a)"  -> prefix "(",  latin lower, suffix ")"
    "A."   -> prefix "",   latin upper, suffix "."
    "(i)"  -> prefix "(",  roman lower, suffix ")"
    "1"    -> prefix "",   arabic,      suffix ""

Only ``a``, ``A``, ``i``, ``I`` and ``1`` act as style selectors, so ``i``
always means roman rather than "the ninth latin letter".
"""

LATIN_LOWER = "latin_lower"
LATIN_UPPER = "latin_upper"
ROMAN_LOWER = "roman_lower"
ROMAN_UPPER = "roman_upper"
ARABIC = "arabic"

# Order matters only for documentation; lookup is by exact character.
_STYLE_BY_CHAR = {
    "a": LATIN_LOWER,
    "A": LATIN_UPPER,
    "i": ROMAN_LOWER,
    "I": ROMAN_UPPER,
    "1": ARABIC,
}

# Schemes offered in the UI. Kept here so the inspector, MCP layer and CLI
# all validate against one list.
SCHEMES = [
    "(a)", "a", "(A)", "A",
    "(1)", "1", "1.",
    "(i)", "i", "(I)", "I",
]

_ROMAN_STEPS = (
    (1000, "m"), (900, "cm"), (500, "d"), (400, "cd"),
    (100, "c"), (90, "xc"), (50, "l"), (40, "xl"),
    (10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i"),
)


def parse_scheme(scheme: str):
    """Split *scheme* into ``(prefix, style, suffix)``.

    Falls back to plain lowercase latin when no selector character is found,
    which keeps malformed user input harmless.
    """
    for pos, char in enumerate(scheme or ""):
        style = _STYLE_BY_CHAR.get(char)
        if style:
            return scheme[:pos], style, scheme[pos + 1:]
    return "", LATIN_LOWER, ""


def _latin(index: int) -> str:
    """0 -> a, 25 -> z, 26 -> aa (spreadsheet-column style)."""
    letters = ""
    n = index + 1
    while n > 0:
        n, rem = divmod(n - 1, 26)
        letters = chr(ord("a") + rem) + letters
    return letters


def _roman(index: int) -> str:
    n = index + 1
    out = ""
    for value, glyph in _ROMAN_STEPS:
        while n >= value:
            out += glyph
            n -= value
    return out


def format_index(index: int, scheme: str) -> str:
    """Render a 0-based *index* using *scheme*."""
    if index < 0:
        index = 0
    prefix, style, suffix = parse_scheme(scheme)
    if style == LATIN_LOWER:
        core = _latin(index)
    elif style == LATIN_UPPER:
        core = _latin(index).upper()
    elif style == ROMAN_LOWER:
        core = _roman(index)
    elif style == ROMAN_UPPER:
        core = _roman(index).upper()
    else:
        core = str(index + 1)
    return f"{prefix}{core}{suffix}"


def core_of(text: str, scheme: str) -> str:
    """Strip *scheme*'s prefix/suffix from *text*.

    Used when building hierarchical labels such as ``A-ii`` from a parent
    rendered as ``(A)``.
    """
    prefix, _style, suffix = parse_scheme(scheme)
    out = text or ""
    if prefix and out.startswith(prefix):
        out = out[len(prefix):]
    if suffix and out.endswith(suffix):
        out = out[: len(out) - len(suffix)]
    return out
