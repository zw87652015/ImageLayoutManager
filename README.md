# ImageLayoutManager

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
  PDF and raster exports are designed to match the on-canvas layout and label placement.
- **Vector image import (SVG)**
  SVG can be placed into cells and will render as vector graphics in PDF export.
- **Label editing**
  Labels are editable per-item. Label color can be applied to a single label, or synced to all labels in the same group via an explicit “Apply to All” button.

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

## File types

- Layout files are stored as `*.figlayout` (ignored by default in `.gitignore` in this repo).
- Supported image imports include common raster formats (PNG/JPG/TIFF/...) and SVG.
- Exports include:
  - `*.pdf`
  - `*.tif` / `*.tiff`
  - `*.jpg` / `*.jpeg`

Notes:

- **DPI** mainly affects raster exports (TIFF/JPG) by controlling output pixel dimensions.
- PDF export is page-size based; DPI affects internal rendering resolution but not the intended physical layout size.

## License

MIT License. See `LICENSE`.
