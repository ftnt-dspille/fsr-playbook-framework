"""The plan's capability ask must REACH the provider.

Rows 6-10 built four native primitives behind an explicit ask, and then nothing
asked -- which is `shipped-but-inert` with extra steps: every capability test
passed, the release shipped, and the deployed wire was byte-identical to the one
before the work. This file is the gate on the other half: `plan_turn` derives an
ask, and `run_agent_turn` hands THAT ask to the provider rather than deriving a
second one of its own.

The other half of the contract matters just as much: a caller with no plan
installed -- the framework's own MCP callers, and every test that builds a
provider by hand -- must keep the pre-seam behaviour.
"""
from __future__ import annotations

import asyncio

import pytest

from fsr_playbooks.llm.provider import (
    DoneEvent,
    ProviderCapabilities,
    TurnRequest,
)
from fsr_playbooks.llm.run_turn import run_agent_turn
from fsr_playbooks.llm.turn_plan import (
    REASONING_ENV,
    TurnBudget,
    _ask_for,
    plan_turn,
    reset_turn_plan,
    set_turn_plan,
)


class _RecordingProvider:
    """Captures the ask instead of serving it."""

    name = "recording"
    capabilities = ProviderCapabilities()

    def __init__(self) -> None:
        self.asked: TurnRequest | None = None

    def request(self, req: TurnRequest):
        from fsr_playbooks.llm.provider import HostEmulation
        self.asked = req
        return HostEmulation.resolve(self.capabilities, req)

    async def stream(self, **kwargs):
        yield DoneEvent()


def _drive(provider, **kwargs):
    return asyncio.run(run_agent_turn(
        provider=provider, system="s", messages=[], tools=[], **kwargs))


def test_the_plans_ask_is_what_reaches_the_provider() -> None:
    plan = plan_turn("build", max_tool_turns=7)
    p = _RecordingProvider()
    token = set_turn_plan(plan)
    try:
        _drive(p)
    finally:
        reset_turn_plan(token)
    assert p.asked is not None
    # The budget the plan computed and STATED in the prompt is the same number
    # handed over -- a provider pacing on a different budget than the one the
    # model was told about is worse than either alone.
    assert p.asked.max_tool_turns == 7
    assert str(plan.budget.max_tool_turns) in plan.prompt
    assert p.asked.prune_history is True


def test_no_plan_installed_keeps_the_pre_seam_ask() -> None:
    p = _RecordingProvider()
    _drive(p)
    assert p.asked is not None
    assert p.asked.reasoning is None
    assert p.asked.defer_tools is False
    # None, not True: nobody asked, so `shrink_history` runs exactly as before.
    assert p.asked.prune_history is None


def test_an_explicit_argument_still_overrides_the_plan() -> None:
    plan = plan_turn("build", max_tool_turns=7)
    p = _RecordingProvider()
    token = set_turn_plan(plan)
    try:
        _drive(p, max_tool_turns=3, reasoning="low")
    finally:
        reset_turn_plan(token)
    assert p.asked.max_tool_turns == 3
    assert p.asked.reasoning == "low"


def test_deferred_tools_are_asked_for_only_when_there_is_a_tail() -> None:
    """Asking with no `mcp_*` tools would put a search tool in the cached
    prefix to search a surface with nothing deferred behind it."""
    budget = TurnBudget(max_tool_turns=8)
    curated = [{"name": "find_connector"}, {"name": "validate_yaml"}]
    assert _ask_for(budget, curated).defer_tools is False
    with_tail = curated + [{"name": "mcp_soc__get_alert"}]
    assert _ask_for(budget, with_tail).defer_tools is True


def test_reasoning_depth_is_not_asked_for_by_default() -> None:
    """Sending `high` changes the wire to buy nothing -- it is already the
    default on every model that takes the parameter."""
    assert _ask_for(TurnBudget(), []).reasoning is None


def test_reasoning_depth_is_overridable_by_env(
        monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(REASONING_ENV, "Low")
    assert _ask_for(TurnBudget(), []).reasoning == "low"


def test_a_provider_serving_a_primitive_stops_the_host_emulating_it() -> None:
    """The point of asking: the residue is what switches the stand-ins off."""
    class _Native(_RecordingProvider):
        capabilities = ProviderCapabilities(task_budget=True,
                                            history_pruning=True)

    plan = plan_turn("build", max_tool_turns=7)
    p = _Native()
    token = set_turn_plan(plan)
    try:
        _drive(p)
    finally:
        reset_turn_plan(token)
    residue = p.request(p.asked)
    assert residue.task_budget is False
    assert residue.history_pruning is False


# -- the triage default (measured on Anthropic Sonnet 5) ----------------------
# A first-look FortiEDR investigation reached the same verdict and facts at
# medium as at the model default, in about 40% less time. The default is its
# own field so only the provider it was measured on applies it.

def test_a_triage_turn_carries_the_measured_default(monkeypatch) -> None:
    monkeypatch.delenv(REASONING_ENV, raising=False)
    ask = plan_turn("triage").ask
    assert ask.reasoning is None
    assert ask.reasoning_default == "medium"
    assert plan_turn("build").ask.reasoning_default is None


def test_the_env_override_replaces_the_default(monkeypatch) -> None:
    monkeypatch.setenv(REASONING_ENV, "high")
    ask = plan_turn("triage").ask
    assert ask.reasoning == "high" and ask.reasoning_default is None


def test_the_default_reaches_the_provider_and_an_argument_replaces_it(monkeypatch) -> None:
    monkeypatch.delenv(REASONING_ENV, raising=False)
    p = _RecordingProvider()
    token = set_turn_plan(plan_turn("triage"))
    try:
        _drive(p)
        assert p.asked.reasoning_default == "medium"
        _drive(p, reasoning="low")
        assert p.asked.reasoning == "low" and p.asked.reasoning_default is None
    finally:
        reset_turn_plan(token)


def test_anthropic_sends_the_default_as_effort() -> None:
    from fsr_playbooks.llm.anthropic_provider import AnthropicProvider
    p = AnthropicProvider(api_key="k", model="claude-sonnet-5")
    p.request(TurnRequest(reasoning_default="medium"))
    kwargs, _ = p._native_request_kwargs(tool_turns=None)
    assert kwargs["output_config"]["effort"] == "medium"
    p.request(TurnRequest(reasoning="high", reasoning_default="medium"))
    kwargs, _ = p._native_request_kwargs(tool_turns=None)
    assert kwargs["output_config"]["effort"] == "high"


def test_the_fortiai_proxy_ignores_the_default() -> None:
    """Any effort there switches the proxy to its LARGE model; a default
    calibrated on another provider must not do that."""
    from fsr_playbooks.llm.fortiai_proxy_provider import FortiAIProxyProvider
    p = FortiAIProxyProvider.__new__(FortiAIProxyProvider)
    p.reasoning_effort = None
    p.request(TurnRequest(reasoning_default="medium"))
    assert p.reasoning_effort is None
