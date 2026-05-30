"""MCP tools: Tools Triage"""
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
    _db,
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
def get_run_env(pb_execution: str) -> dict[str, Any]:
    """Fetch the live Jinja context (`vars` + per-step results) of a past playbook execution.

    The single most useful tool when building the NEXT step in a playbook
    that consumes a prior step's output: it returns exactly what
    `vars.steps.<step_name_underscored>.<field>` will resolve to at runtime.
    Hits GET /api/wf/api/workflows/<pk>/?step_detail=true and rebuilds the
    same shape FSR's widget builds (transform: `step.name.replace(" ", "_")`,
    case preserved).

    Args:
        pb_execution: workflow PK (integer string e.g. "676747") OR task_id UUID

    Returns:
        {
          "status": "finished" | "failed" | ...,
          "name": "<workflow name>",
          "vars": {
            "<env field>": ...,
            "steps": {
              "<step name with spaces→_>": <step result>,
              ...
            }
          }
        }
        or {"error": "..."} on lookup failure.
    """
    try:
        from probes._env import get_client, get_config
    except Exception as e:  # noqa: BLE001
        return {"error": f"could not import _env: {e!r}"}
    cfg = get_config()
    if not cfg.is_live():
        return {"error": "FSR instance not configured (FSR_BASE_URL / FSR_API_KEY missing in .env)"}
    client = get_client()

    # task_id (UUID) → workflow PK. Try live, then historical (purged after ~30-60 min).
    is_uuid = "-" in pb_execution and not pb_execution.isdigit()
    pk_url = None
    base_path = None
    if is_uuid:
        for path in ("/api/wf/api/workflows/", "/api/wf/api/historical-workflows/"):
            try:
                pr = client.session.get(
                    client.base_url + path
                    + f"?task_id={pb_execution}&parent_wf__isnull=True&format=json&limit=1",
                    verify=client.verify_ssl,
                )
                members = (pr.json() or {}).get("hydra:member") or []
            except Exception:  # noqa: BLE001
                continue
            if members:
                pk_url = members[0].get("@id") or ""
                base_path = path
                break
        if not pk_url:
            return {"error": f"no workflow run found for task_id {pb_execution!r} (checked live + historical)"}
        url = client.base_url + "/api" + pk_url + "?step_detail=true"
    else:
        url = client.base_url + f"/api/wf/api/workflows/{pb_execution}/?step_detail=true"

    try:
        r = client.session.get(url, verify=client.verify_ssl)
    except Exception as e:  # noqa: BLE001
        return {"error": f"fetch failed: {e!r}"}
    # Numeric PK can live in either table — fall back to historical on 404.
    if r.status_code == 404 and not is_uuid:
        url = client.base_url + f"/api/wf/api/historical-workflows/{pb_execution}/?step_detail=true"
        try:
            r = client.session.get(url, verify=client.verify_ssl)
        except Exception as e:  # noqa: BLE001
            return {"error": f"historical fetch failed: {e!r}"}
    if r.status_code != 200:
        return {"error": f"HTTP {r.status_code}", "body": r.text[:300]}
    data = r.json()
    env_obj = data.get("env") or {}
    steps_arr = data.get("steps") or []
    steps_map: dict = {}
    for s in steps_arr:
        name = s.get("name")
        if isinstance(name, str):
            steps_map[name.replace(" ", "_")] = s.get("result") or {}
    return {
        "status": data.get("status"),
        "name": data.get("name"),
        "vars": dict(env_obj, steps=steps_map),
    }

@mcp.tool()
def list_configured_connectors(probe: bool = False,
                               verbose: bool = False) -> dict[str, Any]:
    """List connectors that are configured AND active on the live FSR instance.

    A connector with no configuration cannot be called — it'll fail at runtime
    even if it appears in `find_connector`. Use this BEFORE picking which
    connector to put in a playbook.

    Args:
        probe: when True, also healthcheck each one (one HTTP call per
            connector — slower but gives live "Available"/"Disconnected"
            status). When False (default), just lists the configured set.
        verbose: when True, include label, version, and config_count.
            Default returns only name + status to keep tool-result tokens low.

    Returns:
        {configured: [{name, status[, version, label, config_count]}], probed: bool}
        With probe=True, status is "Available", "Disconnected", or an error.
        With probe=False, status comes from the listing endpoint
        ("Completed" = config saved successfully).
    """
    try:
        from probes._env import get_client, get_config
    except Exception as e:  # noqa: BLE001
        return {"error": f"could not import _env: {e!r}"}
    cfg = get_config()
    if not cfg.is_live():
        return {"error": "FSR instance not configured (FSR_BASE_URL / FSR_API_KEY missing in .env)"}
    client = get_client()
    try:
        r = client.session.post(
            client.base_url
            + "/api/integration/connector_details/?format=json&configured=true&exclude=operation&active=true",
            json={}, verify=client.verify_ssl,
        )
        rows = (r.json().get("data") or []) if r.status_code == 200 else []
    except Exception as e:  # noqa: BLE001
        return {"error": f"connector_details fetch failed: {e!r}"}

    out: list[dict] = []
    for x in rows:
        item: dict[str, Any] = {
            "name": x.get("name"),
            "status": x.get("status"),
        }
        # `version` is needed locally for the probe call regardless of verbose.
        x_version = x.get("version")
        if verbose:
            item["version"] = x_version
            item["label"] = x.get("label")
            item["config_count"] = x.get("config_count")
        if probe and item["name"] and x_version:
            try:
                hr = client.session.get(
                    client.base_url
                    + f"/api/integration/connectors/healthcheck/{item['name']}/{x_version}/",
                    verify=client.verify_ssl,
                )
                item["status"] = (hr.json().get("status") if hr.status_code == 200 else f"http_{hr.status_code}")
            except Exception as e:  # noqa: BLE001
                item["status"] = f"error:{e!r}"
        out.append(item)
    return {"configured": out, "probed": probe, "count": len(out)}

@mcp.tool()
def list_tags(prefix: str | None = None, limit: int = 50) -> dict[str, Any]:
    """List FortiSOAR tag names; use to discover tags before filtering runs by them.

    Backed by `GET /api/3/tags?$export=true`. The instance can have 10k+ tags
    (most are auto-generated from threat-intel data), so always pass a prefix
    when looking for workflow-noise tags like "system" or "testing".

    Args:
        prefix: case-insensitive tag prefix (uses `uuid$like=<prefix>%` —
            the tag entity's primary key IS the tag string). Pass None to
            page through everything.
        limit: max tag names to return.

    Returns:
        {"total": <int>, "tags": [<name>, ...]}.
    """
    client = _shared._live_client()
    if client is None:
        return {"error": "FSR instance not configured"}
    qs = "$export=true"
    if prefix:
        import urllib.parse
        # tag entity stores the tag string in the `uuid` column; use
        # SQL LIKE wildcard which is `%` (URL-encoded `%25`).
        qs += f"&uuid$like={urllib.parse.quote(prefix, safe='')}%25"
    qs += f"&$limit={limit}"
    try:
        r = client.session.get(client.base_url + "/api/3/tags?" + qs,
                               verify=client.verify_ssl)
    except Exception as e:  # noqa: BLE001
        return {"error": f"request failed: {e!r}"}
    if r.status_code != 200:
        return {"error": f"HTTP {r.status_code}: {r.text[:200]}"}
    body = r.json() or {}
    tags = body.get("hydra:member") or []
    return {"total": body.get("hydra:totalItems"), "tags": tags[:limit]}


def _build_run_filter_qs(*, modified_after: str | None,
                         modified_before: str | None,
                         tags_include: str | None,
                         tags_exclude: str | None,
                         user_iri: str | None) -> str:
    """Compose the optional server-side filter querystring shared by both
    /workflows/ and /historical-workflows/ listings.
    """
    import urllib.parse
    parts: list[str] = []
    if modified_after:
        parts.append("modified_after=" + urllib.parse.quote(modified_after, safe=":"))
    if modified_before:
        parts.append("modified_before=" + urllib.parse.quote(modified_before, safe=":"))
    if tags_include is not None:
        # CSV like "system,testing" — keep commas unencoded.
        parts.append("tags_include=" + urllib.parse.quote(tags_include, safe=","))
    if tags_exclude is not None:
        parts.append("tags_exclude=" + urllib.parse.quote(tags_exclude, safe=","))
    if user_iri:
        # IRI like "/api/3/people/<uuid>" — keep slashes.
        parts.append("user=" + urllib.parse.quote(user_iri, safe="/"))
    return ("&" + "&".join(parts)) if parts else ""

@mcp.tool()
def list_recent_failed_runs(limit: int = 20,
                            playbook: str | None = None,
                            include_finished: bool = False,
                            modified_after: str | None = None,
                            modified_before: str | None = None,
                            tags_include: str | None = None,
                            tags_exclude: str | None = "system",
                            user_iri: str | None = None) -> list[dict[str, Any]]:
    """List recent workflow runs (default: failures only) for triage.

    Use this when the user says "my playbook is broken" without naming
    the playbook — fetches the most recently-modified failed/errored
    runs across the instance from BOTH the live and historical workflow
    tables (FSR purges live → historical every ~30-60 min).

    Args:
        limit: max rows to return (default 20)
        playbook: optional name filter (client-side substring match)
        include_finished: include finished runs too (default False —
            failed/finished_with_error/terminated only)
        modified_after: ISO timestamp, e.g. "2026-05-01 05:00:00" (server-side)
        modified_before: ISO timestamp (server-side)
        tags_include: CSV of tag names to require (server-side)
        tags_exclude: CSV of tag names to exclude (default "system" to hide
            framework noise; pass "" to include them)
        user_iri: full IRI like "/api/3/people/<uuid>" — filter by triggering
            user (server-side)

    Returns:
        List of {task_id, name, status, error_message, modified, uuid,
        pk, source} where source is "live" or "historical".
    """
    try:
        from probes._env import get_client, get_config
    except Exception as e:  # noqa: BLE001
        return [{"error": f"could not import _env: {e!r}"}]
    cfg = get_config()
    if not cfg.is_live():
        return [{"error": "FSR instance not configured"}]
    client = get_client()
    # Fetch wider when filtering client-side so we still hit the limit
    # after the status filter trims rows.
    fetch = max(limit * 4, 50) if not include_finished else limit
    extra = _build_run_filter_qs(
        modified_after=modified_after, modified_before=modified_before,
        tags_include=tags_include, tags_exclude=tags_exclude,
        user_iri=user_iri,
    )
    members = _fetch_runs_both(client, limit=fetch, extra_qs=extra)
    if not include_finished:
        bad = {"failed", "finished_with_error", "terminated"}
        members = [m for m in members if m.get("status") in bad]
    if playbook:
        members = [m for m in members
                   if playbook.lower() in (m.get("name") or "").lower()]
    return [_shape_run(m) for m in members[:limit]]

@mcp.tool()
def list_playbook_runs(playbook: str | None = None,
                       playbook_uuid: str | None = None,
                       limit: int = 20,
                       include_finished: bool = False,
                       modified_after: str | None = None,
                       modified_before: str | None = None,
                       tags_include: str | None = None,
                       tags_exclude: str | None = "system",
                       user_iri: str | None = None) -> dict[str, Any]:
    """List runs of a single playbook, server-filtered by template_iri.

    Faster + more reliable than `list_recent_failed_runs(playbook=...)`
    when you know which playbook you care about — the API uses
    template_iri to do the filter on its side, so we don't waste a fetch
    of irrelevant rows.

    Args:
        playbook: playbook name (resolved live to uuid).
        playbook_uuid: skip the lookup if you already have the uuid.
        limit: max rows (default 20).
        include_finished: include finished runs too (default failures only).

    Returns:
        {playbook_uuid, runs: [{task_id, name, status, error_message,
         modified, pk}]}.
    """
    client = _shared._live_client()
    if client is None:
        return {"error": "FSR instance not configured"}
    if not playbook_uuid:
        if not playbook:
            return {"error": "provide playbook (name) or playbook_uuid"}
        # Resolve name → uuid.
        import urllib.parse
        qs = urllib.parse.urlencode({"name": playbook, "$limit": 5})
        nr = client.session.get(client.base_url + f"/api/3/workflows?{qs}",
                                verify=client.verify_ssl)
        if nr.status_code != 200:
            return {"error": f"name lookup HTTP {nr.status_code}"}
        members = nr.json().get("hydra:member") or []
        if not members:
            return {"error": f"no playbook named {playbook!r}"}
        playbook_uuid = members[0].get("uuid")
    template_iri = f"/api/3/workflows/{playbook_uuid}"
    fetch = limit * 4 if not include_finished else limit
    extra = _build_run_filter_qs(
        modified_after=modified_after, modified_before=modified_before,
        tags_include=tags_include, tags_exclude=tags_exclude,
        user_iri=user_iri,
    )
    members = _fetch_runs_both(
        client, limit=fetch,
        extra_qs=f"&template_iri={template_iri}{extra}",
    )
    if not include_finished:
        bad = {"failed", "finished_with_error", "terminated"}
        members = [m for m in members if m.get("status") in bad]
    runs = [_shape_run(m) for m in members[:limit]]
    return {"playbook_uuid": playbook_uuid, "count": len(runs), "runs": runs}


# ---------------------------------------------------------------------------
# Picklists
# ---------------------------------------------------------------------------


@mcp.tool()
def verification_status(kind: str, key: str) -> dict[str, Any]:
    """Look up the strongest recorded verification for a (kind, key).

    Lets the agent ask 'has anyone successfully run jira:get_issue on
    this FSR before?' without an extra DB roundtrip from chat.

    Common kinds: 'connector' (key=name), 'operation'
    (key='<connector>:<op>'), 'picklist' (key='<name>:<value>'),
    'module', 'module_field', 'jinja_filter', 'api_endpoint',
    'step_type', 'recipe', 'workflow'.

    Returns `{found: bool, status?, method?, ts?, notes_excerpt?,
    history_count}`. Status is one of tested_pass / tested_fail / seen.
    """
    with _db() as conn:
        rows = _rows(
            conn,
            """SELECT status, method, ts, notes
               FROM verifications WHERE kind=? AND key=?
               ORDER BY ts DESC""",
            (kind, key),
        )
    if not rows:
        return {"found": False, "history_count": 0}
    best = max(rows, key=lambda r: (
        _VERIF_RANK.get(r["status"], 0), r["ts"] or "",
    ))
    notes = best["notes"] or ""
    return {
        "found": True,
        "status": best["status"],
        "method": best["method"],
        "ts": best["ts"],
        "notes_excerpt": (notes[:160] + "…") if len(notes) > 160 else notes,
        "history_count": len(rows),
    }


def _build_query_filters(filters: Any) -> dict[str, Any]:
    """Normalize a friendly filter spec to an FSR /api/query body.

    Accepts either a `{field: value, ...}` dict (AND-combined eq filters)
    or a pre-shaped `{logic, filters: [...]}` body, which is passed
    through unchanged.
    """
    if isinstance(filters, dict) and "filters" in filters and "logic" in filters:
        return filters
    if not isinstance(filters, dict):
        raise ValueError("filters must be a dict")
    flist = []
    for field, value in filters.items():
        flist.append({
            "field": field, "operator": "eq", "value": value, "type": "primitive",
        })
    return {"logic": "AND", "filters": flist} if flist else {
        "logic": "AND", "filters": [],
    }


_COUNT_OPS = {
    "eq": lambda a, b: a == b,
    "ne": lambda a, b: a != b,
    "gt": lambda a, b: a > b,
    "gte": lambda a, b: a >= b,
    "lt": lambda a, b: a < b,
    "lte": lambda a, b: a <= b,
}


def _query_module(client: Any, module: str, body: dict[str, Any],
                  limit: int = 5) -> dict[str, Any]:
    """POST /api/query/<module> with a filter body. Returns hydra payload."""
    url = client.base_url + f"/api/query/{module}?$limit={int(limit)}"
    r = client.session.post(url, json=body, verify=client.verify_ssl)
    if r.status_code != 200:
        return {"_http_status": r.status_code, "_error": r.text[:500]}
    return r.json()

@mcp.tool()
def test_find_record(module: str, query: dict[str, Any] | None = None,
                     limit: int = 5) -> dict[str, Any]:
    """Run a Find-Records preview against the configured FSR.

    Posts the supplied filter body to `/api/query/<module>` and returns
    the total count plus a sample of matching records — same shape the
    live `find_record` step would see at runtime, capped at `limit`
    rows so the inspector preview stays light.

    Args:
      module: bare module name (e.g. ``alerts``). Any ``?$limit=…``
        suffix the visual editor stashes is stripped here.
      query: a pre-shaped query body (``{"logic": ..., "filters": [...]}``).
        ``None`` or empty → fetches the first page unfiltered.
      limit: number of sample records to return (clamped to [1, 50]).

    Returns:
      ``{"ok": true, "module": ..., "total": N, "returned": M,
         "records": [...], "url": "..."}``  when the FSR responds 200,
      else ``{"ok": false, "code": ..., "message": ...}``. The
      ``returned`` count is capped at ``limit`` even when ``total`` is
      larger.
    """
    if not module or not isinstance(module, str):
        return {"ok": False, "code": "missing_module",
                "message": "test_find_record requires a non-empty module name"}
    # Strip the `?$limit=30` tail the visual editor leaves on
    # FindRecords' `module:` arg.
    bare = module.split("?", 1)[0].strip()
    if not bare:
        return {"ok": False, "code": "missing_module",
                "message": f"module {module!r} is empty after stripping query string"}
    body: dict[str, Any]
    if not query:
        body = {"logic": "AND", "filters": []}
    elif isinstance(query, dict) and "filters" in query:
        body = query
    else:
        return {"ok": False, "code": "bad_query",
                "message": "query must be a dict with `logic` + `filters` keys"}
    sample_n = max(1, min(int(limit), 50))

    client = _shared._live_client()
    if client is None:
        return {"ok": False, "code": "no_fsr_configured",
                "message": "no FSR instance is configured — run `fsrpb env set` first"}

    url = f"{client.base_url}/api/query/{bare}?$limit={sample_n}"
    try:
        r = client.session.post(url, json=body, verify=client.verify_ssl)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "code": "transport_error",
                "message": f"POST {url} failed: {exc}", "url": url}
    if r.status_code != 200:
        # FSR's error body is usually short-and-helpful; return a slice
        # so the user sees the actual reason without leaking a megabyte
        # of HTML traceback into the inspector.
        return {"ok": False, "code": f"http_{r.status_code}",
                "message": (r.text[:500] or f"HTTP {r.status_code}"),
                "url": url}
    try:
        data = r.json()
    except Exception:  # noqa: BLE001
        return {"ok": False, "code": "bad_json",
                "message": "FSR returned 200 but body was not JSON", "url": url}

    total = data.get("hydra:totalItems")
    if total is None:
        # `$partial=true` strips totalItems; fall back to member length
        # which is at least a lower bound the user can see.
        total = len(data.get("hydra:member", []))
    members = data.get("hydra:member") or []
    return {
        "ok": True,
        "module": bare,
        "total": int(total),
        "returned": len(members[:sample_n]),
        "records": members[:sample_n],
        "url": url,
    }

@mcp.tool()
def search_module_records(module: str, q: str = "",
                          limit: int = 10) -> dict[str, Any]:
    """Search a FortiSOAR module for records matching a query — the core
    triage PIVOT tool (and the relation IRI picker's backend).

    Use this to find every record touching an indicator: search ``alerts``/
    ``incidents``/``assets``/``identities``/``indicators`` for an IP, user, or
    hostname pulled off the record you're triaging, then ``get_record`` the
    hits to correlate the activity.

    Hits ``GET /api/3/<module>?$search=<q>&$limit=<limit>`` on the
    configured FSR and returns a flat list of ``{iri, label, ...}`` pairs.
    Empty ``q`` returns the most-recent records (FSR's natural sort order).

    Args:
      module: bare module name (e.g. ``alerts``); any ``?$limit=…``
        suffix the visual editor stashes is stripped here.
      q: optional case-insensitive substring; FSR's ``$search`` covers
        each entity's "searchable fields" (name + description for most
        modules — see store/QUERY_API.md §3).
      limit: number of results to return (clamped to [1, 25]).

    Returns:
      ``{"ok": true, "module": "...", "results": [{iri, label, ...}]}``
      on success, else ``{"ok": false, "code": ..., "message": ...}``.
      Each result echoes a short subset of useful display fields so the
      picker can render `name` / `id` without a second fetch.
    """
    if not module or not isinstance(module, str):
        return {"ok": False, "code": "missing_module",
                "message": "search_module_records requires a non-empty module name"}
    bare = module.split("?", 1)[0].strip()
    if not bare:
        return {"ok": False, "code": "missing_module",
                "message": f"module {module!r} is empty after stripping query string"}
    sample_n = max(1, min(int(limit), 25))

    client = _shared._live_client()
    if client is None:
        return {"ok": False, "code": "no_fsr_configured",
                "message": "no FSR instance is configured — run `fsrpb env set` first"}

    # Use $search for substring match across the entity's indexed
    # fields. Falls back to a plain $limit fetch when q is empty so
    # the dropdown has *something* to render before the user types.
    qs = f"$limit={sample_n}"
    if q:
        from urllib.parse import quote
        qs += f"&$search={quote(q)}"
    url = f"{client.base_url}/api/3/{bare}?{qs}"
    try:
        r = client.session.get(url, verify=client.verify_ssl)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "code": "transport_error",
                "message": f"GET {url} failed: {exc}", "url": url}
    if r.status_code != 200:
        return {"ok": False, "code": f"http_{r.status_code}",
                "message": (r.text[:500] or f"HTTP {r.status_code}"),
                "url": url}
    try:
        data = r.json()
    except Exception:  # noqa: BLE001
        return {"ok": False, "code": "bad_json",
                "message": "FSR returned 200 but body was not JSON", "url": url}

    members = data.get("hydra:member") or []
    results = []
    for m in members[:sample_n]:
        if not isinstance(m, dict):
            continue
        iri = m.get("@id")
        if not iri:
            continue
        # Pick the first plausible label field so the dropdown renders
        # something readable. Falls back to the IRI tail (UUID) when no
        # label-like key exists.
        label = (m.get("name") or m.get("title") or m.get("subject")
                 or m.get("displayName") or m.get("hostname")
                 or m.get("description"))
        if not label:
            label = iri.rsplit("/", 1)[-1]
        results.append({
            "iri": iri,
            "label": str(label)[:120],
            "id": m.get("id"),
        })
    return {
        "ok": True,
        "module": bare,
        "total": int(data.get("hydra:totalItems", len(members))),
        "results": results,
        "url": url,
    }


@mcp.tool()
def get_record(iri: str = "", module: str = "", uuid: str = "",
               relationships: bool = True) -> dict[str, Any]:
    """Fetch a single FSR record by IRI (or module+uuid), with relationships.

    The read-only companion the triage prompt assumes when it tells the
    agent to pull an event/alert/asset row by its ``iri``/``module``/``uuid``
    to build an attack timeline or assess blast radius. Wraps
    ``GET /api/3/<module>/<uuid>?$relationships=true`` so related records
    (correlated alerts, linked assets, indicators) come back inline rather
    than as bare IRIs the agent would have to chase one by one.

    Args:
      iri: full record IRI (e.g. ``/api/3/alerts/<uuid>``). Takes
        precedence over module+uuid when both are supplied.
      module: bare module name (e.g. ``alerts``) — required if no ``iri``.
      uuid: record UUID — required if no ``iri``.
      relationships: when true (default), append ``?$relationships=true``
        so related entities are hydrated inline.

    Returns:
      ``{"ok": true, "iri": ..., "record": {...}, "url": ...}`` on a 200,
      else ``{"ok": false, "code": ..., "message": ...}``.
    """
    path = ""
    if iri and isinstance(iri, str):
        # Normalise: accept a full IRI, with or without a leading slash,
        # and strip any query string the caller pasted along.
        path = "/" + iri.strip().lstrip("/").split("?", 1)[0]
    elif module and uuid:
        bare = module.split("?", 1)[0].strip()
        if not bare:
            return {"ok": False, "code": "missing_module",
                    "message": f"module {module!r} is empty after stripping query string"}
        path = f"/api/3/{bare}/{uuid.strip()}"
    else:
        return {"ok": False, "code": "missing_target",
                "message": "get_record requires either `iri` or both `module` and `uuid`"}

    client = _shared._live_client()
    if client is None:
        return {"ok": False, "code": "no_fsr_configured",
                "message": "no FSR instance is configured — run `fsrpb env set` first"}

    url = f"{client.base_url}{path}"
    if relationships:
        url += "?$relationships=true"
    try:
        r = client.session.get(url, verify=client.verify_ssl)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "code": "transport_error",
                "message": f"GET {url} failed: {exc}", "url": url}
    if r.status_code == 404:
        return {"ok": False, "code": "not_found",
                "message": f"no record at {path}", "url": url}
    if r.status_code != 200:
        return {"ok": False, "code": f"http_{r.status_code}",
                "message": (r.text[:500] or f"HTTP {r.status_code}"),
                "url": url}
    try:
        data = r.json()
    except Exception:  # noqa: BLE001
        return {"ok": False, "code": "bad_json",
                "message": "FSR returned 200 but body was not JSON", "url": url}

    return {
        "ok": True,
        "iri": data.get("@id", path),
        "record": data,
        "url": url,
    }


def _assert_one(client: Any, a: dict[str, Any]) -> dict[str, Any]:
    kind = a.get("kind")
    module = a.get("module")
    if not kind:
        return {"ok": False, "code": "missing_kind", "message": "assertion requires `kind`"}
    if not module and kind in ("record_exists", "record_count", "field_equals"):
        return {"ok": False, "code": "missing_module",
                "message": f"{kind} requires `module`", "kind": kind}
    try:
        body = _build_query_filters(a.get("filters", {}))
    except ValueError as e:
        return {"ok": False, "code": "bad_filters", "message": str(e), "kind": kind}

    if kind == "record_exists":
        data = _query_module(client, module, body, limit=1)
        if "_error" in data:
            return {"ok": False, "code": "query_failed", "kind": kind,
                    "message": f"HTTP {data.get('_http_status')}: {data['_error']}"}
        total = int(data.get("hydra:totalItems", len(data.get("hydra:member", []))))
        ok = total > 0
        return {"ok": ok, "kind": kind, "module": module,
                "code": "ok" if ok else "no_match",
                "observed_count": total,
                "message": (f"found {total} matching record(s)" if ok else
                            f"no records matched filters in module '{module}'")}

    if kind == "record_count":
        op = a.get("op", "eq")
        expected = a.get("value")
        if op not in _COUNT_OPS:
            return {"ok": False, "code": "bad_op", "kind": kind,
                    "message": f"op must be one of {sorted(_COUNT_OPS)}"}
        if not isinstance(expected, (int, float)):
            return {"ok": False, "code": "bad_value", "kind": kind,
                    "message": "record_count `value` must be a number"}
        data = _query_module(client, module, body, limit=1)
        if "_error" in data:
            return {"ok": False, "code": "query_failed", "kind": kind,
                    "message": f"HTTP {data.get('_http_status')}: {data['_error']}"}
        total = int(data.get("hydra:totalItems", len(data.get("hydra:member", []))))
        ok = _COUNT_OPS[op](total, expected)
        return {"ok": ok, "kind": kind, "module": module,
                "code": "ok" if ok else "count_mismatch",
                "observed_count": total, "op": op, "expected": expected,
                "message": (f"count {total} {op} {expected}" if ok else
                            f"count {total} not {op} {expected}")}

    if kind == "field_equals":
        field = a.get("field")
        expected = a.get("value")
        if not field:
            return {"ok": False, "code": "missing_field", "kind": kind,
                    "message": "field_equals requires `field`"}
        data = _query_module(client, module, body, limit=2)
        if "_error" in data:
            return {"ok": False, "code": "query_failed", "kind": kind,
                    "message": f"HTTP {data.get('_http_status')}: {data['_error']}"}
        members = data.get("hydra:member", [])
        total = int(data.get("hydra:totalItems", len(members)))
        if total == 0:
            return {"ok": False, "code": "no_match", "kind": kind, "module": module,
                    "field": field, "expected": expected,
                    "message": f"no records matched filters in module '{module}'"}
        if total > 1:
            return {"ok": False, "code": "ambiguous", "kind": kind, "module": module,
                    "field": field, "expected": expected, "observed_count": total,
                    "message": (f"filters matched {total} records; field_equals "
                                "needs exactly one. Tighten filters.")}
        rec = members[0] if members else {}
        # Walk dotted field path against the record (supports nested keys).
        actual: Any = rec
        for part in str(field).split("."):
            if isinstance(actual, dict) and part in actual:
                actual = actual[part]
            else:
                actual = None
                break
        ok = actual == expected
        return {"ok": ok, "kind": kind, "module": module, "field": field,
                "expected": expected, "observed": actual,
                "code": "ok" if ok else "field_mismatch",
                "message": (f"{module}.{field} == {expected!r}" if ok else
                            f"{module}.{field}: expected {expected!r}, "
                            f"got {actual!r}")}

    return {"ok": False, "code": "unknown_kind", "kind": kind,
            "message": (f"unknown assertion kind '{kind}'; expected one of "
                        "record_exists, record_count, field_equals")}