"""MCP tools: Tools Picklists"""
from __future__ import annotations

import sqlite3
from typing import Any

from .. import picklists as _pl
from . import _shared
from ._shared import (
    _db,
    _err,
    mcp,
)

# Import DB_PATH for local use
DB_PATH = _shared.DB_PATH

# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------
#
# All five resolve through `fsr_playbooks.picklists`: reference store first,
# live instance second, `NoPicklistData` (with the fix) last. They previously
# required BOTH a configured live instance AND this repo's `tooling/` on
# sys.path -- neither holds on an appliance, so they were dead there.


@mcp.tool()
def list_picklists() -> dict[str, Any]:
    """List every picklist name known to this instance -- use it to discover
    what picklists exist (Severity, AlertStatus, Threat Type) when you do
    not yet know the name. If you know the module and field instead,
    picklist_for_field finds the picklist for you; to turn a friendly value
    into the IRI a playbook needs, use resolve_picklist_value.

    Use when the agent needs to discover what picklists exist (e.g.
    'Severity', 'AlertStatus', 'Threat Type') before resolving a value
    to an IRI. Answered from the local reference store when it is warmed,
    so it works with no live instance; falls back to a live fetch.
    """
    with _db() as conn:
        try:
            return _pl.picklist_names(conn, _shared._live_client())
        except _pl.NoPicklistData as exc:
            return _err(exc.code, exc.message, suggestions=exc.suggestions)

@mcp.tool()
def get_picklist(name: str) -> dict[str, Any]:
    """List items of a single picklist as [{itemValue, uuid, iri, ordinal}].

    An unknown NAME returns `unknown_picklist` plus near-matches (not an
    empty list) -- "this picklist has no values" and "there is no such
    picklist" are different answers and the agent branches on them
    differently.

    Args:
        name: picklist `listName.name` (e.g. 'AlertStatus', 'Severity').
              Use list_picklists() to discover.
    """
    with _db() as conn:
        try:
            return _pl.picklist_items(conn, name, _shared._live_client())
        except _pl.NoPicklistData as exc:
            return _err(exc.code, exc.message, suggestions=exc.suggestions)

@mcp.tool()
def picklist_for_field(module: str, field: str) -> dict[str, Any]:
    """Given a module and field (e.g. alerts + severity), find WHICH picklist
    backs it, plus its valid values. Start here when you are setting a
    picklist field in a playbook and do not know the picklist name. Then
    pass the value through resolve_picklist_value -- a playbook field needs
    the IRI, and a raw string like 'High' will not bind.

    Returns the picklist_name plus the offline list of valid string
    values pulled from the local module_fields cache. Tries heuristic
    names first (e.g. 'AlertStatus' for alerts.status), then falls back
    to a Jaccard-overlap match against all live picklist values. Result
    persists to data/picklist_name_map.json.

    Args:
        module: lowercase module name, e.g. 'alerts', 'incidents'.
        field:  field name, e.g. 'status', 'severity', 'type'.
    """
    client = _shared._live_client()
    with _db() as conn:
        pn = _pl.picklist_name_for(conn, module, field, client)
        values = _pl.valid_values(conn, module, field)
        out = {"module": module, "field": field, "picklist_name": pn,
               "valid_values_local": values}
        if pn is None:
            # §H: never a bare null. Say which of the two misses this is --
            # unknown field vs. known field with no picklist behind it.
            try:
                known_field = bool(conn.execute(
                    "SELECT 1 FROM module_fields WHERE module_name=? "
                    "AND field_name=? LIMIT 1", (module, field)).fetchone())
            except sqlite3.Error:
                known_field = False
            out["note"] = (
                (repr(module + "." + field) + " is not a picklist-backed "
                 "field -- author it as a plain value, no IRI needed.")
                if known_field else
                ("no field " + repr(field) + " on module " + repr(module)
                 + " in this catalog, which carries the picklist-backed "
                   "fields. So either the field takes a plain value (no IRI "
                   "needed), or the catalog is not warmed -- run `warmup` "
                   "against the target appliance to get its real fields. "
                   "Check the module name too: lowercase plural, e.g. "
                   "'alerts'.")
            )
        return out

@mcp.tool()
def resolve_picklist_value(value: str, picklist_name: str | None = None,
                           module: str | None = None,
                           field: str | None = None) -> dict[str, Any]:
    """Convert a friendly picklist value ('High') into the IRI a playbook field
    actually requires. ALWAYS run this before putting a picklist value in
    YAML: a bare string does not bind, and invented values are a common
    authoring bug. Give it picklist_name, or module + field to
    auto-discover. Values already starting with /api/3/ pass through, and a
    near-miss returns close-match suggestions rather than failing silently.

    Provide either `picklist_name`, or both `module` + `field` to
    auto-discover. Strings that already start with '/api/3/' pass
    through unchanged. Returns close-match suggestions when the value
    isn't an exact itemValue -- useful when the LLM authored an invalid
    value like 'In Progress' for AlertStatus (which only has Open,
    Investigating, Pending, Closed, Active, Re-Opened).
    """
    client = _shared._live_client()
    with _db() as conn:
        pn = picklist_name
        if pn is None and module and field:
            pn = _pl.picklist_name_for(conn, module, field, client)
        if pn is None:
            return _err(
                "picklist_unknown",
                "picklist_name unknown"
                + (" for " + repr(str(module) + "." + str(field))
                   if module and field else ""),
                suggestions=[
                    "pass picklist_name directly (list_picklists shows them)",
                    "or pass module + field so it can be auto-discovered",
                ])
        try:
            return _pl.resolve_iri(conn, value, pn, client)
        except _pl.NoPicklistData as exc:
            return _err(exc.code, exc.message, suggestions=exc.suggestions)


@mcp.tool()
def picklist(name: str = "", module: str = "", field: str = "",
             value: str = "") -> dict[str, Any]:
    """ONE picklist tool -- discover, inspect, and resolve; the args you pass
    pick the mode.

    Which args to pass: `value` alone decides resolution -- pass it (with
    `name`, or `module`+`field` to auto-discover the picklist) to turn a
    friendly value like 'High' into the IRI a playbook field requires; ALWAYS
    do this before putting a picklist value in YAML, a bare string does not
    bind. `module`+`field` without a value answers WHICH picklist backs a
    record field (e.g. alerts + severity) plus its valid values. `name` alone
    lists one picklist's items; an unknown name returns near-matches, not an
    empty list. No args lists every picklist name on this instance. Answered
    from the local reference store when warmed, live fetch as fallback.
    """
    from . import (  # noqa: PLC0415 - late import avoids a registration cycle
        get_picklist,
        list_picklists,
        picklist_for_field,
        resolve_picklist_value,
    )
    if value:
        out = resolve_picklist_value(value, picklist_name=name or None,
                                     module=module or None,
                                     field=field or None)
        mode = "resolve"
    elif module or field:
        if not (module and field):
            return {"ok": False, "code": "missing_field",
                    "message": "field lookup needs BOTH `module` and `field` "
                               "(e.g. module='alerts', field='severity')"}
        out = picklist_for_field(module, field)
        mode = "field"
    elif name:
        out = get_picklist(name)
        mode = "items"
    else:
        out = list_picklists()
        mode = "list"
    if isinstance(out, dict):
        out.setdefault("mode", mode)
        return out
    return {"mode": mode, "results": out}


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
    itemValue. Checks the local reference store first, so it still
    catches typos with no live instance -- the VALUES are globally
    stable even where the per-install IRIs are not.
    """
    client = _shared._live_client()
    with _db() as conn:
        try:
            result = _pl.resolve_iri(conn, value, picklist_name, client)
        except _pl.NoPicklistData as exc:
            return _err(exc.code, exc.message, suggestions=exc.suggestions)
    # `iri_unavailable` means the VALUE checked out and only the per-install
    # IRI is missing -- that is a pass for a precheck, whose question is
    # "would this value be rejected?".
    if result.get("code") == "iri_unavailable":
        result = dict(result, ok=True)
    method = ("live_api_get" if result.get("source") == "live"
              else "reference_db")
    _persist_precheck_verification(
        "picklist", f"{picklist_name}:{value}", method, result,
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

    from .._db import writable_reference_db
    target = writable_reference_db()
    if target is None:
        return  # packaged catalog: enrichment is skipped, never written to
    ts = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None).isoformat()
    notes = (result.get("message") or result.get("code") or "")[:500]
    with sqlite3.connect(str(target)) as conn:
        conn.execute(
            """INSERT OR REPLACE INTO verifications
               (kind, key, method, status, ts, notes)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (kind, key, method, status, ts, notes),
        )