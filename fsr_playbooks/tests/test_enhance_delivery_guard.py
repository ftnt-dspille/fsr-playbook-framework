"""EnhanceDeliveryGuard — the structural counterpart to `score_enhance_delivery`.

The scorer catches "verified but never delivered" offline, after the turn. This
guard catches it IN the loop so the provider can force the delivery. These tests
pin the detector's contract: it fires exactly when a verify passed and no offer
followed, only in enhance mode, and at most once.
"""
from fsr_playbooks.llm._loop_helpers import (
    EnhanceDeliveryGuard, _ENHANCE_OFFER_TOOL,
)

ENHANCE_SLICE = {_ENHANCE_OFFER_TOOL, "verify_enhancement", "get_step_type"}
BUILD_NEW_SLICE = {"emit_playbook_offer", "verify_playbook"}  # no offer tool


def _passing_verify(vid="v1", summary="adds a manual-input gate"):
    return {"ready_to_push": True, "verified_id": vid,
            "diff_summary": {"summary": summary}}


def test_verified_but_not_delivered_is_outstanding():
    g = EnhanceDeliveryGuard()
    g.note_result("verify_enhancement", {}, _passing_verify())
    # This is the e3 failure: a passing verify, the turn ends, no offer.
    assert g.outstanding(ENHANCE_SLICE) == "v1"
    assert g.summary_hint == "adds a manual-input gate"


def test_delivered_is_not_outstanding():
    g = EnhanceDeliveryGuard()
    g.note_result("verify_enhancement", {}, _passing_verify())
    g.note_result(_ENHANCE_OFFER_TOOL, {}, {"ok": True, "card": {}})
    assert g.outstanding(ENHANCE_SLICE) is None


def test_failed_offer_still_outstanding():
    # A rejected handle (unknown_verified_id) is NOT a delivery — the guard must
    # still force a re-delivery with the correct id.
    g = EnhanceDeliveryGuard()
    g.note_result("verify_enhancement", {}, _passing_verify())
    g.note_result(_ENHANCE_OFFER_TOOL, {}, {"ok": False, "code": "unknown_verified_id"})
    assert g.outstanding(ENHANCE_SLICE) == "v1"


def test_failed_verify_is_not_outstanding():
    # No verified_id minted → nothing to deliver → correctly declines (e5).
    g = EnhanceDeliveryGuard()
    g.note_result("verify_enhancement", {}, {"ready_to_push": False, "verified_id": None})
    assert g.outstanding(ENHANCE_SLICE) is None


def test_no_verify_is_not_outstanding():
    # Read-only / explain turn (e4): never verified, nothing to force.
    g = EnhanceDeliveryGuard()
    g.note_result("analyze_playbook", {}, {"ok": True})
    assert g.outstanding(ENHANCE_SLICE) is None


def test_inert_when_offer_tool_not_in_slice():
    # Build-new-playbook / triage turns don't advertise the offer tool. Even a
    # passing verify must not trip the guard there.
    g = EnhanceDeliveryGuard()
    g.note_result("verify_enhancement", {}, _passing_verify())
    assert g.outstanding(BUILD_NEW_SLICE) is None


def test_latest_passing_verify_wins():
    # Iterating: several verifies, only the last blessed bytes should deliver.
    g = EnhanceDeliveryGuard()
    g.note_result("verify_enhancement", {}, _passing_verify(vid="v1", summary="first"))
    g.note_result("verify_enhancement", {}, _passing_verify(vid="v2", summary="second"))
    assert g.outstanding(ENHANCE_SLICE) == "v2"
    assert g.summary_hint == "second"


def test_a_later_failed_verify_keeps_last_good_handle():
    # A passing verify then a failed re-verify: the good handle stands (a
    # failing verify mints no id, so it can't clobber the last blessed one).
    g = EnhanceDeliveryGuard()
    g.note_result("verify_enhancement", {}, _passing_verify(vid="v1"))
    g.note_result("verify_enhancement", {}, {"ready_to_push": False, "verified_id": None})
    assert g.outstanding(ENHANCE_SLICE) == "v1"


def test_fires_at_most_once():
    g = EnhanceDeliveryGuard()
    g.note_result("verify_enhancement", {}, _passing_verify())
    assert g.outstanding(ENHANCE_SLICE) == "v1"
    g.mark_forced()
    # After one forced round the guard is spent — it must not loop.
    assert g.outstanding(ENHANCE_SLICE) is None
