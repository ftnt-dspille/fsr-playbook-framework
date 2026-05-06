"""LLM-evaluation harness smoke tests.

Uses the deterministic `gold` and `echo` providers so the suite is
hermetic — no external LLM calls. Exercises:
  - YAML extraction from fenced/raw responses
  - L1 / L3 / gold scoring gates
  - End-to-end matrix shape + per-model totals

Live gates (L2, L4) are not asserted here — they require an FSR.
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


def test_load_tasks_returns_three():
    tasks = load_tasks()
    assert len(tasks) == 3
    names = {t.name for t in tasks}
    assert names == {
        "hello_connector", "decision_branch", "alert_action_var_chain",
    }
    # Every task has a gold fixture pointer that resolves to a real file.
    for t in tasks:
        assert t.gold_yaml_text(), f"missing gold for {t.name}"


def test_score_invalid_yaml_fails_l1_l3_gold():
    out = score("collection: bad\nplaybooks: []\n", live=False)
    # Empty playbooks compiles fine actually; use a real failure.
    bad = "collection: x\nplaybooks:\n  - name: pb\n    steps: [{type: connector}]"
    out = score(bad, live=False)
    assert out["levels"]["L1"]["passed"] is False
    assert out["max"] >= 2  # L1 + L3 always counted (+ gold if passed in)


def test_score_gold_match():
    tasks = load_tasks(["hello_connector"])
    gold_yaml = tasks[0].gold_yaml_text()
    from mcp_server import compile_yaml
    gold_json = __import__("json").loads(compile_yaml(gold_yaml)["json"])
    out = score(gold_yaml, gold_json=gold_json, live=False)
    assert out["levels"]["L1"]["passed"] is True
    assert out["levels"]["L3"]["passed"] is True
    assert out["levels"]["gold"]["passed"] is True
    # L2/L4 skipped offline.
    assert out["levels"]["L2"]["skipped"] is True
    assert out["levels"]["L4"]["skipped"] is True


def test_run_matrix_gold_perfect_echo_zero():
    matrix = run_matrix(model_names=["gold", "echo"], live=False)
    assert matrix["models"] == ["gold", "echo"]
    assert len(matrix["rows"]) == 6  # 3 tasks x 2 models
    gold_total = matrix["summary"]["gold"]
    echo_total = matrix["summary"]["echo"]
    assert gold_total["fraction"] == 1.0
    assert echo_total["score"] == 0


def test_run_matrix_unknown_model_records_error():
    matrix = run_matrix(model_names=["definitely_not_a_provider"], live=False)
    assert all(r.get("error") for r in matrix["rows"])
    assert matrix["summary"]["definitely_not_a_provider"]["score"] == 0


def test_echo_provider_returns_minimal_yaml():
    out = echo_provider("sys", "user")
    assert "playbooks" in out
