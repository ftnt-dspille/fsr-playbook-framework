"""``warm_catalog`` against a fake box: populates the box tables, stamps identity,
never writes the packaged catalog, and is idempotent.

The fake client speaks the two pyfsr surfaces the warm uses: ``client.get`` /
``client.post`` (parsed JSON) and ``client.session.get`` (a Response-like object
with headers). It serves canned bodies and records which endpoints were hit.
No network, no live box.
"""
from __future__ import annotations

import hashlib
import pathlib
import shutil
import sqlite3
from pathlib import Path

import pytest

from fsr_playbooks import _catalog_meta, warmup
from fsr_playbooks._db import PACKAGED_SLIM_DB
from fsr_playbooks.warmup import WarmupError, warm_catalog

BASE = "https://fsr.example.com"

PICKLISTS = {"hydra:member": [
    {"name": "AlertStatus", "picklists": [
        {"@id": "/api/3/picklists/p1", "itemValue": "Open"},
        {"@id": "/api/3/picklists/p2", "itemValue": "Closed"},
    ]},
    {"name": "Severity", "picklists": [
        {"@id": "/api/3/picklists/p3", "itemValue": "High"},
    ]},
]}
# 8.0 serves tags as bare strings; an object form must still read.
TAGS = {"hydra:member": ["Phishing", {"name": "c2", "@id": "/api/3/tags/c2"}]}
TEAMS = {"hydra:member": [{"name": "SOC", "@id": "/api/3/teams/t1"}]}
METADATA = {"hydra:member": [
    {"type": "alerts", "module": "alerts", "displayName": "Alerts",
     "uniqueConstraint": [{"u": {"columns": ["sourceId"]}}],
     "attributes": [
         {"name": "name", "title": "Name", "type": "text"},
         {"name": "status", "title": "Status", "type": "picklist",
          "dataSource": {"query": {"filters": [
              {"field": "listName__name", "value": "AlertStatus"}]}},
          "validation": {"required": True}},
         {"name": "createDate", "title": "Created", "type": "integer",
          "formType": "datetime"},
     ]},
    {"type": "incidents", "module": "incidents", "displayName": "Incidents",
     "attributes": [{"name": "title", "title": "Title", "type": "text"}]},
]}
# Connector list: one connector with two configurations, one with none.
CONNECTORS = {"data": [
    {"name": "fortinet-soc", "version": "1.0.0", "configuration": [
        {"config_id": "cfg-a", "name": "Default", "default": True},
        {"config_id": "cfg-b", "name": "Lab", "default": False},
    ]},
    {"name": "smtp", "version": "2.0.0", "configuration": []},
]}
DETAILS = {
    ("fortinet-soc", "1.0.0"): {
        "name": "fortinet-soc", "version": "1.0.0", "label": "FortiSOC",
        "category": ["SIEM"], "active": True,
        "operations": [{"operation": "get_incident", "title": "Get",
                        "parameters": [{"name": "id", "type": "text",
                                        "required": True,
                                        "onchange": {"yes": [{"name": "extra"}]}}]}],
    },
    ("smtp", "2.0.0"): {
        "name": "smtp", "version": "2.0.0", "label": "SMTP",
        "operations": [{"operation": "send_email", "parameters": []}],
    },
}
LICENSE = {"nodes": {"n1": {"node": {"role": "primary"},
                            "details": {"serial_no": "FSRTEST0000001"}}}}

# Every endpoint a warm is allowed to hit, by path with the query stripped.
EXPECTED_PATHS = {
    "/api/3/picklist_names", "/api/3/tags", "/api/3/teams",
    "/api/3/staging_model_metadatas", "/api/integration/connectors/",
    "/api/integration/connectors/{name}/{version}/",
    "/api/version", "/api/publish/error", "/api/auth/license",
    "/api/3/model_metadatas", "/api/3/attribute_metadatas",
    "/api/3/picklists",
}


class _Resp:
    def __init__(self, body, *, status: int = 200, etag: str | None = None):
        self._body = body
        self.status_code = status
        self.headers = {"ETag": etag} if etag else {}

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _Session:
    def __init__(self, box: FakeBox):
        self._box = box

    def get(self, url, params=None, headers=None, verify=None, **_):
        path = url[len(BASE):] if url.startswith(BASE) else url
        base = path.split("?")[0]
        self._box.calls.append(base)
        if base in self._box.fail:
            return _Resp({}, status=500)
        body = self._box.routes[base]
        return body if isinstance(body, _Resp) else _Resp(body)


class FakeBox:
    base_url = BASE
    verify_ssl = False

    def __init__(self, *, fail: set[str] = frozenset()):
        self.fail = set(fail)
        self.calls: list[str] = []
        self.session = _Session(self)
        self.routes = {
            "/api/3/picklist_names": _Resp(PICKLISTS, etag='W/"pl-1"'),
            "/api/3/tags": TAGS,
            "/api/3/teams": TEAMS,
            "/api/3/staging_model_metadatas": _Resp(METADATA, etag='W/"md-1"'),
            "/api/integration/connectors/": CONNECTORS,
        }
        self._get_routes = {
            "/api/version": {"version": "8.0.1-6034"},
            "/api/publish/error": {"last_publish_time": 1700000000},
            "/api/auth/license": LICENSE,
        }

    def get(self, path, params=None, **_):
        base = path.split("?")[0]
        if "$limit=0" in path:
            self.calls.append(base)
            return {"hydra:totalItems": 7}
        self.calls.append(base)
        if base in self._get_routes:
            return self._get_routes[base]
        if base == "/api/integration/connectors/":
            return CONNECTORS
        raise KeyError(path)

    def post(self, path, data=None, **_):
        base = path.split("?")[0]
        parts = base.strip("/").split("/")  # api integration connectors <name> <ver>
        key = (parts[3], parts[4])
        self.calls.append("/api/integration/connectors/{name}/{version}/")
        return DETAILS[key]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _copy_seed(tmp_path: Path, name: str = "catalog.db") -> Path:
    target = tmp_path / name
    shutil.copy(PACKAGED_SLIM_DB, target)
    return target


def _count(db: Path, table: str) -> int:
    conn = sqlite3.connect(db)
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        conn.close()


def _rows(db: Path, sql: str) -> list:
    conn = sqlite3.connect(db)
    try:
        return conn.execute(sql).fetchall()
    finally:
        conn.close()


def test_populates_box_tables_and_stamps_identity(tmp_path):
    target = tmp_path / "warm.db"
    report = warm_catalog(FakeBox(), target, instance_label="lab-a",
                          seed_from=PACKAGED_SLIM_DB)

    assert report["committed"] is True
    assert report["errors"] == []
    assert report["counts"] == {
        "modules": 2, "module_fields": 4, "picklists": 3, "tags": 2,
        "teams": 1, "connectors": 2, "operations": 2, "operation_params": 2,
        "connector_configs": 3,
    }
    # Installed-only: the 13 connectors the packaged seed ships are replaced.
    assert {r[0] for r in _rows(target, "SELECT name FROM connectors")} == {"fortinet-soc", "smtp"}
    assert _rows(target, "SELECT picklist_options FROM module_fields "
                         "WHERE module_name='alerts' AND field_name='status'") == [('["Open", "Closed"]',)]
    assert _rows(target, "SELECT type FROM module_fields "
                         "WHERE module_name='alerts' AND field_name='createDate'") == [("datetime",)]
    assert _rows(target, "SELECT unique_constraint FROM modules WHERE name='alerts'") == [('["sourceId"]',)]
    assert _rows(target, "SELECT parent_param_name, condition_value, param_name "
                         "FROM operation_params ORDER BY param_name") == [
        ("id", "yes", "extra"), (None, None, "id")]
    assert _rows(target, "SELECT config_name FROM connector_configs "
                         "WHERE connector='fortinet-soc' ORDER BY config_name") == [
        ("Default",), ("Lab",), ("__default__",)]

    assert report["stamp"]["instance_label"] == "lab-a"
    assert report["stamp"]["base_url"] == "fsr.example.com"
    assert report["stamp"]["fsr_version"] == "8.0.1-6034"
    assert report["stamp"]["instance_serial"] == "FSRTEST0000001"

    conn = sqlite3.connect(target)
    try:
        assert _catalog_meta.check_instance(conn, BASE)[0] == "ok"
        assert _catalog_meta.check_instance(conn, "https://other.example.com")[0] == "mismatch"
        assert _catalog_meta.get(conn, "etag:picklists") == 'W/"pl-1"'
        assert _catalog_meta.get(conn, "etag:model_metadatas") == 'W/"md-1"'
        assert _catalog_meta.get(conn, "count:picklists") == "7"
        assert _catalog_meta.get_data_warmed_at(conn) is not None
        assert _catalog_meta.get(conn, "last_publish_time") == "1700000000"
    finally:
        conn.close()

    status = _rows(target, "SELECT status FROM verifications "
                           "WHERE kind='module' AND key='alerts'")
    assert status == [("tested_pass",)]


def test_second_run_is_idempotent(tmp_path):
    target = tmp_path / "warm.db"
    first = warm_catalog(FakeBox(), target, seed_from=PACKAGED_SLIM_DB)
    second = warm_catalog(FakeBox(), target, seed_from=PACKAGED_SLIM_DB)

    assert second["committed"] is True
    assert second["counts"] == first["counts"]
    assert second["errors"] == []


def test_seeds_static_tables_when_target_absent(tmp_path):
    target = tmp_path / "fresh" / "warm.db"
    assert not target.exists()

    warm_catalog(FakeBox(), target, seed_from=PACKAGED_SLIM_DB)

    assert target.exists()
    assert _count(target, "step_types") > 0


def test_packaged_db_is_never_written(tmp_path):
    before = _sha(PACKAGED_SLIM_DB)
    warm_catalog(FakeBox(), tmp_path / "warm.db", seed_from=PACKAGED_SLIM_DB)
    assert _sha(PACKAGED_SLIM_DB) == before

    with pytest.raises(WarmupError, match="shipped or dev"):
        warm_catalog(FakeBox(), PACKAGED_SLIM_DB)
    assert _sha(PACKAGED_SLIM_DB) == before


def test_refuses_the_default_db_path(tmp_path, monkeypatch):
    target = _copy_seed(tmp_path)
    monkeypatch.setenv("FSRPB_DB", str(target))  # default_db_path() now == target
    before = _sha(target)

    with pytest.raises(WarmupError, match="shipped or dev"):
        warm_catalog(FakeBox(), target)
    assert _sha(target) == before


def test_refuses_a_file_that_is_not_a_reference_catalog(tmp_path):
    other = tmp_path / "other.db"
    conn = sqlite3.connect(other)
    conn.execute("CREATE TABLE unrelated (x)")
    conn.commit()
    conn.close()
    with pytest.raises(WarmupError, match="not a reference catalog"):
        warm_catalog(FakeBox(), other, seed_from=PACKAGED_SLIM_DB)


def test_refuses_an_existing_non_sqlite_file(tmp_path):
    junk = tmp_path / "junk.db"
    junk.write_bytes(b"this is not a database\n")
    with pytest.raises(WarmupError, match="not a sqlite database"):
        warm_catalog(FakeBox(), junk, seed_from=PACKAGED_SLIM_DB)
    assert junk.read_bytes() == b"this is not a database\n"


def test_failed_picklists_rolls_back_and_keeps_catalog(tmp_path):
    target = _copy_seed(tmp_path)
    before_modules = _rows(target, "SELECT name FROM modules ORDER BY name")
    before_conns = _rows(target, "SELECT name FROM connectors ORDER BY name")

    report = warm_catalog(FakeBox(fail={"/api/3/picklist_names"}), target)

    assert report["committed"] is False
    assert report["stamp"] == {}
    assert any(e.startswith("picklists:") for e in report["errors"])
    assert _rows(target, "SELECT name FROM modules ORDER BY name") == before_modules
    assert _rows(target, "SELECT name FROM connectors ORDER BY name") == before_conns


def test_failed_module_metadata_rolls_back(tmp_path):
    target = _copy_seed(tmp_path)
    before = _rows(target, "SELECT name FROM modules ORDER BY name")

    report = warm_catalog(FakeBox(fail={"/api/3/staging_model_metadatas"}), target)

    assert report["committed"] is False
    assert any(e.startswith("metadata:") for e in report["errors"])
    assert _rows(target, "SELECT name FROM modules ORDER BY name") == before


def test_failed_tags_is_reported_and_keeps_its_rows(tmp_path):
    target = _copy_seed(tmp_path)
    conn = sqlite3.connect(target)
    conn.execute("INSERT INTO tags (name, iri) VALUES ('legacy', '/api/3/tags/legacy')")
    conn.commit()
    conn.close()

    report = warm_catalog(FakeBox(fail={"/api/3/tags"}), target)

    assert report["committed"] is True
    assert any(e.startswith("tags:") for e in report["errors"])
    assert _rows(target, "SELECT name FROM tags") == [("legacy",)]
    assert report["counts"]["teams"] == 1  # the other sources still warmed


def test_warm_reads_only_the_expected_endpoints(tmp_path):
    box = FakeBox()
    warm_catalog(box, tmp_path / "warm.db", seed_from=PACKAGED_SLIM_DB)
    assert set(box.calls) == EXPECTED_PATHS


def test_live_license_serial_is_advisory(tmp_path):
    class _Broken:
        base_url = BASE

        def get(self, path, **_):
            raise RuntimeError("license endpoint down")

    assert warmup.live_license_serial(_Broken()) is None


def test_box_catalog_warms_once_then_rewarms_when_the_module_counts_move(tmp_path, monkeypatch):
    from fsr_playbooks import warmup as W

    calls = []

    def fake_warm(client, path, **kw):
        calls.append(path)
        conn = sqlite3.connect(path)
        from fsr_playbooks import _catalog_meta
        _catalog_meta.ensure_table(conn)
        _catalog_meta.stamp_instance(conn, instance_label=None, base_url=client.base_url)
        for c, n in client.counts.items():
            _catalog_meta.record_count(conn, c, n)
        conn.commit()
        conn.close()
        return {"committed": True, "errors": []}

    class C:
        base_url = "https://fortisoar.example.com"
        counts = {"model_metadatas": 46, "attribute_metadatas": 1003}

        def get(self, url, params=None):
            return {"hydra:totalItems": self.counts[url.rsplit("/", 1)[-1]]}

    monkeypatch.setattr(W, "warm_catalog", fake_warm)
    c = C()
    p1 = W.box_catalog(c, tmp_path)
    assert W.box_catalog(c, tmp_path) == p1 and len(calls) == 1  # fresh: no re-warm
    c.counts = {"model_metadatas": 47, "attribute_metadatas": 1005}
    W.box_catalog(c, tmp_path)
    assert len(calls) == 2


def test_a_failed_first_warm_leaves_no_file(tmp_path, monkeypatch):
    from fsr_playbooks import warmup as W

    def failing(client, path, **kw):
        pathlib.Path(path).write_bytes(b"seed")
        return {"committed": False, "errors": ["boom"]}

    class C:
        base_url = "https://fortisoar.example.com"

    monkeypatch.setattr(W, "warm_catalog", failing)
    with pytest.raises(W.WarmupError):
        W.box_catalog(C(), tmp_path)
    assert list(tmp_path.iterdir()) == []
