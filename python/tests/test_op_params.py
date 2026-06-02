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
               options_json TEXT,
               tooltip TEXT, placeholder TEXT, description TEXT,
               visible INTEGER DEFAULT 1, editable INTEGER DEFAULT 1,
               ord INTEGER DEFAULT 0)"""
    )
    con.execute(
        "INSERT INTO operations (connector_name, op_name, category) VALUES "
        "('virustotal','get_ip_reputation','investigation')"
    )
    con.executemany(
        "INSERT INTO operation_params (connector_name, op_name, "
        "parent_param_name, condition_value, param_name, title, type, "
        "required, options_json, ord) VALUES (?,?,?,?,?,?,?,?,?,?)",
        [
            ("virustotal", "get_ip_reputation", None, None, "ip", "IP", "text", 1, None, 0),
            ("virustotal", "get_ip_reputation", None, None, "limit", "Limit", "integer", 0, None, 1),
            ("virustotal", "get_ip_reputation", None, None, "scope", "Scope", "select", 0,
             '["public", "private"]', 2),
            # A conditional sub-param: must NOT be flagged as a top-level unknown.
            ("virustotal", "get_ip_reputation", "scope", "private", "vlan", "VLAN", "text", 1, None, 0),
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


def test_ignores_inactive_conditional_subparams(store):
    # `vlan` is required only when `scope=private`.
    assert _shared._validate_op_params(
        "virustotal", "get_ip_reputation", {"ip": "1.2.3.4"}) is None


def test_accepts_active_conditional_subparam(store):
    assert _shared._validate_op_params(
        "virustotal", "get_ip_reputation",
        {"ip": "1.2.3.4", "scope": "private", "vlan": "vlan-10"}) is None


def test_requires_active_conditional_subparam(store):
    err = _shared._validate_op_params(
        "virustotal", "get_ip_reputation",
        {"ip": "1.2.3.4", "scope": "private"})
    assert err is not None and err["code"] == "bad_params"
    assert any(i["param"] == "vlan" and i["problem"] == "missing_required"
               for i in err["issues"])


def test_accepts_fortigate_quarantine_conditional_args(store):
    con = sqlite3.connect(store)
    con.execute(
        "INSERT INTO operations (connector_name, op_name, category) VALUES "
        "('fortigate-firewall','block_ip_new','containment')"
    )
    con.executemany(
        "INSERT INTO operation_params (connector_name, op_name, "
        "parent_param_name, condition_value, param_name, title, type, "
        "required, options_json, ord) VALUES (?,?,?,?,?,?,?,?,?,?)",
        [
            ("fortigate-firewall", "block_ip_new", "", "", "method",
             "Block Method", "select", 1,
             '["Quarantine Based", "Policy Based"]', 0),
            ("fortigate-firewall", "block_ip_new", "method",
             "Quarantine Based", "ip_addresses", "IP Addresses", "text",
             1, None, 0),
            ("fortigate-firewall", "block_ip_new", "method",
             "Quarantine Based", "time_to_live", "Time to Live", "select",
             1, '["1 Hour", "12 Hour", "Custom Time"]', 1),
            ("fortigate-firewall", "block_ip_new", "time_to_live",
             "Custom Time", "duration", "Duration", "integer", 1, None, 0),
            ("fortigate-firewall", "block_ip_new", "method",
             "Policy Based", "ip_block_policy", "Policy Name", "text",
             1, None, 0),
        ],
    )
    con.commit()
    con.close()

    assert _shared._validate_op_params(
        "fortigate-firewall", "block_ip_new",
        {"method": "Quarantine Based",
         "ip_addresses": "1.1.1.1",
         "time_to_live": "12 Hour"}) is None


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


def test_get_op_schema_groups_conditional_params_with_empty_parent_sentinels(
        store, monkeypatch):
    """Connector warmup writes top-level parent/condition as empty strings.
    Treat those like NULL so onchange branches still render as select groups."""
    from fsr_core.mcp_server import tools_discovery as td

    monkeypatch.setattr(td._shared, "DB_PATH", store)
    con = sqlite3.connect(store)
    con.execute(
        "UPDATE operation_params SET parent_param_name='', condition_value='' "
        "WHERE parent_param_name IS NULL"
    )
    con.commit()
    con.close()

    out = td.get_op_schema("virustotal", "get_ip_reputation", verbose=True)

    assert out["visibility"]["always"] == ["ip", "limit", "scope"]
    assert out["visibility"]["when"]["scope=private"] == ["vlan"]
    assert out["param_groups_by_select"]["scope"]["private"]["params"] == [
        "ip", "limit", "vlan"]


def _add_schema_columns(store, *, static=None, observed=None):
    """Extend the fixture's operations row with the two output-schema columns."""
    con = sqlite3.connect(store)
    for col in ("output_schema_json", "conditional_output_schema_json",
                "output_schema_observed"):
        try:
            con.execute(f"ALTER TABLE operations ADD COLUMN {col} TEXT")
        except sqlite3.OperationalError:
            pass  # already added
    con.execute(
        "UPDATE operations SET output_schema_json=?, output_schema_observed=? "
        "WHERE connector_name='virustotal' AND op_name='get_ip_reputation'",
        (static, observed),
    )
    con.commit()
    con.close()


def test_get_op_schema_excludes_untyped_static_output_schema(store, monkeypatch):
    """E3: the static FortiSOAR output schema is untyped scaffolding and must
    never be surfaced — only the run-derived observed schema is trustworthy."""
    from fsr_core.mcp_server import tools_discovery as td

    monkeypatch.setattr(td._shared, "DB_PATH", store)
    # Static = 1000-line empty-string scaffold (simulated); observed = real shape.
    _add_schema_columns(
        store,
        static='{"general": {"reputation": "", "pulse_info": {"count": ""}}}',
        observed='{"reputation": 5, "country": "US"}',
    )

    out = td.get_op_schema("virustotal", "get_ip_reputation", verbose=True)
    # The untyped static scaffold is gone; the observed shape stays (parsed).
    assert "output_schema_json" not in out
    assert "conditional_output_schema_json" not in out
    assert out["output_schema_observed"] == {"reputation": 5, "country": "US"}


def test_get_op_schema_slim_hint_steers_to_run_op_for_safe_ops(store, monkeypatch):
    """E3: with no observed schema, a read-only (safe) op's slim hint points the
    agent at run_op to observe the real output rather than the excluded scaffold."""
    from fsr_core.mcp_server import tools_discovery as td

    monkeypatch.setattr(td._shared, "DB_PATH", store)
    _add_schema_columns(
        store,
        static='{"general": {"reputation": ""}}',  # present but ignored
        observed=None,                              # nothing observed yet
    )

    out = td.get_op_schema("virustotal", "get_ip_reputation")  # slim
    # get_ip_reputation starts with get_ -> safe; hint must mention run_op,
    # and must NOT claim a schema is "available" off the static scaffold.
    assert "run_op" in out["output_schema"]
    assert "available" not in out["output_schema"]


def test_get_op_schema_slim_hint_reports_observed_when_present(store, monkeypatch):
    from fsr_core.mcp_server import tools_discovery as td

    monkeypatch.setattr(td._shared, "DB_PATH", store)
    _add_schema_columns(store, static=None, observed='{"reputation": 5}')

    out = td.get_op_schema("virustotal", "get_ip_reputation")  # slim
    assert "observed" in out["output_schema"]
    assert "verbose=True" in out["output_schema"]
