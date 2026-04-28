"""``imagelayout-cli`` — headless driver for ImageLayoutManager.

Verbs (v1):

    render   .figpack | .figlayout | .json   ->  pdf | tiff | jpg | png
    pack     .figlayout                       ->  .figpack
    unpack   .figpack                         ->  <dir>/<name>.figlayout + <dir>/<name>_assets/
    inspect  .figpack | .figlayout | .json    ->  human-readable summary on stdout

Output parity with the GUI is intentional: every verb that produces a
rendered figure goes through the same ``PdfExporter`` /
``ImageExporter`` the GUI uses, instantiated on a Qt offscreen
platform plugin. Anything the GUI shows in File > Export — labels,
scale bars, PiPs, rotated text, vector PDF stamping, CMYK ICC — works
here too.

Exit codes
----------
    0  success
    1  user-facing error (bad path, unknown format, etc.)
    2  argparse usage error
    3  bundle integrity / security failure
    4  unexpected internal error
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import sys
import traceback
from typing import List, Optional, Tuple


# ---------------------------------------------------------------------------
# Lazy Qt bootstrap
# ---------------------------------------------------------------------------
#
# We avoid importing Qt at module load — verbs like ``inspect``,
# ``pack`` and ``unpack`` don't need it, so a 200 ms QApplication
# spin-up would just be dead weight. ``_ensure_qapp()`` is called by
# the verbs that actually paint pixels (only ``render`` today).

_QAPP = None  # type: ignore[var-annotated]


def _ensure_qapp():
    """Create a singleton ``QApplication`` for headless rendering.

    Platform-plugin selection is deliberate and load-bearing for
    output correctness:

    * **Windows / macOS** — use the *native* platform plugin
      (``windows`` / ``cocoa``). The native plugin is what the GUI
      build uses, and crucially it's the only thing that initialises
      the OS font database (DirectWrite on Windows, Core Text on
      macOS). The ``offscreen`` plugin on Windows ships with no font
      directory of its own and produces tofu (every glyph rendered as
      a filled rectangle) for any text. We never call
      ``.show()`` on a widget, so no window actually appears — the
      native plugin behaves exactly like a headless renderer in
      practice.
    * **Linux** — default to ``offscreen`` so the CLI works without a
      DISPLAY (CI, SSH, Docker). On Linux the offscreen plugin uses
      fontconfig, which is itself the system font database, so text
      renders correctly.

    Users who really need offscreen on Windows (e.g. running under a
    service account with no GDI access) can still set
    ``QT_QPA_PLATFORM=offscreen`` in the environment to override.
    """
    global _QAPP
    if _QAPP is not None:
        return _QAPP

    # Pick a default platform only when the user hasn't already chosen
    # one via the environment. ``setdefault`` preserves any explicit
    # override.
    if sys.platform.startswith("linux"):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    # Windows + macOS: leave QT_QPA_PLATFORM unset so Qt picks the
    # native plugin and inherits the OS font database.

    from PyQt6.QtWidgets import QApplication  # noqa: WPS433

    _QAPP = QApplication.instance() or QApplication(["imagelayout-cli"])
    return _QAPP


# ---------------------------------------------------------------------------
# Project loading — handles .figpack, .figlayout and .json transparently
# ---------------------------------------------------------------------------

def _load_project(path: str):
    """Load a project from any supported container.

    Returns ``(project, workdir)`` where ``workdir`` is a
    :class:`figpack.WorkingDir` for ``.figpack`` inputs (caller is
    responsible for releasing it on exit), or ``None`` for plain
    JSON inputs.
    """
    if not os.path.isfile(path):
        raise SystemExit(f"error: file not found: {path}")

    ext = os.path.splitext(path)[1].lower()
    if ext == ".figpack":
        # Bundle: extract into a working dir, then build a Project from
        # the resolved project_data (image_paths already point inside
        # the workdir, so the exporter can read them as ordinary files).
        from src.utils.figpack import open_bundle, BundleError
        from src.model.data_model import Project
        try:
            workdir, result = open_bundle(path)
        except BundleError as e:
            raise SystemExit(f"error: bundle open failed: {e}") from e
        try:
            project = Project.from_dict(result.project_data, workdir.path)
            # Match GUI behaviour: derive name from the .figpack filename.
            project.name = os.path.splitext(os.path.basename(path))[0]
            return project, workdir
        except Exception:
            workdir.release()
            raise
    elif ext in (".figlayout", ".json"):
        from src.model.data_model import Project
        return Project.load_from_file(path), None
    else:
        raise SystemExit(
            f"error: unsupported input extension '{ext}' "
            "(want .figpack, .figlayout, or .json)"
        )


# ---------------------------------------------------------------------------
# render
# ---------------------------------------------------------------------------

_RENDER_FORMATS = {"pdf", "tiff", "tif", "jpg", "jpeg", "png"}


def _cmd_render(args: argparse.Namespace) -> int:
    fmt = args.format.lower()
    if fmt not in _RENDER_FORMATS:
        raise SystemExit(f"error: unknown --format '{args.format}'")

    _ensure_qapp()
    project, workdir = _load_project(args.input)
    try:
        # User-supplied DPI override (defaults to project setting).
        if args.dpi is not None:
            project.dpi = int(args.dpi)

        out = args.output or _default_render_output(args.input, fmt)
        os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)

        # The GUI exporters print diagnostic ``DEBUG: ...`` lines via
        # ``print(...)`` (see pdf_exporter.py / image_exporter.py).
        # In a CLI context they're noise on stdout that breaks shell
        # composition (``imagelayout-cli render ... | xargs ...``
        # would receive the debug lines, not just the output path).
        # Capture them into a buffer; replay to stderr only when
        # --verbose is set.
        debug_buf: "io.StringIO" = io.StringIO()
        capture = contextlib.redirect_stdout(debug_buf) if not args.verbose \
            else contextlib.nullcontext()
        with capture:
            if fmt == "pdf":
                from src.export.pdf_exporter import PdfExporter
                PdfExporter.export(project, out)
            else:
                # Normalise to the format string the exporter expects.
                fmt_kw = {"tif": "TIFF", "tiff": "TIFF",
                          "jpg": "JPG", "jpeg": "JPG", "png": "PNG"}[fmt]
                from src.export.image_exporter import ImageExporter
                color_mode = (args.cmyk and "cmyk") or "rgb"
                ImageExporter.export(
                    project, out, fmt_kw,
                    color_mode=color_mode,
                    icc_profile_path=args.icc_profile,
                    rendering_intent=args.icc_intent,
                )

        if args.verbose and debug_buf.getvalue():
            sys.stderr.write(debug_buf.getvalue())

        sys.stdout.write(f"{out}\n")
        sys.stdout.flush()
        return 0
    finally:
        if workdir is not None:
            try:
                workdir.release()
            except Exception:
                pass


def _default_render_output(input_path: str, fmt: str) -> str:
    base = os.path.splitext(os.path.basename(input_path))[0]
    ext = {"jpeg": "jpg", "tif": "tiff"}.get(fmt, fmt)
    return os.path.join(os.path.dirname(os.path.abspath(input_path)),
                        f"{base}.{ext}")


# ---------------------------------------------------------------------------
# pack
# ---------------------------------------------------------------------------

def _cmd_pack(args: argparse.Namespace) -> int:
    src_ext = os.path.splitext(args.input)[1].lower()
    if src_ext not in (".figlayout", ".json"):
        raise SystemExit(
            f"error: 'pack' takes .figlayout/.json input (got {src_ext})"
        )

    from src.utils.figpack import pack_project, BundleError
    project, _ = _load_project(args.input)
    out = args.output or os.path.splitext(args.input)[0] + ".figpack"
    try:
        result = pack_project(project, out)
    except BundleError as e:
        raise SystemExit(f"error: pack failed: {e}") from e
    sys.stdout.write(
        f"{out}  ({result.asset_count} assets"
        + (f", {result.missing_count} missing" if result.missing_count else "")
        + ")\n"
    )
    return 0


# ---------------------------------------------------------------------------
# unpack
# ---------------------------------------------------------------------------

def _cmd_unpack(args: argparse.Namespace) -> int:
    if os.path.splitext(args.input)[1].lower() != ".figpack":
        raise SystemExit("error: 'unpack' takes a .figpack input")

    from src.utils.figpack import unpack_project, BundleError
    base = os.path.splitext(os.path.basename(args.input))[0]
    out_dir = args.output or os.path.join(
        os.path.dirname(os.path.abspath(args.input)), base
    )
    os.makedirs(out_dir, exist_ok=True)
    try:
        result = unpack_project(args.input, out_dir)
    except BundleError as e:
        raise SystemExit(f"error: unpack failed: {e}") from e

    # Write a sidecar .figlayout next to the extracted assets so the
    # output is immediately re-openable in the GUI without re-bundling.
    layout_path = os.path.join(out_dir, f"{base}.figlayout")
    with open(layout_path, "w", encoding="utf-8") as f:
        json.dump(result.project_data, f, indent=4)

    sys.stdout.write(
        f"{out_dir}  ({result.asset_count} assets, "
        f"layout: {os.path.basename(layout_path)})\n"
    )
    return 0


# ---------------------------------------------------------------------------
# inspect
# ---------------------------------------------------------------------------

def _cmd_inspect(args: argparse.Namespace) -> int:
    project, workdir = _load_project(args.input)
    try:
        if args.json:
            payload = {
                "name": project.name,
                "page_mm": [project.page_width_mm, project.page_height_mm],
                "dpi": project.dpi,
                "layout_mode": project.layout_mode,
                "rows": len(project.rows),
                "cells_total": len(project.get_all_leaf_cells()),
                "text_items": len(project.text_items),
                "size_groups": len(getattr(project, "size_groups", []) or []),
                "export_region":
                    project.export_region.to_dict()
                    if getattr(project, "export_region", None) else None,
            }
            json.dump(payload, sys.stdout, indent=2)
            sys.stdout.write("\n")
        else:
            leaves = project.get_all_leaf_cells()
            with_image = sum(1 for c in leaves if c.image_path)
            print(f"name        : {project.name}")
            print(f"page        : {project.page_width_mm} x {project.page_height_mm} mm")
            print(f"dpi         : {project.dpi}")
            print(f"layout_mode : {project.layout_mode}")
            print(f"rows        : {len(project.rows)}")
            print(f"cells       : {len(leaves)} ({with_image} with image)")
            print(f"text items  : {len(project.text_items)}")
            sgroups = getattr(project, "size_groups", []) or []
            if sgroups:
                print(f"size groups : {len(sgroups)}")
            if getattr(project, "export_region", None):
                r = project.export_region
                print(f"export rect : ({r.x_mm}, {r.y_mm}) {r.w_mm} x {r.h_mm} mm")
        return 0
    finally:
        if workdir is not None:
            try:
                workdir.release()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# argparse wiring
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="imagelayout-cli",
        description="Headless driver for ImageLayoutManager. "
                    "Renders, packs, unpacks and inspects figure projects.",
    )
    sub = p.add_subparsers(dest="cmd", required=True, metavar="COMMAND")

    # render -----------------------------------------------------------------
    r = sub.add_parser(
        "render",
        help="Render a project to PDF/TIFF/JPG/PNG (parity with GUI export).",
    )
    r.add_argument("input", help=".figpack, .figlayout or .json")
    r.add_argument("-f", "--format", required=True,
                   help="pdf | tiff | jpg | png")
    r.add_argument("-o", "--output",
                   help="Output path (default: <input_basename>.<fmt>)")
    r.add_argument("--dpi", type=int, default=None,
                   help="Override project DPI for raster formats.")
    r.add_argument("--cmyk", action="store_true",
                   help="(TIFF only) emit CMYK using the embedded ICC profile.")
    r.add_argument("--icc-profile", default=None,
                   help="(TIFF+CMYK) absolute path to a .icc/.icm profile.")
    r.add_argument("--icc-intent", type=int, default=1,
                   help="(TIFF+CMYK) PIL.ImageCms intent: 0=Perc, 1=RelCol, "
                        "2=Sat, 3=AbsCol (default 1).")
    r.add_argument("-v", "--verbose", action="store_true",
                   help="Replay exporter DEBUG lines + Qt warnings to stderr.")
    r.set_defaults(func=_cmd_render)

    # pack -------------------------------------------------------------------
    pk = sub.add_parser(
        "pack",
        help="Bundle a .figlayout + its referenced assets into a .figpack.",
    )
    pk.add_argument("input", help=".figlayout or .json")
    pk.add_argument("-o", "--output", help="Output .figpack path "
                                           "(default: <input>.figpack)")
    pk.set_defaults(func=_cmd_pack)

    # unpack -----------------------------------------------------------------
    up = sub.add_parser(
        "unpack",
        help="Extract a .figpack to a folder + sidecar .figlayout.",
    )
    up.add_argument("input", help=".figpack")
    up.add_argument("-o", "--output",
                    help="Target directory (default: <input_basename>/)")
    up.set_defaults(func=_cmd_unpack)

    # inspect ----------------------------------------------------------------
    ins = sub.add_parser(
        "inspect",
        help="Print a summary of the project (page, dpi, cell counts, ...).",
    )
    ins.add_argument("input", help=".figpack, .figlayout or .json")
    ins.add_argument("--json", action="store_true",
                     help="Emit machine-readable JSON instead of text.")
    ins.set_defaults(func=_cmd_inspect)

    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args) or 0
    except SystemExit:
        raise
    except KeyboardInterrupt:
        sys.stderr.write("interrupted\n")
        return 130
    except Exception as e:  # noqa: BLE001 — top-level guard
        sys.stderr.write(f"unexpected error: {e}\n")
        if os.environ.get("IMAGELAYOUT_CLI_DEBUG"):
            traceback.print_exc()
        return 4


if __name__ == "__main__":
    sys.exit(main())
