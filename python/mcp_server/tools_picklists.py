"""MCP tools: Tools Picklists"""
from __future__ import annotations
from . import _shared

import difflib
import json
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any

from ._shared import (
    mcp,
    _err,
    _rows,
    _verifications_for,
    _serialize_compiler_error,
    _infer_shape,
    _store_observed_schema,
    REPO_ROOT,
)
# Import DB_PATH for local use
DB_PATH = _shared.DB_PATH

# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
def list_picklists() -> dict[str, Any]:
    """List every picklist `listName.name` known to the FSR instance.

    Use when the agent needs to discover what picklists exist (e.g.
    'Severity', 'AlertStatus', 'Threat Type') before resolving a value
    to an IRI. Live-fetched once per process and cached.
    """
    client = _shared._live_client()
    if client is None:
        return {"error": "FSR instance not configured"}
    from picklists import list_picklist_names
    names = list_picklist_names(client)
    return {"count": len(names), "names": names}

@mcp.tool()
def get_picklist(name: str) -> dict[str, Any]:
    """List items of a single picklist as [{itemValue, uuid, iri, ordinal}].

    Args:
        name: picklist `listName.name` (e.g. 'AlertStatus', 'Severity').
              Use list_picklists() to discover.
    """
    client = _shared._live_client()
    if client is None:
        return {"error": "FSR instance not configured"}
    from picklists import picklist_values
    items = picklist_values(client, name)
    return {"name": name, "count": len(items), "items": items}

@mcp.tool()
def picklist_for_field(module: str, field: str) -> dict[str, Any]:
    """Auto-discover the picklist behind a (module, field).

    Returns the picklist_name plus the offline list of valid string
    values pulled from the local module_fields cache. Tries heuristic
    names first (e.g. 'AlertStatus' for alerts.status), then falls back
    to a Jaccard-overlap match against all live picklist values. Result
    persists to store/picklist_name_map.json.

    Args:
        module: lowercase module name, e.g. 'alerts', 'incidents'.
        field:  field name, e.g. 'status', 'severity', 'type'.
    """
    client = _shared._live_client()
    if client is None:
        return {"error": "FSR instance not configured"}
    from picklists import picklist_name_for, valid_values
    pn = picklist_name_for(client, module, field)
    return {
        "module": module, "field": field,
        "picklist_name": pn,
        "valid_values_local": valid_values(module, field),
    }

@mcp.tool()
def resolve_picklist_value(value: str, picklist_name: str | None = None,
                           module: str | None = None,
                           field: str | None = None) -> dict[str, Any]:
    """Resolve a friendly value (e.g. 'High') to a picklist IRI.

    Provide either `picklist_name`, or both `module` + `field` to
    auto-discover. Strings that already start with '/api/3/' pass
    through unchanged. Returns close-match suggestions when the value
    isn't an exact itemValue — useful when the LLM authored an invalid
    value like 'In Progress' for AlertStatus (which only has Open,
    Investigating, Pending, Closed, Active, Re-Opened).
    """
    client = _shared._live_client()
    if client is None:
        return {"error": "FSR instance not configured"}
    from picklists import resolve_iri, picklist_name_for, picklist_values
    pn = picklist_name
    if pn is None and module and field:
        pn = picklist_name_for(client, module, field)
    if pn is None:
        return {"error": "picklist_name unknown — provide it, or "
                         "(module, field) for auto-discovery"}
    iri = resolve_iri(client, value, picklist_name=pn)
    if iri:
        return {"ok": True, "iri": iri, "picklist_name": pn,
                "value": value}
    items = picklist_values(client, pn)
    valid = [it.get("itemValue") for it in items]
    # Cheap fuzzy: prefix or substring match.
    vl = value.lower()
    suggestions = [v for v in valid if v and (
        v.lower().startswith(vl) or vl in v.lower() or
        v.lower() in vl)]
    return {"ok": False, "picklist_name": pn, "value": value,
            "valid_values": valid, "suggestions": suggestions[:5]}


# ---------------------------------------------------------------------------
# api_examples_catalog integration (HTTP virtual-connector fallback)
# ---------------------------------------------------------------------------
# The reference DB ATTACHes the read-only catalog at common.py:62. These
# tools surface 207k+ third-party API examples so the assistant can author
# playbooks via the FortiSOAR HTTP connector when a native connector for
# the target vendor is missing.
#
# Auth taxonomy: the catalog stores free-text auth_method strings; the
# HTTP connector expects an `auth_type` enum. Mapping is deterministic.
_HTTP_AUTH_MAP = {
    "basic": "Basic",
    "bearer": "Bearer Token",
    "token": "Bearer Token",
    "api key": "API Key in Header",
    "apikey": "API Key in Header",
    "oauth": "OAuth 2.0",
    "oauth2": "OAuth 2.0",
    "no auth": "No Auth",
    "none": "No Auth",
}


def _map_http_auth(catalog_auth: str | None) -> str:
    if not catalog_auth:
        return "No Auth"
    a = catalog_auth.lower()
    for needle, mapped in _HTTP_AUTH_MAP.items():
        if needle in a:
            return mapped
    return "No Auth"

@mcp.tool()
def precheck_picklist_value(picklist_name: str,
                            value: str) -> dict[str, Any]:
    """Verify a friendly value resolves to an IRI on the live FSR before
    embedding `{{ 'PL' | picklist('value') }}` in a playbook.

    Catches typos like 'In Progress' for AlertStatus (which only has
    Open / Investigating / Pending / Closed / Active / Re-Opened).
    Returns close-match suggestions when the value isn't an exact
    itemValue.
    """
    client = _shared._live_client()
    if client is None:
        return {"ok": False, "code": "no_live_fsr",
                "message": "FSR instance not configured"}
    from recipes.prechecks import check_picklist_value
    result = check_picklist_value(client, picklist_name, value).to_dict()
    _persist_precheck_verification(
        "picklist", f"{picklist_name}:{value}", "live_api_get", result,
    )
    return result


def _persist_precheck_verification(kind: str, key: str, method: str,
                                    result: dict[str, Any]) -> None:
    """Record a verification row from a precheck result.

    `result.ok` truthy → tested_pass; explicit False → tested_fail; any
    other shape (no live FSR, etc.) is skipped so we don't pollute the
    table with environmental misses.
    """
    ok = result.get("ok")
    if ok is True:
        status = "tested_pass"
    elif ok is False and result.get("code") not in {"no_live_fsr"}:
        status = "tested_fail"
    else:
        return
    import datetime
    ts = datetime.datetime.utcnow().isoformat()
    notes = (result.get("message") or result.get("code") or "")[:500]
    try:
        with sqlite3.connect(_shared.DB_PATH) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO verifications
                   (kind, key, method, status, ts, notes)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (kind, key, method, status, ts, notes),
            )
    except Exception:
        pass