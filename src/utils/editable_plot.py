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

from src.plot_editor.document import PlotDocument, has_plot_metadata
from src.plot_editor.render import PlotRender, render_document
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
