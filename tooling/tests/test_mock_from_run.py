"""Offline tests for mock_from_run: a fixture run payload, no box.

The run dict has the shape pyfsr's get_execution(pk, step_detail=True) returns:
a name, a status, an env, and per-step records with name/status/result.
"""
from __future__ import annotations

import mock_from_run as mfr
import pytest

PLAYBOOK = "Triage Fixture"

YAML_TEXT = """\
collection: Fixture
playbooks:
  - name: Triage Fixture
    is_active: true
    steps:
      - name: trigger
        type: start
        next: Lookup Hosts

      # Hosts come from the connector; the next step reads its data envelope.
      - name: Lookup Hosts
        type: connector
        next: Echo Hosts
        connector: fuzzy-search
        operation: filter_json_by_key_value
        config: ""
        params:
          fuzzyMatch: false

      - name: Echo Hosts
        type: code_snippet
        next: Set Count
        code: |
          print({"first": "{{ vars.steps.Lookup_Hosts.data[0].host | default('none') }}"})

      - name: Set Count
        type: set_variable
        next: Insert Note
        vars:
          count: "{{ vars.steps.Lookup_Hosts.data | length }}"

      - name: Insert Note
        type: insert_data
        next: Broken Ref
        module: comments

      - name: Broken Ref
        type: code_snippet
        next: Skipped Step
        code: |
          print({"wrong": "{{ vars.steps.Lookup_Hosts.code_output.x }}",
                 "gone": "{{ vars.steps.Never_Ran.data.code_output.x }}"})

      - name: Skipped Step
        type: connector
        connector: fuzzy-search
        operation: search_keyword_in_text
        config: ""
        params: {}
"""


def _run(steps, *, status="finished", name=PLAYBOOK, env=None):
    return mfr.RunRecord(
        pk="900001",
        name=name,
        status=status,
        task_id=None,
        env=env if env is not None else {"input": {"records": []}, "debug": True},
        steps=steps,
    )


def _steps(hosts=None):
    hosts = hosts if hosts is not None else [
        {"host": "alpha-fw-01", "tier": "edge"},
        {"host": "beta-fw-02", "tier": "edge"},
    ]
    return [
        {"name": "trigger", "status": "finished", "result": {"debug": True}},
        {"name": "Lookup Hosts", "status": "finished",
         "result": {"data": hosts, "status": "Success", "message": "", "operation": None}},
        {"name": "Echo Hosts", "status": "finished",
         "result": {"data": {"code_output": {"first": "alpha-fw-01"}},
                    "status": "Success", "message": "", "operation": None}},
        {"name": "Set Count", "status": "finished", "result": {"count": "2"}},
        {"name": "Insert Note", "status": "finished",
         "result": {"data": {"id": 7}, "status": "Success", "message": "", "operation": None}},
        {"name": "Broken Ref", "status": "finished",
         "result": {"data": {"code_output": {"wrong": "", "gone": ""}},
                    "status": "Success", "message": "", "operation": None}},
        {"name": "Skipped Step", "status": "skipped", "result": None},
    ]


# --------------------------------------------------------------------------- #
# selection
# --------------------------------------------------------------------------- #

def test_default_mocks_only_executed_successful_connector_and_code_snippet():
    plan = mfr.build_plan(YAML_TEXT, PLAYBOOK, _run(_steps()), max_items=20)
    assert set(plan.mocks) == {"Lookup Hosts", "Echo Hosts", "Broken Ref"}
    actions = {d.step: (d.action, d.reason) for d in plan.decisions}
    assert actions["Insert Note"][0] == "skip"
    assert "default mock target" in actions["Insert Note"][1]
    assert actions["Set Count"][0] == "skip"
    assert actions["Skipped Step"] == ("skip", "step status is skipped")


def test_failed_and_erroring_steps_are_not_mocked():
    steps = _steps()
    steps[1] = {**steps[1], "status": "finished_with_error"}
    steps[2] = {**steps[2], "result": {"data": {}, "status": "Failed"}}
    plan = mfr.build_plan(YAML_TEXT, PLAYBOOK, _run(steps))
    assert "Lookup Hosts" not in plan.mocks
    assert "Echo Hosts" not in plan.mocks
    reasons = {d.step: d.reason for d in plan.decisions if d.action == "skip"}
    assert reasons["Lookup Hosts"] == "step status is finished_with_error"
    assert reasons["Echo Hosts"] == "result status is Failed"


def test_named_steps_override_the_type_filter_and_unknown_names_are_refused():
    plan = mfr.build_plan(YAML_TEXT, PLAYBOOK, _run(_steps()), only={"Insert Note"})
    assert set(plan.mocks) == {"Insert Note"}
    assert plan.mocks["Insert Note"].value == {
        "data": {"id": 7}, "status": "Success", "message": "", "operation": None}
    with pytest.raises(mfr.MockFromRunError, match="not in the YAML"):
        mfr.build_plan(YAML_TEXT, PLAYBOOK, _run(_steps()), only={"Nope"})


def test_run_must_be_finished_and_belong_to_the_playbook():
    with pytest.raises(mfr.MockFromRunError, match="finished run"):
        mfr._check_run_matches(_run(_steps(), status="failed"), PLAYBOOK)
    with pytest.raises(mfr.MockFromRunError, match="not 'Triage Fixture'"):
        mfr._check_run_matches(_run(_steps(), name="Other Playbook"), PLAYBOOK)
    mfr._check_run_matches(_run(_steps()), PLAYBOOK)


def test_pick_playbook_needs_a_name_when_the_file_holds_several():
    two = YAML_TEXT + "  - name: Second\n    steps: []\n"
    with pytest.raises(mfr.MockFromRunError, match="pass --playbook"):
        mfr.pick_playbook(two, None)
    assert mfr.pick_playbook(two, "Second") == "Second"
    assert mfr.pick_playbook(YAML_TEXT, None) == PLAYBOOK


# --------------------------------------------------------------------------- #
# shape: verbatim envelope, caps
# --------------------------------------------------------------------------- #

def test_mock_value_is_the_stored_envelope_verbatim():
    plan = mfr.build_plan(YAML_TEXT, PLAYBOOK, _run(_steps()))
    assert plan.mocks["Echo Hosts"].value == {
        "data": {"code_output": {"first": "alpha-fw-01"}},
        "status": "Success", "message": "", "operation": None,
    }


def test_lists_are_capped_and_each_truncation_is_reported():
    hosts = [{"host": f"h{i}"} for i in range(30)]
    plan = mfr.build_plan(YAML_TEXT, PLAYBOOK, _run(_steps(hosts)), max_items=20)
    mv = plan.mocks["Lookup Hosts"]
    assert len(mv.value["data"]) == 20
    assert mv.truncated == ["data (30 -> 20 items)"]


def test_cap_lists_walks_nested_lists():
    out, notes = mfr.cap_lists({"a": {"b": [1, 2, 3, 4]}, "c": [[1, 2, 3]]}, 2)
    assert out == {"a": {"b": [1, 2]}, "c": [[1, 2]]}
    assert notes == ["a.b (4 -> 2 items)", "c[0] (3 -> 2 items)"]


# --------------------------------------------------------------------------- #
# redaction
# --------------------------------------------------------------------------- #

def test_redact_replaces_emails_ips_bearer_and_secret_keys_stably():
    steps = _steps()
    steps[1] = {"name": "Lookup Hosts", "status": "finished", "result": {
        "data": [
            {"owner": "alice@corp.example", "src": "203.0.113.9", "dst": "203.0.113.9"},
            {"owner": "bob@corp.example", "src": "192.0.2.44", "note": "Bearer abcdefgh1234"},
        ],
        "api_key": "s3cr3t-value",
        "status": "Success", "message": "", "operation": None,
    }}
    plan = mfr.build_plan(YAML_TEXT, PLAYBOOK, _run(steps), redact=True)
    data = plan.mocks["Lookup Hosts"].value["data"]
    assert data[0]["owner"] == "user1@example.com"
    assert data[1]["owner"] == "user2@example.com"
    # the same address maps to the same placeholder everywhere in the mock
    assert data[0]["src"] == data[0]["dst"] == "198.51.0.1"
    assert data[1]["src"] == "198.51.0.2"
    assert data[1]["note"] == "Bearer <redacted>"
    assert plan.mocks["Lookup Hosts"].value["api_key"] == "<redacted>"
    assert plan.redacted > 0
    assert "alice@corp.example" not in repr(plan.mocks["Lookup Hosts"].value)


def test_without_redact_sensitive_values_are_counted_not_changed():
    steps = _steps()
    steps[1] = {"name": "Lookup Hosts", "status": "finished", "result": {
        "data": [{"owner": "alice@corp.example"}], "status": "Success"}}
    plan = mfr.build_plan(YAML_TEXT, PLAYBOOK, _run(steps), redact=False)
    assert plan.mocks["Lookup Hosts"].value["data"][0]["owner"] == "alice@corp.example"
    assert plan.sensitive_seen == {"email": 1}


def test_version_numbers_are_not_mistaken_for_ips():
    assert mfr.scan_sensitive({"v": "8.0.1-6095", "n": "10.0"}) == {}


# --------------------------------------------------------------------------- #
# YAML write (round trip) and the offline render check
# --------------------------------------------------------------------------- #

def test_write_mocks_adds_step_level_mock_result_and_keeps_the_rest():
    plan = mfr.build_plan(YAML_TEXT, PLAYBOOK, _run(_steps(
        [{"host": f"h{i}"} for i in range(30)])), max_items=20)
    out = mfr.write_mocks(YAML_TEXT, PLAYBOOK, plan.mocks)
    assert "mock_result:" in out
    assert out.count("mock_result:") == 3
    assert "truncated: data (30 -> 20 items)" in out
    assert "useMockOutput" not in out  # never flips a step to mock mode
    for keep in ("fuzzy-search", "filter_json_by_key_value", "{{ vars.steps.Lookup_Hosts.data | length }}",
                 "collection: Fixture", "# Hosts come from the connector"):
        assert keep in out


def test_write_mocks_replaces_an_existing_mock_result():
    text = YAML_TEXT.replace(
        "        params:\n          fuzzyMatch: false\n",
        "        params:\n          fuzzyMatch: false\n        mock_result: {data: []}\n",
    )
    plan = mfr.build_plan(text, PLAYBOOK, _run(_steps()))
    assert plan.mocks["Lookup Hosts"].replaced_existing is True
    out = mfr.write_mocks(text, PLAYBOOK, plan.mocks)
    assert out.count("mock_result:") == 3
    assert "mock_result: {data: []}" not in out


def test_render_check_passes_when_refs_match_the_envelope():
    plan = mfr.build_plan(YAML_TEXT, PLAYBOOK, _run(_steps()), only={"Echo Hosts"})
    out = mfr.write_mocks(YAML_TEXT, PLAYBOOK, plan.mocks)
    _, _, findings = mfr.render_check(out, PLAYBOOK, _run(_steps()), plan.mocks)
    # Echo Hosts reads vars.steps.Lookup_Hosts.data[0].host, which the envelope supplies.
    assert not any(f.step == "Echo Hosts" for f in findings)


def test_render_check_flags_refs_that_would_render_empty():
    plan = mfr.build_plan(YAML_TEXT, PLAYBOOK, _run(_steps()))
    out = mfr.write_mocks(YAML_TEXT, PLAYBOOK, plan.mocks)
    _, _, findings = mfr.render_check(out, PLAYBOOK, _run(_steps()), plan.mocks)
    broken = [f for f in findings if f.step == "Broken Ref"]
    assert broken, "a ref missing the .data envelope must be reported"
    assert any("wrong" in f.empty or "code_output" in f.template for f in broken)
    # a step that never ran in the source run is absent from the context
    assert any("Never_Ran" in f.template and f.empty for f in broken)


def test_render_check_counts_templates_and_skips_mock_result_bodies():
    plan = mfr.build_plan(YAML_TEXT, PLAYBOOK, _run(_steps()))
    out = mfr.write_mocks(YAML_TEXT, PLAYBOOK, plan.mocks)
    checked, opaque, _ = mfr.render_check(out, PLAYBOOK, _run(_steps()), plan.mocks)
    assert checked >= 3
    assert opaque == 0
