#!/usr/bin/env python3
"""Lean, read-only FSR MCP server.

The common live + reference-store **read** operations for backend / connector
testing and validation, exposed as a small, safe MCP surface. It re-registers
a curated read subset of the battle-tested `fsr_core.mcp_server` tools onto a
dedicated FastMCP instance — no duplicated live-path logic, and none of the
mutating/authoring tools (push_playbook, run_playbook, emit_*, the agent loop).

Why a separate server: `fsr_core.mcp_server` is the connector's full agent
brain (~60 tools, mixes reads + writes). For ad-hoc testing you want a tight,
read-only set that's cheap in context and can't mutate the platform.

The one non-pure-read here is `run_op`, kept because it's the workhorse for
probing a connector op live; it self-gates unsafe ops (requires confirm=True),
so it stays safe by default.

Creds: the live tools self-load `.env` from the repo root via `probes._env`.

Run:    python python/fsr_read_mcp.py        (stdio transport)
Config: registered in .claude/settings.json as the `fsr-read` MCP server.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Make `fsr_core` (repo root) and `probes` (python/) importable, and run from
# the repo root so store/ + .env relative paths resolve regardless of cwd.
REPO_ROOT = Path(__file__).resolve().parent.parent
for _p in (str(REPO_ROOT), str(REPO_ROOT / "python")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
os.chdir(REPO_ROOT)

from mcp.server.fastmcp import FastMCP  # noqa: E402
import fsr_core.mcp_server as fsrpb  # noqa: E402

read_mcp = FastMCP("fsr-read")

# Curated read-only tools. Grouped by what they touch.
_READ_TOOLS = [
    # --- reference store (offline; no live box needed) ---
    fsrpb.find_connector,             # fuzzy-search connectors
    fsrpb.find_operation,             # list / search a connector's ops
    fsrpb.get_op_schema,              # param schema + best output shape
    fsrpb.get_step_type,              # playbook step-type schema + examples
    fsrpb.list_connector_configurations,  # configured-connector names (cached)
    # --- live reads (hit the box via .env creds) ---
    fsrpb.list_configured_connectors,  # configured connectors + health
    fsrpb.healthcheck_connector,       # one connector's live health
    fsrpb.get_record,                  # read a module record by id/iri
    fsrpb.search_module_records,       # query module records by filter
    fsrpb.list_playbook_runs,          # recent workflow runs
    fsrpb.list_recent_failed_runs,     # recent failed runs (triage)
    fsrpb.get_run_env,                 # a run's vars/env + step results
    fsrpb.run_op,                      # execute one op live (self-gates unsafe)
    fsrpb.render_jinja,                # render a template via the live engine
    # --- validation (pure, offline) ---
    fsrpb.validate_yaml,               # compiler dry-run → structured errors
    fsrpb.verify_playbook,             # full pre-submit gate
]

for _fn in _READ_TOOLS:
    read_mcp.tool()(_fn)


if __name__ == "__main__":
    read_mcp.run(transport="stdio")
