"""Anthropic provider -- the Messages API wire for the shared agent loop.

The loop (tool dispatch, approvals, guards, wrap-up rounds) lives in
`agent_loop.py`. This module supplies what is Anthropic-specific: content
blocks, a tool_result block per call inside one user message, prompt caching
(system + tools prefix, plus a rolling breakpoint on history), and the
model-gated native primitives -- reasoning depth, task budgets, deferred tool
loading and context editing.
"""
from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from typing import Any

try:
    from anthropic import AsyncAnthropic
except ImportError:
    # The SDK isn't installed in every environment (e.g. the FSR connector
    # runtime). Defer the hard failure to AnthropicProvider.__init__ so the
    # module -- and its module-level helpers -- import cleanly without it.
    AsyncAnthropic = None  # type: ignore[assignment,misc]

from . import approvals as _approvals
from ._loop_helpers import DEFAULT_MAX_OUTPUT_TOKENS, unexecuted_tool_calls_note
from ._loop_helpers import shrink_history as _shrink_history
from .agent_loop import (
    ASSESSMENT_DIRECTIVE,
    BUILD_PROGRESS_DIRECTIVE,
    DELIVERY_DIRECTIVE,
    Round,
    RoundUsage,
    ToolCall,
    ToolOutcome,
    is_error_result,
    resume_loop,
    run_loop,
    stringify,
)
from .cache_prefix import prefix_fingerprint as _prefix_fingerprint
from .provider import (
    CapabilityMixin,
    DroppedCall,
    Event,
    Message,
    ProviderCapabilities,
)
from .tools import anthropic_tools

# The agent runs a multi-step tool loop, so the default must be a model that
# can plan across calls. Sonnet 4.5 predates adaptive thinking entirely -- it
# takes no `thinking` / `effort` control at all, so the capability seam has
# nothing to give it. Sonnet 5 is the volume default; callers that want more
# pass `model=` (the connector's config dropdown offers claude-opus-5).
DEFAULT_MODEL = os.environ.get("STUDIO_ANTHROPIC_MODEL", "claude-sonnet-5")

# Kept under their old names for callers that imported them from here.
_ASSESSMENT_DIRECTIVE = ASSESSMENT_DIRECTIVE
_DELIVERY_DIRECTIVE = DELIVERY_DIRECTIVE
_BUILD_PROGRESS_DIRECTIVE = BUILD_PROGRESS_DIRECTIVE
_is_error_result = is_error_result
_stringify = stringify


def _to_anthropic_messages(messages: list[Message]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in messages:
        if isinstance(m.content, str):
            out.append({"role": m.role, "content": m.content})
        else:
            out.append({"role": m.role, "content": m.content})
    return out


def _with_history_breakpoint(msgs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Add a rolling cache breakpoint on the last block of the last message.

    Without this we cache only the (tools + system) prefix -- 2 of the 4
    breakpoints Anthropic allows -- and re-send the whole conversation uncached
    on every iteration. That is the expensive half of an agentic turn: `history`
    grows by an assistant block plus a tool_result block per tool call, so a
    10-tool turn pays full input price on a transcript that is mostly identical
    to the previous request's.

    Anthropic's cache is prefix-based, so a breakpoint at the END of history
    makes each request read everything up to the previous request's breakpoint
    and write only the new increment. Reads bill at 0.1x input; writes at 1.25x
    for the default 5-minute TTL, which refreshes free on every hit -- so a write
    repays itself after roughly three reads.

    Placement follows the documented rule: mark the last block that is identical
    across requests. The final block of the current history is exactly that -- on
    the next request it is unchanged and everything after it is new.
    """
    if not msgs:
        return msgs
    out = list(msgs)
    last = dict(out[-1])
    content = last.get("content")
    # cache_control lives on a content BLOCK, so a bare string must be widened
    # to a one-element text block first.
    if isinstance(content, str):
        if not content:
            return msgs
        blocks: list[Any] = [{"type": "text", "text": content}]
    elif isinstance(content, list) and content:
        blocks = list(content)
    else:
        return msgs
    tail = blocks[-1]
    if not isinstance(tail, dict):
        return msgs
    blocks[-1] = {**tail, "cache_control": {"type": "ephemeral"}}
    last["content"] = blocks
    out[-1] = last
    return out

# ─────────────── native reasoning depth + task budgets (A2 row 7) ───────────────
#
# Two provider primitives replace two things this loop hand-built. Both are
# MODEL-GATED, and the gate is the whole risk: `budget_tokens` is gone on the
# 4.6+ family (400), and `thinking: {"type": "adaptive"}` is not a thing the
# pre-4.6 models accept either. So a model this provider was pointed at that
# predates the family must declare the capability FALSE and let the host
# emulate, rather than send a parameter that fails the turn.

#: Models taking `thinking: {"type": "adaptive"}` and `output_config.effort`.
#: Effort is GA -- no beta header.
_ADAPTIVE_THINKING_MODELS = (
    "claude-fable-5", "claude-mythos-5",
    "claude-opus-5", "claude-opus-4-8", "claude-opus-4-7", "claude-opus-4-6",
    "claude-sonnet-5", "claude-sonnet-4-6",
)

#: Models taking `output_config.task_budget`. A strict subset of the above --
#: Sonnet 4.6 and Opus 4.6 take effort but not a task budget.
_TASK_BUDGET_MODELS = (
    "claude-fable-5", "claude-mythos-5",
    "claude-opus-5", "claude-opus-4-8", "claude-opus-4-7",
    "claude-sonnet-5",
)

#: Beta flag task budgets ride on.
TASK_BUDGET_BETA = "task-budgets-2026-03-13"

#: API floor. A `total` below this is rejected, so a short tool budget still
#: buys at least this much -- the budget paces the model, it does not cap it
#: (`max_tokens` is the enforced ceiling and the model cannot see it).
TASK_BUDGET_MIN_TOKENS = 20_000

#: What one tool turn is worth in budget tokens. Deliberately generous: the
#: budget counts what the model generates plus the tool results it reads, and
#: a tool result in this loop can be a full playbook. Under-budgeting makes
#: the model wrap up early, which is the failure we are trying to STOP.
TASK_BUDGET_TOKENS_PER_TOOL_TURN = 8_000

#: ───────────────── deferred tool loading / tool search (A1.4) ─────────────
#:
#: Models taking tool search + `defer_loading`. Same family as adaptive
#: thinking; the search tool is a server tool, no beta header.
_TOOL_SEARCH_MODELS = _ADAPTIVE_THINKING_MODELS

#: The BM25 search tool. Ranked lexical match over the deferred schemas --
#: the right one for a surface whose names ARE the vocabulary
#: (`mcp_fortisiem__get_incident_by_id` says what it does).
TOOL_SEARCH_TOOL = {
    "type": "tool_search_tool_bm25_20251119",
    "name": "tool_search_tool_bm25",
}


def _is_deferrable(tool: dict[str, Any]) -> bool:
    """True for the LONG TAIL: materialized MCP tools.

    The split has to be config-stable, not page-stable -- deferring by page
    would put us right back to a tool array that changes mid-session, which is
    the cache defect A1.3 just fixed. MCP materialization is a property of the
    configured servers, so `mcp_*` is exactly such a line: dozens of schemas,
    stable for the session, and individually rare in any one turn.
    """
    return str(tool.get("name", "")).startswith("mcp_")


def apply_deferred_loading(
    tools: list[dict[str, Any]], model: str
) -> tuple[list[dict[str, Any]], int]:
    """Mark the long tail `defer_loading: true` and prepend the search tool.

    Returns `(tools, deferred_count)`; `(tools, 0)` unchanged when the model
    cannot search or when there is nothing worth deferring.

    Two API constraints, both enforced here rather than discovered at the
    wire: the search tool itself must not be deferred, and at least one other
    tool must stay loaded (`400 All tools have defer_loading set`). The
    curated surface always satisfies the second -- but a slice that happened
    to be all-MCP would not, so it is checked, not assumed.

    Schemas are APPENDED when found, never swapped, so the cached prefix
    survives a search. That is the whole reason this is the mechanism for a
    dynamic surface rather than per-turn filtering.
    """
    if not _model_supports_tool_search(model):
        return list(tools), 0
    deferrable = [t for t in tools if _is_deferrable(t)]
    if not deferrable or len(deferrable) == len(tools):
        return list(tools), 0
    out: list[dict[str, Any]] = [dict(TOOL_SEARCH_TOOL)]
    for t in tools:
        out.append({**t, "defer_loading": True} if _is_deferrable(t) else t)
    return out, len(deferrable)


def _model_supports_tool_search(model: str) -> bool:
    return (model or "").strip() in _TOOL_SEARCH_MODELS


#: ───────────────── context editing / history pruning (A2, row 10) ─────────
#:
#: Context editing CLEARS old tool results server-side before the model reads
#: the transcript; it is not compaction (which summarizes) and it is not
#: `shrink_history` (which rewrites blocks on our side and pays to resend
#: them). Same family as the other primitives -- an older model must declare
#: the capability False and let the host emulate rather than eat a 400.
_CONTEXT_EDIT_MODELS = _ADAPTIVE_THINKING_MODELS

#: Beta flag context editing rides on. NOT `compact-2026-01-12` -- that is the
#: separate compaction feature, and sending its edit type here is a 400.
CONTEXT_EDIT_BETA = "context-management-2025-06-27"

#: The edit strategy. `clear_tool_uses_20250919` drops old tool RESULTS and
#: keeps the assistant's own reasoning about them. `clear_tool_inputs` is left
#: off on purpose: this loop's tool inputs are the YAML the analyst is having
#: built, and clearing them would erase what a later turn edits.
CONTEXT_EDIT_STRATEGY = {"type": "clear_tool_uses_20250919"}


def _model_supports_context_editing(model: str) -> bool:
    return (model or "").strip() in _CONTEXT_EDIT_MODELS


def context_edit_kwargs(model: str, asked: bool) -> dict:
    """The request kwargs that hand pruning to the server, or `{}`.

    Empty unless the loop explicitly asked AND the model can take it, which is
    what keeps `shrink_history` switched on everywhere else -- the two must
    never both run, or we would pay to rewrite a transcript the server is
    already clearing.
    """
    if not asked or not _model_supports_context_editing(model):
        return {}
    return {"context_management": {"edits": [dict(CONTEXT_EDIT_STRATEGY)]}}


#: Kill switch. `FSR_ANTHROPIC_NATIVE=0` makes this provider declare BOTH
#: primitives unsupported, which routes the turn back through the host-side
#: emulation via the ordinary seam -- one env var, no second code path. It
#: exists because the native path changes the wire (task budgets ride the beta
#: endpoint) and a box can be reverted faster than it can be re-shipped.
NATIVE_ENV_FLAG = "FSR_ANTHROPIC_NATIVE"


def _native_enabled() -> bool:
    return os.environ.get(NATIVE_ENV_FLAG, "1").strip().lower() not in (
        "0", "false", "no", "off",
    )


#: Efforts the API accepts. An unrecognised one is dropped rather than sent --
#: a 400 in the middle of a turn is worse than the default depth.
_EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")


def _model_supports_reasoning_depth(model: str) -> bool:
    return (model or "").strip() in _ADAPTIVE_THINKING_MODELS


def _model_supports_task_budget(model: str) -> bool:
    return (model or "").strip() in _TASK_BUDGET_MODELS


def reasoning_kwargs(model: str, effort: str | None) -> dict[str, Any]:
    """The request kwargs that carry a REQUESTED reasoning depth, or `{}`.

    Empty when nothing was asked or the model cannot take it -- so the default
    path sends no `thinking` / `output_config` at all and behaves exactly as it
    did before this landed. That matters: on the 4.6+ family, omitting
    `thinking` already runs adaptive, so sending it unasked would change the
    wire for every turn to buy nothing.
    """
    depth = (effort or "").strip().lower() or None
    if not depth or depth not in _EFFORT_LEVELS:
        return {}
    if not _model_supports_reasoning_depth(model):
        return {}
    return {
        "thinking": {"type": "adaptive"},
        "output_config": {"effort": depth},
    }


def task_budget_kwargs(model: str, tool_turns: int | None) -> dict[str, Any]:
    """The request kwargs that hand the model a server-tracked token budget.

    `{}` when the model cannot take one, which is what keeps the host-side
    `budget_note` emulation switched on for it. `remaining` is deliberately NOT
    sent: the server tracks the countdown, and a client-computed `remaining`
    alongside a resent history under-reports the spend.
    """
    if not tool_turns or not _model_supports_task_budget(model):
        return {}
    total = max(TASK_BUDGET_MIN_TOKENS,
                int(tool_turns) * TASK_BUDGET_TOKENS_PER_TOOL_TURN)
    return {"output_config": {"task_budget": {"type": "tokens", "total": total}}}


def merge_output_config(*kwarg_sets: dict[str, Any]) -> dict[str, Any]:
    """Merge request kwarg sets, UNIONING their `output_config` instead of
    letting the last one win. `effort` and `task_budget` are siblings in one
    object, so a naive `{**a, **b}` silently drops the effort -- exactly the
    kind of quiet no-op the capability matrix exists to catch.
    """
    merged: dict[str, Any] = {}
    out_cfg: dict[str, Any] = {}
    for kw in kwarg_sets:
        for k, v in kw.items():
            if k == "output_config":
                out_cfg.update(v)
            else:
                merged[k] = v
    if out_cfg:
        merged["output_config"] = out_cfg
    return merged


class AnthropicProvider(CapabilityMixin):
    name = "anthropic"

    @property
    def capabilities(self) -> ProviderCapabilities:  # type: ignore[override]
        """Declared PER MODEL, not per class: the same provider pointed at
        Sonnet 4.5 serves neither primitive and must fall back to the host
        emulation, while on the 4.6+ family both reach the wire.

        `history_pruning` (context editing) is declared here too, but it only
        reaches the wire on a turn that ASKED for it -- see
        `context_edit_kwargs`.
        """
        if not _native_enabled():
            return ProviderCapabilities()
        return ProviderCapabilities(
            reasoning_depth=_model_supports_reasoning_depth(self.model),
            task_budget=_model_supports_task_budget(self.model),
            deferred_tools=_model_supports_tool_search(self.model),
            history_pruning=_model_supports_context_editing(self.model),
        )

    # Class-level default so the loop reads a sane cap even on an instance
    # built without __init__ (tests use `__new__` to drive `_pump` directly).
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS

    def __init__(
        self,
        *,
        model: str = DEFAULT_MODEL,
        api_key: str | None = None,
        base_url: str | None = None,
        client: AsyncAnthropic | None = None,
        approval_gateway: Any = None,
        max_output_tokens: int | None = None,
    ):
        self.model = model or DEFAULT_MODEL
        # Shared ceiling -- see `openai_provider.DEFAULT_MAX_OUTPUT_TOKENS` for
        # why it is uniform rather than per-intent (a cap is a ceiling, not a
        # spend: you are billed on tokens emitted, not on the limit).
        self.max_output_tokens = max_output_tokens or DEFAULT_MAX_OUTPUT_TOKENS
        # base_url override: point at an Anthropic-compatible gateway/proxy
        # (corporate egress proxy, Bedrock/Vertex-compat shim, a local mock).
        # None → the SDK's default (https://api.anthropic.com). Only forwarded
        # when set so we don't override a caller-injected client's own base.
        _client_kwargs: dict[str, Any] = {"max_retries": 5}
        if base_url:
            _client_kwargs["base_url"] = base_url
        # max_retries=5 (SDK default is 2). Failed retries cost nothing --
        # Anthropic only bills successful generations -- so a higher
        # ceiling makes us robust to transient 529 overloads at zero
        # cost. The SDK already exponentially backs off between retries.
        if client is not None:
            self._client = client
        elif AsyncAnthropic is None:
            raise RuntimeError(
                "the 'anthropic' SDK is not installed; AnthropicProvider "
                "needs it unless you inject a `client=`")
        elif api_key:
            self._client = AsyncAnthropic(api_key=api_key, **_client_kwargs)
        else:
            # Falls back to ANTHROPIC_API_KEY env var via SDK default.
            self._client = AsyncAnthropic(**_client_kwargs)
        # ApprovalGateway impl (fsr_playbooks.protocols.ApprovalGateway). When
        # None, falls back to the module-level singleton in
        # `fsr_playbooks.llm.approvals` -- that's what the web backend uses.
        # The FortiSOAR connector passes a PersistedApprovalGateway so
        # paused HITL turns survive worker restarts.
        self._approval_gateway = approval_gateway

    def _native_request_kwargs(
        self, tool_turns: int | None
    ) -> tuple[dict[str, Any], list[str]]:
        """Request kwargs for the primitives THIS model serves, plus any beta
        flags they need. `({}, [])` when nothing was asked or the model cannot
        take it -- the pre-seam wire, byte for byte.

        Only what `request()` asked for is sent. A turn nobody asked anything
        of gets no `thinking`, no `output_config` and the non-beta endpoint,
        which is what keeps this landing free of a blast radius.
        """
        req = self._turn_request
        reasoning = reasoning_kwargs(self.model, req.reasoning)
        # Native budget only when the loop handed one over; `tool_turns` is
        # this stream's own bound, used as the value once asked. Without an
        # ask, `emulation.task_budget` stays True and `budget_note` runs.
        budget: dict[str, Any] = {}
        if req.max_tool_turns is not None and not self.emulation.task_budget:
            budget = task_budget_kwargs(self.model, req.max_tool_turns or tool_turns)
        # Native context editing, likewise only on an explicit ask -- the
        # residue is what keeps `shrink_history` on for everyone else.
        pruning = context_edit_kwargs(
            self.model,
            req.prune_history is True and not self.emulation.history_pruning,
        )
        merged = merge_output_config(reasoning, budget, pruning)
        betas = ([TASK_BUDGET_BETA] if budget else []) + (
            [CONTEXT_EDIT_BETA] if pruning else [])
        return merged, betas

    # -- the loop's seam (see agent_loop) ----------------------------------

    label = "Anthropic"

    def precheck(self) -> str | None:
        return None

    def open_turn(self, *, system: str, messages: list[Message],
                  tools: list[dict[str, Any]] | None, turn_budget: int) -> _AnthropicTurn:
        return _AnthropicTurn(self, system, messages, tools, turn_budget)

    def rehydrate(self, suspended: _approvals.SuspendedSession,
                  outcomes: list[ToolOutcome]) -> list[Message]:
        """The snapshot, then one user message answering every tool_use of the
        suspended assistant message (Anthropic 400s on an unanswered one)."""
        out = [Message(role=m["role"], content=m["content"])
               for m in suspended.history_snapshot]
        out.append(Message(role="user", content=(
            list(suspended.prior_tool_result_blocks)
            + [_result_block(o) for o in outcomes])))
        return out

    def contract_stop(self, raw: str | None) -> str:
        return raw or "end_turn"

    def friendly_error(self, e: Exception) -> str:
        # The SDK already retried 429/5xx/529 up to max_retries; reaching here
        # means retries were exhausted or the error is not retryable.
        from anthropic import (
            APIConnectionError,
            APIStatusError,
            APITimeoutError,
            AuthenticationError,
            BadRequestError,
            PermissionDeniedError,
            RateLimitError,
        )
        if isinstance(e, AuthenticationError):
            return "Anthropic authentication failed -- check ANTHROPIC_API_KEY in the backend env."
        if isinstance(e, PermissionDeniedError):
            return "Anthropic API key lacks permission for this model."
        if isinstance(e, RateLimitError):
            return "You've hit Anthropic's rate limit. Wait a moment and try again."
        if isinstance(e, APITimeoutError):
            return "The request to Anthropic timed out. Try again, or shorten the prompt if it's very long."
        if isinstance(e, APIConnectionError):
            return "Could not reach Anthropic -- check your network connection and try again."
        if isinstance(e, BadRequestError):
            return f"Anthropic rejected the request: {getattr(e, 'message', str(e))[:200]}"
        if isinstance(e, APIStatusError):
            err_type = ""
            try:
                body = getattr(e, "body", None) or {}
                err_type = (body.get("error") or {}).get("type", "")
            except Exception:
                pass
            if err_type == "overloaded_error":
                return ("Anthropic is overloaded right now. We retried a few times "
                        "and still couldn't get through -- please try again in a moment.")
            return (f"Anthropic returned an error (HTTP {getattr(e, 'status_code', '?')}). "
                    f"Please try again.")
        return "Something went wrong talking to Anthropic. Please try again."

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


def _result_block(o: ToolOutcome) -> dict[str, Any]:
    return {"type": "tool_result", "tool_use_id": o.call_id,
            "content": o.content, "is_error": o.is_error}


def _round_usage(final: Any) -> RoundUsage:
    u = getattr(final, "usage", None)
    if not u:
        return RoundUsage()
    return RoundUsage(getattr(u, "input_tokens", 0) or 0,
                      getattr(u, "output_tokens", 0) or 0,
                      getattr(u, "cache_read_input_tokens", 0) or 0,
                      getattr(u, "cache_creation_input_tokens", 0) or 0)


class _AnthropicTurn:
    """One stream's Messages history and the requests that read it."""

    def __init__(self, provider: AnthropicProvider, system: str,
                 messages: list[Message], tools: list[dict[str, Any]] | None,
                 turn_budget: int) -> None:
        self.p = provider
        self.history: list[Message] = list(messages)
        self.turn_budget = turn_budget
        # `is None` (not `not tools`): the budget-ask "deliver" path passes []
        # to force a no-research wrap-up turn.
        self.plain_tools = anthropic_tools() if tools is None else list(tools)
        self.allowed_names = {t["name"] for t in self.plain_tools}
        # Prompt caching: the (system + tools) prefix is cached for 5 min, so
        # within a session every turn after the first reads it at 0.1x.
        self.system = [{"type": "text", "text": system,
                        "cache_control": {"type": "ephemeral"}}]
        req_tools = self.plain_tools
        # A1.4: defer the long tail when the loop asked for it -- applied
        # before the cache stamp, since the flags are config-stable.
        if provider._turn_request.defer_tools and not provider.emulation.deferred_tools:
            req_tools, _n = apply_deferred_loading(req_tools, provider.model)
        self.request_tools = [({**t, "cache_control": {"type": "ephemeral"}}
                               if i == len(req_tools) - 1 else t)
                              for i, t in enumerate(req_tools)]
        # Stamped on every UsageEvent: a session whose fingerprint changes
        # between turns paid to rebuild the cache -- see cache_prefix.
        self._prefix_fp = _prefix_fingerprint(system, req_tools)

    # -- reading ----------------------------------------------------------

    def before_round(self) -> None:
        # Host-side stand-in for context editing; when the server is pruning
        # natively the two must never both run.
        if self.p.emulation.history_pruning:
            _shrink_history(self.history)

    def history_chars(self) -> int:
        try:
            return len(json.dumps(_to_anthropic_messages(self.history), default=str))
        except Exception:
            return 0

    def history_dicts(self) -> list[dict[str, Any]]:
        return [{"role": m.role, "content": m.content} if hasattr(m, "role") else m
                for m in self.history]

    def has_tool(self, name: str) -> bool:
        return any(t.get("name") == name for t in self.plain_tools)

    def usage_extra(self) -> dict[str, Any]:
        return {"prefix_fingerprint": self._prefix_fp}

    def _messages(self) -> list[dict[str, Any]]:
        return _with_history_breakpoint(_to_anthropic_messages(self.history))

    # -- requests ---------------------------------------------------------

    async def stream_round(self) -> AsyncIterator[tuple[str, Any]]:
        p = self.p
        # A task budget rides the BETA endpoint, so the endpoint follows the
        # kwargs rather than being decided up front.
        native_kw, betas = p._native_request_kwargs(self.turn_budget)
        api = p._client.beta.messages if betas else p._client.messages
        extra = {"betas": betas} if betas else {}
        async with api.stream(
            model=p.model,
            max_tokens=p.max_output_tokens,
            system=self.system,
            messages=self._messages(),
            tools=self.request_tools,
            **native_kw,
            **extra,
        ) as stream:
            async for ev in stream:
                if ev.type == "content_block_delta" and getattr(ev.delta, "type", None) == "text_delta":
                    yield ("text", ev.delta.text)
            final = await stream.get_final_message()
        yield ("final", self._parse(final))

    def _parse(self, final: Any) -> Round:
        blocks: list[dict[str, Any]] = []
        calls: list[ToolCall] = []
        for b in final.content:
            if b.type == "text":
                blocks.append({"type": "text", "text": b.text})
            elif b.type == "tool_use":
                blocks.append({"type": "tool_use", "id": b.id, "name": b.name, "input": b.input})
                calls.append(ToolCall(b.id, b.name, dict(b.input)))
        text = "".join(b["text"] for b in blocks if b["type"] == "text")
        # Only a `tool_use` stop executes its calls; any other stop
        # (`max_tokens` above all) drops them -- a tool_use with no tool_result
        # makes the next request a 400.
        dropped: list[DroppedCall] = []
        if calls and final.stop_reason != "tool_use":
            for c in calls:
                raw = json.dumps(c.args, default=str)
                dropped.append(DroppedCall(name=c.name, arg_chars=len(raw), tail=raw[-200:]))
            blocks = [b for b in blocks if b["type"] != "tool_use"]
            if not blocks:
                blocks = [{"type": "text", "text": unexecuted_tool_calls_note(
                    final.stop_reason, [c.name for c in calls])}]
            calls = []
        return Round(text=text, tool_calls=calls, stop_reason=final.stop_reason or "",
                     usage=_round_usage(final), dropped_calls=dropped,
                     # An empty reply is not history: Anthropic refuses a
                     # message with empty content.
                     assistant=Message(role="assistant", content=blocks) if blocks else None)

    async def wrapup_round(self, max_tokens: int) -> AsyncIterator[tuple[str, Any]]:
        p = self.p
        async with p._client.messages.stream(
            model=p.model,
            max_tokens=max_tokens,
            system=self.system,
            messages=self._messages(),
        ) as stream:
            async for ev in stream:
                if ev.type == "content_block_delta" and getattr(ev.delta, "type", None) == "text_delta":
                    yield ("text", ev.delta.text)
            final = await stream.get_final_message()
        yield ("final", _round_usage(final))

    async def forced_call(self, name: str) -> ToolCall | None:
        p = self.p
        schema = next(t for t in self.plain_tools if t.get("name") == name)
        resp = await p._client.messages.create(
            model=p.model, max_tokens=p.max_output_tokens,
            system=self.system,
            messages=self._messages(),
            tools=[schema],
            tool_choice={"type": "tool", "name": name},
        )
        tu = next((b for b in resp.content if getattr(b, "type", None) == "tool_use"), None)
        if tu is None:
            return None
        return ToolCall(getattr(tu, "id", None) or "", name, dict(getattr(tu, "input", {}) or {}))

    # -- history ----------------------------------------------------------

    def append_assistant(self, rnd: Round) -> None:
        if rnd.assistant is not None:
            self.history.append(rnd.assistant)

    def append_user(self, text: str) -> None:
        self.history.append(Message(role="user", content=text))

    def append_tool_call(self, call: ToolCall) -> None:
        self.history.append(Message(role="assistant", content=[{
            "type": "tool_use", "id": call.call_id, "name": call.name, "input": call.args}]))

    def result_wire(self, outcome: ToolOutcome) -> dict[str, Any]:
        return _result_block(outcome)

    def append_tool_results(self, outcomes: list[ToolOutcome], *,
                            note: str | None = None, note_role: str = "user") -> None:
        # One user message answers every call; a note rides as a text block in
        # it (Anthropic has no mid-conversation system role).
        blocks: list[dict[str, Any]] = [_result_block(o) for o in outcomes]
        if note:
            blocks.append({"type": "text", "text": note})
        self.history.append(Message(role="user", content=blocks))

    def snapshot(self) -> list[Any]:
        return _to_anthropic_messages(self.history)
