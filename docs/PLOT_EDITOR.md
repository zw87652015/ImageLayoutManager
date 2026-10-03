# ILM Plot Editor · ILM 图表编辑器

A small companion editor for **editable line plots** that live inside your
ILM figures. It is bundled with ImageLayoutManager (Start Menu shortcut
"ILM Plot Editor") and also runs from source:

```bash
python plot_editor_main.py [file.ilmplot.svg]
# or, from any launch of the app:
python main.py --plot-editor [file.ilmplot.svg]
```

它是随 ImageLayoutManager 一起安装的轻量编辑器，用于创建和编辑
**可编辑折线图**。也可以在 ILM 内：File → New Plot… / Open Plot Editor，
或双击/右键可编辑的图表面板选择 Edit Plot…。

## File format · 文件格式

The native document is a self-contained SVG named `*.ilmplot.svg`. It is a
standard SVG — usable anywhere an image is expected — with a versioned JSON
payload embedded in `<metadata id="ilm-plot-document">` that carries every
editable field (data, labels, sizes, styles). One file is both the vector
snapshot and the editable source of truth, so ordinary `.figpack` bundling,
plain project saves and source export need nothing extra.

本机文档是一个自包含的 `*.ilmplot.svg`：标准 SVG 图像内嵌
`<metadata id="ilm-plot-document">` 中的 JSON 文档。同一份文件既是矢量
快照又是可编辑数据；`.figpack` 打包、普通 `.figlayout` 保存和源文件导出
都无需额外处理。普通 SVG 照常显示；带无法识别/未来版本元数据的文件
仍可显示，只是不能在编辑器中打开。

- **Immutability · 不可变性** — Applying an edit in ILM writes a *new*
  content-addressed file under the persistent `plot_documents` store;
  the original source bytes are never modified, so undo/redo is safe.
  在 ILM 中应用编辑会生成新的按内容寻址的文件，原始文件不会被修改，
  撤销/重做始终安全。
- **Physical typography · 物理字号** — When a native plot is placed in a
  figure, ILM re-renders it so `font_size_pt` / line widths are *real*
  final-figure points at any panel size, crop or rotation. The axes occupy
  a fixed normalized rectangle (`axes_rect`) so alignment markers stay
  valid; margins are not reflowed.
  面板缩放时 ILM 会按实际面板尺寸重新渲染，使字号/线宽等于真实磅值；
  坐标轴占固定的归一化矩形以保证对齐标记有效。

## Scope · 范围

One plot type for now: **line series on a single rectilinear axes**
(linear scales only). Supported per-series styles: color, line width,
`-`/`--`/`-.`/`:`/none, markers `o s ^ v D + x .`, marker size, label.
Document-level: title, axis labels, width/height (mm), font family/size,
title size, X/Y limits (auto or explicit, inverted allowed), legend
(11 standard positions), grid. CSV/TSV data per series (optional header
row), imported from file or pasted into the data editor.

目前仅支持一种图表：单一直角坐标系上的折线序列（仅线性刻度）。
数据为两列 CSV/TSV（可含表头）。

## Generating plots from code · 用代码生成图表

AI agents and scripts can produce editable plots directly — no `.py`
scripts are ever executed by the GUI:

```python
import matplotlib.pyplot as plt
from src.plot_editor.matplotlib_bridge import export_figure

fig, ax = plt.subplots()
ax.plot([0, 1, 2], [0, 1, .5], label='Control')
ax.set(xlabel='Time (s)', ylabel='Response')
ax.legend()
export_figure(fig, 'response.ilmplot.svg')
```

The bridge is plain source — run it with this repository on
``PYTHONPATH`` (or from the repo root). There is no pip-installable
package.

`export_figure` performs a *supported-data/style* import: it captures data,
colors, styles, labels and linear limits exactly, but normalizes margins,
tick formatting and legend chrome — it is **not** a pixel-identical
reconstruction. Figures using unsupported features (scatter/errorbar
artists, images, annotations, extra axes, categorical/date/unit data,
custom transforms or dash patterns) raise `UnsupportedFigureError` before
anything is written; export those as ordinary SVG for display instead.
`from src.plot_editor.matplotlib_bridge import document_from_figure` gives
the document without writing.

## Editing workflow · 编辑流程

- **ILM:** File → *New Plot…* targets the selected leaf cell (or the first
  empty one). *Edit Plot…* appears in the context menu of a native plot
  cell, and double-clicking the cell opens it. "Apply to Figure" writes
  one undo step; Cancel discards the draft.
- **Standalone:** `plot_editor_main.py` / the Start Menu shortcut opens an
  independent window with New/Open/Save/Save As, undo/redo, live SVG
  preview, English/中文 and light/dark controls.
