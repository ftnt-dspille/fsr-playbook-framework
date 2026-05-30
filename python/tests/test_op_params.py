"""Argument validation against the operation parameter schema (Phase 1.1).

A malformed (connector, op, params) call — unknown/typo'd param, missing
required field, or a select value outside the option set — must surface as
an actionable `bad_params` error BEFORE the op runs and BEFORE an approval
card is rendered, so the agent self-corrects instead of the analyst signing
off on a call that then fails at execute. Covered at the offline store
validator and `emit_action_card`.
"""
from __future__ import annotations

import sqlite3

import pytest

import fsr_core.mcp_server._shared as _shared


@pytest.fixture
def store(tmp_path, monkeypatch):
    """Temp store: one connector with one op and a realistic param schema."""
    db = tmp_path / "fsr_reference.db"
    con = sqlite3.connect(db)
    con.execute(
        "CREATE TABLE operations (connector_name TEXT, op_name TEXT, "
        "title TEXT, description TEXT, category TEXT)"
    )
    con.execute(
        """CREATE TABLE operation_params (
               connector_name TEXT, op_name TEXT,
               parent_param_name TEXT, condition_value TEXT,
               param_name TEXT, title TEXT, type TEXT,
               required INTEGER DEFAULT 0, default_value TEXT,
               options_json TEXT)"""
    )
    con.execute(
        "INSERT INTO operations (connector_name, op_name, category) VALUES "
        "('virustotal','get_ip_reputation','investigation')"
    )
    con.executemany(
        "INSERT INTO operation_params (connector_name, op_name, "
        "parent_param_name, condition_value, param_name, title, type, "
        "required, options_json) VALUES (?,?,?,?,?,?,?,?,?)",
        [
            ("virustotal", "get_ip_reputation", None, None, "ip", "IP", "text", 1, None),
            ("virustotal", "get_ip_reputation", None, None, "limit", "Limit", "integer", 0, None),
            ("virustotal", "get_ip_reputation", None, None, "scope", "Scope", "select", 0,
             '["public", "private"]'),
            # A conditional sub-param: must NOT be flagged as a top-level unknown.
            ("virustotal", "get_ip_reputation", "scope", "private", "vlan", "VLAN", "text", 1, None),
        ],
    )
    con.commit()
    con.close()
    monkeypatch.setattr(_shared, "DB_PATH", db)
    return db


# --- offline store validator ----------------------------------------------

def test_accepts_complete_valid_args(store):
    assert _shared._validate_op_params(
        "virustotal", "get_ip_reputation",
        {"ip": "1.2.3.4", "limit": 10, "scope": "public"}) is None


def test_accepts_string_int_for_integer_param(store):
    # FSR coerces "10" -> 10 at execute; don't false-reject.
    assert _shared._validate_op_params(
        "virustotal", "get_ip_reputation", {"ip": "1.2.3.4", "limit": "10"}) is None


def test_rejects_missing_required(store):
    err = _shared._validate_op_params(
        "virustotal", "get_ip_reputation", {"limit": 10})
    assert err is not None and err["code"] == "bad_params"
    probs = {(i["param"], i["problem"]) for i in err["issues"]}
    assert ("ip", "missing_required") in probs


def test_rejects_unknown_param_with_near_match(store):
    err = _shared._validate_op_params(
        "virustotal", "get_ip_reputation", {"ip": "1.2.3.4", "lmit": 10})
    issue = next(i for i in err["issues"] if i["param"] == "lmit")
    assert issue["problem"] == "unknown"
    assert "limit" in issue["near"]


def test_rejects_bad_select_value(store):
    err = _shared._validate_op_params(
        "virustotal", "get_ip_reputation", {"ip": "1.2.3.4", "scope": "global"})
    issue = next(i for i in err["issues"] if i["param"] == "scope")
    assert issue["problem"] == "bad_select_value"
    assert issue["options"] == ["public", "private"]


def test_rejects_uncoercible_integer(store):
    err = _shared._validate_op_params(
        "virustotal", "get_ip_reputation", {"ip": "1.2.3.4", "limit": "abc"})
    assert any(i["param"] == "limit" and i["problem"] == "bad_type"
               for i in err["issues"])


def test_skips_jinja_template_values(store):
    # Agent may pass a templated value; we can't see its runtime content.
    assert _shared._validate_op_params(
        "virustotal", "get_ip_reputation",
        {"ip": "{{vars.input.ip}}", "scope": "{{vars.scope}}"}) is None


def test_ignores_conditional_subparams(store):
    # `vlan` is a sub-param of `scope`; not providing it at top level is fine.
    assert _shared._validate_op_params(
        "virustotal", "get_ip_reputation", {"ip": "1.2.3.4"}) is None


def test_skips_when_no_params_catalogued(store):
    # Op with no params rows → can't validate; don't false-reject.
    assert _shared._validate_op_params(
        "virustotal", "some_uncatalogued_op", {"anything": 1}) is None


# --- emit_action_card -------------------------------------------------------

def test_emit_action_card_rejects_incomplete_args(store):
    from fsr_core.mcp_server.tools_emit import emit_action_card
    out = emit_action_card(
        id="c1", connector="virustotal", operation="get_ip_reputation",
        summary="Look up", args={"limit": 10}, editable_fields=["limit"],
    )
    assert out["ok"] is False and out["code"] == "bad_params"


def test_emit_action_card_allows_valid_args(store):
    from fsr_core.mcp_server.tools_emit import emit_action_card
    out = emit_action_card(
        id="c1", connector="virustotal", operation="get_ip_reputation",
        summary="Look up", args={"ip": "1.2.3.4"}, editable_fields=["ip"],
    )
    assert out["ok"] is True
