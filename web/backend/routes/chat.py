"""Chat SSE endpoint.

POST /api/chat with {messages: [{role, content}], current_yaml?: str}.
Streams Server-Sent Events with the normalized event shape from
fsr_core.llm.provider.
"""
from __future__ import annotations

import json
import os
from typing import Any, AsyncIterator

from fastapi import APIRouter
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from backend import settings as _settings
from fsr_core.llm.factory import get_provider
from fsr_core.llm.provider import (
    ApprovalRequestEvent,
    DoneEvent,
    ErrorEvent,
    Event,
    LadderEvent,
    Message,
    TextEvent,
    ToolResultEvent,
    ToolUseEvent,
    UsageEvent,
)
from fsr_core.llm import approvals as _approval_store
from fsr_core.llm import ladder as _ladder
from backend.system_prompt import build_system_prompt
from backend import history as history_db
from fsr_core.llm.usage_log import est_tokens, log_turn


router = APIRouter(prefix="/api", tags=["chat"])


class ChatMessageIn(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ChatIn(BaseModel):
    messages: list[ChatMessageIn]
    current_yaml: str | None = None
    # None = use the active provider per settings; explicit string =
    # caller-pinned (rare; mostly for tests).
    provider: str | None = None


def _serialize(event: Event) -> dict[str, Any]:
    if isinstance(event, TextEvent):
        return {"event": "text", "data": json.dumps({"text": event.text})}
    if isinstance(event, ToolUseEvent):
        return {
            "event": "tool_use",
            "data": json.dumps({
                "name": event.name,
                "arguments": event.arguments,
                "call_id": event.call_id,
                "tier": event.tier,
            }),
        }
    if isinstance(event, ToolResultEvent):
        # Truncate big results so the UI doesn't get flooded.
        result = event.result
        try:
            preview = json.dumps(result, default=str)
        except Exception:
            preview = str(result)
        if len(preview) > 4000:
            preview = preview[:4000] + "…"
        return {
            "event": "tool_result",
            "data": json.dumps({"call_id": event.call_id, "result_preview": preview}),
        }
    if isinstance(event, UsageEvent):
        # Frontend can render a per-turn cost ribbon. Telemetry side
        # effects (history.db, JSONL) happen in the consumer below —
        # this just forwards the same shape over SSE for live display.
        return {
            "event": "usage",
            "data": json.dumps({
                "session_id": event.session_id,
                "turn": event.turn,
                "model": event.model,
                "input_tokens": event.input_tokens,
                "output_tokens": event.output_tokens,
                "cache_read": event.cache_read,
                "cache_write": event.cache_write,
                "history_chars": event.history_chars,
                "stop_reason": event.stop_reason,
                "tags": event.tags,
                "tool_calls": [
                    {"name": t.name,
                     "args_chars": t.args_chars,
                     "result_chars": t.result_chars}
                    for t in event.tool_calls
                ],
            }),
        }
    if isinstance(event, LadderEvent):
        return {
            "event": "ladder",
            "data": json.dumps({
                "rungs": [
                    {"id": r.id, "label": r.label,
                     "state": r.state, "summary": r.summary}
                    for r in event.rungs
                ],
                "error_count": event.error_count,
                "warning_count": event.warning_count,
                "achieved": event.achieved,
            }),
        }
    if isinstance(event, ApprovalRequestEvent):
        return {
            "event": "approval_request",
            "data": json.dumps({
                "approval_id": event.approval_id,
                "tool_use_id": event.tool_use_id,
                "tool": event.tool,
                "tier": event.tier,
                "preview": event.preview,
                "args_hash": event.args_hash,
                "summary": event.summary,
                "requires_step_up": event.requires_step_up,
            }),
        }
    if isinstance(event, DoneEvent):
        return {"event": "done", "data": json.dumps({"stop_reason": event.stop_reason})}
    if isinstance(event, ErrorEvent):
        return {"event": "error", "data": json.dumps({"message": event.message})}
    return {"event": "error", "data": json.dumps({"message": "unknown event type"})}


def _persist_usage(ev: UsageEvent) -> None:
    """Side-effect for a UsageEvent: write the JSONL firehose AND the
    indexed history.db row. Both are best-effort; we never raise out
    of here so a logging failure can't poison a live chat."""
    record = {
        "session": ev.session_id,
        "turn": ev.turn,
        "model": ev.model,
        "input_tokens": ev.input_tokens,
        "output_tokens": ev.output_tokens,
        "cache_read": ev.cache_read,
        "cache_write": ev.cache_write,
        "stop_reason": ev.stop_reason,
        "self_repair_turn": ev.self_repair_turn,
        "history_chars": ev.history_chars,
        "history_est_tokens": est_tokens(ev.history_chars),
        "tool_calls": [
            {"name": t.name, "args_chars": t.args_chars,
             "result_chars": t.result_chars,
             "result_est_tokens": est_tokens(t.result_chars)}
            for t in ev.tool_calls
        ],
        "tags": ev.tags,
    }
    log_turn(record)
    history_db.record_chat_turn(record)
    print(
        f"[chat {ev.session_id}#{ev.turn}] tokens — "
        f"input:{ev.input_tokens} output:{ev.output_tokens} "
        f"cache_read:{ev.cache_read} cache_write:{ev.cache_write} "
        f"history_chars:{ev.history_chars} "
        f"playbook:{ev.tags.get('playbook_collection') or '-'}",
        flush=True,
    )


def _yaml_tags(yaml_text: str | None) -> dict[str, Any]:
    """Pull the playbook collection name + content hash out of the
    editor YAML so each chat turn can be attributed to the playbook
    being looked at. The collection name is what the user reads; the
    sha lets us tell two same-named edits apart."""
    if not yaml_text:
        return {}
    import hashlib
    import re
    m = re.search(r'^\s*collection\s*:\s*(.+?)\s*$',
                  yaml_text, flags=re.MULTILINE)
    name = m.group(1).strip().strip('"\'') if m else None
    sha = hashlib.sha256(yaml_text.encode("utf-8")).hexdigest()[:12]
    out: dict[str, Any] = {"yaml_sha": sha}
    if name:
        out["playbook_collection"] = name
    return out


def _current_turn(messages: list[Message]) -> int:
    """Approximate turn index = number of user messages submitted in
    this request. Good enough for transcript ordering; the canonical
    turn lives on UsageEvent and lands in chat_turns."""
    return sum(1 for m in messages if m.role == "user")


_PLACEHOLDER_MARKERS = (
    "# Welcome — try one of these to get started:",
    "# ... rest of your current workflow content ...",
)


def _is_meaningful_yaml(text: str | None) -> bool:
    """Drop placeholder/empty buffers server-side. Sending the welcome
    scaffold biases the agent into extending it rather than authoring
    fresh — surfaced as an explicit failure mode by user feedback."""
    if not text:
        return False
    for marker in _PLACEHOLDER_MARKERS:
        if marker in text:
            return False
    # Strip comments + blank lines; require some non-trivial content.
    body = "\n".join(
        ln for ln in text.splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    )
    return len(body) >= 40


# Verbs that signal a surgical change to an existing playbook. Kept
# tight on purpose — false-positives (build flagged as enhance) waste
# a clarifying question; false-negatives (enhance flagged as build)
# trigger silent rewrites, which is the failure mode C2 exists to
# prevent. When in doubt with meaningful YAML present, default to
# enhance.
_ENHANCE_VERBS = (
    "fix", "fixes", "fixing", "update", "updates", "updating",
    "change", "changes", "changing", "edit", "edits", "editing",
    "add a", "add an", "add the", "add another",
    "remove", "removes", "removing", "delete", "deletes", "deleting",
    "make it also", "make it not", "also ", "instead",
    "tweak", "adjust", "patch",
    "why doesn't", "why does", "why is", "why isn't",
    "what's wrong", "whats wrong", "broken", "not working",
)

# Verbs that explicitly want a rewrite even when YAML is present.
# These should go to build mode (with the understanding the existing
# YAML may be discarded).
_REWRITE_VERBS = (
    "rewrite", "refactor", "start over", "from scratch",
    "build me", "build a", "build the", "create a", "create the",
    "make me a", "make me an",
)


def _detect_intent(current_yaml: str | None, last_user_msg: str) -> str:
    """Return "build" or "enhance" for the session's tags + prompt
    selection. Heuristic, not perfect — see C2 in AGENT_LOOP_REFINEMENT_PLAN.

    Rule of thumb (plan §C1):
    - No meaningful YAML in editor → build.
    - Meaningful YAML + explicit rewrite verb → build.
    - Meaningful YAML + enhance verb → enhance.
    - Meaningful YAML + ambiguous → enhance (safer; over-rewriting
      is the failure mode we're trying to avoid).
    """
    if not _is_meaningful_yaml(current_yaml):
        return "build"
    msg = (last_user_msg or "").lower()
    for v in _REWRITE_VERBS:
        if v in msg:
            return "build"
    for v in _ENHANCE_VERBS:
        if v in msg:
            return "enhance"
    return "enhance"


def _last_user_message(body: ChatIn) -> str:
    for m in reversed(body.messages):
        if m.role == "user":
            return m.content or ""
    return ""


def _build_messages(body: ChatIn) -> list[Message]:
    out: list[Message] = []
    if _is_meaningful_yaml(body.current_yaml):
        out.append(Message(
            role="user",
            content=f"Current editor YAML:\n```yaml\n{body.current_yaml}\n```",
        ))
        out.append(Message(role="assistant", content="Acknowledged."))
    for m in body.messages:
        if m.role not in ("user", "assistant"):
            continue
        out.append(Message(role=m.role, content=m.content))  # type: ignore[arg-type]
    return out


@router.post("/chat")
async def chat(body: ChatIn) -> EventSourceResponse:
    chosen = body.provider or _settings.get_active_provider_name()
    cfg = _settings.load_provider(chosen)
    if not cfg.is_configured():
        async def gen_err() -> AsyncIterator[dict[str, Any]]:
            yield {
                "event": "error",
                "data": json.dumps({
                    "message": f"{chosen!r} is not fully configured — open Settings "
                               f"and set the URL/key/model."
                }),
            }
            yield {"event": "done", "data": json.dumps({"stop_reason": "config_error"})}
        return EventSourceResponse(gen_err())

    provider = get_provider(chosen)
    messages = _build_messages(body)
    tags = _yaml_tags(body.current_yaml)
    intent = _detect_intent(body.current_yaml, _last_user_message(body))
    tags["intent"] = intent
    system_prompt = build_system_prompt(intent)

    async def gen() -> AsyncIterator[dict[str, Any]]:
        active_session_written = False
        # Per-turn transcript buffer: full message texts get persisted
        # to chat_messages on each UsageEvent (turn boundary).
        seq_in_turn = 0
        session_id: str | None = None
        # Buffer the latest YAML the assistant emitted so we can score
        # the ladder against the freshest draft after the turn completes.
        latest_assistant_yaml: str | None = None
        # Coalesce consecutive `TextEvent`s into one transcript row.
        # Streaming providers (esp. OpenAI-compat / LM Studio) emit
        # one delta per token, so persisting each as a row turns the
        # history view into hundreds of tiny bordered fragments. We
        # accumulate and flush at turn / tool / stream boundaries.
        assistant_buf: list[str] = []
        assistant_buf_turn: int | None = None
        assistant_buf_seq: int | None = None

        def _flush_assistant_text() -> None:
            nonlocal assistant_buf, assistant_buf_turn, assistant_buf_seq
            if not assistant_buf or session_id is None:
                assistant_buf = []
                assistant_buf_turn = None
                assistant_buf_seq = None
                return
            history_db.record_chat_message(
                session_id,
                assistant_buf_turn or _current_turn(messages),
                assistant_buf_seq if assistant_buf_seq is not None else 0,
                kind="assistant_text",
                content="".join(assistant_buf),
            )
            assistant_buf = []
            assistant_buf_turn = None
            assistant_buf_seq = None
        try:
            # tools=[] → provider self-fills with the right schema shape
            # (Anthropic input_schema vs OpenAI function-calling).
            async for ev in provider.stream(
                system=system_prompt, messages=messages,
                tools=[], tags=tags,
            ):
                if isinstance(ev, UsageEvent):
                    _flush_assistant_text()
                    _persist_usage(ev)
                    if not active_session_written:
                        history_db.write_active_session(ev.session_id)
                        active_session_written = True
                    # First UsageEvent of a chat: capture the user
                    # prompt(s) that led to this turn so the transcript
                    # is self-contained on replay.
                    if session_id is None:
                        session_id = ev.session_id
                        for i, m in enumerate(messages):
                            if m.role == "user" and isinstance(m.content, str):
                                history_db.record_chat_message(
                                    session_id, ev.turn, -100 + i,
                                    kind="user", content=m.content,
                                )
                    # NOTE: do NOT reset seq_in_turn here. The transcript
                    # row's `turn` column is `_current_turn(messages)` —
                    # constant for the whole POST request — while
                    # UsageEvent fires once per *LLM* round-trip inside
                    # the tool-use loop. Resetting seq each round caused
                    # later rounds' rows to collide with earlier ones on
                    # (session_id, turn, seq) and INSERT OR REPLACE
                    # silently overwrote the earlier text/tool_use/
                    # tool_result rows, leaving only the final round
                    # visible in the transcript and in replay.
                elif session_id and isinstance(ev, TextEvent):
                    if not assistant_buf:
                        assistant_buf_turn = _current_turn(messages)
                        assistant_buf_seq = seq_in_turn
                        seq_in_turn += 1
                    assistant_buf.append(ev.text)
                    # Sniff out a fenced ```yaml block from the running
                    # buffer so a block split across deltas still scores.
                    from fsr_core.llm._loop_helpers import extract_yaml_block
                    found = extract_yaml_block("".join(assistant_buf))
                    if found:
                        latest_assistant_yaml = found
                elif session_id and isinstance(ev, ToolUseEvent):
                    _flush_assistant_text()
                    history_db.record_chat_message(
                        session_id, _current_turn(messages), seq_in_turn,
                        kind="tool_use", name=ev.name,
                        content=json.dumps(ev.arguments, default=str),
                    )
                    seq_in_turn += 1
                    # If the assistant is validating/compiling a YAML body,
                    # tag this and subsequent turns with its collection +
                    # sha — so sessions that authored a playbook in chat
                    # but never round-tripped through the editor still
                    # show up in the History list with a real title.
                    # Mutating `tags` in place propagates to UsageEvents
                    # since the provider keeps the same dict reference.
                    if ev.name in ("validate_yaml", "compile_yaml"):
                        yaml_arg = ev.arguments.get("yaml_text") \
                            if isinstance(ev.arguments, dict) else None
                        derived = _yaml_tags(yaml_arg)
                        if derived:
                            tags.update(derived)
                elif session_id and isinstance(ev, ToolResultEvent):
                    _flush_assistant_text()
                    payload = ev.result if isinstance(ev.result, str) \
                        else json.dumps(ev.result, default=str)
                    history_db.record_chat_message(
                        session_id, _current_turn(messages), seq_in_turn,
                        kind="tool_result", name=ev.call_id,
                        content=payload,
                    )
                    seq_in_turn += 1
                yield _serialize(ev)

            # Final flush in case the stream ended without a terminal
            # UsageEvent (e.g. ErrorEvent / DoneEvent without usage).
            _flush_assistant_text()

            # End-of-turn: score the ladder against the freshest YAML
            # we have. Prefer the assistant's just-emitted block; fall
            # back to the editor buffer the user sent in. Skip placeholder
            # YAML so the rung doesn't fire with no real content.
            target = latest_assistant_yaml or (
                body.current_yaml if _is_meaningful_yaml(body.current_yaml) else None
            )
            if target:
                try:
                    ladder = _ladder.evaluate(target)
                    # Persist the snapshot so a session replay or audit
                    # query can reconstruct the loop state at this turn.
                    if session_id:
                        snapshot = {
                            "rungs": [
                                {"id": r.id, "label": r.label,
                                 "state": r.state, "summary": r.summary}
                                for r in ladder.rungs
                            ],
                            "error_count": ladder.error_count,
                            "warning_count": ladder.warning_count,
                            "achieved": ladder.achieved,
                        }
                        history_db.record_chat_message(
                            session_id, _current_turn(messages), seq_in_turn,
                            kind="ladder",
                            content=json.dumps(snapshot),
                        )
                        seq_in_turn += 1
                    yield _serialize(ladder)
                except Exception as exc:  # noqa: BLE001
                    # Never let scoring break a chat turn.
                    print(f"[chat] ladder eval failed: {exc!r}", flush=True)
        finally:
            if active_session_written:
                history_db.write_active_session(None)

    return EventSourceResponse(gen())


# --- HITL approval resume endpoint -----------------------------------------
#
# When the provider hits a tier-3+ tool call it stashes a SuspendedSession
# keyed by approval_id and emits an `approval_request` SSE event. The
# frontend renders an approval card and posts the user's decision here;
# we re-enter the provider loop with the decision baked in. Auth is the
# existing app session — no separate HMAC token. The approval_id itself
# is single-use (popped on resolution), so a replay attempt 404s.

class ApprovalDecisionIn(BaseModel):
    decision: str  # "approve" | "deny"
    # For tier-4 step-up: the user-typed target. Backend asserts this
    # equals the canonical target extracted from the suspended args
    # before flipping decision to approve. Frontend already enforces
    # the same check, but the frontend is bypassable — a curl with
    # `{"decision":"approve"}` and no confirmed_target must still 400.
    confirmed_target: str | None = None


def _extract_target(args: dict[str, Any]) -> str | None:
    """Pull the canonical target identifier out of the suspended args.

    Mirrors the frontend's `targetHint` derivation so both ends agree on
    what string the user must re-type. Order matters — first hit wins."""
    if not isinstance(args, dict):
        return None
    params = args.get("params")
    if isinstance(params, dict):
        for k in ("ip", "host", "target"):
            v = params.get(k)
            if isinstance(v, str) and v:
                return v
    v = args.get("target")
    if isinstance(v, str) and v:
        return v
    return None


@router.post("/approvals/{approval_id}")
async def resolve_approval(
    approval_id: str, body: ApprovalDecisionIn
) -> EventSourceResponse:
    if body.decision not in ("approve", "deny"):
        async def gen_bad() -> AsyncIterator[dict[str, Any]]:
            yield {"event": "error",
                   "data": json.dumps({"message": "decision must be approve or deny"})}
            yield {"event": "done", "data": json.dumps({"stop_reason": "bad_request"})}
        return EventSourceResponse(gen_bad())

    # Peek first so we can validate step-up before consuming the
    # session. A failed step-up must leave the session intact so the
    # user can retype the target.
    suspended = _approval_store.peek(approval_id)
    if suspended is None:
        async def gen_missing() -> AsyncIterator[dict[str, Any]]:
            yield {"event": "error",
                   "data": json.dumps({"message": "approval not found or expired"})}
            yield {"event": "done", "data": json.dumps({"stop_reason": "not_found"})}
        return EventSourceResponse(gen_missing())

    # Tier-4 step-up: backend re-derives the canonical target from the
    # suspended args and requires confirmed_target == target. Only
    # enforced on approve — deny is always allowed regardless of typing.
    if body.decision == "approve" and suspended.tier >= 4:
        target = _extract_target(suspended.args)
        if target and body.confirmed_target != target:
            async def gen_stepup() -> AsyncIterator[dict[str, Any]]:
                yield {"event": "error",
                       "data": json.dumps({
                           "message": f"Type the target ({target}) to confirm "
                                      f"this tier-{suspended.tier} action."
                       })}
                yield {"event": "done", "data": json.dumps({"stop_reason": "step_up_required"})}
            return EventSourceResponse(gen_stepup())

    # Validated — consume the session.
    suspended = _approval_store.pop(approval_id)
    if suspended is None:
        # Lost the race against TTL gc between peek and pop.
        async def gen_race() -> AsyncIterator[dict[str, Any]]:
            yield {"event": "error",
                   "data": json.dumps({"message": "approval not found or expired"})}
            yield {"event": "done", "data": json.dumps({"stop_reason": "not_found"})}
        return EventSourceResponse(gen_race())

    chosen = _settings.get_active_provider_name()
    provider = get_provider(chosen)

    async def gen() -> AsyncIterator[dict[str, Any]]:
        # Mirrors /api/chat: persist text / tool_use / tool_result rows
        # into the existing session's transcript. We don't re-run the
        # ladder eval here — resume is about whether a tool fired, not
        # about fresh YAML emission.
        session_id = suspended.session_id
        seq_in_turn = 0
        assistant_buf: list[str] = []

        def _flush() -> None:
            nonlocal assistant_buf
            if not assistant_buf:
                return
            history_db.record_chat_message(
                session_id, 0, seq_in_turn,
                kind="assistant_text", content="".join(assistant_buf),
            )
            assistant_buf = []

        try:
            resume_fn = getattr(provider, "resume", None)
            if resume_fn is None:
                yield {"event": "error",
                       "data": json.dumps({"message": "provider does not support approval resume"})}
                yield {"event": "done", "data": json.dumps({"stop_reason": "config_error"})}
                return
            async for ev in resume_fn(suspended=suspended, decision=body.decision):
                if isinstance(ev, UsageEvent):
                    _flush()
                    _persist_usage(ev)
                elif isinstance(ev, TextEvent):
                    assistant_buf.append(ev.text)
                elif isinstance(ev, ToolUseEvent):
                    _flush()
                    history_db.record_chat_message(
                        session_id, 0, seq_in_turn,
                        kind="tool_use", name=ev.name,
                        content=json.dumps(ev.arguments, default=str),
                    )
                    seq_in_turn += 1
                elif isinstance(ev, ToolResultEvent):
                    _flush()
                    payload = ev.result if isinstance(ev.result, str) \
                        else json.dumps(ev.result, default=str)
                    history_db.record_chat_message(
                        session_id, 0, seq_in_turn,
                        kind="tool_result", name=ev.call_id, content=payload,
                    )
                    seq_in_turn += 1
                yield _serialize(ev)
            _flush()
        except Exception as exc:  # noqa: BLE001
            yield {"event": "error",
                   "data": json.dumps({"message": f"resume failed: {exc}"})}
            yield {"event": "done", "data": json.dumps({"stop_reason": "resume_error"})}

    return EventSourceResponse(gen())
