from src.model.data_model import Project, TextItem
from src.model.layout_engine import LayoutEngine
from src.utils.label_numbering import core_of, format_index, parse_scheme
from src.utils.sub_labels import is_active

_Y_TOL = 0.5  # mm; cells within this vertical gap count as the same row


def _number_in_reading_order(cells, texts, subs, scheme, key, index, split_counts):
    """Number image panels, finishing a split before the next sibling.

    A column split into two is read top to bottom before the panel to its
    right, so the letters run (a), (b), (c) rather than skipping across. An
    active split strip label takes one letter per segment.
    """
    for cell in sorted(cells, key=key):
        if cell.is_leaf:
            texts[cell.id] = format_index(index, scheme)
            count = split_counts.get(cell.id)
            if count:
                subs[cell.id] = [format_index(index + k, scheme) for k in range(count)]
                index += count
            else:
                index += 1
        else:
            index = _number_in_reading_order(
                cell.children, texts, subs, scheme, key, index, split_counts)
    return index


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
    style = project.label_style_fields("panel")
    font_size = style["font_size_pt"] if style["font_size_pt"] > 0 else 12.0
    return TextItem(
        text=text,
        font_family=style["font_family"],
        font_size_pt=font_size,
        font_weight=style["font_weight"],
        color=style["color"],
        x=x,
        y=y,
        scope="cell",
        subtype="numbering",
        parent_id=cell.id,
        label_tier="panel",
        anchor="top_left_inside",
        offset_x=0.0,
        offset_y=0.0,
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


def _split_texts(full_core: str, count: int, sub_scheme: str, project: Project) -> list:
    """Child labels of a split leaf, always carrying its full ancestry core."""
    prefix, _style, suffix = parse_scheme(sub_scheme)
    return [
        f"{prefix}{full_core}{project.label_sub_separator}"
        f"{core_of(format_index(k, sub_scheme), sub_scheme)}{suffix}"
        for k in range(count)
    ]


def _number_branch(parent, parent_core: str, parent_full: str, sub_scheme: str,
                   project: Project, texts: dict, subs: dict,
                   split_counts: dict, key) -> None:
    """Number *parent*'s direct children, restarting the sub sequence."""
    for index, child in enumerate(sorted(parent.children, key=key)):
        text, core = _compose_sub(parent_core, index, sub_scheme, project)
        texts[child.id] = text
        own = core_of(format_index(index, sub_scheme), sub_scheme)
        full = f"{parent_full}{project.label_sub_separator}{own}"
        if child.is_leaf:
            if child.id in split_counts:
                subs[child.id] = _split_texts(full, split_counts[child.id], sub_scheme, project)
        else:
            _number_branch(child, core, full, sub_scheme, project, texts, subs,
                           split_counts, key)


def _active_split_counts(project: Project) -> dict:
    """Leaf cell id -> segment count, for active panel-tier split labels."""
    counts = {}
    for item in project.text_items:
        if (item.scope == "cell" and item.subtype != "corner"
                and item.label_tier == "panel" and item.parent_id
                and item.parent_id not in counts and is_active(project, item)):
            counts[item.parent_id] = len(item.sub_labels)
    return counts


def _compute(project: Project, scheme: str = None, sub_scheme: str = None) -> tuple:
    """Return ``(main_texts, sub_texts)`` keyed by cell id for one numbering pass."""
    scheme = project.label_scheme if scheme is None else scheme
    if sub_scheme is None:
        sub_scheme = project.label_scheme_sub
    sub_scheme = (sub_scheme or "").strip()

    rects = LayoutEngine.calculate_layout(project).cell_rects
    key = lambda c: _spatial_key(c, rects)  # noqa: E731
    split_counts = _active_split_counts(project)
    texts: dict = {}
    subs: dict = {}

    if sub_scheme:
        for index, cell in enumerate(sorted(project.cells, key=key)):
            text = format_index(index, scheme)
            texts[cell.id] = text
            core = core_of(text, scheme)
            if cell.is_leaf:
                if cell.id in split_counts:
                    subs[cell.id] = _split_texts(core, split_counts[cell.id], sub_scheme, project)
            else:
                _number_branch(cell, core, core, sub_scheme, project, texts, subs,
                               split_counts, key)
        return texts, subs

    _number_in_reading_order(project.cells, texts, subs, scheme, key, 0, split_counts)
    return texts, subs


def compute_label_texts(project: Project, scheme: str = None,
                        sub_scheme: str = None) -> dict:
    """Map each labeled cell id to the text the current scheme would give it.

    Shared by auto-labelling and by scheme changes so both agree on ordering
    and numbering. Pass *scheme* / *sub_scheme* to preview a different scheme
    without mutating the project.

    Two modes, chosen by the sub-scheme:

    * empty — one continuous sequence over image panels only. A split
      container holds no image of its own, so it does not take a letter.
      Its panels are numbered before the next sibling: a column split into
      two is (a) then (b), and the column to its right is (c). An active
      split strip label consumes one letter per segment.
    * set — hierarchical. Top-level panels, including a split container,
      use the main scheme while each split panel restarts its children on
      the sub scheme, giving the journal-standard A / i, ii, iii nesting.
    """
    return _compute(project, scheme, sub_scheme)[0]


def compute_sub_label_texts(project: Project, scheme: str = None,
                            sub_scheme: str = None) -> dict:
    """Map leaf cell id -> segment texts, for active panel-tier split labels."""
    return _compute(project, scheme, sub_scheme)[1]


def apply_numbering_updates(project: Project, scheme: str = None,
                            sub_scheme: str = None, tiers=None) -> dict:
    """Map text-item id -> ``(text, sub_labels_or_None)`` for numbering labels.

    ``None`` for the sub-labels means leave that label's segment texts alone.
    *tiers* limits the labels considered (``None`` = every numbering label).
    """
    texts, subs = _compute(project, scheme, sub_scheme)
    updates = {}
    for item in project.text_items:
        if item.scope != "cell" or item.subtype == "corner":
            continue
        if item.parent_id not in texts:
            continue
        if tiers is not None and item.label_tier not in tiers:
            continue
        sub = None
        if (item.label_tier == "panel" and item.parent_id in subs
                and is_active(project, item)):
            sub = list(subs[item.parent_id])
        updates[item.id] = (texts[item.parent_id], sub)
    return updates


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
