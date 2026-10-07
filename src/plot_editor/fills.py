"""Editor-side curve fills ("Add Fill…"): filled areas defined against
plotted series — under one curve or between two curves — that render as
document bands. No Qt imports: the definitions live in the worksheet
overrides and are compiled to :class:`ilmplot.document.Band` objects by
``compute_band`` inside ``effective_document``.
"""

from dataclasses import dataclass, field
import math
import uuid

import numpy as np

from ilmplot.document import Band, PlotDocumentError

FILL_KINDS = ('under', 'between')


def _err(msg):
    return PlotDocumentError(msg)


def _is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) \
        and math.isfinite(v)


def _check_color(v, ctx):
    if not isinstance(v, str) or not v.startswith('#') \
            or len(v) not in (7, 9):
        raise _err(f"{ctx}: expected '#rrggbb' or '#rrggbbaa'")
    try:
        int(v[1:], 16)
    except ValueError:
        raise _err(f"{ctx}: bad colour {v!r}")
    return v


@dataclass
class CurveFill:
    """A filled area bound to one or two plotted series (by Y column)."""
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    kind: str = 'under'          # 'under' | 'between'
    a: int = 0                   # Y column index of the (first) series
    b: 'int | None' = None       # second series Y column ('between')
    baseline: float = 0.0        # 'under' only
    x_min: 'float | None' = None
    x_max: 'float | None' = None  # None = the data range
    color: str = '#1f77b44d'
    label: str = ''

    _KEYS = ('id', 'kind', 'a', 'b', 'baseline', 'x_min', 'x_max',
             'color', 'label')

    def to_dict(self) -> dict:
        return {'id': self.id, 'kind': self.kind, 'a': int(self.a),
                'b': self.b, 'baseline': float(self.baseline),
                'x_min': self.x_min, 'x_max': self.x_max,
                'color': self.color, 'label': self.label}

    @classmethod
    def from_dict(cls, data, ctx='fills') -> 'CurveFill':
        if not isinstance(data, dict):
            raise _err(f"{ctx}: expected an object")
        unknown = sorted(set(data) - set(cls._KEYS))
        if unknown:
            raise _err(f"{ctx}: unknown field(s) {unknown} — file may "
                       "need a newer version")
        f = cls()
        sid = data.get('id')
        if not isinstance(sid, str) or not sid:
            raise _err(f"{ctx}.id: expected a non-empty string")
        f.id = sid
        if data.get('kind') not in FILL_KINDS:
            raise _err(f"{ctx}.kind: expected one of {FILL_KINDS}")
        f.kind = data['kind']
        for name in ('a', 'b'):
            v = data.get(name)
            if v is None:
                if name == 'a':
                    raise _err(f"{ctx}.a: expected a column index")
                f.b = None
                continue
            if not isinstance(v, int) or isinstance(v, bool) or v < 0:
                raise _err(f"{ctx}.{name}: expected a non-negative "
                           "integer")
            setattr(f, name, v)
        if f.kind == 'between':
            if f.b is None:
                raise _err(f"{ctx}.b: required for a 'between' fill")
            if f.b == f.a:
                raise _err(f"{ctx}: series A and B must differ")
        for name in ('baseline', 'x_min', 'x_max'):
            v = data.get(name)
            if v is None:
                if name == 'baseline':
                    raise _err(f"{ctx}.baseline: expected a number")
                setattr(f, name, None)
                continue
            if not _is_num(v):
                raise _err(f"{ctx}.{name}: expected a finite number")
            setattr(f, name, float(v))
        if f.x_min is not None and f.x_max is not None \
                and not f.x_min < f.x_max:
            raise _err(f"{ctx}: expected x_min < x_max")
        f.color = _check_color(data.get('color'), f"{ctx}.color")
        label = data.get('label')
        if not isinstance(label, str):
            raise _err(f"{ctx}.label: expected a string")
        f.label = label
        return f


def _sorted_xy(xs, ys):
    """Finite ``(x, y)`` pairs sorted by x."""
    pairs = [(float(x), float(y)) for x, y in zip(xs, ys)
             if _is_num(x) and _is_num(y)]
    pairs.sort(key=lambda p: p[0])
    return pairs


def _interp(pairs, x):
    """Linear interpolation through sorted ``(x, y)`` pairs."""
    xs = np.array([p[0] for p in pairs])
    ys = np.array([p[1] for p in pairs])
    return float(np.interp(x, xs, ys))


def _domain_points(pairs, lo, hi):
    """Interior points of *pairs* plus interpolated domain ends."""
    xs = [p[0] for p in pairs]
    out = []
    if xs[0] < lo < xs[-1]:
        out.append((lo, _interp(pairs, lo)))
    elif lo == xs[0]:
        out.append((lo, pairs[0][1]))
    for p in pairs:
        if lo < p[0] < hi:
            out.append(p)
        elif p[0] == lo and not out:
            out.append(p)
    if xs[0] < hi < xs[-1]:
        out.append((hi, _interp(pairs, hi)))
    elif hi == xs[-1]:
        out.append((hi, pairs[-1][1]))
    return out


def compute_band(fill, items) -> 'Band | None':
    """Compile *fill* into a document :class:`Band` over *items*.

    *items* is either the plotted Series objects (matched by
    ``y_column``) or a ``{y_column: (x, y)}`` mapping of the *drawn*
    series — e.g. ``doc.series`` where stacked-line offsets are already
    baked into ``y``.

    ``None`` when a referenced column is not plotted, the x domain is
    empty, or fewer than 2 points remain — the fill stays defined in
    the overrides and simply draws nothing.
    """
    if isinstance(items, dict):
        def xy_at(col):
            return items.get(col)
    else:
        def xy_at(col):
            s = next((it for it in items
                      if getattr(it, 'y_column', None) == col), None)
            return None if s is None else (s.x, s.y)

    sa = xy_at(fill.a)
    if sa is None:
        return None
    pa = _sorted_xy(sa[0], sa[1])
    if len(pa) < 2:
        return None
    xa = [p[0] for p in pa]

    if fill.kind == 'under':
        lo = max(xa[0], fill.x_min if fill.x_min is not None else xa[0])
        hi = min(xa[-1], fill.x_max if fill.x_max is not None else xa[-1])
        if not lo < hi:
            return None
        pts = _domain_points(pa, lo, hi)
        if len(pts) < 2:
            return None
        return Band(id=fill.id, label=fill.label,
                    x=[p[0] for p in pts],
                    y1=[float(fill.baseline)] * len(pts),
                    y2=[p[1] for p in pts], color=fill.color)

    # 'between'
    sb = xy_at(fill.b) if fill.b is not None else None
    if sb is None:
        return None
    pb = _sorted_xy(sb[0], sb[1])
    if len(pb) < 2:
        return None
    xb = [p[0] for p in pb]
    lo = max(xa[0], xb[0],
             fill.x_min if fill.x_min is not None else max(xa[0], xb[0]))
    hi = min(xa[-1], xb[-1],
             fill.x_max if fill.x_max is not None else min(xa[-1], xb[-1]))
    if not lo < hi:
        return None
    xs = sorted({x for x in xa + xb if lo <= x <= hi} | {lo, hi})
    if len(xs) < 2:
        return None
    return Band(id=fill.id, label=fill.label, x=xs,
                y1=[_interp(pa, x) for x in xs],
                y2=[_interp(pb, x) for x in xs],
                color=fill.color)
