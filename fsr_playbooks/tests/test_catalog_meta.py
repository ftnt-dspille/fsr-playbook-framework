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
from datetime import datetime, timedelta, timezone

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
    # No ensure_table() yet -- reads must not blow up.
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


def test_normalize_base_url_drops_default_ports_only():
    """https://box:443 IS https://box; the :13000 migration listener is NOT.

    Over-triggering ahead of a cheap lazy auto-warm is survivable, but default
    ports are pure spelling -- they must not read as a different appliance.
    """
    assert cm.normalize_base_url("https://box/") == \
        cm.normalize_base_url("https://box:443") == "box"
    assert cm.normalize_base_url("http://box:80/some/path") == "box/some/path"
    assert cm.normalize_base_url("https://box:13000") == "box:13000"
    assert cm.base_url_hash("https://box") == cm.base_url_hash("https://box:443/")
    assert cm.base_url_hash("https://box:13000") != cm.base_url_hash("https://box")


def test_stamp_and_check_match(conn):
    cm.stamp_instance(conn, instance_label="dev", base_url="https://198.51.100.10",
                      instance_serial="FSRVMTEST260001")
    assert cm.get(conn, "instance_serial") == "FSRVMTEST260001"
    status, label, _ = cm.check_instance(conn, "https://198.51.100.10/")
    assert status == "ok"
    assert label == "dev"
    other, _, _ = cm.check_instance(conn, "https://198.51.100.99")
    assert other == "mismatch"


def test_license_serial_prefers_the_primary_node():
    payload = {"nodes": {
        "n2": {"details": {"serial_no": "SECONDARY"}, "node": {"role": "secondary"}},
        "n1": {"details": {"serial_no": "PRIMARY-BOX"}, "node": {"role": "primary"}},
    }}
    assert cm.license_serial_from_details(payload) == "PRIMARY-BOX"


def test_license_serial_survives_moduleless_payloads():
    assert cm.license_serial_from_details(None) is None
    assert cm.license_serial_from_details("junk") is None
    assert cm.license_serial_from_details({"nodes": {}}) is None
    assert cm.license_serial_from_details(
        {"details": {"serial_no": "TOPLEVEL"}}) == "TOPLEVEL"


def test_restamp_without_serial_keeps_the_recorded_serial(conn):
    """Serial provenance is write-once through the optional param: a re-stamp
    that cannot fetch the license again never erases the identity."""
    cm.stamp_instance(conn, instance_label="dev", base_url="https://198.51.100.10",
                      instance_serial="FSRVMTEST260001")
    cm.stamp_instance(conn, instance_label="dev2", base_url="https://198.51.100.11")
    assert cm.get(conn, "instance_serial") == "FSRVMTEST260001"


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


# ----------------------- ETag & data_warmed_at (Tier-2 support) -----------------------


def test_record_etag_roundtrip(conn):
    cm.record_etag(conn, "picklists", "abc123def456")
    retrieved = cm.get(conn, "etag:picklists")
    assert retrieved == "abc123def456"


def test_record_etag_idempotent(conn):
    cm.record_etag(conn, "tags", "v1-etag")
    assert cm.get(conn, "etag:tags") == "v1-etag"
    cm.record_etag(conn, "tags", "v2-etag")  # upsert
    assert cm.get(conn, "etag:tags") == "v2-etag"


def test_get_etag_absent_defaults_none(conn):
    retrieved = cm.get(conn, "etag:nonexistent")
    assert retrieved is None


def test_data_warmed_at_sets_iso_timestamp(conn):
    cm.record_data_warmed_at(conn)
    ts = cm.get(conn, "data_warmed_at")
    assert ts is not None
    # Verify ISO-8601 UTC format: "2026-06-23T12:34:56" (no Z suffix in this impl)
    assert len(ts) >= 19  # YYYY-MM-DDTHH:MM:SS
    assert "T" in ts
    assert "-" in ts
    assert ":" in ts


# ----------------------- Tier-2 freshness consume side -----------------------


def test_get_data_warmed_at_absent_is_none(conn):
    assert cm.get_data_warmed_at(conn) is None


def test_get_data_warmed_at_after_record(conn):
    cm.record_data_warmed_at(conn)
    assert cm.get_data_warmed_at(conn) == cm.get(conn, "data_warmed_at")


def test_get_etag_roundtrip_and_absent(conn):
    assert cm.get_etag(conn, "picklists") is None
    cm.record_etag(conn, "picklists", "W/\"abc\"")
    assert cm.get_etag(conn, "picklists") == "W/\"abc\""


def test_is_ttl_expired_when_never_warmed(conn):
    # No data_warmed_at stamp at all → treat as expired (force a first warm).
    assert cm.is_ttl_expired(conn) is True


def test_is_ttl_expired_within_window(conn):
    recent = datetime.now(timezone.utc) - timedelta(seconds=60)
    cm.set_(conn, "data_warmed_at", recent.isoformat(timespec="seconds"))
    assert cm.is_ttl_expired(conn, ttl_seconds=3600) is False


def test_is_ttl_expired_past_window(conn):
    old = datetime.now(timezone.utc) - timedelta(seconds=7200)
    cm.set_(conn, "data_warmed_at", old.isoformat(timespec="seconds"))
    assert cm.is_ttl_expired(conn, ttl_seconds=3600) is True


def test_is_ttl_expired_malformed_timestamp(conn):
    cm.set_(conn, "data_warmed_at", "not-a-timestamp")
    assert cm.is_ttl_expired(conn) is True


def test_is_ttl_expired_naive_timestamp_assumed_utc(conn):
    # A stamp without an offset must not raise (assume UTC) and compare sanely.
    recent = datetime.now(timezone.utc).replace(tzinfo=None)
    cm.set_(conn, "data_warmed_at", recent.isoformat(timespec="seconds"))
    assert cm.is_ttl_expired(conn, ttl_seconds=3600) is False
