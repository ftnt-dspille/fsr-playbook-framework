"""generate_recipe + find_recipe MCP tools.

Hermetic: stubs out the recipe generators with a minimal payload so we
don't need a real connector info.json on disk. The tests verify the
envelope shape, persistence to the recipes table, and find_recipe
read-back path.
"""
from __future__ import annotations

import json
import sqlite3

import pytest

pytest.importorskip("mcp.server.fastmcp",
                    reason="mcp package not installed")

import mcp_server  # noqa: E402
import mcp_server._shared  # noqa: E402, F401

# Minimum fields the generator inspects: name, version, label, operations.
_FAKE_INFO = {
    "name": "fake_connector",
    "label": "Fake",
    "version": "1.0.0",
    "operations": [
        {"operation": "fetch_alerts", "title": "Fetch Alerts",
         "category": "investigation",
         "parameters": [], "output_schema": {}},
    ],
}

# Minimal FSR JSON shape `decompile_to_yaml` will accept.
_FAKE_FSR_JSON = {
    "name": "Fake Recipe",
    "description": "",
    "visible": True,
    "workflows": [],
}


@pytest.fixture
def info_json_path(tmp_path):
    p = tmp_path / "info.json"
    p.write_text(json.dumps(_FAKE_INFO))
    return p


@pytest.fixture
def stub_generators(monkeypatch):
    """Bypass the real generator + decompiler so we test the wiring,
    not the recipe-shape correctness (which has its own tests)."""
    import recipes

    def _fake_threat_feed(info, *, connector_config_uuid):
        assert info["name"] == "fake_connector"
        return _FAKE_FSR_JSON

    def _fake_data_ingest(info, **kw):
        assert info["name"] == "fake_connector"
        return _FAKE_FSR_JSON

    monkeypatch.setattr(
        recipes, "generate_threat_feed_recipe", _fake_threat_feed,
    )
    monkeypatch.setattr(
        recipes, "generate_data_ingest_recipe", _fake_data_ingest,
    )

    from compiler import decompiler
    monkeypatch.setattr(
        decompiler, "decompile_to_yaml",
        lambda fsr_json, db_path: "collection: Fake Recipe\nplaybooks: []\n",
    )


@pytest.fixture
def isolated_recipes_db(tmp_path, monkeypatch):
    """Point the MCP tool at a throwaway DB with just the recipes
    table — keeps the suite from polluting the real reference DB."""
    db = tmp_path / "ref.db"
    with sqlite3.connect(db) as conn:
        conn.execute("""
            CREATE TABLE recipes (
                name TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                when_to_use TEXT,
                yaml_template TEXT NOT NULL,
                source_playbook TEXT
            )
        """)
        conn.commit()
    monkeypatch.setattr(mcp_server._shared, "DB_PATH", db)
    return db


def test_generate_recipe_threat_feed_envelope(
    info_json_path, stub_generators, isolated_recipes_db,
):
    out = mcp_server.generate_recipe(
        kind="threat-feed",
        info_json_path=str(info_json_path),
    )
    assert out["ok"] is True
    assert out["kind"] == "threat-feed"
    assert out["name"] == "threat_feed:fake_connector"
    assert out["connector"] == "fake_connector"
    assert out["yaml"].startswith("collection: Fake Recipe")
    assert out["persisted"] is False  # default


def test_generate_recipe_data_ingest_persists(
    info_json_path, stub_generators, isolated_recipes_db,
):
    out = mcp_server.generate_recipe(
        kind="data-ingest",
        info_json_path=str(info_json_path),
        target_module="alerts",
        persist=True,
        when_to_use="ingest fake_connector alerts",
    )
    assert out["ok"] is True
    assert out["persisted"] is True
    # Read back via find_recipe.
    found = mcp_server.find_recipe(query="fake_connector")
    assert found["count"] == 1
    r = found["recipes"][0]
    assert r["name"] == "data_ingest:fake_connector"
    assert r["kind"] == "data_ingest"
    assert r["when_to_use"] == "ingest fake_connector alerts"
    assert r["yaml_template"].startswith("collection: Fake Recipe")


def test_generate_recipe_bad_kind_returns_envelope(
    info_json_path, stub_generators, isolated_recipes_db,
):
    out = mcp_server.generate_recipe(
        kind="not_a_kind", info_json_path=str(info_json_path),
    )
    assert out["ok"] is False
    assert out["code"] == "bad_kind"
    assert "threat-feed" in out["suggestions"]


def test_generate_recipe_missing_info_json(
    tmp_path, isolated_recipes_db,
):
    out = mcp_server.generate_recipe(
        kind="threat-feed",
        info_json_path=str(tmp_path / "does_not_exist.json"),
    )
    assert out["ok"] is False
    assert out["code"] == "info_json_missing"


def test_find_recipe_filters_by_kind(
    info_json_path, stub_generators, isolated_recipes_db,
):
    mcp_server.generate_recipe(
        kind="threat-feed", info_json_path=str(info_json_path),
        persist=True,
    )
    mcp_server.generate_recipe(
        kind="data-ingest", info_json_path=str(info_json_path),
        persist=True,
    )
    threat = mcp_server.find_recipe(kind="threat_feed")
    di = mcp_server.find_recipe(kind="data_ingest")
    assert threat["count"] == 1
    assert di["count"] == 1
    assert threat["recipes"][0]["name"].startswith("threat_feed:")
    assert di["recipes"][0]["name"].startswith("data_ingest:")
