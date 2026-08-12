"""The change-affordance gate: a turn may only PROPOSE a change if the analyst
reached for one.

Live, an analyst asked in prose only for an explanation. The model explained,
noticed a real defect while explaining, then authored a fix and ended the turn
on an enhancement offer -- a change proposed to someone who never asked, plus a
composer locked for five extra model round-trips after the prose had visibly
finished.

The gate deliberately does NOT read the analyst's words: a lexical check works
in English and fails silently everywhere else, and a model call to decide a gate
makes the gate probabilistic. It gates the transition instead.

WHAT CHANGED. The gate used to escalate the whole write frontier, which meant a
free-typed change request paid for TWO approvals: one asking "want me to draft
the edit?" and then the proposal card's own Apply/Dismiss. The first gated
nothing -- every emit_* on the frontier is pure, and the card it returns is the
real gate. So the tier bump is now scoped to `CHANGE_GATED_TOOLS`, which is
empty: no tool on the frontier writes without a card of its own, and the one
that does write (`push_playbook`) is unconditionally tier 3 anyway.

What that did NOT touch, and what the tests below still pin: the read-only-turn
dispatch refusal (#117), which keys off the unchanged WRITE_FRONTIER_TOOLS, and
the affordance machinery itself, so a future writing tool can be re-armed with
one name.
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
def test_proposing_a_change_is_not_a_second_approval(tool, no_affordance):
    """The frontier no longer escalates just because nobody pressed a chip.

    Every emit_* here is PURE -- it validates its args and returns a card. The
    card IS the gate: Apply is what resumes into the write. Carding the emit
    too meant a free-typed "fix this one field" cost the analyst an approval
    that changed nothing, and then a second one on the card itself.

    `push_playbook` is the exception that proves it: it really writes, and it
    is tier 3 on its own merits with the gate out of the picture entirely.
    """
    tier = T._resolve_tier(tool, {})
    if tool == "push_playbook":
        assert tier == 3, "the one real writer keeps its own unconditional tier"
    else:
        assert tier < 3, (
            f"{tool} escalated with no affordance -- it changes nothing when "
            "it runs, so an approval in front of it is a confirmation in "
            "front of a confirmation")


def test_the_gate_can_still_be_armed_for_a_tool_that_really_writes(
        monkeypatch, no_affordance):
    """CHANGE_GATED_TOOLS is empty, not deleted.

    An empty gate and a removed gate look identical from the outside, and the
    difference matters the day a tool that writes WITHOUT a card of its own is
    added. Arm it here and the escalation, the plain-language question and the
    dropped payload all still work -- so this is dormant machinery, not dead
    code someone will delete as unused.
    """
    monkeypatch.setattr(T, "CHANGE_GATED_TOOLS", frozenset({"verify_enhancement"}))
    assert T._resolve_tier("verify_enhancement", {}) >= 3
    env = T.dispatch("verify_enhancement",
                     {"before_yaml": "a: 1\n" * 500, "after_yaml": "a: 2\n" * 500})
    assert env.get("pending_approval") is True
    assert env.get("reason") == "unrequested_change"
    assert env["preview"]["args"] == {}, "a 'shall I?' card drops the YAML noise"
    assert "didn't ask me to change anything" in env["summary"]
    # …and the tool NEXT to it in the frontier is still ungated, so arming one
    # name cannot quietly re-arm the whole frontier.
    assert T._resolve_tier("emit_patch_proposal", {}) < 3


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


def test_an_unrequested_proposal_reaches_its_own_card_instead():
    """The behaviour the double-approval hid.

    Live, a free-typed "propose a fix for one field" against an open playbook
    stopped on "Approval required: emit_patch_proposal -- want me to draft the
    edit?", and only AFTER approving did the patch card with its own
    Apply/Dismiss appear. The emit is pure, so the first card gated nothing;
    now the proposal goes straight to the card that can actually be accepted
    or dismissed.
    """
    token = T.set_change_affordance(False)
    try:
        env = T.dispatch("emit_patch_proposal", {
            "id": "p1", "title": "Tighten the timeout",
            "before_yaml": "timeout: 30\n", "after_yaml": "timeout: 300\n",
        })
    finally:
        T.reset_change_affordance(token)
    assert env.get("pending_approval") is not True, \
        "the emit must not stage an approval of its own"
    card = (env.get("card") or {}) if isinstance(env, dict) else {}
    assert card.get("type") == "patch_proposal"
    # The card carries BOTH sides, which is what makes Apply an informed
    # decision -- the gate that actually protects the playbook.
    assert card.get("before_yaml") and card.get("after_yaml")


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


# --------------------------------------------------------------------------
# Read-only turn dispatch gate (tracker #117)
# --------------------------------------------------------------------------
# An explain / find_issues chip is a read-only turn. The advertised-list gate
# (`_READ_ONLY_DROP_TOOLS` in the connector) hides write-frontier tools from
# the model's tool list, but a hallucinated call still reaches dispatch. The
# change-affordance gate bumps it to tier 3, staging a "shall I?" approval card
# -- an unrequested proposal on an explain turn. If approved, the enhancement
# runs and can DELETE the open playbook's steps. The read-only dispatch gate
# refuses the call with a clean error instead of staging a card.

@pytest.fixture()
def read_only():
    token = T.set_read_only_turn(True)
    try:
        yield
    finally:
        T.reset_read_only_turn(token)


@pytest.fixture()
def not_read_only():
    token = T.set_read_only_turn(False)
    try:
        yield
    finally:
        T.reset_read_only_turn(token)


@pytest.mark.parametrize("tool", sorted(T.WRITE_FRONTIER_TOOLS))
def test_read_only_turn_refuses_write_frontier(tool, read_only):
    """A hallucinated call to a write-frontier tool on a read-only turn is
    REFUSED, not carded. The model gets a clean error it can narrate."""
    env = T.dispatch(tool, {})
    assert env.get("ok") is False
    assert env.get("code") == "read_only_turn"
    assert "read-only" in env.get("error", "").lower()


@pytest.mark.parametrize("tool", sorted(T.WRITE_FRONTIER_TOOLS))
def test_non_read_only_turn_does_not_refuse(tool, not_read_only):
    """Without the read-only flag, write-frontier tools dispatch normally
    (they may still hit the change-affordance tier-3 gate, but they are not
    refused with read_only_turn)."""
    token = T.set_change_affordance(True)
    try:
        env = T.dispatch(tool, {})
    finally:
        T.reset_change_affordance(token)
    assert env.get("code") != "read_only_turn"


def test_read_only_turn_does_not_gate_analysis_tools(read_only):
    """Analysis tools (analyze_playbook, etc.) are NOT refused on a read-only
    turn -- noticing a defect while explaining is the good part."""
    for tool in ("analyze_playbook", "get_step_type", "find_operation"):
        env = T.dispatch(tool, {})
        assert env.get("code") != "read_only_turn", \
            f"{tool} should not be refused on a read-only turn"


def test_read_only_turn_default_is_false():
    """A host that never declares a read-only turn behaves exactly as before."""
    assert T._is_read_only_turn() is False


def test_read_only_reset_restores_previous_value():
    outer = T.set_read_only_turn(True)
    try:
        assert T._is_read_only_turn() is True
        inner = T.set_read_only_turn(False)
        assert T._is_read_only_turn() is False
        T.reset_read_only_turn(inner)
        assert T._is_read_only_turn() is True
    finally:
        T.reset_read_only_turn(outer)
    assert T._is_read_only_turn() is False


def test_read_only_reset_with_stale_token_fails_open():
    """Same fail-open reasoning as reset_change_affordance."""
    token = T.set_read_only_turn(True)
    T.reset_read_only_turn(token)
    T.reset_read_only_turn(token)  # stale: must not raise
    assert T._is_read_only_turn() is False
