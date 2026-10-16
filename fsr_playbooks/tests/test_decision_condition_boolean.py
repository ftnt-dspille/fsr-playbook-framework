"""A decision branch condition must be a boolean expression.

Live (FortiAI build, 1 of 6): the fall-through branch came out as
``{option: default, condition: else}``. It is not a ``default: true`` branch,
so the coherence check saw an option and a condition and passed it -- but the
VALUE ``else`` is a bare literal, and FSR rejected it at RUNTIME:
``Condition: "else" is not boolean, it is a <class 'str'>``. Verify must catch
that, not the live run. A real branch condition always carries a comparison or
a Jinja block (the other 5 builds wrote ``finalDisposition != 'block'``, which
works).
"""
from __future__ import annotations

from fsr_playbooks.compiler import compile_yaml
from fsr_playbooks.mcp_server._shared import DB_PATH


def _yaml(block_cond: str, allow_cond: str) -> str:
    return f"""collection: C
playbooks:
- name: P
  steps:
  - {{name: Start, type: start, module: alerts, next: Route}}
  - name: Route
    type: decision
    conditions:
    - {{display: Block, when: "{block_cond}", next: Blocked}}
    - {{display: Allow, when: "{allow_cond}", next: Allowed}}
  - {{name: Blocked, type: set_variable, vars: {{x: "1"}}, next: End}}
  - {{name: Allowed, type: set_variable, vars: {{y: "2"}}, next: End}}
  - {{name: End, type: end}}
"""


def _errors(y: str):
    res = compile_yaml(y, DB_PATH)
    return [e for e in (res.errors or []) if e.severity == "error"]


def test_a_bare_else_condition_is_rejected_with_a_default_hint():
    errs = _errors(_yaml("{{ vars.steps.Route.finalDisposition == 'block' }}", "else"))
    msgs = " ".join(e.message for e in errs)
    assert errs, "condition: else must be a verify-time error, not a runtime crash"
    assert "not a boolean" in msgs and "default: true" in msgs, msgs


def test_otherwise_and_bare_default_are_rejected_too():
    for word in ("otherwise", "default", "any"):
        errs = _errors(_yaml("{{ vars.steps.Route.verdict == 'bad' }}", word))
        assert errs, f"condition: {word} should be rejected"


def test_a_real_operator_condition_passes():
    # The shape the other 5 builds used: a bare comparison, no Jinja braces.
    errs = _errors(_yaml("finalDisposition == 'block'", "finalDisposition != 'block'"))
    cond_errs = [e for e in errs if "boolean expression" in e.message]
    assert not cond_errs, [e.to_dict() for e in cond_errs]


def test_a_jinja_block_condition_passes():
    errs = _errors(_yaml(
        "{{ vars.steps.Route.finalDisposition == 'block' }}",
        "{{ vars.steps.Route.finalDisposition != 'block' }}"))
    cond_errs = [e for e in errs if "boolean expression" in e.message]
    assert not cond_errs, [e.to_dict() for e in cond_errs]
