# Agent loop lift — plan

> **STATUS: PARKED — post-demo.** Prerequisite for chat streaming (CHAT_STREAMING_PLAN.md) but not needed for the SOC demo. Resume after demo milestone.

Goal: extract the event-consumer side of `web/backend/routes/chat.py` into a reusable
`fsr_playbooks.llm.run_turn.run_agent_turn()` so the FortiSOAR connector can implement
`chat_turn` / `chat_resume` without duplicating 200+ lines of streaming/persistence
glue. The web app's SSE route shrinks to input shaping + an `on_event` callback
that serializes events for the browser.

## What's actually a "loop"

Important framing: the agent **tool-use loop** already lives inside
`provider.stream()` (AnthropicProvider drives the Anthropic API, handles the
tool_use → tool_result round-trip, and emits one `UsageEvent` per LLM
round-trip). What `chat.py` contains is a **consumer** that drives side
effects from the stream's events. That consumer is what we're lifting.

## Surface to extract

```python
# fsr_playbooks/llm/run_turn.py  (NEW)

@dataclass
class TurnResult:
    transcript: list[Event]
    stop_reason: str | None
    session_id: str | None
    last_assistant_yaml: str | None   # for downstream ladder scoring
    tags: dict[str, Any]              # may have been mutated mid-stream

async def run_agent_turn(
    *,
    provider: LLMProvider,
    system: str,
    messages: list[Message],
    tools: list[dict[str, Any]] | None = None,
    tags: dict[str, Any] | None = None,
    on_event: Callable[[Event], Awaitable[None] | None] | None = None,
    history_sink: HistorySink | None = None,
    turn_for_history: int = 0,
    coalesce_text: bool = True,
) -> TurnResult: ...

async def resume_agent_turn(
    *,
    provider: LLMProvider,
    suspended: SuspendedSession,
    decision: Literal["approve", "deny"],
    on_event: Callable[[Event], Awaitable[None] | None] | None = None,
    history_sink: HistorySink | None = None,
) -> TurnResult: ...
```

Why these arguments:

- **`on_event`** — fires for *every* event before any persistence. The web
  app uses this to push SSE frames to the browser; the connector ignores
  it and reads `TurnResult.transcript` after the call.
- **`history_sink`** — optional. When supplied, the function writes
  `user` / `assistant_text` / `tool_use` / `tool_result` rows for the
  turn. Web app injects `backend.history`; connector injects
  `fsr-playbook-builder.storage.Storage`.
- **`turn_for_history`** — the row's `turn` column. The web app derives
  it from `_current_turn(messages)` (count of user messages in the
  *request body*, not the stream); the connector probably wants its own
  monotonic counter. Caller-supplied so neither side bakes in an
  assumption.
- **`tags`** — passed by reference so the consumer's mid-stream mutation
  (on `validate_yaml` / `compile_yaml` ToolUse) still propagates into
  subsequent UsageEvents from the provider, mirroring today's behavior.
- **`coalesce_text`** — keep the "buffer consecutive TextEvents, flush
  at tool/turn boundary" logic that prevents the OpenAI-compat streaming
  delta storm from creating hundreds of tiny rows. Off by default in
  the protocol shape; web app turns it on.

## Where each chat.py concern lands

| concern (chat.py)                                  | lands in                                       |
|----------------------------------------------------|------------------------------------------------|
| `_serialize` (Event → SSE frame dict)              | **stays in route** (web-only encoding)         |
| `_persist_usage` (log_turn + record_chat_turn)     | **stays in route** (passed as a callback into `history_sink.record_chat_turn`) |
| `_yaml_tags` / `_detect_intent` / `_is_meaningful_yaml` | **stays in route** (chat-UX heuristics)   |
| `_build_messages` (prepends current_yaml)          | **stays in route**                             |
| assistant-text coalescing                          | **moves to run_turn**                          |
| `tool_use` → record_chat_message + tags mutation   | **moves to run_turn**                          |
| `tool_result` → record_chat_message                | **moves to run_turn**                          |
| yaml-block sniffing (`extract_yaml_block`)         | **moves to run_turn** → surfaced as `TurnResult.last_assistant_yaml` |
| ladder eval at end                                 | **stays in route** (uses `last_assistant_yaml`) |
| `write_active_session` on first UsageEvent + on exit | **stays in route** (web's session-active concept) |
| resume endpoint loop                               | **moves to run_turn** (`resume_agent_turn`)    |

The lift is ≈ 200 LoC of the 622 in chat.py. The rest is `_serialize`
(86 LoC), input shaping (60 LoC), the route bodies (250 LoC of FastAPI /
SSE wrapping / error handling), and the resume endpoint's HTTP layer.

## HistorySink shape (already in protocols.py)

```python
class HistorySink(Protocol):
    def write_active_session(self, session_id: str) -> None: ...
    def record_chat_turn(self, record: dict) -> None: ...
    def record_chat_message(
        self, session_id: str, turn: int, seq: int,
        kind: str, content: str, name: str | None = None,
    ) -> None: ...
```

Web app's adapter is a 10-line wrapper around `backend.history`. Connector
already satisfies the protocol via `fsr-playbook-builder.storage.Storage`
(verified by `test_persisted_gateway_satisfies_protocol` — just needs the
same parametric test for the sink methods).

## ApprovalGateway integration

`resume_agent_turn` doesn't need the gateway directly — the route popped
the SuspendedSession before calling it. The gateway argument exists on
the *provider* level: when `provider.stream()` hits a tier-3+ tool call
mid-loop, it calls `gateway.stash(session)` and emits an
`ApprovalRequestEvent`. Today AnthropicProvider imports
`fsr_playbooks.llm.approvals` directly (the backwards-compat facade), which
uses the in-memory default. Plan:

- AnthropicProvider gains an optional `approval_gateway: ApprovalGateway`
  constructor argument; defaults to the in-memory singleton via the
  facade. Web app passes nothing (gets in-memory); connector passes
  its `PersistedApprovalGateway`.
- This is a 5-line change in `anthropic_provider.py` and is the *only*
  reason chat_turn needs the gateway plumbing — without it, the
  connector's chat_turn would silently lose paused turns on restart.

## File-by-file diff sketch

**NEW** `fsr_playbooks/llm/run_turn.py` (~280 LoC)
- `TurnResult` dataclass
- `_TextCoalescer` helper (buffer + flush)
- `_consume_event_for_history(ev, sink, session_id, turn, seq, ...)`
- `run_agent_turn(...)` + `resume_agent_turn(...)`

**EDIT** `fsr_playbooks/llm/__init__.py` — export `run_agent_turn`,
`resume_agent_turn`, `TurnResult`

**EDIT** `fsr_playbooks/llm/anthropic_provider.py` (~5 LoC) — accept optional
`approval_gateway`, route stashes through it

**EDIT** `web/backend/routes/chat.py` — shrinks from 622 → ~350 LoC:
- `chat()` becomes: build inputs → `run_agent_turn(on_event=yield_sse_frame, history_sink=BackendHistoryAdapter())` → ladder eval → done
- `resolve_approval()` becomes: peek/pop/step-up validation → `resume_agent_turn(on_event=yield_sse_frame, ...)` → done

**NEW** `web/backend/_history_sink.py` (~30 LoC) — adapter implementing
`HistorySink` over `backend.history` functions

**EDIT** `fsr-playbook-builder/operations.py` — `chat_turn` and
`chat_resume` become real:
```python
async def chat_turn(config, params):
    _check_health(config)
    provider = _build_provider(config)
    storage = default_storage()
    gateway = PersistedApprovalGateway(storage)
    provider.approval_gateway = gateway   # or pass via build_provider
    messages = [Message(role="user", content=params["intent"])]
    if prior := params.get("messages"):
        messages = _wire_to_messages(prior) + messages
    result = await run_agent_turn(
        provider=provider,
        system=_build_system_prompt(),
        messages=messages,
        history_sink=storage,
        turn_for_history=_next_turn(storage, params["session_id"]),
    )
    return {
        "turn_id": result.session_id,
        "transcript": [_event_to_wire(e) for e in result.transcript],
        "stop_reason": result.stop_reason,
    }
```

## Risks + mitigations

1. **`seq_in_turn` collision rule** (chat.py L379-388). The comment
   warns that resetting `seq` on each UsageEvent caused later
   round-trips to overwrite earlier ones via INSERT OR REPLACE. The
   lifted function must preserve the "don't reset" invariant and ship
   with a regression test that runs a 2-round-trip turn and asserts
   N rows persisted, not just round 2's rows.
2. **`tags` mutation through provider's reference**. The provider keeps
   a reference to the same dict; mutating it during stream consumption
   is what makes subsequent UsageEvents carry the playbook_collection
   tag. Tests must verify the mutation is preserved end-to-end.
3. **First-UsageEvent `session_id` capture + retroactive user-message
   logging**. Today's loop writes the request's user messages to
   chat_messages on the first UsageEvent (using negative `seq` so
   they sort before assistant text). This is load-bearing for replay
   correctness and must be preserved.
4. **Final flush on stream end without UsageEvent**. The current code
   has a `_flush_assistant_text()` in the outer try block after the
   stream finishes. Without it, an ErrorEvent-only stream loses any
   trailing assistant text.
5. **Provider `resume_fn = getattr(provider, "resume", None)` fallback**.
   Some providers (`fake_provider` in tests, possibly `lmstudio_provider`)
   don't implement `resume`. The lifted function must mirror the route's
   defensive check and return a synthetic ErrorEvent rather than
   raising AttributeError.
6. **Test surface**. Today web/tests/test_chat.py exercises the loop end-
   to-end via the FastAPI client. After the lift those tests are still
   the right end-to-end check. Additionally add fsr_playbooks-level tests
   that use `fake_provider` to drive `run_agent_turn` directly — faster
   feedback, no FastAPI startup needed.

## Estimated work

| step                                                        | est. |
|-------------------------------------------------------------|------|
| Write `run_turn.py` + unit tests with fake_provider         | 90m  |
| Wire `approval_gateway` into AnthropicProvider              | 20m  |
| Refactor `chat.py::chat()` to use `run_agent_turn`          | 60m  |
| Refactor `chat.py::resolve_approval()` to use `resume_agent_turn` | 30m |
| Add web/backend `_history_sink.py` adapter                  | 15m  |
| Verify web/tests/test_chat.py + test_approvals.py still pass | 30m |
| Wire connector chat_turn + chat_resume + tests              | 60m  |
| Buffer for regression chases                                | 60m  |
| **Total**                                                   | **~6h** |

Half a day of focused work. Self-contained enough to do in one branch.

## Branch / commit shape

Branch: `agent-loop-lift`
Suggested commit sequence:
1. Add `run_turn.py` + tests (no other changes) — easy to review in isolation
2. Wire `approval_gateway` into AnthropicProvider — surgical
3. Refactor chat.py — biggest diff; validate web tests stay green
4. Implement connector chat_turn / chat_resume + tests
5. Update FSR_CONNECTOR_PLAN.md to mark Phase 3 agent-loop work complete

## Out of scope

- Streaming the connector's chat_turn back to the widget over SSE.
  The 0.1 cut returns the whole transcript on completion; streaming is
  a later widget concern that can use the same `on_event` hook.
- Migrating `_yaml_tags` / `_detect_intent` / ladder eval into fsr_playbooks.
  They're chat-UX heuristics that the connector may want to deviate
  from (different intent space, different ladder set). Keep them in
  the consumer for now.
