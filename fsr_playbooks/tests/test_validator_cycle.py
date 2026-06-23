"""§2.6 — cycle detection before _compute_predecessors.

Verifies that:
  1. _has_cycle correctly identifies cyclic and acyclic playbooks.
  2. A playbook with a cycle gets a cycle error but NO spurious
     'step not reachable' / predecessor errors from _check_jinja_paths.
"""
from fsr_playbooks._db import default_db_path
from fsr_playbooks.compiler import compile_yaml
from fsr_playbooks.compiler.validator import _has_cycle
from fsr_playbooks.compiler.ir import Playbook, Step


# ---------------------------------------------------------------------------
# _has_cycle unit tests
# ---------------------------------------------------------------------------

def _pb(*steps_dicts) -> Playbook:
    steps = [Step(**d) for d in steps_dicts]
    return Playbook(name="p", steps=steps)


def test_has_cycle_simple_loop():
    pb = _pb(
        {"id": "a", "type": "start", "name": "A", "next": "b"},
        {"id": "b", "type": "set_variable", "name": "B", "next": "a"},  # back-edge to a
    )
    assert _has_cycle(pb) is True


def test_has_cycle_self_loop():
    pb = _pb(
        {"id": "a", "type": "start", "name": "A", "next": "a"},
    )
    assert _has_cycle(pb) is True


def test_has_cycle_acyclic():
    pb = _pb(
        {"id": "a", "type": "start", "name": "A", "next": "b"},
        {"id": "b", "type": "set_variable", "name": "B", "next": "c"},
        {"id": "c", "type": "set_variable", "name": "C"},
    )
    assert _has_cycle(pb) is False


def test_has_cycle_empty():
    pb = _pb()
    assert _has_cycle(pb) is False


# ---------------------------------------------------------------------------
# Integration: cycle error surfaced, no spurious predecessor errors
# ---------------------------------------------------------------------------

_CYCLIC_YAML = """
collection: test_cycle
playbooks:
  - name: Cyclic
    steps:
      - name: Start
        type: start
        next: StepA
      - name: StepA
        type: set_variable
        vars:
          x: "{{ vars.steps.StepB.x }}"
        next: StepB
      - name: StepB
        type: set_variable
        vars:
          y: "1"
        next: StepA
"""

# Resolve via the standard order so CI falls back to the packaged slim DB.
DB = default_db_path()


def test_cycle_error_reported():
    res = compile_yaml(_CYCLIC_YAML, DB)
    messages = [e.message for e in res.errors]
    assert any("cycle" in m.lower() for m in messages), (
        f"expected a cycle error, got: {messages}"
    )


def test_no_spurious_predecessor_error_on_cycle():
    """With a cycle, _check_jinja_paths short-circuits. StepA references StepB
    which is technically a 'forward' reference in the cyclic graph — without
    the guard we'd get a BAD_VALUE reachability error even though this is
    exactly the kind of 'works at runtime' pattern FSR supports in loops."""
    res = compile_yaml(_CYCLIC_YAML, DB)
    predecessor_errors = [
        e for e in res.errors
        if "not reachable" in e.message or "predecessor" in e.message.lower()
    ]
    assert predecessor_errors == [], (
        f"spurious predecessor errors on cyclic graph: {predecessor_errors}"
    )
