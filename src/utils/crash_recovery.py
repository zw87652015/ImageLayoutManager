"""Crash safety net and autosave snapshot store.

Three responsibilities, deliberately kept in one Qt-light module:

1. **File logging** — :func:`setup_logging` installs a rotating file
   handler under the per-OS log directory so field failures leave a
   trace (frozen windowed builds have no visible stdout).
2. **Global exception hook** — :func:`install_excepthook` replaces
   ``sys.excepthook``. PyQt6 aborts the process via ``qFatal()`` when
   an unhandled exception escapes a slot *and* the default hook is in
   place; a custom hook prevents the abort, logs the traceback, rescues
   unsaved work via a caller-supplied callback, and shows the user a
   crash dialog instead of silently vanishing.
3. **Snapshot store** — :class:`SnapshotStore` persists per-tab project
   snapshots (plain JSON, absolute image paths) into a recovery
   directory. Snapshots are stamped with the writing PID; on the next
   launch, snapshots whose PID is dead are offered for restoration.

Nothing here imports QtWidgets at module level so the CLI can reuse the
logging half without a GUI installed.
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import os
import sys
import threading
import time
import traceback
from typing import Any, Callable, Dict, List, Optional, Tuple

LOGGER_NAME = "imagelayout"

_SNAPSHOT_SUFFIX = ".autosave.json"


# ──────────────────────────────────────────────────────────────────────
# Per-OS directories
# ──────────────────────────────────────────────────────────────────────

def _app_data_dir() -> str:
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
    return os.path.join(base, "ImageLayoutManager")


def log_dir() -> str:
    if sys.platform == "darwin":
        d = os.path.expanduser("~/Library/Logs/ImageLayoutManager")
    else:
        d = os.path.join(_app_data_dir(), "logs")
    os.makedirs(d, exist_ok=True)
    return d


def recovery_dir() -> str:
    d = os.path.join(_app_data_dir(), "recovery")
    os.makedirs(d, exist_ok=True)
    return d


# ──────────────────────────────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────────────────────────────

def setup_logging(level: int = logging.INFO) -> logging.Logger:
    """Install a rotating file handler; idempotent."""
    logger = logging.getLogger(LOGGER_NAME)
    if getattr(logger, "_ilm_configured", False):
        return logger
    logger.setLevel(level)
    try:
        handler = logging.handlers.RotatingFileHandler(
            os.path.join(log_dir(), "app.log"),
            maxBytes=1024 * 1024, backupCount=3, encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)-8s [%(threadName)s] %(message)s"
        ))
        logger.addHandler(handler)
    except OSError:
        # Read-only home / packaging edge case — degrade to stderr only.
        logger.addHandler(logging.StreamHandler())
    logger._ilm_configured = True  # type: ignore[attr-defined]
    return logger


def log_path() -> str:
    return os.path.join(log_dir(), "app.log")


# ──────────────────────────────────────────────────────────────────────
# Global exception hook
# ──────────────────────────────────────────────────────────────────────

_in_hook = False


def install_excepthook(
    rescue_callback: Optional[Callable[[], List[str]]] = None,
) -> None:
    """Replace ``sys.excepthook`` (and ``threading.excepthook``).

    *rescue_callback* is invoked on a GUI-thread crash and should write
    emergency snapshots of all unsaved work, returning the file paths
    it wrote. The hook never re-raises: replacing the default hook is
    precisely what stops PyQt6 from calling ``qFatal()``/abort, so the
    event loop keeps running after the dialog is dismissed.
    """
    logger = setup_logging()

    def _hook(exc_type, exc_value, exc_tb) -> None:
        global _in_hook
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        if _in_hook:
            # A crash inside the crash handler — last resort: stderr.
            traceback.print_exception(exc_type, exc_value, exc_tb)
            return
        _in_hook = True
        try:
            text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
            logger.critical("Unhandled exception:\n%s", text)

            rescued: List[str] = []
            if rescue_callback is not None:
                try:
                    rescued = rescue_callback() or []
                    if rescued:
                        logger.critical("Rescued %d unsaved project(s): %s",
                                        len(rescued), rescued)
                except Exception:
                    logger.exception("Rescue-save failed")

            _show_crash_dialog(exc_value, rescued)
        finally:
            _in_hook = False

    def _thread_hook(args) -> None:
        if issubclass(args.exc_type, SystemExit):
            return
        logger.critical(
            "Unhandled exception in thread %r:\n%s",
            args.thread.name if args.thread else "?",
            "".join(traceback.format_exception(
                args.exc_type, args.exc_value, args.exc_traceback)),
        )

    sys.excepthook = _hook
    threading.excepthook = _thread_hook


def _show_crash_dialog(exc_value: BaseException, rescued: List[str]) -> None:
    """Best-effort modal crash notice; silent no-op without a QApplication."""
    try:
        from PyQt6.QtWidgets import QApplication, QMessageBox
        if QApplication.instance() is None:
            return
        from src.app.i18n import tr
        detail = f"{type(exc_value).__name__}: {exc_value}"
        body = tr("msg_crash_body").format(error=detail, log=log_path())
        if rescued:
            body += "\n\n" + tr("msg_crash_rescued").format(count=len(rescued))
        box = QMessageBox(QMessageBox.Icon.Critical, tr("msg_crash_title"),
                          body)
        box.exec()
    except Exception:
        # Never let the crash dialog itself take the process down.
        pass


def remap_bundle_paths(project_data: Dict[str, Any], pack_path: str,
                       new_workdir: str) -> None:
    """Repoint dead figpack-cache asset paths in *project_data* (in place).

    Snapshots taken from a .figpack tab reference images inside the
    session's extraction workdir (``<cache_root>/<key>__<random>/…``).
    After a crash that workdir is reaped by the startup orphan sweep, so
    the paths dangle. Re-opening the bundle re-creates the identical
    *relative* asset layout in a fresh workdir; this walks every cell /
    sub-cell / PiP image path and, for paths that no longer exist but
    contain the bundle's ``<key>__`` cache component, substitutes the
    new workdir prefix — but only when the remapped file actually
    exists. Paths that are alive (e.g. user-imported originals) are
    left untouched.
    """
    import re
    from src.utils.figpack.cache_manager import _archive_key
    marker = _archive_key(pack_path) + "__"

    def fix(path: Optional[str]) -> Optional[str]:
        if not path or os.path.isfile(path):
            return path
        parts = [p for p in re.split(r"[\\/]+", path) if p]
        for i, comp in enumerate(parts):
            if comp.startswith(marker):
                candidate = os.path.join(new_workdir, *parts[i + 1:])
                if os.path.isfile(candidate):
                    return candidate
                break
        return path

    def walk_cell(c: Dict[str, Any]) -> None:
        if c.get("image_path"):
            c["image_path"] = fix(c["image_path"])
        for pip in c.get("pip_items") or []:
            if pip.get("image_path"):
                pip["image_path"] = fix(pip["image_path"])
        for child in c.get("children") or []:
            walk_cell(child)

    for cell in project_data.get("cells") or []:
        walk_cell(cell)


# ──────────────────────────────────────────────────────────────────────
# Snapshot store
# ──────────────────────────────────────────────────────────────────────

def pid_alive(pid: int) -> bool:
    """True if *pid* is a running process on this machine.

    On Windows ``os.kill(pid, 0)`` is NOT a liveness probe — it sends
    CTRL_C_EVENT to the target's console process group (interrupting
    it, or ourselves when the pid shares our console). Use
    OpenProcess/GetExitCodeProcess instead.
    """
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        ERROR_ACCESS_DENIED = 5
        handle = kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            # Access denied means the process exists but is protected.
            return ctypes.get_last_error() == ERROR_ACCESS_DENIED
        try:
            code = ctypes.c_ulong()
            if kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return code.value == STILL_ACTIVE
            return True  # unknown — be conservative
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, owned by someone else
    except OSError:
        return False


class SnapshotStore:
    """Per-tab autosave snapshots in :func:`recovery_dir`.

    One file per tab key: ``<key>.autosave.json`` containing::

        {"pid": ..., "saved_at": ..., "original_path": ..., "project": {...}}

    Image paths inside ``project`` are absolute (the model serialises
    them as-is), so a snapshot restores independently of its location.
    """

    def __init__(self, directory: Optional[str] = None):
        self._dir = directory or recovery_dir()
        self._logger = logging.getLogger(LOGGER_NAME)

    def _path_for(self, key: str) -> str:
        return os.path.join(self._dir, key + _SNAPSHOT_SUFFIX)

    def write(self, key: str, project_dict: Dict[str, Any],
              original_path: Optional[str]) -> Optional[str]:
        """Atomically write one snapshot; returns its path or None."""
        payload = {
            "pid": os.getpid(),
            "saved_at": time.time(),
            "original_path": original_path,
            "project": project_dict,
        }
        target = self._path_for(key)
        tmp = target + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f)
            os.replace(tmp, target)
            return target
        except OSError:
            self._logger.exception("Autosave snapshot write failed: %s", target)
            try:
                os.remove(tmp)
            except OSError:
                pass
            return None

    def remove(self, key: str) -> None:
        try:
            os.remove(self._path_for(key))
        except OSError:
            pass

    def pending(self) -> List[Tuple[str, Dict[str, Any]]]:
        """Snapshots left behind by dead processes: [(path, payload), …]."""
        out: List[Tuple[str, Dict[str, Any]]] = []
        try:
            names = os.listdir(self._dir)
        except OSError:
            return out
        for name in sorted(names):
            if not name.endswith(_SNAPSHOT_SUFFIX):
                continue
            path = os.path.join(self._dir, name)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    payload = json.load(f)
                pid = int(payload.get("pid", -1))
            except (OSError, ValueError, json.JSONDecodeError):
                # Corrupt snapshot — remove so it doesn't prompt forever.
                try:
                    os.remove(path)
                except OSError:
                    pass
                continue
            if pid > 0 and pid_alive(pid):
                continue  # another live instance owns it
            out.append((path, payload))
        return out

    @staticmethod
    def discard(path: str) -> None:
        try:
            os.remove(path)
        except OSError:
            pass
