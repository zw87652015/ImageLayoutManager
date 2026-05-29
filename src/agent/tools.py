"""Agent tool registry — v0.1.

Every tool takes a :class:`ToolContext` plus keyword params and returns the
standard response envelope::

    { "ok": True,  "result": {...} }
    { "ok": False, "error": "<code>", "detail": "...", "hint": "..." }

Tools have no Qt-widget dependencies and never touch the canvas directly:
they mutate ``ctx.project`` (optionally via a QUndoCommand pushed onto
``ctx.undo_stack``) and then fire ``ctx.on_changed`` so the GUI transport
can refresh.

To add a new tool: write a function ``def my_tool(ctx, ...)`` returning the
envelope dict, then register it in ``_REGISTRY`` at the bottom.
"""
from __future__ import annotations

import base64
import os
import tempfile
import traceback
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from src.model.data_model import Cell, ExportRegion, Project, RowTemplate


# ── context ─────────────────────────────────────────────────────────────


@dataclass
class ToolContext:
    """Bundles everything a tool needs to read or mutate.

    GUI transport populates every field; CLI transport leaves ``undo_stack``
    and ``main_window`` as ``None`` (commands are run directly without
    pushing onto a stack).
    """

    project: Project
    undo_stack: Any = None              # QUndoStack or None
    main_window: Any = None             # MainWindow or None (tab-creating tools only)
    project_path: Optional[str] = None  # last-known on-disk path
    on_changed: Optional[Callable[[], None]] = None


# ── errors ──────────────────────────────────────────────────────────────


class ToolError(Exception):
    """Raised inside a tool to produce a structured ``{ok: false}`` response."""

    def __init__(self, code: str, detail: str,
                 hint: Optional[str] = None, **extra: Any) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.hint = hint
        self.extra = extra

    def to_response(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"ok": False, "error": self.code, "detail": self.detail}
        if self.hint:
            out["hint"] = self.hint
        out.update(self.extra)
        return out


def _ok(result: Any) -> Dict[str, Any]:
    return {"ok": True, "result": result}


def _apply(ctx: ToolContext, cmd: Any) -> None:
    """Push a QUndoCommand onto the stack, or run it directly when absent."""
    if ctx.undo_stack is not None:
        try:
            cmd.setText(f"Agent: {cmd.text()}")
        except Exception:
            pass
        ctx.undo_stack.push(cmd)
        # Prevent this command from merging with anything that follows it.
        # Qt calls mergeWith on the stack-top when the *next* command arrives;
        # by setting timestamp to -inf the MERGE_TIMEOUT check always fails,
        # so agent steps are never silently collapsed into one undo entry.
        try:
            cmd.timestamp = float("-inf")
        except Exception:
            pass
    else:
        cmd.redo()
    if ctx.on_changed is not None:
        ctx.on_changed()


def _find_cell(ctx: ToolContext, cell_id: str) -> Cell:
    cell = ctx.project.find_cell_by_id(cell_id)
    if cell is None:
        raise ToolError(
            "cell_not_found",
            f"no cell with id={cell_id}",
            hint="call project_describe to list valid cell_ids",
        )
    return cell


# ── tools ───────────────────────────────────────────────────────────────


def _cell_summary(cell: Cell,
                  parent_id: Optional[str] = None) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "id": cell.id,
        "parent_id": parent_id,
        "row": cell.row_index,
        "col": cell.col_index,
        "split_direction": cell.split_direction,
        "image_path": cell.image_path,
        "has_image": bool(cell.image_path) and not cell.is_placeholder,
        "is_placeholder": cell.is_placeholder,
        "fit_mode": cell.fit_mode,
        "rotation": cell.rotation,
        "align_h": cell.align_h,
        "align_v": cell.align_v,
        "padding_mm": {
            "top": cell.padding_top, "right": cell.padding_right,
            "bottom": cell.padding_bottom, "left": cell.padding_left,
        },
        "crop": {
            "left": cell.crop_left, "top": cell.crop_top,
            "right": cell.crop_right, "bottom": cell.crop_bottom,
        },
        "size_group_id": cell.size_group_id,
        "override_mm": {"w": cell.override_width_mm,
                        "h": cell.override_height_mm,
                        "aspect_ratio_locked": cell.aspect_ratio_locked},
        "freeform": {
            "x_mm": cell.freeform_x_mm,
            "y_mm": cell.freeform_y_mm,
            "w_mm": cell.freeform_w_mm,
            "h_mm": cell.freeform_h_mm,
            "z": cell.z_index,
        },
        "scale_bar_enabled": cell.scale_bar_enabled,
    }
    if cell.scale_bar_enabled:
        out["scale_bar"] = {
            "mode": cell.scale_bar_mode,
            "um_per_px": cell.scale_bar_um_per_px,
            "length_um": cell.scale_bar_length_um,
            "unit": cell.scale_bar_unit,
            "color": cell.scale_bar_color,
            "position": cell.scale_bar_position,
            "thickness_mm": cell.scale_bar_thickness_mm,
            "show_text": cell.scale_bar_show_text,
            "offset_x": cell.scale_bar_offset_x,
            "offset_y": cell.scale_bar_offset_y,
            "custom_text": cell.scale_bar_custom_text,
            "text_size_mm": cell.scale_bar_text_size_mm,
        }
    if cell.pip_items:
        out["pip_items"] = [
            {"id": p.id, "type": p.pip_type,
             "image_path": p.image_path,
             "x": p.x, "y": p.y, "w": p.w, "h": p.h,
             "border_enabled": p.border_enabled,
             "scale_bar_enabled": p.scale_bar_enabled}
            for p in cell.pip_items
        ]
    return out


def _walk_cells(cell: Cell,
                parent_id: Optional[str],
                out: list) -> None:
    """Recursively collect all leaf cells, tagging each with its parent's id."""
    if cell.is_leaf:
        out.append(_cell_summary(cell, parent_id))
    else:
        for child in cell.children:
            _walk_cells(child, cell.id, out)


def project_describe(ctx: ToolContext) -> Dict[str, Any]:
    """Snapshot of the active project's structure and content."""
    p = ctx.project
    cells: list = []
    for top_cell in p.cells:
        _walk_cells(top_cell, None, cells)
    rows = [
        {"index": r.index, "column_count": r.column_count,
         "height_ratio": r.height_ratio,
         "column_ratios": list(r.column_ratios)}
        for r in p.rows
    ]
    return _ok({
        "name": p.name,
        "page_mm": {"w": p.page_width_mm, "h": p.page_height_mm},
        "dpi": p.dpi,
        "layout_mode": p.layout_mode,
        "margins_mm": {
            "top": p.margin_top_mm, "right": p.margin_right_mm,
            "bottom": p.margin_bottom_mm, "left": p.margin_left_mm,
        },
        "gap_mm": p.gap_mm,
        "rows": rows,
        "cells": cells,
        "text_items": [
            {
                "id": t.id, "text": t.text,
                "x": t.x, "y": t.y, "rotation": t.rotation,
                "scope": t.scope, "subtype": t.subtype,
                "parent_id": t.parent_id, "anchor": t.anchor,
                "offset_x": t.offset_x, "offset_y": t.offset_y,
                "font_family": t.font_family,
                "font_size_pt": t.font_size_pt,
                "font_weight": t.font_weight,
                "color": t.color,
                "bg_enabled": t.bg_enabled,
                "bg_color": t.bg_color,
                "bg_padding_mm": t.bg_padding_mm,
            }
            for t in p.text_items
        ],
        "size_groups": [
            {"id": g.id, "name": g.name,
             "pinned_width_mm": g.pinned_width_mm,
             "pinned_height_mm": g.pinned_height_mm,
             "members": [c.id for c in p.get_all_leaf_cells()
                         if c.size_group_id == g.id]}
            for g in p.size_groups
        ],
        "export_region": (p.export_region.to_dict()
                          if p.export_region else None),
        "label_settings": {
            "scheme": p.label_scheme,
            "placement": p.label_placement,
            "font_family": p.label_font_family,
            "font_size_pt": p.label_font_size,
            "font_weight": p.label_font_weight,
            "color": p.label_color,
            "anchor": p.label_anchor,
            "align": p.label_align,
            "offset_x": p.label_offset_x,
            "offset_y": p.label_offset_y,
        },
        "path": ctx.project_path,
    })


def project_new(ctx: ToolContext,
                page_size: Optional[Dict[str, float]] = None,
                dpi: Optional[int] = None,
                margins: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
    """Create a fresh project. GUI transport opens it in a new tab."""
    if ctx.main_window is None:
        raise ToolError(
            "not_supported_in_cli",
            "project_new requires the GUI transport in v0.1",
        )
    project = Project()
    if page_size:
        project.page_width_mm = float(page_size.get("w", project.page_width_mm))
        project.page_height_mm = float(page_size.get("h", project.page_height_mm))
    if dpi is not None:
        project.dpi = int(dpi)
    if margins:
        for side in ("top", "right", "bottom", "left"):
            if side in margins:
                setattr(project, f"margin_{side}_mm", float(margins[side]))
    project.rows = [
        RowTemplate(index=0, column_count=2, height_ratio=1.0),
        RowTemplate(index=1, column_count=2, height_ratio=1.0),
    ]
    project.cells = [
        Cell(row_index=r, col_index=c, is_placeholder=True)
        for r in range(2) for c in range(2)
    ]
    ctx.main_window._create_tab(project, path=None)
    return _ok({"name": project.name})


def project_open(ctx: ToolContext, path: str) -> Dict[str, Any]:
    """Open an existing .figlayout / .figpack / .json file."""
    if not os.path.isfile(path):
        raise ToolError("file_not_found", f"no file at {path}")

    if ctx.main_window is not None:
        ctx.main_window._open_path_dispatch(path)
        new_project = ctx.main_window.project
        return _ok({"path": path, "name": new_project.name})

    # CLI: mutate the context's project in place.
    ctx.project = Project.load_from_file(path)
    ctx.project_path = path
    return _ok({"path": path, "name": ctx.project.name})


def project_save(ctx: ToolContext,
                 path: Optional[str] = None) -> Dict[str, Any]:
    """Persist the project as .figlayout / .figpack / .json (extension picks format).

    Omit ``path`` to save in place (like Ctrl+S). With ``path``, behaves like
    Save As — the extension chooses the on-disk format.
    """
    target = path or ctx.project_path
    if not target:
        raise ToolError(
            "no_save_path",
            "project has never been saved; pass an explicit `path`",
            hint="use a .figlayout, .figpack, or .json extension",
        )

    ext = os.path.splitext(target)[1].lower()
    if ext not in (".figlayout", ".figpack", ".json"):
        raise ToolError(
            "invalid_value",
            f"unsupported extension '{ext}'",
            hint="use one of: .figlayout, .figpack, .json",
            field="path",
        )

    abs_target = os.path.abspath(target)
    parent = os.path.dirname(abs_target) or "."
    if not os.path.isdir(parent):
        raise ToolError(
            "file_not_found",
            f"parent directory does not exist: {parent}",
            hint="create the directory first or choose another path",
            field="path",
        )

    if ctx.main_window is not None:
        ok = ctx.main_window._save_project_to_path(abs_target)
        if not ok:
            raise ToolError(
                "save_failed",
                f"main window save returned False for {abs_target}",
            )
        # _save_project_to_path updates _current_project_path on success.
        ctx.project_path = abs_target
        bytes_written = os.path.getsize(abs_target) if os.path.isfile(abs_target) else 0
        return _ok({"path": abs_target, "bytes_written": bytes_written})

    # CLI fallback — Project.save_to_file handles .figlayout and .json only.
    if ext == ".figpack":
        raise ToolError(
            "not_supported_in_cli",
            ".figpack writing requires the GUI transport "
            "(bundle/cache machinery lives in MainWindow)",
            hint="use .figlayout or .json from CLI, or run with --agent-server",
            field="path",
        )
    ctx.project.name = os.path.splitext(os.path.basename(abs_target))[0]
    ctx.project.save_to_file(abs_target)
    ctx.project_path = abs_target
    bytes_written = os.path.getsize(abs_target) if os.path.isfile(abs_target) else 0
    return _ok({"path": abs_target, "bytes_written": bytes_written})


def project_export(ctx: ToolContext, path: str,
                   format: str = "PNG",
                   region: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
    """Render the active project to PNG / JPG / TIFF on disk."""
    fmt = format.upper()
    if fmt in ("TIF", "TIFF"):
        fmt_kw = "TIFF"
    elif fmt in ("JPG", "JPEG"):
        fmt_kw = "JPG"
    elif fmt == "PNG":
        fmt_kw = "PNG"
    else:
        raise ToolError(
            "invalid_value",
            f"unknown format '{format}'",
            hint="use one of: PNG, JPG, TIFF",
            field="format",
        )

    p = ctx.project
    saved_region = p.export_region
    if region is not None:
        p.export_region = ExportRegion(
            x_mm=float(region.get("x_mm", 0.0)),
            y_mm=float(region.get("y_mm", 0.0)),
            w_mm=float(region.get("w_mm", p.page_width_mm)),
            h_mm=float(region.get("h_mm", p.page_height_mm)),
        )
    try:
        from src.export.image_exporter import ImageExporter
        os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
        ImageExporter.export(p, path, fmt_kw)
    finally:
        if region is not None:
            p.export_region = saved_region

    size = os.path.getsize(path) if os.path.isfile(path) else 0
    return _ok({"path": path, "bytes_written": size})


def image_import(ctx: ToolContext, cell_id: str, path: str,
                 fit_mode: Optional[str] = None) -> Dict[str, Any]:
    """Drop an image into the cell. Optionally override its fit mode."""
    cell = _find_cell(ctx, cell_id)
    if not os.path.isfile(path):
        raise ToolError("file_not_found", f"no image at {path}")

    from src.app.commands import DropImageCommand
    cb = (lambda: ctx.on_changed()) if ctx.on_changed else None
    _apply(ctx, DropImageCommand(cell, path, update_callback=cb))

    if fit_mode is not None:
        cell.fit_mode = str(fit_mode)
        if ctx.on_changed is not None:
            ctx.on_changed()

    return _ok({"cell_id": cell.id, "image_path": cell.image_path})


def cell_set_geometry(ctx: ToolContext, cell_id: str,
                      x_mm: float, y_mm: float,
                      w_mm: float, h_mm: float,
                      z: Optional[int] = None) -> Dict[str, Any]:
    """Move/resize a cell. Project must be in 'freeform' layout mode."""
    cell = _find_cell(ctx, cell_id)
    if ctx.project.layout_mode != "freeform":
        raise ToolError(
            "wrong_layout_mode",
            "cell_set_geometry requires freeform layout",
            hint="switch the project to freeform via the Layout menu "
                 "(layout_set_mode tool arrives in v0.2)",
        )

    from src.app.commands import FreeformGeometryCommand
    cb = (lambda: ctx.on_changed()) if ctx.on_changed else None
    _apply(ctx, FreeformGeometryCommand(
        cell, float(x_mm), float(y_mm), float(w_mm), float(h_mm),
        update_callback=cb,
    ))
    if z is not None:
        cell.z_index = int(z)
        if ctx.on_changed is not None:
            ctx.on_changed()
    return _ok({
        "cell_id": cell.id,
        "x_mm": cell.freeform_x_mm,
        "y_mm": cell.freeform_y_mm,
        "w_mm": cell.freeform_w_mm,
        "h_mm": cell.freeform_h_mm,
        "z": cell.z_index,
    })


def row_add(ctx: ToolContext, position: Optional[int] = None,
            column_count: int = 2,
            height_ratio: Optional[float] = None) -> Dict[str, Any]:
    """Insert a new row at *position* (default: append at the end).

    The new row starts with *column_count* placeholder cells; tweak via
    :func:`row_set` afterwards.
    """
    p = ctx.project
    if position is None:
        position = len(p.rows)
    if position < 0 or position > len(p.rows):
        raise ToolError(
            "invalid_value",
            f"position {position} out of range [0, {len(p.rows)}]",
            field="position",
        )
    column_count = max(1, int(column_count))

    from src.app.commands import InsertRowCommand, PropertyChangeCommand
    cb = (lambda: ctx.on_changed()) if ctx.on_changed else None
    _apply(ctx, InsertRowCommand(p, position, column_count=column_count,
                                 update_callback=cb))
    new_row = next((r for r in p.rows if r.index == position), None)
    if new_row is None:
        # Shouldn't happen, but guard against weird states.
        raise ToolError("internal_error", "row insertion did not produce a row")

    if height_ratio is not None:
        _apply(ctx, PropertyChangeCommand(
            new_row, {"height_ratio": float(height_ratio)},
            update_callback=cb, description="Set Row Height Ratio",
        ))
    return _ok({
        "index": new_row.index,
        "column_count": new_row.column_count,
        "height_ratio": new_row.height_ratio,
        "cell_ids": [c.id for c in p.cells if c.row_index == new_row.index],
    })


def row_remove(ctx: ToolContext, index: int) -> Dict[str, Any]:
    """Delete the row at *index* and everything it contains."""
    p = ctx.project
    if not any(r.index == index for r in p.rows):
        raise ToolError(
            "row_not_found",
            f"no row with index={index}",
            hint=f"valid indices: {[r.index for r in p.rows]}",
        )
    from src.app.commands import DeleteRowCommand
    cb = (lambda: ctx.on_changed()) if ctx.on_changed else None
    _apply(ctx, DeleteRowCommand(p, index, update_callback=cb))
    return _ok({"removed_index": index, "rows_remaining": len(p.rows)})


def row_set(ctx: ToolContext, index: int,
            height_ratio: Optional[float] = None,
            column_ratios: Optional[List[float]] = None) -> Dict[str, Any]:
    """Tune a row's height ratio and/or per-column width ratios.

    *column_ratios* must have one entry per column in the row. Any value
    must be > 0.
    """
    row = next((r for r in ctx.project.rows if r.index == index), None)
    if row is None:
        raise ToolError(
            "row_not_found", f"no row with index={index}",
            hint=f"valid indices: {[r.index for r in ctx.project.rows]}",
        )
    changes: Dict[str, Any] = {}
    if height_ratio is not None:
        if float(height_ratio) <= 0:
            raise ToolError("invalid_value", "height_ratio must be > 0",
                            field="height_ratio")
        changes["height_ratio"] = float(height_ratio)
    if column_ratios is not None:
        if len(column_ratios) != row.column_count:
            raise ToolError(
                "invalid_value",
                f"column_ratios length {len(column_ratios)} "
                f"!= row.column_count {row.column_count}",
                field="column_ratios",
            )
        if any(float(r) <= 0 for r in column_ratios):
            raise ToolError("invalid_value", "column_ratios entries must be > 0",
                            field="column_ratios")
        changes["column_ratios"] = [float(r) for r in column_ratios]
    if not changes:
        return _ok({"index": index, "no_change": True})

    from src.app.commands import PropertyChangeCommand
    cb = (lambda: ctx.on_changed()) if ctx.on_changed else None
    _apply(ctx, PropertyChangeCommand(row, changes, update_callback=cb,
                                      description="Set Row Properties"))
    return _ok({
        "index": index,
        "height_ratio": row.height_ratio,
        "column_ratios": list(row.column_ratios),
    })


def cell_add(ctx: ToolContext, row_index: int,
             position: Optional[int] = None) -> Dict[str, Any]:
    """Insert a new placeholder cell into a row (default: append at the end)."""
    p = ctx.project
    row = next((r for r in p.rows if r.index == row_index), None)
    if row is None:
        raise ToolError("row_not_found", f"no row with index={row_index}")
    if position is None:
        position = row.column_count
    if position < 0 or position > row.column_count:
        raise ToolError(
            "invalid_value",
            f"position {position} out of range [0, {row.column_count}]",
            field="position",
        )
    from src.app.commands import InsertCellCommand
    cb = (lambda: ctx.on_changed()) if ctx.on_changed else None
    _apply(ctx, InsertCellCommand(p, row_index, position, update_callback=cb))
    new_cell = next(
        (c for c in p.cells
         if c.row_index == row_index and c.col_index == position),
        None,
    )
    return _ok({"cell_id": new_cell.id if new_cell else None,
                "row": row_index, "col": position})


def cell_remove(ctx: ToolContext, cell_id: str) -> Dict[str, Any]:
    """Remove a top-level cell. Sub-cells are not supported in v0.2 —
    use ``cell_unsplit`` (coming in v0.3) to collapse a split parent."""
    p = ctx.project
    cell = _find_cell(ctx, cell_id)
    # Confirm it's a top-level cell (DeleteCellCommand operates on row/col).
    if cell not in p.cells:
        raise ToolError(
            "not_supported",
            "cell_remove only works on top-level cells in v0.2",
            hint="for split sub-cells, use cell_unsplit on the parent (v0.3)",
        )
    from src.app.commands import DeleteCellCommand
    cb = (lambda: ctx.on_changed()) if ctx.on_changed else None
    _apply(ctx, DeleteCellCommand(p, cell.row_index, cell.col_index,
                                  update_callback=cb))
    return _ok({"removed_cell_id": cell_id})


def cell_swap(ctx: ToolContext, cell_id_a: str, cell_id_b: str) -> Dict[str, Any]:
    """Swap the *content* (image, scale bar, etc.) of two cells in place."""
    a = _find_cell(ctx, cell_id_a)
    b = _find_cell(ctx, cell_id_b)
    if a is b:
        return _ok({"no_change": True})
    from src.app.commands import SwapCellsCommand
    cb = (lambda: ctx.on_changed()) if ctx.on_changed else None
    _apply(ctx, SwapCellsCommand(a, b, project=ctx.project, update_callback=cb))
    return _ok({"a": cell_id_a, "b": cell_id_b})


def cell_split(ctx: ToolContext, cell_id: str,
               direction: str, count: int = 2) -> Dict[str, Any]:
    """Split a leaf cell into *count* sub-cells.

    *direction* is ``'h'`` / ``'horizontal'`` for a horizontal split (side
    by side), or ``'v'`` / ``'vertical'`` for vertical (stacked).
    """
    d = direction.lower()
    if d in ("h", "horizontal"):
        dir_full = "horizontal"
    elif d in ("v", "vertical"):
        dir_full = "vertical"
    else:
        raise ToolError(
            "invalid_value",
            f"direction must be 'h' or 'v', got {direction!r}",
            field="direction",
        )
    count = int(count)
    if count < 2:
        raise ToolError("invalid_value", "count must be >= 2", field="count")

    cell = _find_cell(ctx, cell_id)
    if not cell.is_leaf:
        raise ToolError(
            "cell_already_split",
            f"cell {cell_id} is already split into {len(cell.children)} sub-cells",
            hint="call cell_unsplit first (v0.3) or split one of the children",
        )

    from src.app.commands import SplitCellCommand
    cb = (lambda: ctx.on_changed()) if ctx.on_changed else None
    _apply(ctx, SplitCellCommand(ctx.project, cell_id, dir_full, count,
                                 update_callback=cb))
    parent = ctx.project.find_cell_by_id(cell_id)
    return _ok({
        "cell_id": cell_id,
        "direction": dir_full,
        "child_ids": [c.id for c in parent.children] if parent else [],
    })


def cell_set_split_ratios(ctx: ToolContext, cell_id: str,
                          ratios: List[float]) -> Dict[str, Any]:
    """Resize the children of a split (container) cell.

    *cell_id* is the **parent** — the container that was split, not one
    of its children. *ratios* must have exactly one entry per child,
    matching the order returned by ``project_describe``. All ratios > 0;
    they are relative within the split (``[1, 2, 1]`` ⇒ 25% / 50% / 25%).

    Prefer this over switching to freeform mode when you just want to
    rebalance sub-cells inside an existing split.
    """
    parent = _find_cell(ctx, cell_id)
    if parent.is_leaf:
        raise ToolError(
            "not_a_split_parent",
            f"cell {cell_id} is a leaf, not a split container",
            hint="call cell_split first, or pass the parent's cell_id "
                 "(see parent_id in project_describe)",
        )
    if len(ratios) != len(parent.children):
        raise ToolError(
            "invalid_value",
            f"ratios length {len(ratios)} != {len(parent.children)} children",
            hint=f"this cell has {len(parent.children)} children; "
                 f"pass exactly that many ratios",
            field="ratios",
        )
    if any(float(r) <= 0 for r in ratios):
        raise ToolError("invalid_value",
                        "ratios entries must be > 0", field="ratios")

    from src.app.commands import PropertyChangeCommand
    cb = (lambda: ctx.on_changed()) if ctx.on_changed else None
    _apply(ctx, PropertyChangeCommand(
        parent, {"split_ratios": [float(r) for r in ratios]},
        update_callback=cb, description="Set Split Ratios",
    ))
    return _ok({
        "cell_id": parent.id,
        "split_direction": parent.split_direction,
        "split_ratios": list(parent.split_ratios),
        "child_ids": [c.id for c in parent.children],
    })


def layout_set_mode(ctx: ToolContext, mode: str) -> Dict[str, Any]:
    """Switch the project between ``'grid'`` and ``'freeform'``.

    Grid → freeform bakes the current grid layout into per-cell coordinates
    so the visual result is preserved. Freeform → grid just flips the mode
    (existing freeform coordinates are kept on each cell for re-baking).
    """
    if mode not in ("grid", "freeform"):
        raise ToolError(
            "invalid_value",
            f"mode must be 'grid' or 'freeform', got {mode!r}",
            field="mode",
        )
    p = ctx.project
    if p.layout_mode == mode:
        return _ok({"mode": mode, "no_change": True})

    from src.app.commands import FreeformLayoutModeCommand
    cb = (lambda: ctx.on_changed()) if ctx.on_changed else None
    baked = None
    if mode == "freeform":
        # Bake current grid rects so the LLM gets a usable freeform starting state.
        from src.model.layout_engine import LayoutEngine
        layout = LayoutEngine.calculate_layout(p)
        baked = dict(layout.cell_rects)
    _apply(ctx, FreeformLayoutModeCommand(p, mode, baked, update_callback=cb))
    return _ok({"mode": mode, "baked_cells": len(baked) if baked else 0})


def auto_label_cells(ctx: ToolContext, scheme: Optional[str] = None,
                     placement: str = "in_cell") -> Dict[str, Any]:
    """Generate sequential labels (a, b, c…) for every leaf cell.

    *scheme* is one of ``'a'``, ``'A'``, ``'(a)'``, ``'(A)'``. Omit to keep
    the project's current scheme. *placement* is ``'in_cell'`` (overlaid on
    each image) or ``'row_above'`` (dedicated label row above each picture
    row).
    """
    p = ctx.project
    from src.app.commands import (
        AutoLabelCommand, AutoLabelOutCellCommand, ChangeLabelSchemeCommand,
    )
    cb = (lambda: ctx.on_changed()) if ctx.on_changed else None

    if scheme is not None:
        if scheme not in ("a", "A", "(a)", "(A)"):
            raise ToolError(
                "invalid_value",
                f"scheme must be one of 'a'/'A'/'(a)'/'(A)', got {scheme!r}",
                field="scheme",
            )
        if scheme != p.label_scheme:
            _apply(ctx, ChangeLabelSchemeCommand(p, scheme, update_callback=cb))

    if placement == "in_cell":
        _apply(ctx, AutoLabelCommand(p, update_callback=cb))
    elif placement in ("row_above", "label_row_above"):
        _apply(ctx, AutoLabelOutCellCommand(p, update_callback=cb))
    else:
        raise ToolError(
            "invalid_value",
            f"placement must be 'in_cell' or 'row_above', got {placement!r}",
            field="placement",
        )

    labels = [
        {"id": t.id, "text": t.text, "parent_id": t.parent_id}
        for t in p.text_items
        if t.scope == "cell" and getattr(t, "subtype", None) != "corner"
    ]
    return _ok({"scheme": p.label_scheme, "placement": p.label_placement,
                "label_count": len(labels), "labels": labels})


def auto_layout(ctx: ToolContext) -> Dict[str, Any]:
    """Run ILM's deterministic algorithmic layout pass.

    Sizes rows/columns to balance aspect ratios from the images already
    imported. Useful as a starting point the LLM can then refine.
    """
    if ctx.project.layout_mode != "grid":
        raise ToolError(
            "wrong_layout_mode",
            "auto_layout requires grid layout mode",
            hint="call layout_set_mode('grid') first",
        )
    from src.app.commands import AutoLayoutCommand
    cb = (lambda: ctx.on_changed()) if ctx.on_changed else None
    _apply(ctx, AutoLayoutCommand(ctx.project, update_callback=cb))
    return _ok({"applied": True})


_PREVIEW_DPI_DEFAULT = 150  # ~3k image tokens for an A4 page; cheap to ship


def view_screenshot(ctx: ToolContext, region: Any = "canvas",
                    dpi: Optional[int] = None) -> Dict[str, Any]:
    """Render the project to PNG bytes (base64) for vision-capable agents.

    Renders at a **preview-quality 150 DPI by default**, not the project's
    export DPI — a 600 DPI A4 screenshot is ~35 megapixels and burns
    ~46k image tokens per call. 150 DPI is enough to verify layout,
    spot overlaps, and check fit modes. Pass an explicit ``dpi`` to
    override (e.g. ``dpi=300`` if you need to read small text).
    """
    p = ctx.project
    saved_dpi = p.dpi
    # When the caller omits dpi, *cap* — don't inherit project.dpi (which
    # is typically 600 for publication output and far too expensive for
    # a verification screenshot).
    p.dpi = int(dpi) if dpi is not None else _PREVIEW_DPI_DEFAULT

    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    tmp.close()
    try:
        from src.export.image_exporter import ImageExporter
        ImageExporter.export(p, tmp.name, "PNG")
        with open(tmp.name, "rb") as f:
            data = f.read()
        return _ok({
            "format": "png",
            "encoding": "base64",
            "data": base64.b64encode(data).decode("ascii"),
            "bytes": len(data),
            "dpi": p.dpi,
        })
    finally:
        p.dpi = saved_dpi
        try:
            os.remove(tmp.name)
        except OSError:
            pass


# ── lookup helpers (text / pip / size group) ────────────────────────────


def _find_text_item(ctx: ToolContext, text_id: str):
    for t in ctx.project.text_items:
        if t.id == text_id:
            return t
    raise ToolError(
        "text_not_found",
        f"no text item with id={text_id}",
        hint="call project_describe to list text_item ids",
    )


def _find_pip_item(ctx: ToolContext, pip_id: str):
    """Return ``(pip_item, host_cell)`` for the given PiP id."""
    for cell in ctx.project.get_all_leaf_cells():
        for pip in cell.pip_items:
            if pip.id == pip_id:
                return pip, cell
    raise ToolError(
        "pip_not_found",
        f"no PiP item with id={pip_id}",
        hint="call project_describe to list pip_item ids",
    )


# ── text items: per-item style + free-text creation ─────────────────────

_TEXT_STYLE_FIELDS = {
    "text", "font_family", "font_size_pt", "font_weight", "color",
    "x", "y", "rotation", "anchor", "offset_x", "offset_y",
    "bg_enabled", "bg_color", "bg_padding_mm",
}


def text_set_style(ctx: ToolContext, text_id: str,
                   **changes: Any) -> Dict[str, Any]:
    """Update properties of a single TextItem (label or free text).

    Allowed keys: text, font_family, font_size_pt, font_weight
    ('normal'/'bold'), color (#RRGGBB), x/y (mm), rotation (deg),
    anchor, offset_x/y (mm), bg_enabled, bg_color, bg_padding_mm.
    """
    item = _find_text_item(ctx, text_id)
    bad = set(changes) - _TEXT_STYLE_FIELDS
    if bad:
        raise ToolError(
            "invalid_params",
            f"unknown fields: {sorted(bad)}",
            hint=f"allowed: {sorted(_TEXT_STYLE_FIELDS)}",
        )
    if "font_weight" in changes and changes["font_weight"] not in ("normal", "bold"):
        raise ToolError("invalid_value",
                        "font_weight must be 'normal' or 'bold'",
                        field="font_weight")
    if "font_size_pt" in changes:
        changes["font_size_pt"] = int(changes["font_size_pt"])

    from src.app.commands import PropertyChangeCommand
    cb = (lambda: ctx.on_changed()) if ctx.on_changed else None
    _apply(ctx, PropertyChangeCommand(
        item, dict(changes), update_callback=cb,
        description="Set Text Style",
    ))
    return _ok({"text_id": item.id, "applied": dict(changes)})


def text_add(ctx: ToolContext, text: str,
             x: float = 10.0, y: float = 10.0,
             parent_cell_id: Optional[str] = None,
             font_family: Optional[str] = None,
             font_size_pt: Optional[int] = None,
             font_weight: Optional[str] = None,
             color: Optional[str] = None,
             rotation: Optional[float] = None) -> Dict[str, Any]:
    """Create a new TextItem on the canvas.

    With *parent_cell_id*, the text is anchored to that cell (scope='cell');
    otherwise it floats globally on the page. ``x``/``y`` are in mm.
    """
    from src.model.data_model import TextItem
    from src.app.commands import AddTextCommand

    item = TextItem(text=str(text), x=float(x), y=float(y))
    if parent_cell_id:
        cell = _find_cell(ctx, parent_cell_id)
        item.scope = "cell"
        item.parent_id = cell.id
    if font_family is not None:
        item.font_family = str(font_family)
    if font_size_pt is not None:
        item.font_size_pt = int(font_size_pt)
    if font_weight is not None:
        if font_weight not in ("normal", "bold"):
            raise ToolError("invalid_value",
                            "font_weight must be 'normal' or 'bold'",
                            field="font_weight")
        item.font_weight = str(font_weight)
    if color is not None:
        item.color = str(color)
    if rotation is not None:
        item.rotation = float(rotation)

    cb = (lambda: ctx.on_changed()) if ctx.on_changed else None
    _apply(ctx, AddTextCommand(ctx.project, item, update_callback=cb))
    return _ok({
        "text_id": item.id,
        "scope": item.scope,
        "parent_id": item.parent_id,
    })


def text_remove(ctx: ToolContext, text_id: str) -> Dict[str, Any]:
    """Delete a TextItem (label or free text)."""
    item = _find_text_item(ctx, text_id)
    from src.app.commands import DeleteTextCommand
    cb = (lambda: ctx.on_changed()) if ctx.on_changed else None
    _apply(ctx, DeleteTextCommand(ctx.project, item, update_callback=cb))
    return _ok({"text_id": text_id})


def labels_set_style(ctx: ToolContext, **changes: Any) -> Dict[str, Any]:
    """Restyle every existing cell label in one shot, and update project
    defaults so future auto-labels inherit the same look.

    Allowed keys: font_family, font_size_pt, font_weight, color, anchor,
    offset_x, offset_y. Existing free-text items (non-labels) are not
    touched.
    """
    allowed = {"font_family", "font_size_pt", "font_weight",
               "color", "anchor", "offset_x", "offset_y"}
    bad = set(changes) - allowed
    if bad:
        raise ToolError(
            "invalid_params",
            f"unknown fields: {sorted(bad)}",
            hint=f"allowed: {sorted(allowed)}",
        )
    if "font_size_pt" in changes:
        changes["font_size_pt"] = int(changes["font_size_pt"])
    if "font_weight" in changes and changes["font_weight"] not in ("normal", "bold"):
        raise ToolError("invalid_value",
                        "font_weight must be 'normal' or 'bold'",
                        field="font_weight")

    p = ctx.project
    proj_field_map = {
        "font_family": "label_font_family",
        "font_size_pt": "label_font_size",
        "font_weight": "label_font_weight",
        "color": "label_color",
        "anchor": "label_anchor",
        "offset_x": "label_offset_x",
        "offset_y": "label_offset_y",
    }
    proj_changes = {proj_field_map[k]: v for k, v in changes.items()}

    from src.app.commands import (
        PropertyChangeCommand, MultiPropertyChangeCommand,
    )
    cb = (lambda: ctx.on_changed()) if ctx.on_changed else None

    if proj_changes:
        _apply(ctx, PropertyChangeCommand(
            p, proj_changes, update_callback=cb,
            description="Set Label Defaults",
        ))

    label_items = [
        t for t in p.text_items
        if t.scope == "cell" and getattr(t, "subtype", None) != "corner"
    ]
    if label_items and changes:
        _apply(ctx, MultiPropertyChangeCommand(
            label_items, dict(changes), update_callback=cb,
            description="Style Labels",
        ))
    return _ok({"updated_labels": len(label_items),
                "applied": dict(changes)})


# ── cell properties (image-side: rotate / crop / pad / align) ───────────

_CELL_PROP_FIELDS = {
    "fit_mode", "rotation", "align_h", "align_v",
    "padding_top", "padding_bottom", "padding_left", "padding_right",
    "crop_left", "crop_top", "crop_right", "crop_bottom",
    "z_index", "override_width_mm", "override_height_mm",
    "aspect_ratio_locked",
    "svg_normalize_text", "svg_normalize_text_pt",
}


def cell_set_properties(ctx: ToolContext, cell_id: str,
                        **changes: Any) -> Dict[str, Any]:
    """Set image-side cell properties.

    Allowed keys: fit_mode (contain/cover/fit_w/fit_h),
    rotation (0/90/180/270), align_h (left/center/right),
    align_v (top/center/bottom), padding_*/crop_* (mm/normalised),
    z_index, override_width_mm, override_height_mm,
    aspect_ratio_locked, svg_normalize_text, svg_normalize_text_pt.
    """
    cell = _find_cell(ctx, cell_id)
    bad = set(changes) - _CELL_PROP_FIELDS
    if bad:
        raise ToolError("invalid_params",
                        f"unknown fields: {sorted(bad)}",
                        hint=f"allowed: {sorted(_CELL_PROP_FIELDS)}")
    if "rotation" in changes and int(changes["rotation"]) not in (0, 90, 180, 270):
        raise ToolError("invalid_value",
                        "rotation must be one of 0/90/180/270",
                        field="rotation")
    if "rotation" in changes:
        changes["rotation"] = int(changes["rotation"])
    if "z_index" in changes:
        changes["z_index"] = int(changes["z_index"])

    from src.app.commands import PropertyChangeCommand
    cb = (lambda: ctx.on_changed()) if ctx.on_changed else None
    _apply(ctx, PropertyChangeCommand(
        cell, dict(changes), update_callback=cb,
        description="Set Cell Properties",
    ))
    return _ok({"cell_id": cell.id, "applied": dict(changes)})


# ── scale bar ───────────────────────────────────────────────────────────

_SCALE_BAR_FIELDS = {
    "scale_bar_enabled", "scale_bar_mode", "scale_bar_um_per_px",
    "scale_bar_length_um", "scale_bar_color", "scale_bar_show_text",
    "scale_bar_thickness_mm", "scale_bar_position",
    "scale_bar_offset_x", "scale_bar_offset_y",
    "scale_bar_custom_text", "scale_bar_text_size_mm", "scale_bar_unit",
}


def cell_set_scale_bar(ctx: ToolContext, cell_id: str,
                       **changes: Any) -> Dict[str, Any]:
    """Configure the scale bar on a cell.

    Both prefixed and unprefixed keys are accepted (``length_um`` and
    ``scale_bar_length_um`` mean the same field). Allowed (unprefixed):
    enabled, mode, um_per_px, length_um, color, show_text, thickness_mm,
    position (bottom_left/bottom_center/bottom_right), offset_x, offset_y,
    custom_text, text_size_mm, unit (e.g. 'µm', 'nm').
    """
    cell = _find_cell(ctx, cell_id)
    norm: Dict[str, Any] = {}
    for k, v in changes.items():
        full = k if k.startswith("scale_bar_") else f"scale_bar_{k}"
        if full not in _SCALE_BAR_FIELDS:
            raise ToolError(
                "invalid_params",
                f"unknown scale-bar field: {k}",
                hint="allowed (unprefixed): enabled, mode, um_per_px, "
                     "length_um, color, show_text, thickness_mm, position, "
                     "offset_x, offset_y, custom_text, text_size_mm, unit",
            )
        norm[full] = v

    from src.app.commands import PropertyChangeCommand
    cb = (lambda: ctx.on_changed()) if ctx.on_changed else None
    _apply(ctx, PropertyChangeCommand(
        cell, norm, update_callback=cb, description="Set Scale Bar",
    ))
    return _ok({"cell_id": cell.id, "applied": norm,
                "scale_bar_enabled": cell.scale_bar_enabled})


# ── PiP (Picture-in-Picture) insets ─────────────────────────────────────

_PIP_FIELDS = {
    "pip_type", "image_path",
    "crop_left", "crop_top", "crop_right", "crop_bottom",
    "x", "y", "w", "h",
    "border_enabled", "border_color", "border_width_pt", "border_style",
    "content_padding_pt",
    "show_origin_box", "origin_box_color", "origin_box_style",
    "origin_box_width_pt",
    "scale_bar_enabled", "scale_bar_mode", "scale_bar_um_per_px",
    "scale_bar_length_um", "scale_bar_unit", "scale_bar_color",
    "scale_bar_show_text", "scale_bar_thickness_mm", "scale_bar_position",
    "scale_bar_offset_x", "scale_bar_offset_y",
    "scale_bar_custom_text", "scale_bar_text_size_mm",
}


def pip_add(ctx: ToolContext, cell_id: str,
            pip_type: str = "external",
            image_path: Optional[str] = None,
            x: float = 0.62, y: float = 0.62,
            w: float = 0.33, h: float = 0.33) -> Dict[str, Any]:
    """Add a Picture-in-Picture inset to a cell.

    *pip_type* is 'external' (uses *image_path*) or 'zoom' (samples the
    cell's own image at the crop window). Geometry is normalised to the
    host cell: ``x, y, w, h ∈ [0, 1]``.
    """
    cell = _find_cell(ctx, cell_id)
    if pip_type not in ("external", "zoom"):
        raise ToolError(
            "invalid_value",
            f"pip_type must be 'external' or 'zoom', got {pip_type!r}",
            field="pip_type",
        )
    if pip_type == "external" and image_path:
        if not os.path.isfile(image_path):
            raise ToolError("file_not_found", f"no image at {image_path}")

    from src.model.data_model import PiPItem
    from src.app.commands import AddPiPItemCommand

    pip = PiPItem(pip_type=pip_type, image_path=image_path,
                  x=float(x), y=float(y), w=float(w), h=float(h))
    cb = (lambda: ctx.on_changed()) if ctx.on_changed else None
    _apply(ctx, AddPiPItemCommand(cell, pip, update_callback=cb))
    return _ok({"pip_id": pip.id, "cell_id": cell.id})


def pip_remove(ctx: ToolContext, pip_id: str) -> Dict[str, Any]:
    """Remove a PiP inset (search across all cells)."""
    pip, cell = _find_pip_item(ctx, pip_id)
    from src.app.commands import RemovePiPItemCommand
    cb = (lambda: ctx.on_changed()) if ctx.on_changed else None
    _apply(ctx, RemovePiPItemCommand(cell, pip, update_callback=cb))
    return _ok({"pip_id": pip_id, "cell_id": cell.id})


def pip_set_properties(ctx: ToolContext, pip_id: str,
                       **changes: Any) -> Dict[str, Any]:
    """Update properties on a PiP inset (geometry, border, scale bar, …).

    Allowed keys cover geometry (x/y/w/h, normalised), crop_*, border_*,
    show_origin_box, origin_box_*, content_padding_pt, and the full
    scale_bar_* family.
    """
    pip, cell = _find_pip_item(ctx, pip_id)
    bad = set(changes) - _PIP_FIELDS
    if bad:
        raise ToolError("invalid_params",
                        f"unknown PiP fields: {sorted(bad)}",
                        hint=f"allowed: {sorted(_PIP_FIELDS)}")

    from src.app.commands import PropertyChangeCommand
    cb = (lambda: ctx.on_changed()) if ctx.on_changed else None
    _apply(ctx, PropertyChangeCommand(
        pip, dict(changes), update_callback=cb,
        description="Set PiP Properties",
    ))
    return _ok({"pip_id": pip_id, "cell_id": cell.id,
                "applied": dict(changes)})


# ── z-order, export region, size groups, label defaults ─────────────────


def cell_set_z_index(ctx: ToolContext, cell_id: str, z: int) -> Dict[str, Any]:
    """Set z_index on a cell (higher = drawn on top in freeform mode)."""
    cell = _find_cell(ctx, cell_id)
    from src.app.commands import PropertyChangeCommand
    cb = (lambda: ctx.on_changed()) if ctx.on_changed else None
    _apply(ctx, PropertyChangeCommand(
        cell, {"z_index": int(z)}, update_callback=cb,
        description="Set Z-Index",
    ))
    return _ok({"cell_id": cell.id, "z_index": cell.z_index})


def export_region_set(ctx: ToolContext,
                      x_mm: float, y_mm: float,
                      w_mm: float, h_mm: float) -> Dict[str, Any]:
    """Set the persistent export crop rectangle on the project."""
    if w_mm <= 0 or h_mm <= 0:
        raise ToolError("invalid_value", "w_mm and h_mm must be > 0")
    from src.app.commands import SetExportRegionCommand
    cb = (lambda: ctx.on_changed()) if ctx.on_changed else None
    _apply(ctx, SetExportRegionCommand(
        ctx.project,
        (float(x_mm), float(y_mm), float(w_mm), float(h_mm)),
        update_callback=cb,
    ))
    return _ok({"x_mm": x_mm, "y_mm": y_mm, "w_mm": w_mm, "h_mm": h_mm})


def export_region_clear(ctx: ToolContext) -> Dict[str, Any]:
    """Clear the persistent export crop rectangle (export full page)."""
    if ctx.project.export_region is None:
        return _ok({"no_change": True})
    from src.app.commands import ClearExportRegionCommand
    cb = (lambda: ctx.on_changed()) if ctx.on_changed else None
    _apply(ctx, ClearExportRegionCommand(ctx.project, update_callback=cb))
    return _ok({"cleared": True})


def size_group_create(ctx: ToolContext, cell_ids: List[str],
                      name: Optional[str] = None) -> Dict[str, Any]:
    """Create a SizeGroup that pins the listed cells to a shared W/H."""
    if not cell_ids:
        raise ToolError("invalid_value", "cell_ids must be non-empty",
                        field="cell_ids")
    cells = [_find_cell(ctx, cid) for cid in cell_ids]
    nm = str(name) if name else f"Group {len(ctx.project.size_groups) + 1}"
    from src.app.commands import CreateSizeGroupCommand
    cb = (lambda: ctx.on_changed()) if ctx.on_changed else None
    cmd = CreateSizeGroupCommand(ctx.project, cells, nm, update_callback=cb)
    _apply(ctx, cmd)
    return _ok({
        "group_id": cmd.group.id,
        "name": cmd.group.name,
        "members": [c.id for c in cells],
    })


def size_group_delete(ctx: ToolContext, group_id: str) -> Dict[str, Any]:
    """Delete a SizeGroup; members become ungrouped."""
    if ctx.project.find_size_group(group_id) is None:
        raise ToolError("size_group_not_found",
                        f"no size group with id={group_id}")
    from src.app.commands import DeleteSizeGroupCommand
    cb = (lambda: ctx.on_changed()) if ctx.on_changed else None
    _apply(ctx, DeleteSizeGroupCommand(ctx.project, group_id,
                                       update_callback=cb))
    return _ok({"group_id": group_id})


def size_group_set(ctx: ToolContext, group_id: str,
                   **changes: Any) -> Dict[str, Any]:
    """Set name and/or pinned dimensions on a SizeGroup."""
    if ctx.project.find_size_group(group_id) is None:
        raise ToolError("size_group_not_found",
                        f"no size group with id={group_id}")
    allowed = {"name", "pinned_width_mm", "pinned_height_mm"}
    bad = set(changes) - allowed
    if bad:
        raise ToolError("invalid_params",
                        f"unknown fields: {sorted(bad)}",
                        hint=f"allowed: {sorted(allowed)}")
    from src.app.commands import SizeGroupPropertyChangeCommand
    cb = (lambda: ctx.on_changed()) if ctx.on_changed else None
    _apply(ctx, SizeGroupPropertyChangeCommand(
        ctx.project, group_id, dict(changes), update_callback=cb,
    ))
    return _ok({"group_id": group_id, "applied": dict(changes)})


def size_group_assign(ctx: ToolContext, cell_id: str,
                      group_id: Optional[str] = None) -> Dict[str, Any]:
    """Assign a cell to a SizeGroup, or unassign with ``group_id=None``."""
    cell = _find_cell(ctx, cell_id)
    if group_id is not None and ctx.project.find_size_group(group_id) is None:
        raise ToolError("size_group_not_found",
                        f"no size group with id={group_id}")
    from src.app.commands import PropertyChangeCommand
    cb = (lambda: ctx.on_changed()) if ctx.on_changed else None
    _apply(ctx, PropertyChangeCommand(
        cell, {"size_group_id": group_id},
        update_callback=cb, description="Assign Size Group",
    ))
    return _ok({"cell_id": cell_id, "size_group_id": group_id})


def project_set_label_style(ctx: ToolContext, **changes: Any) -> Dict[str, Any]:
    """Set project-level label defaults that newly auto-labeled cells inherit.

    Allowed keys: scheme ('a'/'A'/'(a)'/'(A)'), placement, font_family,
    font_size_pt, font_weight ('normal'/'bold'), color, anchor, offset_x,
    offset_y, align ('left'/'center'/'right').

    Existing labels are NOT restyled — use ``labels_set_style`` for that.
    """
    allowed = {
        "scheme", "placement", "font_family", "font_size_pt",
        "font_weight", "color", "anchor", "offset_x", "offset_y", "align",
    }
    bad = set(changes) - allowed
    if bad:
        raise ToolError("invalid_params",
                        f"unknown fields: {sorted(bad)}",
                        hint=f"allowed: {sorted(allowed)}")
    proj_field_map = {
        "scheme": "label_scheme",
        "placement": "label_placement",
        "font_family": "label_font_family",
        "font_size_pt": "label_font_size",
        "font_weight": "label_font_weight",
        "color": "label_color",
        "anchor": "label_anchor",
        "offset_x": "label_offset_x",
        "offset_y": "label_offset_y",
        "align": "label_align",
    }
    proj_changes = {proj_field_map[k]: v for k, v in changes.items()}
    if "label_font_size" in proj_changes:
        proj_changes["label_font_size"] = int(proj_changes["label_font_size"])

    from src.app.commands import PropertyChangeCommand
    cb = (lambda: ctx.on_changed()) if ctx.on_changed else None
    _apply(ctx, PropertyChangeCommand(
        ctx.project, proj_changes, update_callback=cb,
        description="Set Label Defaults",
    ))
    return _ok({"applied": dict(changes)})


# ── dispatch ────────────────────────────────────────────────────────────


_REGISTRY: Dict[str, Callable[..., Dict[str, Any]]] = {
    # Project lifecycle
    "project_describe":  project_describe,
    "project_new":       project_new,
    "project_open":      project_open,
    "project_save":      project_save,
    "project_export":    project_export,
    # Layout topology (v0.2)
    "row_add":           row_add,
    "row_remove":        row_remove,
    "row_set":           row_set,
    "cell_add":          cell_add,
    "cell_remove":       cell_remove,
    "cell_swap":         cell_swap,
    "cell_split":        cell_split,
    "cell_set_split_ratios": cell_set_split_ratios,
    "layout_set_mode":   layout_set_mode,
    # Image content
    "image_import":      image_import,
    "cell_set_geometry": cell_set_geometry,
    "cell_set_properties": cell_set_properties,
    "cell_set_scale_bar": cell_set_scale_bar,
    "cell_set_z_index":  cell_set_z_index,
    # PiP insets
    "pip_add":           pip_add,
    "pip_remove":        pip_remove,
    "pip_set_properties": pip_set_properties,
    # Text / labels
    "text_add":          text_add,
    "text_remove":       text_remove,
    "text_set_style":    text_set_style,
    "labels_set_style":  labels_set_style,
    "project_set_label_style": project_set_label_style,
    "auto_label_cells":  auto_label_cells,
    # Size groups
    "size_group_create": size_group_create,
    "size_group_delete": size_group_delete,
    "size_group_set":    size_group_set,
    "size_group_assign": size_group_assign,
    # Export region
    "export_region_set": export_region_set,
    "export_region_clear": export_region_clear,
    # Algorithmic + vision
    "auto_layout":       auto_layout,
    "view_screenshot":   view_screenshot,
}


def list_tools() -> List[str]:
    return sorted(_REGISTRY.keys())


def dispatch(name: str, params: Optional[Dict[str, Any]],
             ctx: ToolContext) -> Dict[str, Any]:
    """Resolve *name* in the registry and call it with **params**.

    Always returns the response envelope — never raises. ``ToolError`` is
    caught and reformatted; any other exception becomes ``internal_error``
    with a traceback for debugging.
    """
    fn = _REGISTRY.get(name)
    if fn is None:
        return ToolError(
            "unknown_tool",
            f"no tool named '{name}'",
            hint=f"available: {', '.join(list_tools())}",
        ).to_response()
    try:
        return fn(ctx, **(params or {}))
    except ToolError as e:
        return e.to_response()
    except TypeError as e:
        # Most commonly: missing/extra kwargs from the agent.
        return ToolError(
            "invalid_params", str(e),
            hint=f"check params for '{name}'",
        ).to_response()
    except Exception as e:
        return {
            "ok": False,
            "error": "internal_error",
            "detail": str(e),
            "traceback": traceback.format_exc(),
        }
