"""Zero-hit find_operation retries with domain synonyms and says so.

Live (2026-08-17): asked to bottle an investigation into a playbook, the agent
searched ``find_operation("fortinet-fortisiemv2", q="get alert")``. FortiSIEM's
term for alerts is *incidents*, so the LIKE search returned nothing, difflib
ranked ``get_user_context`` as "closest", and the agent concluded the
capability didn't exist and dead-ended the analyst. A vocabulary miss must not
read as an absent capability: on zero hits the search retries with
cross-product synonyms (alert↔incident/offense/…) and, when one lands, names
the product's term so the model learns it instead of capitulating.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from fsr_playbooks.mcp_server.tools_discovery import (
    _synonym_queries,
    find_operation,
)


def test_synonym_queries_cover_the_live_miss():
    alts = [a for a, _ in _synonym_queries("get alert")]
    assert "get incident" in alts   # phrase form (titles/descriptions)
    assert "incident" in alts       # bare term (snake_case op names)


def test_synonym_queries_handle_plurals():
    alts = [a for a, _ in _synonym_queries("get alerts")]
    assert "incident" in alts


def test_unknown_terms_produce_no_alternatives():
    assert _synonym_queries("frobnicate the widget") == []


# The suite may isolate the default catalog; target the repo DB explicitly.
_REPO_DB = str(Path(__file__).resolve().parents[2] / "data" / "fsr_reference.db")


def _fortisiem_in_store() -> bool:
    r = find_operation("fortinet-fortisiemv2", "", db_path=_REPO_DB)
    return bool(r.get("matches"))


@pytest.mark.skipif(not _fortisiem_in_store(),
                    reason="fortinet-fortisiemv2 not in the reference store")
def test_get_alert_on_fortisiem_finds_incident_ops():
    """The exact live query. Must return incident ops + an explanation."""
    r = find_operation("fortinet-fortisiemv2", "get alert", db_path=_REPO_DB)
    ops = [m["op_name"] for m in r["matches"]]
    assert any("incident" in op for op in ops), ops
    note = r.get("synonym_note", "")
    assert "incident" in note and "alert" in note, note
