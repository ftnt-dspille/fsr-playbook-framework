"""Investigation-quality eval scoring (Phase 1.4 — Part A).

`mode="investigation"` grades a triage/hunt task on **pivot recall**
(required tool-calls the agent performed / required), not YAML shape, with
a hard fail on any forbidden pivot (e.g. external TI on an internal IP).
"""
from __future__ import annotations

import importlib

scoring = importlib.import_module("evals.scoring")


# --- _fact_matches ----------------------------------------------------------

def _call(name, **args):
    return {"name": name, "args": args}


def test_matches_tool_connector_op_and_indicator():
    fact = {"tool": "run_op", "connector": "virustotal",
            "op": "get_ip_reputation", "args_contains": ["203.0.113.5"]}
    call = _call("run_op", connector="virustotal", op="get_ip_reputation",
                 params={"ip": "203.0.113.5"})
    assert scoring._fact_matches(fact, call) is True


def test_no_match_wrong_op():
    fact = {"tool": "run_op", "connector": "virustotal", "op": "get_ip_reputation"}
    assert scoring._fact_matches(
        fact, _call("run_op", connector="virustotal", op="get_domain_reputation")
    ) is False


def test_no_match_missing_indicator():
    fact = {"tool": "run_op", "connector": "virustotal",
            "args_contains": ["203.0.113.5"]}
    call = _call("run_op", connector="virustotal", params={"ip": "10.0.0.1"})
    assert scoring._fact_matches(fact, call) is False


def test_get_record_module_match():
    fact = {"tool": "get_record", "module": "alerts"}
    assert scoring._fact_matches(fact, _call("get_record", module="alerts")) is True
    assert scoring._fact_matches(fact, _call("get_record", module="incidents")) is False


def test_handles_legacy_input_key():
    # Older trace entries used `input` instead of `args`.
    fact = {"tool": "run_op", "connector": "shodan"}
    call = {"name": "run_op", "input": {"connector": "shodan", "op": "host"}}
    assert scoring._fact_matches(fact, call) is True


# --- _score_investigation ---------------------------------------------------

def test_full_recall_passes():
    required = [
        {"tool": "get_record", "module": "alerts", "label": "fetch alert"},
        {"tool": "run_op", "connector": "virustotal", "args_contains": ["1.2.3.4"]},
    ]
    trace = [
        _call("get_record", module="alerts", uuid="x"),
        _call("run_op", connector="virustotal", params={"ip": "1.2.3.4"}),
    ]
    res = scoring._score_investigation(trace, required, [])
    assert res["passed"] is True and res["recall"] == 1.0
    assert res["missing"] == []


def test_partial_recall_below_gate_fails():
    required = [
        {"tool": "get_record", "module": "alerts"},
        {"tool": "run_op", "connector": "virustotal", "args_contains": ["1.2.3.4"]},
        {"tool": "run_op", "connector": "shodan", "args_contains": ["1.2.3.4"]},
    ]
    trace = [_call("get_record", module="alerts", uuid="x")]  # 1/3 = 0.33
    res = scoring._score_investigation(trace, required, [])
    assert res["passed"] is False
    assert res["matched"] == 1 and res["required"] == 3
    assert len(res["missing"]) == 2


def test_forbidden_pivot_hard_fails_even_at_full_recall():
    required = [{"tool": "get_record", "module": "alerts"}]
    forbidden = [{"tool": "run_op", "connector": "virustotal",
                  "args_contains": ["10.0.0.5"], "label": "VT on internal IP"}]
    trace = [
        _call("get_record", module="alerts", uuid="x"),
        _call("run_op", connector="virustotal", params={"ip": "10.0.0.5"}),
    ]
    res = scoring._score_investigation(trace, required, forbidden)
    assert res["recall"] == 1.0
    assert res["passed"] is False
    assert "VT on internal IP" in res["forbidden_hit"]


# --- score() integration ----------------------------------------------------

# --- _score_investigation_quality (Phase 1.4 strengthening) -----------------

def _good_invest_trace():
    """A clean 4-call investigation that should clear every quality gate."""
    return [
        _call("get_record", module="alerts", uuid="x"),
        _call("search_module_records", module="incidents", q="1.2.3.4"),
        _call("run_op", connector="virustotal", op="get_ip_report",
              params={"ip": "1.2.3.4"}),
        _call("emit_action_card", connector="virustotal", op="block_ip"),
    ]


def test_quality_all_gates_pass_on_clean_trace():
    q = scoring._score_investigation_quality(_good_invest_trace(), {})
    assert q["investigation_tool_budget"]["passed"] is True
    assert q["investigation_no_param_flail"]["passed"] is True
    assert q["investigation_deliverable"]["passed"] is True


def test_quality_tool_budget_fails_on_flailing_run():
    trace = [_call("get_record", uuid="x") for _ in range(13)]
    q = scoring._score_investigation_quality(trace, {"tool_budget_max": 12})
    assert q["investigation_tool_budget"]["passed"] is False
    assert q["investigation_tool_budget"]["calls"] == 13


def test_quality_param_flail_detected():
    # Same connector+op invoked with 3 distinct arg-sets = grounding flail.
    trace = [
        _call("run_op", connector="fortiguard", op="threat_intel_search",
              params={"ip": "1.2.3.4"}),
        _call("run_op", connector="fortiguard", op="threat_intel_search",
              params={"ip_address": "1.2.3.4"}),
        _call("run_op", connector="fortiguard", op="threat_intel_search",
              params={"indicator": "1.2.3.4"}),
    ]
    q = scoring._score_investigation_quality(trace, {"max_param_retries": 2})
    flail = q["investigation_no_param_flail"]
    assert flail["passed"] is False
    assert flail["worst_distinct_argsets"] == 3
    assert flail["op"] == "fortiguard.threat_intel_search"


def test_quality_param_flail_ignores_confirm_retry():
    # A retry that only adds `confirm: true` is the designed confirm-gate
    # path, NOT a param guess — must collapse to one distinct arg-set.
    trace = [
        _call("run_op", connector="vt", op="lookup", params={"ip": "1.2.3.4"}),
        _call("run_op", connector="vt", op="lookup", params={"ip": "1.2.3.4"},
              confirm=True),
    ]
    q = scoring._score_investigation_quality(trace, {"max_param_retries": 2})
    assert q["investigation_no_param_flail"]["worst_distinct_argsets"] == 1


def test_quality_deliverable_credits_choice_card():
    # No containment op configured -> emit_choice_card is the correct ending.
    trace = [
        _call("get_record", uuid="x"),
        _call("emit_choice_card", options=["monitor", "escalate"]),
    ]
    q = scoring._score_investigation_quality(trace, {"require_deliverable": True})
    d = q["investigation_deliverable"]
    assert d["passed"] is True and "emit_choice_card" in d["staged"]


def test_quality_deliverable_fails_when_none_staged():
    trace = [_call("get_record", uuid="x"), _call("run_op", connector="vt")]
    q = scoring._score_investigation_quality(trace, {"require_deliverable": True})
    assert q["investigation_deliverable"]["passed"] is False


def test_quality_deliverable_skipped_when_not_required():
    trace = [_call("get_record", uuid="x")]
    q = scoring._score_investigation_quality(trace, {"require_deliverable": False})
    assert q["investigation_deliverable"]["skipped"] is True


def test_score_investigation_quality_gates_counted_and_can_fail():
    # Full recall but 13 calls + no deliverable -> overall fraction < 1.0.
    required = [{"tool": "get_record", "module": "alerts"}]
    trace = [_call("get_record", module="alerts", uuid="x")]
    trace += [_call("get_record", module="alerts", uuid="x") for _ in range(12)]
    out = scoring.score(
        "", trace=trace, final_text="verdict", mode="investigation",
        required_facts=required,
        investigation_quality={"tool_budget_max": 12, "require_deliverable": True},
    )
    lv = out["levels"]
    assert lv["investigation_recall"]["passed"] is True
    assert lv["investigation_tool_budget"]["passed"] is False
    assert lv["investigation_deliverable"]["passed"] is False
    # The loose authoring tool_budget must be demoted (not double-counted).
    assert lv["tool_budget"].get("informational") is True
    assert out["fraction"] < 1.0


def test_score_investigation_mode_demotes_authoring_gates():
    trace = [
        _call("get_record", module="alerts", uuid="x"),
        _call("run_op", connector="virustotal", op="get_ip_reputation",
              params={"ip": "1.2.3.4"}),
    ]
    required = [
        {"tool": "get_record", "module": "alerts"},
        {"tool": "run_op", "connector": "virustotal", "args_contains": ["1.2.3.4"]},
    ]
    out = scoring.score(
        "",  # no YAML — investigation tasks don't author
        trace=trace, final_text="Investigated the alert; IP is malicious.",
        mode="investigation", required_facts=required,
        # Isolate the demotion check from the deliverable gate (tested above).
        investigation_quality={"require_deliverable": False},
    )
    lv = out["levels"]
    assert lv["investigation_recall"]["passed"] is True
    # Authoring tiers must not drag/help the score.
    assert lv["draft"]["informational"] is True
    assert lv["adherence"]["informational"] is True
    # The loose authoring tool_budget is demoted in favor of the tighter
    # investigation ceiling.
    assert lv["tool_budget"].get("informational") is True
    # Recall + the two active quality gates all pass -> perfect fraction.
    assert out["fraction"] == 1.0
