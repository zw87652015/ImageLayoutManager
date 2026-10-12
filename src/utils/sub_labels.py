"""Split strip labels: one label strip divided into several sub-labels.

Qt-free. Splits are fractions of the strip's long axis (x for row strips,
y for column strips), relative to the strip itself rather than the image.
"""

import math

MAX_SUB_LABELS = 8
MIN_SEGMENT = 0.02


def even_splits(n: int) -> list:
    return [k / n for k in range(1, n)]


def _valid_splits(splits, count: int) -> bool:
    if not isinstance(splits, list) or len(splits) != count - 1:
        return False
    previous = 0.0
    for value in splits:
        if type(value) not in (int, float) or not math.isfinite(value):
            return False
        if not previous < value < 1.0:
            return False
        previous = value
    return True


def sanitize(texts, splits) -> tuple:
    if not isinstance(texts, list) or len(texts) < 2:
        return [], []
    texts = [t if isinstance(t, str) else str(t) for t in texts]
    if not _valid_splits(splits, len(texts)):
        splits = even_splits(len(texts))
    return texts, [float(v) for v in splits]


def segment_spans(splits) -> list:
    bounds = [0.0] + [float(v) for v in splits] + [1.0]
    return [(bounds[i], bounds[i + 1]) for i in range(len(bounds) - 1)]


def segment_rects(rect, splits, vertical: bool) -> list:
    x, y, w, h = rect
    rects = []
    for start, end in segment_spans(splits):
        if vertical:
            rects.append((x, y + start * h, w, (end - start) * h))
        else:
            rects.append((x + start * w, y, (end - start) * w, h))
    return rects


def set_divider(splits, index: int, value: float, min_gap: float = MIN_SEGMENT) -> list:
    if not 0 <= index < len(splits):
        raise IndexError("divider index out of range")
    lower = (splits[index - 1] if index > 0 else 0.0) + min_gap
    upper = (splits[index + 1] if index + 1 < len(splits) else 1.0) - min_gap
    clamped = min(max(float(value), lower), upper)
    result = list(splits)
    result[index] = clamped
    return result


def is_active(project, text_item) -> bool:
    """True when *text_item* is split and drawn in its own label strip."""
    if len(getattr(text_item, "sub_labels", []) or []) < 2:
        return False
    parent = project.find_cell_by_id(text_item.parent_id) if text_item.parent_id else None
    if parent is None or not parent.is_leaf:
        return False
    from src.model.layout_engine import OUT_OF_CELL_PLACEMENTS
    return project.effective_label_placement(text_item) in OUT_OF_CELL_PLACEMENTS
