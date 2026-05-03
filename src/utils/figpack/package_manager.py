"""
.figpack pack / unpack — public API.

This is the Phase-1 implementation:

* image assets only (ICC profile bundling is Phase 3 per plan.md §4);
* full repack on every save (``update_json_only`` fast path is a
  Phase-2 concern);
* preview.jpg / README.html / undo-stack rewriting are deliberately
  deferred — the foundation is what's exercised here.

What IS already wired up:

* atomic save (`atomic_writer` from :mod:`atomic_write`)
* deterministic asset paths (`asset_archive_path` from :mod:`encoding`)
* zip-slip / zip-bomb / encryption / symlink / multi-disk / SFX
  rejection (:mod:`zip_safety`)
* 1 MiB streaming I/O on both pack and unpack
* sha256 computed on pack, verified on unpack
* missing-asset preservation: cell records keep their
  ``original_source_path`` even if the source file is gone

Public API::

    PackResult = pack_project(project, output_path, *, progress, cancel)
    UnpackResult = unpack_project(pack_path, target_dir, *, progress, cancel,
                                  limits=SafetyLimits())
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import platform
import shutil
import sys
import time
import zipfile
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from src.utils.figpack.atomic_write import atomic_writer, cleanup_stray_tmps
from src.utils.figpack.cache_manager import (
    DEFAULT_QUOTA_BYTES,
    WorkingDir,
    _safe_rmtree,
    allocate_working_dir,
)
from src.utils.figpack.encoding import (
    asset_archive_path,
    sanitize_basename,
    to_nfc,
)
from src.utils.figpack.errors import (
    BundleError,
    BundleIntegrityError,
    BundleSecurityError,
)
from src.utils.figpack.zip_safety import (
    SafetyLimits,
    iter_validated_entries,
)

# ──────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────

FIGPACK_FORMAT_VERSION = 1
# figure_number and figure_title were added as optional fields in metadata.json
# without a version bump — v1 readers silently ignore unknown keys, so no break.

# Filenames that always live at the archive root.
PROJECT_JSON = "project.json"
METADATA_JSON = "metadata.json"
PREVIEW_JPEG = "preview.jpg"
README_HTML = "README.html"

# Stream chunk size — applies to both reads from source files when
# packing and reads from archive entries when unpacking.
CHUNK_SIZE = 1 * 1024 * 1024  # 1 MiB

# Resource-ID prefix in transformed project.json.
RESOURCE_PREFIX = "figpack:"

# Type alias for progress callbacks: progress(fraction, message).
ProgressCB = Callable[[float, str], None]
CancelCB = Callable[[], bool]
# Optional preview renderer: receives the live Project, returns
# a JPEG bytestring at ~1080p long-edge. Kept as a callback so the
# figpack stack stays Qt-free; callers wire in ImageExporter.
PreviewRendererCB = Callable[[Any], Optional[bytes]]


# ──────────────────────────────────────────────────────────────────────
# Result dataclasses
# ──────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class AssetRecord:
    """One row of the resource manifest."""
    resource_id: str
    archive_path: Optional[str]
    original_source_path: str
    sha256: Optional[str]
    size_bytes: int
    status: str  # "ok" | "missing"


@dataclass
class PackResult:
    output_path: str
    asset_count: int
    missing_count: int
    bytes_written: int
    assets: List[AssetRecord] = field(default_factory=list)


@dataclass
class UnpackResult:
    target_dir: str
    asset_count: int
    project_data: Dict[str, Any]   # parsed project.json with paths resolved
    metadata: Dict[str, Any]       # parsed metadata.json (raw)
    missing_count: int = 0


# ──────────────────────────────────────────────────────────────────────
# Pack
# ──────────────────────────────────────────────────────────────────────

# Plan §3.1.6 — cloud placeholders surfacing.
# Sources whose bytes live online (OneDrive, iCloud Drive, Dropbox files-
# on-demand) report as regular files but trigger arbitrary-time waits the
# first time we read them. We probe before opening so the UI can prompt.

if sys.platform == "win32":  # pragma: no cover - platform branch
    _FILE_ATTRIBUTE_RECALL_ON_OPEN = 0x00040000
    _FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS = 0x00400000
    _CLOUD_PLACEHOLDER_MASK = (
        _FILE_ATTRIBUTE_RECALL_ON_OPEN
        | _FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS
    )


def is_cloud_placeholder(path: str) -> bool:
    """Best-effort detection of a files-on-demand placeholder.

    * Windows: checks ``GetFileAttributesW`` for ``RECALL_ON_OPEN`` /
      ``RECALL_ON_DATA_ACCESS`` (CloudFilter API; OneDrive, iCloud-on-PC,
      Google Drive File Stream).
    * macOS: probes ``com.apple.fileprovider.fpfs#P`` xattr (iCloud
      Drive). Other providers (Dropbox, Google) are out of scope.
    * Anywhere else: returns False.

    Never raises — a failed probe is reported as "not a placeholder".
    """
    try:
        if sys.platform == "win32":
            import ctypes
            attrs = ctypes.windll.kernel32.GetFileAttributesW(path)
            if attrs == 0xFFFFFFFF:  # INVALID_FILE_ATTRIBUTES
                return False
            return bool(attrs & _CLOUD_PLACEHOLDER_MASK)
        if sys.platform == "darwin":
            try:
                import xattr  # type: ignore[import]
                names = xattr.listxattr(path)
                return any(
                    n.startswith("com.apple.fileprovider.fpfs")
                    for n in names
                )
            except ImportError:
                import subprocess
                p = subprocess.run(
                    ["xattr", path],
                    check=False,
                    capture_output=True, text=True,
                )
                return "com.apple.fileprovider.fpfs" in (p.stdout or "")
    except Exception:
        return False
    return False


# Type alias for the cloud-placeholder resolution callback. Called once
# per pack with the deduplicated list of detected placeholders. The
# return value tells the packer how to proceed:
#   "hydrate" — attempt to read each (the OS will materialise on demand);
#   "skip"    — drop them, marking each as missing in the manifest;
#   "cancel"  — raise BundleError(code="cancelled").
CloudResolution = str  # Literal["hydrate", "skip", "cancel"]
CloudResolverCB = Callable[[List[str]], CloudResolution]


def _resolve_canonical(path: str, *, seen: Dict[str, str]) -> str:
    """Resolve *path* via :func:`os.path.realpath` and detect symlink
    loops via a per-pack ``seen`` map keyed by the **input** path.

    Returns the NFC-normalized canonical absolute path. Raises
    :class:`BundleError(code="symlink_loop")` if resolving *path*
    visits any node twice during the walk.
    """
    raw = to_nfc(os.path.abspath(path))
    cached = seen.get(raw)
    if cached is not None:
        return cached
    # Walk parents one symlink at a time to detect cycles deterministically.
    visited: set = set()
    cur = raw
    for _ in range(64):  # bounded depth: well above any realistic FS depth
        if cur in visited:
            raise BundleError(
                f"symlink loop detected while resolving {path!r}",
                code="symlink_loop",
            )
        visited.add(cur)
        try:
            nxt = to_nfc(os.path.realpath(cur))
        except OSError:
            nxt = cur
        if nxt == cur:
            break
        cur = nxt
    seen[raw] = cur
    return cur


def _iter_cell_image_paths(project) -> List[Tuple[Any, str, str]]:
    """Yield ``(cell, hash_path, content_path)`` for every leaf cell
    with an image.

    * ``hash_path``    — the *sticky* original-source path used to
      derive the deterministic archive entry. When the project came
      from a previously-unpacked bundle, this is whatever
      ``original_source_path`` was set on unpack — so re-packing the
      same project produces byte-identical asset paths.
    * ``content_path`` — where the bytes actually live right now;
      typically ``image_path`` (cache or original).
    Both are absolutized, NFC-normalized, and run through
    :func:`_resolve_canonical` so any symlink in the source tree is
    pinned to its real target and any loop is detected per plan §3.1.7.
    """
    out: List[Tuple[Any, str, str]] = []
    seen: Dict[str, str] = {}
    for cell in project.get_all_leaf_cells():
        content = getattr(cell, "image_path", None)
        if not content:
            continue
        sticky = getattr(cell, "original_source_path", None) or content
        out.append((
            cell,
            _resolve_canonical(sticky, seen=seen),
            _resolve_canonical(content, seen=seen),
        ))
    return out


def _build_manifest(
    project,
    *,
    progress: Optional[ProgressCB],
    cancel: Optional[CancelCB],
    skip_paths: Optional[set] = None,
) -> Tuple[Dict[str, AssetRecord], Dict[str, str], Dict[str, str]]:
    """Scan source files, build resource records, return:

      * ``manifest``: ``{resource_id -> AssetRecord}``
      * ``path_to_id``: ``{abs_source_path -> resource_id}`` (deduped)

    Sources whose file does not exist are recorded with status="missing"
    and ``archive_path=None`` / ``sha256=None``; they will not be added
    to the archive but will still flow through ``project.json`` so the
    user can re-link later.
    """
    manifest: Dict[str, AssetRecord] = {}
    # Maps the *sticky* hash-path → resource id. Cells whose
    # ``image_path`` differs from ``original_source_path`` (typical
    # post-unpack situation) all collapse onto a single manifest row.
    path_to_id: Dict[str, str] = {}
    # Where to actually read bytes from at write time, keyed by rid.
    readable_for: Dict[str, str] = {}

    cell_paths = _iter_cell_image_paths(project)
    next_id = 1
    total = max(len(cell_paths), 1)

    for i, (_cell, hash_path, content_path) in enumerate(cell_paths):
        if cancel and cancel():
            raise BundleError("operation cancelled", code="cancelled")

        if hash_path in path_to_id:
            continue  # already known — deduped by sticky path

        rid = f"res_{next_id}"
        next_id += 1
        path_to_id[hash_path] = rid

        if progress:
            progress(i / total, f"Hashing {os.path.basename(hash_path)}")

        # User asked to skip this source (e.g. cloud placeholder they
        # didn't want to hydrate). Mark missing without ever reading.
        if skip_paths and (
            hash_path in skip_paths or content_path in skip_paths
        ):
            manifest[rid] = AssetRecord(
                resource_id=rid,
                archive_path=None,
                original_source_path=hash_path,
                sha256=None,
                size_bytes=0,
                status="missing",
            )
            continue

        # Read bytes from wherever they currently live (cache after
        # unpack, original directory pre-pack); fall back to hash_path
        # if content_path is gone but hash_path itself happens to
        # still exist (rare).
        readable = content_path if os.path.exists(content_path) else (
            hash_path if os.path.exists(hash_path) else None
        )
        if readable is None:
            manifest[rid] = AssetRecord(
                resource_id=rid,
                archive_path=None,
                original_source_path=hash_path,
                sha256=None,
                size_bytes=0,
                status="missing",
            )
            continue

        # Stream-hash the source file.
        try:
            sha = hashlib.sha256()
            size = 0
            with open(readable, "rb") as f:
                while True:
                    if cancel and cancel():
                        raise BundleError("operation cancelled", code="cancelled")
                    chunk = f.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    sha.update(chunk)
                    size += len(chunk)
        except OSError:
            manifest[rid] = AssetRecord(
                resource_id=rid,
                archive_path=None,
                original_source_path=hash_path,
                sha256=None,
                size_bytes=0,
                status="missing",
            )
            continue

        # Archive-path is derived from the *sticky* hash_path so the
        # entry name stays stable across pack→unpack→repack cycles.
        archive_path, _hash_dir = asset_archive_path(hash_path)
        manifest[rid] = AssetRecord(
            resource_id=rid,
            archive_path=archive_path,
            original_source_path=hash_path,
            sha256=sha.hexdigest(),
            size_bytes=size,
            status="ok",
        )
        # Remember where to actually copy bytes from at write time.
        readable_for[rid] = readable

    return manifest, path_to_id, readable_for


def _transform_project_dict(
    project_dict: Dict[str, Any],
    path_to_id: Dict[str, str],
) -> Dict[str, Any]:
    """Return a copy of ``project_dict`` with cell ``image_path``
    values rewritten to ``"figpack:res_N"`` resource markers.

    Cells whose image is unknown to the manifest (shouldn't happen but
    we cope) keep their original path.
    """
    def rewrite_cells(cells):
        for c in cells:
            ip = c.get("image_path")
            osp = c.get("original_source_path")
            if ip:
                # Same sticky-key logic as _iter_cell_image_paths.
                key = to_nfc(os.path.abspath(osp or ip))
                if key in path_to_id:
                    c["image_path"] = f"{RESOURCE_PREFIX}{path_to_id[key]}"
            children = c.get("children")
            if children:
                rewrite_cells(children)

    out = json.loads(json.dumps(project_dict))  # deep copy via JSON
    rewrite_cells(out.get("cells", []))
    return out


def _build_metadata(
    manifest: Dict[str, AssetRecord],
    *,
    app_version: str,
    project=None,
) -> Dict[str, Any]:
    """Assemble ``metadata.json`` payload from the manifest."""
    return {
        "figpack_format_version": FIGPACK_FORMAT_VERSION,
        "app_version": app_version,
        "created_at": datetime.datetime.now(datetime.timezone.utc)
            .replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "figure_number": getattr(project, "figure_number", "") or "",
        "figure_title": getattr(project, "figure_title", "") or "",
        "host": {
            "os": platform.system().lower(),
            "user": _safe_username(),
        },
        "manifest": {
            rid: {
                "archive_path": rec.archive_path,
                "original_source_path": rec.original_source_path,
                "sha256": rec.sha256,
                "size_bytes": rec.size_bytes,
                "status": rec.status,
            }
            for rid, rec in manifest.items()
        },
        "icc_profiles": {},  # Phase 3
    }


def _build_readme_html(
    metadata: Dict[str, Any],
    project_name: str,
    *,
    has_preview: bool,
) -> bytes:
    """Generate a self-contained ``README.html`` for the bundle.

    Renders an audit table of every manifest entry (status, size, sha
    prefix, original source path) plus top-level metadata. Pure HTML,
    no JS — opens in any browser even when ImageLayoutManager isn't
    installed (plan §2.4).
    """
    import html as _html

    def esc(x: Any) -> str:
        return _html.escape("" if x is None else str(x))

    manifest = metadata.get("manifest", {}) or {}
    rows: List[str] = []
    total_bytes = 0
    ok_count = 0
    miss_count = 0
    for rid in sorted(manifest.keys()):
        rec = manifest[rid]
        sz = int(rec.get("size_bytes") or 0)
        total_bytes += sz
        status = rec.get("status", "?")
        if status == "ok":
            ok_count += 1
        else:
            miss_count += 1
        sha = (rec.get("sha256") or "")[:12]
        rows.append(
            "<tr class='status-{cls}'>"
            "<td><code>{rid}</code></td>"
            "<td>{status}</td>"
            "<td style='text-align:right'>{size}</td>"
            "<td><code>{sha}</code></td>"
            "<td>{archive}</td>"
            "<td>{orig}</td>"
            "</tr>".format(
                cls=esc(status),
                rid=esc(rid),
                status=esc(status),
                size=f"{sz:,}",
                sha=esc(sha),
                archive=esc(rec.get("archive_path") or "—"),
                orig=esc(rec.get("original_source_path") or "—"),
            )
        )

    host = metadata.get("host", {}) or {}
    icc_count = len(metadata.get("icc_profiles", {}) or {})

    preview_block = (
        f"<p><img src='{PREVIEW_JPEG}' alt='Project preview' "
        f"style='max-width:100%;border:1px solid #ccc'></p>"
        if has_preview else ""
    )

    html_doc = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{esc(project_name)} — figpack contents</title>
<style>
  body {{ font-family: -apple-system, "Segoe UI", Helvetica, Arial, sans-serif;
          margin: 2em auto; max-width: 60em; color: #222; }}
  h1 {{ border-bottom: 2px solid #444; padding-bottom: .25em; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 0.9em; }}
  th, td {{ border: 1px solid #ccc; padding: 4px 8px; vertical-align: top; }}
  th {{ background: #f3f3f3; text-align: left; }}
  tr.status-missing {{ background: #fff2f2; color: #a00; }}
  code {{ font-family: ui-monospace, Menlo, Consolas, monospace; }}
  dl {{ display: grid; grid-template-columns: max-content 1fr; gap: 4px 16px; }}
  dt {{ font-weight: 600; color: #555; }}
</style>
</head>
<body>
<h1>{esc(project_name)}</h1>
<p>This file is part of a <code>.figpack</code> bundle generated by
ImageLayoutManager. Open the parent <code>.figpack</code> in
ImageLayoutManager to edit, or extract it as a ZIP archive to inspect
individual assets.</p>

{preview_block}

<h2>Bundle metadata</h2>
<dl>
  <dt>figpack format</dt><dd>v{esc(metadata.get("figpack_format_version"))}</dd>
  <dt>App version</dt><dd>{esc(metadata.get("app_version") or "—")}</dd>
  <dt>Created</dt><dd>{esc(metadata.get("created_at") or "—")}</dd>
  <dt>Host OS / user</dt><dd>{esc(host.get("os") or "?")} / {esc(host.get("user") or "?")}</dd>
  <dt>Assets ok / missing</dt><dd>{ok_count} / {miss_count}</dd>
  <dt>Total asset bytes</dt><dd>{total_bytes:,}</dd>
  <dt>ICC profiles bundled</dt><dd>{icc_count}</dd>
</dl>

<h2>Resource manifest</h2>
<table>
<thead><tr>
<th>resource_id</th><th>status</th><th>size (bytes)</th>
<th>sha256[:12]</th><th>archive path</th><th>original source path</th>
</tr></thead>
<tbody>
{''.join(rows) if rows else '<tr><td colspan="6"><em>No assets.</em></td></tr>'}
</tbody>
</table>
</body>
</html>
"""
    return html_doc.encode("utf-8")


def _estimate_pack_bytes(project) -> int:
    """Sum sizes of every reachable cell source. Best-effort; missing
    files contribute zero. Used by :func:`_preflight_output_volume`."""
    total = 0
    seen: Dict[str, str] = {}
    for cell in project.get_all_leaf_cells():
        ip = getattr(cell, "image_path", None)
        if not ip:
            continue
        try:
            canon = _resolve_canonical(ip, seen=seen)
        except BundleError:
            continue  # symlink loop — surfaced later in _build_manifest
        try:
            total += os.path.getsize(canon)
        except OSError:
            pass
    return total


def _preflight_output_volume(
    output_path: str,
    *,
    projected_bytes: int,
    safety_factor: float = 1.10,
) -> None:
    """Refuse to start a pack when the destination volume is read-only,
    or when free space falls below ``projected_bytes * safety_factor``.

    Plan §3.1.1 — fails closed *before* we open ``atomic_writer``, so
    the pre-existing target file is never put at risk.
    """
    out_dir = os.path.dirname(os.path.abspath(output_path)) or os.getcwd()
    # Auto-create parent dirs the user named in the dialog. If we can't
    # even create them, that's the writability failure we want to flag.
    try:
        os.makedirs(out_dir, exist_ok=True)
    except OSError as e:
        raise BundleError(
            f"cannot create destination directory {out_dir!r}: {e}",
            code="output_dir_unwritable",
        ) from e
    if not os.access(out_dir, os.W_OK):
        raise BundleError(
            f"destination directory is not writable: {out_dir!r}",
            code="output_dir_unwritable",
        )
    try:
        free = shutil.disk_usage(out_dir).free
    except OSError:
        return  # can't probe → don't second-guess the OS
    needed = int(projected_bytes * safety_factor)
    if needed > 0 and free < needed:
        raise BundleError(
            f"insufficient free space on output volume: need ~{needed:,} "
            f"bytes, only {free:,} available at {out_dir!r}",
            code="output_disk_full",
        )


def _safe_username() -> str:
    """Best-effort username; never raises and never leaks PII paths."""
    try:
        return os.environ.get("USERNAME") or os.environ.get("USER") or ""
    except Exception:
        return ""


def _stream_into_zip(
    zf: zipfile.ZipFile,
    archive_name: str,
    source_path: str,
    *,
    cancel: Optional[CancelCB],
) -> None:
    """Copy ``source_path`` into ``zf`` under ``archive_name`` using
    ZIP_STORED + 1 MiB chunks. Never reads the whole file into RAM.
    """
    info = zipfile.ZipInfo(archive_name)
    info.compress_type = zipfile.ZIP_STORED
    # Mark UTF-8 filename — ZipInfo with str does this, but assert.
    with open(source_path, "rb") as src, zf.open(info, mode="w", force_zip64=True) as dst:
        while True:
            if cancel and cancel():
                raise BundleError("operation cancelled", code="cancelled")
            chunk = src.read(CHUNK_SIZE)
            if not chunk:
                break
            dst.write(chunk)


def _writestr_utf8(zf: zipfile.ZipFile, name: str, data: bytes,
                   *, deflated: bool = True) -> None:
    """``writestr`` wrapper that always sets the UTF-8 filename flag."""
    info = zipfile.ZipInfo(name)
    info.compress_type = zipfile.ZIP_DEFLATED if deflated else zipfile.ZIP_STORED
    # Python sets bit 0x800 automatically when filename has non-ASCII;
    # assert it for safety on names that are pure ASCII too.
    info.flag_bits |= 0x800
    zf.writestr(info, data)


def _pack_project_json_only(
    project,
    output_path: str,
    *,
    app_version: str,
    preview_renderer: Optional[PreviewRendererCB],
    progress: Optional[ProgressCB],
    cancel: Optional[CancelCB],
) -> PackResult:
    """Fast path for ``update_json_only=True``.

    Re-emits the archive with **the same physical asset entries** as
    the file currently at *output_path*, but with regenerated
    ``project.json`` and ``metadata.json``. Bytes are stream-copied
    via ``ZipFile.open(..., "r")`` chunked reads — no decompression /
    recompression of asset payloads.
    """
    if not os.path.exists(output_path):
        raise BundleError(
            "update_json_only requires the target archive to exist",
            code="fastpath_no_existing",
        )

    if progress:
        progress(0.0, "Reading existing archive")

    # Pull old manifest so we can validate "no asset changes" and
    # build the new path_to_id map without re-hashing.
    try:
        with zipfile.ZipFile(output_path, "r", allowZip64=True) as zf:
            try:
                old_meta = json.loads(zf.read(METADATA_JSON))
            except KeyError as e:
                raise BundleError(
                    "existing archive missing metadata.json",
                    code="fastpath_bad_archive",
                ) from e
    except zipfile.BadZipFile as e:
        raise BundleError(
            f"existing archive is not a valid zip: {e}",
            code="fastpath_bad_archive",
        ) from e

    old_manifest = old_meta.get("manifest", {}) or {}

    # Build sticky-path → resource id from the old manifest.
    path_to_id: Dict[str, str] = {}
    for rid, rec in old_manifest.items():
        osp = rec.get("original_source_path")
        if isinstance(osp, str):
            path_to_id[to_nfc(os.path.abspath(osp))] = rid

    # Validate every current cell is covered by the old manifest.
    cell_paths = _iter_cell_image_paths(project)
    for _cell, hash_path, _content in cell_paths:
        if hash_path not in path_to_id:
            raise BundleError(
                f"update_json_only: cell references new or relinked "
                f"asset {hash_path!r} not in existing manifest; full "
                f"repack required",
                code="fastpath_dirty_assets",
            )

    # Build new project.json.
    project_dict = project.to_dict()
    transformed = _transform_project_dict(project_dict, path_to_id)

    # Build new metadata: keep manifest as-is (status/sha256/sizes
    # unchanged because bytes are unchanged), only refresh top-level
    # fields like created_at and app_version.
    new_meta = dict(old_meta)
    new_meta["figpack_format_version"] = FIGPACK_FORMAT_VERSION
    new_meta["app_version"] = app_version or new_meta.get("app_version", "")
    new_meta["created_at"] = (
        datetime.datetime.now(datetime.timezone.utc)
        .replace(microsecond=0).isoformat().replace("+00:00", "Z")
    )
    new_meta.setdefault("host", {})
    new_meta["host"]["os"] = platform.system().lower()
    new_meta["host"]["user"] = _safe_username()
    new_meta["figure_number"] = getattr(project, "figure_number", "") or ""
    new_meta["figure_title"] = getattr(project, "figure_title", "") or ""

    project_json = json.dumps(
        transformed, ensure_ascii=False, indent=2,
    ).encode("utf-8")
    metadata_json = json.dumps(
        new_meta, ensure_ascii=False, indent=2,
    ).encode("utf-8")

    # Optional preview re-render — always best-effort. Even on the
    # fast path we want preview.jpg to reflect any layout-only edits
    # the user just made.
    preview_bytes: Optional[bytes] = None
    if preview_renderer is not None:
        try:
            out = preview_renderer(project)
            if isinstance(out, (bytes, bytearray)) and len(out) > 0:
                preview_bytes = bytes(out)
                print(f"[pack fast] preview_bytes={len(preview_bytes)}")
            else:
                print(f"[pack fast] preview_renderer returned {type(out)} len={len(out) if out else 0}")
        except Exception:
            import traceback; traceback.print_exc()
            preview_bytes = None

    project_name = (
        getattr(project, "name", None)
        or os.path.splitext(os.path.basename(output_path))[0]
    )
    readme_bytes = _build_readme_html(
        new_meta, project_name, has_preview=preview_bytes is not None,
    )

    if progress:
        progress(0.1, "Restreaming asset entries")

    # Re-emit archive: JSONs + regenerated audit files first, then
    # every other entry from the old archive, stream-copied via 1 MiB
    # chunks. Old preview/README are dropped — we just wrote fresh ones.
    skip_old = {PROJECT_JSON, METADATA_JSON, PREVIEW_JPEG, README_HTML}
    with atomic_writer(output_path) as out_fp:
        with zipfile.ZipFile(output_path, "r", allowZip64=True) as src_zf, \
             zipfile.ZipFile(out_fp, "w", allowZip64=True) as dst_zf:
            _writestr_utf8(dst_zf, PROJECT_JSON, project_json, deflated=True)
            _writestr_utf8(dst_zf, METADATA_JSON, metadata_json, deflated=True)
            if preview_bytes is not None:
                _writestr_utf8(
                    dst_zf, PREVIEW_JPEG, preview_bytes, deflated=False,
                )
            _writestr_utf8(dst_zf, README_HTML, readme_bytes, deflated=True)

            entries = [
                info for info in src_zf.infolist()
                if not info.is_dir() and info.filename not in skip_old
            ]
            entries.sort(key=lambda i: i.filename)
            total = max(len(entries), 1)
            for i, info in enumerate(entries):
                if cancel and cancel():
                    raise BundleError(
                        "operation cancelled", code="cancelled",
                    )
                if progress:
                    progress(
                        0.1 + 0.9 * (i / total),
                        f"Streaming {os.path.basename(info.filename)}",
                    )
                # Preserve compression type bytewise; ZipFile.open in
                # 'r' decompresses, so we re-emit through a fresh
                # ZipInfo with the same compress_type.
                new_info = zipfile.ZipInfo(info.filename)
                new_info.compress_type = info.compress_type
                new_info.flag_bits |= 0x800
                with src_zf.open(info, "r") as sf, \
                     dst_zf.open(new_info, "w", force_zip64=True) as df:
                    while True:
                        if cancel and cancel():
                            raise BundleError(
                                "operation cancelled", code="cancelled",
                            )
                        chunk = sf.read(CHUNK_SIZE)
                        if not chunk:
                            break
                        df.write(chunk)

    if progress:
        progress(1.0, "Done")

    # Reconstruct AssetRecord list from the unchanged manifest so the
    # PackResult shape stays consistent with the slow path.
    assets: List[AssetRecord] = []
    ok = 0
    miss = 0
    for rid, rec in old_manifest.items():
        ar = AssetRecord(
            resource_id=rid,
            archive_path=rec.get("archive_path"),
            original_source_path=rec.get("original_source_path", ""),
            sha256=rec.get("sha256"),
            size_bytes=int(rec.get("size_bytes") or 0),
            status=rec.get("status", "ok"),
        )
        assets.append(ar)
        if ar.status == "ok":
            ok += 1
        else:
            miss += 1

    return PackResult(
        output_path=output_path,
        asset_count=ok,
        missing_count=miss,
        bytes_written=os.path.getsize(output_path),
        assets=assets,
    )


def pack_project(
    project,
    output_path: str,
    *,
    app_version: str = "",
    update_json_only: bool = False,
    preview_renderer: Optional[PreviewRendererCB] = None,
    cloud_resolver: Optional[CloudResolverCB] = None,
    progress: Optional[ProgressCB] = None,
    cancel: Optional[CancelCB] = None,
) -> PackResult:
    """Atomically write ``project`` to ``output_path`` as a ``.figpack``.

    When *update_json_only* is true, the existing archive at
    ``output_path`` is reused: every non-JSON entry is **stream-copied**
    bytewise into the new archive, and only ``project.json`` /
    ``metadata.json`` are regenerated. This is the fast path for "I
    edited only layout / labels, no assets changed" saves — common
    enough that the speed win on multi-GB bundles dominates UX.

    Preconditions for the fast path (raises on violation; caller falls
    back to a full repack):
    * ``output_path`` exists and is a valid figpack we wrote.
    * Every cell's sticky ``original_source_path`` (or ``image_path``
      for projects that have never been packed) is already present in
      the existing archive's manifest. New / replaced / deleted assets
      force the full path.

    Raises :class:`BundleError` (and subclasses) on any failure; the
    pre-existing ``output_path`` is never partially written.
    """
    cleanup_stray_tmps(output_path)
    _preflight_output_volume(
        output_path,
        # Rough projection: sum of every existing source file. Cheaper
        # than _build_manifest hashing and good enough to refuse a
        # full-disk write before we touch the target.
        projected_bytes=_estimate_pack_bytes(project),
    )

    if update_json_only:
        return _pack_project_json_only(
            project, output_path,
            app_version=app_version,
            preview_renderer=preview_renderer,
            progress=progress, cancel=cancel,
        )

    if progress:
        progress(0.0, "Scanning assets")

    # Plan §3.1.6 — surface cloud placeholders before we open them.
    skip_paths: Optional[set] = None
    cell_paths = _iter_cell_image_paths(project)
    placeholder_set: List[str] = []
    seen_placeholder: set = set()
    for _cell, hash_path, content_path in cell_paths:
        for p in (hash_path, content_path):
            if p and p not in seen_placeholder and is_cloud_placeholder(p):
                seen_placeholder.add(p)
                placeholder_set.append(p)
    if placeholder_set:
        decision: CloudResolution = "hydrate"
        if cloud_resolver is not None:
            try:
                decision = cloud_resolver(list(placeholder_set))
            except Exception:
                decision = "hydrate"
        if decision == "cancel":
            raise BundleError(
                "operation cancelled by user (cloud placeholder dialog)",
                code="cancelled",
            )
        if decision == "skip":
            skip_paths = set(placeholder_set)
        # else "hydrate": fall through; the OS will materialise on read.

    manifest, path_to_id, readable_for = _build_manifest(
        project, progress=progress, cancel=cancel, skip_paths=skip_paths,
    )
    project_dict = project.to_dict()
    transformed = _transform_project_dict(project_dict, path_to_id)
    metadata = _build_metadata(manifest, app_version=app_version, project=project)

    project_json = json.dumps(
        transformed, ensure_ascii=False, indent=2
    ).encode("utf-8")
    metadata_json = json.dumps(
        metadata, ensure_ascii=False, indent=2
    ).encode("utf-8")

    # Optional preview rendering — best-effort, never fatal.
    preview_bytes: Optional[bytes] = None
    if preview_renderer is not None:
        if progress:
            progress(0.05, "Rendering preview")
        try:
            out = preview_renderer(project)
            if isinstance(out, (bytes, bytearray)) and len(out) > 0:
                preview_bytes = bytes(out)
        except Exception:
            preview_bytes = None

    project_name = (
        getattr(project, "name", None)
        or os.path.splitext(os.path.basename(output_path))[0]
    )
    readme_bytes = _build_readme_html(
        metadata, project_name, has_preview=preview_bytes is not None,
    )

    if progress:
        progress(0.1, "Writing archive")

    # Sort ok-asset records by archive path for byte-deterministic output.
    ok_assets = sorted(
        (rec for rec in manifest.values() if rec.status == "ok"),
        key=lambda r: r.archive_path,
    )
    missing_count = sum(1 for r in manifest.values() if r.status == "missing")

    # Atomically open the target.
    bytes_written_before = 0
    if os.path.exists(output_path):
        try:
            bytes_written_before = os.path.getsize(output_path)
        except OSError:
            pass

    with atomic_writer(output_path) as out_fp:
        with zipfile.ZipFile(out_fp, "w", allowZip64=True) as zf:
            # Deterministic insertion order:
            #   1. project.json  (compressed)
            #   2. metadata.json (compressed)
            #   3. assets/* sorted
            _writestr_utf8(zf, PROJECT_JSON, project_json, deflated=True)
            _writestr_utf8(zf, METADATA_JSON, metadata_json, deflated=True)
            if preview_bytes is not None:
                # Already JPEG-compressed; STORED is faster and equally small.
                _writestr_utf8(zf, PREVIEW_JPEG, preview_bytes, deflated=False)
            _writestr_utf8(zf, README_HTML, readme_bytes, deflated=True)

            total = max(len(ok_assets), 1)
            for i, rec in enumerate(ok_assets):
                if cancel and cancel():
                    raise BundleError("operation cancelled", code="cancelled")
                if progress:
                    progress(
                        0.1 + 0.9 * (i / total),
                        f"Packing {os.path.basename(rec.original_source_path)}",
                    )
                src_path = readable_for.get(
                    rec.resource_id, rec.original_source_path,
                )
                _stream_into_zip(
                    zf, rec.archive_path, src_path,
                    cancel=cancel,
                )

    if progress:
        progress(1.0, "Done")

    bytes_written = os.path.getsize(output_path)
    return PackResult(
        output_path=output_path,
        asset_count=sum(1 for r in manifest.values() if r.status == "ok"),
        missing_count=missing_count,
        bytes_written=bytes_written,
        assets=list(manifest.values()),
    )


# ──────────────────────────────────────────────────────────────────────
# Unpack
# ──────────────────────────────────────────────────────────────────────

def _strip_macos_quarantine(path: str) -> None:
    """Remove ``com.apple.quarantine`` from *path* on macOS.

    No-op on every other OS. Plan §5: quarantine inherited from a
    downloaded ``.figpack`` propagates to extracted files and breaks
    QImage / QPixmap loads on Apple-Silicon Gatekeeper. Best-effort —
    never raises; xattr support is optional.
    """
    if platform.system() != "Darwin":
        return
    try:
        import xattr  # type: ignore[import]
        try:
            xattr.removexattr(path, "com.apple.quarantine")
        except (KeyError, OSError):
            pass
    except ImportError:
        # Fall back to the system tool if the wheel isn't available.
        try:
            import subprocess
            subprocess.run(
                ["xattr", "-d", "com.apple.quarantine", path],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            pass


def _stream_extract(
    zf: zipfile.ZipFile,
    relpath: str,
    dest: str,
    *,
    expected_sha256: Optional[str],
    cancel: Optional[CancelCB],
) -> str:
    """Extract one entry to ``dest`` (a final on-disk path).

    Returns the computed sha256 (hex). If ``expected_sha256`` is given
    and does not match, raises :class:`BundleIntegrityError` and removes
    the partial file.
    """
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    sha = hashlib.sha256()
    tmp = dest + ".part"
    try:
        with zf.open(relpath, "r") as src, open(tmp, "wb") as out:
            while True:
                if cancel and cancel():
                    raise BundleError("operation cancelled", code="cancelled")
                chunk = src.read(CHUNK_SIZE)
                if not chunk:
                    break
                sha.update(chunk)
                out.write(chunk)
        digest = sha.hexdigest()
        if expected_sha256 and digest != expected_sha256:
            raise BundleIntegrityError(
                f"sha256 mismatch on {relpath!r} "
                f"(expected {expected_sha256[:12]}…, got {digest[:12]}…)"
            )
        os.replace(tmp, dest)
        _strip_macos_quarantine(dest)
        return digest
    except BaseException:
        try:
            if os.path.exists(tmp):
                os.unlink(tmp)
        except OSError:
            pass
        raise


def _resolve_resource_paths(
    project_data: Dict[str, Any],
    manifest: Dict[str, Any],
    target_dir: str,
) -> int:
    """In-place rewrite of ``"figpack:res_N"`` markers in
    ``project_data`` back to absolute on-disk paths.

    Returns the number of cells whose resource was missing (and got
    ``image_path=None`` in the result).
    """
    target_real = os.path.realpath(target_dir)
    missing = 0

    def rewrite(cells):
        nonlocal missing
        for c in cells:
            ip = c.get("image_path")
            if isinstance(ip, str) and ip.startswith(RESOURCE_PREFIX):
                rid = ip[len(RESOURCE_PREFIX):]
                rec = manifest.get(rid)
                if not rec:
                    c["image_path"] = None
                    missing += 1
                elif rec.get("status") != "ok":
                    c["image_path"] = None
                    # Sticky-pointer survives even when the byte
                    # contents are missing — user can re-link later.
                    c["original_source_path"] = rec.get(
                        "original_source_path"
                    )
                    missing += 1
                else:
                    ap = rec["archive_path"]
                    c["image_path"] = os.path.join(
                        target_real, *ap.split("/")
                    )
                    # Pin the original path on the cell so a subsequent
                    # repack hashes by the *same* sticky key as the
                    # original pack (plan §6.5).
                    c["original_source_path"] = rec.get(
                        "original_source_path"
                    )
            children = c.get("children")
            if children:
                rewrite(children)

    rewrite(project_data.get("cells", []))
    return missing


def unpack_project(
    pack_path: str,
    target_dir: str,
    *,
    progress: Optional[ProgressCB] = None,
    cancel: Optional[CancelCB] = None,
    limits: SafetyLimits = SafetyLimits(),
) -> UnpackResult:
    """Extract ``pack_path`` into ``target_dir`` (created if needed).

    Returns :class:`UnpackResult` whose ``project_data`` already has
    every ``image_path`` rewritten to a real on-disk path inside
    ``target_dir`` — callers can feed it straight to
    :meth:`Project.from_dict`.

    Raises :class:`BundleSecurityError` for any safety violation
    (caught by the validator), :class:`BundleIntegrityError` for sha256
    mismatches, and :class:`BundleError` for everything else.
    """
    os.makedirs(target_dir, exist_ok=True)
    target_real = os.path.realpath(target_dir)

    # Mark "extraction in progress" — cleanup pass must not delete
    # this dir until we either finish or roll back.
    sentinel = os.path.join(target_real, ".extracting")
    open(sentinel, "w", encoding="utf-8").close()

    extracted_paths: List[str] = []
    try:
        with zipfile.ZipFile(pack_path, "r", allowZip64=True) as zf:
            # Up-front validation (raises on any bad shape).
            entries = list(iter_validated_entries(
                zf, target_real, archive_path=pack_path, limits=limits,
            ))

            # Read metadata.json first so we know which sha256 to check
            # against each extracted asset. project.json arrives second.
            try:
                meta_bytes = zf.read(METADATA_JSON)
            except KeyError as e:
                raise BundleError(
                    f"archive missing required {METADATA_JSON}",
                    code="missing_metadata",
                ) from e
            metadata = json.loads(meta_bytes.decode("utf-8"))

            try:
                project_bytes = zf.read(PROJECT_JSON)
            except KeyError as e:
                raise BundleError(
                    f"archive missing required {PROJECT_JSON}",
                    code="missing_project_json",
                ) from e
            project_data = json.loads(project_bytes.decode("utf-8"))

            # Format-version gate.
            ver = metadata.get("figpack_format_version")
            if not isinstance(ver, int) or ver > FIGPACK_FORMAT_VERSION:
                raise BundleError(
                    f"unsupported figpack format version {ver!r}; this "
                    f"build understands up to {FIGPACK_FORMAT_VERSION}",
                    code="unsupported_version",
                )

            # Build sha256 lookup keyed by archive_path.
            sha_by_path: Dict[str, str] = {}
            for rec in metadata.get("manifest", {}).values():
                ap = rec.get("archive_path")
                sh = rec.get("sha256")
                if ap and sh:
                    sha_by_path[ap] = sh

            # Stream-extract every file entry except the JSON ones we
            # already consumed.
            asset_count = 0
            file_entries = [e for e in entries if e.relpath not in (
                PROJECT_JSON, METADATA_JSON, PREVIEW_JPEG, README_HTML,
            )]
            total = max(len(file_entries), 1)
            for i, ve in enumerate(file_entries):
                if cancel and cancel():
                    raise BundleError("operation cancelled", code="cancelled")
                if progress:
                    progress(
                        i / total,
                        f"Extracting {os.path.basename(ve.relpath)}",
                    )
                expected = sha_by_path.get(ve.relpath)
                _stream_extract(
                    zf, ve.relpath, ve.dest_abspath,
                    expected_sha256=expected,
                    cancel=cancel,
                )
                extracted_paths.append(ve.dest_abspath)
                asset_count += 1

        # Rewrite project_data resource markers → real paths.
        missing = _resolve_resource_paths(project_data, metadata.get("manifest", {}), target_real)

        # Atomically remove the sentinel last — only after success.
        try:
            os.unlink(sentinel)
        except OSError:
            pass

        if progress:
            progress(1.0, "Done")

        return UnpackResult(
            target_dir=target_real,
            asset_count=asset_count,
            project_data=project_data,
            metadata=metadata,
            missing_count=missing,
        )
    except BaseException:
        # Roll back partial extraction. The sentinel stays in place;
        # the cleanup pass will see it (with no holder) and treat the
        # working dir as orphaned, removing it on the next launch
        # (plan §3.2.6).
        for p in extracted_paths:
            try:
                if os.path.exists(p):
                    os.unlink(p)
            except OSError:
                pass
        raise


# ──────────────────────────────────────────────────────────────────────
# High-level: open a bundle into a managed working directory
# ──────────────────────────────────────────────────────────────────────

def open_bundle(
    pack_path: str,
    *,
    cache_root: Optional[str] = None,
    quota_bytes: int = DEFAULT_QUOTA_BYTES,
    progress: Optional[ProgressCB] = None,
    cancel: Optional[CancelCB] = None,
    limits: SafetyLimits = SafetyLimits(),
) -> Tuple[WorkingDir, UnpackResult]:
    """Allocate a locked working dir and extract *pack_path* into it.

    The returned :class:`WorkingDir` owns the OS-level lock for the
    cache directory and **must** be released (via context-manager exit
    or :meth:`WorkingDir.release`) when the caller is done with the
    extracted assets — typically when the corresponding tab is closed.

    On any failure during extraction the lock is released and the
    partial working directory is wiped synchronously, so the cache
    never accumulates sub-grace-period orphans on routine errors
    (corrupt archive, sha256 mismatch, cancelled by user, etc.).
    """
    # Best-effort projection of unzipped size for quota planning. We
    # peek at the central directory only — no extraction yet.
    estimated = 0
    try:
        with zipfile.ZipFile(pack_path, "r", allowZip64=True) as zf:
            for info in zf.infolist():
                estimated += info.file_size
    except (zipfile.BadZipFile, OSError):
        # Defer the real diagnosis to unpack_project; just don't reserve
        # any space if we can't even read the archive.
        estimated = 0

    workdir = allocate_working_dir(
        pack_path,
        cache_root=cache_root,
        quota_bytes=quota_bytes,
        estimated_uncompressed_bytes=estimated,
    )
    try:
        try:
            result = unpack_project(
                pack_path,
                workdir.path,
                progress=progress,
                cancel=cancel,
                limits=limits,
            )
        except zipfile.BadZipFile as e:
            raise BundleError(
                f"not a valid figpack archive: {e}",
                code="bad_archive",
            ) from e
        return workdir, result
    except BaseException:
        # Tear down synchronously — the orphan-sweep grace period is
        # for *crashes*, not for clean error paths.
        try:
            workdir.release()
        finally:
            _safe_rmtree(workdir.path)
        raise
