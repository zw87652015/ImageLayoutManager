"""
Scale bar mappings manager.

Manages user-defined mappings from a name to a µm/pixel value, stored in a
JSON file under the user's home directory.  Ships with two built-in defaults
that preserve backward compatibility with projects saved before this feature.
"""

import json
import os
from typing import List, Tuple

_CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".imagelayoutmanager", "scale_bar_mappings.json")

# Built-in defaults (kept for backward compatibility with old project files)
_BUILTIN_DEFAULTS: List[Tuple[str, float]] = [
    ("rgb", 0.1301),
    ("bayer", 0.2569),
]


def _default_mappings() -> List[dict]:
    return [{"name": name, "um_per_px": val, "unit": "µm"} for name, val in _BUILTIN_DEFAULTS]


def load_mappings() -> List[dict]:
    """Return list of dicts with keys 'name' and 'um_per_px'."""
    if os.path.exists(_CONFIG_PATH):
        try:
            with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            mappings = data.get("mappings", [])
            # Validate entries and ensure 'unit' exists
            valid = []
            for m in mappings:
                if isinstance(m.get("name"), str) and isinstance(m.get("um_per_px"), (int, float)):
                    m.setdefault("unit", "µm")
                    valid.append(m)
            if valid:
                return valid
        except Exception:
            pass
    return _default_mappings()


def save_mappings(mappings: List[dict]) -> None:
    """Persist the mappings list to disk."""
    os.makedirs(os.path.dirname(_CONFIG_PATH), exist_ok=True)
    with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump({"mappings": mappings}, f, indent=2, ensure_ascii=False)


def get_um_per_px(name: str) -> float:
    """
    Return the µm/pixel value for a mapping name.

    Falls back to the old hard-coded values for 'rgb' / 'bayer' so that
    project files saved before this feature still render correctly even if the
    user has not yet customised their mapping list.
    """
    for m in load_mappings():
        if m["name"] == name:
            return float(m["um_per_px"])
    # Hard-coded legacy fallback
    legacy = dict(_BUILTIN_DEFAULTS)
    return legacy.get(name, 0.1301)


def mapping_names() -> List[str]:
    """Return just the names of all defined mappings."""
    return [m["name"] for m in load_mappings()]
