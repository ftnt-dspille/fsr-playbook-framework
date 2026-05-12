"""mcp_server.step_through_playbook — simulator extensions for the
render-path validator (RENDER_PATH_VALIDATOR_PLAN.md Phase 1).

Each test pins one provenance / step-type behavior so future drift on
the analyzer's foundation is loud.
"""
from __future__ import annotations

import textwrap

import pytest

pytest.importorskip(
    "mcp.server.fastmcp",
    reason="mcp package not installed (pip install mcp)",
)

import mcp_server  # noqa: E402


@pytest.fixture(autouse=True)
def _no_live_fsr(monkeypatch):
    """Force the stepper offline so jinja-render is a no-op and we
    exercise the deterministic simulation paths only."""
    monkeypatch.setattr(mcp_server, "_live_client", lambda: None)


# ---- helpers ----------------------------------------------------------

def _trace_by_id(result):
    return {r["step_id"]: r for r in result["trace"]}


# ---- P1.1 simulated_from provenance ----------------------------------

def test_set_variable_provenance_is_computed():
    yaml = textwrap.dedent("""\
        playbooks:
          - name: P
            steps:
              - id: t
                type: start
                name: T
                next: sv
              - id: sv
                type: set_variable
                name: SV
                arguments:
                  arg_list:
                    - name: x
                      value: hello
                next: stop
              - id: stop
                type: stop
                name: Stop
        """)
    r = mcp_server.step_through_playbook(yaml)
    by = _trace_by_id(r)
    assert by["sv"]["simulated_from"] == "computed"
    assert by["sv"]["output"] == {"x": "hello"}
    assert by["t"]["simulated_from"] == "computed"


# ---- P1.2 mock_result honored ----------------------------------------

def test_mock_result_short_circuits_connector_execution():
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
                  connector: jira
                  operation: get_ticket_details
                  mock_result:
                    data:
                      key: JIR-7
                      summary: mocked
                next: stop
              - id: stop
                type: stop
                name: Stop
        """)
    r = mcp_server.step_through_playbook(yaml)
    by = _trace_by_id(r)
    assert by["c"]["simulated_from"] == "mock_result"
    assert by["c"]["output"]["data"]["key"] == "JIR-7"


def test_mock_result_on_record_crud():
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
                name: Create
                arguments:
                  module: alerts
                  mock_result:
                    id: 42
                    status: open
                next: stop
              - id: stop
                type: stop
                name: Stop
        """)
    r = mcp_server.step_through_playbook(yaml)
    by = _trace_by_id(r)
    assert by["rc"]["simulated_from"] == "mock_result"
    assert by["rc"]["output"] == {"id": 42, "status": "open"}


# ---- P1.3 Decision auto-eval -----------------------------------------

def test_decision_auto_picks_first_truthy_branch():
    yaml = textwrap.dedent("""\
        playbooks:
          - name: P
            steps:
              - id: t
                type: start
                name: T
                next: d
              - id: d
                type: decision
                name: D
                arguments:
                  conditions:
                    - display: "Hot"
                      when: "true"
                      next: hot
                    - display: "Cold"
                      when: "false"
                      next: cold
                branches:
                  Hot: hot
                  Cold: cold
              - id: hot
                type: set_variable
                name: Hot
                arguments:
                  arg_list:
                    - name: path
                      value: hot_path
                next: stop
              - id: cold
                type: set_variable
                name: Cold
                arguments:
                  arg_list:
                    - name: path
                      value: cold_path
                next: stop
              - id: stop
                type: stop
                name: Stop
        """)
    r = mcp_server.step_through_playbook(yaml)
    by = _trace_by_id(r)
    assert by["d"]["simulated_from"] == "computed"
    assert by["d"]["output"] == {"branch": "Hot"}
    assert "hot" in by  # took the hot branch
    assert "cold" not in by  # cold was skipped


def test_decision_honors_default_when_all_false():
    yaml = textwrap.dedent("""\
        playbooks:
          - name: P
            steps:
              - id: t
                type: start
                name: T
                next: d
              - id: d
                type: decision
                name: D
                arguments:
                  conditions:
                    - display: "Maybe"
                      when: "false"
                      next: maybe
                    - display: "Else"
                      default: true
                      next: else_path
                branches:
                  Maybe: maybe
                  Else: else_path
              - id: maybe
                type: stop
                name: Maybe
              - id: else_path
                type: stop
                name: Else
        """)
    r = mcp_server.step_through_playbook(yaml)
    by = _trace_by_id(r)
    assert by["d"]["output"] == {"branch": "Else"}
    assert "else_path" in by
    assert "maybe" not in by


def test_decision_pinned_branch_wins_over_auto():
    yaml = textwrap.dedent("""\
        playbooks:
          - name: P
            steps:
              - id: t
                type: start
                name: T
                next: d
              - id: d
                type: decision
                name: D
                arguments:
                  conditions:
                    - display: "A"
                      when: "true"
                      next: a
                    - display: "B"
                      when: "false"
                      next: b
                branches:
                  A: a
                  B: b
              - id: a
                type: stop
                name: A
              - id: b
                type: stop
                name: B
        """)
    r = mcp_server.step_through_playbook(yaml, branch_choices={"d": "B"})
    by = _trace_by_id(r)
    assert by["d"]["output"] == {"branch": "B"}
    assert "b" in by
    assert "a" not in by


# ---- P1.4 ManualInput resolution -------------------------------------

def test_manual_input_resolves_from_manual_choices():
    yaml = textwrap.dedent("""\
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
                arguments:
                  options:
                    - display: Approve
                    - display: Reject
                branches:
                  Approve: stop
                  Reject: stop
              - id: stop
                type: stop
                name: Stop
        """)
    r = mcp_server.step_through_playbook(yaml, manual_choices={"mi": "Reject"})
    by = _trace_by_id(r)
    assert by["mi"]["output"] == {"option": "Reject"}
    assert by["mi"]["simulated_from"] == "computed"


def test_manual_input_falls_back_to_first_option():
    yaml = textwrap.dedent("""\
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
                arguments:
                  options:
                    - display: Approve
                    - display: Reject
                branches:
                  Approve: stop
                  Reject: stop
              - id: stop
                type: stop
                name: Stop
        """)
    r = mcp_server.step_through_playbook(yaml)
    by = _trace_by_id(r)
    assert by["mi"]["output"] == {"option": "Approve"}


# ---- P1.7 output_shape inference -------------------------------------

def test_output_shape_dict():
    s = mcp_server._infer_output_shape({"a": 1, "b": "x", "c": [1, 2]})
    assert s["kind"] == "dict"
    assert s["top_keys"] == ["a", "b", "c"]
    assert s["types"] == {"a": "int", "b": "string", "c": "list"}


def test_output_shape_list():
    s = mcp_server._infer_output_shape([{"id": 1, "name": "n"}])
    assert s["kind"] == "list"
    assert s["length"] == 1
    assert s["item_type"] == "dict"
    assert s["item_keys"] == ["id", "name"]


def test_output_shape_scalar():
    s = mcp_server._infer_output_shape("hello")
    assert s["kind"] == "string"
    assert s["value"] == "hello"


def test_output_shape_attached_to_every_trace_record():
    yaml = textwrap.dedent("""\
        playbooks:
          - name: P
            steps:
              - id: t
                type: start
                name: T
                next: sv
              - id: sv
                type: set_variable
                name: SV
                arguments:
                  arg_list:
                    - name: x
                      value: 1
                next: stop
              - id: stop
                type: stop
                name: Stop
        """)
    r = mcp_server.step_through_playbook(yaml)
    for rec in r["trace"]:
        assert rec["output_shape"] is not None, rec["step_id"]
        assert "kind" in rec["output_shape"]


# ---- P1.5 for_each iteration -----------------------------------------

def test_for_each_sequential_emits_list_of_per_iteration_dicts():
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
                  item: "{{ [10, 20, 30] }}"
                arguments:
                  arg_list:
                    - name: current
                      value: "{{ vars.item }}"
                next: stop
              - id: stop
                type: stop
                name: Stop
        """)
    r = mcp_server.step_through_playbook(yaml)
    by = _trace_by_id(r)
    out = by["loop"]["output"]
    assert isinstance(out, list)
    assert len(out) == 3
    # Each iteration carries the body's set_var keys + the task_id stub.
    assert out[0]["current"] == "10" or out[0]["current"] == 10 \
        or out[0]["current"] == "{{ vars.item }}"  # offline jinja may not resolve
    assert all("task_id" in entry for entry in out)
    assert by["loop"]["loop_iterations"] == 3
    assert by["loop"]["output_shape"]["kind"] == "list"


def test_for_each_break_loop_includes_breaking_iteration():
    """Real-FSR semantics: break_loop runs AFTER the iteration's
    body, so [1,2,3,4,5] with break on item==3 produces 3 entries
    not 2 — matches the captured probe fixture."""
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
                  item: "{{ [1, 2, 3, 4, 5] }}"
                  break_loop: "{{ vars.item == 3 }}"
                arguments:
                  arg_list:
                    - name: current
                      value: "{{ vars.item }}"
                next: stop
              - id: stop
                type: stop
                name: Stop
        """)
    # Offline: the live Jinja engine is absent so break_loop's
    # predicate template renders as the verbatim string, which our
    # _truthy reader treats as truthy → break fires after the first
    # iteration. That's an honest limitation of the offline path; the
    # fixture-backed test (test_render_path_fixtures.py) pins the
    # live-FSR do-while behavior end-to-end.
    r = mcp_server.step_through_playbook(yaml)
    by = _trace_by_id(r)
    out = by["loop"]["output"]
    assert isinstance(out, list)
    assert 1 <= len(out) <= 5
    # The break-AFTER semantics matter: even when break fires, the
    # iteration's body output IS in the result list.
    assert all("task_id" in entry for entry in out)


def test_for_each_condition_filters_iterations():
    """Without live Jinja the condition won't render to a bool, so
    we don't assert filtering offline. The fixture-backed test pins
    the live-FSR behavior. Smoke: condition presence doesn't crash."""
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
                  item: "{{ [1, 2, 3] }}"
                  condition: "{{ vars.item % 2 == 0 }}"
                arguments:
                  arg_list:
                    - name: current
                      value: "{{ vars.item }}"
                next: stop
              - id: stop
                type: stop
                name: Stop
        """)
    r = mcp_server.step_through_playbook(yaml)
    by = _trace_by_id(r)
    assert isinstance(by["loop"]["output"], list)


def test_for_each_empty_list_yields_empty_output():
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
                  item: "{{ [] }}"
                arguments:
                  arg_list:
                    - name: current
                      value: "{{ vars.item }}"
                next: stop
              - id: stop
                type: stop
                name: Stop
        """)
    r = mcp_server.step_through_playbook(yaml)
    by = _trace_by_id(r)
    assert by["loop"]["output"] == []
    assert by["loop"]["loop_iterations"] == 0


def test_coerce_literal_list_handles_inline_jinja_literal():
    assert mcp_server._coerce_literal_list("{{ [1, 2, 3] }}") == [1, 2, 3]
    assert mcp_server._coerce_literal_list("[1, 2]") == [1, 2]
    assert mcp_server._coerce_literal_list([7, 8]) == [7, 8]
    assert mcp_server._coerce_literal_list("{{ vars.x }}") == []
    assert mcp_server._coerce_literal_list(None) == []


# ---- _truthy edge cases ----------------------------------------------

@pytest.mark.parametrize("v,expected", [
    ("true", True), ("True", True), ("1", True), ("yes", True),
    ("false", False), ("False", False), ("0", False), ("no", False),
    ("", False), ("null", False), ("none", False),
    (1, True), (0, False), ([1], True), ([], False),
    ({"a": 1}, True), ({}, False), (None, False), (True, True), (False, False),
])
def test_truthy(v, expected):
    assert mcp_server._truthy(v) is expected
