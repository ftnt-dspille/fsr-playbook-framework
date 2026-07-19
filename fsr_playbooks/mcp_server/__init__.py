"""FSR Playbook MCP server.

Exposes the compiler + reference store as MCP tools for any agent
(Claude Code, IDE plugins) to author FortiSOAR playbooks via tool use.

Tools:
  find_connector       — fuzzy-search 714 connectors by name/category/desc
  find_operation       — list or search ops for a specific connector
  get_op_schema        — full param schema + best available output shape
  get_connector_source — fetch operations.py source code (cached after first fetch)
  run_op               — execute one op live; infers + caches real output shape
  get_step_type        — schema + examples for a playbook step type
  find_jinja_filter    — search the Jinja filter catalog
  render_jinja         — render a template against the live FSR endpoint
  search_playbooks     — FTS over playbook_seen patterns
  validate_yaml        — compiler dry-run → structured errors
  compile_yaml         — compile YAML → FSR WorkflowCollection JSON string

Run:
  python -m mcp_server                    (stdio transport, default)
  fsrpb mcp                               (via CLI entry-point)
"""
from __future__ import annotations

# Import and register all tools
from . import (
    tools_analysis,
    tools_catalog,
    tools_compile,
    tools_connector_discovery,
    tools_corpus,
    tools_discovery,
    tools_execution,
    tools_jinja,
    tools_picklists,
    tools_recipe,
    tools_verify,
    tools_enhancement,
    tools_emit,
)

# Import shared infrastructure for external use
from ._shared import mcp, REPO_ROOT, DB_PATH, _safe_op_category, _err, _db, _rows

# Re-export public tool names
# (Users import these via `from mcp_server import <tool_name>`)

# Connector & playbook-run discovery (shared with the SOC triage path)
from .tools_connector_discovery import (
    get_run_env,
    list_configured_connectors,
    list_playbook_runs,
    find_containment_actions,
    find_enrichment_actions,
)

# Discovery tools
from .tools_discovery import (
    _CONFIG_CACHE,
    _ICON_CACHE,
    find_connector,
    find_operation,
    find_operation_example,
    get_connector_icon,
    get_connector_source,
    get_op_schema,
    get_step_type,
    list_connector_configurations,
)

# Compilation tools
from .tools_compile import (
    _FRIENDLY_FORMS,
    build_playbook_from_trace,
    compile_yaml,
    resolve_yaml,
    validate_yaml,
)

# Execution tools
from .tools_execution import (
    dry_run_playbook,
    healthcheck_connector,
    push_playbook,
    run_op,
    run_playbook,
    _record_verification,
)

# Jinja tools
from .tools_jinja import (
    find_jinja_example,
    find_jinja_filter,
    find_jinja_pattern,
    get_filter_examples,
    render_jinja,
)

# Corpus tools
from .tools_corpus import (
    find_step_examples,
    find_step_recipe,
    review_chat_session,
    review_recent_thumbs_down,
    search_api_examples,
    search_playbooks,
)

# Picklist tools
from .tools_picklists import (
    get_picklist,
    list_picklists,
    picklist_for_field,
    precheck_picklist_value,
    resolve_picklist_value,
)

# Analysis tools
from .tools_analysis import (
    analyze_playbook,
    precheck_connector_installed,
    step_test,
    step_through_playbook,
    start_debug_session,
    step_debug_session,
    continue_debug_session,
    stop_debug_session,
    get_debug_session,
    suggest_fix_for_diagnostic,
    synthesize_http_step,
    _coerce_literal_list,
    _infer_output_shape,
    _truthy,
)

# Recipe tools
from .tools_recipe import (
    assert_playbook_outcome,
    diagnose_yaml_against_pb_execution,
    find_recipe,
    generate_recipe,
    set_failed_run_provider,
    why_did_playbook_fail,
)

# Verify
from .tools_verify import verify_playbook
from .tools_enhancement import verify_enhancement
from .tools_emit import (
    emit_action_card,
    emit_capability_gap_card,
    emit_choice_card,
    emit_decision_step,
    emit_manual_input,
    emit_patch_proposal,
    emit_playbook_offer,
)

# Catalog (Phase 0 + 0.5 of CONNECTOR_INTEGRATION_PLAN)
from .tools_catalog import (
    find_api_example,
    find_api_fixture,
    find_api_product,
    propose_http_fallback,
)

# =========================================================================
# Entry point
# =========================================================================


def main() -> None:
    """Run the MCP server on stdio transport."""
    mcp.run(transport="stdio")


__all__ = [
    # Infrastructure
    "mcp",
    "main",
    "REPO_ROOT",
    "DB_PATH",
    # Discovery
    "_CONFIG_CACHE",
    "_ICON_CACHE",
    "find_connector",
    "find_operation",
    "find_operation_example",
    "get_connector_icon",
    "get_connector_source",
    "get_op_schema",
    "get_step_type",
    "list_connector_configurations",
    # Compilation
    "validate_yaml",
    "resolve_yaml",
    "compile_yaml",
    "build_playbook_from_trace",
    "_FRIENDLY_FORMS",
    # Execution
    "run_op",
    "push_playbook",
    "run_playbook",
    "dry_run_playbook",
    "healthcheck_connector",
    # Jinja
    "find_jinja_filter",
    "find_jinja_pattern",
    "find_jinja_example",
    "get_filter_examples",
    "render_jinja",
    # Corpus
    "search_playbooks",
    "review_chat_session",
    "review_recent_thumbs_down",
    "find_step_examples",
    "find_step_recipe",
    "search_api_examples",
    # Picklists
    "list_picklists",
    "get_picklist",
    "picklist_for_field",
    "resolve_picklist_value",
    "precheck_picklist_value",
    # Analysis
    "step_through_playbook",
    "start_debug_session",
    "step_debug_session",
    "continue_debug_session",
    "stop_debug_session",
    "get_debug_session",
    "analyze_playbook",
    "suggest_fix_for_diagnostic",
    "step_test",
    "precheck_connector_installed",
    "synthesize_http_step",
    # Recipe
    "assert_playbook_outcome",
    "find_recipe",
    "generate_recipe",
    "diagnose_yaml_against_pb_execution",
    "why_did_playbook_fail",
    "set_failed_run_provider",
    # Verify
    "verify_playbook",
    # Catalog (Phase 0 + 0.5)
    "find_api_example",
    "find_api_fixture",
    "find_api_product",
    "propose_http_fallback",
]
