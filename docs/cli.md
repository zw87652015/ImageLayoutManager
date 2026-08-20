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
| `edit`    | Mutate a project headlessly — create rows, import images, label, lay out |

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

## `edit` — headless authoring

`edit` applies the *same* operations the AI assistant uses (see
[`agent_concepts.md`](agent_concepts.md) for what each tool means and how
rows / cells / labels relate) to a file, with no GUI and no MCP host
running. It is
the scriptable half of the app: everything the tool registry exposes —
rows, cells, splits, image import, labels, group labels, size groups,
PiPs, export regions, auto-layout — is reachable from a shell or CI job.

```powershell
# What can I call?
imagelayout-cli.exe edit --list-tools

# Label every panel, overwriting the input (written atomically)
imagelayout-cli.exe edit figure_4.figlayout --in-place `
    --call auto_label_cells '{"scheme": "(a)"}'

# Build a figure from scratch, then render it
imagelayout-cli.exe edit --new -o figure_5.figlayout `
    --call row_add '{"position": 2, "column_count": 3}'
imagelayout-cli.exe render figure_5.figlayout -f pdf

# Batch of steps from a file, packed straight into a bundle
imagelayout-cli.exe edit figure_4.figlayout -o figure_4.figpack --script ops.json

# Machine-readable report of every step
imagelayout-cli.exe edit figure_4.figlayout --dry-run --json `
    --call project_describe
```

`ops.json` is an ordered step list — a bare array, or `{"steps": [...]}`:

```json
[
  { "tool": "image_import", "params": { "cell_id": "…", "path": "C:/data/a.png" } },
  { "tool": "auto_layout" },
  { "tool": "auto_label_cells", "params": { "scheme": "(a)" } }
]
```

Pass `--script -` to read it from stdin.

### Contract

- **Ordered.** `--script` steps run first, then each `--call` in
  command-line order.
- **All-or-nothing.** A failing step aborts before anything is written, so
  the input file is left exactly as it was. `--keep-going` applies the
  remaining steps and still writes, but the exit code stays `1`.
- **Atomic.** `--in-place` and every `.figlayout` / `.json` write commit
  through a temp file + rename; an interrupted run cannot truncate your
  only copy.
- **Pipeable.** Per-step progress goes to **stderr**; **stdout** carries
  only the output path (or the `--json` report, or the project JSON with
  `-o -`).
- **`.figpack` output** is supported (`-o out.figpack`); `.figpack`
  *input* is not — `unpack` it first, edit the `.figlayout`, then `pack`.
  A bundle's images live in a temporary extraction, so editing one
  in place would re-resolve assets from paths that may not exist on this
  machine.

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
