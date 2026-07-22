"""OpenAI provider — streaming chat with tool use + full HITL parity.

This is the OpenAI Chat Completions sibling of `AnthropicProvider`. It
speaks the same `LLMProvider` protocol (TextEvent / ToolUseEvent /
ToolResultEvent / ApprovalRequestEvent / UsageEvent / DoneEvent) and
carries the SAME human-in-the-loop machinery the connector relies on:

- tier resolution via `tools._resolve_tier`
- parallel read-only dispatch up to the first tier-3+ call
- approval suspension: a `pending_approval` envelope stashes a
  `SuspendedSession` through the injected ApprovalGateway and emits an
  ApprovalRequestEvent + DoneEvent("pending_approval")
- `resume()` re-dispatches the approved call (or synthesizes a denial)
  and re-enters the loop
- the repeated-error guard, intent-slice guard, self-repair, and the
  P1 forced-assessment / max-tool-turns wrap-up rounds

The only thing that differs from AnthropicProvider is the wire format:
OpenAI delivers tool calls as `tool_calls` deltas keyed by `index` with
`function.arguments` arriving as fragmented JSON-string chunks, and each
tool result is its OWN `{"role": "tool", ...}` message rather than a
block inside a user turn. The HITL semantics are identical.

Works against OpenAI proper by default; `base_url` override lets it
drive any OpenAI-compatible endpoint (vLLM, Together, Groq, …). For LM
Studio specifically, prefer `LMStudioProvider` — it defaults to the
local server and a permissive api_key. The two share no code so a change
to one can't regress the other.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
import uuid as _uuid
from typing import Any, AsyncIterator

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
    BadRequestError,
    PermissionDeniedError,
    RateLimitError,
)

from . import approvals as _approvals
from ._loop_helpers import (
    DEFAULT_MAX_OUTPUT_TOKENS,
    MAX_PARALLEL_TOOLS,
    MAX_SELF_REPAIR_TURNS,
    MAX_TOOL_TURNS,
    STREAM_TIMEOUT_SECS,
    EnhanceDeliveryGuard,
    TriageDiscipline,
    _ENHANCE_OFFER_TOOL,
    compile_errors as _compile_errors,
    drain_with_idle_timeout,
    extract_yaml_block as _extract_yaml_block,
)
from .provider import (
    ApprovalRequestEvent,
    DoneEvent,
    ErrorEvent,
    Event,
    Message,
    TextEvent,
    ToolCallUsage,
    ToolResultEvent,
    ToolUseEvent,
    UsageEvent,
)
from .tools import _resolve_tier as _tier_for, dispatch, openai_tools


DEFAULT_BASE_URL = (
    os.environ.get("OPENAI_ENDPOINT")
    or os.environ.get("STUDIO_OPENAI_BASE_URL")
    or "https://api.openai.com/v1"
)
DEFAULT_MODEL = (
    os.environ.get("OPENAI_MODEL")
    or os.environ.get("STUDIO_OPENAI_MODEL")
    or "gpt-4o"
)


# OpenAI's chat-completions `finish_reason` vocabulary differs from the
# connector's stop_reason contract (which the AnthropicProvider satisfies
# natively, since Anthropic already returns "end_turn"). Without this mapping
# the OpenAI path leaks the raw "stop"/"length" tokens, so a normal turn ends
# on stop_reason="stop" instead of the contract's "end_turn" — silently
# breaking every consumer keyed on the contract (the live chat test T3, etc.).
# Map the OpenAI tokens onto the same vocabulary Anthropic emits.
_FINISH_TO_CONTRACT = {
    "stop": "end_turn",
    # The OUTPUT-TOKEN CAP, and nothing else. This used to map onto
    # "max_turns", a name that reads as the tool-loop budget — so a build turn
    # truncated mid-playbook looked like the benign "ran out of steps, send
    # another message" stop instead of a half-written document. The tool-loop
    # budget has always had its OWN reason (`max_tool_turns`, emitted by the
    # loop below), so "max_turns" never meant anything but the token cap; the
    # collision was purely in the name. Consumers that must treat a cut-off
    # turn as incomplete (the widget's fence guard, the T1 harness's
    # DriveError) already accept "max_tokens" alongside the old token.
    "length": "max_tokens",
    "content_filter": "error",
    "function_call": "end_turn",
    "tool_calls": "end_turn",  # only reached when the tool loop already closed
}


def _contract_stop_reason(finish_reason: str | None) -> str:
    """Normalize an OpenAI finish_reason to the connector stop_reason contract.

    A missing/empty finish_reason means a clean completion → "end_turn"."""
    if not finish_reason:
        return "end_turn"
    return _FINISH_TO_CONTRACT.get(finish_reason, finish_reason)


# Mirrors AnthropicProvider._ASSESSMENT_DIRECTIVE — the P1 forced written
# assessment when a turn ran tools but closed with no narrative text.
_ASSESSMENT_DIRECTIVE = (
    "You ran tools but did not write anything back to the analyst. Stop "
    "calling tools. In a short written assessment, tell the analyst: "
    "(1) what you found, (2) your severity / disposition verdict, and "
    "(3) the single recommended next action. Be concise and do not call tools."
)

# Forced enhance-delivery round. The turn verified an edit (ready_to_push) but
# ended without calling `emit_enhancement_offer` — usually narrating the call
# instead of making it. We pin `tool_choice` to the offer tool so the CALL is
# structural, and override `verified_id` afterward so a forced round can only
# deliver the blessed bytes. Directive is belt-and-suspenders for the summary.
_DELIVERY_DIRECTIVE = (
    "You verified an edit to the open playbook and it is ready to apply, but "
    "you have not delivered it. Call `emit_enhancement_offer` now with "
    "verified_id {vid!r} to apply it — a written description is NOT a "
    "substitute for the call. Write the `summary` as one or two plain-English "
    "lines describing what the edit changes."
)


def _max_tokens_param(model: str, value: int) -> dict[str, int]:
    """The output-cap kwarg for `model`, under its correct name.

    GPT-5 and later reject `max_tokens` outright ("Unsupported parameter:
    'max_tokens' is not supported with this model. Use 'max_completion_tokens'
    instead.", HTTP 400) — so sending the old name makes every call to those
    models fail. Older models (gpt-4o, gpt-4.1*) accept `max_tokens`; some do not
    yet accept the new name, so we cannot simply always send the new one.
    """
    name = "max_completion_tokens" if _is_gpt5_plus(model) else "max_tokens"
    return {name: value}


def _is_gpt5_plus(model: str) -> bool:
    """True for GPT-5+ ids (``gpt-5``, ``gpt-5.4-nano``, ``gpt-5.6-terra``, …).

    Deliberately prefix-based rather than an allow-list: OpenAI ships new
    point-releases and named variants continuously, and an allow-list would
    silently fall back to the old parameter name — i.e. a 400 on every call —
    for any id we hadn't enumerated yet. Gateways serving non-OpenAI models
    (GLM via the frank endpoint) don't match and keep the legacy name.
    """
    m = (model or "").lower().lstrip("openai/")
    if not m.startswith("gpt-"):
        return False
    ver = m[4:].split("-")[0]           # "5.4" from "gpt-5.4-nano"
    try:
        return float(ver) >= 5
    except ValueError:
        return False


def _cached_tokens(usage: Any) -> int:
    """Tokens served from OpenAI's prompt cache, or 0 if unreported.

    Chat Completions reports this at ``usage.prompt_tokens_details.cached_tokens``
    (the Responses API uses ``input_tokens_details`` — we are on the former).
    Caching is automatic for prompts >=1024 tokens and needs no opt-in; cache
    reads bill at 90% off. The value is a SUBSET of ``prompt_tokens``, not an
    addition to it, so cost math must subtract before applying the discount.

    There is no cache-WRITE counterpart on the models we default to: writes are
    free and unreported pre-GPT-5.6. GPT-5.6+ does report ``cache_write_tokens``
    (billed 1.25x input) — wire that up here if we ever default to one.
    """
    try:
        return getattr(usage.prompt_tokens_details, "cached_tokens", 0) or 0
    except Exception:
        return 0


def _to_openai_messages(system: str, messages: list[Message]) -> list[dict[str, Any]]:
    """Translate normalized Messages into OpenAI chat shape.

    Plain-string user/assistant turns map one-to-one. Internal turns we
    append during the loop (assistant w/ tool_calls, tool result
    messages) are already OpenAI-shaped dicts carried as Message.content
    list[dict]; they pass through verbatim — each block carries its own
    `role`, so the Message.role on a list-content carrier is ignored."""
    out: list[dict[str, Any]] = [{"role": "system", "content": system}]
    for m in messages:
        if isinstance(m.content, str):
            out.append({"role": m.role, "content": m.content})
        else:
            for block in m.content:
                out.append(block)  # type: ignore[arg-type]
    return out


def _normalize_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Coerce a tool list into the OpenAI Chat Completions shape
    (`{type:"function", function:{name, description, parameters}}`).

    The connector advertises an intent tool-slice using the Anthropic shape
    (`{name, description, input_schema}`) regardless of the active provider —
    so a triage turn reaches us with Anthropic-shaped tools and OpenAI 400s
    with "Missing required parameter: 'tools[0].type'". We own our wire
    format: accept either shape and convert. Already-OpenAI tools pass
    through untouched; entries without a resolvable name are dropped."""
    out: list[dict[str, Any]] = []
    for t in tools or []:
        if not isinstance(t, dict):
            continue
        if t.get("type") == "function" and isinstance(t.get("function"), dict):
            out.append(t)
            continue
        name = t.get("name")
        if not name:
            continue
        out.append({
            "type": "function",
            "function": {
                "name": name,
                "description": t.get("description", ""),
                "parameters": (t.get("input_schema") or t.get("parameters")
                               or {"type": "object", "properties": {}}),
            },
        })
    return out


class OpenAIProvider:
    name = "openai"

    # Class-level default so the loop reads a sane cap even on an instance
    # built without __init__ (tests use `__new__` to drive `_pump` directly).
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        client: AsyncOpenAI | None = None,
        approval_gateway: Any = None,
        max_output_tokens: int | None = None,
    ):
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self.api_key = api_key
        self.model = model or DEFAULT_MODEL
        # Overridable so a deployment pinned to a model with a lower output
        # limit can lower it without a release. See DEFAULT_MAX_OUTPUT_TOKENS.
        self.max_output_tokens = max_output_tokens or DEFAULT_MAX_OUTPUT_TOKENS
        # max_retries=5 (SDK default is 2). Same rationale as Anthropic:
        # the SDK exponentially backs off on 429/5xx and only successful
        # generations are billed, so a higher ceiling is robust at no cost.
        self._client = client or AsyncOpenAI(
            base_url=self.base_url,
            api_key=api_key or os.environ.get("OPENAI_API_KEY"),
            timeout=120.0,
            max_retries=5,
        )
        # ApprovalGateway impl (fsr_playbooks.protocols.ApprovalGateway). None →
        # the module-level singleton in `fsr_playbooks.llm.approvals` (web
        # backend default). The connector passes a PersistedApprovalGateway
        # so paused HITL turns survive worker restarts.
        self._approval_gateway = approval_gateway

    # -- resume ------------------------------------------------------------

    async def resume(
        self,
        *,
        suspended: "_approvals.SuspendedSession",
        decision: str,  # "approve" | "deny"
    ) -> AsyncIterator[Event]:
        """Resume a turn suspended on a pending tier-3+ approval.

        OpenAI form of AnthropicProvider.resume: the assistant turn (with
        its `tool_calls`) already lives in `history_snapshot`. We rebuild
        one `{"role": "tool", …}` message per tool_use the model emitted —
        the prior results that completed before the gate, the resolved
        pending call (re-dispatched on approve / synthesized denial on
        deny), and `superseded_by_approval` placeholders for calls that
        hadn't run yet — then re-enter `stream()`."""
        # Phase 3.1 HMAC binding check — fail closed on tamper / lost secret.
        if not _approvals.verify(suspended):
            yield ErrorEvent(
                message="Approval binding check failed — the suspended action "
                        "could not be verified and was not executed. Re-issue "
                        "the request."
            )
            yield DoneEvent(stop_reason="approval_unverified")
            return

        if decision == "approve":
            resolved = dispatch(
                suspended.tool, {**suspended.args, "_approved": True},
                _internal=True,
            )
        else:
            resolved = {"ok": False, "code": "user_denied",
                        "reason": "User denied the action."}

        # Surface the resolved result inline with the approval card.
        yield ToolResultEvent(call_id=suspended.tool_use_id, result=resolved)

        # prior_tool_result_blocks are already OpenAI `role:tool` dicts.
        tool_messages: list[dict[str, Any]] = list(
            suspended.prior_tool_result_blocks
        )
        tool_messages.append({
            "role": "tool",
            "tool_call_id": suspended.tool_use_id,
            "content": _stringify(resolved),
        })
        for skipped in suspended.remaining_tool_calls:
            tool_messages.append({
                "role": "tool",
                "tool_call_id": skipped.call_id,
                "content": "{\"ok\": false, \"code\": \"superseded_by_approval\"}",
            })

        # history_snapshot is the OpenAI history WITHOUT the system message
        # (stream() re-prepends it). Carry the whole thing — snapshot dicts
        # then the rebuilt tool messages — as a single list-content Message
        # so `_to_openai_messages` lays them out in order.
        carried: list[dict[str, Any]] = list(suspended.history_snapshot) + tool_messages
        rehydrated = [Message(role="user", content=carried)]

        async for ev in self.stream(
            system=suspended.system,
            messages=rehydrated,
            tools=[],
            tags=suspended.tags,
        ):
            yield ev

    # -- wrap-up round -----------------------------------------------------

    async def _wrapup_call(
        self,
        *,
        history: list[dict[str, Any]],
        directive: str,
        session_id: str,
        turn_idx: int,
        tags: dict[str, Any],
        self_repair_turns: int,
        stop_reason_label: str,
        max_tokens: int = 512,
    ) -> AsyncIterator[Event]:
        """One forced no-tools model round yielding its text + a UsageEvent.

        Shared by the max-tool-turns wrap-up and the P1 forced-assessment
        guarantee. Appends `directive` as a user turn, runs with NO tools,
        and streams the text. Failures are logged and swallowed — the
        caller still emits a terminal DoneEvent so the turn never hangs."""
        history.append({"role": "user", "content": directive})
        try:
            history_chars = len(json.dumps(history, default=str))
        except Exception:
            history_chars = 0
        input_tok = output_tok = cached_tok = 0
        try:
            stream = await self._client.chat.completions.create(
                model=self.model,
                messages=history,
                stream=True,
                **_max_tokens_param(self.model, max_tokens),
                stream_options={"include_usage": True},
            )
            async for chunk in stream:
                if chunk.usage is not None:
                    input_tok = chunk.usage.prompt_tokens or 0
                    output_tok = chunk.usage.completion_tokens or 0
                    cached_tok = _cached_tokens(chunk.usage)
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    yield TextEvent(text=delta.content)
            yield UsageEvent(
                session_id=session_id, turn=turn_idx, model=self.model,
                input_tokens=input_tok, output_tokens=output_tok,
                cache_read=cached_tok, cache_write=0,
                history_chars=history_chars,
                stop_reason=stop_reason_label,
                self_repair_turn=self_repair_turns,
                tool_calls=[], tags=tags,
            )
        except Exception:
            import logging
            logging.exception("%s call failed", stop_reason_label)

    # -- main loop ---------------------------------------------------------

    async def stream(
        self,
        *,
        system: str,
        messages: list[Message],
        tools: list[dict[str, Any]],
        tags: dict[str, Any] | None = None,
        case_state: Any = None,  # CaseState | None, kept as Any to avoid import
    ) -> AsyncIterator[Event]:
        if not self.model:
            yield ErrorEvent(message="No OpenAI model selected — set one in Settings.")
            return

        history = _to_openai_messages(system, messages)
        self_repair_turns = 0
        any_tools_run = False
        assessment_forced = False
        # Enhance mode: guarantees a passing verify is actually delivered via
        # emit_enhancement_offer rather than narrated. Inert unless the offer
        # tool is in the advertised slice (see EnhanceDeliveryGuard).
        _delivery = EnhanceDeliveryGuard()
        session_id = _uuid.uuid4().hex[:8]
        turn_idx = 0
        tags = tags or {}
        # Own the wire format: openai_tools() when the caller passed nothing,
        # else coerce whatever shape we were handed (the connector advertises
        # Anthropic-shaped tools for triage) into the OpenAI envelope.
        tools = _normalize_tools(tools) if tools else openai_tools()

        # Defense-in-depth for the intent tool-slice (see llm/intents.py):
        # dispatch will run ANY tool name, so refuse names the caller didn't
        # advertise. The model only ever sees `allowed_names`; this is a
        # backstop against a stale widget / replayed transcript.
        allowed_names = {
            (t.get("function") or {}).get("name") or t.get("name")
            for t in tools
        }

        # P4 — repeated-error guard. Don't re-run an identical (name, args)
        # call that already failed this turn; return a guard envelope so the
        # model adapts instead of burning budget on the same 400 twice.
        failed_signatures: set[str] = set()
        # Triage discipline (hunt floor + forbidden pivot + call-once) — see
        # _loop_helpers.TriageDiscipline. Fires only on triage tool names.
        # If case_state is provided, pass its investigation to seed counters.
        investigation_state = (
            getattr(case_state, "investigation", None)
            if case_state is not None else None
        )
        # Authoring/build turns lack the triage-only staging tool
        # `emit_action_card`; the hunt-floor gate must not block
        # find_containment_actions DISCOVERY there. Fully in force for triage.
        _authoring = "emit_action_card" not in allowed_names
        _discipline = TriageDiscipline(
            state=investigation_state,
            capabilities=(getattr(case_state, "capabilities", None)
                          if case_state is not None else None),
            authoring=_authoring,
        )

        def _call_signature(nm: str, ar: dict[str, Any]) -> str:
            try:
                return nm + "|" + json.dumps(ar, sort_keys=True, default=str)
            except Exception:
                return nm + "|" + repr(ar)

        def _guarded_dispatch(nm: str, ar: dict[str, Any]) -> Any:
            if nm not in allowed_names:
                return {
                    "ok": False,
                    "error": (
                        f"Tool '{nm}' is not available in this session: the "
                        f"current task intent does not permit it. Not executed."
                    ),
                }
            sig = _call_signature(nm, ar)
            if sig in failed_signatures:
                return {
                    "ok": False,
                    "repeated_call_guard": True,
                    "error": (
                        f"This exact call to `{nm}` already failed earlier this "
                        f"turn and was NOT re-run. Do not retry the identical "
                        f"arguments — change the inputs (e.g. resolve the "
                        f"correct id from the record's sourcedata) or stop and "
                        f"report the blocker in your assessment."
                    ),
                }
            guard = _discipline.evaluate(nm, ar)
            if guard is not None:
                # Terminal guards (forbidden pivot / call-once) can never
                # succeed — register the signature so an identical re-call hits
                # the firmer repeated_call_guard and the model stops retrying.
                # The hunt-floor block is intentionally NOT terminal: that exact
                # call should succeed once investigation has caught up.
                if guard.get("forbidden_pivot_guard") or guard.get("call_once_guard"):
                    failed_signatures.add(sig)
                return guard
            result = dispatch(nm, ar)
            _discipline.note_result(nm, ar, result)
            if _is_error_result(result):
                failed_signatures.add(sig)
            return result

        for _turn in range(MAX_TOOL_TURNS):
            turn_idx += 1
            try:
                history_chars = len(json.dumps(history, default=str))
            except Exception:
                history_chars = 0

            # Stream the round-trip live: yield text deltas as they arrive
            # (so the connector's chat_poll feed shows a live token stream)
            # while accumulating tool-call slots + usage. `_pump` tags text
            # deltas `("text", str)`; on completion it yields one
            # `("final", (tool_buf, finish_reason, input_tok, output_tok))`.
            # `drain_with_idle_timeout` supplies the per-delta inactivity
            # timeout + cancellation (shared across providers).
            async def _pump():
                text_acc = ""
                tool_buf: dict[int, dict[str, Any]] = {}
                finish_reason: str | None = None
                input_tok = output_tok = cached_tok = 0
                stream = await self._client.chat.completions.create(
                    model=self.model,
                    messages=history,
                    tools=tools,
                    stream=True,
                    **_max_tokens_param(self.model, self.max_output_tokens),
                    stream_options={"include_usage": True},
                )
                async for chunk in stream:
                    if chunk.usage is not None:
                        input_tok = chunk.usage.prompt_tokens or 0
                        output_tok = chunk.usage.completion_tokens or 0
                        cached_tok = _cached_tokens(chunk.usage)
                    if not chunk.choices:
                        continue
                    choice = chunk.choices[0]
                    delta = choice.delta
                    if delta and delta.content:
                        text_acc += delta.content
                        yield ("text", delta.content)   # live delta
                    if delta and delta.tool_calls:
                        for tc in delta.tool_calls:
                            slot = tool_buf.setdefault(
                                tc.index, {"id": "", "name": "", "args": ""}
                            )
                            if tc.id:
                                slot["id"] = tc.id
                            if tc.function:
                                if tc.function.name:
                                    slot["name"] = tc.function.name
                                if tc.function.arguments:
                                    slot["args"] += tc.function.arguments
                    if choice.finish_reason:
                        finish_reason = choice.finish_reason
                yield ("final", (text_acc, tool_buf, finish_reason,
                                 input_tok, output_tok, cached_tok))

            text_buf = ""
            tool_buf: dict[int, dict[str, Any]] = {}
            finish_reason = None
            input_tok = output_tok = cached_tok = 0
            try:
                async for _kind, _payload in drain_with_idle_timeout(
                    _pump(), timeout=STREAM_TIMEOUT_SECS
                ):
                    if _kind == "text":
                        yield TextEvent(text=_payload)   # live delta
                    else:  # "final"
                        (text_buf, tool_buf, finish_reason,
                         input_tok, output_tok, cached_tok) = _payload
            except asyncio.TimeoutError:
                import logging
                logging.warning("openai stream timed out after %ss", STREAM_TIMEOUT_SECS)
                yield ErrorEvent(
                    message=f"The request to OpenAI timed out after "
                            f"{STREAM_TIMEOUT_SECS}s. The API may be slow or "
                            f"unreachable — please try again."
                )
                return
            except Exception as e:
                import logging
                logging.exception("openai stream failed")
                yield ErrorEvent(message=_friendly_error(e, self.base_url))
                return

            # Assemble the assistant message and append to history.
            assistant_msg: dict[str, Any] = {"role": "assistant"}
            assistant_msg["content"] = text_buf or None
            tool_calls: list[tuple[str, str, dict[str, Any]]] = []
            tool_calls_for_msg: list[dict[str, Any]] = []
            for idx in sorted(tool_buf.keys()):
                slot = tool_buf[idx]
                call_id = slot["id"] or f"call_{session_id}_{turn_idx}_{idx}"
                raw_args = slot["args"] or "{}"
                try:
                    parsed = json.loads(raw_args)
                    if not isinstance(parsed, dict):
                        parsed = {}
                except Exception:
                    parsed = {}
                tool_calls_for_msg.append({
                    "id": call_id, "type": "function",
                    "function": {"name": slot["name"], "arguments": raw_args},
                })
                tool_calls.append((call_id, slot["name"], parsed))
            if tool_calls_for_msg:
                assistant_msg["tool_calls"] = tool_calls_for_msg
            history.append(assistant_msg)

            tool_call_usage: list[ToolCallUsage] = []

            def _emit_usage(stop_reason: str, *, repair_delta: int = 0):
                return UsageEvent(
                    session_id=session_id, turn=turn_idx, model=self.model,
                    input_tokens=input_tok, output_tokens=output_tok,
                    cache_read=cached_tok, cache_write=0,
                    history_chars=history_chars,
                    stop_reason=stop_reason,
                    self_repair_turn=self_repair_turns - repair_delta,
                    tool_calls=tool_call_usage, tags=tags,
                )

            # Terminal turn (no tool calls) — self-repair, P1 assessment, done.
            if not tool_calls_for_msg or finish_reason != "tool_calls":
                if self_repair_turns < MAX_SELF_REPAIR_TURNS and text_buf:
                    yaml_block = _extract_yaml_block(text_buf)
                    if yaml_block:
                        errors_text = _compile_errors(yaml_block)
                        if errors_text:
                            self_repair_turns += 1
                            history.append({
                                "role": "user",
                                "content": (
                                    "The YAML you just produced doesn't compile. "
                                    "Fix the errors and emit a corrected fenced "
                                    "```yaml block.\n\nErrors:\n" + errors_text
                                ),
                            })
                            yield _emit_usage(finish_reason or "", repair_delta=1)
                            continue

                # Enhance-delivery guard — a verify passed but no offer
                # followed. Force ONE round pinned to emit_enhancement_offer so
                # the delivery is a real tool call, then override verified_id
                # with the blessed handle so the forced call can only apply the
                # bytes the gate actually cleared.
                _vid = _delivery.outstanding(allowed_names)
                if _vid is not None:
                    _delivery.mark_forced()
                    yield _emit_usage("enhance_delivery_forced")
                    offer_schema = next(
                        (t for t in tools
                         if (t.get("function") or {}).get("name")
                         == _ENHANCE_OFFER_TOOL), None)
                    if offer_schema is not None:
                        turn_idx += 1
                        history.append({
                            "role": "user",
                            "content": _DELIVERY_DIRECTIVE.format(vid=_vid),
                        })
                        try:
                            resp = await self._client.chat.completions.create(
                                model=self.model, messages=history,
                                tools=[offer_schema],
                                tool_choice={
                                    "type": "function",
                                    "function": {"name": _ENHANCE_OFFER_TOOL},
                                },
                                **_max_tokens_param(self.model, 512),
                            )
                            msg = resp.choices[0].message
                            raw = (msg.tool_calls[0].function.arguments
                                   if msg.tool_calls else "{}")
                            try:
                                oargs = json.loads(raw) if raw else {}
                            except Exception:
                                oargs = {}
                            if not isinstance(oargs, dict):
                                oargs = {}
                            # The whole point of the guard: never trust a
                            # forced round to carry the right handle.
                            oargs["verified_id"] = _vid
                            call_id = (msg.tool_calls[0].id
                                       if msg.tool_calls else _uuid.uuid4().hex[:8])
                            yield ToolUseEvent(
                                name=_ENHANCE_OFFER_TOOL, arguments=oargs,
                                call_id=call_id,
                                tier=_tier_for(_ENHANCE_OFFER_TOOL, oargs))
                            _t0 = time.perf_counter()
                            oresult = _guarded_dispatch(_ENHANCE_OFFER_TOOL, oargs)
                            _dur = int((time.perf_counter() - _t0) * 1000)
                            yield ToolResultEvent(
                                call_id=call_id, result=oresult, duration_ms=_dur)
                        except Exception:
                            import logging
                            logging.exception("forced enhance delivery failed")
                    yield DoneEvent(stop_reason="end_turn")
                    return

                if not text_buf.strip() and any_tools_run and not assessment_forced:
                    assessment_forced = True
                    yield _emit_usage("assessment_forced")
                    turn_idx += 1
                    async for ev in self._wrapup_call(
                        history=history, directive=_ASSESSMENT_DIRECTIVE,
                        session_id=session_id, turn_idx=turn_idx, tags=tags,
                        self_repair_turns=self_repair_turns,
                        stop_reason_label="assessment_summary",
                    ):
                        yield ev
                    yield DoneEvent(stop_reason=_contract_stop_reason(finish_reason))
                    return

                yield _emit_usage(finish_reason or "")
                yield DoneEvent(stop_reason=_contract_stop_reason(finish_reason))
                return

            # --- tool execution with HITL approval boundary ---------------
            # Parallel read-only dispatch up to the first tier-3+ call; the
            # approval call + everything after route through the sequential
            # suspend path. Mirrors AnthropicProvider §2.8.
            tiers = [_tier_for(name, args) for (_cid, name, args) in tool_calls]
            approval_idx = next(
                (i for i, t in enumerate(tiers) if t >= 3), len(tool_calls)
            )
            parallel_batch = tool_calls[:approval_idx]

            tool_messages: list[dict[str, Any]] = []

            def _record(name: str, args: dict[str, Any], result: Any,
                        duration_ms: int | None = None) -> str:
                content_str = _stringify(result)
                try:
                    args_chars = len(json.dumps(args, default=str))
                except Exception:
                    args_chars = 0
                tool_call_usage.append(ToolCallUsage(
                    name=name, args_chars=args_chars, result_chars=len(content_str),
                    duration_ms=duration_ms,
                ))
                return content_str

            for (call_id, name, args), tier in zip(parallel_batch, tiers):
                yield ToolUseEvent(name=name, arguments=args, call_id=call_id, tier=tier)
            if parallel_batch:
                _sem = asyncio.Semaphore(MAX_PARALLEL_TOOLS)

                async def _run_one(nm: str, ar: dict[str, Any]) -> Any:
                    async with _sem:
                        _t0 = time.perf_counter()
                        res = await asyncio.to_thread(_guarded_dispatch, nm, ar)
                        return res, int((time.perf_counter() - _t0) * 1000)

                batch_results = await asyncio.gather(
                    *[_run_one(name, args) for (_cid, name, args) in parallel_batch]
                )
                for (call_id, name, args), (result, dur_ms) in zip(parallel_batch, batch_results):
                    yield ToolResultEvent(call_id=call_id, result=result, duration_ms=dur_ms)
                    content_str = _record(name, args, result, dur_ms)
                    _delivery.note_result(name, args, result)
                    tool_messages.append({
                        "role": "tool", "tool_call_id": call_id, "content": content_str,
                    })

            pending: ApprovalRequestEvent | None = None
            for i in range(approval_idx, len(tool_calls)):
                call_id, name, args = tool_calls[i]
                yield ToolUseEvent(
                    name=name, arguments=args, call_id=call_id,
                    tier=_tier_for(name, args),
                )
                _t0 = time.perf_counter()
                result = _guarded_dispatch(name, args)
                dur_ms = int((time.perf_counter() - _t0) * 1000)
                if isinstance(result, dict) and result.get("pending_approval"):
                    remaining = list(tool_calls[i + 1:])
                    approval_id = result["approval_id"]
                    # history (incl. the assistant tool_calls turn) is the
                    # snapshot, minus the leading system message — stream()
                    # re-prepends system on resume.
                    suspended_session = _approvals.SuspendedSession(
                        approval_id=approval_id,
                        session_id=session_id,
                        tool=name,
                        tool_use_id=call_id,
                        args=args,
                        tier=int(result.get("tier", 3)),
                        history_snapshot=list(history[1:]),
                        prior_tool_result_blocks=list(tool_messages),
                        remaining_tool_calls=[
                            _approvals.SkippedToolCall(
                                call_id=cid, name=cn, args=ca,
                            )
                            for cid, cn, ca in remaining
                        ],
                        system=system,
                        tags=dict(tags),
                        summary=result.get("summary"),
                    )
                    _approvals.bind(suspended_session)
                    if self._approval_gateway is not None:
                        self._approval_gateway.stash(suspended_session)
                    else:
                        _approvals.stash(suspended_session)
                    pending = ApprovalRequestEvent(
                        approval_id=approval_id,
                        tool_use_id=call_id,
                        tool=name,
                        tier=int(result.get("tier", 3)),
                        preview=result.get("preview") or {},
                        args_hash=result.get("args_hash", ""),
                        summary=result.get("summary"),
                        requires_step_up=bool(result.get("requires_step_up")),
                    )
                    break

                yield ToolResultEvent(call_id=call_id, result=result, duration_ms=dur_ms)
                content_str = _record(name, args, result, dur_ms)
                _delivery.note_result(name, args, result)
                tool_messages.append({
                    "role": "tool", "tool_call_id": call_id, "content": content_str,
                })

            if pending is not None:
                yield pending
                yield _emit_usage("pending_approval")
                yield DoneEvent(stop_reason="pending_approval")
                return

            history.extend(tool_messages)
            any_tools_run = True
            yield _emit_usage(finish_reason or "tool_calls")

        # Tool-turn budget exhausted — one no-tools wrap-up round.
        turn_idx += 1
        async for ev in self._wrapup_call(
            history=history,
            directive=(
                f"You've used the full tool-turn budget ({MAX_TOOL_TURNS} "
                f"rounds) without finishing. Stop calling tools. In 2-4 "
                f"sentences, tell the user: (1) what state the YAML is in "
                f"(valid? warnings? errors?), (2) what specifically is left to "
                f"do, and (3) one concrete next step they can take. Do not "
                f"re-emit the YAML."
            ),
            session_id=session_id, turn_idx=turn_idx, tags=tags,
            self_repair_turns=self_repair_turns,
            stop_reason_label="max_tool_turns_summary",
        ):
            yield ev
        yield DoneEvent(stop_reason="max_tool_turns")


def _is_error_result(result: Any) -> bool:
    return isinstance(result, dict) and (
        result.get("ok") is False or "error" in result)


def _stringify(result: Any) -> str:
    if isinstance(result, str):
        return result
    try:
        return json.dumps(result, default=str)
    except Exception:
        return str(result)


def _friendly_error(e: Exception, base_url: str) -> str:
    if isinstance(e, AuthenticationError):
        return "OpenAI authentication failed — check the API key."
    if isinstance(e, PermissionDeniedError):
        return "The OpenAI API key lacks permission for this model."
    if isinstance(e, RateLimitError):
        return "You've hit OpenAI's rate limit. Wait a moment and try again."
    if isinstance(e, APITimeoutError):
        return "The request to OpenAI timed out. Try again, or shorten the prompt."
    if isinstance(e, APIConnectionError):
        return (f"Could not reach the OpenAI endpoint at {base_url} — check "
                f"network connectivity and the base URL.")
    if isinstance(e, BadRequestError):
        return f"OpenAI rejected the request: {getattr(e, 'message', str(e))[:200]}"
    if isinstance(e, APIStatusError):
        status = getattr(e, "status_code", "?")
        return f"OpenAI returned HTTP {status}."
    return f"{type(e).__name__}: {e}"
