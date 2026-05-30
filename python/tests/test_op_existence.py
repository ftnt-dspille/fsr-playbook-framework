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

import fsr_core.mcp_server._shared as _shared


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
    from fsr_core.mcp_server.tools_emit import emit_action_card
    out = emit_action_card(
        id="c1", connector="virustotal", operation="lookup_ip",
        summary="Look up the IP", args={"ip": "1.2.3.4"}, editable_fields=["ip"],
    )
    assert out["ok"] is False
    assert out["code"] == "unknown_operation"


def test_emit_action_card_allows_real_op(store):
    from fsr_core.mcp_server.tools_emit import emit_action_card
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
    from fsr_core.mcp_server import tools_execution as te
    monkeypatch.setattr(te, "_configured_rows",
                        lambda client, force=False: [{"name": "virustotal", "id": "cid-1"}])
    client = _FakeClient(["get_ip_reputation", "get_domain_reputation"])
    err = te._validate_op_live(client, "virustotal", "lookup_ip")
    assert err is not None and err["code"] == "unknown_operation"
    typo = te._validate_op_live(client, "virustotal", "get_ip_reputaion")
    assert typo["code"] == "unknown_operation"
    assert "get_ip_reputation" in typo["near"]


def test_validate_op_live_accepts_real(monkeypatch):
    from fsr_core.mcp_server import tools_execution as te
    monkeypatch.setattr(te, "_configured_rows",
                        lambda client, force=False: [{"name": "virustotal", "id": "cid-1"}])
    assert te._validate_op_live(_FakeClient(["get_ip_reputation"]),
                                "virustotal", "get_ip_reputation") is None


def test_validate_op_live_never_blocks_on_lookup_failure(monkeypatch):
    """A transient detail-fetch error must not false-reject a real op."""
    from fsr_core.mcp_server import tools_execution as te
    monkeypatch.setattr(te, "_configured_rows",
                        lambda client, force=False: [{"name": "virustotal", "id": "cid-1"}])

    class _Boom:
        def post(self, path, body):
            raise RuntimeError("FSR unreachable")

    assert te._validate_op_live(_Boom(), "virustotal", "anything") is None


def test_validate_op_live_skips_when_live_list_empty(monkeypatch):
    from fsr_core.mcp_server import tools_execution as te
    monkeypatch.setattr(te, "_configured_rows",
                        lambda client, force=False: [{"name": "virustotal", "id": "cid-1"}])
    assert te._validate_op_live(_FakeClient([]), "virustotal", "anything") is None
