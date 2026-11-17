"""Small tool-contract slips from live-session review: each cost the model a
round trip it should not have needed."""
from __future__ import annotations

import sqlite3

import pytest

from fsr_playbooks.mcp_server import tools_find, tools_jinja
from fsr_playbooks.mcp_server.tools_emit import emit_card


@pytest.fixture
def filter_db(monkeypatch, tmp_path):
    path = tmp_path / "f.sqlite"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE jinja_macros (name TEXT, signature TEXT, "
                "description TEXT, curated_doc TEXT, output_type_observed TEXT,"
                " output_type_declared TEXT, parameters_json TEXT)")
    for n in ("from_json", "to_json", "json_query", "regex_replace"):
        con.execute("INSERT INTO jinja_macros (name) VALUES (?)", (n,))
    con.execute("CREATE TABLE jinja_filter_usage (filter_name TEXT, "
                "expression TEXT, from_playbook TEXT, from_step TEXT, "
                "step_type TEXT, occurrences INT)")
    con.commit()
    con.close()

    def _db():
        c = sqlite3.connect(path)
        c.row_factory = sqlite3.Row
        return c
    monkeypatch.setattr(tools_jinja, "_db", _db)


def test_filter_usage_near_miss_suggests_the_real_filter(filter_db):
    out = tools_find.find(kind="filter_usage", query="fromjson")
    assert "error" in out
    assert out["suggestions"][0] == "from_json"
    assert "from_json" in out["error"]


def test_filter_usage_no_near_miss_has_no_bogus_suggestion(filter_db):
    out = tools_find.find(kind="filter_usage", query="zzzzqqq")
    assert "error" in out and not out.get("suggestions")


def test_find_example_without_connector_says_connector_is_needed(
        monkeypatch, tmp_path):
    import sys
    import types
    common = types.ModuleType("probes.common")
    common.CATALOG_DB_PATH = tmp_path / "absent.sqlite"
    pkg = types.ModuleType("probes")
    pkg.common = common
    monkeypatch.setitem(sys.modules, "probes", pkg)
    monkeypatch.setitem(sys.modules, "probes.common", common)
    out = tools_find.find(kind="example", query="block ip")
    assert out["code"] == "catalog_unavailable"
    assert "without `connector`" in out["message"]
    assert "connector=<name>" in out["message"]


def test_single_option_with_allow_text_is_a_valid_choice_card():
    r = emit_card("choice", {
        "id": "c1", "prompt": "What should it do?", "allow_text": True,
        "options": [{"label": "Enrich the alert", "value": "enrich"}]})
    assert r["ok"] is True and r["card"]["type"] == "choice_card"


def test_single_option_without_allow_text_still_refused_and_says_how():
    r = emit_card("choice", {
        "id": "c1", "prompt": "pick",
        "options": [{"label": "a", "value": "a"}]})
    assert r["ok"] is False and r["code"] == "too_few_options"
    assert "allow_text" in r["message"]
