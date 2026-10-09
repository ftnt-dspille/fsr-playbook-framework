"""A raw catalog step type nobody uses, with no argument contract, is refused.

Analyst sim: asked to call the existing 'Block IP - Shared' playbook, the model
wrote `type: MapPlaybook` with `playbook:` and `parameters:`. MapPlaybook is a
real catalog row with zero uses in the library, so the compiler took it and
passed the guessed arguments through: it compiled, verified, staged and walked
clean, and called nothing.
"""
from __future__ import annotations

from fsr_playbooks._db import default_db_path
from fsr_playbooks.compiler import compile_yaml

_PB = """
collection: C
playbooks:
  - name: P
    steps:
      - {name: Start, type: start_on_create, module: alerts, next: Call}
      - name: Call
        type: __TYPE__
        __ARGS__
"""


def _compile(step_type: str, args: str):
    return compile_yaml(_PB.replace("__TYPE__", step_type).replace("__ARGS__", args),
                        default_db_path())


def test_map_playbook_is_refused_and_points_at_workflow_reference():
    res = _compile("MapPlaybook", "playbook: Block IP - Shared")
    assert not res.ok
    err = next(e for e in res.errors if e.code.value == "unknown_step_type")
    assert "workflow_reference" in err.message


def test_a_raw_name_the_library_uses_still_compiles():
    # CyopsUtilites has no short alias but 491 library uses: not a guess.
    res = _compile("CyopsUtilites", "connector: cyops_utilities\n        operation: no_op\n        params: {}")
    assert not [e for e in res.errors if e.code.value == "unknown_step_type"], res.errors


def test_the_documented_type_compiles():
    res = compile_yaml("""
collection: C
playbooks:
  - name: Child
    parameters: [ip]
    steps:
      - {name: Start, type: start, next: Note}
      - {name: Note, type: set_variable, vars: {ip: "{{ vars.input.params.ip }}"}}
  - name: P
    steps:
      - {name: Start, type: start_on_create, module: alerts, next: Call}
      - {name: Call, type: workflow_reference, target: Child, ip: "{{ vars.input.records[0].sourceIp }}"}
""", default_db_path())
    assert res.ok, [e.message for e in res.errors]
