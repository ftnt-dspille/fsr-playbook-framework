"""TRIAGE_BUILD_AUDIT C2 — an unsynced WorkflowPriority picklist must not read
as an authoring bug. When the reference DB has zero priority rows we can't
validate against anything, so priority is left unset SILENTLY (no bad_value
warning); when rows DO exist, an unknown name still warns as before.
"""
from __future__ import annotations

import sqlite3
from types import SimpleNamespace


from fsr_playbooks.compiler.ir import PRIORITY_LIST_NAME
from fsr_playbooks.compiler.resolver import Resolver


def _resolver_with_priorities(values: list[str]) -> Resolver:
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE picklists (list_name TEXT, item_value TEXT, item_iri TEXT)")
    conn.executemany(
        "INSERT INTO picklists VALUES (?,?,?)",
        [(PRIORITY_LIST_NAME, v, f"/api/3/picklists/{v}") for v in values],
    )
    conn.commit()
    r = Resolver.__new__(Resolver)  # bypass __init__'s file open
    r.conn = conn
    r.conn.row_factory = sqlite3.Row
    return r


def test_unsynced_priority_is_silent():
    r = _resolver_with_priorities([])  # nothing synced
    pb = SimpleNamespace(priority="High", priority_iri=None)
    errors: list = []
    r._resolve_priority(pb, "playbooks[0]", errors)
    assert errors == [], "unsynced picklist must not emit a warning"
    assert pb.priority is None


def test_known_priority_resolves_iri():
    r = _resolver_with_priorities(["High", "Low"])
    pb = SimpleNamespace(priority="High", priority_iri=None)
    errors: list = []
    r._resolve_priority(pb, "playbooks[0]", errors)
    assert errors == []
    assert pb.priority_iri == "/api/3/picklists/High"


def test_unknown_priority_with_synced_list_still_warns():
    r = _resolver_with_priorities(["High", "Low"])
    pb = SimpleNamespace(priority="Critikal", priority_iri=None)
    errors: list = []
    r._resolve_priority(pb, "playbooks[0]", errors)
    assert len(errors) == 1
    assert pb.priority is None
