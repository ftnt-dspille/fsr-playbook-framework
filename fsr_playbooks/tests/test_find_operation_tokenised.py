"""find_operation searches a multi-word ``q`` word by word and never answers empty
for a connector that has read ops.

A run searched ``find(kind="operation", connector="servicenow", query="search
tickets by keyword incident change")``. The whole string is a substring of no op,
so it came back empty, the agent never queried the ticket system, and the verdict
missed the deciding ticket. The ops were advance_search, search_record and
fetch_incidents.
"""
from __future__ import annotations

import sqlite3

import pytest

from fsr_playbooks.mcp_server.tools_discovery import _op_query_tokens, find_operation

_SCHEMA = """
CREATE TABLE connectors (name TEXT PRIMARY KEY);
CREATE TABLE operations (
    connector_name TEXT NOT NULL, op_name TEXT NOT NULL, title TEXT,
    annotation TEXT, category TEXT, description TEXT,
    visible INTEGER DEFAULT 1, enabled INTEGER DEFAULT 1,
    output_schema_json TEXT, conditional_output_schema_json TEXT,
    PRIMARY KEY (connector_name, op_name));
CREATE TABLE verifications (kind TEXT, key TEXT, status TEXT, method TEXT, ts TEXT, notes TEXT);
CREATE TABLE operation_params (
    connector_name TEXT, op_name TEXT, param_name TEXT, title TEXT, type TEXT,
    required INTEGER, ord INTEGER, parent_param_name TEXT, condition_value TEXT);
"""
_OPS = [
    ("advance_search", "Advanced Search", "Search records with a query"),
    ("search_record", "Search Record", "Find records by keyword"),
    ("fetch_incidents", "Fetch Incidents", "Fetch incident records"),
    ("create_record", "Create Record", "Create a record"),
    ("delete_record", "Delete Record", "Delete a record"),
]


@pytest.fixture()
def db(tmp_path):
    path = tmp_path / "ref.db"
    c = sqlite3.connect(path)
    c.executescript(_SCHEMA)
    c.execute("INSERT INTO connectors VALUES ('servicenow')")
    for op, title, desc in _OPS:
        c.execute("INSERT INTO operations (connector_name, op_name, title, description)"
                  " VALUES ('servicenow', ?, ?, ?)", (op, title, desc))
    c.commit()
    c.close()
    return str(path)


def _names(r):
    return [m["op_name"] for m in r["matches"]]


def test_tokens_drop_noise_and_add_singulars():
    assert _op_query_tokens("search tickets by keyword incident change") == [
        "search", "tickets", "ticket", "keyword", "incident", "change"]
    assert _op_query_tokens("advance_search") == []


def test_multiword_query_matches_ops_by_their_words(db):
    r = find_operation("servicenow", "search tickets by keyword incident change",
                       db_path=db)
    names = _names(r)
    assert {"advance_search", "search_record", "fetch_incidents"} <= set(names)
    assert "delete_record" not in names
    assert r["token_note"]


def test_best_match_ranks_first(db):
    r = find_operation("servicenow", "search keyword", db_path=db)
    assert _names(r)[0] in {"advance_search", "search_record"}


def test_phrase_hit_is_unchanged(db):
    r = find_operation("servicenow", "fetch_incidents", db_path=db)
    assert _names(r) == ["fetch_incidents"]
    assert "token_note" not in r


def test_no_match_lists_the_read_ops_not_empty(db):
    r = find_operation("servicenow", "zzqq wibble", db_path=db)
    names = _names(r)
    assert set(names) == {"advance_search", "search_record", "fetch_incidents"}
    assert r["listing_note"]


def test_unknown_connector_is_still_a_miss(db):
    r = find_operation("nosuch", "zzqq wibble", db_path=db)
    assert r["matches"] == [] and r["suggestion"]
