"""Utilities for nested layout support: circular reference detection and thumbnail generation."""

import os
import json
from typing import Optional, Set


def detect_circular_reference(
    parent_path: str,
    candidate_path: str,
    visited: Optional[Set[str]] = None,
) -> bool:
    """Return True if importing candidate_path would create a circular reference.

    Walks the nested_layout_path fields inside candidate_path (and recursively
    inside any sub-layouts it references) to see if any of them point back to
    parent_path or any file already in the visited set.
    """
    parent_path = os.path.normcase(os.path.abspath(parent_path))
    candidate_path = os.path.normcase(os.path.abspath(candidate_path))

    if parent_path == candidate_path:
        return True

    if visited is None:
        visited = set()
    visited.add(parent_path)

    return _walk_for_cycle(candidate_path, visited)


def _walk_for_cycle(path: str, visited: Set[str]) -> bool:
    """Recursively check if *path* or any of its nested layouts is in *visited*."""
    path = os.path.normcase(os.path.abspath(path))

    if path in visited:
        return True

    visited.add(path)

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return False

    cells = data.get("cells", [])
    for cell in cells:
        nested = cell.get("nested_layout_path")
        if nested and os.path.isfile(nested):
            if _walk_for_cycle(nested, visited):
                return True

    return False
