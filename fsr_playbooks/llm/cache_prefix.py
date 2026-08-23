"""The cached-prefix fingerprint -- what prompt caching actually keys on.

Anthropic's prompt cache is a **prefix match**: `tools` render before `system`,
which renders before `messages`, and any byte change anywhere in that prefix
discards everything after it. `anthropic_provider` marks the last tool with
`cache_control`, so for us the cached prefix is exactly *(tools, system)*.

That makes a dynamic tool surface and a warm cache directly opposed, and we
had no way to see it. The token counters were already plumbed
(`UsageEvent.cache_read` / `cache_write`, populated from
`cache_read_input_tokens` / `cache_creation_input_tokens` and summarised by
`fsrpb chat-stats`), but nothing said *why* a cache went cold -- only that it
had. A fingerprint does: two turns of one session with different fingerprints
could not possibly have shared a cache, and the diff names the tool that
moved.

Deliberately NOT a hash of the whole request: `messages` grows every turn by
design, and folding it in would make every fingerprint unique and the signal
worthless.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

#: Keys that are cosmetic to the model but noisy in a hash. `cache_control` is
#: the marker we ourselves stamp onto the last tool, so it moves whenever the
#: slice's length changes -- which is exactly what we are trying to measure,
#: not a change we want to double-count.
_IGNORED_TOOL_KEYS = frozenset({"cache_control"})


def _canonical_tool(tool: Any) -> Any:
    if not isinstance(tool, dict):
        return tool
    return {k: v for k, v in sorted(tool.items()) if k not in _IGNORED_TOOL_KEYS}


def prefix_fingerprint(system: Any, tools: Any) -> str:
    """A stable 12-char digest of the cacheable *(tools, system)* prefix.

    Order-sensitive on purpose -- reordering tools invalidates the cache just
    as surely as adding one, and a set-based digest would hide that. Sorted
    keys WITHIN each tool, because JSON key order is an artifact of how the
    dict was built and not something the wire preserves meaningfully.
    """
    payload = {
        "tools": [_canonical_tool(t) for t in (tools or [])],
        "system": system if isinstance(system, str) else json.dumps(
            system, sort_keys=True, default=str),
    }
    blob = json.dumps(payload, sort_keys=False, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:12]


def tool_names(tools: Any) -> list[str]:
    """The advertised tool names, in order -- the human-readable half of a
    fingerprint diff."""
    out: list[str] = []
    for t in tools or []:
        if isinstance(t, dict):
            name = t.get("name")
            if not name and isinstance(t.get("function"), dict):
                name = t["function"].get("name")
            if isinstance(name, str) and name:
                out.append(name)
    return out


def explain_change(prev_system: Any, prev_tools: Any,
                   system: Any, tools: Any) -> str:
    """Why the prefix moved, in one line. Empty when it did not.

    Answers the question a bare fingerprint mismatch cannot: was it the tool
    set, the tool order, a tool's schema, or the system prompt?
    """
    if prefix_fingerprint(prev_system, prev_tools) == prefix_fingerprint(
            system, tools):
        return ""
    before, after = tool_names(prev_tools), tool_names(tools)
    added = [n for n in after if n not in set(before)]
    removed = [n for n in before if n not in set(after)]
    parts: list[str] = []
    if added:
        parts.append(f"+{len(added)} tools ({', '.join(added[:5])})")
    if removed:
        parts.append(f"-{len(removed)} tools ({', '.join(removed[:5])})")
    if not added and not removed and before != after:
        parts.append("tool ORDER changed")
    if not added and not removed and before == after:
        parts.append("a tool SCHEMA changed")
    if prev_system != system:
        parts.append("system prompt changed")
    return "; ".join(parts) or "prefix changed"


__all__ = ["prefix_fingerprint", "tool_names", "explain_change"]
