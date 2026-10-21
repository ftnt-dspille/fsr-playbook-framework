"""The record-read and hunt tool names, in one place.

`llm.tools` registers them (SAFE_TOOLS / TOOL_TIERS / RETIRED_TO_UNION) and
`llm.intents` scopes them to triage (TRIAGE_ONLY_TOOLS). Both import from here
so the two lists cannot drift. Dependency-free on purpose: `intents` imports
nothing heavy.
"""
from __future__ import annotations

# Advertised record reads + per-product hunt tools (mcp_server.tools_triage /
# tools_noc / tools_edr). Read-only, tier 1.
HUNT_TOOLS: tuple[str, ...] = (
    "get_record",
    "search_module_records",
    "siem_search",
    "faz_search",
    "fmg_device",
    "edr_host",
)

# Per-axis hunt helpers → the merged hunt tool that replaced each (#69, B3a).
# Kept registered, never advertised: saved playbooks call them through
# `call_mcp_tool`, and persona allowlists may still name them.
HUNT_RETIRED_TO_UNION: dict[str, str] = {
    "siem_events_for_incident": "siem_search", "siem_raw_query": "siem_search",
    "siem_search_ip": "siem_search", "siem_search_host": "siem_search",
    "siem_search_user": "siem_search",
    "faz_get_alerts": "faz_search", "faz_event_summary": "faz_search",
    "faz_raw_query": "faz_search", "faz_search_ip": "faz_search",
    "faz_search_device_events": "faz_search", "faz_search_by_serial": "faz_search",
    "fmg_get_device_list": "fmg_device", "fmg_get_device_status": "fmg_device",
    "fmg_get_ha_status": "fmg_device",
    "fmg_get_policy_package_status": "fmg_device",
}
