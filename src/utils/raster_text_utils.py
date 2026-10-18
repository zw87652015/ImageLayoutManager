"""Raster text size matching.

Pipeline
--------
1. ``regions_from_detections`` turns OCR boxes into ``RasterTextRegion``
   candidates and decides whether each one is *safe* to edit: the label must
   sit on a uniform background and its glyphs must not touch anything else.
2. ``build_raster_override_spec`` converts the project-wide text-group size
   (points in the final figure) into a per-region scale factor, taking the
   panel's physical scale (fit/crop/rotation/layout) into account.
3. ``apply_raster_text_overrides`` renders the spec: the glyph pixels are
   extracted as an RGBA layer, the original box is filled with background,
   the layer is scaled and composited back around its anchor.  Regions whose
   enlarged footprint would collide with other content are skipped and
   reported instead of damaging the figure.

A box's height is set by its tallest letters, so a line mixing capitals with
plain lowercase has dead space above the short ones — and any *other* nearby
shape (a diagram pointer, a corner) that happens to sit in that gap would
otherwise look like it's part of the label. ``_classify_text_pixels`` (used
by both step 1's safety check and step 3's extraction) separates the two via
connected components: real glyphs reach the text line's shared baseline,
disconnected floating shapes usually don't. Anything classified as foreign
is excluded from extraction/scaling and left un-erased on the canvas.

The original file is never modified; everything is regenerated from it.
"""

from __future__ import annotations

import json
import math
import os
from typing import List, Optional, Tuple

from PIL import Image

from src.model.data_model import RasterTextRegion
from src.utils.raster_text_frame import image_bounds, to_image, to_text

# Ink-height fractions of the em size, measured on Arial, MS YaHei and SimSun.
# A label's ink box height depends on which characters it contains, so the em
# can only be recovered by asking what the *text* should reach: "Response"
# spans cap-height plus a descender (~0.92 em) while "concentration" is only
# x-height (~0.54 em). Dividing every label by one constant biased the
# estimate by up to 30%, which then de-synced raster panels from SVG panels
# sharing the same text group.
CAP_HEIGHT_RATIO = 0.72     # capitals/digits; also the fallback for unknown text
X_HEIGHT_RATIO = 0.54       # lowercase without ascenders or descenders
ASCENDER_RATIO = 0.73       # b d f h k l t, i/j dots, brackets
DESCENDER_RATIO = 0.205     # added below the baseline by g j p q y, brackets
CJK_RATIO = 0.94            # CJK glyphs nearly fill their em box

_CAP_CHARS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")
_ASCENDER_CHARS = set("bdfhkltij([{)]}|/\\!?\"'#$&*@£€§")
_DESCENDER_CHARS = set("gjpqy,;([{)]}|/\\@_$µμ")
_X_HEIGHT_CHARS = set("acemnorsuvwxzµμ")


def _is_wide_script(char: str) -> bool:
    """True for CJK and other full-width glyphs that fill the em box."""
    return any(start <= ord(char) <= end for start, end in (
        (0x1100, 0x11FF), (0x2E80, 0xA4CF), (0xA960, 0xA97F),
        (0xAC00, 0xD7FF), (0xF900, 0xFAFF), (0xFE30, 0xFE4F),
        (0xFF00, 0xFF60), (0xFFE0, 0xFFE6), (0x20000, 0x3FFFF),
    ))


def ink_ratio_for_text(text: str) -> float:
    """Expected ink-box height as a fraction of the em for *text*.

    Falls back to the capital-height ratio when the text is unknown or has no
    recognised characters, which matches the previous behaviour rather than
    inventing a size. Still an estimate — the exact value depends on the
    font, which the pixels do not record — so the inspector keeps the
    resulting size editable.
    """
    stripped = (text or "").strip()
    if not stripped:
        return CAP_HEIGHT_RATIO
    if any(_is_wide_script(char) for char in stripped):
        return CJK_RATIO
    top = 0.0
    bottom = 0.0
    for char in stripped:
        if char in _ASCENDER_CHARS:
            top = max(top, ASCENDER_RATIO)
        elif char in _CAP_CHARS:
            top = max(top, CAP_HEIGHT_RATIO)
        elif char in _X_HEIGHT_CHARS:
            top = max(top, X_HEIGHT_RATIO)
        if char in _DESCENDER_CHARS:
            bottom = DESCENDER_RATIO
    if top <= 0.0:
        # Punctuation-only or an unrecognised alphabet: keep the old constant
        # instead of guessing from marks that may sit anywhere on the line.
        return CAP_HEIGHT_RATIO
    return top + bottom


# Max channel difference from the background that still counts as background.
BG_TOLERANCE = 40
# Channel difference at which a pixel is treated as fully opaque foreground.
FG_FULL = 80
# Padding (px) added around OCR boxes so anti-aliased edges are included.
BOX_PAD = 3
# Tolerance used only to judge whether the background is flat (gradients /
# textures fail this even though many of their pixels still pass the wider
# BG_TOLERANCE used to separate ink from background).
FLAT_TOLERANCE = 20
ANCHORS = ("center", "left", "right", "top", "bottom")


def _np():
    import numpy as np
    return np


def _hex_to_rgb(value: str) -> Tuple[int, int, int]:
    v = value.lstrip('#')
    return tuple(int(v[i:i + 2], 16) for i in (0, 2, 4))


def _rgb_to_hex(rgb) -> str:
    return '#%02x%02x%02x' % tuple(int(c) for c in rgb[:3])


def _clip_box(x, y, w, h, img_w, img_h):
    x0, y0 = max(0, int(x)), max(0, int(y))
    x1, y1 = min(img_w, int(x + w)), min(img_h, int(y + h))
    return x0, y0, max(0, x1 - x0), max(0, y1 - y0)


def _dominant_color(arr_rgb) -> Tuple[Tuple[int, int, int], float]:
    """Background colour of *arr_rgb* and the fraction of pixels matching it.

    Background pixels normally vastly outnumber ink pixels in a text-label
    box, so the per-channel median is a robust first estimate regardless of
    *where* the ink sits — unlike an edge-pixel estimate, which a tightly
    fit box full of mixed-height letters (capitals vs. lowercase, ascenders
    and descenders reaching the border) can easily throw off. The estimate
    is refined to the mean of pixels actually close to that median, which
    also absorbs sensor/JPEG speckle without being fooled by it.
    """
    np = _np()
    flat = arr_rgb.reshape(-1, 3).astype(np.int32)
    candidate = np.median(flat, axis=0)
    tight = np.max(np.abs(flat - candidate), axis=1) <= FLAT_TOLERANCE
    frac = float(tight.mean())
    color = np.median(flat[tight], axis=0) if tight.any() else candidate
    return tuple(int(round(v)) for v in color), frac


def sample_background(arr, x, y, w, h) -> Tuple[int, int, int]:
    """Background colour = the box's dominant colour (see ``_dominant_color``)."""
    crop = arr[y:y + h, x:x + w, :3]
    color, _frac = _dominant_color(crop)
    return color


def _crosses_boundary(arr, x, y, w, h, bg) -> bool:
    """True when foreground continues from just inside the box to just
    outside it on some edge — a real object (axis line, rule, neighbouring
    graphic) cut by the box, not merely the label's own glyphs reaching a
    snugly-fit edge.  A short run only (not a lone anti-aliased pixel)
    counts, matching the tolerance used for the interior analysis.
    """
    H, W = arr.shape[:2]

    def _run_frac(strip):
        if len(strip) == 0:
            return 0.0
        fg = int((_distance(strip[:, None, :], bg) > BG_TOLERANCE).sum())
        return fg / len(strip) if fg >= 2 else 0.0

    if y > 0 and _run_frac(arr[y - 1, x:x + w, :3]) >= 0.02:
        return True
    if y + h < H and _run_frac(arr[y + h, x:x + w, :3]) >= 0.02:
        return True
    if x > 0 and _run_frac(arr[y:y + h, x - 1, :3]) >= 0.02:
        return True
    if x + w < W and _run_frac(arr[y:y + h, x + w, :3]) >= 0.02:
        return True
    return False


def _distance(arr_rgb, bg):
    np = _np()
    return np.max(np.abs(arr_rgb.astype(np.int16) - np.array(bg, dtype=np.int16)), axis=2)


def _alpha(dist):
    np = _np()
    return np.clip(dist.astype(np.float32) / FG_FULL, 0.0, 1.0)


def _tight_bbox(alpha, threshold=0.5):
    np = _np()
    ys, xs = np.nonzero(alpha > threshold)
    if len(xs) == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1)


def _connected_components(mask):
    """Label 4-connected True regions of a 2D bool array.

    Returns ``(labels, count)`` with ``labels`` an int array the same shape
    as *mask* (0 = background, 1..count = components). Uses OpenCV when
    available (shipped transitively with the default RapidOCR backend) and
    falls back to a small pure-Python union-find otherwise, since regions
    here are always tiny (a text label, not a full image).
    """
    np = _np()
    if not mask.any():
        return np.zeros(mask.shape, dtype=np.int32), 0
    try:
        import cv2
        count, labels = cv2.connectedComponents(mask.astype(np.uint8), connectivity=4)
        return labels.astype(np.int32), count - 1
    except Exception:
        return _connected_components_py(mask)


def _connected_components_py(mask):
    np = _np()
    H, W = mask.shape
    labels = np.zeros((H, W), dtype=np.int32)
    parent = [0]

    def find(a):
        while parent[a] != a:
            a = parent[a]
        return a

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    next_label = 0
    for y in range(H):
        row = mask[y]
        if not row.any():
            continue
        for x in range(W):
            if not row[x]:
                continue
            left = labels[y, x - 1] if x > 0 and mask[y, x - 1] else 0
            up = labels[y - 1, x] if y > 0 and mask[y - 1, x] else 0
            if left and up:
                lbl = min(left, up)
                labels[y, x] = lbl
                union(left, up)
            elif left or up:
                labels[y, x] = left or up
            else:
                next_label += 1
                parent.append(next_label)
                labels[y, x] = next_label

    if next_label == 0:
        return labels, 0
    remap = {}
    out_count = 0
    ys, xs = np.nonzero(labels)
    for y, x in zip(ys, xs):
        root = find(int(labels[y, x]))
        if root not in remap:
            out_count += 1
            remap[root] = out_count
        labels[y, x] = remap[root]
    return labels, out_count


# Characters whose ink (or part of it) legitimately floats above the baseline,
# so a disconnected blob in their column is text, not a stray object.
_FLOATING_CHARS = set("-–—‐−·•°'\"‘’“”`´^~*=+<>±×÷%:;?!ij¡¿²³¹⁰⁴⁵⁶⁷⁸⁹ª\u2032\u2033\u00b7")


def _char_may_float(ch: str) -> bool:
    if not ch:
        return False
    if ch in _FLOATING_CHARS:
        return True
    import unicodedata
    if len(unicodedata.normalize("NFD", ch)) > 1:   # accented letter: é, ü, ñ …
        return True
    return ord(ch) >= 0x2E80                          # CJK etc.: multi-stroke glyphs


def _classify_text_pixels(alpha, threshold=0.5, chars=None, origin=(0, 0)):
    """Split a box's non-background pixels into the label's own glyphs vs.
    incidental foreign content, and return the glyph-only tight bbox.

    A rectangular box's height is set by its tallest letters, so when a line
    mixes capitals/ascenders with plain lowercase, there is dead space above
    the short letters — and if some *other* nearby shape (a diagram pointer,
    a corner, a leader line) happens to poke into exactly that gap, it sits
    fully inside the box without touching any edge, so it looks completely
    clean under any purely edge/interior-colour check.

    Geometry alone can't settle every blob: a hyphen or an i-dot never
    reaches the baseline either. So the OCR's *recognised characters*
    (``chars`` = ``[char, x, y, w, h]`` in image px, ``origin`` = the box's
    top-left) act as the judge: a floating blob is text when the character
    occupying its columns is one whose ink legitimately floats ("-", ":",
    "i", accented letters, …); under a plain letter/digit it is foreign.
    Without character info we fall back to geometry: components reaching the
    shared baseline are text, so is anything in the x-height band between
    baseline-reaching glyphs (a hyphen), and small marks centred close above
    a glyph (dots/accents).

    Returns ``(text_alpha, foreign_mask, glyph_box)``. When classification
    can't be done confidently (one blob, or nothing reaches the estimated
    baseline), everything is kept as text — never invent an exclusion we're
    not sure about.
    """
    np = _np()
    binary = alpha > threshold
    labels, count = _connected_components(binary)
    if count <= 1:
        return alpha, np.zeros(alpha.shape, dtype=bool), _tight_bbox(alpha, threshold)

    comps = []
    for lbl in range(1, count + 1):
        ys, xs = np.nonzero(labels == lbl)
        if len(xs) == 0:
            continue
        comps.append({"label": lbl, "top": int(ys.min()), "bottom": int(ys.max()),
                      "left": int(xs.min()), "right": int(xs.max()), "area": len(xs)})
    if len(comps) <= 1:
        return alpha, np.zeros(alpha.shape, dtype=bool), _tight_bbox(alpha, threshold)

    bottoms = np.array([c["bottom"] for c in comps], dtype=np.float64)
    heights = np.array([c["bottom"] - c["top"] + 1 for c in comps], dtype=np.float64)
    baseline = float(np.median(bottoms))
    tol = max(2.0, 0.25 * float(np.median(heights)))

    is_text = {c["label"]: (c["top"] <= baseline + tol and c["bottom"] >= baseline - tol)
              for c in comps}
    text_comps = [c for c in comps if is_text[c["label"]]]
    if not text_comps:
        # Nothing reached the estimated baseline — don't trust the estimate;
        # keep the old, permissive behaviour rather than risk cutting real text.
        return alpha, np.zeros(alpha.shape, dtype=bool), _tight_bbox(alpha, threshold)

    text_area_med = float(np.median([c["area"] for c in text_comps]))
    x_top = float(np.median([c["top"] for c in text_comps]))
    ox = origin[0]
    char_cols = [(str(c[0]), int(c[1]) - ox, int(c[1]) + int(c[3]) - 1 - ox)
                 for c in (chars or []) if len(c) >= 5]

    def _owners(c, margin=2):
        return [ch for ch, left, right in char_cols
                if c["left"] <= right + margin and c["right"] >= left - margin]

    def _is_diacritic(c):
        # Small, close above, and centred on a supporting glyph.
        cx = (c["left"] + c["right"]) / 2.0
        for t in text_comps:
            if c["bottom"] >= t["top"]:
                continue
            gap = t["top"] - c["bottom"]
            offset = abs(cx - (t["left"] + t["right"]) / 2.0)
            if (c["area"] <= 0.6 * text_area_med
                    and gap <= max(2.0, 0.3 * (t["bottom"] - t["top"] + 1))
                    and offset <= max(2.0, 0.3 * (t["right"] - t["left"] + 1))):
                return True
        return False

    for c in comps:
        if is_text[c["label"]]:
            continue
        if char_cols:
            owners = _owners(c)
            if owners and any(_char_may_float(ch) for ch in owners):
                is_text[c["label"]] = True
            elif owners and _is_diacritic(c):
                is_text[c["label"]] = True      # e.g. an "i" the OCR read as "l"
            continue
        # No character info: geometric fallback.
        in_band = c["top"] >= x_top - tol and c["bottom"] <= baseline + tol
        if in_band or _is_diacritic(c):
            is_text[c["label"]] = True

    text_labels = [c["label"] for c in comps if is_text[c["label"]]]
    text_mask = np.isin(labels, text_labels)
    foreign_mask = binary & ~text_mask
    text_alpha = np.where(text_mask, alpha, 0.0)
    return text_alpha, foreign_mask, _tight_bbox(text_alpha, threshold)


def analyze_region(arr, x, y, w, h, background: Optional[str] = None, chars=None) -> dict:
    """Inspect a candidate box.  Returns dict(bg, glyph_box, reason).

    ``reason`` is None when the region looks safe to edit; otherwise a short
    advisory string: ``no_text`` | ``background`` | ``touching``.
    ``glyph_box`` is the tight bbox of the label's own glyphs (see
    ``_classify_text_pixels``) in image pixels — any incidental foreign
    content inside the box is excluded from it.  ``foreign_excluded`` is
    True when such content was found (informational; doesn't set ``reason``,
    since that content is left untouched rather than being a hazard).

    Background is the box's dominant colour, which stays reliable even when
    a mix of tall/short glyphs (capitals vs. lowercase, ascenders and
    descenders) makes the label's own ink reach the box's edges — that is
    normal for text and must not, by itself, look like "something else is in
    here". Genuine hazards are judged by what happens *outside* the box:
    "background" means no single colour dominates the box's own interior
    (gradient/photo); "touching" means a foreground run continues from just
    inside the box to just outside it — an external object cut by the box.
    """
    H, W = arr.shape[:2]
    x, y, w, h = _clip_box(x, y, w, h, W, H)
    if w == 0 or h == 0:
        return {"bg": "#ffffff", "glyph_box": None, "reason": "no_text", "foreign_excluded": False}
    crop = arr[y:y + h, x:x + w, :3]
    if background:
        bg, bg_frac = _hex_to_rgb(background), None
    else:
        bg, bg_frac = _dominant_color(crop)
    alpha = _alpha(_distance(crop, bg))
    _text_alpha, foreign_mask, tight = _classify_text_pixels(alpha, chars=chars, origin=(x, y))
    if tight is None:
        return {"bg": _rgb_to_hex(bg), "glyph_box": None, "reason": "no_text", "foreign_excluded": False}
    tx, ty, tw, th = tight
    result = {"bg": _rgb_to_hex(bg), "glyph_box": (x + tx, y + ty, tw, th), "reason": None,
             "foreign_excluded": bool(foreign_mask.any())}

    # Gradient / textured / photographic background: no single colour
    # dominates the box's interior. Skipped when the caller supplied a fixed
    # background (re-checking a region against its already-known colour).
    if bg_frac is not None and bg_frac < 0.55:
        result["reason"] = "background"
        return result

    if _crosses_boundary(arr, x, y, w, h, bg):
        result["reason"] = "touching"
    return result


def _fit_box(arr, x, y, w, h, pad: int = BOX_PAD):
    """Snap an OCR box to its glyphs, then pad each side independently.

    OCR boxes are loose and tick marks / axis lines often sit a few pixels
    away, so a fixed pad would swallow them and the region would be flagged
    as "touching" although the label itself is perfectly isolated.  Instead:
    shrink to the tight foreground bbox, then grow each side one pixel at a
    time while the new row/column is still clean background.
    """
    np = _np()
    H, W = arr.shape[:2]
    if w == 0 or h == 0:
        return x, y, w, h
    bg = sample_background(arr, x, y, w, h)
    tight = _tight_bbox(_alpha(_distance(arr[y:y + h, x:x + w, :3], bg)))
    if tight is None:
        return x, y, w, h
    tx, ty, tw, th = tight
    x0, y0, x1, y1 = x + tx, y + ty, x + tx + tw, y + ty + th   # half-open

    def _clean(strip):
        if len(strip) == 0:
            return False
        fg = int((_distance(strip[:, None, :], bg) > BG_TOLERANCE).sum())
        return fg < 2 or fg / len(strip) < 0.02

    for _ in range(pad):
        if y0 > 0 and _clean(arr[y0 - 1, x0:x1, :3]):
            y0 -= 1
        if y1 < H and _clean(arr[y1, x0:x1, :3]):
            y1 += 1
        if x0 > 0 and _clean(arr[y0:y1, x0 - 1, :3]):
            x0 -= 1
        if x1 < W and _clean(arr[y0:y1, x1, :3]):
            x1 += 1
    return x0, y0, x1 - x0, y1 - y0


def _text_frame_patch(arr, x, y, w, h, angle, margin, fill):
    """Resample *arr* into the text frame of *angle* (numpy bilinear).

    Returns ``(patch, origin)`` where patch is a uint8 HxWx3 image covering
    text-frame ``[x-margin, x+w+margin) x [y-margin, y+h+margin)`` and
    origin is its top-left ``(x-margin, y-margin)``.  A pixel centre sits
    at integer-plus-0.5 in every frame; patch pixel (row, col) samples the
    image at the centre ``to_image(origin_u + col + 0.5, origin_v + row +
    0.5)`` expressed in ``coord - 0.5`` index space.  Samples outside the
    image take *fill* so image edges do not look like ink.
    """
    np = _np()
    H, W = arr.shape[:2]
    m = int(margin)
    wp, hp = int(w) + 2 * m, int(h) + 2 * m
    uu = x - m + np.arange(wp, dtype=np.float64) + 0.5
    vv = y - m + np.arange(hp, dtype=np.float64) + 0.5
    a = math.radians(angle)
    c, s = math.cos(a), math.sin(a)
    px = uu[None, :] * c - vv[:, None] * s
    py = uu[None, :] * s + vv[:, None] * c
    col, row = px - 0.5, py - 0.5
    c0, r0 = np.floor(col).astype(np.int64), np.floor(row).astype(np.int64)
    wc, wr = col - c0, row - r0
    fillf = np.asarray(fill, dtype=np.float32)
    patch = np.zeros((hp, wp, 3), dtype=np.float32)
    for rr, wrow in ((r0, 1.0 - wr), (r0 + 1, wr)):
        for cc, wcol in ((c0, 1.0 - wc), (c0 + 1, wc)):
            ok = (rr >= 0) & (rr < H) & (cc >= 0) & (cc < W)
            vals = arr[np.clip(rr, 0, H - 1), np.clip(cc, 0, W - 1), :3].astype(np.float32)
            vals = np.where(ok[..., None], vals, fillf)
            patch += vals * (wrow * wcol)[..., None]
    return patch.astype(np.uint8), (x - m, y - m)


def _rotated_margin(h):
    return max(BOX_PAD + 2, int(round(0.15 * h)))


def _rotated_patch(arr, x, y, w, h, angle):
    """Patch + origin for a rotated region; fill = dominant colour of the
    region's image AABB so image edges don't read as ink."""
    H, W = arr.shape[:2]
    ax, ay, aw, ah = _clip_box(*image_bounds(x, y, w, h, angle), W, H)
    fill = _dominant_color(arr[ay:ay + ah, ax:ax + aw, :3])[0] if aw and ah else (255, 255, 255)
    return _text_frame_patch(arr, x, y, w, h, angle, _rotated_margin(h), fill)


def _rotated_masks(arr, x, y, w, h, angle, background, chars):
    """Source-frame masks for a rotated region (``angle != 0``).

    Returns ``dict(origin, inside, text_alpha, foreign, bg, glyph_box)``:
    ``origin`` is the top-left of the region's image AABB clipped to the
    image; ``inside`` marks the source pixels whose centre maps inside the
    text-frame box; ``text_alpha``/``foreign`` share that crop's frame;
    ``glyph_box`` is the tight glyph box in the *text frame* (or None).
    The text-frame text mask is dilated by 1 px before mapping back so
    anti-aliased glyph edges are included.
    """
    np = _np()
    H, W = arr.shape[:2]
    ax, ay, aw, ah = _clip_box(*image_bounds(x, y, w, h, angle), W, H)
    src = arr[ay:ay + ah, ax:ax + aw, :3]
    m = _rotated_margin(h)
    patch, (ox, oy) = _rotated_patch(arr, x, y, w, h, angle)
    if background:
        bg = _hex_to_rgb(background)
    else:
        bg = _dominant_color(patch[m:m + h, m:m + w])[0] if h and w else (255, 255, 255)
    cols = ax + np.arange(aw, dtype=np.float64) + 0.5
    rows = ay + np.arange(ah, dtype=np.float64) + 0.5
    ca, sa = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    u = cols[None, :] * ca + rows[:, None] * sa
    v = -cols[None, :] * sa + rows[:, None] * ca
    inside = (u >= x) & (u < x + w) & (v >= y) & (v < y + h)
    text_mask = np.zeros(patch.shape[:2], dtype=bool)
    tight = None
    if h > 0 and w > 0 and patch.shape[0] >= m + h and patch.shape[1] >= m + w:
        box_alpha = _alpha(_distance(patch[m:m + h, m:m + w], bg))
        text_alpha_box, _foreign_box, tight = _classify_text_pixels(
            box_alpha, chars=chars, origin=(x, y))
        text_mask[m:m + h, m:m + w] = text_alpha_box > 0.5
    dil = text_mask.copy()
    dil[1:, :] |= text_mask[:-1, :]
    dil[:-1, :] |= text_mask[1:, :]
    dil[:, 1:] |= text_mask[:, :-1]
    dil[:, :-1] |= text_mask[:, 1:]
    ji = np.floor(u - ox).astype(np.int64)
    ii = np.floor(v - oy).astype(np.int64)
    ok = (ii >= 0) & (ii < dil.shape[0]) & (ji >= 0) & (ji < dil.shape[1])
    sampled = np.zeros((ah, aw), dtype=bool)
    sampled[ok] = dil[ii[ok], ji[ok]]
    text_src = inside & sampled
    src_alpha = _alpha(_distance(src, bg))
    text_alpha = np.where(text_src, src_alpha, 0.0).astype(np.float32)
    foreign = inside & (src_alpha > 0.5) & ~text_src
    glyph_box = None
    if tight is not None:
        tx, ty, tw, th = tight
        glyph_box = (x + tx, y + ty, tw, th)
    return {"origin": (ax, ay), "inside": inside, "text_alpha": text_alpha,
            "foreign": foreign, "bg": bg, "glyph_box": glyph_box}


_DASH_CHARS = "-−–—‐"


def _trim_dash_tick(arr, x, y, w, h, text, chars, info):
    """Trim a leading/trailing "dash" that is really a tick mark.

    Colorbar/axis ticks often get read as part of the label ("-6.5"), and
    the tick's ink continuing out of the box marks the region "touching".
    When the label starts or ends with a dash and the box's edge component
    (or the matching character box) looks like a tick, cut it off and
    re-analyse; the trim is accepted only when the new box is clean.
    Returns ``((x, y, w, h), text, chars, info)`` or None.  All coordinates
    are in the caller's frame (image or text frame).
    """
    np = _np()
    stripped = (text or "").strip()
    if len(stripped) <= 1:
        return None
    bg = _hex_to_rgb(info["bg"]) if info.get("bg") else sample_background(arr, x, y, w, h)
    glyph_h = info["glyph_box"][3] if info.get("glyph_box") else 0
    for side in ("left", "right"):
        dash = stripped[0] if side == "left" else stripped[-1]
        if dash not in _DASH_CHARS:
            continue
        boundary = None
        new_chars = list(chars)
        edge_char = None
        if side == "left" and chars:
            first = min(chars, key=lambda c: c[1])
            if str(first[0]) == dash:
                edge_char = first
                boundary = first[1] + first[3]
        elif side == "right" and chars:
            last = max(chars, key=lambda c: c[1] + c[3])
            if str(last[0]) == dash:
                edge_char = last
                boundary = last[1]
        if boundary is None and glyph_h:
            alpha = _alpha(_distance(arr[y:y + h, x:x + w, :3], bg))
            labels, count = _connected_components(alpha > 0.5)
            comps = []
            for lbl in range(1, count + 1):
                ys, xs = np.nonzero(labels == lbl)
                if len(xs):
                    comps.append((int(xs.min()), int(xs.max()),
                                  int(ys.min()), int(ys.max())))
            if comps:
                if side == "left":
                    comp = min(comps, key=lambda c: c[0])
                    cw, chh = comp[1] - comp[0] + 1, comp[3] - comp[2] + 1
                    if chh <= 0.35 * glyph_h and cw >= 1.5 * chh:
                        boundary = x + comp[1] + 1
                else:
                    comp = max(comps, key=lambda c: c[1])
                    cw, chh = comp[1] - comp[0] + 1, comp[3] - comp[2] + 1
                    if chh <= 0.35 * glyph_h and cw >= 1.5 * chh:
                        boundary = x + comp[0]
        if boundary is None:
            continue
        if edge_char is not None:
            new_chars = [c for c in chars if c is not edge_char]
        if side == "left":
            nx, ny, nw, nh = boundary, y, x + w - boundary, h
            ntext = stripped[1:].lstrip()
        else:
            nx, ny, nw, nh = x, y, boundary - x, h
            ntext = stripped[:-1].rstrip()
        if nw <= 0 or not ntext:
            continue
        fx, fy, fw, fh = _fit_box(arr, nx, ny, nw, nh)
        ninfo = analyze_region(arr, fx, fy, fw, fh, chars=new_chars)
        if ninfo["reason"] is None:
            return (fx, fy, fw, fh), ntext, new_chars, ninfo
    return None


def regions_from_detections(image: Image.Image, detections) -> List[Tuple[RasterTextRegion, Optional[str]]]:
    """Build candidate regions from OCR detections.

    Returns ``[(region, reason)]`` where ``reason`` is None for editable
    regions.  Boxes are padded by ``BOX_PAD`` and the em size is estimated
    from the glyph height (cap-height heuristic); users can correct it.
    """
    np = _np()
    arr = np.asarray(image.convert("RGB"))
    H, W = arr.shape[:2]
    out = []
    for det in detections:
        angle = getattr(det, "angle", 0.0) or 0.0
        chars = [list(c) for c in (getattr(det, "chars", None) or [])]
        if angle != 0:
            # Rotated label: geometry lives in the text frame (see
            # raster_text_frame). Analyse a resampled, axis-aligned patch
            # of that frame so the usual checks apply unchanged.
            patch, (ox, oy) = _rotated_patch(arr, det.x, det.y, det.w, det.h, angle)
            m = _rotated_margin(det.h)
            pchars = [[c[0], c[1] - ox, c[2] - oy, c[3], c[4]]
                      for c in chars if len(c) >= 5]
            px, py, pw, ph = _fit_box(patch, m, m, det.w, det.h)
            info = analyze_region(patch, px, py, pw, ph, chars=pchars)
            text = det.text
            if info["reason"] == "touching":
                trimmed = _trim_dash_tick(patch, px, py, pw, ph, text, pchars, info)
                if trimmed is not None:
                    (px, py, pw, ph), text, pchars, info = trimmed
            x, y, w, h = px + ox, py + oy, pw, ph
            chars = [[c[0], c[1] + ox, c[2] + oy, c[3], c[4]] for c in pchars]
            glyph_h = info["glyph_box"][3] if info["glyph_box"] else 0.0
            region = RasterTextRegion(
                x=x, y=y, w=w, h=h, text=text, vertical=False, angle=angle,
                font_size_px=round(glyph_h / ink_ratio_for_text(text), 2),
                background=info["bg"], enabled=info["reason"] is None,
                warning=info["reason"], foreign_excluded=info["foreign_excluded"],
                chars=chars,
            )
            out.append((region, info["reason"]))
            continue
        x, y, w, h = _fit_box(arr, *_clip_box(det.x, det.y, det.w, det.h, W, H))
        info = analyze_region(arr, x, y, w, h, chars=chars)
        text = det.text
        if info["reason"] == "touching":
            trimmed = _trim_dash_tick(arr, x, y, w, h, text, chars, info)
            if trimmed is not None:
                (x, y, w, h), text, chars, info = trimmed
        vertical = det.h > det.w * 1.5 and len(det.text.strip()) > 1
        glyph_h = 0.0
        if info["glyph_box"]:
            gx, gy, gw, gh = info["glyph_box"]
            glyph_h = gw if vertical else gh
        region = RasterTextRegion(
            x=x, y=y, w=w, h=h, text=text, vertical=vertical,
            font_size_px=round(glyph_h / ink_ratio_for_text(text), 2),
            background=info["bg"], enabled=info["reason"] is None,
            warning=info["reason"], foreign_excluded=info["foreign_excluded"],
            chars=chars,
        )
        out.append((region, info["reason"]))
    return out


def reanalyze_region(image: Image.Image, region: RasterTextRegion) -> Optional[str]:
    """Re-run the safety check for a (possibly user-edited) region box and
    refresh its background / size estimate.  Returns the advisory reason."""
    np = _np()
    arr = np.asarray(image.convert("RGB"))
    angle = getattr(region, "angle", 0.0) or 0.0
    if angle != 0:
        m = _rotated_margin(region.h)
        patch, (ox, oy) = _rotated_patch(arr, region.x, region.y, region.w, region.h, angle)
        pchars = [[c[0], c[1] - ox, c[2] - oy, c[3], c[4]]
                  for c in region.chars if len(c) >= 5]
        info = analyze_region(patch, m, m, region.w, region.h, chars=pchars)
        region.background = info["bg"]
        region.warning = info["reason"]
        region.foreign_excluded = info["foreign_excluded"]
        if info["glyph_box"]:
            region.font_size_px = round(
                info["glyph_box"][3] / ink_ratio_for_text(region.text), 2)
        return info["reason"]
    info = analyze_region(arr, region.x, region.y, region.w, region.h, chars=region.chars)
    region.background = info["bg"]
    region.warning = info["reason"]
    region.foreign_excluded = info["foreign_excluded"]
    if info["glyph_box"]:
        gx, gy, gw, gh = info["glyph_box"]
        region.font_size_px = round(
            (gw if region.vertical else gh) / ink_ratio_for_text(region.text), 2)
    return info["reason"]


def is_raster_path(path: Optional[str]) -> bool:
    from src.utils.image_proxy import RASTER_EXTENSIONS
    return bool(path) and os.path.splitext(path)[1].lower() in RASTER_EXTENSIONS


def raster_pt_per_px(project, cell, layout_result=None, content_size_mm=None):
    """Point size of one source pixel in *cell*'s raster image, or None.

    Derived from the image's pixel size (PIL header only, no decode) and the
    cell's mm-per-unit scale.  None when the image is missing/unreadable or
    not a raster file.
    """
    path = getattr(cell, 'image_path', None)
    if not is_raster_path(path) or not os.path.exists(path):
        return None
    try:
        with Image.open(path) as im:
            img_w, img_h = im.size
    except Exception:
        return None
    from src.utils.panel_scale import panel_mm_per_unit
    mm_per_px = panel_mm_per_unit(project, cell, img_w, img_h, layout_result, content_size_mm)
    return mm_per_px * 72.0 / 25.4


def build_raster_override_spec(project, cell, layout_result=None,
                               content_size_mm=None) -> Optional[dict]:
    """Per-render spec for *cell* or None when nothing needs to change.

    The spec is JSON-serialisable so the image proxy can hash it as a cache
    key and the worker thread can apply it without touching the model.
    """
    regions = [r for r in getattr(cell, 'raster_text_regions', [])
               if r.enabled and r.group_id and r.font_size_px > 0]
    if not regions:
        return None
    pt_per_px = raster_pt_per_px(project, cell, layout_result, content_size_mm)
    if pt_per_px is None:
        return None
    groups = {g.id: g for g in getattr(project, 'svg_text_groups', [])}
    entries = []
    for r in regions:
        group = groups.get(r.group_id)
        if group is None:
            continue
        current_pt = r.font_size_px * pt_per_px
        if current_pt <= 0:
            continue
        entry = {
            "id": r.id, "x": r.x, "y": r.y, "w": r.w, "h": r.h,
            "scale": round(group.font_size_pt / current_pt, 5),
            "anchor": r.anchor if r.anchor in ANCHORS else "center",
            "background": r.background,
            "chars": [list(c) for c in (r.chars or [])],
        }
        if getattr(r, "angle", 0.0):
            entry["angle"] = r.angle
        entries.append(entry)
    return {"regions": entries} if entries else None


def spec_key(spec: dict) -> str:
    return json.dumps(spec, sort_keys=True, separators=(',', ':'))


def _place(tx, ty, tw, th, nw, nh, anchor):
    if anchor == "left":
        return tx, ty + (th - nh) / 2
    if anchor == "right":
        return tx + tw - nw, ty + (th - nh) / 2
    if anchor == "top":
        return tx + (tw - nw) / 2, ty
    if anchor == "bottom":
        return tx + (tw - nw) / 2, ty + th - nh
    return tx + (tw - nw) / 2, ty + (th - nh) / 2


def get_raster_text_mask(image: Image.Image, region):
    np = _np()
    arr = np.asarray(image.convert('RGB'))
    angle = getattr(region, "angle", 0.0) or 0.0
    if angle != 0:
        masks = _rotated_masks(arr, region.x, region.y, region.w, region.h,
                               angle, region.background, region.chars)
        return masks["text_alpha"], masks["foreign"], masks["origin"]
    x, y, w, h = _clip_box(region.x, region.y, region.w, region.h, image.width, image.height)
    if not w or not h:
        return np.zeros((0, 0)), np.zeros((0, 0), dtype=bool), (x, y)
    bg = _hex_to_rgb(region.background) if region.background else sample_background(arr, x, y, w, h)
    alpha = _alpha(_distance(arr[y:y + h, x:x + w], bg))
    text_alpha, foreign, _tight = _classify_text_pixels(alpha, chars=region.chars, origin=(x, y))
    return text_alpha, foreign, (x, y)


def apply_raster_text_overrides(image: Image.Image, spec: dict,
                                overlay_masks=None) -> Tuple[Image.Image, List[dict]]:
    """Return (processed RGBA image, report).

    Report entries: ``{"id", "status", "scale"}`` with status one of
    ``applied`` | ``skipped_no_text`` | ``skipped_bounds`` | ``skipped_collision``.
    """
    np = _np()
    src = image.convert("RGBA")
    arr = np.array(src)
    out = arr.copy()
    H, W = arr.shape[:2]
    report = []
    layers = []

    for entry in spec.get("regions", []):
        angle = float(entry.get("angle", 0) or 0)
        if angle != 0:
            # Rotated region: entry x/y/w/h and chars are text-frame
            # coordinates; masks and the erased area are source pixels.
            masks = _rotated_masks(arr, entry["x"], entry["y"], entry["w"],
                                   entry["h"], angle, entry.get("background"),
                                   entry.get("chars"))
            ax, ay = masks["origin"]
            ah, aw = masks["inside"].shape
            if overlay_masks is not None:
                overlay_masks[entry['id']] = {
                    'alpha': masks["text_alpha"], 'origin': (ax, ay),
                    'protected_mask': masks["foreign"], 'protected_origin': (ax, ay),
                }
            if masks["glyph_box"] is None or aw == 0 or ah == 0:
                report.append({"id": entry["id"], "status": "skipped_no_text", "scale": entry["scale"]})
                continue
            bg = masks["bg"]
            a2 = masks["text_alpha"]
            rgb = arr[ay:ay + ah, ax:ax + aw, :3].astype(np.float32)
            bgf = np.array(bg, dtype=np.float32)
            safe = np.maximum(a2, 0.05)[..., None]
            fg = np.clip(bgf + (rgb - bgf) / safe, 0, 255)
            fg[a2 < 0.05] = bgf
            layer = np.dstack([fg, a2[..., None] * 255.0]).astype(np.uint8)
            erased = masks["inside"] & ~masks["foreign"]
            region_rgb = out[ay:ay + ah, ax:ax + aw, :3]
            region_rgb[erased] = bg
            out[ay:ay + ah, ax:ax + aw, :3] = region_rgb
            region_alpha = out[ay:ay + ah, ax:ax + aw, 3]
            region_alpha[erased] = 255
            out[ay:ay + ah, ax:ax + aw, 3] = region_alpha
            layers.append((entry, angle, masks, (ax, ay, aw, ah), erased, layer))
            continue
        x, y, w, h = _clip_box(entry["x"], entry["y"], entry["w"], entry["h"], W, H)
        if w == 0 or h == 0:
            report.append({"id": entry["id"], "status": "skipped_no_text", "scale": entry["scale"]})
            continue
        bg = _hex_to_rgb(entry["background"]) if entry.get("background") else sample_background(arr, x, y, w, h)
        crop = arr[y:y + h, x:x + w, :3]
        alpha = _alpha(_distance(crop, bg))
        # Any incidental foreign content (e.g. a diagram pointer poking into
        # the gap a box picks up above short letters) is excluded from the
        # extracted glyph layer AND left un-erased below — it never moves.
        text_alpha, foreign_mask, tight = _classify_text_pixels(
            alpha, chars=entry.get("chars"), origin=(x, y))
        if overlay_masks is not None:
            overlay_masks[entry['id']] = {
                'alpha': text_alpha, 'origin': (x, y),
                'protected_mask': foreign_mask, 'protected_origin': (x, y),
            }
        if tight is None:
            report.append({"id": entry["id"], "status": "skipped_no_text", "scale": entry["scale"]})
            continue
        tx, ty, tw, th = tight
        a = text_alpha[ty:ty + th, tx:tx + tw]
        rgb = crop[ty:ty + th, tx:tx + tw].astype(np.float32)
        bgf = np.array(bg, dtype=np.float32)
        # Un-mix anti-aliased edge pixels so scaling does not drag the old
        # background colour along: pix = bg + alpha * (fg - bg)  =>  fg.
        safe = np.maximum(a, 0.05)[..., None]
        fg = np.clip(bgf + (rgb - bgf) / safe, 0, 255)
        fg[a < 0.05] = bgf
        layer = np.dstack([fg, a[..., None] * 255.0]).astype(np.uint8)
        layers.append((entry, (x, y, w, h), (x + tx, y + ty, tw, th), bg, layer))
        erase = ~foreign_mask
        region_rgb = out[y:y + h, x:x + w, :3]
        region_rgb[erase] = bg
        out[y:y + h, x:x + w, :3] = region_rgb
        region_alpha = out[y:y + h, x:x + w, 3]
        region_alpha[erase] = 255
        out[y:y + h, x:x + w, 3] = region_alpha

    for item in layers:
        if len(item) == 6:
            _apply_rotated(item, arr, out, report, overlay_masks)
            continue
        entry, box, glyph_box, bg, layer = item
        gx, gy, gw, gh = glyph_box
        s = float(entry["scale"])
        nw, nh = max(1, int(round(gw * s))), max(1, int(round(gh * s)))
        dx, dy = _place(gx, gy, gw, gh, nw, nh, entry.get("anchor", "center"))
        dx, dy = int(round(dx)), int(round(dy))
        if dx < 0 or dy < 0 or dx + nw > W or dy + nh > H:
            report.append({"id": entry["id"], "status": "skipped_bounds", "scale": s})
            _restore(out, arr, box)
            continue
        dest = out[dy:dy + nh, dx:dx + nw, :3]
        # Collision = a real object in the way, not a few noisy pixels.
        busy = (_distance(dest, bg) > BG_TOLERANCE).sum()
        if busy > max(4, 0.005 * dest.shape[0] * dest.shape[1]):
            report.append({"id": entry["id"], "status": "skipped_collision", "scale": s})
            _restore(out, arr, box)
            continue
        if (nw, nh) != (gw, gh):
            layer_img = Image.fromarray(layer, "RGBA").resize((nw, nh), Image.Resampling.LANCZOS)
            layer = np.asarray(layer_img)
        la = layer[..., 3:4].astype(np.float32) / 255.0
        dest[...] = (layer[..., :3].astype(np.float32) * la + dest.astype(np.float32) * (1 - la)).astype(np.uint8)
        if overlay_masks is not None:
            overlay_masks[entry['id']].update(alpha=la[..., 0], origin=(dx, dy))
        report.append({"id": entry["id"], "status": "applied", "scale": s})

    return Image.fromarray(out, "RGBA"), report


def _apply_rotated(item, arr, out, report, overlay_masks):
    """Place the scaled glyph layer for a rotated (angle != 0) entry.

    The layer covers the region's image AABB; it is scaled uniformly about
    the anchor point *P* (the glyph box's anchor mapped to image
    coordinates).  A uniform scale in image space is equally uniform in the
    text frame, so the scaled oriented glyph rect stays axis-aligned there,
    which is where the bounds/collision tests run.
    """
    np = _np()
    entry, angle, masks, (ax, ay, aw, ah), erased, layer = item
    s = float(entry["scale"])
    H, W = arr.shape[:2]
    bg = masks["bg"]
    gx, gy, gw, gh = masks["glyph_box"]
    anchor = entry.get("anchor", "center")
    if anchor == "left":
        pu, pv = gx, gy + gh / 2.0
    elif anchor == "right":
        pu, pv = gx + gw, gy + gh / 2.0
    elif anchor == "top":
        pu, pv = gx + gw / 2.0, gy
    elif anchor == "bottom":
        pu, pv = gx + gw / 2.0, gy + gh
    else:
        pu, pv = gx + gw / 2.0, gy + gh / 2.0
    px, py = to_image(pu, pv, angle)
    sgx, sgy = pu + (gx - pu) * s, pv + (gy - pv) * s
    sgw, sgh = gw * s, gh * s

    def _restore_erased():
        sub = out[ay:ay + ah, ax:ax + aw]
        sub[erased] = arr[ay:ay + ah, ax:ax + aw][erased]

    bx, by, bw, bh = image_bounds(sgx, sgy, sgw, sgh, angle)
    if bx < 0 or by < 0 or bx + bw > W or by + bh > H:
        report.append({"id": entry["id"], "status": "skipped_bounds", "scale": s})
        _restore_erased()
        return
    nw, nh = max(1, int(round(aw * s))), max(1, int(round(ah * s)))
    dx = int(round(px + (ax - px) * s))
    dy = int(round(py + (ay - py) * s))
    cx0, cy0 = max(0, dx), max(0, dy)
    cx1, cy1 = min(W, dx + nw), min(H, dy + nh)
    if cx1 > cx0 and cy1 > cy0:
        cols = cx0 + np.arange(cx1 - cx0, dtype=np.float64) + 0.5
        rows = cy0 + np.arange(cy1 - cy0, dtype=np.float64) + 0.5
        ca, sa = math.cos(math.radians(angle)), math.sin(math.radians(angle))
        u = cols[None, :] * ca + rows[:, None] * sa
        v = -cols[None, :] * sa + rows[:, None] * ca
        footprint = (u >= sgx) & (u < sgx + sgw) & (v >= sgy) & (v < sgy + sgh)
        dest = out[cy0:cy1, cx0:cx1, :3]
        busy = footprint & (_distance(dest, bg) > BG_TOLERANCE)
        if busy.sum() > max(4, 0.005 * footprint.sum()):
            report.append({"id": entry["id"], "status": "skipped_collision", "scale": s})
            _restore_erased()
            return
    if (nw, nh) != (aw, ah):
        layer = np.asarray(Image.fromarray(layer, "RGBA").resize((nw, nh), Image.Resampling.LANCZOS))
    if cx1 > cx0 and cy1 > cy0:
        lsub = layer[cy0 - dy:cy1 - dy, cx0 - dx:cx1 - dx]
        la = lsub[..., 3:4].astype(np.float32) / 255.0
        dest = out[cy0:cy1, cx0:cx1, :3]
        dest[...] = (lsub[..., :3].astype(np.float32) * la
                     + dest.astype(np.float32) * (1 - la)).astype(np.uint8)
    if overlay_masks is not None:
        overlay_masks[entry['id']].update(
            alpha=layer[..., 3].astype(np.float32) / 255.0, origin=(dx, dy))
    report.append({"id": entry["id"], "status": "applied", "scale": s})


def _restore(out, arr, box):
    x, y, w, h = box
    out[y:y + h, x:x + w] = arr[y:y + h, x:x + w]


def load_raster_with_overrides(path: str, spec: Optional[dict]) -> Image.Image:
    """Open *path* and apply *spec* (if any); always returns an RGBA image."""
    with Image.open(path) as im:
        img = im.convert("RGBA")
    if not spec:
        return img
    processed, _report = apply_raster_text_overrides(img, spec)
    return processed
