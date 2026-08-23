"""A1.3: page steering is a RANKING in the prompt, never a slice of `tools[]`.

The defect being fixed is a cache one. Tool definitions sit in the cacheable
prefix (`tools` → `system` → `messages`), so a per-page subtraction discards
the whole prefix -- the system prompt behind it included -- every time the
analyst changes page. Naming the page's preferred tools in the prior steers
just as well and leaves the prefix alone.

So the load-bearing assertion here is a NEGATIVE one: `preferred_tools` must
not change the advertised array.
"""
from __future__ import annotations

from fsr_playbooks.llm.turn_plan import TurnContext, plan_turn

def _plan(**ctx_kwargs):
    # `plan_turn` builds the FULL consolidated surface itself -- it does no
    # slicing at all, which is precisely the invariant these tests defend.
    return plan_turn(intent="investigate", context=TurnContext(**ctx_kwargs))


def test_preferred_tools_are_named_in_the_prior() -> None:
    plan = _plan(page="alert record #37326",
                 preferred_tools=("investigate_alert", "find_connector"))
    assert "`investigate_alert`" in plan.prompt
    assert "`find_connector`" in plan.prompt
    # Ranked, not alphabetised: the page's order is the steer.
    assert plan.prompt.index("`investigate_alert`") < plan.prompt.index("`find_connector`")


def test_ranking_does_not_subtract_from_the_advertised_array() -> None:
    """The whole point. Everything stays advertised; only the prose moves."""
    ranked = _plan(page="alert record #37326",
                   preferred_tools=("investigate_alert",))
    plain = _plan(page="alert record #37326")
    assert [t["name"] for t in ranked.tools] == [t["name"] for t in plain.tools]
    assert ranked.tools == plain.tools


def test_the_prior_says_the_ranking_is_not_a_restriction() -> None:
    """A model that reads the ranking as a whitelist would refuse work the
    analyst asked for -- the same failure the intent wall had before Phase 3."""
    plan = _plan(preferred_tools=("investigate_alert",))
    assert "not a restriction" in plan.prompt
    assert "full tool surface is available" in plan.prompt


def test_no_preference_says_nothing() -> None:
    plan = _plan(page="playbook editor")
    assert "best first" not in plan.prompt


def test_failsafe_plan_states_no_preference() -> None:
    """A failsafe plan asserts no page facts -- a ranking is a page fact."""
    from fsr_playbooks.llm.turn_plan import TurnPlan
    assert TurnPlan.failsafe("no module").context.preferred_tools == ()
