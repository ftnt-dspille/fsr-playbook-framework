"""The agent loop, written once.

Every provider used to carry its own copy of this loop -- tool dispatch, the
approval boundary, the repeated-error and intent-slice guards, self-repair,
the delivery guards, the wrap-up rounds -- and the copies drifted: a guard
fixed in one provider stayed broken in the other, and the difference then read
as a model difference. The loop now lives here and a provider supplies only its
wire format through a `WireTurn` (one per stream) plus a handful of methods:

    precheck()                  -> error text or None
    open_turn(system, messages, tools, turn_budget) -> WireTurn
    rehydrate(suspended, outcomes) -> list[Message]   (resume after approval)
    contract_stop(raw_stop)     -> the connector's stop_reason vocabulary
    friendly_error(exc)         -> user-readable text for a failed request
    label, model, max_output_tokens, emulation, _approval_gateway

Nothing a provider supplies decides behaviour. If a rule needs to differ by
provider, it is a wire-format fact and belongs in the WireTurn; everything else
belongs here, where it applies to all of them.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid as _uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from . import approvals as _approvals
from ._loop_helpers import (
    DEFAULT_MAX_OUTPUT_TOKENS,
    EMPTY_WRAPUP_TEXT,
    FAILED_EDIT_DIRECTIVE,
    MAX_PARALLEL_TOOLS,
    MAX_SELF_REPAIR_TURNS,
    MAX_TOOL_TURNS,
    STREAM_TIMEOUT_SECS,
    UNATTENDED_CONTAIN_DIRECTIVE,
    UNVERIFIED_DRAFT_DIRECTIVE,
    BuildProgressGuard,
    ContainmentFollowThrough,
    CreateDeliveryGuard,
    EnhanceDeliveryGuard,
    ProgressMeter,
    PromisedActionGuard,
    TriageDiscipline,
    VerdictDeliveryGuard,
    _effective_tool_name,
    analyst_has_the_yaml,
    budget_ask_card,
    budget_note,
    compile_errors,
    drain_with_idle_timeout,
    evidence_id_line,
    extract_yaml_block,
    is_authoring_slice,
    is_verdict_evidence,
    latest_user_text,
    model_view,
    stall_directive,
    verdict_directive,
    verdict_repair_directive,
    with_readable_dates,
    wrapup_directive,
)
from .authorization import needs_approval
from .provider import (
    ApprovalRequestEvent,
    DoneEvent,
    DroppedCall,
    ErrorEvent,
    Event,
    Message,
    TextEvent,
    ToolCallUsage,
    ToolResultEvent,
    ToolUseEvent,
    UsageEvent,
)
from .tools import _resolve_tier as _tier_for
from .tools import dispatch

log = logging.getLogger(__name__)

#: Marks a tool call whose arguments the model emitted unparseably. It travels
#: in place of the args so every dispatch site bounces it identically, instead
#: of running the tool with `{}` -- a different call from the one the model
#: made, and one whose tier (read out of the args) can come out lower.
BAD_ARGS_KEY = "__bad_tool_arguments__"

#: P1 -- forced written assessment, when a turn ran tools but closed with no
#: narrative text.
ASSESSMENT_DIRECTIVE = (
    "You ran tools but did not write anything back to the analyst. Stop "
    "calling tools. In a short written assessment, tell the analyst: "
    "(1) what you found, (2) your severity / disposition verdict, and "
    "(3) the single recommended next action. Be concise and do not call tools."
)

#: Forced enhance-delivery round: a verify passed but no offer followed. The
#: round is pinned to `emit_card` and `verified_id` is overridden afterwards,
#: so a forced round can only deliver the bytes the gate cleared.
DELIVERY_DIRECTIVE = (
    "You verified an edit to the open playbook and it is ready to apply, but "
    "you have not delivered it. Call `emit_card(card_type='enhancement_offer', ...)` now with "
    "verified_id {vid!r} to apply it -- a written description is NOT a "
    "substitute for the call. Write the `summary` (in the payload) as one or two plain-English "
    "lines describing what the edit changes."
)

BUILD_PROGRESS_DIRECTIVE = (
    "You have researched the step types and connector operations but have not "
    "authored anything yet -- describing what you WILL build is not building it. "
    "Draft the full playbook YAML now and call `verify_playbook` with it, then "
    "deliver it with `emit_card(card_type='playbook_offer', ...)`. Do not end the turn with a plan."
)

UNVERIFIED_DRAFT_FAILED_DIRECTIVE = (
    "Your draft was checked but never verified, so it was verified for you and "
    "the result is above: it still has required fixes. Fix them and call "
    "`verify_playbook` with the corrected YAML; a passing verify is delivered "
    "to the analyst as a card. If something outside the playbook blocks it, "
    "emit_card(card_type='capability_gap', ...) naming it."
)

_SELF_REPAIR_PREFIX = (
    "The YAML you just produced doesn't compile. Fix the errors and emit a "
    "corrected fenced ```yaml block.\n\nErrors:\n"
)


# ───────────────────────────── wire seam ─────────────────────────────


@dataclass
class ToolCall:
    call_id: str
    name: str
    args: dict[str, Any]


@dataclass
class RoundUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read: int = 0
    cache_write: int = 0


@dataclass
class Round:
    """One model round-trip, already parsed out of the wire format.

    `tool_calls` holds only calls the loop may EXECUTE: a round that stopped
    for any reason other than tool use (the output cap above all, which cuts a
    call off mid-arguments) reports them in `dropped_calls` instead, and the
    WireTurn keeps them out of history -- replaying a call that never ran makes
    the next request a 400.
    """
    text: str
    tool_calls: list[ToolCall]
    stop_reason: str
    usage: RoundUsage
    dropped_calls: list[DroppedCall] = field(default_factory=list)
    #: Wire-format assistant message for history; None when the reply was
    #: empty (an empty message replayed fails the next request on both APIs).
    assistant: Any = None


@dataclass
class ToolOutcome:
    """One tool result as history needs it: content already rendered. The
    call's name and args ride along for wires that replay calls as text."""
    call_id: str
    content: str
    is_error: bool
    name: str = ""
    args: dict[str, Any] = field(default_factory=dict)


class WireTurn(Protocol):
    """One stream's wire state: the history in the provider's own shape and
    the requests that read it. Created per stream, so a provider instance
    shared across turns carries no per-turn state."""

    #: Tools as the caller advertised them, normalized to this wire. These
    #: (not the request-ready copy) are what a suspended session stores.
    plain_tools: list[dict[str, Any]]
    allowed_names: set[str]

    def before_round(self) -> None: ...
    def history_chars(self) -> int: ...
    def history_dicts(self) -> list[dict[str, Any]]: ...
    def stream_round(self) -> AsyncIterator[tuple[str, Any]]: ...
    def wrapup_round(self, max_tokens: int) -> AsyncIterator[tuple[str, Any]]: ...
    def has_tool(self, name: str) -> bool: ...
    async def forced_call(self, name: str) -> ToolCall | None: ...
    def append_assistant(self, rnd: Round) -> None: ...
    def append_user(self, text: str) -> None: ...
    def append_tool_call(self, call: ToolCall) -> None: ...
    def append_tool_results(self, outcomes: list[ToolOutcome], *,
                            note: str | None = None, note_role: str = "user") -> None: ...
    def result_wire(self, outcome: ToolOutcome) -> Any: ...
    def snapshot(self) -> list[Any]: ...
    def usage_extra(self) -> dict[str, Any]: ...


# ───────────────────────────── shared helpers ─────────────────────────────


def is_error_result(result: Any) -> bool:
    """True if a tool result is a failure. Guard redirects and deferrals are
    steering, not errors, so they don't count (tracker #60)."""
    if not isinstance(result, dict):
        return False
    if result.get("kind") in ("guard_redirect", "guard_defer"):
        return False
    return result.get("ok") is False or "error" in result


def stringify(result: Any) -> str:
    if isinstance(result, str):
        return result
    try:
        return json.dumps(with_readable_dates(result), default=str)
    except Exception:
        return str(result)


def parse_tool_arguments(raw: str) -> dict[str, Any]:
    """Arguments the model streamed as a JSON string, or a BAD_ARGS marker."""
    try:
        parsed = json.loads(raw or "{}")
    except Exception as exc:  # noqa: BLE001
        return {BAD_ARGS_KEY: f"arguments were not valid JSON ({exc})"}
    if not isinstance(parsed, dict):
        return {BAD_ARGS_KEY: ("arguments must be a JSON object, got "
                               f"{type(parsed).__name__}")}
    return parsed


def _offer_summary(hint: str, said: str, default: str) -> str:
    """The card's summary: the verify's own description when it gave one,
    else the first paragraph of what the model told the analyst."""
    if (hint or "").strip():
        return hint.strip()
    first = (said or "").strip().split("\n\n", 1)[0].strip()
    return first[:400] if first else default


def _call_signature(name: str, args: dict[str, Any]) -> str:
    try:
        return name + "|" + json.dumps(args, sort_keys=True, default=str)
    except Exception:
        return name + "|" + repr(args)


# ───────────────────────────── the loop ─────────────────────────────


async def run_loop(
    provider: Any,
    *,
    system: str,
    messages: list[Message],
    tools: list[dict[str, Any]] | None,
    tags: dict[str, Any] | None = None,
    case_state: Any = None,
    max_tool_turns: int | None = None,
) -> AsyncIterator[Event]:
    """Drive one agent turn on `provider`. See the module docstring."""
    problem = provider.precheck()
    if problem:
        yield ErrorEvent(message=problem)
        return

    from ..mcp_server._citation_validator import (
        clear_tool_registry,
        get_turn_evidence,
        register_tool_result,
    )
    clear_tool_registry()

    tags = tags or {}
    turn_budget = max_tool_turns or MAX_TOOL_TURNS
    w: WireTurn = provider.open_turn(system=system, messages=messages,
                                     tools=tools, turn_budget=turn_budget)
    allowed = w.allowed_names

    # Delivery and discipline guards. Each watches executed results and, at the
    # end of a turn, may ask for one more round; see each class in _loop_helpers.
    delivery = EnhanceDeliveryGuard()
    create = CreateDeliveryGuard()
    build = BuildProgressGuard()
    verdict = VerdictDeliveryGuard()
    promise = PromisedActionGuard()
    progress = ProgressMeter()
    contain = ContainmentFollowThrough(enabled=bool(tags.get("unattended")))
    observers = (delivery, create, build, verdict, contain, promise, progress)
    investigation = getattr(case_state, "investigation", None) if case_state is not None else None
    discipline = TriageDiscipline(
        state=investigation,
        capabilities=(getattr(case_state, "capabilities", None)
                      if case_state is not None else None),
        authoring=is_authoring_slice(allowed),
        # The analyst's own words are the only reliable carrier of an explicit
        # containment order -- see `_detect_analyst_order`.
        user_text=latest_user_text(messages),
    )
    # P4 -- repeated-error guard: an identical (name, args) call that already
    # failed this turn is not re-run.
    failed_signatures: set[str] = set()

    trace_id = _uuid.uuid4().hex[:8]   # telemetry correlation, not the chat id
    turn_idx = 0
    self_repair_turns = 0
    any_tools_run = False
    assessment_forced = False
    dropped_calls: list[DroppedCall] = []

    def guarded_dispatch(name: str, args: dict[str, Any]) -> Any:
        if isinstance(args, dict) and BAD_ARGS_KEY in args:
            return {
                "ok": False, "code": "bad_tool_arguments",
                "message": (f"{name}: {args[BAD_ARGS_KEY]}. Re-issue the call "
                            f"with a single valid JSON object as the arguments."),
                "suggestions": [],
            }
        # Defense-in-depth for the intent tool-slice (llm/intents.py): dispatch
        # runs ANY tool name, so refuse names the caller did not advertise.
        if name not in allowed:
            return {
                "ok": False,
                "error": (f"Tool '{name}' is not available in this session: the "
                          f"current task intent does not permit it. Not executed."),
            }
        sig = _call_signature(name, args)
        if sig in failed_signatures:
            return {
                "ok": False,
                "repeated_call_guard": True,
                "error": (
                    f"This exact call to `{name}` already failed earlier this "
                    f"turn and was NOT re-run. Do not retry the identical "
                    f"arguments -- change the inputs (e.g. resolve the "
                    f"correct id from the record's sourcedata) or stop and "
                    f"report the blocker in your assessment."
                ),
            }
        guard = discipline.evaluate(name, args)
        if guard is not None:
            # Terminal guards (call-once) can never succeed; remembering the
            # signature makes an identical re-call hit the firmer
            # repeated_call_guard. The hunt floor is NOT terminal.
            if guard.get("call_once_guard"):
                failed_signatures.add(sig)
            return guard
        result = dispatch(name, args)
        discipline.note_result(name, args, result)
        if is_error_result(result):
            failed_signatures.add(sig)
        return result

    async def wrapup(directive: str, label: str,
                     max_tokens: int | None = None) -> AsyncIterator[Event]:
        """One forced no-tools round. Failures are logged and swallowed; the
        caller still emits the terminal DoneEvent, so the turn never hangs."""
        w.append_user(directive)
        history_chars = w.history_chars()
        try:
            usage = RoundUsage()
            said = False
            async for kind, payload in w.wrapup_round(
                    max_tokens or provider.max_output_tokens):
                if kind == "text":
                    said = said or bool((payload or "").strip())
                    yield TextEvent(text=payload)
                else:
                    usage = payload
            if not said:
                yield TextEvent(text=EMPTY_WRAPUP_TEXT)
            yield UsageEvent(
                session_id=trace_id, turn=turn_idx, model=provider.model,
                input_tokens=usage.input_tokens, output_tokens=usage.output_tokens,
                cache_read=usage.cache_read, cache_write=usage.cache_write,
                history_chars=history_chars, stop_reason=label,
                self_repair_turn=self_repair_turns, tool_calls=[], tags=tags,
                **w.usage_extra(),
            )
        except Exception:
            log.exception("%s call failed", label)
            yield ErrorEvent(message="hit max tool budget; summary failed -- see history above")

    async def loop_call(name: str, args: dict[str, Any], out: list[Any],
                        tcu: list[ToolCallUsage]) -> AsyncIterator[Event]:
        """A call the LOOP makes, not the model: delivering what a verify
        already blessed, or verifying a draft the model checked and left.
        Runs through the same dispatch and observers as a model call, so the
        transcript, the cards and the guards cannot tell the difference.
        Appends `(call, result, outcome)` to `out`."""
        call = ToolCall(f"loop_{_uuid.uuid4().hex[:8]}", name, args)
        yield ToolUseEvent(name=name, arguments=args, call_id=call.call_id,
                           tier=_tier_for(name, args))
        t0 = time.perf_counter()
        result = await asyncio.to_thread(guarded_dispatch, name, args)
        dur_ms = int((time.perf_counter() - t0) * 1000)
        yield ToolResultEvent(call_id=call.call_id, result=result, duration_ms=dur_ms)
        out.append((call, result, record(call, result, dur_ms, tcu)))

    def record(call: ToolCall, result: Any, duration_ms: int | None,
               tcu: list[ToolCallUsage]) -> ToolOutcome:
        success = not is_error_result(result)
        register_tool_result(call.call_id, call.name, success, call.args, result)
        content = (evidence_id_line(call.call_id, call.name, call.args, success)
                   + stringify(model_view(call.name, result)))
        try:
            args_chars = len(json.dumps(call.args, default=str))
        except Exception:
            args_chars = 0
        tcu.append(ToolCallUsage(name=call.name, args_chars=args_chars,
                                 result_chars=len(content), duration_ms=duration_ms))
        for o in observers:
            o.note_result(call.name, call.args, result)
        return ToolOutcome(call.call_id, content, not success, call.name, call.args)

    async def force_emit_card(default_type: str, fix: Callable[[dict[str, Any]], None],
                              out: list[Any]) -> AsyncIterator[Event]:
        """One round pinned to `emit_card`, so a delivery is a real tool call
        and not a sentence promising one. Appends `(call, args, result)` to
        `out`; `fix` repairs the arguments (and may override what the model
        sent -- only verified bytes may reach a card)."""
        call = await w.forced_call("emit_card")
        args = dict(call.args) if call else {}
        if not args.get("card_type"):
            args["card_type"] = default_type
        if not isinstance(args.get("payload"), dict):
            args["payload"] = {}
        fix(args)
        call_id = (call.call_id if call and call.call_id else _uuid.uuid4().hex[:8])
        yield ToolUseEvent(name="emit_card", arguments=args, call_id=call_id,
                           tier=_tier_for("emit_card", args))
        t0 = time.perf_counter()
        result = guarded_dispatch("emit_card", args)
        yield ToolResultEvent(call_id=call_id, result=result,
                              duration_ms=int((time.perf_counter() - t0) * 1000))
        out.append((ToolCall(call_id, "emit_card", args), result))

    for _turn in range(turn_budget):
        turn_idx += 1
        try:
            w.before_round()
        except Exception:
            log.exception("history compaction failed")   # never fails a turn
        history_chars = w.history_chars()

        rnd: Round | None = None
        try:
            async for kind, payload in drain_with_idle_timeout(
                    w.stream_round(), timeout=STREAM_TIMEOUT_SECS):
                if kind == "text":
                    yield TextEvent(text=payload)   # live delta
                else:
                    rnd = payload
        except asyncio.TimeoutError:
            log.warning("%s stream timed out after %ss", provider.label, STREAM_TIMEOUT_SECS)
            yield ErrorEvent(
                message=f"The request to {provider.label} timed out after "
                        f"{STREAM_TIMEOUT_SECS}s. The API may be slow or "
                        f"unreachable -- please try again.")
            return
        except Exception as exc:
            log.exception("%s stream failed", provider.label)
            yield ErrorEvent(message=provider.friendly_error(exc))
            return
        assert rnd is not None
        w.append_assistant(rnd)
        dropped_calls = rnd.dropped_calls
        tool_call_usage: list[ToolCallUsage] = []

        def usage_event(stop_reason: str, *, repair_delta: int = 0,
                        _rnd: Round = rnd, _hc: int = history_chars,
                        _tcu: list[ToolCallUsage] = tool_call_usage) -> UsageEvent:
            u = _rnd.usage
            return UsageEvent(
                session_id=trace_id, turn=turn_idx, model=provider.model,
                input_tokens=u.input_tokens, output_tokens=u.output_tokens,
                cache_read=u.cache_read, cache_write=u.cache_write,
                history_chars=_hc, stop_reason=stop_reason,
                self_repair_turn=self_repair_turns - repair_delta,
                tool_calls=_tcu, tags=tags, dropped_calls=_rnd.dropped_calls,
                **w.usage_extra(),
            )

        # ── terminal round: no executable tool calls ──────────────────
        if not rnd.tool_calls:
            if self_repair_turns < MAX_SELF_REPAIR_TURNS and rnd.text:
                yaml_block = extract_yaml_block(rnd.text)
                errors_text = compile_errors(yaml_block) if yaml_block else None
                if errors_text:
                    self_repair_turns += 1
                    w.append_user(_SELF_REPAIR_PREFIX + errors_text)
                    yield usage_event(rnd.stop_reason or "", repair_delta=1)
                    continue

            # A draft the model checked (validate/compile) and then left: the
            # loop runs the verify itself. A pass is delivered below with no
            # model round; a fail goes back to the model with its fixes.
            nudge: tuple[str, str] | None = None
            verified_by_loop = False
            if build.unverified_draft(allowed) and build.clean_draft and "verify_playbook" in allowed:
                build.mark_verify_forced()
                yield usage_event("unverified_draft_verified")
                out: list[Any] = []
                async for ev in loop_call("verify_playbook", {"yaml_text": build.clean_draft},
                                          out, tool_call_usage):
                    yield ev
                call, result, outcome = out[0]
                verified_by_loop = bool(isinstance(result, dict) and result.get("ready_to_push"))
                if not verified_by_loop:
                    w.append_tool_call(call)
                    w.append_tool_results([outcome])
                    nudge = ("unverified_draft_failed", UNVERIFIED_DRAFT_FAILED_DIRECTIVE)

            # Nudges: each appends ONE directive and lets the loop run on.
            said = None if (nudge or verified_by_loop) else promise.outstanding(rnd.text)
            if nudge or verified_by_loop:
                pass
            elif said:
                promise.mark_forced()
                nudge = ("promised_action_forced", promise.directive(said))
            elif build.outstanding(allowed):
                build.mark_forced()
                nudge = ("build_progress_forced", BUILD_PROGRESS_DIRECTIVE)
            elif build.unverified_draft(allowed):
                build.mark_verify_forced()
                nudge = ("unverified_draft_forced", UNVERIFIED_DRAFT_DIRECTIVE)
            else:
                nfix = delivery.failed_edit(allowed)
                if nfix:
                    delivery.mark_fix_forced()
                    nudge = ("failed_edit_forced", FAILED_EDIT_DIRECTIVE.format(n=nfix))
            if nudge:
                yield usage_event(nudge[0])
                turn_idx += 1
                w.append_user(nudge[1])
                continue

            # Delivery. A verify passed and the turn is ending without the offer
            # card: the loop delivers it with the bytes the verify blessed. No
            # model round -- there is nothing left for the model to decide, and
            # asking it to make the call only gave it another chance to narrate.
            vid = delivery.outstanding(allowed)
            offer: dict[str, Any] | None = None
            if vid is not None and w.has_tool("emit_card"):
                delivery.mark_forced()
                yield usage_event("enhance_delivery_forced")
                offer = {"card_type": "enhancement_offer", "payload": {
                    "id": f"offer-{_uuid.uuid4().hex[:8]}", "verified_id": vid,
                    "summary": _offer_summary(delivery.summary_hint, rnd.text,
                                              "The edit is verified and ready to apply.")}}
            elif create.outstanding(allowed) is not None and w.has_tool("emit_card"):
                create.mark_forced()
                yield usage_event("create_delivery_forced")
                payload = {"id": f"offer-{_uuid.uuid4().hex[:8]}",
                           "summary": _offer_summary(create.summary_hint, rnd.text,
                                                     "Playbook drafted and verified.")}
                create.apply_bytes(payload)
                offer = {"card_type": "playbook_offer", "payload": payload}
            if offer is not None:
                try:
                    async for ev in loop_call("emit_card", offer, [], tool_call_usage):
                        yield ev
                except Exception:
                    log.exception("loop delivery failed")
                yield DoneEvent(stop_reason="end_turn")
                return

            if contain.outstanding(allowed):
                contain.mark_fired()
                yield usage_event("containment_follow_through")
                turn_idx += 1
                w.append_user(UNATTENDED_CONTAIN_DIRECTIVE)
                continue

            # Verdict: a triage turn that gathered evidence and never concluded
            # gets one forced emit_card(verdict) round citing this turn's
            # evidence ids, with one repair attempt.
            if verdict.outstanding(allowed):
                verdict.mark_forced()
                yield usage_event("verdict_guard_forced")
                evidence = get_turn_evidence()
                registry = evidence.valid_ids() if evidence else {}
                evidence_ids = [
                    eid for eid, info in registry.items()
                    if info.get("ok") is True and is_verdict_evidence(info.get("name") or "")
                ]
                if w.has_tool("emit_card"):
                    turn_idx += 1
                    directive = verdict_directive(evidence_ids)
                    forced: tuple[ToolCall, Any] | None = None
                    for _attempt in range(2):
                        w.append_user(directive)
                        out: list[Any] = []
                        try:
                            async for ev in force_emit_card("verdict", lambda _a: None, out):
                                yield ev
                        except Exception:
                            log.exception("forced verdict delivery failed")
                            break
                        call, result = out[0]
                        contain.note_result("emit_card", call.args, result)
                        if not (isinstance(result, dict) and result.get("ok") is False):
                            forced = (call, result)
                            break
                        directive = verdict_repair_directive(result, call.args)
                    if forced is not None and contain.outstanding(allowed):
                        # The forced verdict is real history now, so the model
                        # stages containment against what it decided.
                        call, result = forced
                        w.append_tool_call(call)
                        w.append_tool_results(
                            [ToolOutcome(call.call_id, stringify(result), is_error_result(result),
                                         call.name, call.args)],
                            note=UNATTENDED_CONTAIN_DIRECTIVE, note_role="user")
                        contain.mark_fired()
                        # Marks that follow-through fired. Zero tokens: this
                        # round's usage was reported as verdict_guard_forced.
                        yield UsageEvent(
                            session_id=trace_id, turn=turn_idx, model=provider.model,
                            input_tokens=0, output_tokens=0, cache_read=0, cache_write=0,
                            history_chars=0, stop_reason="containment_follow_through",
                            self_repair_turn=self_repair_turns, tool_calls=[], tags=tags,
                            **w.usage_extra())
                        turn_idx += 1
                        continue
                yield DoneEvent(stop_reason="end_turn")
                return

            # P1 -- the turn ran tools but wrote nothing back: one no-tools round.
            if not rnd.text.strip() and any_tools_run and not assessment_forced:
                assessment_forced = True
                yield usage_event("assessment_forced")
                turn_idx += 1
                async for ev in wrapup(ASSESSMENT_DIRECTIVE, "assessment_summary"):
                    yield ev
                yield DoneEvent(stop_reason=provider.contract_stop(rnd.stop_reason))
                return

            yield usage_event(rnd.stop_reason or "")
            yield DoneEvent(stop_reason=provider.contract_stop(rnd.stop_reason))
            return

        # ── tool round: parallel up to the approval boundary ──────────
        calls = rnd.tool_calls
        tiers = [_tier_for(c.name, c.args) for c in calls]
        approval_idx = next((i for i, t in enumerate(tiers) if needs_approval(t)), len(calls))
        # Staging an action card ends the agent's half of the turn, which
        # TriageDiscipline enforces -- but only for calls evaluated after the
        # card's result is noted. Concurrent siblings would slip past it
        # (measured: a card at call 7 followed by four more that ran), so the
        # card closes the parallel batch and the rest go through the guard.
        card_idx = next((i for i, c in enumerate(calls)
                         if _effective_tool_name(c.name, c.args) == "emit_action_card"), None)
        batch_end = approval_idx if card_idx is None else min(approval_idx, card_idx + 1)
        parallel = calls[:batch_end]
        outcomes: list[ToolOutcome] = []

        for call, tier in zip(parallel, tiers):
            yield ToolUseEvent(name=call.name, arguments=call.args,
                               call_id=call.call_id, tier=tier)
        if parallel:
            sem = asyncio.Semaphore(MAX_PARALLEL_TOOLS)

            async def run_one(c: ToolCall) -> tuple[Any, int]:
                async with sem:
                    t0 = time.perf_counter()
                    res = await asyncio.to_thread(guarded_dispatch, c.name, c.args)
                    return res, int((time.perf_counter() - t0) * 1000)

            results = await asyncio.gather(*[run_one(c) for c in parallel])
            for call, (result, dur_ms) in zip(parallel, results):
                yield ToolResultEvent(call_id=call.call_id, result=result, duration_ms=dur_ms)
                outcomes.append(record(call, result, dur_ms, tool_call_usage))

        pending: ApprovalRequestEvent | None = None
        for i in range(batch_end, len(calls)):
            call = calls[i]
            yield ToolUseEvent(name=call.name, arguments=call.args,
                               call_id=call.call_id, tier=_tier_for(call.name, call.args))
            t0 = time.perf_counter()
            result = guarded_dispatch(call.name, call.args)
            dur_ms = int((time.perf_counter() - t0) * 1000)
            if isinstance(result, dict) and result.get("pending_approval"):
                pending = _suspend(provider, w, system, tags, trace_id, call, result,
                                   outcomes, calls[i + 1:], guarded_dispatch,
                                   get_turn_evidence)
                break
            yield ToolResultEvent(call_id=call.call_id, result=result, duration_ms=dur_ms)
            outcomes.append(record(call, result, dur_ms, tool_call_usage))

        if pending is not None:
            yield pending
            yield usage_event("pending_approval")
            yield DoneEvent(stop_reason="pending_approval")
            return

        # TurnPlan item 3: state the shrinking budget in the soft window before
        # the cliff (the forced wrap-up round handles exhaustion).
        note = budget_note(_turn + 1, turn_budget) if provider.emulation.task_budget else ""
        w.append_tool_results(outcomes, note=f"[turn budget] {note}" if note else None,
                              note_role="system")
        any_tools_run = True
        yield usage_event(rnd.stop_reason or "tool_use")

        # No progress (repetition / sustained failure): answer now rather than
        # spending the ceiling. See ProgressMeter.
        stall = progress.end_round()
        if stall:
            turn_idx += 1
            async for ev in wrapup(stall_directive(stall), f"stalled_{stall}",
                                   DEFAULT_MAX_OUTPUT_TOKENS):
                yield ev
            yield DoneEvent(stop_reason="end_turn")
            return

    # Tool-turn budget exhausted. When nothing has been delivered the model is
    # TOLD to deliver (a "continue or deliver?" card left unanswered strands the
    # turn with nothing); only when something is delivered is the choice real.
    if not analyst_has_the_yaml(w.history_dicts()):
        directive, max_tok = wrapup_directive(w.history_dicts(), turn_budget)
        # Zero tokens: the last round's usage was already reported.
        yield UsageEvent(
            session_id=trace_id, turn=turn_idx, model=provider.model,
            input_tokens=0, output_tokens=0, cache_read=0, cache_write=0,
            history_chars=0, stop_reason="max_tool_turns",
            self_repair_turn=self_repair_turns, tool_calls=[], tags=tags,
            dropped_calls=dropped_calls,
        )
        turn_idx += 1
        async for ev in wrapup(directive, "max_tool_turns", max_tok):
            yield ev
        yield DoneEvent(stop_reason="end_turn")
        return
    card = budget_ask_card(turn_budget)
    card_result = dispatch("emit_choice_card", card, _internal=True)
    yield ToolUseEvent(name="emit_choice_card", arguments=card,
                       call_id="_budget_ask", tier=0)
    yield ToolResultEvent(call_id="_budget_ask", result=card_result)
    yield DoneEvent(stop_reason="max_tool_turns")


def _suspend(provider: Any, w: WireTurn, system: str, tags: dict[str, Any],
             trace_id: str, call: ToolCall, result: dict[str, Any],
             outcomes: list[ToolOutcome], rest: list[ToolCall],
             guarded_dispatch: Callable[[str, dict[str, Any]], Any],
             get_turn_evidence: Callable[[], Any]) -> ApprovalRequestEvent:
    """Stash everything resume needs and return the approval event.

    The snapshot already holds the assistant message with this call; the
    outcomes are the calls that completed before the gate; `rest` are the ones
    the turn never reached (resume answers them with placeholders, since both
    APIs require a result for every call)."""
    # Gated calls right behind this one share its card.
    batch, remaining = _approvals.collect_batch(
        [(c.call_id, c.name, c.args) for c in rest], guarded_dispatch, _tier_for)
    evidence = get_turn_evidence()
    tier = int(result.get("tier", 3))
    suspended = _approvals.SuspendedSession(
        approval_id=result["approval_id"],
        # The CHAT session id, not the per-stream trace id: a trace id here can
        # never join to chat_sessions, so the monitor's Pending panel showed an
        # unresolvable session and no row could derive `waiting_approval`.
        session_id=tags.get("session_id") or trace_id,
        tool=call.name,
        tool_use_id=call.call_id,
        args=call.args,
        tier=tier,
        history_snapshot=w.snapshot(),
        prior_tool_result_blocks=[w.result_wire(o) for o in outcomes],
        remaining_tool_calls=[_approvals.SkippedToolCall(call_id=cid, name=cn, args=ca)
                              for cid, cn, ca in remaining],
        system=system,
        tags=dict(tags),
        summary=result.get("summary"),
        # The advertised slice, as advertised -- resume re-enters with it.
        tools=list(w.plain_tools),
        # Citations survive resume.
        turn_evidence_state=evidence.to_dict() if evidence else {},
        batch=batch,
    )
    # Phase 3.1: HMAC-bind the session to its args so store tampering is
    # detected on resume.
    _approvals.bind(suspended)
    gateway = getattr(provider, "_approval_gateway", None)
    if gateway is not None:
        gateway.stash(suspended)
    else:
        _approvals.stash(suspended)
    return ApprovalRequestEvent(
        approval_id=result["approval_id"],
        tool_use_id=call.call_id,
        tool=call.name,
        tier=tier,
        preview=result.get("preview") or {},
        args_hash=result.get("args_hash", ""),
        summary=result.get("summary"),
        requires_step_up=bool(result.get("requires_step_up")),
        batch=[b.card() for b in batch],
        policy=result.get("policy"),
    )


async def resume_loop(provider: Any, *, suspended: _approvals.SuspendedSession,
                      decision: str) -> AsyncIterator[Event]:
    """Resume a turn suspended on a tier-3+ approval.

    Re-dispatches the approved call (or synthesizes a denial), answers every
    other call of the suspended assistant message, then re-enters the
    provider's `stream()` with the rebuilt history."""
    # Fail closed on tamper / lost secret.
    if not _approvals.verify(suspended):
        yield ErrorEvent(message="Approval binding check failed -- the suspended action "
                                 "could not be verified and was not executed. Re-issue "
                                 "the request.")
        yield DoneEvent(stop_reason="approval_unverified")
        return

    if decision == "approve":
        # Bypass the gate this one time (see tools.dispatch). Off-loop: live MCP
        # tools call asyncio.run() internally, which raises on a running loop.
        resolved = await asyncio.to_thread(
            dispatch, suspended.tool, {**suspended.args, "_approved": True},
            _internal=True)
    else:
        resolved = {"ok": False, "code": "user_denied", "reason": "User denied the action."}

    # A NAMED synthetic tool_use before the result: the original lives in the
    # prior turn's transcript, and a renderer matching by call_id within this
    # turn would otherwise draw a nameless chip.
    yield ToolUseEvent(name=suspended.tool, arguments=dict(suspended.args),
                       call_id=suspended.tool_use_id, tier=suspended.tier, synthetic=True)
    yield ToolResultEvent(call_id=suspended.tool_use_id, result=resolved)
    # The rest of the card: the same decision, in order.
    batch_results = await asyncio.to_thread(_approvals.resolve_batch, suspended, decision)
    for b, res in batch_results:
        yield ToolUseEvent(name=b.name, arguments=dict(b.args),
                           call_id=b.call_id, tier=b.tier, synthetic=True)
        yield ToolResultEvent(call_id=b.call_id, result=res)

    outcomes = [ToolOutcome(suspended.tool_use_id, stringify(resolved),
                            is_error_result(resolved), suspended.tool, dict(suspended.args))]
    outcomes += [ToolOutcome(b.call_id, stringify(res), is_error_result(res), b.name, dict(b.args))
                 for b, res in batch_results]
    outcomes += [ToolOutcome(s.call_id, _approvals.superseded_result_json(), True,
                             s.name, dict(s.args or {}))
                 for s in suspended.remaining_tool_calls]

    async for ev in provider.stream(
        system=suspended.system,
        messages=provider.rehydrate(suspended, outcomes),
        # Old pickled sessions predate the field -- getattr, not attr.
        tools=list(getattr(suspended, "tools", None) or []),
        tags=suspended.tags,
    ):
        yield ev
