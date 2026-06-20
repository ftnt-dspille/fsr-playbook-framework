"""Public execution/runtime extension API (RECONCILIATION_PLAN Phase 1, D4=(a)).

The carved-out triage cluster (now living in the connector, not this package)
needs a handful of run/healthcheck/DB helpers that today are underscore-private
internals of `mcp_server.tools_execution`, `mcp_server._shared`, `llm.tools`, and
`agent.skill_trace`. Rather than let the connector reach into those private names
(fragile — they can be refactored out from under it), this module is the SINGLE
stable surface the connector may import for execution support.

Contract:
- These names are frozen by `tests/test_public_surface_contract.py`. Renaming or
  dropping one breaks the library suite before the connector ever sees it.
- This module only RE-EXPORTS; the underscore originals stay put and unrenamed, so
  existing in-package callers are untouched. If an internal helper's behaviour must
  change, change it at the source — the facade name and signature are the contract.

See RECONCILIATION_PLAN.md §Phase 1 for the rename map and rationale.
"""
from __future__ import annotations

# --- reference DB + shared helpers (mcp_server._shared) ---------------------
from .mcp_server._shared import (
    _VERIF_RANK as VERIF_RANK,
    _capability_gap_suggestion as capability_gap_suggestion,
    _db as open_reference_db,
    _live_client as live_client,
    _rows as query_rows,
)

# --- run / healthcheck (mcp_server.tools_execution) -------------------------
# `run_op` is already a public @mcp.tool(); re-exported here so the connector has
# one import site for the whole execution surface.
from .mcp_server.tools_execution import (
    _agent_configured_rows as agent_configured_rows,
    _cached_health as cached_health,
    _fetch_runs_both as fetch_runs,
    _live_healthcheck as live_healthcheck,
    _shape_run as shape_run,
    _store_health as store_health,
    run_op,
)

# --- op-approval tiering (llm.tools) ----------------------------------------
from .llm.tools import _tier_for_run_op as tier_for_run_op

# --- trace control (agent.skill_trace) --------------------------------------
from .agent.skill_trace import mute_recording

__all__ = [
    # _shared
    "VERIF_RANK",
    "capability_gap_suggestion",
    "open_reference_db",
    "live_client",
    "query_rows",
    # tools_execution
    "agent_configured_rows",
    "cached_health",
    "fetch_runs",
    "live_healthcheck",
    "shape_run",
    "store_health",
    "run_op",
    # llm.tools
    "tier_for_run_op",
    # agent.skill_trace
    "mute_recording",
]
