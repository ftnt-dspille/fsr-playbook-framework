"""The advertised input_schema is the one argument contract, and dispatch holds
every call to it.

Regression source: two pydantic copies of the tool signatures used to re-check
calls after the schema gate. Copies drift: a live matrix run had get_record's
copy require module+record_id(str) while the tool accepts iri / module+uuid /
module+record_id (every form the agent tried bounced), and the emit_* card
copies demanded a `title` neither tool accepts. The schema is built from the
signature itself, so it cannot drift that way; what a schema cannot say lives
in tool_models.CROSS_FIELD_RULES.
"""
import inspect
import json
from typing import Any, Literal

import pytest

from fsr_playbooks.llm import tools as T
from fsr_playbooks.llm.tool_models import CROSS_FIELD_RULES, coerce_scalar_args


def _dispatch_refusal(name, args):
    """What dispatch's argument stages say about ``args`` (None = accepted)."""
    c = T._Call(name=name, spec=T.REGISTRY[name], args=dict(args), internal=False,
                session_id=None, approved_by=None, summary=None)
    T._coerce_args(c)
    return T._check_args(c)


# --- get_record: the cross-field rule ---------------------------------------

@pytest.mark.parametrize("args", [
    {"iri": "/api/3/alerts/e035f3f3-4ff3-4036-a625-bc66d48846e5"},
    {"module": "alerts", "uuid": "e035f3f3-4ff3-4036-a625-bc66d48846e5"},
    {"module": "alerts", "record_id": "30369"},
    {"iri": "/api/3/alerts/x", "module": "alerts", "uuid": "x",
     "relationships": False, "full": True, "record_id": "1"},
])
def test_every_real_way_to_name_a_record_passes(args):
    assert CROSS_FIELD_RULES["get_record"](args) is None


@pytest.mark.parametrize("args", [
    {"relationships": True}, {"module": "alerts"}, {"record_id": "f879"},
    {"iri": "", "module": "", "uuid": ""},
])
def test_a_call_that_names_no_record_is_refused_with_an_example(args):
    why = CROSS_FIELD_RULES["get_record"](args)
    assert why and "get_record(iri=" in why


def test_dispatch_applies_the_rule_before_any_card_or_body(monkeypatch):
    assert _dispatch_refusal("search_playbooks", {"q": "x"}) is None
    monkeypatch.setitem(CROSS_FIELD_RULES, "search_playbooks", lambda a: "needs y")
    out = _dispatch_refusal("search_playbooks", {"q": "x"})
    assert out["ok"] is False and out["code"] == "invalid_tool_args"
    assert "needs y" in out["error"]


# --- the card emitters: the schema demands exactly the real parameters ------

def test_emit_action_card_accepts_its_real_signature():
    assert _dispatch_refusal("emit_action_card", {
        "id": "block_c2_ip", "connector": "fortigate-firewall",
        "operation": "block_ip_new", "summary": "Block C2 IP 51.15.43.205 on FortiGate",
        "args": {"ip": "51.15.43.205", "ip_type": "IPv4"}, "editable_fields": ["ip"],
    }) is None


def test_emit_action_card_names_what_is_missing_and_never_title():
    out = _dispatch_refusal("emit_action_card", {
        "id": "block_c2_ip", "connector": "fortigate-firewall",
        "operation": "block_ip_new", "summary": "Block C2 IP"})
    assert out["code"] == "invalid_tool_args"
    assert "args" in out["error"] and "editable_fields" in out["error"]
    assert "title" not in out["error"]


def test_emit_choice_card_accepts_its_real_signature_and_names_what_is_missing():
    assert _dispatch_refusal("emit_choice_card", {
        "id": "branch", "prompt": "Contain now or build a playbook?",
        "options": [{"label": "Contain", "value": "contain"},
                    {"label": "Build", "value": "build"}]}) is None
    out = _dispatch_refusal("emit_choice_card", {"id": "branch"})
    assert "prompt" in out["error"] and "options" in out["error"]
    assert "title" not in out["error"]


# --- retired: patch_proposal ----------------------------------------------


def test_the_retired_patch_proposal_is_refused_toward_its_replacement():
    """patch_proposal was retired 2026-09: the model had stopped choosing it,
    and its snippet-match apply was fragile. A call that still asks for it is
    refused at the arg gate, which names enhancement_offer."""
    assert "emit_patch_proposal" not in T.REGISTRY
    r = T.dispatch("emit_card", {"card_type": "patch_proposal",
                                 "payload": {"title": "Fix ip"}})
    assert r["ok"] is False and r["code"] == "invalid_tool_args"
    assert "enhancement_offer" in r["error"]


# --- schema <-> signature parity ---------------------------------------------

def test_every_schema_requires_exactly_the_signature_required_params():
    """The guard the pydantic copies never had: a schema that asks for a
    parameter the function lacks (or omits one it requires) is a contract the
    model cannot satisfy. Holds for every registered tool."""
    drift = []
    for name, spec in T.REGISTRY.items():
        try:
            sig = inspect.signature(spec.fn)
        except (TypeError, ValueError):
            continue
        params = sig.parameters
        if any(p.kind is p.VAR_KEYWORD for p in params.values()):
            continue
        real_required = {p for p, v in params.items()
                         if v.default is inspect.Parameter.empty
                         and v.kind in (v.POSITIONAL_OR_KEYWORD, v.KEYWORD_ONLY)}
        schema = spec.input_schema or {}
        advertised = set(schema.get("properties") or {})
        required = set(schema.get("required") or [])
        if required - set(params):
            drift.append(f"{name}: requires {sorted(required - set(params))} "
                         "the function does not take")
        if real_required - required:
            drift.append(f"{name}: does not require {sorted(real_required - required)}")
        if advertised - set(params):
            drift.append(f"{name}: advertises {sorted(advertised - set(params))} "
                         "the function does not take")
    assert not drift, drift


# --- the schema builder: Literal and unions ------------------------------------

def test_a_literal_is_advertised_as_its_allowed_values():
    assert T._py_type_to_json(Literal["ip", "host"]) == {
        "type": "string", "enum": ["ip", "host"]}


def test_a_union_of_types_is_advertised_as_a_type_list():
    """`dict | list` used to be advertised with no type, so the gate passed
    anything and a second pydantic copy did the type check."""
    assert T._py_type_to_json(dict[str, Any] | list[str] | None) == {
        "type": ["object", "array"], "items": {"type": "string"}}
    assert T._py_type_to_json(str | dict) == {"type": ["string", "object"]}
    assert T._py_type_to_json(Any | int) == {}


# ---------------------------------------------------------------------------
# JSON-string arguments.
#
# Observed live: the agent emitted `filters` as a JSON STRING six times in one
# turn. Both structures it tried were valid; only the string wrapper was wrong,
# and the error never said so. It gave up, fell back to free-text `q=`, got
# `total: 0`, and answered from that -- a filtered read that silently returned
# nothing. Coercion is keyed on the advertised schema, so every tool gets it.
# ---------------------------------------------------------------------------
_CONTAINERS = {"type": "object", "properties": {
    "q": {"type": "string"},
    "filters": {"type": ["object", "array"]},
    "params": {"type": "object"},
    "sort": {"type": ["string", "array"]},
}}


def test_a_stringified_dict_or_list_for_a_container_union_is_decoded():
    assert coerce_scalar_args(_CONTAINERS, {"filters": '{"ztpfDevices.uuid": "abc"}'}) \
        == {"filters": {"ztpfDevices.uuid": "abc"}}
    assert coerce_scalar_args(
        _CONTAINERS, {"filters": '[{"field": "status", "value": "R"}]'}) \
        == {"filters": [{"field": "status", "value": "R"}]}


def test_run_op_params_as_json_or_blank_string():
    schema = T.REGISTRY["run_op"].input_schema
    assert coerce_scalar_args(schema, {"connector": "c", "op": "o",
                                       "params": '{"ip": "1.2.3.4"}'})["params"] \
        == {"ip": "1.2.3.4"}
    assert "params" not in coerce_scalar_args(
        schema, {"connector": "c", "op": "o", "params": "  "})
    assert "filters" not in coerce_scalar_args(_CONTAINERS, {"filters": ""})


def test_a_field_that_admits_a_string_is_never_touched():
    """A summary or YAML body that happens to start with `{` must arrive
    exactly as sent."""
    args = {"q": '{"looks": "like json"}', "sort": '["a"]'}
    assert coerce_scalar_args(_CONTAINERS, args) == args


def test_an_undeclared_field_is_never_touched():
    args = {"not_declared": '{"a": 1}'}
    assert coerce_scalar_args(_CONTAINERS, args) is args


def test_a_string_that_is_not_json_is_left_to_fail_with_its_own_error():
    assert coerce_scalar_args(_CONTAINERS, {"filters": "{not json"}) == {"filters": "{not json"}


def test_every_container_param_in_the_registry_survives_a_stringified_value():
    """The parity guard. This defect arrived twice (run_op `params`, search
    `filters`) and was patched per-model once -- widening one shape at a time
    loses that race. Any advertised object/array parameter (or a union of
    them) must accept its own JSON-string form."""
    checked = 0
    for name, spec in T.REGISTRY.items():
        schema = spec.input_schema or {}
        for pname, prop in (schema.get("properties") or {}).items():
            t = prop.get("type") if isinstance(prop, dict) else None
            kinds = set(t) if isinstance(t, list) else {t}
            if not kinds or not kinds <= {"object", "array"}:
                continue
            sample = {"k": "v"} if "object" in kinds else [{"k": "v"}]
            out = coerce_scalar_args(schema, {pname: json.dumps(sample)})
            assert out[pname] == sample, f"{name}.{pname}"
            checked += 1
    assert checked >= 10, f"the guard checked only {checked} params"


# ---------------------------------------------------------------------------
# Stringly-typed tool arguments
#
# Regression source: the first graded run of the LOCAL matrix (harness +
# connector sidecar + a gateway-served model). That model emitted EVERY tool
# argument as a string, and two distinct failures followed:
#
#   find_enrichment_actions(limit="25")  -> actions[:limit] raised
#                                           "slice indices must be integers"
#   find_containment_actions(probe="False") -> "False" is a NON-EMPTY string,
#                                           so `if probe:` was True and the
#                                           call ran with the OPPOSITE of what
#                                           was asked, returning plausible
#                                           output and reporting nothing.
#
# The root cause was upstream of both: 32 of 39 tools advertised an
# `input_schema` with NO parameter types, because their modules use
# `from __future__ import annotations` and `inspect.signature` therefore
# returns annotations as strings. A model told `{"limit": {"default": 25}}`
# was never given a contract to break.
# ---------------------------------------------------------------------------

def test_every_tool_advertises_a_type_for_every_parameter():
    """The schema we hand the model must name each parameter's type.

    Asserted as a PROPERTY over the whole registry rather than for the two
    tools that broke: the cause is a module-level `from __future__ import
    annotations`, so the next tool added to any such module inherits the bug
    silently. A parameter with a default but no `type` is exactly what the
    model saw for 32 tools.
    """
    from fsr_playbooks.llm.tools import REGISTRY

    untyped = []
    for name, spec in REGISTRY.items():
        for pname, prop in (spec.input_schema or {}).get("properties", {}).items():
            if not isinstance(prop, dict) or "type" not in prop:
                untyped.append(f"{name}.{pname}")
    assert not untyped, (
        "these tool parameters are advertised to the model with NO type, so it "
        "has no contract to honour and will send whatever it likes (commonly a "
        f"string for every argument): {untyped[:15]}")


def test_declared_int_and_bool_params_survive_their_string_form():
    """Property over the registry: any int/bool parameter must accept the
    string a provider actually sends. Per-tool fixes lose this race -- the
    class already hit two tools in one turn."""
    from fsr_playbooks.llm.tool_models import coerce_scalar_args
    from fsr_playbooks.llm.tools import REGISTRY

    checked = 0
    for name, spec in REGISTRY.items():
        props = (spec.input_schema or {}).get("properties", {})
        for pname, prop in props.items():
            jtype = prop.get("type") if isinstance(prop, dict) else None
            if jtype == "integer":
                out = coerce_scalar_args(spec.input_schema, {pname: "25"})
                assert out[pname] == 25 and isinstance(out[pname], int), \
                    f"{name}.{pname} (integer) does not survive being sent as \"25\""
                checked += 1
            elif jtype == "boolean":
                out = coerce_scalar_args(spec.input_schema, {pname: "False"})
                assert out[pname] is False, (
                    f"{name}.{pname} (boolean) sent as \"False\" stays a truthy "
                    f"string -- the call would run with the opposite meaning and "
                    f"report nothing")
                checked += 1
    assert checked >= 10, \
        f"the guard checked only {checked} params; the registry has far more"


def test_the_exact_live_args_that_broke_the_matrix():
    """The verbatim argument dict from the failing transcript."""
    from fsr_playbooks.llm.tool_models import coerce_scalar_args
    from fsr_playbooks.llm.tools import REGISTRY

    schema = REGISTRY["find_containment_actions"].input_schema
    out = coerce_scalar_args(
        schema,
        {"limit": "25", "probe": "False", "requested_by": "", "target_type": "ip"},
    )
    assert out["limit"] == 25
    assert out["probe"] is False          # the SILENT half
    assert out["target_type"] == "ip"     # a real string stays a string


@pytest.mark.parametrize("args", [
    {"limit": "abc"},      # not a number at all
    {"limit": ""},         # empty
    {"limit": "25.5"},     # a float where an int is declared
    {"probe": "maybe"},    # not a boolean spelling
    {"probe": "0.0"},      # falsy-looking, but not one of the accepted words
])
def test_ambiguous_strings_are_left_alone_not_guessed(args):
    """Coercion must never convert a loud rejection into a silent guess.

    Anything that does not parse unambiguously is passed through untouched so
    the existing validation / TypeError path still returns the
    self-correctable "bad arguments for X" the model can act on.
    """
    from fsr_playbooks.llm.tool_models import coerce_scalar_args
    from fsr_playbooks.llm.tools import REGISTRY

    schema = REGISTRY["find_containment_actions"].input_schema
    assert coerce_scalar_args(schema, args) == args


def test_string_parameters_are_never_coerced():
    """A declared string keeps whatever the model sent, including text that
    happens to look like a number or a boolean."""
    from fsr_playbooks.llm.tool_models import coerce_scalar_args
    from fsr_playbooks.llm.tools import REGISTRY

    schema = REGISTRY["find_containment_actions"].input_schema
    args = {"target_type": "25", "requested_by": "true"}
    assert coerce_scalar_args(schema, args) == args


# --- a content-free action card --------------------------------------------
# Live: a staged card whose whole summary was "." rendered an empty body with a
# live Confirm button. The refusal lived only in the connector's pydantic copy,
# which the emit_card path never reached.

@pytest.mark.parametrize("summary", [".", "block", "  ok    "])
def test_an_action_card_that_says_nothing_is_refused_on_the_emit_card_path(summary):
    r = T.dispatch("emit_card", {"card_type": "action", "payload": {
        "id": "c1", "connector": "fortigate-firewall", "operation": "block_ip_new",
        "summary": summary, "args": {"ip": "10.0.0.1"}, "editable_fields": ["ip"]}})
    assert r["ok"] is False and r["code"] == "missing_field", r
    assert "summary" in r["message"]


def test_a_real_summary_stages():
    r = T.dispatch("emit_card", {"card_type": "action", "payload": {
        "id": "c1", "connector": "fortigate-firewall", "operation": "block_ip_new",
        "summary": "Block 10.0.0.1 on FortiGate", "args": {"ip": "10.0.0.1"},
        "editable_fields": ["ip"]}})
    assert r.get("code") != "missing_field", r
