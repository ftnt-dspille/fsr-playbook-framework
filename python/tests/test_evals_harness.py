"""LLM-evaluation harness smoke tests.

Uses the deterministic `gold` and `echo` providers so the suite is
hermetic — no external LLM calls. Exercises:
  - YAML extraction from fenced/raw responses
  - Compiles / gold scoring gates
  - End-to-end matrix shape + per-model totals

Live gates (Runs, Works) are not asserted here — they require an FSR.
"""
from __future__ import annotations

import pytest

pytest.importorskip("mcp.server.fastmcp",
                    reason="mcp package not installed")

from evals.harness import run_matrix  # noqa: E402
from evals.providers import echo_provider, extract_yaml  # noqa: E402
from evals.scoring import score  # noqa: E402
from evals.tasks import load_tasks  # noqa: E402


def test_extract_yaml_strips_fence():
    assert extract_yaml("blah\n```yaml\nfoo: 1\n```\nblah") == "foo: 1"


def test_extract_yaml_falls_back_to_raw():
    assert extract_yaml("foo: 1") == "foo: 1"


def test_load_tasks_corpus():
    """Phase-3A expanded corpus to 15 tasks. The original three remain
    present; every task with a gold path resolves to a real fixture."""
    tasks = load_tasks()
    assert len(tasks) >= 15
    names = {t.name for t in tasks}
    for must_have in ("hello_connector", "decision_branch",
                      "alert_action_var_chain"):
        assert must_have in names
    for t in tasks:
        if t.gold_yaml_path:
            assert t.gold_yaml_text(), f"missing gold for {t.name}"


def test_score_invalid_yaml_fails_draft_and_verified():
    bad = "collection: x\nplaybooks:\n  - name: pb\n    steps: [{type: connector}]"
    out = score(bad, live=False)
    assert out["levels"]["draft"]["passed"] is False
    assert out["levels"]["verified"]["passed"] is False
    # draft + verified + matches_example(skipped) + live(skipped) → max ≥ 2
    assert out["max"] >= 2


def test_score_gold_match():
    tasks = load_tasks(["hello_connector"])
    gold_yaml = tasks[0].gold_yaml_text()
    from mcp_server import compile_yaml
    gold_json = __import__("json").loads(compile_yaml(gold_yaml, verbose=True)["json"])
    out = score(gold_yaml, gold_json=gold_json, live=False)
    assert out["levels"]["draft"]["passed"] is True
    assert out["levels"]["matches_example"]["passed"] is True
    # live_tested skipped offline.
    assert out["levels"]["live_tested"]["skipped"] is True


def test_run_matrix_gold_beats_echo():
    matrix = run_matrix(model_names=["gold", "echo"], live=False)
    assert matrix["models"] == ["gold", "echo"]
    n_tasks = len(matrix["tasks"])
    assert len(matrix["rows"]) == 2 * n_tasks
    gold_total = matrix["summary"]["gold"]
    echo_total = matrix["summary"]["echo"]
    # Gold won't be 100% because the strict-whitelist sub-check flags some
    # legacy fixtures, several harder tasks (soc_*, noc_*, itops_*,
    # jinja_chain_*) have no gold reference yet, and `matches_example` is
    # now informational so it no longer lifts the gold provider's ceiling.
    # Just assert the order and that gold dominates echo.
    assert gold_total["fraction"] >= 0.55
    assert echo_total["score"] == 0


def test_run_matrix_unknown_model_records_error():
    matrix = run_matrix(model_names=["definitely_not_a_provider"], live=False)
    assert all(r.get("error") for r in matrix["rows"])
    assert matrix["summary"]["definitely_not_a_provider"]["score"] == 0


def test_echo_provider_returns_minimal_yaml():
    out = echo_provider("sys", "user")
    assert "playbooks" in out
