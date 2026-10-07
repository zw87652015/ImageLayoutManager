"""Statistics helpers for the native plot kinds (Qt-free, numpy only).

``gaussian_kde`` reproduces ``scipy.stats.gaussian_kde`` for 1-D data
(covariance = ``var(ddof=1) * factor**2``; 'scott' factor ``n**-0.2``,
'silverman' ``(n * 3/4)**-0.2``, a numeric bandwidth is the factor
itself, as scipy treats a scalar ``bw_method``). scipy is not a
dependency of ILM, so the KDE is evaluated directly in numpy.
"""

from __future__ import annotations

import math

import numpy as np

BANDWIDTHS = ('scott', 'silverman')


def _bandwidth_factor(bandwidth, n):
    if bandwidth == 'scott':
        return n ** -0.2
    if bandwidth == 'silverman':
        return (n * 0.75) ** -0.2
    try:
        f = float(bandwidth)
    except (TypeError, ValueError):
        raise ValueError(f'bandwidth: expected scott/silverman or a '
                         f'positive number, got {bandwidth!r}')
    if not math.isfinite(f) or f <= 0:
        raise ValueError(f'bandwidth: expected a positive number, '
                         f'got {bandwidth!r}')
    return f


def gaussian_kde(values, bandwidth='scott'):
    """Return ``(evaluate(points) -> densities, bw_abs)``.

    ``bw_abs`` is the absolute bandwidth ``factor * sd`` (scipy's
    ``kde.factor * std``), matching ``kde.covariance = var*factor²``.
    """
    v = np.asarray(values, dtype=float)
    v = v[np.isfinite(v)]
    n = v.size
    factor = _bandwidth_factor(bandwidth, n)
    sd = float(np.std(v, ddof=1)) if n > 1 else 0.0
    bw_abs = factor * sd

    def evaluate(points):
        p = np.asarray(points, dtype=float)
        if n == 0 or bw_abs <= 0:
            return np.zeros(p.shape)
        z = (p[:, None] - v[None, :]) / bw_abs
        return np.exp(-0.5 * z * z).sum(axis=1) / (n * bw_abs
                                                 * math.sqrt(2 * math.pi))

    return evaluate, bw_abs


def violin_shape(values, bandwidth='scott'):
    """``(eval_points, half_width)`` for one violin body, or None.

    NCPlot rule: evaluate over ``[min - 2.5·bw, max + 2.5·bw]`` at 200
    points (bw = factor × sd(ddof=1)); normalize the density so its max
    is 0.3. ``None`` when n < 2 or the values are constant.
    """
    v = np.asarray(values, dtype=float)
    v = v[np.isfinite(v)]
    if v.size < 2:
        return None
    sd = float(np.std(v, ddof=1))
    if sd == 0:
        return None
    evaluate, bw = gaussian_kde(v, bandwidth)
    pts = np.linspace(float(v.min()) - 2.5 * bw,
                      float(v.max()) + 2.5 * bw, 200)
    density = evaluate(pts)
    peak = float(density.max())
    if peak > 0:
        density = density / peak * 0.3
    return pts, density


def box_stats(values):
    """``(q1, median, q3, lo_whisker, hi_whisker)`` — linear percentiles,
    whiskers clamped to the data within 1.5·IQR (NCPlot)."""
    v = np.asarray(values, dtype=float)
    v = v[np.isfinite(v)]
    q1, med, q3 = np.percentile(v, [25.0, 50.0, 75.0])
    iqr = q3 - q1
    lo = max(float(v.min()), float(q1 - 1.5 * iqr))
    hi = min(float(v.max()), float(q3 + 1.5 * iqr))
    return float(q1), float(med), float(q3), lo, hi


def jitter(n, beside, seed):
    """Deterministic horizontal jitter offsets (NCPlot ranges).

    ``seed`` is 42 + group index, so each group jitters stably.
    """
    rng = np.random.default_rng(seed)
    if beside:
        return rng.uniform(0.22, 0.38, size=n)
    return rng.uniform(-0.12, 0.12, size=n)
