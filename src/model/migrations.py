"""
Project file migration system.

Legacy application-version migrations are registered in MIGRATIONS.
Schema migrations are registered by their source revision in SCHEMA_MIGRATIONS.
All loaders validate and upgrade copied data before constructing a Project.
"""

import copy
import math
import re
from typing import Dict, Any, List, Tuple, Callable, Optional

from src.version import APP_VERSION

PROJECT_SCHEMA_VERSION = 3


class ProjectMigrationError(ValueError):
    pass


class UnsupportedProjectVersion(ProjectMigrationError):
    pass


def _ver(s: str) -> Tuple[int, ...]:
    """Parse a legacy application version for compatibility checks."""
    if not isinstance(s, str):
        raise ProjectMigrationError('Invalid project file_version: expected a version string.')
    match = re.fullmatch(r'v?(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:[-+][0-9A-Za-z][0-9A-Za-z.+-]*)?', s)
    if not match:
        raise ProjectMigrationError(f'Invalid project file_version: {s!r}.')
    return tuple(int(part or 0) for part in match.groups())

# ──────────────────────────────────────────────
# Migration functions
# ──────────────────────────────────────────────
# Each function receives the raw project dict and returns the mutated dict.
# Convention: def _migrate_X_to_Y(data: dict) -> dict


def _migrate_none_to_1_0_0(data: Dict[str, Any]) -> Dict[str, Any]:
    """Upgrade pre-versioned files to 1.0.0 schema."""
    # Ensure all 1.0.0 fields have defaults
    data.setdefault("label_align", "center")
    data.setdefault("label_offset_x", 0.0)
    data.setdefault("label_offset_y", 0.0)
    data.setdefault("label_row_height", 0.0)
    return data


# ──────────────────────────────────────────────
# Migration registry
# ──────────────────────────────────────────────
# (from_version_str | None, to_version_str, migration_func)
# None means "no version tag" (legacy files).
MIGRATIONS: List[Tuple[Optional[str], str, Callable[[Dict[str, Any]], Dict[str, Any]]]] = [
    (None, "1.0.0", _migrate_none_to_1_0_0),
]


def _records(data, key):
    records = data.get(key, [])
    if not isinstance(records, list) or any(not isinstance(item, dict) for item in records):
        raise ProjectMigrationError(f'Invalid project {key}: expected a list of objects.')
    return records


def validate_plot_area(data):
    if not isinstance(data, dict):
        raise ProjectMigrationError('Invalid plot_area: expected an object.')
    values = [data.get(key, default) for key, default in
              (('left', 0.0), ('top', 0.0), ('right', 1.0), ('bottom', 1.0))]
    if any(type(value) not in (int, float) or not 0.0 <= value <= 1.0
           or not math.isfinite(value) for value in values):
        raise ProjectMigrationError('Invalid plot_area: coordinates must be finite numbers from zero to one.')
    left, top, right, bottom = values
    if right <= left or bottom <= top:
        raise ProjectMigrationError('Invalid plot_area: select a box with positive width and height.')
    digest = data.get('source_digest', '')
    if not isinstance(digest, str) or (digest and not re.fullmatch(r'[0-9a-fA-F]{64}', digest)):
        raise ProjectMigrationError('Invalid plot_area source_digest: expected a SHA256 hex digest or an empty string.')


def validate_plot_alignment_group(data):
    if not isinstance(data, dict):
        raise ProjectMigrationError('Invalid plot alignment group: expected an object.')
    if 'id' in data and (not isinstance(data['id'], str) or not data['id']):
        raise ProjectMigrationError('Invalid plot alignment group id: expected a nonempty string.')
    if not isinstance(data.get('name', 'Plot alignment'), str):
        raise ProjectMigrationError('Invalid plot alignment group name: expected a string.')
    members = data.get('cell_ids', [])
    if (not isinstance(members, list) or not members
            or any(not isinstance(cid, str) or not cid for cid in members)):
        raise ProjectMigrationError('Invalid plot alignment cell_ids: select a nonempty list of cell IDs.')
    if len(members) != len(set(members)):
        raise ProjectMigrationError('Invalid plot alignment cell_ids: each member must be unique.')
    reference = data.get('reference_id', '')
    if not isinstance(reference, str) or reference not in members:
        raise ProjectMigrationError('Invalid plot alignment reference_id: select a declared member.')
    if data.get('sizing_mode', 'reference') not in ('reference', 'fit'):
        raise ProjectMigrationError('Invalid plot alignment sizing_mode: choose reference or fit.')
    baseline = data.get('baseline_mode', 'grid_rows')
    if baseline not in ('grid_rows', 'single', 'custom'):
        raise ProjectMigrationError('Invalid plot alignment baseline_mode: choose grid_rows, single or custom.')
    rows = data.get('row_groups', {})
    if (not isinstance(rows, dict)
            or any(not isinstance(cid, str) or type(row) is not int or row < 0
                   for cid, row in rows.items())):
        raise ProjectMigrationError('Invalid plot alignment row_groups: use cell IDs and nonnegative integer rows.')
    if baseline == 'custom' and any(cid not in rows for cid in members):
        raise ProjectMigrationError('Invalid plot alignment row_groups: assign every member to a row.')


def _validate_structure(data):
    for group in _records(data, 'plot_alignment_groups'):
        validate_plot_alignment_group(group)
    for key in ('rows', 'size_groups', 'text_items', 'group_labels'):
        _records(data, key)
    for group in _records(data, 'svg_text_groups'):
        _records(group, 'members')
    if data.get('export_region') is not None and not isinstance(data['export_region'], dict):
        raise ProjectMigrationError('Invalid project export_region: expected an object or null.')
    stack = list(_records(data, 'cells'))
    while stack:
        cell = stack.pop()
        stack.extend(_records(cell, 'children'))
        _records(cell, 'pip_items')
        _records(cell, 'raster_text_regions')
        if cell.get('plot_area') is not None:
            validate_plot_area(cell['plot_area'])


def _migrate_schema_0_to_1(data):
    file_ver_str = data.get('file_version')
    target = _ver(APP_VERSION)
    for from_ver, to_ver, func in MIGRATIONS:
        # Determine whether this migration step should run
        if from_ver is None:
            # Applies only when the file has no version tag
            if file_ver_str is not None:
                continue
        else:
            if file_ver_str is not None and _ver(file_ver_str) >= _ver(to_ver):
                continue
        if _ver(to_ver) > target:
            continue
        data = func(data)
        file_ver_str = to_ver
        if _ver(to_ver) >= target:
            break

    defaults = {
        'page_width_mm': 210.0, 'page_height_mm': 297.0,
        'margin_left_mm': 10.0, 'margin_right_mm': 10.0,
        'margin_top_mm': 10.0, 'margin_bottom_mm': 10.0,
        'gap_mm': 2.0, 'dpi': 600, 'layout_mode': 'grid', 'grid_mode': 'stretch',
        'row_alignment': 'center', 'rows': [], 'cells': [], 'size_groups': [],
        'svg_text_groups': [], 'text_items': [], 'group_labels': [], 'export_region': None,
        'label_scheme': '(a)', 'label_scheme_sub': '', 'label_sub_prefix_parent': False,
        'label_sub_separator': '', 'label_placement': 'in_cell', 'label_font_family': 'Arial',
        'label_font_size': 12, 'label_font_weight': 'bold', 'label_color': '#000000',
        'label_anchor': 'top_left', 'label_align': 'center', 'label_valign': 'center',
        'label_offset_x': 0.0,
        'label_offset_y': 0.0, 'label_row_height': 0.0, 'label_col_width': 10.0,
        'figure_number': '', 'figure_title': '', 'tiff_color_mode': 'rgb',
        'cmyk_icc_profile_path': None, 'cmyk_rendering_intent': 1,
        'corner_label_font_family': 'Arial', 'corner_label_font_size': 12,
        'corner_label_font_weight': 'bold', 'corner_label_color': '#000000',
        'title_label_font_family': 'Arial', 'title_label_font_size': 10,
        'title_label_font_weight': 'normal', 'title_label_color': '#000000',
    }
    for key, default in defaults.items():
        data.setdefault(key, copy.deepcopy(default))
    stack = list(data['cells'])
    while stack:
        cell = stack.pop()
        if cell.get('nested_layout_path') and not cell.get('image_path'):
            raise ProjectMigrationError(
                'This project contains a legacy nested layout that cannot be converted automatically. '
                'Open it in the original ILM version and export that panel as an image first; '
                'the original project has not been modified.')
        cell.pop('nested_layout_path', None)
        cell.setdefault('scale_bar_um_per_px', {'rgb': 0.1301, 'bayer': 0.2569}.get(cell.get('scale_bar_mode', 'rgb'), 0.1301))
        cell.setdefault('svg_normalize_text', False)
        cell.setdefault('svg_normalize_text_pt', 8.0)
        cell.setdefault('raster_text_regions', [])
        for region in cell['raster_text_regions']:
            region.setdefault('chars', [])
            region.setdefault('warning', None)
            region.setdefault('foreign_excluded', False)
        stack.extend(cell.get('children', []))
    return data


def _migrate_schema_1_to_2(data):
    data.setdefault('plot_alignment_groups', [])
    stack = list(data.get('cells', []))
    while stack:
        cell = stack.pop()
        cell.setdefault('plot_area', None)
        stack.extend(cell.get('children', []))
    return data


def _migrate_schema_2_to_3(data):
    data.setdefault('label_valign', 'center')
    for item in data.get('text_items', []):
        item.setdefault('label_align', None)
        item.setdefault('label_valign', None)
        item.setdefault('label_offset_x', None)
        item.setdefault('label_offset_y', None)
    return data


SCHEMA_MIGRATIONS = {0: _migrate_schema_0_to_1, 1: _migrate_schema_1_to_2, 2: _migrate_schema_2_to_3}


def migrate_project_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate compatibility and return an upgraded copy without changing the writer version."""
    if not isinstance(data, dict):
        raise ProjectMigrationError('Invalid project: expected a JSON object.')
    schema = data.get('schema_version', 0)
    if type(schema) is not int or schema < 0:
        raise ProjectMigrationError('Invalid project schema_version: expected a non-negative integer.')
    if schema > PROJECT_SCHEMA_VERSION:
        raise UnsupportedProjectVersion(
            f'This project uses schema {schema}; ILM {APP_VERSION} supports up to schema '
            f'{PROJECT_SCHEMA_VERSION}. Please upgrade ILM to open this newer project.')
    writer = data.get('file_version')
    if writer is not None:
        writer_version = _ver(writer)
        if schema == 0 and writer_version > _ver(APP_VERSION):
            raise UnsupportedProjectVersion(
                f'This project was saved by newer ILM {writer} without a supported schema version. '
                f'Please upgrade ILM (installed: {APP_VERSION}).')
    _validate_structure(data)
    migrated = copy.deepcopy(data)
    while schema < PROJECT_SCHEMA_VERSION:
        upgrade = SCHEMA_MIGRATIONS.get(schema)
        if upgrade is None:
            raise ProjectMigrationError(f'No migration is available from project schema {schema}.')
        migrated = upgrade(migrated)
        schema += 1
        migrated['schema_version'] = schema
        _validate_structure(migrated)
    # Stamp current version
    migrated['schema_version'] = PROJECT_SCHEMA_VERSION
    return migrated
