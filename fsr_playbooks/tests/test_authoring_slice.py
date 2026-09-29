"""One authoring-turn test for every provider (parallel-name-list bug class).

The fortiai proxy decided "authoring" with `"emit_action_card" not in
allowed_names`; that tool folded into `emit_card`, so every proxy turn --
triage included -- ran TriageDiscipline in authoring mode.
"""
import inspect

from fsr_playbooks.llm import (
    anthropic_provider,
    fortiai_proxy_provider,
    openai_provider,
)
from fsr_playbooks.llm._loop_helpers import (
    AUTHORING_MARKER_TOOLS,
    is_authoring_slice,
)
from fsr_playbooks.llm.intents import BUILD_ONLY_TOOLS, tools_for_intent


def _names(intent):
    return {t.get("name") for t in tools_for_intent(intent)}


def test_markers_are_build_only():
    # A marker the triage slice keeps would make every triage turn "authoring".
    assert AUTHORING_MARKER_TOOLS <= BUILD_ONLY_TOOLS


def test_triage_slice_is_not_authoring_build_slice_is():
    assert not is_authoring_slice(_names("triage"))
    assert is_authoring_slice(_names("build"))


def test_no_provider_keeps_its_own_copy():
    for mod in (anthropic_provider, openai_provider, fortiai_proxy_provider):
        src = inspect.getsource(mod)
        assert "is_authoring_slice(allowed_names)" in src, mod.__name__
        assert '"emit_action_card" not in allowed_names' not in src, mod.__name__
