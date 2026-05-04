"""Push / env route tests — subprocess is mocked.

The run-playbook SSE path is not unit-tested here; it requires async
subprocess streaming which adds complexity disproportionate to what the
test would prove. Phase 3 ships with the CLI integration verified by
hand against a live FSR.
"""
from __future__ import annotations

import json
import subprocess
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.app import app
from backend.routes import playbook as playbook_route


client = TestClient(app)


def _mock_run(stdout: str = "", stderr: str = "", returncode: int = 0):
    def _run(cmd, **kwargs):
        return SimpleNamespace(stdout=stdout, stderr=stderr, returncode=returncode)

    return _run


def test_push_happy_path(monkeypatch):
    monkeypatch.setattr(
        playbook_route.subprocess,
        "run",
        _mock_run(stdout="pushed Hello World\n", returncode=0),
    )
    r = client.post(
        "/api/playbook/push", json={"text": "collection: Hi\nplaybooks: []\n"}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["exit_code"] == 0
    assert "pushed" in body["stdout"]


def test_push_failure_propagates(monkeypatch):
    monkeypatch.setattr(
        playbook_route.subprocess,
        "run",
        _mock_run(stderr="409 conflict\n", returncode=2),
    )
    r = client.post("/api/playbook/push", json={"text": "x"})
    body = r.json()
    assert body["ok"] is False
    assert body["exit_code"] == 2
    assert "409" in body["stderr"]


def test_push_invalid_mode():
    r = client.post("/api/playbook/push", json={"text": "x", "mode": "wat"})
    assert r.status_code == 400


def test_env_happy_path(monkeypatch):
    payload = {"vars": {"input": {"params": {"ip": "1.2.3.4"}}, "steps": {}}}
    monkeypatch.setattr(
        playbook_route.subprocess, "run", _mock_run(stdout=json.dumps(payload))
    )
    r = client.get("/api/run/676747/env")
    body = r.json()
    assert body["ok"] is True
    assert body["env"] == payload


def test_env_subprocess_error(monkeypatch):
    monkeypatch.setattr(
        playbook_route.subprocess, "run",
        _mock_run(stderr="not configured", returncode=2),
    )
    r = client.get("/api/run/abc/env")
    body = r.json()
    assert body["ok"] is False
    assert "not configured" in (body["error"] or "")


def test_scrub_strips_insecure_warning_block():
    raw = (
        "pushed Hello\n"
        "/path/connectionpool.py:1097: InsecureRequestWarning: Unverified HTTPS request "
        "is being made to host '10.99.249.205'. Adding certificate verification is strongly "
        "advised. See: https://urllib3.readthedocs.io/en/latest/advanced-usage.html#tls-warnings\n"
        "  warnings.warn(\n"
        "completed in 1.2s\n"
    )
    cleaned = playbook_route._scrub(raw)
    assert "InsecureRequestWarning" not in cleaned
    assert "warnings.warn" not in cleaned
    assert "urllib3.readthedocs.io" not in cleaned
    assert "pushed Hello" in cleaned
    assert "completed in 1.2s" in cleaned


def test_scrub_respects_opt_out(monkeypatch):
    monkeypatch.setenv("FSR_SUPPRESS_INSECURE_WARNING", "false")
    raw = "before\nInsecureRequestWarning: yo\nafter\n"
    assert playbook_route._scrub(raw) == raw


def test_push_strips_noise_from_stdout(monkeypatch):
    noisy = (
        "pushed Hello\n"
        "InsecureRequestWarning: Unverified HTTPS request is being made\n"
        "  warnings.warn(\n"
        "done\n"
    )
    monkeypatch.setattr(
        playbook_route.subprocess, "run", _mock_run(stdout=noisy, returncode=0)
    )
    r = client.post("/api/playbook/push", json={"text": "x"})
    body = r.json()
    assert "InsecureRequestWarning" not in body["stdout"]
    assert "warnings.warn" not in body["stdout"]
    assert "pushed Hello" in body["stdout"]
    assert "done" in body["stdout"]


def test_env_non_json_output(monkeypatch):
    monkeypatch.setattr(
        playbook_route.subprocess, "run", _mock_run(stdout="hello not json")
    )
    r = client.get("/api/run/abc/env")
    body = r.json()
    assert body["ok"] is False
    assert "non-JSON" in (body["error"] or "")
