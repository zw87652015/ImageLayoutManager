"""Label preview for the numbering scheme pickers (Qt-free).

Shows three panels where panel 2 is split into two sub-panels, using the same
rules as the canvas: hierarchical sub labels come from auto_label._compose_sub,
flat numbering (no sub scheme) runs consecutive main-style letters across the
split children.
"""

from types import SimpleNamespace

from src.utils.auto_label import _compose_sub
from src.utils.label_numbering import core_of, format_index


def preview(main_scheme, sub_scheme, prefix_parent, separator):
    """[(label, [sub_labels])] for three panels, the second split into two.

    *label* is the panel's own label (for the split panel, its first sub label
    in flat mode). *sub_labels* is empty for unsplit panels.
    """
    main = main_scheme or "a"
    if not sub_scheme:
        first = format_index(0, main)
        second_subs = [format_index(1, main), format_index(2, main)]
        third = format_index(3, main)
        return [(first, []), (second_subs[0], second_subs), (third, [])]

    project = SimpleNamespace(label_sub_prefix_parent=bool(prefix_parent),
                              label_sub_separator=separator or "")
    parent_label = format_index(1, main)
    parent_core = core_of(parent_label, main)
    subs = [_compose_sub(parent_core, index, sub_scheme, project)[0] for index in range(2)]
    return [
        (format_index(0, main), []),
        (parent_label, subs),
        (format_index(2, main), []),
    ]
