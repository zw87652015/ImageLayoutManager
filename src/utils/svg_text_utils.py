"""Utilities for extracting and overriding font sizes in SVG text elements."""

import io
import math
import xml.etree.ElementTree as ET
import re
from typing import List, Optional


def _collect_text_content(elem) -> str:
    parts = []

    def _walk(e):
        if e.text:
            t = e.text.strip()
            if t:
                parts.append(t)
        for child in e:
            local = child.tag.split('}')[-1] if '}' in child.tag else child.tag
            if local in ('tspan', 'textPath'):
                _walk(child)
            if child.tail:
                t = child.tail.strip()
                if t:
                    parts.append(t)

    _walk(elem)
    return ' '.join(parts)


def _iter_text_elements(root):
    """Yield (elem, key, pos_index) for every <text> element in document order."""
    idx = 0

    def walk(elem):
        nonlocal idx
        local = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
        if local == 'text':
            elem_id = elem.get('id')
            key = elem_id if elem_id else f'_pos_{idx}'
            yield elem, key, idx
            idx += 1
        for child in elem:
            yield from walk(child)

    yield from walk(root)


def get_svg_text_elements(svg_path: str) -> List[dict]:
    """
    Parse an SVG file and return metadata about all <text> elements.

    Each dict has:
        key        — stable identifier: id attr or _pos_{N}
        text       — visible text content
        element_id — id attribute value, or None
        pos_index  — 0-based index among text elements
    """
    try:
        tree = ET.parse(svg_path)
    except Exception:
        return []

    root = tree.getroot()
    result = []
    for elem, key, idx in _iter_text_elements(root):
        content = _collect_text_content(elem) or f'<text {idx}>'
        result.append({
            'key': key,
            'text': content,
            'element_id': elem.get('id'),
            'pos_index': idx,
        })
    return result


def _register_all_namespaces(svg_path: str):
    try:
        for event, data in ET.iterparse(svg_path, events=['start-ns']):
            prefix, uri = data
            try:
                ET.register_namespace(prefix, uri)
            except Exception:
                pass
    except Exception:
        pass
    # Always register the default SVG namespace
    ET.register_namespace('', 'http://www.w3.org/2000/svg')
    ET.register_namespace('xlink', 'http://www.w3.org/1999/xlink')


def _set_font_size(elem, font_size_pt: float):
    """Write font-size into the element's inline style="" attribute.

    Inline style has the highest CSS specificity (beats class selectors and SVG
    presentation attributes), so the change is guaranteed to take effect even
    when the original SVG uses CSS classes to set font sizes.
    """
    new_size = f'{font_size_pt}pt'
    style = elem.get('style', '')
    if style and 'font-size' in style:
        new_style = re.sub(r'font-size\s*:\s*[^;]+', f'font-size:{new_size}', style)
    elif style:
        new_style = f'font-size:{new_size};{style}'
    else:
        new_style = f'font-size:{new_size}'
    elem.set('style', new_style)
    # Remove presentation attribute if present to avoid ambiguity
    elem.attrib.pop('font-size', None)


def apply_svg_font_overrides(svg_path: str, overrides: dict) -> Optional[bytes]:
    """
    Return modified SVG bytes with font-size overrides applied, or None.

    Args:
        svg_path  — path to the original SVG file
        overrides — {element_key: font_size_pt}
    """
    if not overrides:
        return None

    _register_all_namespaces(svg_path)

    try:
        tree = ET.parse(svg_path)
    except Exception:
        return None

    root = tree.getroot()
    modified = False

    for elem, key, _idx in _iter_text_elements(root):
        if key in overrides:
            _set_font_size(elem, overrides[key])
            modified = True

    if not modified:
        return None

    try:
        return ET.tostring(root, encoding='unicode').encode('utf-8')
    except Exception:
        return None


def build_svg_overrides_for_path(project, svg_path: str) -> dict:
    """Return {element_key: font_size_pt} for a given svg_path from project groups."""
    overrides = {}
    for group in getattr(project, 'svg_text_groups', []):
        for member in group.members:
            if member.svg_path == svg_path:
                overrides[member.element_key] = group.font_size_pt
    return overrides


# ──────────────────────────────────────────────────────────────────────────────
# SVG text normalization engine
# ──────────────────────────────────────────────────────────────────────────────

_NUM_RE = re.compile(r'[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?')


def _parse_transform_matrix(transform_str: str) -> list:
    """Parse an SVG transform attribute string into an affine matrix [a,b,c,d,e,f].

    Handles: matrix, translate, scale, rotate, skewX, skewY.
    Multiple transforms are combined left-to-right (SVG spec order).
    """
    result = [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]  # identity
    if not transform_str:
        return result
    for fn_m in re.finditer(r'(\w+)\s*\(([^)]*)\)', transform_str):
        fn = fn_m.group(1).lower()
        args = [float(x) for x in _NUM_RE.findall(fn_m.group(2))]
        if fn == 'matrix' and len(args) >= 6:
            m = list(args[:6])
        elif fn == 'translate':
            tx = args[0] if args else 0.0
            ty = args[1] if len(args) > 1 else 0.0
            m = [1.0, 0.0, 0.0, 1.0, tx, ty]
        elif fn == 'scale':
            sx = args[0] if args else 1.0
            sy = args[1] if len(args) > 1 else sx
            m = [sx, 0.0, 0.0, sy, 0.0, 0.0]
        elif fn == 'rotate':
            ang = math.radians(args[0]) if args else 0.0
            c, s = math.cos(ang), math.sin(ang)
            if len(args) == 3:
                cx, cy = args[1], args[2]
                m = [c, s, -s, c, cx - cx * c + cy * s, cy - cy * c - cx * s]
            else:
                m = [c, s, -s, c, 0.0, 0.0]
        elif fn == 'skewx':
            ang = math.radians(args[0]) if args else 0.0
            m = [1.0, 0.0, math.tan(ang), 1.0, 0.0, 0.0]
        elif fn == 'skewy':
            ang = math.radians(args[0]) if args else 0.0
            m = [1.0, math.tan(ang), 0.0, 1.0, 0.0, 0.0]
        else:
            continue
        # Post-multiply: result = result * m  (left-to-right SVG application)
        a, b, cc, d, e, f = result
        ma, mb, mc, md, me, mf = m
        result = [
            a * ma + cc * mb,
            b * ma + d  * mb,
            a * mc + cc * md,
            b * mc + d  * md,
            a * me + cc * mf + e,
            b * me + d  * mf + f,
        ]
    return result


def _matrix_effective_scale(matrix: list) -> float:
    """Geometric-mean of x- and y-axis scale factors from a 2-D affine matrix."""
    a, b, c, d = matrix[0], matrix[1], matrix[2], matrix[3]
    sx = math.sqrt(a * a + b * b)
    sy = math.sqrt(c * c + d * d)
    s = math.sqrt(sx * sy) if (sx > 0 and sy > 0) else max(sx, sy)
    return max(s, 1e-9)


def _walk_normalize(elem, acc: list, target_pt: float) -> None:
    """Recursively walk *elem*, accumulating the CTM, normalising <text>/<tspan>."""
    local = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag

    # Combine accumulated matrix with this element's own transform
    em = _parse_transform_matrix(elem.get('transform', ''))
    a, b, cc, d, e, f = acc
    ma, mb, mc, md, me, mf = em
    new_acc = [
        a * ma + cc * mb,
        b * ma + d  * mb,
        a * mc + cc * md,
        b * mc + d  * md,
        a * me + cc * mf + e,
        b * me + d  * mf + f,
    ]

    if local == 'text':
        effective_scale = _matrix_effective_scale(new_acc)
        adjusted = round(target_pt / effective_scale, 3)
        _set_font_size(elem, adjusted)
        # Normalise all <tspan> descendants to the same visual size.
        # tspan cannot carry its own transform, so effective_scale is the same.
        for desc in elem.iter():
            desc_local = desc.tag.split('}')[-1] if '}' in desc.tag else desc.tag
            if desc_local == 'tspan' and desc is not elem:
                _set_font_size(desc, adjusted)
        return  # no need to recurse further into text children

    for child in elem:
        _walk_normalize(child, new_acc, target_pt)


def _register_all_namespaces_from_bytes(svg_bytes: bytes) -> None:
    """Register all XML namespaces found in *svg_bytes* so ET round-trips them."""
    try:
        for event, data in ET.iterparse(io.BytesIO(svg_bytes), events=['start-ns']):
            prefix, uri = data
            try:
                ET.register_namespace(prefix, uri)
            except Exception:
                pass
    except Exception:
        pass
    ET.register_namespace('', 'http://www.w3.org/2000/svg')
    ET.register_namespace('xlink', 'http://www.w3.org/1999/xlink')


def normalize_svg_text(svg_bytes: bytes, target_pt: float) -> bytes:
    """Return SVG bytes with every <text>/<tspan> font-size set to *target_pt*.

    Accounts for ancestor transform scaling (scale/matrix/rotate) so the
    *visual* size of text matches *target_pt* regardless of how deeply nested
    the element is inside scaled groups.

    Additionally normalises font-size values inside <style> CSS blocks via
    a best-effort regex pass.

    Text converted to outlines (<path> elements — Illustrator "Create Outlines")
    cannot be resized; the function silently leaves them unchanged.

    Returns the original *svg_bytes* unchanged on any parse error.
    """
    _register_all_namespaces_from_bytes(svg_bytes)
    try:
        root = ET.fromstring(svg_bytes)
    except Exception:
        return svg_bytes

    identity = [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]
    _walk_normalize(root, identity, target_pt)

    # Best-effort: replace font-size in <style> CSS blocks
    for elem in root.iter():
        local = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
        if local == 'style' and elem.text:
            elem.text = re.sub(
                r'font-size\s*:\s*[^;}"]*',
                f'font-size: {target_pt}pt',
                elem.text,
            )

    try:
        return ET.tostring(root, encoding='unicode').encode('utf-8')
    except Exception:
        return svg_bytes


def apply_svg_font_overrides_from_bytes(
    svg_bytes: bytes, overrides: dict
) -> Optional[bytes]:
    """Like ``apply_svg_font_overrides`` but takes already-loaded bytes."""
    if not overrides:
        return None
    _register_all_namespaces_from_bytes(svg_bytes)
    try:
        root = ET.fromstring(svg_bytes)
    except Exception:
        return None
    modified = False
    for elem, key, _idx in _iter_text_elements(root):
        if key in overrides:
            _set_font_size(elem, overrides[key])
            modified = True
    if not modified:
        return None
    try:
        return ET.tostring(root, encoding='unicode').encode('utf-8')
    except Exception:
        return None


def get_svg_override_bytes_for_cell(project, cell) -> Optional[bytes]:
    """Return modified SVG bytes for *cell*, or ``None`` if no changes are needed.

    Pipeline (in order):
    1. If ``cell.svg_normalize_text`` is True: normalize all text to
       ``cell.svg_normalize_text_pt``, accounting for ancestor transforms.
    2. Apply per-element SvgTextGroup overrides on top.

    This is the single entry-point used by both the canvas proxy and the
    raster export pipeline so the two stay in sync.
    """
    path = getattr(cell, 'image_path', None)
    if not path or not path.lower().endswith('.svg'):
        return None

    do_normalize = getattr(cell, 'svg_normalize_text', False)
    overrides = build_svg_overrides_for_path(project, path)

    if not do_normalize and not overrides:
        return None

    try:
        with open(path, 'rb') as fh:
            base_bytes = fh.read()
    except OSError:
        return None

    # Step 1 — normalise
    if do_normalize:
        target_pt = float(getattr(cell, 'svg_normalize_text_pt', 8.0))
        base_bytes = normalize_svg_text(base_bytes, target_pt)

    # Step 2 — per-element group overrides on top of (possibly normalised) bytes
    if overrides:
        result = apply_svg_font_overrides_from_bytes(base_bytes, overrides)
        if result:
            return result

    return base_bytes if do_normalize else None
