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
    Message,
    TextEvent,
    ToolResultEvent,
    ToolUseEvent,
    UsageEvent,
)
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


def _build_messages(body: ChatIn) -> list[Message]:
    out: list[Message] = []
    if body.current_yaml:
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
        try:
            # tools=[] → provider self-fills with the right schema shape
            # (Anthropic input_schema vs OpenAI function-calling).
            async for ev in provider.stream(
                system=SYSTEM_PROMPT, messages=messages,
                tools=[], tags=tags,
            ):
                if isinstance(ev, UsageEvent):
                    _persist_usage(ev)
                    # Write the active-session marker once per stream,
                    # so a follow-up `fsrpb push` from the CLI can
                    # correlate the push to this chat session.
                    if not active_session_written:
                        history_db.write_active_session(ev.session_id)
                        active_session_written = True
                yield _serialize(ev)
        finally:
            if active_session_written:
                history_db.write_active_session(None)

    return EventSourceResponse(gen())
