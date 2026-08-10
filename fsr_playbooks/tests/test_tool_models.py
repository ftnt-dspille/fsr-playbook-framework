"""Gate models in llm/tool_models.py must mirror the REAL registered tool
signatures -- a stale model silently rejects legitimate calls at dispatch.

Regression source: a live matrix run where get_record's model required
module+record_id(str) while the registered tool accepts iri / module+uuid /
module+record_id; every form the agent tried bounced (3 tool errors in one
turn, turn ended with no deliverable). The same drift class later hit the
emit_action_card / emit_choice_card models (required `title`, a field neither
registered tool accepts).
"""
import inspect

import json
import typing
from typing import Any

import pytest
from pydantic import ValidationError

from fsr_playbooks.llm.tool_models import (
    EmitActionCardArgs,
    EmitChoiceCardArgs,
    EmitPatchProposalArgs,
    GetRecordArgs,
)
from fsr_playbooks.mcp_server import tools_emit


def test_iri_only_is_valid():
    GetRecordArgs(iri="/api/3/alerts/e035f3f3-4ff3-4036-a625-bc66d48846e5")


def test_module_plus_uuid_is_valid():
    GetRecordArgs(module="alerts", uuid="e035f3f3-4ff3-4036-a625-bc66d48846e5")


def test_module_plus_int_record_id_coerces():
    # The live agent passed record_id as a bare integer; the gate must
    # coerce, not bounce.
    args = GetRecordArgs(module="alerts", record_id=30369)
    assert args.record_id == "30369"


def test_no_identifier_rejected_with_example():
    with pytest.raises(ValidationError) as exc:
        GetRecordArgs(relationships=True)
    assert "get_record(iri=" in str(exc.value)


def test_module_alone_rejected():
    with pytest.raises(ValidationError):
        GetRecordArgs(module="alerts")


def test_real_signature_kwargs_all_accepted():
    # Full real signature: get_record(iri, module, uuid, relationships,
    # full, record_id) -- the model must not reject any real param.
    GetRecordArgs(iri="/api/3/alerts/x", module="alerts", uuid="x",
                  relationships=False, full=True, record_id="1")


# --- emit_action_card ------------------------------------------------------
# The live agent staged a containment card with the REAL tool's args
# (id, connector, operation, summary, args) and the old gate bounced it with
# "title: Field required" -- title is not a param the tool accepts. The gate
# must accept exactly the registered signature.


def test_emit_action_card_accepts_real_signature():
    # The exact shape a grounded containment card uses: the agent fills
    # args from find_containment_actions' params, editable_fields from the
    # params it wants the analyst to tweak.
    EmitActionCardArgs(
        id="block_c2_ip",
        connector="fortigate-firewall",
        operation="block_ip_new",
        summary="Block C2 IP 51.15.43.205 on FortiGate",
        args={"ip": "51.15.43.205", "ip_type": "IPv4"},
        editable_fields=["ip"],
    )


def test_emit_action_card_rejects_missing_required():
    with pytest.raises(ValidationError) as exc:
        EmitActionCardArgs(
            id="block_c2_ip", connector="fortigate-firewall",
            operation="block_ip_new", summary="Block C2 IP",
        )  # missing args + editable_fields
    msg = str(exc.value)
    assert "args" in msg and "editable_fields" in msg
    # The drift symptom must NOT recur: the gate must not demand `title`.
    assert "title" not in msg


# --- emit_choice_card ------------------------------------------------------


def test_emit_choice_card_accepts_real_signature():
    EmitChoiceCardArgs(
        id="branch",
        prompt="Contain now or build a playbook?",
        options=[{"label": "Contain", "value": "contain"},
                 {"label": "Build", "value": "build"}],
    )


def test_emit_choice_card_rejects_missing_required():
    with pytest.raises(ValidationError) as exc:
        EmitChoiceCardArgs(id="branch")  # missing prompt + options
    msg = str(exc.value)
    assert "prompt" in msg and "options" in msg
    assert "title" not in msg


# --- emit_patch_proposal ---------------------------------------------------


def test_emit_patch_proposal_accepts_real_signature():
    EmitPatchProposalArgs(
        id="fix-ip-jinja",
        title="Fix the source-IP jinja in 'Block source'",
        before_yaml="ip: {{ vars.records[0].ip }}",
        after_yaml="ip: {{ vars.input.records[0].ip }}",
        rationale="records[0] is empty on a record-action trigger",
        target_step="Block source",
        target_path="arguments.ip",
        tier=0,
        reply_tool="apply_patch",
    )


def test_emit_patch_proposal_rejects_missing_required():
    with pytest.raises(ValidationError) as exc:
        EmitPatchProposalArgs(id="p", title="t")  # missing before/after
    msg = str(exc.value)
    assert "before_yaml" in msg and "after_yaml" in msg


def test_emit_patch_proposal_tool_builds_card_with_defaults():
    out = tools_emit.emit_patch_proposal(
        id="p1", title="Fix ip", before_yaml="ip: a", after_yaml="ip: b")
    assert out["ok"] is True
    card = out["card"]
    assert card["type"] == "patch_proposal"
    assert card["proposal_id"] == "p1"
    assert card["reply_tool"] == "apply_patch"  # default
    assert card["tier"] == 0                     # default
    assert "target" not in card                  # no step/path given


def test_emit_patch_proposal_tool_rejects_noop():
    out = tools_emit.emit_patch_proposal(
        id="p2", title="t", before_yaml="ip: a", after_yaml="  ip: a  ")
    assert out["ok"] is False
    assert out["code"] == "noop_patch"


def test_emit_patch_proposal_dispatches_and_halts_via_registry():
    from fsr_playbooks.llm import tools
    assert "emit_patch_proposal" in tools.REGISTRY
    assert tools.REGISTRY["emit_patch_proposal"].tier == 0
    r = tools.dispatch("emit_patch_proposal", dict(
        id="p3", title="Fix", before_yaml="a: 1", after_yaml="a: 2",
        target_step="S", target_path="arguments.a"))
    assert r["ok"] and r["card"]["type"] == "patch_proposal"
    assert r["card"]["target"] == {"step": "S", "path": "arguments.a"}


# --- signature-sync guard --------------------------------------------------
# The guard that was MISSING when GetRecordArgs, then the emit_* card models,
# drifted from their registered signatures. Introspects each registered tool
# the gate covers (that lives in tools_emit) and asserts the gate declares
# every real required param -- so a stale gate can't silently bounce a
# legitimate call again. Extend REAL_FNS as more gated tools are pinned down.


REAL_FNS = {
    "emit_action_card": tools_emit.emit_action_card,
    "emit_choice_card": tools_emit.emit_choice_card,
    "emit_patch_proposal": tools_emit.emit_patch_proposal,
}


@pytest.mark.parametrize("tool_name", sorted(REAL_FNS))
def test_gate_model_covers_all_real_required_params(tool_name):
    from fsr_playbooks.llm import tool_models as tm

    fn = REAL_FNS[tool_name]
    model = tm.TOOL_MODELS[tool_name]
    sig = inspect.signature(fn)
    real_required = {
        p for p, v in sig.parameters.items()
        if v.default is inspect.Parameter.empty
        and v.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD,
                       inspect.Parameter.KEYWORD_ONLY)
    }
    declared = set(model.model_fields)
    missing = real_required - declared
    assert not missing, (
        f"{tool_name}: gate {model.__name__} is missing required real params "
        f"{sorted(missing)}; declared={sorted(declared)}"
    )



# ---------------------------------------------------------------------------
# JSON-string argument coercion.
#
# Observed live: the agent emitted `filters` as a JSON STRING six times in one
# turn. Both structures it tried were valid; only the string wrapper was wrong,
# and the error never said so. It gave up, fell back to free-text `q=`, got
# `total: 0`, and answered from that -- a filtered read that silently returned
# nothing. These tests are about that, not about the parsing.
# ---------------------------------------------------------------------------
from fsr_playbooks.llm.tool_models import coerce_json_string_args as _coerce


def test_a_stringified_dict_filter_is_decoded():
    out = _coerce("search_module_records",
                  {"module": "m", "filters": '{"ztpfDevices.uuid": "abc"}'})
    assert out["filters"] == {"ztpfDevices.uuid": "abc"}


def test_a_stringified_list_filter_is_decoded():
    """The other shape the agent alternates between when the first is refused."""
    out = _coerce("search_module_records",
                  {"module": "m",
                   "filters": '[{"field": "status", "op": "eq", "value": "R"}]'})
    assert out["filters"] == [{"field": "status", "op": "eq", "value": "R"}]


def test_a_stringified_run_op_params_is_decoded():
    """The same defect one tool over -- the reason this is generic."""
    out = _coerce("run_op", {"connector": "c", "op": "o",
                             "params": '{"ip": "1.2.3.4"}'})
    assert out["params"] == {"ip": "1.2.3.4"}


def test_a_string_field_is_never_touched():
    """A summary or YAML body that happens to start with `{` must arrive
    exactly as sent. Coercion that guessed here would corrupt data to fix a
    validation error."""
    out = _coerce("search_module_records",
                  {"module": "m", "q": '{"looks": "like json"}'})
    assert out["q"] == '{"looks": "like json"}'
    assert _coerce("search_module_records",
                   {"module": "m", "sort": "stepNumber"})["sort"] == "stepNumber"


def test_an_undeclared_field_is_never_touched():
    """`extra="allow"` fields have no known intended type. Guessing at one is
    how a coercion layer starts corrupting data."""
    args = {"module": "m", "not_a_declared_field": '{"a": 1}'}
    assert _coerce("search_module_records", args)["not_a_declared_field"] \
        == '{"a": 1}'


def test_a_string_that_is_not_json_is_left_to_fail_with_its_own_error():
    args = {"module": "m", "filters": "{not json at all"}
    assert _coerce("search_module_records", args)["filters"] == "{not json at all"


def test_a_json_scalar_is_not_a_container_and_is_left_alone():
    assert _coerce("run_op", {"connector": "c", "op": "o",
                              "params": "[1, 2, 3]"})["params"] == [1, 2, 3]
    # ... but a bare scalar never looks like JSON to us in the first place.
    assert _coerce("run_op", {"connector": "c", "op": "o",
                              "params": "12"})["params"] == "12"


def test_an_unknown_tool_and_an_untouched_call_return_the_input_unchanged():
    args = {"filters": '{"a": 1}'}
    assert _coerce("no_such_tool", args) is args
    clean = {"module": "m", "filters": {"a": 1}}
    assert _coerce("search_module_records", clean) is clean


def test_the_stringified_filter_now_passes_the_gate_it_used_to_bounce_off():
    """End-to-end at the boundary: the model that rejected this is the one the
    agent hit six times."""
    from fsr_playbooks.llm.tool_models import (SearchModuleRecordsArgs,
                                               TOOL_MODELS)
    raw = {"module": "m", "filters": '{"ztpfDevices.uuid": "abc"}',
           "fields": '["id", "name"]'}
    with pytest.raises(Exception):
        SearchModuleRecordsArgs(**raw)
    ok = TOOL_MODELS["search_module_records"](
        **_coerce("search_module_records", raw))
    assert ok.filters == {"ztpfDevices.uuid": "abc"}
    assert ok.fields == ["id", "name"]


def test_every_container_field_in_every_model_survives_a_stringified_value():
    """The parity guard. This defect has now arrived twice (run_op `params`,
    search `filters`) and been patched per-model once already -- widening models
    one shape at a time loses that race. So assert the PROPERTY across the whole
    registry: any declared field that cannot be a plain string must accept its
    own JSON-string form after coercion. A new tool with a dict argument
    inherits the fix, or fails here."""
    from fsr_playbooks.llm.tool_models import TOOL_MODELS, _accepts_str

    checked = 0
    for tool, model in TOOL_MODELS.items():
        for fname, field in model.model_fields.items():
            if _accepts_str(field.annotation):
                continue
            origin = typing.get_origin(field.annotation)
            members = typing.get_args(field.annotation) or (field.annotation,)
            sample: Any
            if any(typing.get_origin(m) is dict or m is dict for m in members):
                sample = {"k": "v"}
            elif any(typing.get_origin(m) is list or m is list for m in members):
                sample = [{"k": "v"}] if fname == "filters" else ["a"]
            else:
                continue  # int/bool fields: not a container, not this class
            del origin
            out = _coerce(tool, {fname: json.dumps(sample)})
            assert out[fname] == sample, (
                f"{tool}.{fname} is a container field that does not survive "
                f"being sent as a JSON string -- the agent WILL send it that "
                f"way, and the error it gets back names types, never the string")
            checked += 1
    assert checked >= 4, f"the guard checked only {checked} fields; it should " \
                         f"cover run_op.params and search.filters at minimum"


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
