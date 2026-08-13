"""#127 -- behavioral assertions on a built playbook (`behavior` level).

`draft` says it compiles, `verified` says it is statically sound. Neither reads
the prompt, so a playbook that loops the wrong field or blocks BEFORE the
approval gate scored exactly as well as a correct one.

These tests run against really-compiled YAML, not hand-built IR objects,
because the failure mode this engine can have is asserting on a vocabulary the
compiler does not use -- `for_each` is a dict, not a string; `end` survives as
a step type but `record_action` does not. A grader that fails a correct answer
is the defect #127 exists to remove, so the vocabulary is pinned here.
"""
from __future__ import annotations

import importlib

ira = importlib.import_module("evals.ir_assertions")

GATED = """
collection: Gate Fixtures
description: approval gate ahead of a block.

playbooks:
  - name: Block With Approval
    description: fixture.
    steps:
      - name: start
        type: start
        next: Ask Analyst
      - name: Ask Analyst
        type: manual_input
        title: "Block this IP?"
        options:
          - display: Block
            primary: true
            next: Block IP
          - display: Skip
            next: Note Skipped
      - name: Block IP
        type: connector
        connector: fortigate
        operation: block_ip
        params:
          ip: "{{ vars.steps.Ask_Analyst.ip }}"
      - name: Note Skipped
        type: set_variable
        vars:
          outcome: skipped
"""

# Same steps, same connector, same compile result -- but the block runs FIRST
# and the analyst is asked afterwards. Only a behavioral assertion can tell
# this apart from GATED; `draft` and `verified` cannot.
UNGATED = """
collection: Gate Fixtures
description: the block runs before anyone is asked.

playbooks:
  - name: Block Then Ask
    description: fixture.
    steps:
      - name: start
        type: start
        next: Block IP
      - name: Block IP
        type: connector
        connector: fortigate
        operation: block_ip
        next: Ask Analyst
        params:
          ip: "1.2.3.4"
      - name: Ask Analyst
        type: manual_input
        title: "We blocked it. OK?"
        options:
          - display: Fine
            primary: true
            next: Note Skipped
      - name: Note Skipped
        type: set_variable
        vars:
          outcome: acknowledged
"""


def _check(yaml_text, assertions):
    return ira.check_ir_assertions(yaml_text, assertions)


# --- the vocabulary actually matches what the compiler emits ---------------

def test_step_types_resolve_as_asserted():
    r = _check(GATED, [
        {"kind": "step_type_present", "type": "manual_input"},
        {"kind": "step_type_present", "type": "connector"},
        {"kind": "step_type_present", "type": "set_variable"},
    ])
    assert r["passed"] is True, r["failures"]


def test_connector_op_matches_a_real_connector_step():
    r = _check(GATED, [{"kind": "connector_op", "connector": "fortigate",
                        "operation_contains": "block_ip"}])
    assert r["passed"] is True, r["failures"]


def test_connector_op_that_is_absent_fails():
    r = _check(GATED, [{"kind": "connector_op", "connector": "virustotal"}])
    assert r["passed"] is False


# --- the assertion the gate exists for ------------------------------------

def test_the_block_must_be_reachable_only_through_the_gate():
    r = _check(GATED, [{"kind": "reachable",
                        "from": {"type": "manual_input"},
                        "to": {"type": "connector", "connector": "fortigate"},
                        "note": "P2: the block is downstream of the approval"}])
    assert r["passed"] is True, r["failures"]


def test_a_playbook_that_blocks_before_asking_fails_that_assertion():
    # Same steps, same connector, compiles and verifies identically -- and it
    # contains the analyst's gate AFTER the containment. This is the case the
    # old scoreboard could not see at all.
    r = _check(UNGATED, [{"kind": "reachable",
                          "from": {"type": "manual_input"},
                          "to": {"type": "connector", "connector": "fortigate"}}])
    assert r["passed"] is False
    assert "reachable" in r["detail"] or r["failures"]


def test_reachability_follows_branches_not_list_order():
    # `Note Skipped` is the LAST step in the list but sits on the Skip arm, so
    # it is reachable from the gate. List-order comparison would say otherwise.
    r = _check(GATED, [{"kind": "reachable",
                        "from": {"type": "manual_input"},
                        "to": {"type": "set_variable"}}])
    assert r["passed"] is True, r["failures"]


# --- argument text + branch shape -----------------------------------------

def test_arg_text_contains_reads_resolved_arguments():
    r = _check(GATED, [{"kind": "arg_text_contains", "type": "connector",
                        "contains": "vars.steps."}])
    assert r["passed"] is True, r["failures"]


def test_branch_count_sees_the_gate_arms():
    r = _check(GATED, [{"kind": "branch_count", "type": "manual_input",
                        "min": 2}])
    assert r["passed"] is True, r["failures"]
    assert _check(GATED, [{"kind": "branch_count", "type": "manual_input",
                           "min": 3}])["passed"] is False


# --- the honesty rules ----------------------------------------------------

def test_a_fixture_with_no_assertions_skips_rather_than_passing():
    r = _check(GATED, [])
    assert r["skipped"] is True
    assert r["passed"] is False


def test_an_unknown_assertion_kind_fails_loudly():
    # A typo'd assertion that passes vacuously is worse than no assertion.
    r = _check(GATED, [{"kind": "step_tpye_present", "type": "connector"}])
    assert r["passed"] is False
    assert "unknown assertion kind" in r["failures"][0]


def test_uncompilable_yaml_is_unjudgeable_not_misbehaving():
    r = _check("this: is not: a playbook\n",
               [{"kind": "step_type_present", "type": "connector"}])
    assert r["passed"] is False
    assert "did not compile" in r["detail"] or "did not compile" in r["failures"][0]


def test_the_detail_names_what_failed():
    r = _check(GATED, [{"kind": "step_type_present", "type": "code_snippet",
                        "note": "runs a python step"}])
    assert "runs a python step" in r["detail"]
    assert r["checked"] == 1


# --- calibration: the assertions must not fail a CORRECT answer ------------
#
# The failure mode of a behavioral grader is failing a right answer, so the
# fixtures' assertions are calibrated against the golds -- the closest thing we
# have to known-correct playbooks. Every gold that actually answers its own
# prompt must pass.
#
# Three used to fail, and each was a defect in the FIXTURE, not in the
# assertions (fixed in Phase 0 of docs/AGENT_INTELLIGENCE_PLAN.md):
#
#   hello_connector        prompt asked for smtp `send_email`; the gold calls
#                          fortisiem `get_org_name_by_org_id`. Prompt rewritten
#                          to the gold's actual behavior.
#   alert_action_var_chain prompt asked for a `find_record` on alerts; its gold
#                          (demo_alert_action.yaml) had none. Repointed at
#                          examples/demo_record_find_update.yaml, which does.
#   record_action_trigger  prompt asked for an `update_record` the gold does not
#                          contain -- and the gold was the SAME file as
#                          alert_action_var_chain's, one example serving two
#                          prompts and answering neither. Now the sole owner of
#                          demo_alert_action.yaml, prompt matched to it.
#
# A wrong gold makes `matches_example` meaningless for that row and makes the
# gold control row understate the harness. This set stays empty: if a gold
# starts failing, either the fixture drifted from its gold or an assertion
# punishes a correct answer.
KNOWN_MISMATCHED_GOLDS: set = set()


def test_every_gold_that_answers_its_prompt_passes_its_assertions():
    import pathlib

    from evals.scoring import score
    from evals.tasks import load_tasks

    failing = set()
    for t in load_tasks():
        if not t.gold_yaml_path or not t.ir_assertions:
            continue
        r = score(pathlib.Path(t.gold_yaml_path).read_text(),
                  ir_assertions=t.ir_assertions)
        if not r["levels"]["behavior"]["passed"]:
            failing.add(t.name)
    # Not `<=`: an unexpected PASS matters too. If a listed gold starts
    # passing, someone fixed the fixture and this list is now a lie.
    assert failing == KNOWN_MISMATCHED_GOLDS, (
        f"unexpected failures: {sorted(failing - KNOWN_MISMATCHED_GOLDS)}; "
        f"now-passing (update the list): "
        f"{sorted(KNOWN_MISMATCHED_GOLDS - failing)}")
