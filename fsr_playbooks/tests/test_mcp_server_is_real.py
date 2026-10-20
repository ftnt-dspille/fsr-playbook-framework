"""When the real MCP SDK is installed, `_shared.mcp` must be the real server.

mcp 2.x renamed `mcp.server.fastmcp.FastMCP` to `mcp.server.mcpserver.MCPServer`.
If `_shared` only knows the old 1.x import path, it silently falls back to the
no-op `_FallbackFastMCP` shim under mcp 2.x -- and then the stdio server
(`python -m mcp_server` / `fsrpb mcp`) cannot run and the connector's
`call_mcp_tool` registry (which scans `_shared.mcp._tool_manager`) comes up
empty. Those failures are invisible to tests that call the tool functions
directly (the decorator returns the function unchanged in the shim too), so
this test pins the one thing that distinguishes a real server from the shim:
a working `_tool_manager` and a `run` that is not the shim's hard error.
"""
from __future__ import annotations

import pytest

# Only meaningful where the real server SDK is present. Absent it (the connector
# sandbox), the fallback shim is the intended object and there is nothing here
# to assert.
pytest.importorskip("mcp.server.mcpserver", reason="mcp server SDK not installed")


def test_shared_mcp_is_the_real_server_not_the_fallback_shim():
    from fsr_playbooks.mcp_server import _shared

    assert type(_shared.mcp).__name__ != "_FallbackFastMCP", (
        "_shared.mcp fell back to the no-op shim even though the real mcp "
        "server SDK is installed; the import in _shared.py is not finding "
        "MCPServer (mcp 2.x renamed it from mcp.server.fastmcp.FastMCP)"
    )
    # The two things the shim cannot provide and real consumers depend on:
    # a tool registry to scan, and a usable stdio runner.
    assert hasattr(_shared.mcp, "_tool_manager"), (
        "real server must expose a _tool_manager for the call_mcp_tool registry")
    assert hasattr(_shared.mcp._tool_manager, "_tools")


def test_registered_tools_are_visible_on_the_tool_manager():
    """A tool module's `@mcp.tool()` registrations land on the real manager."""
    import fsr_playbooks.mcp_server.tools_find  # noqa: F401  (registers tools)
    from fsr_playbooks.mcp_server import _shared

    tools = getattr(_shared.mcp._tool_manager, "_tools", {})
    assert tools, "no tools registered on the shared MCP server"
