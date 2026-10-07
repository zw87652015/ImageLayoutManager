"""Qt/ILM boundary helpers for native editable plot documents.

Native plots (``*.ilmplot.svg`` — a self-contained SVG carrying a versioned
``ilm-plot`` JSON document in its ``<metadata>`` node) are stored as
content-addressed, immutable files under ``plot_documents_root()``. ILM
undo/redo therefore never mutates source bytes: applying an edit produces a
new file and the undo command swaps the path.

The root is a *sibling* of the sweepable figpack cache — these are
persistent user assets, and plain ``.figlayout`` saves relocate them into
``<name>_assets/`` (see :func:`collect_plot_assets` /
``MainWindow._save_project_to_path``).
"""

from __future__ import annotations

import hashlib
import os
from typing import Optional, Tuple

from ilmplot.document import PlotDocument, has_plot_metadata
from ilmplot.render import (
    PlotRender, load_rendered_document, render_document,
)
from src.utils.figpack import cache_manager
from src.utils.figpack.atomic_write import atomic_write_bytes


def plot_documents_root(cache_root: Optional[str] = None) -> str:
    """Persistent store for generated plot documents (never swept)."""
    root = cache_root or cache_manager.default_cache_root()
    path = os.path.join(os.path.dirname(root), 'plot_documents')
    os.makedirs(path, exist_ok=True)
    return path


def is_editable_plot(path: Optional[str]) -> bool:
    """True when *path* is an SVG carrying an ilm-plot metadata node."""
    if not path or not path.lower().endswith('.svg'):
        return False
    return has_plot_metadata(path)


def plot_document_error(path: Optional[str]) -> Optional[str]:
    """The document's load error message, or None when it loads.

    Returns None for files that are not native editable plots.
    """
    if not is_editable_plot(path):
        return None
    try:
        load_rendered_document(path)
    except Exception as e:
        return str(e)
    return None


def plot_is_loadable(path: Optional[str]) -> bool:
    """True when *path* is an editable plot whose document parses."""
    return is_editable_plot(path) and plot_document_error(path) is None


def plot_reflows(project, cell) -> bool:
    """True when *cell* re-renders its native plot to fill the cell.

    Locked-aspect cells and plot-alignment group members keep the fixed
    ``style_scale`` behaviour; everything else gates on the file being a
    loadable ``*.ilmplot.svg``.
    """
    path = getattr(cell, 'image_path', None)
    if not path or getattr(cell, 'is_placeholder', False):
        return False
    if getattr(cell, 'aspect_ratio_locked', False):
        return False
    if getattr(cell, 'plot_reflow', False) is not True:
        return False
    groups = getattr(project, 'plot_alignment_groups', None)
    if isinstance(groups, list):
        cid = getattr(cell, 'id', None)
        for group in groups:
            members = getattr(group, 'cell_ids', None)
            if isinstance(members, list) and cid in members:
                return False
    return plot_is_loadable(path)


def reflow_figure_size_mm(cell, clip_w_mm: float, clip_h_mm: float):
    """Unrotated figure size (mm) whose cropped/rotated view fills the clip."""
    from src.utils.plot_alignment import rotate_box
    rc = rotate_box((cell.crop_left, cell.crop_top,
                     cell.crop_right, cell.crop_bottom), cell.rotation)
    wr = clip_w_mm / (rc[2] - rc[0])
    hr = clip_h_mm / (rc[3] - rc[1])
    return (hr, wr) if cell.rotation % 180 else (wr, hr)


def resolve_plot_row_frames(project, layout_result) -> dict:
    """Shared vertical axes spans for reflowing plots in the same grid row.

    Returns ``{cell_id: (top_mm, bottom_mm)}`` measured from each figure's
    own top edge — feed to ``render_document_fitted`` as ``v_span_mm`` so
    same-row plots share identical axes tops and bottoms in page
    coordinates.  Left/right margins stay per plot.  Cached on
    ``layout_result._plot_row_frames``.
    """
    cached = getattr(layout_result, '_plot_row_frames', None)
    if cached is not None:
        return cached
    frames = {}
    try:
        if getattr(project, 'layout_mode', None) != 'freeform':
            frames = _compute_plot_row_frames(project, layout_result)
    except Exception:
        frames = {}
    try:
        layout_result._plot_row_frames = frames
    except Exception:
        pass
    return frames


def _compute_plot_row_frames(project, layout_result) -> dict:
    from src.model.layout_engine import LayoutEngine
    from ilmplot.render import (
        MIN_AXES_FRACTION, fit_plot_area, load_rendered_document)
    from src.utils.plot_alignment import content_rect
    rows = LayoutEngine._row_by_cell_id(project)
    groups = {}
    for cell in project.get_all_leaf_cells():
        rect = layout_result.cell_rects.get(cell.id)
        if rect is None:
            continue
        try:
            if not plot_reflows(project, cell):
                continue
        except Exception:
            continue
        if cell.rotation % 360 != 0:
            continue
        crop = (cell.crop_left, cell.crop_top,
                cell.crop_right, cell.crop_bottom)
        if crop != (0.0, 0.0, 1.0, 1.0):
            continue
        key = (rows.get(cell.id), round(rect[1], 2),
               round(rect[1] + rect[3], 2))
        groups.setdefault(key, []).append((cell, rect))
    frames = {}
    for members in groups.values():
        if len(members) < 2:
            continue
        try:
            entries = []
            for cell, rect in members:
                cx, cy, cw, ch = content_rect(cell, rect,
                                              project.layout_mode)
                fw, fh = reflow_figure_size_mm(cell, cw, ch)
                if fw <= 0 or fh <= 0:
                    raise ValueError
                pa = fit_plot_area(
                    load_rendered_document(cell.image_path), fw, fh)
                entries.append((cell, cy, fh,
                                cy + pa[1] * fh, cy + pa[3] * fh))
            shared_top = max(e[3] for e in entries)
            shared_bottom = min(e[4] for e in entries)
            if any(shared_bottom - shared_top < MIN_AXES_FRACTION * e[2]
                   for e in entries):
                continue
            for cell, cy, fh, _top, _bottom in entries:
                frames[cell.id] = (shared_top - cy, shared_bottom - cy)
        except Exception:
            continue
    return frames


def store_plot_document(document: PlotDocument,
                        root: Optional[str] = None) -> Tuple[str, PlotRender]:
    """Render *document* and store it as an immutable content-addressed file.

    Returns ``(path, PlotRender)``; an identical document always maps to the
    same path and is never rewritten.
    """
    render = render_document(document)
    digest = hashlib.sha256(render.svg).hexdigest()
    directory = root or plot_documents_root()
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, f'plot-{digest}.ilmplot.svg')
    if not os.path.isfile(path):
        atomic_write_bytes(path, render.svg, preflight=False)
    # Return the canonical path: figpack sticky-keying resolves symlinks /
    # 8.3 aliases, so a non-canonical path would fail the archive lookup.
    return os.path.realpath(path), render


def _inside(path: str, root: str) -> bool:
    try:
        return os.path.commonpath([
            os.path.normcase(os.path.realpath(path)),
            os.path.normcase(os.path.realpath(root)),
        ]) == os.path.normcase(os.path.realpath(root))
    except ValueError:
        return False


def _files_identical(a: str, b: str) -> bool:
    try:
        if os.path.getsize(a) != os.path.getsize(b):
            return False
        with open(a, 'rb') as fa, open(b, 'rb') as fb:
            while True:
                ca, cb = fa.read(1 << 20), fb.read(1 << 20)
                if ca != cb:
                    return False
                if not ca:
                    return True
    except OSError:
        return False


def relocate_plot_documents(project, layout_path: str,
                            plot_root: str) -> list[str]:
    """Copy native plot files living under *plot_root* into the sidecar
    ``<layout basename>_assets/`` next to *layout_path* and rewrite
    ``cell.image_path`` references. Returns the list of copied paths.

    Kept separate from ``relocate_pasted_images`` so native plots never
    trigger the pasted-image save notification. SvgTextGroup members that
    referenced a relocated path gain an entry for the new sidecar path
    (same element keys) so saved projects keep their font groups; the
    original members stay for undo/sharing.
    """
    base = os.path.splitext(os.path.basename(layout_path))[0]
    assets_dir = os.path.join(os.path.dirname(layout_path), f"{base}_assets")
    copied: list[str] = []
    targets = []
    for cell in project.get_all_leaf_cells():
        for obj in (cell, *list(getattr(cell, 'pip_items', []) or [])):
            path = getattr(obj, 'image_path', None)
            if (path and os.path.isfile(path) and _inside(path, plot_root)
                    and is_editable_plot(path)):
                targets.append((obj, path))
    if not targets:
        return copied
    os.makedirs(assets_dir, exist_ok=True)
    moved: list[tuple[str, str]] = []
    for obj, src in targets:
        dst = os.path.realpath(
            os.path.join(assets_dir, os.path.basename(src)))
        if not (os.path.isfile(dst) and _files_identical(src, dst)):
            with open(src, 'rb') as fh:
                atomic_write_bytes(dst, fh.read(), preflight=False)
            copied.append(dst)
        obj.image_path = dst
        moved.append((src, dst))
    if moved:
        from src.model.data_model import SvgTextMember
        for group in getattr(project, 'svg_text_groups', []) or []:
            for old, new in moved:
                for member in [m for m in group.members
                               if m.svg_path == old]:
                    if not any(m.svg_path == new
                               and m.element_key == member.element_key
                               for m in group.members):
                        group.members.append(SvgTextMember(
                            svg_path=new,
                            element_key=member.element_key))
    return copied
