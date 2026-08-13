"""`mode="repair"` -- the troubleshoot verb, which had zero coverage.

`select_diagnose_failure` graded only that the turn REACHED
`why_did_playbook_fail`; nothing ever checked whether the diagnosis was right.
A repair fixture carries a broken playbook and the condition that must hold
once it is fixed, and grades two things that are worthless apart:

  the defect is gone           -- `behavior` + `verified`
  nothing else moved          -- `no_collateral_damage`

The second is the one with teeth. Deleting the failing step clears every
diagnostic and passes the first.
"""
from __future__ import annotations

import importlib
import pathlib

scoring = importlib.import_module("evals.scoring")
tasks_mod = importlib.import_module("evals.tasks")

BROKEN = pathlib.Path(
    "tooling/evals/broken/manual_input_block_ip_bad_step_ref.yaml").read_text()
FIXED = pathlib.Path(
    "tooling/evals/golds/manual_input_block_ip.yaml").read_text()


def _task():
    return {t.name: t for t in tasks_mod.load_tasks()}["repair_bad_step_ref"]


def _score(after: str):
    t = _task()
    return scoring.score(after, mode="repair", before_yaml=BROKEN,
                         ir_assertions=t.ir_assertions,
                         user_message=t.prompt)


# --- calibration: the before-state is really broken, the fix really passes --

def test_the_broken_fixture_actually_fails_today():
    # A "broken" fixture that compiles clean would make the whole row
    # meaningless -- the agent could return it unchanged and score.
    r = scoring.score(BROKEN)
    assert r["levels"]["draft"]["passed"] is False
    assert r["levels"]["verified"]["passed"] is False


def test_the_correct_repair_scores_full_marks():
    r = _score(FIXED)
    assert r["score"] == r["max"], r["levels"]
    assert r["levels"]["no_collateral_damage"]["passed"] is True
    assert r["levels"]["behavior"]["passed"] is True


def test_returning_the_broken_playbook_unchanged_fails():
    r = _score(BROKEN)
    assert r["levels"]["verified"]["passed"] is False
    assert r["score"] < r["max"]


# --- the gate with teeth ---------------------------------------------------

def test_deleting_the_failing_step_is_caught_as_collateral_damage():
    # The tempting wrong fix: drop the connector step. Every diagnostic
    # clears, `verified` passes, and the playbook no longer does its job.
    gutted = FIXED.replace("""      - name: Block IP
        type: connector
        next: Done
        connector: fortigate-firewall
        operation: block_ip_new
        config: ""
        params:
          method: Quarantine Based
          ip_addresses: "{{ vars.steps.Analyst_IP_Action.input.target_ip }}"
""", "")
    gutted = gutted.replace("            next: Block IP", "            next: Done")
    assert "Block IP" not in gutted.split("options:")[-1]

    r = _score(gutted)
    assert r["levels"]["verified"]["passed"] is True, (
        "the point of this test is a gutted playbook that still verifies")
    assert r["levels"]["no_collateral_damage"]["passed"] is False
    assert "step_dropped" in r["levels"]["no_collateral_damage"]["regressions"]


def test_renaming_a_step_while_fixing_it_is_caught():
    # Silent rename breaks every external vars.steps.<slug> reference -- the
    # same class of bug the fixture's own defect is.
    renamed = FIXED.replace("Analyst IP Action", "Analyst Decision").replace(
        "Analyst_IP_Action", "Analyst_Decision")
    r = _score(renamed)
    assert r["levels"]["no_collateral_damage"]["passed"] is False


# --- mode plumbing ---------------------------------------------------------

def test_the_gate_skips_outside_repair_mode():
    r = scoring.score(FIXED)
    assert r["levels"]["no_collateral_damage"]["skipped"] is True


def test_a_fixture_with_no_before_yaml_skips_rather_than_passing():
    lv = scoring.score_no_collateral_damage("", FIXED)
    assert lv["skipped"] is True and lv["passed"] is False


def test_the_broken_playbook_reaches_the_model_with_the_prompt():
    # The prompt alone ("find the defect") is only half the ask; if the YAML
    # never reached the model the row would measure nothing.
    from evals.harness import _user_message_for
    msg = _user_message_for(_task())
    assert "analyst_ip_action" in msg
    assert "```yaml" in msg


def test_repair_demotes_the_gates_that_would_reward_a_rewrite():
    r = _score(FIXED)
    counted = {k for k, v in r["levels"].items()
               if not v.get("skipped") and not v.get("informational")}
    assert counted == {"behavior", "verified", "no_collateral_damage"}, counted


def test_an_uncompilable_answer_cannot_pass_the_collateral_gate():
    # verify_enhancement returns an EMPTY regression list for an `after` that
    # does not compile, and an empty list read as "nothing broke" scored the
    # echo provider 1/3 on this fixture -- a turn that delivered a stub
    # earning a gate. Unjudgeable is a failure: the analyst cannot approve
    # what does not compile.
    lv = scoring.score_no_collateral_damage(BROKEN, "playbooks: []\n")
    assert lv["skipped"] is False
    assert lv["passed"] is False
    assert "did not compile" in lv["detail"]
