"""Pydantic models for tool argument validation.

Validates tool arguments at the provider boundary so malformed LLM tool
calls are caught early. Internal logic remains unchanged.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field, ConfigDict


class GetRecordArgs(BaseModel):
    """Arguments for the get_record tool."""
    model_config = ConfigDict(extra="allow")

    module: str
    record_id: str = Field(...)
    include: Optional[list[str]] = None


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
