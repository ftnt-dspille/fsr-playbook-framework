"""Self-teaching diagnostics (PLAYBOOK_AUTHORING_DX_PLAN 0b).

A compile error on a high-foot-gun step type (manual_input / workflow_reference)
carries a minimal *compiling* example in its suggestion, so the fix travels on
the error channel.
"""
import textwrap

from fsr_playbooks._db import default_db_path
from fsr_playbooks.compiler import compile_yaml
from fsr_playbooks.compiler.teaching import _TEACHING

DB = default_db_path()


def test_workflow_reference_error_carries_example():
    y = """
collection: C
playbooks:
- name: P
  is_active: true
  steps:
  - {name: Start, type: start, next: Call}
  - {name: Call, type: workflow_reference, arguments: {}}
"""
    r = compile_yaml(y, DB)
    assert not r.ok
    err = next(e for e in r.errors if e.code.value == "missing_field")
    assert err.suggestion and "example (workflow_reference)" in err.suggestion
    assert "target:" in err.suggestion


def test_non_footgun_error_is_not_enriched():
    # An unknown connector error on a connector step gets no teaching block.
    y = """
collection: C
playbooks:
- name: P
  is_active: true
  steps:
  - {name: Start, type: start, next: Do}
  - {name: Do, type: connector, connector: no_such_connector_xyz, operation: nope}
"""
    r = compile_yaml(y, DB)
    assert not r.ok
    assert all("example (" not in (e.suggestion or "") for e in r.errors)


def test_embedded_examples_compile():
    # Every teaching example must compile inside a minimal playbook, so the
    # diagnostics can't teach a shape that doesn't work. The examples end with
    # illustrative `next:`/`target:` pointers to steps/playbooks outside the
    # snippet; the scaffolding below drops the trailing `next:` (making the step
    # terminal) and stubs any referenced `target:` child playbook.
    for stype, example in _TEACHING.items():
        lines = [ln for ln in example.splitlines() if ln.startswith("    ")]
        block = textwrap.dedent("\n".join(lines))
        kept, target = [], None
        for ln in block.splitlines():
            s = ln.strip()
            if s.startswith("next:"):
                continue
            if s.startswith("target:"):
                target = s.split(":", 1)[1].strip()
            kept.append(ln)
        block = "\n".join(kept)
        first = _first_step_name(block)

        playbooks = (
            "- name: P\n  is_active: true\n  steps:\n"
            f"  - {{name: Start, type: start, next: {first}}}\n"
            + textwrap.indent(block, "  ")
            + "\n"
        )
        if target:
            playbooks += (
                f"- name: {target}\n  is_active: true\n  steps:\n"
                "  - {name: Start, type: start}\n"
            )
        y = f"collection: T\nplaybooks:\n{playbooks}"
        r = compile_yaml(y, DB)
        blocking = [e.message for e in r.errors if e.severity != "warning"]
        assert r.ok, f"teaching example for {stype} does not compile: {blocking}\n{y}"


def _first_step_name(block: str) -> str:
    for line in block.splitlines():
        s = line.strip()
        if s.startswith("- name:"):
            return s.split(":", 1)[1].strip()
    return "Start"
