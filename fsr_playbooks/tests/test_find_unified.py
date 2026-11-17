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


# -- kind='step': the query is a step TYPE, in whatever spelling the model has --

def _stub_step_examples(monkeypatch):
    import fsr_playbooks.mcp_server.tools_corpus as tc
    seen = []

    def fake(step_type, contains=None, limit=20):
        seen.append(step_type)
        return [{"step_name": "x", "step_type": step_type}]
    monkeypatch.setattr(tc, "find_step_examples", fake)
    return seen


def test_step_query_accepts_every_spelling_of_a_type(monkeypatch):
    """The examples are keyed by the canonical FSR name. A model writes the
    authoring name, spaced or cased its own way; each of these returned an
    EMPTY list (read as "no examples exist") while the catalog held thousands."""
    seen = _stub_step_examples(monkeypatch)
    cases = {
        "SetVariable": "SetVariable", "set_variable": "SetVariable",
        "set variable": "SetVariable", "Set Variable": "SetVariable",
        "decision": "Decision", "Decision": "Decision",
        "update_record": "UpdateRecord", "update record": "UpdateRecord",
        "UpdateRecord": "UpdateRecord",
        "start": "cybersponse.abstract_trigger",
        "manual_input": "ManualInput", "connector": "Connectors",
        "find_record": "FindRecords", "create_record": "InsertData",
        # extra words after the type: the type still decides
        "update_record comments": "UpdateRecord",
        "decision conditions when next default": "Decision",
    }
    for query, canonical in cases.items():
        r = find("step", query)
        assert r.get("step_type") == canonical, (query, r)
        assert r["results"] and r["kind"] == "step", (query, r)
    assert seen == list(cases.values())


def test_step_query_that_names_no_type_fails_loudly_with_the_vocabulary(monkeypatch):
    seen = _stub_step_examples(monkeypatch)
    for query in ("", "record", "branch condition", "how do I add a comment"):
        r = find("step", query)
        assert r["ok"] is False and r["code"] == "unknown_step_type", (query, r)
        assert {"set_variable", "decision", "update_record"} <= set(r["valid_step_types"])
        assert "results" not in r, "an empty list here reads as 'no examples exist'"
    assert seen == [], "no catalog search for a query that names no type"


def test_step_type_with_no_examples_says_so_instead_of_returning_empty(monkeypatch):
    """A packaged install has no step corpus. The empty list read as "try
    another wording"; say plainly that there is nothing to find."""
    import fsr_playbooks.mcp_server.tools_corpus as tc
    monkeypatch.setattr(tc, "find_step_examples", lambda *a, **kw: [])
    r = find("step", "decision")
    assert r["ok"] is False and r["code"] == "no_step_examples"
    assert r["step_type"] == "Decision" and "results" not in r


def test_step_examples_are_capped_however_many_are_asked_for(monkeypatch):
    """find's default limit is 10; ten step examples is several KB carried on
    every later round. Three show the shape."""
    import fsr_playbooks.mcp_server.tools_corpus as tc
    asked = []

    def fake(step_type, contains=None, limit=20):
        asked.append(limit)
        return [{"step_name": str(i)} for i in range(limit)]
    monkeypatch.setattr(tc, "find_step_examples", fake)
    assert len(find("step", "decision")["results"]) == tf.STEP_EXAMPLES_SHOWN
    assert len(find("step", "decision", limit=15)["results"]) == tf.STEP_EXAMPLES_SHOWN
    assert len(find("step", "decision", limit=1)["results"]) == 1
    assert asked == [3, 3, 1]
