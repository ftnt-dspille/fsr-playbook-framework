"""Tier-2 conditional refetch — ``probes.common.conditional_refetch``.

Drives the TTL short-circuit + ``If-None-Match`` 304/200 protocol against a
mock client (no live SOAR). Verifies the ETag/``data_warmed_at`` bookkeeping in
``_catalog_meta`` and the per-outcome return contract.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from fsr_playbooks import _catalog_meta as cm
from probes.common import conditional_refetch


class _Resp:
    def __init__(self, status_code, *, etag=None, body=None):
        self.status_code = status_code
        self.headers = {"ETag": etag} if etag else {}
        self._body = body

    def json(self):
        return self._body


class _Client:
    """Minimal stand-in for the pyfsr client surface the probe uses."""

    def __init__(self, resp):
        self.base_url = "https://soar.example"
        self.verify_ssl = False
        self._resp = resp
        self.calls: list[dict] = []
        self.session = self

    def get(self, url, params=None, headers=None, verify=None):
        self.calls.append({"url": url, "params": params, "headers": headers})
        if isinstance(self._resp, Exception):
            raise self._resp
        return self._resp


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    yield c
    c.close()


def _stamp_warm(conn, *, age_seconds):
    when = datetime.now(timezone.utc) - timedelta(seconds=age_seconds)
    cm.set_(conn, "data_warmed_at", when.isoformat(timespec="seconds"))


def test_fresh_within_ttl_makes_no_request(conn):
    _stamp_warm(conn, age_seconds=10)
    client = _Client(_Resp(200, etag="new", body={"data": []}))
    outcome, payload = conditional_refetch(
        client, url="/api/3/picklists", conn=conn, collection="picklists",
        ttl_seconds=3600,
    )
    assert outcome == "fresh"
    assert payload is None
    assert client.calls == []  # short-circuited before any HTTP


def test_expired_sends_if_none_match_and_handles_304(conn):
    _stamp_warm(conn, age_seconds=7200)
    cm.record_etag(conn, "picklists", "etag-v1")
    client = _Client(_Resp(304))
    outcome, payload = conditional_refetch(
        client, url="/api/3/picklists", conn=conn, collection="picklists",
        ttl_seconds=3600,
    )
    assert outcome == "unchanged"
    assert payload is None
    # conditional header sent with the stored ETag
    assert client.calls[0]["headers"] == {"If-None-Match": "etag-v1"}
    # 304 means content is current → warm clock advanced, ETag unchanged
    assert cm.is_ttl_expired(conn, ttl_seconds=3600) is False
    assert cm.get_etag(conn, "picklists") == "etag-v1"


def test_expired_200_records_new_etag_and_returns_body(conn):
    _stamp_warm(conn, age_seconds=7200)
    cm.record_etag(conn, "picklists", "etag-v1")
    body = {"data": [{"id": 1}]}
    client = _Client(_Resp(200, etag="etag-v2", body=body))
    outcome, payload = conditional_refetch(
        client, url="/api/3/picklists", conn=conn, collection="picklists",
        ttl_seconds=3600,
    )
    assert outcome == "refreshed"
    assert payload == body
    assert cm.get_etag(conn, "picklists") == "etag-v2"
    assert cm.is_ttl_expired(conn, ttl_seconds=3600) is False


def test_never_warmed_issues_unconditional_get(conn):
    # No data_warmed_at and no ETag → expired, plain GET (no If-None-Match).
    client = _Client(_Resp(200, body={"data": []}))
    outcome, _ = conditional_refetch(
        client, url="/api/3/tags", conn=conn, collection="tags",
    )
    assert outcome == "refreshed"
    assert client.calls[0]["headers"] is None


def test_request_exception_returns_error(conn):
    _stamp_warm(conn, age_seconds=7200)
    client = _Client(RuntimeError("connection reset"))
    outcome, msg = conditional_refetch(
        client, url="/api/3/tags", conn=conn, collection="tags",
        ttl_seconds=3600,
    )
    assert outcome == "error"
    assert "tags" in msg


def test_unexpected_status_returns_error(conn):
    _stamp_warm(conn, age_seconds=7200)
    client = _Client(_Resp(500))
    outcome, msg = conditional_refetch(
        client, url="/api/3/tags", conn=conn, collection="tags",
        ttl_seconds=3600,
    )
    assert outcome == "error"
    assert "500" in msg
