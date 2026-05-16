"""why_did_playbook_fail — one-shot triage convenience tool (I19).

Chains list_recent_failed_runs → get_run_env → (optional decompile)
→ diagnose_yaml_against_pb_execution. Tests stub the underlying tools
so behavior is hermetic.
"""
from __future__ import annotations

import pytest

pytest.importorskip("mcp.server.fastmcp",
                    reason="mcp package not installed")

import mcp_server  # noqa: E402
import mcp_server.tools_jinja  # noqa: E402, F401
import mcp_server.tools_recipe  # noqa: E402, F401
import mcp_server.tools_triage  # noqa: E402, F401


YAML = """
collection: Triage Demo
playbooks:
  - name: pb
    steps:
      - id: trig
        type: start
        name: Trig
      - id: a
        type: set_variable
        name: First Step
        arguments:
          arg_list:
            x: "{{ vars.steps.Ghost.foo }}"
      - id: b
        type: end
        name: Done
"""


@pytest.fixture
def stub_chain(monkeypatch):
    """Stub triage + jinja so the chain runs hermetically."""

    def fake_get_run_env(pb_execution):
        return {
            "status": "failed", "name": "Triage Demo",
            "vars": {"steps": {}},
        }

    def fake_render_jinja(template, context=None, from_pb_execution=None):
        if "Ghost" in template:
            return {"output": ""}
        return {"output": template}

    monkeypatch.setattr(mcp_server.tools_triage, "get_run_env",
                        fake_get_run_env)
    monkeypatch.setattr(mcp_server.tools_jinja, "render_jinja",
                        fake_render_jinja)


def test_run_id_path_passes_yaml_through(stub_chain):
    out = mcp_server.why_did_playbook_fail("12345", yaml_text=YAML)
    assert out["pb_execution"] == "12345"
    assert out["run_status"] == "failed"
    assert out["summary"]["render_failures"] == 1
    assert any("Ghost" in h for h in out["hints"])


def test_uuid_treated_as_run_id(stub_chain):
    uuid = "abcdef12-3456-7890-abcd-ef1234567890"
    out = mcp_server.why_did_playbook_fail(uuid, yaml_text=YAML)
    assert out["pb_execution"] == uuid


def test_name_resolution_picks_most_recent_failed(stub_chain, monkeypatch):
    monkeypatch.setattr(
        mcp_server.tools_triage, "list_recent_failed_runs",
        lambda limit=20, playbook=None, **_:
            [{"task_id": "task-uuid-1", "name": playbook,
              "status": "failed", "modified": "2026-05-16",
              "error_message": "boom: KeyError"}],
    )
    out = mcp_server.why_did_playbook_fail("Triage Demo", yaml_text=YAML)
    assert out["pb_execution"] == "task-uuid-1"
    assert out["error_message"] == "boom: KeyError"
    assert out["matched_run"]["name"] == "Triage Demo"


def test_name_with_no_runs_returns_structured_error(monkeypatch):
    monkeypatch.setattr(
        mcp_server.tools_triage, "list_recent_failed_runs",
        lambda limit=20, playbook=None, **_: [],
    )
    out = mcp_server.why_did_playbook_fail("Nonexistent PB")
    assert out["ok"] is False
    assert out["code"] == "no_failed_runs"
    assert isinstance(out["suggestions"], list)


def test_list_runs_error_surfaces_structured(monkeypatch):
    monkeypatch.setattr(
        mcp_server.tools_triage, "list_recent_failed_runs",
        lambda limit=20, playbook=None, **_:
            [{"error": "FSR instance not configured"}],
    )
    out = mcp_server.why_did_playbook_fail("Whatever")
    assert out["ok"] is False
    assert out["code"] == "no_failed_runs"
    assert "FSR instance not configured" in out["message"]


def test_looks_like_run_id():
    from mcp_server.tools_recipe import _looks_like_run_id
    assert _looks_like_run_id("676747")
    assert _looks_like_run_id("abcdef12-3456-7890-abcd-ef1234567890")
    assert not _looks_like_run_id("Block Indicator")
    assert not _looks_like_run_id("pb-42")
