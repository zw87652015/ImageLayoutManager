"""
figpack — bundled-project (.figpack) support.

Public API lives in ``package_manager``; the other modules are
implementation details but are importable for unit testing.

See plan.md in the repository root for the full specification.
"""

from src.utils.figpack.errors import (
    BundleError,
    BundleIntegrityError,
    BundleSecurityError,
)
from src.utils.figpack.package_manager import (
    AssetRecord,
    PackResult,
    UnpackResult,
    pack_project,
    unpack_project,
    open_bundle,
    FIGPACK_FORMAT_VERSION,
)
from src.utils.figpack.zip_safety import SafetyLimits
from src.utils.figpack.cache_manager import (
    WorkingDir,
    allocate_working_dir,
    cleanup_orphans,
    default_cache_root,
    register_pre_delete_hook,
)

__all__ = [
    "BundleError",
    "BundleIntegrityError",
    "BundleSecurityError",
    "AssetRecord",
    "PackResult",
    "UnpackResult",
    "SafetyLimits",
    "pack_project",
    "unpack_project",
    "open_bundle",
    "FIGPACK_FORMAT_VERSION",
    "WorkingDir",
    "allocate_working_dir",
    "cleanup_orphans",
    "default_cache_root",
    "register_pre_delete_hook",
]
