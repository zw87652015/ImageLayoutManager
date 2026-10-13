"""Geometry for the row/cell '+' buttons around the page layout.

Buttons are sized in screen pixels (THICKNESS_PX / GAP_PX), so the caller
converts them to scene mm at the current zoom. Pure math — no Qt imports.
"""

from dataclasses import dataclass

THICKNESS_PX = 16.0   # short side, logical px on screen
GAP_PX = 6.0          # gap between layout edge and button, logical px


@dataclass(frozen=True)
class AddButtonSpec:
    action: str        # "row_above" | "row_below" | "cell_left" | "cell_right"
    x: float           # mm, scene coords
    y: float
    w: float
    h: float
    row_index: int = -1
    col_index: int = -1


def add_button_specs(row_rects, col_counts, group_label_rects, margin_left,
                     content_width, thickness_mm, gap_mm) -> list:
    """Specs for the add-row/add-cell buttons, in creation order.

    row_rects: row_index -> (x, y, w, h); col_counts: row_index -> column_count
    (1 when missing); group_label_rects: iterable of (x, y, w, h) side bands.
    """
    if not row_rects:
        return []
    T = thickness_mm
    GAP = gap_mm
    sorted_rows = sorted(row_rects.items(), key=lambda kv: kv[0])
    group_label_rects = list(group_label_rects)

    def _side_band_extent(rx, ry, rw, rh):
        left_x, right_x = rx, rx + rw
        for bx, by, bw, bh in group_label_rects:
            if by + bh <= ry or by >= ry + rh:
                continue  # no vertical overlap with this row
            if bx + bw <= rx + 0.01:
                left_x = min(left_x, bx)
            elif bx >= rx + rw - 0.01:
                right_x = max(right_x, bx + bw)
        return left_x, right_x

    specs = []
    first_idx, (_, first_y, _, _) = sorted_rows[0]
    specs.append(AddButtonSpec("row_above", margin_left, first_y - T - GAP,
                               content_width, T, row_index=first_idx))
    last_idx, (_, last_y, _, last_h) = sorted_rows[-1]
    specs.append(AddButtonSpec("row_below", margin_left, last_y + last_h + GAP,
                               content_width, T, row_index=last_idx))

    for row_idx, (rx, ry, rw, rh) in sorted_rows:
        col_count = col_counts.get(row_idx, 1)
        left_x, right_x = _side_band_extent(rx, ry, rw, rh)
        specs.append(AddButtonSpec("cell_left", left_x - T - GAP, ry, T, rh,
                                   row_index=row_idx, col_index=0))
        specs.append(AddButtonSpec("cell_right", right_x + GAP, ry, T, rh,
                                   row_index=row_idx, col_index=col_count))
    return specs
