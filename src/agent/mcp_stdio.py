"""Zero-dependency MCP-over-stdio adapter for ImageLayoutManager.

Replaces the ``mcp`` pip package with a hand-rolled JSON-RPC 2.0 handler
so the frozen exe can serve as its own MCP server — no external Python
runtime required.

Usage (source)::

    python main.py --mcp

Usage (frozen exe)::

    ImageLayoutManager.exe --mcp

The adapter reads JSON-RPC from stdin, writes responses to stdout, and
proxies tool calls to the running ILM app over WebSocket (reading
port + token from the local discovery file).
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


# ── make ``src`` importable when running from repo root ───────────────

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


# ── imports that are available in the frozen exe ──────────────────────

import websockets  # noqa: E402  — bundled by PyInstaller

from src.agent.tool_specs import CONCEPTS_PRIMER_MD, TOOL_SPECS  # noqa: E402


# ── constants ─────────────────────────────────────────────────────────

SERVER_NAME = "imagelayout-manager"
SERVER_VERSION = "0.3.0"
PROTOCOL_VERSION = "2024-11-05"

_CONCEPTS_URI = "ilm://concepts"

# Snapshot the real stdout binary stream at import time. ``run_stdio``
# re-binds ``sys.stdout`` to ``sys.stderr`` to trap stray ``print(...)``
# from imported modules; without this snapshot the JSON-RPC responses
# would be written to stderr and the MCP host (Claude/Windsurf/Cursor)
# would time out waiting for ``initialize``. Using ``sys.__stdout__``
# would also work, but a local snapshot survives further reassignment
# and is None-safe in --windowed PyInstaller builds.
_STDOUT_BIN = sys.stdout.buffer if hasattr(sys.stdout, "buffer") else None


# ── ILM discovery + WS client ────────────────────────────────────────


def _discovery_path() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return Path(base) / "ImageLayoutManager" / "agent.json"


def _load_discovery() -> Dict[str, Any]:
    p = _discovery_path()
    if not p.exists():
        raise RuntimeError(
            "ILM is not running with MCP Server enabled. "
            "Open ImageLayoutManager → Tools → Enable MCP Server, "
            f"then retry.\nExpected discovery file at: {p}"
        )
    return json.loads(p.read_text(encoding="utf-8"))


class _ILMClient:
    """Persistent WebSocket connection to the running ILM app."""

    def __init__(self) -> None:
        self._ws: Optional[Any] = None
        self._next_id = 0
        self._lock = asyncio.Lock()

    async def _ensure_connected(self) -> None:
        if self._ws is not None:
            return
        disc = _load_discovery()
        url = f"ws://127.0.0.1:{disc['port']}"
        ws = await websockets.connect(url, max_size=64 * 1024 * 1024)
        await ws.send(json.dumps({"type": "auth", "token": disc["token"]}))
        ack = json.loads(await ws.recv())
        if ack.get("type") != "auth_ok":
            await ws.close()
            raise RuntimeError(f"ILM authentication failed: {ack}")
        self._ws = ws

    async def call(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        async with self._lock:
            await self._ensure_connected()
            assert self._ws is not None
            self._next_id += 1
            req = {
                "jsonrpc": "2.0",
                "id": self._next_id,
                "method": method,
                "params": params,
            }
            try:
                await self._ws.send(json.dumps(req))
                raw = await self._ws.recv()
            except websockets.ConnectionClosed:
                self._ws = None
                raise RuntimeError(
                    "Lost connection to ILM. Re-enable "
                    "Tools → Enable MCP Server, then retry."
                )
            return json.loads(raw)

    async def close(self) -> None:
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None


# ── JSON-RPC helpers ──────────────────────────────────────────────────


def _write(obj: Any) -> None:
    """Write a JSON-RPC message to the *real* stdout (newline-delimited).

    Must use ``_STDOUT_BIN`` rather than ``sys.stdout.buffer`` — ``run_stdio``
    re-binds ``sys.stdout`` to ``sys.stderr`` for print-trap purposes, so the
    live ``sys.stdout`` no longer points to the pipe the MCP host is reading.
    """
    if _STDOUT_BIN is None:
        return
    data = json.dumps(obj, ensure_ascii=False)
    _STDOUT_BIN.write(data.encode("utf-8") + b"\n")
    _STDOUT_BIN.flush()


def _result(msg_id: Any, result: Any) -> None:
    _write({"jsonrpc": "2.0", "id": msg_id, "result": result})


def _error(msg_id: Any, code: int, message: str,
           data: Any = None) -> None:
    err: Dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    _write({"jsonrpc": "2.0", "id": msg_id, "error": err})


# ── MCP handlers ─────────────────────────────────────────────────────


def _handle_initialize(msg: Dict[str, Any]) -> None:
    _result(msg["id"], {
        "protocolVersion": PROTOCOL_VERSION,
        "capabilities": {
            "tools": {},
            "resources": {},
        },
        "serverInfo": {
            "name": SERVER_NAME,
            "version": SERVER_VERSION,
        },
    })


def _handle_tools_list(msg: Dict[str, Any]) -> None:
    tools: List[Dict[str, Any]] = []
    for spec in TOOL_SPECS:
        tools.append({
            "name": spec["name"],
            "description": spec["description"],
            "inputSchema": spec["input_schema"],
        })
    _result(msg["id"], {"tools": tools})


async def _handle_tools_call(msg: Dict[str, Any],
                             ilm: _ILMClient) -> None:
    params = msg.get("params", {})
    name = params.get("name", "")
    arguments = params.get("arguments") or {}

    try:
        resp = await ilm.call(name, arguments)
    except Exception as e:
        _result(msg["id"], {
            "content": [{"type": "text", "text": f"Transport error: {e}"}],
            "isError": True,
        })
        return

    # JSON-RPC error from ILM
    if "error" in resp and resp.get("result") is None:
        err = resp["error"]
        payload = {
            "error": err.get("message"),
            "details": err.get("data"),
        }
        _result(msg["id"], {
            "content": [{
                "type": "text",
                "text": json.dumps(payload, indent=2, ensure_ascii=False),
            }],
            "isError": True,
        })
        return

    result = resp.get("result", {})

    # view_screenshot → image content block
    if (
        name == "view_screenshot"
        and isinstance(result, dict)
        and result.get("encoding") == "base64"
        and result.get("format") == "png"
    ):
        _result(msg["id"], {
            "content": [
                {
                    "type": "image",
                    "data": result["data"],
                    "mimeType": "image/png",
                },
                {
                    "type": "text",
                    "text": (f"Screenshot rendered at {result.get('dpi')} DPI "
                             f"({result.get('bytes')} bytes)."),
                },
            ],
        })
        return

    _result(msg["id"], {
        "content": [{
            "type": "text",
            "text": json.dumps(result, indent=2, ensure_ascii=False,
                               default=str),
        }],
    })


def _handle_resources_list(msg: Dict[str, Any]) -> None:
    _result(msg["id"], {
        "resources": [{
            "uri": _CONCEPTS_URI,
            "name": "ImageLayoutManager Concepts Primer",
            "description": (
                "Mental model + recipes for driving ILM. Covers rows, "
                "cells, splits, grid vs freeform, labels, and worked "
                "examples for common figure shapes. Read once before "
                "issuing tool calls."
            ),
            "mimeType": "text/markdown",
        }],
    })


def _handle_resources_read(msg: Dict[str, Any]) -> None:
    params = msg.get("params", {})
    uri = params.get("uri", "")
    if str(uri) == _CONCEPTS_URI:
        _result(msg["id"], {
            "contents": [{
                "uri": _CONCEPTS_URI,
                "mimeType": "text/markdown",
                "text": CONCEPTS_PRIMER_MD,
            }],
        })
    else:
        _error(msg["id"], -32602, f"Unknown resource: {uri}")


def _handle_ping(msg: Dict[str, Any]) -> None:
    _result(msg["id"], {})


# ── main loop ─────────────────────────────────────────────────────────

_HANDLERS = {
    "initialize":                _handle_initialize,
    "tools/list":                _handle_tools_list,
    "resources/list":            _handle_resources_list,
    "resources/read":            _handle_resources_read,
    "ping":                      _handle_ping,
}

# Notifications (no "id") — acknowledge silently
_NOTIFICATIONS = {
    "notifications/initialized",
    "notifications/cancelled",
}

# Async handlers that need the ILM client
_ASYNC_HANDLERS = {
    "tools/call": _handle_tools_call,
}


async def run_stdio() -> None:
    """Read MCP JSON-RPC from stdin, dispatch, write to stdout."""
    # Redirect any stray print() / warnings to stderr so they don't
    # corrupt the JSON-RPC stream on stdout.
    if not getattr(sys.stdout, "_mcp_redirected", False):
        sys.stderr = open(os.devnull, "w") if sys.stderr is None else sys.stderr
        sys.stdout = sys.stderr
        sys.stdout._mcp_redirected = True  # type: ignore[attr-defined]

    ilm = _ILMClient()
    loop = asyncio.get_event_loop()

    # Use run_in_executor for cross-platform stdin reading (Windows
    # asyncio doesn't support connect_read_pipe on stdin).
    def _readline() -> bytes:
        return sys.__stdin__.buffer.readline()

    try:
        while True:
            line = await loop.run_in_executor(None, _readline)
            if not line:
                break

            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue

            method = msg.get("method", "")
            msg_id = msg.get("id")

            # Notification — no response expected
            if msg_id is None:
                if method not in _NOTIFICATIONS:
                    # Unknown notification — log to stderr, don't crash
                    print(f"Unknown notification: {method}",
                          file=sys.__stderr__)
                continue

            # Sync handlers
            if method in _HANDLERS:
                try:
                    _HANDLERS[method](msg)
                except Exception as e:
                    _error(msg_id, -32603, str(e))
                continue

            # Async handlers (need await)
            if method in _ASYNC_HANDLERS:
                try:
                    await _ASYNC_HANDLERS[method](msg, ilm)
                except Exception as e:
                    _error(msg_id, -32603, str(e))
                continue

            # Unknown method
            _error(msg_id, -32601, f"Method not found: {method}")

    finally:
        await ilm.close()
