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
    here required module+record_id(str) — a stale gate that rejected every
    legitimate form the agent tried on a live matrix run (iri-only,
    module+uuid, integer record_id), 3 tool errors in one turn.
    `coerce_numbers_to_str` accepts an integer id instead of bouncing it.
    """
    model_config = ConfigDict(extra="allow", coerce_numbers_to_str=True)

    iri: Optional[str] = None
    module: Optional[str] = None
    uuid: Optional[str] = None
    record_id: Optional[str] = None
    relationships: Optional[bool] = None
    full: Optional[bool] = None
    include: Optional[list[str]] = None

    @model_validator(mode="after")
    def _one_identifier(self) -> "GetRecordArgs":
        if not (self.iri or (self.module and (self.uuid or self.record_id))):
            raise ValueError(
                "identify the record via `iri` alone, or `module` plus "
                "`uuid`/`record_id` — e.g. "
                'get_record(iri="/api/3/alerts/<uuid>") or '
                'get_record(module="alerts", uuid="<uuid>")'
            )
        return self


class SearchModuleRecordsArgs(BaseModel):
    """Arguments for the search_module_records tool."""
    model_config = ConfigDict(extra="allow")

    module: str
    filters: Optional[dict[str, Any]] = None
    limit: Optional[int] = None


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
    `title` — a field the registered tool does not accept — while omitting
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
