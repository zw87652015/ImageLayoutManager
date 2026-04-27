"""
Presence-file locking — the same model used by Microsoft Office (~$filename).

On open  : write a small file next to the document containing
           username | hostname | pid.
On close : delete the file.
On open when file exists : check if the recorded PID is still alive on the
           same host.  If yes → locked by another instance.
           If no  → stale lock from a previous crash; silently take over.
"""

from __future__ import annotations

import os
import socket
import getpass


SEPARATOR = "|"


class PresenceLockError(Exception):
    """Raised when a file is already open by another live instance."""
    def __init__(self, message: str, owner: str):
        super().__init__(message)
        self.owner = owner   # human-readable "User on Host (pid N)"


class PresenceLock:
    """Presence-file lock for a single document path.

    Usage::

        lock = PresenceLock(doc_path)
        lock.acquire()          # raises PresenceLockError if already open
        ...
        lock.release()          # deletes the presence file
    """

    def __init__(self, doc_path: str):
        self._doc_path = os.path.abspath(doc_path)
        self._lock_path = _lock_path_for(doc_path)
        self._held = False

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def acquire(self) -> None:
        existing = _read(self._lock_path)
        if existing is not None:
            user, host, pid_str = existing
            if _is_alive(host, pid_str):
                owner = f"{user} on {host} (pid {pid_str})"
                raise PresenceLockError(
                    f"lock already held by {owner}", owner=owner
                )
            # Stale lock from a crash — silently take over.

        _write(self._lock_path)
        self._held = True

    def release(self) -> None:
        if not self._held:
            return
        self._held = False
        try:
            os.remove(self._lock_path)
        except OSError:
            pass

    @property
    def held(self) -> bool:
        return self._held

    # context-manager support
    def __enter__(self) -> "PresenceLock":
        self.acquire()
        return self

    def __exit__(self, *_) -> None:
        self.release()


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _lock_path_for(doc_path: str) -> str:
    d, f = os.path.split(os.path.abspath(doc_path))
    return os.path.join(d, f"~${f}")


def _write(lock_path: str) -> None:
    user = getpass.getuser()
    host = socket.gethostname()
    pid  = str(os.getpid())
    content = SEPARATOR.join([user, host, pid])
    with open(lock_path, "w", encoding="utf-8") as fh:
        fh.write(content)


def _read(lock_path: str) -> tuple[str, str, str] | None:
    """Return (user, host, pid_str) or None if the file doesn't exist / is corrupt."""
    try:
        with open(lock_path, "r", encoding="utf-8") as fh:
            parts = fh.read().strip().split(SEPARATOR)
        if len(parts) == 3:
            return parts[0], parts[1], parts[2]
    except OSError:
        pass
    return None


def _is_alive(host: str, pid_str: str) -> bool:
    """Return True if the process is still running on this machine."""
    if host != socket.gethostname():
        # Different machine — we can't check; conservatively treat as alive.
        return True
    try:
        pid = int(pid_str)
    except ValueError:
        return False
    try:
        # os.kill(pid, 0) raises OSError if the process doesn't exist.
        os.kill(pid, 0)
        return True
    except OSError:
        return False
