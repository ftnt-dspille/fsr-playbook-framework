"""OpenAI provider -- the Chat Completions wire for the shared agent loop.

The loop itself (tool dispatch, approvals, guards, wrap-up rounds) lives in
`agent_loop.py` and is the same for every provider. This module supplies only
what is OpenAI-specific: tool calls arrive as `tool_calls` deltas keyed by
`index` with `function.arguments` streamed as JSON-string fragments, each tool
result is its OWN `{"role": "tool", ...}` message, and `finish_reason` uses a
different vocabulary from the connector's stop_reason contract.

Works against OpenAI proper by default; `base_url` drives any
OpenAI-compatible endpoint (vLLM, Together, Groq, LM Studio, the Frank
gateway). The `lmstudio` provider name is this class with LM Studio's local
defaults (see `lmstudio()`).
"""
from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from typing import Any

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
from ._loop_helpers import DEFAULT_MAX_OUTPUT_TOKENS, unexecuted_tool_calls_note
from .agent_loop import (
    ASSESSMENT_DIRECTIVE,
    BAD_ARGS_KEY,
    BUILD_PROGRESS_DIRECTIVE,
    DELIVERY_DIRECTIVE,
    Round,
    RoundUsage,
    ToolCall,
    ToolOutcome,
    is_error_result,
    parse_tool_arguments,
    resume_loop,
    run_loop,
    stringify,
)
from .provider import CapabilityMixin, DroppedCall, Event, Message, ProviderCapabilities
from .replay import blocks_to_openai, is_block_content
from .tools import openai_tools

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

# LM Studio's local server. It requires *something* in the api_key field but
# never validates it.
LMSTUDIO_BASE_URL = os.environ.get("STUDIO_LMSTUDIO_BASE_URL", "http://localhost:1234/v1")
LMSTUDIO_MODEL = os.environ.get("STUDIO_LMSTUDIO_MODEL", "")
LMSTUDIO_API_KEY = os.environ.get("STUDIO_LMSTUDIO_API_KEY", "lm-studio")

# Kept under their old names for callers that imported them from here.
_BAD_ARGS_KEY = BAD_ARGS_KEY
_ASSESSMENT_DIRECTIVE = ASSESSMENT_DIRECTIVE
_DELIVERY_DIRECTIVE = DELIVERY_DIRECTIVE
_BUILD_PROGRESS_DIRECTIVE = BUILD_PROGRESS_DIRECTIVE
_is_error_result = is_error_result
_stringify = stringify

#: Where an unparseable tool-call argument string is kept in HISTORY.
_UNPARSED_ARGS_KEY = "__unparsed_arguments__"


def _history_safe_arguments(raw: str) -> str:
    """The `arguments` string to replay in history for one tool call.

    The model occasionally streams arguments that are not valid JSON. The tool
    already gets a `_BAD_ARGS_KEY` error for that, so the model can repair it;
    but replaying the raw string in the NEXT request makes an OpenAI-compatible
    gateway reject the whole history ("Assistant tool call function.arguments
    must be valid JSON", HTTP 400), and the turn dies instead of repairing.
    Keep what the model sent, wrapped as valid JSON, so it can still see its
    own mistake next to the error.
    """
    raw = raw or "{}"
    try:
        json.loads(raw)
        return raw
    except Exception:  # noqa: BLE001
        return json.dumps({_UNPARSED_ARGS_KEY: raw[:4000]})

_FINISH_TO_CONTRACT = {
    "stop": "end_turn",
    # The OUTPUT-TOKEN CAP, and nothing else. This used to map onto
    # "max_turns", a name that reads as the tool-loop budget -- so a build turn
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


def _max_tokens_param(model: str, value: int) -> dict[str, int]:
    """The output-cap kwarg for `model`, under its correct name.

    GPT-5 and later reject `max_tokens` outright ("Unsupported parameter:
    'max_tokens' is not supported with this model. Use 'max_completion_tokens'
    instead.", HTTP 400) -- so sending the old name makes every call to those
    models fail. Older models (gpt-4o, gpt-4.1*) accept `max_tokens`; some do not
    yet accept the new name, so we cannot simply always send the new one.
    """
    name = "max_completion_tokens" if _is_gpt5_plus(model) else "max_tokens"
    return {name: value}


def _is_gpt5_plus(model: str) -> bool:
    """True for GPT-5+ ids (``gpt-5``, ``gpt-5.4-nano``, ``gpt-5.6-terra``, …).

    Deliberately prefix-based rather than an allow-list: OpenAI ships new
    point-releases and named variants continuously, and an allow-list would
    silently fall back to the old parameter name -- i.e. a 400 on every call --
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
    (the Responses API uses ``input_tokens_details`` -- we are on the former).
    Caching is automatic for prompts >=1024 tokens and needs no opt-in; cache
    reads bill at 90% off. The value is a SUBSET of ``prompt_tokens``, not an
    addition to it, so cost math must subtract before applying the discount.

    There is no cache-WRITE counterpart on the models we default to: writes are
    free and unreported pre-GPT-5.6. GPT-5.6+ does report ``cache_write_tokens``
    (billed 1.25x input) -- wire that up here if we ever default to one.
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
    list[dict]; they pass through verbatim -- each block carries its own
    `role`, so the Message.role on a list-content carrier is ignored."""
    out: list[dict[str, Any]] = [{"role": "system", "content": system}]
    for m in messages:
        if isinstance(m.content, str):
            out.append({"role": m.role, "content": m.content})
        elif is_block_content(m.content):
            # Replayed history in the neutral block form -- see llm/replay.py.
            out.extend(blocks_to_openai(m.role, m.content))
        else:
            # Already an OpenAI-shaped dict (assistant w/ tool_calls, or
            # tool result message). Trust it.
            for block in m.content:
                out.append(block)  # type: ignore[arg-type]
    return out


def _normalize_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Coerce a tool list into the OpenAI Chat Completions shape
    (`{type:"function", function:{name, description, parameters}}`).

    The connector advertises an intent tool-slice using the Anthropic shape
    (`{name, description, input_schema}`) regardless of the active provider --
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



# OpenAI's `finish_reason` vocabulary differs from the connector's stop_reason
# contract (Anthropic already returns "end_turn"); see _FINISH_TO_CONTRACT.


class _OpenAITurn:
    """One stream's Chat Completions history and the requests that read it."""

    def __init__(self, provider: OpenAIProvider, system: str,
                 messages: list[Message], tools: list[dict[str, Any]] | None) -> None:
        self.p = provider
        self.history = _to_openai_messages(system, messages)
        # Own the wire format: openai_tools() when the caller passed nothing,
        # else coerce whatever shape we were handed (the connector advertises
        # Anthropic-shaped tools) into the OpenAI envelope. `is not None`: the
        # budget-ask "deliver" path passes [] to force a no-research turn.
        self.plain_tools = _normalize_tools(tools) if tools is not None else openai_tools()
        self.allowed_names = {
            n for t in self.plain_tools
            if (n := (t.get("function") or {}).get("name") or t.get("name"))
        }
        self._round = 0

    # -- reading ----------------------------------------------------------

    def before_round(self) -> None:
        self._round += 1

    def history_chars(self) -> int:
        try:
            return len(json.dumps(self.history, default=str))
        except Exception:
            return 0

    def history_dicts(self) -> list[dict[str, Any]]:
        return self.history

    def has_tool(self, name: str) -> bool:
        return self._schema(name) is not None

    def _schema(self, name: str) -> dict[str, Any] | None:
        return next((t for t in self.plain_tools
                     if (t.get("function") or {}).get("name") == name), None)

    def usage_extra(self) -> dict[str, Any]:
        return {}

    # -- requests ---------------------------------------------------------

    async def stream_round(self) -> AsyncIterator[tuple[str, Any]]:
        """Stream one round: ("text", delta)* then ("final", Round)."""
        p = self.p
        text = ""
        slots: dict[int, dict[str, str]] = {}
        finish: str | None = None
        usage = RoundUsage()
        stream = await p._client.chat.completions.create(
            model=p.model,
            messages=self.history,
            tools=self.plain_tools,
            stream=True,
            **_max_tokens_param(p.model, p.max_output_tokens),
            stream_options={"include_usage": True},
        )
        async for chunk in stream:
            if chunk.usage is not None:
                usage = RoundUsage(chunk.usage.prompt_tokens or 0,
                                   chunk.usage.completion_tokens or 0,
                                   _cached_tokens(chunk.usage), 0)
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            delta = choice.delta
            if delta and delta.content:
                text += delta.content
                yield ("text", delta.content)
            if delta and delta.tool_calls:
                for tc in delta.tool_calls:
                    slot = slots.setdefault(tc.index, {"id": "", "name": "", "args": ""})
                    if tc.id:
                        slot["id"] = tc.id
                    if tc.function:
                        if tc.function.name:
                            slot["name"] = tc.function.name
                        if tc.function.arguments:
                            slot["args"] += tc.function.arguments
            if choice.finish_reason:
                finish = choice.finish_reason
        yield ("final", self._parse(text, slots, finish, usage))

    def _parse(self, text: str, slots: dict[int, dict[str, str]],
               finish: str | None, usage: RoundUsage) -> Round:
        msg: dict[str, Any] = {"role": "assistant", "content": text or None}
        calls: list[ToolCall] = []
        wire_calls: list[dict[str, Any]] = []
        for idx in sorted(slots):
            slot = slots[idx]
            call_id = slot["id"] or f"call_{id(self):x}_{self._round}_{idx}"
            wire_calls.append({
                "id": call_id, "type": "function",
                "function": {"name": slot["name"],
                             "arguments": _history_safe_arguments(slot["args"])},
            })
            calls.append(ToolCall(call_id, slot["name"], parse_tool_arguments(slot["args"])))
        # Only a `tool_calls` finish executes its calls; any other stop
        # (`length` above all -- cut off mid-arguments) drops them, because
        # replaying calls that never ran makes the next request a 400.
        dropped: list[DroppedCall] = []
        if wire_calls and finish != "tool_calls":
            dropped = [DroppedCall(name=s["name"] or "", arg_chars=len(s["args"]),
                                   tail=s["args"][-200:]) for _i, s in sorted(slots.items())]
            if not text:
                msg["content"] = unexecuted_tool_calls_note(
                    finish, [c["function"]["name"] for c in wire_calls])
            wire_calls, calls = [], []
        if wire_calls:
            msg["tool_calls"] = wire_calls
        # An empty reply replayed as {"content": null} makes the next request
        # a 400 (live: gpt-5.4-mini answered a delivered verdict with nothing).
        assistant = msg if (msg["content"] or wire_calls) else None
        return Round(text=text, tool_calls=calls, stop_reason=finish or "",
                     usage=usage, dropped_calls=dropped, assistant=assistant)

    async def wrapup_round(self, max_tokens: int) -> AsyncIterator[tuple[str, Any]]:
        p = self.p
        usage = RoundUsage()
        stream = await p._client.chat.completions.create(
            model=p.model,
            messages=self.history,
            stream=True,
            # The normal ceiling, not a small one: a reasoning model spends its
            # reasoning out of this budget, and at 512 a wrap-up came back with
            # every token spent and no text (Frank sweep).
            **_max_tokens_param(p.model, max_tokens),
            stream_options={"include_usage": True},
        )
        async for chunk in stream:
            if chunk.usage is not None:
                usage = RoundUsage(chunk.usage.prompt_tokens or 0,
                                   chunk.usage.completion_tokens or 0,
                                   _cached_tokens(chunk.usage), 0)
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta and delta.content:
                yield ("text", delta.content)
        yield ("final", usage)

    async def forced_call(self, name: str) -> ToolCall | None:
        p = self.p
        resp = await p._client.chat.completions.create(
            model=p.model, messages=self.history,
            tools=[self._schema(name)],
            tool_choice={"type": "function", "function": {"name": name}},
            **_max_tokens_param(p.model, p.max_output_tokens),
        )
        msg = resp.choices[0].message
        if not msg.tool_calls:
            return None
        tc = msg.tool_calls[0]
        try:
            args = json.loads(tc.function.arguments or "{}")
        except Exception:
            args = {}
        return ToolCall(tc.id or "", name, args if isinstance(args, dict) else {})

    # -- history ----------------------------------------------------------

    def append_assistant(self, rnd: Round) -> None:
        if rnd.assistant is not None:
            self.history.append(rnd.assistant)

    def append_user(self, text: str) -> None:
        self.history.append({"role": "user", "content": text})

    def append_tool_call(self, call: ToolCall) -> None:
        self.history.append({"role": "assistant", "content": None, "tool_calls": [{
            "id": call.call_id, "type": "function",
            "function": {"name": call.name, "arguments": json.dumps(call.args)}}]})

    def result_wire(self, outcome: ToolOutcome) -> dict[str, Any]:
        return {"role": "tool", "tool_call_id": outcome.call_id, "content": outcome.content}

    def append_tool_results(self, outcomes: list[ToolOutcome], *,
                            note: str | None = None, note_role: str = "user") -> None:
        self.history.extend(self.result_wire(o) for o in outcomes)
        if note:
            self.history.append({"role": note_role, "content": note})

    def snapshot(self) -> list[Any]:
        # Without the leading system message: stream() re-prepends it.
        return list(self.history[1:])


class OpenAIProvider(CapabilityMixin):
    name = "openai"
    label = "OpenAI"
    #: Sends no reasoning/budget parameters (it also fronts Frank/GLM, whose
    #: endpoint exposes a different set), so the host emulates everything.
    capabilities = ProviderCapabilities()

    # Class-level default so an instance built without __init__ still has a cap.
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
        # max_retries=5 (SDK default 2): the SDK backs off on 429/5xx and only
        # successful generations are billed.
        self._client = client or AsyncOpenAI(
            base_url=self.base_url,
            api_key=api_key or os.environ.get("OPENAI_API_KEY"),
            timeout=120.0,
            max_retries=5,
        )
        # ApprovalGateway impl. None -> the module singleton in `approvals`;
        # the connector passes a persisted one so paused turns survive restarts.
        self._approval_gateway = approval_gateway

    # -- the loop's seam (see agent_loop) ----------------------------------

    def precheck(self) -> str | None:
        return None if self.model else "No OpenAI model selected -- set one in Settings."

    def open_turn(self, *, system: str, messages: list[Message],
                  tools: list[dict[str, Any]] | None, turn_budget: int) -> _OpenAITurn:
        return _OpenAITurn(self, system, messages, tools)

    def rehydrate(self, suspended: _approvals.SuspendedSession,
                  outcomes: list[ToolOutcome]) -> list[Message]:
        # Snapshot dicts, then one role:tool message per call of the suspended
        # assistant message, carried as a single list-content Message so
        # `_to_openai_messages` lays them out in order.
        carried: list[dict[str, Any]] = (
            list(suspended.history_snapshot)
            + list(suspended.prior_tool_result_blocks)
            + [{"role": "tool", "tool_call_id": o.call_id, "content": o.content}
               for o in outcomes])
        return [Message(role="user", content=carried)]

    def contract_stop(self, raw: str | None) -> str:
        return _contract_stop_reason(raw)

    def friendly_error(self, exc: Exception) -> str:
        return _friendly_error(exc, self.base_url)

    # -- LLMProvider -------------------------------------------------------

    async def stream(
        self,
        *,
        system: str,
        messages: list[Message],
        tools: list[dict[str, Any]],
        tags: dict[str, Any] | None = None,
        case_state: Any = None,
        max_tool_turns: int | None = None,
    ) -> AsyncIterator[Event]:
        async for ev in run_loop(self, system=system, messages=messages, tools=tools,
                                 tags=tags, case_state=case_state,
                                 max_tool_turns=max_tool_turns):
            yield ev

    async def resume(self, *, suspended: _approvals.SuspendedSession,
                     decision: str) -> AsyncIterator[Event]:
        async for ev in resume_loop(self, suspended=suspended, decision=decision):
            yield ev


def lmstudio(*, base_url: str | None = None, api_key: str | None = None,
             model: str | None = None, **kw: Any) -> OpenAIProvider:
    """LM Studio's local server is plain OpenAI-compatible: this is the OpenAI
    provider with LM Studio's defaults."""
    p = OpenAIProvider(base_url=base_url or LMSTUDIO_BASE_URL,
                       api_key=api_key or LMSTUDIO_API_KEY,
                       model=model or LMSTUDIO_MODEL or None, **kw)
    p.name = "lmstudio"
    p.label = "LM Studio"
    if not model and not LMSTUDIO_MODEL:
        p.model = ""   # LM Studio serves whatever is loaded; precheck asks for one
    return p


def _friendly_error(e: Exception, base_url: str) -> str:
    if isinstance(e, AuthenticationError):
        return "OpenAI authentication failed -- check the API key."
    if isinstance(e, PermissionDeniedError):
        return "The OpenAI API key lacks permission for this model."
    if isinstance(e, RateLimitError):
        return "You've hit OpenAI's rate limit. Wait a moment and try again."
    if isinstance(e, APITimeoutError):
        return "The request to OpenAI timed out. Try again, or shorten the prompt."
    if isinstance(e, APIConnectionError):
        return (f"Could not reach the OpenAI endpoint at {base_url} -- check "
                f"network connectivity and the base URL.")
    if isinstance(e, BadRequestError):
        return f"OpenAI rejected the request: {getattr(e, 'message', str(e))[:200]}"
    if isinstance(e, APIStatusError):
        status = getattr(e, "status_code", "?")
        return f"OpenAI returned HTTP {status}."
    return f"{type(e).__name__}: {e}"
