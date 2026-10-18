"""
Loss-aware downgrade from the current project schema to a target schema
that an older ILM release can open.

Each step in DOWNGRADES converts a schema-N dict (already a private
copy) into schema N-1 and reports ``(code, count)`` issues describing
what had to be left out. ``downgrade_project_data`` deep-copies the
input, walks the chain, stamps the target ``schema_version`` and keeps
``file_version`` untouched. Issue ``code`` strings are rendered to
localized text in the app layer (src/app/save_older_dialog.py) so this
module stays Qt-free.
"""

import copy
from typing import Any, Dict, List, Tuple

from src.model.migrations import PROJECT_SCHEMA_VERSION

Issue = Tuple[str, int]

# (target schema, release range that reads it), best target first.
DOWNGRADE_TARGETS = [
    (7, "3.6.0 – 3.6.1"),
    (6, "3.5.2 – 3.5.3"),
    (5, "3.5.1"),
    (4, "3.4.2 – 3.4.3"),
]


def _iter_cells(data: Dict[str, Any]):
    stack = list(data.get("cells", []))
    while stack:
        cell = stack.pop()
        yield cell
        stack.extend(cell.get("children") or [])


def _down_8_to_7(data: Dict[str, Any]) -> Tuple[Dict[str, Any], List[Issue]]:
    data = copy.deepcopy(data)
    removed = 0
    for cell in _iter_cells(data):
        if "raster_text_regions" not in cell:
            continue
        kept = []
        for region in cell.get("raster_text_regions") or []:
            if region.get("angle"):
                removed += 1
            else:
                region.pop("angle", None)
                kept.append(region)
        cell["raster_text_regions"] = kept
    data["schema_version"] = 7
    return data, [("rotated_text_removed", removed)]


def _down_7_to_6(data: Dict[str, Any]) -> Tuple[Dict[str, Any], List[Issue]]:
    data = copy.deepcopy(data)
    merged = 0
    for item in data.get("text_items") or []:
        if item.pop("sub_labels", None):
            merged += 1
        item.pop("sub_label_splits", None)
    data["schema_version"] = 6
    return data, [("split_labels_merged", merged)]


def _down_6_to_5(data: Dict[str, Any]) -> Tuple[Dict[str, Any], List[Issue]]:
    data = copy.deepcopy(data)
    marks = data.pop("marks", None) or []
    data["schema_version"] = 5
    return data, [("marks_removed", len(marks))]


def _down_5_to_4(data: Dict[str, Any]) -> Tuple[Dict[str, Any], List[Issue]]:
    data = copy.deepcopy(data)
    lost = 0
    for cell in _iter_cells(data):
        reflow = cell.pop("plot_reflow", None)
        if (
            reflow is False
            and str(cell.get("image_path") or "").endswith(".ilmplot.svg")
        ):
            lost += 1
    data["schema_version"] = 4
    return data, [("plot_reflow_lost", lost)]


DOWNGRADES = {
    8: _down_8_to_7,
    7: _down_7_to_6,
    6: _down_6_to_5,
    5: _down_5_to_4,
}


def downgrade_project_data(
    data: Dict[str, Any], target_schema: int
) -> Tuple[Dict[str, Any], List[Issue]]:
    """Return ``(new_data, issues)`` downgraded to *target_schema*.

    *data* is a current-schema dict as produced by ``Project.to_dict()``;
    it is never mutated. Issues with a zero count are omitted.
    """
    if target_schema >= PROJECT_SCHEMA_VERSION:
        raise ValueError(f"target schema must be < {PROJECT_SCHEMA_VERSION}")
    if target_schema not in dict(DOWNGRADE_TARGETS):
        raise ValueError(f"unsupported downgrade target schema {target_schema}")
    out = copy.deepcopy(data)
    merged: Dict[str, int] = {}
    order: List[str] = []
    schema = out.get("schema_version", PROJECT_SCHEMA_VERSION)
    while schema > target_schema:
        step = DOWNGRADES.get(schema)
        if step is None:
            raise ValueError(f"no downgrade step from schema {schema}")
        out, issues = step(out)
        for code, count in issues:
            if code not in merged:
                order.append(code)
                merged[code] = 0
            merged[code] += count
        schema -= 1
    out["schema_version"] = target_schema
    return out, [(code, merged[code]) for code in order if merged[code] > 0]
