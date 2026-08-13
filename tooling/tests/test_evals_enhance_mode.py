"""`mode="enhance"` -- collateral damage from an edit becomes a number.

`verify_enhancement` has computed `step_dropped` / `step_renamed_silently` /
`behavior_changed_outside_diff` for a while, and the matrix never read any of
it: an edit that gutted the playbook scored exactly as well as a surgical one.

Three gates count here, each catching a different failure that really happened:

  behavior              the edit did what was ASKED
  no_collateral_damage  nothing else moved
  enhance_delivery      the edit reached the playbook, not the chat log

The last is the live failure the enhance scenarios were written from -- asked
to add a manual_input step, the agent verified one document and then typed
three different ones at the analyst. Every tool call returned ok.
"""
from __future__ import annotations

import importlib
import pathlib

scoring = importlib.import_module("evals.scoring")
tasks_mod = importlib.import_module("evals.tasks")

AFTER = pathlib.Path(
    "tooling/evals/golds/enhance_add_approval_gate_after.yaml").read_text()


def _task():
    return {t.name: t for t in tasks_mod.load_tasks()}["enhance_add_approval_gate"]


def _score(after: str, trace=None, text: str = ""):
    t = _task()
    return scoring.score(after, mode="enhance", before_yaml=t.broken_yaml_text(),
                         ir_assertions=t.ir_assertions, user_message=t.prompt,
                         trace=trace, final_text=text)


def _delivering_trace(after: str):
    return [
        {"name": "verify_enhancement",
         "args": {"before_yaml": _task().broken_yaml_text(), "after_yaml": after},
         "verify": {"ready_to_push": True, "verified_id": "v1"}},
        {"name": "emit_enhancement_offer", "args": {"verified_id": "v1"}},
    ]


# --- calibration ----------------------------------------------------------

def test_the_before_playbook_is_a_real_starting_point():
    # If the OPEN playbook did not compile, every row would fail for a reason
    # that has nothing to do with the edit.
    r = scoring.score(_task().broken_yaml_text())
    assert r["levels"]["draft"]["passed"] is True


def test_the_correct_edit_scores_full_marks():
    r = _score(AFTER, trace=_delivering_trace(AFTER))
    assert r["score"] == r["max"], r["levels"]
    assert r["levels"]["enhance_delivery"]["passed"] is True


def test_returning_the_playbook_unedited_fails_the_ask():
    before = _task().broken_yaml_text()
    r = _score(before, trace=_delivering_trace(before))
    assert r["levels"]["behavior"]["passed"] is False
    assert r["levels"]["no_collateral_damage"]["passed"] is True, (
        "an unedited playbook breaks nothing -- that gate must not be what "
        "catches this, or it is just a duplicate of `behavior`")


# --- the gates with teeth -------------------------------------------------

def test_dropping_an_untouched_step_while_editing_is_caught():
    gutted = AFTER.replace("""  - type: connector
    name: Enrich IP
    connector: cyops_utilities
    operation: no_op
    params: {}
    next: Confirm Block
""", "")
    gutted = gutted.replace("    next: Enrich IP", "    next: Confirm Block")
    r = _score(gutted, trace=_delivering_trace(gutted))
    assert r["levels"]["behavior"]["passed"] is True, (
        "the ASKED-for gate is still there -- only the collateral gate should "
        "fail, which is the whole point of having both")
    assert r["levels"]["no_collateral_damage"]["passed"] is False
    assert "step_dropped" in r["levels"]["no_collateral_damage"]["regressions"]


def test_silently_renaming_an_untouched_step_is_caught():
    # Breaks every external vars.steps.<slug> reference, invisibly.
    renamed = AFTER.replace("Enrich IP", "Enrich Address")
    r = _score(renamed, trace=_delivering_trace(renamed))
    assert r["levels"]["no_collateral_damage"]["passed"] is False


def test_printing_the_edit_instead_of_applying_it_fails():
    # The original defect: verified, ready_to_push, then a YAML fence in chat
    # and nothing written.
    trace = [{"name": "verify_enhancement",
              "args": {"before_yaml": _task().broken_yaml_text(),
                       "after_yaml": AFTER},
              "verify": {"ready_to_push": True, "verified_id": "v1"}}]
    r = _score(AFTER, trace=trace, text=f"Here you go:\n\n```yaml\n{AFTER}\n```")
    assert r["levels"]["enhance_delivery"]["passed"] is False
    assert r["score"] < r["max"]


# --- mode plumbing --------------------------------------------------------

def test_the_open_playbook_reaches_the_model_with_the_ask():
    from evals.harness import _user_message_for
    msg = _user_message_for(_task())
    assert "Suspicious IP Response" in msg and "```yaml" in msg


def test_enhance_counts_exactly_the_three_gates():
    r = _score(AFTER, trace=_delivering_trace(AFTER))
    counted = {k for k, v in r["levels"].items()
               if not v.get("skipped") and not v.get("informational")}
    assert counted == {"behavior", "verified", "no_collateral_damage",
                       "enhance_delivery"}, counted
