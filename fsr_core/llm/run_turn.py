"""Reusable agent-turn driver.

`run_agent_turn` consumes the event stream from `provider.stream()` and
performs the side effects that used to live inline in
`web/backend/routes/chat.py`: assistant-text coalescing, tool_use /
tool_result history rows, YAML sniffing for downstream consumers,
mid-stream tag mutation when the assistant validates/compiles a YAML
body, and first-UsageEvent retroactive user-message logging.

Consumers — the web SSE route, the FortiSOAR connector — supply two
optional adapters:

- `on_event`: called for every emitted event before any side effects.
  Web route uses it to push SSE frames; the connector ignores it and
  reads `TurnResult.transcript` after the call.
- `history_sink`: persistence target. Optional; without one, no rows
  are written and the function just collects the transcript.

The "loop" itself — the tool_use → tool_result agentic round-trip —
already lives inside `provider.stream()`. This module is the
*consumer* of that stream.
"""
from __future__ import annotations

import inspect
import json
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

from .approvals import SuspendedSession
from ._loop_helpers import extract_yaml_block
from .provider import (
    ApprovalRequestEvent,
    DoneEvent,
    ErrorEvent,
    Event,
    LLMProvider,
    Message,
    TextEvent,
    ToolResultEvent,
    ToolUseEvent,
    UsageEvent,
)


# Tool names whose `yaml_text` argument should re-tag the turn with the
# playbook collection name + sha. Kept here (not in the consumer) because
# the tag mutation is what stamps subsequent UsageEvents — moving it out
# of the stream-consumer loop would break that invariant.
_YAML_TAGGING_TOOLS = ("validate_yaml", "compile_yaml")


# History-message kinds. Mirrors web/backend/history.py's enum so the
# connector's sqlite rows are wire-compatible with the web app's.
KIND_USER = "user"
KIND_ASSISTANT_TEXT = "assistant_text"
KIND_TOOL_USE = "tool_use"
KIND_TOOL_RESULT = "tool_result"


EventCallback = Optional[Callable[[Event], Optional[Awaitable[None]]]]


@dataclass
class TurnResult:
    """Snapshot of one turn. Returned from both `run_agent_turn` and
    `resume_agent_turn`.

    `last_assistant_yaml` is the freshest fenced ```yaml block the
    assistant emitted during this turn, surfaced so callers can use
    it without re-parsing the transcript.

    `tags` is the same dict the caller passed in (or a fresh one if
    they passed None). Mutated mid-stream when the assistant uses
    `validate_yaml` / `compile_yaml`, mirroring chat.py behavior.
    """
    transcript: list[Event] = field(default_factory=list)
    stop_reason: Optional[str] = None
    session_id: Optional[str] = None
    last_assistant_yaml: Optional[str] = None
    tags: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    final_seq: int = 0
    """Next available seq value in the current turn after the stream
    completes. Consumers persisting post-stream rows use this to
    avoid colliding with the transcript rows the function already
    wrote."""


class _TextCoalescer:
    """Buffers consecutive TextEvents and flushes them as a single
    history row at the next tool / turn / stream boundary.

    Streaming providers (OpenAI-compat, LM Studio) emit one TextEvent
    per token; persisting each as a row turns the history view into
    hundreds of bordered fragments. This is the same heuristic the
    old chat.py used.
    """

    def __init__(self) -> None:
        self.buf: list[str] = []
        self.turn: Optional[int] = None
        self.seq: Optional[int] = None

    def append(self, text: str, *, turn: int, seq: int) -> None:
        if not self.buf:
            self.turn = turn
            self.seq = seq
        self.buf.append(text)

    def flush(
        self, sink, session_id: Optional[str],
    ) -> bool:
        """Returns True if a row was written."""
        if not self.buf or session_id is None or sink is None:
            self.buf, self.turn, self.seq = [], None, None
            return False
        sink.record_chat_message(
            session_id,
            self.turn if self.turn is not None else 0,
            self.seq if self.seq is not None else 0,
            kind=KIND_ASSISTANT_TEXT,
            content="".join(self.buf),
        )
        self.buf, self.turn, self.seq = [], None, None
        return True

    def joined(self) -> str:
        return "".join(self.buf)


async def _fire_event_callback(cb: EventCallback, ev: Event) -> None:
    if cb is None:
        return
    out = cb(ev)
    if inspect.isawaitable(out):
        await out


def _yaml_tags(yaml_text: Optional[str]) -> dict[str, Any]:
    """Pull the playbook collection name + content hash out of YAML.
    Standalone duplicate of web/backend/routes/chat.py's helper so
    fsr_core has no dependency on the web app. Behavior must stay in
    sync — both compute a 12-char sha-256 prefix and pull
    `^collection:` line by name."""
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


async def run_agent_turn(
    *,
    provider: LLMProvider,
    system: str,
    messages: list[Message],
    tools: Optional[list[dict[str, Any]]] = None,
    tags: Optional[dict[str, Any]] = None,
    on_event: EventCallback = None,
    history_sink: Any = None,            # HistorySink protocol; Any to keep this file's imports cheap
    turn_for_history: int = 0,
    session_id: Optional[str] = None,
    user_message_seq_base: int = -100,
    coalesce_text: bool = True,
) -> TurnResult:
    """Drive one user turn through the provider and return the transcript.

    Side effects per event mirror web/backend/routes/chat.py exactly so
    the web app can swap to this function without behavior drift.

    Args:
      provider: anything implementing LLMProvider.
      system: system prompt.
      messages: wire-form prior + current user message.
      tools: tool schemas; empty list → provider self-fills.
      tags: free-form dict round-tripped on each UsageEvent. **Mutated
        in-place** when the assistant uses validate_yaml/compile_yaml,
        because the provider holds a reference to this dict and stamps
        subsequent UsageEvents from it.
      on_event: fired for each event before persistence; awaitable
        return is supported. Web route uses this to push SSE frames.
      history_sink: implements HistorySink. None → no rows written.
      turn_for_history: the `turn` column value for chat_messages rows.
        Web app derives from the request body's user-message count;
        connector picks its own monotonic scheme.
      session_id: optional pre-supplied session id. When provided,
        text / tool_use / tool_result events are persisted from the
        very first round-trip. When omitted, the function waits for
        the first UsageEvent (provider-generated id) before persisting
        anything — this mirrors web/backend/routes/chat.py behavior
        and means the first round's assistant text lives in the SSE
        stream only, not in history.db. The connector pre-supplies
        the widget's session id to avoid that gap.
      user_message_seq_base: starting `seq` for the retroactive user-
        message rows logged on the first UsageEvent. Default -100
        matches the web app and ensures user rows sort before assistant
        rows within the same `turn`.
      coalesce_text: True buffers consecutive TextEvents and flushes
        at tool / turn / end boundaries; False writes each as its own
        row. The web app keeps True; tests may turn it off for
        clarity.

    Returns: TurnResult with the full transcript, stop_reason, captured
    session_id (from the first UsageEvent), and last_assistant_yaml
    (freshest fenced yaml block, for caller use).
    """
    if tools is None:
        tools = []
    if tags is None:
        tags = {}

    result = TurnResult(tags=tags, session_id=session_id)
    coalescer = _TextCoalescer()
    seq_in_turn = 0
    # NOTE: seq does NOT reset between LLM round-trips inside a single
    # turn. AnthropicProvider emits one UsageEvent per round-trip; if
    # we reset seq on each, later rounds' rows collide with earlier
    # rounds on (session_id, turn, seq) and INSERT OR REPLACE silently
    # overwrites. See chat.py L379-388 for the original incident note.

    try:
        async for ev in provider.stream(
            system=system, messages=messages, tools=tools, tags=tags,
        ):
            await _fire_event_callback(on_event, ev)
            result.transcript.append(ev)

            if isinstance(ev, UsageEvent):
                if coalesce_text:
                    coalescer.flush(history_sink, result.session_id)
                if result.session_id is None:
                    # First UsageEvent: capture the session_id and
                    # retroactively log the user messages from the
                    # request body. Negative seq base so they sort
                    # before the assistant rows in this same turn.
                    result.session_id = ev.session_id
                    if history_sink is not None:
                        for i, m in enumerate(messages):
                            if m.role == "user" and isinstance(m.content, str):
                                history_sink.record_chat_message(
                                    ev.session_id,
                                    ev.turn,
                                    user_message_seq_base + i,
                                    kind=KIND_USER,
                                    content=m.content,
                                )
                result.stop_reason = ev.stop_reason

            elif isinstance(ev, TextEvent) and result.session_id:
                if coalesce_text:
                    coalescer.append(ev.text, turn=turn_for_history, seq=seq_in_turn)
                    if not coalescer.buf[:-1]:  # this was the first append
                        seq_in_turn += 1
                    # Sniff fenced yaml block from the running buffer
                    # so a block split across deltas still scores.
                    found = extract_yaml_block(coalescer.joined())
                    if found:
                        result.last_assistant_yaml = found
                else:
                    if history_sink is not None:
                        history_sink.record_chat_message(
                            result.session_id, turn_for_history, seq_in_turn,
                            kind=KIND_ASSISTANT_TEXT, content=ev.text,
                        )
                        seq_in_turn += 1
                    found = extract_yaml_block(ev.text)
                    if found:
                        result.last_assistant_yaml = found

            elif isinstance(ev, ToolUseEvent) and result.session_id:
                if coalesce_text:
                    coalescer.flush(history_sink, result.session_id)
                if history_sink is not None:
                    history_sink.record_chat_message(
                        result.session_id, turn_for_history, seq_in_turn,
                        kind=KIND_TOOL_USE, name=ev.name,
                        content=json.dumps(ev.arguments, default=str),
                    )
                seq_in_turn += 1
                # Mid-stream tag mutation. The provider holds a reference
                # to `tags`; mutating in place propagates the
                # playbook_collection tag onto subsequent UsageEvents.
                if ev.name in _YAML_TAGGING_TOOLS:
                    yaml_arg = ev.arguments.get("yaml_text") \
                        if isinstance(ev.arguments, dict) else None
                    derived = _yaml_tags(yaml_arg)
                    if derived:
                        tags.update(derived)

            elif isinstance(ev, ToolResultEvent) and result.session_id:
                if coalesce_text:
                    coalescer.flush(history_sink, result.session_id)
                if history_sink is not None:
                    payload = ev.result if isinstance(ev.result, str) \
                        else json.dumps(ev.result, default=str)
                    history_sink.record_chat_message(
                        result.session_id, turn_for_history, seq_in_turn,
                        kind=KIND_TOOL_RESULT, name=ev.call_id,
                        content=payload,
                    )
                seq_in_turn += 1

            elif isinstance(ev, DoneEvent):
                result.stop_reason = ev.stop_reason

            elif isinstance(ev, ErrorEvent):
                result.error = ev.message
                if result.stop_reason is None:
                    result.stop_reason = "error"

        # Final flush in case the stream ended without a terminal
        # tool / Usage boundary (e.g. ErrorEvent or pure-text turn).
        if coalesce_text:
            coalescer.flush(history_sink, result.session_id)

    except Exception as exc:  # noqa: BLE001
        result.error = f"{type(exc).__name__}: {exc}"
        # An exception terminates the stream — that's the real terminal
        # state regardless of whatever stop_reason the last UsageEvent
        # carried.
        result.stop_reason = "stream_error"
        if coalesce_text:
            coalescer.flush(history_sink, result.session_id)
        # Surface a synthetic ErrorEvent so on_event callers (SSE
        # route) can render the failure inline.
        err_ev = ErrorEvent(message=result.error)
        await _fire_event_callback(on_event, err_ev)
        result.transcript.append(err_ev)

    result.final_seq = seq_in_turn
    return result


async def resume_agent_turn(
    *,
    provider: LLMProvider,
    suspended: SuspendedSession,
    decision: str,
    on_event: EventCallback = None,
    history_sink: Any = None,
    turn_for_history: int = 0,
    coalesce_text: bool = True,
) -> TurnResult:
    """Resume a HITL-suspended turn after the user approves or denies.

    The caller is responsible for having `pop`'d the SuspendedSession
    from its ApprovalGateway before invoking. This function calls
    `provider.resume(suspended=suspended, decision=decision)` and
    consumes the resulting event stream with the same side-effect
    rules as `run_agent_turn`.

    Returns a TurnResult. If the provider doesn't implement `resume`,
    returns a result with `error` set and a synthetic ErrorEvent in
    `transcript`.
    """
    result = TurnResult(session_id=suspended.session_id)
    coalescer = _TextCoalescer()
    seq_in_turn = 0

    resume_fn = getattr(provider, "resume", None)
    if resume_fn is None:
        err_ev = ErrorEvent(message="provider does not support approval resume")
        result.error = err_ev.message
        result.stop_reason = "config_error"
        result.transcript.append(err_ev)
        await _fire_event_callback(on_event, err_ev)
        return result

    try:
        async for ev in resume_fn(suspended=suspended, decision=decision):
            await _fire_event_callback(on_event, ev)
            result.transcript.append(ev)

            if isinstance(ev, UsageEvent):
                if coalesce_text:
                    coalescer.flush(history_sink, result.session_id)
                result.stop_reason = ev.stop_reason

            elif isinstance(ev, TextEvent):
                if coalesce_text:
                    coalescer.append(ev.text, turn=turn_for_history, seq=seq_in_turn)
                    if not coalescer.buf[:-1]:
                        seq_in_turn += 1
                else:
                    if history_sink is not None:
                        history_sink.record_chat_message(
                            result.session_id, turn_for_history, seq_in_turn,
                            kind=KIND_ASSISTANT_TEXT, content=ev.text,
                        )
                        seq_in_turn += 1

            elif isinstance(ev, ToolUseEvent):
                if coalesce_text:
                    coalescer.flush(history_sink, result.session_id)
                if history_sink is not None:
                    history_sink.record_chat_message(
                        result.session_id, turn_for_history, seq_in_turn,
                        kind=KIND_TOOL_USE, name=ev.name,
                        content=json.dumps(ev.arguments, default=str),
                    )
                seq_in_turn += 1

            elif isinstance(ev, ToolResultEvent):
                if coalesce_text:
                    coalescer.flush(history_sink, result.session_id)
                if history_sink is not None:
                    payload = ev.result if isinstance(ev.result, str) \
                        else json.dumps(ev.result, default=str)
                    history_sink.record_chat_message(
                        result.session_id, turn_for_history, seq_in_turn,
                        kind=KIND_TOOL_RESULT, name=ev.call_id,
                        content=payload,
                    )
                seq_in_turn += 1

            elif isinstance(ev, DoneEvent):
                result.stop_reason = ev.stop_reason

            elif isinstance(ev, ErrorEvent):
                result.error = ev.message
                if result.stop_reason is None:
                    result.stop_reason = "error"

        if coalesce_text:
            coalescer.flush(history_sink, result.session_id)

    except Exception as exc:  # noqa: BLE001
        result.error = f"{type(exc).__name__}: {exc}"
        if result.stop_reason is None:
            result.stop_reason = "stream_error"
        if coalesce_text:
            coalescer.flush(history_sink, result.session_id)
        err_ev = ErrorEvent(message=result.error)
        await _fire_event_callback(on_event, err_ev)
        result.transcript.append(err_ev)

    return result


__all__ = [
    "TurnResult",
    "run_agent_turn",
    "resume_agent_turn",
    "KIND_USER", "KIND_ASSISTANT_TEXT", "KIND_TOOL_USE", "KIND_TOOL_RESULT",
]
