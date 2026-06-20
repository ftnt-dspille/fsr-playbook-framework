"""Offer-timing eval dimension (SKILL_BASED_PLAYBOOK_PLAN §6 / TODO Track A4).

Grades whether the agent called `emit_playbook_offer` at the right moment,
read straight from the tool-use trace. Informational in `score()` so it tracks
prompt regressions without skewing the YAML-authoring score.
"""
from __future__ import annotations

import importlib

scoring = importlib.import_module("evals.scoring")


def _run_op(connector, op):
    return {"name": "run_op", "args": {"connector": connector, "op": op}}


def _offer():
    return {"name": "emit_playbook_offer", "args": {"id": "x", "summary": "s"}}


def test_offered_once_after_containment_passes():
    trace = [_run_op("virustotal", "get_ip_report"),
             _run_op("fortiedr", "isolate_host"),
             _offer()]
    lv = scoring.score_offer_timing(trace)
    assert lv["passed"] is True and lv["offers"] == 1
    assert "containment" in lv["detail"]


def test_no_offer_no_containment_passes():
    trace = [_run_op("virustotal", "get_ip_report"),
             _run_op("abuseipdb", "lookup_ip")]
    lv = scoring.score_offer_timing(trace)
    assert lv["passed"] is True and lv["offers"] == 0


def test_containment_without_offer_fails():
    trace = [_run_op("fortiedr", "isolate_host")]
    lv = scoring.score_offer_timing(trace)
    assert lv["passed"] is False and lv["offers"] == 0


def test_offered_twice_fails():
    trace = [_run_op("fortiedr", "isolate_host"), _offer(), _offer()]
    lv = scoring.score_offer_timing(trace)
    assert lv["passed"] is False and lv["offers"] == 2


def test_offered_before_any_action_fails():
    trace = [_offer(), _run_op("fortiedr", "isolate_host")]
    lv = scoring.score_offer_timing(trace)
    assert lv["passed"] is False
    assert "premature" in lv["detail"]


def test_offered_after_read_only_only_passes_with_review_flag():
    trace = [_run_op("virustotal", "get_ip_report"), _offer()]
    lv = scoring.score_offer_timing(trace)
    assert lv["passed"] is True
    assert lv.get("needs_review") is True


def test_score_includes_informational_offer_timing_level():
    trace = [_run_op("fortiedr", "isolate_host"), _offer()]
    out = scoring.score("", trace=trace)
    ot = out["levels"]["offer_timing"]
    assert ot["informational"] is True
    assert ot["passed"] is True


def test_score_skips_offer_timing_when_no_trace():
    out = scoring.score("", trace=None)
    assert out["levels"]["offer_timing"]["skipped"] is True
