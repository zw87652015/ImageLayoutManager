# ImageLayoutManager — agent notes

## Environment
- Conda env: `imagelayout` (`conda env create -f environment.yml`); `git` is not on PATH in the default shell.
- Run the app: `python main.py`; headless CLI: `python cli_main.py --help`.
- Windows packaging: keep Qt DLLs under `_internal/PyQt6/Qt6/bin`, not duplicate `_internal/Qt6*.dll` copies from Conda. Inno Setup upgrades must also remove obsolete top-level Qt DLLs with the targeted `[InstallDelete]` rule; copying a clean bundle over an old installation leaves stale DLLs behind. `python -m unittest test_windows_packaging` checks that cleanup stays limited to those files.

## Verification
- Tests are plain `unittest` modules at the repo root (no pytest config):
  - `python -m unittest test_svg_text_groups` — project-wide SVG text groups (canvas fingerprint, scale, export).
  - `python -m unittest test_raster_text` — raster text size matching (OCR → regions → resize → export).
  - `python -m unittest test_raster_text_overlay` — rounded text envelopes, protected pixels, preview selection, scaling, and theme colors.
  - `python -m unittest test_project_migrations test_project_bundle_compatibility` — legacy/schema migrations, future-version guards, plain/bundle parity, rendering and save integrity.
  - `python -m unittest test_welcome_drop` — welcome-window saved-project drag/drop, filtering, and opener routing.
  - `python -m unittest test_help_dialog` — bilingual in-app guide pages, rich-text markup, and shortcut/content checks. The offline guide content is embedded in `src/app/help_dialog.py`; tab labels live in `src/app/i18n.py`.
- GUI tests need `QT_QPA_PLATFORM=offscreen`; Qt finds no system fonts offscreen, so tests load
  `%WINDIR%\Fonts\arial.ttf` explicitly when text rendering matters.
- Byte-compile check: `python -m compileall -q src main.py cli_main.py`.

## Project compatibility
- `src/model/migrations.py::PROJECT_SCHEMA_VERSION` is the project-data revision, independent of `APP_VERSION`.
- `schema_version` is written by `Project.to_dict()`; `file_version` records the writing application.
- All `Project.from_dict()` calls validate/migrate copied input. Bundle unpack also validates the project before extracting assets; ZIP/container safety gates remain separate.
- Missing `schema_version` means legacy schema 0. Migration 0→1 preserves explicit values and freezes legacy project defaults; absent raster OCR character boxes remain empty, without running OCR on load.
- Unsupported future schemas and newer app-only legacy files raise actionable errors. A newer writer using a supported explicit schema is allowed.
- Future incompatible changes must increment `PROJECT_SCHEMA_VERSION` and register each source revision in `SCHEMA_MIGRATIONS`; never just relabel old data. Add compatibility fixtures for renamed fields, default changes, and rendering semantics.
- Loading does not rewrite the source. Plain project saves and bundle saves use atomic replacement. Removed nested layouts without an image fallback are rejected rather than silently losing content.

## Text size matching architecture
- Text groups (`Project.svg_text_groups`, `SvgTextGroup.font_size_pt`) are **points in the final figure**.
- `src/utils/panel_scale.py::panel_mm_per_unit` is the single source of truth for how many mm one image
  unit covers (fit/crop/rotation/layout); both SVG and raster pipelines divide by it.
- SVG: `svg_text_utils.get_svg_override_bytes_for_cell`; raster: `raster_text_utils.build_raster_override_spec`
  (+ `apply_raster_text_overrides`). Exporters go through `src/utils/text_overrides.overrides_for_cell`.
- Canvas: `CanvasScene.refresh_layout` puts both overrides in the per-cell fingerprint and passes them to
  `CellItem.update_data` → `ImageProxy.get_pixmap(..., svg_override_bytes, raster_override)` which caches per
  (path, content-hash), so the same file can render differently in different panels.
- OCR backends live in `src/utils/raster_text_ocr.py`; selection is in Preferences → Text Detection
  (`ocr_backend` / `ocr_command` QSettings). Default and shipped backend: `rapidocr` (+ `onnxruntime`).
- Raster safety checks (`analyze_region`, `raster_text_utils.py`) judge a box's *own interior* only:
  background = dominant colour (robust to mixed-height glyphs touching the box edge), "touching" =
  foreground continuing from just inside to just outside an edge (real external object, not the
  label's own ink). `_classify_text_pixels` additionally splits interior foreground into connected
  components and keeps only ones reaching the text line's shared baseline — anything else (e.g. a
  diagram pointer sitting in the dead space a box picks up above short letters when the same line
  has tall ones) is excluded from extraction/scaling and left un-erased on the canvas
  (`RasterTextRegion.foreign_excluded`). Floating blobs that ARE text ("-", i-dots, accents, ":") are
  rescued using the OCR's per-character boxes as the judge (`RasterTextRegion.chars`, filled by every
  backend that can: RapidOCR word boxes, Tesseract `image_to_boxes`, command JSON `chars`): a blob under
  a character in `_FLOATING_CHARS` / with a combining mark / CJK is text; under a plain letter it's
  foreign. With no char info, geometry falls back to x-height band + centred-diacritic rules.
