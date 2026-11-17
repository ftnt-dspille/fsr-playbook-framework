"""Enhance bucket: grade whether the agent DELIVERED the edit, not whether its
tool calls returned ok.

The gap this closes, from a live appliance: asked "how does a manual input step
work, can you add one", the agent called `verify_enhancement`, got
`ready_to_push: True`, and then printed the revised playbook into chat three
times -- each rendering subtly different from the verified one. Nothing was
written. Every tool call in that transcript returned ok, so nothing that graded
tool errors could see the failure; the analyst asked twice more and got two more
walls of YAML.

`score_enhance_delivery` grades the delivery, so the defect has a failing test
before it has a live repro. These scenarios are deterministic -- synthetic
traces, no LLM, no box -- so they run in CI. Whether the MODEL reaches for the
tool is a separate, live-graded question; this pins that the harness can TELL.
"""
from __future__ import annotations

from tooling.evals.scoring import score_enhance_delivery

VID = "0a86f7c1b0c9d221"
FULL_PB = "Here is the revised playbook:\n\n```yaml\nplaybooks:\n- name: PB\n```\n"


def _verify(vid: str | None = VID, ready: bool = True) -> dict:
    return {"name": "verify_enhancement",
            "args": {"before_yaml": "x", "after_yaml": "y"},
            "result": {"ready_to_push": ready, "verified_id": vid if ready else None}}


def _offer(vid: str = VID) -> dict:
    return {"name": "emit_enhancement_offer",
            "args": {"id": "e1", "summary": "s", "verified_id": vid}}


def test_the_happy_path_passes():
    r = score_enhance_delivery([_verify(), _offer()], "Added the approval gate.")
    assert r["passed"] and not r["skipped"]


def test_the_live_defect_fails():
    """Verified, then printed the playbook instead of applying it.

    This is the exact transcript shape captured live. If this ever passes, the
    bucket has stopped measuring the thing it was built for.
    """
    r = score_enhance_delivery([_verify()], FULL_PB)
    assert r["passed"] is False
    assert r["code"] == "printed_instead_of_applied"


def test_verified_but_silent_fails():
    """No fence, no offer -- the edit still never happened."""
    r = score_enhance_delivery([_verify()], "I've added the step.")
    assert r["passed"] is False
    assert r["code"] == "verified_not_applied"


def test_declining_to_deliver_a_broken_edit_passes():
    """A red verify with no delivery is CORRECT behaviour, not a miss.

    Grading this as a failure would push the agent toward shipping edits that
    did not pass -- the opposite of the point.
    """
    r = score_enhance_delivery([_verify(vid=None, ready=False)],
                               "That edit doesn't validate yet because…")
    assert r["passed"] is True


def test_delivering_an_id_no_verify_issued_fails():
    """Structurally impossible through the tool -- so it means a bypass."""
    r = score_enhance_delivery([_verify(), _offer("deadbeefdeadbeef")])
    assert r["passed"] is False
    assert r["code"] == "unverified_delivery"


def test_delivering_without_an_id_fails():
    r = score_enhance_delivery([_verify(), _offer("")])
    assert r["passed"] is False
    assert r["code"] == "unverified_delivery"


def test_offering_twice_fails():
    r = score_enhance_delivery([_verify(), _offer(), _offer()])
    assert r["passed"] is False
    assert r["code"] == "offered_twice"


def test_a_read_only_turn_skips():
    r = score_enhance_delivery([{"name": "analyze_playbook", "args": {}}],
                               "This playbook enriches then blocks.")
    assert r["skipped"] is True
    assert r["passed"] is True


def test_a_snippet_alongside_the_offer_passes_but_is_flagged():
    """Showing the changed step is encouraged; a whole playbook is the old bug.

    We can't reliably tell a snippet from a document, so pass and flag rather
    than guess -- a false failure here would train the agent out of explaining
    its edit at all.
    """
    r = score_enhance_delivery([_verify(), _offer()], FULL_PB)
    assert r["passed"] is True
    assert r.get("needs_review") is True


def test_results_absent_from_the_trace_still_grade():
    """Some harnesses don't thread tool results onto the call record. The gate
    must degrade to grading the CALL SHAPE rather than skipping silently -- a
    gate that quietly stops measuring is worse than no gate."""
    trace = [{"name": "verify_enhancement", "args": {}}, _offer()]
    r = score_enhance_delivery(trace, "Applied.")
    assert r["passed"] is True and not r["skipped"]


# --- the scenario fixtures themselves ---------------------------------------
# A scenario whose `before_yaml` doesn't parse grades nothing: every run fails
# for a reason that has nothing to do with the agent. Validate the fixtures.

def _scenarios():
    import json
    from pathlib import Path
    d = Path(__file__).resolve().parents[1] / "evals" / "enhance_scenarios"
    return [(p.name, json.loads(p.read_text()))
            for p in sorted(d.glob("*.json"))]


def test_enhance_scenarios_are_well_formed():
    scs = _scenarios()
    assert scs, "the enhance bucket must not be empty"
    for fname, sc in scs:
        for key in ("name", "prompt", "before_yaml", "expect", "notes"):
            assert sc.get(key), f"{fname} missing {key!r}"
        assert sc["name"] == fname[:-len(".json")], f"{fname} name mismatch"


def test_enhance_scenario_before_yaml_compiles():
    """The mounted OPEN PLAYBOOK must be a VALID playbook.

    Otherwise `verify_enhancement`'s before-side is unparseable, the regression
    diff silently degrades to a build-mode verify, and the scenario stops
    measuring the thing it names.
    """
    from fsr_playbooks._db import default_db_path
    from fsr_playbooks.compiler import compile_yaml
    for fname, sc in _scenarios():
        res = compile_yaml(sc["before_yaml"], default_db_path())
        assert res.ok, (f"{fname} before_yaml does not compile: "
                        f"{[e.message for e in res.errors]}")


def test_the_read_only_scenario_expects_no_delivery():
    """Guards the inverse failure: a bucket that only rewards delivering edits
    would train the agent to edit on a 'just explain it' turn."""
    by_name = dict(_scenarios())
    ro = by_name["e4_explain_only_no_edit.json"]
    assert ro["expect"]["delivery"] == "none"
    assert ro["expect"]["no_yaml_fence"] is True


def _edit(vid: str | None = VID, ready: bool = True) -> dict:
    return {"name": "edit_playbook",
            "args": {"operations": [{"op": "add_step", "after": "Start",
                                     "step": {"name": "Gate", "type": "manual_input"}}]},
            "result": {"ready_to_push": ready, "verified_id": vid if ready else None,
                       "after_yaml": "playbooks:\n- name: PB\n"}}


def test_an_edit_playbook_delivery_passes():
    """The prompt routes every designer edit through edit_playbook, which runs
    verify_enhancement and issues the verified_id. Scoring only
    verify_enhancement graded that correct path `no_verify`."""
    r = score_enhance_delivery([_edit(), _offer()], "Added the approval gate.")
    assert r["passed"] and not r["skipped"], r


def test_an_edit_playbook_turn_that_prints_yaml_still_fails():
    r = score_enhance_delivery([_edit()], FULL_PB)
    assert not r["passed"] and r["code"] == "printed_instead_of_applied"


def test_verify_gates_share_one_source_with_the_loop_guards():
    from fsr_playbooks.llm._loop_helpers import _ENHANCE_VERIFY_TOOLS
    from tooling.evals import providers, scoring
    assert set(_ENHANCE_VERIFY_TOOLS) <= set(scoring._VERIFY_TOOLS)
    assert set(_ENHANCE_VERIFY_TOOLS) <= providers._VERIFY_TOOL_NAMES


def test_delivered_yaml_reads_edit_playbook_result():
    from tooling.evals.scoring import delivered_yaml
    assert delivered_yaml("done", [_edit()]) == "playbooks:\n- name: PB\n"


def test_a_consolidated_emit_card_delivery_counts():
    """Live 09-28: enhance-live graded 9/10 `verified_not_applied` because the
    delivery arrived as emit_card(card_type='enhancement_offer') and the live
    runner scored the raw trace."""
    card = {"name": "emit_card",
            "args": {"card_type": "enhancement_offer",
                     "payload": {"id": "e1", "summary": "s", "verified_id": VID}},
            "result": {"ok": True}}
    r = score_enhance_delivery([_edit(), card], "Added the approval gate.")
    assert r["passed"] and not r["skipped"], r


def test_a_refused_offer_then_a_good_one_is_one_delivery():
    refused = {"name": "emit_card",
               "args": {"card_type": "enhancement_offer",
                        "payload": {"id": "e1", "verified_id": "bogus"}},
               "result": {"ok": False, "code": "unknown_verified_id"}}
    good = {"name": "emit_card",
            "args": {"card_type": "enhancement_offer",
                     "payload": {"id": "e1", "summary": "s", "verified_id": VID}},
            "result": {"ok": True}}
    r = score_enhance_delivery([_edit(), refused, good], "done")
    assert r["passed"], r
