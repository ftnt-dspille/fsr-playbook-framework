"""Suspended-session store for the HITL approval flow.

When a provider loop hits a tier-3+ tool call, it stashes everything
needed to resume — history snapshot, system prompt, tools list, tags,
the pending tool_use id, and the original tool args — under the
`approval_id` minted by `tools.dispatch`. A subsequent POST to
`/api/approvals/{approval_id}` resolves the decision: on approve we
re-dispatch with the internal `_approved=True` sentinel and patch the
synthetic tool_result; on deny we substitute `{ok: false,
code: "user_denied"}` and resume. The HITL guardrails plan calls for
single-use scope, so each entry is consumed (popped) on resolution.

This is in-memory: the chat backend is single-process today. If we
later run multiple workers, swap the dict for Redis or sqlite-backed
storage — the public surface (`stash`, `pop`, `peek`) is small enough
that the migration is mechanical.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any


# 10 minutes. Long enough that a user can context-switch to read the
# args; short enough that a stale approval doesn't sit around for hours
# if someone walks away. The plan's HMAC variant used 60s; without HMAC
# we get our binding from the in-memory record itself, which we can
# afford to keep longer.
_TTL_SECONDS = 600


@dataclass
class SuspendedSession:
    approval_id: str
    session_id: str
    tool: str
    tool_use_id: str
    args: dict[str, Any]
    tier: int
    # Wire-form history up to (but NOT including) the user turn that
    # would carry the tool_result blocks for the just-stopped assistant
    # turn. The assistant turn (text + tool_use blocks) IS included.
    history_snapshot: list[Any]
    # tool_result blocks for tool_uses that resolved before the
    # pending one. Resume appends these + the resolved pending result
    # + placeholder denials for `remaining_tool_calls` into a single
    # user turn before re-entering the provider loop.
    prior_tool_result_blocks: list[dict[str, Any]]
    # Tool calls from the same assistant turn that hadn't run yet
    # when we suspended. Stored as (call_id, name, args). On resume
    # they're synthesized as `{ok: false, code: "superseded_by_approval"}`
    # so the model sees one tool_result per tool_use it emitted.
    remaining_tool_calls: list[tuple[str, str, dict[str, Any]]]
    system: str
    tags: dict[str, Any]
    summary: str | None = None
    created_at: float = field(default_factory=time.time)

    def expired(self, now: float | None = None) -> bool:
        return (now or time.time()) - self.created_at > _TTL_SECONDS


_LOCK = threading.Lock()
_STORE: dict[str, SuspendedSession] = {}


def stash(s: SuspendedSession) -> None:
    with _LOCK:
        _gc_locked()
        _STORE[s.approval_id] = s


def peek(approval_id: str) -> SuspendedSession | None:
    with _LOCK:
        _gc_locked()
        return _STORE.get(approval_id)


def pop(approval_id: str) -> SuspendedSession | None:
    """Single-use consume. Returns None if missing or expired."""
    with _LOCK:
        _gc_locked()
        s = _STORE.pop(approval_id, None)
        if s and s.expired():
            return None
        return s


def clear() -> None:
    """Test helper."""
    with _LOCK:
        _STORE.clear()


def _gc_locked() -> None:
    now = time.time()
    dead = [k for k, v in _STORE.items() if v.expired(now)]
    for k in dead:
        _STORE.pop(k, None)
