"""The consolidated `find` tool dispatches to the right catalog (Phase 1).

Unit-level: the constituents are stubbed, so these pin the ROUTING contract
(kind vocabulary, required args, the typed action_type field, list-wrapping)
without a box or a warmed reference DB.
"""
from __future__ import annotations

import fsr_playbooks.mcp_server.tools_find as tf
from fsr_playbooks.mcp_server import find


def test_unknown_kind_names_the_vocabulary():
    r = find("frobnicate", "x")
    assert r["ok"] is False and r["code"] == "unknown_kind"
    assert "action" in r["valid_kinds"]


def test_operation_without_connector_says_what_to_do_first():
    r = find("operation", "block ip")
    assert r["ok"] is False and r["code"] == "missing_connector"
    assert "kind='connector'" in r["message"]


def test_kind_tag_rides_on_dict_results(monkeypatch):
    import fsr_playbooks.mcp_server as m
    monkeypatch.setattr(m, "find_connector",
                        lambda q, limit=15: {"matches": [{"name": q}]})
    r = find("connector", "virustotal")
    assert r["kind"] == "connector" and r["matches"]


def test_list_results_are_wrapped(monkeypatch):
    import fsr_playbooks.mcp_server as m
    monkeypatch.setattr(m, "find_jinja_filter",
                        lambda q, limit=15: [{"name": "ipaddr"}])
    r = find("jinja", "extract ip")
    assert r["kind"] == "jinja" and r["results"][0]["name"] == "ipaddr"


def _stub_action_catalogs(monkeypatch):
    import fsr_playbooks.mcp_server as m
    monkeypatch.setattr(m, "find_containment_actions",
                        lambda target_type="", limit=25, **kw: {
                            "probed": True,
                            "actions": [{"connector": "fortigate",
                                         "op": "block_ip_new", "tier": 3}]})
    monkeypatch.setattr(m, "find_enrichment_actions",
                        lambda target_type="", limit=25, **kw: {
                            "probed": True,
                            "actions": [{"connector": "virustotal",
                                         "op": "ip_reputation", "tier": 1}]})
    monkeypatch.setattr(m, "find_record_actions",
                        lambda action="", module="alerts", **kw: (
                            {"ok": False, "code": "unknown_action"}
                            if action not in ("", "comment") else
                            {"actions": [{"action": "comment",
                                          "connector": "cyops_utilities",
                                          "tier": 3}]}))


def test_action_kind_merges_families_with_a_typed_field(monkeypatch):
    _stub_action_catalogs(monkeypatch)
    r = find("action", target_type="ip")
    fams = {a["action_type"] for a in r["actions"]}
    assert fams == {"containment", "enrichment"}
    assert r["count"] == 2 and "containment" in r["sections"]


def test_action_type_restricts_to_one_family(monkeypatch):
    _stub_action_catalogs(monkeypatch)
    r = find("action", target_type="ip", action_type="enrichment")
    assert [a["action_type"] for a in r["actions"]] == ["enrichment"]


def test_record_family_recovers_from_a_prose_query(monkeypatch):
    _stub_action_catalogs(monkeypatch)
    r = find("action", "write a note about the verdict", action_type="record")
    assert [a["action"] for a in r["actions"]] == ["comment"]


def test_bad_action_type_names_the_vocabulary(monkeypatch):
    _stub_action_catalogs(monkeypatch)
    r = find("action", action_type="destroy")
    assert r["ok"] is False and r["code"] == "unknown_action_type"


def test_find_is_in_the_llm_registry_with_the_enum_schema():
    from fsr_playbooks.llm.tools import REGISTRY, SAFE_TOOLS, TOOL_TIERS
    assert "find" in SAFE_TOOLS and TOOL_TIERS["find"] == 1
    spec = REGISTRY["find"]
    kinds = spec.input_schema["properties"]["kind"]["enum"]
    assert set(kinds) == set(tf.FIND_KINDS)
    # Selection guidance lives in the description, not 100 lines into a
    # prompt (assessment Phase 1.5).
    assert "Which kind to pick" in spec.description
