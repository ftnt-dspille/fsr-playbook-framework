"""Phase 2 step 2b: the evidence-score ladder fixes (still shadow, nothing decides
on the score). One group per change, each written to fail without its change:

1. coverage counts only sources that can hold evidence about the subject, and
   credits a native-MCP tool as a query of its source
2. the ladder: 0.80 / 0.85 (coverage) / 0.90 (corroboration) / 0.95 (both)
3. a hedge disposition (suspicious, needs_more_info) is capped
4. benign corroboration distinguishes record kinds; a generic record read or
   module search never corroborates a conviction
5. derived network addresses and handed-in identifiers are sourced
"""
from __future__ import annotations

import pytest

from fsr_playbooks.mcp_server import _citation_validator as cv
from fsr_playbooks.mcp_server._evidence_score import score_verdict
from fsr_playbooks.mcp_server.tools_emit import emit_card

IP = "203.0.113.9"
HOST_IP = "100.64.4.5"
RECORD = "11111111-2222-3333-4444-555555555555"
MAL = {"source": "VirusTotal", "verdict": "malicious", "severity": "error"}

SOURCES = {"siem_": "FortiSIEM", "faz_": "FortiAnalyzer", "fmg_": "FortiManager"}
CONNECTORS = {"virustotal": {"label": "VirusTotal", "kind": "intel"},
              "servicenow": {"label": "ServiceNow", "kind": "tickets"}}


def vt(ip=IP):
    return {"name": "run_op", "ok": True, "finding": MAL, "idents": [ip],
            "args": {"connector": "virustotal", "op": "query_ip", "params": {"ip": ip}}}


def siem(ip=IP):
    return {"name": "siem_search_events", "ok": True, "idents": [ip],
            "args": {"query": ip}}


def read(module, ip=IP, name="search_module_records"):
    return {"name": name, "ok": True, "idents": [ip],
            "args": {"module": module, "filters": {"q": ip}}}


def card(disposition="true_positive", summary=None, ips=(IP,)):
    s = summary or "beaconing to " + " and ".join(ips)
    return {"id": "v", "disposition": disposition, "confidence": 0.9, "summary": s,
            "findings": [{"claim": s, "evidence": ["a"]}]}


def score(c, registry, unchecked=(), **kw):
    return score_verdict(c, registry, record_subject=RECORD,
                         unchecked_sources=list(unchecked), ready_sources=SOURCES,
                         ready_connectors=CONNECTORS, **kw)


# ---- 1. applicable-source coverage ------------------------------------------------

def test_native_mcp_tools_count_as_queried_sources():
    mcp = {"name": "mcp_fortisiem__get_reputation_by_entity", "ok": True,
           "finding": MAL, "idents": [IP], "args": {"entity": IP}}
    s = score(card(), {"a": mcp}, ["FortiSIEM", "VirusTotal"])
    assert s["components"]["coverage"] is True, s["missing"]


def test_an_unqueried_native_mcp_product_is_still_missing():
    other = {"name": "mcp_otherthing__lookup", "ok": True, "finding": None,
             "idents": [IP], "args": {}}
    s = score(card(), {"a": vt(), "b": other}, ["FortiSIEM"])
    assert s["components"]["coverage"] is False


def test_management_plane_and_aggregator_do_not_hold_external_indicator_evidence():
    s = score(card(), {"a": vt(), "b": siem()}, ["FortiAnalyzer", "FortiManager"])
    assert s["components"]["coverage"] is True and s["score"] == 0.95
    # the SIEM is still applicable to the same question
    s = score(card(), {"a": vt()}, ["FortiSIEM", "FortiAnalyzer"])
    assert s["components"]["coverage"] is False
    assert s["missing"][-1].endswith("FortiSIEM")


def test_an_internal_only_question_still_counts_the_aggregator():
    c = card("benign", ips=(HOST_IP,))
    reg = {"t": read("assets", HOST_IP)}
    s = score(c, reg, ["FortiAnalyzer"])
    assert s["components"]["coverage"] is False


def test_external_intel_does_not_apply_to_an_internal_address():
    c = card("benign", ips=(HOST_IP,))
    reg = {"t": read("assets", HOST_IP)}
    assert score(c, reg, ["VirusTotal"])["components"]["coverage"] is True
    # but an external address is exactly what intel is for
    c = card("benign", ips=(IP,))
    reg = {"t": read("assets", IP)}
    assert score(c, reg, ["VirusTotal"])["components"]["coverage"] is False


def test_a_hash_is_an_indicator_intel_applies_to():
    h = "a" * 64
    c = card("benign", summary=f"file {h} on {HOST_IP}", ips=())
    reg = {"t": {"name": "get_record", "ok": True, "idents": [HOST_IP, h],
                 "args": {"module": "assets"}}}
    assert score(c, reg, ["VirusTotal"])["components"]["coverage"] is False


# ---- 2. the ladder ----------------------------------------------------------------

def test_ladder_values_and_order():
    reg = {"a": vt(), "b": siem()}
    only = score(card(), {"a": vt()}, ["ServiceNow"])
    covered = score(card(), {"a": vt()}, [])
    corro = score(card(), reg, ["ServiceNow"])
    full = score(card(), reg, [])
    assert [x["score"] for x in (only, covered, corro, full)] == [0.8, 0.85, 0.9, 0.95]
    assert corro["score"] > covered["score"]


# ---- 3. hedge dispositions ----------------------------------------------------------

@pytest.mark.parametrize("d", ["suspicious", "needs_more_info"])
def test_a_hedge_disposition_is_capped(d):
    s = score(card(d), {"a": vt(), "b": siem()}, [])
    assert s["score"] == 0.5 and "hedge_disposition" in s["capped_by"]


def test_a_decided_disposition_is_not_capped_by_the_hedge_rule():
    s = score(card("true_positive"), {"a": vt(), "b": siem()}, [])
    assert "hedge_disposition" not in s["capped_by"]


# ---- 4. record kind ----------------------------------------------------------------

def test_benign_asset_plus_change_record_corroborate():
    c = card("benign", ips=(HOST_IP,))
    reg = {"a": read("assets", HOST_IP), "b": read("change_requests", HOST_IP)}
    s = score(c, reg, [])
    assert s["components"]["corroboration"] is True and s["score"] == 0.95
    assert sorted(s["support_classes"]) == ["other:asset", "other:change"]


def test_benign_two_reads_of_the_same_kind_are_one_source():
    c = card("benign", ips=(HOST_IP,))
    reg = {"a": read("assets", HOST_IP), "b": read("assets", HOST_IP, name="get_record")}
    s = score(c, reg, [])
    assert s["components"]["corroboration"] is False and s["score"] == 0.85


def test_a_module_search_is_not_a_second_source_for_a_conviction():
    # a C2 rating plus a module search that only echoes the alert
    reg = {"a": vt(), "echo": read("alerts")}
    s = score(card(), reg, [])
    assert s["components"]["corroboration"] is False and s["score"] == 0.85


def test_a_log_product_run_through_the_generic_runner_is_a_log_hit():
    hit = {"name": "run_op", "ok": True, "idents": [IP],
           "args": {"connector": "fortinet-fortisiemv2", "op": "execute_api_request"}}
    s = score(card(), {"a": vt(), "b": hit}, [])
    assert s["components"]["corroboration"] is True
    # and it is not exculpatory for a benign call
    assert score(card("benign"), {"b": hit}, [])["components"]["support"] is False


# ---- 5. provenance ----------------------------------------------------------------

def test_a_network_address_derived_from_a_sourced_address_is_not_a_recital():
    reg = {"a": vt("192.0.2.9"), "b": siem("192.0.2.9")}
    c = card(summary="beaconing to 192.0.2.9 within 192.0.2.0/24")
    s = score(c, reg, [])
    assert s["components"]["provenance"] is True and s["score"] == 0.95
    c = card(summary="beaconing to 192.0.2.9; the 192.0.2.0 network is hostile")
    assert score(c, reg, [])["components"]["provenance"] is True


def test_a_cidr_over_no_sourced_address_is_still_a_recital():
    reg = {"a": vt(), "b": siem()}
    c = card(summary=f"beaconing to {IP} and the 198.51.100.0/24 range")
    s = score(c, reg, [])
    assert s["capped_by"] == ["unsourced_identifier"] and s["score"] == 0.5


def test_a_fabricated_address_is_still_capped():
    reg = {"a": vt(), "b": siem()}
    c = card(summary=f"beaconing to {IP}, relay 192.0.2.77")
    assert score(c, reg, [])["capped_by"] == ["unsourced_identifier"]


def test_identifiers_the_turn_was_handed_are_sourced():
    reg = {"a": vt(), "b": siem()}
    c = card(summary=f"beaconing to {IP} from {HOST_IP}")
    assert score(c, reg, [])["capped_by"] == ["unsourced_identifier"]
    s = score(c, reg, [], known_extra=[HOST_IP])
    assert s["capped_by"] == [] and s["score"] == 0.95


@pytest.fixture
def handed_turn():
    cv.clear_tool_registry()
    cv.register_tool_result("call_vt", "run_op", True,
                            {"connector": "virustotal", "op": "query_ip",
                             "params": {"ip": IP}}, {"ok": True, "data": {"ip": IP}})
    yield
    cv.set_turn_known_context(None)
    cv.clear_tool_registry()


def test_the_emit_path_reads_the_analyst_message_and_the_mounted_record(handed_turn):
    from fsr_playbooks.llm import session_state as ss
    payload = {"disposition": "true_positive", "severity": "high", "confidence": 0.8,
               "summary": f"{IP} contacted from {HOST_IP}", "unknowns": [],
               "findings": [{"claim": f"{HOST_IP} sent to {IP}", "evidence": ["call_vt"]}]}
    r = emit_card(card_type="verdict", payload=dict(payload))
    assert r["card"]["evidence_score"]["capped_by"] == ["unsourced_identifier"]
    cv.set_turn_known_context({"sourceIp": HOST_IP})
    r = emit_card(card_type="verdict", payload=dict(payload))
    assert "unsourced_identifier" not in r["card"]["evidence_score"]["capped_by"]
    cv.set_turn_known_context(None)
    with ss.bound(ss.SessionState(user_message=f"is {HOST_IP} ok?")):
        r = emit_card(card_type="verdict", payload=dict(payload))
    assert "unsourced_identifier" not in r["card"]["evidence_score"]["capped_by"]


# ---- 6. step 2c: the contradiction cap needs a real contradiction -----------------

def weak_vt(ip=IP, score_str="3/94"):
    f = {"source": "VirusTotal", "verdict": "malicious", "severity": "error",
         "score_str": score_str}
    return {"name": "run_op", "ok": True, "finding": f, "idents": [ip],
            "args": {"connector": "virustotal", "op": "query_ip", "params": {"ip": ip}}}


def clean_vt(ip=IP):
    return {"name": "run_op", "ok": True, "idents": [ip],
            "finding": {"source": "VirusTotal", "verdict": "clean", "severity": "ok",
                        "score_str": "0/94"},
            "args": {"connector": "virustotal", "op": "query_ip", "params": {"ip": ip}}}


def test_a_few_detections_do_not_contradict_a_record_backed_benign_call():
    reg = {"a": read("assets"), "b": read("change_requests"), "c": weak_vt()}
    s = score(card("false_positive"), reg)
    assert "contradiction" not in s["capped_by"], s
    assert s["score"] >= 0.85


@pytest.mark.parametrize("score_str", ["4/94", "9/200", "3/60"])
def test_weak_scales_are_weak(score_str):
    reg = {"a": read("assets"), "c": weak_vt(score_str=score_str)}
    assert "contradiction" not in score(card("false_positive"), reg)["capped_by"]


@pytest.mark.parametrize("score_str", ["12/94", "47/94", "5/94", "2/3", None])
def test_real_detections_still_contradict_a_benign_call(score_str):
    reg = {"a": read("assets"), "c": weak_vt(score_str=score_str)}
    s = score(card("false_positive"), reg)
    assert "contradiction" in s["capped_by"] and s["score"] == 0.5


def test_weak_rating_still_contradicts_a_benign_call_with_no_record_behind_it():
    # benign resting only on a clean rating from another feed, no record
    reg = {"a": clean_vt(), "c": weak_vt("203.0.113.9")}
    s = score(card("false_positive"), reg)
    assert "contradiction" in s["capped_by"]


def test_clean_rating_does_not_contradict_a_log_backed_conviction():
    reg = {"a": clean_vt(), "b": siem()}
    s = score(card(), reg)
    assert "contradiction" not in s["capped_by"], s
    assert s["components"]["no_contradiction"] is True
    # still honest: nothing rated the subject malicious, so no support
    assert s["tier"] == "no_independent_support" and s["score"] == 0.5
    assert any("log hits" in m for m in s["missing"])


def test_clean_rating_still_contradicts_a_conviction_with_a_malicious_rating():
    reg = {"a": clean_vt(), "b": siem(), "c": vt()}
    assert "contradiction" in score(card(), reg)["capped_by"]


def test_clean_rating_still_contradicts_a_conviction_with_no_log_hit():
    reg = {"a": clean_vt(), "b": read("alerts")}
    assert "contradiction" in score(card(), reg)["capped_by"]


# ---- 7. step 2c: a native-MCP log tool is a log hit --------------------------------

def mcp_rep():
    return {"name": "mcp_fortisiem__get_reputation_by_entity", "ok": True,
            "finding": MAL, "idents": [IP], "args": {"entity": IP}}


def mcp_incidents(server="fortisiem", tool="get_incidents_by_entity"):
    return {"name": f"mcp_{server}__{tool}", "ok": True, "idents": [IP],
            "args": {"entity": IP}}


def test_native_mcp_log_lookup_corroborates_a_native_mcp_rating():
    s = score(card(), {"a": mcp_rep(), "b": mcp_incidents()}, ["FortiSIEM"])
    assert s["components"]["corroboration"] is True, s["missing"]
    assert s["tier"] == "support_corroborated_covered" and s["score"] == 0.95


def test_native_mcp_log_lookup_is_a_log_class_not_a_record_read():
    s = score(card(), {"a": vt(), "b": mcp_incidents(tool="get_context_by_entity")}, [])
    assert s["components"]["corroboration"] is True


def test_a_non_log_native_mcp_server_still_does_not_corroborate():
    s = score(card(), {"a": vt(), "b": mcp_incidents("utility", "global_search")}, [])
    assert s["components"]["corroboration"] is False and s["score"] == 0.85
