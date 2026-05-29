# ImageLayoutManager — Agent Integration Design

**Status**: implemented MCP/GUI bridge, 36-tool surface  
**Owner**: zw87652015  
**Date**: 2026-05-29

---

## 1. Goals

Let an LLM agent author multi-panel publication figures end-to-end while the human
watches and steers, and run the same operations headlessly for batch jobs.

- **Primary**: agent drives the running GUI via local RPC; human can interrupt, undo,
  take over, hand back.
- **Secondary**: shipped `imagelayout-cli mcp` stdio adapter so MCP hosts can launch
  a standalone subprocess with no extra Python runtime or packages.
- **Vision loop**: agent can request canvas screenshots so vision-capable LLMs verify
  their own work.
- **Reproducibility**: every agent action is one entry on the existing `QUndoStack` —
  full undo/redo, dirty tracking, no special "agent mode".

---

## 2. Non-goals

- ❌ Cloud / remote agents — server is **localhost only**, single-user, single-app-instance.
- ❌ Replacing the GUI. The Inspector, drag-and-drop, etc. are not deprecated; the agent
  is just another input source.
- ❌ A natural-language layer inside the app. The host (Claude / Cursor / your own client)
  handles NL → tool-call translation.
- ❌ Multi-agent concurrency on one project (out of scope for v1).

---

## 3. Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ MCP host (Claude Desktop / Claude Code / Cursor / Windsurf) │
└──────┬──────────────────────────────────────────┬───────────┘
       │ JSON-RPC over WebSocket (localhost)      │ stdio MCP
       │ + screenshot bytes                       │
       ▼                                          ▼
┌──────────────────┐                    ┌──────────────────────┐
│  GUI server      │                    │   MCP stdio adapter   │
│  src/agent/      │                    │   imagelayout-cli     │
│    server.py     │                    │   imagelayout-cli mcp │
│  (lives inside   │                    │                       │
│   MainWindow)    │                    │                       │
└────────┬─────────┘                    └──────────┬────────────┘
         │                                         │
         └──────────────┬──────────────────────────┘
                        ▼
        ┌─────────────────────────────────┐
        │  src/agent/tools.py             │  ← single source of truth
        │  Pure-Python functions on a     │
        │  Project + UndoStack.           │
        │  Zero Qt-widget dependencies.   │
        └─────────────────────────────────┘
                        │
                        ▼
        ┌─────────────────────────────────┐
        │  Existing model + commands      │
        │  Cell, Project,                 │
        │  PropertyChangeCommand,         │
        │  LayoutEngine, ImageExporter,   │
        │  get_svg_override_bytes_for_    │
        │  cell, …                        │
        └─────────────────────────────────┘
```

**Why this shape:**

- `tools.py` is the contract. Both transports import it; tests target it directly.
- Each tool wraps existing `QUndoCommand` subclasses — no parallel data path, no risk
  of agent state diverging from GUI state.
- The GUI server is a thin Qt-thread-aware wrapper that schedules tool calls onto the
  main thread via `QMetaObject.invokeMethod`.

---

## 4. Transport A — GUI WebSocket server

**Protocol**: JSON-RPC 2.0 over WebSocket on `ws://127.0.0.1:<port>`.  
Port is auto-assigned on enable and written to
`%APPDATA%/ImageLayoutManager/agent.json` with the token so clients can discover
it without hard-coding anything.

**Why JSON-RPC over WebSocket inside the GUI:**

- App is already running; stdio is awkward for a GUI process.
- The MCP stdio process has a short host-controlled lifecycle, while the GUI is a
  long-running interactive app. The WebSocket bridge decouples those lifecycles.

**Lifecycle:**

- Off by default. User toggles **Tools → Enable MCP Server** (or `--agent-server`
  launch flag).
- Token is written into `agent.json`; the stdio adapter authenticates with it.
- Server stops on app exit or toggle-off.

**Threading:**

- WS server runs on a background `QThread` (asyncio bridge).
- Every tool call is marshalled to the GUI thread before touching `Project` / scene.
- Returns are JSON-serialisable; no `QObject` ever crosses the wire.

---

## 5. Transport B — MCP stdio adapter

```bash
imagelayout-cli mcp
```

- Launched by MCP hosts as a subprocess.
- Speaks MCP-over-stdio with the host.
- Reads `%APPDATA%/ImageLayoutManager/agent.json` (or platform equivalent), opens
  `ws://127.0.0.1:<port>`, authenticates with the token, then proxies tool calls to
  the running GUI.
- Serves `tools/list`, `resources/list`, `resources/read`, `ping`, and
  `tools/call`.
- Does **not** require the external `mcp` Python package.

---

## 6. Tool surface

**Naming convention**: `noun_verb`, snake_case.  
**Return envelope**:

```jsonc
{ "ok": true,  "result": { ... } }
{ "ok": false, "error": "cell_not_found",
               "detail": "no cell with id=abc-123",
               "hint": "call project_describe to list valid cell_ids" }
```

All tools return JSON-serialisable results. Tool descriptions and schemas are served
from `src/agent/tool_specs.py`.

---

### 6.1 Project lifecycle

| Tool | Key args | Returns |
|------|----------|---------|
| `project_new` | `page_size, dpi, margins?` | `{project_id}` |
| `project_open` | `path` | `{project_id, summary}` |
| `project_save` | `path?` | `{path}` |
| `project_export` | `path, format, region?` | `{bytes_written}` |
| `project_describe` | — | full structured tree (rows, cells, text items, PiPs) |

### 6.2 Layout — grid mode

| Tool | Key args |
|------|----------|
| `row_add` | `position, height_ratio?` |
| `row_remove` | `index` |
| `row_set` | `index, {height_ratio?, column_ratios?}` |
| `cell_add` | `row_index, position?` |
| `cell_remove` | `cell_id` |
| `cell_swap` | `cell_id_a, cell_id_b` |
| `cell_split` | `cell_id, direction: 'h' \| 'v', count` |
| `layout_set_mode` | `'grid' \| 'freeform'` |

### 6.3 Layout — freeform mode

| Tool | Key args |
|------|----------|
| `cell_set_geometry` | `cell_id, {x_mm, y_mm, w_mm, h_mm, z?}` |
| `cell_set_z_index` | `cell_id, z` |

### 6.4 Image content

| Tool | Key args |
|------|----------|
| `image_import` | `cell_id, path, fit_mode?` |
| `cell_set_properties` | `cell_id, fit_mode?, rotation?, crop_*?, padding_*?, align_h?, align_v?, z_index?, override_*?, svg_normalize_text?` |

### 6.5 Scale bar

| Tool | Key args |
|------|----------|
| `cell_set_scale_bar` | `cell_id, enabled?, mode?, um_per_px?, length_um?, unit?, color?, thickness_mm?, position?, offset_x?, offset_y?, custom_text?, show_text?, text_size_mm?` |

### 6.6 Text & labels

| Tool | Key args |
|------|----------|
| `auto_label_cells` | `scheme: '(a)'\|'A'\|'a'\|'(A)', placement` |
| `labels_set_style` | `font_family?, font_size_pt?, font_weight?, color?, anchor?, offset_x?, offset_y?` |
| `project_set_label_style` | defaults for future auto-labels |
| `text_add` | `text, x?, y?, parent_cell_id?, font_family?, font_size_pt?, font_weight?, color?, rotation?` |
| `text_set_style` | `text_id, text?, font_family?, font_size_pt?, font_weight?, color?, x?, y?, rotation?, anchor?, offset_*?, bg_*?` |
| `text_remove` | `text_id` |

### 6.7 PiP (picture-in-picture)

| Tool | Key args |
|------|----------|
| `pip_add` | `cell_id, type: 'zoom'\|'external', {x, y, w, h, …}` |
| `pip_set_properties` | `pip_id, geometry?, crop?, border?, origin box?, scale_bar_*?` |
| `pip_remove` | `pip_id` |

### 6.8 Size groups

| Tool | Key args |
|------|----------|
| `size_group_create` | `cell_ids, name?` |
| `size_group_set` | `group_id, name?, pinned_width_mm?, pinned_height_mm?` |
| `size_group_assign` | `cell_id, group_id?` |
| `size_group_delete` | `group_id` |

### 6.9 Export region

| Tool | Key args |
|------|----------|
| `export_region_set` | `x_mm, y_mm, w_mm, h_mm` |
| `export_region_clear` | — |

---

## 7. Object identity

- **`cell_id`** — existing `Cell.id` (UUID).
- **`text_id`, `pip_id`, `group_id`** — existing UUIDs throughout the model.

Use `project_describe` after each structural operation. Adding/removing rows,
adding/removing cells, splitting cells, and auto-label operations can change the set
of valid leaf cells and text items.

---

## 8. The session loop

```
1. User opens app and clicks "Tools → Enable MCP Server".
2. User opens .figlayout or starts blank.
3. MCP host launches `imagelayout-cli mcp`.
4. CLI adapter connects to the running GUI server.
5. Agent calls project_describe → receives the full project tree.
6. Agent plans: "I need a 2×3 grid, 85 mm wide, scale bars in row 2."
7. Agent calls layout / image / label / scale-bar / PiP tools in sequence.
8. Agent calls view_screenshot to verify visually.
9. Human sees every change live. Hits Ctrl+Z to revert one step, or types a
   correction in the chat, which the agent translates to more tool calls.
10. Agent calls project_export when satisfied. Human reviews, saves, ships.
```

The key differentiator over a pure-CLI workflow is that the agent gets immediate
visual feedback and the human retains real-time control throughout.

---

## 9. Error handling

Error codes are a stable enum the agent can branch on. `hint` is written for LLMs.

```jsonc
// Success
{ "ok": true, "result": { "cell_id": "abc-123" } }

// Known error
{
  "ok": false,
  "error": "cell_not_found",
  "detail": "no cell with id=abc-123",
  "hint": "call project_describe to list valid cell_ids"
}

// Validation error (dry_run or live)
{
  "ok": false,
  "error": "invalid_value",
  "field": "target_pt",
  "detail": "target_pt must be > 0, got -1.0"
}
```

Tools validate inputs before mutation and return stable error strings such as
`cell_not_found`, `invalid_value`, or `wrong_layout_mode`.

---

## 10. Undo & dirty tracking

- Mutating tools route through existing `QUndoCommand` implementations where the GUI
  already has commands for that operation.
- Human Ctrl+Z remains the source of truth for reverting agent changes.
- No parallel data path is introduced; tools mutate the same model the GUI edits.

---

## 11. Security and shipping model

| Constraint | Detail |
|------------|--------|
| Network | Bind `127.0.0.1` only; no LAN / internet exposure |
| Auth | Random 256-bit Bearer token, regenerated on every server enable |
| No shell | No `eval`, `exec`, `os.system`, or subprocess exposed as tools |
| Opt-in | No port opens until the user explicitly enables the server |
| Ship together | GUI exe and `imagelayout-cli.exe` must be rebuilt and shipped together |

After upgrading, users should restart both ILM and the MCP host so `tools/list` from
the CLI adapter and `tools.dispatch` inside the GUI see the same registry.

---

*End of document.*
