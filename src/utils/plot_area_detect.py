"""Plot-area suggestions for the Align Plot Areas dialog.

Three sources, most exact first: a native ilm-plot document, a matplotlib SVG
axes patch, and a raster axis-line heuristic. The pure functions take numpy
and stdlib types only; the Qt/PIL/file adapter is at the bottom.

Every box is (left, top, right, bottom), normalized to the UNCROPPED source,
the same frame PlotArea uses.
"""

from __future__ import annotations

import math
import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from functools import lru_cache

import numpy as np

_MAX_SVG_BYTES = 64 * 1024 * 1024
_MAX_SIDE = 1000
_DARK = 128
_ALPHA_WHITE = 32
_BRIDGE = 2
_LONG_RUN = 0.35
_CLUSTER = 2
_FRAME_TOL = 0.03
_MIN_SPAN = 0.10
_SVG_MIN_SPAN = 0.05


@dataclass(frozen=True)
class Suggestion:
    box: tuple
    source: str  # "native" | "svg_axes" | "raster_axes"


# ── raster ────────────────────────────────────────────────────────────────

def _longest_run(line, bridge):
    """(length, start, end) of the longest True run, bridging short gaps."""
    idx = np.flatnonzero(line)
    if idx.size == 0:
        return 0, 0, 0
    breaks = np.flatnonzero(np.diff(idx) > bridge + 1)
    starts = np.concatenate(([0], breaks + 1))
    ends = np.concatenate((breaks, [idx.size - 1]))
    lengths = idx[ends] - idx[starts] + 1
    k = int(np.argmax(lengths))
    return int(lengths[k]), int(idx[starts[k]]), int(idx[ends[k]])


def _clusters(indices):
    groups = [[int(indices[0])]]
    for value in indices[1:]:
        value = int(value)
        if value - groups[-1][-1] <= _CLUSTER:
            groups[-1].append(value)
        else:
            groups.append([value])
    return groups


def suggest_from_raster(gray, alpha=None):
    gray = np.asarray(gray)
    if gray.ndim != 2 or gray.size == 0:
        return None
    if alpha is not None:
        gray = np.where(np.asarray(alpha) < _ALPHA_WHITE, 255, gray).astype(np.uint8)
    h0, w0 = gray.shape
    step = max(1, math.ceil(max(h0, w0) / _MAX_SIDE))
    dark = gray[::step, ::step] < _DARK
    h, w = dark.shape

    col_len = np.zeros(w, int)
    col_s = np.zeros(w, int)
    col_e = np.zeros(w, int)
    for x in range(w):
        col_len[x], col_s[x], col_e[x] = _longest_run(dark[:, x], _BRIDGE)
    row_len = np.zeros(h, int)
    row_s = np.zeros(h, int)
    row_e = np.zeros(h, int)
    for y in range(h):
        row_len[y], row_s[y], row_e[y] = _longest_run(dark[y, :], _BRIDGE)

    col_cands = np.flatnonzero(col_len >= _LONG_RUN * h)
    row_cands = np.flatnonzero(row_len >= _LONG_RUN * w)
    if col_cands.size == 0 or row_cands.size == 0:
        return None
    col_clusters = _clusters(col_cands)
    row_clusters = _clusters(row_cands)

    left = col_clusters[0]
    x = left[-1]                       # interior edge of the left axis
    y0 = int(col_s[x])

    tol_x = _FRAME_TOL * w
    bottom = None
    for cluster in reversed(row_clusters):  # lowest first
        if any(abs(int(row_s[y]) - x) <= tol_x for y in cluster):
            bottom = cluster
            break
    if bottom is None:
        bottom = row_clusters[-1]
    yb = bottom[0]                     # interior edge of the bottom axis
    x1 = int(row_e[yb])

    top = y0
    tol_y = _FRAME_TOL * h
    for cluster in row_clusters:
        if cluster is bottom:
            continue
        if any(abs(y - y0) <= tol_y for y in cluster):
            top = cluster[-1]
            break

    right = x1
    tol_x2 = _FRAME_TOL * w
    for cluster in col_clusters:
        if cluster is left or cluster[0] <= x:
            continue
        if any(abs(c - x1) <= tol_x2 for c in cluster):
            right = cluster[0]
            break

    if right <= x or yb <= top:
        return None
    l_n = x * step / w0
    t_n = top * step / h0
    r_n = min(1.0, right * step / w0)
    b_n = min(1.0, yb * step / h0)
    if r_n - l_n < _MIN_SPAN or b_n - t_n < _MIN_SPAN:
        return None
    return Suggestion((l_n, t_n, r_n, b_n), "raster_axes")


# ── matplotlib SVG ────────────────────────────────────────────────────────

_DOCTYPE_SUBSET = re.compile(rb"<!DOCTYPE[^>]*\[", re.S)
_PATH_CHARS = re.compile(r"[\sMLZmlz0-9eE.,+\-]*")
_NUMBER_OR_CMD = re.compile(r"[MLZmlz]|[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")


def _local(tag):
    return str(tag).rsplit("}", 1)[-1]


def _path_points(d):
    """Vertices of an absolute M/L/Z path, or None for anything else."""
    if not _PATH_CHARS.fullmatch(d):
        return None
    points = []
    numbers = []
    cmd = None
    for token in _NUMBER_OR_CMD.findall(d):
        if token in ("M", "L", "Z", "z"):
            if numbers:
                return None
            cmd = token
            continue
        if token in ("m", "l") or cmd not in ("M", "L"):
            return None
        numbers.append(float(token))
        if len(numbers) == 2:
            points.append((numbers[0], numbers[1]))
            numbers = []
    if numbers:
        return None
    return points or None


def _viewbox(root):
    vb = root.get("viewBox")
    if vb:
        parts = [float(v) for v in re.split(r"[\s,]+", vb.strip())]
        if len(parts) == 4 and parts[2] > 0 and parts[3] > 0:
            return parts[0], parts[1], parts[2], parts[3]
    try:
        w = float(re.match(r"[-+]?[\d.]+", root.get("width", "")).group(0))
        h = float(re.match(r"[-+]?[\d.]+", root.get("height", "")).group(0))
    except (AttributeError, ValueError):
        return None
    return (0.0, 0.0, w, h) if w > 0 and h > 0 else None


def suggest_from_svg(svg_bytes: bytes):
    if not svg_bytes or len(svg_bytes) > _MAX_SVG_BYTES:
        return None
    if b"<!ENTITY" in svg_bytes or _DOCTYPE_SUBSET.search(svg_bytes):
        return None
    try:
        root = ET.fromstring(svg_bytes)
    except ET.ParseError:
        return None
    view = _viewbox(root)
    if view is None:
        return None
    vx, vy, vw, vh = view

    best = None
    for group in root.iter():
        if _local(group.tag) != "g" or not group.get("id", "").startswith("axes_"):
            continue
        patch = None
        for sub in group.iter():
            if sub is group or _local(sub.tag) != "g":
                continue
            if not sub.get("id", "").startswith("patch_"):
                continue
            paths = [p for p in sub.iter() if _local(p.tag) == "path" and p.get("d")]
            if paths:
                patch = paths[0]
                break
        if patch is None:
            continue
        points = _path_points(patch.get("d"))
        if not points:
            continue
        xs = [(px - vx) / vw for px, _ in points]
        ys = [(py - vy) / vh for _, py in points]
        l, r = max(0.0, min(xs)), min(1.0, max(xs))
        t, b = max(0.0, min(ys)), min(1.0, max(ys))
        if r - l < _SVG_MIN_SPAN or b - t < _SVG_MIN_SPAN:
            continue
        area = (r - l) * (b - t)
        if best is None or area > best[0]:
            best = (area, (l, t, r, b))
    if best is None:
        return None
    return Suggestion(best[1], "svg_axes")


# ── native plot document ─────────────────────────────────────────────────

def suggest_from_native(path):
    try:
        from src.utils.editable_plot import plot_is_loadable
        from ilmplot.render import load_rendered_document, render_document
        if not plot_is_loadable(path):
            return None
        render = render_document(load_rendered_document(path))
        box = tuple(float(v) for v in render.plot_area)
        return Suggestion(box, "native")
    except Exception:
        return None


# ── adapter: files and Qt images ─────────────────────────────────────────

@lru_cache(maxsize=64)
def _file_suggestion(real, mtime_ns, size):
    native = suggest_from_native(real)
    if native is not None:
        return native
    if real.lower().endswith(".svg"):
        with open(real, "rb") as source:
            data = source.read(_MAX_SVG_BYTES + 1)
        return suggest_from_svg(data)
    return _raster_from_file(real)


def _raster_from_file(real):
    try:
        from PIL import Image
        with Image.open(real) as image:
            rgba = np.asarray(image.convert("RGBA"))
    except Exception:
        return None
    gray = (rgba[..., 0] * 0.299 + rgba[..., 1] * 0.587 + rgba[..., 2] * 0.114)
    return suggest_from_raster(gray.astype(np.uint8), rgba[..., 3])


def _qimage_arrays(qimage):
    from PyQt6.QtGui import QImage
    argb = qimage.convertToFormat(QImage.Format.Format_ARGB32)
    w, h = argb.width(), argb.height()
    if w == 0 or h == 0:
        return None
    ptr = argb.constBits()
    ptr.setsize(argb.sizeInBytes())
    raw = np.frombuffer(ptr, dtype=np.uint8).reshape(h, argb.bytesPerLine())
    px = raw[:, : w * 4].reshape(h, w, 4)
    blue, green, red, alpha = px[..., 0], px[..., 1], px[..., 2], px[..., 3]
    gray = red * 0.299 + green * 0.587 + blue * 0.114
    return gray.astype(np.uint8), alpha.copy()


def suggest_plot_area(path, qimage=None):
    """Best suggestion for the source at *path* (or the decoded *qimage*)."""
    if not path:
        return None
    try:
        real = os.path.realpath(path)
        stat = os.stat(real)
    except OSError:
        return None
    suggestion = _file_suggestion(real, stat.st_mtime_ns, stat.st_size)
    if suggestion is not None or qimage is None:
        return suggestion
    arrays = _qimage_arrays(qimage)
    if arrays is None:
        return None
    return suggest_from_raster(*arrays)
