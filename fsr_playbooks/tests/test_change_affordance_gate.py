"""The change-affordance gate: a turn may only PROPOSE a change if the analyst
reached for one.

Live, an analyst asked in prose only for an explanation. The model explained,
noticed a real defect while explaining, then authored a fix and ended the turn
on an enhancement offer -- a change proposed to someone who never asked, plus a
composer locked for five extra model round-trips after the prose had visibly
finished.

The gate deliberately does NOT read the analyst's words: a lexical check works
in English and fails silently everywhere else, and a model call to decide a gate
makes the gate probabilistic. It gates the transition instead -- no affordance,
the write frontier cards.
"""
from __future__ import annotations

import pytest

from fsr_playbooks.llm import tools as T


@pytest.fixture()
def no_affordance():
    token = T.set_change_affordance(False)
    try:
        yield
    finally:
        T.reset_change_affordance(token)


@pytest.fixture()
def with_affordance():
    token = T.set_change_affordance(True)
    try:
        yield
    finally:
        T.reset_change_affordance(token)


@pytest.mark.parametrize("tool", sorted(T.WRITE_FRONTIER_TOOLS))
def test_write_frontier_escalates_without_an_affordance(tool, no_affordance):
    assert T._resolve_tier(tool, {}) >= 3


@pytest.mark.parametrize("tool", sorted(T.WRITE_FRONTIER_TOOLS))
def test_write_frontier_is_unchanged_with_an_affordance(tool, with_affordance):
    baseline = T.TOOL_TIERS.get(tool, 0)
    tier = T._resolve_tier(tool, {})
    # push_playbook is tier 3 on its own merits; the others fall back to theirs.
    assert tier == (3 if tool == "push_playbook" else max(baseline, 0))


def test_default_is_fail_open():
    """A host that never declares an affordance must behave exactly as before
    -- the gate is opt-in, so an older connector cannot be broken by it."""
    assert T._change_affordance_present() is True
    assert T._resolve_tier("emit_enhancement_offer", {}) == \
        T.TOOL_TIERS.get("emit_enhancement_offer", 0)


@pytest.mark.parametrize("tool", [
    "analyze_playbook", "step_through_playbook", "find_operation",
    "get_step_type", "why_did_playbook_fail",
])
def test_analysis_tools_are_never_gated(tool, no_affordance):
    """Noticing a defect while explaining is the good part. Only proposing the
    change unasked is the defect."""
    assert T._resolve_tier(tool, {}) < 3


@pytest.mark.parametrize("tool", [
    "compile_yaml", "validate_yaml", "verify_playbook",
    "build_playbook_from_trace",
])
def test_new_playbook_authoring_is_not_gated(tool, no_affordance):
    """Authoring a playbook the analyst does not have yet changes nothing of
    theirs. Gating it would put a card in front of the ordinary build flow."""
    assert T._resolve_tier(tool, {}) < 3


def test_reset_restores_the_previous_value():
    outer = T.set_change_affordance(False)
    try:
        assert T._change_affordance_present() is False
        inner = T.set_change_affordance(True)
        assert T._change_affordance_present() is True
        T.reset_change_affordance(inner)
        assert T._change_affordance_present() is False
    finally:
        T.reset_change_affordance(outer)
    assert T._change_affordance_present() is True


def test_reset_with_a_stale_token_fails_open():
    """An un-reset or cross-thread bind must not leave the gate latched on for
    the next turn this worker serves -- that would card a legitimate flow with
    no way for the analyst to tell why."""
    token = T.set_change_affordance(False)
    T.reset_change_affordance(token)
    T.reset_change_affordance(token)  # stale: must not raise
    assert T._change_affordance_present() is True


def test_gated_card_explains_itself_and_drops_the_yaml_payload():
    """The card is not "approve this tool call" -- the analyst never asked for
    a change, so it has to ask the question in their terms. And the raw args of
    verify_enhancement are two whole YAML documents; they are noise on a
    'shall I?' prompt."""
    token = T.set_change_affordance(False)
    try:
        env = T.dispatch("verify_enhancement",
                         {"before_yaml": "a: 1\n" * 500,
                          "after_yaml": "a: 2\n" * 500})
    finally:
        T.reset_change_affordance(token)
    assert env.get("pending_approval") is True
    assert env.get("reason") == "unrequested_change"
    assert env["preview"]["args"] == {}
    assert "didn't ask me to change anything" in env["summary"]


def test_ordinary_tier_3_card_is_unaffected():
    """A genuine tier-3 action still carries its real preview and no
    unrequested-change reason -- the gate must not repaint every approval."""
    token = T.set_change_affordance(True)
    try:
        env = T.dispatch("push_playbook", {"yaml_text": "playbooks: []"})
    finally:
        T.reset_change_affordance(token)
    assert env.get("pending_approval") is True
    assert env.get("reason") is None
    assert env["preview"]["args"], "a real approval keeps its preview"
