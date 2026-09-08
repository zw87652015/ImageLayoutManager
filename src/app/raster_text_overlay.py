import numpy as np
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPainterPath

from src.utils.raster_text_utils import _connected_components


def _rounded_path(path, radius):
    result = QPainterPath()
    result.setFillRule(Qt.FillRule.OddEvenFill)
    for polygon in path.simplified().toSubpathPolygons():
        points = [(p.x(), p.y()) for p in polygon]
        if len(points) > 1 and points[0] == points[-1]:
            points.pop()
        points = [p for i, p in enumerate(points) if p != points[i - 1]]
        changed = True
        while changed and len(points) >= 3:
            changed = False
            keep = []
            for i, b in enumerate(points):
                a, c = points[i - 1], points[(i + 1) % len(points)]
                if abs((b[0] - a[0]) * (c[1] - b[1]) -
                       (b[1] - a[1]) * (c[0] - b[0])) < 1e-8:
                    changed = True
                else:
                    keep.append(b)
            points = keep
        if len(points) < 3:
            continue
        corners = []
        for i, b in enumerate(points):
            a, c = points[i - 1], points[(i + 1) % len(points)]
            incoming = np.array(a) - b
            outgoing = np.array(c) - b
            before, after = np.linalg.norm(incoming), np.linalg.norm(outgoing)
            r = min(radius, before / 2, after / 2)
            corners.append((np.array(b) + incoming * r / before, b,
                            np.array(b) + outgoing * r / after))
        result.moveTo(*corners[0][0])
        for entry, corner, exit_point in corners:
            result.lineTo(*entry)
            result.quadTo(*corner, *exit_point)
        result.closeSubpath()
    return result


def text_envelope_path(text_alpha, origin=(0, 0), protected_mask=None,
                       protected_origin=None, vertical=False):
    result = QPainterPath()
    alpha = np.asarray(text_alpha)
    if alpha.ndim != 2 or not alpha.size:
        return result
    threshold = 0.5 if np.nanmax(alpha) <= 1 else 127.5
    ink = alpha > threshold
    labels, count = _connected_components(ink)
    if not count:
        return result
    ys, xs = np.nonzero(ink)
    ids = labels[ys, xs] - 1
    left = np.full(count, alpha.shape[1], dtype=float)
    top = np.full(count, alpha.shape[0], dtype=float)
    right, bottom = np.zeros(count), np.zeros(count)
    np.minimum.at(left, ids, xs)
    np.minimum.at(top, ids, ys)
    np.maximum.at(right, ids, xs + 1)
    np.maximum.at(bottom, ids, ys + 1)
    height = np.median(right - left if vertical else bottom - top)
    padding = float(np.clip(height * 0.08, 1, 2))
    rects = np.column_stack((left - padding, top - padding,
                            right + padding, bottom + padding))
    rects += np.array([origin[0], origin[1], origin[0], origin[1]])
    result.setFillRule(Qt.FillRule.WindingFill)

    def add_rect(x0, y0, x1, y1):
        result.addRect(float(x0), float(y0), float(x1 - x0), float(y1 - y0))

    for rect in rects:
        add_rect(*rect)
    centers = (rects[:, :2] + rects[:, 2:]) / 2
    distances = np.full(count, np.inf)
    distances[0] = 0
    parents = np.zeros(count, dtype=int)
    visited = np.zeros(count, dtype=bool)
    width = max(0.75, padding * 0.75)
    for _ in range(count):
        current = int(np.argmin(distances))
        if visited.any():
            a, b = rects[parents[current]], rects[current]
            start, end = [], []
            for axis in range(2):
                lo, hi = max(a[axis], b[axis]), min(a[axis + 2], b[axis + 2])
                if lo <= hi:
                    start.append((lo + hi) / 2)
                    end.append((lo + hi) / 2)
                elif a[axis + 2] < b[axis]:
                    start.append(a[axis + 2])
                    end.append(b[axis])
                else:
                    start.append(a[axis])
                    end.append(b[axis + 2])
            bend = [start[0], end[1]] if vertical else [end[0], start[1]]
            for p, q in ((start, bend), (bend, end)):
                add_rect(min(p[0], q[0]) - width, min(p[1], q[1]) - width,
                         max(p[0], q[0]) + width, max(p[1], q[1]) + width)
        visited[current] = True
        gap = np.maximum(0, np.maximum(rects[:, :2] - rects[current, 2:],
                                        rects[current, :2] - rects[:, 2:]))
        scores = gap.sum(axis=1) + np.abs(centers - centers[current]).sum(axis=1) * 1e-4
        closer = (~visited) & (scores < distances)
        distances[closer], parents[closer] = scores[closer], current
        distances[visited] = np.inf
    result = result.simplified()
    if protected_mask is not None:
        protected = np.asarray(protected_mask)
        if protected.ndim == 2 and protected.size:
            blocked = QPainterPath()
            blocked.setFillRule(Qt.FillRule.WindingFill)
            px, py = origin if protected_origin is None else protected_origin
            margin = 0.75
            for y in np.flatnonzero((protected > 0).any(axis=1)):
                transitions = np.diff(np.pad((protected[y] > 0).astype(np.int8), (1, 1)))
                for x0, x1 in zip(np.flatnonzero(transitions == 1),
                                  np.flatnonzero(transitions == -1)):
                    blocked.addRect(float(px + x0 - margin), float(py + y - margin),
                                    float(x1 - x0 + 2 * margin), 1 + 2 * margin)
            result = result.subtracted(blocked.simplified())
    return _rounded_path(result, padding)
