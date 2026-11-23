"""Phase 2 step 2: the evidence score is computed and RECORDED, never decided on.

Two halves. The score is pinned for fixed registries (each ladder boundary,
record-only reads, the contradiction cap, unsourced identifiers). And the
decision path is pinned unchanged: the policy's outcome and failed list are the
same whatever score the verdict carries, and the model's confidence is still
what the floor compares.
"""
from __future__ import annotations

import copy

import pytest

from fsr_playbooks.llm.autonomy import evaluate, parse_policy
from fsr_playbooks.mcp_server import _citation_validator as cv
from fsr_playbooks.mcp_server._evidence_score import identifiers, score_verdict
from fsr_playbooks.mcp_server.tools_emit import emit_card

IP = "203.0.113.9"
OTHER = "198.51.100.77"
RECORD = "11111111-2222-3333-4444-555555555555"

MAL = {"source": "VirusTotal", "verdict": "malicious", "severity": "error"}
CLEAN = {"source": "VirusTotal", "verdict": "clean", "severity": "ok"}

SIEM_PREFIX = {"siem_": "FortiSIEM"}
TICKETS = {"servicenow": {"label": "ServiceNow", "kind": "tickets"}}


def vt(ip=IP, finding=MAL, **kw):
    return {"name": "run_op", "ok": True, "finding": finding, "idents": [ip],
            "args": {"connector": "virustotal", "op": "query_ip", "params": {"ip": ip}},
            **kw}


def siem(ip=IP, thin=False):
    e = {"name": "siem_search_events", "ok": True, "idents": [] if thin else [ip],
         "args": {"query": ip}}
    if thin:
        e["thin"] = True
    return e


def ticket(ip=IP):
    return {"name": "run_op", "ok": True, "idents": [ip],
            "args": {"connector": "servicenow", "op": "search", "params": {"q": ip}}}


def record_read(ip=IP):
    return {"name": "get_record", "ok": True, "idents": [ip],
            "args": {"uuid": RECORD}}


def card(disposition="true_positive", conf=0.9, ip=IP, evidence=("a",)):
    return {"id": "v1", "disposition": disposition, "confidence": conf,
            "summary": f"beaconing to {ip}",
            "findings": [{"claim": f"host contacted {ip}", "evidence": list(evidence)}]}


def score(c, registry, unchecked=(), **kw):
    return score_verdict(c, registry, record_subject=RECORD,
                         unchecked_sources=list(unchecked), ready_sources=SIEM_PREFIX,
                         ready_connectors=TICKETS, **kw)


@pytest.mark.parametrize("case, c, registry, unchecked, want, tier", [
    ("support, uncovered, one class", card(), {"a": vt()}, ["ServiceNow"], 0.8, "support"),
    ("support + coverage", card(), {"a": vt()}, [], 0.88, "support_partial"),
    ("support + corroboration, uncovered", card(), {"a": vt(), "b": siem()},
     ["ServiceNow"], 0.88, "support_partial"),
    ("support + corroboration + coverage (C2 shape)", card(), {"a": vt(), "b": siem()},
     [], 0.95, "support_corroborated_covered"),
    ("record read only", card(), {"a": record_read()}, [], 0.5, "no_independent_support"),
    ("no lookups at all", card(), {}, [], 0.5, "no_independent_support"),
    ("thin siem is not support", card(), {"b": siem(thin=True)}, [], 0.5,
     "no_independent_support"),
    ("lookup about another ip", card(), {"a": vt(OTHER)}, [], 0.5,
     "no_independent_support"),
    ("weak rating is not malicious support", card(), {"a": vt(finding={"severity": "warning"})},
     [], 0.5, "no_independent_support"),
])
def test_ladder(case, c, registry, unchecked, want, tier):
    s = score(c, registry, unchecked)
    assert (s["score"], s["tier"]) == (want, tier), (case, s)


def test_record_text_is_not_independent_even_next_to_a_rated_lookup_on_the_alert():
    # a read of the alert itself adds no class: the 680b4332 rule
    s = score(card(), {"a": vt(), "r": record_read()}, [])
    assert s["score"] == 0.88 and s["support_classes"] == ["intel"]


def test_contradiction_caps_the_score():
    s = score(card(), {"a": vt(), "b": siem(), "c": vt(finding=CLEAN)}, [])
    assert s["score"] == 0.5 and s["capped_by"] == ["contradiction"]
    assert s["components"]["no_contradiction"] is False


def test_an_identifier_in_no_tool_result_caps_the_score():
    c = card()
    c["summary"] = f"beaconing to {IP} and {OTHER}"
    s = score(c, {"a": vt(), "b": siem()}, [])
    assert s["score"] == 0.5 and s["capped_by"] == ["unsourced_identifier"]
    assert OTHER in s["missing"][-1]


def test_benign_needs_exculpatory_support_not_a_log_hit():
    c = card("benign")
    assert score(c, {"b": siem()}, [])["tier"] == "no_independent_support"
    s = score(c, {"t": ticket(), "b": siem()}, [])
    assert s["components"]["support"] and s["support_classes"] == ["tickets"]
    # a malicious rating about the subject contradicts a benign call
    s = score(c, {"t": ticket(), "a": vt()}, [])
    assert s["capped_by"] == ["contradiction"] and s["score"] == 0.5


def test_the_models_confidence_is_not_an_input():
    reg = {"a": vt(), "b": siem()}
    lo, hi = score(card(conf=0.2), reg), score(card(conf=0.99), reg)
    assert lo == hi


def test_identifiers_are_narrow():
    got = identifiers({"x": f"seen {IP} at 12:30, 3 hits, v1.2.3", "h": "a" * 32,
                       "bad": "999.1.1.1"})
    assert got == sorted([IP, "a" * 32])


# ---- recorded, on the card and in the decision record ---------------------------

@pytest.fixture
def turn():
    cv.clear_tool_registry()
    cv.set_result_reader(lambda c, o, p, r: MAL if c == "virustotal" else None)
    cv.register_tool_result("call_vt", "run_op", True,
                            {"connector": "virustotal", "op": "query_ip",
                             "params": {"ip": IP}}, {"ok": True, "data": {"malicious": 40}})
    yield
    cv.set_result_reader(None)
    cv.clear_tool_registry()


def _emit(conf=0.85):
    return emit_card(card_type="verdict", payload={
        "disposition": "true_positive", "severity": "high", "confidence": conf,
        "summary": f"beaconing to {IP}", "unknowns": [],
        "findings": [{"claim": f"host contacted {IP}", "evidence": ["call_vt"]}]})


def test_the_card_carries_the_score_beside_the_models_confidence(turn):
    r = _emit(0.85)
    c = r["card"]
    assert c["confidence"] == 0.85
    assert c["evidence_score"]["score"] == 0.88  # no ready sources reported: covered
    assert c["evidence_score"]["tier"] == "support_partial"
    assert cv.get_turn_evidence().verdicts()[-1]["evidence_score"]["score"] == 0.88


def test_a_scoring_failure_never_touches_the_verdict(turn, monkeypatch):
    from fsr_playbooks.mcp_server import _evidence_score
    monkeypatch.setattr(_evidence_score, "score_verdict",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    r = _emit()
    assert r["ok"] is True and "evidence_score" not in r["card"]


# ---- the decision path is unchanged ----------------------------------------------

POLICY = {
    "version": 1, "enabled": True, "mode": "shadow",
    "rules": [{
        "id": "block-external-ip",
        "action": {"connector": "fortigate-firewall", "op": "block_ip_new"},
        "when": {"verdict": {"disposition": ["true_positive"], "min_confidence": 0.9},
                 "target": {"kind": "ip", "external_only": True},
                 "evidence": {"cites_tool_kind": "enrichment"}},
    }],
}
BLOCK = {"tool": "emit_action_card", "connector": "fortigate-firewall",
         "op": "block_ip_new", "args": {"ip_addresses": IP}}


def _decide(conf, ev_score):
    p, err = parse_policy(copy.deepcopy(POLICY))
    assert err is None
    v = {"id": "v1", "disposition": "true_positive", "confidence": conf,
         "findings": [{"claim": "x", "evidence": ["tu1"]}]}
    if ev_score is not None:
        v["evidence_score"] = ev_score
    return evaluate(p, BLOCK, verdicts=[v], registry={"tu1": vt()}, counter=lambda r, t: (0, 0))


@pytest.mark.parametrize("conf, expect", [(0.95, "would_act"), (0.85, "would_not_act")])
def test_the_floor_still_compares_the_models_confidence(conf, expect):
    """Whatever score rides on the verdict (top tier, bottom tier, none), the
    outcome and the failed lines are those of the confidence alone."""
    base = _decide(conf, None)
    assert base["outcome"] == expect
    for s in ({"score": 0.95, "tier": "support_corroborated_covered"},
              {"score": 0.5, "tier": "no_independent_support"}):
        d = _decide(conf, s)
        assert (d["outcome"], d["failed"]) == (base["outcome"], base["failed"])
        assert d["model_confidence"] == conf and d["evidence_score"] == s
