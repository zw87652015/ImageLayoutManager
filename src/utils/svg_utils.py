"""SVG sanitization utilities for ImageLayoutManager.

Qt's QSvgRenderer implements SVG Tiny 1.2, which forbids nested <svg>
elements.  Software such as OriginLab exports SVGs with an outer <svg>
that declares the physical size and a nested <svg> that holds all drawing
content.  When Qt encounters the nested element it logs:

    qt.svg: Skipping a nested svg element, because SVG Document must not
            contain nested svg elements in Svg Tiny 1.2

…and renders nothing, producing a blank (white) cell.

sanitize_svg_bytes() detects this pattern and rewrites the file in-memory
by replacing every nested <svg …> tag with a <g transform="..."> tag that
applies the viewport/viewBox transform the nested <svg> would have produced,
and the corresponding </svg> with </g>.  The outer <svg> is left untouched.

Additional normalisation:
  - viewBox values that use commas as separators (e.g. "0,0 100,200")
    are rewritten to use spaces ("0 0 100 200") because Qt's SVG Tiny
    parser only accepts the space-separated form.
"""
from __future__ import annotations

import re
from typing import Optional


_RE_VIEWBOX = re.compile(
    r'(viewBox\s*=\s*["\'])([^"\']+)(["\'])',
    re.IGNORECASE,
)


def _fix_viewbox(m: re.Match) -> str:
    """Replace commas inside a viewBox value with spaces."""
    quote_open = m.group(1)
    value = m.group(2).replace(",", " ")
    value = re.sub(r"\s+", " ", value).strip()
    quote_close = m.group(3)
    return f"{quote_open}{value}{quote_close}"


def sanitize_svg_bytes(data: bytes) -> bytes:
    """Return sanitised SVG bytes suitable for QSvgRenderer.

    Transformations applied (only when needed — no copy if nothing changes):
    - viewBox comma separators → spaces  (Qt only accepts space-separated)
    - Nested <svg> elements → <g transform="...">  (SVG Tiny 1.2 disallows nesting)
    - White-fill <mask> → <clipPath>  (Qt SVG Tiny ignores <mask>; <clipPath> is supported)
    """
    try:
        text = data.decode("utf-8", errors="replace")
    except Exception:
        return data

    modified = False

    # ── Fix viewBox comma-separated values ───────────────────────────────
    new_text, n_viewbox = _RE_VIEWBOX.subn(_fix_viewbox, text)
    if n_viewbox:
        text = new_text
        modified = True

    # ── Flatten nested <svg> elements ────────────────────────────────────
    svg_open_count = len(re.findall(r"<svg[\s>]", text, re.IGNORECASE))
    if svg_open_count > 1:
        text = _flatten_nested_svgs(text)
        modified = True

    # ── Convert white-fill masks to clipPaths ─────────────────────────────
    # Qt SVG Tiny does not support <mask> and silently skips masked groups,
    # making clipped content invisible.  A mask whose only child is a solid
    # white shape is semantically identical to a <clipPath> with that shape,
    # so we rewrite it.  This covers the common OriginLab/Inkscape pattern
    # of using a white rectangle mask to clip plot content to the axis area.
    new_text, n_mask = _convert_white_masks_to_clippath(text)
    if n_mask:
        text = new_text
        modified = True

    if modified:
        return text.encode("utf-8")
    return data


# ── Attribute parsing helpers ─────────────────────────────────────────────────

_RE_ATTR = re.compile(r'(\w[\w-]*)\s*=\s*(?:"([^"]*)"|\' ([^\']*)\'|(\S+))', re.IGNORECASE)


def _parse_attrs(tag_text: str) -> dict[str, str]:
    """Extract attribute name→value pairs from an SVG opening tag string."""
    result: dict[str, str] = {}
    for m in re.finditer(r'([\w:.-]+)\s*=\s*(?:"([^"]*)"' + r"|'([^']*)')", tag_text):
        name = m.group(1).lower()
        value = m.group(2) if m.group(2) is not None else m.group(3)
        result[name] = value
    return result


def _parse_number(s: str, default: float = 0.0) -> float:
    """Parse a CSS/SVG length, stripping units. Returns default on failure."""
    if not s:
        return default
    s = s.strip()
    # Strip common units
    for unit in ("px", "pt", "mm", "cm", "in", "em", "ex", "%"):
        if s.endswith(unit):
            s = s[: -len(unit)].strip()
            break
    try:
        return float(s)
    except ValueError:
        return default


def _parse_viewbox(s: str) -> Optional[tuple[float, float, float, float]]:
    """Parse a viewBox attribute string into (min_x, min_y, width, height)."""
    s = s.replace(",", " ")
    parts = s.split()
    if len(parts) != 4:
        return None
    try:
        return tuple(float(p) for p in parts)  # type: ignore[return-value]
    except ValueError:
        return None


def _viewbox_transforms(w: float, h: float, vx: float, vy: float, vw: float, vh: float, par: str) -> list[str]:
    """Return transform fragments for mapping a viewBox onto a viewport."""
    transforms: list[str] = []
    par_lower = par.lower()
    none_mode = "none" in par_lower

    sx = w / vw
    sy = h / vh
    if not none_mode:
        scale = max(sx, sy) if "slice" in par_lower else min(sx, sy)
        sx = sy = scale

    parts = par.split()
    align = parts[0].lower() if parts else "xmidymid"

    if "xmin" in align:
        tx = 0.0
    elif "xmax" in align:
        tx = w - vw * sx
    else:
        tx = (w - vw * sx) / 2.0

    if "ymin" in align:
        ty = 0.0
    elif "ymax" in align:
        ty = h - vh * sy
    else:
        ty = (h - vh * sy) / 2.0

    if tx != 0 or ty != 0:
        transforms.append(f"translate({tx:g} {ty:g})")
    scale_str = f"scale({sx:g} {sy:g})" if none_mode else f"scale({sx:g})"
    transforms.append(scale_str)
    if vx != 0 or vy != 0:
        transforms.append(f"translate({-vx:g} {-vy:g})")
    return transforms


def _nested_svg_transform(attrs: dict[str, str]) -> str:
    """Compute the transform string that replicates a nested <svg> viewport.

    A nested <svg x="X" y="Y" width="W" height="H" viewBox="vx vy vw vh"
    preserveAspectRatio="..."> is equivalent to:
        translate(X, Y) + viewBox scale/align + translate(-vx, -vy)
    """
    x = _parse_number(attrs.get("x", "0"))
    y = _parse_number(attrs.get("y", "0"))
    w = _parse_number(attrs.get("width", "0"))
    h = _parse_number(attrs.get("height", "0"))
    vb_str = attrs.get("viewbox", "")
    par = attrs.get("preserveaspectratio", "xMidYMid meet").strip()

    transforms: list[str] = []
    if x != 0 or y != 0:
        transforms.append(f"translate({x:g} {y:g})")

    if vb_str and w > 0 and h > 0:
        vb = _parse_viewbox(vb_str)
        if vb is not None:
            vx, vy, vw, vh = vb
            if vw > 0 and vh > 0:
                transforms.extend(_viewbox_transforms(w, h, vx, vy, vw, vh, par))

    return " ".join(transforms)


# ── Mask → clipPath conversion ───────────────────────────────────────────────

# A <mask> whose sole content is one or more shapes filled with white (or no
# fill that resolves to white) acts purely as a clip region.  Qt SVG Tiny
# ignores <mask> entirely, so the masked group vanishes.  We detect this
# pattern and rewrite:
#   <mask id="X"> <shape fill="white" .../> </mask>
#   → <clipPath id="X"> <shape .../> </clipPath>
# and leave <g mask="url(#X)"> → <g clip-path="url(#X)">.

_RE_MASK_BLOCK = re.compile(
    r'<mask(\s[^>]*)?>.*?</mask\s*>',
    re.IGNORECASE | re.DOTALL,
)
_RE_MASK_REF = re.compile(
    r'\bmask\s*=\s*(["\'])url\(#([^)]+)\)\1',
    re.IGNORECASE,
)


def _is_white_fill_mask(mask_inner: str) -> bool:
    """Return True if every child element in *mask_inner* has a white fill
    (or is a shape that resolves to white — the only colour that passes
    through as fully opaque in SVG masking)."""
    # Strip whitespace-only text nodes
    stripped = mask_inner.strip()
    if not stripped:
        return False
    # Find all child elements
    child_tags = re.findall(r'<[^/!?][^>]*>', stripped, re.IGNORECASE)
    if not child_tags:
        return False
    for tag in child_tags:
        tag_lower = tag.lower()
        # Accept fill="white" or fill="#ffffff" / fill="#fff"
        fill_m = re.search(r'\bfill\s*=\s*["\']([^"\']*)["\']', tag_lower)
        if fill_m:
            fill_val = fill_m.group(1).strip()
            if fill_val in ("white", "#ffffff", "#fff", "rgb(255,255,255)", "rgb(255, 255, 255)"):
                continue
        # Accept no fill attribute (SVG default fill is black, not white — reject)
        return False
    return True


def _convert_white_masks_to_clippath(text: str) -> tuple[str, int]:
    """Replace white-fill <mask> elements with <clipPath> and update references.

    Returns (new_text, number_of_conversions).
    """
    converted_ids: set[str] = set()
    result = text

    def _replace_mask(m: re.Match) -> str:
        attrs_text = m.group(1) or ""
        id_m = re.search(r'\bid\s*=\s*["\']([^"\']+)["\']', attrs_text, re.IGNORECASE)
        if not id_m:
            return m.group(0)
        mask_id = id_m.group(1)

        full = m.group(0)
        # Extract inner content (between <mask...> and </mask>)
        inner_start = full.index(">") + 1
        inner_end = full.rindex("<")
        inner = full[inner_start:inner_end]

        if not _is_white_fill_mask(inner):
            return m.group(0)

        # Remove fill="white" from child shapes — clipPath shapes ignore fill
        inner_clean = re.sub(
            r'\s*fill\s*=\s*["\'][^"\']*["\']', "", inner, flags=re.IGNORECASE
        )
        converted_ids.add(mask_id)
        return f"<clipPath{attrs_text}>{inner_clean}</clipPath>"

    new_text = _RE_MASK_BLOCK.sub(_replace_mask, result)
    if not converted_ids:
        return text, 0

    # Update all mask="url(#id)" references for converted masks
    def _replace_ref(m: re.Match) -> str:
        mask_id = m.group(2)
        if mask_id in converted_ids:
            quote = m.group(1)
            return f'clip-path={quote}url(#{mask_id}){quote}'
        return m.group(0)

    new_text = _RE_MASK_REF.sub(_replace_ref, new_text)
    return new_text, len(converted_ids)


# ── Internal flattening implementation ───────────────────────────────────────

# Matches an opening <svg ...> tag up to its closing >.
_RE_SVG_OPEN_FULL = re.compile(r"<svg(\s[^>]*)?>", re.IGNORECASE | re.DOTALL)
_RE_SVG_CLOSE = re.compile(r"</svg\s*>", re.IGNORECASE)


def _svg_open_to_g(m: re.Match) -> tuple[int, int, str]:
    """Convert a nested <svg...> match into a (start, end, replacement) tuple."""
    attrs_text = m.group(1) or ""
    attrs = _parse_attrs(attrs_text)
    transform = _nested_svg_transform(attrs)
    replacement = f'<g transform="{transform}">' if transform else "<g>"
    return (m.start(), m.end(), replacement)


def _collect_replacements(events: list) -> list[tuple[int, int, str]]:
    """Walk open/close events and return replacement spans for nested svg tags."""
    replacements: list[tuple[int, int, str]] = []
    depth = 0
    for _pos, kind, payload in events:
        if kind == "open":
            depth += 1
            if depth > 1:
                replacements.append(_svg_open_to_g(payload))
        else:
            if depth > 1:
                replacements.append((payload[0], payload[1], "</g>"))
            depth -= 1
    return replacements


def _flatten_nested_svgs(text: str) -> str:
    """Replace all nested <svg> / </svg> pairs with <g transform="..."> / </g>.

    The outermost <svg> and its corresponding </svg> are left intact.
    For each nested <svg>, the viewport/viewBox attributes are converted into
    an equivalent transform= so that content positions are preserved.
    """
    open_matches: list[re.Match] = list(_RE_SVG_OPEN_FULL.finditer(text))
    if not open_matches:
        return text

    close_spans = [(m.start(), m.end()) for m in _RE_SVG_CLOSE.finditer(text)]

    events: list = [(m.start(), "open", m) for m in open_matches]
    events += [(s, "close", (s, e)) for s, e in close_spans]
    events.sort(key=lambda x: x[0])

    replacements = _collect_replacements(events)

    if not replacements:
        return text

    # Apply replacements from right to left to preserve indices
    replacements.sort(key=lambda x: x[0], reverse=True)
    result = list(text)
    for start, end, sub in replacements:
        result[start:end] = list(sub)

    return "".join(result)
