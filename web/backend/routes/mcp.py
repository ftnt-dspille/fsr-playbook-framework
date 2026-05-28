"""Generic HTTP dispatcher over registered MCP tools.

Lets the visual editor (and any other UI) invoke any MCP tool without
per-tool plumbing. The browser POSTs `{args}` to `/api/mcp/<tool>` and
gets `{ok, result}` back.

Allowlist gate: by default every tool registered on `mcp_server.mcp`
is exposed. Set `FSRPB_MCP_ALLOW=tool_a,tool_b` to restrict, or
`FSRPB_MCP_DENY=…` to blacklist a few. Surfaced as Phase 0.1 of
VISUAL_EDITOR_PLAN.md.
"""
from __future__ import annotations

import asyncio
import inspect
import json
import os
from typing import Any

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/api/mcp", tags=["mcp"])


def _allow_deny() -> tuple[set[str] | None, set[str]]:
    allow_raw = os.environ.get("FSRPB_MCP_ALLOW", "").strip()
    deny_raw = os.environ.get("FSRPB_MCP_DENY", "").strip()
    allow = (
        {t.strip() for t in allow_raw.split(",") if t.strip()}
        if allow_raw else None
    )
    deny = {t.strip() for t in deny_raw.split(",") if t.strip()}
    return allow, deny


def _mcp():
    import fsr_core.mcp_server as mcp_server  # imported lazily so test harnesses can stub it
    return mcp_server.mcp


def _coerce_result(res: Any) -> Any:
    """FastMCP's `call_tool` returns either a Sequence[ContentBlock] or a
    dict. Normalize to JSON-able shape."""
    if isinstance(res, dict):
        return res
    if isinstance(res, (list, tuple)):
        # FastMCP often returns [ContentBlock, structured_dict]; prefer
        # the dict when present (structured output the tool actually
        # returned), fall back to JSON-decoding the content block.
        for item in res:
            if isinstance(item, dict):
                return item
        out = []
        for item in res:
            text = getattr(item, "text", None)
            if text is not None:
                try:
                    out.append(json.loads(text))
                except Exception:
                    out.append(text)
            else:
                out.append(repr(item))
        return out[0] if len(out) == 1 else out
    return res


@router.get("/_tools")
def list_tools() -> dict[str, Any]:
    """List every tool exposed through the dispatcher.

    Returns the same metadata the MCP server uses, plus the
    allow/deny verdict so the UI can grey out gated tools.
    """
    allow, deny = _allow_deny()
    tools = asyncio.run(_mcp().list_tools())
    out = []
    for t in tools:
        gated = (allow is not None and t.name not in allow) or (t.name in deny)
        out.append({
            "name": t.name,
            "title": getattr(t, "title", None),
            "description": (t.description or "").strip(),
            "input_schema": t.inputSchema,
            "gated": gated,
        })
    return {"count": len(out), "tools": out}


@router.post("/{tool_name}")
async def dispatch(tool_name: str, request: Request) -> dict[str, Any]:
    """Invoke `tool_name` with the JSON body as keyword arguments."""
    allow, deny = _allow_deny()
    if allow is not None and tool_name not in allow:
        raise HTTPException(403, f"tool {tool_name!r} not in FSRPB_MCP_ALLOW")
    if tool_name in deny:
        raise HTTPException(403, f"tool {tool_name!r} is in FSRPB_MCP_DENY")
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        raise HTTPException(400, "body must be a JSON object of tool args")

    mc = _mcp()
    try:
        result = await mc.call_tool(tool_name, body)
    except Exception as e:
        # FastMCP's call_tool raises ToolError on unknown names + arg
        # validation; surface the message rather than a 500.
        return {"ok": False, "error": f"{type(e).__name__}: {e}",
                "tool": tool_name}
    return {"ok": True, "tool": tool_name, "result": _coerce_result(result)}
