"""`run_op` against a connector that exists nowhere must bounce a clean
`unknown_connector` error BEFORE the tier gate — not escalate an uncatalogued
connector to a tier-3 approval card the model can't act on.

Regression for the live 8.0 case: an alert hunt with no SIEM configured
fabricated `run_op("fortinet-fortisiem", "siem_search_host")` and parked on an
approval card instead of self-correcting the way the dedicated `siem_*` wrappers
already do.
"""
from __future__ import annotations

import sqlite3

import pytest

from fsr_playbooks.llm import tools as tools_mod


@pytest.fixture()
def db_with_one_connector(tmp_path, monkeypatch):
    """A reference DB whose `connectors` table holds exactly `real-connector`."""
    db = tmp_path / "ref.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE connectors (name TEXT)")
    con.execute("INSERT INTO connectors (name) VALUES ('real-connector')")
    con.commit()
    con.close()
    monkeypatch.setattr(tools_mod, "_DB_PATH", db)
    return db


def test_absent_connector_returns_unknown_connector(db_with_one_connector, monkeypatch):
    # stale hint None ⇒ the connector truly exists nowhere ⇒ clean bounce.
    monkeypatch.setattr(
        "fsr_playbooks.mcp_server._shared.stale_catalog_hint", lambda c: None)
    err = tools_mod._run_op_absent_connector_error("fortinet-fortisiem", "siem_search_host")
    assert err is not None
    assert err["code"] == "unknown_connector"
    assert err["connector"] == "fortinet-fortisiem"
    assert err["ok"] is False
    assert err["suggestions"], "must guide the model to self-correct"


def test_catalogued_connector_falls_through(db_with_one_connector):
    # Known connector ⇒ None ⇒ normal tiering decides (may still card).
    assert tools_mod._run_op_absent_connector_error("real-connector", "any_op") is None


def test_stale_catalog_connector_stays_conservative(db_with_one_connector, monkeypatch):
    # Absent from catalog but present on the box (installed-after-warmup) ⇒
    # keep the conservative path, do NOT misreport it as missing.
    monkeypatch.setattr(
        "fsr_playbooks.mcp_server._shared.stale_catalog_hint",
        lambda c: {"code": "stale_catalog", "message": "re-warmup", "suggestions": []})
    assert tools_mod._run_op_absent_connector_error("just-installed", "some_op") is None


def test_empty_connector_is_noop(db_with_one_connector):
    assert tools_mod._run_op_absent_connector_error("", "op") is None


def test_dispatch_bounces_absent_connector_instead_of_carding(db_with_one_connector, monkeypatch):
    """End-to-end: an ungranted `run_op` against an absent connector returns the
    clean error instead of a `pending_approval` approval card."""
    monkeypatch.setattr(
        "fsr_playbooks.mcp_server._shared.stale_catalog_hint", lambda c: None)
    out = tools_mod.dispatch("run_op",
                             {"connector": "fortinet-fortisiem", "op": "siem_search_host"})
    assert isinstance(out, dict)
    assert out.get("code") == "unknown_connector"
    assert not out.get("pending_approval"), "must NOT surface an approval card"
    assert "approval_id" not in out
