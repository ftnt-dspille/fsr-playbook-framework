"""Conformance of the compiler's emitted JSON against the editor-derived
wire-shape oracle (docs/STEP_WIRE_SHAPES.json).

Two layers:

* ``_clean_step_arguments`` is a pure function mirroring the editor's save-time
  cleanup (empty-field deletion + for_each loop-mode normalization). We unit-test
  it directly — it needs no reference DB and pins every documented rule.
* End-to-end: compile a minimal fixture per step type and assert the emitted
  top-level argument keys are a subset of what the oracle documents for that type
  (editor-only/UI-state keys excluded). The slim reference DB ships no connector
  metadata, so connector/code_snippet steps can't resolve offline — those rules
  are covered by the unit layer instead.
"""
from __future__ import annotations

import pytest

from fsr_playbooks.compiler import compile_yaml
from fsr_playbooks.compiler.emitter import _clean_step_arguments
from fsr_playbooks._db import PACKAGED_SLIM_DB
from fsr_playbooks.tests.wire_shape_oracle import (
    load_oracle,
    normalize_emitted_keys,
)

ORACLE = load_oracle()


# --------------------------------------------------------------------------
# Layer 1 — _clean_step_arguments (editor save-time cleanup), pure unit tests
# --------------------------------------------------------------------------

def _clean(args):
    a = dict(args)
    _clean_step_arguments(a)
    return a


@pytest.mark.parametrize("key,val", [
    ("when", ""),
    ("mock_result", ""),
])
def test_empty_scalar_envelope_keys_deleted(key, val):
    assert key not in _clean({key: val, "operation": "x"})


def test_nonempty_when_preserved():
    assert _clean({"when": "{{ vars.x }}"})["when"] == "{{ vars.x }}"


def test_do_until_deleted_when_condition_empty():
    assert "do_until" not in _clean({"do_until": {"condition": "", "retries": 3}})


def test_do_until_preserved_when_condition_set():
    out = _clean({"do_until": {"condition": "{{ x }}", "retries": 3}})
    assert out["do_until"]["retries"] == 3


def test_message_deleted_when_content_empty():
    assert "message" not in _clean({"message": {"content": "", "records": []}})


def test_for_each_deleted_when_item_empty():
    assert "for_each" not in _clean({"for_each": {"item": "", "condition": "true"}})


def test_for_each_bulk_deletes_parallel_and_defaults_batch_size():
    out = _clean({"for_each": {"item": "{{ vars.l }}", "__bulk": True, "parallel": False}})
    fe = out["for_each"]
    assert "parallel" not in fe          # mutually exclusive with __bulk
    assert fe["batch_size"] == 100       # editor default


def test_for_each_bulk_keeps_explicit_batch_size():
    out = _clean({"for_each": {"item": "{{ vars.l }}", "__bulk": True, "batch_size": 25}})
    assert out["for_each"]["batch_size"] == 25


def test_for_each_sequential_drops_batch_size():
    out = _clean({"for_each": {"item": "{{ vars.l }}", "parallel": False, "batch_size": 50}})
    assert "batch_size" not in out["for_each"]


def test_for_each_parallel_drops_batch_size():
    out = _clean({"for_each": {"item": "{{ vars.l }}", "parallel": True, "batch_size": 50}})
    assert "batch_size" not in out["for_each"]


def test_break_loop_deleted_when_apply_async():
    out = _clean({"apply_async": True,
                  "for_each": {"item": "{{ x }}", "break_loop": "{{ stop }}"}})
    assert "break_loop" not in out["for_each"]


def test_break_loop_deleted_when_agent_set():
    out = _clean({"agent": "lab-collector",
                  "for_each": {"item": "{{ x }}", "break_loop": "{{ stop }}"}})
    assert "break_loop" not in out["for_each"]


def test_break_loop_preserved_without_async_or_agent():
    out = _clean({"for_each": {"item": "{{ x }}", "break_loop": "{{ stop }}"}})
    assert out["for_each"]["break_loop"] == "{{ stop }}"


# --------------------------------------------------------------------------
# Layer 2 — emitted argument keys ⊆ oracle documented keys, per step type
# --------------------------------------------------------------------------

def _emitted_steps(yaml_text: str):
    """Compile and yield (name, stepType_iri, arguments) for every WorkflowStep."""
    res = compile_yaml(yaml_text, PACKAGED_SLIM_DB)
    assert res.ok, f"fixture failed to compile: {[str(e.code)+':'+e.message for e in res.errors if e.severity!='warning']}"
    out = []

    def walk(o):
        if isinstance(o, dict):
            if o.get("@type") == "WorkflowStep":
                out.append((o.get("name"), o.get("stepType"), o.get("arguments") or {}))
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(res.fsr_json)
    return out


# Conformance registry — ONE entry per oracle step type (all 21). Each entry is
# one of:
#   ("check", target_step_name, yaml)  → compile and assert emitted argument keys
#                                         ⊆ the oracle's documented keys.
#   ("live",  reason)                  → resolvable only against live connector
#                                         metadata the slim test DB doesn't ship;
#                                         the wire rules are pinned at the unit
#                                         layer above instead. Reported as skips.
#   ("gap",   reason)                  → a Phase-2 coverage gap (no friendly short
#                                         type yet). Reported as xfails — the
#                                         punch-list the plan asked for.
#
# A meta-test below asserts this registry covers every oracle type, so a new
# step type can never be added to the oracle without a conformance decision.
FIXTURES: dict[str, tuple] = {
    "Decision": ("check", "Route", """
collection: c
playbooks:
  - name: P
    steps:
      - {name: Start, type: start}
      - name: Route
        type: decision
        conditions:
          - {when: "{{ vars.x }}", display: "Hi", next: A}
        next: A
      - {name: A, type: set_variable, vars: {y: 1}}
"""),
    "ManualInput": ("check", "Ask", """
collection: c
playbooks:
  - name: P
    steps:
      - {name: Start, type: start}
      - name: Ask
        type: manual_input
        arguments: {title: "Approve?", description: ok}
        options:
          - {display: Yes, next: A}
      - {name: A, type: set_variable, vars: {y: 1}}
"""),
    "FindRecords": ("check", "Find", """
collection: c
playbooks:
  - name: P
    steps:
      - {name: Start, type: start}
      - name: Find
        type: find_record
        arguments:
          module: alerts
          query: {logic: AND, filters: [], sort: [], limit: 30}
"""),
    "Delay": ("check", "Wait", """
collection: c
playbooks:
  - name: P
    steps:
      - {name: Start, type: start}
      - {name: Wait, type: delay, seconds: 30}
"""),
    "UpdateRecord": ("check", "Upd", """
collection: c
playbooks:
  - name: P
    steps:
      - {name: Start, type: start}
      - name: Upd
        type: update_record
        arguments:
          module: incidents
          resource: {status: Closed}
"""),
    "InsertData": ("check", "New", """
collection: c
playbooks:
  - name: P
    steps:
      - {name: Start, type: start}
      - name: New
        type: create_record
        arguments:
          module: alerts
          resource: {name: a}
"""),
    "cybersponse.post_create": ("check", "Trig", """
collection: c
playbooks:
  - name: P
    steps:
      - {name: Trig, type: start_on_create, module: alerts}
      - {name: A, type: set_variable, vars: {y: 1}}
"""),
    "cybersponse.post_update": ("check", "Trig", """
collection: c
playbooks:
  - name: P
    steps:
      - {name: Trig, type: start_on_update, module: alerts}
      - {name: A, type: set_variable, vars: {y: 1}}
"""),
    "cybersponse.action": ("check", "Trig", """
collection: c
playbooks:
  - name: P
    steps:
      - {name: Trig, type: start, module: alerts}
      - {name: A, type: set_variable, vars: {y: 1}}
"""),
    "cybersponse.abstract_trigger": ("check", "Trig", """
collection: c
playbooks:
  - name: P
    steps:
      - {name: Trig, type: start}
      - {name: A, type: set_variable, vars: {y: 1}}
"""),
    "cybersponse.api_call": ("check", "Trig", """
collection: c
playbooks:
  - name: P
    steps:
      - {name: Trig, type: api_endpoint, arguments: {route: /x}}
      - {name: A, type: set_variable, vars: {y: 1}}
"""),
    "SetVariable": ("check", "SV", """
collection: c
playbooks:
  - name: P
    steps:
      - {name: Start, type: start, next: SV}
      - {name: SV, type: set_variable, vars: {score: 5}}
"""),
    "WorkflowReference": ("check", "Ref", """
collection: c
playbooks:
  - name: Target
    steps:
      - {name: Start, type: start}
  - name: P
    steps:
      - {name: Start, type: start, next: Ref}
      - {name: Ref, type: workflow_reference, arguments: {target: "Target"}}
"""),
    "IngestBulkFeed": ("check", "Ing", """
collection: c
playbooks:
  - name: P
    steps:
      - {name: Start, type: start, next: Ing}
      - name: Ing
        type: ingest_bulk_feed
        arguments: {collection: indicators, resource: {value: "{{ vars.x }}"}}
"""),
    "CodeSnippet": ("check", "Run", """
collection: c
playbooks:
  - name: P
    steps:
      - {name: Start, type: start, next: Run}
      - {name: Run, type: code_snippet, arguments: {code: "print(1)"}}
"""),
    # Resolvable only against live connector metadata (slim DB ships none) —
    # the wire rules for these are pinned at the unit layer above.
    "Connectors": ("live", "needs connector/op metadata absent from the slim DB"),
    "CyopsUtilites": ("live", "end/no_op resolves the cyops_utilities connector, "
                              "absent from the slim DB"),
    # Phase-2 coverage (short type + normalizer landed).
    "SendEmail": ("check", "Mail", """
collection: c
playbooks:
  - name: P
    steps:
      - {name: Start, type: start, next: Mail}
      - name: Mail
        type: send_email
        arguments:
          to: ["soc@example.com"]
          subject: "Alert {{ vars.id }}"
          body: "An alert fired."
"""),
    "ManualTask": ("check", "Task", """
collection: c
playbooks:
  - name: P
    steps:
      - {name: Start, type: start, next: Task}
      - name: Task
        type: create_task
        arguments:
          resource: {name: "Investigate {{ vars.id }}"}
"""),
    "SetAPIKeys": ("check", "Keys", """
collection: c
playbooks:
  - name: P
    steps:
      - {name: Start, type: start, next: Keys}
      - name: Keys
        type: set_api_keys
        arguments: {public_key: "{{ vars.pub }}", private_key: "{{ vars.priv }}"}
"""),
    "Approval": ("check", "Approve", """
collection: c
playbooks:
  - name: P
    steps:
      - {name: Start, type: start, next: Approve}
      - name: Approve
        type: approval
        arguments:
          resource:
            assignedTo: "/api/3/people/abc"
            approvaldescription: "Please approve containment."
"""),
}


def test_registry_covers_every_oracle_type():
    """No oracle step type may exist without an explicit conformance decision."""
    missing = set(ORACLE) - set(FIXTURES)
    assert not missing, f"oracle types with no conformance registry entry: {sorted(missing)}"
    extra = set(FIXTURES) - set(ORACLE)
    assert not extra, f"registry entries with no matching oracle type: {sorted(extra)}"


@pytest.mark.parametrize("canonical", sorted(FIXTURES), ids=sorted(FIXTURES))
def test_emitted_keys_subset_of_oracle(canonical):
    entry = FIXTURES[canonical]
    kind = entry[0]
    if kind == "live":
        pytest.skip(entry[1])
    if kind == "gap":
        pytest.xfail(entry[1])
    _, step_name, yaml_text = entry
    shape = ORACLE[canonical]
    documented = set(shape.all_keys)
    steps = {n: args for (n, _iri, args) in _emitted_steps(yaml_text)}
    assert step_name in steps, f"step {step_name!r} not emitted; got {list(steps)}"
    emitted = normalize_emitted_keys(steps[step_name])
    if shape.has_open_keys:
        # SetVariable accepts arbitrary user-chosen variable names at the
        # arguments root (the oracle's `[key: string]` wildcard), so an
        # emitted ⊆ documented check is meaningless. The contract that matters
        # is enforced elsewhere (the validator rejects reserved var names); here
        # we only assert the step compiled and emitted its variable.
        assert "score" in emitted, f"set_variable did not emit its var: {sorted(emitted)}"
        return
    extra = emitted - documented
    assert not extra, (
        f"{canonical} emitted keys not documented in the wire-shape oracle: "
        f"{sorted(extra)} (documented: {sorted(documented)})"
    )


# --------------------------------------------------------------------------
# Layer 3 — targeted assertions for the Phase-1 normalizer fixes
# --------------------------------------------------------------------------

def test_action_trigger_builds_params_from_input_vars():
    """ACTION_TRIGGER step_variables.input.params is a dict keyed by input var
    name (bundle lines 34560-34564), each mapping to vars.request.data."""
    yaml_text = """
collection: c
playbooks:
  - name: P
    steps:
      - name: Start
        type: start
        module: alerts
        arguments:
          inputVariables:
            - {name: severity}
            - {name: note}
      - {name: A, type: set_variable, vars: {y: 1}}
"""
    steps = {n: args for (n, _i, args) in _emitted_steps(yaml_text)}
    params = steps["Start"]["step_variables"]["input"]["params"]
    assert params == {
        "severity": '{{vars.request.data["severity"]}}',
        "note": '{{vars.request.data["note"]}}',
    }
    assert steps["Start"]["step_variables"]["input"]["records"] == "{{vars.input.records}}"


def test_action_trigger_no_input_vars_keeps_empty_params_array():
    yaml_text = """
collection: c
playbooks:
  - name: P
    steps:
      - {name: Start, type: start, module: alerts}
      - {name: A, type: set_variable, vars: {y: 1}}
"""
    steps = {n: args for (n, _i, args) in _emitted_steps(yaml_text)}
    assert steps["Start"]["step_variables"]["input"]["params"] == []


def test_find_record_select_fields_dropped_when_checkbox_false():
    yaml_text = """
collection: c
playbooks:
  - name: P
    steps:
      - {name: Start, type: start}
      - name: Find
        type: find_record
        arguments:
          module: alerts
          checkboxFields: false
          query: {logic: AND, filters: [], sort: [], limit: 30, __selectFields: [name]}
"""
    steps = {n: args for (n, _i, args) in _emitted_steps(yaml_text)}
    assert "__selectFields" not in steps["Find"]["query"]


def test_start_on_delete_emits_post_delete_trigger_shape():
    """start_on_delete resolves to cybersponse.post_delete and emits the same
    canonical trigger shape as post_create/post_update: the deleted record(s)
    arrive at vars.input.records (WIRE_SHAPE_GAP_PLAN Phase 2)."""
    yaml_text = """
collection: c
playbooks:
  - name: P
    steps:
      - {name: Trig, type: start_on_delete, module: alerts}
      - {name: A, type: set_variable, vars: {y: 1}}
"""
    steps = {n: (iri, args) for (n, iri, args) in _emitted_steps(yaml_text)}
    iri, args = steps["Trig"]
    assert iri.endswith("ef350fda-1771-477a-8f90-16f68cd7e5cb")  # post_delete
    assert args["resource"] == "alerts"
    assert args["step_variables"]["input"]["records"] == ["{{vars.input.records[0]}}"]


def test_delay_canonical_nested_form_preserved():
    """A canonical nested `delay: {...}` without a `rule` keeps the author's
    durations instead of being zeroed."""
    yaml_text = """
collection: c
playbooks:
  - name: P
    steps:
      - {name: Start, type: start}
      - name: Wait
        type: delay
        arguments:
          delay: {days: 0, hours: 2, minutes: 0, seconds: 0}
"""
    steps = {n: args for (n, _i, args) in _emitted_steps(yaml_text)}
    assert steps["Wait"]["delay"]["hours"] == 2
    assert "rule" in steps["Wait"]  # resume rule still filled
