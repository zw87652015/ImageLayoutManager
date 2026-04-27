"""
Atomic file writes for .figpack and any other "must not corrupt the
existing file on crash" path in the app.

Pattern (plan.md §3.1.1, §6.1):

  1. Create a temp file *in the same directory* as the final target,
     so :func:`os.replace` is always same-volume and therefore atomic
     on both NTFS (Windows) and APFS / HFS+ (macOS).
  2. Write all bytes through the supplied callback.
  3. ``flush()`` + ``os.fsync(fd)`` to push to disk before commit, so
     a power loss between rename and physical write cannot leave a
     zero-length file in place of the user's project.
  4. ``os.replace(tmp, target)`` to commit. On Windows this overwrites
     atomically iff source+dest are on the same volume; on POSIX it
     is unconditionally atomic.
  5. On *any* exception unlink the temp file and re-raise, leaving the
     pre-existing target untouched.

We intentionally do **not** put the temp file in ``%TEMP%`` / ``/tmp``:
that would silently turn the rename into a cross-volume copy, which
is not atomic and can leave a half-written file next to the user's
real project on crash.

Public API:

* :func:`atomic_write_bytes(path, data)`
* :func:`atomic_writer(path)` — context manager yielding a binary file
  object; commits on ``__exit__`` if no exception, rolls back otherwise.
* :func:`preflight_target(path)` — verifies the target directory exists,
  is writable, and has a sane amount of free space. Raises
  :class:`BundleError` with a user-readable message otherwise.
"""

from __future__ import annotations

import contextlib
import os
import secrets
import shutil
import tempfile
from typing import BinaryIO, Iterator

from src.utils.figpack.errors import BundleError


# ──────────────────────────────────────────────────────────────────────
# Pre-flight
# ──────────────────────────────────────────────────────────────────────

def preflight_target(path: str, *, min_free_bytes: int = 16 * 1024 * 1024) -> None:
    """Validate that we can plausibly write ``path``.

    Raises :class:`BundleError` if:
      * the parent directory does not exist
      * the parent directory is not writable
      * less than ``min_free_bytes`` of free space remains on the volume

    This is a best-effort check. On Windows in particular, the only
    truly reliable way to know whether you can write is to try; we do
    these checks to surface a friendlier error *before* the user has
    waited 30 s for a multi-GB pack to fail at the very last byte.
    """
    parent = os.path.dirname(os.path.abspath(path)) or "."

    if not os.path.isdir(parent):
        raise BundleError(
            f"Cannot save: directory does not exist: {parent}",
            code="preflight_no_dir",
        )

    # os.access is unreliable on Windows ACLs, but a False here is still
    # informative; we treat True as "probably ok" and let the actual
    # open() below produce the authoritative error if the ACL lies.
    if not os.access(parent, os.W_OK):
        raise BundleError(
            f"Cannot save: directory is not writable: {parent}",
            code="preflight_not_writable",
        )

    try:
        free = shutil.disk_usage(parent).free
    except OSError:
        # Some virtual filesystems (network mounts in odd states) raise
        # here. Don't fail pre-flight for that — let the real write try.
        return

    if free < min_free_bytes:
        raise BundleError(
            f"Cannot save: not enough free space on volume containing "
            f"{parent} (have {free // (1024*1024)} MiB, need at least "
            f"{min_free_bytes // (1024*1024)} MiB).",
            code="preflight_no_space",
        )


# ──────────────────────────────────────────────────────────────────────
# Internal: temp-file creation in the target directory
# ──────────────────────────────────────────────────────────────────────

def _open_sibling_tmp(path: str):
    """Open a fresh temp file in the same directory as ``path``.

    Returns ``(fd, tmp_path)``. Caller is responsible for closing the
    fd and either committing (``os.replace``) or unlinking it.
    """
    parent = os.path.dirname(os.path.abspath(path)) or "."
    base = os.path.basename(path)
    # `mkstemp` opens with O_EXCL so two concurrent writers can't pick
    # the same name. Adding random suffix on top is paranoia but cheap.
    suffix = f".tmp-{secrets.token_hex(4)}"
    fd, tmp = tempfile.mkstemp(prefix=f".{base}.", suffix=suffix, dir=parent)
    return fd, tmp


# ──────────────────────────────────────────────────────────────────────
# Public: atomic write
# ──────────────────────────────────────────────────────────────────────

@contextlib.contextmanager
def atomic_writer(path: str, *, preflight: bool = True) -> Iterator[BinaryIO]:
    """Context manager: ``with atomic_writer(p) as f: f.write(...)``.

    Commits on clean exit, rolls back (unlinks the tmp) on exception.
    The pre-existing ``path`` is *never* truncated or removed unless
    the commit succeeds, so a crash mid-write leaves the user's old
    file intact.
    """
    if preflight:
        preflight_target(path)

    fd, tmp = _open_sibling_tmp(path)
    f: BinaryIO | None = None
    try:
        f = os.fdopen(fd, "wb")
        yield f
        # Push file contents and metadata to disk before the rename.
        f.flush()
        try:
            os.fsync(f.fileno())
        except OSError:
            # fsync can fail on some network filesystems; the OS will
            # still flush eventually. Don't block the commit on that.
            pass
        f.close()
        f = None
        os.replace(tmp, path)
        tmp = ""  # signal: do not unlink
    except BaseException:
        # Best-effort rollback. We catch BaseException (not just
        # Exception) so KeyboardInterrupt / SystemExit also clean up.
        if f is not None:
            try:
                f.close()
            except OSError:
                pass
        raise
    finally:
        if tmp and os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                # Leaving a stray .tmp-* sibling is undesirable but not
                # catastrophic; cleanup pass at next save will pick it up.
                pass


def atomic_write_bytes(path: str, data: bytes, *, preflight: bool = True) -> None:
    """Convenience wrapper for the simple "write these bytes" case."""
    with atomic_writer(path, preflight=preflight) as f:
        f.write(data)


# ──────────────────────────────────────────────────────────────────────
# Cleanup of stray temp siblings (e.g. left behind by a crash)
# ──────────────────────────────────────────────────────────────────────

def cleanup_stray_tmps(path: str, *, max_age_seconds: int = 24 * 3600) -> int:
    """Remove ``.<basename>.tmp-*`` siblings of ``path`` older than the
    given age. Returns how many were removed.

    Called opportunistically before a save to keep the project
    directory tidy; never raises.
    """
    import time

    parent = os.path.dirname(os.path.abspath(path)) or "."
    base = os.path.basename(path)
    prefix = f".{base}."
    if not os.path.isdir(parent):
        return 0

    removed = 0
    now = time.time()
    try:
        entries = os.listdir(parent)
    except OSError:
        return 0
    for name in entries:
        if not name.startswith(prefix) or ".tmp-" not in name:
            continue
        full = os.path.join(parent, name)
        try:
            if now - os.path.getmtime(full) < max_age_seconds:
                continue
            os.unlink(full)
            removed += 1
        except OSError:
            continue
    return removed
