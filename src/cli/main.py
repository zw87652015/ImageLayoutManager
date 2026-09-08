"""``imagelayout-cli`` — headless driver for ImageLayoutManager.

Verbs (v1):

    render   .figpack | .figlayout | .json   ->  pdf | tiff | jpg | png
    pack     .figlayout                       ->  .figpack
    unpack   .figpack                         ->  <dir>/<name>.figlayout + <dir>/<name>_assets/
    inspect  .figpack | .figlayout | .json    ->  human-readable summary on stdout
    edit     .figlayout | .json               ->  .figlayout | .json | .figpack

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
        from src.model.migrations import ProjectMigrationError
        try:
            return Project.load_from_file(path), None
        except ProjectMigrationError as e:
            raise SystemExit(f"error: cannot open project: {e}") from e
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
        group_labels = getattr(project, "group_labels", []) or []
        if args.json:
            payload = {
                "name": project.name,
                "page_mm": [project.page_width_mm, project.page_height_mm],
                "dpi": project.dpi,
                "layout_mode": project.layout_mode,
                "rows": len(project.rows),
                "cells_total": len(project.get_all_leaf_cells()),
                "text_items": len(project.text_items),
                "group_labels": [g.to_dict() for g in group_labels],
                "label_scheme": project.label_scheme,
                "label_scheme_sub": getattr(project, "label_scheme_sub", ""),
                "label_placement": project.label_placement,
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
            print(f"labels      : scheme {project.label_scheme} / "
                  f"{getattr(project, 'label_scheme_sub', '') or 'flat'} "
                  f"@ {project.label_placement}")
            if group_labels:
                print(f"group labels: {len(group_labels)}")
                for g in group_labels:
                    target = (f"row {g.row_index}" if g.row_index is not None
                              else f"{len(g.cell_ids)} cells")
                    print(f"              - {g.text!r} ({g.side}, {target})")
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
# edit — headless project mutation via the agent tool registry
# ---------------------------------------------------------------------------
#
# ``src/agent/tools.py`` was written GUI-agnostic on purpose:
# ``ToolContext`` allows ``undo_stack``/``main_window`` to be None, and
# ``_apply`` then runs each QUndoCommand directly instead of pushing it.
# ``edit`` is the CLI transport for that registry — the same tools an MCP
# host drives through a running GUI, applied to a file with no GUI at all.
#
# Stdout discipline matches ``render``: only the resulting path (or the
# ``--json`` report) goes to stdout, so the verb stays pipeable. Per-step
# progress is written to stderr.

_EDIT_OUTPUT_EXTS = (".figlayout", ".json", ".figpack")


def _parse_call(spec: List[str]) -> Tuple[str, dict]:
    """Turn one ``--call TOOL ['{json}']`` occurrence into ``(name, params)``.

    Trailing values are re-joined before parsing: cmd.exe and PowerShell both
    re-split a quoted JSON argument on its spaces, so ``{"a": 1}`` can arrive
    as two argv entries. JSON is whitespace-insensitive, so joining restores
    the original document on every shell.
    """
    if not spec:
        raise SystemExit("error: --call needs a TOOL name")
    name = spec[0]
    if len(spec) == 1:
        return name, {}
    raw = " ".join(spec[1:])
    try:
        params = json.loads(raw)
    except json.JSONDecodeError as e:
        raise SystemExit(f"error: --call {name}: invalid JSON params: {e}") from e
    if not isinstance(params, dict):
        raise SystemExit(f"error: --call {name}: params must be a JSON object")
    return name, params


def _load_script(path: str) -> List[Tuple[str, dict]]:
    """Read an ordered step list from *path* (``-`` means stdin).

    Accepts a bare JSON array or ``{"steps": [...]}``. Each step is
    ``{"tool": name, "params": {...}}``; ``name``/``args`` are honoured as
    aliases so hand-written scripts and tool-call logs both work.
    """
    try:
        if path == "-":
            raw = sys.stdin.read()
        else:
            # utf-8-sig: PowerShell's Out-File/redirection writes a BOM by
            # default, and json.loads rejects it. Plain UTF-8 still decodes.
            with open(path, "r", encoding="utf-8-sig") as f:
                raw = f.read()
    except OSError as e:
        raise SystemExit(f"error: cannot read script {path}: {e}") from e
    raw = raw.lstrip("\ufeff")  # piped stdin can carry a BOM too

    try:
        doc = json.loads(raw)
    except json.JSONDecodeError as e:
        raise SystemExit(f"error: script {path} is not valid JSON: {e}") from e

    steps = doc.get("steps") if isinstance(doc, dict) else doc
    if not isinstance(steps, list):
        raise SystemExit(
            f"error: script {path} must be a JSON array of steps "
            'or {"steps": [...]}'
        )

    out: List[Tuple[str, dict]] = []
    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            raise SystemExit(f"error: script step {i} is not a JSON object")
        name = step.get("tool") or step.get("name")
        if not name:
            raise SystemExit(f'error: script step {i} has no "tool" key')
        params = step.get("params", step.get("args", {})) or {}
        if not isinstance(params, dict):
            raise SystemExit(f'error: script step {i}: "params" must be an object')
        out.append((str(name), params))
    return out


def _write_project(project, out: str) -> str:
    """Persist *project* to *out*. ``-`` streams .figlayout JSON to stdout."""
    if out == "-":
        sys.stdout.write(json.dumps(project.to_dict(), indent=4) + "\n")
        return "-"

    abs_out = os.path.abspath(out)
    parent = os.path.dirname(abs_out) or "."
    if not os.path.isdir(parent):
        raise SystemExit(f"error: output directory does not exist: {parent}")

    if os.path.splitext(abs_out)[1].lower() == ".figpack":
        from src.utils.figpack import pack_project, BundleError
        from src.version import APP_VERSION
        try:
            pack_project(project, abs_out, app_version=APP_VERSION)
        except BundleError as e:
            raise SystemExit(f"error: pack failed: {e}") from e
        return abs_out

    # .figlayout / .json — same serialisation Project.save_to_file uses,
    # but committed atomically: an interrupted --in-place edit must never
    # truncate what may be the user's only copy.
    from src.utils.figpack.atomic_write import atomic_write_bytes
    project.name = os.path.splitext(os.path.basename(abs_out))[0]
    atomic_write_bytes(abs_out, json.dumps(project.to_dict(), indent=4).encode("utf-8"))
    return abs_out


def _resolve_edit_target(args: argparse.Namespace) -> Optional[str]:
    """Validate the input/output combination; return the output path or None."""
    if args.in_place:
        if not args.input:
            raise SystemExit("error: --in-place needs an INPUT file")
        out = args.input
    elif args.output:
        out = args.output
    elif args.dry_run:
        return None
    else:
        raise SystemExit(
            "error: nothing to write to — pass -o/--output, --in-place, "
            "or --dry-run"
        )

    if out == "-" and args.json:
        raise SystemExit(
            "error: -o - and --json both write to stdout; pick one"
        )

    if out != "-":
        ext = os.path.splitext(out)[1].lower()
        if ext not in _EDIT_OUTPUT_EXTS:
            raise SystemExit(
                f"error: unsupported output extension '{ext}' "
                f"(want {', '.join(_EDIT_OUTPUT_EXTS)})"
            )

    if args.input and os.path.splitext(args.input)[1].lower() == ".figpack":
        # A .figpack is opened by extracting into a temp working dir that is
        # released on exit, so its cell image_paths are only valid for this
        # process. Re-packing from them would also re-resolve every asset
        # from its original source path, silently dropping any asset whose
        # source is absent on this machine. Route users through unpack.
        raise SystemExit(
            "error: 'edit' does not take .figpack input\n"
            "       run 'imagelayout-cli unpack in.figpack -o dir' first, edit "
            "dir/<name>.figlayout, then 'pack' it back"
        )
    return out


def _cmd_edit(args: argparse.Namespace) -> int:
    from src.agent import tools

    if args.list_tools:
        for name in tools.list_tools():
            sys.stdout.write(f"{name}\n")
        return 0

    if args.new and args.input:
        raise SystemExit("error: --new takes no INPUT file")
    if not args.new and not args.input:
        raise SystemExit("error: 'edit' needs an INPUT file (or --new)")

    steps: List[Tuple[str, dict]] = []
    if args.script:
        steps.extend(_load_script(args.script))
    for spec in (args.call or []):
        steps.append(_parse_call(spec))
    if args.new:
        # --new is just an implicit first step, so it shows up in --json
        # output like everything else and has one definition of "new project".
        steps.insert(0, ("project_new", {}))
    if not steps:
        raise SystemExit(
            "error: no operations given — use --call and/or --script "
            "(--list-tools lists what's available)"
        )

    known = set(tools.list_tools())
    unknown = sorted({name for name, _ in steps if name not in known})
    if unknown:
        raise SystemExit(
            f"error: unknown tool(s): {', '.join(unknown)}\n"
            "       run 'imagelayout-cli edit --list-tools' for the full list"
        )

    out = _resolve_edit_target(args)

    # Tools construct QUndoCommands and a few (project_export,
    # view_screenshot) drive the real exporters, so a QApplication has to
    # exist. Spinning one up unconditionally costs ~200 ms and avoids the
    # "works for these tools, crashes for those" class of surprise.
    _ensure_qapp()

    from src.agent.tools import ToolContext
    from src.model.data_model import Project

    if args.new:
        ctx = ToolContext(project=Project(), project_path=None)
    else:
        project, _ = _load_project(args.input)
        ctx = ToolContext(project=project,
                          project_path=os.path.abspath(args.input))

    envelopes: List[dict] = []
    failed = 0
    for name, params in steps:
        env = tools.dispatch(name, params, ctx)
        envelopes.append({"tool": name, **env})
        if env.get("ok"):
            if not args.json:
                sys.stderr.write(f"ok    {name}\n")
        else:
            failed += 1
            if not args.json:
                sys.stderr.write(
                    f"FAIL  {name}: {env.get('error')}: {env.get('detail')}\n"
                )
            if not args.keep_going:
                break

    # A failed step without --keep-going aborts before any write, so the
    # input file is left exactly as it was.
    wrote: Optional[str] = None
    if out is not None and not args.dry_run and not (failed and not args.keep_going):
        wrote = _write_project(ctx.project, out)

    if args.json:
        json.dump({"ok": failed == 0, "steps": envelopes, "output": wrote},
                  sys.stdout, indent=2)
        sys.stdout.write("\n")
    elif wrote and wrote != "-":
        sys.stdout.write(f"{wrote}\n")
    sys.stdout.flush()
    return 1 if failed else 0


# ---------------------------------------------------------------------------
# mcp (MCP-over-stdio adapter — no Qt required)
# ---------------------------------------------------------------------------

def _cmd_mcp(args: argparse.Namespace) -> int:
    import asyncio
    from src.agent.mcp_stdio import run_stdio
    try:
        asyncio.run(run_stdio())
    except (KeyboardInterrupt, BrokenPipeError):
        pass
    return 0


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

    # edit -------------------------------------------------------------------
    ed = sub.add_parser(
        "edit",
        help="Apply agent tool operations to a project headlessly (no GUI).",
        description="Mutate a project by running agent tools against it. "
                    "Steps are applied in order: --script first, then each "
                    "--call. Nothing is written unless every step succeeds "
                    "(see --keep-going). Per-step progress goes to stderr; "
                    "stdout carries only the output path or the --json report.",
        epilog="examples:\n"
               "  imagelayout-cli edit fig.figlayout --in-place "
               "--call auto_label_cells '{\"scheme\": \"(a)\"}'\n"
               "  imagelayout-cli edit fig.figlayout -o out.figpack "
               "--script ops.json --json\n"
               "  imagelayout-cli edit --new -o blank.figlayout "
               "--call row_add '{\"position\": 2, \"column_count\": 3}'\n"
               "  cat ops.json | imagelayout-cli edit fig.figlayout -o - --script -",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ed.add_argument("input", nargs="?",
                    help=".figlayout or .json (omit when using --new)")
    ed.add_argument("--new", action="store_true",
                    help="Start from a blank project instead of INPUT.")
    ed.add_argument("--call", action="append", nargs="+", metavar="TOOL",
                    help="Run TOOL, optionally followed by a JSON object of "
                         "params. Repeatable; applied in order.")
    ed.add_argument("--script", metavar="FILE",
                    help='JSON array of {"tool": ..., "params": {...}} steps '
                         "('-' reads stdin).")
    tgt = ed.add_mutually_exclusive_group()
    tgt.add_argument("-o", "--output",
                     help="Write the result here: .figlayout, .json or "
                          ".figpack ('-' streams .figlayout JSON to stdout).")
    tgt.add_argument("-i", "--in-place", action="store_true",
                     help="Overwrite INPUT (written atomically).")
    ed.add_argument("--keep-going", action="store_true",
                    help="Continue past a failing step and still write the "
                         "result (exit code stays 1).")
    ed.add_argument("--dry-run", action="store_true",
                    help="Apply every step in memory but write nothing.")
    ed.add_argument("--json", action="store_true",
                    help="Emit one JSON object containing every step envelope.")
    ed.add_argument("--list-tools", action="store_true",
                    help="Print the available tool names and exit.")
    ed.set_defaults(func=_cmd_edit)

    # mcp --------------------------------------------------------------------
    mcp = sub.add_parser(
        "mcp",
        help="Run the MCP-over-stdio adapter (launched by AI hosts, not by humans).",
    )
    mcp.set_defaults(func=_cmd_mcp)

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
