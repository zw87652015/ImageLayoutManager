"""Mocked how-to animations for the User Guide (Qt-free).

A demo is a scene (plain data) plus a timeline of beats. ``frame_at`` evaluates
the timeline at one moment and returns a Frame of shapes and texts in stage
units (STAGE_W x STAGE_H). ``help_demo_paint`` draws a Frame. Nothing here
imports Qt, and nothing depends on wall-clock time.

Text values: a ``str`` is an i18n key; a ``(en, zh)`` tuple is a literal pair.
"""

import math
from dataclasses import dataclass, field, replace

from src.app.i18n import translate

STAGE_W = 400.0
STAGE_H = 160.0
MIN_TEXT = 9.0
MENU_ROW_H = 13.0
MENUBAR_H = 12.0
TOOLBAR_H = 18.0
CURSOR_H = 13.0
KEYCAP_H = 14.0

CANVAS_Y = MENUBAR_H + TOOLBAR_H
TEXT_SAFETY = 1.08
TEXT_SIZE = 9.0
TOAST_SIZE = 10.0
TITLE_X0 = 4.0
TITLE_W = 30.0
TOOL_X0 = 4.0
TOOL_Y = MENUBAR_H + 2.0
TOOL_H = 14.0
TOOL_ICON = 10.0
TOOL_PAD = 3.0
TOOL_TEXT_GAP = 3.0
TOOL_SPLIT_W = 9.0
TOOL_SPACING = 2.0
TOOL_SEP_W = 7.0
TOOL_RIGHT = STAGE_W - 4.0
EXPORT_PAD = 6.0
MENU_SEP_H = 5.0
MENU_PAD = 3.0
MENU_SHADOW = 1.5
MENU_SIDE = 8.0
MENU_ARROW_W = 10.0
MENU_MIN_W = 60.0
MENU_ROWS_MAX = 7
INSPECTOR_X = 256.0
INSPECTOR_HIDDEN_X = STAGE_W
FIELD_VALUE_X = 364.0
FIELD_VALUE_W = 30.0
FIELD_Y0 = 56.0
FIELD_PITCH = 20.0
TILE_FIELD_H = 23.0
TILE_X0 = 318.0
TILE_W_MAX = 16.0
TILE_H = 12.0
TILE_GAP = 2.0
FIELD_TEXT_CX = FIELD_VALUE_X + 1.0 + (FIELD_VALUE_W - 3.0) / 2.0
SELECT_MS = 250
CARET_BLINK_MS = 265
CAPS_Y = 116.0
TOAST_Y = 142.0
BLANK_POINT = (14.0, 140.0)
PRESS_MS = 120
RIPPLE_MS = 300
CLICK_MS = PRESS_MS + RIPPLE_MS
RIGHT_MARK_MS = 400

MENU_TITLES = ("menu_file", "menu_edit", "menu_layout", "menu_view", "menu_tools", "menu_help")
CONTEXT_MENUS = ("ctx", "ctx_img", "ctx_missing", "ctx_plot", "pip_ctx")

# Visible menu rows, taken from the real menus in main_window.py (contiguous
# slices; a trailing "more" row stands for the items that are cut off).
MENUS = {
    "menu_file": (
        ("item", "action_convert_to_bundle", None),
        ("sep",),
        ("item", "action_import", None),
        ("item", "action_open_grid", None),
        ("item", "action_reload", None),
        ("item", "action_export_sources", None),
        ("more",),
    ),
    "menu_edit": (
        ("item", "action_delete_img", None),
        ("sep",),
        ("item", "action_auto_label_incell", None),
        ("item", "action_auto_label_outcell", None),
        ("item", "menu_group_label", "menu_group_label"),
        ("item", "action_auto_layout", None),
        ("more",),
    ),
    "menu_layout": (
        ("item", "action_align_plots", None),
        ("sep",),
        ("item", "action_bake", None),
        ("item", "action_grid_mode", None),
        ("sep",),
        ("item", "action_bring_front", None),
        ("more",),
    ),
    "menu_view": (
        ("item", "action_toggle_layers", None),
        ("item", "action_show_rulers", None),
        ("item", "menu_ruler_units", "menu_ruler_units"),
        ("more",),
    ),
    "toolbar_export": (
        ("item", "action_export_pdf", None),
        ("item", "action_export_tiff", None),
        ("item", "action_export_jpg", None),
        ("item", "action_export_png", None),
        ("item", "action_copy_png_clipboard", None),
        ("item", "action_export_svg", None),
        ("more",),
    ),
    "ctx": (
        ("item", "ctx_fit_mode", "ctx_fit_mode"),
        ("item", "ctx_rotation", "ctx_rotation"),
        ("sep",),
        ("item", "ctx_insert", "ctx_insert"),
        ("item", "ctx_split_subcell", "ctx_split_subcell"),
        ("item", "ctx_delete", "ctx_delete"),
        ("more",),
    ),
    "ctx_insert": (
        ("item", "ctx_row_above", None),
        ("item", "ctx_row_below", None),
        ("sep",),
        ("item", "ctx_col_left", None),
        ("item", "ctx_col_right", None),
    ),
    "ctx_split_subcell": (
        ("item", "ctx_cell_above", None),
        ("item", "ctx_cell_below", None),
        ("item", "ctx_cell_left", None),
        ("item", "ctx_cell_right", None),
        ("sep",),
        ("item", "ctx_split_n_cols", None),
        ("item", "ctx_split_n_rows", None),
    ),
}

MENUS.update({
    # Cell context menu for image cells (order follows main_window's cell menu).
    "ctx_img": (
        ("item", "ctx_crop_image", None),
        ("item", "ctx_fit_mode", "ctx_fit_mode"),
        ("item", "ctx_rotation", "ctx_rotation"),
        ("sep",),
        ("item", "ctx_enable_scale_bar", None),
        ("sep",),
        ("item", "ctx_create_size_group", None),
    ),
    "ctx_fit_mode": (
        ("item", "ctx_fit_contain", None),
        ("item", "ctx_fit_cover", None),
    ),
    "ctx_missing": (
        ("item", "ctx_import_image", None),
        ("item", "action_delete_img", None),
    ),
    "ctx_plot": (
        ("item", "ctx_svg_text_inspector", None),
        ("sep",),
        ("item", "ctx_create_size_group", None),
    ),
    "pip_ctx": (
        ("item", "pip_ctx_remove", None),
    ),
    "menu_group_label": (
        ("item", "action_group_label_top", None),
        ("item", "action_group_label_bottom", None),
        ("item", "action_group_label_left", None),
        ("item", "action_group_label_right", None),
    ),
})

# tool id -> (i18n label key, icon name, has a dropdown). Mirrors the real toolbar.
TOOLS = {
    "undo": ("action_undo", "undo", False),
    "redo": ("action_redo", "redo", False),
    "new": ("action_new", "new", False),
    "open": ("action_open", "open", False),
    "save": ("action_save", "save", False),
    "auto_incell": ("action_auto_label_incell", "cell_labels", False),
    "auto_outcell": ("action_auto_label_outcell", "row_labels", True),
    "auto_layout": ("action_auto_layout", "auto_layout", True),
    "draw": ("action_draw_mode", "mark_polyline", False),
    "export": ("toolbar_export", "export", False),
}

# Groups in toolbar order, separated by a gap; "export" sits apart, right-aligned.
TOOL_GROUPS = (("undo", "redo"), ("new", "open", "save"), ("auto_incell", "auto_outcell", "auto_layout", "draw"))

FIELD_LABELS = {
    "page_w": "lbl_page_width",
    "page_h": "lbl_page_height",
    "gap": "lbl_cell_gap",
    "lfont": "lbl_font",
    "lsize": "lbl_size",
    "lcolor": "lbl_color",
    "mleft": "lbl_margin_left",
    "fit": "lbl_fit_mode",
    "rot": "lbl_rotation",
    "freex": "lbl_pos_x",
    "freey": "lbl_pos_y",
    "freew": "lbl_width_mm",
    "freeh": "lbl_height_mm",
    "sgw": "lbl_size_group_pinned_w",
    "calib": "lbl_mapping",
    "sbpos": "lbl_position",
}


@dataclass(frozen=True)
class Beat:
    kind: str
    ms: int
    target: object = None
    data: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Demo:
    key: str
    scene: dict
    beats: tuple


@dataclass(frozen=True)
class Shape:
    kind: str
    rect: tuple = ()
    fill: str = ""
    line: str = ""
    alpha: float = 1.0
    radius: float = 0.0
    dashed: bool = False
    name: str = ""
    extra: tuple = ()
    order: int = 0

    def bounds(self):
        if self.kind == "line":
            x1, y1, x2, y2 = self.rect
            return (min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1))
        if self.kind == "picture" and len(self.extra) > 1 and self.extra[1]:
            return self.extra[1]
        return self.rect


@dataclass(frozen=True)
class Text:
    rect: tuple
    value: object
    size: float
    role: str
    alpha: float = 1.0
    align: str = "left"
    order: int = 0


@dataclass(frozen=True)
class Frame:
    step: int
    t_ms: int
    shapes: tuple
    texts: tuple


# ----------------------------------------------------------------------
# Text sizing (estimate, language-independent: the wider of en / zh)
# ----------------------------------------------------------------------

def _width_of(text, size):
    return sum(size if ord(ch) > 0x2E80 else 0.6 * size for ch in text)


def text_width(value, size):
    if isinstance(value, tuple):
        candidates = value
    else:
        candidates = (translate(value, "en"), translate(value, "zh"))
    return TEXT_SAFETY * max(_width_of(c, size) for c in candidates)


def _lit(text):
    return (text, text)


TILE_FIELDS = {
    "fit": (("fit_contain", _lit("contain")), ("fit_cover", _lit("cover"))),
    "rot": (("rot_0", _lit("0\u00b0")), ("rot_90", _lit("90\u00b0")),
            ("rot_180", _lit("180\u00b0")), ("rot_270", _lit("270\u00b0"))),
    "sbpos": (("sb_bottom_left", "pos_bottom_left"), ("sb_bottom_center", "pos_bottom_center"),
              ("sb_bottom_right", "pos_bottom_right")),
}


# ----------------------------------------------------------------------
# State: plain dicts. ``_merge`` applies changes (None deletes a key);
# ``_blend`` interpolates between two states for morphs.
# ----------------------------------------------------------------------

def _merge(base, changes):
    out = dict(base)
    for key, value in changes.items():
        if value is None:
            out.pop(key, None)
        elif isinstance(value, dict):
            out[key] = _merge(out[key], value) if isinstance(out.get(key), dict) else _merge({}, value)
        else:
            out[key] = value
    return out


def _lerp(a, b, k):
    return a + (b - a) * k


def _fade(entry, k, appearing):
    if not isinstance(entry, dict):
        return entry
    out = dict(entry)
    base = entry.get("alpha", 1.0)
    out["alpha"] = base * k if appearing else base * (1.0 - k)
    return out


def _blend(a, b, k):
    if k >= 1.0:
        return b
    if isinstance(a, dict) and isinstance(b, dict):
        out = {}
        for key in list(a) + [key for key in b if key not in a]:
            if key in a and key in b:
                out[key] = _blend(a[key], b[key], k)
            elif key in b:
                out[key] = _fade(b[key], k, appearing=True)
            elif isinstance(a[key], dict):
                out[key] = _fade(a[key], k, appearing=False)
        return out
    if isinstance(a, bool) or isinstance(b, bool):
        return a if k < 0.5 else b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return _lerp(a, b, k)
    if (isinstance(a, tuple) and isinstance(b, tuple) and len(a) == len(b)
            and all(isinstance(x, (int, float)) for x in a + b)):
        return tuple(_lerp(x, y, k) for x, y in zip(a, b))
    return a if k < 0.5 else b


def _clamp(v, lo=0.0, hi=1.0):
    return max(lo, min(hi, v))


def _ease_io(u):
    u = _clamp(u)
    return u * u * (3.0 - 2.0 * u)


def _ease_out(u):
    u = _clamp(u)
    return 1.0 - (1.0 - u) ** 3


# ----------------------------------------------------------------------
# Geometry helpers
# ----------------------------------------------------------------------

def _title_rect(menu_key):
    index = MENU_TITLES.index(menu_key)
    return (TITLE_X0 + index * TITLE_W, 0.0, TITLE_W, MENUBAR_H)


def _toolbar_layout(state):
    """Tool rects by id, and the x of each group separator. Raises if the tools overlap Export."""
    present = tuple(state["tools"])
    for tid in present:
        if tid not in TOOLS:
            raise ValueError("unknown tool: " + tid)
    rects = {}
    separators = []
    x = TOOL_X0
    groups_placed = 0
    for group in TOOL_GROUPS:
        ids = [tid for tid in group if tid in present]
        if not ids:
            continue
        if groups_placed:
            separators.append(x + TOOL_SEP_W / 2.0)
            x += TOOL_SEP_W
        for index, tid in enumerate(ids):
            if index:
                x += TOOL_SPACING
            label, _icon, has_menu = TOOLS[tid]
            width = TOOL_PAD + TOOL_ICON + TOOL_TEXT_GAP + text_width(label, TEXT_SIZE) + TOOL_PAD
            if has_menu:
                width += TOOL_SPLIT_W
            rects[tid] = (x, TOOL_Y, width, TOOL_H)
            x += width
        groups_placed += 1
    left_end = x
    limit = TOOL_RIGHT
    if "export" in present:
        label = TOOLS["export"][0]
        width = EXPORT_PAD + TOOL_ICON + TOOL_TEXT_GAP + text_width(label, TEXT_SIZE) + EXPORT_PAD
        rects["export"] = (TOOL_RIGHT - width, TOOL_Y, width, TOOL_H)
        limit = TOOL_RIGHT - width
    if left_end + 6.0 > limit:
        raise ValueError("toolbar buttons overlap Export or run off the stage")
    return rects, separators


def _tool_rects(state):
    return _toolbar_layout(state)[0]


def _center(rect):
    x, y, w, h = rect
    return (x + w / 2.0, y + h / 2.0)


def _ordered_pids(state):
    panels = state["panels"]
    return sorted(panels, key=lambda pid: (panels[pid]["rect"][1], panels[pid]["rect"][0], pid))


def _visible_rows(state):
    """Visual rows of visible panels: [(row key, union rect, [panel ids])] sorted top to bottom."""
    groups = {}
    for pid in _ordered_pids(state):
        entry = state["panels"][pid]
        if entry.get("alpha", 1.0) < 0.5:
            continue
        groups.setdefault(entry["row"], []).append(pid)
    rows = []
    for key, pids in groups.items():
        rects = [state["panels"][p]["rect"] for p in pids]
        x0 = min(r[0] for r in rects)
        y0 = min(r[1] for r in rects)
        x1 = max(r[0] + r[2] for r in rects)
        y1 = max(r[1] + r[3] for r in rects)
        rows.append((key, (x0, y0, x1 - x0, y1 - y0), pids))
    rows.sort(key=lambda item: (item[1][1], item[0]))
    return rows


def _dividers(state):
    """Gap rects between neighbouring columns of each visual row, row by row."""
    out = []
    for _key, row_rect, pids in _visible_rows(state):
        columns = {}
        for pid in pids:
            rect = state["panels"][pid]["rect"]
            columns.setdefault(round(rect[0], 1), []).append(rect)
        cols = [columns[k] for k in sorted(columns)]
        for left, right in zip(cols, cols[1:]):
            left_edge = max(r[0] + r[2] for r in left)
            right_edge = min(r[0] for r in right)
            mid = (left_edge + right_edge) / 2.0
            out.append((mid - 2.0, row_rect[1], 4.0, row_rect[3]))
    return out


def _menu_boxes(state):
    """Open menus as boxes. A submenu opens right of its parent, else left without
    overlapping it; if neither fits, the whole chain shifts left."""
    shift = 0.0
    boxes = []
    for _attempt in range(3):
        boxes, needed = _layout_chain(state, shift)
        if needed <= 0:
            break
        shift += needed
    return boxes


def _layout_chain(state, shift):
    boxes = []
    needed = 0.0
    for depth, key in enumerate(state["menus"]):
        if key not in MENUS:
            raise ValueError("unknown menu: " + key)
        entries = MENUS[key]
        widths = [text_width(e[1], TEXT_SIZE) + 2 * MENU_SIDE
                  + (MENU_ARROW_W if e[2] else 0.0) for e in entries if e[0] == "item"]
        width = max([MENU_MIN_W] + widths)
        height = 2 * MENU_PAD + sum(MENU_SEP_H if e[0] == "sep" else MENU_ROW_H for e in entries)
        if depth == 0:
            if key in CONTEXT_MENUS:
                base_x, y = state["ctx_anchor"]
            elif key in MENU_TITLES:
                base_x, y = _title_rect(key)[0], MENUBAR_H
            elif key == "toolbar_export":
                ex, _ey, ew, _eh = _tool_rects(state)["export"]
                base_x, y = ex + ew - width, CANVAS_Y
            else:
                raise ValueError("menu has no anchor: " + key)
            x = base_x - shift
        else:
            parent = boxes[-1]
            parent_rows = [r for r in parent["rows"] if r["sub"] == key]
            if not parent_rows:
                raise ValueError("submenu not under open menu: " + key)
            px, _py, pw, _ph = parent["rect"]
            y = parent_rows[0]["rect"][1]
            if px + pw + width <= STAGE_W:
                x = px + pw
            else:
                x = px - width
                needed = max(needed, -x)
        x = min(max(0.0, x), STAGE_W - width - MENU_SHADOW)
        y = min(max(0.0, y), STAGE_H - height - MENU_SHADOW)
        rows = []
        ry = y + MENU_PAD
        for entry in entries:
            kind = entry[0]
            h = MENU_SEP_H if kind == "sep" else MENU_ROW_H
            rows.append({"kind": kind, "key": entry[1] if kind == "item" else "",
                         "sub": entry[2] if kind == "item" else None,
                         "rect": (x, ry, width, h)})
            ry += h
        boxes.append({"key": key, "rect": (x, y, width, height), "rows": rows})
    return boxes, needed


def _highlight_rows(boxes, cursor):
    """One highlighted row per open menu box, as in Qt: the row that opened the next
    submenu stays lit; the deepest menu with no open submenu lights the item under the cursor."""
    highlighted = {}
    for index in range(len(boxes) - 1):
        child = boxes[index + 1]["key"]
        highlighted[index] = next(r for r in boxes[index]["rows"] if r["sub"] == child)
    hit = _hovered_row(boxes, cursor)
    if hit is not None:
        index = next(i for i, box in enumerate(boxes) if box["key"] == hit[0])
        if index == len(boxes) - 1:
            highlighted[index] = hit[1]
    return highlighted


def _hovered_row(boxes, cursor):
    """The one item row under the cursor: (menu key, row) from the deepest menu under it."""
    cx, cy = cursor
    for box in reversed(boxes):
        bx, by, bw, bh = box["rect"]
        if bx <= cx <= bx + bw and by <= cy <= by + bh:
            for row in box["rows"]:
                rx, ry, rw, rh = row["rect"]
                if row["kind"] == "item" and rx <= cx < rx + rw and ry <= cy < ry + rh:
                    return box["key"], row
            return None
    return None


def _resolve(name, state):
    """Stage rect for a target name (a point is a zero-size rect)."""
    if isinstance(name, tuple):
        return (float(name[0]), float(name[1]), 0.0, 0.0)
    if name == "blank":
        return (BLANK_POINT[0], BLANK_POINT[1], 0.0, 0.0)
    head, _sep, rest = name.partition(":")
    if head == "menu":
        return _title_rect(rest)
    if head == "item":
        menu_key, item_key = rest.split("/", 1)
        for box in _menu_boxes(state):
            if box["key"] == menu_key:
                for row in box["rows"]:
                    if row["kind"] == "item" and row["key"] == item_key:
                        return row["rect"]
        raise ValueError("item not in an open menu: " + name)
    if head == "ctx":
        for box in _menu_boxes(state):
            for row in box["rows"]:
                if row["kind"] == "item" and row["key"] == rest:
                    return row["rect"]
        raise ValueError("ctx item not open: " + name)
    if head == "tool":
        return _tool_rects(state)[rest]
    if head == "panel":
        pids = _ordered_pids(state)
        pid = pids[int(rest)] if rest.isdigit() else rest
        return state["panels"][pid]["rect"]
    if head == "label":
        labelled = [pid for pid in _ordered_pids(state) if "label" in state["panels"][pid]]
        return state["panels"][labelled[int(rest)]]["label"]["rect"]
    if head == "field":
        y = _field_rows(state)[rest]
        if rest in TILE_FIELDS:
            tiles = _tile_rects(rest, y)
            return (TILE_X0, y, tiles[-1][0] + tiles[-1][2] - TILE_X0, TILE_H)
        return (FIELD_VALUE_X, y, FIELD_VALUE_W, 13.0)
    if head == "tile":
        fid, index = rest.split("/", 1)
        return _tile_rects(fid, _field_rows(state)[fid])[int(index)]
    if head == "divider":
        return _dividers(state)[int(rest)]
    if head == "plus":
        _key, row_rect, _pids = _visible_rows(state)[int(rest)]
        return _plus_rect(row_rect)
    if head == "elem":
        return tuple(state["elements"][rest]["rect"])
    raise ValueError("unknown target: " + name)


def _plus_rect(row_rect):
    x, y, w, h = row_rect
    return (x + w + 4.0, y + h / 2.0 - 4.0, 8.0, 8.0)


def _field_rows(state):
    rows, y = {}, FIELD_Y0
    for fid in state["field_order"]:
        rows[fid] = y
        y += TILE_FIELD_H if fid in TILE_FIELDS else FIELD_PITCH
    return rows


def _tile_rects(fid, y):
    count = len(TILE_FIELDS[fid])
    width = min(TILE_W_MAX, (STAGE_W - 6.0 - TILE_X0 - TILE_GAP * (count - 1)) / count)
    return [(TILE_X0 + index * (width + TILE_GAP), y, width, TILE_H) for index in range(count)]


def _fit_43(inner):
    x, y, w, h = inner
    fit_w = min(w, h * 4.0 / 3.0)
    fit_h = fit_w * 3.0 / 4.0
    return (x + (w - fit_w) / 2.0, y + (h - fit_h) / 2.0, fit_w, fit_h)


# ----------------------------------------------------------------------
# Beat evaluation. Each ``_at_*`` returns (state, overlay) for a local time.
# ----------------------------------------------------------------------

def _at_step(beat, state, local):
    return _merge(state, {"step": beat.data["n"]}), {}


def _at_wait(beat, state, local):
    return state, {}


def _at_set(beat, state, local):
    return _merge(state, beat.data["changes"]), {}


def _at_morph(beat, state, local):
    target = _merge(state, beat.data["changes"])
    if local >= beat.ms:
        return target, {}
    return _blend(state, target, _ease_out(local / beat.ms)), {}


def _at_open_menu(beat, state, local):
    return _merge(state, {"menus": beat.data["path"]}), {}


def _at_close_menus(beat, state, local):
    return _merge(state, {"menus": ()}), {}


def _at_context_menu(beat, state, local):
    return _merge(state, {"menus": (beat.data["menu"],), "ctx_anchor": state["cursor"]}), {}


def _at_move(beat, state, local):
    start = state["cursor"]
    dest = _center(_resolve(beat.target, state))
    if local >= beat.ms:
        changes = {"cursor": dest}
        if beat.data.get("after"):
            changes.update(beat.data["after"])
        return _merge(state, changes), _divider_overlay(beat)
    u = _ease_io(local / beat.ms)
    pos = (_lerp(start[0], dest[0], u), _lerp(start[1], dest[1], u))
    return _merge(state, {"cursor": pos}), _divider_overlay(beat)


def _divider_overlay(beat):
    if isinstance(beat.target, str) and beat.target.startswith("divider:"):
        return {"divider": int(beat.target.split(":", 1)[1])}
    return {}


def _at_click(beat, state, local):
    pos = _center(_resolve(beat.target, state)) if beat.target is not None else state["cursor"]
    overlay = {}
    if isinstance(beat.target, str) and beat.target.startswith("field:"):
        overlay["focus"] = beat.target.split(":", 1)[1]
    overlay.update(_divider_overlay(beat))
    if beat.data.get("right"):
        overlay["right"] = local < RIGHT_MARK_MS
        changes = {"cursor": pos}
    else:
        overlay["pressed"] = local < PRESS_MS
        if PRESS_MS <= local < CLICK_MS:
            overlay["ripple"] = (pos, (local - PRESS_MS) / RIPPLE_MS)
        changes = {"cursor": pos}
        if local >= beat.ms:
            changes["menus"] = ()
    return _merge(state, changes), overlay


def _at_double_click(beat, state, local):
    pos = _center(_resolve(beat.target, state))
    overlay = {"pressed": (0 <= local < 100) or (160 <= local < 260)}
    if 260 <= local < beat.ms:
        overlay["ripple"] = (pos, (local - 260) / 200.0)
    changes = {"cursor": pos}
    if local >= beat.ms:
        changes["menus"] = ()
    return _merge(state, changes), overlay


def _panel_at(state, pos):
    for pid in _ordered_pids(state):
        entry = state["panels"][pid]
        if entry.get("alpha", 1.0) < 0.5:
            continue
        x, y, w, h = entry["rect"]
        if x <= pos[0] <= x + w and y <= pos[1] <= y + h:
            return pid
    return None


def _at_drag(beat, state, local):
    ms = beat.ms
    src_rect = _resolve(beat.target, state)
    start = _center(src_rect)
    dst_rect = _resolve(beat.data["dst"], state)
    end = _center(dst_rect)
    live = beat.data.get("live")
    if local >= ms:
        base = _merge(state, live) if live else state
        st = _merge(base, {"cursor": end})
        return st, {}
    u = _ease_io(local / ms)
    pos = (_lerp(start[0], end[0], u), _lerp(start[1], end[1], u))
    st = state
    if live:
        st = _blend(state, _merge(state, live), u)
    st = _merge(st, {"cursor": pos})
    overlay = {"pressed": True}
    if beat.data.get("ghost"):
        overlay["ghost"] = (beat.data["ghost"], pos)
        drop = _panel_at(st, pos)
        if drop is not None:
            overlay["drop"] = drop
    if isinstance(beat.target, str) and beat.target.startswith("divider:"):
        overlay["divider"] = int(beat.target.split(":", 1)[1])
    return st, overlay


def _at_keys(beat, state, local):
    ms = beat.ms
    alpha = _clamp(min(local / 150.0, (ms - local) / 150.0))
    return state, {"keycaps": (beat.data["caps"], alpha, beat.data["dead"])}


def _at_hold_keys(beat, state, local):
    if local >= beat.ms:
        return _merge(state, {"held": beat.data["caps"]}), {}
    return state, {"keycaps": (beat.data["caps"], _clamp(local / float(beat.ms)), False)}


def _at_release_keys(beat, state, local):
    caps = state.get("held", ())
    if local >= beat.ms:
        return _merge(state, {"held": None}), {}
    return state, {"keycaps": (caps, 1.0 - _clamp(local / float(beat.ms)), False)}


def _at_hold_drag(beat, state, local):
    pos = state["cursor"]
    overlay = {"pressed": True, "drop_alpha": 0.55 + 0.45 * math.cos(2.0 * math.pi * local / 600.0)}
    if beat.data.get("ghost"):
        overlay["ghost"] = (beat.data["ghost"], pos)
    drop = _panel_at(state, pos)
    if drop is not None:
        overlay["drop"] = drop
    return state, overlay


def _value_en(value):
    return value[0] if isinstance(value, tuple) else translate(value, "en")


def _at_type(beat, state, local):
    text = beat.data["text"]
    per = beat.data["per"]
    fid = beat.data["field"]
    if fid.startswith("elem:"):
        if local >= len(text) * per:
            typed = text
        else:
            typed = text[:max(1, int(local // per) + 1)]
        return _merge(state, {"elements": {fid[5:]: {"text": _lit(typed)}}}), {"focus": fid}
    if local < SELECT_MS:
        return state, {"focus": fid, "select": (fid, _width_of(_value_en(state["fields"][fid]), TEXT_SIZE))}
    typing = local - SELECT_MS
    end = len(text) * per
    if typing >= end:
        typed = text
    else:
        typed = text[:max(1, int(typing // per) + 1)]
    overlay = {"focus": fid}
    if typing < end or int((typing - end) / CARET_BLINK_MS) % 2 == 0:
        overlay["caret"] = (fid, FIELD_TEXT_CX + _width_of(typed, TEXT_SIZE) / 2.0 + 0.5)
    return _merge(state, {"fields": {fid: _lit(typed)}}), overlay


def _at_toast(beat, state, local):
    ms = beat.ms
    alpha = _clamp(min(local / 200.0, (ms - local) / 200.0))
    return state, {"toast": (beat.data["text"], alpha)}


_AT = {
    "step": _at_step,
    "wait": _at_wait,
    "set": _at_set,
    "morph": _at_morph,
    "open_menu": _at_open_menu,
    "close_menus": _at_close_menus,
    "context_menu": _at_context_menu,
    "move": _at_move,
    "click": _at_click,
    "double_click": _at_double_click,
    "drag": _at_drag,
    "keys": _at_keys,
    "type": _at_type,
    "toast": _at_toast,
    "hold_keys": _at_hold_keys,
    "release_keys": _at_release_keys,
    "hold_drag": _at_hold_drag,
}


def _run(demo, t_ms):
    t = _clamp(float(t_ms), 0.0, float(duration(demo)))
    state = dict(demo.scene)
    start = 0.0
    for index, beat in enumerate(demo.beats):
        end = start + beat.ms
        if t < end or index == len(demo.beats) - 1:
            local = _clamp(t - start, 0.0, float(beat.ms))
            return _AT[beat.kind](beat, state, local)
        state = _AT[beat.kind](beat, state, float(beat.ms))[0]
        start = end
    return state, {}


# ----------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------

def duration(demo):
    return int(sum(beat.ms for beat in demo.beats))


def beat_starts(demo):
    starts, t = [], 0
    for beat in demo.beats:
        starts.append(t)
        t += beat.ms
    return starts


def state_at(demo, t_ms):
    return _run(demo, t_ms)[0]


def target_rect(demo, name, t_ms):
    return _resolve(name, state_at(demo, t_ms))


def frame_at(demo, t_ms):
    t = int(round(_clamp(float(t_ms), 0.0, float(duration(demo)))))
    state, overlay = _run(demo, t)
    return _build_frame(state, overlay, t)


# ----------------------------------------------------------------------
# Frame building
# ----------------------------------------------------------------------

def _fit_rect(inner, aspect):
    x, y, w, h = inner
    fit_w = min(w, h * aspect)
    fit_h = fit_w / aspect
    return (x + (w - fit_w) / 2.0, y + (h - fit_h) / 2.0, fit_w, fit_h)


def _fit_geometry(entry, quarter):
    x, y, w, h = entry["rect"]
    inner = (x + 3.0, y + 3.0, w - 6.0, h - 6.0)
    aspect = entry.get("aspect", 4.0 / 3.0)
    if quarter:
        aspect = 1.0 / aspect
    fit = entry.get("fit", "fit")
    ix, iy, iw, ih = inner
    if fit == "scale":
        return inner, None
    fitted = _fit_rect(inner, aspect)
    if fit == "fill":
        if aspect >= iw / ih:
            ch, cw = ih, ih * aspect
        else:
            cw, ch = iw, iw / aspect
        return (ix + (iw - cw) / 2.0, iy + (ih - ch) / 2.0, cw, ch), inner
    if fit == "crop":
        left, top, right, bottom = entry.get("crop_box", (0.0, 0.0, 1.0, 1.0))
        fx, fy, fw, fh = fitted
        s = iw / ((right - left) * fw)
        return (ix - left * fw * s, iy - top * fh * s, fw * s, fh * s), inner
    return fitted, None


def _picture_geometry(entry):
    """(picture rect, clip rect or None, rotation) for a panel's picture."""
    rot = entry.get("rot", 0)
    if not rot:
        rect, clip = _fit_geometry(entry, 0)
        return rect, clip, 0
    k = _clamp(rot / 90.0)
    (x0, y0, w0, h0), _clip = _fit_geometry(entry, 0)
    (x1, y1, w1, h1), _clip = _fit_geometry(entry, 1)
    x, y, w, h = entry["rect"]
    cx = _lerp(x0 + w0 / 2.0, x1 + w1 / 2.0, k)
    cy = _lerp(y0 + h0 / 2.0, y1 + h1 / 2.0, k)
    dw = _lerp(w0, h1, k)
    dh = _lerp(h0, w1, k)
    inner = (x + 3.0, y + 3.0, w - 6.0, h - 6.0)
    return (cx - dw / 2.0, cy - dh / 2.0, dw, dh), inner, rot


def _draw_order(state):
    panels = state["panels"]
    return sorted(panels, key=lambda pid: (panels[pid].get("z", 0), panels[pid]["rect"][1],
                                           panels[pid]["rect"][0], pid))


def _emit_element(el, shapes, texts):
    alpha = el.get("alpha", 1.0)
    if alpha <= 0.01:
        return
    kind = el.get("shape", "box")
    rect = tuple(el["rect"])
    if kind == "box":
        width = el.get("width", 0.0)
        shapes.append(Shape("rect", rect, el.get("fill", ""), el.get("line", ""), alpha,
                            el.get("radius", 0.0), el.get("dashed", False),
                            extra=(width,) if width else ()))
    elif kind == "picture":
        shapes.append(Shape("picture", rect, alpha=alpha, name=el.get("name", "micro"),
                            extra=(el.get("rot", 0), el.get("clip"))))
    elif kind == "line":
        shapes.append(Shape("line", rect, line=el.get("line", "ink"), alpha=alpha,
                            dashed=el.get("dashed", False),
                            extra=("arrow",) if el.get("arrow") else ()))
    else:
        shapes.append(Shape(kind, rect, fill=el.get("fill", "ink"), line=el.get("line", ""),
                            alpha=alpha, name=el.get("name", "")))
    if el.get("text") is not None:
        texts.append(Text(tuple(el.get("text_rect", rect)), el["text"], el.get("size", TEXT_SIZE),
                          el.get("role", "ink"), alpha, el.get("align", "center")))


def _build_frame(state, overlay, t_ms):
    items = []
    shapes = texts = items
    cursor = (min(state["cursor"][0], STAGE_W - 16.0), min(state["cursor"][1], STAGE_H - CURSOR_H))
    menus_open = bool(state["menus"])

    def rect(r, fill="", line="", alpha=1.0, radius=0.0, dashed=False, width=0.0):
        shapes.append(Shape("rect", tuple(r), fill, line, alpha, radius, dashed,
                            extra=(width,) if width else ()))

    def text(r, value, size, role, alpha=1.0, align="left"):
        texts.append(Text(tuple(r), value, size, role, alpha, align))

    def keycap_row(caps, alpha, dead=False):
        widths = [text_width((cap, cap), TEXT_SIZE) + 8.0 for cap in caps]
        plus_w = text_width(("+", "+"), TEXT_SIZE) + 6.0
        total = sum(widths) + plus_w * (len(caps) - 1)
        visible_w = min(STAGE_W, state.get("inspector_x", INSPECTOR_HIDDEN_X))
        x0 = min(max(4.0, visible_w / 2 - total / 2), visible_w - 4.0 - total)
        cap_alpha = alpha * 0.55 if dead else alpha
        x = x0
        for index, (cap, cw) in enumerate(zip(caps, widths)):
            rect((x, CAPS_Y, cw, KEYCAP_H), fill="surface", line="mid", alpha=cap_alpha, radius=2.5)
            text((x + 4, CAPS_Y, cw - 8, KEYCAP_H), (cap, cap), TEXT_SIZE, "ink", cap_alpha, "center")
            x += cw
            if index < len(caps) - 1:
                text((x, CAPS_Y, plus_w, KEYCAP_H), ("+", "+"), TEXT_SIZE, "muted", cap_alpha, "center")
                x += plus_w
        if dead:
            shapes.append(Shape("cross", (x0 - 2.0, CAPS_Y - 2.0, total + 4.0, KEYCAP_H + 4.0),
                                fill="muted", alpha=alpha))

    # Canvas and page
    rect((0, CANVAS_Y, STAGE_W, STAGE_H - CANVAS_Y), fill="canvas")
    if state.get("page"):
        px, py, pw, ph = state["page"]
        rect((px, py, pw, ph), fill="base", line="mid")
        if state.get("guides"):
            margin = state.get("margin", 6.0)
            rect((px + margin, py + margin, pw - 2 * margin, ph - 2 * margin), line="muted", dashed=True)

    # Panels, in z order
    drop = overlay.get("drop")
    for pid in _draw_order(state):
        entry = state["panels"][pid]
        alpha = entry.get("alpha", 1.0)
        if alpha <= 0.01:
            continue
        x, y, w, h = entry["rect"]
        kind = entry.get("kind")
        if kind is None:
            rect((x, y, w, h), fill="base", line="mid", alpha=alpha, dashed=True)
        else:
            rect((x, y, w, h), fill="base", line="mid", alpha=alpha)
            pic_rect, clip, rot = _picture_geometry(entry)
            shapes.append(Shape("picture", pic_rect, alpha=alpha, name=kind, extra=(rot, clip)))
        if entry.get("selected"):
            for hx, hy in ((x, y), (x + w, y), (x, y + h), (x + w, y + h)):
                rect((hx - 2, hy - 2, 4, 4), fill="accent", alpha=alpha)
        if entry.get("fit") == "crop_edit" and kind is not None:
            fx, fy, fw, fh = pic_rect
            left, top, right, bottom = entry.get("crop_box", (0.0, 0.0, 1.0, 1.0))
            cx, cy = fx + fw * left, fy + fh * top
            cw, ch = fw * (right - left), fh * (bottom - top)
            rect((fx, fy, fw, cy - fy), fill="ink", alpha=0.45 * alpha)
            rect((fx, cy + ch, fw, fy + fh - (cy + ch)), fill="ink", alpha=0.45 * alpha)
            rect((fx, cy, cx - fx, ch), fill="ink", alpha=0.45 * alpha)
            rect((cx + cw, cy, fx + fw - (cx + cw), ch), fill="ink", alpha=0.45 * alpha)
            for hx, hy in ((cx, cy), (cx + cw, cy), (cx, cy + ch), (cx + cw, cy + ch)):
                rect((hx - 2, hy - 2, 4, 4), fill="accent", alpha=alpha)
        if pid == drop:
            rect((x - 1, y - 1, w + 2, h + 2), line="accent", alpha=overlay.get("drop_alpha", 0.95), width=2.0)
        label = entry.get("label")
        if label:
            la = label.get("alpha", 1.0) * alpha
            if la > 0.01:
                text(label["rect"], label["text"], TEXT_SIZE, state["label_color"], la)

    # Divider highlight: only while a beat targets divider:<i>
    dividers = _dividers(state)
    divider_index = overlay.get("divider")
    if divider_index is not None and divider_index < len(dividers):
        dx, dy, dw, dh = dividers[divider_index]
        shapes.append(Shape("rect", (dx, dy, dw, dh), fill="accent", alpha=0.9, name="divider"))

    # "+" add buttons on the row under the cursor, not over menus, dialogs or preview
    dialog_open = any(eid.startswith(("dlg", "viewer", "ts_", "strip", "status", "pv_", "fx_", "pal_"))
                      for eid in state.get("elements", {}))
    plus_ok = not menus_open and state.get("plus", True) and not dialog_open
    for _key, row_rect, _pids in _visible_rows(state):
        rx, ry, rw, rh = row_rect
        if ry <= cursor[1] <= ry + rh and rx - 2 <= cursor[0] <= rx + rw + 14 and plus_ok:
            pr = _plus_rect(row_rect)
            rect(pr, fill="accent", radius=4.0)
            shapes.append(Shape("glyph", pr, name="plus", fill="base"))

    # Inspector
    ix = state.get("inspector_x", INSPECTOR_HIDDEN_X)
    if ix < STAGE_W - 0.5:
        rect((ix, CANVAS_Y, STAGE_W - ix, STAGE_H - CANVAS_Y), fill="base", line="mid")
        text((ix + 6, CANVAS_Y + 4, STAGE_W - ix - 12, 12), state["inspector_title"], TEXT_SIZE, "ink")
        focus = overlay.get("focus")
        select = overlay.get("select")
        caret = overlay.get("caret")
        rows = _field_rows(state)
        for fid in state["field_order"]:
            fy = rows[fid]
            text((ix + 6, fy, FIELD_VALUE_X - ix - 10, 13), FIELD_LABELS[fid], TEXT_SIZE, "ink")
            if fid in TILE_FIELDS:
                selected = int(round(state["fields"][fid]))
                for index, ((key, _caption), (tx, ty, tw, th)) in enumerate(
                        zip(TILE_FIELDS[fid], _tile_rects(fid, fy))):
                    rect((tx, ty, tw, th), fill="base", line="mid", radius=2.0)
                    if index == selected:
                        rect((tx, ty, tw, th), fill="accent", alpha=0.16, radius=2.0)
                        rect((tx, ty, tw, th), line="accent", radius=2.0)
                    shapes.append(Shape("pictogram", (tx + 1.5, ty + 1.5, tw - 3.0, th - 3.0), name=key))
                text((TILE_X0, fy + TILE_H + 1.0, STAGE_W - 6.0 - TILE_X0, 10.0),
                     TILE_FIELDS[fid][selected][1], TEXT_SIZE, "muted", align="left")
                continue
            if fid == "lcolor":
                rect((FIELD_VALUE_X, fy, 14, 13), fill=state["label_color"], line="mid")
                continue
            rect((FIELD_VALUE_X, fy, FIELD_VALUE_W, 13), fill="base",
                 line="accent" if fid == focus else "mid")
            if select and select[0] == fid:
                rect((FIELD_TEXT_CX - select[1] / 2.0 - 1.0, fy + 1.0, select[1] + 2.0, 11.0),
                     fill="accent", alpha=0.35, radius=1.0)
            text((FIELD_VALUE_X + 1, fy, FIELD_VALUE_W - 3, 13), state["fields"][fid],
                 TEXT_SIZE, "ink", align="center")
            if caret and caret[0] == fid:
                rect((caret[1], fy + 2.0, 1.0, 9.0), fill="ink")

    # Overlay elements: dialogs, tool strips, status bar, marks, insets, icons
    for el in state.get("elements", {}).values():
        _emit_element(el, shapes, texts)

    # Menubar and toolbar
    rect((0, 0, STAGE_W, CANVAS_Y), fill="chrome")
    shapes.append(Shape("line", (0, CANVAS_Y, STAGE_W, CANVAS_Y), line="mid"))
    open_title = state["menus"][0] if state["menus"] else None
    for menu_key in MENU_TITLES:
        tr_rect = _title_rect(menu_key)
        if menu_key == open_title:
            rect(tr_rect, fill="accent", alpha=0.25)
        text(tr_rect, menu_key, TEXT_SIZE, "ink", align="center")

    tiles, separators = _toolbar_layout(state)
    for tid, tr_rect in tiles.items():
        tx, ty, tw, th = tr_rect
        label, icon, has_menu = TOOLS[tid]
        inside = tx <= cursor[0] <= tx + tw and ty <= cursor[1] <= ty + th
        if tid == "export":
            rect(tr_rect, fill="accent", radius=3.0)
            if inside:
                rect(tr_rect, fill="ink", alpha=0.20 if overlay.get("pressed") else 0.10, radius=3.0)
            icon_x = tx + EXPORT_PAD
            shapes.append(Shape("icon", (icon_x, ty + 2, TOOL_ICON, TOOL_ICON), name=icon, fill="on_accent"))
            text((icon_x + TOOL_ICON + TOOL_TEXT_GAP, ty, text_width(label, TEXT_SIZE), th), label,
                 TEXT_SIZE, "on_accent")
            continue
        if inside and overlay.get("pressed"):
            rect(tr_rect, fill="accent", alpha=0.18, radius=3.0)
        elif inside:
            rect(tr_rect, fill="ink", alpha=0.07, radius=3.0)
        icon_x = tx + TOOL_PAD
        shapes.append(Shape("icon", (icon_x, ty + 2, TOOL_ICON, TOOL_ICON), name=icon, fill="ink"))
        text((icon_x + TOOL_ICON + TOOL_TEXT_GAP, ty, text_width(label, TEXT_SIZE), th), label, TEXT_SIZE, "ink")
        if has_menu:
            shapes.append(Shape("chevron", (tx + tw - TOOL_SPLIT_W + 2.5, ty + th / 2 - 1.5, 4, 3),
                                fill="ink", name="down"))
    for sx in separators:
        shapes.append(Shape("line", (sx, TOOL_Y + 2, sx, TOOL_Y + TOOL_H - 2), line="mid"))

    # Step badge: never elided, never covered by menus
    step_no = int(round(state["step"]))
    rect((4.0, CANVAS_Y + 3.0, 12.0, 12.0), fill="accent", radius=6.0)
    text((4.0, CANVAS_Y + 3.0, 12.0, 12.0), (str(step_no), str(step_no)), TEXT_SIZE, "base",
         align="center")

    # Menus (drawn above the chrome and badge)
    boxes = _menu_boxes(state)
    highlighted = _highlight_rows(boxes, cursor)
    for box_index, box in enumerate(boxes):
        bx, by, bw, bh = box["rect"]
        rect((bx + MENU_SHADOW, by + MENU_SHADOW, bw, bh), fill="ink", alpha=0.12, radius=2.0)
        rect(box["rect"], fill="base", line="mid", radius=2.0)
        for row in box["rows"]:
            rx, ry, rw, rh = row["rect"]
            if row["kind"] == "sep":
                shapes.append(Shape("line", (rx + 4, ry + rh / 2, rx + rw - 4, ry + rh / 2), line="mid"))
                continue
            inside = highlighted.get(box_index) is row
            if row["kind"] == "more":
                text((rx + MENU_SIDE, ry, rw - 2 * MENU_SIDE, rh), ("\u2026", "\u2026"),
                     TEXT_SIZE, "muted", align="left")
                continue
            if inside:
                rect(row["rect"], fill="accent", alpha=0.9, radius=1.0)
            role = "base" if inside else "ink"
            text((rx + MENU_SIDE, ry, rw - 2 * MENU_SIDE, rh), row["key"], TEXT_SIZE, role)
            if row["sub"]:
                shapes.append(Shape("chevron", (rx + rw - MENU_ARROW_W + 3, ry + rh / 2 - 3, 4, 6),
                                    fill=role, name="right"))

    # Keycaps
    if "keycaps" in overlay:
        keycap_row(*overlay["keycaps"])
    elif state.get("held"):
        keycap_row(state["held"], 1.0)

    # Toast
    if "toast" in overlay:
        value, alpha = overlay["toast"]
        tw = text_width(value, TOAST_SIZE) + 16.0
        tx = (STAGE_W - tw) / 2
        rect((tx, TOAST_Y, tw, 14.0), fill="ink", alpha=alpha, radius=3.0)
        text((tx + 8, TOAST_Y, tw - 16, 14.0), value, TOAST_SIZE, "base", alpha, "center")

    # Pointer, click feedback and drag ghost
    if overlay.get("ripple"):
        (rx, ry), progress = overlay["ripple"]
        radius = min(3.0 + 9.0 * progress, rx, ry, STAGE_W - rx, STAGE_H - ry)
        shapes.append(Shape("ring", (rx - radius, ry - radius, 2 * radius, 2 * radius),
                            line="accent", alpha=1.0 - progress))
    if overlay.get("ghost"):
        kind, (gx, gy) = overlay["ghost"]
        shapes.append(Shape("ghost", (min(gx + 6.0, STAGE_W - 22.0), min(gy + 6.0, STAGE_H - 16.0), 22.0, 16.0),
                            alpha=0.9, name=kind))
    if overlay.get("right"):
        shapes.append(Shape("mouse", (cursor[0] + 9.0, cursor[1], 7.0, 11.0), extra=("right",)))
    if state.get("draw_tool"):
        hx = min(max(cursor[0], 5.0), STAGE_W - 14.0)
        hy = min(max(cursor[1], 5.0), STAGE_H - 14.0)
        shapes.append(Shape("cursor", (hx - 5.0, hy - 5.0, 10.0, 10.0), name="cross"))
        rect((hx + 4.0, hy + 4.0, 9.0, 9.0), fill="base", line="ink", radius=1.5)
        shapes.append(Shape("icon", (hx + 5.0, hy + 5.0, 7.0, 7.0), name="mark_" + state["draw_tool"], fill="ink"))
    else:
        shapes.append(Shape("cursor", (cursor[0], cursor[1], 9.0, CURSOR_H)))

    stamped = [replace(item, order=index) for index, item in enumerate(items)]
    return Frame(step=step_no, t_ms=t_ms,
                 shapes=tuple(item for item in stamped if isinstance(item, Shape)),
                 texts=tuple(item for item in stamped if isinstance(item, Text)))


# ----------------------------------------------------------------------
# Beat constructors
# ----------------------------------------------------------------------

def step(n):
    return Beat("step", 0, data={"n": n})


def wait(ms):
    return Beat("wait", int(ms))


def set(**changes):
    return Beat("set", 0, data={"changes": changes})


def morph(ms, **changes):
    return Beat("morph", int(ms), data={"changes": changes})


def move(target, ms=600, after=None):
    return Beat("move", int(ms), target=target, data={"after": after})


def click(target=None, right=False):
    return Beat("click", CLICK_MS, target=target, data={"right": right})


def double_click(target):
    return Beat("double_click", 600, target=target)


def drag(src, dst, ms=900, ghost=None, live=None):
    return Beat("drag", int(ms), target=src,
                data={"dst": dst, "ghost": ghost, "live": live})


def open_menu(path):
    return Beat("open_menu", 250, data={"path": tuple(path)})


def close_menus():
    return Beat("close_menus", 150)


def _item_has_sub(menu_key, item_key):
    for entry in MENUS.get(menu_key, ()):
        if entry[0] == "item" and entry[1] == item_key:
            return entry[2]
    raise ValueError("no item %s in %s" % (item_key, menu_key))


def hover_item(path):
    menu_key, item_key = path[-2], path[-1]
    has_sub = _item_has_sub(menu_key, item_key)
    menus = tuple(path) if has_sub else tuple(path[:-1])
    return move("item:%s/%s" % (menu_key, item_key), ms=350, after={"menus": menus})


def context_menu(menu_id="ctx"):
    return Beat("context_menu", 300, data={"menu": menu_id})


def keys(*caps, ms=900, dead=False):
    return Beat("keys", int(ms), data={"caps": tuple(caps), "dead": dead})


def hold_keys(*caps, ms=250):
    return Beat("hold_keys", int(ms), data={"caps": tuple(caps)})


def release_keys(ms=200):
    return Beat("release_keys", int(ms))


def hold_drag(ms, ghost=None):
    return Beat("hold_drag", int(ms), data={"ghost": ghost})


def pick(field_id, index, ms=500):
    return [move("tile:%s/%d" % (field_id, index), ms), click(), set(fields={field_id: index})]


def type_text(field_id, text, ms_per_char=90):
    select = 0 if field_id.startswith("elem:") else SELECT_MS
    ms = select + len(text) * ms_per_char + 300
    return Beat("type", ms, data={"field": field_id, "text": text, "per": ms_per_char})


def toast(text, ms=1200):
    return Beat("toast", int(ms), data={"text": text})


# ----------------------------------------------------------------------
# Scenes
# ----------------------------------------------------------------------

PAGE_FILL = 0.85
PAGE_MARGIN = 8.0
GAP_BEFORE = 3.0     # stage units for the gap as first drawn ("2")
GAP_AFTER = 9.0      # stage units once "4" is typed (illustrative, not to scale)
FF_ASPECT = 200.0 / 116.0
RC_ASPECT = 240.0 / 116.0
PL_ASPECT = 236.0 / 80.0


def _fit_page(aspect, canvas_w):
    """Page of the given aspect: 85% of the canvas height, centred left of canvas_w."""
    height = PAGE_FILL * (STAGE_H - CANVAS_Y)
    width = height * aspect
    max_w = canvas_w - 2 * PAGE_MARGIN
    if width > max_w:
        width = max_w
        height = width / aspect
    x = (canvas_w - width) / 2.0
    y = CANVAS_Y + ((STAGE_H - CANVAS_Y) - height) / 2.0
    return (x, y, width, height)


def _grid2x2(page, gap):
    px, py, pw, ph = page
    x0, y0, iw, ih = px + PAGE_MARGIN, py + PAGE_MARGIN, pw - 2 * PAGE_MARGIN, ph - 2 * PAGE_MARGIN
    cw, ch = (iw - gap) / 2.0, (ih - gap) / 2.0
    return {
        "p0": (x0, y0, cw, ch), "p1": (x0 + cw + gap, y0, cw, ch),
        "p2": (x0, y0 + ch + gap, cw, ch), "p3": (x0 + cw + gap, y0 + ch + gap, cw, ch),
    }


def _rows(page, counts, gap=4.0, pad=PAGE_MARGIN):
    px, py, pw, ph = page
    iw, ih = pw - 2 * pad, ph - 2 * pad
    row_h = (ih - (len(counts) - 1) * gap) / len(counts)
    out, y = [], py + pad
    for count in counts:
        cw = (iw - (count - 1) * gap) / count
        out.append([(px + pad + k * (cw + gap), y, cw, row_h) for k in range(count)])
        y += row_h + gap
    return out


def _row_panel(rect, row, kind=None, **extra):
    entry = {"rect": tuple(rect), "row": row, "kind": kind, "alpha": 1.0, "selected": False}
    entry.update(extra)
    return entry


def _panels_for(page, rows_ids, kinds):
    rects = _rows(page, [len(r) for r in rows_ids])
    out = {}
    for row_index, (ids, cells) in enumerate(zip(rows_ids, rects)):
        for pid, rect in zip(ids, cells):
            out[pid] = _row_panel(rect, "r%d" % row_index, kinds.get(pid))
    return out


def _split_rect(rect):
    x, y, w, h = rect
    half = (h - 4.0) / 2.0
    return (x, y, w, half), (x, y + half + 4.0, w, half)


def _label_panels(page, mode):
    """Three labelled panels: in-cell labels, or the same panels with an above-cell band."""
    out = {}
    for i, rect in enumerate(_rows(page, [3])[0]):
        x, y, w, h = rect
        pid = "p%d" % i
        letter = "(%s)" % "abc"[i]
        if mode == "in":
            out[pid] = {"rect": rect, "label": {
                "text": (letter, letter), "rect": (x + 2.0, y + 2.0, 20.0, 11.0), "alpha": 1.0}}
        else:
            out[pid] = {"rect": (x, y + 14.0, w, h - 14.0), "label": {
                "text": (letter, letter), "rect": (x + 2.0, y + 1.0, 20.0, 11.0), "alpha": 1.0}}
    return out


def _scene_first_figure():
    page = _fit_page(FF_ASPECT, STAGE_W)
    rows = {"p0": "r0", "p1": "r0", "p2": "r1", "p3": "r1"}
    panels = {pid: _row_panel(rect, rows[pid]) for pid, rect in _grid2x2(page, GAP_BEFORE).items()}
    return {
        "step": 1,
        "cursor": (300.0, 96.0),
        "menus": (),
        "ctx_anchor": (0.0, 0.0),
        "tools": ("save", "auto_layout", "export"),
        "page": page,
        "guides": False,
        "panels": panels,
        "inspector_x": INSPECTOR_HIDDEN_X,
        "inspector_title": "grp_project",
        "fields": {"page_w": _lit("210"), "page_h": _lit("297"), "gap": _lit("2")},
        "field_order": ("page_w", "page_h", "gap"),
        "label_color": "ink",
    }


def _scene_rows_cells():
    page = _fit_page(RC_ASPECT, STAGE_W)
    kinds = {"a0": "photo", "a1": "chart", "a2": "bars", "b0": "micro", "b1": "photo"}
    panels = _panels_for(page, [["a0", "a1", "a2"], ["b0", "b1"]], kinds)
    return {
        "step": 1,
        "cursor": (300.0, 120.0),
        "menus": (),
        "ctx_anchor": (0.0, 0.0),
        "tools": (),
        "page": page,
        "guides": False,
        "panels": panels,
        "inspector_x": INSPECTOR_HIDDEN_X,
        "inspector_title": "grp_project",
        "fields": {},
        "field_order": (),
        "label_color": "ink",
    }


def _scene_panel_labels():
    page = _fit_page(PL_ASPECT, STAGE_W)
    kinds = ("photo", "chart", "photo")
    panels = {"p%d" % i: _row_panel(rect, "r0", kinds[i])
              for i, rect in enumerate(_rows(page, [3])[0])}
    return {
        "step": 1,
        "cursor": (300.0, 120.0),
        "menus": (),
        "ctx_anchor": (0.0, 0.0),
        "tools": ("auto_incell", "auto_outcell"),
        "page": page,
        "guides": False,
        "panels": panels,
        "inspector_x": INSPECTOR_HIDDEN_X,
        "inspector_title": "grp_text",
        "fields": {"lfont": _lit("Arial"), "lsize": _lit("9 pt"), "lcolor": _lit("")},
        "field_order": ("lfont", "lsize", "lcolor"),
        "label_color": "ink",
    }


def _build_demos():
    # --- first_figure -------------------------------------------------
    ff_inspector_page = _fit_page(FF_ASPECT, INSPECTOR_X)
    ff_beats = [
        step(1), wait(300),
        move("menu:menu_file", 700), click(), open_menu(("menu_file",)), wait(200),
        move("item:menu_file/action_import", 700), click(), wait(200),
    ]
    for pid, kind in (("p0", "chart"), ("p1", "micro"), ("p2", "photo"), ("p3", "bars")):
        ff_beats += [set(panels={pid: {"kind": kind}}), wait(120)]
    ff_beats += [
        wait(400),
        step(2),
        move("blank", 600), click(),
        morph(450, inspector_x=INSPECTOR_X, page=ff_inspector_page,
              panels={pid: {"rect": rect} for pid, rect in _grid2x2(ff_inspector_page, GAP_BEFORE).items()}),
        wait(250),
        move("field:gap", 600), click(), type_text("gap", "4", 120), wait(200),
        morph(500, panels={pid: {"rect": rect} for pid, rect in _grid2x2(ff_inspector_page, GAP_AFTER).items()}),
        wait(400),
        step(3),
        keys("Ctrl", "S", ms=900), toast(("Saved", "已保存"), ms=1100), wait(400),
        move("tool:export", 600), click(), open_menu(("toolbar_export",)), wait(200),
        move("item:toolbar_export/action_export_pdf", 600), click(),
        toast(("figure.pdf", "figure.pdf"), ms=1200), wait(400),
    ]

    # --- rows_cells ---------------------------------------------------
    page = _fit_page(RC_ASPECT, STAGE_W)
    kinds = {"a0": "photo", "a1": "chart", "a2": "bars", "a3": None,
             "b0": "micro", "b1": "photo", "n0": None, "b1b": None}
    after_add = {"panels": _panels_for(page, [["a0", "a1", "a2", "a3"], ["b0", "b1"]], kinds)}
    after_row = {"panels": _panels_for(page, [["a0", "a1", "a2", "a3"], ["n0"], ["b0", "b1"]], kinds)}
    # Split b1 into a top and a bottom sub-cell in the same column; the new one starts empty.
    b1_top, b1_bottom = _split_rect(after_row["panels"]["b1"]["rect"])
    split = {"panels": {
        "b1": {"rect": b1_top},
        "b1b": _row_panel(b1_bottom, "r2", None),
    }}
    # Live width change of the bottom row when its divider moves right.
    b0_rect = after_row["panels"]["b0"]["rect"]
    dx = 40.0
    live = {"panels": {
        "b0": {"rect": (b0_rect[0], b0_rect[1], b0_rect[2] + dx, b0_rect[3])},
        "b1": {"rect": (b1_top[0] + dx, b1_top[1], b1_top[2] - dx, b1_top[3])},
        "b1b": {"rect": (b1_bottom[0] + dx, b1_bottom[1], b1_bottom[2] - dx, b1_bottom[3])},
    }}
    divider_x = b0_rect[0] + b0_rect[2] + 2.0
    divider_y = b1_top[1] + (b1_bottom[1] + b1_bottom[3] - b1_top[1]) / 2.0
    rc_beats = [
        step(1), wait(300),
        move("plus:0", 700), click(), morph(550, **after_add), wait(300),
        move("panel:a1", 700), click(right=True), context_menu("ctx"), wait(250),
        hover_item(("ctx", "ctx_insert")), wait(150),
        move("item:ctx_insert/ctx_row_below", 500), click(),
        morph(550, **after_row), wait(400),
        step(2),
        move("panel:b1", 600), click(right=True), context_menu("ctx"), wait(250),
        hover_item(("ctx", "ctx_split_subcell")), wait(150),
        move("item:ctx_split_subcell/ctx_cell_above", 500), click(),
        morph(550, **split), wait(400),
        step(3),
        move("divider:3", 600),
        drag("divider:3", (divider_x + dx, divider_y), ms=1000, live=live), wait(400),
    ]

    # --- panel_labels ---------------------------------------------------
    pl_page = _fit_page(PL_ASPECT, STAGE_W)
    pl_inspector_page = _fit_page(PL_ASPECT, INSPECTOR_X)
    pl_beats = [
        step(1), wait(300),
        move("menu:menu_edit", 600), click(), open_menu(("menu_edit",)), wait(200),
        move("item:menu_edit/action_auto_label_incell", 600), click(),
        morph(260, panels=_label_panels(pl_page, "in")), wait(400),
        step(2),
        move("menu:menu_edit", 600), click(), open_menu(("menu_edit",)), wait(200),
        move("item:menu_edit/action_auto_label_outcell", 600), click(),
        morph(600, panels=_label_panels(pl_page, "band")), wait(400),
        step(3),
        move("label:0", 600), click(),
        morph(450, inspector_x=INSPECTOR_X, page=pl_inspector_page,
              panels=_label_panels(pl_inspector_page, "band")), wait(250),
        move("field:lcolor", 600), click(),
        morph(300, label_color="accent"), wait(500),
    ]

    return {
        "first_figure": Demo("first_figure", _scene_first_figure(), tuple(ff_beats)),
        "rows_cells": Demo("rows_cells", _scene_rows_cells(), tuple(rc_beats)),
        "panel_labels": Demo("panel_labels", _scene_panel_labels(), tuple(pl_beats)),
    }


# ----------------------------------------------------------------------
# Element and scene helpers for the topic demos
# ----------------------------------------------------------------------

def _el(shape, rect, **kw):
    el = {"shape": shape, "rect": tuple(rect)}
    el.update(kw)
    return el


def _box(rect, **kw):
    return _el("box", rect, **kw)


def _pic(rect, name, **kw):
    return _el("picture", rect, name=name, **kw)


def _txt(rect, value, role="ink", size=TEXT_SIZE, align="center", **kw):
    return _el("box", rect, text=value, role=role, size=size, align=align, **kw)


def _line(x1, y1, x2, y2, **kw):
    return _el("line", (x1, y1, x2, y2), **kw)


def _none(ids):
    return {key: None for key in ids}


def _frac(page, fr):
    px, py, pw, ph = page
    fx, fy, fw, fh = fr
    return (px + fx * pw, py + fy * ph, fw * pw, fh * ph)


def _quad(rect, gap):
    x, y, w, h = rect
    cw, ch = (w - gap) / 2.0, (h - gap) / 2.0
    return {
        "p0": (x, y, cw, ch), "p1": (x + cw + gap, y, cw, ch),
        "p2": (x, y + ch + gap, cw, ch), "p3": (x + cw + gap, y + ch + gap, cw, ch),
    }


def _inner(page, margin=PAGE_MARGIN):
    px, py, pw, ph = page
    return (px + margin, py + margin, pw - 2 * margin, ph - 2 * margin)


def _pic_rect(entry):
    return _picture_geometry(entry)[0]


def _scene(page, panels, *, tools=(), inspector_x=INSPECTOR_HIDDEN_X, title="grp_project",
           fields=None, order=(), elements=None, cursor=(300.0, 120.0)):
    return {
        "step": 1,
        "cursor": cursor,
        "menus": (),
        "ctx_anchor": (0.0, 0.0),
        "tools": tuple(tools),
        "page": page,
        "guides": False,
        "margin": 6.0,
        "panels": panels,
        "inspector_x": inspector_x,
        "inspector_title": title,
        "fields": dict(fields or {}),
        "field_order": tuple(order),
        "label_color": "ink",
        "elements": dict(elements or {}),
    }


def _dialog(prefix, rect, title):
    x, y, w, h = rect
    return {
        prefix + "_bg": _box(rect, fill="base", line="mid", radius=3.0),
        prefix + "_bar": _box((x, y, w, 13.0), fill="surface", line="mid", text=title,
                              align="left", text_rect=(x + 6.0, y, w - 12.0, 13.0)),
    }


def _badge(rect, n):
    x, y = rect[0], rect[1]
    return {"text": (str(n), str(n)), "rect": (x + 2.0, y + 2.0, 10.0, 11.0), "alpha": 1.0}


def _al_rects(page, aspects, height, gap=4.0):
    px, py, pw, ph = page
    fit_height = (pw - 2 * PAGE_MARGIN - gap * (len(aspects) - 1)) / sum(aspects)
    height = min(height, fit_height)
    widths = [height * a for a in aspects]
    total = sum(widths) + gap * (len(widths) - 1)
    x = px + (pw - total) / 2.0
    y = py + (ph - height) / 2.0
    out = []
    for w in widths:
        out.append((x, y, w, height))
        x += w + gap
    return out


def _inset_ids():
    return ["inset_b", "inset_p", "h1", "h2", "h3", "h4"]


def _inset_els(rect, handles=False):
    x, y, w, h = rect
    els = {
        "inset_b": _box(rect, fill="base", line="accent", width=1.2),
        "inset_p": _pic((x + 2.0, y + 2.0, w - 4.0, h - 4.0), "photo"),
    }
    if handles:
        for hid, (hx, hy) in (("h1", (x, y)), ("h2", (x + w, y)), ("h3", (x, y + h)), ("h4", (x + w, y + h))):
            els[hid] = _box((hx - 2.0, hy - 2.0, 4.0, 4.0), fill="accent")
    return els


# ----------------------------------------------------------------------
# The remaining topic demos
# ----------------------------------------------------------------------

def _explorer_ids():
    return ["fx_bg", "fx_bar"] + ["fx_f%d" % i for i in range(3)] + ["fx_n%d" % i for i in range(3)]


def _explorer(alpha):
    x, y = 2.0, CANVAS_Y + 18.0
    els = {
        "fx_bg": _box((x, y, 58.0, 76.0), fill="base", line="mid", radius=2.0, alpha=alpha),
        "fx_bar": _box((x, y, 58.0, 11.0), fill="chrome", line="mid", text=("Files", "文件"),
                       align="left", text_rect=(x + 4.0, y, 52.0, 11.0), alpha=alpha),
    }
    for i, name in enumerate(("a.png", "b.png", "c.png")):
        fy = y + 16.0 + i * 19.0
        els["fx_f%d" % i] = _el("file", (6.0, fy, 12.0, 15.0), fill="base", line="ink", alpha=alpha)
        els["fx_n%d" % i] = _txt((21.0, fy + 2.0, 34.0, 11.0), (name, name), role="muted",
                                 size=TEXT_SIZE, align="left", alpha=alpha)
    return els


def _explorer_hide():
    return [morph(250, elements={key: {"alpha": 0.0} for key in _explorer_ids()}),
            set(elements=_none(_explorer_ids()))]


def _build_add_images():
    page = _fit_page(1.5, STAGE_W)
    rows = [["a0", "a1", "a2"], ["b0", "b1", "b2"]]
    panels = _panels_for(page, rows, {"a0": "chart", "b1": "micro"})
    grid = _rows(page, [3, 3])
    ids = ["a0", "a1", "a2", "b0", "b1", "b2"]
    targets = {pid: panels[pid]["rect"] for pid in ids}
    grid_new = {"g%d" % i: _row_panel(grid[i // 3][i % 3], "r%d" % (i // 3), kind)
                for i, kind in enumerate(["chart", "micro", "photo", "bars", "photo", "chart"])}
    fill_order = [("a2", "bars"), ("b0", "micro"), ("b2", "photo")]
    beats = [
        step(1), wait(300),
        morph(250, elements=_explorer(1.0)), wait(150),
        move("elem:fx_f0", 500),
        drag("elem:fx_f0", "panel:a1", ms=900, ghost="file"),
        *_explorer_hide(),
        set(panels={"a1": {"kind": "photo"}}), wait(400),
        step(2),
        move("menu:menu_file", 600), click(), open_menu(("menu_file",)), wait(200),
        move("item:menu_file/action_import", 600), click(), wait(150),
        morph(300, panels={pid: {"label": _badge(targets[pid], n)}
                           for n, (pid, _k) in enumerate(fill_order, 1)}),
        wait(400),
    ]
    for n, (pid, kind) in enumerate(fill_order, 1):
        beats += [set(panels={pid: {"kind": kind, "label": None}}), wait(260)]
    beats += [
        wait(300),
        step(3),
        move("menu:menu_file", 600), click(), open_menu(("menu_file",)), wait(200),
        move("item:menu_file/action_open_grid", 600), click(), wait(150),
        morph(800, panels={**_none(ids), **grid_new}),
        wait(500),
    ]
    return Demo("add_images", _scene(page, panels, order=(), fields={}, elements=_explorer(0.0)),
                tuple(beats))


def _build_swap_replace():
    page = _fit_page(1.5, STAGE_W)
    panels = _panels_for(page, [["a0", "a1"], ["b0", "b1"]],
                         {"a0": "chart", "a1": "bars", "b0": "micro", "b1": "photo"})
    a0, b0 = panels["a0"]["rect"], panels["b0"]["rect"]
    beats = [
        step(1), wait(300),
        morph(250, elements=_explorer(1.0)), wait(150),
        move("elem:fx_f0", 500),
        drag("elem:fx_f0", "panel:a0", ms=900, ghost="file"),
        *_explorer_hide(),
        morph(500, elements={"xf": _pic(_pic_rect(panels["a0"]), "photo")}),
        wait(200),
        set(panels={"a0": {"kind": "photo"}}, elements={"xf": None}), wait(400),
        step(2),
        move("panel:a0", 600),
        drag("panel:a0", "panel:b0", ms=1000, ghost="chart"), wait(300),
        step(3),
        hold_drag(1200, ghost="chart"),
        morph(600, panels={"a0": {"rect": b0, "row": panels["b0"]["row"]},
                           "b0": {"rect": a0, "row": panels["a0"]["row"]}}),
        wait(400),
    ]
    return Demo("swap_replace", _scene(page, panels, elements=_explorer(0.0)), tuple(beats))


def _build_auto_layout():
    aspects = (1.6, 0.9, 1.2)
    height = 40.0
    page = _fit_page(1.6, STAGE_W)
    ids = ["p0", "p1", "p2"]
    kinds = {"p0": "photo", "p1": "chart", "p2": "micro"}
    orig = _rows(page, [3])[0]
    panels = {pid: _row_panel(orig[i], "r0", kinds[pid], aspect=aspects[i]) for i, pid in enumerate(ids)}
    fitted = {pid: rect for pid, rect in zip(ids, _al_rects(page, aspects, height))}
    page_i = _fit_page(1.6, INSPECTOR_X)
    fitted_i = dict(zip(ids, _al_rects(page_i, aspects, height)))
    page_n = _fit_page(1.6 * 180.0 / 210.0, INSPECTOR_X)
    fitted_n = dict(zip(ids, _al_rects(page_n, aspects, height)))
    orig_i = dict(zip(ids, _rows(page_i, [3])[0]))
    inner_i, inner_n = page_i[2] - 2 * PAGE_MARGIN, page_n[2] - 2 * PAGE_MARGIN
    scale_x = inner_n / inner_i
    squeezed = {pid: {"rect": (page_n[0] + PAGE_MARGIN + (r[0] - page_i[0] - PAGE_MARGIN) * scale_x, r[1],
                              r[2] * scale_x, r[3])} for pid, r in fitted_i.items()}
    beats = [
        step(1), wait(300),
        keys("Ctrl", "Shift", "A", ms=800),
        morph(700, panels={pid: {"rect": r} for pid, r in fitted.items()}), wait(400),
        step(2),
        keys("Ctrl", "Z", ms=700),
        morph(600, panels={pid: {"rect": r} for pid, r in dict(zip(ids, orig)).items()}), wait(300),
        move("tool:auto_layout", 600), click(),
        morph(700, panels={pid: {"rect": r} for pid, r in fitted.items()}), wait(400),
        step(3),
        move("blank", 500), click(),
        morph(450, inspector_x=INSPECTOR_X, page=page_i,
              panels={pid: {"rect": r} for pid, r in fitted_i.items()}), wait(250),
        move("field:page_w", 500), click(), type_text("page_w", "180", 120), wait(200),
        morph(600, page=page_n, panels=squeezed), wait(300),
        move("tool:auto_layout", 600), click(),
        morph(600, panels={pid: {"rect": r} for pid, r in fitted_n.items()}), wait(400),
    ]
    scene = _scene(page, panels, tools=("auto_layout",), fields={"page_w": _lit("210")},
                   order=("page_w",))
    return Demo("auto_layout", scene, tuple(beats))


def _build_page_setup():
    page = _fit_page(1.4, STAGE_W)
    page_i = _fit_page(1.4, INSPECTOR_X)
    kinds = {"p0": "chart", "p1": "micro", "p2": "photo", "p3": "bars"}
    panels = {pid: _row_panel(rect, "r0" if pid in ("p0", "p1") else "r1", kinds[pid])
              for pid, rect in _grid2x2(page, 3.0).items()}
    page_w = _fit_page(1.6, INSPECTOR_X)
    margin = 20.0 / 240.0 * page_w[2]
    page_m = page_w
    page_h2 = (page_w[0], page_w[1] + page_w[3] * 0.06, page_w[2], page_w[3] * 0.88)
    margin_h = 20.0 / 240.0 * page_h2[2]
    beats = [
        step(1), wait(300),
        move("blank", 600), click(),
        morph(450, inspector_x=INSPECTOR_X, page=page_i,
              panels={pid: {"rect": r} for pid, r in _quad(_inner(page_i, 8.0), 3.0).items()}),
        wait(300),
        step(2),
        move("field:page_w", 500), click(), type_text("page_w", "240", 110), wait(200),
        morph(600, page=page_w,
              panels={pid: {"rect": r} for pid, r in _quad(_inner(page_w, 8.0), 3.0).items()}),
        wait(150),
        move("field:mleft", 500), click(), type_text("mleft", "20", 120), wait(200),
        morph(600, guides=True, margin=margin,
              panels={pid: {"rect": r} for pid, r in _quad(
                  (page_m[0] + margin, page_m[1] + margin, page_m[2] - 2 * margin, page_m[3] - 2 * margin),
                  3.0).items()}),
        wait(400),
        step(3),
        move("field:gap", 500), click(), type_text("gap", "6", 120), wait(200),
        morph(700, page=page_h2, margin=margin_h,
              panels={pid: {"rect": r} for pid, r in _quad(
                  (page_h2[0] + margin_h, page_h2[1] + margin_h,
                   page_h2[2] - 2 * margin_h, page_h2[3] - 2 * margin_h), 9.0).items()}),
        wait(400),
    ]
    fields = {"page_w": _lit("210"), "page_h": _lit("150"), "mleft": _lit("10"), "gap": _lit("2")}
    scene = _scene(page, panels, fields=fields, order=("page_w", "page_h", "mleft", "gap"))
    return Demo("page_setup", scene, tuple(beats))


def _build_crop_fit():
    page = _fit_page(1.4, STAGE_W)
    panels = {"c0": _row_panel(_inner(page, 8.0), "r0", "photo", aspect=0.6, fit="fit", rot=0)}
    page_i = _fit_page(1.4, INSPECTOR_X)
    c0_i = _inner(page_i, 8.0)
    fitted = _picture_geometry(dict(panels["c0"], rect=c0_i))[0]
    corner = (fitted[0] + fitted[2], fitted[1] + fitted[3])
    crop_box = (0.1, 0.36, 0.9, 0.98)   # picture fractions: left, top, right, bottom (hill peaks)
    dst = (fitted[0] + crop_box[2] * fitted[2], fitted[1] + crop_box[3] * fitted[3])
    beats = [
        step(1), wait(300),
        move("panel:c0", 500), click(),
        morph(450, inspector_x=INSPECTOR_X, page=page_i, panels={"c0": {"rect": c0_i, "selected": True}}),
        wait(250),
        *pick("fit", 1),
        morph(500, panels={"c0": {"fit": "fill"}}), wait(400),
        *pick("fit", 0),
        morph(500, panels={"c0": {"fit": "fit"}}), wait(400),
        step(2),
        move("panel:c0", 500), click(right=True), context_menu("ctx_img"), wait(200),
        move("item:ctx_img/ctx_crop_image", 500), click(),
        morph(300, panels={"c0": {"fit": "crop_edit", "selected": True, "crop_box": (0.0, 0.0, 1.0, 1.0)}}),
        wait(150),
        move(corner, 400),
        drag(corner, dst, ms=900, live={"panels": {"c0": {"crop_box": crop_box}}}), wait(150),
        keys("Enter", ms=700),
        set(panels={"c0": {"fit": "crop", "selected": False}}), wait(300),
        step(3),
        *pick("rot", 1),
        morph(600, panels={"c0": {"rot": 90}}), wait(400),
    ]
    fields = {"fit": 0, "rot": 0}
    return Demo("crop_fit", _scene(page, panels, fields=fields, order=("fit", "rot"),
                                   title="grp_cell"), tuple(beats))


def _build_insets():
    page = _fit_page(1.5, STAGE_W)
    rows = _rows(page, [2])[0]
    panels = {"p0": _row_panel(rows[0], "r0", "chart"), "p1": _row_panel(rows[1], "r0", "photo")}
    x, y, w, h = rows[0]
    zone = (x + w * 0.55, y + 3.0, w * 0.42, h * 0.42)
    inset = (zone[0] + 1.0, zone[1] + 1.0, zone[2] - 2.0, zone[3] - 2.0)
    center = (zone[0] + zone[2] / 2.0, zone[1] + zone[3] / 2.0)
    elements = {"zone": _box(zone, line="accent", dashed=True, width=1.5, alpha=0.0)}
    elements.update(_explorer(0.0))
    moved = (inset[0] - 24.0, inset[1] + 12.0, inset[2], inset[3])
    moved_c = (moved[0] + moved[2] / 2.0, moved[1] + moved[3] / 2.0)
    resized = (moved[0], moved[1], moved[2] - 16.0, moved[3] - 12.0)
    beats = [
        step(1), wait(300),
        morph(250, elements=_explorer(1.0)), wait(150),
        move("elem:fx_f0", 500),
        drag("elem:fx_f0", center, ms=900, ghost="file"),
        *_explorer_hide(),
        morph(200, elements={"zone": {"alpha": 1.0}}), wait(150),
        morph(400, elements={**_none(["zone"]), **_inset_els(inset)}), wait(400),
        step(2),
        move("elem:inset_b", 600), click(),
        morph(300, elements=_inset_els(inset, handles=True)), wait(200),
        drag("elem:inset_b", moved_c, ms=800, live={"elements": _inset_els(moved, handles=True)}),
        wait(150),
        move("elem:h4", 400),
        drag("elem:h4", (resized[0] + resized[2], resized[1] + resized[3]), ms=800,
             live={"elements": _inset_els(resized, handles=True)}),
        wait(300),
        step(3),
        move("elem:inset_b", 500), click(right=True), context_menu("pip_ctx"), wait(200),
        move("item:pip_ctx/pip_ctx_remove", 500), click(),
        morph(450, elements=_none(_inset_ids())), wait(400),
    ]
    return Demo("insets", _scene(page, panels, elements=elements), tuple(beats))


def _build_shared_titles():
    page = _fit_page(1.5, STAGE_W)
    panels = _panels_for(page, [["a0", "a1", "a2"]], {"a0": "chart", "a1": "micro", "a2": "photo"})
    r0, r1 = panels["a0"]["rect"], panels["a1"]["rect"]
    band = (r0[0], r0[1], r1[0] + r1[2] - r0[0], 13.0)
    shifted = {"a0": {"rect": (r0[0], r0[1] + 15.0, r0[2], r0[3] - 15.0)},
               "a1": {"rect": (r1[0], r1[1] + 15.0, r1[2], r1[3] - 15.0)}}
    band_moved = (band[0] + 18.0, band[1], band[2], band[3])
    beats = [
        step(1), wait(300),
        move("panel:a0", 500), click(), set(panels={"a0": {"selected": True}}), wait(150),
        hold_keys("Ctrl", ms=250),
        move("panel:a1", 500), click(), set(panels={"a1": {"selected": True}}), wait(150),
        release_keys(), wait(250),
        step(2),
        move("menu:menu_edit", 500), click(), open_menu(("menu_edit",)), wait(200),
        hover_item(("menu_edit", "menu_group_label")), wait(200),
        move("item:menu_group_label/action_group_label_top", 500), click(),
        morph(600, panels=shifted, elements={"band": _box(band, line="accent", dashed=True, width=1.0)}),
        wait(400),
        step(3),
        double_click("elem:band"), type_text("elem:band", "Control", 110), wait(250),
        move("elem:band", 400),
        drag("elem:band", (band_moved[0] + band_moved[2] / 2.0, band_moved[1] + band_moved[3] / 2.0),
             ms=700, live={"elements": {"band": {"rect": band_moved}}}),
        wait(400),
    ]
    return Demo("shared_titles", _scene(page, panels), tuple(beats))


def _sbar(m, pos, text):
    x, y, w, h = m
    x1, x2 = (x + w - 44.0, x + w - 8.0) if pos == "right" else (x + 8.0, x + 44.0)
    yl = y + h - 9.0
    return {"sb_line": _line(x1, yl, x2, yl, line="ink", width=2.0),
            "sb_txt": _txt((x1 - 2.0, yl - 11.0, x2 - x1 + 4.0, 9.0), (text, text))}


def _build_scale_bar():
    page = _fit_page(1.5, STAGE_W)
    rects = _rows(page, [2])[0]
    panels = {"m0": _row_panel(rects[0], "r0", "micro"), "m1": _row_panel(rects[1], "r0", "chart")}
    page_i = _fit_page(1.5, INSPECTOR_X)
    rects_i = _rows(page_i, [2])[0]
    m0_i = rects_i[0]
    beats = [
        step(1), wait(300),
        move("panel:m0", 500), click(right=True), context_menu("ctx_img"), wait(200),
        move("item:ctx_img/ctx_enable_scale_bar", 500), click(),
        morph(500, elements=_sbar(rects[0], "right", "20 \u00b5m")), wait(400),
        step(2),
        move("panel:m0", 500), click(),
        morph(450, inspector_x=INSPECTOR_X, page=page_i,
              panels={"m0": {"rect": rects_i[0]}, "m1": {"rect": rects_i[1]}},
              elements=_sbar(m0_i, "right", "20 \u00b5m")),
        wait(250),
        move("field:calib", 500), click(), type_text("calib", "0.25", 110), wait(200),
        morph(300, elements={"sb_txt": {"text": ("50 \u00b5m", "50 \u00b5m")}}), wait(400),
        step(3),
        *pick("sbpos", 0),
        morph(500, elements=_sbar(m0_i, "left", "50 \u00b5m")), wait(400),
    ]
    fields = {"calib": _lit("20"), "sbpos": 2}
    return Demo("scale_bar", _scene(page, panels, fields=fields, order=("calib", "sbpos"),
                                    title="grp_scale_bar"), tuple(beats))


_PALETTE_TOOLS = ("select", "dot", "line", "arrow", "rect", "ellipse", "polygon", "polyline")
_PALETTE_X0 = 99.0


def _palette_els(alpha, active="select"):
    x0, y0 = _PALETTE_X0, CANVAS_Y + 6.0
    els = {"pal_bg": _box((x0, y0, 202.0, 22.0), fill="base", line="mid", radius=4.0, alpha=alpha)}
    for index, tool in enumerate(_PALETTE_TOOLS):
        tx, ty = x0 + 4.0 + index * 17.0, y0 + 3.0
        on = tool == active
        els["pal_t_" + tool] = _box((tx, ty, 16.0, 16.0), fill="accent" if on else "", radius=3.0,
                                    alpha=alpha * 0.16 if on else alpha)
        els["pal_i_" + tool] = _el("icon", (tx + 2.0, ty + 2.0, 12.0, 12.0), fill="ink",
                                   name="mark_" + tool, alpha=alpha)
    els["pal_sep"] = _line(x0 + 143.0, y0 + 4.0, x0 + 143.0, y0 + 18.0, line="mid", alpha=alpha)
    els["pal_lock"] = _el("icon", (x0 + 149.0, y0 + 5.0, 12.0, 12.0), fill="ink",
                          name="lock_closed", alpha=alpha)
    els["pal_done"] = _txt((x0 + 166.0, y0 + 3.0, 32.0, 16.0), "draw_palette_done", role="accent",
                           size=TEXT_SIZE, align="center", alpha=alpha)
    return els


def _marks_ui(alpha=1.0, active="select"):
    els = {"status": _box((0.0, 148.0, STAGE_W, 12.0), fill="surface", line="mid",
                          text=("Draw mode", "绘制模式"), align="left",
                          text_rect=(6.0, 148.0, 120.0, 12.0), alpha=alpha)}
    els.update(_palette_els(alpha, active))
    return els


def _build_marks():
    page = _fit_page(1.5, STAGE_W)
    rows = _rows(page, [2])[0]
    panels = {"p0": _row_panel(rows[0], "r0", "chart"), "p1": _row_panel(rows[1], "r0", "photo")}
    x, y, w, h = rows[0]
    a_start = (x + 14.0, y + h * 0.75)
    a_end = (x + 70.0, y + h * 0.25)
    r_start = (x + 20.0, y + h * 0.1)
    r_end = (x + 90.0, y + h * 0.5)
    x2, y2, _w2, h2 = rows[1]
    b_start = (x2 + 14.0, y2 + h2 * 0.75)
    b_end = (x2 + 70.0, y2 + h2 * 0.25)
    elements = dict(_marks_ui(0.0), **{
        "arrow1": _line(a_start[0], a_start[1], a_start[0], a_start[1], line="accent", arrow=True, alpha=0.0),
        "arrow2": _line(b_start[0], b_start[1], b_start[0], b_start[1], line="accent", arrow=True, alpha=0.0),
        "rect1": _box((r_start[0], r_start[1], 0.0, 0.0), line="accent", width=1.5, alpha=0.0),
    })
    ui_ids = list(_marks_ui(0.0).keys())
    beats = [
        step(1), wait(300),
        move("tool:draw", 500), click(),
        morph(400, elements=_marks_ui(1.0, "select")), wait(400),
        step(2),
        move("elem:pal_t_arrow", 450), click(),
        set(draw_tool="arrow", elements=_marks_ui(1.0, "arrow")),
        move(a_start, 450),
        drag(a_start, a_end, ms=700,
             live={"elements": {"arrow1": {"rect": (a_start[0], a_start[1], a_end[0], a_end[1]), "alpha": 1.0}}}),
        wait(200),
        move(b_start, 450),
        drag(b_start, b_end, ms=700,
             live={"elements": {"arrow2": {"rect": (b_start[0], b_start[1], b_end[0], b_end[1]), "alpha": 1.0}}}),
        wait(250),
        move("elem:pal_t_rect", 450), click(),
        set(draw_tool="rect", elements=_marks_ui(1.0, "rect")),
        move(r_start, 450),
        drag(r_start, r_end, ms=700,
             live={"elements": {"rect1": {"rect": (r_start[0], r_start[1],
                                                   r_end[0] - r_start[0], r_end[1] - r_start[1]),
                                          "alpha": 1.0}}}),
        wait(250),
        step(3),
        keys("Esc", ms=700),
        set(draw_tool=None, elements=_marks_ui(1.0, "select")), wait(300),
        move("elem:pal_done", 500), click(),
        morph(500, elements=_marks_ui(0.0, "select")),
        set(elements=_none(ui_ids + list(_palette_els(0.0).keys()))),
        wait(400),
    ]
    return Demo("marks", _scene(page, panels, tools=("save", "draw"), elements=elements), tuple(beats))


def _build_text_sizes():
    page = _fit_page(1.5, STAGE_W)
    c0 = _inner(page, 8.0)
    panels = {"c0": _row_panel(c0, "r0", "chart")}
    dlg = {}
    dlg.update(_dialog("dlg", (64.0, 30.0, 272.0, 124.0), "svgtxt_inspector_title"))
    dlg["dlg_pic"] = _pic((74.0, 52.0, 126.0, 96.0), "chart")
    dlg["tb1"] = _txt((210.0, 56.0, 118.0, 14.0), ("X axis label", "X 轴标签"), size=9.0, align="left")
    dlg["tb2"] = _txt((210.0, 74.0, 118.0, 14.0), ("Tick 1", "刻度 1"), size=10.0, align="left")
    dlg["tb3"] = _txt((210.0, 92.0, 118.0, 14.0), ("Legend", "图例"), size=12.0, align="left")
    dlg["chip_add"] = _box((210.0, 116.0, 30.0, 14.0), fill="accent", radius=3.0, text=("+", "+"),
                           role="base", size=9.0)
    beats = [
        step(1), wait(300),
        move("panel:c0", 500), click(right=True), context_menu("ctx_plot"), wait(200),
        move("item:ctx_plot/ctx_svg_text_inspector", 500), click(),
        morph(500, elements=dlg), wait(400),
        step(2),
        move("elem:tb1", 500), click(), set(elements={"tb1": {"fill": "accent", "line": "accent", "role": "base"}}),
        move("elem:tb3", 500), click(), set(elements={"tb3": {"fill": "accent", "line": "accent", "role": "base"}}),
        wait(200),
        move("elem:chip_add", 500), click(),
        morph(300, elements={"chip_add": None,
                             "chip": _box((210.0, 116.0, 40.0, 14.0), fill="accent", radius=3.0,
                                          text=("8 pt", "8 pt"), role="base", size=9.0)}),
        wait(400),
        step(3),
        move("elem:chip", 500), click(),
        morph(450, elements={"chip": {"text": ("10 pt", "10 pt")},
                             "tb1": {"rect": (210.0, 56.0, 118.0, 16.0), "size": 11.0},
                             "tb3": {"rect": (210.0, 92.0, 118.0, 16.0), "size": 11.0}}),
        wait(400),
    ]
    return Demo("text_sizes", _scene(page, panels), tuple(beats))


def _build_align_plots():
    page = _fit_page(1.4, STAGE_W)
    px, py, pw, ph = page
    rects = _rows(page, [3])[0]
    panels = {"p%d" % i: _row_panel(r, "r0", "chart") for i, r in enumerate(rects)}
    # Each chart's plot frame: a different top offset and height inside its panel.
    offsets = ((6.0, 56.0), (14.0, 46.0), (3.0, 62.0))
    baseline_y = rects[0][1] + rects[0][3] - 10.0
    elements = {}
    aligned = {}
    for i, (x, y, w, h) in enumerate(rects):
        off, fh = offsets[i]
        elements["pf%d" % i] = _box((x + 8.0, y + off, w - 16.0, fh), line="ink", width=1.0)
        aligned["pf%d" % i] = {"rect": (x + 8.0, baseline_y - fh, w - 16.0, fh)}
    dlg = _dialog("dlg", (48.0, 28.0, 304.0, 124.0), "action_align_plots")
    cards = [(60.0 + i * 96.0, 48.0) for i in range(3)]
    for i, (cx, cy) in enumerate(cards):
        dlg["card%d" % i] = _box((cx, cy, 88.0, 84.0), line="mid", radius=2.0)
        dlg["cpic%d" % i] = _pic((cx + 6.0, cy + 6.0, 76.0, 48.0), "chart")
        dlg["chk%d" % i] = _box((cx + 6.0, cy + 60.0, 10.0, 10.0), line="mid", radius=1.0)
        dlg["star%d" % i] = _el("star", (cx + 70.0, cy + 60.0, 10.0, 10.0), fill="accent", alpha=0.0)
    dlg["btn_apply"] = _box((300.0, 132.0, 44.0, 14.0), fill="accent", radius=3.0,
                            text="plot_apply", role="base", size=9.0)
    dlg_ids = list(dlg.keys())
    beats = [
        step(1), wait(300),
        move("menu:menu_layout", 500), click(), open_menu(("menu_layout",)), wait(200),
        move("item:menu_layout/action_align_plots", 600), click(),
        morph(500, elements=dlg), wait(400),
        step(2),
    ]
    for i, (cx, cy) in enumerate(cards):
        sug = _box((cx + 14.0, cy + 14.0, 60.0, 36.0), line="accent", dashed=True, width=1.2)
        tick = _el("check", (cx + 6.0, cy + 60.0, 10.0, 10.0), fill="accent")
        beats += [
            move("elem:chk%d" % i, 400), click(),
            morph(250, elements={"tick%d" % i: tick, "sug%d" % i: sug}),
            keys("Enter", ms=450),
            morph(250, elements={"sug%d" % i: {"dashed": False}}), wait(150),
        ]
    beats += [
        step(3),
        move("elem:star0", 400), click(),
        morph(250, elements={"star0": {"alpha": 1.0}}), wait(200),
        move("elem:btn_apply", 450), click(),
        morph(400, elements=_none(dlg_ids + ["tick%d" % i for i in range(3)]
                                  + ["sug%d" % i for i in range(3)])),
        morph(700, elements=dict(aligned, **{"baseline": _line(
            px + 8.0, baseline_y, px + pw - 8.0, baseline_y, line="accent", dashed=True)})),
        wait(400),
    ]
    scene = _scene(page, panels, elements=elements)
    return Demo("align_plots", scene, tuple(beats))


def _build_same_size():
    page = _fit_page(1.5, STAGE_W)
    small = _frac(page, (0.05, 0.2, 0.22, 0.3))
    big = _frac(page, (0.4, 0.12, 0.42, 0.52))
    panels = {"s0": _row_panel(small, "r0", "chart"), "s1": _row_panel(big, "r0", "micro")}
    target = (0.3, 0.4)

    def resized(fr_pos, width_frac, height_frac):
        x, y = _frac(page, fr_pos)[:2]
        return (x, y, width_frac * page[2], height_frac * page[3])

    same_s0 = resized((0.05, 0.2, 0.22, 0.3), target[0], target[1])
    same_s1 = resized((0.4, 0.12, 0.42, 0.52), target[0], target[1])
    wide = (0.46, 0.4)
    page_i = _fit_page(1.5, INSPECTOR_X)
    s0_i = _frac(page_i, (0.05, 0.2, target[0], target[1]))
    s1_i = _frac(page_i, (0.4, 0.12, target[0], target[1]))
    wide_s0 = _frac(page_i, (0.05, 0.2, wide[0], wide[1]))
    wide_s1 = _frac(page_i, (0.4, 0.12, wide[0], wide[1]))
    beats = [
        step(1), wait(300),
        move("panel:s0", 500), click(), set(panels={"s0": {"selected": True}}), wait(150),
        hold_keys("Ctrl", ms=250),
        move("panel:s1", 500), click(), set(panels={"s1": {"selected": True}}), wait(150),
        release_keys(), wait(250),
        step(2),
        move("panel:s1", 500), click(right=True), context_menu("ctx_img"), wait(200),
        move("item:ctx_img/ctx_create_size_group", 500), click(),
        morph(700, panels={"s0": {"rect": same_s0}, "s1": {"rect": same_s1}}), wait(300),
        step(3),
        morph(450, inspector_x=INSPECTOR_X, page=page_i,
              panels={"s0": {"rect": s0_i}, "s1": {"rect": s1_i}}), wait(250),
        move("field:sgw", 500), click(), type_text("sgw", "120", 120), wait(200),
        morph(600, panels={"s0": {"rect": wide_s0}, "s1": {"rect": wide_s1}}), wait(400),
    ]
    fields = {"sgw": _lit("0")}
    return Demo("same_size", _scene(page, panels, fields=fields, order=("sgw",),
                                    title="grp_cell"), tuple(beats))


def _build_freeform():
    page = _fit_page(1.5, STAGE_W)
    px, py, pw, ph = page
    grid_fr = {"p0": (0.04, 0.1, 0.46, 0.4), "p1": (0.52, 0.1, 0.46, 0.4),
               "p2": (0.04, 0.52, 0.46, 0.4), "p3": (0.52, 0.52, 0.46, 0.4)}
    kinds = {"p0": "chart", "p1": "micro", "p2": "photo", "p3": "bars"}
    panels = {pid: _row_panel(_frac(page, fr), "r0", kinds[pid]) for pid, fr in grid_fr.items()}
    panels["p0"]["z"] = 1
    elements = {
        "grid_v": _line(px + pw / 2.0, py, px + pw / 2.0, py + ph, line="muted", dashed=True),
        "grid_h": _line(px, py + ph / 2.0, px + pw, py + ph / 2.0, line="muted", dashed=True),
    }
    overlap_fr = (0.2, 0.3, 0.46, 0.4)
    over = _frac(page, overlap_fr)
    over_c = (over[0] + over[2] / 2.0, over[1] + over[3] / 2.0)
    page_i = _fit_page(1.5, INSPECTOR_X)
    over_i = _frac(page_i, overlap_fr)
    wide_i = _frac(page_i, (0.2, 0.3, 0.62, 0.4))
    beats = [
        step(1), wait(300),
        move("menu:menu_layout", 500), click(), open_menu(("menu_layout",)), wait(200),
        move("item:menu_layout/action_bake", 500), click(),
        morph(500, elements=_none(["grid_v", "grid_h"])), wait(200),
        move("panel:p0", 500), click(),
        drag("panel:p0", over_c, ms=900, live={"panels": {"p0": {"rect": over}}}),
        wait(300),
        step(2),
        move("panel:p0", 400), click(),
        morph(450, inspector_x=INSPECTOR_X, page=page_i,
              panels={pid: {"rect": _frac(page_i, fr)} for pid, fr in grid_fr.items()}
              | {"p0": {"rect": over_i}}),
        wait(250),
        move("field:freew", 500), click(), type_text("freew", "70", 120), wait(200),
        morph(500, panels={"p0": {"rect": wide_i}}), wait(300),
        step(3),
        move("menu:menu_layout", 500), click(), open_menu(("menu_layout",)), wait(200),
        move("item:menu_layout/action_bring_front", 500), click(),
        set(panels={"p1": {"z": 2}}), wait(400),
    ]
    fields = {"freex": _lit("12"), "freey": _lit("8"), "freew": _lit("50"), "freeh": _lit("40")}
    order = ("freex", "freey", "freew", "freeh")
    scene = _scene(page, panels, elements=elements, fields=fields, order=order, title="sec_freeform")
    scene["plus"] = False
    return Demo("freeform", scene, tuple(beats))


def _build_export():
    page = _fit_page(1.5, STAGE_W)
    px, py, pw, ph = page
    quads = _grid2x2(page, 4.0)
    kinds = {"p0": "chart", "p1": "micro", "p2": "photo", "p3": "bars"}
    panels = {pid: _row_panel(rect, "r0" if pid in ("p0", "p1") else "r1", kinds[pid])
              for pid, rect in quads.items()}
    # The viewer shows the whole page at a slightly smaller scale, centred in its body.
    k = 0.8
    body = (100.0, 56.0, 200.0, 94.0)
    mx = body[0] + (body[2] - pw * k) / 2.0
    my = body[1] + (body[3] - ph * k) / 2.0

    def mini(rect):
        x, y, w, h = rect
        return (mx + (x - px) * k, my + (y - py) * k, w * k, h * k)

    viewer = _dialog("viewer", (96.0, 38.0, 208.0, 116.0), ("figure.pdf", "figure.pdf"))
    for pid, kind in kinds.items():
        viewer["vp_" + pid] = _pic(mini(quads[pid]), kind)
        viewer["vb_" + pid] = _box(mini(quads[pid]), line="mid")
    beats = [
        step(1), wait(300),
        move("panel:p0", 400), click(), set(panels={"p0": {"selected": True}}), wait(150),
        move("tool:export", 500), click(), open_menu(("toolbar_export",)), wait(200),
        move("item:toolbar_export/action_export_pdf", 500), click(),
        set(elements={"doc": _el("file", (44.0, 40.0, 16.0, 20.0), fill="base", line="ink"),
                      "doc_t": _txt((30.0, 62.0, 60.0, 10.0), ("figure.pdf", "figure.pdf"))}),
        morph(800, elements={"doc": {"rect": (360.0, 60.0, 20.0, 26.0)},
                             "doc_t": {"rect": (330.0, 88.0, 60.0, 10.0)}}),
        wait(400),
        step(2),
        move("elem:doc", 500), double_click("elem:doc"),
        morph(600, elements=dict(viewer, **_none(["doc", "doc_t"]))), wait(600),
        step(3),
        keys("Ctrl", "Shift", "P", ms=800),
        morph(500, plus=False, panels={pid: {"selected": False} for pid in panels},
              elements=dict(_none(list(viewer.keys())), **{"pv_bar": _box(
                  (0.0, 148.0, STAGE_W, 12.0), fill="surface", line="mid",
                  text="action_preview_mode", align="left", text_rect=(6.0, 148.0, 120.0, 12.0))})),
        wait(400),
    ]
    return Demo("export", _scene(page, panels, tools=("save", "auto_layout", "export")), tuple(beats))


def _build_save_share():
    page = _fit_page(1.5, STAGE_W)
    panels = _panels_for(page, [["a0", "a1"], ["b0", "b1"]],
                         {"a0": "chart", "a1": "micro", "b0": "bars", "b1": "photo"})
    rects = {pid: panels[pid]["rect"] for pid in panels}
    kinds = {pid: panels[pid]["kind"] for pid in panels}
    title = (page[0], CANVAS_Y + 1.0, page[2], 12.0)
    title_hl = (title[0] + 1.0, title[1] + 1.0, title[2] - 2.0, title[3] - 2.0)
    pkg = (340.0, 96.0, 34.0, 26.0)
    folder = (340.0, 56.0, 34.0, 26.0)
    elements = {"titlebar": _txt(title, ("figure*", "figure*"), size=9.0)}
    copies_pk = {"pk%d" % i: _pic(rects[pid], kinds[pid]) for i, pid in enumerate(panels)}
    copies_fc = {"fc%d" % i: _pic(rects[pid], kinds[pid]) for i, pid in enumerate(panels)}
    small_pk = {"pk%d" % i: {"rect": (pkg[0] + 8, pkg[1] + 8, 18.0, 12.0), "alpha": 0.0}
                for i in range(len(panels))}
    small_fc = {"fc%d" % i: {"rect": (folder[0] + 8, folder[1] + 8, 18.0, 12.0), "alpha": 0.0}
                for i in range(len(panels))}
    beats = [
        step(1), wait(300),
        morph(250, elements={"title_hl": _box(title_hl, line="accent", radius=2.0)}), wait(300),
        keys("Ctrl", "S", ms=800),
        set(elements={"titlebar": {"text": ("figure", "figure")}, "title_hl": None}),
        toast(("Saved", "已保存"), ms=900), wait(300),
        step(2),
        move("menu:menu_file", 500), click(), open_menu(("menu_file",)), wait(200),
        move("item:menu_file/action_convert_to_bundle", 500), click(),
        set(elements=copies_pk),
        morph(800, elements=dict(small_pk, **{"pkg": _el("package", pkg),
                                              "pkg_t": _txt((330.0, 124.0, 68.0, 10.0),
                                                            ("figure.figpack", "figure.figpack"))})),
        wait(400),
        step(3),
        move("menu:menu_file", 500), click(), open_menu(("menu_file",)), wait(200),
        move("item:menu_file/action_export_sources", 500), click(),
        set(elements=copies_fc),
        morph(800, elements=dict(small_fc, **{"folder": _el("folder", folder),
                                              "folder_t": _txt((330.0, 84.0, 68.0, 10.0),
                                                               ("Sources", "源图片"))})),
        wait(400),
    ]
    return Demo("save_share", _scene(page, panels, elements=elements), tuple(beats))


def _build_troubleshoot():
    page = _fit_page(1.5, STAGE_W)
    rows = _rows(page, [2])[0]
    panels = {"p0": _row_panel(rows[0], "r0", "missing", aspect=1.5, fit="fill"),
              "p1": _row_panel(rows[1], "r0", "chart")}
    page_i = _fit_page(1.5, INSPECTOR_X)
    rows_i = _rows(page_i, [2])[0]
    beats = [
        step(1), wait(300),
        move("panel:p0", 500), click(right=True), context_menu("ctx_missing"), wait(200),
        move("item:ctx_missing/ctx_import_image", 500), click(),
        set(panels={"p0": {"kind": "photo"}}), wait(400),
        step(2),
        move("panel:p0", 400), click(),
        morph(450, inspector_x=INSPECTOR_X, page=page_i,
              panels={"p0": {"rect": rows_i[0], "selected": True}, "p1": {"rect": rows_i[1]}}),
        wait(250),
        *pick("fit", 0),
        morph(400, panels={"p0": {"fit": "fit"}}), wait(300),
        step(3),
        move((330.0, 130.0), 500), click(),
        keys("Ctrl", "Shift", "A", ms=900, dead=True), wait(200),
        move("blank", 500), click(),
        keys("Ctrl", "Shift", "A", ms=700),
        morph(600, panels={"p0": {"rect": _al_rects(page_i, (1.5, 1.0), 62.0)[0]},
                           "p1": {"rect": _al_rects(page_i, (1.5, 1.0), 62.0)[1]}}),
        wait(400),
    ]
    fields = {"fit": 1}
    panels["p0"]["aspect"] = 1.5
    panels["p1"]["aspect"] = 1.0
    return Demo("troubleshoot", _scene(page, panels, fields=fields, order=("fit",),
                                       title="grp_cell"), tuple(beats))


def _build_more():
    builders = (
        _build_add_images, _build_swap_replace, _build_auto_layout, _build_page_setup,
        _build_crop_fit, _build_insets, _build_shared_titles, _build_scale_bar,
        _build_marks, _build_text_sizes, _build_align_plots, _build_same_size,
        _build_freeform, _build_export, _build_save_share, _build_troubleshoot,
    )
    return {demo.key: demo for demo in (build() for build in builders)}


def _pace(demo, min_step=2500, minimum=9500):
    """Each step lasts at least min_step ms (held at its end), and the demo at least minimum ms."""
    spans = [[]]
    for beat in demo.beats:
        if beat.kind == "step" and spans[-1]:
            spans.append([])
        spans[-1].append(beat)
    for span in spans:
        span_ms = sum(beat.ms for beat in span)
        if span_ms < min_step:
            span.append(wait(min_step - span_ms))
    missing = minimum - sum(beat.ms for span in spans for beat in span)
    if missing > 0:
        share, remainder = divmod(missing, len(spans))
        for index, span in enumerate(spans):
            extra = share + (remainder if index == len(spans) - 1 else 0)
            if extra:
                span.append(wait(extra))
    return Demo(demo.key, demo.scene, tuple(beat for span in spans for beat in span))


DEMOS = {key: _pace(demo) for key, demo in {**_build_demos(), **_build_more()}.items()}
