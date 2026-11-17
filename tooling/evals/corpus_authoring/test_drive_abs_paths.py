"""The drivers must hand claude -p an ABSOLUTE --mcp-config and cwd.

claude -p runs with cwd=work. A relative --mcp-config then resolves against
work and does not exist, so --strict-mcp-config loads no servers, the agent has
no toolkit tools, and the scorecard reports 0 -- a measurement artifact that
reads like "the agent never used the tool". These pin the paths absolute even
when the caller passes a relative work dir (red without the work.resolve() fix).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tooling.evals.corpus_authoring import drive, drive_repair


class _Proc:
    stdout = ""
    stderr = ""
    returncode = 0


def _capture(monkeypatch, module):
    seen: dict = {}

    def fake_run(cmd, cwd=None, **kw):
        seen["cmd"] = cmd
        seen["cwd"] = cwd
        mc = cmd.index("--mcp-config")
        seen["mcp_config"] = cmd[mc + 1]
        return _Proc()

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    return seen


@pytest.fixture(autouse=True)
def _box_env(monkeypatch, tmp_path):
    monkeypatch.setenv("FSR_BASE_URL", "https://box.example.com:13000")
    monkeypatch.setenv("FSR_API_KEY", "x")
    exe = tmp_path / "fsr-agentic-toolkit"
    exe.write_text("#!/bin/sh\n")
    monkeypatch.setenv("FSR_TOOLKIT_EXE", str(exe))


def _assert_absolute(seen):
    assert Path(seen["cwd"]).is_absolute(), seen["cwd"]
    assert Path(seen["mcp_config"]).is_absolute(), seen["mcp_config"]
    # the config claude is pointed at must actually exist on disk
    assert Path(seen["mcp_config"]).exists(), seen["mcp_config"]


def test_drive_task_uses_absolute_mcp_config_from_relative_work(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    seen = _capture(monkeypatch, drive)
    drive.drive_task({"id": "t", "spec": "do"}, Path("relwork"))
    _assert_absolute(seen)


def test_drive_repair_uses_absolute_mcp_config_from_relative_work(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    seen = _capture(monkeypatch, drive_repair)
    drive_repair.drive_repair({"id": "t"}, {"yaml": "x: 1", "kind": "k"}, Path("relwork"))
    _assert_absolute(seen)
