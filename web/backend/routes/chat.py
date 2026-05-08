"""Chat SSE endpoint.

POST /api/chat with {messages: [{role, content}], current_yaml?: str}.
Streams Server-Sent Events with the normalized event shape from
backend.llm.provider.
"""
from __future__ import annotations

import json
import os
from typing import Any, AsyncIterator

from fastapi import APIRouter
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from backend import settings as _settings
from backend.llm.factory import get_provider
from backend.llm.provider import (
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
from backend.llm import ladder as _ladder
from backend.system_prompt import SYSTEM_PROMPT
from backend import history as history_db
from backend.llm.usage_log import est_tokens, log_turn


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
            "data": json.dumps(
                {"name": event.name, "arguments": event.arguments, "call_id": event.call_id}
            ),
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
                system=SYSTEM_PROMPT, messages=messages,
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
                    from backend.llm._loop_helpers import extract_yaml_block
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
