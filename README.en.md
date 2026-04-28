# ImageLayoutManager

[中文说明](README.md)

Academic Image Layout Manager.

## Overview

ImageLayoutManager is a PyQt6 desktop tool for producing consistent, publication-ready multi-panel figures with repeatable spacing, alignment, labels, and export.

## What you can do with it

- **Assemble multi-panel figures**
  Place multiple images into a single layout with consistent margins and gaps.
- **Keep layouts reproducible**
  Save and re-open layout definitions so a figure can be regenerated later.
- **Export for papers and reports**
  Export layouts to common formats suitable for academic writing workflows.

Additional highlights:

- **Hierarchical cell splitting**
  Split cells infinitely in vertical or horizontal stacks with proportional sizing. Label cells can be added above sub-cell groups without disrupting the layout.
- **WYSIWYG export**
  PDF, raster, and SVG exports match the on-canvas layout and label placement exactly.
- **Vector image import (SVG)**
  SVG can be placed into cells and renders as vector graphics in PDF and SVG export.
- **Label editing**
  Labels are editable per-item. Label color can be applied to a single label, or synced to all labels in the same group via an explicit “Apply to All” button.
- **Portable project bundles (.figpack)**
  Pack a project and all its referenced images into a single portable `.figpack` file. Share it with collaborators without worrying about broken image paths.
- **File locking**
  Opening a project file locks it so the same file cannot be opened twice — in the same instance or in a separate one — preventing accidental concurrent edits.

## Downloads

Pre-built binaries are attached to each [GitHub Release](../../releases).

| File | Platform | Notes |
|---|---|---|
| `ImageLayoutManager_version_Setup.exe` | Windows | **Recommended.** Installer build — extracts once on install, opens instantly every launch. |
| `ImageLayoutManager_version.exe` | Windows | Portable single-file build — no installation needed, but takes 5-10 s to open on every launch while it self-extracts. |
| `ImageLayoutManager_version.zip` | macOS | App bundle — unzip and move to Applications. |

## Getting started

### Prerequisites

- Python 3.9+ recommended
- Qt/PyQt6 runtime via pip

### Install

This repository may be used in two common ways:

1. **Run from source** (recommended during development)
2. **Package/installer build** (if the project provides one)

Install dependencies:

```bash
pip install -r requirements.txt
```

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
```

### Access

After installing the Windows version, the CLI is available via:
- **Start Menu**: "ImageLayoutManager CLI (shell)" — opens a PowerShell pre-configured with the CLI in PATH
- **Installation directory**: `C:\Program Files\ImageLayoutManager\imagelayout-cli.exe`

Run `imagelayout-cli.exe --help` for full usage information.

## File types

### Project files

| Extension | Description |
|---|---|
| `*.figlayout` | Default project format. A JSON file that stores the layout; image files are referenced by path and stay separate. Lightweight and VCS-friendly. |
| `*.figpack` | Portable bundle format. A ZIP archive containing the layout JSON and all referenced images. Use **File → Convert to .figpack…** to bundle an open `.figlayout` project. Ideal for sharing or archiving a completed figure. |

When a project file is open, a hidden presence file (`~$filename`) is written next to it. If you try to open the same file in another instance, the app will refuse and show the owner's username. The lock is released automatically when the tab is closed.

### Image import

Supported raster formats: PNG, JPG, TIFF, BMP, GIF, WebP.  
SVG files are also supported and render as vector graphics in PDF and SVG export.

### Export formats

| Format | Notes |
|---|---|
| `*.pdf` | Vector text; images embedded at project DPI. |
| `*.tif` / `*.tiff` | Raster; output pixel dimensions = physical size × DPI. |
| `*.jpg` / `*.jpeg` | Raster; same as TIFF but lossy. |
| `*.png` | Raster; lossless. |
| `*.svg` | Vector; text and layout are vector; raster images are embedded. |

**DPI** controls output pixel dimensions for raster exports and the internal rendering resolution for PDF. It does not affect physical layout size.

## Support

If you find this project useful and would like to support its development, you can buy me a coffee via Alipay:

<img src="assets/Alipay.jpg" alt="Alipay QR code" width="200"/>

## License

Apache-2.0 license. See `LICENSE`.
