"""G3 wiring — the Tier-2 ``conditional_refetch`` opt-in is actually consumed by
the real probes (``probe_connector_configs`` / ``probe_api_endpoints`` /
``probe_modules``), not just exercised in isolation by ``test_conditional_refetch``.

For each wired probe we assert the four-outcome contract AND the critical
correctness property the wiring adds: the probe's tables are NOT wiped on a
``fresh`` / ``unchanged`` / ``error`` outcome (only on a refreshed 200), so a
skip never empties the catalog. Default-off (``FSR_CONDITIONAL_REFETCH`` unset)
keeps the legacy always-re-pull path.

Mock client + in-memory DB built from the shipped ``schema.sql`` — no live SOAR.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from probes import _env
from probes import common as probes_common
from probes import probe_api_endpoints
from probes import probe_connector_configs
from probes import probe_modules

SCHEMA_PATH = probes_common.SCHEMA_PATH


# --------------------------------------------------------------------- helpers


class _Resp:
    """Stand-in for a requests.Response."""

    def __init__(self, body=None, *, status_code=200, etag=None):
        self.status_code = status_code
        self.headers = {"ETag": etag} if etag else {}
        self._body = body

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _MockSession:
    """``client.session.get(url)`` returns a Response-like _Resp (status/headers/json)."""

    def __init__(self, routes):
        self._routes = routes  # url-substring -> _Resp
        self.calls: list[dict] = []

    def get(self, url, params=None, headers=None, verify=None, **_):
        self.calls.append({"url": url, "headers": headers})
        for needle, resp in self._routes.items():
            if needle in url:
                return resp
        return _Resp({"hydra:member": []})


class _MockClient:
    """``client.session`` is a _MockSession (returns _Resp); ``client.get(path)``
    is the pyfsr wrapper that returns the parsed JSON dict directly."""

    base_url = "https://soar.example"
    verify_ssl = False

    def __init__(self, session_routes=None, get_routes=None):
        self.session = _MockSession(session_routes or {})
        self._get_routes = get_routes or {}  # path-substring -> dict (or _Resp)

    def get(self, path, **_):
        for needle, val in self._get_routes.items():
            if needle in path:
                return val.json() if isinstance(val, _Resp) else val
        return {"hydra:member": []}


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA_PATH.read_text())
    c.commit()
    yield c
    c.close()


@pytest.fixture
def cond_enabled(monkeypatch):
    """Flip the opt-in ON for the duration of the test."""
    monkeypatch.setattr(_env, "is_conditional_enabled", lambda: True)
    monkeypatch.setattr(_env, "get_client", lambda: _MockClient())


def _seed_connector_configs(conn, n=1):
    conn.executemany(
        "INSERT INTO connector_configs (connector, config_name, config_id, is_default) "
        "VALUES (?, ?, ?, ?)",
        [(f"conn{i}", "Default", f"cid{i}", 1) for i in range(n)],
    )
    conn.commit()


def _count(conn, table):
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


# ----------------------------------------------------- probe_connector_configs


def test_connector_configs_fresh_skips_wipe(conn, cond_enabled, monkeypatch):
    """Within TTL -> no request, no wipe, rows survive, returns zeros."""
    probe = probe_connector_configs  # bound from the module-level import

    _seed_connector_configs(conn, 3)
    monkeypatch.setattr(probe, "conditional_refetch",
                        lambda *a, **k: ("fresh", None))

    n_conn, n_rows, errs = probe._live(conn)

    assert (n_conn, n_rows, errs) == (0, 0, [])
    assert _count(conn, "connector_configs") == 3  # pre-seed untouched


def test_connector_configs_unchanged_skips_wipe(conn, cond_enabled, monkeypatch):
    """304 -> no wipe, no rewrite, rows survive (data_warmed_at bumped by the helper)."""
    probe = probe_connector_configs  # bound from the module-level import

    _seed_connector_configs(conn, 2)
    monkeypatch.setattr(probe, "conditional_refetch",
                        lambda *a, **k: ("unchanged", None))

    n_conn, n_rows, errs = probe._live(conn)

    assert (n_conn, n_rows, errs) == (0, 0, [])
    assert _count(conn, "connector_configs") == 2


def test_connector_configs_refreshed_wipes_and_rewrites(conn, cond_enabled, monkeypatch):
    """200 -> wipe the stale rows + write the fresh payload."""
    probe = probe_connector_configs  # bound from the module-level import

    _seed_connector_configs(conn, 5)  # stale rows that must be replaced
    payload = {"data": [
        {"name": "smtp", "configuration": [
            {"config_id": "new1", "name": "Default", "default": True}]},
        {"name": "http", "configuration": [
            {"config_id": "new2", "name": "Prod", "default": False}]},
    ]}
    monkeypatch.setattr(probe, "conditional_refetch",
                        lambda *a, **k: ("refreshed", payload))

    n_conn, n_rows, errs = probe._live(conn)

    assert errs == []
    assert n_conn == 2                       # two connectors with configs
    # 2 named + 2 __default__ (one per connector) = 4 rows
    assert _count(conn, "connector_configs") == 4
    # stale seeded rows are gone:
    assert conn.execute(
        "SELECT COUNT(*) FROM connector_configs WHERE connector IN ('conn0','conn1')"
    ).fetchone()[0] == 0


def test_connector_configs_error_keeps_catalog(conn, cond_enabled, monkeypatch):
    """Request failure -> no wipe, rows survive, error propagated."""
    probe = probe_connector_configs  # bound from the module-level import

    _seed_connector_configs(conn, 2)
    monkeypatch.setattr(probe, "conditional_refetch",
                        lambda *a, **k: ("error", "boom: timeout"))

    n_conn, n_rows, errs = probe._live(conn)

    assert (n_conn, n_rows) == (0, 0)
    assert errs == ["boom: timeout"]
    assert _count(conn, "connector_configs") == 2  # untouched


def test_connector_configs_disabled_uses_legacy_path(conn, monkeypatch):
    """Default (opt-in OFF) -> unconditional wipe + fetch; no conditional_refetch call."""
    probe = probe_connector_configs  # bound from the module-level import

    monkeypatch.setattr(_env, "is_conditional_enabled", lambda: False)
    # NOTE: _live (not main) doesn't wipe on the legacy path — main owns the
    # unconditional wipe. So no pre-seed; we assert the fetch+write+ETag only.

    calls = {"conditional": 0}
    client = _MockClient(session_routes={
        "/api/integration/connectors/": _Resp({"data": [
            {"name": "fresh", "configuration": [
                {"config_id": "c1", "name": "Default", "default": True}]},
        ]}, etag="etag-v1"),
    })
    monkeypatch.setattr(_env, "get_client", lambda: client)
    real_conditional = probe.conditional_refetch

    def _spy(*a, **k):
        calls["conditional"] += 1
        return real_conditional(*a, **k)

    monkeypatch.setattr(probe, "conditional_refetch", _spy)

    n_conn, n_rows, errs = probe._live(conn)

    assert calls["conditional"] == 0           # legacy path never consults it
    assert errs == []
    assert n_conn == 1
    assert _count(conn, "connector_configs") == 2  # 1 named + __default__
    # legacy path records the ETag + Tier-2 warm time (conditional_refetch did not):
    from fsr_playbooks import _catalog_meta
    assert _catalog_meta.get_etag(conn, "connector_configs") == "etag-v1"
    assert _catalog_meta.get_data_warmed_at(conn) is not None


# -------------------------------------------------------- probe_api_endpoints


def test_api_endpoints_fresh_skips_wipe(conn, cond_enabled, monkeypatch):
    probe = probe_api_endpoints  # bound from the module-level import

    _seed_api_endpoint(conn)
    wiped = {"n": 0}
    real_wipe = probe.wipe_probe_tables

    def _wipe_spy(c, name):
        wiped["n"] += 1
        return real_wipe(c, name)

    monkeypatch.setattr(probe, "conditional_refetch", lambda *a, **k: ("fresh", None))
    monkeypatch.setattr(probe, "wipe_probe_tables", _wipe_spy)

    count, errs = probe._live_hydra(conn)

    assert (count, errs) == (0, [])
    assert wiped["n"] == 0
    assert _count(conn, "api_endpoints") == 1  # pre-seed survives


def test_api_endpoints_refreshed_wipes_and_derives(conn, cond_enabled, monkeypatch):
    probe = probe_api_endpoints  # bound from the module-level import

    wiped = {"n": 0}
    real_wipe = probe.wipe_probe_tables

    def _wipe_spy(c, name):
        wiped["n"] += 1
        return real_wipe(c, name)

    # Hydra root with one collection -> a GET endpoint upsert + a member route.
    root = {"foos": "/api/3/foos"}
    monkeypatch.setattr(probe, "conditional_refetch",
                        lambda *a, **k: ("refreshed", root))
    monkeypatch.setattr(probe, "wipe_probe_tables", _wipe_spy)

    count, errs = probe._live_hydra(conn)

    assert errs == []
    assert wiped["n"] == 1
    assert count > 0  # discovered the collection + member routes


def test_api_endpoints_error_keeps_catalog(conn, cond_enabled, monkeypatch):
    probe = probe_api_endpoints  # bound from the module-level import

    _seed_api_endpoint(conn)
    monkeypatch.setattr(probe, "conditional_refetch",
                        lambda *a, **k: ("error", "503"))

    count, errs = probe._live_hydra(conn)

    assert count == 0
    assert errs == ["503"]
    assert _count(conn, "api_endpoints") == 1  # untouched


def _seed_api_endpoint(conn):
    conn.execute(
        "INSERT INTO api_endpoints (path_pattern, http_method, service, source) "
        "VALUES ('/api/3/old', 'GET', 'php', 'stale')"
    )
    conn.commit()


# ---------------------------------------------------------------- probe_modules


def _modules_client():
    """A mock client whose tags/teams/metadata GETs return empty members, and
    version/publish/count GETs return benign values. Picklists is NOT routed
    here — the conditional path supplies it via conditional_refetch."""
    empty = _Resp({"hydra:member": []})
    return _MockClient(
        session_routes={  # client.session.get(url, ...)
            "/api/3/tags": empty,
            "/api/3/teams": empty,
            "staging_model_metadatas": _Resp({"hydra:member": []}),
        },
        get_routes={  # client.get(path) -> dict
            "/api/version": {"version": "8.0.0"},
            "/api/publish/error": {"last_publish_time": 0},
            "$limit=0": {"hydra:totalItems": 0},
        },
    )


def test_modules_fresh_skips_wipe(conn, cond_enabled, monkeypatch):
    probe = probe_modules  # bound from the module-level import

    _seed_module(conn)
    wiped = {"n": 0}
    real_wipe = probe.wipe_probe_tables

    def _wipe_spy(c, name):
        wiped["n"] += 1
        return real_wipe(c, name)

    monkeypatch.setattr(probe, "conditional_refetch", lambda *a, **k: ("fresh", None))
    monkeypatch.setattr(probe, "wipe_probe_tables", _wipe_spy)

    n_mod, n_fld, errs = probe._live(conn)

    assert (n_mod, n_fld, errs) == (0, 0, [])
    assert wiped["n"] == 0
    assert _count(conn, "modules") == 1  # pre-seed survives


def test_modules_refreshed_wipes_and_runs(conn, cond_enabled, monkeypatch):
    """Refreshed 200 -> wipe_probe_tables fires, the body parses, the run completes."""
    probe = probe_modules  # bound from the module-level import

    wiped = {"n": 0}
    real_wipe = probe.wipe_probe_tables

    def _wipe_spy(c, name):
        wiped["n"] += 1
        return real_wipe(c, name)

    # A picklist_names body with one list + one item.
    picklists_body = {"hydra:member": [
        {"name": "Severities", "picklists": [
            {"@id": "/api/3/picklists/abc", "itemValue": "High"}]},
    ]}
    monkeypatch.setattr(probe, "conditional_refetch",
                        lambda *a, **k: ("refreshed", picklists_body))
    monkeypatch.setattr(probe, "wipe_probe_tables", _wipe_spy)
    monkeypatch.setattr(_env, "get_client", lambda: _modules_client())
    _ensure_modules_probe_tables(conn)

    n_mod, n_fld, errs = probe._live(conn)

    assert errs == []
    assert wiped["n"] == 1
    # metadata returned no members -> no modules/fields, but picklists parsed:
    assert n_mod == 0 and n_fld == 0
    assert _count(conn, "picklists") == 1  # the one item row from the payload


def test_modules_error_keeps_catalog(conn, cond_enabled, monkeypatch):
    probe = probe_modules  # bound from the module-level import

    _seed_module(conn)
    monkeypatch.setattr(probe, "conditional_refetch",
                        lambda *a, **k: ("error", "metadata down"))

    n_mod, n_fld, errs = probe._live(conn)

    assert (n_mod, n_fld) == (0, 0)
    assert errs == ["metadata down"]
    assert _count(conn, "modules") == 1  # untouched


def _ensure_modules_probe_tables(conn):
    # tags/teams are created by probe_modules.main() (CREATE TABLE IF NOT
    # EXISTS), not schema.sql — ensure they exist for direct _live calls.
    conn.execute("CREATE TABLE IF NOT EXISTS tags (name TEXT PRIMARY KEY, iri TEXT NOT NULL)")
    conn.execute("CREATE TABLE IF NOT EXISTS teams (name TEXT PRIMARY KEY, iri TEXT NOT NULL)")
    conn.commit()


def _seed_module(conn):
    _ensure_modules_probe_tables(conn)
    conn.execute(
        "INSERT INTO modules (name, label) VALUES ('alerts', 'Alerts')"
    )
    conn.commit()
