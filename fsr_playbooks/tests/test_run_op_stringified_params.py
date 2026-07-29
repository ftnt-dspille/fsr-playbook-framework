"""Regression: run_op must accept a STRINGIFIED-JSON `params` arg.

Models routinely emit `run_op(params='{"indicator":"1.2.3.4"}')` -- params is
shown as JSON in the tool docs. Before the fix the dispatch layer left the
string as-is: the arg gate bounced it ("params: Input should be a valid
dictionary") and, when it slipped through, the op ran with no params and the
connector rejected it ("IOC/ID Value not Provided"). A live enrich-then-block
turn burned ~10 calls on this. The dispatch layer now parses a JSON-string
object back to a dict before validation and tier-resolution.
"""
from __future__ import annotations

import pytest

from fsr_playbooks.llm import tools as tools_mod
from fsr_playbooks.llm.tools import REGISTRY, ToolSpec, dispatch


@pytest.fixture
def fake_run_op(monkeypatch):
    """Register a throwaway tier-0 `run_op` that records the params it got."""
    seen: list = []

    def _fn(connector="", op="", params=None, confirm=None, **kw):
        seen.append(params)
        return {"ok": True, "echo_params": params}

    spec = ToolSpec(
        name="run_op",
        description="test-only run_op",
        input_schema={"type": "object", "properties": {}},
        fn=_fn,
        tier=0,
    )
    monkeypatch.setitem(REGISTRY, "run_op", spec)
    monkeypatch.setitem(tools_mod.TOOL_TIERS, "run_op", 0)  # execute immediately
    monkeypatch.delenv("EVAL_APPROVAL_POLICY", raising=False)
    yield seen


def test_json_string_params_parsed_to_dict(fake_run_op):
    out = dispatch("run_op", {
        "connector": "fortinet-fortiguard-ioc", "op": "ioc_search",
        "params": '{"indicator": "116.12.57.43"}',
    })
    assert out.get("ok") is True
    assert fake_run_op == [{"indicator": "116.12.57.43"}]


def test_real_dict_params_pass_through(fake_run_op):
    dispatch("run_op", {
        "connector": "c", "op": "o", "params": {"indicator": "1.2.3.4"},
    })
    assert fake_run_op == [{"indicator": "1.2.3.4"}]


def test_empty_string_params_dropped(fake_run_op):
    dispatch("run_op", {"connector": "c", "op": "o", "params": "  "})
    assert fake_run_op == [None]


def test_non_object_json_string_left_for_gate(fake_run_op):
    # A JSON string that isn't an object isn't coerced; the arg gate then
    # returns a structured error instead of executing with a bad params type.
    out = dispatch("run_op", {"connector": "c", "op": "o", "params": "[1,2,3]"})
    assert "error" in out and "params" in out["error"]
    assert fake_run_op == []  # never executed
