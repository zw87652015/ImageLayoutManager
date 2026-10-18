"""Undo/session bookkeeping for the Match Text Size windows (Qt-free).

Both windows apply edits live.  ``SessionRecorder`` snapshots the shared
text-group state (plus the raster cell's regions when the window has one)
after every user edit and folds the whole session into a single
``TextMatchSessionCommand`` on the project's undo stack — Ctrl+Z in the
main window restores the state the window opened with.
"""

import copy

from src.model.data_model import RasterTextRegion, SvgTextGroup


def capture(project, cell=None) -> dict:
    """Deep, JSON-like snapshot of the state the windows can edit."""
    return {
        "groups": [g.to_dict() for g in project.svg_text_groups],
        "regions": ([r.to_dict() for r in cell.raster_text_regions]
                    if cell is not None else None),
    }


def restore(project, cell_id, state) -> None:
    """Put *project* back to *state* (groups always, regions when the cell
    snapshot exists and the cell is still in the project)."""
    project.svg_text_groups = [SvgTextGroup.from_dict(g) for g in state["groups"]]
    if state["regions"] is not None and cell_id is not None:
        cell = project.find_cell_by_id(cell_id)
        if cell is not None:
            cell.raster_text_regions = [RasterTextRegion.from_dict(r)
                                        for r in state["regions"]]


def scoped_revert(current, baseline, image, other_refs) -> tuple[dict, list]:
    """Per-image Revert state: *baseline* scoped to *image* only.

    ``image``: ``{"kind": "raster", "cell_id": str}`` or
    ``{"kind": "svg", "svg_path": str}``.  ``other_refs``: group ids used by
    other images' raster regions.  Returns ``(new_state, kept_names)`` —
    never mutates the inputs.

    Rules: start from the current groups; put this image's memberships /
    regions back to baseline (recreating a deleted baseline group that the
    restored content references); drop groups created since baseline when
    nothing uses them; restore a surviving group's name/size to baseline
    unless other images share it (then keep it and report its name).
    """
    current = copy.deepcopy(current)
    baseline = copy.deepcopy(baseline)
    other_refs = set(other_refs or ())
    groups = [g for g in current["groups"]]
    baseline_groups = {g["id"]: g for g in baseline["groups"]}
    kept_names = []
    svg = image["kind"] == "svg"

    if svg:
        svg_path = image["svg_path"]
        for g in groups:
            g["members"] = [m for m in g["members"]
                            if m["svg_path"] != svg_path]
        for bg in baseline["groups"]:
            mine = [m for m in bg["members"] if m["svg_path"] == svg_path]
            if not mine:
                continue
            g = next((g for g in groups if g["id"] == bg["id"]), None)
            if g is None:
                groups.append({**bg, "members": mine})
            else:
                have = {m["element_key"] for m in g["members"]}
                g["members"] += [m for m in mine
                                 if m["element_key"] not in have]
        new_regions = current["regions"]
    else:
        new_regions = baseline["regions"]
        have_ids = {g["id"] for g in groups}
        for gid in {r.get("group_id") for r in (new_regions or [])} - {None}:
            if gid not in have_ids and gid in baseline_groups:
                bg = copy.deepcopy(baseline_groups[gid])
                bg["members"] = []
                groups.append(bg)
                have_ids.add(gid)

    if svg:
        svg_path = image["svg_path"]

        def used_by_me(g):
            return any(m["svg_path"] == svg_path for m in g["members"])

        def used_by_others(g):
            return (any(m["svg_path"] != svg_path for m in g["members"])
                    or g["id"] in other_refs)
    else:
        region_gids = {r.get("group_id") for r in (new_regions or [])}

        def used_by_me(g):
            return g["id"] in region_gids

        def used_by_others(g):
            return bool(g["members"]) or g["id"] in other_refs

    out = []
    for g in groups:
        gid = g["id"]
        if gid not in baseline_groups:
            if used_by_me(g) or used_by_others(g):
                out.append(g)
            continue
        bg = baseline_groups[gid]
        if (g.get("font_size_pt") != bg.get("font_size_pt")
                or g.get("name") != bg.get("name")):
            if used_by_others(g):
                kept_names.append(g["name"])
            else:
                g["font_size_pt"] = bg["font_size_pt"]
                g["name"] = bg["name"]
        out.append(g)
    return {"groups": out, "regions": new_regions}, kept_names


class SessionRecorder:
    """Turns the live edits of one Match Text Size window into undo steps.

    ``stack`` may be None (tests): ``record`` then only tracks ``_last``.
    ``make_command(before=…, after=…)`` builds the QUndoCommand to push.
    Consecutive edits merge into the same command while it is still the
    top of the stack; a foreign command on top starts a new one.
    """

    def __init__(self, project, cell_id, stack, make_command, open_state=None):
        self._project = project
        self._cell_id = cell_id
        self._stack = stack
        self._make_command = make_command
        self.open_state = copy.deepcopy(open_state) if open_state is not None else self._capture()
        self._last = self.open_state
        self._cmd = None

    def _capture(self):
        cell = (self._project.find_cell_by_id(self._cell_id)
                if self._cell_id is not None else None)
        return capture(self._project, cell)

    def record(self) -> None:
        """Call after every user edit."""
        state = self._capture()
        if state == self._last:
            return
        if self._stack is not None:
            top = (self._stack.command(self._stack.index() - 1)
                   if self._stack.index() > 0 else None)
            if self._cmd is None or top is not self._cmd:
                self._cmd = self._make_command(before=self._last, after=state)
                self._stack.push(self._cmd)
            else:
                self._cmd.after = state
        self._last = state

    def rebase(self) -> None:
        """Sync ``_last`` after an external refresh / undo-redo. Never pushes."""
        self._last = self._capture()

    def changed(self) -> bool:
        return self._capture() != self.open_state
