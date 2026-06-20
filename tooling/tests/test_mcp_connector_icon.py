"""mcp_server.get_connector_icon — three-tier cache (memory→disk→live).

The live tier requires a configured FSR; we stub `_live_client` to keep
the test offline. Disk persistence is verified by clearing the in-memory
cache between calls and asserting the second call reports `cached=disk`.
"""
from __future__ import annotations

import pytest

pytest.importorskip(
    "mcp.server.fastmcp",
    reason="mcp package not installed (pip install mcp)",
)

import fsr_playbooks.mcp_server as mcp_server  # noqa: E402
import fsr_playbooks.mcp_server._shared  # noqa: E402, F401


class _FakeClient:
    """Stand-in for the pyfsr client. Counts calls so we can prove the
    disk cache short-circuits the live round-trip."""

    def __init__(self, payload: dict):
        self.payload = payload
        self.calls = 0

    def post(self, path: str, body):  # noqa: ARG002
        self.calls += 1
        return self.payload


@pytest.fixture
def stub_live(monkeypatch):
    fake = _FakeClient({
        "icon_small": "data:image/png;base64,SMALL_FIXTURE",
        "icon_large": "data:image/png;base64,LARGE_FIXTURE",
    })
    monkeypatch.setattr(mcp_server._shared, "_live_client", lambda: fake)
    # Pretend the connector is in the local store at version 1.0.0.
    # `get_connector_icon` only reads `version` from the connectors row,
    # so a tiny stand-in is enough.
    import sqlite3
    db = mcp_server.DB_PATH
    with sqlite3.connect(db) as conn:
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
            "INSERT OR IGNORE INTO connectors (name, version, source) "
            "VALUES ('icon_test', '1.0.0', 'test')"
        )
        conn.execute("DELETE FROM connector_icons WHERE name='icon_test'")
        conn.commit()
    mcp_server._ICON_CACHE.pop("icon_test", None)
    yield fake
    # Cleanup so a re-run doesn't see a stale row.
    mcp_server._ICON_CACHE.pop("icon_test", None)


def test_live_then_disk_then_memory(stub_live):
    # First call: live fetch + write-through to disk + memory.
    r1 = mcp_server.get_connector_icon("icon_test")
    assert r1["ok"] is True
    assert r1["cached"] == "live"
    assert r1["icon_small"].endswith("SMALL_FIXTURE")
    assert stub_live.calls == 1

    # Second call: memory hit, no live call.
    r2 = mcp_server.get_connector_icon("icon_test")
    assert r2["cached"] == "memory"
    assert stub_live.calls == 1

    # Drop in-memory cache → next call must come from disk, NOT live.
    mcp_server._ICON_CACHE.pop("icon_test", None)
    r3 = mcp_server.get_connector_icon("icon_test")
    assert r3["cached"] == "disk"
    assert r3["icon_small"].endswith("SMALL_FIXTURE")
    assert stub_live.calls == 1, "disk hit must short-circuit the live fetch"


def test_unknown_connector_returns_error():
    r = mcp_server.get_connector_icon("definitely-not-a-connector-xyz")
    assert r["ok"] is False
    assert "not found" in r["error"]


def test_no_live_client_after_disk_miss(monkeypatch, stub_live):
    # Kill the live client AFTER the disk row was wiped. We should get
    # an error pointing at the missing FSR config, not a stack trace.
    monkeypatch.setattr(mcp_server._shared, "_live_client", lambda: None)
    mcp_server._ICON_CACHE.pop("icon_test", None)
    import sqlite3
    with sqlite3.connect(mcp_server.DB_PATH) as conn:
        conn.execute("DELETE FROM connector_icons WHERE name='icon_test'")
        conn.commit()
    r = mcp_server.get_connector_icon("icon_test")
    assert r["ok"] is False
    assert "FSR instance not configured" in r["error"]
