"""MCP-facing tool specifications: descriptions + JSON schemas.

Single source of truth for what the LLM sees about each tool. The
:mod:`src.agent.mcp_server` adapter feeds these straight into MCP
``tools/list`` responses.

Conventions
-----------
* The ``description`` is written for the LLM — it should explain *when*
  to call this tool, mention prerequisites, and warn about adjacent
  tools that are easy to confuse (e.g. ``cell_split`` vs ``cell_add``).
  Pair every tool with the corresponding section of
  ``docs/agent_concepts.md`` (also served as the ``ilm://concepts``
  MCP resource).
* The ``input_schema`` is JSON Schema. Required keys go in ``required``;
  optional keys are documented in ``description`` per property.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List


# ── concepts primer (served as MCP resource ilm://concepts) ─────────────


def _load_primer() -> str:
    primer = Path(__file__).resolve().parents[2] / "docs" / "agent_concepts.md"
    if primer.exists():
        return primer.read_text(encoding="utf-8")
    return ("(agent_concepts.md not found; the MCP adapter expects it at "
            "<repo>/docs/agent_concepts.md)")


CONCEPTS_PRIMER_MD: str = _load_primer()


# ── schema builders ────────────────────────────────────────────────────


def _obj(properties: Dict[str, Any], required: tuple = ()) -> Dict[str, Any]:
    """Build a JSON Schema object with ``additionalProperties: False``."""
    return {
        "type": "object",
        "properties": properties,
        "required": list(required),
        "additionalProperties": False,
    }


_PAGE_SIZE = {
    "type": "object",
    "description": "Page size in mm.",
    "properties": {
        "w": {"type": "number", "exclusiveMinimum": 0},
        "h": {"type": "number", "exclusiveMinimum": 0},
    },
    "required": ["w", "h"],
    "additionalProperties": False,
}

_MARGINS = {
    "type": "object",
    "description": "Per-side page margins in mm.",
    "properties": {
        "top":    {"type": "number", "minimum": 0},
        "right":  {"type": "number", "minimum": 0},
        "bottom": {"type": "number", "minimum": 0},
        "left":   {"type": "number", "minimum": 0},
    },
    "additionalProperties": False,
}

_REGION = {
    "type": "object",
    "description": "Sub-rectangle of the page in mm.",
    "properties": {
        "x_mm": {"type": "number"},
        "y_mm": {"type": "number"},
        "w_mm": {"type": "number", "exclusiveMinimum": 0},
        "h_mm": {"type": "number", "exclusiveMinimum": 0},
    },
    "required": ["x_mm", "y_mm", "w_mm", "h_mm"],
    "additionalProperties": False,
}


# ── tool specifications ────────────────────────────────────────────────


TOOL_SPECS: List[Dict[str, Any]] = [
    # ── project lifecycle ────────────────────────────────────────────
    {
        "name": "project_describe",
        "description": (
            "Return the full structure of the active project: page size, "
            "DPI, layout mode, rows, all leaf cells (with parent_id for "
            "split sub-cells), and text items. **Call this first to "
            "discover cell_ids, and again after every structural mutation** "
            "(row_add, cell_split, cell_remove, etc.) to refresh — IDs can "
            "appear or disappear after splits."
        ),
        "input_schema": _obj({}),
    },
    {
        "name": "project_new",
        "description": (
            "Create a fresh project in a new tab (GUI transport only). "
            "Defaults to A4 portrait at 600 DPI with a 2×2 placeholder "
            "grid — reshape with row_add / row_remove / cell_split before "
            "importing images if you want a different topology."
        ),
        "input_schema": _obj({
            "page_size": _PAGE_SIZE,
            "dpi": {"type": "integer", "minimum": 72, "maximum": 2400,
                    "description": "Target export DPI. 600 is standard for "
                                   "publication; 300 for screen previews."},
            "margins": _MARGINS,
        }),
    },
    {
        "name": "project_open",
        "description": (
            "Open an existing .figpack / .figlayout / .json project file. "
            "GUI transport opens in a new tab; CLI transport replaces the "
            "in-memory project."
        ),
        "input_schema": _obj({
            "path": {"type": "string",
                     "description": "Absolute path to the project file."},
        }, required=("path",)),
    },
    {
        "name": "project_save",
        "description": (
            "Persist the project file (the editable source, NOT a rendered "
            "image — use `project_export` for PNG/JPG/TIFF). The file "
            "extension picks the on-disk format:\n"
            "  • `.figlayout` — JSON layout + external image paths (default; "
            "small, edit-friendly)\n"
            "  • `.figpack`   — zipped bundle that embeds the images "
            "(portable, single file). GUI transport only.\n"
            "  • `.json`      — legacy plain JSON (same shape as .figlayout)\n"
            "**Do NOT hand-roll JSON and write it yourself** — call this "
            "tool so ILM owns the schema, paths, and bundle/cache details. "
            "Omit `path` to save in place (like Ctrl+S); pass `path` to do "
            "Save As. All three formats work over MCP."
        ),
        "input_schema": _obj({
            "path": {"type": "string",
                     "description": "Absolute output path with one of the "
                                    "supported extensions. Omit to save "
                                    "over the current project file."},
        }),
    },
    {
        "name": "project_export",
        "description": (
            "Render the active project to PNG / JPG / TIFF on disk at the "
            "project's DPI. Optional `region` crops the output to a "
            "sub-rectangle in mm. For PDF export, the user must use the "
            "GUI (no agent tool for PDF yet)."
        ),
        "input_schema": _obj({
            "path": {"type": "string",
                     "description": "Absolute output path."},
            "format": {"type": "string",
                       "enum": ["PNG", "JPG", "JPEG", "TIFF", "TIF"],
                       "default": "PNG"},
            "region": _REGION,
        }, required=("path",)),
    },

    # ── row tools ────────────────────────────────────────────────────
    {
        "name": "row_add",
        "description": (
            "Insert a new row. Omit `position` to append at the bottom. "
            "`column_count` is the initial number of placeholder cells in "
            "*this* row only — rows are independent and do not have to "
            "align. `height_ratio` is relative to other rows: ratios "
            "[1, 2, 1] split the page 25% / 50% / 25%. **To add a column "
            "to an existing row, use `cell_add` — NOT `row_add`.**"
        ),
        "input_schema": _obj({
            "position": {"type": "integer", "minimum": 0,
                         "description": "Insertion index (default: append)."},
            "column_count": {"type": "integer", "minimum": 1, "default": 2},
            "height_ratio": {"type": "number", "exclusiveMinimum": 0,
                             "description": "Relative row height (default: 1.0)."},
        }),
    },
    {
        "name": "row_remove",
        "description": (
            "Delete a row and everything inside it (cells, images, text). "
            "Subsequent rows shift up to fill the gap."
        ),
        "input_schema": _obj({
            "index": {"type": "integer", "minimum": 0,
                      "description": "Row index to delete."},
        }, required=("index",)),
    },
    {
        "name": "row_set",
        "description": (
            "Tune a row's `height_ratio` and/or per-column width ratios. "
            "`column_ratios` must have exactly one entry per column in "
            "that row, all > 0. Ratios are relative within the row."
        ),
        "input_schema": _obj({
            "index": {"type": "integer", "minimum": 0},
            "height_ratio": {"type": "number", "exclusiveMinimum": 0},
            "column_ratios": {"type": "array",
                              "items": {"type": "number", "exclusiveMinimum": 0},
                              "description": "One entry per column in the row."},
        }, required=("index",)),
    },

    # ── cell tools (top-level inside a row) ─────────────────────────
    {
        "name": "cell_add",
        "description": (
            "Add a placeholder cell to an existing row. Use this to add a "
            "*column* to a row. **Do not confuse with `cell_split`** — "
            "split is for nesting sub-figures *inside* an existing cell."
        ),
        "input_schema": _obj({
            "row_index": {"type": "integer", "minimum": 0},
            "position": {"type": "integer", "minimum": 0,
                         "description": "Column position (default: append)."},
        }, required=("row_index",)),
    },
    {
        "name": "cell_remove",
        "description": (
            "Delete a top-level cell; the row's column count decreases by "
            "one. **Only works on top-level cells.** For split sub-cells, "
            "remove the parent or use `cell_unsplit` (v0.3) to collapse."
        ),
        "input_schema": _obj({
            "cell_id": {"type": "string"},
        }, required=("cell_id",)),
    },
    {
        "name": "cell_swap",
        "description": (
            "Swap the *content* (image, scale bar, fit mode, etc.) of two "
            "cells in place. The cells themselves stay where they are; "
            "only their contents trade. Use for reordering panels without "
            "rebuilding the layout."
        ),
        "input_schema": _obj({
            "cell_id_a": {"type": "string"},
            "cell_id_b": {"type": "string"},
        }, required=("cell_id_a", "cell_id_b")),
    },
    {
        "name": "cell_split",
        "description": (
            "Subdivide a *leaf* cell into `count` sub-cells. Use for "
            "**nested sub-figures inside one grid slot** — e.g. a 2×2 "
            "block inside a wide top panel: `cell_split(top, 'h', 2)` "
            "then `cell_split` each child `('v', 2)`. **To add a column "
            "to a row, use `cell_add` — NOT `cell_split`.**"
        ),
        "input_schema": _obj({
            "cell_id": {"type": "string"},
            "direction": {"type": "string",
                          "enum": ["h", "v", "horizontal", "vertical"],
                          "description": "'h' for side-by-side, 'v' for stacked."},
            "count": {"type": "integer", "minimum": 2, "default": 2},
        }, required=("cell_id", "direction")),
    },

    {
        "name": "cell_set_split_ratios",
        "description": (
            "Resize the children of a split container cell. **Pass the "
            "parent's cell_id (the container that was split), not a "
            "child's.** `ratios` must have one entry per child, in the "
            "order returned by project_describe. Ratios are relative "
            "within the split: `[1, 2, 1]` gives 25% / 50% / 25%. "
            "**This is the right tool for 'make sub-cell X smaller' or "
            "'rebalance these split children' — DO NOT switch to "
            "freeform mode and use cell_set_geometry for that.**"
        ),
        "input_schema": _obj({
            "cell_id": {"type": "string",
                        "description": "Parent (container) cell id, not "
                                       "a child id. Find it via "
                                       "project_describe — it's the "
                                       "parent_id field of the children."},
            "ratios": {"type": "array",
                       "items": {"type": "number", "exclusiveMinimum": 0},
                       "description": "One ratio per child, in describe "
                                      "order. All > 0."},
        }, required=("cell_id", "ratios")),
    },

    # ── layout mode ─────────────────────────────────────────────────
    {
        "name": "layout_set_mode",
        "description": (
            "Switch between 'grid' (rows × columns, default) and 'freeform' "
            "(per-cell mm coordinates, overlap allowed). Switching "
            "grid → freeform **bakes** current positions so the visual "
            "layout is preserved as a starting point. Use freeform for: "
            "overlapping insets, irregular arrangements, precise mm "
            "positioning. Use grid for: standard publication figures."
        ),
        "input_schema": _obj({
            "mode": {"type": "string", "enum": ["grid", "freeform"]},
        }, required=("mode",)),
    },

    # ── image content & geometry ─────────────────────────────────────
    {
        "name": "image_import",
        "description": (
            "Drop an image into a cell. `path` must be an absolute local "
            "file path the app can read (PNG, JPG, TIFF, SVG, …). "
            "`fit_mode` defaults to 'contain' — the whole image fits "
            "inside the cell with letterboxing if aspect ratios differ. "
            "Use 'cover' to fill the cell and crop overflow. Always call "
            "`project_describe` first to get the right `cell_id`."
        ),
        "input_schema": _obj({
            "cell_id": {"type": "string"},
            "path": {"type": "string"},
            "fit_mode": {"type": "string",
                         "enum": ["contain", "cover", "fit_w", "fit_h"],
                         "default": "contain"},
        }, required=("cell_id", "path")),
    },
    {
        "name": "cell_set_geometry",
        "description": (
            "Position and size a cell by absolute mm coordinates. "
            "**Requires `layout_mode='freeform'`** — call "
            "`layout_set_mode('freeform')` first if the project is in "
            "grid mode. `z` controls draw order for overlapping cells "
            "(higher = on top).\n\n"
            "**Do NOT switch to freeform just to resize cells.** For "
            "resizing within a grid use the right tool for the level:\n"
            "  • whole row taller/shorter → `row_set(height_ratio=…)`\n"
            "  • columns within a row → `row_set(column_ratios=[…])`\n"
            "  • sub-cells inside a split → `cell_set_split_ratios`\n"
            "Freeform mode is for *overlap, free positioning, or "
            "irregular layouts*, not for routine resizing."
        ),
        "input_schema": _obj({
            "cell_id": {"type": "string"},
            "x_mm": {"type": "number"},
            "y_mm": {"type": "number"},
            "w_mm": {"type": "number", "exclusiveMinimum": 0},
            "h_mm": {"type": "number", "exclusiveMinimum": 0},
            "z": {"type": "integer",
                  "description": "Draw order; higher = on top."},
        }, required=("cell_id", "x_mm", "y_mm", "w_mm", "h_mm")),
    },

    # ── cell content / styling ──────────────────────────────────────
    {
        "name": "cell_set_properties",
        "description": (
            "Update image-side cell properties: rotation (0/90/180/270), "
            "fit_mode, alignment, padding (mm), crop (normalised 0–1), "
            "z_index, override_width/height_mm, aspect_ratio_locked, "
            "and SVG text-normalisation flags. Pass only the keys you "
            "want to change."
        ),
        "input_schema": _obj({
            "cell_id": {"type": "string"},
            "fit_mode": {"type": "string",
                         "enum": ["contain", "cover", "fit_w", "fit_h"]},
            "rotation": {"type": "integer", "enum": [0, 90, 180, 270]},
            "align_h": {"type": "string",
                        "enum": ["left", "center", "right"]},
            "align_v": {"type": "string",
                        "enum": ["top", "center", "bottom"]},
            "padding_top":    {"type": "number", "minimum": 0},
            "padding_bottom": {"type": "number", "minimum": 0},
            "padding_left":   {"type": "number", "minimum": 0},
            "padding_right":  {"type": "number", "minimum": 0},
            "crop_left":   {"type": "number", "minimum": 0, "maximum": 1},
            "crop_top":    {"type": "number", "minimum": 0, "maximum": 1},
            "crop_right":  {"type": "number", "minimum": 0, "maximum": 1},
            "crop_bottom": {"type": "number", "minimum": 0, "maximum": 1},
            "z_index": {"type": "integer"},
            "override_width_mm":  {"type": "number", "minimum": 0},
            "override_height_mm": {"type": "number", "minimum": 0},
            "aspect_ratio_locked": {"type": "boolean"},
            "svg_normalize_text":   {"type": "boolean"},
            "svg_normalize_text_pt": {"type": "number",
                                      "exclusiveMinimum": 0},
        }, required=("cell_id",)),
    },
    {
        "name": "cell_set_scale_bar",
        "description": (
            "Configure the microscopy scale bar on a cell. Pass "
            "`enabled=true` to turn it on; tune length, thickness, color, "
            "position, offsets, custom text, and µm/px calibration. "
            "Keys may use the `scale_bar_` prefix or omit it."
        ),
        "input_schema": _obj({
            "cell_id": {"type": "string"},
            "enabled": {"type": "boolean"},
            "mode": {"type": "string"},
            "um_per_px": {"type": "number", "exclusiveMinimum": 0},
            "length_um": {"type": "number", "exclusiveMinimum": 0},
            "color": {"type": "string",
                      "description": "Hex color, e.g. '#FFFFFF'."},
            "show_text": {"type": "boolean"},
            "thickness_mm": {"type": "number", "exclusiveMinimum": 0},
            "position": {"type": "string",
                         "enum": ["bottom_left", "bottom_center",
                                  "bottom_right"]},
            "offset_x": {"type": "number"},
            "offset_y": {"type": "number"},
            "custom_text": {"type": ["string", "null"]},
            "text_size_mm": {"type": "number", "exclusiveMinimum": 0},
            "unit": {"type": "string",
                     "description": "Display unit (e.g. 'µm', 'nm')."},
        }, required=("cell_id",)),
    },
    {
        "name": "cell_set_z_index",
        "description": (
            "Set the z_index of a cell. Higher values draw on top. "
            "Mainly useful in freeform mode for overlapping cells."
        ),
        "input_schema": _obj({
            "cell_id": {"type": "string"},
            "z": {"type": "integer"},
        }, required=("cell_id", "z")),
    },

    # ── PiP (Picture-in-Picture) insets ─────────────────────────────
    {
        "name": "pip_add",
        "description": (
            "Add a Picture-in-Picture inset to a cell. `pip_type='external'` "
            "uses an external image at `image_path`; `pip_type='zoom'` "
            "samples the host cell's own image at the crop window. "
            "Geometry (x/y/w/h) is normalised to the host cell, in [0, 1]."
        ),
        "input_schema": _obj({
            "cell_id": {"type": "string"},
            "pip_type": {"type": "string",
                         "enum": ["external", "zoom"],
                         "default": "external"},
            "image_path": {"type": "string",
                           "description": "Absolute path; required for "
                                          "pip_type='external' (optional "
                                          "if you'll set it later)."},
            "x": {"type": "number", "minimum": 0, "maximum": 1},
            "y": {"type": "number", "minimum": 0, "maximum": 1},
            "w": {"type": "number", "exclusiveMinimum": 0, "maximum": 1},
            "h": {"type": "number", "exclusiveMinimum": 0, "maximum": 1},
        }, required=("cell_id",)),
    },
    {
        "name": "pip_remove",
        "description": "Remove a PiP inset by id (search across all cells).",
        "input_schema": _obj({
            "pip_id": {"type": "string"},
        }, required=("pip_id",)),
    },
    {
        "name": "pip_set_properties",
        "description": (
            "Update properties on a PiP inset: geometry (x/y/w/h, "
            "normalised), crop window, border style/width/color, "
            "origin-box marker, and the full scale_bar_* family. Pass "
            "only keys you want to change."
        ),
        "input_schema": _obj({
            "pip_id": {"type": "string"},
            "pip_type": {"type": "string", "enum": ["external", "zoom"]},
            "image_path": {"type": ["string", "null"]},
            "x": {"type": "number"},
            "y": {"type": "number"},
            "w": {"type": "number", "exclusiveMinimum": 0},
            "h": {"type": "number", "exclusiveMinimum": 0},
            "crop_left":   {"type": "number", "minimum": 0, "maximum": 1},
            "crop_top":    {"type": "number", "minimum": 0, "maximum": 1},
            "crop_right":  {"type": "number", "minimum": 0, "maximum": 1},
            "crop_bottom": {"type": "number", "minimum": 0, "maximum": 1},
            "border_enabled": {"type": "boolean"},
            "border_color":   {"type": "string"},
            "border_width_pt": {"type": "number", "minimum": 0},
            "border_style":   {"type": "string",
                               "enum": ["solid", "dashed"]},
            "content_padding_pt": {"type": "number", "minimum": 0},
            "show_origin_box":   {"type": "boolean"},
            "origin_box_color":  {"type": "string"},
            "origin_box_style":  {"type": "string",
                                  "enum": ["solid", "dashed"]},
            "origin_box_width_pt": {"type": "number", "minimum": 0},
            "scale_bar_enabled": {"type": "boolean"},
            "scale_bar_length_um": {"type": "number",
                                    "exclusiveMinimum": 0},
            "scale_bar_unit":  {"type": "string"},
            "scale_bar_color": {"type": "string"},
            "scale_bar_show_text": {"type": "boolean"},
            "scale_bar_thickness_mm": {"type": "number",
                                       "exclusiveMinimum": 0},
            "scale_bar_position": {"type": "string"},
            "scale_bar_offset_x": {"type": "number"},
            "scale_bar_offset_y": {"type": "number"},
            "scale_bar_custom_text": {"type": ["string", "null"]},
            "scale_bar_text_size_mm": {"type": "number",
                                       "exclusiveMinimum": 0},
            "scale_bar_um_per_px": {"type": "number",
                                    "exclusiveMinimum": 0},
        }, required=("pip_id",)),
    },

    # ── text items (free text + per-item styling) ───────────────────
    {
        "name": "text_add",
        "description": (
            "Create a new free text item on the canvas. With "
            "`parent_cell_id`, the text is anchored to that cell; "
            "without it, the text floats globally on the page. "
            "Coordinates are in mm."
        ),
        "input_schema": _obj({
            "text": {"type": "string"},
            "x": {"type": "number"},
            "y": {"type": "number"},
            "parent_cell_id": {"type": "string"},
            "font_family": {"type": "string"},
            "font_size_pt": {"type": "integer", "minimum": 1},
            "font_weight": {"type": "string", "enum": ["normal", "bold"]},
            "color": {"type": "string"},
            "rotation": {"type": "number"},
        }, required=("text",)),
    },
    {
        "name": "text_remove",
        "description": "Delete a TextItem (auto-label or free text).",
        "input_schema": _obj({
            "text_id": {"type": "string"},
        }, required=("text_id",)),
    },
    {
        "name": "text_set_style",
        "description": (
            "Update the style of one TextItem. Use this for per-label "
            "tweaks. To restyle ALL labels at once, prefer "
            "`labels_set_style` instead."
        ),
        "input_schema": _obj({
            "text_id": {"type": "string"},
            "text": {"type": "string"},
            "font_family": {"type": "string"},
            "font_size_pt": {"type": "integer", "minimum": 1},
            "font_weight": {"type": "string", "enum": ["normal", "bold"]},
            "color": {"type": "string"},
            "x": {"type": "number"},
            "y": {"type": "number"},
            "rotation": {"type": "number"},
            "anchor": {"type": "string"},
            "offset_x": {"type": "number"},
            "offset_y": {"type": "number"},
            "bg_enabled": {"type": "boolean"},
            "bg_color": {"type": "string"},
            "bg_padding_mm": {"type": "number", "minimum": 0},
        }, required=("text_id",)),
    },
    {
        "name": "labels_set_style",
        "description": (
            "Restyle EVERY existing cell label in one shot, AND update the "
            "project-level defaults so future auto-labels inherit the same "
            "look. Best tool for 'make labels smaller / change label font'."
        ),
        "input_schema": _obj({
            "font_family": {"type": "string"},
            "font_size_pt": {"type": "integer", "minimum": 1},
            "font_weight": {"type": "string", "enum": ["normal", "bold"]},
            "color": {"type": "string"},
            "anchor": {"type": "string"},
            "offset_x": {"type": "number"},
            "offset_y": {"type": "number"},
        }),
    },
    {
        "name": "project_set_label_style",
        "description": (
            "Set project-level label defaults that NEW auto-labels inherit. "
            "Does NOT restyle existing labels — use `labels_set_style` for "
            "that. Useful before a fresh `auto_label_cells` call."
        ),
        "input_schema": _obj({
            "scheme": {"type": "string",
                       "enum": ["a", "A", "(a)", "(A)"]},
            "placement": {"type": "string"},
            "font_family": {"type": "string"},
            "font_size_pt": {"type": "integer", "minimum": 1},
            "font_weight": {"type": "string", "enum": ["normal", "bold"]},
            "color": {"type": "string"},
            "anchor": {"type": "string"},
            "offset_x": {"type": "number"},
            "offset_y": {"type": "number"},
            "align": {"type": "string",
                      "enum": ["left", "center", "right"]},
        }),
    },

    # ── size groups (force shared W/H across cells) ─────────────────
    {
        "name": "size_group_create",
        "description": (
            "Create a SizeGroup that pins the listed cells to a shared "
            "width/height. Without pinned dimensions, the layout engine "
            "picks the min of members' natural sizes."
        ),
        "input_schema": _obj({
            "cell_ids": {"type": "array",
                         "items": {"type": "string"},
                         "minItems": 1},
            "name": {"type": "string"},
        }, required=("cell_ids",)),
    },
    {
        "name": "size_group_delete",
        "description": "Delete a SizeGroup; members become ungrouped.",
        "input_schema": _obj({
            "group_id": {"type": "string"},
        }, required=("group_id",)),
    },
    {
        "name": "size_group_set",
        "description": (
            "Set name and/or pinned dimensions on a SizeGroup. "
            "Set pinned_width_mm/pinned_height_mm > 0 to force absolute "
            "sizes; 0 lets the layout engine pick them."
        ),
        "input_schema": _obj({
            "group_id": {"type": "string"},
            "name": {"type": "string"},
            "pinned_width_mm":  {"type": "number", "minimum": 0},
            "pinned_height_mm": {"type": "number", "minimum": 0},
        }, required=("group_id",)),
    },
    {
        "name": "size_group_assign",
        "description": (
            "Assign a cell to a SizeGroup, or unassign by passing "
            "`group_id=null`."
        ),
        "input_schema": _obj({
            "cell_id": {"type": "string"},
            "group_id": {"type": ["string", "null"]},
        }, required=("cell_id",)),
    },

    # ── export region (persistent crop) ─────────────────────────────
    {
        "name": "export_region_set",
        "description": (
            "Set a persistent export crop rectangle on the project. "
            "Once set, exporters render only this rectangle instead of "
            "the full page. Use `export_region_clear` to revert."
        ),
        "input_schema": _obj({
            "x_mm": {"type": "number"},
            "y_mm": {"type": "number"},
            "w_mm": {"type": "number", "exclusiveMinimum": 0},
            "h_mm": {"type": "number", "exclusiveMinimum": 0},
        }, required=("x_mm", "y_mm", "w_mm", "h_mm")),
    },
    {
        "name": "export_region_clear",
        "description": (
            "Clear the persistent export crop rectangle (export full "
            "page on subsequent renders)."
        ),
        "input_schema": _obj({}),
    },

    # ── labels & best-fit ────────────────────────────────────────────
    {
        "name": "auto_label_cells",
        "description": (
            "Generate sequential labels — (a), (b), (c)… — for every leaf "
            "cell in reading order. `scheme` picks the alphabet; "
            "`placement='in_cell'` overlays labels on each image (default), "
            "`placement='row_above'` adds a dedicated label row above each "
            "picture row (pick this when overlays would obscure content)."
        ),
        "input_schema": _obj({
            "scheme": {"type": "string", "enum": ["a", "A", "(a)", "(A)"]},
            "placement": {"type": "string",
                          "enum": ["in_cell", "row_above"],
                          "default": "in_cell"},
        }),
    },
    {
        "name": "auto_layout",
        "description": (
            "Run ILM's deterministic best-fit pass: re-balances row "
            "heights and column widths based on imported images' aspect "
            "ratios. **Grid mode only.** Re-run after importing images "
            "or changing topology so cells aren't sized arbitrarily."
        ),
        "input_schema": _obj({}),
    },

    # ── vision ──────────────────────────────────────────────────────
    {
        "name": "view_screenshot",
        "description": (
            "Render the active project to PNG and return it as an image "
            "content block (visible to multimodal LLMs). Use to verify "
            "positioning, check for overlaps, or confirm fit modes "
            "between mutations. **Renders at 150 DPI by default** — "
            "enough to see layout issues, cheap on tokens (~3k image "
            "tokens for A4). Bump `dpi` only if you genuinely need to "
            "read small text or inspect fine detail; 600 DPI burns ~46k "
            "tokens per call."
        ),
        "input_schema": _obj({
            "dpi": {"type": "integer", "minimum": 72, "maximum": 1200,
                    "description": "Preview DPI. Default 150 is "
                                   "sufficient for layout verification. "
                                   "Higher values multiply token cost "
                                   "quadratically."},
        }),
    },
]


# Sanity check: every tool in the registry has a spec and vice versa.
def _check_registry_alignment() -> None:
    try:
        from src.agent.tools import list_tools
    except Exception:
        return
    spec_names = {s["name"] for s in TOOL_SPECS}
    reg_names = set(list_tools())
    missing_spec = reg_names - spec_names
    missing_reg = spec_names - reg_names
    if missing_spec:
        import warnings
        warnings.warn(f"Tools without specs: {sorted(missing_spec)}")
    if missing_reg:
        import warnings
        warnings.warn(f"Specs without tools: {sorted(missing_reg)}")


_check_registry_alignment()
