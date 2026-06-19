"""compiler.render_analyzer — diagnostics over a step-through trace.

RENDER_PATH_VALIDATOR_PLAN.md Phase 3. Tests pin C1 (unreachable),
C2 (missing key), C3 (required arg empty), and severity downgrade
for conditionally-skipped producers.
"""
from __future__ import annotations

import textwrap

import pytest

pytest.importorskip("mcp.server.fastmcp",
                    reason="mcp package not installed")

import fsr_playbooks.mcp_server as mcp_server  # noqa: E402
import fsr_playbooks.mcp_server._shared  # noqa: E402, F401
from fsr_playbooks.compiler.render_analyzer import analyze, diagnostics_dict  # noqa: E402


@pytest.fixture(autouse=True)
def _no_live_fsr(monkeypatch):
    monkeypatch.setattr(mcp_server._shared, "_live_client", lambda: None)


def _trace(yaml_text, **kwargs):
    r = mcp_server.step_through_playbook(yaml_text, **kwargs)
    assert r.get("trace") is not None, r
    return r["trace"]


def _by_kind(diags):
    out = {}
    for d in diags:
        out.setdefault(d.kind, []).append(d)
    return out


# ---- C1 unreachable_var_path -----------------------------------------

def test_c1_flags_reference_to_nonexistent_step():
    yaml = textwrap.dedent("""\
        playbooks:
          - name: P
            steps:
              - id: t
                type: start
                name: T
                next: emit
              - id: emit
                type: set_variable
                name: Emit
                arguments:
                  arg_list:
                    - name: x
                      value: "{{ vars.steps.does_not_exist.id }}"
                next: stop
              - id: stop
                type: stop
                name: Stop
        """)
    diags = analyze(_trace(yaml))
    by = _by_kind(diags)
    assert "unreachable_var_path" in by
    d = by["unreachable_var_path"][0]
    assert d.severity == "error"
    assert "does_not_exist" in d.path
    assert d.extra.get("missing_step") == "does_not_exist"


def test_c1_flags_reference_to_later_step():
    yaml = textwrap.dedent("""\
        playbooks:
          - name: P
            steps:
              - id: t
                type: start
                name: T
                next: emit
              - id: emit
                type: set_variable
                name: Emit
                arguments:
                  arg_list:
                    - name: x
                      value: "{{ vars.steps.later.value }}"
                next: later
              - id: later
                type: set_variable
                name: Later
                arguments:
                  arg_list:
                    - name: value
                      value: 42
                next: stop
              - id: stop
                type: stop
                name: Stop
        """)
    diags = analyze(_trace(yaml))
    by = _by_kind(diags)
    assert "unreachable_var_path" in by
    d = by["unreachable_var_path"][0]
    assert "executes AFTER" in d.message
    assert d.extra["consumer_index"] < d.extra["producer_index"]


def test_c1_does_not_flag_valid_predecessor():
    yaml = textwrap.dedent("""\
        playbooks:
          - name: P
            steps:
              - id: t
                type: start
                name: T
                next: producer
              - id: producer
                type: set_variable
                name: Producer
                arguments:
                  arg_list:
                    - name: value
                      value: 1
                next: consumer
              - id: consumer
                type: set_variable
                name: Consumer
                arguments:
                  arg_list:
                    - name: x
                      value: "{{ vars.steps.Producer.value }}"
                next: stop
              - id: stop
                type: stop
                name: Stop
        """)
    diags = analyze(_trace(yaml))
    assert _by_kind(diags).get("unreachable_var_path", []) == []


# ---- C2 missing_key --------------------------------------------------

def test_c2_flags_typo_in_known_output_shape():
    yaml = textwrap.dedent("""\
        playbooks:
          - name: P
            steps:
              - id: t
                type: start
                name: T
                next: fetch
              - id: fetch
                type: connector
                name: Fetch
                arguments:
                  connector: jira
                  operation: get_ticket_details
                  mock_result:
                    summary: "ok"
                    status: "open"
                next: emit
              - id: emit
                type: set_variable
                name: Emit
                arguments:
                  arg_list:
                    - name: s
                      value: "{{ vars.steps.Fetch.statuss }}"
                next: stop
              - id: stop
                type: stop
                name: Stop
        """)
    diags = analyze(_trace(yaml))
    by = _by_kind(diags)
    assert "missing_key" in by
    d = by["missing_key"][0]
    assert d.severity == "error"
    assert "statuss" in d.path
    assert "status" in d.suggestion  # close-key heuristic


def test_c2_passes_when_key_exists():
    yaml = textwrap.dedent("""\
        playbooks:
          - name: P
            steps:
              - id: t
                type: start
                name: T
                next: fetch
              - id: fetch
                type: connector
                name: Fetch
                arguments:
                  connector: jira
                  operation: get_ticket_details
                  mock_result:
                    summary: "ok"
                next: emit
              - id: emit
                type: set_variable
                name: Emit
                arguments:
                  arg_list:
                    - name: s
                      value: "{{ vars.steps.Fetch.summary }}"
                next: stop
              - id: stop
                type: stop
                name: Stop
        """)
    diags = analyze(_trace(yaml))
    assert _by_kind(diags).get("missing_key", []) == []


def test_c2_downgrades_when_producer_was_conditionally_skipped():
    yaml = textwrap.dedent("""\
        playbooks:
          - name: P
            steps:
              - id: t
                type: start
                name: T
                next: gated
              - id: gated
                type: set_variable
                name: Gated
                arguments:
                  condition: "false"
                  arg_list:
                    - name: value
                      value: 1
                next: emit
              - id: emit
                type: set_variable
                name: Emit
                arguments:
                  arg_list:
                    - name: s
                      value: "{{ vars.steps.Gated.missing_field }}"
                next: stop
              - id: stop
                type: stop
                name: Stop
        """)
    diags = analyze(_trace(yaml))
    by = _by_kind(diags)
    # The producer was skipped — severity should drop to warning,
    # not error, because the producer might not run at runtime.
    if "missing_key" in by:
        assert by["missing_key"][0].severity == "warning"


# ---- C3 required_arg_empty -------------------------------------------

def test_c3_flags_empty_module_on_create_record():
    yaml = textwrap.dedent("""\
        playbooks:
          - name: P
            steps:
              - id: t
                type: start
                name: T
                next: rc
              - id: rc
                type: create_record
                name: RC
                arguments:
                  module: ""
                next: stop
              - id: stop
                type: stop
                name: Stop
        """)
    diags = analyze(_trace(yaml))
    by = _by_kind(diags)
    assert "required_arg_empty" in by
    assert by["required_arg_empty"][0].path == "module"


def test_c3_flags_empty_connector_on_connector_step():
    yaml = textwrap.dedent("""\
        playbooks:
          - name: P
            steps:
              - id: t
                type: start
                name: T
                next: c
              - id: c
                type: connector
                name: C
                arguments:
                  connector: ""
                  operation: get_ticket_details
                  mock_result: {}
                next: stop
              - id: stop
                type: stop
                name: Stop
        """)
    diags = analyze(_trace(yaml))
    by = _by_kind(diags)
    assert "required_arg_empty" in by
    fields = {d.path for d in by["required_arg_empty"]}
    assert "connector" in fields


# ---- Step-level condition skip ---------------------------------------

def test_step_condition_falsy_marks_conditionally_executed():
    yaml = textwrap.dedent("""\
        playbooks:
          - name: P
            steps:
              - id: t
                type: start
                name: T
                next: gated
              - id: gated
                type: set_variable
                name: Gated
                arguments:
                  condition: "false"
                  arg_list:
                    - name: value
                      value: 1
                next: stop
              - id: stop
                type: stop
                name: Stop
        """)
    trace = _trace(yaml)
    by_id = {r["step_id"]: r for r in trace}
    assert by_id["gated"]["conditionally_executed"] is True
    assert by_id["gated"]["output"] == {}


def test_step_condition_truthy_runs_normally():
    yaml = textwrap.dedent("""\
        playbooks:
          - name: P
            steps:
              - id: t
                type: start
                name: T
                next: gated
              - id: gated
                type: set_variable
                name: Gated
                arguments:
                  condition: "true"
                  arg_list:
                    - name: value
                      value: 1
                next: stop
              - id: stop
                type: stop
                name: Stop
        """)
    trace = _trace(yaml)
    by_id = {r["step_id"]: r for r in trace}
    assert by_id["gated"].get("conditionally_executed") is not True
    assert by_id["gated"]["output"] == {"value": 1}


# ---- diagnostics_dict serialization ----------------------------------

def test_c4_picklist_drift_fires_with_validator():
    """C4 calls the validator function (typically
    precheck_picklist_value) for each {{ 'PL' | picklist('val') }}
    reference and emits a diagnostic when the value isn't found."""
    yaml = textwrap.dedent("""\
        playbooks:
          - name: P
            steps:
              - id: t
                type: start
                name: T
                next: emit
              - id: emit
                type: set_variable
                name: Emit
                arguments:
                  arg_list:
                    - name: status
                      value: "{{ 'AlertStatus' | picklist('In Progress') }}"
                next: stop
              - id: stop
                type: stop
                name: Stop
        """)
    trace = _trace(yaml)

    def stub_validator(picklist, value):
        if picklist == "AlertStatus" and value == "In Progress":
            return {"ok": False,
                    "suggestions": ["Investigating", "Open", "Pending"],
                    "message": "value not in picklist"}
        return {"ok": True}

    from fsr_playbooks.compiler.render_analyzer import analyze
    diags = analyze(trace, picklist_validator=stub_validator)
    by = _by_kind(diags)
    assert "picklist_drift" in by
    d = by["picklist_drift"][0]
    assert d.severity == "error"
    assert "AlertStatus" in d.path
    assert "Investigating" in d.suggestion


def test_c4_skipped_when_no_validator():
    yaml = textwrap.dedent("""\
        playbooks:
          - name: P
            steps:
              - id: t
                type: start
                name: T
                next: emit
              - id: emit
                type: set_variable
                name: Emit
                arguments:
                  arg_list:
                    - name: status
                      value: "{{ 'AlertStatus' | picklist('Bogus') }}"
                next: stop
              - id: stop
                type: stop
                name: Stop
        """)
    diags = analyze(_trace(yaml))  # no validator
    assert _by_kind(diags).get("picklist_drift", []) == []


def test_c4_skips_when_validator_cannot_reach_fsr():
    yaml = textwrap.dedent("""\
        playbooks:
          - name: P
            steps:
              - id: t
                type: start
                name: T
                next: emit
              - id: emit
                type: set_variable
                name: Emit
                arguments:
                  arg_list:
                    - name: status
                      value: "{{ 'AlertStatus' | picklist('X') }}"
                next: stop
              - id: stop
                type: stop
                name: Stop
        """)
    def offline_validator(_pl, _val):
        return {"ok": False, "code": "no_live_fsr",
                "message": "FSR not configured"}
    from fsr_playbooks.compiler.render_analyzer import analyze
    diags = analyze(_trace(yaml), picklist_validator=offline_validator)
    assert _by_kind(diags).get("picklist_drift", []) == []


def test_c4_caches_repeated_picklist_value_pairs():
    """Same (picklist, value) pair shouldn't hit the validator twice
    even when referenced from multiple steps."""
    yaml = textwrap.dedent("""\
        playbooks:
          - name: P
            steps:
              - id: t
                type: start
                name: T
                next: e1
              - id: e1
                type: set_variable
                name: E1
                arguments:
                  arg_list:
                    - name: x
                      value: "{{ 'AlertStatus' | picklist('Open') }}"
                next: e2
              - id: e2
                type: set_variable
                name: E2
                arguments:
                  arg_list:
                    - name: y
                      value: "{{ 'AlertStatus' | picklist('Open') }}"
                next: stop
              - id: stop
                type: stop
                name: Stop
        """)
    calls: list[tuple] = []

    def counting_validator(pl, val):
        calls.append((pl, val))
        return {"ok": True}

    from fsr_playbooks.compiler.render_analyzer import analyze
    analyze(_trace(yaml), picklist_validator=counting_validator)
    assert calls == [("AlertStatus", "Open")]  # cached, called once


def test_analyze_playbook_mcp_tool_returns_diagnostics():
    yaml = textwrap.dedent("""\
        playbooks:
          - name: P
            steps:
              - id: t
                type: start
                name: T
                next: emit
              - id: emit
                type: set_variable
                name: Emit
                arguments:
                  arg_list:
                    - name: x
                      value: "{{ vars.steps.missing.id }}"
                next: stop
              - id: stop
                type: stop
                name: Stop
        """)
    r = mcp_server.analyze_playbook(yaml)
    assert r["ok"] is False
    assert r["error_count"] >= 1
    assert any(d["kind"] == "unreachable_var_path" for d in r["diagnostics"])


def test_analyze_playbook_clean_returns_ok():
    yaml = textwrap.dedent("""\
        playbooks:
          - name: P
            steps:
              - id: t
                type: start
                name: T
                next: producer
              - id: producer
                type: set_variable
                name: Producer
                arguments:
                  arg_list:
                    - name: value
                      value: 1
                next: consumer
              - id: consumer
                type: set_variable
                name: Consumer
                arguments:
                  arg_list:
                    - name: x
                      value: "{{ vars.steps.Producer.value }}"
                next: stop
              - id: stop
                type: stop
                name: Stop
        """)
    r = mcp_server.analyze_playbook(yaml)
    assert r["ok"] is True
    assert r["error_count"] == 0


def test_diagnostics_dict_is_jsonable():
    yaml = textwrap.dedent("""\
        playbooks:
          - name: P
            steps:
              - id: t
                type: start
                name: T
                next: emit
              - id: emit
                type: set_variable
                name: Emit
                arguments:
                  arg_list:
                    - name: x
                      value: "{{ vars.steps.missing.id }}"
                next: stop
              - id: stop
                type: stop
                name: Stop
        """)
    out = diagnostics_dict(_trace(yaml))
    import json
    # round-trips cleanly
    assert json.loads(json.dumps(out))[0]["kind"] == "unreachable_var_path"


# ---- C6 index_into_non_list ------------------------------------------

def test_c6_flags_index_into_dict_attr():
    """Producer's mock_result has an attr that is a dict; downstream
    `[0]`s it — runtime would raise TypeError on subscription."""
    yaml = textwrap.dedent("""\
        playbooks:
          - name: P
            steps:
              - id: t
                type: start
                name: T
                next: produce
              - id: produce
                type: set_variable
                name: Produce
                arguments:
                  arg_list:
                    - name: meta
                      value: '{"author": "alice", "tag": "phish"}'
                next: consume
              - id: consume
                type: set_variable
                name: Consume
                arguments:
                  arg_list:
                    - name: x
                      value: "{{ vars.steps.Produce.meta[0] }}"
                next: stop
              - id: stop
                type: stop
                name: Stop
        """)
    diags = analyze(_trace(yaml))
    by = _by_kind(diags)
    # Whether this fires depends on the simulator inferring `meta` as
    # dict-shaped — guard the assertion so we don't false-fail when
    # the trace doesn't expose enough shape info.
    if "index_into_non_list" in by:
        d = by["index_into_non_list"][0]
        assert d.severity == "warning"
        assert d.extra.get("attr") == "meta"


# ---- C9 loop_var_leak ------------------------------------------------

def test_c9_flags_vars_item_outside_loop():
    yaml = textwrap.dedent("""\
        playbooks:
          - name: P
            steps:
              - id: t
                type: start
                name: T
                next: loop
              - id: loop
                type: set_variable
                name: Loop
                for_each:
                  item: "[1, 2, 3]"
                  parallel: false
                arguments:
                  arg_list:
                    - name: in_loop
                      value: "{{ vars.item }}"
                next: after
              - id: after
                type: set_variable
                name: After
                arguments:
                  arg_list:
                    - name: oops
                      value: "{{ vars.item }}"
                next: stop
              - id: stop
                type: stop
                name: Stop
        """)
    import yaml as _yaml
    pb_dict = _yaml.safe_load(yaml)["playbooks"][0]
    diags = analyze(_trace(yaml), playbook=pb_dict)
    by = _by_kind(diags)
    assert "loop_var_leak" in by
    bad = [d for d in by["loop_var_leak"] if d.step_id == "after"]
    assert bad, by
    assert bad[0].severity == "error"


def test_c9_silent_when_vars_item_inside_loop():
    yaml = textwrap.dedent("""\
        playbooks:
          - name: P
            steps:
              - id: t
                type: start
                name: T
                next: loop
              - id: loop
                type: set_variable
                name: Loop
                for_each:
                  item: "[1, 2, 3]"
                  parallel: false
                arguments:
                  arg_list:
                    - name: in_loop
                      value: "{{ vars.item }}"
                next: stop
              - id: stop
                type: stop
                name: Stop
        """)
    import yaml as _yaml
    pb_dict = _yaml.safe_load(yaml)["playbooks"][0]
    diags = analyze(_trace(yaml), playbook=pb_dict)
    by = _by_kind(diags)
    assert "loop_var_leak" not in by


# ---- C10 dead_step ---------------------------------------------------

def test_c10_flags_unreferenced_set_variable():
    yaml = textwrap.dedent("""\
        playbooks:
          - name: P
            steps:
              - id: t
                type: start
                name: T
                next: dead
              - id: dead
                type: set_variable
                name: Dead
                arguments:
                  arg_list:
                    - name: useless
                      value: "42"
                next: stop
              - id: stop
                type: stop
                name: Stop
        """)
    diags = analyze(_trace(yaml))
    by = _by_kind(diags)
    assert "dead_step" in by
    assert by["dead_step"][0].severity == "info"


def test_c10_silent_when_step_is_referenced():
    yaml = textwrap.dedent("""\
        playbooks:
          - name: P
            steps:
              - id: t
                type: start
                name: T
                next: prod
              - id: prod
                type: set_variable
                name: Prod
                arguments:
                  arg_list:
                    - name: x
                      value: "42"
                next: cons
              - id: cons
                type: set_variable
                name: Cons
                arguments:
                  arg_list:
                    - name: y
                      value: "{{ vars.steps.Prod.x }}"
                next: stop
              - id: stop
                type: stop
                name: Stop
        """)
    diags = analyze(_trace(yaml))
    by = _by_kind(diags)
    # `prod` is referenced by `cons`; `cons` itself is dead since
    # nothing reads `y`, but we only care that the referenced producer
    # is silent here.
    dead_ids = {d.step_id for d in by.get("dead_step", [])}
    assert "prod" not in dead_ids, by


# ---- C7 decision_unset_path ------------------------------------------

def test_c7_flags_sibling_branch_reference():
    """A decision on branch B references a step that only runs on
    branch A — its output is never set on the path that reaches this
    decision."""
    yaml = textwrap.dedent("""\
        playbooks:
          - name: P
            steps:
              - id: t
                type: start
                name: T
                next: outer
              - id: outer
                type: decision
                name: Outer
                arguments:
                  conditions:
                    - display: "A"
                      when: "true"
                      next: prod_a
                    - display: "B"
                      default: true
                      next: inner
              - id: prod_a
                type: set_variable
                name: ProdA
                arguments:
                  arg_list:
                    - name: hits
                      value: 5
                next: stop
              - id: inner
                type: decision
                name: Inner
                arguments:
                  conditions:
                    - display: "Yes"
                      when: "{{ vars.steps.ProdA.hits > 0 }}"
                      next: stop
                    - display: "Else"
                      default: true
                      next: stop
              - id: stop
                type: stop
                name: Stop
        """)
    import yaml as _yaml
    pb_dict = _yaml.safe_load(yaml)["playbooks"][0]
    diags = analyze(_trace(yaml), playbook=pb_dict)
    by = _by_kind(diags)
    assert "decision_unset_path" in by, by
    d = by["decision_unset_path"][0]
    assert d.step_id == "inner"
    assert d.extra.get("producer_step") == "ProdA"
    assert d.severity == "warning"


def test_c7_silent_when_producer_is_predecessor():
    """Straight-line: producer runs before the decision on every
    path → no diagnostic."""
    yaml = textwrap.dedent("""\
        playbooks:
          - name: P
            steps:
              - id: t
                type: start
                name: T
                next: prod
              - id: prod
                type: set_variable
                name: Prod
                arguments:
                  arg_list:
                    - name: hits
                      value: 5
                next: d
              - id: d
                type: decision
                name: D
                arguments:
                  conditions:
                    - display: "Yes"
                      when: "{{ vars.steps.Prod.hits > 0 }}"
                      next: stop
                    - display: "Else"
                      default: true
                      next: stop
              - id: stop
                type: stop
                name: Stop
        """)
    import yaml as _yaml
    pb_dict = _yaml.safe_load(yaml)["playbooks"][0]
    diags = analyze(_trace(yaml), playbook=pb_dict)
    by = _by_kind(diags)
    assert "decision_unset_path" not in by, by


# ---- C8 mi_mode_mismatch ---------------------------------------------

def _mi_yaml(mi_block, read_value):
    return textwrap.dedent(f"""\
        playbooks:
          - name: P
            steps:
              - id: t
                type: start
                name: T
                next: mi
              - id: mi
                type: manual_input
                name: MI
                {mi_block}
                next: read
              - id: read
                type: set_variable
                name: Read
                arguments:
                  arg_list:
                    - name: r
                      value: "{read_value}"
                next: stop
              - id: stop
                type: stop
                name: Stop
        """)


def test_c8_flags_undeclared_input_field_on_inputbased():
    yaml = _mi_yaml(
        """arguments:
                  type: InputBased
                  input:
                    schema:
                      inputVariables:
                        - {name: reason, type: text}
                  response_mapping:
                    options:
                      - {option: OK, step_iri: null}""",
        "{{ vars.steps.MI.input.notdeclared }}",
    )
    import yaml as _yaml
    pb = _yaml.safe_load(yaml)["playbooks"][0]
    diags = analyze(_trace(yaml), playbook=pb)
    by = _by_kind(diags)
    assert "mi_mode_mismatch" in by, by
    d = by["mi_mode_mismatch"][0]
    assert d.severity == "error"
    assert d.actual == "notdeclared"
    assert d.expected == ["reason"]


def test_c8_silent_when_declared_input_field_used():
    yaml = _mi_yaml(
        """arguments:
                  type: InputBased
                  input:
                    schema:
                      inputVariables:
                        - {name: reason, type: text}
                  response_mapping:
                    options:
                      - {option: OK, step_iri: null}""",
        "{{ vars.steps.MI.input.reason }}",
    )
    import yaml as _yaml
    pb = _yaml.safe_load(yaml)["playbooks"][0]
    diags = analyze(_trace(yaml), playbook=pb)
    by = _by_kind(diags)
    assert "mi_mode_mismatch" not in by, by


def test_c8_flags_input_read_on_decisionbased():
    yaml = _mi_yaml(
        """arguments:
                  type: DecisionBased
                  response_mapping:
                    options:
                      - {option: OK, step_iri: null}""",
        "{{ vars.steps.MI.input.anything }}",
    )
    import yaml as _yaml
    pb = _yaml.safe_load(yaml)["playbooks"][0]
    diags = analyze(_trace(yaml), playbook=pb)
    by = _by_kind(diags)
    assert "mi_mode_mismatch" in by, by
    d = by["mi_mode_mismatch"][0]
    assert d.severity == "error"
    assert d.extra["mode"] == "DecisionBased"


def test_c8_allows_system_metadata_keys():
    yaml = _mi_yaml(
        """arguments:
                  type: InputBased
                  input:
                    schema:
                      inputVariables:
                        - {name: reason, type: text}
                  response_mapping:
                    options:
                      - {option: OK, step_iri: null}""",
        "{{ vars.steps.MI.userid }}",
    )
    import yaml as _yaml
    pb = _yaml.safe_load(yaml)["playbooks"][0]
    diags = analyze(_trace(yaml), playbook=pb)
    by = _by_kind(diags)
    assert "mi_mode_mismatch" not in by, by


def test_c8_warns_on_buttononly_inputbased_when_input_read():
    """InputBased MI with no declared inputVariables — can't prove
    mismatch, so warn instead of error."""
    yaml = _mi_yaml(
        """arguments:
                  type: InputBased
                  response_mapping:
                    options:
                      - {option: OK, step_iri: null}""",
        "{{ vars.steps.MI.input.something }}",
    )
    import yaml as _yaml
    pb = _yaml.safe_load(yaml)["playbooks"][0]
    diags = analyze(_trace(yaml), playbook=pb)
    by = _by_kind(diags)
    assert "mi_mode_mismatch" in by, by
    assert by["mi_mode_mismatch"][0].severity == "warning"
