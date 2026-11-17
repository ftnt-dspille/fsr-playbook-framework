"""#127 step 1-2 -- the scoreboard has to be able to move, and to stop lying.

Three defects, all found by reading the detail column of a run that scored a
perfect 5/5:

1. `draft`/`verified` parsed chat PROSE as YAML, so turns that never claimed to
   emit a playbook reported "compile failed" with parse errors on markdown
   tables. Noise in the detail column is why only the summary number gets read.
2. `verify_called_before_submit` looked only for `verify_playbook`, so every
   enhance turn was marked "never called verify" for using the gate the enhance
   path *requires*.
3. `mode="tool_selection"` counted exactly one gate, so the baseline was 5/5 by
   construction -- a number that can drop but never climb is not a signal for
   improvement work.
"""
from __future__ import annotations

import importlib

scoring = importlib.import_module("evals.scoring")


def _call(name, **args):
    return {"name": name, "args": args}


PROSE = """Here is what I found.

| Detail | Value |
|---|---|
| Run | `abc-123` |

The approval id is `appr-7`, so nothing further is needed.
"""

FENCED = "Sure:\n\n```yaml\ncollection: C\nplaybooks: []\n```\n"


# --- 1. prose is not a playbook --------------------------------------------

def test_agentic_turn_with_no_yaml_delivers_nothing():
    # The turn ran tools and answered in prose. Scraping that prose is how
    # "compile failed: while parsing a block mapping" ended up describing a
    # markdown table.
    assert scoring.delivered_yaml(PROSE, [_call("list_playbook_runs")]) == ""


def test_a_fenced_block_still_counts_for_an_agentic_turn():
    got = scoring.delivered_yaml(FENCED, [_call("find_connector")])
    assert got.startswith("collection: C")


def test_a_yaml_bearing_tool_arg_still_wins_over_chat():
    trace = [_call("emit_playbook_offer", yaml="collection: FromCard\n")]
    # Returned verbatim -- this is the artifact the analyst receives.
    assert scoring.delivered_yaml(FENCED, trace) == "collection: FromCard\n"


def test_the_raw_text_fallback_survives_for_non_agentic_providers():
    # No trace = a single-shot provider (gold/echo/local model). There the
    # whole reply IS the answer and a missing fence is a formatting slip, not
    # evidence that nothing was delivered.
    assert scoring.delivered_yaml("collection: C\nplaybooks: []\n", None) != ""


def test_draft_says_nothing_was_delivered_instead_of_inventing_errors():
    r = scoring.score("", trace=[_call("run_playbook")], mode="tool_selection",
                      terminal_tool=["run_playbook"])
    draft = r["levels"]["draft"]
    assert draft["code"] == "no_yaml_delivered"
    assert draft["errors"] == []
    assert "no YAML" in draft["detail"]
    # In a mode that never expects a playbook, the tier is skipped outright.
    assert draft["skipped"] is True
    assert r["levels"]["verified"]["skipped"] is True


def test_build_mode_still_fails_a_turn_that_delivered_nothing():
    # The honesty fix must not become an escape hatch: in build mode "no YAML"
    # is the failure, it just gets an accurate label.
    r = scoring.score("", trace=[_call("find_connector")])
    assert r["levels"]["draft"]["skipped"] is False
    assert r["levels"]["draft"]["passed"] is False
    assert r["levels"]["draft"]["code"] == "no_yaml_delivered"


# --- 2. the enhance path has its own verify gate ---------------------------

def test_verify_enhancement_counts_as_verifying():
    trace = [{"name": "verify_enhancement", "args": {},
              "verify": {"ready_to_push": True}},
             _call("emit_enhancement_offer", verified_id="abc")]
    m = scoring._verify_metrics(trace)
    assert m["verify_called_before_submit"]["passed"] is True
    assert m["verify_called_before_submit"]["tools"] == ["verify_enhancement"]
    # …and the ready_to_push it returned is read, so the enhance turn does not
    # then fail the NEXT gate for the same reason.
    assert m["final_verify_ready_to_push"]["passed"] is True


def test_a_turn_that_gated_nothing_still_fails():
    m = scoring._verify_metrics([_call("find_connector")])
    assert m["verify_called_before_submit"]["passed"] is False
    assert "verify_enhancement" in m["verify_called_before_submit"]["detail"]


def test_the_detail_names_which_gate_ran():
    trace = [{"name": "verify_playbook", "args": {}, "verify": {}},
             {"name": "verify_enhancement", "args": {}, "verify": {}}]
    d = scoring._verify_metrics(trace)["verify_called_before_submit"]["detail"]
    assert "verify_playbook" in d and "verify_enhancement" in d


# --- 3. a score that can climb ---------------------------------------------

def _selection(trace, audit=None):
    return scoring.score("", trace=trace, audit=audit, mode="tool_selection",
                         terminal_tool=["emit_playbook_offer"])


def test_reaching_the_terminal_tool_is_no_longer_the_whole_verdict():
    # Offered twice: reached the terminal tool, and broke the never-offer-twice
    # bar getting there. Under the old scoreboard this was 1/1.
    # (Offering ONCE here is correct -- this fixture asked for a playbook --
    # so the single-offer trace is no longer the example of a docked row.)
    r = _selection([_call("emit_playbook_offer", yaml="x"),
                    _call("emit_playbook_offer", yaml="x")], audit=[])
    assert r["levels"]["terminal_tool_reached"]["passed"] is True
    assert r["levels"]["offer_timing"]["passed"] is False
    assert r["max"] > 1
    assert r["score"] < r["max"]


def test_the_promoted_gates_are_counted_not_informational():
    r = _selection([_call("emit_playbook_offer", yaml="x")], audit=[])
    for k in scoring._SELECTION_COUNTED_GATES:
        assert r["levels"][k].get("informational") is not True, k
    # Everything else stays informational -- research is still not credit.
    assert r["levels"]["tool_budget"]["informational"] is True


def test_a_clean_selection_turn_can_still_score_full_marks():
    trace = [_call("run_op", op="get_alert"),
             _call("emit_playbook_offer", yaml="x")]
    r = _selection(trace, audit=[])
    assert r["score"] == r["max"]
    assert r["fraction"] == 1.0


def test_over_escalation_costs_a_point_it_used_to_get_for_free():
    trace = [_call("run_op", op="get_alert"),
             _call("emit_playbook_offer", yaml="x")]
    r = _selection(trace, audit=[{"tier": 3, "name": "run_op"}])
    assert r["levels"]["appropriate_approval_requests"]["passed"] is False
    assert r["score"] == r["max"] - 1


def test_a_gate_with_no_input_is_skipped_not_counted_as_failed():
    # No audit log => the approval gate cannot be graded. It must not drag the
    # composite down; a missing instrument is not a failing agent.
    r = _selection([_call("emit_playbook_offer", yaml="x")], audit=None)
    assert r["levels"]["appropriate_approval_requests"]["skipped"] is True
    counted = [k for k, v in r["levels"].items()
               if not v.get("skipped") and not v.get("informational")]
    assert "appropriate_approval_requests" not in counted


def test_decoys_stay_diagnostic_and_never_flip_a_gate():
    trace = [_call("find_connector"), _call("run_op", op="get_alert"),
             _call("emit_playbook_offer", yaml="x")]
    r = scoring.score("", trace=trace, audit=[], mode="tool_selection",
                      terminal_tool=["emit_playbook_offer"],
                      forbidden_facts=[{"tool": "find_connector",
                                        "label": "researched connectors"}])
    term = r["levels"]["terminal_tool_reached"]
    assert term["decoys_before"] == ["researched connectors"]
    assert term["passed"] is True
    assert r["score"] == r["max"]
