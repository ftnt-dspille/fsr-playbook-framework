"""The MCP server package imports without the MCP SDK; the SDK binds on first real use.

Importing `fsr_playbooks.mcp_server` used to load the MCP SDK (~0.5s) on every
connector cold start and test process, although only the stdio server needs
it. `_shared.mcp` is now a recording shim: `@mcp.tool()` stores the
registration (same args, same order, function returned unchanged) and the real
`MCPServer` is built and the registrations replayed onto it on first real use
(`.run()`, or any attribute such as `_tool_manager`).
"""
from __future__ import annotations

import ast
import pathlib
import subprocess
import sys

import pytest

PKG_DIR = pathlib.Path(__file__).resolve().parents[1] / "mcp_server"


def test_importing_the_mcp_server_package_does_not_load_the_mcp_sdk():
    code = (
        "import sys\n"
        "import fsr_playbooks.mcp_server  # noqa: F401\n"
        "loaded = sorted(m for m in sys.modules if m == 'mcp' or m.startswith('mcp.'))\n"
        "print(loaded)\n"
    )
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True,
                          text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "[]", (
        f"importing fsr_playbooks.mcp_server loaded the MCP SDK: {proc.stdout.strip()}")


def _decorated_tool_names_in_source() -> set[str]:
    """Every function the mcp_server package registers, found by scanning source.

    Covers `@mcp.tool()` / `@mcp.tool(...)` decorators and the call form
    `name = mcp.tool()(name)`.
    """
    names: set[str] = set()
    for path in PKG_DIR.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for dec in node.decorator_list:
                    target = dec.func if isinstance(dec, ast.Call) else dec
                    if (isinstance(target, ast.Attribute) and target.attr == "tool"
                            and isinstance(target.value, ast.Name)
                            and target.value.id == "mcp"):
                        names.add(node.name)
            if (isinstance(node, ast.Assign) and isinstance(node.value, ast.Call)
                    and isinstance(node.value.func, ast.Call)):
                inner = node.value.func.func
                if (isinstance(inner, ast.Attribute) and inner.attr == "tool"
                        and isinstance(inner.value, ast.Name) and inner.value.id == "mcp"
                        and len(node.value.args) == 1
                        and isinstance(node.value.args[0], ast.Name)):
                    names.add(node.value.args[0].id)
    return names


def test_bound_server_registers_exactly_the_decorated_tools():
    pytest.importorskip("mcp.server.mcpserver", reason="mcp server SDK not installed")
    import fsr_playbooks.mcp_server  # noqa: F401  (registers every tool module)
    from fsr_playbooks.mcp_server import _shared

    registered = set(getattr(_shared.mcp._tool_manager, "_tools", {}) or {})
    expected = _decorated_tool_names_in_source()
    assert expected, "source scan found no mcp.tool() registrations"
    assert registered == expected, {
        "missing": sorted(expected - registered),
        "unexpected": sorted(registered - expected),
    }


def test_deferred_shim_replays_registrations_made_before_and_after_binding():
    pytest.importorskip("mcp.server.mcpserver", reason="mcp server SDK not installed")
    from fsr_playbooks.mcp_server._shared import _DeferredMCP

    shim = _DeferredMCP("shim-test")

    @shim.tool()
    def before_bind() -> str:
        return "a"

    assert shim._real is None, "recording must not build the SDK server"

    shim._bind()

    @shim.tool(name="renamed_after")
    def after_bind() -> str:
        return "b"

    # Decorator returns the function unchanged in both phases.
    assert before_bind() == "a" and after_bind() == "b"
    names = set(shim._tool_manager._tools)
    assert names == {"before_bind", "renamed_after"}, sorted(names)


def test_deferred_shim_forwards_tool_arguments_on_replay():
    pytest.importorskip("mcp.server.mcpserver", reason="mcp server SDK not installed")
    from fsr_playbooks.mcp_server._shared import _DeferredMCP

    shim = _DeferredMCP("shim-args")

    @shim.tool(name="custom_name", description="custom desc")
    def impl() -> str:
        return "x"

    tool = shim._tool_manager._tools.get("custom_name")
    assert tool is not None, sorted(shim._tool_manager._tools)
    assert tool.description == "custom desc"
