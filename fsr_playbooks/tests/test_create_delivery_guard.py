"""CreateDeliveryGuard -- the CREATE counterpart to EnhanceDeliveryGuard.

Live-observed failure this pins (box .159, connector 0.5.64): a build turn ran
the research tools (`get_step_type`, `find_connector`, `find_operation`),
drafted YAML, and then ended with "Next, I will author a playbook that ..." --
no `emit_playbook_offer`, so the analyst got prose and no card to accept. The
enhance path had a guard for exactly this shape; create did not, so whether the
card appeared came down to the model's whim.

These tests pin the detector's contract: it fires exactly when a
`verify_playbook` passed and no offer followed, only when the offer tool is
advertised, and at most once.
"""
from fsr_playbooks.llm._loop_helpers import (
    _CREATE_OFFER_TOOL,
    _CREATE_VERIFY_TOOL,
    CreateDeliveryGuard,
)

BUILD_SLICE = {_CREATE_OFFER_TOOL, _CREATE_VERIFY_TOOL, "get_step_type"}
# Triage advertises the offer tool (trace-compiled close) but never verifies;
# an enhance slice carries the enhancement pair instead.
ENHANCE_SLICE = {"emit_enhancement_offer", "verify_enhancement"}

# Real playbooks: the guard ignores a draft with no action steps.
YAML_A = ("playbooks:\n  - name: A\n    steps:\n"
    "      - {name: Start, type: start, next: Note}\n"
    "      - {name: Note, type: set_variable, vars: {note: ok}}\n")
YAML_B = ("playbooks:\n  - name: B\n    steps:\n"
    "      - {name: Start, type: start, next: Note}\n"
    "      - {name: Note, type: set_variable, vars: {note: ok}}\n")


def _passing_verify(summary="enriches the sender domain"):
    return {"ready_to_push": True, "summary": summary}


def test_verified_but_not_delivered_is_outstanding():
    # The live failure: verify passed, turn ended, no offer card.
    g = CreateDeliveryGuard()
    g.note_result(_CREATE_VERIFY_TOOL, {"yaml_text": YAML_A}, _passing_verify())
    assert g.outstanding(BUILD_SLICE) == YAML_A
    assert g.summary_hint == "enriches the sender domain"


def test_delivered_is_not_outstanding():
    g = CreateDeliveryGuard()
    g.note_result(_CREATE_VERIFY_TOOL, {"yaml_text": YAML_A}, _passing_verify())
    g.note_result(_CREATE_OFFER_TOOL, {}, {"ok": True, "card": {}})
    assert g.outstanding(BUILD_SLICE) is None


def test_failed_offer_still_outstanding():
    # A rejected offer is not a delivery; the guard must still force one.
    g = CreateDeliveryGuard()
    g.note_result(_CREATE_VERIFY_TOOL, {"yaml_text": YAML_A}, _passing_verify())
    g.note_result(_CREATE_OFFER_TOOL, {}, {"ok": False, "code": "bad_yaml"})
    assert g.outstanding(BUILD_SLICE) == YAML_A


def test_failed_verify_is_not_outstanding():
    # Nothing was blessed, so there are no bytes safe to offer.
    g = CreateDeliveryGuard()
    g.note_result(_CREATE_VERIFY_TOOL, {"yaml_text": YAML_A},
                  {"ready_to_push": False})
    assert g.outstanding(BUILD_SLICE) is None


def test_no_verify_is_not_outstanding():
    # Read-only / explain turn: never verified, nothing to force.
    g = CreateDeliveryGuard()
    g.note_result("analyze_playbook", {}, {"ok": True})
    assert g.outstanding(BUILD_SLICE) is None


def test_inert_when_offer_tool_not_in_slice():
    g = CreateDeliveryGuard()
    g.note_result(_CREATE_VERIFY_TOOL, {"yaml_text": YAML_A}, _passing_verify())
    assert g.outstanding(ENHANCE_SLICE) is None


def test_verify_without_yaml_arg_is_not_outstanding():
    # The blessed bytes come from the CALL args, not the result (which is a
    # punch list). No yaml in → nothing safe to force out.
    g = CreateDeliveryGuard()
    g.note_result(_CREATE_VERIFY_TOOL, {}, _passing_verify())
    assert g.outstanding(BUILD_SLICE) is None
    g.note_result(_CREATE_VERIFY_TOOL, {"yaml_text": "   "}, _passing_verify())
    assert g.outstanding(BUILD_SLICE) is None


def test_accepts_either_yaml_arg_name():
    # verify_playbook's param is `yaml_text`; the offer tool's is `yaml`, and
    # models mix them. Accept both rather than silently declining to fire.
    g = CreateDeliveryGuard()
    g.note_result(_CREATE_VERIFY_TOOL, {"yaml": YAML_B}, _passing_verify())
    assert g.outstanding(BUILD_SLICE) == YAML_B


def test_latest_passing_verify_wins():
    # Draft → verify → repair → re-verify: only the last blessed bytes ship.
    g = CreateDeliveryGuard()
    g.note_result(_CREATE_VERIFY_TOOL, {"yaml_text": YAML_A},
                  _passing_verify("first"))
    g.note_result(_CREATE_VERIFY_TOOL, {"yaml_text": YAML_B},
                  _passing_verify("second"))
    assert g.outstanding(BUILD_SLICE) == YAML_B
    assert g.summary_hint == "second"


def test_a_later_failed_verify_keeps_last_good_bytes():
    g = CreateDeliveryGuard()
    g.note_result(_CREATE_VERIFY_TOOL, {"yaml_text": YAML_A}, _passing_verify())
    g.note_result(_CREATE_VERIFY_TOOL, {"yaml_text": YAML_B},
                  {"ready_to_push": False})
    assert g.outstanding(BUILD_SLICE) == YAML_A


def test_fires_at_most_once():
    g = CreateDeliveryGuard()
    g.note_result(_CREATE_VERIFY_TOOL, {"yaml_text": YAML_A}, _passing_verify())
    assert g.outstanding(BUILD_SLICE) == YAML_A
    g.mark_forced()
    assert g.outstanding(BUILD_SLICE) is None


# --- trace builds ------------------------------------------------------------
# Live (.159 sweep row 5, twice): "save that as a playbook" after a triage ran
# build_playbook_from_trace, got a clean compile, and ended in prose. The build
# is a preview; only an offer card gives the analyst something to Accept.

_TRACE_BUILD = "build_playbook_from_trace"


def _trace_built(yaml_text=YAML_A, compiled=True):
    return {"ok": True, "yaml": yaml_text,
            "compile_summary": {"ok": compiled, "workflows": 1, "steps": 2},
            "verified": {}, "gaps": {"siem_search": ["args"]}}


def test_clean_trace_build_owes_a_trace_offer():
    g = CreateDeliveryGuard()
    g.note_result(_TRACE_BUILD, {"name": "x"}, _trace_built())
    # "" = owed, but as a TRACE offer: no bytes ride on it.
    assert g.outstanding(BUILD_SLICE) == ""
    payload = {"yaml": "playbooks:\n  - name: HALLUCINATED\n"}
    g.apply_bytes(payload)
    assert "yaml" not in payload
    assert "build_playbook_from_trace" in g.directive


def test_trace_build_then_offer_is_delivered():
    g = CreateDeliveryGuard()
    g.note_result(_TRACE_BUILD, {}, _trace_built())
    g.note_result("emit_card", {"card_type": "playbook_offer", "payload": {}},
                  {"ok": True, "card": {}})
    assert g.outstanding(BUILD_SLICE) is None


def test_trace_build_that_did_not_compile_owes_nothing():
    g = CreateDeliveryGuard()
    g.note_result(_TRACE_BUILD, {}, _trace_built(compiled=False))
    assert g.outstanding(BUILD_SLICE) is None
    g.note_result(_TRACE_BUILD, {}, {"ok": False, "code": "empty_trace"})
    assert g.outstanding(BUILD_SLICE) is None


def test_trace_build_with_no_action_steps_owes_nothing():
    g = CreateDeliveryGuard()
    g.note_result(_TRACE_BUILD, {}, _trace_built(
        yaml_text="playbooks:\n  - name: E\n    steps:\n"
                  "      - {name: Start, type: start}\n"))
    assert g.outstanding(BUILD_SLICE) is None


def test_verify_after_trace_build_offers_the_verified_bytes():
    # The model filled the gaps by hand and verified: those bytes win.
    g = CreateDeliveryGuard()
    g.note_result(_TRACE_BUILD, {}, _trace_built())
    g.note_result(_CREATE_VERIFY_TOOL, {"yaml_text": YAML_B}, _passing_verify())
    assert g.outstanding(BUILD_SLICE) == YAML_B
    payload = {}
    g.apply_bytes(payload)
    assert payload["yaml"] == YAML_B
    assert "verify_playbook" in g.directive


def test_trace_build_after_verify_supersedes_it():
    g = CreateDeliveryGuard()
    g.note_result(_CREATE_VERIFY_TOOL, {"yaml_text": YAML_A}, _passing_verify())
    g.note_result(_TRACE_BUILD, {}, _trace_built())
    assert g.outstanding(BUILD_SLICE) == ""
