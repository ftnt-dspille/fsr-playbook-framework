#!/usr/bin/env python3
"""Lean, read-only FSR MCP server.

The common live + reference-store **read** operations for backend / connector
testing AND widget (frontend) work, exposed as a small, safe MCP surface. It
re-registers a curated read subset of the battle-tested `fsr_playbooks.mcp_server`
tools onto a dedicated FastMCP instance — no duplicated live-path logic, and
none of the mutating/authoring tools (push_playbook, run_playbook, emit_*, the
agent loop).

Widget-side tools (read-only, .env-cred client):
  - picklists: list_picklists / get_picklist / picklist_for_field /
    resolve_picklist_value / precheck_picklist_value (csField dropdowns,
    cs-conditional, c3charts groupby .itemValue, install-time FK guards)
  - get_connector_icon (action-renderer / widget rendering)
  - get_module_metadata / list_modules (field/attribute schema — the #1 widget
    lookup; defined here, not in the agent brain, since the agent doesn't need
    them but widget templates constantly do)
  - list_widgets / get_widget (what's installed + current uuid/version)
Endpoint gotchas baked in: `staging_model_metadatas` needs `$relationships=true`
to inline `attributes`; `/api/3/widgets` 500s on `$orderby=name` (sort client-
side). WRITES (widget install, record create/delete) are deliberately excluded —
keep this server read-only; put mutations in a separate gated server.

Why a separate server: `fsr_playbooks.mcp_server` is the connector's full agent
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

# Make `fsr_playbooks` (repo root) and `probes` (python/) importable, and run from
# the repo root so store/ + .env relative paths resolve regardless of cwd.
REPO_ROOT = Path(__file__).resolve().parent.parent
for _p in (str(REPO_ROOT), str(REPO_ROOT / "tooling")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
os.chdir(REPO_ROOT)

from typing import Any  # noqa: E402

from mcp.server.fastmcp import FastMCP  # noqa: E402
import fsr_playbooks.mcp_server as fsrpb  # noqa: E402

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
    # --- picklists (widget-side: csField dropdowns, cs-conditional, ----------
    #     c3charts groupby .itemValue, install-time picklist FK guards) --------
    fsrpb.list_picklists,              # all picklist names
    fsrpb.get_picklist,                # one picklist's items (value/color/order)
    fsrpb.picklist_for_field,          # field -> its bound picklist
    fsrpb.resolve_picklist_value,      # coerce a label/value to the real item
    fsrpb.precheck_picklist_value,     # validate a value before it FK-errors
    fsrpb.get_connector_icon,          # connector icon (action-renderer/widgets)
    # --- validation (pure, offline) ---
    fsrpb.validate_yaml,               # compiler dry-run → structured errors
    fsrpb.verify_playbook,             # full pre-submit gate
]

for _fn in _READ_TOOLS:
    read_mcp.tool()(_fn)


# ───────────────────── widget-side live reads (Tier 2/3) ─────────────────
# These are test-surface tools (module/field metadata + widget lifecycle),
# defined here rather than in the connector's agent brain — the agent doesn't
# need them, but widget work constantly does. Read-only; .env-cred client.

def _live_get(path: str) -> Any:
    """GET a hydra path via the .env pyfsr client. Returns parsed JSON, or a
    {"error": ...} dict when the box isn't configured / the call fails."""
    try:
        from probes._env import get_client, get_config
    except Exception as e:  # noqa: BLE001
        return {"error": f"could not import _env: {e!r}"}
    if not get_config().is_live():
        return {"error": "FSR not configured (FSR_BASE_URL / auth missing in .env)"}
    client = get_client()
    try:
        return client.get(path)
    except Exception as e:  # noqa: BLE001
        return {"error": f"GET {path} failed: {e!r}"}


def _picklist_name(attr: dict) -> str | None:
    """The picklist listName an attribute binds to (e.g. 'AlertStatus'),
    mirroring probe_modules._picklist_list_name."""
    ds = attr.get("dataSource") or {}
    if not isinstance(ds, dict):
        return None
    for f in (ds.get("query") or {}).get("filters", []) or []:
        if isinstance(f, dict) and f.get("field") == "listName__name":
            v = f.get("value")
            if isinstance(v, str):
                return v
    return None


_META_BASE = "/api/3/staging_model_metadatas?$limit=2147483647&$orderby=type"


def get_module_metadata(module: str) -> dict:
    """Field/attribute schema for one module — the #1 widget lookup.

    Returns each field's `name`, `title`, `type` (the attr type IS the related
    module type for relationship fields), `required`, and `picklist_name` when
    picklist-backed (call `get_picklist(name)` for its values). `module` is the
    module *type* (e.g. 'alerts', 'incidents'); plural module names on
    forticloud are fine. Use this to drive csField, cs-conditional, and any
    field-aware widget template.
    """
    data = _live_get(f"{_META_BASE}&$relationships=true")
    if isinstance(data, dict) and data.get("error"):
        return data
    members = (data or {}).get("hydra:member") or []
    want = module.strip().lower()
    hit = next((m for m in members
                if str(m.get("type", "")).lower() == want
                or str(m.get("module", "")).lower() == want), None)
    if hit is None:
        types = sorted({m.get("type") for m in members if m.get("type")})
        return {"error": f"module {module!r} not found",
                "available": types[:80]}
    fields = []
    for a in (hit.get("attributes") or []):
        if not isinstance(a, dict) or not a.get("name"):
            continue
        validation = a.get("validation")
        fields.append({
            "name": a.get("name"),
            "title": a.get("title") or a.get("displayName") or a.get("name"),
            "type": a.get("type") or a.get("formType"),
            "required": bool(isinstance(validation, dict)
                             and validation.get("required") is True),
            "picklist_name": _picklist_name(a),
        })
    return {
        "module": hit.get("type"),
        "label": hit.get("displayName") or hit.get("module") or hit.get("type"),
        "plural": hit.get("module"),
        "field_count": len(fields),
        "fields": fields,
    }


def list_modules() -> dict:
    """Lightweight list of every module: `type`, `label`, `plural`. Use to
    discover the right module type (and the plural-vs-singular name that bites
    on forticloud) before a metadata/record lookup."""
    data = _live_get(_META_BASE)  # no $relationships → small payload
    if isinstance(data, dict) and data.get("error"):
        return data
    members = (data or {}).get("hydra:member") or []
    mods = [{
        "type": m.get("type"),
        "label": m.get("displayName") or m.get("module") or m.get("type"),
        "plural": m.get("module"),
    } for m in members if m.get("type")]
    mods.sort(key=lambda m: str(m["type"]))
    return {"count": len(mods), "modules": mods}


def list_widgets() -> dict:
    """Installed widgets with `name`, `uuid`, `category`, `version` — confirm
    what's on the box and the current uuid/version (a push mints a new uuid)."""
    # NB: /api/3/widgets 500s on `$orderby=name` — sort in python instead.
    data = _live_get("/api/3/widgets?$limit=2147483647")
    if isinstance(data, dict) and data.get("error"):
        return data
    members = (data or {}).get("hydra:member") or []
    widgets = [{
        "name": w.get("name"),
        "uuid": w.get("uuid") or (w.get("@id") or "").rsplit("/", 1)[-1],
        "title": w.get("title"),
        "category": w.get("category"),
        "version": w.get("version"),
    } for w in members]
    widgets.sort(key=lambda w: str(w.get("name") or ""))
    return {"count": len(widgets), "widgets": widgets}


def get_widget(uuid_or_name: str) -> dict:
    """One widget's full record by uuid (or exact name) — template/options/
    metadata for inspecting an installed widget."""
    key = uuid_or_name.strip()
    if key and "-" in key and " " not in key:  # looks like a uuid
        data = _live_get(f"/api/3/widgets/{key}")
        if isinstance(data, dict) and not data.get("error"):
            return data
    # fall back to name match
    data = _live_get("/api/3/widgets?$limit=2147483647")
    if isinstance(data, dict) and data.get("error"):
        return data
    members = (data or {}).get("hydra:member") or []
    hit = next((w for w in members
                if str(w.get("name", "")).lower() == key.lower()
                or str(w.get("uuid", "")) == key), None)
    if hit is None:
        return {"error": f"widget {uuid_or_name!r} not found"}
    return hit


for _fn in (get_module_metadata, list_modules, list_widgets, get_widget):
    read_mcp.tool()(_fn)


if __name__ == "__main__":
    read_mcp.run(transport="stdio")
