"""Anthropic provider -- streaming with tool use.

We do the agentic loop here so the route handler stays a dumb pipe:
- send messages + tools
- stream text deltas as TextEvent
- on stop_reason=tool_use, emit ToolUseEvent for each tool_use block,
  then call dispatch(), append a tool_result message, and loop again
- emit DoneEvent on stop_reason=end_turn (or any non-tool_use stop)
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from collections.abc import AsyncIterator
from typing import Any

try:
    from anthropic import AsyncAnthropic
except ImportError:
    # The SDK isn't installed in every environment (e.g. the test/dev box
    # that only exercises the pure helpers, or the FSR connector runtime).
    # Defer the hard failure to AnthropicProvider.__init__ so the module --
    # and its module-level helpers -- import cleanly without it.
    AsyncAnthropic = None  # type: ignore[assignment,misc]

from . import approvals as _approvals
from ._loop_helpers import (
    DEFAULT_MAX_OUTPUT_TOKENS,
    MAX_PARALLEL_TOOLS,
    MAX_SELF_REPAIR_TURNS,
    MAX_TOOL_TURNS,
    STREAM_TIMEOUT_SECS,
    UNVERIFIED_DRAFT_DIRECTIVE,
    BuildProgressGuard,
    CreateDeliveryGuard,
    EnhanceDeliveryGuard,
    ProgressMeter,
    PromisedActionGuard,
    TriageDiscipline,
    VerdictDeliveryGuard,
    drain_with_idle_timeout,
    latest_user_text,
    stall_directive,
    unexecuted_tool_calls_note,
    verdict_directive,
    verdict_repair_directive,
)
from ._loop_helpers import (
    compile_errors as _compile_errors,
)
from ._loop_helpers import (
    extract_yaml_block as _extract_yaml_block,
)
from ._loop_helpers import (
    shrink_history as _shrink_history,
)
from .cache_prefix import prefix_fingerprint as _prefix_fingerprint
from .provider import (
    ApprovalRequestEvent,
    CapabilityMixin,
    DoneEvent,
    DroppedCall,
    ErrorEvent,
    Event,
    Message,
    ProviderCapabilities,
    TextEvent,
    ToolCallUsage,
    ToolResultEvent,
    ToolUseEvent,
    UsageEvent,
)
from .tools import _resolve_tier as _tier_for
from .tools import anthropic_tools, dispatch

# The agent runs a multi-step tool loop, so the default must be a model that
# can plan across calls. Sonnet 4.5 predates adaptive thinking entirely -- it
# takes no `thinking` / `effort` control at all, so the capability seam has
# nothing to give it. Sonnet 5 is the volume default; callers that want more
# pass `model=` (the connector's config dropdown offers claude-opus-5).
DEFAULT_MODEL = os.environ.get("STUDIO_ANTHROPIC_MODEL", "claude-sonnet-5")


# P1 -- forced written assessment. When a turn runs tools but the final
# assistant block carries no text (only tool_use / emitted cards), the chat
# looks like it "didn't answer." We append this directive and do ONE more
# no-tools round so the analyst always gets a narrative close.
_ASSESSMENT_DIRECTIVE = (
    "You ran tools but did not write anything back to the analyst. Stop "
    "calling tools. In a short written assessment, tell the analyst: "
    "(1) what you found, (2) your severity / disposition verdict, and "
    "(3) the single recommended next action. Be concise and do not call tools."
)

# Forced enhance-delivery round (mirrors OpenAIProvider._DELIVERY_DIRECTIVE).
# A verify passed but no emit_enhancement_offer followed -- force the call via
# tool_choice and override verified_id afterward so the forced round can only
# apply the blessed bytes.
_BUILD_PROGRESS_DIRECTIVE = (
    "You have researched the step types and connector operations but have not "
    "authored anything yet -- describing what you WILL build is not building it. "
    "Draft the full playbook YAML now and call `verify_playbook` with it, then "
    "deliver it with `emit_card(card_type='playbook_offer', ...)`. Do not end the turn with a plan."
)

_CREATE_DELIVERY_DIRECTIVE = (
    "You drafted a playbook and `verify_playbook` cleared it, but you have not "
    "delivered it. Call `emit_card(card_type='playbook_offer', ...)` now -- describing the playbook in "
    "prose is NOT a substitute for the call, and the analyst has no way to save "
    "it without the card. Write the `summary` (in the payload) as one or two plain-English lines "
    "describing what the playbook does."
)

_DELIVERY_DIRECTIVE = (
    "You verified an edit to the open playbook and it is ready to apply, but "
    "you have not delivered it. Call `emit_card(card_type='enhancement_offer', ...)` now with "
    "verified_id {vid!r} to apply it -- a written description is NOT a "
    "substitute for the call. Write the `summary` (in the payload) as one or two plain-English "
    "lines describing what the edit changes."
)


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

    async def resume(
        self,
        *,
        suspended: _approvals.SuspendedSession,
        decision: str,  # "approve" | "deny"
    ) -> AsyncIterator[Event]:
        """Resume a turn that was suspended on a pending_approval.

        Rebuilds the user-side tool_result message covering every
        tool_use the model emitted in the suspended assistant turn:
        - prior_tool_result_blocks for calls that completed pre-pending
        - one block for the pending call (re-dispatched on approve, or
          synthesized `{ok: false, code: "user_denied"}` on deny)
        - placeholders for remaining_tool_calls (Anthropic requires a
          tool_result for every tool_use; without these the next
          messages call 400s).

        Then re-enters `stream()` with the rebuilt history. The full
        provider loop (text deltas, further tool calls, UsageEvent,
        DoneEvent) flows as usual.
        """
        # Phase 3.1: verify the HMAC binding before trusting the stored args.
        # A mismatch means the session was tampered with (or minted before a
        # secret rotation / restart without a stable FSR_APPROVAL_HMAC_KEY) --
        # fail closed rather than re-dispatch a possibly-substituted call.
        if not _approvals.verify(suspended):
            yield ErrorEvent(
                message="Approval binding check failed -- the suspended action "
                        "could not be verified and was not executed. Re-issue "
                        "the request."
            )
            yield DoneEvent(stop_reason="approval_unverified")
            return

        if decision == "approve":
            # Bypass the gate this one time -- see tools.dispatch. Off-loop
            # like the main loop's dispatch: live MCP tools call asyncio.run()
            # internally, which raises if dispatched inline on the running loop.
            resolved = await asyncio.to_thread(
                dispatch,
                suspended.tool,
                {**suspended.args, "_approved": True},
                _internal=True,
            )
            decision_event_result: Any = resolved
        else:
            resolved = {"ok": False, "code": "user_denied",
                        "reason": "User denied the action."}
            decision_event_result = resolved

        # Emit a NAMED synthetic tool_use before the result: the original
        # ToolUseEvent lives in the prior turn's transcript, so a renderer
        # matching name by call_id within THIS turn finds nothing and falls
        # back to a nameless "tool" chip (live: the approve/deny result on a
        # resumed turn rendered as `Used skill tool`).
        yield ToolUseEvent(
            name=suspended.tool, arguments=dict(suspended.args),
            call_id=suspended.tool_use_id, tier=suspended.tier,
            synthetic=True,
        )
        # Emit the resolved tool_result so the UI can render it inline
        # with the approval card it was waiting on.
        yield ToolResultEvent(
            call_id=suspended.tool_use_id,
            result=decision_event_result,
        )

        resumed_blocks: list[dict[str, Any]] = list(
            suspended.prior_tool_result_blocks
        )
        resumed_blocks.append({
            "type": "tool_result",
            "tool_use_id": suspended.tool_use_id,
            "content": _stringify(resolved),
            "is_error": _is_error_result(resolved),
        })
        for skipped in suspended.remaining_tool_calls:
            resumed_blocks.append({
                "type": "tool_result",
                "tool_use_id": skipped.call_id,
                "content": "{\"ok\": false, \"code\": "
                            "\"superseded_by_approval\"}",
                "is_error": True,
            })

        # Rehydrate Messages from the wire-form snapshot + the rebuilt
        # tool_result user turn. The provider's `stream()` will run
        # _to_anthropic_messages over this again, which is a no-op for
        # already-shaped block lists.
        rehydrated: list[Message] = []
        for m in suspended.history_snapshot:
            rehydrated.append(Message(role=m["role"], content=m["content"]))
        rehydrated.append(Message(role="user", content=resumed_blocks))

        async for ev in self.stream(
            system=suspended.system,
            messages=rehydrated,
            # Old pickled sessions predate the field -- getattr, not attr.
            tools=list(getattr(suspended, "tools", None) or []),
            tags=suspended.tags,
        ):
            yield ev

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

    async def _wrapup_call(
        self,
        *,
        history: list[Message],
        directive: str,
        cached_system: Any,
        session_id: str,
        turn_idx: int,
        tags: dict[str, Any],
        self_repair_turns: int,
        stop_reason_label: str,
        max_tokens: int = 512,
    ) -> AsyncIterator[Event]:
        """One forced no-tools model round that yields its text + a UsageEvent.

        Shared by the max-tool-turns wrap-up and the P1 forced-assessment
        guarantee. Appends ``directive`` as a user turn, runs the model with
        NO tools (so it can't keep investigating), and streams the resulting
        text. Failures are logged and swallowed -- the caller still emits a
        terminal DoneEvent so the turn never hangs.
        """
        history.append(Message(role="user", content=directive))
        try:
            history_chars = len(json.dumps(
                _to_anthropic_messages(history), default=str
            ))
        except Exception:
            history_chars = 0
        try:
            async with self._client.messages.stream(
                model=self.model,
                max_tokens=max_tokens,
                system=cached_system,
                messages=_with_history_breakpoint(_to_anthropic_messages(history)),
            ) as stream:
                async for event in stream:
                    if event.type == "content_block_delta" and getattr(
                        event.delta, "type", None
                    ) == "text_delta":
                        yield TextEvent(text=event.delta.text)
                final = await stream.get_final_message()
            usage = getattr(final, "usage", None)
            yield UsageEvent(
                session_id=session_id, turn=turn_idx, model=self.model,
                input_tokens=getattr(usage, "input_tokens", 0) or 0 if usage else 0,
                output_tokens=getattr(usage, "output_tokens", 0) or 0 if usage else 0,
                cache_read=getattr(usage, "cache_read_input_tokens", 0) or 0 if usage else 0,
                cache_write=getattr(usage, "cache_creation_input_tokens", 0) or 0 if usage else 0,
                history_chars=history_chars,
                stop_reason=stop_reason_label,
                self_repair_turn=self_repair_turns,
                tool_calls=[], tags=tags,
            )
        except Exception:
            import logging
            logging.exception("%s call failed", stop_reason_label)
            yield ErrorEvent(
                message=(
                    "hit max tool budget; summary failed -- see "
                    "history above"
                ),
            )

    async def stream(
        self,
        *,
        system: str,
        messages: list[Message],
        tools: list[dict[str, Any]],
        tags: dict[str, Any] | None = None,
        case_state: Any = None,  # CaseState | None, kept as Any to avoid import
        max_tool_turns: int | None = None,  # budget-ask resume (None → MAX_TOOL_TURNS)
    ) -> AsyncIterator[Event]:
        import uuid as _uuid

        history = list(messages)
        self_repair_turns = 0
        # Clear per-turn citation validator state for structured verdicts
        from ..mcp_server._citation_validator import clear_tool_registry
        clear_tool_registry()
        # P1 -- forced-assessment guarantee. `any_tools_run` flips once any
        # tool result has been folded into history; `assessment_forced`
        # caps the guarantee at one extra round so it can't loop.
        any_tools_run = False
        assessment_forced = False
        # Enhance mode: guarantees a passing verify is delivered via
        # emit_enhancement_offer rather than narrated. Inert unless the offer
        # tool is in the advertised slice (see EnhanceDeliveryGuard).
        _delivery = EnhanceDeliveryGuard()
        # CREATE counterpart -- see CreateDeliveryGuard.
        _create_delivery = CreateDeliveryGuard()
        # Triage turns that gathered evidence must close with a verdict card.
        _verdict_guard = VerdictDeliveryGuard()
        _promise_guard = PromisedActionGuard()
        _progress = ProgressMeter()
        _build_progress = BuildProgressGuard()
        session_id = _uuid.uuid4().hex[:8]
        turn_idx = 0
        tags = tags or {}
        # Allow callers to pass tools=None to have the provider supply its
        # own. Keeps the route handler ignorant of which schema shape applies.
        # `is None` (not `not tools`): the budget-ask "deliver" path passes
        # tools=[] to force a no-research wrap-up turn; `not tools` would
        # silently replace [] with the full tool list.
        if tools is None:
            tools = anthropic_tools()

        # Defense-in-depth for the intent tool-slice (see llm/intents.py).
        # The caller advertises an intent-filtered tool list (triage drops
        # the build-only authoring/mutation surface), but `dispatch` will
        # happily execute ANY tool name. If a build-only tool name reaches
        # us in a triage session -- model confusion, a stale widget, a
        # replayed transcript -- refuse to run it instead of silently
        # authoring/mutating. The model only ever sees `allowed_names`, so
        # in the normal path this never triggers; it's a backstop.
        allowed_names = {t["name"] for t in tools}

        # P4 -- repeated-error guard. If a tool call with the identical
        # (name, args) shape already failed once this turn, don't re-run it:
        # return a guard envelope telling the model to stop retrying that exact
        # shape and adapt (e.g. re-resolve a SIEM incidentId from sourcedata)
        # or surface the blocker. Stops the "same 400 twice, no adaptation"
        # budget burn seen in live triage.
        failed_signatures: set[str] = set()
        # Triage discipline (hunt floor + forbidden pivot + call-once) -- see
        # _loop_helpers.TriageDiscipline. Fires only on triage tool names.
        # If case_state is provided, pass its investigation to seed counters.
        investigation_state = (
            getattr(case_state, "investigation", None)
            if case_state is not None else None
        )
        # Authoring/build turns are detected by the presence of build-only tools
        # like verify_playbook or push_playbook -- triage never advertises these.
        # Old check ("emit_action_card" not in allowed_names) no longer works
        # since emit_action_card is consolidated into emit_card (both triage and
        # build have emit_card, but with different card_type affordances).
        _authoring = (
            "verify_playbook" in allowed_names or
            "push_playbook" in allowed_names or
            "verify_enhancement" in allowed_names
        )
        _discipline = TriageDiscipline(
            state=investigation_state,
            capabilities=(getattr(case_state, "capabilities", None)
                          if case_state is not None else None),
            authoring=_authoring,
            # The analyst's own words are the only reliable carrier of an
            # explicit containment order -- see `_detect_analyst_order`.
            user_text=latest_user_text(messages),
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
                        f"arguments -- change the inputs (e.g. resolve the "
                        f"correct id from the record's sourcedata) or stop and "
                        f"report the blocker in your assessment."
                    ),
                }
            guard = _discipline.evaluate(nm, ar)
            if guard is not None:
                # Terminal guards (forbidden pivot / call-once) can never
                # succeed -- register the signature so an identical re-call hits
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

        # Prompt caching: mark the last tool with `cache_control` so the
        # entire (system + tools) prefix is cached for 5 min. Cached reads
        # cost 90% less ($0.30/M vs $3/M for Sonnet 4.5). Within a back-to-
        # back chat session every turn after the first is a cache hit.
        cached_system = [
            {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}
        ]
        # A1.4: defer the long tail when the loop asked for it. Applied
        # BEFORE the cache_control stamp so the search tool and the
        # `defer_loading` flags are inside the cached prefix -- they are
        # config-stable, so they cache like the rest of it.
        if self._turn_request.defer_tools and not self.emulation.deferred_tools:
            tools, _deferred_n = apply_deferred_loading(tools, self.model)
        cached_tools: list[dict[str, Any]] = []
        for i, t in enumerate(tools):
            if i == len(tools) - 1:
                cached_tools.append({**t, "cache_control": {"type": "ephemeral"}})
            else:
                cached_tools.append(t)
        # Stamp the prefix digest onto every UsageEvent this stream emits. A
        # session whose fingerprint changes between turns paid to rebuild the
        # cache, and `cache_read` alone cannot say why -- see cache_prefix.
        _prefix_fp = _prefix_fingerprint(system, tools)

        _turn_budget = max_tool_turns or MAX_TOOL_TURNS
        for _turn in range(_turn_budget):
            turn_idx += 1
            # Compact older turns: dedupe idempotent-tool results and
            # cap older validate_yaml/compile_yaml bodies. Only mutates
            # historical blocks -- the most recent assistant + tool_result
            # stay byte-identical so prompt cache is preserved.
            try:
                # Host-side stand-in for context editing. `emulation` says
                # whether it is ours to do: on a turn that asked for native
                # pruning (row 10) the residue is False here and the server
                # clears the old tool results instead -- the two never both
                # run, because paying to rewrite a transcript the server is
                # already clearing is worse than either alone.
                if self.emulation.history_pruning:
                    _shrink_history(history)
            except Exception:
                # Never let compaction break a chat turn.
                import logging
                logging.exception("shrink_history failed")
            # Snapshot history size BEFORE the LLM round-trip so we can
            # see what we paid to send. Cached system+tools aren't in
            # this number -- Anthropic's `cache_read_input_tokens` is.
            try:
                history_chars = len(json.dumps(
                    _to_anthropic_messages(history), default=str
                ))
            except Exception:
                history_chars = 0
            # §2.2 -- stream the round-trip live: text deltas reach the caller
            # (and the connector's chat_poll feed) AS THEY ARRIVE, so the widget
            # shows a live token stream instead of the whole answer landing at
            # once on turn completion. `_pump` keeps `get_final_message()` inside
            # the SDK's streaming context; `drain_with_idle_timeout` supplies the
            # per-delta inactivity timeout + cancellation (shared across
            # providers -- see _loop_helpers).
            # Native primitives for this model, if any were asked for. A
            # task budget must ride the BETA messages endpoint, so the choice
            # of endpoint follows the kwargs rather than being decided up front.
            _native_kw, _native_betas = self._native_request_kwargs(_turn_budget)

            async def _pump():
                _msgs = (self._client.beta.messages if _native_betas
                         else self._client.messages)
                _extra = {"betas": _native_betas} if _native_betas else {}
                async with _msgs.stream(
                    model=self.model,
                    max_tokens=self.max_output_tokens,
                    system=cached_system,
                    messages=_with_history_breakpoint(_to_anthropic_messages(history)),
                    tools=cached_tools,
                    **_native_kw,
                    **_extra,
                ) as _stream:
                    async for _ev in _stream:
                        if _ev.type == "content_block_delta" and getattr(
                            _ev.delta, "type", None
                        ) == "text_delta":
                            yield ("text", _ev.delta.text)
                    yield ("final", await _stream.get_final_message())

            final = None
            try:
                async for _kind, _payload in drain_with_idle_timeout(
                    _pump(), timeout=STREAM_TIMEOUT_SECS
                ):
                    if _kind == "text":
                        yield TextEvent(text=_payload)   # live delta
                    else:  # "final"
                        final = _payload
            except asyncio.TimeoutError:
                import logging
                logging.warning(
                    "anthropic stream timed out after %ss", STREAM_TIMEOUT_SECS
                )
                yield ErrorEvent(
                    message=f"The request to Anthropic timed out after "
                            f"{STREAM_TIMEOUT_SECS}s. The API may be slow "
                            f"or unreachable -- please try again."
                )
                return
            except Exception as e:
                # Surface a clean, user-readable message; log the raw
                # detail server-side. The SDK already auto-retried up to
                # max_retries on 429/5xx/529 -- if we reach this except
                # block, retries were exhausted (or it's a non-retryable
                # error like Auth/BadRequest).
                import logging

                from anthropic import (
                    APIConnectionError,
                    APIStatusError,
                    APITimeoutError,
                    AuthenticationError,
                    BadRequestError,
                    PermissionDeniedError,
                    RateLimitError,
                )
                logging.exception("anthropic stream failed")
                if isinstance(e, AuthenticationError):
                    msg = "Anthropic authentication failed -- check ANTHROPIC_API_KEY in the backend env."
                elif isinstance(e, PermissionDeniedError):
                    msg = "Anthropic API key lacks permission for this model."
                elif isinstance(e, RateLimitError):
                    msg = "You've hit Anthropic's rate limit. Wait a moment and try again."
                elif isinstance(e, APITimeoutError):
                    msg = "The request to Anthropic timed out. Try again, or shorten the prompt if it's very long."
                elif isinstance(e, APIConnectionError):
                    msg = "Could not reach Anthropic -- check your network connection and try again."
                elif isinstance(e, BadRequestError):
                    msg = f"Anthropic rejected the request: {getattr(e, 'message', str(e))[:200]}"
                elif isinstance(e, APIStatusError):
                    # 529 overloaded_error and any other status that
                    # slipped past auto-retry. Pull the canonical type
                    # from the response body if present.
                    err_type = ""
                    try:
                        body = getattr(e, "body", None) or {}
                        err_type = (body.get("error") or {}).get("type", "")
                    except Exception:
                        pass
                    if err_type == "overloaded_error":
                        msg = ("Anthropic is overloaded right now. We retried a few times "
                               "and still couldn't get through -- please try again in a moment.")
                    else:
                        status = getattr(e, "status_code", "?")
                        msg = f"Anthropic returned an error (HTTP {status}). Please try again."
                else:
                    msg = "Something went wrong talking to Anthropic. Please try again."
                yield ErrorEvent(message=msg)
                return

            assistant_blocks: list[dict[str, Any]] = []
            tool_calls: list[tuple[str, str, dict[str, Any]]] = []
            for block in final.content:
                if block.type == "text":
                    assistant_blocks.append({"type": "text", "text": block.text})
                elif block.type == "tool_use":
                    assistant_blocks.append({
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    })
                    tool_calls.append((block.id, block.name, dict(block.input)))

            # Only a `tool_use` stop executes its calls; any other stop
            # (`max_tokens` above all -- the block is cut off mid-input) takes
            # the terminal branch below. A tool_use with no tool_result makes
            # the next request a 400, so drop them. See unexecuted_tool_calls_note.
            dropped_calls: list[DroppedCall] = []
            if tool_calls and final.stop_reason != "tool_use":
                dropped = [n for (_i, n, _a) in tool_calls]
                for (_i, n, a) in tool_calls:
                    raw = json.dumps(a, default=str)
                    dropped_calls.append(DroppedCall(name=n, arg_chars=len(raw),
                                                     tail=raw[-200:]))
                assistant_blocks = [b for b in assistant_blocks
                                    if b["type"] != "tool_use"]
                if not assistant_blocks:
                    assistant_blocks = [{"type": "text",
                                         "text": unexecuted_tool_calls_note(
                                             final.stop_reason, dropped)}]
                tool_calls = []

            history.append(Message(role="assistant", content=assistant_blocks))

            usage = getattr(final, "usage", None)
            input_tok = getattr(usage, "input_tokens", 0) or 0 if usage else 0
            output_tok = getattr(usage, "output_tokens", 0) or 0 if usage else 0
            cache_hit = getattr(usage, "cache_read_input_tokens", 0) or 0 if usage else 0
            cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0 if usage else 0

            # Tool-call sizes are filled in once we execute the tools
            # below; built up locally so we can fold them into the
            # single UsageEvent we emit at the end of the turn.
            tool_call_usage: list[ToolCallUsage] = []

            if final.stop_reason != "tool_use" or not tool_calls:
                # Self-repair: if the assistant emitted a fenced yaml block
                # that doesn't compile, feed the structured errors back as
                # a synthetic user turn and let it try again. Capped at
                # MAX_SELF_REPAIR_TURNS so cost can't spiral.
                if self_repair_turns < MAX_SELF_REPAIR_TURNS:
                    final_text = "".join(
                        b.get("text", "") for b in assistant_blocks if b.get("type") == "text"
                    )
                    yaml_block = _extract_yaml_block(final_text)
                    if yaml_block:
                        errors_text = _compile_errors(yaml_block)
                        if errors_text:
                            self_repair_turns += 1
                            history.append(Message(
                                role="user",
                                content=(
                                    f"The YAML you just produced doesn't compile. "
                                    f"Fix the errors and emit a corrected fenced ```yaml "
                                    f"block.\n\nErrors:\n{errors_text}"
                                ),
                            ))
                            yield UsageEvent(
                                session_id=session_id, turn=turn_idx, model=self.model,
                                input_tokens=input_tok, output_tokens=output_tok,
                                cache_read=cache_hit, cache_write=cache_write,
                                prefix_fingerprint=_prefix_fp,
                                history_chars=history_chars,
                                stop_reason=final.stop_reason or "",
                                self_repair_turn=self_repair_turns - 1,
                                tool_calls=tool_call_usage, tags=tags,
                                dropped_calls=dropped_calls,
                            )
                            continue
                # Enhance-delivery guard -- a verify passed but no offer
                # followed. Force ONE round pinned to emit_enhancement_offer so
                # the delivery is a real tool call, then override verified_id
                # with the blessed handle so the forced call can only apply the
                # bytes the gate actually cleared.
                # Promised an action or a card and made no call -- see
                # PromisedActionGuard.
                _said = _promise_guard.outstanding("".join(
                    b.get("text", "") for b in assistant_blocks
                    if b.get("type") == "text"))
                if _said:
                    _promise_guard.mark_forced()
                    yield UsageEvent(
                        session_id=session_id, turn=turn_idx, model=self.model,
                        input_tokens=input_tok, output_tokens=output_tok,
                        cache_read=cache_hit, cache_write=cache_write,
                        prefix_fingerprint=_prefix_fp,
                        history_chars=history_chars,
                        stop_reason="promised_action_forced",
                        self_repair_turn=self_repair_turns,
                        tool_calls=tool_call_usage, tags=tags,
                        dropped_calls=dropped_calls,
                    )
                    turn_idx += 1
                    history.append(Message(
                        role="user", content=_promise_guard.directive(_said)))
                    continue

                if _build_progress.outstanding(allowed_names):
                    _build_progress.mark_forced()
                    yield UsageEvent(
                        session_id=session_id, turn=turn_idx, model=self.model,
                        input_tokens=input_tok, output_tokens=output_tok,
                        cache_read=cache_hit, cache_write=cache_write,
                        prefix_fingerprint=_prefix_fp,
                        history_chars=history_chars,
                        stop_reason="build_progress_forced",
                        self_repair_turn=self_repair_turns,
                        tool_calls=tool_call_usage, tags=tags,
                        dropped_calls=dropped_calls,
                    )
                    turn_idx += 1
                    history.append(Message(
                        role="user", content=_BUILD_PROGRESS_DIRECTIVE))
                    continue

                # Drafted and checked, never verified -- nothing to offer yet.
                # See BuildProgressGuard.unverified_draft.
                if _build_progress.unverified_draft(allowed_names):
                    _build_progress.mark_verify_forced()
                    yield UsageEvent(
                        session_id=session_id, turn=turn_idx, model=self.model,
                        input_tokens=input_tok, output_tokens=output_tok,
                        cache_read=cache_hit, cache_write=cache_write,
                        prefix_fingerprint=_prefix_fp,
                        history_chars=history_chars,
                        stop_reason="unverified_draft_forced",
                        self_repair_turn=self_repair_turns,
                        tool_calls=tool_call_usage, tags=tags,
                        dropped_calls=dropped_calls,
                    )
                    turn_idx += 1
                    history.append(Message(
                        role="user", content=UNVERIFIED_DRAFT_DIRECTIVE))
                    continue

                _vid = _delivery.outstanding(allowed_names)
                if _vid is not None:
                    _delivery.mark_forced()
                    yield UsageEvent(
                        session_id=session_id, turn=turn_idx, model=self.model,
                        input_tokens=input_tok, output_tokens=output_tok,
                        cache_read=cache_hit, cache_write=cache_write,
                        prefix_fingerprint=_prefix_fp,
                        history_chars=history_chars,
                        stop_reason="enhance_delivery_forced",
                        self_repair_turn=self_repair_turns,
                        tool_calls=tool_call_usage, tags=tags,
                        dropped_calls=dropped_calls,
                    )
                    # Look for emit_card in the advertised tools (old name no longer advertised)
                    offer_schema = next(
                        (t for t in tools
                         if t.get("name") == "emit_card"), None)
                    if offer_schema is not None:
                        turn_idx += 1
                        history.append(Message(
                            role="user",
                            content=_DELIVERY_DIRECTIVE.format(vid=_vid)))
                        try:
                            resp = await self._client.messages.create(
                                model=self.model, max_tokens=512,
                                system=cached_system,
                                messages=_with_history_breakpoint(
                                    _to_anthropic_messages(history)),
                                tools=[offer_schema],
                                tool_choice={"type": "tool",
                                             "name": "emit_card"},
                            )
                            tu = next((b for b in resp.content
                                       if getattr(b, "type", None) == "tool_use"),
                                      None)
                            oargs = dict(getattr(tu, "input", {}) or {}) if tu else {}
                            # Ensure card_type is set to enhancement_offer
                            if not oargs.get("card_type"):
                                oargs["card_type"] = "enhancement_offer"
                            # Wrap payload with verified_id if using enhancement_offer
                            if oargs.get("card_type") == "enhancement_offer":
                                if not isinstance(oargs.get("payload"), dict):
                                    oargs["payload"] = {}
                                oargs["payload"]["verified_id"] = _vid
                            call_id = getattr(tu, "id", None) or _uuid.uuid4().hex[:8]
                            yield ToolUseEvent(
                                name="emit_card", arguments=oargs,
                                call_id=call_id,
                                tier=_tier_for("emit_card", oargs))
                            oresult = _guarded_dispatch("emit_card", oargs)
                            yield ToolResultEvent(
                                call_id=call_id, result=oresult)
                        except Exception:
                            import logging
                            logging.exception("forced enhance delivery failed")
                    yield DoneEvent(stop_reason="end_turn")
                    return

                # Create-delivery guard -- verify_playbook passed but no offer
                # card followed. Mirrors the enhance block above; overrides
                # `yaml` so only verified bytes can reach the card.
                _vyaml = _create_delivery.outstanding(allowed_names)
                if _vyaml is not None:
                    _create_delivery.mark_forced()
                    yield UsageEvent(
                        session_id=session_id, turn=turn_idx, model=self.model,
                        input_tokens=input_tok, output_tokens=output_tok,
                        cache_read=cache_hit, cache_write=cache_write,
                        prefix_fingerprint=_prefix_fp,
                        history_chars=history_chars,
                        stop_reason="create_delivery_forced",
                        self_repair_turn=self_repair_turns,
                        tool_calls=tool_call_usage, tags=tags,
                        dropped_calls=dropped_calls,
                    )
                    # Look for emit_card in the advertised tools (old name no longer advertised)
                    offer_schema = next(
                        (t for t in tools
                         if t.get("name") == "emit_card"), None)
                    if offer_schema is not None:
                        turn_idx += 1
                        history.append(Message(
                            role="user", content=_CREATE_DELIVERY_DIRECTIVE))
                        try:
                            resp = await self._client.messages.create(
                                model=self.model, max_tokens=512,
                                system=cached_system,
                                messages=_with_history_breakpoint(
                                    _to_anthropic_messages(history)),
                                tools=[offer_schema],
                                tool_choice={"type": "tool",
                                             "name": "emit_card"},
                            )
                            tu = next((b for b in resp.content
                                       if getattr(b, "type", None) == "tool_use"),
                                      None)
                            oargs = dict(getattr(tu, "input", {}) or {}) if tu else {}
                            # Ensure card_type is set to playbook_offer
                            if not oargs.get("card_type"):
                                oargs["card_type"] = "playbook_offer"
                            # Wrap arguments in payload for emit_card
                            if not isinstance(oargs.get("payload"), dict):
                                oargs["payload"] = {}
                            payload = oargs["payload"]
                            payload["yaml"] = _vyaml
                            if not str(payload.get("id") or "").strip():
                                payload["id"] = f"offer-{_uuid.uuid4().hex[:8]}"
                            if not str(payload.get("summary") or "").strip():
                                payload["summary"] = (
                                    _create_delivery.summary_hint
                                    or "Playbook drafted and verified."
                                )
                            call_id = getattr(tu, "id", None) or _uuid.uuid4().hex[:8]
                            yield ToolUseEvent(
                                name="emit_card", arguments=oargs,
                                call_id=call_id,
                                tier=_tier_for("emit_card", oargs))
                            oresult = _guarded_dispatch("emit_card", oargs)
                            yield ToolResultEvent(
                                call_id=call_id, result=oresult)
                        except Exception:
                            import logging
                            logging.exception("forced create delivery failed")
                    yield DoneEvent(stop_reason="end_turn")
                    return
                # Verdict guard: a triage turn that gathered evidence and never
                # concluded gets ONE forced emit_card(verdict) round, citing
                # this turn's evidence ids (the citation gate checks them).
                if _verdict_guard.outstanding(allowed_names):
                    _verdict_guard.mark_forced()
                    yield UsageEvent(
                        session_id=session_id, turn=turn_idx, model=self.model,
                        input_tokens=input_tok, output_tokens=output_tok,
                        cache_read=cache_hit, cache_write=cache_write,
                        prefix_fingerprint=_prefix_fp,
                        history_chars=history_chars,
                        stop_reason="verdict_guard_forced",
                        self_repair_turn=self_repair_turns,
                        tool_calls=tool_call_usage, tags=tags,
                        dropped_calls=dropped_calls,
                    )
                    from ..mcp_server._citation_validator import get_turn_evidence
                    from ._loop_helpers import is_verdict_evidence
                    evidence = get_turn_evidence()
                    registry = evidence.valid_ids() if evidence else {}
                    evidence_ids = [
                        eid for eid, info in registry.items()
                        if info.get("ok") is True
                        and is_verdict_evidence(info.get("name") or "")
                    ]
                    card_schema = next(
                        (t for t in tools if t.get("name") == "emit_card"), None)
                    if card_schema is not None:
                        turn_idx += 1
                        directive = verdict_directive(evidence_ids)
                        # One repair attempt -- see verdict_repair_directive.
                        for _attempt in range(2):
                            history.append(Message(role="user", content=directive))
                            try:
                                resp = await self._client.messages.create(
                                    model=self.model, max_tokens=2048,
                                    system=cached_system,
                                    messages=_with_history_breakpoint(
                                        _to_anthropic_messages(history)),
                                    tools=[card_schema],
                                    tool_choice={"type": "tool", "name": "emit_card"},
                                )
                                tu = next((b for b in resp.content
                                           if getattr(b, "type", None) == "tool_use"),
                                          None)
                                oargs = dict(getattr(tu, "input", {}) or {}) if tu else {}
                                if not oargs.get("card_type"):
                                    oargs["card_type"] = "verdict"
                                if not isinstance(oargs.get("payload"), dict):
                                    oargs["payload"] = {}
                                call_id = getattr(tu, "id", None) or _uuid.uuid4().hex[:8]
                                yield ToolUseEvent(
                                    name="emit_card", arguments=oargs, call_id=call_id,
                                    tier=_tier_for("emit_card", oargs))
                                oresult = _guarded_dispatch("emit_card", oargs)
                                yield ToolResultEvent(call_id=call_id, result=oresult)
                                if not (isinstance(oresult, dict)
                                        and oresult.get("ok") is False):
                                    break
                                directive = verdict_repair_directive(oresult, oargs)
                            except Exception:
                                import logging
                                logging.exception("forced verdict delivery failed")
                                break
                    yield DoneEvent(stop_reason="end_turn")
                    return
                # P1 -- forced-assessment guarantee. The turn ran tools but
                # the final assistant block has no text (only tool_use /
                # emitted cards). Emit the usage for the round we paid for,
                # then force ONE no-tools round so the analyst gets a written
                # close instead of silence. Capped via `assessment_forced`.
                final_text = "".join(
                    b.get("text", "") for b in assistant_blocks
                    if b.get("type") == "text"
                ).strip()
                if not final_text and any_tools_run and not assessment_forced:
                    assessment_forced = True
                    yield UsageEvent(
                        session_id=session_id, turn=turn_idx, model=self.model,
                        input_tokens=input_tok, output_tokens=output_tok,
                        cache_read=cache_hit, cache_write=cache_write,
                        prefix_fingerprint=_prefix_fp,
                        history_chars=history_chars,
                        stop_reason="assessment_forced",
                        self_repair_turn=self_repair_turns,
                        tool_calls=tool_call_usage, tags=tags,
                        dropped_calls=dropped_calls,
                    )
                    turn_idx += 1
                    async for ev in self._wrapup_call(
                        history=history, directive=_ASSESSMENT_DIRECTIVE,
                        cached_system=cached_system, session_id=session_id,
                        turn_idx=turn_idx, tags=tags,
                        self_repair_turns=self_repair_turns,
                        stop_reason_label="assessment_summary",
                    ):
                        yield ev
                    yield DoneEvent(stop_reason=final.stop_reason or "end_turn")
                    return
                yield UsageEvent(
                    session_id=session_id, turn=turn_idx, model=self.model,
                    input_tokens=input_tok, output_tokens=output_tok,
                    cache_read=cache_hit, cache_write=cache_write,
                    prefix_fingerprint=_prefix_fp,
                    history_chars=history_chars,
                    stop_reason=final.stop_reason or "",
                    self_repair_turn=self_repair_turns,
                    tool_calls=tool_call_usage, tags=tags,
                    dropped_calls=dropped_calls,
                )
                yield DoneEvent(stop_reason=final.stop_reason or "end_turn")
                return

            # Execute tools, emit events, append tool_result message.
            # If any call returns a pending_approval envelope, we
            # stash the suspension state and bail out for this turn.
            # The chat layer resumes once the user decides.
            tool_result_blocks: list[dict[str, Any]] = []
            pending: ApprovalRequestEvent | None = None
            pending_remaining: list[tuple[str, str, dict[str, Any]]] = []

            def _record_result(name: str, args: dict[str, Any], result: Any,
                               duration_ms: int | None = None, call_id: str | None = None) -> dict[str, Any]:
                # Build the tool_result block + fold usage. Returns the block
                # so callers can both append it and (for parallel calls) keep
                # tool_use order intact.
                _delivery.note_result(name, args, result)
                _create_delivery.note_result(name, args, result)
                _verdict_guard.note_result(name, args, result)
                _promise_guard.note_result(name, args, result)
                _progress.note_result(name, args, result)
                _build_progress.note_result(name, args, result)
                # Register the tool result for citation validation
                if call_id:
                    success = not _is_error_result(result)
                    from ..mcp_server._citation_validator import register_tool_result
                    register_tool_result(call_id, name, success)
                content_str = _stringify(result)
                block = {
                    "type": "tool_result",
                    "tool_use_id": "",  # filled by caller
                    "content": content_str,
                    "is_error": _is_error_result(result),
                }
                try:
                    args_chars = len(json.dumps(args, default=str))
                except Exception:
                    args_chars = 0
                tool_call_usage.append(ToolCallUsage(
                    name=name, args_chars=args_chars,
                    result_chars=len(content_str),
                    duration_ms=duration_ms,
                ))
                return block

            # §2.8 -- Parallel read-only dispatch. The first tier-3+ call (if
            # any) is the approval boundary; by construction every call before
            # it is read-only (tier ≤ 2), so those are safe to fan out
            # concurrently. The approval call itself + everything after it
            # route through the sequential suspend path below, unchanged.
            tiers = [_tier_for(name, args) for (_cid, name, args) in tool_calls]
            approval_idx = next(
                (idx for idx, t in enumerate(tiers) if t >= 3), len(tool_calls)
            )
            parallel_batch = tool_calls[:approval_idx]

            # Emit ToolUseEvents up front so the stream preserves tool_use
            # order even though execution is concurrent.
            for (call_id, name, args), tier in zip(parallel_batch, tiers):
                yield ToolUseEvent(
                    name=name, arguments=args, call_id=call_id, tier=tier,
                )
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
                # Emit results + build tool_result blocks in tool_use order.
                for (call_id, name, args), (result, dur_ms) in zip(parallel_batch, batch_results):
                    yield ToolResultEvent(call_id=call_id, result=result, duration_ms=dur_ms)
                    block = _record_result(name, args, result, dur_ms, call_id=call_id)
                    block["tool_use_id"] = call_id
                    tool_result_blocks.append(block)

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
                    # The assistant turn (with this tool_use) is already
                    # appended to history above. Stash everything resume
                    # needs, including any earlier tool_result_blocks for
                    # calls that resolved in this same turn, plus the
                    # tool_use_ids for calls we DIDN'T get to so resume
                    # can fill them with placeholder denials.
                    pending_remaining = list(tool_calls[i + 1:])
                    approval_id = result["approval_id"]
                    # Capture the current turn evidence so citations survive resume.
                    from ..mcp_server._citation_validator import get_turn_evidence
                    evidence = get_turn_evidence()
                    evidence_state = evidence.to_dict() if evidence else {}

                    suspended_session = _approvals.SuspendedSession(
                        approval_id=approval_id,
                        # The CHAT session id, not `session_id` -- that local
                        # is a per-stream trace id (uuid4().hex[:8]) used for
                        # telemetry correlation. Stashing it here wrote a value
                        # into suspended_sessions.session_id that could never
                        # join to chat_sessions, so the monitor's Pending panel
                        # showed an unresolvable session with a null intent and
                        # user, and list_active_sessions could never derive
                        # `waiting_approval` for any row.
                        session_id=(tags or {}).get("session_id") or session_id,
                        tool=name,
                        tool_use_id=call_id,
                        args=args,
                        tier=int(result.get("tier", 3)),
                        history_snapshot=_to_anthropic_messages(history),
                        prior_tool_result_blocks=list(tool_result_blocks),
                        remaining_tool_calls=[
                            _approvals.SkippedToolCall(
                                call_id=cid, name=cn, args=ca,
                            )
                            for cid, cn, ca in pending_remaining
                        ],
                        system=system,
                        tags=dict(tags),
                        summary=result.get("summary"),
                        # the advertised slice -- resume re-enters with it
                        tools=list(tools or []),
                        turn_evidence_state=evidence_state,
                    )
                    # Phase 3.1: HMAC-bind the session to its args before
                    # stashing, so store tampering is detected on resume.
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

                # Flag failures (via `_record_result` → `_is_error_result`)
                # so the model's self-repair loop branches on a real error
                # signal instead of guessing from prose.
                yield ToolResultEvent(call_id=call_id, result=result, duration_ms=dur_ms)
                block = _record_result(name, args, result, dur_ms, call_id=call_id)
                block["tool_use_id"] = call_id
                tool_result_blocks.append(block)

            if pending is not None:
                # Suspend: emit the approval request + usage for the
                # round-trip we already paid for, then a DoneEvent with
                # a sentinel stop_reason so the chat layer knows this
                # isn't a normal end-of-turn.
                yield pending
                yield UsageEvent(
                    session_id=session_id, turn=turn_idx, model=self.model,
                    input_tokens=input_tok, output_tokens=output_tok,
                    cache_read=cache_hit, cache_write=cache_write,
                    prefix_fingerprint=_prefix_fp,
                    history_chars=history_chars,
                    stop_reason="pending_approval",
                    self_repair_turn=self_repair_turns,
                    tool_calls=tool_call_usage, tags=tags,
                    dropped_calls=dropped_calls,
                )
                yield DoneEvent(stop_reason="pending_approval")
                return

            # TurnPlan item 3: state the shrinking budget in the soft window
            # before the cliff (the forced wrap-up round handles exhaustion).
            from ._loop_helpers import budget_note
            _bnote = budget_note(_turn + 1, _turn_budget) \
                if self.emulation.task_budget else ""
            if _bnote:
                tool_result_blocks.append(
                    {"type": "text", "text": f"[turn budget] {_bnote}"})
            history.append(Message(role="user", content=tool_result_blocks))
            any_tools_run = True
            yield UsageEvent(
                session_id=session_id, turn=turn_idx, model=self.model,
                input_tokens=input_tok, output_tokens=output_tok,
                cache_read=cache_hit, cache_write=cache_write,
                prefix_fingerprint=_prefix_fp,
                history_chars=history_chars,
                stop_reason=final.stop_reason or "tool_use",
                self_repair_turn=self_repair_turns,
                tool_calls=tool_call_usage, tags=tags,
                dropped_calls=dropped_calls,
            )

            # No progress (repetition / sustained failure): answer now rather
            # than spending the ceiling. See ProgressMeter.
            _stall = _progress.end_round()
            if _stall:
                turn_idx += 1
                async for ev in self._wrapup_call(
                    history=history, directive=stall_directive(_stall),
                    cached_system=cached_system, session_id=session_id,
                    turn_idx=turn_idx, tags=tags,
                    self_repair_turns=self_repair_turns,
                    stop_reason_label=f"stalled_{_stall}",
                    max_tokens=DEFAULT_MAX_OUTPUT_TOKENS,
                ):
                    yield ev
                yield DoneEvent(stop_reason="end_turn")
                return

        # Tool-turn budget exhausted. Two paths:
        #
        # 1. Nothing delivered (no YAML, no offer card): skip the budget-ask
        #    and force the wrap-up directive. The budget-ask asks "continue or
        #    deliver?" -- but "deliver" is the ONLY sane answer when the analyst
        #    has nothing, and a chat-sweep (or a distracted analyst) leaves the
        #    card unanswered, so the turn ends at awaiting_choice with nothing
        #    delivered. This is the build_plain_request_no_record 3/3 failure:
        #    the model burns 16 rounds on research and the budget-ask strands
        #    it. The wrapup_directive tells the model to stop researching and
        #    deliver from what it already knows -- one forced no-tools round.
        #
        # 2. Something IS delivered: the budget-ask is meaningful (the analyst
        #    might want more rounds to refine). Emit the choice card as before.
        from ._loop_helpers import (
            analyst_has_the_yaml,
            budget_ask_card,
            wrapup_directive,
        )
        # Message is a dataclass; analyst_has_the_yaml expects dicts. Convert.
        _hist_dicts = [
            {"role": m.role, "content": m.content} if hasattr(m, "role")
            else m for m in history
        ]
        if not analyst_has_the_yaml(_hist_dicts):
            _directive, _max_tok = wrapup_directive(history, _turn_budget)
            yield UsageEvent(
                session_id=session_id, turn=turn_idx, model=self.model,
                input_tokens=0, output_tokens=0,
                cache_read=0, cache_write=0,
                history_chars=0,
                stop_reason="max_tool_turns",
                self_repair_turn=self_repair_turns,
                tool_calls=[], tags=tags,
                dropped_calls=dropped_calls,
            )
            turn_idx += 1
            async for ev in self._wrapup_call(
                history=history, directive=_directive,
                cached_system=cached_system, session_id=session_id,
                turn_idx=turn_idx, tags=tags,
                self_repair_turns=self_repair_turns,
                stop_reason_label="max_tool_turns",
                max_tokens=_max_tok,
            ):
                yield ev
            yield DoneEvent(stop_reason="end_turn")
            return
        _card = budget_ask_card(_turn_budget)
        _card_result = dispatch("emit_choice_card", _card, _internal=True)
        yield ToolUseEvent(
            name="emit_choice_card", arguments=_card, call_id="_budget_ask",
            tier=0,
        )
        yield ToolResultEvent(call_id="_budget_ask", result=_card_result)
        yield DoneEvent(stop_reason="max_tool_turns")
        return


def _is_error_result(result: Any) -> bool:
    """True if a tool result represents a failure, for the wire
    `is_error` flag. Recognizes the canonical `{ok: false}` envelope
    (from `_err`) and a bare `{error: ...}` dict.

    Guard results (kind=='guard_redirect' or 'guard_defer') are steering, not
    errors, so they don't get flagged."""
    if not isinstance(result, dict):
        return False
    # Guard redirects and deferrals are steering, not errors
    if result.get("kind") in ("guard_redirect", "guard_defer"):
        return False
    return result.get("ok") is False or "error" in result


def _stringify(result: Any) -> str:
    import json

    if isinstance(result, str):
        return result
    try:
        from ._loop_helpers import with_readable_dates
        return json.dumps(with_readable_dates(result), default=str)
    except Exception:
        return str(result)


