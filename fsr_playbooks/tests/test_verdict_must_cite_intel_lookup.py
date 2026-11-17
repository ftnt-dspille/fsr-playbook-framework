"""A true_positive verdict must cite the threat-intel lookup it rests on.

Live on .159 (autonomy row `tp_blocked_alone_then_undone`, gpt-5.4-mini) a run
came back with a confident true_positive (0.98) whose findings cited a non-
lookup result, so the autonomy policy refused the block AFTER the turn ended
("the verdict cites no successful threat-intel lookup") -- too late for the
model to repair. emit_verdict now refuses that verdict in-turn, naming the
rated lookup ids it ran, so the fix is one retry (the same loud-refusal lever
that drove invalid-evidence-id refusals to zero).
"""
from __future__ import annotations

import pytest

from fsr_playbooks.mcp_server._citation_validator import (
    clear_tool_registry,
    register_tool_result,
    set_result_reader,
)
from fsr_playbooks.mcp_server.tools_emit import emit_card

TARGET = "216.118.101.173"


def _malicious_reader(connector, op, params, result):
    """A VirusTotal-style reader that rates the queried IP malicious."""
    if connector == "virustotal":
        return {"source": "VirusTotal", "severity": "error", "verdict": "malicious",
                "indicator": (params or {}).get("ip")}
    return None


@pytest.fixture(autouse=True)
def _turn_evidence():
    clear_tool_registry()
    set_result_reader(_malicious_reader)
    # This turn ran a rated intel lookup AND a plain record read.
    register_tool_result("call_vt", "run_op", True,
                         {"connector": "virustotal", "op": "query_ip",
                          "params": {"ip": TARGET}},
                         {"ok": True, "data": {"malicious": 40}})
    register_tool_result("call_rec", "get_record", True)
    yield
    set_result_reader(None)
    clear_tool_registry()


def _verdict(evidence_ids, disposition="true_positive"):
    return emit_card(card_type="verdict", payload={
        "disposition": disposition, "severity": "high", "confidence": 0.95,
        "summary": "C2 beacon confirmed", "unknowns": [],
        "findings": [{"claim": "the host beaconed to a known C2 address",
                      "evidence": evidence_ids}]})


def _codes(r):
    return [p.get("code") for p in (r.get("problems") or [])]


def test_true_positive_citing_only_a_record_read_is_refused():
    r = _verdict(["call_rec"])
    assert r.get("ok") is False, r
    assert "verdict_omits_intel_citation" in _codes(r), r
    # The refusal names the lookup id the model can cite.
    assert "call_vt" in r["message"], r["message"]


def test_true_positive_citing_the_intel_lookup_is_accepted():
    r = _verdict(["call_vt"])
    assert r.get("ok") is not False, r
    assert r.get("card", {}).get("type") == "verdict_card", r


def test_true_positive_may_cite_both_lookup_and_read():
    r = _verdict(["call_vt", "call_rec"])
    assert r.get("ok") is not False, r
    assert r.get("card", {}).get("type") == "verdict_card", r


def test_a_non_true_positive_is_not_forced_to_cite_intel():
    # Suspicious/benign conclusions are not the autonomy acting threshold.
    r = _verdict(["call_rec"], disposition="suspicious")
    assert "verdict_omits_intel_citation" not in _codes(r), r


def test_no_rated_lookup_ran_means_no_intel_refusal():
    # Only a record read in the registry -> nothing to force citing.
    clear_tool_registry()
    register_tool_result("call_rec", "get_record", True)
    r = _verdict(["call_rec"])
    assert "verdict_omits_intel_citation" not in _codes(r), r
