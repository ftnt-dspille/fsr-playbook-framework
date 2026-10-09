"""The capability matrix: a declared primitive must REACH THE WIRE.

`shipped-but-inert` is the recurring defect in this codebase -- a feature that
is present, imported, released, and silently does nothing. The capability seam
in `provider.py` is a new place for exactly that to happen: a provider can
declare `reasoning_depth = True` and never send a reasoning parameter, and
every test that only reads `capabilities` would still be green.

So this file does not read the declaration. For each capability a provider
declares TRUE it demands a PROBE -- a callable that drives the provider and
asserts the primitive is observable on what it would send. A provider that
flips a flag without adding a probe fails here, and so does one whose probe
stops finding the primitive.

The other half is the fallback: for each capability a provider declares FALSE,
asking for it must come back as host emulation, because that residue is what
switches the hand-built stand-ins (`TurnBudget.note()`, `shrink_history`) on.
"""
from __future__ import annotations

import pytest

from fsr_playbooks.llm.anthropic_provider import (
    CONTEXT_EDIT_BETA,
    TASK_BUDGET_BETA,
    TASK_BUDGET_MIN_TOKENS,
    AnthropicProvider,
)
from fsr_playbooks.llm.fake_provider import FakeProvider
from fsr_playbooks.llm.fortiai_proxy_provider import (
    FEATURE_LARGE,
    FortiAIProxyProvider,
    _resolve_llm_config,
)
from fsr_playbooks.llm.openai_provider import OpenAIProvider, lmstudio
from fsr_playbooks.llm.provider import (
    CAPABILITY_NAMES,
    HostEmulation,
    ProviderCapabilities,
    TurnRequest,
)

#: Every provider this package ships, by the name it registers under. Adding a
#: provider without adding it here is caught by `test_every_provider_is_in_the_matrix`.
PROVIDERS = {
    "anthropic": lambda: AnthropicProvider(api_key="test-key"),
    "openai": lambda: OpenAIProvider(api_key="test-key"),
    "lmstudio": lambda: lmstudio(),
    "fortiai-proxy": lambda: FortiAIProxyProvider(base_url="https://example.invalid",
                                                  api_key="test-key", client=object()),
    "fake": lambda: FakeProvider(),
}


def _probe_fortiai_reasoning(p: FortiAIProxyProvider) -> None:
    """FortiAI serves reasoning depth by putting it in `params.config`."""
    p.request(TurnRequest(reasoning="high"))
    overlay = _resolve_llm_config(p.feature, p.reasoning_effort)
    assert overlay.get("reasoning_effort") == "high", overlay
    # effort implies LARGE -- asking for depth on MEDIUM is a 400 at the wire.
    assert overlay.get("model") == FEATURE_LARGE, overlay


def _probe_anthropic_reasoning(p: AnthropicProvider) -> None:
    """Anthropic serves depth with adaptive thinking + `output_config.effort`."""
    p.request(TurnRequest(reasoning="high"))
    kwargs, betas = p._native_request_kwargs(tool_turns=8)
    assert kwargs.get("thinking") == {"type": "adaptive"}, kwargs
    assert kwargs["output_config"]["effort"] == "high", kwargs
    # Effort is GA -- asking for depth alone must not drag in a beta flag.
    assert betas == [], betas
    # A model that predates the family must NOT be sent these.
    old = AnthropicProvider(api_key="test-key", model="claude-sonnet-4-5-20250929")
    assert old.capabilities.reasoning_depth is False
    old.request(TurnRequest(reasoning="high"))
    assert old._native_request_kwargs(tool_turns=8) == ({}, [])


def _probe_anthropic_task_budget(p: AnthropicProvider) -> None:
    """A handed-over turn bound becomes a server-tracked token budget."""
    p.request(TurnRequest(max_tool_turns=16))
    kwargs, betas = p._native_request_kwargs(tool_turns=16)
    budget = kwargs["output_config"]["task_budget"]
    assert budget["type"] == "tokens"
    assert budget["total"] >= TASK_BUDGET_MIN_TOKENS, budget
    # `remaining` is the server's to track; sending ours under-reports spend.
    assert "remaining" not in budget, budget
    assert betas == [TASK_BUDGET_BETA], betas
    # Both primitives at once must SURVIVE each other -- they are siblings in
    # one `output_config`, so a naive merge silently drops the effort.
    p.request(TurnRequest(reasoning="max", max_tool_turns=16))
    kwargs, _ = p._native_request_kwargs(tool_turns=16)
    assert kwargs["output_config"]["effort"] == "max", kwargs
    assert "task_budget" in kwargs["output_config"], kwargs


def _probe_anthropic_deferred_tools(p: AnthropicProvider) -> None:
    """The long tail is deferred and the search tool is prepended."""
    from fsr_playbooks.llm.anthropic_provider import apply_deferred_loading

    surface = [{"name": "find_connector"}, {"name": "validate_yaml"},
               {"name": "mcp_soc__get_alert"}, {"name": "mcp_soc__block_indicator"}]
    out, n = apply_deferred_loading(surface, p.model)
    assert n == 2, out
    assert out[0]["type"].startswith("tool_search_tool_bm25"), out[0]
    deferred = {t["name"] for t in out if t.get("defer_loading")}
    assert deferred == {"mcp_soc__get_alert", "mcp_soc__block_indicator"}
    # API constraint: the search tool is never itself deferred, and at least
    # one other tool stays loaded.
    assert "defer_loading" not in out[0]
    assert any(not t.get("defer_loading") for t in out[1:])
    # An all-deferrable slice would trip `400 All tools have defer_loading
    # set`, so it is left alone rather than sent.
    all_mcp = [{"name": "mcp_soc__get_alert"}]
    assert apply_deferred_loading(all_mcp, p.model) == (all_mcp, 0)
    # And a model without tool search gets the slice untouched.
    old = AnthropicProvider(api_key="k", model="claude-sonnet-4-5-20250929")
    assert apply_deferred_loading(surface, old.model) == (surface, 0)


def _probe_anthropic_history_pruning(p: AnthropicProvider) -> None:
    """An explicit ask becomes server-side context editing, and only then."""
    p.request(TurnRequest(prune_history=True))
    kwargs, betas = p._native_request_kwargs(tool_turns=8)
    edits = kwargs["context_management"]["edits"]
    assert edits == [{"type": "clear_tool_uses_20250919"}], kwargs
    assert CONTEXT_EDIT_BETA in betas, betas
    # NOT compaction -- a different feature with a different beta flag.
    assert "compact-2026-01-12" not in betas, betas
    # Nobody asked -> nothing on the wire, and `shrink_history` stays on.
    p.request(TurnRequest())
    assert p._native_request_kwargs(tool_turns=8) == ({}, [])
    assert p.emulation.history_pruning is True
    # A model that predates the family emulates instead of eating a 400.
    old = AnthropicProvider(api_key="test-key", model="claude-sonnet-4-5-20250929")
    assert old.capabilities.history_pruning is False
    old.request(TurnRequest(prune_history=True))
    assert old._native_request_kwargs(tool_turns=8) == ({}, [])
    assert old.emulation.history_pruning is True


def test_native_pruning_and_the_host_stand_in_never_both_run() -> None:
    """The failure this guards is paying twice: `shrink_history` rewriting a
    transcript the server is already clearing."""
    p = AnthropicProvider(api_key="test-key")
    residue = p.request(TurnRequest(prune_history=True))
    kwargs, _ = p._native_request_kwargs(tool_turns=8)
    assert "context_management" in kwargs
    assert residue.history_pruning is False


def test_prune_history_false_prunes_nowhere() -> None:
    p = AnthropicProvider(api_key="test-key")
    residue = p.request(TurnRequest(prune_history=False))
    assert residue.history_pruning is False
    assert p._native_request_kwargs(tool_turns=8) == ({}, [])


#: (provider name, capability) -> probe. A declared-true capability with no
#: entry here is a failure, not an omission.
PROBES = {
    ("fortiai-proxy", "reasoning_depth"): _probe_fortiai_reasoning,
    ("anthropic", "reasoning_depth"): _probe_anthropic_reasoning,
    ("anthropic", "task_budget"): _probe_anthropic_task_budget,
    ("anthropic", "deferred_tools"): _probe_anthropic_deferred_tools,
    ("anthropic", "history_pruning"): _probe_anthropic_history_pruning,
}


@pytest.mark.parametrize("name", sorted(PROVIDERS))
def test_provider_declares_capabilities(name: str) -> None:
    caps = PROVIDERS[name]().capabilities
    assert isinstance(caps, ProviderCapabilities)


@pytest.mark.parametrize("name", sorted(PROVIDERS))
def test_declared_capability_reaches_the_wire(name: str) -> None:
    provider = PROVIDERS[name]()
    for cap in CAPABILITY_NAMES:
        if not getattr(provider.capabilities, cap):
            continue
        probe = PROBES.get((name, cap))
        assert probe is not None, (
            f"{name} declares {cap}=True with no probe. Declaring a capability "
            f"is a claim that it reaches the wire; add a probe to PROBES that "
            f"proves it, or set the flag False and let the host emulate."
        )
        probe(provider)


@pytest.mark.parametrize("name", sorted(PROVIDERS))
def test_undeclared_capability_falls_back_to_host_emulation(name: str) -> None:
    provider = PROVIDERS[name]()
    # Ask for EVERY capability -- a residue is only meaningful against an ask.
    residue = provider.request(TurnRequest(reasoning="high", max_tool_turns=8,
                                           prune_history=True, defer_tools=True))
    for cap in CAPABILITY_NAMES:
        if getattr(provider.capabilities, cap):
            assert not getattr(residue, cap), (
                f"{name} declares {cap} natively but still asked the host to "
                f"emulate it -- both paths would run."
            )
        else:
            assert getattr(residue, cap), (
                f"{name} does not serve {cap}, so the host-side stand-in must "
                f"be switched on for it."
            )


@pytest.mark.parametrize("name", sorted(PROVIDERS))
def test_unasked_provider_emulates_exactly_as_before(name: str) -> None:
    """A provider nobody calls `request()` on -- the framework's own MCP
    callers -- must behave as it did before the seam existed: budget notes and
    history shrinking on, nothing deferred, no reasoning override."""
    e = PROVIDERS[name]().emulation
    assert e.task_budget is True
    assert e.history_pruning is True
    assert e.deferred_tools is False
    assert e.reasoning_depth is False


def test_probe_registry_has_no_stale_entries() -> None:
    for (name, cap) in PROBES:
        assert name in PROVIDERS, f"probe for unknown provider {name!r}"
        assert cap in CAPABILITY_NAMES, f"probe for unknown capability {cap!r}"
        assert getattr(PROVIDERS[name]().capabilities, cap), (
            f"{name} has a probe for {cap} but no longer declares it -- either "
            f"the capability regressed silently or the probe is stale."
        )


def test_resolve_is_pure_and_symmetric() -> None:
    caps = ProviderCapabilities(reasoning_depth=True, task_budget=True)
    r = HostEmulation.resolve(caps, TurnRequest(reasoning="low", max_tool_turns=8))
    assert r == HostEmulation(reasoning_depth=False, task_budget=False,
                              deferred_tools=False, history_pruning=True)
    # Not asking for a capability is not the same as the provider serving it,
    # but both mean "do not emulate".
    assert HostEmulation.resolve(ProviderCapabilities(),
                                 TurnRequest(reasoning=None)).reasoning_depth is False


def test_every_provider_is_in_the_matrix() -> None:
    """A provider that never enters this file is a provider whose declaration
    nothing checks -- which is how the seam would quietly rot."""
    import importlib
    import inspect
    import pkgutil

    import fsr_playbooks.llm as llm_pkg
    from fsr_playbooks.llm.provider import CapabilityMixin

    found: set[str] = set()
    for mod in pkgutil.iter_modules(llm_pkg.__path__):
        if not mod.name.endswith("_provider"):
            continue
        module = importlib.import_module(f"fsr_playbooks.llm.{mod.name}")
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if (obj is not CapabilityMixin and issubclass(obj, CapabilityMixin)
                    and obj.__module__ == module.__name__):
                found.add(obj.name)
    missing = found - set(PROVIDERS)
    assert not missing, (
        f"providers absent from the capability matrix: {sorted(missing)}. Add "
        f"a constructor to PROVIDERS so its declaration is checked."
    )


def test_task_budget_is_not_sent_unless_the_loop_hands_one_over() -> None:
    """The blast-radius guard. Declaring the capability must not change the
    wire for callers that never asked: no `output_config`, no beta endpoint,
    and the host-side budget note still running."""
    p = AnthropicProvider(api_key="test-key")
    assert p.capabilities.task_budget is True
    assert p._native_request_kwargs(tool_turns=16) == ({}, [])
    assert p.emulation.task_budget is True


def test_deferred_loading_is_not_applied_unless_asked() -> None:
    """Same blast-radius rule as the task budget: declaring the capability
    must not change the array for a caller that never asked."""
    from fsr_playbooks.llm.anthropic_provider import apply_deferred_loading

    p = AnthropicProvider(api_key="test-key")
    assert p.capabilities.deferred_tools is True
    assert p._turn_request.defer_tools is False
    # The provider only calls `apply_deferred_loading` behind that flag; the
    # function itself stays pure and callable either way.
    surface = [{"name": "find_connector"}, {"name": "mcp_soc__get_alert"}]
    assert apply_deferred_loading(surface, p.model)[1] == 1
