# `imagelayout-cli`

Headless driver for ImageLayoutManager. Same renderer as the GUI's
`File → Export`, no display server required.

## Verbs

| Verb      | Purpose                                                         |
| --------- | --------------------------------------------------------------- |
| `render`  | `.figpack` / `.figlayout` → `pdf` / `tiff` / `jpg` / `png`      |
| `pack`    | `.figlayout` → `.figpack` (bundle layout + referenced assets)   |
| `unpack`  | `.figpack` → folder containing assets + sidecar `.figlayout`    |
| `inspect` | Print page size, DPI, cell counts, etc. (text or `--json`)      |

## Examples

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

## Exit codes

| Code | Meaning                                            |
| ---- | -------------------------------------------------- |
| 0    | Success                                            |
| 1    | User-facing error (bad path, unknown format, etc.) |
| 2    | Argparse usage error                               |
| 3    | Bundle integrity / security failure                |
| 4    | Unexpected internal error                          |
| 130  | Interrupted (Ctrl+C)                               |

Set `IMAGELAYOUT_CLI_DEBUG=1` to print full tracebacks on exit-4 errors.

## Output parity

`render` reuses the same `PdfExporter` / `ImageExporter` classes as
`File → Export` — labels, scale bars, PiPs, rotated text, vector PDF
stamping, CMYK ICC conversion all behave identically.

### Platform plugin

To preserve text rendering parity with the GUI the CLI uses the
*native* Qt platform plugin on Windows and macOS (`windows` /
`cocoa`). The native plugin is the only one that initialises the OS
font database (DirectWrite on Windows, Core Text on macOS); the
`offscreen` plugin on Windows ships without a font directory and
renders every glyph as a filled rectangle (tofu). No window is ever
shown — `QPdfWriter` / `QImage` paint to a paint device, not a
window — so the native plugin behaves like a headless renderer in
practice.

On Linux the CLI defaults to `offscreen`, which uses fontconfig
(the system font db) and works without a `DISPLAY` (CI, SSH, Docker).

You can override the choice with `QT_QPA_PLATFORM` in the environment
if you need to (e.g. running under a Windows service account with no
GDI access — accept that text will tofu).

## Installation

The Windows installer (`ImageLayoutManager_Setup.exe`, produced by
`build_installer_windows.py`) ships `imagelayout-cli.exe` next to the
GUI exe. After install:

```powershell
"C:\Program Files\ImageLayoutManager\imagelayout-cli.exe" --help
```

Or use the **ImageLayoutManager CLI (shell)** Start Menu entry, which
opens `cmd.exe` in the install directory with `imagelayout-cli --help`
already executed — from there you can run any verb without typing the
full path.

To call `imagelayout-cli` from any shell, add the install directory to
`PATH` manually (System Properties → Environment Variables) — the
installer deliberately does **not** modify `PATH` to avoid surprising
existing user customisations.

## Building

Dev runs (no install needed):

```powershell
python cli_main.py inspect path\to\file.figpack
```

Standalone CLI binary (without the GUI installer):

```powershell
pyinstaller --noconfirm imagelayout-cli.spec
# → dist\imagelayout-cli\imagelayout-cli.exe
```

Combined GUI + CLI installer:

```powershell
python build_installer_windows.py
# → dist\ImageLayoutManager_Setup.exe   (contains both exes)
```

Both specs exclude Qt modules the app doesn't need (`QtNetwork`,
`QtMultimedia`, `QtWebEngine*`, `Qt3D*`, `QtQml`, `QtQuick*`, …) but
include matplotlib + numpy because `$...$` LaTeX math depends on them.
