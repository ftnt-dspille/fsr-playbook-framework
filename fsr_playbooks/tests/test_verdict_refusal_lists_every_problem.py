"""A refused verdict names every problem at once, with the contract.

Live on .159 a verdict took nine emit_card calls: each refusal named one defect
and the model fixed exactly that one -- payload shape, disposition, confidence
type, claim, evidence type, action shape, action label, and finally evidence
ids that were prose. One refusal listing all of them is one repair.
"""
from __future__ import annotations

import pytest

from fsr_playbooks.mcp_server._citation_validator import (
    clear_tool_registry,
    register_tool_result,
)
from fsr_playbooks.mcp_server.tools_emit import emit_card, verdict_contract


@pytest.fixture(autouse=True)
def _turn_evidence():
    clear_tool_registry()
    register_tool_result("call_1", "get_record", True)
    yield
    clear_tool_registry()


def test_every_defect_in_one_refusal():
    # The live sequence's defects, all in one payload.
    r = emit_card(card_type="verdict", payload={
        "disposition": "unconfirmed", "severity": "Medium", "confidence": "medium",
        "summary": "s",
        "findings": [{"claim": "", "evidence": "call_1"}],
        "recommended_actions": ["isolate the host"]})
    assert r["ok"] is False
    codes = [p["code"] for p in r["problems"]]
    for want in ("bad_disposition", "bad_severity", "bad_confidence",
                 "bad_finding", "bad_finding_evidence", "bad_action"):
        assert want in codes, (want, codes)
    assert r["message"].startswith(f"{len(codes)} problems")
    assert verdict_contract() in r["suggestions"]


def test_a_single_problem_reads_as_before():
    r = emit_card(card_type="verdict", payload={
        "disposition": "inconclusive", "severity": "medium", "confidence": 0.5,
        "summary": "s", "unknowns": ["x"],
        "findings": [{"claim": "c", "evidence": ["call_1"]}]})
    assert r["code"] == "bad_disposition"
    assert r["message"].startswith("disposition must be one of")


def test_a_wrong_shape_payload_is_told_the_contract():
    r = emit_card(card_type="verdict", payload={"title": "t", "verdict": "bad"})
    assert r["code"] == "bad_payload"
    assert verdict_contract() in r["suggestions"]


def test_a_bool_is_not_a_confidence():
    r = emit_card(card_type="verdict", payload={
        "disposition": "benign", "severity": "low", "confidence": True,
        "summary": "s", "findings": [{"claim": "c", "evidence": ["x"]}]})
    assert "bad_confidence" in [p["code"] for p in r["problems"]]


def test_structural_and_id_problems_arrive_together():
    # The ninth live refusal (prose cited as evidence) came only after eight
    # structural repairs; now it rides along with the first.
    r = emit_card(card_type="verdict", payload={
        "disposition": "suspicious", "severity": "medium", "confidence": "medium",
        "summary": "s", "unknowns": ["x"],
        "findings": [{"claim": "c", "evidence": ["the alert says so"]}]})
    codes = [p["code"] for p in r["problems"]]
    assert codes == ["bad_confidence", "invalid_evidence_ids"], codes
    assert any("call_1" in h for h in r["suggestions"])
