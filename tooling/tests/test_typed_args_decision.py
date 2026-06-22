"""Typed-args layer: the `decision` per-step-type model (Phase 2).

`expand_decision` replaces the imperative branch-promotion in
`NormalizerMixin._normalize_decision_args`. These tests pin parity (next→
branches promotion, next stripped, original key order, non-dict pass-through,
the leave-unchanged early-returns) plus the new additive win — a mistyped
condition key is caught structurally instead of silently dropping the branch —
and assert end-to-end `compile_yaml` output is unchanged.
"""
from __future__ import annotations

from fsr_playbooks.compiler import compile_yaml
from fsr_playbooks.compiler.errors import CompileError, ErrorCode
from fsr_playbooks.compiler.typed_args import (
    STEP_ARG_MODELS,
    DecisionArgs,
    expand_decision,
    is_modeled,
)


# ── scaffold ──────────────────────────────────────────────────────────────
def test_registry_models_decision():
    assert STEP_ARG_MODELS.get("decision") is DecisionArgs
    assert is_modeled("decision") is True


# ── branch promotion parity ───────────────────────────────────────────────
def test_next_promoted_to_branches_and_stripped():
    branches: dict = {}
    errs: list[CompileError] = []
    args = {"conditions": [
        {"option": "hot", "condition": "{{ x > 1 }}", "next": "Escalate"},
        {"option": "cold", "condition": "{{ x <= 1 }}", "next": "Close"},
    ]}
    out = expand_decision(args, branches, "p", errs)
    assert errs == []
    assert branches == {"hot": "Escalate", "cold": "Close"}
    # `next` stripped; every other key preserved in original order
    assert out["conditions"] == [
        {"option": "hot", "condition": "{{ x > 1 }}"},
        {"option": "cold", "condition": "{{ x <= 1 }}"},
    ]


def test_existing_branch_not_overwritten():
    branches = {"hot": "AlreadyWired"}
    errs: list[CompileError] = []
    expand_decision(
        {"conditions": [{"option": "hot", "next": "Escalate"}]},
        branches, "p", errs)
    # setdefault semantics — pre-existing branch wins
    assert branches == {"hot": "AlreadyWired"}


def test_condition_without_next_or_option_left_alone():
    branches: dict = {}
    errs: list[CompileError] = []
    out = expand_decision(
        {"conditions": [{"option": "Else", "default": True}]},
        branches, "p", errs)
    assert errs == []
    assert branches == {}
    assert out["conditions"] == [{"option": "Else", "default": True}]


def test_non_dict_condition_passes_through():
    branches: dict = {}
    errs: list[CompileError] = []
    out = expand_decision(
        {"conditions": ["weird", {"option": "a", "next": "B"}]},
        branches, "p", errs)
    assert out["conditions"][0] == "weird"
    assert out["conditions"][1] == {"option": "a"}
    assert branches == {"a": "B"}


# ── leave-unchanged early-returns ─────────────────────────────────────────
def test_empty_args_returns_none():
    branches: dict = {}
    errs: list[CompileError] = []
    assert expand_decision({}, branches, "p", errs) is None
    assert branches == {} and errs == []


def test_conditions_not_a_list_returns_none():
    branches: dict = {}
    errs: list[CompileError] = []
    assert expand_decision({"conditions": "nope"}, branches, "p", errs) is None
    assert errs == []


def test_sibling_keys_survive():
    branches: dict = {}
    errs: list[CompileError] = []
    out = expand_decision(
        {"conditions": [{"option": "a", "next": "B"}],
         "mock_result": {"x": 1}},
        branches, "p", errs)
    assert out["mock_result"] == {"x": 1}


# ── new win: mistyped condition key caught structurally ───────────────────
def test_typo_condition_key_is_caught():
    branches: dict = {}
    errs: list[CompileError] = []
    out = expand_decision(
        {"conditions": [
            {"option": "hot", "condition": "{{ x }}", "nxt": "Escalate"}]},
        branches, "playbooks[0].steps[2]", errs)
    # structural error surfaced at the offending key
    assert any(
        e.code == ErrorCode.UNKNOWN_PARAM
        and e.path == "playbooks[0].steps[2].arguments.conditions[0].nxt"
        for e in errs)
    # output still built leniently (legacy lenience preserved): the typo'd
    # key is NOT `next`, so it stays on the cleaned condition and no branch wires
    assert out["conditions"][0] == {
        "option": "hot", "condition": "{{ x }}", "nxt": "Escalate"}
    assert branches == {}


# ── end-to-end: compile_yaml output unchanged ─────────────────────────────
_PB = """\
collection: T
playbooks:
  - name: T
    steps:
      - type: start
        name: Start
        next: D
      - type: decision
        name: D
        conditions:
          - display: hot
            when: "{{ vars.input.value > 10 }}"
            next: Hot
          - display: cold
            when: "{{ vars.input.value <= 10 }}"
            next: Cold
        default: Cold
      - type: set_variable
        name: Hot
        vars: {tier: "2"}
        next: End
      - type: set_variable
        name: Cold
        vars: {tier: "1"}
        next: End
      - type: end
        name: End
"""


def _decision_conditions(fsr_json: dict) -> list:
    for c in fsr_json.get("data", []):
        for wf in c.get("workflows", []):
            for s in wf.get("steps", []):
                if s.get("name") == "D":
                    return s["arguments"].get("conditions", [])
    return []


def test_compile_yaml_emits_wired_conditions(db_path):
    r = compile_yaml(_PB, db_path)
    assert r.ok, [e.message for e in r.errors]
    conds = _decision_conditions(r.fsr_json)
    by_option = {c.get("option"): c for c in conds if isinstance(c, dict)}
    # author's two branches present, each wired to a step_iri by the emitter
    assert "hot" in by_option and "cold" in by_option
    assert by_option["hot"]["step_iri"].startswith("/api/3/workflow_steps/")
    # `next` never leaks onto the wire
    assert all("next" not in c for c in conds if isinstance(c, dict))
    # step-level `default: Cold` synthesized an explicit default else-row
    assert any(c.get("default") for c in conds if isinstance(c, dict))
