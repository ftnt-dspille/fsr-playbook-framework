"""LLM-evaluation harness smoke tests.

Uses the deterministic `gold` and `echo` providers so the suite is
hermetic -- no external LLM calls. Exercises:
  - YAML extraction from fenced/raw responses
  - Compiles / gold scoring gates
  - End-to-end matrix shape + per-model totals

Live gates (Runs, Works) are not asserted here -- they require an FSR.
"""
from __future__ import annotations

import sqlite3

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
    from fsr_playbooks.mcp_server import compile_yaml
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


# ---------------------------------------------------------------------------
# Crash durability. `save_run` writes only after the WHOLE matrix finishes, so
# without a per-row checkpoint any late failure discards every completed
# result -- a transient sqlite error at task 34/36 once cost a 74-minute run.
# ---------------------------------------------------------------------------

def test_checkpoint_survives_a_crash_mid_run(tmp_path, monkeypatch):
    """A run that dies partway must leave its finished rows on disk."""
    from evals import harness

    path = tmp_path / "rows.jsonl"
    tasks = [t.name for t in load_tasks(None)][:3]
    boom = tasks[-1]

    real_score = harness.score

    def exploding_score(*a, **kw):
        # Blow up the way the real crash did: inside scoring, not the provider.
        if exploding_score.calls >= 2:
            raise sqlite3.OperationalError("disk I/O error")
        exploding_score.calls += 1
        return real_score(*a, **kw)
    exploding_score.calls = 0
    monkeypatch.setattr(harness, "score", exploding_score)

    harness.run_matrix(model_names=["echo"], task_names=tasks,
                       checkpoint_path=path)

    recovered = harness.recover_rows(path)
    assert len(recovered) == 3, "every attempted task should be checkpointed"
    assert [r["task"] for r in recovered] == tasks
    # The scoring failure is recorded, not fatal, and names itself.
    assert any(r.get("error", "").startswith("scoring:") for r in recovered)
    assert boom in [r["task"] for r in recovered]


def test_scoring_failure_does_not_abort_the_matrix(monkeypatch):
    """One bad task must not discard the tasks that already succeeded."""
    from evals import harness

    tasks = [t.name for t in load_tasks(None)][:3]
    real_score = harness.score

    def flaky(*a, **kw):
        flaky.calls += 1
        if flaky.calls == 1:
            raise sqlite3.OperationalError("disk I/O error")
        return real_score(*a, **kw)
    flaky.calls = 0
    monkeypatch.setattr(harness, "score", flaky)

    matrix = harness.run_matrix(model_names=["echo"], task_names=tasks)
    assert len(matrix["rows"]) == 3, "a scoring crash truncated the matrix"
    assert sum(1 for r in matrix["rows"] if "error" in r) == 1


def test_recover_rows_tolerates_a_torn_final_line(tmp_path):
    """A hard kill can cut the last write mid-object."""
    from evals.harness import recover_rows

    p = tmp_path / "rows.jsonl"
    p.write_text('{"task": "a", "score": 1}\n{"task": "b", "sco')
    rows = recover_rows(p)
    assert [r["task"] for r in rows] == ["a"]
