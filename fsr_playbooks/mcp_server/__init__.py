"""FSR Playbook MCP server.

Exposes the compiler + reference store as MCP tools for any agent
(Claude Code, IDE plugins) to author FortiSOAR playbooks via tool use.

Tools:
  find_connector       -- fuzzy-search 714 connectors by name/category/desc
  find_operation       -- list or search ops for a specific connector
  get_op_schema        -- full param schema + best available output shape
  get_connector_source -- fetch operations.py source code (cached after first fetch)
  run_op               -- execute one op live; infers + caches real output shape
  get_step_type        -- schema + examples for a playbook step type
  find_jinja_filter    -- search the Jinja filter catalog
  render_jinja         -- render a template against the live FSR endpoint
  search_playbooks     -- FTS over playbook_seen patterns
  validate_yaml        -- compiler dry-run → structured errors
  compile_yaml         -- compile YAML → FSR WorkflowCollection JSON string

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
    tools_compose,
    tools_connector_discovery,
    tools_corpus,
    tools_discovery,
    tools_edr,
    tools_emit,
    tools_enhancement,
    tools_execution,
    tools_jinja,
    tools_noc,
    tools_picklists,
    tools_plan,
    tools_playbook_run,
    tools_recipe,
    tools_records,
    tools_triage,
    tools_verify,
    tools_workflows,
)

# Import shared infrastructure for external use
from ._shared import DB_PATH, REPO_ROOT, _db, _err, _rows, _safe_op_category, mcp

# Analysis tools
from .tools_analysis import (
    _coerce_literal_list,
    _infer_output_shape,
    _truthy,
    analyze_playbook,
    continue_debug_session,
    get_debug_session,
    precheck_connector_installed,
    start_debug_session,
    step_debug_session,
    step_test,
    step_through_playbook,
    stop_debug_session,
    suggest_fix_for_diagnostic,
    synthesize_http_step,
)

# Catalog (Phase 0 + 0.5 of CONNECTOR_INTEGRATION_PLAN)
from .tools_catalog import (
    find_api_example,
    find_api_fixture,
    find_api_product,
    propose_http_fallback,
)
from .tools_compile import (
    _FRIENDLY_FORMS,
    build_playbook_from_trace,
    compile_yaml,
    resolve_yaml,
    validate_yaml,
)

# Compilation tools
from .tools_compose import compose_playbook

# Re-export public tool names
# (Users import these via `from mcp_server import <tool_name>`)
# Connector & playbook-run discovery (shared with the SOC triage path)
from .tools_connector_discovery import (
    find_containment_actions,
    find_enrichment_actions,
    find_record_actions,
    get_run_env,
    list_configured_connectors,
    list_playbook_runs,
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

# Record reads + hunt tools (the retired per-axis helpers stay importable for
# dispatch and call_mcp_tool; see llm.hunt_tools)
from .tools_edr import edr_host
from .tools_emit import (
    emit_action_card,
    emit_capability_gap_card,
    emit_card,
    emit_choice_card,
    emit_decision_step,
    emit_enhancement_offer,
    emit_manual_input,
    emit_playbook_offer,
    emit_verdict,  # Internal only; not exported in __all__
)
from .tools_enhancement import edit_playbook, verify_enhancement

# Execution tools
from .tools_execution import (
    _record_verification,
    connector_health,
    dry_run_playbook,
    healthcheck_connector,
    push_playbook,
    run_op,
)

# Jinja tools
from .tools_find import find
from .tools_jinja import (
    find_jinja_example,
    find_jinja_filter,
    find_jinja_pattern,
    get_filter_examples,
    render_jinja,
)
from .tools_noc import (
    faz_event_summary,
    faz_search_by_serial,
    faz_search_device_events,
    fmg_device,
    fmg_get_device_list,
    fmg_get_device_status,
    fmg_get_ha_status,
    fmg_get_policy_package_status,
)

# Picklist tools
from .tools_picklists import (
    get_picklist,
    list_picklists,
    picklist,
    picklist_for_field,
    precheck_picklist_value,
    resolve_picklist_value,
)

# Verify
from .tools_plan import plan_playbook
from .tools_playbook_run import list_module_playbooks, resume_playbook, run_playbook

# Recipe tools
from .tools_recipe import (
    assert_playbook_outcome,
    diagnose_yaml_against_pb_execution,
    find_recipe,
    generate_recipe,
    set_failed_run_provider,
    why_did_playbook_fail,
)
from .tools_records import create_record, update_record
from .tools_triage import (
    faz_get_alerts,
    faz_raw_query,
    faz_search,
    faz_search_ip,
    get_record,
    list_recent_failed_runs,
    list_tags,
    search_module_records,
    siem_events_for_incident,
    siem_raw_query,
    siem_search,
    siem_search_host,
    siem_search_ip,
    siem_search_user,
    test_find_record,
    verification_status,
)
from .tools_verify import verify_playbook
from .tools_workflows import (
    build_playbook,
    debug_run,
    investigate_alert,
    orient,
    provision_module,
    repair_playbook,
    verify_effect,
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
    "find",
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
    "resume_playbook",
    "list_module_playbooks",
    "dry_run_playbook",
    "connector_health",
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
    "picklist",
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
    "compose_playbook",
    "plan_playbook",
    "verify_playbook",
    # Emit / card tools
    "emit_card",
    "emit_choice_card",
    "emit_action_card",
    "emit_capability_gap_card",
    "emit_playbook_offer",
    "emit_enhancement_offer",
    "emit_manual_input",
    "emit_decision_step",
    # Catalog (Phase 0 + 0.5)
    "find_api_example",
    "find_api_fixture",
    "find_api_product",
    "propose_http_fallback",
    # Record reads + hunt tools
    "get_record",
    "create_record",
    "build_playbook",
    "debug_run",
    "investigate_alert",
    "orient",
    "provision_module",
    "repair_playbook",
    "verify_effect",
    "update_record",
    "search_module_records",
    "list_tags",
    "list_recent_failed_runs",
    "verification_status",
    "test_find_record",
    "siem_search",
    "faz_search",
    "fmg_device",
    "edr_host",
    # Retired per-axis hunt helpers (dispatchable, never advertised)
    "siem_events_for_incident",
    "siem_raw_query",
    "siem_search_ip",
    "siem_search_host",
    "siem_search_user",
    "faz_get_alerts",
    "faz_event_summary",
    "faz_raw_query",
    "faz_search_ip",
    "faz_search_device_events",
    "faz_search_by_serial",
    "fmg_get_device_list",
    "fmg_get_device_status",
    "fmg_get_ha_status",
    "fmg_get_policy_package_status",
]
