from src.model.data_model import Project, TextItem
from src.model.layout_engine import LayoutEngine
from src.utils.label_numbering import core_of, format_index, parse_scheme

_Y_TOL = 0.5  # mm; cells within this vertical gap count as the same row


def _collect_leaves(cell, out):
    if cell.is_leaf:
        out.append(cell)
    else:
        for child in cell.children:
            _collect_leaves(child, out)


def _collect_branches(cell, out):
    if not cell.is_leaf:
        out.append(cell)
        for child in cell.children:
            _collect_branches(child, out)


def _spatial_key(cell, rects):
    rect = rects.get(cell.id)
    if rect is None:
        return (float("inf"), float("inf"))
    x, y, _w, _h = rect
    return (round(y / _Y_TOL), x)


def _make_label(cell, text: str, project: Project, rects: dict):
    if cell.id not in rects:
        return None
    x, y, _w, _h = rects[cell.id]
    offset = 2.0
    style = project.label_style_fields("panel")
    font_size = style["font_size_pt"] if style["font_size_pt"] > 0 else 10.0
    return TextItem(
        text=text,
        font_family=style["font_family"],
        font_size_pt=font_size,
        font_weight=style["font_weight"],
        color=style["color"],
        x=x + offset,
        y=y + offset,
        scope="cell",
        subtype="numbering",
        parent_id=cell.id,
        label_tier="panel",
        anchor="top_left_inside",
        offset_x=offset,
        offset_y=offset,
    )


def _compose_sub(parent_core: str, index: int, sub_scheme: str, project: Project) -> tuple:
    """Build a sub-cell label, returning ``(display_text, core_text)``.

    ``core_text`` is the affix-free form that deeper levels prefix onto, so
    a three-level figure reads A / A-i / A-i-1 rather than A / (i) / (1).
    """
    core = core_of(format_index(index, sub_scheme), sub_scheme)
    if project.label_sub_prefix_parent and parent_core:
        core = f"{parent_core}{project.label_sub_separator}{core}"
    prefix, _style, suffix = parse_scheme(sub_scheme)
    return f"{prefix}{core}{suffix}", core


def _number_branch(parent, parent_core: str, sub_scheme: str,
                   project: Project, texts: dict, key) -> None:
    """Number *parent*'s direct children, restarting the sub sequence."""
    for index, child in enumerate(sorted(parent.children, key=key)):
        text, core = _compose_sub(parent_core, index, sub_scheme, project)
        texts[child.id] = text
        if not child.is_leaf:
            _number_branch(child, core, sub_scheme, project, texts, key)


def compute_label_texts(project: Project, scheme: str = None,
                        sub_scheme: str = None) -> dict:
    """Map every cell id to the label text the current scheme would give it.

    Shared by auto-labelling and by scheme changes so both agree on ordering
    and numbering. Pass *scheme* / *sub_scheme* to preview a different scheme
    without mutating the project.

    Two modes, chosen by the sub-scheme:

    * empty — one continuous sequence. Leaves are numbered first (a, b, c…)
      and branch cells continue it, matching the convention that sub-panels
      are lettered before their composite parent.
    * set — hierarchical. Top-level panels use the main scheme while each
      split panel restarts its children on the sub scheme, giving the
      journal-standard A / i, ii, iii nesting.
    """
    scheme = project.label_scheme if scheme is None else scheme
    if sub_scheme is None:
        sub_scheme = project.label_scheme_sub
    sub_scheme = (sub_scheme or "").strip()

    rects = LayoutEngine.calculate_layout(project).cell_rects
    key = lambda c: _spatial_key(c, rects)  # noqa: E731
    texts: dict = {}

    if sub_scheme:
        for index, cell in enumerate(sorted(project.cells, key=key)):
            text = format_index(index, scheme)
            texts[cell.id] = text
            if not cell.is_leaf:
                _number_branch(cell, core_of(text, scheme), sub_scheme,
                               project, texts, key)
        return texts

    leaves_flat: list = []
    branches_flat: list = []
    for cell in project.cells:
        _collect_leaves(cell, leaves_flat)
        _collect_branches(cell, branches_flat)
    for index, cell in enumerate(sorted(leaves_flat, key=key)
                                 + sorted(branches_flat, key=key)):
        texts[cell.id] = format_index(index, scheme)
    return texts


class AutoLabel:
    @staticmethod
    def generate_labels(project: Project) -> None:
        """Append panel labels to project.text_items (caller clears existing ones)."""
        rects = LayoutEngine.calculate_layout(project).cell_rects
        texts = compute_label_texts(project)

        def walk(cell):
            if cell.id in texts:
                item = _make_label(cell, texts[cell.id], project, rects)
                if item:
                    project.text_items.append(item)
            for child in cell.children:
                walk(child)

        for cell in project.cells:
            walk(cell)
