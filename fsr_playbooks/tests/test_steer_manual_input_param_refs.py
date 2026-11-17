"""Steer `vars.input.params.<name>` to the manual_input step that collects it.

The model commonly reads an analyst-entered value off the trigger params bag
(`vars.input.params.ip_address`) when the value is really collected by a
manual_input step and lives at `vars.steps.<step>.input.<name>`. When the name
is NOT a declared playbook parameter but EXACTLY ONE manual_input step declares
an input field of that name, the right target is derivable -- the compiler
steers the reference there with a warning instead of erroring. Ambiguous or
unmatched names still error (no silent guess).
"""
from __future__ import annotations

from fsr_playbooks._db import PACKAGED_SLIM_DB
from fsr_playbooks.compiler import compile_yaml


def _run(yaml_text: str):
    res = compile_yaml(yaml_text, PACKAGED_SLIM_DB)
    errs = [e.message for e in res.errors if e.severity != "warning"]
    warns = [e.message for e in res.warnings]
    return res, errs, warns


_MI = """collection: C
playbooks:
  - name: P
    steps:
      - {name: Start, type: start, next: Ask}
      - type: manual_input
        name: Ask
        next: Use
        inputs:
          - {name: ip_address, kind: ipv4, label: IP, required: true}
      - name: Use
        type: set_variable
        vars: {note: "blocking {{ vars.input.params.ip_address }}"}
"""


def test_wrong_ref_is_steered_to_the_manual_input_step():
    res, errs, warns = _run(_MI)
    assert res.ok, errs                       # no longer an undeclared-param error
    assert not any("not declared" in e for e in errs)
    assert any("steered to `vars.steps.Ask.input.ip_address`" in w for w in warns), warns


def test_ambiguous_field_is_not_steered_and_still_errors():
    # Two manual_input steps collect the same field -> the target is not
    # derivable, so no steer and the undeclared-param error stands.
    y = """collection: C
playbooks:
  - name: P
    steps:
      - {name: Start, type: start, next: AskA}
      - type: manual_input
        name: AskA
        next: AskB
        inputs: [{name: ip_address, kind: ipv4, label: IP}]
      - type: manual_input
        name: AskB
        next: Use
        inputs: [{name: ip_address, kind: ipv4, label: IP}]
      - name: Use
        type: set_variable
        vars: {note: "{{ vars.input.params.ip_address }}"}
"""
    res, errs, warns = _run(y)
    assert not res.ok
    assert any("not declared" in e for e in errs)
    assert not any("steered" in w for w in warns)


def test_declared_playbook_param_is_left_alone():
    # A name that really IS a declared playbook parameter must not be hijacked.
    y = """collection: C
playbooks:
  - name: P
    parameters: [ip_address]
    steps:
      - {name: Start, type: start, next: Use}
      - name: Use
        type: set_variable
        vars: {note: "{{ vars.input.params.ip_address }}"}
"""
    res, errs, warns = _run(y)
    assert res.ok, errs
    assert not any("steered" in w for w in warns)


def test_unmatched_undeclared_param_still_errors():
    # A params ref matching neither a declared parameter nor any manual_input
    # field stays a hard error -- nothing to steer to.
    y = """collection: C
playbooks:
  - name: P
    steps:
      - {name: Start, type: start, next: Use}
      - name: Use
        type: set_variable
        vars: {note: "{{ vars.input.params.mystery }}"}
"""
    res, errs, warns = _run(y)
    assert not res.ok
    assert any("not declared" in e and "mystery" in e for e in errs)
