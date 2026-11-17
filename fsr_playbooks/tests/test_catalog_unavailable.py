"""The vendor API catalog is optional. Without it, find(kind='example') must
say so and point at the playbook-side corpora.

Live (box, playbook enhancement turn): the model asked find(kind='example',
query='Containment Comment create_record comments alert') for a worked step.
With no connector named, that routes to the vendor API catalog, which an
appliance install does not ship, and the model got back SQLite's own text:
"catalog DB unavailable: no such table: catalog.entries_fts" -- nothing that
told it the playbook examples live under kind='recipe' / kind='step'.
"""
from __future__ import annotations

import sqlite3
import sys
import types

import pytest

from fsr_playbooks.mcp_server import tools_find  # noqa: E402
from fsr_playbooks.mcp_server.tools_analysis import synthesize_http_step  # noqa: E402
from fsr_playbooks.mcp_server.tools_corpus import search_api_examples  # noqa: E402


def _catalog_at(monkeypatch, path) -> None:
    # `_db()` attaches the catalog from probes.common.CATALOG_DB_PATH when that
    # imports (a dev checkout) and the file exists; a stand-in module makes
    # the test independent of whether this checkout has `probes` at all.
    common = types.ModuleType("probes.common")
    common.CATALOG_DB_PATH = path
    pkg = types.ModuleType("probes")
    pkg.common = common
    monkeypatch.setitem(sys.modules, "probes", pkg)
    monkeypatch.setitem(sys.modules, "probes.common", common)


@pytest.fixture
def no_catalog(monkeypatch, tmp_path):
    _catalog_at(monkeypatch, tmp_path / "absent.sqlite")


@pytest.fixture
def catalog_without_fts(monkeypatch, tmp_path):
    path = tmp_path / "catalog.sqlite"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE entries (id INTEGER PRIMARY KEY, product_id INT)")
    con.execute("CREATE TABLE products (id INTEGER PRIMARY KEY, name TEXT)")
    con.commit()
    con.close()
    _catalog_at(monkeypatch, path)


def _assert_points_elsewhere(text: str) -> None:
    assert "no such table" not in text
    assert "kind='recipe'" in text and "kind='step'" in text


@pytest.mark.parametrize("fixture", ["no_catalog", "catalog_without_fts"])
def test_find_example_without_the_catalog_says_where_to_look(fixture, request):
    request.getfixturevalue(fixture)
    out = tools_find.find(kind="example",
                          query="Containment Comment create_record comments alert")
    assert out["ok"] is False
    assert out["code"] == "catalog_unavailable"
    assert out["kind"] == "example"
    _assert_points_elsewhere(out["message"])


@pytest.mark.parametrize("fixture", ["no_catalog", "catalog_without_fts"])
def test_search_api_examples_reports_unavailable_not_sqlite(fixture, request):
    request.getfixturevalue(fixture)
    rows = search_api_examples("block ip")
    assert len(rows) == 1 and rows[0]["code"] == "catalog_unavailable"
    assert "entries_fts" in rows[0]["missing_tables"]
    _assert_points_elsewhere(rows[0]["hint"])


def test_synthesize_http_step_without_the_catalog(no_catalog):
    out = synthesize_http_step(1)
    assert out["code"] == "catalog_unavailable"
    _assert_points_elsewhere(out["hint"])
