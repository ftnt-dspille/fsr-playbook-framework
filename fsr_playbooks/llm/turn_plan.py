"""TurnPlan -- the single per-turn resolution point (redesign Phase 2).

Phase 1 consolidated the tool *surface*; this module consolidates the
*routing*. Historically a turn's prompt, tool slice, and tier behavior were
resolved at three independent points that never saw each other (intent
derivation, tool slicing, prompt layering -- see the SOC Assistant Design
Assessment §1a). The consequences were structural: the model could not reach a
capability the router didn't anticipate, affordances appeared and disappeared
opaquely, and a request that crossed the triage/build boundary dead-ended in
prose instead of a ``capability_gap`` card.

``plan_turn()`` replaces that with ONE function returning ONE object:

    TurnPlan(prompt, tools, tier_policy, budget, gates)

and three deliberate inversions of the old design:

1. **The full consolidated surface is advertised.** Intent no longer removes
   tools from the model's list; it becomes a *stated prior* in the prompt
   ("you are on an alert record") that the model may override when the
   analyst's ask says otherwise.
2. **The gate moves to dispatch.** What the old slices protected is enforced
   where it matters -- at the call -- via tier policy (already declared on
   every description since Phase 1) plus a small set of *affordance* gates
   keyed on real page state (e.g. no open playbook => nothing to patch), not
   on intent. A gated call returns a structured refusal that names the gap
   and points at ``emit_card(card_type='capability_gap')`` -- fail closed
   with a path forward, never a silent removal.
3. **The model is told its constraints.** The prompt states the tool budget,
   the approval-tier contract, and the never-dead-end rule up front, so
   approval is a plan and running out of turns ends in a graceful close.

Hosts install the plan for the duration of a turn with ``set_turn_plan()``
(ContextVar, same pattern as the read-only-turn gate in ``tools.py``);
``dispatch`` consults the active plan's gates. A host that never installs a
plan sees zero behavior change (fail-open, like every other turn-scoped gate).
"""
from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from .intents import (
    classify_message,
    gate_directive,
    load_intent_prompt,
    resolve_intent,
)

# Default hard ceiling mirrors the historical connector loop cap. The plan
# turns it from an invisible cliff into a stated budget + graceful close.
DEFAULT_MAX_TOOL_TURNS = 16
# When this many calls remain, budget_note() starts telling the model to
# wrap up instead of letting the ceiling truncate it mid-thought.
SOFT_CLOSE_REMAINING = 3


@dataclass(frozen=True)
class TurnBudget:
    """The turn's tool-call budget, stated to the model instead of hidden."""

    max_tool_turns: int = DEFAULT_MAX_TOOL_TURNS
    soft_close_remaining: int = SOFT_CLOSE_REMAINING

    def remaining(self, calls_used: int) -> int:
        return max(0, self.max_tool_turns - calls_used)

    def note(self, calls_used: int) -> str:
        """A mid-loop nudge for the host to inject once the budget runs low.

        Empty while there is headroom; a wrap-up directive inside the soft
        window; a hard close order at zero."""
        left = self.remaining(calls_used)
        if left == 0:
            return (
                "Tool budget exhausted. Do not call more tools. Close the "
                "turn now: summarize what was established, and if the task "
                "is unfinished, say exactly what remains and how to resume."
            )
        if left <= self.soft_close_remaining:
            return (
                f"{left} tool call{'s' if left != 1 else ''} left this turn "
                "-- wrap up. Prefer delivering a result (a card or a "
                "conclusion) over starting a new line of investigation."
            )
        return ""


# Card types whose accept-path writes to the OPEN playbook. With no playbook
# open there is nothing to patch/enhance, so the affordance gate refuses them
# at dispatch (still advertised -- the refusal teaches, removal never did).
_OPEN_PLAYBOOK_CARD_TYPES = frozenset({"patch_proposal", "enhancement_offer"})
# Direct (pre-union) emitters for the same frontier, kept in lockstep with
# intents.ENHANCE_ONLY_TOOLS + emit_patch_proposal.
_OPEN_PLAYBOOK_TOOLS = frozenset({
    "emit_patch_proposal", "emit_enhancement_offer", "verify_enhancement",
})


@dataclass(frozen=True)
class TurnContext:
    """The real page/session state the plan grounds on -- facts, not intent."""

    page: str | None = None            # e.g. "alert record #37326", "playbook editor"
    has_open_playbook: bool = False
    has_trace: bool = False            # a triage transcript exists to bottle
    scenario_title: str | None = None


@dataclass(frozen=True)
class TurnPlan:
    """Everything a host needs to run one turn, resolved in one place."""

    intent: str
    prompt: str
    tools: list[dict[str, Any]] = field(default_factory=list)
    tier_policy: dict[str, int] = field(default_factory=dict)
    budget: TurnBudget = field(default_factory=TurnBudget)
    context: TurnContext = field(default_factory=TurnContext)

    def gate_refusal(self, name: str, args: dict[str, Any] | None) -> dict[str, Any] | None:
        """The dispatch-level affordance gate.

        Returns a structured refusal dict when the call is not afforded by the
        current page state, else None. Refusals fail CLOSED with a visible path
        forward -- the model is told to name the gap via
        ``emit_card(card_type='capability_gap')`` rather than dead-ending.
        """
        gated = name in _OPEN_PLAYBOOK_TOOLS
        if name == "emit_card":
            gated = (args or {}).get("card_type") in _OPEN_PLAYBOOK_CARD_TYPES
        if gated and not self.context.has_open_playbook:
            return {
                "ok": False,
                "code": "not_afforded",
                "error": (
                    "There is no open playbook in this session, so there is "
                    "nothing to patch or enhance. If the analyst's request "
                    "needs an open playbook, say which one to open; if the "
                    "capability they asked for doesn't exist here, emit_card("
                    "card_type='capability_gap', ...) naming the gap and the "
                    "closest available path -- do not end in prose asking "
                    "them to advise."
                ),
            }
        return None


def _context_prior(intent: str, ctx: TurnContext) -> str:
    facts = []
    if ctx.page:
        facts.append(f"the analyst is on {ctx.page}")
    if ctx.scenario_title:
        facts.append(f"the case is: {ctx.scenario_title}")
    if ctx.has_open_playbook:
        facts.append("a playbook is open in the editor")
    if ctx.has_trace:
        facts.append(
            "this session already carries an investigation trace "
            "(build_playbook_from_trace can bottle it directly)"
        )
    stated = "; ".join(facts) if facts else "no page state was provided"
    return (
        "\n\n## Turn context (a prior, not a cage)\n"
        f"Working prior: **{intent}**. Page state: {stated}. The full tool "
        "surface is available to you regardless of this prior -- if the "
        "analyst's request crosses into other work (triage from the editor, "
        "authoring from an alert), follow the request, not the prior."
    )


def _constraints(budget: TurnBudget) -> str:
    return (
        "\n\n## Constraints (stated up front)\n"
        f"- Tool budget: at most {budget.max_tool_turns} tool calls this "
        "turn. When told few calls remain, wrap up -- deliver a result, "
        "don't open a new line of investigation.\n"
        "- Every tool's description declares its Approval tier. A tier-3 "
        "call suspends this turn for analyst approval -- that is normal; "
        "plan for it rather than avoiding the action.\n"
        "- Never dead-end the analyst. If the request cannot be fulfilled "
        "with the capabilities available, emit_card("
        "card_type='capability_gap', ...) naming exactly what is missing "
        "and the closest path forward. A prose close like 'this may not be "
        "feasible, please advise' is a failure."
    )


def plan_turn(
    intent: Any = None,
    *,
    context: TurnContext | None = None,
    message: str | None = None,
    max_tool_turns: int = DEFAULT_MAX_TOOL_TURNS,
) -> TurnPlan:
    """Resolve one turn: prompt + tools + tier policy + budget, in one place."""
    from .tools import TOOL_TIERS, anthropic_tools

    intent = resolve_intent(intent)
    ctx = context or TurnContext()
    budget = TurnBudget(max_tool_turns=max_tool_turns)

    tools = anthropic_tools()  # the FULL consolidated surface -- no slicing
    tier_policy = {t["name"]: TOOL_TIERS.get(t["name"], 0) for t in tools}

    prompt = load_intent_prompt(intent)
    prompt += _context_prior(intent, ctx)
    prompt += _constraints(budget)
    if message is not None:
        prompt += gate_directive(classify_message(message), ctx.scenario_title)

    return TurnPlan(
        intent=intent, prompt=prompt, tools=tools,
        tier_policy=tier_policy, budget=budget, context=ctx,
    )


# --- turn-scoped installation (same pattern as set_read_only_turn) ---------

_ACTIVE_PLAN: ContextVar[TurnPlan | None] = ContextVar("_active_turn_plan", default=None)


def set_turn_plan(plan: TurnPlan | None) -> Any:
    """Install the plan for this turn; dispatch consults its gates.
    Returns a token for ``reset_turn_plan``."""
    return _ACTIVE_PLAN.set(plan)


def reset_turn_plan(token: Any) -> None:
    """Undo ``set_turn_plan``. Never raises (turn-boundary cleanup)."""
    try:
        _ACTIVE_PLAN.reset(token)
    except (RuntimeError, ValueError, LookupError):
        _ACTIVE_PLAN.set(None)


def active_turn_plan() -> TurnPlan | None:
    try:
        return _ACTIVE_PLAN.get()
    except LookupError:  # pragma: no cover - defensive
        return None


__all__ = [
    "TurnPlan", "TurnBudget", "TurnContext", "plan_turn",
    "set_turn_plan", "reset_turn_plan", "active_turn_plan",
    "DEFAULT_MAX_TOOL_TURNS", "SOFT_CLOSE_REMAINING",
]
