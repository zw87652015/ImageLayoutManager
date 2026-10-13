"""Pure math for revealing a selection in the canvas viewport.

No Qt imports, so it can be unit-tested without a QApplication.
"""


def axis_reveal_delta(t0: float, t1: float, v0: float, v1: float) -> float:
    """Minimal shift of the view along one axis so [t0, t1] is shown inside [v0, v1].

    t is the target interval and v the visible interval (already inset by the margin).
    """
    if t1 - t0 <= v1 - v0:
        if t0 < v0:
            return t0 - v0
        if t1 > v1:
            return t1 - v1
        return 0.0
    if t0 <= v0 and t1 >= v1:
        return 0.0
    if t0 > v0:
        return t0 - v0
    return t1 - v1


def reveal_margin(view_len: float, preferred: float = 24.0) -> float:
    return max(0.0, min(preferred, view_len / 6.0))
