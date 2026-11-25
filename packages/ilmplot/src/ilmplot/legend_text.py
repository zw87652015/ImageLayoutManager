"""Legend template text: ``\\l(ref)`` symbol refs and ``%(ref)`` labels.

Reference syntax ``REF = [BS]?\\d+`` (1-based): plain ``n`` is the n-th
main item (``document.series`` for line kinds, ``categories`` for
stacked columns, ``groups`` for histograms), ``Bn`` a fill band and
``Sn`` a span. ``\\l(REF)`` is a legend-symbol placeholder recognised
only as a leading run on a line; ``%(REF)`` anywhere substitutes the
referenced item's label (empty when the ref does not resolve).
"""

import re

from .mathtext import safe_text

MAX_LEGEND_TEXT = 2000
MAX_LEGEND_LINES = 50

_REF = r'[BS]?\d+'
# A leading run of ``\l(REF)`` placeholders (and whitespace) on a line.
_LEAD_RUN = re.compile(r'^\s*((?:\\l\(%s\)\s*)+)' % _REF)
_L_REF = re.compile(r'\\l\((%s)\)' % _REF)
_LABEL_REF = re.compile(r'%%\((%s)\)' % _REF)


def parse_template(text):
    """Split *text* into ``(refs, text)`` rows, one per line.

    ``refs`` holds the leading ``\\l(REF)`` references (possibly
    several); ``text`` is the rest of the line with them stripped.
    Blank lines are kept as ``([], '')``.
    """
    out = []
    for line in (text or '').split('\n'):
        m = _LEAD_RUN.match(line)
        if not m:
            out.append(([], line))
            continue
        out.append((_L_REF.findall(m.group(1)), line[m.end():]))
    return out


def substitute(text, label_of):
    """Replace every ``%(REF)`` in *text* via ``label_of(ref)``.

    ``label_of`` returns the item's label or None; unresolved refs
    become an empty string.
    """
    def rep(m):
        label = label_of(m.group(1))
        return label if label is not None else ''
    return _LABEL_REF.sub(rep, text or '')


def _main_items(document):
    """``(key, item)`` pairs of the main collection for kinds that
    have a legend, in reference order; empty for the others."""
    kind = getattr(document, 'kind', None)
    if kind == 'line':
        return [('series:%s' % s.id, s) for s in document.series]
    if kind == 'stacked_column':
        return [('stack:%s' % c.id, c) for c in document.categories]
    if kind == 'histogram':
        return [('hist:%s' % g.id, g) for g in document.groups]
    return []


def default_template(document) -> str:
    """Template text equivalent to the automatic legend.

    One ``\\l(n) %(n)`` line per entry the automatic legend would show —
    main items with a non-empty label (and, for line kinds, not
    ``_``-prefixed) that are not in ``legend_hidden`` — then labelled
    bands ``\\l(Bn) %(Bn)`` and spans ``\\l(Sn) %(Sn)``. Returns '' for
    kinds without a legend.
    """
    main = _main_items(document)
    if not main:
        return ''
    kind = document.kind
    hidden = set(getattr(document, 'legend_hidden', None) or ())
    lines = []
    for n, (key, item) in enumerate(main, 1):
        if key in hidden:
            continue
        label = safe_text(getattr(item, 'label', '') or '')
        if not label or (kind == 'line' and label.startswith('_')):
            continue
        lines.append('\\l(%d) %%(%d)' % (n, n))
    for n, b in enumerate(getattr(document, 'bands', None) or (), 1):
        if not b.label or 'band:%s' % b.id in hidden:
            continue
        lines.append('\\l(B%d) %%(B%d)' % (n, n))
    for n, sp in enumerate(getattr(document, 'spans', None) or (), 1):
        if not sp.label or 'span:%s' % sp.id in hidden:
            continue
        lines.append('\\l(S%d) %%(S%d)' % (n, n))
    return '\n'.join(lines)
