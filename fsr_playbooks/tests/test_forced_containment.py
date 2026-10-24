"""A confident true_positive the model declined to stage is contained anyway.

Live on .159 (autonomy row tp_blocked_alone_then_undone, gpt-5.4-mini on 0.8.2)
the model delivered true_positive 0.96 but staged NO containment card
(staged=0), so the enforced policy had nothing to act on and the block never
ran -- the autonomous tier-1 promise ("one rule acts without a click") silently
failed on model judgement. The loop now forces the block the admin's policy
defines for this turn's cited malicious external target, so the policy always
has a card to judge; it still refuses a protected/internal/unrated/rate-capped
one, so forcing never bypasses a check.
"""
from __future__ import annotations

import pytest

from fsr_playbooks.llm._loop_helpers import forced_containment
from fsr_playbooks.llm.autonomy import set_turn_policy
from fsr_playbooks.mcp_server._citation_validator import (
    clear_tool_registry,
    register_tool_result,
    set_result_reader,
)

_POLICY = {
    "version": 1, "enabled": True, "mode": "enforce",
    "rules": [{
        "id": "block-external-ip",
        "action": {"connector": "fortigate-firewall", "op": "block_ip_new"},
        "when": {"verdict": {"disposition": ["true_positive"], "min_confidence": 0.8},
                 "target": {"kind": "ip", "external_only": True, "not_in": "protected_ips"},
                 "evidence": {"cites_tool_kind": "enrichment"}}}],
    "protected": {"protected_ips": []},
}


def _reader(connector, op, params, result):
    if connector == "virustotal":
        return {"source": "VirusTotal", "severity": "error", "verdict": "malicious",
                "indicator": (params or {}).get("ip")}
    return None


def _run_vt(ip):
    register_tool_result("call_vt", "run_op", True,
                         {"connector": "virustotal", "op": "query_ip",
                          "params": {"ip": ip}}, {"ok": True, "data": {"malicious": 40}})


@pytest.fixture(autouse=True)
def _ctx():
    clear_tool_registry()
    set_result_reader(_reader)
    set_turn_policy(_POLICY)
    yield
    set_turn_policy(None)
    set_result_reader(None)
    clear_tool_registry()


def test_pins_the_cited_malicious_external_ip():
    _run_vt("216.118.101.173")
    pin = forced_containment("true_positive")
    assert pin is not None
    assert pin["connector"] == "fortigate-firewall"
    assert pin["operation"] == "block_ip_new"
    assert pin["args"] == {"ip_addresses": ["216.118.101.173"]}


def test_internal_target_is_not_forced():
    _run_vt("10.1.2.3")  # internal -> the policy would refuse; nothing to force
    assert forced_containment("true_positive") is None


def test_non_true_positive_is_not_forced():
    _run_vt("216.118.101.173")
    for d in ("suspicious", "false_positive", "benign", "needs_more_info", None):
        assert forced_containment(d) is None, d


def test_no_enabled_policy_no_force():
    _run_vt("216.118.101.173")
    set_turn_policy(None)
    assert forced_containment("true_positive") is None


def test_an_unrated_lookup_is_not_forced():
    # A lookup the reader does not rate (no finding) is not evidence to act on.
    register_tool_result("call_x", "run_op", True,
                         {"connector": "some-logs", "op": "search",
                          "params": {"ip": "216.118.101.173"}}, {"ok": True})
    assert forced_containment("true_positive") is None


# --- the loop forces the card when the guard supplies a pin ------------------

def test_loop_forces_the_containment_card_when_a_pin_exists(monkeypatch):
    # Reuse the OpenAI-loop harness; patch the guard to supply a pin so the
    # test does not depend on the live registry/reader wiring (covered above).
    from test_containment_follow_through import (
        _hunt_round,
        _prose,
        _run,
        _verdict_round,
    )

    pin = {"connector": "fortigate-firewall", "operation": "block_ip_new",
           "args": {"ip_addresses": ["216.118.101.173"]}, "summary": "Contain"}
    monkeypatch.setattr("fsr_playbooks.llm.agent_loop.forced_containment",
                        lambda _d: pin)

    # TP verdict delivered, then the model ends on prose (stages nothing).
    events, disp, sent = _run([_hunt_round(), _verdict_round(), _prose(), _prose()])

    # The loop forced an emit_card ACTION card carrying the pinned block.
    action_emits = [e for e in events
                    if type(e).__name__ == "ToolUseEvent"
                    and getattr(e, "name", None) == "emit_card"
                    and (getattr(e, "arguments", {}) or {}).get("card_type") == "action"]
    assert action_emits, [type(e).__name__ for e in events]
    payload = action_emits[-1].arguments["payload"]
    assert payload["connector"] == "fortigate-firewall"
    assert payload["operation"] == "block_ip_new"
    assert payload["args"] == {"ip_addresses": ["216.118.101.173"]}


def test_loop_does_not_force_without_a_pin():
    # No policy/pin -> behaviour unchanged: asks once, ends, nothing forced.
    from test_containment_follow_through import (
        _hunt_round,
        _prose,
        _run,
        _verdict_round,
    )
    events, disp, sent = _run([_hunt_round(), _verdict_round(), _prose(), _prose()])
    action_emits = [e for e in events
                    if type(e).__name__ == "ToolUseEvent"
                    and getattr(e, "name", None) == "emit_card"
                    and (getattr(e, "arguments", {}) or {}).get("card_type") == "action"]
    assert not action_emits
