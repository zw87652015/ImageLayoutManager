# ilmplot

Qt-free core for ILM's editable `*.ilmplot.svg` plot documents, plus a
matplotlib `Figure` → `*.ilmplot.svg` bridge.

A `*.ilmplot.svg` is a standard SVG that also embeds a versioned JSON
`PlotDocument` in `<metadata id="ilm-plot-document">` — the file is both
the vector snapshot and the editable source of truth. ILM's per-cell
"Reflow" re-renders such documents at the cell's real size; plain SVGs
only scale as pictures.

## Install

```sh
pip install ilmplot
```

From a source checkout: `pip install packages/ilmplot`.

Requires Python ≥ 3.10, matplotlib ≥ 3.7, numpy ≥ 1.23.

## Use

```python
import matplotlib.pyplot as plt
import ilmplot

fig, ax = plt.subplots()
ax.plot([0, 1, 2], [0, 1, .5], label='Control')
ax.legend()
ilmplot.savefig(fig, 'a.ilmplot.svg')
```

### Native vs fallback

`ilmplot.savefig(fig, path)` writes a native `*.ilmplot.svg` when the
figure maps onto the document model. If it uses unsupported features,
`savefig` emits a `FallbackWarning` and writes a **plain** SVG (real
text, `svg.fonttype='none'`) to the same path instead, so callers always
get a usable file. `savefig(fig, path, strict=True)` raises
`UnsupportedFigureError` and leaves any existing file untouched.

Check without writing:

```python
result = ilmplot.convert(fig)
if result.document is None:
    print(result.reasons)   # features that block a native file
print(result.notes)         # harmless normalisations applied
```

### Supported

One rectilinear `Axes`; `plot()`/`errorbar()` (y-errors) / `scatter`
(uniform size and colour) / `bar()` (single, grouped, stacked; categorical
x, or categorical y with `barh()`); vertical and horizontal bars convert
separately (they cannot be mixed in one axes). Touching uniform bars
with integer heights, which is what `ax.hist()` draws, convert as a
native histogram when the bins reproduce exactly: shared uniform bins,
integer counts, first and last bins non-empty, and at most 100,000
samples. `ax.step()` and `plot(drawstyle='steps-pre'|'steps-mid'|
'steps-post')` convert as step lines (`'steps'` is accepted as
`'steps-pre'`).
`fill_between()`/`stackplot()` shaded bands (including `where=` splits,
`step=` boundaries, and constant baselines such as `fill_between(x, y, 0)`)
and `axvspan()`/`axhspan()` full-height/width strips, drawn under the
series; linear and base-10 log scales; tick direction/length,
`MultipleLocator` steps, `%.Nf`/`{x:.Nf}` decimals, minor ticks; spines,
grid, legend (standard `loc`s), title (any `loc`), `ax.text` notes.

Heatmaps: one `imshow()`/`matshow()` image or one uniform, flat
`pcolormesh()` grid, with a linear colour norm, a common colormap from a
fixed list (`viridis`, `plasma`, `inferno`, `magma`, `cividis`, `gray`,
the `Blues`/`Greens`/`Reds`/`Greys`/`Oranges`/`Purples` family,
`YlOrRd`, `YlGnBu`, `RdBu`, `coolwarm`, `bwr`, `seismic`, `Spectral`,
`PiYG`, `PRGn`, `BrBG`, `hot`, `turbo`, `jet`, each also in its `_r`
form), and optionally its own vertical colourbar with a label. An image
with the default interpolation (`'auto'`/`'antialiased'`) converts when
it renders as nearest-neighbour, that is when it is upsampled by more
than 3× along both axes; otherwise pass `interpolation='nearest'`.
Blank or masked cells stay blank.

### Not supported (→ reasons)

Subplots/twin/inset/colorbar axes (a heatmap's own colourbar is the
exception); polar/3D; negative bars; bars mixed with line/scatter
series or with each other across orientations; histograms that cannot
be reproduced exactly (density or weighted counts, `histtype='step'`,
non-uniform or mismatched bin edges, empty first or last bins, more
than 100,000 samples), and touching bars with non-integer heights;
boxplot and violinplot; colormapped or multi-size `scatter`; `xerr`;
`annotate` arrows; rotated text; date/unit axes other than string
categories; symlog/logit; `fill_betweenx`, partial-height/width spans
(`axvspan(ymin=…)`/`axhspan(xmin=…)`), hatched or unrecognised fill
polygons and other collections; heatmaps with a non-linear norm, custom
tick positions, RGB(A) data, image alpha, horizontal or extended
colourbars, or non-flat or non-uniform `pcolormesh` grids; figure-level
texts/legends; custom dash patterns/transforms/handles.

Band documents carry a `bands` array (`x`, `y1`, `y2` boundaries of
equal length, `color`, `label`, `id`) and stamp `requires: ["bands"]`,
so older readers raise the friendly capability error instead of
silently dropping the shading. Series error bars can likewise render
as a shaded band: `LineSeries.error_style='band'` (drawn in the series
colour at `error_alpha` opacity, default 0.3) stamps
`requires: ["error_band"]`. Span documents carry a `spans` array
(`axis` `'x'`/`'y'`, finite `lo`/`hi` with `lo < hi`, `color`, `label`,
`id`) and stamp `requires: ["spans"]`; spans render below bands at
zorder 0.9 with gid `ilmplot-span-<id>`, and their data extent is
clipped to the final view limits.

Step lines stamp `requires: ["step_lines"]`, and heatmaps stamp
`requires: ["heatmap"]` and use `kind: "heatmap"`.

The strict legacy API is kept: `ilmplot.bridge.document_from_figure(fig)`
and `ilmplot.bridge.export_figure(fig, path)` raise
`UnsupportedFigureError` on any unsupported feature.

### Compatibility

Documents that use the `heatmap` kind or capability, or the `step_lines`
capability, need ilmplot ≥ 0.1.1 (and a current ILM) to open. Older
readers refuse them with the usual capability error that names the
missing feature; they never silently drop the data.

## Layout

`document` — schema + strict parsing; `render` — deterministic
matplotlib SVG renderer; `stats`, `mathtext` — helpers; `bridge` — the
matplotlib bridge; `messages` — host-translatable error strings.

## Tests

```sh
PYTHONPATH=packages/ilmplot/src python -m unittest discover -s packages/ilmplot/tests
```
