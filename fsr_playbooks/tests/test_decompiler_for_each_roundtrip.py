"""The decompiler must emit `for_each:` — dropping it is silent data loss.

Found by mounting real playbooks pulled from a live appliance as offline
fixtures: two of them looped (`for_each.item`), and the YAML that came back
had no loop in it at all. `for_each` lives inside `arguments:` on the wire and
the IR build lifts it out, but the emitter never put it back, so the loop was
lifted into a field nothing read.

Why this class matters more than a normal fidelity gap: the widget saves the
agent's LAST ```yaml fence back OVER the open record. So a pull -> ask the
agent for one small edit -> push of a looping playbook silently rewrites
"run this for every open incident" into "run it once, on nothing" — no error,
no diff the analyst would notice, and a control-flow change is not something
they would think to re-check after a one-field edit.
"""
from __future__ import annotations

import yaml

from fsr_playbooks._db import PACKAGED_SLIM_DB
from fsr_playbooks.compiler import compile_yaml
from fsr_playbooks.compiler.decompiler import decompile_to_yaml

_LOOPING = """
collection: T
playbooks:
  - name: PB
    steps:
      - name: Start
        type: start_on_create
        module: incidents
        next: Find Open
      - name: Find Open
        type: find_record
        module: incidents
        arguments:
          query:
            logic: AND
            filters: []
        next: Escalate Each
      - name: Escalate Each
        type: set_variable
        for_each:
          item: "{{ vars.steps.Find_Open }}"
          parallel: false
          condition: "{{ vars.item.severity != 'Low' }}"
        vars:
          sev: "{{ vars.item.severity }}"
"""


def _roundtrip(yaml_text: str) -> dict:
    res = compile_yaml(yaml_text, PACKAGED_SLIM_DB)
    assert res.ok, [e.message for e in res.errors if e.severity != "warning"]
    doc = yaml.safe_load(decompile_to_yaml(res.fsr_json, PACKAGED_SLIM_DB))
    return {s["name"]: s for s in doc["playbooks"][0]["steps"]}


def test_for_each_survives_a_round_trip():
    """The behavioural bar: a loop that went in comes back out."""
    step = _roundtrip(_LOOPING)["Escalate Each"]
    assert "for_each" in step, (
        "for_each was DROPPED — pull->edit->push would delete the loop and "
        "turn a per-record playbook into a single-shot one"
    )
    assert step["for_each"]["item"] == "{{ vars.steps.Find_Open }}"


def test_for_each_options_are_not_lossy():
    """`parallel` / `condition` change what the loop DOES, so a partial
    round-trip is its own defect — a loop that comes back without its guard
    condition runs on records it was written to skip."""
    fe = _roundtrip(_LOOPING)["Escalate Each"]["for_each"]
    assert fe.get("parallel") is False
    assert fe.get("condition") == "{{ vars.item.severity != 'Low' }}"


def test_for_each_is_emitted_at_step_level_not_buried_in_arguments():
    """The parser reads `for_each:` from the step surface. Emitting it back
    inside `arguments:` would look lossless in a dict diff and still fail to
    recompile as a loop."""
    step = _roundtrip(_LOOPING)["Escalate Each"]
    assert "for_each" not in (step.get("arguments") or {})


def test_recompiles_to_the_same_wire_for_each():
    """End-to-end: the decompiled YAML compiles back to a step whose wire
    `arguments.for_each` matches the original. This is the assertion that
    actually protects the analyst's playbook."""
    first = compile_yaml(_LOOPING, PACKAGED_SLIM_DB)
    again = compile_yaml(
        decompile_to_yaml(first.fsr_json, PACKAGED_SLIM_DB), PACKAGED_SLIM_DB)
    assert again.ok, [e.message for e in again.errors if e.severity != "warning"]

    def _fe(payload):
        steps = payload["data"][0]["workflows"][0]["steps"]
        hit = [s for s in steps if (s.get("arguments") or {}).get("for_each")]
        assert len(hit) == 1, f"expected exactly one looping step, got {len(hit)}"
        return hit[0]["arguments"]["for_each"]

    assert _fe(again.fsr_json) == _fe(first.fsr_json)


def test_non_looping_steps_do_not_grow_a_for_each_key():
    """No-regression guard: the fix must not stamp an empty `for_each:` onto
    every step — noise in the YAML the agent reads is its own cost."""
    by_name = _roundtrip(_LOOPING)
    assert "for_each" not in by_name["Find Open"]
    assert "for_each" not in by_name["Start"]
