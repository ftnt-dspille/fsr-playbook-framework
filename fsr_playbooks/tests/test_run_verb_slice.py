"""The run verb must be WHOLE in every intent (#82).

`run_playbook` was already in both slices on purpose -- authoring a playbook and
running one are different verbs. But the tools that make a run usable were split
across the two subtraction sets, so neither intent held the whole verb:

    tool                    triage   build
    run_playbook            yes      yes
    search_playbooks        NO       yes     (BUILD_ONLY)
    resume_playbook         yes      NO      (TRIAGE_ONLY)
    list_module_playbooks   yes      NO      (TRIAGE_ONLY)

Build could START a run it could not RESUME -- a run that paused on a
manual-input step was stranded in that intent.

Two of those four tools are CONNECTOR-supplied (`resume_playbook`,
`list_module_playbooks` are registered by `register_triage_tools()`), so the
framework-standalone registry cannot see them. These tests therefore assert what
IS decidable here -- the subtraction logic, including against a simulated
connector mutation -- and the connector's own suite asserts the full table
against the real registration.
"""
from __future__ import annotations

import pytest

from fsr_playbooks.llm import intents as I


def _slice(intent: str) -> set:
    return {t["name"] for t in I.tools_for_intent(intent)}


@pytest.fixture
def triage_only_restored():
    """`TRIAGE_ONLY_TOOLS` is mutable by design (the connector extends it at
    registration). Snapshot and restore so a test that simulates that mutation
    cannot leak into the rest of the suite."""
    saved = set(I.TRIAGE_ONLY_TOOLS)
    yield I.TRIAGE_ONLY_TOOLS
    I.TRIAGE_ONLY_TOOLS.clear()
    I.TRIAGE_ONLY_TOOLS.update(saved)


def test_run_verb_whole_in_every_intent():
    """Every run-verb tool the registry actually HAS is in both slices.

    Scoped to registered names on purpose: asserting all four here would fail
    for a reason that is not a defect (the connector isn't loaded), and a test
    that is red for a non-defect gets muted.
    """
    registered = {t["name"] for t in _all_tools()}
    present = I.RUN_VERB_TOOLS & registered
    assert present, "no run-verb tool is registered at all -- the set is dead"
    for intent in I.INTENTS:
        assert present <= _slice(intent), (
            f"{intent} is missing {sorted(present - _slice(intent))} -- the run "
            f"verb must be whole in every intent")


def test_run_verb_survives_a_connector_style_triage_only_extension(
        triage_only_restored):
    """The load-bearing case: the gap only APPEARS once the connector extends
    TRIAGE_ONLY_TOOLS. Simulate that extension with a name the registry has, and
    the build slice must still advertise it."""
    triage_only_restored.add("run_playbook")
    assert "run_playbook" in _slice("build"), (
        "extending TRIAGE_ONLY_TOOLS dropped run_playbook from build -- the "
        "RUN_VERB exemption is not applied at call time")
    assert "run_playbook" in _slice("triage")


def test_run_verb_survives_a_build_only_extension():
    """Symmetric direction: `search_playbooks` is retired from advertisement
    (CONSOLIDATED_AWAY -- subsumed by `find(kind=playbook)`), so the global-
    search half of the run verb now rides on `find`, which must survive both
    subtractions the way the exemption used to guarantee for the old name."""
    assert "search_playbooks" in I.BUILD_ONLY_TOOLS, (
        "premise changed -- search_playbooks left BUILD_ONLY_TOOLS")
    assert "find" in _slice("triage") and "find" in _slice("build"), (
        "the run verb lost its global playbook search -- `find` must be "
        "advertised in every intent")


def test_exemption_does_not_leak_authoring_into_triage():
    """The fix must not become 'triage gets everything'. Deploying a NEW
    playbook is authoring, not running a deployed one."""
    assert "push_playbook" not in I.RUN_VERB_TOOLS
    triage = _slice("triage")
    for name in ("push_playbook", "compile_yaml", "validate_yaml"):
        assert name not in triage, f"{name} leaked into the triage slice"


def test_exemption_does_not_leak_containment_into_build():
    """Symmetric guard: build still must not stage containment or run ops."""
    build = _slice("build")
    for name in ("emit_action_card", "run_op"):
        assert name not in I.RUN_VERB_TOOLS
        assert name not in build, f"{name} leaked into the build slice"


def test_enhance_only_does_not_overlap_the_run_verb():
    """ENHANCE_ONLY_TOOLS is gated out of a no-open-playbook build by the
    connector. If a run-verb tool ever joined that set it would be dropped
    behind the exemption's back, so assert they stay disjoint."""
    assert not (I.ENHANCE_ONLY_TOOLS & I.RUN_VERB_TOOLS)


def _all_tools():
    from fsr_playbooks.llm.tools import anthropic_tools
    return anthropic_tools()
