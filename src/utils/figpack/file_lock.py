"""
Cross-platform exclusive file lock (Windows + macOS + Linux).

Used by the working-directory lifecycle (plan.md §3.2.3, §6.4) so the
cache-cleanup pass can safely tell "owned by another instance" from
"orphaned by a crash" *without* trusting PIDs (PID reuse on Windows
is fast) and *without* trusting mtimes (long-running sessions get
hostile to mtime-based heuristics).

Semantics:

* :class:`ExclusiveLock` is a context manager.
* On ``__enter__`` we open ``<path>`` (creating it if needed) and
  acquire an OS-level exclusive lock. If the lock is already held by
  another process, ``acquire`` raises :class:`LockHeldError`.
* On ``__exit__`` (and on process exit / crash) the OS releases the
  lock automatically, even if our process is killed with SIGKILL /
  ``TerminateProcess`` — that's the whole reason we use kernel locks
  rather than a pidfile.
* :func:`is_locked(path)` is the read-only "is anyone holding this?"
  query used by the cache cleanup pass: it briefly tries to acquire
  the lock; if it can, the dir is orphaned.

  IMPORTANT — Windows quirk: ``msvcrt.locking`` is *per-fd*, not
  per-process. A second ``open()`` of the same file from the **same**
  process can acquire its own independent lock, so calling
  :func:`is_locked` from inside the lock-holding process is *not*
  reliable. This is fine for the cache-cleanup use case because
  cleanup always runs in a freshly-launched ImageLayoutManager
  instance (i.e. a different process from any tab that owns a working
  dir). For in-process double-acquire prevention, :class:`ExclusiveLock`
  guards itself via the ``self._fd`` check.

Implementation notes:

* Windows: :func:`msvcrt.locking` with ``LK_NBLCK`` (non-blocking
  exclusive). Locks the first byte of the file. Released when the fd
  is closed or the process dies.
* POSIX (macOS, Linux): :func:`fcntl.flock` with ``LOCK_EX | LOCK_NB``.
  Whole-file lock semantics; released on close or process death.
* We never use ``fcntl.lockf`` / ``F_SETLK`` (POSIX advisory record
  locks): they have the well-known foot-gun that closing *any* fd to
  the file releases *all* locks, which breaks cleanup correctness.
"""

from __future__ import annotations

import os
import sys
from typing import Optional


class LockHeldError(OSError):
    """Raised when an exclusive lock is already held by another process."""


# ──────────────────────────────────────────────────────────────────────
# Platform-specific primitives
# ──────────────────────────────────────────────────────────────────────

if sys.platform == "win32":  # pragma: no cover - platform branch
    import msvcrt

    def _try_lock(fd: int) -> bool:
        # msvcrt.locking locks `n` bytes starting at the *current* file
        # position. We must seek to byte 0 first; otherwise two processes
        # opening the file at different offsets would lock disjoint
        # ranges and never contend.
        try:
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False

    def _unlock(fd: int) -> None:
        try:
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        except OSError:
            # Closing the fd will release any remaining locks.
            pass

else:  # POSIX (macOS, Linux)
    import fcntl

    def _try_lock(fd: int) -> bool:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            return False

    def _unlock(fd: int) -> None:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            pass


# ──────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────

class ExclusiveLock:
    """Context-manager exclusive file lock.

    Typical use::

        with ExclusiveLock(workdir / ".lock"):
            ...   # we own this working directory

    On entry: opens (creating if needed) ``path``, writes a small marker
    so the file has at least 1 byte (Windows requires that), then takes
    the lock.

    On exit: releases the lock and closes the fd. The lock file itself
    is **not** unlinked — its presence (with no holder) is exactly the
    "orphaned working dir" signal that cleanup is looking for.
    """

    def __init__(self, path: str):
        self.path = os.fspath(path)
        self._fd: Optional[int] = None

    # context-manager interface ------------------------------------------------

    def __enter__(self) -> "ExclusiveLock":
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()

    # explicit interface -------------------------------------------------------

    def acquire(self) -> None:
        if self._fd is not None:
            raise RuntimeError("lock already acquired")

        # O_CREAT | O_RDWR so we can both create the file and write the
        # marker byte that Windows requires.
        flags = os.O_RDWR | os.O_CREAT
        # On POSIX we want the file to be private to the user; 0o600 is
        # standard for cache locks.
        fd = os.open(self.path, flags, 0o600)
        try:
            # Ensure at least 1 byte exists for Windows' byte-range lock.
            try:
                if os.fstat(fd).st_size == 0:
                    os.write(fd, b"\0")
            except OSError:
                pass

            if not _try_lock(fd):
                raise LockHeldError(f"lock already held: {self.path}")
        except BaseException:
            os.close(fd)
            raise

        self._fd = fd

    def release(self) -> None:
        fd = self._fd
        if fd is None:
            return
        self._fd = None
        try:
            _unlock(fd)
        finally:
            try:
                os.close(fd)
            except OSError:
                pass

    @property
    def held(self) -> bool:
        return self._fd is not None


def is_locked(path: str) -> bool:
    """Non-destructive probe: is anyone currently holding this lock?

    Briefly opens the file and tries to acquire it; if successful,
    immediately releases. Returns ``True`` if the file is currently
    held by another process, ``False`` otherwise (including the case
    where the file does not exist).

    This is the primitive the cache-cleanup pass uses to decide whether
    a working directory is orphaned.
    """
    if not os.path.exists(path):
        return False
    try:
        fd = os.open(path, os.O_RDWR)
    except OSError:
        # Permission error or transient issue → conservatively report
        # "locked" so cleanup leaves the dir alone.
        return True
    try:
        try:
            if os.fstat(fd).st_size == 0:
                os.write(fd, b"\0")
        except OSError:
            pass
        if _try_lock(fd):
            _unlock(fd)
            return False
        return True
    finally:
        try:
            os.close(fd)
        except OSError:
            pass
