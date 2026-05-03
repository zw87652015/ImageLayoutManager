# .figpack Format Specification

Version: **2**  
Last updated: 2026-05-03

---

## Overview

A `.figpack` file is a ZIP archive (ZIP64-capable) that bundles a complete ImageLayoutManager figure — layout JSON, all referenced image assets, a rendered preview, and a human-readable audit page — into a single portable file.

The format is intentionally simple: rename any `.figpack` to `.zip` and extract it with any standard ZIP tool to inspect its contents.

---

## Archive Structure

```
figure.figpack          (ZIP64 archive)
├── project.json        required — layout and settings
├── metadata.json       required — format version, publication metadata, asset manifest
├── preview.jpg         optional — JPEG thumbnail, long-edge ≤ 1920 px
├── README.html         optional — self-contained human-readable audit page
└── assets/
    └── <hash_dir>/
        └── <filename>  image assets, path derived from original source path hash
```

All filenames inside the archive use UTF-8 encoding (ZIP flag bit 0x800 set).

---

## `metadata.json`

Top-level fields:

| Field | Type | Description |
|---|---|---|
| `figpack_format_version` | integer | Format version. This document describes version **2**. |
| `app_version` | string | ImageLayoutManager version that wrote this file (e.g. `"3.3.0"`). |
| `created_at` | string | ISO 8601 UTC timestamp of last save (e.g. `"2026-05-03T10:00:00Z"`). |
| `figure_number` | string | Publication figure identifier (e.g. `"Figure 1"`, `"Supplementary Figure 3"`). May be empty. |
| `figure_title` | string | Short descriptive title for the figure. May be empty. |
| `host.os` | string | OS that wrote the file (`"windows"`, `"darwin"`, `"linux"`). |
| `host.user` | string | Username hint — not guaranteed to be present or accurate. |
| `manifest` | object | Asset records keyed by resource ID (see below). |
| `icc_profiles` | object | Reserved for Phase 3 ICC profile bundling. Currently always `{}`. |

### `manifest` entries

Each entry is keyed by a resource ID (`"res_1"`, `"res_2"`, …):

| Field | Type | Description |
|---|---|---|
| `archive_path` | string or null | Path inside the ZIP where the asset bytes live. Null if missing. |
| `original_source_path` | string | Absolute path to the source file on the machine that packed this bundle. Used to re-link if the asset goes missing. |
| `sha256` | string or null | Hex SHA-256 of the asset bytes. Null if missing. |
| `size_bytes` | integer | Byte size of the asset. 0 if missing. |
| `status` | string | `"ok"` or `"missing"`. |

---

## `project.json`

Contains the full layout definition. Key top-level fields:

| Field | Type | Description |
|---|---|---|
| `file_version` | string | App version that wrote this file. |
| `name` | string | Project/figure name. |
| `figure_number` | string | Same as `metadata.json` — kept in sync on every save. |
| `figure_title` | string | Same as `metadata.json` — kept in sync on every save. |
| `page_width_mm` | float | Canvas width in millimetres. |
| `page_height_mm` | float | Canvas height in millimetres. |
| `dpi` | integer | Export resolution. |
| `cells` | array | Recursive cell tree. Leaf cells reference assets via `"figpack:res_N"` resource markers. |

Cell `image_path` values inside the archive always use the `"figpack:res_N"` prefix. When unpacked, these are rewritten to absolute on-disk paths before being handed to the application.

---

## Version History

| Version | Change |
|---|---|
| 1 | Initial release. |
| 2 | Added `figure_number` and `figure_title` to `metadata.json` and `project.json`. |

---

## Compatibility Rules

- A reader that knows version N **must** accept all files with `figpack_format_version ≤ N`.
- A reader that knows version N **must** reject files with `figpack_format_version > N` with a clear error.
- New fields added in a version bump always have safe defaults (empty string, empty object) so older readers that ignore unknown keys are unaffected.

---

## Security Properties

The packer enforces the following on every write, and the unpacker validates on every read:

- **Zip-slip prevention** — all extracted paths are verified to stay within the target directory.
- **Zip-bomb prevention** — total uncompressed size and entry count are capped (`SafetyLimits`).
- **No encryption** — encrypted ZIP entries are rejected.
- **No symlinks** — symlink entries are rejected.
- **SHA-256 integrity** — every asset is verified against its manifest hash on unpack.
- **Atomic writes** — the output file is never partially written; a temp file is renamed into place only on success.
