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


def _set_font_size(elem, font_size: float, unit: str = 'pt',
                   override_last: bool = False):
    """Write font-size into the element's inline style="" attribute.

    Inline style has the highest CSS specificity (beats class selectors and SVG
    presentation attributes), so the change is guaranteed to take effect even
    when the original SVG uses CSS classes to set font sizes.

    ``unit`` is ``'px'`` (SVG user units) for sizes already converted to the
    document's coordinate system, which avoids depending on the renderer's
    pt→px factor. See ``get_svg_override_bytes_for_cell``.
    """
    new_size = f'{font_size}{unit}'
    style = elem.get('style', '')
    if override_last:
        parts = [part for part in style.split(';')
                 if part.strip() and not re.match(r'^\s*font-size\s*:', part, re.I)]
        new_style = ';'.join(parts + [f'font-size:{new_size}'])
    elif style and 'font-size' in style:
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
    if not _apply_group_font_sizes(root, overrides):
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


def _rescale_text_coordinates(elem, scale):
    length = re.compile(r'([-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?)(%|[A-Za-z]+)?')
    def inverse(match):
        unit = match.group(2) or ''
        if unit in ('em', 'ex'):
            return match.group(0)
        return f'{float(match.group(1)) / scale:.12g}{unit}'
    for node in elem.iter():
        if node.tag.rsplit('}', 1)[-1] not in ('text', 'tspan'):
            continue
        for key in ('x', 'y', 'dx', 'dy', 'textLength'):
            if key in node.attrib:
                node.set(key, length.sub(inverse, node.get(key)))
        for key in ('letter-spacing', 'word-spacing', 'stroke-width'):
            if key in node.attrib:
                node.set(key, length.sub(inverse, node.get(key)))
        style = node.get('style')
        if style:
            node.set('style', re.sub(
                r'((?:letter-spacing|word-spacing|stroke-width)\s*:\s*)([^;]+)',
                lambda m: m.group(1) + length.sub(inverse, m.group(2)), style))


def _walk_normalize(elem, acc: list, target_pt: float, unit: str = 'pt',
                    precise: bool = False) -> None:
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
        adjusted = target_pt / effective_scale
        size = adjusted
        if precise and unit == 'px':
            size = 128
            comp = adjusted / size
            if abs(comp - 1.0) > 1e-12:
                _rescale_text_coordinates(elem, comp)
                elem.set('transform', (elem.get('transform', '') + f' scale({comp:.12g})').strip())
        _set_font_size(elem, size, unit, override_last=precise)
        # Normalise all <tspan> descendants to the same visual size.
        # tspan cannot carry its own transform, so effective_scale is the same.
        for desc in elem.iter():
            desc_local = desc.tag.split('}')[-1] if '}' in desc.tag else desc.tag
            if desc_local == 'tspan' and desc is not elem:
                _set_font_size(desc, size, unit, override_last=precise)
        return  # no need to recurse further into text children

    for child in elem:
        _walk_normalize(child, new_acc, target_pt, unit, precise)


def _positioned_text_runs(svg_bytes):
    try:
        root = ET.fromstring(svg_bytes)
    except ET.ParseError:
        return svg_bytes
    changed = False
    for elem in list(root.iter()):
        if elem.tag.rsplit('}', 1)[-1] != 'text' or (elem.text or '').strip():
            continue
        children = list(elem)
        if not children or any(key in elem.attrib for key in ('rotate', 'textLength')):
            continue
        if any(child.tag.rsplit('}', 1)[-1] != 'tspan'
               or 'x' not in child.attrib or 'y' not in child.attrib
               or 'transform' in child.attrib or (child.tail or '').strip()
               or any(node.tag.rsplit('}', 1)[-1] == 'textPath' for node in child.iter())
               for child in children):
            continue
        namespace = elem.tag[:-4]
        elem.tag = namespace + 'g'
        for key in ('x', 'y', 'dx', 'dy'):
            elem.attrib.pop(key, None)
        for child in children:
            child.tag = namespace + 'text'
        changed = True
    return ET.tostring(root, encoding='unicode').encode('utf-8') if changed else svg_bytes


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


def normalize_svg_text(svg_bytes: bytes, target_pt: float, unit: str = 'pt',
                       precise: bool = False) -> bytes:
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
    _walk_normalize(root, identity, target_pt, unit, precise)

    # Best-effort: replace font-size in <style> CSS blocks
    for elem in root.iter():
        local = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
        if local == 'style' and elem.text:
            elem.text = re.sub(
                r'font-size\s*:\s*[^;}"]*',
                f'font-size: {target_pt}{unit}',
                elem.text,
            )

    try:
        return ET.tostring(root, encoding='unicode').encode('utf-8')
    except Exception:
        return svg_bytes


def apply_svg_font_overrides_from_bytes(
    svg_bytes: bytes, overrides: dict, unit: str = 'pt', precise: bool = False
) -> Optional[bytes]:
    """Like ``apply_svg_font_overrides`` but takes already-loaded bytes."""
    if not overrides:
        return None
    _register_all_namespaces_from_bytes(svg_bytes)
    try:
        root = ET.fromstring(svg_bytes)
    except Exception:
        return None
    if not _apply_group_font_sizes(root, overrides, unit, precise):
        return None
    try:
        return ET.tostring(root, encoding='unicode').encode('utf-8')
    except Exception:
        return None


def _apply_group_font_sizes(root, overrides, unit: str = 'pt',
                            precise: bool = False):
    parents = {child: parent for parent in root.iter() for child in parent}
    modified = False
    for elem, key, _idx in _iter_text_elements(root):
        if key not in overrides:
            continue
        transforms = []
        parent = parents.get(elem)
        while parent is not None:
            transforms.append(parent.get('transform', ''))
            parent = parents.get(parent)
        acc = _parse_transform_matrix(' '.join(reversed(transforms)))
        _walk_normalize(elem, acc, overrides[key], unit, precise)
        modified = True
    return modified


def svg_mm_per_unit(project, cell, svg_bytes, layout_result=None, content_size_mm=None):
    """Millimetres on the page covered by one SVG user unit of *cell*.

    ``panel_mm_per_unit`` works in the renderer's default-size pixels, so the
    viewBox-to-default-size scale is folded in here to land on user units —
    the coordinate system font sizes are written in.
    """
    from PyQt6.QtCore import QByteArray
    from PyQt6.QtSvg import QSvgRenderer
    from src.utils.panel_scale import panel_mm_per_unit
    from src.utils.svg_utils import sanitize_svg_bytes

    renderer = QSvgRenderer(QByteArray(sanitize_svg_bytes(svg_bytes)))
    if not renderer.isValid():
        return 1.0
    size = renderer.defaultSize()
    view_box = renderer.viewBoxF()
    if size.isEmpty() or view_box.isEmpty():
        return 1.0
    image_w, image_h = size.width(), size.height()
    ratio = panel_mm_per_unit(project, cell, image_w, image_h, layout_result, content_size_mm)
    view_scale = math.sqrt(image_w / view_box.width() * image_h / view_box.height())
    return max(ratio * view_scale, 1e-9)


def _svg_text_stage(project, cell, layout_result=None, content_size_mm=None,
                    mm_per_unit_fn=None):
    """Shared steps of ``get_svg_override_bytes_for_cell``.

    Returns ``(bytes, positioned)`` — the SVG drawn for *cell* before
    ``_positioned_text_runs`` (which rewrites text structure, so element
    keys must be read here) and whether that pass still applies — or
    ``None`` when the cell needs no change.
    """
    from src.utils.typography_mode import uses_points
    mm_fn = mm_per_unit_fn or svg_mm_per_unit
    path = getattr(cell, 'image_path', None)
    if not path or not path.lower().endswith('.svg'):
        return None

    do_normalize = getattr(cell, 'svg_normalize_text', False)
    overrides = build_svg_overrides_for_path(project, path)

    precise = uses_points(project)

    # Cheap cached metadata probe BEFORE reading the file — ordinary SVGs
    # with no overrides/normalization must not re-read bytes per layout.
    try:
        from ilmplot.document import has_plot_metadata
        native = has_plot_metadata(path)
    except Exception:
        native = False

    if not native and not do_normalize and not overrides:
        return None

    try:
        with open(path, 'rb') as fh:
            base_bytes = fh.read()
    except OSError:
        return None

    # Native editable plot (ilm-plot metadata): re-render the embedded
    # document so fonts/line widths come out at true final-figure points for
    # this cell's placed size. A corrupt/future metadata payload keeps the
    # stored vector snapshot (display only — the editor explains the issue).
    native_doc = None
    if native:
        try:
            from ilmplot.render import load_rendered_document
            native_doc = load_rendered_document(path)
        except Exception:
            native_doc = None

    mm_per_unit = None
    if native_doc is not None:
        reflow = False
        try:
            from src.utils.editable_plot import plot_reflows, reflow_figure_size_mm
            reflow = plot_reflows(project, cell)
        except Exception:
            reflow = False
        handled = False
        if reflow:
            # Re-render at the exact content-area size: the figure fills the
            # cell (any aspect) with true point sizes. mm_per_unit stays
            # None so normalize/group steps recompute it from the new bytes.
            clip_w = clip_h = 0.0
            if content_size_mm is not None:
                clip_w, clip_h = content_size_mm
            else:
                if layout_result is None:
                    from src.model.layout_engine import LayoutEngine
                    layout_result = LayoutEngine.calculate_layout(project)
                rect = layout_result.cell_rects.get(cell.id)
                if rect is not None:
                    clip_w, clip_h = rect[2], rect[3]
                    if project.layout_mode != 'freeform':
                        clip_w -= cell.padding_left + cell.padding_right
                        clip_h -= cell.padding_top + cell.padding_bottom
            if clip_w > 0 and clip_h > 0:
                handled = True
                try:
                    from src.model.layout_engine import LayoutEngine
                    from ilmplot.render import render_document_fitted
                    from src.utils.editable_plot import resolve_plot_row_frames
                    if layout_result is None:
                        layout_result = LayoutEngine.calculate_layout(project)
                    fig_size = reflow_figure_size_mm(cell, clip_w, clip_h)
                    v_span = resolve_plot_row_frames(
                        project, layout_result).get(cell.id)
                    try:
                        base_bytes = render_document_fitted(
                            native_doc, *fig_size, v_span_mm=v_span).svg
                    except Exception:
                        if v_span is None:
                            raise
                        base_bytes = render_document_fitted(
                            native_doc, *fig_size).svg
                except Exception:
                    pass  # fall back to the stored snapshot bytes
        if not handled:
            mm_per_unit = mm_fn(project, cell, base_bytes,
                                layout_result, content_size_mm)
            # plot_reflow off keeps the stored snapshot verbatim — the
            # exact bytes the Plot Editor saved — so no style-scaled
            # re-render either. Placement then scales it like a picture.
            if mm_per_unit > 0 and getattr(cell, 'plot_reflow', False):
                try:
                    from ilmplot.render import render_document
                    base_bytes = render_document(
                        native_doc,
                        style_scale=(25.4 / 72.0) / mm_per_unit).svg
                except Exception:
                    pass  # fall back to the stored snapshot bytes

    if overrides:
        # A group size is points in the final figure, so convert it to the
        # SVG's own user units and write it as "px" (1 px = 1 user unit).
        # Writing "pt" instead would re-enter the renderer's pt→px factor:
        # QtSvg resolves pt at ~1.24 px/pt rather than the 96/72 the page
        # maths assumes, which rendered synced text ~7% too small and left
        # it inconsistent with raster panels in the same group.
        if mm_per_unit is None:
            mm_per_unit = mm_fn(project, cell, base_bytes, layout_result, content_size_mm)
        overrides = {key: (size * 25.4 / 72.0) / mm_per_unit for key, size in overrides.items()}

    # Step 1 — normalise
    if do_normalize:
        target_pt = float(getattr(cell, 'svg_normalize_text_pt', 8.0))
        if precise:
            if mm_per_unit is None:
                mm_per_unit = mm_fn(project, cell, base_bytes, layout_result,
                                    content_size_mm)
            base_bytes = normalize_svg_text(
                base_bytes, (target_pt * 25.4 / 72.0) / mm_per_unit,
                unit='px', precise=True)
        else:
            base_bytes = normalize_svg_text(base_bytes, target_pt)

    # Step 2 — per-element group overrides on top of (possibly normalised) bytes
    if overrides:
        result = apply_svg_font_overrides_from_bytes(
            base_bytes, overrides, unit='px', precise=precise)
        if result:
            return result, precise

    if native_doc is not None or do_normalize:
        return base_bytes, precise
    return None


def get_svg_override_bytes_for_cell(project, cell, layout_result=None,
                                    content_size_mm=None) -> Optional[bytes]:
    """Return modified SVG bytes for *cell*, or ``None`` if no changes are needed.

    Pipeline (in order):
    1. If ``cell.svg_normalize_text`` is True: normalize all text to
       ``cell.svg_normalize_text_pt``, accounting for ancestor transforms.
    2. Apply per-element SvgTextGroup overrides on top.

    This is the single entry-point used by both the canvas proxy and the
    raster export pipeline so the two stay in sync.
    """
    stage = _svg_text_stage(project, cell, layout_result, content_size_mm)
    if stage is None:
        return None
    data, positioned = stage
    return _positioned_text_runs(data) if positioned else data


_FONT_UNIT_PX = {'': 1.0, 'px': 1.0, 'pt': 4.0 / 3.0, 'pc': 16.0,
                 'mm': 96.0 / 25.4, 'cm': 96.0 / 2.54, 'in': 96.0}
_LENGTH_RE = re.compile(
    r'^\s*([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)\s*([a-z%]*)\s*$', re.I)
_FONT_SHORTHAND_RE = re.compile(
    r'(?:^|\s)([-+]?(?:\d+\.?\d*|\.\d+))(px|pt|pc|mm|cm|in|em)(?=[\s/;]|$)',
    re.I)


def _parse_length(text):
    m = _LENGTH_RE.match(text or '')
    if m is None:
        return None
    return float(m.group(1)), m.group(2).lower()


def _declared_font_size(elem):
    """``(value, unit)`` from inline style, then the ``font`` shorthand, then
    the presentation attribute; ``None`` when no numeric size is declared."""
    decl = {}
    for part in (elem.get('style', '') or '').split(';'):
        if ':' in part:
            name, value = part.split(':', 1)
            decl[name.strip().lower()] = value.strip()
    if 'font-size' in decl:
        return _parse_length(decl['font-size'])
    if 'font' in decl:
        m = _FONT_SHORTHAND_RE.search(' ' + decl['font'])
        return (float(m.group(1)), m.group(2).lower()) if m else None
    if elem.get('font-size') is not None:
        return _parse_length(elem.get('font-size'))
    return None


def _font_size_px(elem, parents):
    decl = _declared_font_size(elem)
    if decl is None:
        return None
    value, unit = decl
    if unit in _FONT_UNIT_PX:
        return value * _FONT_UNIT_PX[unit]
    if unit == 'em':
        node = parents.get(elem)
        while node is not None:
            base = _font_size_px(node, parents)
            if base is not None:
                return value * base
            node = parents.get(node)
    return None


def _text_size_pt(elem, parents, mm_per_unit):
    px = _font_size_px(elem, parents)
    if px is None or mm_per_unit <= 0:
        return None
    transforms = []
    node = parents.get(elem)
    while node is not None:
        transforms.append(node.get('transform', ''))
        node = parents.get(node)
    acc = _parse_transform_matrix(' '.join(reversed(transforms)))
    em = _parse_transform_matrix(elem.get('transform', ''))
    a, b, cc, d, e, f = acc
    ma, mb, mc, md, me, mf = em
    ctm = [a * ma + cc * mb, b * ma + d * mb, a * mc + cc * md,
           b * mc + d * md, a * me + cc * mf + e, b * me + d * mf + f]
    return px * _matrix_effective_scale(ctm) * mm_per_unit * 72.0 / 25.4


_TEXT_ROLE_ORDER = ('title', 'axis_label', 'tick', 'legend', 'series_label',
                    'colorbar', 'other')
_TEXT_ROLE_BY_ID = {'ilmplot-title': 'title',
                    'ilmplot-xlabel': 'axis_label',
                    'ilmplot-ylabel': 'axis_label',
                    'ilmplot-heatmap-colorbar': 'colorbar'}


def _text_role_of_id(elem_id) -> Optional[str]:
    if not elem_id:
        return None
    role = _TEXT_ROLE_BY_ID.get(elem_id)
    if role is not None:
        return role
    if elem_id.startswith(('xtick_', 'ytick_')):
        return 'tick'
    if elem_id == 'legend' or elem_id.startswith('legend_'):
        return 'legend'
    if elem_id.startswith('ilmplot-series-label-'):
        return 'series_label'
    return None


def _text_role(elem, parents) -> str:
    """Role of a ``<text>`` from its own id, then its nearest ancestor with a
    role-bearing id (``ilmplot-title``, ``xtick_N``, ``legend_N``, ...)."""
    node = elem
    while node is not None:
        role = _text_role_of_id(node.get('id'))
        if role is not None:
            return role
        node = parents.get(node)
    return 'other'


def svg_text_rows(project, cell, layout_result=None, content_size_mm=None,
                  mm_per_unit_fn=None) -> list:
    """One row per ``<text>`` of the SVG *cell* draws (before positioning).

    Each row: ``key`` (same keys as ``get_svg_text_elements``), ``element_id``,
    ``text``, ``size_pt`` — the effective final-figure point size, or
    ``None`` when the size cannot be determined from the file — and ``role``
    (see ``_text_role``).
    """
    mm_fn = mm_per_unit_fn or svg_mm_per_unit
    stage = _svg_text_stage(project, cell, layout_result, content_size_mm,
                            mm_fn)
    if stage is not None:
        data = stage[0]
    else:
        path = getattr(cell, 'image_path', None)
        if not path or not path.lower().endswith('.svg'):
            return []
        try:
            with open(path, 'rb') as fh:
                data = fh.read()
        except OSError:
            return []
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return []
    mm = mm_fn(project, cell, data, layout_result, content_size_mm)
    parents = {child: parent for parent in root.iter() for child in parent}
    rows = []
    for elem, key, idx in _iter_text_elements(root):
        rows.append({
            'key': key,
            'element_id': elem.get('id'),
            'text': _collect_text_content(elem) or f'<text {idx}>',
            'size_pt': _text_size_pt(elem, parents, mm),
            'role': _text_role(elem, parents),
        })
    return rows


def svg_text_effective_sizes(project, cell, layout_result=None,
                             content_size_mm=None,
                             mm_per_unit_fn=None) -> dict:
    """``{element key: effective final-figure point size}`` for the elements
    whose size can be determined."""
    return {row['key']: row['size_pt'] for row in svg_text_rows(
        project, cell, layout_result, content_size_mm, mm_per_unit_fn)
        if row['size_pt'] is not None}


def describe_text_sizes(rows) -> list:
    """``[(size_pt, count, example_text)]`` sorted by size, sizes rounded to
    0.1 pt, from rows returned by ``svg_text_rows``."""
    groups = {}
    for row in rows:
        size = row.get('size_pt')
        if size is None:
            continue
        key = round(size, 1)
        count, example = groups.get(key, (0, row.get('text', '')))
        groups[key] = (count + 1, example)
    return [(size, count, example)
            for size, (count, example) in sorted(groups.items())]


def describe_text_roles(rows) -> list:
    """``[(role, size_pt, count, example_text, keys)]`` in ``_TEXT_ROLE_ORDER``,
    then by size; sizes rounded to 0.1 pt, rows without a size skipped.
    ``keys`` is the tuple of element keys (``svg_text_rows`` order)."""
    groups = {}
    for row in rows:
        size = row.get('size_pt')
        if size is None:
            continue
        key = (row.get('role') or 'other', round(size, 1))
        entry = groups.setdefault(key, [0, row.get('text', ''), []])
        entry[0] += 1
        entry[2].append(row.get('key'))
    order = {role: i for i, role in enumerate(_TEXT_ROLE_ORDER)}
    return [(role, size, count, example, tuple(keys)) for (role, size), (count, example, keys)
            in sorted(groups.items(),
                      key=lambda item: (order.get(item[0][0], len(order)),
                                        item[0][1]))]


def apply_plot_text_size(project, svg_path, keys, new_pt, make_name) -> str:
    """Set the final-figure size of the SVG text elements *keys* of *svg_path*.

    Reuses the group when it is exactly this element set (and holds no members
    of other files), renaming it only while it still carries the name
    ``make_name`` would have given its old size. Otherwise *keys* are removed
    from every group of *svg_path*, groups emptied by that are dropped, and a
    new group named ``make_name(new_pt)`` is created. Returns the group id.
    Members of other SVG files are never touched.
    """
    from src.model.data_model import SvgTextGroup, SvgTextMember

    keys = list(dict.fromkeys(keys))
    wanted = set(keys)
    groups = project.svg_text_groups
    owners = [g for g in groups if any(m.svg_path == svg_path and m.element_key in wanted
                                       for m in g.members)]
    if len(owners) == 1:
        group = owners[0]
        mine = {m.element_key for m in group.members if m.svg_path == svg_path}
        exclusive = mine == wanted and all(m.svg_path == svg_path for m in group.members)
        if exclusive:
            if group.name == make_name(group.font_size_pt):
                group.name = make_name(new_pt)
            group.font_size_pt = new_pt
            return group.id

    emptied = []
    for group in groups:
        before = len(group.members)
        group.members = [m for m in group.members
                         if not (m.svg_path == svg_path and m.element_key in wanted)]
        if before and not group.members:
            emptied.append(group.id)
    project.svg_text_groups = [g for g in groups if g.id not in emptied]

    group = SvgTextGroup(name=make_name(new_pt), font_size_pt=new_pt,
                         members=[SvgTextMember(svg_path=svg_path, element_key=k)
                                  for k in keys])
    project.svg_text_groups.append(group)
    return group.id


def format_text_size(size_pt) -> str:
    """Display form of a point size: at most two decimals, no trailing zeros."""
    return f'{round(size_pt, 2):g}'


def svg_text_preview_source(project, cell):
    """``(source, positioned, rendered)`` for the SVG a cell's text preview draws.

    ``source`` is the stage output before ``_positioned_text_runs`` — the bytes
    ``svg_text_rows`` takes its keys from — and ``rendered`` is what
    ``get_svg_override_bytes_for_cell`` returns for the same stage. ``None``
    when the cell needs no SVG change (the raw file is drawn instead).
    """
    stage = _svg_text_stage(project, cell)
    if stage is None:
        return None
    source, positioned = stage
    rendered = _positioned_text_runs(source) if positioned else source
    return source, positioned, rendered


def text_preview_rects(svg_bytes, keys, width_px, height_px, positioned=False) -> dict:
    """``{key: QRectF}`` of the ``<text>`` elements *keys* (all when ``None``)
    in pixels of a *width_px* × *height_px* render of *svg_bytes* (viewBox
    stretched over the image, as ``QSvgRenderer.render`` draws it).

    *svg_bytes* must be the pre-positioning source (keys come from it).
    ``positioned`` replays ``_positioned_text_runs`` on the id-tagged copy
    so tspan-based text measures its real extent; ids survive that rewrite.
    ``boundsOnElement`` includes the element's own transform but not its
    ancestors', so the ancestor chain is applied here. Keys that cannot be
    placed are omitted.
    """
    from PyQt6.QtCore import QByteArray, QRectF
    from PyQt6.QtGui import QTransform
    from PyQt6.QtSvg import QSvgRenderer

    try:
        root = ET.fromstring(svg_bytes)
    except ET.ParseError:
        return {}
    wanted = None if keys is None else set(keys)
    taken = {elem.get('id') for elem in root.iter() if elem.get('id')}
    targets = {}
    for elem, key, idx in _iter_text_elements(root):
        if wanted is not None and key not in wanted:
            continue
        if elem.get('id') is None:
            tag_id = f'_ilm_hl_{idx}'
            while tag_id in taken:
                tag_id += '_'
            taken.add(tag_id)
            elem.set('id', tag_id)
        targets[key] = elem.get('id')
    if not targets:
        return {}
    data = ET.tostring(root, encoding='unicode').encode('utf-8')
    if positioned:
        data = _positioned_text_runs(data)
    renderer = QSvgRenderer(QByteArray(data))
    if not renderer.isValid():
        return {}
    view_box = renderer.viewBoxF()
    if view_box.isEmpty():
        view_box = QRectF(0, 0, renderer.defaultSize().width(),
                          renderer.defaultSize().height())
    if view_box.isEmpty():
        return {}
    sx, sy = width_px / view_box.width(), height_px / view_box.height()

    doc = ET.fromstring(data)
    parents = {child: parent for parent in doc.iter() for child in parent}
    by_id = {}
    for elem in doc.iter():
        if elem.get('id') is not None:
            by_id.setdefault(elem.get('id'), elem)

    rects = {}
    for key, elem_id in targets.items():
        elem = by_id.get(elem_id)
        if elem is None or not renderer.elementExists(elem_id):
            continue
        bounds = renderer.boundsOnElement(elem_id)
        if bounds.isEmpty():
            continue
        chain = []
        node = parents.get(elem)
        while node is not None:
            chain.append(node.get('transform', ''))
            node = parents.get(node)
        ctm = QTransform(*_parse_transform_matrix(' '.join(reversed(chain))))
        mapped = ctm.mapRect(bounds)
        rects[key] = QRectF((mapped.left() - view_box.left()) * sx,
                            (mapped.top() - view_box.top()) * sy,
                            mapped.width() * sx, mapped.height() * sy)
    return rects
