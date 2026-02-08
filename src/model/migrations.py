"""
Project file migration system.

Each migration function upgrades a project dict from one version to the next.
Register migrations in MIGRATIONS as (from_version, to_version, function).
They are applied sequentially when loading an older file.
"""

from typing import Dict, Any, List, Tuple, Callable

from src.version import APP_VERSION


def _ver(s: str) -> Tuple[int, ...]:
    """Parse a version string like '1.2.3' into a comparable tuple."""
    return tuple(int(x) for x in s.split("."))

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
MIGRATIONS: List[Tuple[str | None, str, Callable[[Dict[str, Any]], Dict[str, Any]]]] = [
    (None, "1.0.0", _migrate_none_to_1_0_0),
]


def migrate_project_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Apply all necessary migrations to bring *data* up to APP_VERSION.
    Returns the (mutated) data dict with ``file_version`` set to APP_VERSION.
    """
    file_ver_str = data.get("file_version", None)
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

        data = func(data)
        data["file_version"] = to_ver
        file_ver_str = to_ver

        if _ver(to_ver) >= target:
            break

    # Stamp current version
    data["file_version"] = APP_VERSION
    return data
