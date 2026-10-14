"""Qt-free helpers for choosing the project file format on save."""
from __future__ import annotations

import os
import re
from typing import Tuple

LAYOUT_FILTER = "Figure Layout (*.figlayout)"
JSON_FILTER = "JSON (*.json)"
BUNDLE_FILTER = "Figure Bundle (*.figpack)"
PROJECT_EXTS = (".figlayout", ".json", ".figpack")

_EXT_IN_FILTER = re.compile(r"\(\*(\.[^)\s]+)\)")


def project_filters(first_ext: str) -> Tuple[str, str]:
    """Return ``(filter_string, initial_filter)`` for the project save dialog.

    A bundle choice puts the bundle filter first; anything else keeps the
    default layout-first order.
    """
    if first_ext == ".figpack":
        return (f"{BUNDLE_FILTER};;{LAYOUT_FILTER};;{JSON_FILTER}", BUNDLE_FILTER)
    return (f"{LAYOUT_FILTER};;{JSON_FILTER};;{BUNDLE_FILTER}", LAYOUT_FILTER)


def ensure_extension(path: str, selected_filter: str) -> str:
    """Append the extension of *selected_filter* when *path* has no project extension."""
    if os.path.splitext(path)[1].lower() in PROJECT_EXTS:
        return path
    match = _EXT_IN_FILTER.search(selected_filter or "")
    ext = match.group(1) if match else ".figlayout"
    return path + ext
