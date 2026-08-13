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


# =========================================================================
# Breadth: two more enhance fixtures, chosen so the three do not collapse
# into one test. 39 inserts into a straight line (the easy half); 42 REWIRES
# an existing step's `next:`; 43 grades a catalog-shape mistake rather than
# a wiring one.
# =========================================================================

def _for(name: str):
    """(task, gold_text, score_fn) for any enhance fixture."""
    t = {x.name: x for x in tasks_mod.load_tasks()}[name]
    gold = pathlib.Path(t.gold_yaml_path).read_text()

    def go(after: str, deliver: bool = True):
        trace = None
        if deliver:
            trace = [
                {"name": "verify_enhancement",
                 "args": {"before_yaml": t.broken_yaml_text(),
                          "after_yaml": after},
                 "verify": {"ready_to_push": True, "verified_id": "v1"}},
                {"name": "emit_enhancement_offer", "args": {"verified_id": "v1"}},
            ]
        return scoring.score(after, mode="enhance",
                             before_yaml=t.broken_yaml_text(),
                             ir_assertions=t.ir_assertions,
                             user_message=t.prompt, trace=trace, final_text="")

    return t, gold, go


# --- fixture 42: the rewire ------------------------------------------------

def test_fixture_42_gold_edit_scores_full_marks():
    t, gold, go = _for("enhance_gate_block_on_verdict")
    r = go(gold)
    assert r["score"] == r["max"], r["levels"]


def test_fixture_42_an_orphaned_decision_is_caught_by_both_gates():
    # Adding the decision without repointing `Enrich IP` leaves it
    # unreachable. `verified` sees that too (1 required fix) -- measured,
    # not assumed -- so this is NOT a behavior-only case. What behavior adds
    # is the reason: it names the missing repoint rather than "unreachable
    # step", which is the difference between a diagnostic and a grade.
    t, gold, go = _for("enhance_gate_block_on_verdict")
    orphaned = gold.replace("    next: Is It Malicious\n", "    next: Block IP\n")
    assert "next: Is It Malicious" not in orphaned

    r = go(orphaned)
    assert r["levels"]["verified"]["passed"] is False
    assert r["levels"]["behavior"]["passed"] is False
    assert "REPOINTED" in r["levels"]["behavior"]["detail"]


def test_fixture_42_a_decision_placed_after_the_block_is_behavior_only():
    # The genuinely static-invisible failure: the decision is wired in and
    # reachable, so nothing dangles and the playbook verifies -- but it sits
    # DOWNSTREAM of the block, so the IP is blocked before the verdict is
    # consulted. Exactly the request inverted, and only `behavior` objects.
    t, gold, go = _for("enhance_gate_block_on_verdict")
    inverted = gold.replace("    next: Is It Malicious\n", "    next: Block IP\n")
    inverted = inverted.replace("""  - type: decision
    name: Is It Malicious
    conditions:
    - display: Malicious
      when: '{{ vars.steps.Enrich_IP.data.reputation == "malicious" }}'
      next: Block IP
    - display: Else
      default: true
      next: End
""", "")
    inverted = inverted.replace("""    ip_addresses: '{{ vars.input.params.ip_to_investigate }}'
    next: End
""", """    ip_addresses: '{{ vars.input.params.ip_to_investigate }}'
    next: Is It Malicious
  - type: decision
    name: Is It Malicious
    conditions:
    - display: Malicious
      when: '{{ vars.steps.Enrich_IP.data.reputation == "malicious" }}'
      next: End
    - display: Else
      default: true
      next: End
""")

    r = go(inverted)
    assert r["levels"]["draft"]["passed"] is True
    assert r["levels"]["verified"]["passed"] is True, r["levels"]["verified"]
    assert r["levels"]["no_collateral_damage"]["passed"] is True
    assert r["levels"]["behavior"]["passed"] is False


# --- fixture 43: the catalog-shape mistake ---------------------------------

def test_fixture_43_gold_edit_scores_full_marks():
    t, gold, go = _for("enhance_add_incident_record")
    r = go(gold)
    assert r["score"] == r["max"], r["levels"]


def test_fixture_43_appending_the_record_past_the_block_answers_a_different_ask():
    # "after Enrich IP" is half the request. A create_record parked at the
    # end satisfies "one exists" and is not what was asked for.
    t, gold, go = _for("enhance_add_incident_record")
    appended = gold.replace("    next: Create Incident\n", "    next: Block IP\n")
    appended = appended.replace("    next: Block IP\n    - type: create_record",
                                "    next: End\n    - type: create_record")
    r = go(appended)
    assert r["levels"]["behavior"]["passed"] is False


def test_fixture_43_a_connector_step_is_not_a_create_record():
    # The scenario's own note: 'create a record' is NATIVE. An agent that
    # bolts on a connector operation instead has made the mistake the
    # fixture is named for, and every other gate is content.
    t, gold, go = _for("enhance_add_incident_record")
    as_connector = gold.replace("""  - type: create_record
    name: Create Incident
    module: incidents
    operation: Overwrite
    fields:
      name: 'Suspicious IP {{ vars.input.params.ip_to_investigate }}'
      description: >-
        Enrichment completed for {{ vars.input.params.ip_to_investigate }};
        containment pending.
    next: Block IP
""", """  - type: connector
    name: Create Incident
    connector: cyops_utilities
    operation: no_op
    params: {}
    next: Block IP
""")
    assert "type: create_record" not in as_connector

    r = go(as_connector)
    assert r["levels"]["draft"]["passed"] is True
    assert r["levels"]["no_collateral_damage"]["passed"] is True
    assert r["levels"]["behavior"]["passed"] is False


# --- fixture 44: the rename, and the grader it unblocked -------------------
#
# This fixture could not exist until `verify_enhancement` stopped calling an
# explicitly-requested rename `step_renamed_silently` at error severity. Its
# gold FAILED `no_collateral_damage` -- rule 1, a grader punishing a correct
# answer, in a call that also gates the analyst-facing #126 card.
# `fsr_playbooks/tests/test_enhancement_requested_rename.py` pins the tool
# fix; these pin the eval row.

def test_fixture_44_the_requested_rename_scores_full_marks():
    t, gold, go = _for("enhance_rename_step")
    r = go(gold)
    assert r["score"] == r["max"], r["levels"]
    # Demoted, not hidden: the analyst still sees the consequence.
    assert "step_renamed_as_requested" in r["levels"][
        "no_collateral_damage"]["warnings"]


def test_fixture_44_refusing_to_rename_does_not_score():
    # The other half of the fix. Now that the rename is permitted, an agent
    # that leaves the playbook alone breaks nothing at all -- so
    # `no_collateral_damage` is perfectly happy and `behavior` is the only
    # gate standing between "did what was asked" and "did nothing".
    t, gold, go = _for("enhance_rename_step")
    r = go(t.broken_yaml_text())
    assert r["levels"]["no_collateral_damage"]["passed"] is True
    assert r["levels"]["behavior"]["passed"] is False


def test_fixture_44_renaming_without_repointing_start_fails():
    # A rename that orphans the step is not a rename. `Start` still points
    # at a step name that no longer exists.
    t, gold, go = _for("enhance_rename_step")
    # Only the START step's pointer, and only once -- `gold.replace` on the
    # bare string would also hit the file's comment header, which is how an
    # earlier version of this test "passed" while changing nothing.
    orphaned = gold.replace("    button_label: Respond\n"
                            "    next: Reputation Lookup\n",
                            "    button_label: Respond\n"
                            "    next: Enrich IP\n", 1)
    assert orphaned != gold
    assert "next: Enrich IP" in orphaned.split("steps:")[1]

    r = go(orphaned)
    assert r["levels"]["behavior"]["passed"] is False


def test_fixture_44_renaming_a_second_step_nobody_named_still_blocks():
    # The exemption is not a licence to rewrite: it covers the step the
    # analyst named, and nothing else.
    t, gold, go = _for("enhance_rename_step")
    extra = gold.replace("name: Block IP", "name: Contain It").replace(
        "next: Block IP", "next: Contain It")
    r = go(extra)
    assert r["levels"]["no_collateral_damage"]["passed"] is False


# --- fixture 45: an ask the catalog rejects, made the thing under test -----
#
# "a field of kind ip_address" names a kind that does not exist -- the enum
# has `ipv4`. Both acceptable outcomes (author ipv4 outright, or author the
# ask literally, fail verify and fix) land on the same gold. The failure
# graded is delivering the rejected document anyway.

def test_fixture_45_gold_edit_scores_full_marks():
    t, gold, go = _for("enhance_manual_input_ip_field")
    r = go(gold)
    assert r["score"] == r["max"], r["levels"]


def test_fixture_45_the_literal_ask_does_not_compile():
    # If `kind: ip_address` compiled, the fixture would grade nothing: the
    # trap has to be real for the row to mean anything.
    t, gold, go = _for("enhance_manual_input_ip_field")
    literal = gold.replace("      kind: ipv4", "      kind: ip_address")
    assert literal != gold

    r = go(literal)
    assert r["levels"]["draft"]["passed"] is False
    assert r["levels"]["behavior"]["passed"] is False
    # ...and it cannot sneak past the collateral gate on an empty diff.
    assert r["levels"]["no_collateral_damage"]["passed"] is False


def test_fixture_45_delivering_the_rejected_yaml_scores_worse_than_not():
    # The specific live failure: the validator refused it and the agent
    # pushed it anyway. Delivery alone must not buy back the lost gates.
    t, gold, go = _for("enhance_manual_input_ip_field")
    literal = gold.replace("      kind: ipv4", "      kind: ip_address")
    assert go(literal)["score"] < go(gold)["score"]


# --- fixture 46: the read-only turn ---------------------------------------
#
# `mode="refuse"` inverts `adherence`, so "delivered nothing" is the pass.
# Both delivery paths have to fail, not just the YAML fence -- the card is
# the one that actually writes.

def _refuse_score(yaml_text: str, trace, text: str):
    t = {x.name: x for x in tasks_mod.load_tasks()}["refuse_explain_only_no_edit"]
    return scoring.score(yaml_text, mode="refuse", trace=trace,
                         final_text=text, user_message=t.prompt)


def _open_playbook():
    return {x.name: x for x in tasks_mod.load_tasks()}[
        "refuse_explain_only_no_edit"].broken_yaml_text()


def test_fixture_46_explaining_without_writing_scores_full_marks():
    r = _refuse_score("", [], "This playbook triggers on an alert, enriches "
                             "the IP, then blocks it.")
    assert r["score"] == r["max"], r["levels"]
    assert r["levels"]["adherence"]["passed"] is True


def test_fixture_46_pasting_the_playbook_back_is_an_unrequested_write():
    before = _open_playbook()
    r = _refuse_score(before, [], f"Here it is:\n\n```yaml\n{before}\n```")
    assert r["levels"]["adherence"]["passed"] is False


def test_fixture_46_emitting_a_card_fails_too_and_that_is_the_point():
    # A fixture that only caught the YAML fence would miss the path that
    # actually changes the analyst's playbook.
    before = _open_playbook()
    trace = [
        {"name": "verify_enhancement",
         "args": {"before_yaml": before, "after_yaml": before},
         "verify": {"ready_to_push": True, "verified_id": "v1"}},
        {"name": "emit_enhancement_offer", "args": {"verified_id": "v1"}},
    ]
    r = _refuse_score("", trace, "Done -- I have applied it.")
    assert r["levels"]["adherence"]["passed"] is False
    assert "emit_enhancement_offer" in r["levels"]["adherence"]["detail"]


def test_fixture_46_the_open_playbook_reaches_the_model():
    # "explain what this playbook does" has no referent without it.
    from evals.harness import _user_message_for
    t = {x.name: x for x in tasks_mod.load_tasks()}["refuse_explain_only_no_edit"]
    msg = _user_message_for(t)
    assert "Suspicious IP Response" in msg and "```yaml" in msg
