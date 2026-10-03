# NCPlotGenerator review and ILM plot-editor direction

Reviewed source: `E:/Codes/NCPlotGenerator`.

This is a source-level design review of the dedicated generators, their GUI
entry points, the `ncplot` application, palette files, and the saved
`radial_plot.png`. The original analysis/generation scripts were not executed.
The folder demonstrates useful workflows; this review does not identify which
script revision produced each published figure.

## Recommendation

Add reusable **Plot Styles** to the companion Plot Editor, accessible from ILM.
Start with a style selector and **Save Current Style As…**, **Edit…**, and
**Import/Export…**. The existing plot controls should do most of the editing.
A large separate theme-design application is unnecessary for the first version.

Develop plot families from the specialised tools below, with shared axes,
series, annotations, styling, and physical-size handling. Keep ILM responsible
for assembling panels and determining their final placement.

## What is worth carrying forward

The folder contains two approaches:

- The general `ncplot/` application separates `DataModel`, `PlotConfiguration`,
  `NatureStyle`, and `PlotEngine`. This separation is useful, although the
  style currently includes layout and export settings too.
- The root-level generators and their GUIs contain more specialised choices:
  wide-table column selection, raw-point overlays, side density curves,
  significance brackets, stacked profiles, external legends, and custom
  palettes. These are particularly useful product references.

### Plot families

| Family | Evidence in the source | Features to retain | Suggested order |
|---|---|---|---|
| Line, scatter, and mixed observations/curves | `scatter_line_generator.py::NatureScatterLinePlot.generate_plot`; `radial_plotter.py::main` | Independent marker/line styling, transparency, open markers, shared color identity, annotations, area fills, outside legends, numeric colorbars | First expansion |
| Grouped distributions | `box_plot_generator.py::NatureBoxPlot.generate_plot`; `violin_plot_generator.py::NatureViolinPlot.generate_violin_plot_wide` | Box; box + raw points; box + points + side density; violin + inner box; points beside the violin; group labels; optional sample summaries and comparison brackets | Next |
| Stacked profiles | `stacked_y_line_generator.py::generate_plot`; `mountain_stacked_plot_generator.py::generate_plot` | Offsets, ordering, optional fill, direct labels, baseline visibility, label wrapping | Next |
| Composition and group comparison | `stacked_column_generator.py::generate_stacked_plot`; `ncplot/plot_engine.py::_render_bar`, `_render_grouped_bar` | Vertical/horizontal bars, percentage stacking, category ordering, percentage labels, outside legends | Following distributions/profiles |
| Diagnostic plots | `qq_plot_generator.py::generate_qq_plot`; `ncplot/plot_engine.py::_render_residuals` | Quantiles, reference/fitted lines, supplied bands, diagnostic annotations | After explicit analysis/provenance support |
| Density and matrix plots | `ncplot/plot_engine.py::_render_histogram`, `_render_kde`, `_render_ecdf`, `_render_heatmap` | Distribution views and annotated correlation heatmaps with numeric color mapping | Later, according to demand |
| 3D stacked planes | `stacked_plane_3d_plot_generator.py::generate_plot` | Camera, plane offsets, translucent fills, depth labels | Later; requires a separate 3D geometry/editing contract |

The radial example is a **Cartesian scatter-and-line composition**, not a polar
plot. It reads observed points and already fitted curves from separate files,
links their appearance by time, and replaces a long legend with an inset
colorbar. This is a useful acceptance example for a general mixed-series editor.
It does not require ILM to implement the fitting analysis to reproduce the
composition.

Some general-app labels overstate distinct implementations:
`PAIRPLOT` and `BUBBLE` route to the ordinary scatter renderer; `RAINCLOUD`
routes to the violin renderer. `TREEMAP` is listed in the model but has no
specific dispatch entry, so it falls back to scatter. Those names should not
be treated as completed capabilities to import wholesale
(`ncplot/models.py::PlotType`, `ncplot/plot_engine.py::_render_single`).

The specialised box + points + side-density variant is a stronger concrete
reference for a raincloud-like composition than the general-app menu label.

### Shared interactions

- Import a wide CSV/table, choose one X column and several Y columns. For
  distributions, choose several observation columns. The current ILM editor's
  per-series two-column entry is useful for small plots but does not yet match
  this workflow.
- Expose independent axis-label, tick-label, title, legend, and annotation
  typography. The current native document combines several of these roles.
- Retain mathematical labels, manual line breaks, and optional wrapping.
- Represent annotations by purpose: text, arrow, reference line, highlighted
  region, and comparison bracket. Store their coordinate system explicitly
  (data, axes fraction, or physical offset).
- Give pale fills visible borders and distinguish raw points from summaries
  using both opacity and shape. `enhance_contrast` in the violin generator is
  a useful example of this intent.
- Make outside legends and colorbars first-class layout elements with reserved
  space. The timeline records successive overlap fixes as legends moved from
  inside the data to above the axes and then to the right.

## Sizing: what the old code reveals

1. **Requested dimensions and saved dimensions can differ.** For example,
   `scatter_line_generator.py::save_figure`, the violin/box/stacked-column
   exporters, and `ncplot/ui/main_window.py::_export_figure` use
   `bbox_inches="tight"`. This computes a content-dependent export boundary;
   changing text or an outside legend can change the saved page bounds even
   when `figsize` is unchanged. `tight_layout()` changes axes arrangement;
   `bbox_inches="tight"` additionally changes export bounds.
2. **Some stroke widths undergo an extra unit conversion.** The repeated
   `0.5 * 0.3528` assignments to `axes.linewidth` and tick widths, also present
   in `NatureStyle.to_rcparams`, convert a point value toward millimetres
   before passing it to settings that already expect points. A declared
   0.5-point intention therefore becomes approximately 0.1764 points.
3. **Display size and document size are coupled in the old previews.**
   `ncplot/ui/preview_panel.py` attaches the engine's Figure to a resizable
   QtAgg canvas and returns that same Figure for export. QtAgg canvas resizing
   can change Figure inches. The violin GUI instead fixes its canvas at
   600 × 500 pixels. That constrains a widget, not a publication size in mm.
   The timeline explicitly records this category of problem; this review
   did not replay the original interactive sessions.
4. **Manual magnification mixes different unit meanings.**
   `scatter_line_generator.py` has a `magnify_2x` branch that doubles fonts,
   line widths, and scatter `s`. Matplotlib's scatter `s` is an area in pt²,
   while line widths and font sizes are lengths in pt; doubling both is not
   uniform visual magnification.

The desired contract is:

- ILM owns the final outer panel rectangle in **mm**. A standalone document
  owns an equivalent explicit width/height when it is not placed in ILM.
- Text sizes, strokes, tick lengths, marker diameters, and physical padding use
  **pt**. A scatter renderer converts a requested marker diameter to its
  area-based API at the renderer boundary.
- Preview zoom changes display magnification only. Raster DPI changes sampling
  resolution only. Neither rewrites document geometry or style values.
- Export preserves the requested outer dimensions. Long labels, outside
  legends, and colorbars consume space inside that allocation; the UI exposes
  space problems instead of silently changing the output page size.
- Distinguish the outer panel from the inner data area. A future gutter/layout
  pass should return the actual axes rectangle to ILM so alignment uses current
  geometry after a label/style edit.

The current ILM prototype already compensates native font/stroke sizes at the
placed panel scale and separates SVG preview from the document size. Its
`axes_rect` is fixed in normalized coordinates. Measured gutters and outside
legend/colorbar placement remain additional work, particularly for small panels
and long labels. A style library alone will not solve those layout cases.

## Palette collection

Exact source colors and their order are captured in
[`NCPlotGenerator_palettes.json`](NCPlotGenerator_palettes.json), with a visual
sheet in [`NCPlotGenerator_palettes.png`](NCPlotGenerator_palettes.png).
The catalog is a research artifact, not an installed ILM preset format.

The eight captured schemes are Colorful, Muted Rainbow, Ocean, Wong/Okabe-Ito,
Blue–Pink, Blue–Red, Blue–Red Preserve Ends, and Purple–Brown. They were checked
against the literal definitions in `scatter_line_generator.py`; Blue–Pink,
Blue–Red, and Purple–Brown also match their `ColorThemes/*.txt` files.
Colorful and Wong contain the same color set in different orders.

Keep category palettes, ordered palettes, and numeric colormaps distinct.
The same colors can be offered in more than one mode, but applying colors to
categories is different from mapping a numerical variable to color.

For example, the radial script selects each series color by its index but
constructs its colorbar from a 5–95-second numeric normalization. Those mappings
coincide for a complete, evenly spaced set of time points; missing or uneven
times can make them disagree. The new renderer should use the same stored
normalization for both `color = cmap(norm(time))` and the colorbar.

For categories, persist the resolved series/group color assignments. Reordering
rows or adding a series should not unexpectedly change the identity of
"Control" or another explicitly mapped group. A user can choose to reassign a
palette, but that should be an explicit operation.

## What belongs in a reusable Plot Style

| Component | Examples |
|---|---|
| Typography by role | Family, label/tick/legend/title/annotation sizes, weight, text color |
| Series appearance | Color cycle, line-width/dash defaults, marker shape/diameter/fill/edge |
| Axes | Visible spines, spine/tick widths, tick lengths/direction, grid appearance |
| Filled elements | Fill opacity, outline treatment, box/violin defaults, band appearance |
| Legend and annotation appearance | Frame, background, text, padding, bracket/arrow stroke |

Use a separate **Layout Preset** for preferred panel dimensions and reserved
legend space, and a **Plot Template** for a recurring plot structure.
Applying a Plot Style should not overwrite dimensions, axis limits, units,
category order, data, normalization, fitting choices, or statistical methods.
The application's light/dark UI theme remains independent.

A suggested simple flow:

1. Choose a Plot Style from a small swatch/preview selector.
2. Adjust the usual controls on the current plot.
3. Choose **Save Current Style As…** and name it, e.g. "My lab".
4. Set it as the default for future plots if desired.
5. In ILM, **Apply Style to Selected Plots…** previews the change and commits
   one undo operation. Local overrides have an explicit Keep/Reset choice.
6. Export/import the style as a small, versioned, data-only JSON document.

A future dedicated style dialog can group these same settings and show previews
on several synthetic plot types. It need not expose all Matplotlib rcParams.
Built-in style names should describe appearance rather than imply automatic
compliance with a journal's changing requirements.

### Persistence and precedence

- Each native plot embeds a complete style snapshot plus explicit element
  overrides. A style-library id/name/revision may record provenance.
- A saved plot remains reproducible when shared with someone who does not have
  the author's style library. Editing/deleting a library preset does not
  silently restyle existing publication figures.
- Resolve styles as **embedded style snapshot → explicit element overrides**.
  The user's preferred default selects the snapshot for a new plot; it is not
  a hidden live dependency of existing plots.
- Offer explicit updates to selected plots when a library style changes.
  Color mappings follow persistent group/series keys, with user-controlled
  semantic links across panels.
- The native document is currently schema 1. Adding these fields/types needs
  a native-document migration preserving the existing visible defaults,
  including the hardcoded spine, tick, marker-edge, and legend-frame sizes in
  `src/plot_editor/render.py`. Merely changing the schema number would be wrong.
- Per-document styles and a per-user library can be introduced without changing
  the ILM project schema. Persisting project-level defaults or linked styles
  later would require a separate project-schema decision.

## Scientific choices to preserve explicitly

Several generators combine presentation with calculations or transformations:

- Box/violin code chooses percentile/whisker conventions, KDE bandwidth and
  evaluation extent, jitter, and per-column missing-value handling.
- Stacked columns replace NaNs with zero and clamp negative values before
  normalizing rows to percentages.
- Mountain profiles subtract each series minimum before adding offsets;
  stacked-Y profiles add offsets to the original values without that
  subtraction. These similar-looking plots have different transformations.
- Q-Q generators calculate reference quantiles, fitted lines, bands, and test
  annotations. These methods need independent specification and validation
  before becoming general public-app analysis features.
- The scatter/line "shadow" is a fill to the baseline, not an uncertainty band.
- The radial example reads externally fitted curve coordinates; the plotting
  script does not perform that fit.

A theme must never select or change those scientific choices. Initially,
accept externally calculated curves, intervals, and annotation values with
clear provenance. When native calculations are added, retain raw data and
explicit method parameters separately from the style, including deterministic
jitter settings and a declared missing-value policy.

## Proposed implementation sequence

1. **Styles and size foundations:** one palette registry; role-based typography
   and axes/marker styles; personal preset save/load/default; embedded snapshots;
   exact-size export and explicit layout-space handling.
2. **Publication XY workflows:** wide-table column mapping; real scatter and
   mixed observed/fitted series; shared color keys; outside legends; numeric
   colorbars; reusable reference lines/regions/text annotations.
3. **Grouped distributions and profiles:** box + observations + optional
   density, violin, stacked-Y, and mountain profiles. Add each through the
   same native document/edit/save/export path, with explicit transformations.
4. **Composition and diagnostics:** stacked/grouped bars, Q-Q/residuals, and
   general distribution/heatmap tools after their calculation contracts are
   settled.
5. **3D and less common families:** a later extension with separate projection
   and editing behavior; existing SVG/PDF import remains available meanwhile.

Good first acceptance cases are a small line/scatter panel in two physical
sizes with the same style, a radial-like observation/curve composition with a
shared time colormap, and saving/reopening that figure on an installation with
no personal presets. Expanding the menu with every legacy plot name would not
test those end-to-end requirements.
