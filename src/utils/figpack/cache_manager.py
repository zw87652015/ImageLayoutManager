"""
figpack working-directory cache manager (plan.md §3.2).

Responsibilities:

* Pick the per-OS cache root and create it on demand
  (Windows: ``%LOCALAPPDATA%\\ImageLayoutManager\\figpack_cache``;
  macOS:   ``~/Library/Caches/ImageLayoutManager/figpack_cache.noindex``;
  Linux:   ``$XDG_CACHE_HOME/ImageLayoutManager/figpack_cache``).
* Allocate a per-archive working directory keyed by
  ``sha1(abs_pack_path)[:12] + "__" + random``.
* Hold an OS-level exclusive lock for the lifetime of the tab so
  other instances can detect ownership without trusting PIDs / mtimes.
* Sweep orphaned working dirs on app start: a dir whose ``.lock`` is
  unheld and whose ``.extracting`` sentinel (if any) is older than
  10 minutes is deleted with a small retry loop (Windows AV / Spotlight
  briefly hold files open).
* Enforce a soft quota (default 10 GiB) by evicting unlocked dirs in
  LRU order before allocating a new one.

Nothing in here knows about ZIP internals — the actual extraction is
``package_manager.unpack_project``. The cache manager hands out a
target dir and stays out of the way.

The :class:`WorkingDir` returned by :func:`allocate_working_dir` is a
context manager: leaving the ``with`` block releases the lock so the
next cleanup pass can collect the directory if the caller decides not
to keep it.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import shutil
import stat
import sys
import time
from dataclasses import dataclass
from typing import Callable, Iterator, List, Optional, Tuple

from src.utils.figpack.encoding import to_nfc
from src.utils.figpack.errors import BundleError
from src.utils.figpack.file_lock import ExclusiveLock, LockHeldError, is_locked

# ──────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────

LOCK_FILENAME = ".lock"
EXTRACTING_SENTINEL = ".extracting"

# A dir whose .extracting sentinel is older than this *and* whose lock
# is unheld is considered "crashed mid-extraction" and may be reaped.
EXTRACTING_GRACE_SECONDS = 10 * 60

DEFAULT_QUOTA_BYTES = 10 * 1024 ** 3  # 10 GiB
DELETE_RETRIES = 3
DELETE_RETRY_BACKOFF_S = 0.1


# ──────────────────────────────────────────────────────────────────────
# Image-proxy flush hook (plan §3.2.5)
# ──────────────────────────────────────────────────────────────────────
#
# Windows refuses to delete files that are still open for read. Before
# we tear down a working directory we must close every PIL ``Image`` /
# ``QImageReader`` handle that points inside it. The cache manager
# itself doesn't depend on Qt; the UI layer registers a callback here
# at startup.
_pre_delete_hook: Optional[Callable[[str], None]] = None


def register_pre_delete_hook(
    hook: Optional[Callable[[str], None]],
) -> None:
    """Register a callback invoked with each working-dir path right
    before :func:`_safe_rmtree`. Pass ``None`` to clear the hook.

    The callback must close any open file handles the caller owns
    that point inside *path*. Exceptions raised by the hook are
    swallowed — deletion proceeds regardless.
    """
    global _pre_delete_hook
    _pre_delete_hook = hook


def _run_pre_delete_hook(path: str) -> None:
    cb = _pre_delete_hook
    if cb is None:
        return
    try:
        cb(path)
    except Exception:
        pass


# ──────────────────────────────────────────────────────────────────────
# Cache root
# ──────────────────────────────────────────────────────────────────────

def default_cache_root() -> str:
    """Return the OS-blessed cache root, creating it if needed."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser(
            r"~\AppData\Local"
        )
        root = os.path.join(base, "ImageLayoutManager", "figpack_cache")
    elif sys.platform == "darwin":
        # `.noindex` keeps Spotlight from indexing multi-GB TIFFs.
        root = os.path.expanduser(
            "~/Library/Caches/ImageLayoutManager/figpack_cache.noindex"
        )
    else:
        base = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser(
            "~/.cache"
        )
        root = os.path.join(base, "ImageLayoutManager", "figpack_cache")

    os.makedirs(root, exist_ok=True)
    _try_mark_not_indexed(root)
    return root


def _try_mark_not_indexed(path: str) -> None:
    """Best-effort: hide cache from indexers on Windows.

    macOS uses the ``.noindex`` suffix on the directory name itself
    (handled in :func:`default_cache_root`); Linux indexers honor
    ``.nomedia`` / ``.trackerignore`` but those are out of scope for v1.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes  # local import — Windows only

        FILE_ATTRIBUTE_HIDDEN = 0x02
        FILE_ATTRIBUTE_NOT_CONTENT_INDEXED = 0x2000
        attrs = (
            FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_NOT_CONTENT_INDEXED
        )
        ctypes.windll.kernel32.SetFileAttributesW(path, attrs)
    except Exception:
        # Non-fatal — indexing-exclusion is a hint, not a correctness
        # property.
        pass


# ──────────────────────────────────────────────────────────────────────
# Working-dir allocation
# ──────────────────────────────────────────────────────────────────────

def _archive_key(pack_path: str) -> str:
    """Deterministic short key derived from the archive's abs path.

    Two windows opening the same archive get the same key prefix but
    different random suffixes, so they never share a working dir.
    """
    norm = to_nfc(os.path.abspath(pack_path))
    return hashlib.sha1(norm.encode("utf-8")).hexdigest()[:12]


@dataclass
class WorkingDir:
    """Owned working directory plus its held lock.

    Use as a context manager; on exit the lock is released, after which
    the next cleanup pass is free to delete the directory.
    """
    path: str
    pack_path: str
    _lock: ExclusiveLock

    def __enter__(self) -> "WorkingDir":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()

    def release(self) -> None:
        self._lock.release()


def allocate_working_dir(
    pack_path: str,
    *,
    cache_root: Optional[str] = None,
    quota_bytes: int = DEFAULT_QUOTA_BYTES,
    estimated_uncompressed_bytes: int = 0,
) -> WorkingDir:
    """Create + lock a fresh working directory for *pack_path*.

    Order of operations:

    1. Sweep orphaned dirs (cheap; bounded by `os.listdir` of the cache
       root).
    2. Enforce quota: if cache size + projected need exceeds the quota,
       evict unlocked dirs in LRU order.
    3. ``mkdir`` ``<cache_root>/<key>__<random>``, take its ``.lock``.

    Raises :class:`BundleError` if the cache cannot satisfy the quota.
    """
    root = cache_root or default_cache_root()
    cleanup_orphans(root)
    _enforce_quota(
        root,
        quota_bytes=quota_bytes,
        incoming_bytes=estimated_uncompressed_bytes,
    )
    _check_disk_free(root, estimated_uncompressed_bytes)

    key = _archive_key(pack_path)
    suffix = secrets.token_hex(4)
    workdir = os.path.join(root, f"{key}__{suffix}")
    os.makedirs(workdir, exist_ok=False)

    lock = ExclusiveLock(os.path.join(workdir, LOCK_FILENAME))
    try:
        lock.acquire()
    except BaseException:
        # Allocation failed; tear down the empty dir so we don't leak.
        try:
            shutil.rmtree(workdir, ignore_errors=True)
        except OSError:
            pass
        raise

    return WorkingDir(path=workdir, pack_path=pack_path, _lock=lock)


# ──────────────────────────────────────────────────────────────────────
# Cleanup / quota
# ──────────────────────────────────────────────────────────────────────

def cleanup_orphans(cache_root: Optional[str] = None) -> List[str]:
    """Delete every working dir in *cache_root* whose lock is unheld.

    A dir with a present ``.extracting`` sentinel younger than
    :data:`EXTRACTING_GRACE_SECONDS` is *skipped* even if its lock is
    free — another instance is currently writing into it.

    Returns the list of paths that were successfully deleted.
    """
    root = cache_root or default_cache_root()
    deleted: List[str] = []
    if not os.path.isdir(root):
        return deleted

    for name in os.listdir(root):
        sub = os.path.join(root, name)
        if not os.path.isdir(sub):
            continue
        lock_path = os.path.join(sub, LOCK_FILENAME)
        sentinel = os.path.join(sub, EXTRACTING_SENTINEL)

        # If the lock file doesn't exist at all, the dir is malformed
        # (probably leftover from a failed mkdir); reap it.
        lock_exists = os.path.exists(lock_path)
        if lock_exists and is_locked(lock_path):
            continue  # owned by another live instance

        if os.path.exists(sentinel):
            try:
                age = time.time() - os.path.getmtime(sentinel)
            except OSError:
                age = 0
            if age < EXTRACTING_GRACE_SECONDS:
                continue

        if _safe_rmtree(sub):
            deleted.append(sub)
    return deleted


def _check_disk_free(cache_root: str, incoming_bytes: int) -> None:
    """Refuse extraction when the cache volume's free space is below
    ``incoming_bytes * 1.10`` (plan §3.2.4 — must hold *before* writing
    any byte). Best-effort on platforms where ``shutil.disk_usage`` is
    unsupported.
    """
    if incoming_bytes <= 0:
        return
    try:
        free = shutil.disk_usage(cache_root).free
    except OSError:
        return
    needed = int(incoming_bytes * 1.10)
    if free < needed:
        raise BundleError(
            f"insufficient free space on cache volume: need ~{needed:,} "
            f"bytes, only {free:,} available at {cache_root!r}",
            code="cache_disk_full",
        )


def _enforce_quota(
    cache_root: str,
    *,
    quota_bytes: int,
    incoming_bytes: int,
) -> None:
    """Evict unlocked dirs (LRU by lock mtime) until quota fits."""
    if quota_bytes <= 0:
        return

    candidates = list(_iter_unlocked(cache_root))
    used = sum(sz for _, _, sz in candidates) + sum(
        sz for _, sz in _iter_locked_sizes(cache_root)
    )
    needed = used + max(incoming_bytes, 0)
    if needed <= quota_bytes:
        return

    # Sort by lock mtime ascending (oldest first → LRU).
    candidates.sort(key=lambda t: t[1])
    for path, _mtime, size in candidates:
        if needed <= quota_bytes:
            break
        if _safe_rmtree(path):
            needed -= size

    if needed > quota_bytes:
        raise BundleError(
            f"figpack cache quota exceeded: need {needed} bytes, "
            f"quota is {quota_bytes} bytes; free up disk space or "
            f"raise the quota in Preferences",
            code="cache_quota_exceeded",
        )


def _iter_unlocked(
    cache_root: str,
) -> Iterator[Tuple[str, float, int]]:
    """Yield ``(path, lock_mtime, dir_size_bytes)`` for unlocked dirs."""
    if not os.path.isdir(cache_root):
        return
    for name in os.listdir(cache_root):
        sub = os.path.join(cache_root, name)
        if not os.path.isdir(sub):
            continue
        lock_path = os.path.join(sub, LOCK_FILENAME)
        if not os.path.exists(lock_path) or is_locked(lock_path):
            continue
        # Skip in-flight extractions.
        sentinel = os.path.join(sub, EXTRACTING_SENTINEL)
        if os.path.exists(sentinel):
            try:
                if (time.time() - os.path.getmtime(sentinel)
                        < EXTRACTING_GRACE_SECONDS):
                    continue
            except OSError:
                pass
        try:
            mtime = os.path.getmtime(lock_path)
        except OSError:
            mtime = 0.0
        yield sub, mtime, _dir_size(sub)


def _iter_locked_sizes(cache_root: str) -> Iterator[Tuple[str, int]]:
    """Yield ``(path, size)`` for currently-locked dirs (kept in budget)."""
    if not os.path.isdir(cache_root):
        return
    for name in os.listdir(cache_root):
        sub = os.path.join(cache_root, name)
        if not os.path.isdir(sub):
            continue
        lock_path = os.path.join(sub, LOCK_FILENAME)
        if os.path.exists(lock_path) and is_locked(lock_path):
            yield sub, _dir_size(sub)


def _dir_size(path: str) -> int:
    total = 0
    for dirpath, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(dirpath, f))
            except OSError:
                pass
    return total


# ──────────────────────────────────────────────────────────────────────
# Robust deletion (Windows-safe)
# ──────────────────────────────────────────────────────────────────────

def _on_rmtree_error(func, path, exc_info) -> None:
    """``shutil.rmtree`` ``onerror`` hook that clears the read-only bit
    (Windows refuses to delete files with FILE_ATTRIBUTE_READONLY) and
    retries once. Subsequent failures bubble out to the caller's
    retry loop."""
    try:
        os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
        func(path)
    except OSError:
        # Let the outer retry loop handle it.
        raise


def _safe_rmtree(path: str) -> bool:
    """Delete *path* with retry on transient Windows / AV errors.

    Invokes the registered pre-delete hook (plan §3.2.5) once before
    the first attempt so the caller can flush PIL / QImageReader
    handles that would otherwise pin files inside *path*.
    """
    _run_pre_delete_hook(path)
    last_err: Optional[BaseException] = None
    for i in range(DELETE_RETRIES):
        try:
            shutil.rmtree(path, onerror=_on_rmtree_error)
            return True
        except OSError as e:
            last_err = e
            time.sleep(DELETE_RETRY_BACKOFF_S * (i + 1))
    # Final swallow — the caller (cleanup pass) shouldn't crash on a
    # single sticky cache dir; we'll get it next launch.
    return False
