"""Packaged triage→build agent loop, exposed as two MCP tools.

This is the *third* front-end onto the same agent loop the FortiSOAR
connector (`operations.py: chat_turn`) and the web backend
(`web/backend/routes/chat.py`) already drive. All three assemble the same
five pieces from ``fsr_playbooks``:

  1. Provider    — ``factory.get_provider`` (here defaulted to the local
                   gpt-oss OpenAI gateway for token-cheap triage).
  2. System prompt — ``intents.load_intent_prompt(intent)``.
  3. Tool slice  — ``intents.tools_for_intent(intent)``.
  4. Trace       — ``skill_trace.set_active_trace`` around the turn, so the
                   ops the agent runs become a ``SkillTrace`` that
                   ``build_playbook_from_trace`` can compile.
  5. Approvals   — an ``InMemoryApprovalGateway`` per session; tier-3+ calls
                   suspend mid-turn and resume via ``triage_build_resume``.

The only thing this module adds is an **in-process session store** keyed by
``session_id`` (the connector uses sqlite + the widget; the web app uses the
request body + sqlite). No persistence across MCP-server restarts — a dropped
approval just re-runs, which is acceptable for an interactive desktop tool.

See ``docs/ARCHITECTURE_AGENT_LOOP.md`` for the shared-wiring contract.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ._shared import mcp, _err
from fsr_playbooks.agent import skill_trace
from fsr_playbooks.llm import factory, intents
from fsr_playbooks.llm.approvals import InMemoryApprovalGateway
from fsr_playbooks.llm.provider import (
    ApprovalRequestEvent,
    ErrorEvent,
    Message,
    TextEvent,
    ToolUseEvent,
)
from fsr_playbooks.llm.run_turn import run_agent_turn, resume_agent_turn
from fsr_playbooks.protocols import ProviderConfig


# --- env-backed ConfigProvider for the standalone MCP server --------------
#
# The web app and the connector each install their own ConfigProvider at
# startup; the bare `python -m mcp_server` process has none. We install a
# small env-backed one on first use (only if nothing else already did, so an
# embedding host's config wins).
#
# Provider selector: `FSR_LLM_PROVIDER` (the neutral name for this surface).
# `STUDIO_LLM_PROVIDER` is honored only as a legacy fallback so one shared
# `.env` can still drive both this server and the web app (`web/backend/
# settings.py`, which predates this and uses the STUDIO_ name). The
# OPENAI_*/ANTHROPIC_* keys are already the standard names, shared as-is.
# Default = openai (the gpt-oss gateway — triage loops are token-heavy, this
# makes them ~free). Set FSR_LLM_PROVIDER=anthropic for quality A/Bs.

def _env(*names: str, default: Optional[str] = None) -> Optional[str]:
    for n in names:
        v = os.environ.get(n)
        if v:
            return v
    return default


class _EnvConfigProvider:
    def get_active_provider_name(self) -> str:
        return _env("FSR_LLM_PROVIDER", "STUDIO_LLM_PROVIDER", default="openai")

    def load_provider(self, name: str) -> ProviderConfig:
        if name == "anthropic":
            return ProviderConfig(
                name="anthropic",
                api_key=_env("ANTHROPIC_API_KEY", "STUDIO_ANTHROPIC_API_KEY"),
                base_url=_env("ANTHROPIC_BASE_URL", "STUDIO_ANTHROPIC_BASE_URL"),
                model=_env("ANTHROPIC_MODEL", "STUDIO_ANTHROPIC_MODEL"),
            )
        # openai-compatible (default → the gpt-oss gateway in .env.example)
        return ProviderConfig(
            name=name,
            api_key=_env("OPENAI_API_KEY", "STUDIO_OPENAI_API_KEY",
                         default="sk-local"),
            base_url=_env("OPENAI_ENDPOINT", "STUDIO_OPENAI_BASE_URL",
                          "OPENAI_BASE_URL"),
            model=_env("OPENAI_MODEL", "STUDIO_OPENAI_MODEL"),
        )


_ENV_LOADED = False


def _load_repo_env_once() -> None:
    """setdefault the repo-root `.env` into os.environ.

    The MCP server otherwise only loads `.env` lazily when `run_op` builds
    the live FSR client (`probes._env`) — which is AFTER we construct the
    provider. Loading it here means the provider env (STUDIO_*/OPENAI_*/
    ANTHROPIC_*) is populated before `get_provider`. `setdefault` so a real
    environment value (e.g. Claude Desktop's MCP `env` block) still wins."""
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    _ENV_LOADED = True
    try:
        from ._shared import REPO_ROOT
        env_path = REPO_ROOT / ".env"
        if not env_path.is_file():
            return
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip().strip('"').strip("'")
            if key:
                os.environ.setdefault(key, val)
    except Exception:  # noqa: BLE001 — env load is best-effort
        pass


def _ensure_config_provider() -> None:
    _load_repo_env_once()
    # Peek the factory's installed provider; only install ours if none.
    if getattr(factory, "_CONFIG_PROVIDER", None) is None:
        factory.set_config_provider(_EnvConfigProvider())


# --- in-process session store ---------------------------------------------

_SESSION_TTL = 1800  # 30 min idle eviction


@dataclass
class _Session:
    session_id: str
    messages: List[Message] = field(default_factory=list)
    trace: Any = field(default_factory=skill_trace.SkillTrace)
    gateway: InMemoryApprovalGateway = field(
        default_factory=InMemoryApprovalGateway)
    pending_approval_id: Optional[str] = None
    last_used: float = field(default_factory=time.time)


_SESSIONS: Dict[str, _Session] = {}


def _evict() -> None:
    now = time.time()
    for k in [k for k, v in _SESSIONS.items()
              if now - v.last_used > _SESSION_TTL]:
        _SESSIONS.pop(k, None)


def _get_or_create(session_id: Optional[str]) -> _Session:
    _evict()
    if session_id and session_id in _SESSIONS:
        s = _SESSIONS[session_id]
        s.last_used = time.time()
        return s
    sid = session_id or uuid.uuid4().hex
    s = _Session(session_id=sid)
    _SESSIONS[sid] = s
    return s


# --- transcript flattening -------------------------------------------------
#
# Wire-compatible *naming* with the connector's card vocabulary
# (operations.py `_CARD_EMITTER_TO_TYPE`) but without the widget envelope —
# a desktop MCP client just needs text + structured cards.

_CARD_EMITTER_TO_TYPE = {
    "emit_choice_card": "choice_card",
    "emit_action_card": "action_card",
    "emit_manual_input": "manual_input",
    "emit_capability_gap_card": "capability_gap",
    "emit_playbook_offer": "playbook_offer",
}


def _collapse_assistant_turn(result: Any) -> str:
    """Flatten a turn's transcript into one assistant-message string for the
    next turn's history. Mirrors the connector's `_text_of` collapse: tool
    calls and cards become compact markers, so we never replay raw tool_use
    ids (which would need exact pairing) and the model still recalls what it
    did. Never empty — Anthropic rejects empty assistant content."""
    parts: List[str] = []
    for ev in result.transcript:
        if isinstance(ev, TextEvent):
            if ev.text:
                parts.append(ev.text)
        elif isinstance(ev, ToolUseEvent):
            ctype = _CARD_EMITTER_TO_TYPE.get(ev.name)
            args = json.dumps(ev.arguments or {}, default=str)[:300]
            if ctype:
                parts.append(f"[{ctype} '{ev.call_id}': {args}]")
            else:
                parts.append(f"[called {ev.name}({args})]")
    text = "\n".join(p for p in parts if p)
    return text or "[turn produced no text]"


def _flatten(result: Any) -> Dict[str, Any]:
    """transcript → {text, cards[], approval?, playbook_offer?, error?}."""
    texts: List[str] = []
    cards: List[Dict[str, Any]] = []
    playbook_offer: Optional[Dict[str, Any]] = None
    approval: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    for ev in result.transcript:
        if isinstance(ev, TextEvent):
            if ev.text:
                texts.append(ev.text)
        elif isinstance(ev, ToolUseEvent):
            ctype = _CARD_EMITTER_TO_TYPE.get(ev.name)
            if ctype:
                card = {"type": ctype, "id": ev.call_id, "args": ev.arguments}
                cards.append(card)
                if ctype == "playbook_offer":
                    playbook_offer = card
        elif isinstance(ev, ApprovalRequestEvent):
            approval = {
                "approval_id": ev.approval_id,
                "tool": ev.tool,
                "tier": ev.tier,
                "preview": ev.preview,
                "summary": ev.summary,
                "requires_step_up": ev.requires_step_up,
            }
        elif isinstance(ev, ErrorEvent):
            error = ev.message
    out: Dict[str, Any] = {"text": "".join(texts), "cards": cards}
    if approval is not None:
        out["approval"] = approval
    if playbook_offer is not None:
        out["playbook_offer"] = playbook_offer
    if error is not None:
        out["error"] = error
    return out


def _staged_actions(session: _Session) -> List[Dict[str, Any]]:
    """The containment/mutating ops the agent STAGED via emit_action_card
    (recorded into the trace, never executed). These are what an accepted
    playbook would automate."""
    out: List[Dict[str, Any]] = []
    for c in getattr(session.trace, "calls", []) or []:
        if getattr(c, "staged", False):
            out.append({
                "skill_id": c.skill_id,
                "step_name": c.step_name,
                "inputs": c.resolved_inputs,
            })
    return out


def _entity_context(entity: Any) -> Optional[str]:
    """Minimal record-context block to ground the turn (compact form of the
    connector's `_entity_context_block`). The model answers from `fields`
    and uses the lookup keys to fetch correlated rows via its SOAR tools."""
    if not isinstance(entity, dict):
        return None
    lines: List[str] = []
    module = entity.get("module") or entity.get("type")
    ident = entity.get("uuid") or entity.get("id")
    header = "RECORD CONTEXT"
    if module:
        header += f" ({module}{('/' + str(ident)) if ident else ''})"
    lines.append(header)
    fields = entity.get("fields")
    if isinstance(fields, dict):
        for k, v in fields.items():
            if v not in (None, ""):
                lines.append(f"  {k}: {v}")
    keys = [f"{k}={entity[k]}" for k in ("iri", "module", "uuid", "id")
            if entity.get(k)]
    if keys:
        lines.append("Lookup keys (fetch correlated rows with your SOAR "
                     "tools — NOT in fields above): " + " ".join(keys))
    return "\n".join(lines) if len(lines) > 1 else None


def _run(session: _Session, intent: str, provider_name: Optional[str],
         coro_factory) -> Dict[str, Any]:
    """Shared turn driver: install trace + run the coroutine + flatten.
    `coro_factory(provider)` returns the awaitable (run or resume)."""
    _ensure_config_provider()
    try:
        provider = factory.get_provider(
            provider_name or None, approval_gateway=session.gateway)
    except Exception as exc:  # noqa: BLE001
        return _err("provider_init_failed", f"{type(exc).__name__}: {exc}")

    skill_trace.set_active_trace(session.trace)
    try:
        result = asyncio.run(coro_factory(provider))
    except Exception as exc:  # noqa: BLE001
        return _err("agent_turn_failed", f"{type(exc).__name__}: {exc}")
    finally:
        skill_trace.clear_active_trace()

    # Persist the assistant turn (collapsed) for the next turn's context.
    session.messages.append(
        Message(role="assistant", content=_collapse_assistant_turn(result)))

    flat = _flatten(result)
    session.pending_approval_id = (
        flat["approval"]["approval_id"]
        if result.stop_reason == "pending_approval" and "approval" in flat
        else None)

    return {
        "ok": result.error is None,
        "session_id": session.session_id,
        "intent": intent,
        "stop_reason": result.stop_reason,
        "text": flat["text"],
        "cards": flat["cards"],
        "staged_actions": _staged_actions(session),
        "approval": flat.get("approval"),
        "playbook_offer": flat.get("playbook_offer"),
        "error": flat.get("error"),
    }


# --- the two (+one) MCP tools ---------------------------------------------


@mcp.tool()
def triage_build_turn(
    message: str,
    session_id: str = "",
    intent: str = "triage",
    entity: Optional[Dict[str, Any]] = None,
    provider: str = "",
) -> Dict[str, Any]:
    """Run one turn of the packaged investigate→triage→build agent loop.

    The same loop the FortiSOAR widget drives, with no FSR UI: read-only
    enrichment runs inline, containment is STAGED via an action card for
    approval, and the ops the agent runs are recorded into a per-session
    trace so a follow-up "build a re-runnable playbook from what you just
    did" compiles them via build_playbook_from_trace.

    Args:
      message: the analyst's message for this turn.
      session_id: omit to start a new session; pass the returned id to
        continue. HITL state + trace live under it.
      intent: "triage" (default — investigate + stage) or "build"
        (author/compile a playbook).
      entity: optional {module, uuid|id, fields, iri, tags} record to
        ground the turn in (injected as RECORD CONTEXT).
      provider: override the LLM provider for this turn ("openai" |
        "anthropic"); default = env (local gpt-oss gateway).

    Returns: {ok, session_id, stop_reason, text, cards[], staged_actions[],
      approval?, playbook_offer?}. When stop_reason == "pending_approval",
      `approval` carries the action awaiting a decision — call
      triage_build_resume to approve/deny.
    """
    intent = intents.resolve_intent(intent)
    session = _get_or_create(session_id or None)

    user_text = message
    ctx = _entity_context(entity)
    if ctx:
        user_text = f"{ctx}\n\n{message}"
    session.messages.append(Message(role="user", content=user_text))

    if isinstance(entity, dict):
        mod = entity.get("module") or entity.get("type")
        if mod:
            skill_trace.set_active_trace_module(mod)
        if isinstance(entity.get("fields"), dict):
            skill_trace.set_active_trace_record_fields(entity["fields"])

    system = intents.load_intent_prompt(intent)
    tools = intents.tools_for_intent(intent)

    def _coro(provider_obj):
        return run_agent_turn(
            provider=provider_obj,
            system=system,
            messages=session.messages,
            tools=tools,
            tags={"session_id": session.session_id, "intent": intent},
            session_id=session.session_id,
        )

    return _run(session, intent, provider or None, _coro)


@mcp.tool()
def triage_build_resume(
    session_id: str,
    decision: str,
    provider: str = "",
) -> Dict[str, Any]:
    """Resume a turn suspended on a pending approval (tier-3+ action).

    Args:
      session_id: the session returned by triage_build_turn.
      decision: "approve" or "deny".
      provider: optional provider override (must match the turn's provider
        family for resume to replay correctly); default = env.

    Returns: same shape as triage_build_turn. Re-suspends if the next
    tier-3+ call needs another approval.
    """
    session = _SESSIONS.get(session_id)
    if session is None:
        return _err("unknown_session", f"unknown session_id {session_id!r}")
    session.last_used = time.time()
    if not session.pending_approval_id:
        return _err("no_pending_approval", "no pending approval for this session")
    if decision not in ("approve", "deny"):
        return _err("bad_decision", "decision must be 'approve' or 'deny'")

    suspended = session.gateway.pop(session.pending_approval_id)
    session.pending_approval_id = None
    if suspended is None:
        return _err("approval_expired", "suspended session expired or already resolved")

    def _coro(provider_obj):
        return resume_agent_turn(
            provider=provider_obj,
            suspended=suspended,
            decision=decision,
        )

    intent = suspended.tags.get("intent", "triage") \
        if isinstance(suspended.tags, dict) else "triage"
    return _run(session, intent, provider or None, _coro)


# =========================================================================
# Desktop-native path — the driving model (Claude Desktop / Claude Code) runs
# the loop ITSELF using the granular tools; these expose the two pieces the
# packaged turn used to hide so no inner model / API key is needed:
#   1. a trace-session lifecycle (so run_op recording is on while you drive),
#   2. the tuned triage guidance (so you inherit the same discipline).
# `run_op` records into the active trace; `build_playbook_from_trace()` reads
# it. See [[feedback_desktop_native_triage]].
# =========================================================================


@mcp.tool()
def triage_session_start(entity: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Begin recording the ops you run so they can be compiled into a
    re-runnable playbook later.

    Use this when YOU (Claude Desktop / Claude Code) are driving the triage
    with the granular tools directly — call it ONCE at the start, then run
    `run_op` for read-only enrichment and `emit_action_card` to stage
    containment, and finish with `build_playbook_from_trace()` (no args — it
    reads this session). Recording is process-global, so it stays on across
    your tool calls until you call `triage_session_clear`.

    Args:
      entity: optional {module, uuid|id, fields} record to ground the trace
        (stamps the module + record fields onto the compiled playbook).
    """
    trace = skill_trace.SkillTrace()
    skill_trace.set_active_trace(trace)
    module = None
    if isinstance(entity, dict):
        module = entity.get("module") or entity.get("type")
        if module:
            skill_trace.set_active_trace_module(module)
        if isinstance(entity.get("fields"), dict):
            skill_trace.set_active_trace_record_fields(entity["fields"])
    return {
        "ok": True,
        "recording": True,
        "module": module,
        "how_to_drive": (
            "Run read-only enrichment with run_op. STAGE any containment "
            "(block/isolate/disable) with emit_action_card — do NOT run it. "
            "When done, call build_playbook_from_trace() with no args to "
            "compile what you did into a playbook."),
        "guidance": "call triage_guidance for the full triage instruction sheet",
    }


@mcp.tool()
def triage_session_state() -> Dict[str, Any]:
    """Show what the current triage recording has captured so far — the ops
    that will become playbook steps when you call build_playbook_from_trace."""
    trace = skill_trace.get_active_trace()
    if trace is None:
        return {"ok": True, "recording": False, "calls": [], "count": 0}
    calls = [
        {"skill_id": c.skill_id, "step_name": c.step_name,
         "staged": bool(getattr(c, "staged", False))}
        for c in getattr(trace, "calls", []) or []
    ]
    return {"ok": True, "recording": True, "calls": calls, "count": len(calls)}


@mcp.tool()
def triage_session_clear() -> Dict[str, Any]:
    """Stop recording and discard the current triage trace (start fresh)."""
    skill_trace.clear_active_trace()
    return {"ok": True, "recording": False}


@mcp.tool()
def triage_guidance() -> Dict[str, Any]:
    """The tuned FortiSOAR triage instruction sheet. Load this at the start of
    an incident triage so you follow the same discipline the packaged agent
    uses: investigate read-only, correlate across BOTH alerts and incidents,
    stage—never silently run—containment, and keep the loop tight."""
    return {"ok": True, "guidance": intents.load_intent_prompt("triage")}


# Also surface the triage instinct sheet as an MCP *prompt* primitive, so a
# client (Claude Desktop / Claude Code) can load it natively without a tool
# round-trip. Best-effort — guarded so a FastMCP build without prompt support
# (the connector's fallback shim) doesn't break import.
try:  # pragma: no cover - registration only
    @mcp.prompt(name="triage", description="FortiSOAR incident-triage instincts")
    def _triage_prompt() -> str:
        return intents.load_intent_prompt("triage")
except Exception:  # noqa: BLE001
    pass


__all__ = [
    "triage_build_turn", "triage_build_resume",
    "triage_session_start", "triage_session_state", "triage_session_clear",
    "triage_guidance",
]
