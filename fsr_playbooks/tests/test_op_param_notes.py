"""Our notes on vendor op parameters reach the model, and cannot rot.

The model reads `get_op_schema` and `find(kind='operation')` through
`dispatch`; these tests read exactly that, not the note table.
"""
from __future__ import annotations

import json
import sqlite3

import pytest

from fsr_playbooks import op_param_notes as N
from fsr_playbooks.llm import tools as T
from fsr_playbooks.mcp_server import _shared


def _catalog_params(connector: str) -> set[tuple[str, str]]:
    with sqlite3.connect(_shared.DB_PATH) as c:
        return set(c.execute(
            "SELECT op_name, param_name FROM operation_params "
            "WHERE connector_name=?", (connector,)).fetchall())


def _need(connector: str) -> None:
    if not _catalog_params(connector):
        pytest.skip(f"catalog has no {connector!r} connector")


def test_every_note_names_a_real_connector_op_param():
    by_connector: dict[str, list[tuple[str, str]]] = {}
    for (c, o, p) in N.OP_PARAM_NOTES:
        by_connector.setdefault(c, []).append((o, p))
    checked = 0
    for connector, pairs in by_connector.items():
        have = _catalog_params(connector)
        if not have:
            continue  # this catalog lacks the connector: not checkable here
        missing = [pr for pr in pairs if pr not in have]
        assert missing == [], f"notes for {connector} name params the catalog lacks: {missing}"
        checked += len(pairs)
    if not checked:
        pytest.skip("catalog has none of the connectors the notes name")


def test_notes_are_short_and_have_an_example():
    for key, text in N.OP_PARAM_NOTES.items():
        assert len(text) < 400, key
        assert "e.g." in text or "=" in text, key


def _schema_md(op: str) -> str:
    out = T.dispatch("get_op_schema", {"connector": "servicenow", "op": op})
    return out["markdown"]


def test_get_op_schema_shows_the_note_beside_the_vendor_text():
    _need("servicenow")
    md = _schema_md("advance_search")
    line = next(ln for ln in md.splitlines() if ln.startswith("- adv_query"))
    assert "System ID, description, and state" in line     # vendor text stays
    assert N.NOTE_PREFIX in line                            # marked as ours
    assert "sysparm_query=short_descriptionLIKE" in line    # the working shape


@pytest.mark.parametrize("op", ["advance_search", "get_SIR", "fetch_incidents"])
def test_every_noted_op_shows_its_adv_query_note(op):
    _need("servicenow")
    line = next(ln for ln in _schema_md(op).splitlines() if ln.startswith("- adv_query"))
    assert N.NOTE_PREFIX in line


def test_fetch_incidents_time_params_state_the_t():
    _need("servicenow")
    md = _schema_md("fetch_incidents")
    for p in ("start_time", "end_time"):
        line = next(ln for ln in md.splitlines() if ln.startswith(f"- {p}"))
        assert N.NOTE_PREFIX in line and "T between date and time" in line


def test_verbose_schema_carries_the_note():
    _need("servicenow")
    out = T.dispatch("get_op_schema", {"connector": "servicenow",
                                       "op": "get_SIR", "verbose": True})
    p = next(x for x in out["params"] if x["param_name"] == "adv_query")
    assert p["note"].startswith(N.NOTE_PREFIX)


def test_find_single_match_embeds_the_note():
    _need("servicenow")
    out = T.dispatch("find", {"kind": "operation", "connector": "servicenow",
                              "query": "advance_search"})
    assert "schema" in out, out
    assert N.NOTE_PREFIX in out["schema"]["markdown"]


def test_find_multi_match_signature_carries_the_note():
    _need("servicenow")
    out = T.dispatch("find", {"kind": "operation", "connector": "servicenow",
                              "query": "SIR"})
    ops = {m["op_name"]: m for m in out["matches"]}
    adv = next(x for x in ops["get_SIR"]["params"] if x["name"] == "adv_query")
    assert adv["note"].startswith(N.NOTE_PREFIX)
    # ops with no note are untouched
    assert all("note" not in x for x in ops["delete_SIR"].get("params", []))


def test_unnoted_params_get_no_note():
    _need("servicenow")
    md = _schema_md("get_SIR")
    assert md.count(N.NOTE_PREFIX) == 1
    assert json.dumps(N.note_for("servicenow", "get_SIR", "table_name")) == "null"
