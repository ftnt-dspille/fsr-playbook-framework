"""BuildProgressGuard -- the research-but-never-authored detector.

The live failure (box .159, connector 0.5.65 / fsr_playbooks 0.6.5, matrix row
B3): a "build me a playbook that ..." turn ran 11 research calls --
`get_step_type` x4, `find_connector` x3, `find_operation` x2, `get_op_schema`
x2 -- then ended with prose. No validate_yaml, no verify_playbook, no offer,
and 11 of a 16-call budget used, so it did not run out of turns.

Why the delivery guards can't catch it: CreateDeliveryGuard requires a PASSING
verify to have blessed bytes. With no verify at all there is nothing safe to
force -- forcing an offer would hand the analyst unverified YAML. So this guard
detects the distinct "never entered the authoring half" shape instead.
"""
from fsr_playbooks.llm._loop_helpers import (
    BuildProgressGuard, _CREATE_OFFER_TOOL, _CREATE_VERIFY_TOOL,
)

BUILD_SLICE = {_CREATE_OFFER_TOOL, _CREATE_VERIFY_TOOL,
               "get_step_type", "find_connector", "find_operation",
               "get_op_schema", "validate_yaml"}
# Triage advertises the offer tool (trace-compiled close) but NOT verify_playbook.
TRIAGE_SLICE = {_CREATE_OFFER_TOOL, "run_op", "get_record"}
# The FULL default registry: advertises the build pair *and* emit_action_card.
# Providers substitute this when a caller passes no slice, so a research-heavy
# triage turn lands here and must not be nudged into authoring.
FULL_SLICE = BUILD_SLICE | {"emit_action_card", "run_op", "get_record"}


def _research_only(g):
    for n in ("get_step_type", "get_step_type", "find_connector",
              "find_operation", "get_op_schema"):
        g.note_result(n, {}, {"ok": True})


def test_research_only_build_turn_is_outstanding():
    # Verbatim B3: research calls, nothing authored.
    g = BuildProgressGuard()
    _research_only(g)
    assert g.outstanding(BUILD_SLICE) is True


def test_verify_counts_as_authoring():
    g = BuildProgressGuard()
    _research_only(g)
    g.note_result(_CREATE_VERIFY_TOOL, {"yaml_text": "x"}, {"ready_to_push": True})
    assert g.outstanding(BUILD_SLICE) is False


def test_validate_yaml_counts_as_authoring():
    # Drafting and validating IS progress even if verify never ran -- the turn
    # is in the authoring loop, so the nudge would be noise.
    g = BuildProgressGuard()
    _research_only(g)
    g.note_result("validate_yaml", {}, {"ok": False})
    assert g.outstanding(BUILD_SLICE) is False


def test_offer_counts_as_authoring():
    g = BuildProgressGuard()
    _research_only(g)
    g.note_result(_CREATE_OFFER_TOOL, {}, {"ok": True})
    assert g.outstanding(BUILD_SLICE) is False


def test_trace_compile_counts_as_authoring():
    # The trace path authors without drafting YAML by hand.
    g = BuildProgressGuard()
    _research_only(g)
    g.note_result("build_playbook_from_trace", {}, {"ok": True})
    assert g.outstanding(BUILD_SLICE) is False


def test_enhance_pair_counts_as_authoring():
    g = BuildProgressGuard()
    _research_only(g)
    g.note_result("verify_enhancement", {}, {"ready_to_push": True})
    assert g.outstanding(BUILD_SLICE) is False


def test_no_tools_at_all_is_not_outstanding():
    # A conversational reply ("what can you do?") ran no tools. Forcing YAML out
    # of that would be worse than the bug.
    g = BuildProgressGuard()
    assert g.outstanding(BUILD_SLICE) is False


def test_inert_on_triage_slice():
    # Triage advertises the offer tool but not verify_playbook; a triage turn is
    # research-heavy by design and must never be nudged to author YAML.
    g = BuildProgressGuard()
    _research_only(g)
    assert g.outstanding(TRIAGE_SLICE) is False


def test_inert_when_offer_tool_absent():
    g = BuildProgressGuard()
    _research_only(g)
    assert g.outstanding({_CREATE_VERIFY_TOOL, "get_step_type"}) is False


def test_fires_at_most_once():
    g = BuildProgressGuard()
    _research_only(g)
    assert g.outstanding(BUILD_SLICE) is True
    g.mark_forced()
    assert g.outstanding(BUILD_SLICE) is False


def test_inert_on_the_full_default_registry():
    # `tools=[]` makes both providers substitute the whole registry, which
    # carries emit_action_card. That is a triage-capable slice, so a turn that
    # only ran read tools there is a triage turn, not a stalled build.
    g = BuildProgressGuard()
    _research_only(g)
    g.note_result("get_record", {}, {"ok": True})
    assert g.outstanding(FULL_SLICE) is False


def test_run_request_is_not_nudged_into_authoring():
    # Live on .159: "Run the Link Similar Alerts playbook." kept the FULL build
    # slice because the run-mode gate failed open, and called find_connector /
    # list_playbook_runs / find_operation. Nudging that turn to "draft the full
    # playbook YAML now" would author something the analyst never asked for.
    g = BuildProgressGuard()
    g.note_result("find_connector", {}, {"ok": True})
    g.note_result("list_playbook_runs", {}, {"ok": True})
    g.note_result("find_operation", {}, {"ok": True})
    assert g.outstanding(BUILD_SLICE) is False


def test_diagnose_turn_is_not_nudged():
    g = BuildProgressGuard()
    g.note_result("why_did_playbook_fail", {}, {"ok": True})
    assert g.outstanding(BUILD_SLICE) is False
