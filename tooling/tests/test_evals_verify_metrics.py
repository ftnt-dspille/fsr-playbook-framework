"""Unit tests for the three verify-related agentic metrics added in
Phase 4 of VERIFY_PLAYBOOK_PLAN.md."""
from __future__ import annotations

from evals.scoring import _verify_metrics, score


def _trace(*verifies):
    """Build a trace with one verify_playbook entry per arg.
    Each arg is `ready_to_push: bool`."""
    return [
        {"name": "validate_yaml", "args_chars": 1, "result_chars": 1},
        *[
            {"name": "verify_playbook", "args_chars": 10, "result_chars": 50,
             "verify": {"ready_to_push": r, "required_fix_count": 0 if r else 2,
                        "warning_count": 0}}
            for r in verifies
        ],
    ]


def test_never_called_fails():
    m = _verify_metrics([{"name": "validate_yaml"}])
    assert m["verify_called_before_submit"]["passed"] is False
    assert m["final_verify_ready_to_push"]["passed"] is False
    assert m["verify_iterations_until_ready"]["iterations"] == 0


def test_one_call_ready_passes():
    m = _verify_metrics(_trace(True))
    assert m["verify_called_before_submit"]["passed"]
    assert m["final_verify_ready_to_push"]["passed"]
    assert m["verify_iterations_until_ready"]["iterations"] == 1


def test_iterations_counted_until_first_ready():
    m = _verify_metrics(_trace(False, False, True))
    assert m["final_verify_ready_to_push"]["passed"]
    assert m["verify_iterations_until_ready"]["iterations"] == 3


def test_never_ready_fails_final_gate():
    m = _verify_metrics(_trace(False, False))
    assert m["verify_called_before_submit"]["passed"]
    assert m["final_verify_ready_to_push"]["passed"] is False


def test_last_call_wins_even_after_a_ready_one():
    # Agent reached ready then mutated YAML and a later verify failed —
    # the *last* verify determines what got shown to the user.
    m = _verify_metrics(_trace(True, False))
    assert m["final_verify_ready_to_push"]["passed"] is False
    assert m["verify_iterations_until_ready"]["iterations"] == 1


def test_score_integrates_verify_metrics_when_trace_present():
    yaml = "collection: x\nplaybooks:\n  - name: p\n    steps:\n      - name: s\n        type: start\n"
    s = score(yaml, trace=_trace(True), final_text="```yaml\nx\n```")
    assert "verify_called_before_submit" in s["levels"]
    assert s["levels"]["verify_called_before_submit"]["passed"]
    assert s["levels"]["final_verify_ready_to_push"]["passed"]


def test_score_skips_verify_metrics_when_no_trace():
    yaml = "collection: x\nplaybooks:\n  - name: p\n    steps:\n      - name: s\n        type: start\n"
    s = score(yaml, trace=None)
    for k in ("verify_called_before_submit",
              "verify_iterations_until_ready",
              "final_verify_ready_to_push"):
        assert s["levels"][k]["skipped"] is True
