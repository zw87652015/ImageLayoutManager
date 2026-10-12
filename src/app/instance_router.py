"""Route file-open launches to an already-running window.

Every running MainWindow owns a small QLocalServer plus a registry file in
``AppLocalDataLocation/instances`` named ``<pid>.instance``; the file's
content is its server name and its mtime is the window's last-focus time.
A second launch (Explorer double-click → ``exe "<path>"``) forwards its
file argument to the most recently focused live instance, then exits.
"""

import ctypes
import json
import os
import re
import sys
import time

from PyQt6.QtCore import QObject, QTimer, pyqtSignal, QStandardPaths
from PyQt6.QtNetwork import QLocalServer, QLocalSocket

_MAX_MESSAGE = 64 * 1024


def default_registry_dir() -> str:
    base = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.AppLocalDataLocation)
    d = os.path.join(base, "instances")
    os.makedirs(d, exist_ok=True)
    return d


def _sanitized_username() -> str:
    try:
        user = os.getlogin()
    except OSError:
        user = os.environ.get("USERNAME") or os.environ.get("USER") or "user"
    return re.sub(r"[^A-Za-z0-9_-]", "", user) or "user"


def ordered_instances(registry_dir, exclude_pid=None):
    """[(pid, server_name, path)] newest last-focus mtime first.

    Files that are unreadable, empty, badly named, or belong to
    *exclude_pid* are skipped.
    """
    entries = []
    try:
        names = os.listdir(registry_dir)
    except OSError:
        return entries
    for fn in names:
        if not fn.endswith(".instance"):
            continue
        try:
            pid = int(fn[:-len(".instance")])
        except ValueError:
            continue
        if exclude_pid is not None and pid == exclude_pid:
            continue
        path = os.path.join(registry_dir, fn)
        try:
            with open(path, "r", encoding="utf-8") as f:
                server_name = f.read().strip()
            mtime = os.stat(path).st_mtime
        except OSError:
            continue
        if not server_name:
            continue
        entries.append((mtime, pid, server_name, path))
    entries.sort(reverse=True)
    return [(pid, name, path) for _mtime, pid, name, path in entries]


class InstanceServer(QObject):
    """Per-window QLocalServer that accepts {"open": path} requests."""

    open_requested = pyqtSignal(str)

    def __init__(self, parent=None, pid=None, name=None):
        super().__init__(parent)
        self._pid = os.getpid() if pid is None else pid
        self._name = name or f"ILM-{_sanitized_username()}-{self._pid}"
        self._registry_path = None
        self._buffers = {}
        self._server = QLocalServer(self)
        self._server.newConnection.connect(self._on_connection)

    @property
    def server_name(self) -> str:
        return self._name

    def start(self, registry_dir=None) -> bool:
        registry_dir = registry_dir or default_registry_dir()
        os.makedirs(registry_dir, exist_ok=True)
        # removeServer cleans up a stale endpoint left by a crashed process.
        QLocalServer.removeServer(self._name)
        if not self._server.listen(self._name):
            return False
        self._registry_path = os.path.join(
            registry_dir, f"{self._pid}.instance")
        try:
            with open(self._registry_path, "w", encoding="utf-8") as f:
                f.write(self._name)
        except OSError:
            pass
        self.touch()
        return True

    def touch(self):
        """Stamp the registry file as focused right now."""
        if not self._registry_path:
            return
        try:
            now = time.time()
            os.utime(self._registry_path, (now, now))
        except OSError:
            pass

    def shutdown(self):
        self._server.close()
        if self._registry_path:
            try:
                os.remove(self._registry_path)
            except OSError:
                pass
            self._registry_path = None

    # -- connections -----------------------------------------------------

    def _on_connection(self):
        while self._server.hasPendingConnections():
            sock = self._server.nextPendingConnection()
            self._buffers[sock] = b""
            sock.readyRead.connect(lambda s=sock: self._on_ready_read(s))
            sock.disconnected.connect(
                lambda s=sock: self._buffers.pop(s, None))
            self._on_ready_read(sock)

    def _on_ready_read(self, sock):
        buf = self._buffers.get(sock, b"") + bytes(sock.readAll())
        if b"\n" not in buf:
            if len(buf) > _MAX_MESSAGE:
                self._reply(sock, b"error\n")
            else:
                self._buffers[sock] = buf
            return
        line, _, _rest = buf.partition(b"\n")
        path = None
        try:
            msg = json.loads(line.decode("utf-8", "replace"))
            if isinstance(msg, dict) and isinstance(msg.get("open"), str):
                path = msg["open"]
        except ValueError:
            pass
        if path is not None:
            self._reply(sock, b"ok\n")
            # Defer the emit so the ack above is never blocked behind a
            # dialog the file open may show.
            QTimer.singleShot(
                0, lambda p=path: self.open_requested.emit(p))
        else:
            self._reply(sock, b"error\n")

    def _reply(self, sock, payload: bytes):
        try:
            sock.write(payload)
            sock.flush()
        except Exception:
            pass
        self._buffers.pop(sock, None)
        sock.disconnectFromServer()
        sock.deleteLater()


def forward_to_running_instance(path, registry_dir=None,
                                timeout_ms=3000) -> bool:
    """Offer *path* to each live instance, most recently focused first.

    Returns True when one acknowledged the request. Stale registry files
    (connection refused) are deleted; a live-but-unresponsive instance's
    file is kept.
    """
    registry_dir = registry_dir or default_registry_dir()
    target = os.path.normpath(os.path.abspath(path))
    payload = (json.dumps({"open": target}) + "\n").encode("utf-8")
    for pid, name, reg_path in ordered_instances(
            registry_dir, exclude_pid=os.getpid()):
        if sys.platform == "win32":
            # This process was launched by Explorer and holds foreground
            # rights; grant them so the target window can raise itself.
            try:
                ctypes.windll.user32.AllowSetForegroundWindow(pid)
            except Exception:
                pass
        sock = QLocalSocket()
        sock.connectToServer(name)
        if not sock.waitForConnected(timeout_ms):
            try:
                os.remove(reg_path)
            except OSError:
                pass
            continue
        sock.write(payload)
        if not sock.waitForBytesWritten(timeout_ms):
            continue
        if not sock.waitForReadyRead(timeout_ms):
            continue
        if bytes(sock.readLine()).strip() == b"ok":
            return True
    return False
