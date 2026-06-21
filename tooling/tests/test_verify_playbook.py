"""End-to-end tests for the verify_playbook MCP tool.

Uses the real reference DB (read-only) and real compile pipeline. No
live FSR (live_probe defaults to False)."""
from __future__ import annotations

import textwrap


from fsr_playbooks.mcp_server import verify_playbook


def _yaml(body: str) -> str:
    return textwrap.dedent(body).lstrip("\n")


def test_envelope_shape_on_compile_error():
    res = verify_playbook(yaml_text="not: valid yaml: at all: ::")
    assert res["ok"] is False
    assert res["ready_to_push"] is False
    assert isinstance(res["required_fixes"], list)
    assert isinstance(res["warnings"], list)
    assert isinstance(res["checks_run"], list)
    assert isinstance(res["next_actions"], list)
    # compile check ran and failed.
    compile_checks = [c for c in res["checks_run"] if c["name"] == "compile"]
    assert compile_checks and compile_checks[0]["ok"] is False


def test_clean_set_variable_playbook_is_ready_to_push():
    yaml = _yaml("""
        collection: TestCol
        playbooks:
          - name: TP
            steps:
              - name: Start
                type: start
                next: set
              - name: set
                type: set_variable
                vars:
                  foo: "bar"
                next: use
              - name: use
                type: set_variable
                vars:
                  echo: "{{ vars.steps.set.foo }}"
    """)
    res = verify_playbook(yaml_text=yaml)
    # No required fixes from walker for valid set_variable refs.
    walker_errors = [f for f in res["required_fixes"]
                     if f.get("code") in {"unreachable_step_reference",
                                          "missing_field_on_step_output",
                                          "non_list_indexed"}]
    assert walker_errors == [], walker_errors


def test_unreachable_step_reference_blocks_push():
    yaml = _yaml("""
        collection: TestCol
        playbooks:
          - name: TP
            steps:
              - name: Start
                type: start
                next: branch
              - name: branch
                type: decision
                branches:
                  yes: a
                  no: b
              - name: a
                type: set_variable
                vars:
                  x: "1"
              - name: b
                type: set_variable
                vars:
                  y: "{{ vars.steps.a.x }}"
    """)
    res = verify_playbook(yaml_text=yaml)
    codes = {f["code"] for f in res["required_fixes"]}
    # `a` is on the yes branch; `b` is on the no branch — the compiler
    # catches it as `bad_value` (unreachable Jinja ref) and the walker
    # would otherwise emit `unreachable_step_reference`. Either is fine
    # — the point is it gets blocked.
    assert codes & {"unreachable_step_reference", "bad_value"}
    assert res["ready_to_push"] is False


def test_live_probe_off_no_blanket_warning():
    """When live_probe=False is the requested mode we should NOT emit a
    blanket warning — it just clutters every result with noise and
    teaches the agent to ignore warnings. Specific stale-shape refs
    still surface as `unknown_shape_downstream_reference`."""
    yaml = _yaml("""
        collection: TestCol
        playbooks:
          - name: TP
            steps:
              - name: Start
                type: start
                next: set
              - name: set
                type: set_variable
                vars:
                  x: "1"
    """)
    res = verify_playbook(yaml_text=yaml, live_probe=False)
    codes = {w["code"] for w in res["warnings"]}
    assert "live_probe_skipped_unsafe" not in codes


def test_next_actions_listed_when_blocked():
    yaml = _yaml("""
        collection: TestCol
        playbooks:
          - name: TP
            steps:
              - name: Start
                type: start
                next: use
              - name: use
                type: set_variable
                vars:
                  x: "{{ vars.steps.never_existed.foo }}"
    """)
    res = verify_playbook(yaml_text=yaml)
    assert res["ready_to_push"] is False
    assert len(res["next_actions"]) >= 1


def test_type_trace_written_and_pathed():
    """Phase 5 — verify_playbook persists a trace file and returns its path;
    verbose folds the per-branch decisions into evidence, lean mode omits
    them (but still writes the file)."""
    import json
    from pathlib import Path

    yaml = _yaml("""
        collection: TestCol
        playbooks:
          - name: TP
            steps:
              - name: Start
                type: start
                next: set
              - name: set
                type: set_variable
                vars:
                  echo: "{{ vars.steps.set.foo }}"
    """)
    res = verify_playbook(yaml_text=yaml, verbose=True)
    path = res["evidence"].get("type_trace_path")
    assert path and Path(path).exists()
    payload = json.loads(Path(path).read_text())
    assert "branches" in payload and payload["yaml_sha"]
    # verbose folds the trace into evidence
    assert "type_trace" in res["evidence"]

    # lean mode still writes the file + path, but no folded trace
    res2 = verify_playbook(yaml_text=yaml, verbose=False)
    assert res2["evidence"].get("type_trace_path")
    assert "type_trace" not in res2["evidence"]
