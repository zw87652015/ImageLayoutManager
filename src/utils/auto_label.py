from src.model.data_model import Project, TextItem
from src.model.layout_engine import LayoutEngine

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


def _label_text(index: int, start_char: str, use_parens: bool) -> str:
    text = chr(ord(start_char) + index)
    return f"({text})" if use_parens else text


def _make_label(cell, text: str, project: Project, rects: dict):
    if cell.id not in rects:
        return None
    x, y, _w, _h = rects[cell.id]
    offset = 2.0
    font_size = project.label_font_size if project.label_font_size > 0 else 10.0
    return TextItem(
        text=text,
        font_family=project.label_font_family,
        font_size_pt=font_size,
        font_weight=project.label_font_weight,
        color=project.label_color,
        x=x + offset,
        y=y + offset,
        scope="cell",
        subtype="numbering",
        parent_id=cell.id,
        anchor="top_left_inside",
        offset_x=offset,
        offset_y=offset,
    )


class AutoLabel:
    @staticmethod
    def generate_labels(project: Project) -> None:
        """Append panel labels to project.text_items (caller clears existing ones).

        Leaves are labeled first (a, b, c…), then branch cells continue the
        sequence — matching the convention that sub-panels are lettered before
        their composite parent.
        """
        layout = LayoutEngine.calculate_layout(project)
        rects = layout.cell_rects

        key = lambda c: _spatial_key(c, rects)  # noqa: E731

        leaves_flat: list = []
        branches_flat: list = []
        for cell in project.cells:
            _collect_leaves(cell, leaves_flat)
            _collect_branches(cell, branches_flat)
        leaves = sorted(leaves_flat, key=key)
        branches = sorted(branches_flat, key=key)

        start_char = 'A' if 'A' in project.label_scheme else 'a'
        use_parens = '(' in project.label_scheme

        for i, cell in enumerate(leaves + branches):
            item = _make_label(cell, _label_text(i, start_char, use_parens), project, rects)
            if item:
                project.text_items.append(item)
