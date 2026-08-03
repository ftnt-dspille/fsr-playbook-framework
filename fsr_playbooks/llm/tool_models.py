"""Pydantic models for tool argument validation.

Validates tool arguments at the provider boundary so malformed LLM tool
calls are caught early. Internal logic remains unchanged.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field, ConfigDict, model_validator


class GetRecordArgs(BaseModel):
    """Arguments for the get_record tool.

    Mirrors the REAL registered signature: get_record(iri="", module="",
    uuid="", relationships=True, full=False, record_id=""). The old model
    here required module+record_id(str) -- a stale gate that rejected every
    legitimate form the agent tried on a live matrix run (iri-only,
    module+uuid, integer record_id), 3 tool errors in one turn.
    `coerce_numbers_to_str` accepts an integer id instead of bouncing it.
    """
    model_config = ConfigDict(extra="allow", coerce_numbers_to_str=True)

    iri: Optional[str] = None
    module: Optional[str] = None
    uuid: Optional[str] = None
    record_id: Optional[str] = None
    # Accept a bool OR a list of relationship names. The registered tool takes a
    # bool ("hydrate related records inline"), but the agent naturally reaches
    # for `relationships=["ztpfArtifacts"]` to expand a *named* relationship --
    # which used to bounce at this gate with "Input should be a valid boolean",
    # dead-ending the very "summarize the related steps" turn ztpf devices need.
    # A name-list is coerced to True (hydrate all) in the tool; a bad value can
    # never regress a lookup into a validation error.
    relationships: Optional[bool | list[str]] = None
    full: Optional[bool] = None
    include: Optional[list[str]] = None

    @model_validator(mode="after")
    def _one_identifier(self) -> "GetRecordArgs":
        if not (self.iri or (self.module and (self.uuid or self.record_id))):
            raise ValueError(
                "identify the record via `iri` alone, or `module` plus "
                "`uuid`/`record_id` -- e.g. "
                'get_record(iri="/api/3/alerts/<uuid>") or '
                'get_record(module="alerts", uuid="<uuid>"). '
                "get_record fetches ONE record -- to find records by a field or "
                "relationship (e.g. every step on a device), use "
                "search_module_records(module=..., filters={...})."
            )
        return self


class SearchModuleRecordsArgs(BaseModel):
    """Arguments for the search_module_records tool.

    ``filters`` accepts BOTH shapes the agent emits: the ``{field: value}`` map
    the tool documents, AND the list-of-conditions form
    ``[{"field": ..., "op": ..., "value": ...}]`` (or ``{"key":..,"value":..}``)
    it instinctively reaches for. The list form used to bounce here with
    "filters: Input should be a valid dictionary" -- the single most frequent
    tool error in live ztpf sessions (the agent retried it 4+ times per session,
    never finding records that plainly existed). The tool normalizes whichever
    shape arrives; this gate must not reject either.
    """
    model_config = ConfigDict(extra="allow")

    module: str
    filters: Optional[dict[str, Any] | list[dict[str, Any]]] = None
    limit: Optional[int] = None
    # DECLARED, not left to `extra="allow"`, and not decoration: only declared
    # fields get JSON-string coercion (see `coerce_json_string_args`), and the
    # agent emits `fields` as a JSON string in the same breath as `filters`.
    # Mirrors the real signature: search_module_records(module, q, limit,
    # filters, fields, sort). `sort` and `q` admit a plain string, so they are
    # never coerced -- `sort="stepNumber"` is the common, correct form.
    q: Optional[str] = None
    fields: Optional[list[str]] = None
    sort: Optional[str | list] = None


class RunOpArgs(BaseModel):
    """Arguments for the run_op tool."""
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    connector: str = Field(...)
    op: str = Field(...)
    params: Optional[dict[str, Any]] = None
    confirm: Optional[bool] = None


class EmitActionCardArgs(BaseModel):
    """Arguments for the emit_action_card tool.

    Mirrors the REAL registered signature: emit_action_card(id, connector,
    operation, summary, args, editable_fields). The old model here required
    `title` -- a field the registered tool does not accept -- while omitting
    id/connector/args/editable_fields entirely. So every live containment card
    the agent staged (correctly passing summary/operation/args) bounced with
    "title: Field required" and the turn ended with no action card (matrix
    run 7 T1). Same drift class as GetRecordArgs (run 5).
    """
    model_config = ConfigDict(extra="allow")

    id: str
    connector: str
    operation: str
    summary: str
    args: dict[str, Any]
    editable_fields: list[str]
    # Declared intent (tracker #60). "analyst" means the user explicitly ordered
    # this containment, which exempts the card from the hunt floor -- see
    # `_loop_helpers.TriageDiscipline`. Optional and defaulted so an unset field
    # keeps the pre-#60 behavior exactly.
    requested_by: Optional[str] = None


class EmitPatchProposalArgs(BaseModel):
    """Arguments for the emit_patch_proposal tool.

    Mirrors the registered signature: emit_patch_proposal(id, title,
    before_yaml, after_yaml, rationale?, target_step?, target_path?, tier?,
    reply_tool?). The runtime check in tools_emit.emit_patch_proposal is the
    belt-and-suspenders for callers that bypass the LLM (eval harness, tests);
    this model is the wire-arg gate on the dispatch path.
    """
    model_config = ConfigDict(extra="allow")

    id: str
    title: str
    before_yaml: str
    after_yaml: str
    rationale: Optional[str] = None
    target_step: Optional[str] = None
    target_path: Optional[str] = None
    tier: Optional[int] = None
    reply_tool: Optional[str] = None


class EmitChoiceCardArgs(BaseModel):
    """Arguments for the emit_choice_card tool.

    Mirrors the REAL registered signature: emit_choice_card(id, prompt,
    options, multi, min_select, max_select). The old model required `title`
    (not a real param) and omitted id/prompt/multi/min_select/max_select.
    """
    model_config = ConfigDict(extra="allow")

    id: str
    prompt: str
    options: list[dict[str, Any]]
    multi: Optional[bool] = None
    min_select: Optional[int] = None
    max_select: Optional[int] = None


class ValidateYamlArgs(BaseModel):
    """Arguments for the validate_yaml tool."""
    model_config = ConfigDict(extra="allow")

    yaml_text: str = Field(...)


class CompileYamlArgs(BaseModel):
    """Arguments for the compile_yaml tool."""
    model_config = ConfigDict(extra="allow")

    yaml_text: str = Field(...)
    name: Optional[str] = None
    collection: Optional[str] = None


class ResolveYamlArgs(BaseModel):
    """Arguments for the resolve_yaml tool."""
    model_config = ConfigDict(extra="allow")

    yaml_text: str = Field(...)


class ListConfiguredConnectorsArgs(BaseModel):
    """Arguments for the list_configured_connectors tool."""
    model_config = ConfigDict(extra="allow")


class SearchAlerts(BaseModel):
    """Arguments for the search_alerts tool."""
    model_config = ConfigDict(extra="allow")

    query: Optional[str] = None
    limit: Optional[int] = None


# Mapping of tool names to their argument models
TOOL_MODELS = {
    "get_record": GetRecordArgs,
    "search_module_records": SearchModuleRecordsArgs,
    "run_op": RunOpArgs,
    "emit_action_card": EmitActionCardArgs,
    "emit_patch_proposal": EmitPatchProposalArgs,
    "emit_choice_card": EmitChoiceCardArgs,
    "validate_yaml": ValidateYamlArgs,
    "compile_yaml": CompileYamlArgs,
    "resolve_yaml": ResolveYamlArgs,
    "list_configured_connectors": ListConfiguredConnectorsArgs,
    "search_alerts": SearchAlerts,
}


# ---------------------------------------------------------------------------
# JSON-string argument coercion
# ---------------------------------------------------------------------------
# A model that emits a structured argument as a JSON *string* cannot recover
# from being told no. Observed, six calls in one turn:
#
#   filters: "{\"ztpfDevices.uuid\": \"5b23...\"}"   -> rejected
#   filters: "[{\"field\": ..., \"value\": ...}]"    -> rejected
#
# Both STRUCTURES are correct -- dict form and list form are exactly what the
# model above accepts. The only thing wrong is the string wrapper, and the
# error ("Input should be a valid dictionary; Input should be a valid list")
# names the two accepted types without ever saying "you sent a string". So the
# model reads it as "my structure is wrong", permutes structure until it gives
# up, falls back to a free-text `q=`, gets `total: 0`, and answers from that.
#
# The cost is not the wasted calls. It is that a FILTERED READ SILENTLY
# RETURNED NOTHING and the turn continued as though the device had no steps.
#
# This is the same defect as run_op's stringified `params`, one tool over --
# which is why the fix is here and generic rather than a third per-model patch.
# `SearchModuleRecordsArgs` was ALREADY widened once for the list-vs-dict shape
# ("the single most frequent tool error in live ztpf sessions"); the failure
# came straight back one layer out. Widening models one shape at a time loses
# this race.
#
# Scope, deliberately narrow:
#   * Only DECLARED fields. An `extra="allow"` field's intended type is unknown
#     and guessing at it is how a coercion layer starts corrupting data.
#   * Never a field that can be a `str`. A summary or a YAML body that happens
#     to start with `{` must arrive exactly as sent.
#   * Only a value that both looks like JSON and parses to a container. A
#     string that merely starts with `{` and does not parse is left alone to
#     fail validation with its own error.
import json  # noqa: E402
import types  # noqa: E402
import typing  # noqa: E402


def _accepts_str(annotation: Any) -> bool:
    """True when `annotation` admits a plain `str` anywhere in its union.

    Conservative by construction: an annotation this cannot decompose returns
    True, so the field is left untouched.
    """
    if annotation is str or annotation is Any:
        return True
    if annotation is None or annotation is type(None):
        # `Optional[...]` puts NoneType in every union. Counting it as
        # str-accepting would disable coercion on every optional field, which
        # is all of them.
        return False
    origin = typing.get_origin(annotation)
    if origin is typing.Union or origin is types.UnionType:
        # Only a UNION's members are alternatives. Recursing into a generic's
        # type PARAMETERS instead would read `dict[str, Any]` as "accepts str"
        # (because its key type is `str`) and quietly disable coercion on the
        # one field this whole layer exists for.
        return any(_accepts_str(a) for a in typing.get_args(annotation))
    return origin is None and annotation not in (dict, list, tuple, set)


def coerce_json_string_args(name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Return `args` with JSON-string values decoded for `name`'s declared,
    non-``str`` fields. Unknown tool, or nothing to do, returns `args` itself.

    Call this BEFORE validation *and* before invoking the tool: coercing only
    for the gate would let a string past the gate and hand it to the tool body,
    which is a worse failure than the rejection it replaced -- silent instead
    of loud.
    """
    model = TOOL_MODELS.get(name)
    if model is None or not isinstance(args, dict) or not args:
        return args
    out: Optional[dict[str, Any]] = None
    for key, field in model.model_fields.items():
        value = args.get(key)
        if not isinstance(value, str):
            continue
        stripped = value.strip()
        if not stripped[:1] in ("{", "["):
            continue
        if _accepts_str(field.annotation):
            continue
        try:
            decoded = json.loads(stripped)
        except (ValueError, TypeError):
            continue  # not JSON after all -- let it fail with its own error
        if not isinstance(decoded, (dict, list)):
            continue
        if out is None:
            out = dict(args)
        out[key] = decoded
    return out if out is not None else args
