"""Operation-existence validation (regression for the 'agent proposed a
VirusTotal op that doesn't exist' bug).

A hallucinated/typo'd (connector, op) must surface as an actionable
`unknown_operation` error BEFORE the user is asked to approve it — never
an opaque post-approval execution failure. Covered at three layers: the
offline store validator, `emit_action_card`, and the live-FSR fallback
(`_validate_op_live`).
"""
from __future__ import annotations

import sqlite3

import pytest

import fsr_playbooks.mcp_server._shared as _shared


@pytest.fixture(autouse=True)
def _isolate_op_def_cache(tmp_path, monkeypatch):
    """The live op-def cache is sqlite-backed at `tools_execution.DB_PATH`;
    isolate it per-test so ops cached by one test never leak into another (or
    touch the real reference store). Tests that need a specific DB override
    this with their own `monkeypatch.setattr(te, "DB_PATH", ...)` afterward."""
    from fsr_playbooks.mcp_server import tools_execution as te
    monkeypatch.setattr(te, "DB_PATH", str(tmp_path / "op_def_cache.db"))


@pytest.fixture
def store(tmp_path, monkeypatch):
    """Point the reference DB at a temp store with one connector + ops."""
    db = tmp_path / "fsr_reference.db"
    con = sqlite3.connect(db)
    con.execute(
        "CREATE TABLE operations (connector_name TEXT, op_name TEXT, "
        "title TEXT, description TEXT, category TEXT)"
    )
    con.executemany(
        "INSERT INTO operations (connector_name, op_name, category) VALUES (?,?,?)",
        [
            ("virustotal", "get_ip_reputation", "investigation"),
            ("virustotal", "get_domain_reputation", "investigation"),
            ("virustotal", "get_file_reputation", "investigation"),
        ],
    )
    con.commit()
    con.close()
    monkeypatch.setattr(_shared, "DB_PATH", db)
    return db


# --- offline store validator ----------------------------------------------

def test_validate_op_exists_accepts_real_op(store):
    assert _shared._validate_op_exists("virustotal", "get_ip_reputation") is None


def test_validate_op_exists_rejects_phantom_op(store):
    err = _shared._validate_op_exists("virustotal", "lookup_ip")
    assert err is not None
    assert err["ok"] is False
    assert err["code"] == "unknown_operation"
    assert err["connector"] == "virustotal"
    assert err["op"] == "lookup_ip"


def test_validate_op_exists_suggests_near_match(store):
    err = _shared._validate_op_exists("virustotal", "get_ip_rep")
    assert err["code"] == "unknown_operation"
    assert "get_ip_reputation" in err["near"]


def test_validate_op_exists_skips_empty_catalogue(store):
    """Unknown connector (no ops catalogued) → can't prove non-existence,
    so don't false-reject; the connector check / live exec guard it."""
    assert _shared._validate_op_exists("not-synced-connector", "anything") is None


# --- emit_action_card -------------------------------------------------------

def test_emit_action_card_rejects_phantom_op(store):
    from fsr_playbooks.mcp_server.tools_emit import emit_action_card
    out = emit_action_card(
        id="c1", connector="virustotal", operation="lookup_ip",
        summary="Look up the IP", args={"ip": "1.2.3.4"}, editable_fields=["ip"],
    )
    assert out["ok"] is False
    assert out["code"] == "unknown_operation"


def test_emit_action_card_allows_real_op(store):
    from fsr_playbooks.mcp_server.tools_emit import emit_action_card
    out = emit_action_card(
        id="c1", connector="virustotal", operation="get_ip_reputation",
        summary="Look up the IP", args={"ip": "1.2.3.4"}, editable_fields=["ip"],
    )
    assert out["ok"] is True
    assert out["card"]["operation"] == "get_ip_reputation"


# --- live-FSR fallback ------------------------------------------------------

class _FakeClient:
    """Minimal client whose detail POST returns a fixed operations list."""
    def __init__(self, op_names):
        self._op_names = op_names

    def post(self, path, body):
        return {"operations": [{"operation": n} for n in self._op_names]}


def test_validate_op_live_rejects_phantom(monkeypatch):
    from fsr_playbooks.mcp_server import tools_execution as te
    monkeypatch.setattr(te, "_configured_rows",
                        lambda client, force=False: [{"name": "virustotal", "id": "cid-1"}])
    client = _FakeClient(["get_ip_reputation", "get_domain_reputation"])
    err = te._validate_op_live(client, "virustotal", "lookup_ip")
    assert err is not None and err["code"] == "unknown_operation"
    typo = te._validate_op_live(client, "virustotal", "get_ip_reputaion")
    assert typo["code"] == "unknown_operation"
    assert "get_ip_reputation" in typo["near"]


def test_validate_op_live_accepts_real(monkeypatch):
    from fsr_playbooks.mcp_server import tools_execution as te
    monkeypatch.setattr(te, "_configured_rows",
                        lambda client, force=False: [{"name": "virustotal", "id": "cid-1"}])
    assert te._validate_op_live(_FakeClient(["get_ip_reputation"]),
                                "virustotal", "get_ip_reputation") is None


def test_validate_op_live_never_blocks_on_lookup_failure(monkeypatch):
    """A transient detail-fetch error must not false-reject a real op."""
    from fsr_playbooks.mcp_server import tools_execution as te
    monkeypatch.setattr(te, "_configured_rows",
                        lambda client, force=False: [{"name": "virustotal", "id": "cid-1"}])

    class _Boom:
        def post(self, path, body):
            raise RuntimeError("FSR unreachable")

    assert te._validate_op_live(_Boom(), "virustotal", "anything") is None


def test_validate_op_live_skips_when_live_list_empty(monkeypatch):
    from fsr_playbooks.mcp_server import tools_execution as te
    monkeypatch.setattr(te, "_configured_rows",
                        lambda client, force=False: [{"name": "virustotal", "id": "cid-1"}])
    assert te._validate_op_live(_FakeClient([]), "virustotal", "anything") is None


# --- live param grounding (Phase 1.4 — param-level live grounding) ----------
# The offline param check no-ops on an un-synced connector, so the agent used
# to discover real param names by trial-and-error live (the mail_egress flail).
# These cover validating arg names against the LIVE connector definition.

class _FakeOpClient:
    """Client whose detail POST returns ops WITH parameter lists."""
    def __init__(self, ops):
        # ops: {op_name: [ {name, required, title, ...}, ... ]}
        self._ops = ops

    def post(self, path, body):
        return {"operations": [
            {"operation": name, "parameters": params}
            for name, params in self._ops.items()
        ]}


_VT_OPS = {
    "get_ip_reputation": [
        {"name": "ip", "title": "IP Address", "type": "text", "required": True},
        {"name": "limit", "title": "Limit", "type": "integer", "required": False},
    ],
}


def test_validate_op_params_live_rejects_unknown_param():
    from fsr_playbooks.mcp_server import tools_execution as te
    op_def = {"operation": "get_ip_reputation", "parameters": _VT_OPS["get_ip_reputation"]}
    err = te._validate_op_params_live(op_def, "virustotal", "get_ip_reputation",
                                      {"ip_address": "1.2.3.4"})
    assert err is not None and err["code"] == "bad_params"
    probs = {i["param"]: i for i in err["issues"]}
    # the guessed name is flagged unknown...
    assert probs["ip_address"]["problem"] == "unknown"
    # ...and the real required param is reported missing.
    assert probs["ip"]["problem"] == "missing_required"


def test_validate_op_params_live_suggests_near_match():
    from fsr_playbooks.mcp_server import tools_execution as te
    op_def = {"operation": "get_ip_reputation", "parameters": _VT_OPS["get_ip_reputation"]}
    # a close typo of a real param -> near-match suggestion.
    err = te._validate_op_params_live(op_def, "virustotal", "get_ip_reputation",
                                      {"ip": "1.2.3.4", "limt": 5})
    probs = {i["param"]: i for i in err["issues"]}
    assert probs["limt"]["problem"] == "unknown"
    assert "limit" in probs["limt"]["near"]


def test_validate_op_params_live_accepts_good_args():
    from fsr_playbooks.mcp_server import tools_execution as te
    op_def = {"operation": "get_ip_reputation", "parameters": _VT_OPS["get_ip_reputation"]}
    assert te._validate_op_params_live(
        op_def, "virustotal", "get_ip_reputation", {"ip": "1.2.3.4"}) is None


def test_validate_op_params_live_fails_open_without_param_list():
    from fsr_playbooks.mcp_server import tools_execution as te
    # No parameters on the live op → can't prove a name is unknown.
    assert te._validate_op_params_live(
        {"operation": "x", "parameters": []}, "c", "x", {"anything": 1}) is None
    assert te._validate_op_params_live(None, "c", "x", {"anything": 1}) is None


def _stub_unsynced_live(monkeypatch, store, client):
    """Wire validate_op_grounded down its live path: empty store for the
    connector + a configured/healthy live client."""
    from fsr_playbooks.mcp_server import tools_execution as te
    # the store fixture has NO ops for 'shodan' → store_ops_count == 0
    monkeypatch.setattr(te, "_db", lambda: sqlite3.connect(store))
    # point the sqlite-backed op-def cache at the same temp store
    monkeypatch.setattr(te, "DB_PATH", str(store))
    monkeypatch.setattr(te, "_configured_rows",
                        lambda c, force=False: [
                            {"name": "shodan", "id": "cid-9", "version": "1.0.0"}])
    monkeypatch.setattr(te, "_preflight_connector",
                        lambda c, conn, config="": None)
    return te


def test_validate_op_grounded_live_param_flail_blocked(monkeypatch, store):
    client = _FakeOpClient({"host": [
        {"name": "ip", "title": "IP", "type": "text", "required": True}]})
    te = _stub_unsynced_live(monkeypatch, store, client)
    # right op, wrong param name (the flail) → bad_params off the live def.
    err = te.validate_op_grounded("shodan", "host",
                                  params={"ip_address": "1.2.3.4"}, client=client)
    assert err is not None and err["code"] == "bad_params"


def test_validate_op_grounded_live_good_params_pass(monkeypatch, store):
    client = _FakeOpClient({"host": [
        {"name": "ip", "title": "IP", "type": "text", "required": True}]})
    te = _stub_unsynced_live(monkeypatch, store, client)
    assert te.validate_op_grounded("shodan", "host",
                                   params={"ip": "1.2.3.4"}, client=client) is None


def test_validate_op_grounded_without_params_skips_param_check(monkeypatch, store):
    """Back-compat: no `params` arg → op-existence only, never bad_params."""
    client = _FakeOpClient({"host": [
        {"name": "ip", "title": "IP", "type": "text", "required": True}]})
    te = _stub_unsynced_live(monkeypatch, store, client)
    assert te.validate_op_grounded("shodan", "host", client=client) is None


def test_emit_action_card_blocks_flailed_param_on_unsynced(monkeypatch, store):
    """End-to-end: a card with a guessed param name for an un-synced connector
    is rejected before it can reach the analyst."""
    from fsr_playbooks.mcp_server import tools_execution as te
    client = _FakeOpClient({"host": [
        {"name": "ip", "title": "IP", "type": "text", "required": True}]})
    monkeypatch.setattr(te, "_db", lambda: sqlite3.connect(store))
    monkeypatch.setattr(te, "DB_PATH", str(store))
    monkeypatch.setattr(te, "_configured_rows",
                        lambda c, force=False: [
                            {"name": "shodan", "id": "cid-9", "version": "1.0.0"}])
    monkeypatch.setattr(te, "_preflight_connector",
                        lambda c, conn, config="": None)
    monkeypatch.setattr(te, "_live_client_for_grounding", lambda: client)
    from fsr_playbooks.mcp_server.tools_emit import emit_action_card
    out = emit_action_card(
        id="c1", connector="shodan", operation="host",
        summary="Look up the host", args={"ip_address": "1.2.3.4"},
        editable_fields=["ip_address"])
    assert out["ok"] is False and out["code"] == "bad_params"


# --- live op-def cache + warmup (don't re-fetch the connector detail per pivot)

class _CountingClient:
    """Client that counts how many detail POSTs it serves."""
    def __init__(self, ops):
        self._ops = ops
        self.posts = 0

    def post(self, path, body):
        self.posts += 1
        return {"operations": [
            {"operation": n, "parameters": p} for n, p in self._ops.items()]}


def test_op_def_cache_roundtrip_and_ttl(tmp_path, monkeypatch):
    from fsr_playbooks.mcp_server import tools_execution as te
    monkeypatch.setattr(te, "DB_PATH", str(tmp_path / "s.db"))
    assert te._cached_op_defs("shodan", "1.0.0") is None
    te._store_op_defs("shodan", "1.0.0", [{"operation": "host"}])
    assert te._cached_op_defs("shodan", "1.0.0") == [{"operation": "host"}]
    # a different version misses (an upgrade re-fetches)
    assert te._cached_op_defs("shodan", "2.0.0") is None
    # expired rows are ignored
    monkeypatch.setattr(te, "_OP_DEFS_TTL_S", -1)
    assert te._cached_op_defs("shodan", "1.0.0") is None


def test_live_ops_for_is_cached_after_first_fetch(tmp_path, monkeypatch):
    from fsr_playbooks.mcp_server import tools_execution as te
    monkeypatch.setattr(te, "DB_PATH", str(tmp_path / "s.db"))
    monkeypatch.setattr(te, "_configured_rows",
                        lambda c, force=False: [
                            {"name": "shodan", "id": "cid-9", "version": "1.0.0"}])
    client = _CountingClient({"host": [{"name": "ip", "required": True}]})
    a = te._live_ops_for(client, "shodan")
    b = te._live_ops_for(client, "shodan")
    assert a == b and client.posts == 1  # second call served from cache


def test_populate_op_definitions_warms_all_configured(tmp_path, monkeypatch):
    from fsr_playbooks.mcp_server import tools_execution as te
    db = tmp_path / "s.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE operations (connector_name TEXT, op_name TEXT)")
    # 'virustotal' IS synced (has ops); 'shodan' is not — both get warmed.
    con.execute("INSERT INTO operations VALUES ('virustotal','get_ip_reputation')")
    con.commit()
    con.close()
    monkeypatch.setattr(te, "DB_PATH", str(db))
    monkeypatch.setattr(te, "_db", lambda: sqlite3.connect(db))
    monkeypatch.setattr(te, "_configured_rows",
                        lambda c, force=False: [
                            {"name": "virustotal", "id": "v", "version": "1.0.0"},
                            {"name": "shodan", "id": "s", "version": "1.0.0"}])
    client = _CountingClient({"host": [{"name": "ip", "required": True}]})
    res = te.populate_op_definitions(client, time_budget_s=30.0)
    assert res["ok"] is True
    assert res["warmed"] == 2 and client.posts == 2
    # both connectors' live op-defs (operations + params) are now cached
    assert te._cached_op_defs("shodan", "1.0.0") is not None
    assert te._cached_op_defs("virustotal", "1.0.0") is not None


def test_populate_op_definitions_respects_budget_and_fresh_cache(tmp_path, monkeypatch):
    from fsr_playbooks.mcp_server import tools_execution as te
    db = tmp_path / "s.db"
    monkeypatch.setattr(te, "DB_PATH", str(db))
    monkeypatch.setattr(te, "_db", lambda: sqlite3.connect(":memory:"))
    monkeypatch.setattr(te, "_configured_rows",
                        lambda c, force=False: [
                            {"name": "shodan", "id": "s", "version": "1.0.0"}])
    te._store_op_defs("shodan", "1.0.0", [{"operation": "host"}])  # already fresh
    client = _CountingClient({"host": []})
    res = te.populate_op_definitions(client, time_budget_s=30.0)
    assert res["fresh_cached"] == 1 and res["warmed"] == 0 and client.posts == 0
