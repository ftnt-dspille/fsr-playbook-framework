"""One argument gate for every registered tool (tracker #172, W1).

The gate refuses a call whose arguments can't be right BEFORE the tool runs,
and says how to fix it in one retry. Replayed against ~23.5k recorded calls it
refused 2 that had "worked", both genuinely wrong, and caught 104 failures
with a named fix instead of a raw TypeError or an error from deep in a tool.
"""
from __future__ import annotations

import dataclasses
import inspect

import pytest

from fsr_playbooks.llm import arg_gate
from fsr_playbooks.llm import tools as T


def _plain(spec) -> bool:
    try:
        sig = inspect.signature(spec.fn)
    except (TypeError, ValueError):
        return False
    return not any(p.kind is inspect.Parameter.VAR_KEYWORD
                   for p in sig.parameters.values())


_PLAIN = sorted(n for n, s in T.REGISTRY.items() if _plain(s))


@pytest.fixture
def never_runs(monkeypatch):
    """Swap a tool's fn for one that records being called."""
    calls: list[str] = []

    def install(name: str):
        spec = T.REGISTRY[name]
        orig = spec.fn

        def fake(*a, **kw):
            calls.append(name)
            return {"ok": True}
        fake.__signature__ = inspect.signature(orig)  # type: ignore[attr-defined]
        monkeypatch.setitem(T.REGISTRY, name, dataclasses.replace(spec, fn=fake))
        return calls
    return install


# ---------------------------------------------------------------- the sweep

_FILL = {"string": "x", "integer": 1, "number": 1, "boolean": True,
         "object": {}, "array": []}


def _required_args(spec) -> dict:
    """Type-correct filler for every required argument."""
    props = spec.input_schema.get("properties") or {}
    out = {}
    for r in spec.input_schema.get("required") or []:
        t = (props.get(r) or {}).get("type")
        out[r] = _FILL.get(t if isinstance(t, str) else "string", "x")
    return out


@pytest.mark.parametrize("name", _PLAIN)
def test_an_unknown_key_is_refused_before_the_tool_runs(name, never_runs):
    calls = never_runs(name)
    spec = T.REGISTRY[name]
    args = _required_args(spec)
    args["zz_not_a_real_argument"] = 1
    out = T.dispatch(name, args, _internal=True)
    assert out.get("code") == arg_gate.CODE, out
    assert "zz_not_a_real_argument" in out["error"]
    assert "Valid arguments" in out["error"]
    assert calls == []


@pytest.mark.parametrize(
    "name", [n for n in _PLAIN if T.REGISTRY[n].input_schema.get("required")])
def test_a_missing_required_argument_is_refused(name, never_runs):
    calls = never_runs(name)
    out = T.dispatch(name, {}, _internal=True)
    assert out.get("code") == arg_gate.CODE, out
    assert "required, missing" in out["error"]
    assert calls == []


def _typed_prop(schema, jtype):
    for k, v in (schema.get("properties") or {}).items():
        if isinstance(v, dict) and v.get("type") == jtype:
            return k
    return None


@pytest.mark.parametrize(
    "name", [n for n in _PLAIN
             if _typed_prop(T.REGISTRY[n].input_schema, "integer")])
def test_a_wrong_type_is_refused_with_what_was_expected(name, never_runs):
    calls = never_runs(name)
    spec = T.REGISTRY[name]
    key = _typed_prop(spec.input_schema, "integer")
    args = _required_args(spec)
    args[key] = "lots"                     # not coercible to an integer
    out = T.dispatch(name, args, _internal=True)
    assert out.get("code") == arg_gate.CODE, out
    assert f"{key}: expected integer" in out["error"]
    assert calls == []


# ------------------------------------------------------- message quality

def test_a_renamed_argument_names_the_right_one():
    """`query` for `q`: string similarity alone misses it (ratio 0.33). One
    unknown key + one missing required key is a rename."""
    out = T.dispatch("find_connector", {"query": "fortigate"}, _internal=True)
    assert "did you mean 'q'" in out["error"]
    assert out["suggestions"] == ["rename 'query' to 'q'"]


def test_an_enum_violation_lists_the_allowed_values():
    out = T.dispatch("find", {"kind": "widgets", "query": "x"}, _internal=True)
    assert out["code"] == arg_gate.CODE
    assert "'connector'" in out["error"] and "use one of" in out["error"]


def test_every_problem_is_reported_at_once():
    out = T.dispatch("find_connector", {"limit": "lots", "bogus": 1}, _internal=True)
    joined = " ".join(out["problems"])
    assert "bogus" in joined and "q: required" in joined and "limit: expected integer" in joined


# --------------------------------------------------- null / coercion rules

def test_null_for_an_optional_argument_means_not_given(never_runs):
    calls = never_runs("find_connector")
    out = T.dispatch("find_connector", {"q": "fortigate", "limit": None},
                     _internal=True)
    assert out.get("code") != arg_gate.CODE, out
    assert calls == ["find_connector"]


def test_null_for_a_required_argument_is_refused(never_runs):
    never_runs("find_connector")
    out = T.dispatch("find_connector", {"q": None}, _internal=True)
    assert "q: required, got null" in out["error"]


def test_one_bare_value_for_a_string_list_is_wrapped():
    from fsr_playbooks.llm.tool_models import coerce_scalar_args
    schema = {"properties": {"only": {"type": "array", "items": {"type": "string"}}}}
    assert coerce_scalar_args(schema, {"only": "email"}) == {"only": ["email"]}
    # A comma list is NOT split -- that would be a guess. The gate refuses it.
    assert coerce_scalar_args(schema, {"only": "a,b"}) == {"only": "a,b"}


# A pydantic/FastMCP server (FortiSIEM's MCP) declares a nested model as a
# `$ref` with no `type`. Live, the model sent params='{"ip": [...]}' to every
# FortiSIEM tool and all of them were refused: no enrichment ever ran.
_REF_SCHEMA = {
    "$defs": {"Q": {"type": "object", "properties": {"ip": {"type": "array"}}}},
    "properties": {"params": {"$ref": "#/$defs/Q"}},
    "required": ["params"],
}


def test_a_json_string_for_a_ref_object_is_decoded():
    from fsr_playbooks.llm.tool_models import coerce_scalar_args
    out = coerce_scalar_args(_REF_SCHEMA, {"params": '{"ip": ["198.51.100.77"]}'})
    assert out == {"params": {"ip": ["198.51.100.77"]}}


def test_a_ref_without_type_but_with_properties_is_an_object():
    from fsr_playbooks.llm.tool_models import coerce_scalar_args
    schema = {"$defs": {"Q": {"properties": {"ip": {}}}},
              "properties": {"params": {"$ref": "#/$defs/Q"}}}
    assert coerce_scalar_args(schema, {"params": '{"ip": "x"}'}) == {"params": {"ip": "x"}}


def test_an_optional_ref_object_is_decoded_but_a_string_member_is_respected():
    from fsr_playbooks.llm.tool_models import coerce_scalar_args
    nullable = {"$defs": _REF_SCHEMA["$defs"],
                "properties": {"params": {"anyOf": [{"$ref": "#/$defs/Q"}, {"type": "null"}]}}}
    assert coerce_scalar_args(nullable, {"params": '{"ip": []}'}) == {"params": {"ip": []}}
    # A string is an allowed shape: the text may be exactly what is wanted.
    either = {"properties": {"q": {"anyOf": [{"type": "object"}, {"type": "string"}]}}}
    assert coerce_scalar_args(either, {"q": '{"a": 1}'}) == {"q": '{"a": 1}'}


def test_a_ref_object_sent_as_text_runs_through_dispatch(monkeypatch):
    seen = {}

    def tool(params):
        seen["params"] = params
        return {"ok": True}

    spec = T.REGISTRY["find_connector"]
    monkeypatch.setitem(T.REGISTRY, "mcp_x__lookup",
                        type(spec)(name="mcp_x__lookup", fn=tool,
                                   input_schema=_REF_SCHEMA,
                                   **{k: getattr(spec, k) for k in type(spec).__dataclass_fields__
                                      if k not in ("name", "fn", "input_schema")}))
    out = T.dispatch("mcp_x__lookup", {"params": '{"ip": ["198.51.100.77"]}'}, _internal=True)
    assert out == {"ok": True}, out
    assert seen["params"] == {"ip": ["198.51.100.77"]}


# --------------------------------------------- bad call vs failing tool

def test_a_typeerror_inside_the_tool_is_a_tool_error_not_bad_arguments(monkeypatch):
    spec = T.REGISTRY["find_connector"]

    def broken(q: str, limit: int = 10, verbose: bool = False):
        return len(None)                   # TypeError from the BODY
    monkeypatch.setitem(T.REGISTRY, "find_connector",
                        dataclasses.replace(spec, fn=broken))
    out = T.dispatch("find_connector", {"q": "x"}, _internal=True)
    assert out["code"] == "tool_error", out
    assert "not your arguments" in out["error"]
    assert "_invoke_failure" not in out


# ------------------------------------------------------------ the contract

def test_plumbing_parameters_are_never_advertised():
    leaked = sorted(n for n, s in T.REGISTRY.items()
                    if {"db_path", "trace_json"} & set(s.input_schema.get("properties") or {}))
    assert leaked == []


def test_an_unadvertised_parameter_is_refused(never_runs):
    calls = never_runs("get_op_schema")
    out = T.dispatch("get_op_schema",
                     {"connector": "c", "op": "o", "db_path": "/tmp/x.db"},
                     _internal=True)
    assert out.get("code") == arg_gate.CODE
    assert calls == []


@pytest.mark.parametrize("name", _PLAIN)
def test_every_advertised_argument_exists_on_the_function(name):
    spec = T.REGISTRY[name]
    sig = inspect.signature(spec.fn).parameters
    ghost = [k for k in (spec.input_schema.get("properties") or {}) if k not in sig]
    assert ghost == [], f"{name} advertises arguments its function lacks: {ghost}"


def test_a_model_cannot_supply_a_skill_trace():
    """`trace_json` is test/batch plumbing; a model's own summary parses to
    zero calls. Not advertised, and refused if sent."""
    spec = T.REGISTRY["build_playbook_from_trace"]
    assert "trace_json" not in spec.input_schema["properties"]
    out = T.dispatch("build_playbook_from_trace",
                     {"trace_json": '{"steps": []}'}, _internal=True)
    assert out.get("code") == arg_gate.CODE


def _edit_problems(op):
    spec = T.REGISTRY["edit_playbook"]
    out = arg_gate.check("edit_playbook", spec.input_schema, spec.fn,
                         {"operations": [op]})
    return out["problems"]


@pytest.mark.parametrize("key", ["type", "action"])
def test_a_missing_nested_key_names_the_sibling_it_was_sent_as(key):
    """Session health: `type: update_step` was 8 of 9 edit_playbook
    refusals, and the refusal only said "'op' is a required property"."""
    problems = _edit_problems({key: "update_step", "name": "A", "set": {"x": 1}})
    assert problems == [f"operations[0]: 'op' is a required property -- "
                        f"you sent it as '{key}': use op: 'update_step'"]


def test_a_misspelled_nested_key_gets_a_rename_hint():
    problems = _edit_problems({"opp": "nonsense", "name": "A"})
    assert problems == ["operations[0]: 'op' is a required property -- "
                        "rename 'opp' to 'op'"]


def test_no_hint_when_nothing_points_at_the_missing_key():
    assert _edit_problems({"name": "A"}) == ["operations[0]: 'op' is a required property"]


def test_an_array_sent_as_broken_json_text_says_where_it_breaks():
    # Analyst sim: edit_playbook `operations` arrived as JSON text with an
    # unbalanced brace, twice, and the refusal said only "expected array, got
    # str" -- nothing about the text failing to parse, so the model resent it.
    spec = T.REGISTRY["edit_playbook"]
    broken = '[{"op": "add_step", "step": {"name": "A", "type": "end"}}}, {"op": "x"}]'
    r = arg_gate.check("edit_playbook", spec.input_schema, spec.fn, {"operations": broken})
    assert r is not None
    assert "does not parse" in r["error"] and "char" in r["error"]
    assert "not a string" in r["error"]
