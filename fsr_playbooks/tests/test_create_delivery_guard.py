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

YAML_A = "playbooks:\n  - name: A\n"
YAML_B = "playbooks:\n  - name: B\n"


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
