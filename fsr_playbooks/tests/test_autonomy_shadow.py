"""Autonomy policy, shadow mode (plans/AUTONOMOUS_TIER1.md phase C).

Each check is paired with the case that must NOT fire. The decision is graded
on structure -- the delivered verdict, the cited lookups' arguments, the call's
own args -- never prose. And it never changes what happens: the card or the
approval envelope still waits for a human.
"""
from __future__ import annotations

import pytest

from fsr_playbooks.llm import autonomy
from fsr_playbooks.llm.autonomy import (
    evaluate,
    parse_policy,
    set_turn_policy,
    shadow_decision,
)
from fsr_playbooks.mcp_server import _citation_validator as cv

EXT = "203.0.113.9"          # TEST-NET-3: external by is_internal_ip
INT = "10.1.2.3"

POLICY = {
    "version": 1, "enabled": True, "mode": "shadow",
    "rules": [{
        "id": "block-external-ip",
        "action": {"connector": "fortigate-firewall", "op": "block_ip_new"},
        "when": {"verdict": {"disposition": ["true_positive"], "min_confidence": 0.9},
                 "target": {"kind": "ip", "external_only": True, "not_in": "protected_ips"},
                 "evidence": {"cites_tool_kind": "enrichment"}},
        "limits": {"per_hour": 10, "per_target_per_day": 1},
        "undo": {"connector": "fortigate-firewall", "op": "unblock_ip"},
    }],
    "protected": {"protected_ips": ["198.51.100.1"]},
}


def _pol(**over):
    raw = {**POLICY, **over}
    p, err = parse_policy(raw)
    assert err is None, err
    return p


def _block(ip=EXT):
    return {"tool": "emit_action_card", "connector": "fortigate-firewall",
            "op": "block_ip_new",
            "args": {"method": "Quarantine Based", "ip_addresses": ip,
                     "time_to_live": "1 Hour"}}


# A read-only TI lookup (virustotal query_ip is tier 2) about the target. An
# op the catalog does not know tiers as 3 and is NOT a lookup: fails closed.
def _registry(ip=EXT, ok=True, op="query_ip", connector="virustotal"):
    return {"tu1": {"name": "run_op", "ok": ok,
                    "args": {"connector": connector, "op": op, "params": {"value": ip}}}}


def _verdict(disposition="true_positive", confidence=0.95, evidence=("tu1",)):
    return {"id": "v1", "disposition": disposition, "confidence": confidence,
            "findings": [{"claim": "malicious per TI", "evidence": list(evidence)}]}


def _eval(call=None, verdicts=None, registry=None, policy=None, counter=lambda r, t: (0, 0)):
    return evaluate(policy or _pol(), call or _block(),
                    verdicts=[_verdict()] if verdicts is None else verdicts,
                    registry=_registry() if registry is None else registry,
                    counter=counter)


def test_the_rule_fires_when_every_check_holds():
    d = _eval()
    assert d["outcome"] == "would_act", d["failed"]
    assert d["rule"] == "block-external-ip" and d["targets"] == [EXT]
    assert d["mode"] == "shadow" and d["verdict_id"] == "v1" and d["evidence"] == ["tu1"]


def test_no_rule_covers_a_different_op():
    call = {**_block(), "op": "block_url"}
    assert _eval(call=call) is None


def test_a_disabled_policy_decides_nothing():
    assert _eval(policy=_pol(enabled=False)) is None


@pytest.mark.parametrize("case, kwargs, needle", [
    ("no verdict", {"verdicts": []}, "no verdict"),
    ("wrong disposition", {"verdicts": [_verdict(disposition="suspicious")]}, "suspicious"),
    ("confidence 0.85", {"verdicts": [_verdict(confidence=0.85)]}, "below 0.9"),
    ("internal ip", {"call": _block(INT), "registry": _registry(INT)}, "internal"),
    ("protected ip", {"call": _block("198.51.100.1"), "registry": _registry("198.51.100.1")},
     "protected"),
    ("uncited verdict", {"verdicts": [_verdict(evidence=())]}, "cites no"),
    ("cited lookup failed", {"registry": _registry(ok=False)}, "cites no"),
    ("cited lookup about another ip", {"registry": _registry("203.0.113.77")},
     f"about {EXT}"),
    ("cited a write, not a lookup", {"registry": _registry(op="block_ip_new",
                                                         connector="fortigate-firewall")},
     "cites no"),
    ("hourly cap reached", {"counter": lambda r, t: (10, 0)}, "this hour"),
    ("target already acted on today", {"counter": lambda r, t: (0, 1)}, "today"),
    ("no counter: limits fail closed", {"counter": None}, "cannot be checked"),
])
def test_each_check_failing_means_would_not_act(case, kwargs, needle):
    d = _eval(**kwargs)
    assert d["outcome"] == "would_not_act", case
    assert any(needle in f for f in d["failed"]), (case, d["failed"])


def test_text_in_the_record_cannot_satisfy_the_rule():
    """A prompt-injected 'confirmed malicious' with no cited lookup is a claim,
    not evidence."""
    v = _verdict(evidence=("record-text",))
    d = _eval(verdicts=[v], registry={})
    assert d["outcome"] == "would_not_act"


@pytest.mark.parametrize("entry", [
    # The live .159 case: a SIEM search that found NO events for 8.8.8.8 was
    # cited as the lookup about it, and the policy blocked Google DNS.
    {"name": "siem_search", "ok": True,
     "args": {"by": "ip", "value": EXT, "direction": "any"}},
    {"name": "get_record", "ok": True, "args": {"iri": f"/api/3/indicators/{EXT}"}},
    {"name": "search_module_records", "ok": True,
     "args": {"module": "indicators", "q": EXT}},
    # Read-only connector ops that are not threat intelligence.
    {"name": "run_op", "ok": True, "args": {"connector": "fortigate-firewall",
                                           "op": "get_blocked_ip",
                                           "params": {"ip": EXT}}},
    {"name": "run_op", "ok": True, "args": {"connector": "fortinet-fortisiemv2",
                                           "op": "get_entity_context",
                                           "params": {"value": EXT}}},
], ids=["siem-search", "record-read", "module-search", "firewall-block-list",
        "siem-entity-context"])
def test_only_a_threat_intel_lookup_is_evidence(entry):
    d = _eval(registry={"tu1": entry})
    assert d["outcome"] == "would_not_act"
    assert any("threat-intel" in f for f in d["failed"]), d["failed"]


@pytest.mark.parametrize("connector, op", [
    ("virustotal", "query_ip"),
    ("fortinet-fortiguard-ioc", "ioc_search"),
    ("abuseipdb", "check_ip"),
])
def test_threat_intel_connectors_count(connector, op):
    assert _eval(registry=_registry(connector=connector, op=op))["outcome"] == "would_act"


def test_enforce_is_not_available_in_this_build():
    d = _eval(policy=_pol(mode="enforce"))
    assert d["outcome"] == "would_act" and d["mode"] == "enforce_unavailable"


def test_a_policy_that_does_not_parse_is_never_half_applied():
    err = set_turn_policy({"rules": [{"id": "x"}]})
    assert err and "does not parse" in err
    assert autonomy.get_turn_policy() is None


# ---- the turn wiring: verdicts recorded as delivered, shadow on the card ----

@pytest.fixture
def turn():
    ev = cv.TurnEvidence()
    cv.set_turn_evidence(ev)
    set_turn_policy(POLICY, counter=lambda r, t: (0, 0))
    yield ev
    set_turn_policy(None)
    cv.set_turn_evidence(None)


def test_a_verdict_delivered_after_the_action_does_not_count(turn):
    cv.register_tool_result("tu1", "run_op", True,
                            {"connector": "virustotal",
                             "op": "query_ip", "params": {"value": EXT}})
    before = shadow_decision(_block())
    assert before["outcome"] == "would_not_act"
    turn.record_verdict(_verdict())
    assert shadow_decision(_block())["outcome"] == "would_act"


def test_evidence_survives_suspend_and_resume(turn):
    cv.register_tool_result("tu1", "run_op", True, {"connector": "x", "op": "y",
                                                    "params": {"value": EXT}})
    turn.record_verdict(_verdict())
    back = cv.TurnEvidence.from_dict(turn.to_dict())
    assert back.verdicts()[0]["id"] == "v1"
    assert back.valid_ids()["tu1"]["args"]["params"]["value"] == EXT


def test_no_policy_means_no_decision():
    set_turn_policy(None)
    assert shadow_decision(_block()) is None


def test_a_policy_bug_never_blocks(turn, monkeypatch):
    monkeypatch.setattr(autonomy, "evaluate", lambda *a, **k: 1 / 0)
    assert shadow_decision(_block()) is None


def test_emit_verdict_records_the_delivered_card(turn):
    from fsr_playbooks.mcp_server.tools_emit import emit_verdict
    fn = getattr(emit_verdict, "fn", emit_verdict)
    cv.register_tool_result("tu1", "run_op", True, {"connector": "x", "op": "y"})
    out = fn(disposition="true_positive", severity="high", confidence=0.95,
             summary="TI says malicious", findings=[{"claim": "bad", "evidence": ["tu1"]}])
    assert out["ok"], out
    assert turn.verdicts()[-1]["id"] == out["card"]["id"]


def test_a_refused_verdict_is_not_recorded(turn):
    from fsr_playbooks.mcp_server.tools_emit import emit_verdict
    fn = getattr(emit_verdict, "fn", emit_verdict)
    out = fn(disposition="true_positive", severity="high", confidence=0.95,
             summary="x", findings=[{"claim": "bad", "evidence": ["nope"]}])
    assert out["ok"] is False and turn.verdicts() == []


def test_the_dispatch_envelope_carries_the_shadow_decision_and_still_suspends(turn, monkeypatch):
    from fsr_playbooks.llm import tools as T
    monkeypatch.setattr(T, "_precard_error", lambda n, a: None)
    monkeypatch.setattr(T, "_active_eval_policy", lambda: None)
    cv.register_tool_result("tu1", "run_op", True,
                            {"connector": "virustotal",
                             "op": "query_ip", "params": {"value": EXT}})
    turn.record_verdict(_verdict())
    T.clear_audit_log()
    env = T.dispatch("run_op", {"connector": "fortigate-firewall", "op": "block_ip_new",
                                "params": {"method": "Quarantine Based",
                                           "ip_addresses": EXT, "time_to_live": "1 Hour"}})
    assert env.get("pending_approval") is True, env
    assert env["policy"]["outcome"] == "would_act"
    assert any(r["decision"] == "shadow:block-external-ip:would_act"
               for r in T.snapshot_audit_log())


def test_an_uncatalogued_lookup_does_not_count_as_evidence():
    d = _eval(registry=_registry(connector="made-up-ti", op="lookup"))
    assert d["outcome"] == "would_not_act"


def test_the_action_card_carries_the_shadow_decision(turn, monkeypatch):
    from fsr_playbooks.mcp_server import tools_emit, tools_execution
    monkeypatch.setattr(tools_execution, "_live_client_for_grounding", lambda: None)
    monkeypatch.setattr(tools_execution, "_preflight_connector", lambda *a, **k: None)
    cv.register_tool_result("tu1", "run_op", True,
                            {"connector": "virustotal", "op": "query_ip",
                             "params": {"value": EXT}})
    turn.record_verdict(_verdict())
    fn = getattr(tools_emit.emit_action_card, "fn", tools_emit.emit_action_card)
    out = fn(id="c1", connector="fortigate-firewall", operation="block_ip_new",
             summary="Block the C2 address", editable_fields=[],
             args={"method": "Quarantine Based", "ip_addresses": EXT,
                   "time_to_live": "1 Hour"})
    assert out["ok"], out
    assert out["card"]["policy"]["outcome"] == "would_act"
    assert out["card"]["type"] == "action_card"   # still a card to approve


def test_one_address_under_two_keys_is_one_target():
    call = _block()
    call["args"]["ip"] = EXT
    d = _eval(call=call)
    assert d["targets"] == [EXT] and d["outcome"] == "would_act"
