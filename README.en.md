# ImageLayoutManager

[中文说明](README.md)

Academic Image Layout Manager.

## Overview

ImageLayoutManager is a PyQt6 desktop tool for producing consistent, publication-ready multi-panel figures with repeatable spacing, alignment, labels, and export.

<img width="2024" height="1318" alt="image" src="https://github.com/user-attachments/assets/33d3f481-5525-4da1-9084-401e297dfc7c" />


## AI-driven figure composition

Connect Claude Desktop, Claude Code, Cursor, Windsurf, or any other MCP host to ILM and let the AI compose your figure from a folder of images.

![MCP workflow](docs/MCP-screenshot.png)

See [docs/mcp_setup.md](docs/mcp_setup.md) for setup. Inside the app: **Tools → MCP Setup Guide…** has a one-click "Auto Register…" for the major hosts.


## What you can do with it

- **Grid and freeform layouts**
  Arrange panels with consistent margins and gaps, split cells into nested rows or columns, or position panels freely and reorder them in the Layers panel.
- **Editable scientific plots**
  Create line, scatter, violin, ridgeline and column plots in the bundled ILM Plot Editor. Save the data, settings and vector image together as `*.ilmplot.svg`.
- **Plot alignment**
  Mark the plot areas inside imported panels, then match their heights and baselines while preserving image proportions.
- **Consistent typography**
  New projects use real final-figure points for labels, titles, annotations and scale-bar text. Match selected text sizes across SVG and raster panels without modifying the source files; raster text detection uses the bundled OCR backend.
- **Labels, scale bars and insets**
  Add panel numbering, shared labels, scale bars and picture-in-picture (PiP) insets. Edit individual labels or explicitly apply their style to the whole group.
- **Image and clipboard import**
  Drag in images or folders, or paste images and text from the clipboard. Work with raster images, SVG and PDF panels.
- **Publication exports**
  Export PDF, SVG, TIFF, PNG and JPEG with physical page dimensions and configurable raster DPI.
- **Portable projects**
  Keep a lightweight `.figlayout` project or bundle the layout and referenced images into one `.figpack` for sharing. File locking helps prevent concurrent edits.
- **Guided tutorials**
  Learn layout, annotation, text sizing, plot alignment and native-plot Reflow in practice projects. The Plot Editor also has its own guided lessons.
- **AI/MCP-assisted figure editing**
  Connect Claude Desktop, Claude Code, Cursor, Windsurf, Cline, or another MCP host to the running app. AI can build layouts, import images, style labels/text, crop/rotate/pad panels, add scale bars and PiP insets, manage size groups, set export regions, request screenshots, and save/export projects.

## Downloads

Windows users can install ImageLayoutManager from the [Microsoft Store](https://apps.microsoft.com/detail/9NGNW4D8L5QH). Updates are delivered through the Store.

Pre-built binaries are attached to each [GitHub Release](../../releases).

| File | Platform | Notes |
|---|---|---|
| `ImageLayoutManager_version_Setup.exe` | Windows | Standalone installer; extracts files once during installation. |
| `ImageLayoutManager_version.exe` | Windows | Portable single-file build; extracts files at each launch. |
| `ImageLayoutManager_<version>_macOS.zip` | macOS (Apple Silicon) | App bundle for Apple Silicon Macs — unzip and move to Applications. |
| `ImageLayoutManager_<version>_macOS_Intel.zip` | macOS (Intel) | App bundle for Intel Macs — unzip and move to Applications. |

Standalone Windows builds embed version, publisher, and Apache-2.0 copyright metadata in the installer, GUI executable, and CLI executable. Downloads from GitHub Releases may be unsigned and trigger Windows SmartScreen warnings; use the official release page and verify checksums when provided. Microsoft Store packages are signed by Microsoft during distribution. See the License section for the bundled dependencies' license terms.

Before upgrading an installed Windows build, close ImageLayoutManager and any AI host using MCP (Claude Desktop, Claude Code, Cursor, Windsurf, Cline, etc.). Those hosts can keep `imagelayout-cli.exe mcp` running in the background, which locks files under `_internal\PyQt6\` and can make the installer fail with "DeleteFile failed; code 5: Access is denied".

## Getting started

Pre-built downloads include the runtime; Python is only needed when running from source. From the repository root, create the provided Python 3.13 environment:

```bash
conda env create -f environment.yml
conda activate imagelayout
python main.py
```

Alternatively, use an activated Python 3.13 virtual environment:

```bash
python -m pip install -r requirements.txt
python main.py
```

Dependencies are pinned in [`requirements.txt`](requirements.txt); the Conda environment also includes PyInstaller for packaging.

## Usage

Run the app:

```bash
python main.py
```

Typical workflow:

1. **Create a new layout**
2. **Add images** to cells
3. **Split cells** into sub-cells via right-click menu (vertical/horizontal stacks with adjustable ratios)
4. **Adjust spacing/alignment** and sub-cell size ratios in the inspector
5. **Save the layout** (so it can be reproduced)
6. **Export** to the target format

## Command-line interface (CLI)

A headless CLI tool (`imagelayout-cli.exe`) is included with the Windows installer for automated workflows. It provides pixel-perfect output parity with the GUI export functions.

### Verbs

| Verb      | Purpose                                                         |
| --------- | --------------------------------------------------------------- |
| `render`  | `.figpack` / `.figlayout` → `pdf` / `tiff` / `jpg` / `png`      |
| `pack`    | `.figlayout` → `.figpack` (bundle layout + referenced assets)   |
| `unpack`  | `.figpack` → folder containing assets + sidecar `.figlayout`    |
| `inspect` | Print page size, DPI, cell counts, etc. (text or `--json`)      |
| `edit`    | Mutate a project headlessly — rows, images, labels, auto-layout  |
| `mcp`     | Stdio MCP adapter for AI hosts; proxies tools to the running GUI |

### Examples

```powershell
# Pixel-perfect PDF render at the project's saved DPI
imagelayout-cli.exe render figure_4.figpack -f pdf -o figure_4.pdf

# Override DPI for a fast preview PNG
imagelayout-cli.exe render figure_4.figlayout -f png --dpi 150

# Print-ready CMYK TIFF using a specific ICC profile
imagelayout-cli.exe render figure_4.figpack -f tiff --cmyk `
    --icc-profile "C:\ICC\USWebCoatedSWOP.icc" --icc-intent 1 -o fig.tiff

# Bundle a .figlayout + every referenced image into a .figpack
imagelayout-cli.exe pack figure_4.figlayout -o figure_4.figpack

# Unpack a .figpack so you can edit the JSON / images by hand
imagelayout-cli.exe unpack figure_4.figpack -o ./extracted/

# Quick summary
imagelayout-cli.exe inspect figure_4.figpack
imagelayout-cli.exe inspect figure_4.figpack --json

# Edit without opening the GUI: label every panel in place
imagelayout-cli.exe edit figure_4.figlayout --in-place `
    --call auto_label_cells '{"scheme": "(a)"}'

# Build a figure from scratch, or replay a batch of steps from a file
imagelayout-cli.exe edit --new -o figure_5.figlayout --script ops.json
imagelayout-cli.exe edit --list-tools

# MCP adapter used by Claude/Cursor/Windsurf after enabling MCP Server in the GUI
imagelayout-cli.exe mcp
```

`edit` runs the same operations the AI assistant uses, so every scripted
step behaves exactly like the equivalent GUI action. A failing step aborts
before anything is written, and `--in-place` writes atomically. See
[`docs/cli.md`](docs/cli.md) for the full contract.

For setup instructions, see [`docs/mcp_setup.md`](docs/mcp_setup.md). After upgrading, restart both ImageLayoutManager and your AI host so the GUI server and `imagelayout-cli.exe mcp` load the same tool list. If the installer reports a locked `.pyd` file, fully quit the AI host or stop any remaining `imagelayout-cli.exe` process, then run the installer again.

### Access

For the standalone Windows installer, the CLI is available via:

- **Start Menu**: "ImageLayoutManager CLI (shell)" — opens a PowerShell pre-configured with the CLI in PATH
- **Installation directory**: `C:\Program Files\ImageLayoutManager\imagelayout-cli.exe`

Run `imagelayout-cli.exe --help` for full usage information. From source, use `python cli_main.py --help` and replace `imagelayout-cli.exe` in the examples with `python cli_main.py`. The macOS app bundle includes the CLI at `ImageLayoutManager.app/Contents/MacOS/imagelayout-cli`.

## File types

### Project files

| Extension | Description |
|---|---|
| `*.figlayout` | Default project format. A JSON file that stores the layout; image files are referenced by path and stay separate. Lightweight and VCS-friendly. |
| `*.figpack` | Portable bundle format. A ZIP archive containing the layout JSON and all referenced images. Use **File → Convert to .figpack…** to bundle an open `.figlayout` project. Ideal for sharing or archiving a completed figure. |

Projects saved by 3.5.1 require ImageLayoutManager 3.5.1 or later. Older projects remain readable and retain their original layout and text-sizing behavior; keep an original copy if you need to return to an older version.

When a project file is open, a hidden presence file (`~$filename`) is written next to it. If you try to open the same file in another instance, the app will refuse and show the owner's username. The lock is released automatically when the tab is closed.

### Image import

Supported raster formats: PNG, JPG, TIFF, BMP, GIF, WebP.  
SVG and PDF panels are also supported. Native `*.ilmplot.svg` files can be reopened in the Plot Editor.

### Export formats

| Format | Notes |
|---|---|
| `*.pdf` | Vector text; images embedded at project DPI. |
| `*.tif` / `*.tiff` | Raster; output pixel dimensions = physical size × DPI. |
| `*.jpg` / `*.jpeg` | Raster; same as TIFF but lossy. |
| `*.png` | Raster; lossless. |
| `*.svg` | Vector; text and layout are vector; raster images are embedded. |

**DPI** controls output pixel dimensions for raster exports and the internal rendering resolution for PDF. It does not affect physical layout size.

## Editable plots

Version 3.5.1 includes the **ILM Plot Editor**, a separate window with a worksheet and plot preview. Open it from the Welcome window, **File → Open Plot Editor**, or an empty cell's context menu via **New .ilmplot.svg**. Double-click a native plot cell or choose **Edit Plot…** to edit an existing plot.

- **Chart types:** line, scatter, line + scatter, stacked line, ridgeline, violin, column, stacked column and 100% stacked column.
- **Data:** import CSV, TSV, TXT or Excel (`.xlsx`), drag files into the editor, or paste into the worksheet. Y error columns support symmetric and asymmetric error bars on line/scatter and ordinary column plots.
- **Styling:** double-click plot elements to edit them; add free text and significance brackets, choose or create colour themes, and reuse style presets.
- **Save:** `*.ilmplot.svg` keeps the vector snapshot, plot data and settings in one file. It can be used as an ordinary SVG and included in a `.figpack`.

Native plots keep their saved SVG appearance when first placed in ILM. Enable **REFLOW ON** in the Inspector or cell context menu to adapt the plot to the cell while keeping text and line widths at their true point sizes. Locking the cell's aspect ratio pauses Reflow.

To launch the editor directly from source:

```bash
python plot_editor_main.py
```

## Build a Windows Store package (MSIX)

Use a Windows x64 environment with the project dependencies and PyInstaller installed. Activate the `imagelayout` Conda environment and run these commands from the repository root in PowerShell. Set `$makeappx` to an existing x64 `MakeAppx.exe` from the Windows SDK or the `Microsoft.Windows.SDK.BuildTools` package.

```powershell
conda activate imagelayout
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$candidate = "build\store-candidate-$stamp"
$output = "dist\msix-$stamp"
$makeappx = "C:\path\to\x64\makeappx.exe"

python build_installer_windows.py --onedir-only --output-root $candidate
if ($LASTEXITCODE -ne 0) { throw "Onedir build failed" }

python build_msix.py `
    --bundle "$candidate\dist\ImageLayoutManager" `
    --output $output `
    --identity-name "RiverQuasar.ImageLayoutManager" `
    --publisher "CN=3A918967-921B-4748-8927-958534864D92" `
    --publisher-display-name "River Quasar" `
    --makeappx $makeappx
if ($LASTEXITCODE -ne 0) { throw "MSIX packaging failed" }
```

The first command creates an isolated bundle containing the GUI and CLI without invoking Inno Setup. Both output directories must be new; existing builds are preserved. The second command creates `$output\ImageLayoutManager-<version>-x64.msix` (for application version 3.5.1, the package version is 3.5.1.0). Upload that `.msix` file in Partner Center for this app. The local package is unsigned; Microsoft signs Store packages. Omitting `--makeappx` creates only a layout directory, not an MSIX.

The Store identity above belongs to this app; use your own registered identity for a separately published fork. Build outputs under `build/` and `dist/` are Git-ignored. Downloaded dependency sources are not automatically included in the MSIX. The generated license manifest currently records `source_status: incomplete`; successful packaging does not complete the outstanding source verification and publication work.

## License

The source code is licensed under Apache-2.0. See `LICENSE`.

**Note on pre-built binaries:** the official binaries bundle PyQt6 (GPL v3) and PyMuPDF (AGPL-3.0). As a combined work, the distributed binaries are governed by GPL v3 / AGPL-3.0 terms in addition to Apache-2.0. If you redistribute the binaries — or ship your own build that includes these components — you must comply with those licenses, or obtain commercial licenses from Riverbank Computing (PyQt6) and Artifex Software (PyMuPDF). See `NOTICE` for the full third-party list. Use **About → Licenses and source…** to read bundled notices offline. [`SOURCES.md`](SOURCES.md) lists corresponding-source locations and their recorded verification status; [`NOTICE`](NOTICE) lists third-party notices.
