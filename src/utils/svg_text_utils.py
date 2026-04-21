"""Utilities for extracting and overriding font sizes in SVG text elements."""

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
    new_size = f'{font_size_pt}pt'
    style = elem.get('style', '')
    if style and 'font-size' in style:
        new_style = re.sub(r'font-size\s*:\s*[^;]+', f'font-size:{new_size}', style)
        elem.set('style', new_style)
    else:
        # Set or replace the font-size attribute directly
        elem.set('font-size', new_size)


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
