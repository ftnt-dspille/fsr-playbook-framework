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
    _CREATE_OFFER_TOOL,
    _CREATE_VERIFY_TOOL,
    BuildProgressGuard,
    VerdictDeliveryGuard,
    is_authoring_slice,
)

BUILD_SLICE = {_CREATE_OFFER_TOOL, _CREATE_VERIFY_TOOL,
               "get_step_type", "find_connector", "find_operation",
               "get_op_schema", "validate_yaml"}
# Triage advertises the offer tool (trace-compiled close) but NOT verify_playbook.
TRIAGE_SLICE = {_CREATE_OFFER_TOOL, "run_op", "get_record"}
# The FULL default registry: what triage gets when no intent can be inferred.
# Includes discovery tools but NOT build-only tools like verify_playbook.
# When a caller passes no slice (e.g., unknown client), triage modes should land here.
# Note: Uses emit_card (advertised) not emit_action_card (internal canonical name).
FULL_SLICE = {"get_step_type", "find_connector", "find_operation", "get_op_schema",
              "validate_yaml", "emit_card", "run_op", "get_record"}


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


def test_analyze_playbook_is_diagnose_not_stalled_build():
    """A "why is my YAML invalid" turn runs research + analyze_playbook and
    explains the result. analyze_playbook READS/diagnoses an existing playbook
    (it wraps step_through_playbook), so the turn must NOT be forced to author
    an edit/offer. Regression: Frank build-matrix B2 gave a complete round-3
    explanation, then the guard hijacked it into authoring over +8 rounds."""
    g = BuildProgressGuard()
    _research_only(g)
    g.note_result("analyze_playbook", {"yaml_text": "playbooks: []"},
                  {"ok": False, "error": "step 'X': ..."})
    assert g.outstanding(BUILD_SLICE) is False


# ─── incomplete(): a drafted-but-unfinished build must not dead-end ──────────

INCOMPLETE_SLICE = BUILD_SLICE | {"emit_card"}


def test_incomplete_when_a_draft_still_has_fixes():
    g = BuildProgressGuard()
    g.note_result("verify_playbook", {"yaml_text": "playbooks: [...]"},
                  {"ok": True, "ready_to_push": False,
                   "required_fixes": [{"message": "step 'Block' is unreachable"},
                                      {"message": "connector 'x' not configured"}]})
    assert g.incomplete(INCOMPLETE_SLICE) is True
    assert g.last_fixes == ["step 'Block' is unreachable",
                            "connector 'x' not configured"]


def test_not_incomplete_when_the_draft_verified_clean():
    g = BuildProgressGuard()
    g.note_result("verify_playbook",
                  {"yaml_text": "playbooks:\n- name: p\n  steps:\n  - {name: Block, type: connector}\n"},
                  {"ok": True, "ready_to_push": True, "required_fixes": []})
    assert g.incomplete(INCOMPLETE_SLICE) is False


def test_not_incomplete_when_the_model_asked_a_choice():
    g = BuildProgressGuard()
    g.note_result("verify_playbook", {}, {"ok": True, "ready_to_push": False,
                  "required_fixes": [{"message": "needs a target IP"}]})
    g.note_result("emit_card", {"card_type": "choice"}, {"ok": True})
    assert g.incomplete(INCOMPLETE_SLICE) is False


def test_incomplete_fires_once():
    g = BuildProgressGuard()
    g.note_result("verify_playbook", {}, {"ok": True, "ready_to_push": False,
                  "required_fixes": [{"message": "x"}]})
    assert g.incomplete(INCOMPLETE_SLICE) is True
    g.mark_incomplete_shown()
    assert g.incomplete(INCOMPLETE_SLICE) is False


def test_triage_turn_never_incomplete():
    g = BuildProgressGuard()
    g.note_result("get_record", {}, {"ok": True})
    g.note_result("run_op", {}, {"ok": True})
    assert g.incomplete(TRIAGE_SLICE | {"emit_card"}) is False
# The live triage turn: every turn advertises the full surface, verify_playbook
# and the offer tool included, so the authoring-slice check passes. What the turn
# ran is the only thing that tells it apart from a build.
LIVE_SLICE = FULL_SLICE | {_CREATE_OFFER_TOOL, _CREATE_VERIFY_TOOL}


def test_reputation_lookup_is_not_a_stalled_build():
    """Live on a box, alert page: "whats the reputation of 1.1.1.1". The model
    ran find(kind=action, action_type=enrichment), get_op_schema x2, run_op x2
    (VirusTotal, OTX) and answered in prose. BuildProgressGuard counted the
    get_op_schema calls as build research and forced a playbook nobody asked
    for. The turn executed enrichment ops, so it is investigating."""
    assert is_authoring_slice(LIVE_SLICE)
    g = BuildProgressGuard()
    g.note_result("find", {"kind": "action", "action_type": "enrichment"},
                  {"ok": True, "data": [{"name": "Get IP Reputation"}]})
    g.note_result("get_op_schema", {"connector": "virustotal", "operation": "get_ip"},
                  {"ok": True, "params": []})
    g.note_result("get_op_schema", {"connector": "otx", "operation": "get_indicator"},
                  {"ok": True, "params": []})
    g.note_result("run_op", {"connector": "virustotal", "operation": "get_ip",
                             "params": {"ip": "1.1.1.1"}},
                  {"ok": True, "data": {"malicious": 0, "harmless": 80}})
    g.note_result("run_op", {"connector": "otx", "operation": "get_indicator",
                             "params": {"ip": "1.1.1.1"}},
                  {"ok": True, "data": {"pulse_count": 0}})
    assert g.outstanding(LIVE_SLICE) is False


def test_genuine_build_research_still_fires_on_the_live_slice():
    """The narrowing above must not hollow out the guard: a build turn that
    researched op schemas and step types, executed nothing, and stopped is still
    a stalled build on the same full surface."""
    assert is_authoring_slice(LIVE_SLICE)
    g = BuildProgressGuard()
    g.note_result("find", {"kind": "action", "action_type": "containment"},
                  {"ok": True, "data": []})
    g.note_result("get_op_schema", {"connector": "fortigate", "operation": "block_ip"},
                  {"ok": True, "params": []})
    g.note_result("get_op_schema", {"connector": "fortigate", "operation": "unblock_ip"},
                  {"ok": True, "params": []})
    g.note_result("get_step_type", {"type": "connector"}, {"ok": True})
    assert g.outstanding(LIVE_SLICE) is True


def test_reputation_lookup_gets_one_verdict_round_not_a_playbook():
    """What the reputation turn should get instead: the triage verdict guard
    sees an answered enrichment and no authoring, so it asks for one verdict
    card. The build guard stays out of it."""
    g = BuildProgressGuard()
    v = VerdictDeliveryGuard()
    calls = [
        ("find", {"kind": "action", "action_type": "enrichment"}, {"ok": True, "data": []}),
        ("get_op_schema", {"connector": "virustotal", "operation": "get_ip"}, {"ok": True}),
        ("run_op", {"connector": "virustotal", "operation": "get_ip"},
         {"ok": True, "data": {"malicious": 0}}),
    ]
    for name, args, result in calls:
        g.note_result(name, args, result)
        v.note_result(name, args, result)
    assert g.outstanding(LIVE_SLICE) is False
    assert v.outstanding(LIVE_SLICE) is True


def test_schema_then_failed_run_op_is_not_a_stalled_build():
    """#190: an enrichment turn read an op schema, then its run_op ERRORED.
    The op was still attempted, so the turn is investigating, not stalled on
    authoring. An answered-only check let it be forced into a playbook."""
    g = BuildProgressGuard()
    g.note_result("get_op_schema", {"connector": "virustotal", "operation": "get_ip"},
                  {"ok": True, "params": []})
    g.note_result("run_op", {"connector": "virustotal", "operation": "get_ip",
                             "params": {"ip": "1.1.1.1"}},
                  {"ok": False, "error": "connector timeout"})
    assert g.outstanding(LIVE_SLICE) is False


def test_schema_then_deferred_run_op_is_not_a_stalled_build():
    """#190: a schema read followed by a run_op that a guard DEFERRED (not yet
    run). The model is on the op path; forcing an authoring round here is
    the wrong nudge."""
    g = BuildProgressGuard()
    g.note_result("get_op_schema", {"connector": "virustotal", "operation": "get_ip"},
                  {"ok": True, "params": []})
    g.note_result("run_op", {"connector": "virustotal", "operation": "get_ip"},
                  {"kind": "guard_defer", "ok": False})
    assert g.outstanding(LIVE_SLICE) is False
