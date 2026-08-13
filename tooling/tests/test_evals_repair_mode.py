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


def _calibrate(name: str):
    """(gold row, broken row) for a repair fixture, scored as the matrix does."""
    t = {x.name: x for x in tasks_mod.load_tasks()}[name]
    before = t.broken_yaml_text()
    gold = pathlib.Path(t.gold_yaml_path).read_text()

    def go(after):
        return scoring.score(after, mode="repair", before_yaml=before,
                             ir_assertions=t.ir_assertions,
                             user_message=t.prompt)

    return go(gold), go(before), gold, before, go


# --- fixture 40: the containment shape that bans nothing -------------------
#
# `block_ip_new` Address Based with the singular `ip` answers Success on a real
# appliance with every result bucket empty -- live-verified on the lab
# FortiGate. The prompt gives the agent exactly that symptom.
#
# Calibration surprise worth keeping: the compiler ALREADY catches this, as a
# `param-set conflict`, so the before-state fails `draft` rather than sliding
# past every static gate. That is a product fact, not an assumption, and it is
# why `repair_loop_over_wrong_field` exists -- without it the repair corpus
# would be nothing but compile failures.

def test_fixture_40_gold_passes_and_the_broken_containment_does_not():
    gold_r, broken_r, *_ = _calibrate("repair_wrong_containment_param")
    assert gold_r["score"] == gold_r["max"], gold_r["levels"]
    assert broken_r["levels"]["behavior"]["passed"] is False
    # The specific defect, not just "something failed".
    assert "ip_addresses" in broken_r["levels"]["behavior"]["detail"]


def test_fixture_40_deleting_the_block_is_caught_only_by_collateral_damage():
    # The cheapest way to silence "the firewall banned nothing" is to stop
    # calling the firewall. Every diagnostic clears.
    _, _, gold, _, go = _calibrate("repair_wrong_containment_param")
    gutted = gold.replace("""      - name: Block High Score IPs
        type: connector
        next: Comment On Alert
        connector: fortigate-firewall
        operation: block_ip_new
        config: ""
        params:
          method: Quarantine Based
          ip_addresses: "{{ vars.item }}"
        for_each:
          item: "{{ vars.high_ips }}"
          parallel: false
""", "")
    gutted = gutted.replace("            next: Block High Score IPs",
                            "            next: Comment On Alert")
    assert "Block High Score IPs" not in gutted

    r = go(gutted)
    assert r["levels"]["verified"]["passed"] is True, (
        "the point of this test is a gutted playbook that still verifies")
    assert r["levels"]["no_collateral_damage"]["passed"] is False
    assert "step_dropped" in r["levels"]["no_collateral_damage"]["regressions"]


# --- fixture 41: the tier no static gate can see ---------------------------
#
# Iterating `vars.input.records` instead of `records[0].sender_ips` is a
# perfectly legal playbook: it compiles, it verifies, and it scores exactly one
# thing per run. `for_each_over` is the only gate that can tell.

def test_fixture_41_broken_loop_compiles_and_verifies_and_still_fails():
    gold_r, broken_r, *_ = _calibrate("repair_loop_over_wrong_field")
    assert gold_r["score"] == gold_r["max"], gold_r["levels"]
    assert broken_r["levels"]["draft"]["passed"] is True
    assert broken_r["levels"]["verified"]["passed"] is True
    assert broken_r["levels"]["no_collateral_damage"]["passed"] is True
    # ...and the row is still not full marks, because behavior sees it.
    assert broken_r["levels"]["behavior"]["passed"] is False
    assert broken_r["score"] < broken_r["max"]


def test_fixture_41_unrolling_the_loop_disagrees_with_the_collateral_gate():
    # Rule 3 of the plan: a pair of gates that always agree is one gate
    # wearing two names. Dropping the loop and scoring the whole list in one
    # call silences the symptom without dropping or renaming a step -- so
    # `no_collateral_damage` is content and only `behavior` objects.
    _, _, gold, _, go = _calibrate("repair_loop_over_wrong_field")
    unrolled = gold.replace("""          ip: "{{ vars.item }}"
        for_each:
          item: "{{ vars.input.records[0].sender_ips }}"
          parallel: false
""", """          ip: "{{ vars.input.records[0].sender_ips }}"
""")
    assert "vars.item" not in unrolled.split("Collect High Scores")[0]

    r = go(unrolled)
    assert r["levels"]["no_collateral_damage"]["passed"] is True
    assert r["levels"]["behavior"]["passed"] is False


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
