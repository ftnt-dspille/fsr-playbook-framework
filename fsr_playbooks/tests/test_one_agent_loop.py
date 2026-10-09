"""Every provider runs the ONE agent loop in `llm/agent_loop.py`.

Each provider used to carry its own copy of the loop, and the copies drifted:
OpenAI closed a parallel batch at an action card and Anthropic did not; OpenAI
reported the last round's tokens twice at the budget cliff; the FortiAI proxy
had none of the delivery or verdict guards and ignored the turn budget it was
handed. These tests pin the structure so a provider cannot grow a copy again.
"""
from __future__ import annotations

import inspect

import pytest

from fsr_playbooks.llm import agent_loop
from fsr_playbooks.llm.anthropic_provider import AnthropicProvider
from fsr_playbooks.llm.factory import get_provider, registered_names
from fsr_playbooks.llm.fortiai_proxy_provider import FortiAIProxyProvider
from fsr_playbooks.llm.openai_provider import OpenAIProvider, lmstudio

PROVIDERS = (OpenAIProvider, AnthropicProvider, FortiAIProxyProvider)

#: Things only the loop may do. A provider module that does any of them has
#: started its own loop.
_LOOP_ONLY = ("TriageDiscipline(", "collect_batch(", "SuspendedSession(",
              "EnhanceDeliveryGuard(", "budget_note(", "register_tool_result(")


@pytest.mark.parametrize("cls", PROVIDERS, ids=lambda c: c.__name__)
def test_provider_delegates_to_the_shared_loop(cls):
    assert "run_loop(" in inspect.getsource(cls.stream)
    assert "resume_loop(" in inspect.getsource(cls.resume)


@pytest.mark.parametrize("cls", PROVIDERS, ids=lambda c: c.__name__)
def test_provider_module_keeps_no_loop_of_its_own(cls):
    src = inspect.getsource(inspect.getmodule(cls))
    assert [s for s in _LOOP_ONLY if s in src] == []


def test_the_loop_holds_every_rule():
    src = inspect.getsource(agent_loop)
    for s in _LOOP_ONLY:
        assert s in src, s


def test_an_action_card_closes_the_parallel_batch_for_every_provider():
    """Was OpenAI-only: on Anthropic, calls after a staged card ran
    concurrently with it and slipped past TriageDiscipline."""
    assert '== "emit_action_card"' in inspect.getsource(agent_loop.run_loop)


def test_lmstudio_is_the_openai_provider_with_local_defaults():
    p = lmstudio(model="qwen")
    assert isinstance(p, OpenAIProvider)
    assert p.base_url.startswith("http://localhost:1234")
    assert p.name == "lmstudio" and p.model == "qwen"
    assert "lmstudio" in registered_names()


def test_lmstudio_without_a_model_asks_for_one():
    assert lmstudio().precheck() is not None


def test_factory_still_builds_lmstudio():
    class _Cfg:
        def get_active_provider_name(self):
            return "lmstudio"

        def load_provider(self, name):
            class C:
                model = "m"
                api_key = None
                base_url = None
            return C()

    from fsr_playbooks.llm import factory
    old = factory._settings
    factory._settings = lambda: _Cfg()
    try:
        p = get_provider()
    finally:
        factory._settings = old
    assert isinstance(p, OpenAIProvider) and p.model == "m"
