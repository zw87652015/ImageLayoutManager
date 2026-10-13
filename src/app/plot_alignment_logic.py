"""Qt-free helpers for the Align Plot Areas dialog.

Pure functions and a small undo history; the dialog wires them to widgets.
"""

import time


def plan_initial_group(selected_ids, groups, eligible):
    """What to show when the dialog opens for *selected_ids*.

    *groups* is ``[(group_id, member_ids), ...]``; *eligible* is the set of
    panel ids that may join a new group.
    """
    owner = {}
    for gid, members in groups:
        for cid in members:
            owner.setdefault(cid, gid)
    for cid in selected_ids:
        if cid in owner:
            unassigned = [c for c in selected_ids if c not in owner]
            return ("open", owner[cid], unassigned)
    eligible_selected = [c for c in selected_ids if c in eligible]
    if len(eligible_selected) >= 2:
        return ("create", eligible_selected)
    if groups:
        return ("open", groups[0][0], [])
    return ("empty",)


def order_rows(all_ids, member_ids):
    """(members in member order, non-members in all_ids order)."""
    known = set(all_ids)
    members = [c for c in member_ids if c in known]
    member_set = set(members)
    others = [c for c in all_ids if c not in member_set]
    return members, others


def next_needed(order, current, needed):
    """The next id after *current* (wrapping) that is in *needed*.

    *current* itself is returned only when it is the sole needed id.
    """
    if not order or not needed:
        return None
    start = order.index(current) if current in order else -1
    count = len(order)
    for step in range(1, count + 1):
        cid = order[(start + step) % count]
        if cid in needed:
            return cid
    return None


_MIN_EDGE = 1e-4


def nudge_box(box, dx, dy, *, resize=False):
    """Move (or resize from the right/bottom edges) a normalized box."""
    left, top, right, bottom = box
    if not resize:
        width, height = right - left, bottom - top
        new_left = min(max(0.0, left + dx), 1.0 - width)
        new_top = min(max(0.0, top + dy), 1.0 - height)
        return (new_left, new_top, new_left + width, new_top + height)
    new_right = min(1.0, max(left + _MIN_EDGE, right + dx))
    new_bottom = min(1.0, max(top + _MIN_EDGE, bottom + dy))
    return (left, top, new_right, new_bottom)


class MarkHistory:
    """Undo/redo of mark changes as ``(cid, old, new)`` entries.

    ``undo()`` returns the entry list (callers restore each ``old``);
    ``redo()`` returns it again (callers apply each ``new``).
    """

    def __init__(self, clock=time.monotonic, window=0.6):
        self._clock = clock
        self._window = window
        self._undo = []
        self._redo = []
        self._last_key = None
        self._last_time = None

    def push(self, entries, coalesce_key=None):
        entries = [tuple(entry) for entry in entries]
        now = self._clock()
        coalesce = (
            coalesce_key is not None
            and self._undo
            and self._last_key == coalesce_key
            and self._last_time is not None
            and now - self._last_time <= self._window
        )
        if coalesce:
            previous = self._undo[-1]
            merged = {}
            for cid, old, new in previous:
                merged[cid] = [old, new]
            for cid, old, new in entries:
                if cid in merged:
                    merged[cid][1] = new
                else:
                    merged[cid] = [old, new]
            self._undo[-1] = [(cid, old, new) for cid, (old, new) in merged.items()]
        else:
            self._undo.append(entries)
        self._redo.clear()
        self._last_key = coalesce_key
        self._last_time = now

    def undo(self):
        if not self._undo:
            return None
        entries = self._undo.pop()
        self._redo.append(entries)
        self._last_key = None
        return entries

    def redo(self):
        if not self._redo:
            return None
        entries = self._redo.pop()
        self._undo.append(entries)
        self._last_key = None
        return entries


GROUP_COLORS = ("#4F5BD5", "#2F8F5B", "#C2410C", "#B4236A", "#0E7C86", "#7C5CC4")


def group_color(index):
    return GROUP_COLORS[index % len(GROUP_COLORS)]


def card_status(is_member, has_area, has_suggestion, has_issue):
    """Status dot for a panel card: "problem", "needs", "ok", or None for non-members."""
    if not is_member:
        return None
    if has_issue:
        return "problem"
    if not has_area or has_suggestion:
        return "needs"
    return "ok"


def cycle_row(value, member_count):
    """Next custom baseline number: 1 -> ... -> member_count -> 1."""
    if member_count < 1 or value < 1 or value >= member_count:
        return 1
    return value + 1


def card_order(all_ids, member_ids):
    """Current-group members first (member order), then the rest in project order."""
    members, others = order_rows(all_ids, member_ids)
    return members + others


def progress(marked, members):
    """(fraction, "m/n") for the footer ring; fraction is 0 when there are no members."""
    if members <= 0:
        return 0.0, "0/0"
    fraction = min(1.0, max(0.0, marked / members))
    return fraction, f"{marked}/{members}"
