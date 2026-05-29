# ImageLayoutManager — Agent Concepts Primer

**For**: LLMs (and humans) driving ILM via the agent tools.
**Read this once** before issuing tool calls. It is also served at runtime
via MCP `resources/read` on the URI `ilm://concepts`.

---

## What ILM is

ILM lays out **multi-panel publication figures**. A project is a single
page (mm-based, with a target DPI for raster export) containing:

- **Rows** — horizontal strips top-to-bottom.
- **Cells** — within each row, one or more side-by-side panels.
- **Cell content** — an image (with fit mode, rotation, crop, padding),
  optional scale bar, optional picture-in-picture insets.
- **Text items** — floating labels or anchored corner labels.

The output is a single image (PNG / JPG / TIFF) or a PDF. There is no
"page 2".

---

## The mental model: rows, cells, splits

```
Page
├── Row 0  (height_ratio: 1.0,  column_count: 2)
│    ├── Cell  (image, scale bar, ...)
│    └── Cell  (image, ...)
├── Row 1  (height_ratio: 2.0,  column_count: 1)
│    └── Cell  (split into children — a 2×2 nested sub-figure)
│         ├── Cell  (leaf, has image)
│         ├── Cell  (leaf, has image)
│         ├── Cell  (leaf, has image)
│         └── Cell  (leaf, has image)
└── Row 2  (height_ratio: 1.0,  column_count: 3)
     ├── Cell
     ├── Cell
     └── Cell
```

Key facts that are easy to get wrong:

- **`column_count` is per-row.** Rows are independent — row 0 can have
  2 columns, row 1 can have 5. They do **not** have to align.
- **`height_ratio` is relative.** Three rows with ratios `[1, 2, 1]`
  split the page **25% / 50% / 25%**, not in millimetres.
- **`column_ratios` (set via `row_set`) is relative within a row.**
  Two columns with `[2, 1]` give the left cell 2/3 of the row width.
- **Splits are for *nesting*, not for adding columns.** If you want
  another column in an existing row, use `cell_add`. If you want a
  nested sub-figure *inside* one existing slot, use `cell_split`.
- **Only leaf cells hold content.** A split cell becomes a container;
  its image (if any) moves into the first child automatically.

---

## Two layout modes: grid vs freeform

### Grid mode (default)

- Cells positioned by `(row_index, col_index)` and resized by ratios.
- Use for: standard publication figures, equal-spacing grids,
  anything you'd describe as "N rows by M columns".
- All `row_*` / `cell_add` / `cell_remove` / `cell_swap` / `cell_split`
  tools work here.

### Freeform mode

- Cells positioned by absolute mm coordinates: `(x_mm, y_mm, w_mm, h_mm)`.
- `z_index` controls stacking order — higher draws on top.
- Use for: overlapping insets, irregular arrangements, hand-tuned
  positioning that doesn't fit a grid.
- Switch with `layout_set_mode(mode='freeform')` — this **bakes** the
  current grid layout into freeform coordinates so the visual result
  is preserved as a starting point.
- `cell_set_geometry` only works in this mode.

You can switch back and forth. Switching freeform → grid keeps the
freeform coordinates on each cell, so re-baking later is loss-free.

---

## The composition primitives

Each tool below has a JSON Schema (returned by MCP `tools/list`). This
section is the **conceptual** guide; the schema is the **mechanical**
guide.

### Rows

- `row_add(position?, column_count?, height_ratio?)` — insert a new row.
  Omit `position` to append. The row starts with `column_count`
  placeholder cells.
- `row_remove(index)` — delete a row and everything in it. Subsequent
  rows shift up.
- `row_set(index, height_ratio?, column_ratios?)` — tune ratios.
  `column_ratios` must have one entry per column in that row.

### Cells (top-level, inside a row)

- `cell_add(row_index, position?)` — add a column to an existing row.
- `cell_remove(cell_id)` — delete a top-level cell. The row's column
  count decreases by one.
- `cell_swap(cell_id_a, cell_id_b)` — swap *content* (image, scale bar,
  fit mode, etc.) of two cells. The cells stay where they are; only
  their contents trade. Use for re-ordering panels.

### Splits (nested sub-figures inside one cell)

- `cell_split(cell_id, direction, count?)` — turn a leaf cell into a
  container with `count` children. `direction='h'` for side-by-side,
  `'v'` for stacked.
- Splits are recursive: you can split a child of a split.
- `cell_set_split_ratios(parent_id, ratios)` — **rebalance the children
  of a split**. Pass the *parent's* `cell_id` (the container), not a
  child's. Ratios are relative within the split, same convention as
  `row_set(column_ratios=…)`. **This is the right tool for "make
  sub-cell X smaller" — don't switch to freeform mode for that.**

### Cell content

- `image_import(cell_id, path, fit_mode?)` — place an image. Path must
  be a local file the app can read.
- `cell_set_properties(cell_id, …)` — change image-side properties:
  `fit_mode`, `rotation`, `align_h`, `align_v`, padding, crop window,
  `z_index`, per-cell override sizes, aspect-ratio lock, and SVG text
  normalisation. Use this for "rotate panel", "crop panel", "add padding",
  "align image left", or "make SVG text 8 pt".
- `cell_set_scale_bar(cell_id, …)` — configure microscopy scale bars:
  enabled, calibration (`um_per_px`), length, unit, color, text, thickness,
  position, and offsets.
- `cell_set_geometry(cell_id, x_mm, y_mm, w_mm, h_mm, z?)` — freeform
  position only.
- `cell_set_z_index(cell_id, z)` — stacking order shortcut. Higher draws
  on top, mainly useful in freeform mode.

### PiP insets

- `pip_add(cell_id, pip_type, image_path?, x?, y?, w?, h?)` — add a
  Picture-in-Picture inset to a host cell. Geometry is normalised to the
  host cell: `x/y/w/h` are fractions in `[0, 1]`.
- `pip_set_properties(pip_id, …)` — update PiP geometry, crop, border,
  origin box, external image path, or the PiP's own scale bar.
- `pip_remove(pip_id)` — delete a PiP inset.

### Labels

- `auto_label_cells(scheme?, placement?)` — generate sequential
  `(a)(b)(c)…` labels for every leaf cell.
  - `scheme`: `'a'`, `'A'`, `'(a)'`, `'(A)'`.
  - `placement='in_cell'` overlays labels on top of each image.
  - `placement='row_above'` adds a dedicated label row above each
    picture row. Pick this when images are dense and overlays would
    obscure content.
- `labels_set_style(…)` — restyle **all existing cell labels** and update
  project defaults for future labels. Use this for "make labels smaller",
  "make labels bold", "move labels inward", or "change label color".
- `text_set_style(text_id, …)` — restyle one text item or one label.
- `project_set_label_style(…)` — update defaults for labels generated in
  the future. It does **not** touch existing labels.
- `text_add(…)` / `text_remove(text_id)` — create or delete free text
  annotations.

### Size groups and export regions

- `size_group_create(cell_ids, name?)` — group cells so they share a
  common width/height.
- `size_group_set(group_id, …)` — rename a group or pin its absolute
  width/height in mm.
- `size_group_assign(cell_id, group_id?)` — move a cell into a size group,
  or unassign it with `group_id=null`.
- `size_group_delete(group_id)` — remove a size group.
- `export_region_set(x_mm, y_mm, w_mm, h_mm)` — persistently crop exports
  to a page sub-rectangle.
- `export_region_clear()` — export the full page again.

### Algorithmic best-fit

- `auto_layout()` — re-balance row heights and column widths based on
  imported images' aspect ratios. Grid mode only. Re-run after adding
  images or changing topology.

### Vision and IO

- `project_describe()` — full structural snapshot. Call after every
  structural change to refresh `cell_id`s and the hierarchy.
- `view_screenshot(dpi?)` — PNG of the current canvas. Use to verify.
  Defaults to **150 DPI** for cheap previews (~3k image tokens for A4).
  Bump `dpi` only if you need to read small text — 600 DPI is ~46k
  tokens per call.
- `project_export(path, format)` — write a **rendered image** (PNG/JPG/TIFF) to disk.
- `project_save(path?)` — persist the **editable project file** (.figlayout,
  .figpack, or .json — the extension picks the format). Omit `path` to save
  in place. Always use this for "save the project" — never hand-write the JSON.
- `project_new`, `project_open` — create / open projects.

---

## Recipes

### Recipe 1 — Simple 2×2 grid

```
project_new(page_size={w: 148, h: 210}, dpi: 600)
row_add(column_count: 2)
row_add(column_count: 2)
desc = project_describe()
for cell, img in zip(desc.cells, my_image_paths):
    image_import(cell.id, path=img)
auto_label_cells(scheme: '(a)')
auto_layout()
project_export(path: 'figure.png', format: 'PNG')
```

### Recipe 2 — One wide top + three bottom panels

```
project_new(page_size={w: 180, h: 120})
row_add(column_count: 1)              # top: full-width strip
row_add(column_count: 3)              # bottom: three panels
row_set(index: 0, height_ratio: 1.5)  # top gets 60% of page height
# Now fill cells. Order: top row first (1 cell), bottom row next (3 cells).
desc = project_describe()
image_import(desc.cells[0].id, path: 'schematic.png')
image_import(desc.cells[1].id, path: 'panel_a.tif')
image_import(desc.cells[2].id, path: 'panel_b.tif')
image_import(desc.cells[3].id, path: 'panel_c.tif')
auto_label_cells(scheme: '(a)', placement: 'in_cell')
project_export(path: 'figure.png', format: 'PNG')
```

### Recipe 3 — Nested 2×2 inside the top panel

```
project_new(page_size={w: 180, h: 240})
row_add(column_count: 1)         # top container (will be split 2×2)
row_add(column_count: 1)         # bottom: single image
row_set(index: 0, height_ratio: 2.0)

# Find the top container cell and split it twice.
desc = project_describe()
top_id = next(c.id for c in desc.cells if c.row == 0)
cell_split(top_id, direction: 'h', count: 2)   # left/right
desc = project_describe()
left_id, right_id = [c.id for c in desc.cells if c.parent_id == top_id]
cell_split(left_id,  direction: 'v', count: 2) # stack the left half
cell_split(right_id, direction: 'v', count: 2) # stack the right half

# Now you have 4 leaves under top_id + 1 cell in row 1 = 5 panels to fill.
```

### Recipe 4 — Freeform overlay

```
project_new(...)
row_add(column_count: 2)
# import main panels in grid mode first
for cell, img in zip(project_describe().cells, my_image_paths):
    image_import(cell.id, path: img)

# Switch to freeform — current grid positions are baked in.
layout_set_mode(mode: 'freeform')

# Now overlap a small inset on top of the first panel.
desc = project_describe()
cell_set_geometry(desc.cells[0].id, x_mm: 10, y_mm: 10, w_mm: 80, h_mm: 60, z: 0)
# (To create a new floating cell for the inset, you'd add a row in grid
#  mode first, then bake — agent tools to create cells directly in
#  freeform mode arrive in v0.3.)
```

### Recipe 5 — Labels above each row (out-cell mode)

```
project_new(...)
row_add(column_count: 3)
row_add(column_count: 3)
for cell, img in zip(project_describe().cells, my_image_paths):
    image_import(cell.id, path: img)
auto_label_cells(scheme: '(a)', placement: 'row_above')
# A dedicated label strip is inserted above each picture row.
# The labels do not obscure the images.
```

### Recipe 6 — Make labels publication-sized with breathing room

```
# First inspect existing label ids and current defaults.
desc = project_describe()

# Restyle every existing cell label and future labels at once.
# Typical 180–210 mm figures look better with 8–12 pt labels, not huge titles.
labels_set_style(font_size_pt: 10, font_weight: 'bold',
                 color: '#000000', offset_x: 1.5, offset_y: 1.0)

# Verify visually, then nudge offsets if labels are too close to image edges.
view_screenshot()
```

Use `labels_set_style` for global label cleanup. Use
`text_set_style(text_id, …)` only when one label needs a special tweak.
Use `project_set_label_style` before `auto_label_cells` when you are setting
defaults for labels that do not exist yet.

### Recipe 7 — Add a calibrated scale bar

```
desc = project_describe()
cell_id = desc.cells[0].id
cell_set_scale_bar(cell_id,
                   enabled: true,
                   um_per_px: 0.1301,
                   length_um: 10,
                   unit: 'µm',
                   color: '#FFFFFF',
                   position: 'bottom_right',
                   thickness_mm: 0.5,
                   show_text: true,
                   text_size_mm: 2.0)
view_screenshot()
```

### Recipe 8 — Add an inset with a visible border

```
desc = project_describe()
host = desc.cells[0].id
pip = pip_add(host, pip_type: 'zoom', x: 0.62, y: 0.62, w: 0.33, h: 0.33)
pip_set_properties(pip.pip_id,
                   crop_left: 0.25, crop_top: 0.25,
                   crop_right: 0.55, crop_bottom: 0.55,
                   border_enabled: true,
                   border_color: '#FFFFFF',
                   border_width_pt: 1.5)
view_screenshot()
```

---

## How to choose: decision table

| Goal                              | Tool                                                  |
|-----------------------------------|-------------------------------------------------------|
| Add a row                         | `row_add`                                             |
| Add a column to an existing row   | `cell_add(row_index, position?)`                      |
| Make one cell into 4 sub-panels   | `cell_split` (twice — `'h'` then `'v'` on each child) |
| Resize a row                      | `row_set(index, height_ratio=…)`                      |
| Change column widths in a row     | `row_set(index, column_ratios=[…])`                   |
| Resize sub-cells inside a split   | `cell_set_split_ratios(parent_id, ratios=[…])`        |
| Reorder panels                    | `cell_swap`                                           |
| Overlap / freely position a panel | `layout_set_mode('freeform')` then `cell_set_geometry`|
| Re-balance everything             | `auto_layout`                                         |
| Overlay (a)(b)(c) on images       | `auto_label_cells(placement='in_cell')`               |
| Labels above each row             | `auto_label_cells(placement='row_above')`             |
| Make all labels smaller/styled    | `labels_set_style(font_size_pt=…, …)`                 |
| Style one label/text item         | `text_set_style(text_id, …)`                          |
| Add free text annotation          | `text_add(text=…, x=…, y=…)`                          |
| Rotate/crop/pad/align image       | `cell_set_properties(cell_id, …)`                     |
| Add or edit a scale bar           | `cell_set_scale_bar(cell_id, …)`                      |
| Add a PiP inset                   | `pip_add` then `pip_set_properties`                   |
| Force cells to share W/H          | `size_group_create` / `size_group_set`                |
| Crop exported page persistently   | `export_region_set` / `export_region_clear`           |
| Render to PNG                     | `project_export(path, format='PNG')`                  |
| Save the editable project file    | `project_save(path?)` — .figlayout / .figpack / .json |
| See the current canvas            | `view_screenshot`                                     |

---

## Common pitfalls

1. **`cell_set_geometry` in grid mode** → returns `wrong_layout_mode`.
   Call `layout_set_mode(mode='freeform')` first — but think twice
   before doing so. Most "make this panel smaller" requests are
   answered by `row_set` (for row heights / column widths) or
   `cell_set_split_ratios` (for sub-cells in a split). Freeform is
   for overlap and irregular positioning, not routine resizing.
2. **`cell_split` to "add a column"** → wrong tool. Splits create
   *children* inside one slot. Use `cell_add(row_index)` to add a
   column to an existing row.
3. **`cell_remove` on a split sub-cell** → returns `not_supported`.
   Only top-level cells can be removed; sub-cells live or die with
   their parent.
4. **Stale `cell_id`s** → every structural change (split, add, remove,
   swap) can change the leaf set. Call `project_describe` again to
   refresh. Do **not** cache IDs across structural edits.
5. **Forgetting `auto_layout`** → without it, rows and columns inherit
   default ratios. Cells full of skinny images sit in big square slots.
   Run `auto_layout` after importing images and after structural changes.
6. **`project_new` defaults to a 2×2 placeholder grid.** If you want a
   different shape, either remove rows with `row_remove` or call
   `project_new` and immediately reshape before importing images.
7. **Confusing label defaults with existing labels.**
   `project_set_label_style` changes defaults for future labels only.
   `labels_set_style` changes existing labels and defaults together.
8. **Using freeform mode for PiP-style insets.** Prefer `pip_add` for an
   inset inside a panel. Use freeform only when the whole cell itself must
   overlap other cells.

---

## Default workflow for "make me a figure from these images"

```
1. project_new(page_size, dpi)                       — start blank
2. Analyse images (host vision: aspect ratios,
   content type, hierarchy)                          — outside ILM
3. Decide topology: how many rows, what column_count
   per row, any nested splits                        — reasoning
4. row_add × N, with column_count + height_ratio     — build the skeleton
5. cell_split as needed for nested sub-figures       — refine topology
6. project_describe → get cell_ids in order          — discover IDs
7. image_import for each panel                       — fill content
8. auto_layout                                        — re-balance
9. auto_label_cells(scheme, placement)               — label
10. labels_set_style / cell_set_scale_bar / pip_add  — style + annotate
11. view_screenshot → verify                         — feedback loop
12. project_export(path, format)                     — output
```

If verify shows a problem, fix with `cell_swap` / `row_set` /
`cell_set_geometry` (after switching to freeform), then re-screenshot.
