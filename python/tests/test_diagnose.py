"""diagnose_yaml_against_pb_execution — closes the failure-recovery loop.

Tests stub out get_run_env + render_jinja so the behavior is hermetic:
no real FSR is needed. We're verifying the YAML walker, the
vars.steps.<key> reachability hint, and the structured envelope.
"""
from __future__ import annotations

import pytest

pytest.importorskip("mcp.server.fastmcp",
                    reason="mcp package not installed")

import fsr_playbooks.mcp_server as mcp_server  # noqa: E402
import fsr_playbooks.mcp_server.tools_jinja  # noqa: E402, F401
import fsr_playbooks.mcp_server.tools_triage  # noqa: E402, F401


YAML_REFERENCING_STEP = """
collection: Diag Demo
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
            x: "{{ vars.steps.Missing_Step.foo }}"
      - id: b
        type: set_variable
        name: Second Step
        arguments:
          arg_list:
            y: "literal {{ vars.steps.First_Step.value }}"
      - id: c
        type: end
        name: Done
"""


@pytest.fixture
def patched(monkeypatch):
    """Stub get_run_env + render_jinja deterministically."""

    def fake_get_run_env(pb_execution):
        return {
            "status": "failed",
            "name": "Diag Demo",
            "vars": {
                "steps": {
                    "First_Step": {"value": "abc"},
                },
            },
        }

    def fake_render_jinja(template, context=None, from_pb_execution=None):
        # Emulate: any reference to Missing_Step renders empty;
        # references to First_Step render the literal "abc".
        if "Missing_Step" in template:
            return {"output": ""}
        if "First_Step" in template:
            return {"output": "literal abc"}
        return {"output": template}

    monkeypatch.setattr(mcp_server.tools_triage, "get_run_env", fake_get_run_env)
    monkeypatch.setattr(mcp_server.tools_jinja, "render_jinja", fake_render_jinja)


def test_diagnose_collects_template_rows(patched):
    out = mcp_server.diagnose_yaml_against_pb_execution(
        YAML_REFERENCING_STEP, "12345",
    )
    assert out["pb_execution"] == "12345"
    assert out["run_status"] == "failed"
    diags = out["step_diagnostics"]
    paths = {(d["step"], d["arg_path"]) for d in diags}
    assert ("First Step", "arg_list.x") in paths
    assert ("Second Step", "arg_list.y") in paths


def test_diagnose_flags_missing_step_via_hint(patched):
    out = mcp_server.diagnose_yaml_against_pb_execution(
        YAML_REFERENCING_STEP, "12345",
    )
    hints = " ".join(out["hints"])
    assert "Missing_Step" in hints
    assert "First_Step" in hints  # listed as available


def test_diagnose_marks_empty_render_as_failure(patched):
    out = mcp_server.diagnose_yaml_against_pb_execution(
        YAML_REFERENCING_STEP, "12345",
    )
    by_path = {d["arg_path"]: d for d in out["step_diagnostics"]}
    assert by_path["arg_list.x"]["code"] == "empty_render"
    assert by_path["arg_list.y"]["code"] == "ok"
    assert out["summary"]["render_failures"] == 1


def test_diagnose_run_env_unavailable_envelope(monkeypatch):
    monkeypatch.setattr(
        mcp_server.tools_triage, "get_run_env",
        lambda pk: {"error": "no such workflow"},
    )
    out = mcp_server.diagnose_yaml_against_pb_execution(
        "playbooks: []", "999",
    )
    assert out["ok"] is False
    assert out["code"] == "run_env_unavailable"
    assert isinstance(out["suggestions"], list)


def test_diagnose_yaml_parse_error(monkeypatch):
    monkeypatch.setattr(
        mcp_server.tools_triage, "get_run_env",
        lambda pk: {"status": "finished", "vars": {"steps": {}}},
    )
    out = mcp_server.diagnose_yaml_against_pb_execution(
        "this: is\n  not: [valid: yaml", "1",
    )
    assert out["ok"] is False
    assert out["code"] == "yaml_parse_failed"
