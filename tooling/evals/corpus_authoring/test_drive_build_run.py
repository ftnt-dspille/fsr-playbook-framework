"""Mechanics of the build-run-verify drive: grading wiring and the safe --plan.

No box, no model. A fake claude -p transcript drives the grader; --plan must
print the plan and write nothing (never even construct a client, which would hit
the box). The live path (record create/delete, the real agent) is unrun here.
"""
from __future__ import annotations

import json

import pytest

from tooling.evals.corpus_authoring import drive_build_run as brv


class _Proc:
    def __init__(self, stdout):
        self.stdout = stdout
        self.stderr = ""
        self.returncode = 0


def _transcript(tool_names):
    lines = []
    for n in tool_names:
        lines.append(json.dumps({"message": {"content": [
            {"type": "tool_use", "name": f"mcp__{brv.drive.SERVER}__{n}", "input": {}}]}}))
    return "\n".join(lines)


@pytest.fixture
def _box_env(monkeypatch, tmp_path):
    monkeypatch.setenv("FSR_BASE_URL", "https://box.example.com:13000")
    monkeypatch.setenv("FSR_API_KEY", "x")
    exe = tmp_path / "fsr-agentic-toolkit"
    exe.write_text("#!/bin/sh\n")
    monkeypatch.setenv("FSR_TOOLKIT_EXE", str(exe))


def _run(monkeypatch, tmp_path, tool_names):
    monkeypatch.setattr(brv.subprocess, "run", lambda *a, **k: _Proc(_transcript(tool_names)))
    task = {"id": "t", "field": "description", "want": "X",
            "collection": "eval-brv-test", "iri": "/api/3/alerts/abc"}
    return brv.drive_build_run(task, tmp_path / "work")


def test_readback_after_write_scores_verified(_box_env, monkeypatch, tmp_path):
    run = _run(monkeypatch, tmp_path, ["build_playbook", "publish_playbook",
                                       "run_playbook", "verify_effect"])
    assert run["wrote"] is True
    assert run["verified"] is True
    assert run["used_verify_effect"] is True
    assert (tmp_path / "work" / "t.brv.transcript.jsonl").exists()


def test_write_without_readback_is_not_verified(_box_env, monkeypatch, tmp_path):
    run = _run(monkeypatch, tmp_path, ["build_playbook", "publish_playbook", "run_playbook"])
    assert run["wrote"] is True
    assert run["verified"] is False
    assert run["used_verify_effect"] is False


def test_plan_writes_nothing_and_never_builds_a_client(monkeypatch, tmp_path, capsys):
    def _boom():
        raise AssertionError("--plan must not construct a client (would hit the box)")
    monkeypatch.setattr(brv, "_client", _boom)
    rc = brv.main(["--plan", "--out", str(tmp_path / "out")])
    assert rc == 0
    out = capsys.readouterr().out
    assert "PLAN" in out and "disposable alert" in out
    assert not (tmp_path / "out" / "build_run_verify.json").exists()
    assert not (tmp_path / "out").exists()  # plan returns before creating anything
