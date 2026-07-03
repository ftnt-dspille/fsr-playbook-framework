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
    """Arguments for the emit_action_card tool."""
    model_config = ConfigDict(extra="allow")

    title: str
    summary: Optional[str] = None
    description: Optional[str] = None
    operation: Optional[str] = None
    recommended_values: Optional[dict[str, Any]] = None


class EmitChoiceCardArgs(BaseModel):
    """Arguments for the emit_choice_card tool."""
    model_config = ConfigDict(extra="allow")

    title: str
    options: list[dict[str, Any]] = Field(...)
    description: Optional[str] = None


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
    "emit_choice_card": EmitChoiceCardArgs,
    "validate_yaml": ValidateYamlArgs,
    "compile_yaml": CompileYamlArgs,
    "resolve_yaml": ResolveYamlArgs,
    "list_configured_connectors": ListConfiguredConnectorsArgs,
    "search_alerts": SearchAlerts,
}
