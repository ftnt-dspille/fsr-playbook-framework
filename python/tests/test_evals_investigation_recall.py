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
    )
    lv = out["levels"]
    assert lv["investigation_recall"]["passed"] is True
    # Authoring tiers must not drag/help the score.
    assert lv["draft"]["informational"] is True
    assert lv["adherence"]["informational"] is True
    # The recall gate is the only counted gate -> perfect fraction.
    assert out["fraction"] == 1.0
