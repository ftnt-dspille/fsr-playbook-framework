"""Catalog provenance / freshness metadata + the multi-instance guard.

Covers ``fsr_playbooks/_catalog_meta.py``:

* the key/value table round-trips and tolerates an absent table;
* base-URL normalization collapses scheme / trailing-slash differences;
* :func:`instance_guard` fires a diagnostic ONLY on a genuine mismatch, stays
  silent when the catalog is unstamped or no target is configured, and respects
  the strict-mode escalation.
"""
from __future__ import annotations

import sqlite3

import pytest

from fsr_playbooks import _catalog_meta as cm
from fsr_playbooks.compiler.errors import CompileError, ErrorCode


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    yield c
    c.close()


def test_get_on_absent_table_is_unstamped(conn):
    # No ensure_table() yet — reads must not blow up.
    assert cm.get(conn, "base_url_hash") is None
    assert cm.get_all(conn) == {}
    status, label, h = cm.check_instance(conn, "https://10.0.0.1")
    assert status == "unstamped"


def test_set_get_roundtrip(conn):
    cm.set_(conn, "fsr_version", "7.6.5-622")
    assert cm.get(conn, "fsr_version") == "7.6.5-622"
    cm.set_(conn, "fsr_version", "7.7.0-1")  # upsert
    assert cm.get(conn, "fsr_version") == "7.7.0-1"


def test_normalize_base_url_collapses_scheme_and_slash():
    a = cm.normalize_base_url("https://SOAR.example.com/")
    b = cm.normalize_base_url("http://soar.example.com")
    assert a == b == "soar.example.com"
    assert cm.base_url_hash("https://soar.example.com/") == \
        cm.base_url_hash("soar.example.com")


def test_stamp_and_check_match(conn):
    cm.stamp_instance(conn, instance_label="dev", base_url="https://<your-fortisoar-host>")
    status, label, _ = cm.check_instance(conn, "https://<your-fortisoar-host>/")
    assert status == "ok"
    assert label == "dev"
    other, _, _ = cm.check_instance(conn, "https://<your-fortisoar-host>")
    assert other == "mismatch"


def test_guard_silent_without_target(conn, monkeypatch):
    cm.stamp_instance(conn, instance_label="dev", base_url="https://a.example")
    monkeypatch.delenv("FSR_BASE_URL", raising=False)
    errors: list[CompileError] = []
    cm.instance_guard(conn, errors)
    assert errors == []


def test_guard_silent_when_unstamped(conn, monkeypatch):
    monkeypatch.setenv("FSR_BASE_URL", "https://b.example")
    errors: list[CompileError] = []
    cm.instance_guard(conn, errors)  # nothing stamped → no basis to complain
    assert errors == []


def test_guard_warns_on_mismatch(conn, monkeypatch):
    cm.stamp_instance(conn, instance_label="dev", base_url="https://a.example")
    monkeypatch.setenv("FSR_BASE_URL", "https://b.example")
    monkeypatch.delenv("FSRPB_STRICT_INSTANCE", raising=False)
    errors: list[CompileError] = []
    cm.instance_guard(conn, errors)
    assert len(errors) == 1
    assert errors[0].code == ErrorCode.INSTANCE_MISMATCH
    assert errors[0].severity == "warning"
    assert "dev" in errors[0].message


def test_guard_strict_mode_blocks(conn, monkeypatch):
    cm.stamp_instance(conn, instance_label="dev", base_url="https://a.example")
    monkeypatch.setenv("FSR_BASE_URL", "https://b.example")
    monkeypatch.setenv("FSRPB_STRICT_INSTANCE", "1")
    errors: list[CompileError] = []
    cm.instance_guard(conn, errors)
    assert len(errors) == 1
    assert errors[0].severity == "error"


def test_guard_ok_when_target_matches(conn, monkeypatch):
    cm.stamp_instance(conn, instance_label="dev", base_url="https://a.example")
    monkeypatch.setenv("FSR_BASE_URL", "https://a.example/")
    errors: list[CompileError] = []
    cm.instance_guard(conn, errors)
    assert errors == []
