"""tool_selection scores the right tool for the situation against known lists."""
from __future__ import annotations

from tooling.evals.corpus_authoring import tool_selection as ts


def test_reaching_for_debug_run_is_right():
    g = ts.grade_tool_selection(
        ["verify_playbook", "debug_run", "repair_playbook"],
        "runtime_output_dependency")
    assert g["selected_right"] is True
    assert g["brute_forced"] is False
    assert g["expected"] == "debug_run"


def test_compile_loop_without_debug_is_brute_force():
    g = ts.grade_tool_selection(
        ["compile_playbook_yaml", "verify_playbook", "compile_playbook_yaml"],
        "runtime_output_dependency")
    assert g["selected_right"] is False
    assert g["brute_forced"] is True


def test_no_tools_at_all_is_a_miss_not_brute_force():
    g = ts.grade_tool_selection([], "runtime_output_dependency")
    assert g["selected_right"] is False
    assert g["brute_forced"] is False


def test_mcp_prefixes_are_stripped():
    g = ts.grade_tool_selection(
        ["mcp__fsr-agentic-toolkit__debug_run"], "runtime_output_dependency")
    assert g["selected_right"] is True
    assert g["called"] == ["debug_run"]


def test_unknown_situation_scores_none_not_false():
    g = ts.grade_tool_selection(["compile_playbook_yaml"], "authoring")
    assert g["selected_right"] is None  # no intended diagnostic to expect


def test_aggregate_rates_and_histogram():
    rows = [
        ts.grade_tool_selection(["debug_run", "verify_playbook"],
                                "runtime_output_dependency"),
        ts.grade_tool_selection(["compile_playbook_yaml"],
                                "runtime_output_dependency"),
        ts.grade_tool_selection(["compile_playbook_yaml"], "authoring"),  # None
    ]
    agg = ts.aggregate(rows)
    assert agg["selected_right"] == "1/2"   # the None row is excluded
    assert agg["brute_forced"] == "1/2"
    assert agg["tool_histogram"]["compile_playbook_yaml"] == 2
