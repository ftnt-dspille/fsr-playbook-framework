"""mcp_server.list_connector_configurations — wraps connector_configs.

We stub the underlying live-fetch helper so the test stays offline.
"""
from __future__ import annotations

import pytest

pytest.importorskip(
    "mcp.server.fastmcp",
    reason="mcp package not installed (pip install mcp)",
)

import fsr_core.mcp_server as mcp_server  # noqa: E402


@pytest.fixture
def stub_list(monkeypatch):
    fake = [
        {"config_id": "uuid-A", "name": "prod", "default": True},
        {"config_id": "uuid-B", "name": "staging", "default": False},
    ]
    import connector_configs
    monkeypatch.setattr(connector_configs, "list_configurations", lambda c: fake)
    mcp_server._CONFIG_CACHE.pop("svc", None)
    yield fake
    mcp_server._CONFIG_CACHE.pop("svc", None)


def test_passes_through_and_caches(stub_list):
    # `svc` isn't a real connector row in the DB so the SQLite branch
    # short-circuits, dropping us to the live tier.
    r1 = mcp_server.list_connector_configurations("svc")
    assert r1["ok"] is True
    assert r1["source"] == "live"
    assert r1["configurations"] == stub_list

    r2 = mcp_server.list_connector_configurations("svc")
    assert r2["source"] == "memory"
    assert r2["configurations"] == stub_list


def test_refresh_bypasses_cache(stub_list, monkeypatch):
    mcp_server.list_connector_configurations("svc")  # populate
    new_fake = [{"config_id": "uuid-C", "name": "dev", "default": False}]
    import connector_configs
    monkeypatch.setattr(connector_configs, "list_configurations", lambda c: new_fake)

    r = mcp_server.list_connector_configurations("svc", refresh=True)
    assert r["source"] == "live"
    assert r["configurations"] == new_fake


def test_sqlite_source_when_info_json_has_configurations(monkeypatch):
    """info_json from probe ingest already contains the full
    `configuration` array. Prefer that over a live round-trip — saves
    ~2 s per first-touch lookup."""
    import sqlite3, json
    name = "sqlite_first_test"
    blob = json.dumps({
        "configuration": [
            {"config_id": "uuid-X", "name": "prod", "default": True},
            {"config_id": "uuid-Y", "name": "qa",   "default": False},
        ]
    })
    with sqlite3.connect(mcp_server.DB_PATH) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS connectors ("
            " name TEXT PRIMARY KEY, version TEXT NOT NULL,"
            " label TEXT, category TEXT, description TEXT,"
            " publisher TEXT, contributor TEXT,"
            " active INTEGER, system INTEGER, cs_approved INTEGER,"
            " cs_compatible INTEGER, ingestion_supported INTEGER,"
            " tags_json TEXT, config_schema_json TEXT,"
            " source TEXT NOT NULL, source_path TEXT, info_json TEXT)"
        )
        conn.execute(
            "INSERT OR REPLACE INTO connectors (name, version, source, info_json)"
            " VALUES (?, '1.0.0', 'test', ?)", (name, blob)
        )
        conn.commit()
    mcp_server._CONFIG_CACHE.pop(name, None)

    # If the SQLite path is wired correctly, this MUST NOT call the
    # live helper. Wire a tripwire.
    import connector_configs
    monkeypatch.setattr(
        connector_configs, "list_configurations",
        lambda c: pytest.fail("live path called when SQLite had data")
    )
    r = mcp_server.list_connector_configurations(name)
    assert r["ok"] is True
    assert r["source"] == "sqlite"
    assert [c["name"] for c in r["configurations"]] == ["prod", "qa"]


def test_live_fetch_error_returns_error(monkeypatch):
    mcp_server._CONFIG_CACHE.pop("explodes", None)
    import connector_configs
    monkeypatch.setattr(
        connector_configs, "list_configurations",
        lambda c: (_ for _ in ()).throw(RuntimeError("network down"))
    )
    r = mcp_server.list_connector_configurations("explodes")
    assert r["ok"] is False
    assert "network down" in r["error"]
