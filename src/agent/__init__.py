"""ImageLayoutManager agent integration layer.

See docs/agent_integration.md for the full design. v0.1 ships:

* :mod:`src.agent.tools` — pure-Python tool functions, one source of
  truth for both transports.
* :mod:`src.agent.server` — JSON-RPC over WebSocket on localhost,
  Qt-thread-aware. Toggled via Tools → Enable MCP Server.
"""
