"""Repair-driver mechanics, box-free and LLM-free (fake `claude -p`).

Pins the contract run_repair relies on: the broken YAML reaches the prompt, the
MCP wiring matches the authoring driver, and the repaired YAML is taken from the
last tool call that carried it (not a stale fence). A fake subprocess stands in
for `claude -p` so no subscription or box is touched.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from tooling.evals.corpus_authoring import drive, drive_repair


class _FakeProc:
    def __init__(self, stdout: str) -> None:
        self.stdout, self.stderr, self.returncode = stdout, "", 0


def _stream(*events: dict) -> str:
    return "\n".join(json.dumps(e) for e in events)


def _tool_use(name, **inp):
    return {"message": {"content": [
        {"type": "tool_use", "name": f"mcp__{drive.SERVER}__{name}", "input": inp}]}}


def test_repair_prompt_carries_broken_yaml_and_extracts_fix(tmp_path, monkeypatch):
    broken = "collection: X\nplaybooks:\n- name: P\n  steps:\n  - type: start\n    name: s\n    next: GHOST\n"
    fixed = "collection: X\nplaybooks:\n- name: P\n  steps:\n  - type: start\n    name: s\n"
    captured: dict = {}

    def fake_run(cmd, **kw):
        captured["cmd"] = cmd
        # the agent diagnoses then repairs: verify first, repair_playbook last.
        return _FakeProc(_stream(
            _tool_use("verify_playbook", yaml_text=broken),
            _tool_use("repair_playbook", yaml_text=fixed),
            {"type": "result", "result": "fixed it"}))

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(drive_repair.subprocess, "run", fake_run)
    # a real toolkit exe is not needed for mechanics; stub the resolver + creds
    monkeypatch.setattr(drive, "_toolkit_exe", lambda: "/bin/true")
    monkeypatch.setenv("FSR_BASE_URL", "https://box.example.com")
    monkeypatch.setenv("FSR_API_KEY", "x")

    task = {"id": "loop__demo__abcd1234__expert"}
    defect = {"kind": "unknown_step_reference", "yaml": broken}
    res = drive_repair.drive_repair(task, defect, tmp_path, timeout=5)

    # the broken YAML must be in the prompt the agent saw
    prompt = captured["cmd"][2]
    assert "GHOST" in prompt and "Broken playbook" in prompt
    # MCP wiring identical to the authoring driver
    assert "--strict-mcp-config" in captured["cmd"]
    assert drive._ALLOWED in captured["cmd"]
    # repaired YAML is the LAST tool yaml (repair_playbook), not the broken one
    assert res["repaired_yaml"] == fixed
    assert res["repaired_yaml"] != broken
    assert res["used_debug"] is True          # repair_playbook counts as debug/repair
    assert res["used_verify"] is True
    assert res["tools"] == ["verify_playbook", "repair_playbook"]


def test_transcript_is_written(tmp_path, monkeypatch):
    monkeypatch.setattr(subprocess, "run",
                        lambda cmd, **kw: _FakeProc(_stream(_tool_use("orient", goal="x"))))
    monkeypatch.setattr(drive_repair.subprocess, "run",
                        lambda cmd, **kw: _FakeProc(_stream(_tool_use("orient", goal="x"))))
    monkeypatch.setattr(drive, "_toolkit_exe", lambda: "/bin/true")
    monkeypatch.setenv("FSR_BASE_URL", "https://box.example.com")
    monkeypatch.setenv("FSR_API_KEY", "x")
    task = {"id": "simple__p__0000__terse"}
    defect = {"kind": "orphan_step", "yaml": "collection: X\nplaybooks: []\n"}
    drive_repair.drive_repair(task, defect, tmp_path, timeout=5)
    t = Path(tmp_path) / "simple__p__0000__terse__orphan_step.repair.transcript.jsonl"
    assert t.exists() and t.read_text().strip()
