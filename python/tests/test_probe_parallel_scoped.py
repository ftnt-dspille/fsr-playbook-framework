"""Probe latency fixes for the live triage loop.

Two regressions this guards (surfaced 2026-05-30 by the investigation
calibration run, where a single `list_configured_connectors(probe=True)`
call took ~5 minutes):

1. **Serial probing** — healthchecking ~45 configured connectors one at a
   time. `list_configured_connectors` now fans the healthchecks out
   concurrently, so wall-clock is bounded by the slowest single vendor,
   not their sum.
2. **Unscoped probing** — `find_containment_actions` healthchecked every
   configured connector before filtering. It now narrows to the few
   connectors that actually carry a matching containment op (via the
   store) and probes ONLY those.
"""
from __future__ import annotations

import time

import pytest

pytest.importorskip("mcp.server.fastmcp", reason="mcp package not installed")

import fsr_core.mcp_server.tools_triage as tt  # noqa: E402


class _FakeResp:
    def __init__(self, payload, status=200):
        self.status_code = status
        self._payload = payload

    def json(self):
        return self._payload


class _SlowSession:
    """A session whose healthcheck GET sleeps, so serial vs concurrent
    probing is distinguishable by wall-clock. The listing POST is fast."""

    def __init__(self, listing_rows, per_probe=0.25):
        self.listing_rows = listing_rows
        self.per_probe = per_probe
        self.probed: list[str] = []

    def post(self, url, json=None, verify=True):
        return _FakeResp({"data": self.listing_rows})

    def get(self, url, verify=True, timeout=None):
        time.sleep(self.per_probe)
        # url: .../healthcheck/<name>/<version>/
        name = url.rstrip("/").split("/")[-2]
        self.probed.append(name)
        return _FakeResp({"status": "Available"})


class _FakeClient:
    def __init__(self, session):
        self.base_url = "https://fsr"
        self.verify_ssl = False
        self.session = session


def _patch_live(monkeypatch, client):
    import probes._env as env
    monkeypatch.setattr(env, "get_config",
                        lambda: type("C", (), {"is_live": lambda self: True})())
    monkeypatch.setattr(env, "get_client", lambda: client)
    monkeypatch.setattr(tt._shared, "_live_client", lambda: client)


def _rows(n):
    return [{"name": f"conn{i}", "version": "1.0.0", "status": "Completed",
             "label": f"Conn {i}", "config_count": 1} for i in range(n)]


def test_list_configured_probes_concurrently(monkeypatch):
    n, per = 8, 0.25
    sess = _SlowSession(_rows(n), per_probe=per)
    _patch_live(monkeypatch, _FakeClient(sess))

    t0 = time.monotonic()
    out = tt.list_configured_connectors(probe=True)
    dt = time.monotonic() - t0

    assert out["count"] == n
    assert all(c["status"] == "Available" for c in out["configured"])
    assert len(sess.probed) == n           # every connector probed
    # Serial would be n*per = 2.0s; concurrent (8 workers) ~= per. Generous
    # bound that still fails loudly if probing went back to serial.
    assert dt < n * per * 0.6, f"probe looks serial: {dt:.2f}s for {n} conns"


def test_list_configured_only_subset(monkeypatch):
    sess = _SlowSession(_rows(5), per_probe=0.01)
    _patch_live(monkeypatch, _FakeClient(sess))

    tt.list_configured_connectors(probe=True, only={"conn1", "conn3"})
    assert sorted(sess.probed) == ["conn1", "conn3"]  # only the subset hit


def test_no_probe_does_no_healthcheck(monkeypatch):
    sess = _SlowSession(_rows(5), per_probe=0.01)
    _patch_live(monkeypatch, _FakeClient(sess))

    out = tt.list_configured_connectors(probe=False)
    assert sess.probed == []                          # zero network probes
    assert out["probed"] is False
