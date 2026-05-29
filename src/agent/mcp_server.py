"""MCP-over-stdio adapter for ImageLayoutManager.

What this is
------------
An MCP (Model Context Protocol) server, designed to be launched as a
subprocess by an MCP host — Claude Desktop, Claude Code, Cursor, Cline,
etc. The host speaks MCP-over-stdio with this process; this process
speaks the existing ImageLayoutManager JSON-RPC WebSocket protocol with
a running ILM app.

::

    ┌──────────────────────────────┐   stdio (MCP)    ┌────────────────┐
    │ Claude Code / Claude Desktop │ ───────────────► │  this adapter  │
    └──────────────────────────────┘                  └────────┬───────┘
                                                               │ WS (JSON-RPC, tokened)
                                                               ▼
                                                       ┌───────────────┐
                                                       │ running ILM   │
                                                       │ (GUI session) │
                                                       └───────────────┘

Why this shape
--------------
ILM is a long-running desktop GUI. MCP hosts launch servers on demand
and tear them down between sessions. The lifecycles don't match. This
adapter is the thin translator that bridges them: short-lived MCP
process, long-lived ILM process, one WebSocket between them.

The adapter is also where the LLM-facing **tool descriptions** and the
**ilm://concepts** resource live (see ``src.agent.tool_specs`` and
``docs/agent_concepts.md``). Keeping them out of the ILM process means
swapping out prompt-engineering choices doesn't require restarting the
GUI.

Host configuration
------------------
Add to your host's MCP servers config:

* **Claude Code**::

      claude mcp add imagelayout -- \\
          "C:/Program Files/ImageLayoutManager/imagelayout-cli.exe" "mcp"

* **Claude Desktop** (``claude_desktop_config.json``)::

      {
        "mcpServers": {
          "imagelayout": {
            "command": "C:/Program Files/ImageLayoutManager/imagelayout-cli.exe",
            "args": ["mcp"]
          }
        }
      }

Installed builds use ``imagelayout-cli.exe mcp`` and do not require external
Python packages. Directly running this legacy source adapter still requires
``pip install mcp websockets``.

…and a running ILM with **Tools → Enable MCP Server** turned on.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


# ── make ``src`` importable when this file is launched directly ────────


_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


# ── deferred imports (so import errors surface as runtime messages) ────


def _import_mcp() -> Any:
    try:
        import mcp.server.stdio                              # noqa: F401
        import mcp.types as _types                           # noqa: F401
        from mcp.server import NotificationOptions, Server   # noqa: F401
        from mcp.server.models import InitializationOptions  # noqa: F401
        return None
    except ImportError as e:
        sys.stderr.write(
            "The 'mcp' Python package is not installed.\n"
            "Run:  pip install mcp websockets\n"
            f"(import error: {e})\n"
        )
        sys.exit(1)


_import_mcp()


import mcp.types as types                                    # noqa: E402
from mcp.server import NotificationOptions, Server           # noqa: E402
from mcp.server.models import InitializationOptions          # noqa: E402
from mcp.server.stdio import stdio_server                    # noqa: E402

import websockets                                            # noqa: E402

from src.agent.tool_specs import CONCEPTS_PRIMER_MD, TOOL_SPECS  # noqa: E402


# ── ILM discovery ──────────────────────────────────────────────────────


def _discovery_path() -> Path:
    """Mirror of ``src.agent.server._discovery_path`` for the adapter side."""
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
            "ILM MCP server is not running. Open ImageLayoutManager, "
            "click  Tools → Enable MCP Server  (or launch with "
            "--agent-server), then retry.\n"
            f"Expected discovery file at: {p}"
        )
    return json.loads(p.read_text(encoding="utf-8"))


# ── persistent WS client ───────────────────────────────────────────────


class _ILMClient:
    """One WebSocket connection to ILM, kept open for the adapter's life."""

    def __init__(self) -> None:
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
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
        """Send one JSON-RPC request and wait for its response.

        Serialised under a lock — the WS connection is a single duplex
        stream and concurrent ``tools/call``s would otherwise interleave.
        """
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
                # The GUI was closed / agent server toggled off. Drop the
                # cached socket so the next call re-discovers and reconnects.
                self._ws = None
                raise RuntimeError(
                    "Lost connection to ILM. Re-enable Tools → Enable "
                    "Agent Server, then retry."
                )
            return json.loads(raw)

    async def close(self) -> None:
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None


_ilm = _ILMClient()


# ── MCP server wiring ──────────────────────────────────────────────────


server = Server("imagelayout-manager")


@server.list_tools()
async def _list_tools() -> List[types.Tool]:
    return [
        types.Tool(
            name=spec["name"],
            description=spec["description"],
            inputSchema=spec["input_schema"],
        )
        for spec in TOOL_SPECS
    ]


@server.call_tool()
async def _call_tool(
    name: str, arguments: Optional[Dict[str, Any]]
) -> List[types.TextContent | types.ImageContent]:
    args = arguments or {}
    try:
        resp = await _ilm.call(name, args)
    except Exception as e:
        return [types.TextContent(type="text", text=f"Transport error: {e}")]

    # JSON-RPC error envelope from ILM.
    if "error" in resp and resp.get("result") is None:
        err = resp["error"]
        payload = {
            "error":   err.get("message"),
            "details": err.get("data"),
        }
        return [types.TextContent(
            type="text",
            text=json.dumps(payload, indent=2, ensure_ascii=False),
        )]

    result = resp.get("result", {})

    # Special-case view_screenshot: hoist the base64 PNG into an MCP
    # ImageContent block so multimodal LLMs can actually *see* the
    # canvas rather than receive a wall of base64 text.
    if (
        name == "view_screenshot"
        and isinstance(result, dict)
        and result.get("encoding") == "base64"
        and result.get("format") == "png"
    ):
        return [
            types.ImageContent(
                type="image",
                data=result["data"],
                mimeType="image/png",
            ),
            types.TextContent(
                type="text",
                text=(f"Screenshot rendered at {result.get('dpi')} DPI "
                      f"({result.get('bytes')} bytes)."),
            ),
        ]

    return [types.TextContent(
        type="text",
        text=json.dumps(result, indent=2, ensure_ascii=False, default=str),
    )]


# ── concepts primer resource ───────────────────────────────────────────


_CONCEPTS_URI = "ilm://concepts"


@server.list_resources()
async def _list_resources() -> List[types.Resource]:
    return [types.Resource(
        uri=_CONCEPTS_URI,
        name="ImageLayoutManager Concepts Primer",
        description=(
            "Mental model + recipes for driving ILM. Covers rows, cells, "
            "splits, grid vs freeform, labels, and worked examples for "
            "common figure shapes. Read once before issuing tool calls."
        ),
        mimeType="text/markdown",
    )]


@server.read_resource()
async def _read_resource(uri: str) -> str:
    if str(uri) == _CONCEPTS_URI:
        return CONCEPTS_PRIMER_MD
    raise ValueError(f"Unknown resource: {uri}")


# ── entry point ────────────────────────────────────────────────────────


async def _main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="imagelayout-manager",
                server_version="0.2.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        pass
