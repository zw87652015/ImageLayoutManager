"""Note text helpers (pure Python)."""
import re

from ilmplot.mathtext import MATH_RE

MAX_NOTE_TEXT = 500   # mirrors Annotation.from_dict

# LaTeX commands beginning with ``\n`` — a typed ``\n`` is only a
# newline escape when it does not complete one of these.
_N_COMMANDS = frozenset(
    {'nabla', 'natural', 'nearrow', 'neg', 'neq', 'nexists', 'ngeq',
     'ngtr', 'ni', 'nleftarrow', 'nleftrightarrow', 'nleq', 'nless',
     'nmid', 'not', 'notin', 'nparallel', 'nprec', 'nrightarrow',
     'nshortmid', 'nshortparallel', 'nsim', 'nsubseteq', 'nsucc',
     'nsupseteq', 'ntriangleleft', 'ntriangleright', 'nu', 'nvdash',
     'nvDash', 'nVdash', 'nwarrow'})

_ESC = re.compile(r'(?<!\\)\\n([A-Za-z]*)')


def expand_newline_escapes(text):
    """Turn a typed two-character ``\\n`` into a real newline outside
    ``$...$`` math segments only, and only when it does not complete a
    LaTeX command (so ``\\nu``, ``\\neq``, ``\\nabla`` survive).
    ``\\\\n`` (escaped backslash) is left alone."""
    def sub(m):
        return m.group(0) if 'n' + m.group(1) in _N_COMMANDS \
            else '\n' + m.group(1)

    out = []
    pos = 0
    for m in MATH_RE.finditer(text):
        out.append(_ESC.sub(sub, text[pos:m.start()]))
        out.append(m.group(0))
        pos = m.end()
    out.append(_ESC.sub(sub, text[pos:]))
    return ''.join(out)
