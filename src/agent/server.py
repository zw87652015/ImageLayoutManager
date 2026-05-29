"""WebSocket JSON-RPC server for the agent integration (GUI transport).

Architecture
------------
* :class:`AgentServerController` lives on the GUI thread. It owns a
  :class:`AgentServerThread` (subclass of ``QThread``) which runs an
  asyncio event loop and the ``websockets`` server.
* When a JSON-RPC request arrives, the asyncio handler creates a
  :class:`concurrent.futures.Future` and asks the controller (via
  ``QMetaObject.invokeMethod``) to run the tool on the GUI thread. The
  asyncio side awaits the future via :func:`asyncio.wrap_future`.
* This funnels every model mutation through the GUI thread, so the
  existing single-threaded ``QUndoStack`` + ``Project`` invariants hold.

Protocol
--------
1. Client connects to ``ws://127.0.0.1:<port>``.
2. Client sends first frame ``{"type": "auth", "token": "..."}`` within
   five seconds.
3. Server replies ``{"type": "auth_ok"}`` and accepts subsequent
   JSON-RPC 2.0 messages on the same socket. Bad token → ``auth_failed``
   then disconnect.

Discovery
---------
On start the controller writes ``%APPDATA%/ImageLayoutManager/agent.json``
(or ``~/.config/ImageLayoutManager/agent.json`` on Unix) containing the
chosen port and the freshly-minted token. Removed on stop.
"""
from __future__ import annotations

import asyncio
import json
import os
import secrets
import socket
import sys
from concurrent.futures import Future
from typing import Any, Dict, Optional

from PyQt6.QtCore import (
    QObject, QThread, QMetaObject, Qt, Q_ARG, pyqtSignal, pyqtSlot,
)


# ── discovery file ──────────────────────────────────────────────────────


def _discovery_dir() -> str:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    d = os.path.join(base, "ImageLayoutManager")
    os.makedirs(d, exist_ok=True)
    return d


def _discovery_path() -> str:
    return os.path.join(_discovery_dir(), "agent.json")


# ── async worker thread ────────────────────────────────────────────────


class AgentServerThread(QThread):
    """Runs the asyncio + ``websockets`` server on a background thread."""

    started_ok = pyqtSignal(int)   # port
    failed     = pyqtSignal(str)   # error message

    def __init__(self, controller: "AgentServerController",
                 port: int, token: str, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._controller = controller
        self._port = port
        self._token = token
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._stop_event: Optional[asyncio.Event] = None

    def run(self) -> None:                                # noqa: D401
        try:
            import websockets                              # noqa: WPS433
        except ImportError:
            self.failed.emit(
                "The 'websockets' Python package is not installed.\n"
                "Run:  pip install websockets"
            )
            return

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        self._stop_event = asyncio.Event()

        async def handler(websocket):  # noqa: ANN001 — websockets signature
            try:
                first = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                msg = json.loads(first)
                if msg.get("type") != "auth" or msg.get("token") != self._token:
                    await websocket.send(json.dumps({"type": "auth_failed"}))
                    return
                await websocket.send(json.dumps({"type": "auth_ok"}))
            except Exception:                              # noqa: BLE001
                return

            # The async-for itself raises ConnectionClosed* when the peer
            # disconnects without a close frame (normal when an MCP adapter
            # subprocess exits or is restarted). Swallow that path so it
            # doesn't surface as a connection-handler crash.
            try:
                async for raw in websocket:
                    req: Dict[str, Any] = {}
                    try:
                        req = json.loads(raw)
                        method = req.get("method")
                        params = req.get("params") or {}
                        req_id = req.get("id")

                        fut: Future = Future()
                        self._controller._submit_tool_call(method, params, fut)
                        result = await asyncio.wrap_future(fut)

                        if result.get("ok"):
                            resp = {"jsonrpc": "2.0", "id": req_id,
                                    "result": result["result"]}
                        else:
                            data = {k: v for k, v in result.items()
                                    if k not in ("ok", "error", "detail")}
                            resp = {
                                "jsonrpc": "2.0", "id": req_id,
                                "error": {
                                    "code": -32000,
                                    "message": result.get("error", "unknown"),
                                    "data": {
                                        "detail": result.get("detail"),
                                        **data,
                                    },
                                },
                            }
                        await websocket.send(json.dumps(resp))
                    except websockets.exceptions.ConnectionClosed:
                        # Peer dropped mid-request; nothing left to reply to.
                        break
                    except Exception as e:                     # noqa: BLE001
                        err = {
                            "jsonrpc": "2.0",
                            "id": req.get("id") if isinstance(req, dict) else None,
                            "error": {"code": -32603, "message": str(e)},
                        }
                        try:
                            await websocket.send(json.dumps(err))
                        except Exception:
                            break
            except websockets.exceptions.ConnectionClosed:
                # Normal disconnect — adapter subprocess exited / restarted.
                return

        async def main_async():
            server = await websockets.serve(handler, "127.0.0.1", self._port)
            self.started_ok.emit(self._port)
            await self._stop_event.wait()
            server.close()
            await server.wait_closed()

        try:
            loop.run_until_complete(main_async())
        except Exception as e:                             # noqa: BLE001
            self.failed.emit(str(e))
        finally:
            try:
                loop.close()
            except Exception:
                pass

    def stop_async(self) -> None:
        """Trigger shutdown from any thread."""
        if self._loop is not None and self._stop_event is not None:
            self._loop.call_soon_threadsafe(self._stop_event.set)


# ── controller (GUI thread) ────────────────────────────────────────────


class AgentServerController(QObject):
    """Owns the server thread and routes tool calls to the GUI thread."""

    status_changed = pyqtSignal(bool, str)  # (running, info_or_error)

    def __init__(self, main_window) -> None:               # noqa: ANN001
        super().__init__(main_window)
        self._main_window = main_window
        self._thread: Optional[AgentServerThread] = None
        self._port: Optional[int] = None
        self._token: Optional[str] = None

    # ── public API ──

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.isRunning()

    @property
    def port(self) -> Optional[int]:
        return self._port

    @property
    def token(self) -> Optional[str]:
        return self._token

    def start(self) -> tuple[int, str]:
        """Start the server. Returns ``(port, token)``."""
        if self.is_running():
            assert self._port is not None and self._token is not None
            return self._port, self._token

        port = _pick_free_port()
        token = secrets.token_urlsafe(32)
        thread = AgentServerThread(self, port, token, parent=self)
        thread.started_ok.connect(lambda p: self._on_started(p))
        thread.failed.connect(self._on_failed)
        self._thread = thread
        self._port = port
        self._token = token
        _write_discovery(port, token)
        thread.start()
        return port, token

    def stop(self) -> None:
        if self._thread is not None:
            self._thread.stop_async()
            self._thread.wait(3000)
            self._thread = None
        self._port = None
        self._token = None
        _remove_discovery()
        self.status_changed.emit(False, "")

    # ── internals ──

    def _on_started(self, port: int) -> None:
        self.status_changed.emit(
            True, f"Listening on ws://127.0.0.1:{port}"
        )

    def _on_failed(self, msg: str) -> None:
        self._thread = None
        self._port = None
        self._token = None
        _remove_discovery()
        self.status_changed.emit(False, msg)

    def _submit_tool_call(self, method: str, params: Dict[str, Any],
                          future: Future) -> None:
        """Called from the WS thread. Schedules :meth:`_run_tool` on the GUI thread."""
        QMetaObject.invokeMethod(
            self,
            "_run_tool",
            Qt.ConnectionType.QueuedConnection,
            Q_ARG(str, method or ""),
            Q_ARG(object, params),
            Q_ARG(object, future),
        )

    @pyqtSlot(str, object, object)
    def _run_tool(self, method: str, params: Dict[str, Any],
                  future: Future) -> None:
        try:
            from src.agent import tools
            ctx = self._main_window.get_agent_tool_context()
            result = tools.dispatch(method, params, ctx)
        except Exception as e:                             # noqa: BLE001
            import traceback as _tb
            result = {
                "ok": False,
                "error": "internal_error",
                "detail": str(e),
                "traceback": _tb.format_exc(),
            }
        future.set_result(result)


# ── helpers ─────────────────────────────────────────────────────────────


def _pick_free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
    finally:
        s.close()


def _write_discovery(port: int, token: str) -> None:
    try:
        with open(_discovery_path(), "w", encoding="utf-8") as f:
            json.dump({"port": port, "token": token}, f)
    except OSError:
        pass


def _remove_discovery() -> None:
    try:
        os.remove(_discovery_path())
    except OSError:
        pass
