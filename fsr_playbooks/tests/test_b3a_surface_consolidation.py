"""B3a: one advertised entry point per capability.

41 tools rode on every turn (~40k chars, identical for triage and build); 17
of them were called 0-2 times in 287 live sessions on .159. They are retired
from the advertised surface -- never from REGISTRY -- each naming the union
that subsumes it. These pin the relationships a retirement can silently break.
"""
from __future__ import annotations

import re

import pytest

from fsr_playbooks.llm import tools as T


def _advertised() -> dict[str, dict]:
    return {t["name"]: t for t in T.anthropic_tools()}


def test_every_union_is_itself_advertised():
    adv = _advertised()
    for old, union in T.retired_to_union().items():
        if union in T.REGISTRY:  # host unions only exist once the host registers
            assert union in adv, f"{old} → {union}, but {union} is not advertised"


def test_retired_tools_stay_dispatchable():
    for old in T.RETIRED_TO_UNION:
        if old in T.REGISTRY:
            assert old not in _advertised()


def test_no_advertised_description_sends_the_model_to_a_retired_tool():
    retired = set(T.retired_to_union())
    for name, spec in _advertised().items():
        hits = sorted(n for n in retired
                      if re.search(rf"\b{re.escape(n)}\b", spec["description"]))
        assert not hits, f"{name}'s description names retired {hits}"


def test_openai_and_anthropic_surfaces_agree():
    assert {t["function"]["name"] for t in T.openai_tools()} == set(_advertised())


def test_the_retirements_the_live_evidence_justified():
    adv = _advertised()
    for gone in ("compile_yaml", "step_through_playbook", "dry_run_playbook",
                 "diagnose_yaml_against_pb_execution", "get_run_env",
                 "find_step_examples", "find_jinja_pattern", "get_filter_examples",
                 "propose_http_fallback", "emit_decision_step", "push_playbook",
                 "connector_health"):
        assert gone not in adv, gone


def test_host_retirement_hook(monkeypatch):
    monkeypatch.setattr(T, "_HOST_RETIRED", {})
    name = next(iter(_advertised()))
    T.retire_tools({name: "find"})
    assert name not in _advertised()
    assert T.retired_to_union()[name] == "find"


@pytest.mark.parametrize("kind,module,fn", [
    ("step", "tools_corpus", "find_step_examples"),
    ("jinja_block", "tools_jinja", "find_jinja_pattern"),
    ("filter_usage", "tools_jinja", "get_filter_examples"),
])
def test_new_find_kinds_reach_their_catalog(monkeypatch, kind, module, fn):
    import importlib

    from fsr_playbooks.mcp_server.tools_find import find
    mod = importlib.import_module(f"fsr_playbooks.mcp_server.{module}")
    seen = {}

    def fake(q, *a, **kw):
        seen["q"] = q
        return [{"hit": q}]
    monkeypatch.setattr(mod, fn, fake)
    out = getattr(find, "fn", find)(kind=kind, query="decision")
    assert seen == {"q": "decision"}
    assert out["kind"] == kind and out["results"] == [{"hit": "decision"}]


def test_find_schema_enum_matches_find_kinds():
    from fsr_playbooks.mcp_server.tools_find import FIND_KINDS
    enum = T.TOOL_SCHEMA_OVERRIDES["find"]["properties"]["kind"]["enum"]
    assert list(enum) == list(FIND_KINDS)
