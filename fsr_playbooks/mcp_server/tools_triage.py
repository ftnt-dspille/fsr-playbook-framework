"""MCP tools: Tools Triage"""
from __future__ import annotations

import json
import re
from typing import Any, Literal

from fsr_playbooks.mcp_server import _shared
from fsr_playbooks.mcp_server._shared import _VERIF_RANK, _db, _rows, mcp
from fsr_playbooks.mcp_server.tools_connector_discovery import _build_run_filter_qs
from fsr_playbooks.mcp_server.tools_execution import _fetch_runs_both, _shape_run

# ---------------------------------------------------------------------------
# Record summarization -- keep get_record cheap for the agent loop
# ---------------------------------------------------------------------------
# A hydrated FSR alert/incident with $relationships=true is ~100KB of JSON:
# ~80 null/empty fields, picklist objects wrapped in hydra metadata, and big
# hydrated reference lists (MITRE mitigations/software/groups, indicators).
# The triage agent only needs the populated scalar fields (indicators are
# already top-level: sourceIp/destinationIp/hostName/userName/...) plus a
# thin index of related records to pivot on. Echoing the full blob back into
# history every turn is what blows the per-minute token budget. This prunes
# it to a triage projection; pass `full=True` to get_record for the raw body.

# Hydra/audit/owner noise that carries no triage signal.
_REC_NOISE_KEYS = frozenset({
    "@context", "@type", "createUser", "modifyUser", "tenant", "owners",
    "ownersList", "__self", "__replace", "peKpiData",
})
# Hydrated reference lists where the useful signal is already a top-level
# scalar (mitreattackid / mitreTechnique). Collapse to names only.
_REC_REFERENCE_LISTS = frozenset({
    "mitremitigations", "mitresoftware", "mitregroups", "mitretactics",
    "mitre_techniques", "mitre_sub_techniques",
})
_REC_MAX_REL = 5          # cap hydrated relationship members per list
_REC_MAX_STR = 600        # truncate long strings (e.g. HTML description)

# Modules whose verdict/identity signal must ride inline on a bare search row
# (no `fields=` requested), because reporting the hit without it is useless:
# an indicator lookup exists to surface the reputation. Mirrors the way an
# alert carries sourceIp top-level. Only applied when the model requested no
# fields; `available_fields` is still named so it can ask for more.
_VERDICT_MODULE_FIELDS = {
    "indicators": ("reputation", "value", "type", "source"),
}
_TAG_RE = re.compile(r"<[^>]+>")


def _is_empty(v: Any) -> bool:
    return v is None or v == "" or v == [] or v == {}


def _ref_label(d: dict[str, Any]) -> str:
    return str(d.get("name") or d.get("title") or d.get("value")
               or d.get("displayName") or d.get("hostname")
               or d.get("itemValue") or d.get("@id", ""))[:120]


def _shrink_value(key: str, v: Any) -> Any:
    """Prune a single record field to its triage-relevant core."""
    # Picklist / state object: {"@id":..., "itemValue": "Open", ...} -> scalar.
    if isinstance(v, dict) and "itemValue" in v:
        return v.get("itemValue")
    # Other hydrated single reference: keep iri + label.
    if isinstance(v, dict) and "@id" in v:
        lbl = _ref_label(v)
        return {"iri": v["@id"], "label": lbl} if lbl else {"iri": v["@id"]}
    if isinstance(v, dict):
        inner = {k: _shrink_value(k, x) for k, x in v.items()
                 if k not in _REC_NOISE_KEYS and not _is_empty(x)}
        return inner
    if isinstance(v, list):
        members = [m for m in v if not _is_empty(m)]
        if not members:
            return None
        # Reference-data lists: names only.
        if key in _REC_REFERENCE_LISTS:
            names = [_ref_label(m) if isinstance(m, dict) else str(m)
                     for m in members]
            return names[:_REC_MAX_REL] + (
                [f"...+{len(names) - _REC_MAX_REL} more"]
                if len(names) > _REC_MAX_REL else [])
        # Hydrated relationship members: thin index of {iri, label, type, ...}.
        out = []
        for m in members[:_REC_MAX_REL]:
            if isinstance(m, dict) and "@id" in m:
                ref = {"iri": m["@id"]}
                lbl = _ref_label(m)
                if lbl:
                    ref["label"] = lbl
                for k in ("type", "value", "indicatorType", "reputation",
                          "severity"):
                    if not _is_empty(m.get(k)):
                        ref[k] = _shrink_value(k, m[k])
                out.append(ref)
            else:
                out.append(_shrink_value(key, m))
        if len(members) > _REC_MAX_REL:
            out.append(f"...+{len(members) - _REC_MAX_REL} more")
        return out
    if isinstance(v, str):
        s = _TAG_RE.sub(" ", v).strip() if "<" in v and ">" in v else v
        s = re.sub(r"\s+", " ", s) if s != v else s
        return s[:_REC_MAX_STR] + "…" if len(s) > _REC_MAX_STR else s
    return v


# Known-boilerplate top-level keys that carry no triage/pivot signal but bloat
# a `full` body: multi-paragraph impact prose, SLA/escalation plumbing.
_REC_FULL_DROP_KEYS = frozenset({
    "impactAssessments", "escalationRules", "escalation_rules",
    "responseProcedure", "recommendations",
})
# Hard ceiling on a `full=True` body so a single get_record can NEVER dump the
# raw ~100KB hydrated incident into the per-turn context (it then rides in
# messages[] and is re-sent every subsequent turn). The pruned default is ~5%
# of this; the cap is the structural backstop for the rare full path.
_REC_FULL_MAX_BYTES = 8192


def _clean_full_record(rec: dict[str, Any]) -> dict[str, Any]:
    """A `full=True` body with the dead weight stripped: null/empty fields,
    hydra/audit noise, SLA plumbing, and known-boilerplate prose. Keeps every
    populated field otherwise (this is the debug path -- it must stay faithful),
    just without the ~80 null fields and the impact-assessment wall that make
    the raw body 100KB."""
    if not isinstance(rec, dict):
        return rec
    out: dict[str, Any] = {}
    for k, v in rec.items():
        if k in ("@id", "uuid", "id", "name"):  # always keep identity
            out[k] = v
            continue
        if k in _REC_NOISE_KEYS or k in _REC_FULL_DROP_KEYS:
            continue
        if "sla" in k.lower():  # *SLA* timers/dates -- plumbing, not signal
            continue
        if _is_empty(v):
            continue
        out[k] = v
    return out


def _cap_json(obj: Any, max_bytes: int = _REC_FULL_MAX_BYTES):
    """Bound a value's serialized size. Returns (value, truncated). When the
    JSON exceeds `max_bytes`, replaces it with a head/tail-truncated marker so
    a single tool result can't blow the token budget -- the agent still sees the
    shape + identity, and is told to fetch specific fields via the pruned
    projection instead."""
    s = json.dumps(obj, default=str)
    if len(s) <= max_bytes:
        return obj, False
    half = max_bytes // 2
    return {
        "_truncated": True,
        "_original_bytes": len(s),
        "_head": s[:half],
        "_tail": s[-half:],
        "_note": ("full body exceeded the size cap and was head/tail "
                  "truncated; re-fetch without full= for the pruned "
                  "projection (every pivotable field, ~5% the size)"),
    }, True


def _summarize_record(rec: dict[str, Any]) -> dict[str, Any]:
    """Prune a hydrated FSR record to a compact triage projection.

    Drops null/empty fields, hydra/audit noise, and collapses picklist
    objects + hydrated reference lists. Always preserves the record's
    identity (@id/uuid/name) and every populated scalar field -- which is
    where the indicators the agent enriches (sourceIp/destinationIp/host/
    user/hashes) live. Module-agnostic; safe for alerts/incidents/assets.
    """
    if not isinstance(rec, dict):
        return rec
    out: dict[str, Any] = {}
    for k, v in rec.items():
        if k in ("@id", "uuid", "id", "name"):  # always keep identity
            out[k] = v
            continue
        if k in _REC_NOISE_KEYS or _is_empty(v):
            continue
        sv = _shrink_value(k, v)
        if not _is_empty(sv):
            out[k] = sv
    return out

# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# Containment-action discovery -- one call, no connector-by-connector hunting
# ---------------------------------------------------------------------------
# Containment verbs that mark an op as a response action (not a read/reversal).
# Op-name prefixes that are reads or the UNDO of a containment action -- never
# what "stage containment" wants.
# Indicator type -> op-name/title keywords. The agent passes the type of the
# thing it wants to contain; we match it to the right family of ops.

# --- Read/enrichment discovery (mirror of the containment side) -------------
# An enrichment op takes an indicator (IP / domain / URL / hash / email / host)
# and returns intel about it -- reputation, context, IOC lookup, geo/whois. It's
# read-only: the agent runs it directly via run_op and summarizes, never cards
# it. Most read ops carry the catch-all `investigation` category, so category
# alone can't select them; we match indicator/intel tokens in the op name+title
# and use a tier<=2 read guard, the inverse of the containment tier>=3 guard.
# Tokens that NAME a specific indicator type. Used to (a) confirm a candidate
# op is about the requested indicator and (b) reject ops that name only a
# *different* indicator (e.g. get_domain_reputation when enriching an IP).
# Note: "address" is deliberately NOT an ip token -- it matches firewall
# address-objects (`get_addresses`), MAC/email addresses, etc.
# Write-ish / plumbing ops that share the `investigation` category but aren't an
# indicator lookup -- re-scans, submissions, detonations, raw API passthroughs.
# Connector preference for enrichment ranking. High-signal TI connectors first
# so they survive the `limit` cut; AlienVault OTX is de-prioritized (slow,
# noisy, frequently times out -- see memory `agent_no_alienvault_otx`). Lower
# rank value = preferred. Substring match against the connector name; anything
# unlisted lands in the middle band so a chatty deprioritized connector can't
# bury an unknown-but-neutral one.
# Cap per connector so one chatty connector can't crowd the slate.





















@mcp.tool()
def list_tags(prefix: str | None = None, limit: int = 50) -> dict[str, Any]:
    """List FortiSOAR tag names; use to discover tags before filtering runs by them.

    Backed by `GET /api/3/tags?$export=true`. The instance can have 10k+ tags
    (most are auto-generated from threat-intel data), so always pass a prefix
    when looking for workflow-noise tags like "system" or "testing".

    Args:
        prefix: case-insensitive tag prefix (uses `uuid$like=<prefix>%` --
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
        r = _get_with_reauth(client, client.base_url + "/api/3/tags?" + qs)
    except Exception as e:  # noqa: BLE001
        return {"error": f"request failed: {e!r}"}
    if r.status_code != 200:
        return {"error": f"HTTP {r.status_code}: {r.text[:200]}"}
    body = r.json() or {}
    tags = body.get("hydra:member") or []
    return {"total": body.get("hydra:totalItems"), "tags": tags[:limit]}



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
    the playbook -- fetches the most recently-modified failed/errored
    runs across the instance from BOTH the live and historical workflow
    tables (FSR purges live → historical every ~30-60 min).

    Args:
        limit: max rows to return (default 20)
        playbook: optional name filter (client-side substring match)
        include_finished: include finished runs too (default False --
            failed/finished_with_error/terminated only)
        modified_after: ISO timestamp, e.g. "2026-05-01 05:00:00" (server-side)
        modified_before: ISO timestamp (server-side)
        tags_include: CSV of tag names to require (server-side)
        tags_exclude: CSV of tag names to exclude (default "system" to hide
            framework noise; pass "" to include them)
        user_iri: full IRI like "/api/3/people/<uuid>" -- filter by triggering
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


# The model writes operators in many dialects; map them all to FSR's names.
_OP_ALIASES = {
    "=": "eq", "==": "eq", "eq": "eq", "is": "eq", "equals": "eq",
    "!=": "neq", "ne": "neq", "neq": "neq", "not": "neq", "isnot": "neq",
    ">": "gt", "gt": "gt", ">=": "gte", "gte": "gte",
    "<": "lt", "lt": "lt", "<=": "lte", "lte": "lte",
    "in": "in", "contains": "contains", "like": "like",
    "isnull": "isnull", "notnull": "notnull",
}


def _normalize_condition(cond: dict[str, Any]) -> dict[str, Any] | None:
    """One list-form condition → an FSR primitive filter. Accepts field/key and
    op/operator aliases. A null value with an eq/neq op becomes the FSR
    ``isnull``/``notnull`` operator (what "pending steps have no run group"
    needs -- a plain ``field=null`` never matches)."""
    field = cond.get("field") or cond.get("key") or cond.get("name")
    if not field:
        return None
    raw_op = str(cond.get("op") or cond.get("operator") or "eq").strip().lower()
    op = _OP_ALIASES.get(raw_op, raw_op)
    value = cond.get("value", cond.get("val"))
    if value is None:
        # "field is empty" -- FSR's `isnull` operator takes a bool value:
        # true → IS NULL, false → IS NOT NULL (canonical query doc). A neq-null
        # condition ("has a run group") is `isnull=false`; everything else is
        # `isnull=true`. (A bare `field=null` never matches -- the class of query
        # that returned 0 for "pending steps with no run group".)
        return {"field": field, "operator": "isnull",
                "value": op != "neq", "type": "primitive"}
    return {"field": field, "operator": op, "value": value, "type": "primitive"}


def _list_item_conditions(item: Any) -> list[dict[str, Any]]:
    """One item of the list form as conditions. Besides a condition dict, the
    model writes an equality clause as a string (``"ztpf_run_groups = null"``,
    ``"datakey:interface_stats"``) or a one-field map (``{"severity": "High"}``).
    Both were dropped here without a word, so the search ran UNFILTERED and its
    rows read as matches; a pydantic copy of the signature parsed them, but only
    to validate, and threw the result away. Anything else is refused: a filter
    invented from nonsense is worse than none."""
    if isinstance(item, dict):
        if any(item.get(k) for k in ("field", "key", "name")):
            return [item]
        return [{"field": k, "value": v} for k, v in item.items()]
    if isinstance(item, str):
        for sep in ("==", "=", ":"):
            if sep in item:
                k, _, val = item.partition(sep)
                k, val = k.strip(), val.strip().strip('"').strip("'")
                if k:
                    return [{"field": k,
                             "value": None if val.lower() in ("null", "none") else val}]
    raise ValueError(
        f"cannot read the filter {item!r}: use a condition "
        '{"field": ..., "op": ..., "value": ...}, a {"field": value} map, or an '
        'equality string like "status = Open"')


def _build_query_filters(filters: Any) -> dict[str, Any]:
    """Normalize a friendly filter spec to an FSR /api/query body.

    Accepts every shape the agent emits:
      * ``{field: value, ...}`` -- a map of AND-combined eq filters;
      * ``[{"field"|"key": .., "op"|"operator": .., "value": ..}]`` -- the
        list-of-conditions form (the shape it instinctively reaches for);
      * a pre-shaped ``{logic, filters: [...]}`` body -- passed through.
    A ``None``/absent value on a condition is treated as an ``isnull`` test.
    """
    if isinstance(filters, dict) and "filters" in filters and "logic" in filters:
        return filters
    flist: list[dict[str, Any]] = []
    if isinstance(filters, list):
        for cond in filters:
            for one in _list_item_conditions(cond):
                norm = _normalize_condition(one)
                if norm is not None:
                    flist.append(norm)
    elif isinstance(filters, dict):
        for field, value in filters.items():
            # `{field: {"$lt": x, "$gte": y}}` -- the Mongo-style range the
            # model writes for "older than" / "between". Read as one eq on a
            # dict value it matched nothing, and the model concluded ranges
            # were unsupported.
            if isinstance(value, dict) and value and all(
                    str(k).lstrip("$").lower() in _OP_ALIASES for k in value):
                for op, v in value.items():
                    flist.append(_normalize_condition(
                        {"field": field, "op": str(op).lstrip("$"), "value": v}))
                continue
            flist.append(_normalize_condition({"field": field, "value": value}))
    else:
        raise ValueError("filters must be a dict or a list of conditions")
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
    r = _post_with_reauth(client, url, json=body)
    if r.status_code != 200:
        return {"_http_status": r.status_code, "_error": r.text[:500]}
    return r.json()

@mcp.tool()
def test_find_record(module: str, query: dict[str, Any] | None = None,
                     limit: int = 5) -> dict[str, Any]:
    """Run a Find-Records preview against the configured FSR.

    Posts the supplied filter body to `/api/query/<module>` and returns
    the total count plus a sample of matching records -- same shape the
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
                "message": "no FSR instance is configured -- run `fsrpb env set` first"}

    url = f"{client.base_url}/api/query/{bare}?$limit={sample_n}"
    try:
        r = _post_with_reauth(client, url, json=body)
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

# ---------------------------------------------------------------------------
# Module-name preflight + field-scoped query parsing (shared by the lookup
# tools). These exist because live sessions showed two systemic lookup
# failures: (1) the agent guesses a camelCase collection name (`ztpfRunGroups`)
# that isn't a route → a 404 the model can't recover from, and (2) the agent
# reaches for a field filter (`datakey:interface_stats`) but the tool only ran
# a full-text `$search`, so the literal `field:value` string matched nothing
# even though the record exists. `_module_preflight` catches (1) with a nearest
# suggestion; `_split_field_query` catches (2) by routing `field:value` to a
# real equality filter.
# ---------------------------------------------------------------------------
_FIELD_QUERY_RE = re.compile(r"^\s*([A-Za-z][\w.]*)\s*[:=]\s*(\S.*?)\s*$")


def _nearest_modules(module: str) -> list[str]:
    """Up to 3 known module names close to ``module`` -- used to enrich a genuine
    404, never to block a request.

    Preflight-as-a-gate is unsafe: the reference catalog is not authoritative
    for a deployment's *custom* modules (a live box carried ``ztpf_metadata_sources``
    that the warmed catalog didn't list), so blocking on "not in catalog" would
    reject valid lookups. Instead we let the request run and, only when FSR
    itself returns 404 (route/record truly absent), offer the nearest catalog
    name as a hint -- turning the ``ztpfRunGroups`` class of guess into an
    actionable ``did you mean ztpf_run_groups?`` without ever false-blocking."""
    try:
        from fsr_playbooks.mcp_server.tools_verify import _known_modules
        known = _known_modules()
    except Exception:  # noqa: BLE001
        return []
    if not known or module in known:
        return []
    import difflib
    return difflib.get_close_matches(module, known, n=3, cutoff=0.6)


def _split_field_query(module: str, q: str) -> tuple[dict[str, str], str]:
    """Split a query into ``(field_filters, free_text)``.

    A whole-string ``field:value`` (or ``field=value``) -- the syntax the model
    naturally emits and the exact shape that silently returned zero rows in live
    sessions -- becomes an equality filter ``{field: value}``. Anything else stays
    free text for ``$search``. When the module's field catalog is warm and the
    parsed field isn't a real field, we leave it as free text so an unknown-field
    filter can't 400 (best-effort; the caller also has a $search fallback)."""
    if not q:
        return {}, ""
    m = _FIELD_QUERY_RE.match(q)
    if not m:
        return {}, q
    field, value = m.group(1), m.group(2)
    try:
        from fsr_playbooks.mcp_server.tools_verify import _module_field_names
        fields = _module_field_names(module)
    except Exception:  # noqa: BLE001
        fields = []
    if fields and field not in fields:
        return {}, q  # unknown field on a warm catalog ⇒ keep as full-text
    return {field: value}, ""


def _normalize_sort(sort: Any) -> list[dict[str, str]]:
    """Normalize every sort spelling the model reaches for to the query API's
    ``[{"field": .., "direction": "ASC"|"DESC"}]`` body form.

    Accepts ``"modifyDate"``, ``"-modifyDate"``, ``"modifyDate desc"``,
    ``{"field": .., "direction": ..}``, or a list of any of those. Default
    direction is DESC: sorting is nearly always "latest first" here.
    Raises ``ValueError`` on a shape that carries no field name, so a typo'd
    sort is a loud refusal rather than a silently unordered result.
    """
    if sort is None:
        return []
    items = sort if isinstance(sort, list) else [sort]
    out: list[dict[str, str]] = []
    for it in items:
        field, direction = None, "DESC"
        if isinstance(it, str):
            s = it.strip()
            if not s:
                continue
            if s.startswith("-"):
                field, direction = s[1:].strip(), "DESC"
            elif s.startswith("+"):
                field, direction = s[1:].strip(), "ASC"
            else:
                parts = s.replace(",", " ").split()
                field = parts[0]
                if len(parts) > 1 and parts[1].lower() in ("asc", "desc"):
                    direction = parts[1].upper()
        elif isinstance(it, dict):
            field = it.get("field") or it.get("key") or it.get("name")
            d = str(it.get("direction") or it.get("order") or "DESC").upper()
            direction = "ASC" if d.startswith("ASC") else "DESC"
        if not field:
            raise ValueError(
                f"sort entry {it!r} has no field name -- use sort='modifyDate', "
                "'-modifyDate', or [{'field': 'modifyDate', 'direction': 'DESC'}]")
        out.append({"field": str(field).strip(), "direction": direction})
    return out


def _sort_key(value: Any) -> tuple:
    """Order-preserving key that survives the mixed types a crudhub row carries.

    Numbers order numerically, numeric STRINGS order numerically too ("9" before
    "10", not after), and other strings order case-insensitively. Returns a
    ``(rank, value)`` tuple so Python never compares an int to a str and raises
    mid-sort. Missing values are not handled here -- see ``_sort_rows``, which
    keeps them last in BOTH directions (a null is unknown, not "smallest", and a
    DESC flip must not float empty rows to the top of a "latest first" list).
    """
    if value is None:
        return (2, "")
    if isinstance(value, bool):
        return (0, float(value))
    if isinstance(value, (int, float)):
        return (0, float(value))
    s = str(value)
    # A numeric string ("12") must order as a number, not lexically ("12" < "9").
    try:
        return (0, float(s))
    except ValueError:
        return (1, s.casefold())


def _nearest_field_names(wanted: str, available: list[str]) -> list[str]:
    """Field names on the module closest to ``wanted`` -- the stepNum→stepNumber
    fix. Prefix/substring first (that is the real typo shape), then difflib."""
    import difflib
    w = wanted.casefold()
    near = [f for f in available
            if f.casefold().startswith(w) or w in f.casefold()]
    if not near:
        near = difflib.get_close_matches(wanted, available, n=3, cutoff=0.6)
    return near[:3]


def _with_sort_fields(fields: list[str] | None,
                      sort_spec: list[dict[str, str]]) -> list[str]:
    """``fields`` plus every field being sorted on, order preserved, no repeats.
    One definition shared by the server-sorted and client-sorted paths so they
    cannot disagree about whether the ordering key is visible."""
    out = [f for f in (fields or []) if isinstance(f, str) and f.strip()]
    for spec in sort_spec:
        if spec["field"] not in out:
            out.append(spec["field"])
    return out


def _sort_rows(members: list[dict], sort_spec: list[dict[str, str]]) -> list[dict]:
    """``members`` ordered by ``sort_spec``, rows missing a key always last.

    Applies the keys least- to most-significant (the stable multi-key idiom, so
    the FIRST listed field ends up primary), and after each one re-partitions
    rows whose field is absent to the back. Doing that as a second stable sort --
    rather than encoding it in the key -- is what makes "missing last" hold under
    ``reverse=True`` too, which a rank baked into the key cannot do.
    """
    ordered = list(members)
    for spec in reversed(sort_spec):
        f = spec["field"]
        ordered.sort(key=lambda m, f=f: _sort_key(m.get(f)),
                     reverse=(spec["direction"] == "DESC"))
        ordered.sort(key=lambda m, f=f: m.get(f) is None)
    return ordered


def _sort_fallback(client: Any, bare: str, body: dict,
                   sort_spec: list[dict[str, str]], sample_n: int,
                   fields: list[str] | None, qurl: str) -> dict[str, Any]:
    """Deliver ``sort_spec`` after the query API refused it: re-fetch unsorted
    and order the page here.

    The honest caveat is carried in the result: this orders the rows we
    RETURNED, not the whole match set, so a truncated result sorted this way is
    "the first N by the server's order, then sorted" -- the shaped output says so
    rather than letting the model imply a global ordering.

    When the requested field is on none of the returned records we stop and name
    the fields that ARE there (plus the nearest matches), because that is a real
    typo and inventing an order for it would be worse than the refusal.
    """
    unsorted_body = {k: v for k, v in (body or {}).items() if k != "sort"}
    url = f"{client.base_url}/api/query/{bare}?$limit={sample_n}"
    try:
        r = _post_with_reauth(client, url, json=unsorted_body)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "code": "transport_error",
                "message": f"POST {url} failed: {exc}", "url": url}
    if r.status_code != 200:
        return {"ok": False, "code": f"http_{r.status_code}",
                "message": (r.text[:500] or f"HTTP {r.status_code}"), "url": url}
    try:
        data = r.json()
    except Exception:  # noqa: BLE001
        return {"ok": False, "code": "bad_json",
                "message": "FSR returned 200 but body was not JSON", "url": url}
    if not isinstance(data, dict):
        return {"ok": False, "code": "bad_json",
                "message": "FSR returned 200 but body was not an object", "url": url}

    members = [m for m in (data.get("hydra:member") or []) if isinstance(m, dict)]
    available = sorted({k for m in members for k in m.keys()
                        if isinstance(k, str) and not k.startswith("@")})
    unknown = [s["field"] for s in sort_spec
               if not any(s["field"] in m for m in members)]
    if unknown and members:
        near = {u: _nearest_field_names(u, available) for u in unknown}
        suggest = "; ".join(f"{u!r} → {', '.join(n) or 'no close match'}"
                            for u, n in near.items())
        return {
            "ok": False, "code": "unknown_sort_field", "url": qurl,
            "message": (
                f"{bare!r} records carry no field named "
                f"{', '.join(repr(u) for u in unknown)}, so they cannot be "
                f"ordered by it. Did you mean: {suggest}. Sorting IS supported "
                "on this module -- retry with a field name from `sortable`."),
            "sortable": available,
        }

    ordered = _sort_rows(members, sort_spec)

    want = _with_sort_fields(fields, sort_spec)
    out = _shape_search_members({**data, "hydra:member": ordered},
                                sample_n, bare, qurl, matched_by="filter",
                                fields=want)
    out["sorted_client_side"] = [f"{s['field']} {s['direction']}"
                                 for s in sort_spec]
    note = (f"{bare!r} does not support server-side sorting, so the "
            f"{out.get('showing', 0)} returned rows were ordered here by "
            f"{', '.join(out['sorted_client_side'])}.")
    if out.get("truncated"):
        # The one claim this fallback must not let the model make.
        note += (" These are the first rows in the server's own order, then "
                 "sorted -- NOT the global top rows for this ordering. Say so.")
    out["message"] = f"{note} {out.get('message', '')}".strip()
    return out


def _flatten_field(value: Any) -> Any:
    """Reduce one raw crudhub field value to something a model can read.

    Picklists arrive as ``{"itemValue": "Complete", ...}`` and relationships as
    a record dict or a list of them -- dumping those verbatim buries the answer
    in IRIs and @context noise. Collapse each to its display value, keeping the
    ``iri`` so the agent can still pivot with ``get_record``."""
    if isinstance(value, dict):
        if "itemValue" in value:  # picklist
            return value.get("itemValue")
        label = (value.get("name") or value.get("title") or value.get("subject")
                 or value.get("displayName") or value.get("hostname"))
        iri = value.get("@id")
        if label or iri:
            return {"label": str(label)[:120] if label else None, "iri": iri}
        return value
    if isinstance(value, list):
        return [_flatten_field(v) for v in value[:10]]
    return value


def _unknown_field_in(text: str) -> str | None:
    """The field name out of FSR's ``[Field:<name> does not exist in module
    definition]`` 400, or None if that isn't what went wrong."""
    m = re.search(r"Field:\s*([A-Za-z0-9_.]+)\s+does not exist", text or "")
    return m.group(1) if m else None


def _filterable_fields(client: Any, bare: str) -> list[str]:
    """The field names records in ``bare`` actually carry, sampled from one row.
    Cheap (one row, no schema call) and always current for custom modules."""
    try:
        r = _get_with_reauth(client, f"{client.base_url}/api/3/{bare}?$limit=1")
        if r.status_code != 200:
            return []
        members = (r.json() or {}).get("hydra:member") or []
        return sorted({k for m in members if isinstance(m, dict)
                       for k in m.keys()
                       if isinstance(k, str) and not k.startswith("@")})[:60]
    except Exception:  # noqa: BLE001 -- a suggestion list is best-effort
        return []


def _unknown_filter_field(client: Any, bare: str, bad_field: str,
                          url: str) -> dict[str, Any]:
    """Refuse an unknown FILTER field the way an unknown sort field and an
    unknown module name are already refused -- by name, with the real options.

    Filters were the one lookup path that leaked FSR's raw 400 ("Field:label
    does not exist in module definition") straight to the model. Worse, the
    single most likely bad filter is INDUCED by this tool: every result row is
    keyed ``label``, which is a display name synthesized here from
    name/title/subject, not a stored field -- so filtering on what the output
    calls things is a guaranteed 400. Say that explicitly rather than making
    the model infer it from a stack of HTTP noise."""
    available = _filterable_fields(client, bare)
    msg = (f"{bad_field!r} is not a field on {bare!r} records, so it cannot be "
           f"filtered on.")
    if bad_field == "label":
        msg += (" `label` is a DISPLAY NAME this tool synthesizes for each "
                "result row (from name/title/subject/hostname) -- it does not "
                "exist in FortiSOAR. Filter on `name` instead.")
    if available:
        msg += f" Fields these records carry: {', '.join(available)}."
    return {"ok": False, "code": "unknown_filter_field", "field": bad_field,
            "module": bare, "filterable": available, "url": url,
            "message": msg + " Re-run with a real field name."}


def _shape_search_members(data: dict, sample_n: int, bare: str, url: str,
                          matched_by: str | None = None,
                          fields: list[str] | None = None,
                          page: int = 1) -> dict[str, Any]:
    """Shape a crudhub list body into the flat ``{iri,label,id}`` result dict
    shared by the field-filter and ``$search`` paths.

    When ``fields`` is given, each requested field is echoed onto its result
    from the member dict the API already returned -- the payload carries every
    field, so this costs no extra call and is what kills the ``get_record``
    fan-out a summarize-these-records turn used to need.

    Always reports whether the answer is partial: ``total`` is the server's
    match count, ``showing`` is how many rows are in ``results``, and when they
    differ a ``truncated`` flag plus an explicit instruction to disclose it.
    A silently-truncated list read as a complete one in live sessions (5 of 59
    automation steps summarized as "the latest automation steps")."""
    members = data.get("hydra:member") or []
    user_want = [f for f in (fields or []) if isinstance(f, str) and f.strip()]
    # Verdict-bearing modules carry identity-level signal that a bare
    # {iri,label,id} row drops -- an indicator's whole point is its reputation,
    # the way an alert's is its sourceIp. Without this, a pivot that searches
    # indicators for the alert's source IP finds the hit but reads only its
    # name, so the agent reports "present in the database" and never cites the
    # Suspicious/Malicious verdict (live F1). When the model asked for no
    # fields, inject the module's verdict fields so the reputation rides inline
    # -- no second get_record, and `available_fields` is still named below.
    auto_want = [] if user_want else list(_VERDICT_MODULE_FIELDS.get(bare, ()))
    want = user_want or auto_want
    results = []
    seen_fields: set[str] = set()
    for m in members[:sample_n]:
        if not isinstance(m, dict):
            continue
        iri = m.get("@id")
        if not iri:
            continue
        label = (m.get("name") or m.get("title") or m.get("subject")
                 or m.get("displayName") or m.get("hostname")
                 or m.get("description"))
        if not label:
            label = iri.rsplit("/", 1)[-1]
        row = {"iri": iri, "label": str(label)[:120], "id": m.get("id")}
        for f in want:
            if f in m:
                seen_fields.add(f)
                row[f] = _flatten_field(m[f])
        results.append(row)
    total = int(data.get("hydra:totalItems", len(members)))
    out: dict[str, Any] = {
        "ok": True,
        "module": bare,
        "total": total,
        "showing": len(results),
        "results": results,
        "url": url,
    }
    if matched_by:
        out["matched_by"] = matched_by
    if user_want:
        missing = [f for f in user_want if f not in seen_fields]
        if missing:
            # Don't fail the search over a bad field name -- say which ones the
            # module never returned so the model can correct instead of
            # silently treating an absent field as an empty value.
            out["unknown_fields"] = missing
            out["hint"] = (f"these requested fields are not on {bare!r} records: "
                           f"{', '.join(missing)} -- they are absent from the "
                           "results, not empty.")
    if not user_want and results:
        # The model asked for no fields, so every row is {iri,label,id} -- which is
        # exactly when it goes and `get_record`s each hit to find the values it
        # needs (live: 10 searches + 10 get_records for one "summarize these"
        # turn, which then truncated at 25 of 75). The payload we ALREADY have
        # carries every field, so naming them costs nothing and turns the next
        # query into one call. It doubles as the sortable-field list, killing the
        # `stepNum` vs `stepNumber` guessing at the source.
        out["available_fields"] = sorted(
            {k for m in members[:sample_n] if isinstance(m, dict)
             for k in m.keys() if isinstance(k, str) and not k.startswith("@")}
        )[:60]
        # Which of those are RELATIONSHIPS, called out separately.
        #
        # A flat alphabetical list makes `ztpfRunGroups` indistinguishable from
        # `triggerKey`, and the model picks scalar fields it can name from the
        # question's own words. Observed: "what have we done to make changes"
        # produced a clean two-call summary with
        # fields=[name,status,stepNumber,script,...] and NO run group -- so the
        # answer could not attribute a single step to the run that performed it,
        # and the omission is invisible because the summary reads complete.
        #
        # Grouping and attribution are exactly the questions that need a
        # relationship, and they are exactly the questions `fields=` is for. So
        # name them, rather than hoping the model infers which entries in a
        # 20-name list point at other records.
        rel_fields = sorted(_relationship_fields(members[:sample_n]))
        if rel_fields:
            out["relationship_fields"] = rel_fields
        out["hint"] = (
            "these rows carry only iri/label/id. To summarize, group, sort or "
            "compare, re-run this search with `fields=[...]` from "
            "`available_fields` -- do NOT call get_record on each hit."
            + (f" To group rows, or say WHICH related record each row belongs "
               f"to, you must include the relationship field itself: "
               f"{', '.join(rel_fields)}. Omitting it does not make the answer "
               f"shorter, it makes it unattributable." if rel_fields else ""))
    # Where this page sits in the match set. `page` is 1-based (FSR's `$page`),
    # so page 2 of a 25-row page starts at record 26.
    first = (max(1, int(page)) - 1) * sample_n
    out["page"] = max(1, int(page))
    out["pages"] = max(1, -(-total // sample_n)) if sample_n else 1
    if total > first + len(results):
        out["truncated"] = True
        out["has_more"] = True
        out["next_page"] = out["page"] + 1
        # Naming the next page is the whole point. Before pagination existed
        # this message could only say "narrow your filters", so a question whose
        # honest answer spans every record -- "list every change on this device",
        # 88 steps deep -- had no reachable answer at all: the model relayed a
        # partial view or stopped to ask permission it could not act on. Say
        # exactly which call gets the rest.
        out["message"] = (
            f"showing records {first + 1}-{first + len(results)} of {total}. "
            f"This is a PARTIAL view. To cover them all, call this tool again "
            f"with page={out['next_page']} (same module/filters/fields) and keep "
            f"paging while `has_more` is true -- there are {out['pages']} pages "
            f"at limit={sample_n}. Only summarize once you have every page, or "
            "state plainly that the answer covers just the rows you read.")
    elif out["page"] > 1:
        out["has_more"] = False
        out["message"] = (
            f"showing records {first + 1}-{first + len(results)} of {total} "
            "-- this is the LAST page.")
    if not results:
        # An empty result is where the model used to spin -- silently retrying
        # query variants. Tell it how to widen instead of leaving it guessing.
        out["hint"] = ("no records matched. If you used an exact field filter, "
                       "confirm the field/value (list a few with an empty q to "
                       "see what exists); if you used free-text q, it is a "
                       "substring $search -- for an exact field match pass "
                       "filters={field: value}.")
    return out


def _relationship_fields(members: list) -> set:
    """Field names on these records that point at ANOTHER record.

    Identified by the value's shape, not by a name list: a relationship carries
    an `@id` IRI (one record, or a list of them). A picklist is also a dict but
    carries `itemValue` with no `@id`, and must NOT be reported as a
    relationship -- `status` is a value to select, not a record to group by.

    Shape-based on purpose. A hardcoded set of relationship names would be one
    more parallel list to drift out of sync with the module schema, and would
    be silently wrong on every custom module.
    """
    def _is_rel(v) -> bool:
        if isinstance(v, dict):
            return isinstance(v.get("@id"), str) and "/api/3/" in v["@id"]
        if isinstance(v, list):
            return any(_is_rel(i) for i in v)
        return False

    out = set()
    for m in members:
        if not isinstance(m, dict):
            continue
        for k, v in m.items():
            if isinstance(k, str) and not k.startswith("@") and _is_rel(v):
                out.add(k)
    return out


@mcp.tool()
def search_module_records(module: str, q: str = "",
                          limit: int = 10,
                          filters: dict[str, Any] | list[dict[str, Any] | str] | None = None,
                          fields: list[str] | None = None,
                          sort: str | list | None = None,
                          page: int = 1) -> dict[str, Any]:
    """Search a FortiSOAR module for records matching a query -- the core
    triage PIVOT tool (and the relation IRI picker's backend).

    Use this to find every record touching an indicator: search ``alerts``/
    ``incidents``/``assets``/``identities``/``indicators`` for an IP, user, or
    hostname pulled off the record you're triaging, then ``get_record`` the
    hits to correlate the activity.

    Hits ``GET /api/3/<module>?$search=<q>&$limit=<limit>`` on the
    configured FSR and returns a flat list of ``{iri, label, ...}`` pairs.
    Empty ``q`` returns the most-recent records (FSR's natural sort order).

    Three ways to match specific fields exactly (as opposed to `$search`'s
    free-text scan, which does NOT understand ``field:value`` syntax):

      * pass ``filters={"datakey": "interface_stats"}`` -- one or more exact
        field equalities, ANDed together;
      * pass the list form ``filters=[{"field": "status", "op": "eq",
        "value": "Ready"}]`` -- conditions with operators (``eq``, ``neq``,
        ``gt``, ``lt``, ``in``, …); or
      * write ``q="datakey:interface_stats"`` -- a whole-string ``field:value``
        (or ``field=value``) is routed to the same equality filter.

    To find CHILD records by their PARENT (e.g. every automation step on a
    device, or steps with NO run group), filter on the relationship field:
      * by parent IRI/uuid: ``filters={"ztpf_device": "/api/3/ztpf_devices/<uuid>"}``
      * "has no run group": ``filters=[{"field": "ztpf_run_group", "value": null}]``
        -- a null value is matched as *is-empty*, NOT a literal "null" string.
    Structured filters (list form, or any null/non-eq condition) go through the
    Find-Records query API, which understands relationship + null semantics that
    a flat ``?field=value`` cannot express.

    Use a field filter when you know the field (e.g. a metadata source's
    ``datakey``, a record's ``name``); use free-text ``q`` to fuzzy-match
    across a module's searchable fields.

    Args:
      module: bare module name (e.g. ``alerts``); any ``?$limit=…``
        suffix the visual editor stashes is stripped here. An unknown
        collection name is refused with a nearest-match suggestion.
      q: optional query. A whole-string ``field:value`` becomes an exact
        field filter; otherwise it is a case-insensitive ``$search``
        substring across each entity's "searchable fields".
      limit: number of results per page (clamped to [1, 25]).
      page: which page of results to read, 1-based (default 1). The row cap is
        per PAGE, not per question: when a result comes back with
        ``has_more: true``, re-run the identical call with ``page=next_page``
        and keep going until ``has_more`` is false. That is how you answer
        "list every X" on a module with hundreds of records -- do NOT summarize
        page 1 as though it were the whole set, and do NOT stop to ask the
        analyst for permission to read the rest.
      filters: exact-match conditions. Either a ``{field: value}`` map, or the
        list form ``[{"field"|"key": .., "op"|"operator": .., "value": ..}]``.
        A ``None`` value on a condition matches records where that field is
        empty. Takes precedence over / merges with ``field:value`` from ``q``.
      fields: extra field names to echo onto each result, e.g.
        ``["status", "stepNumber", "modifyDate", "ztpfRunGroups"]``. **Use this
        whenever you intend to summarize, group, or sort the hits** -- the rows
        then carry what you need and you do NOT have to ``get_record`` each hit
        (that fan-out is what limited a 59-record summary to its first 5).
        Picklists collapse to their display value and relationships to
        ``{label, iri}``. Names the module doesn't have come back in
        ``unknown_fields`` rather than failing the search.
      sort: order the results -- ``"modifyDate"`` (descending by default),
        ``"-modifyDate"`` / ``"createDate asc"``, or the explicit list form
        ``[{"field": "modifyDate", "direction": "DESC"}]``. Sorting routes the
        search through the query API; when that module can't sort server-side the
        rows are ordered here instead (flagged ``sorted_client_side``), so a
        sort request is honored either way. Use ``modifyDate``/``createDate`` for
        "latest"/"how long ago" questions -- FSR has no ``modifiedOn`` field. Sort
        by a field name from ``available_fields`` (e.g. ``stepNumber``), not a
        guess.

    Returns:
      ``{"ok": true, "module": .., "total": N, "showing": n, "results":
      [{iri, label, id, ...fields}]}`` on success, else ``{"ok": false, "code":
      .., "message": ..}``. Every result carries ``page`` and ``pages``. When
      rows remain beyond this page it is flagged ``truncated`` **and**
      ``has_more: true`` with a ``next_page`` -- fetch that page and keep going;
      only relay a partial view if you deliberately stop early, and say so.
      When you passed no ``fields``, the result also names ``available_fields``
      (every field these records carry) -- re-query with the ones you need rather
      than calling ``get_record`` per hit. ``sorted_client_side`` means the
      ordering was applied to the returned page only. An empty ``results``
      carries a ``hint`` on how to widen the query; ``unknown_sort_field``
      carries the module's real ``sortable`` names, and ``unknown_filter_field``
      the real ``filterable`` ones. Note ``label`` is a display name synthesized
      for each row -- it is NOT a filterable field; filter on ``name``.
    """
    if not module or not isinstance(module, str):
        return {"ok": False, "code": "missing_module",
                "message": "search_module_records requires a non-empty module name"}
    bare = module.split("?", 1)[0].strip()
    if not bare:
        return {"ok": False, "code": "missing_module",
                "message": f"module {module!r} is empty after stripping query string"}
    sample_n = max(1, min(int(limit), 25))
    # FSR paginates with a 1-based `$page`; `$offset`/`$skip` are accepted and
    # then silently IGNORED (live-verified on 8.0 -- both returned page 1
    # again). Anything that computes a row offset must go through `$page`, or
    # it re-reads the first page while believing it advanced.
    try:
        page_n = max(1, int(page))
    except (TypeError, ValueError):
        page_n = 1
    _pg = f"&$page={page_n}" if page_n > 1 else ""

    # A structured spec -- the list-of-conditions form, or a dict/list carrying a
    # null test or a non-eq operator -- needs the Find-Records query API (it
    # expresses is-null and relationship semantics a flat `?field=value` GET
    # cannot). A plain `{field: scalar}` dict stays on the proven flat-GET path.
    def _needs_query_api(f: Any) -> bool:
        if isinstance(f, list):
            return True
        if isinstance(f, dict):
            if "logic" in f and "filters" in f:
                return True
            # A null test, a dotted relationship/picklist path (`status.itemValue`,
            # `ztpfDevices.uuid`), or an IRI value all need the query API -- the
            # flat `?field=value` GET can't express relationship/null semantics.
            for k, v in f.items():
                if v is None:
                    return True
                if isinstance(k, str) and "." in k:
                    return True
                if isinstance(v, str) and v.startswith("/api/3/"):
                    return True
        return False

    client = _shared._live_client()
    if client is None:
        return {"ok": False, "code": "no_fsr_configured",
                "message": "no FSR instance is configured -- run `fsrpb env set` first"}

    # A requested sort ALSO forces the query API: only its POST body carries a
    # `sort` clause (live-verified on 8.0 -- the flat `?field=value` GET has no
    # ordering knob). Routing here keeps one right way to order results.
    try:
        sort_spec = _normalize_sort(sort)
    except ValueError as e:
        return {"ok": False, "code": "bad_sort", "message": str(e)}

    if sort_spec or (filters is not None and _needs_query_api(filters)):
        try:
            body = _build_query_filters(filters if filters is not None else {})
        except ValueError as e:
            return {"ok": False, "code": "bad_filters", "message": str(e)}
        if sort_spec:
            body = {**body, "sort": sort_spec}
        # Always echo the fields we ORDERED by. An ordering the model cannot see
        # is one it re-derives or doubts -- live, it hand-parsed step
        # numbers out of record labels because the sorted rows carried none.
        # Applies to the server-sorted path too, not just the fallback (a live
        # probe returned correctly-sorted rows with `stepNumber` absent).
        sorted_fields = _with_sort_fields(fields, sort_spec)
        qurl = f"{client.base_url}/api/query/{bare}?$limit={sample_n}{_pg}"
        try:
            qr = _post_with_reauth(client, qurl, json=body)
            if qr.status_code == 200:
                qdata = qr.json()
                if isinstance(qdata, dict):
                    return _shape_search_members(qdata, sample_n, bare, qurl,
                                                 matched_by="filter",
                                                 fields=sorted_fields,
                                                 page=page_n)
            bad_field = _unknown_field_in(qr.text)
            if bad_field:
                return _unknown_filter_field(client, bare, bad_field, qurl)
            if sort_spec and qr.status_code >= 400:
                # A sort the query API rejects is NOT the end of the road, and
                # saying so was the bug: live, the model asked for
                # `stepNum`, got this error, and told the analyst "this module
                # does not support sorting by a step number field" -- the field is
                # `stepNumber` and it sorts fine. Refuse-and-stop turned a typo
                # into a false capability claim. Re-run the query unsorted and
                # order the page ourselves; the ordering the analyst asked for is
                # deliverable either way.
                return _sort_fallback(client, bare, body, sort_spec, sample_n,
                                      fields, qurl)
            return {"ok": False, "code": f"http_{qr.status_code}",
                    "message": (qr.text[:500] or f"HTTP {qr.status_code}"),
                    "url": qurl}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "code": "transport_error",
                    "message": f"POST {qurl} failed: {exc}", "url": qurl}

    # Assemble exact-equality field filters from a `{field: value}` dict and
    # from a `field:value` written into `q` (the syntax the model reaches for).
    field_filters: dict[str, str] = {}
    if isinstance(filters, dict):
        for k, v in filters.items():
            if isinstance(k, str) and k.strip() and v is not None:
                field_filters[k.strip()] = str(v)
    orig_q = q or ""
    q_filters, q = _split_field_query(bare, orig_q)
    for k, v in q_filters.items():
        field_filters.setdefault(k, v)

    # Exact field-equality path (the fix for the silent-zero class). Build
    # `?field=value&...&$limit=n`. On a clean 200 -- even with zero rows -- this
    # is authoritative (an exact filter that matches nothing is a real "no
    # match", returned with a hint). Only a transport/HTTP error falls through
    # to $search on the original text, so a bad field name never regresses.
    if field_filters:
        from urllib.parse import quote
        parts = "&".join(f"{quote(k)}={quote(v)}" for k, v in field_filters.items())
        furl = f"{client.base_url}/api/3/{bare}?{parts}&$limit={sample_n}{_pg}"
        try:
            fr = _get_with_reauth(client, furl)
            if fr.status_code == 200:
                fdata = fr.json()
                if isinstance(fdata, dict):
                    return _shape_search_members(fdata, sample_n, bare, furl,
                                                 matched_by="filter",
                                                 fields=fields,
                                                 page=page_n)
            # A named-but-nonexistent field is a mistake to REPORT, not to
            # paper over. Falling through to $search here turned "filter on
            # label" into a fuzzy text scan whose unrelated hits look like a
            # real answer -- the silent-wrong-answer shape this tool exists to
            # avoid. Transport errors still fall through; only a field FSR
            # explicitly rejects stops here.
            bad_field = _unknown_field_in(fr.text)
            if bad_field:
                return _unknown_filter_field(client, bare, bad_field, furl)
        except Exception:  # noqa: BLE001 -- fall through to $search
            pass
        # Filter fetch failed (unknown field 400, transport). Recover the model's
        # original free text for a best-effort $search rather than dead-ending.
        q = orig_q

    # A purely-numeric query ("560") almost always means the analyst wants
    # record #560 (the per-module sequential `id`), not a text match -- and
    # $search doesn't cover the `id` column, so it returns 0 or a flood of
    # unrelated hits. Try the `?id=<n>` equality filter first; only fall
    # through to $search when nothing matches that id.
    if q and q.strip().isdigit():
        from urllib.parse import quote
        id_url = f"{client.base_url}/api/3/{bare}?id={quote(q.strip())}&$limit=1"
        try:
            ir = _get_with_reauth(client, id_url)
            if ir.status_code == 200:
                idata = ir.json()
                imembers = [m for m in (idata.get("hydra:member") or [])
                            if isinstance(m, dict) and m.get("@id")]
                if imembers:
                    m = imembers[0]
                    label = (m.get("name") or m.get("title") or m.get("subject")
                             or m.get("displayName") or m.get("hostname")
                             or m.get("description")
                             or m["@id"].rsplit("/", 1)[-1])
                    return {
                        "ok": True, "module": bare, "matched_by": "id",
                        "total": 1, "showing": 1,
                        "results": [{"iri": m["@id"], "label": str(label)[:120],
                                     "id": m.get("id"),
                                     **{f: _flatten_field(m[f])
                                        for f in (fields or []) if f in m}}],
                        "url": id_url,
                    }
        except Exception:  # noqa: BLE001 -- fall through to $search
            pass

    # Use $search for substring match across the entity's indexed
    # fields. Falls back to a plain $limit fetch when q is empty so
    # the dropdown has *something* to render before the user types.
    qs = f"$limit={sample_n}{_pg}"
    if q:
        from urllib.parse import quote
        qs += f"&$search={quote(q)}"
    url = f"{client.base_url}/api/3/{bare}?{qs}"
    try:
        r = _get_with_reauth(client, url)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "code": "transport_error",
                "message": f"GET {url} failed: {exc}", "url": url}
    if r.status_code == 404:
        near = _nearest_modules(bare)
        msg = f"no such module route {bare!r}"
        if near:
            msg += f" -- did you mean: {', '.join(near)}?"
        return {"ok": False, "code": "not_found", "message": msg,
                "suggestions": near, "url": url}
    if r.status_code != 200:
        return {"ok": False, "code": f"http_{r.status_code}",
                "message": (r.text[:500] or f"HTTP {r.status_code}"),
                "url": url}
    try:
        data = r.json()
    except Exception:  # noqa: BLE001
        return {"ok": False, "code": "bad_json",
                "message": "FSR returned 200 but body was not JSON", "url": url}

    if q and not data.get("hydra:totalItems") and not (data.get("hydra:member") or []):
        named = _search_by_name(client, bare, q, sample_n, _pg)
        if named is not None:
            ndata, nurl, nfield = named
            out = _shape_search_members(ndata, sample_n, bare, nurl, fields=fields,
                                        page=page_n)
            out["matched_by"] = f"{nfield} contains"
            return out

    return _shape_search_members(data, sample_n, bare, url, fields=fields,
                                 page=page_n)


# Label fields a record is usually named by, tried in order when `$search`
# finds nothing. `$search` only covers the fields a module marks searchable,
# and on some custom modules that excludes the name: every ztpf_run_groups
# lookup by its own name ("ztpf-1790107549") returned 0 live, and the agent
# reported the run group as not existing. A field the module lacks 400s and is
# skipped.
_NAME_FIELDS = ("name", "title", "subject")


def _search_by_name(client: Any, bare: str, q: str, limit: int,
                    page_qs: str) -> tuple[dict, str, str] | None:
    """The first ``<field>$like=%q%`` over `_NAME_FIELDS` that matches, or None."""
    from urllib.parse import quote
    for field in _NAME_FIELDS:
        url = (f"{client.base_url}/api/3/{bare}?$limit={limit}{page_qs}"
               f"&{field}$like={quote('%' + q.strip() + '%')}")
        try:
            r = _get_with_reauth(client, url)
            if r.status_code != 200:
                continue
            data = r.json()
        except Exception:  # noqa: BLE001 -- best effort; the empty $search result stands
            continue
        if data.get("hydra:member"):
            return data, url, field
    return None


# Re-authenticating request wrappers live centrally in _shared (any live MCP
# tool hits the same staleness class) -- see `_shared.live_request_with_reauth`.
_get_with_reauth = _shared.live_get_with_reauth
_post_with_reauth = _shared.live_post_with_reauth


def _resolve_record_id(client: Any, module: str, rec_id: str,
                       relationships: bool) -> tuple[dict[str, Any] | None,
                                                     str, dict[str, Any] | None]:
    """Resolve a per-module sequential ``id`` (the "Incident #560" a human
    types) to a full record via the URL-param ``id`` equality filter.

    FSR exposes two identifiers per record: the UUID (global, what
    ``get_record`` natively wants) and the integer ``id`` (sequential
    *within a module*, what the UI shows and the only id an analyst knows
    off-hand). ``GET /api/3/<module>/<id>`` 404s -- the path segment must be
    a UUID -- so we go through ``?id=<n>`` (default ``eq`` operator, see
    store/QUERY_API.md §1) and take the single member.

    Returns ``(record|None, url, error|None)``: the record dict on a hit,
    or an error payload (3rd slot) the caller can return verbatim.
    """
    from urllib.parse import quote
    qs = f"id={quote(rec_id)}&$limit=1"
    if relationships:
        qs += "&$relationships=true"
    url = f"{client.base_url}/api/3/{module}?{qs}"
    try:
        r = _get_with_reauth(client, url)
    except Exception as exc:  # noqa: BLE001
        return None, url, {"ok": False, "code": "transport_error",
                           "message": f"GET {url} failed: {exc}", "url": url}
    if r.status_code != 200:
        return None, url, {"ok": False, "code": f"http_{r.status_code}",
                           "message": (r.text[:500] or f"HTTP {r.status_code}"),
                           "url": url}
    try:
        data = r.json()
    except Exception:  # noqa: BLE001
        return None, url, {"ok": False, "code": "bad_json",
                           "message": "FSR returned 200 but body was not JSON",
                           "url": url}
    members = data.get("hydra:member") or []
    if not members or not isinstance(members[0], dict):
        return None, url, {
            "ok": False, "code": "not_found",
            "message": (f"no {module} record with id {rec_id} "
                        "(the per-module sequential number, not a UUID)"),
            "url": url}
    return members[0], url, None


# A verbatim field read is for a template or script the model will edit;
# past this many characters it is clipped and says so.
_VERBATIM_MAX = 60000


def _clipped_text_fields(rec: dict[str, Any]) -> list[str]:
    """Top-level text fields the record view shortened: cut past the length cap
    or rewritten without their HTML tags. Live, the model rewrote a whole
    automation-action template from the first 600 characters of it."""
    out = []
    for k, v in rec.items():
        if not isinstance(k, str) or k.startswith("@") or not isinstance(v, str):
            continue
        if len(v) > _REC_MAX_STR or ("<" in v and ">" in v and _TAG_RE.search(v)):
            out.append(k)
    return out


def _verbatim_fields(rec: dict[str, Any], names: list[str]) -> dict[str, Any]:
    """``{fields: {name: value}}`` read whole from ``rec`` (names matched
    case-insensitively), plus ``unknown_fields`` with the closest real names."""
    if isinstance(names, str):
        names = [names]
    by_low = {k.lower(): k for k in rec if isinstance(k, str) and not k.startswith("@")}
    got: dict[str, Any] = {}
    clipped: list[str] = []
    unknown: dict[str, list[str]] = {}
    for n in names or []:
        key = n if n in rec else by_low.get(str(n).strip().lower())
        if key is None:
            unknown[str(n)] = _nearest_field_names(str(n), sorted(by_low.values()))
            continue
        v = rec[key]
        if isinstance(v, str) and len(v) > _VERBATIM_MAX:
            v = v[:_VERBATIM_MAX]
            clipped.append(key)
        got[key] = v
    out: dict[str, Any] = {"fields": got}
    if clipped:
        out["fields_clipped"] = {k: f"first {_VERBATIM_MAX} characters" for k in clipped}
    if unknown:
        out["unknown_fields"] = unknown
    return out


@mcp.tool()
def get_record(iri: str = "", module: str = "", uuid: str = "",
               relationships: bool | list[str] = True, full: bool = False,
               record_id: str = "", fields: list[str] | None = None) -> dict[str, Any]:
    """Fetch a single FSR record by IRI, module+uuid, or module+record_id.

    The read-only companion the triage prompt assumes when it tells the
    agent to pull an event/alert/asset row by its ``iri``/``module``/``uuid``
    to build an attack timeline or assess blast radius. Wraps
    ``GET /api/3/<module>/<uuid>?$relationships=true`` so related records
    (correlated alerts, linked assets, indicators) come back inline rather
    than as bare IRIs the agent would have to chase one by one.

    To fetch the record a human names by its **sequential number** (e.g.
    "investigate case 560" / "incident #560"), pass that number as
    ``record_id`` together with ``module`` -- that integer is the per-module
    ``id`` column, NOT a UUID, so it can't go in the IRI path (FSR would
    404). A bare-numeric value pasted into ``uuid`` or ``iri`` is treated
    the same way as a convenience.

    Args:
      iri: full record IRI (e.g. ``/api/3/alerts/<uuid>``). Takes
        precedence over module+uuid when both are supplied. A bare number
        (or ``module:560`` shorthand) is treated as a ``record_id``.
      module: bare module name (e.g. ``alerts``/``incidents``) -- required
        with ``uuid`` or ``record_id``.
      uuid: record UUID -- required if no ``iri``. An all-digits value is
        treated as a ``record_id`` lookup instead.
      record_id: the per-module sequential ``id`` (what the UI shows as
        "#560"); resolved via ``?id=<n>`` and needs ``module``.
      fields: field names to return verbatim and whole under ``fields`` (a
        template, script or long description you will read closely or edit).
        The record view shortens long text and strips HTML; it lists what it
        shortened under ``clipped_fields``.
      relationships: when true (default), append ``?$relationships=true``
        so related entities are hydrated inline.
      full: leave this false. The default pruned projection already
        contains every triage-relevant field -- all indicator scalars
        (sourceIp/destinationIp/host/user/hashes), severity/status, and a
        capped {iri,label} index of related records -- at ~5% the size.
        ``full=True`` does NOT return the raw ~100KB body: it returns a
        cleaned (null/empty + SLA/boilerplate stripped), hard size-capped
        body with ``coerced_full=true`` set. It exists only for rare
        schema-debugging; do NOT set it during normal triage -- the pruned
        default has every pivotable field already.

    Returns:
      ``{"ok": true, "iri": ..., "record": {...}, "url": ...}`` on a 200,
      else ``{"ok": false, "code": ..., "message": ...}``. When pruned,
      ``"summarized": true`` is set so callers know it isn't the raw body.
    """
    # `relationships` may arrive as a list of names (the agent reaches for
    # `relationships=["ztpfArtifacts"]` to expand a named relationship); the
    # native contract is a bool ("hydrate all inline"), so collapse it.
    relationships = bool(relationships)

    # A UUID pasted into `record_id` is the record's real UUID, not the
    # sequential id -- the agent uses "record_id" to mean "the id of the record".
    # `record_id` only id-resolves when all-digits; a UUID there matched no
    # branch and fell through to `missing_target` (the top ztpf device error).
    # Route it to the uuid path so `module`+`record_id=<uuid>` just works.
    _UUID_SHAPE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                             r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
    if not uuid and record_id and _UUID_SHAPE.match(str(record_id).strip()):
        uuid = str(record_id).strip()
        record_id = ""

    # First, normalise a numeric "record id" (the per-module sequential
    # number a human knows) out of whichever slot the agent dropped it in.
    rid = ""
    mod_hint = (module or "").split("?", 1)[0].strip()
    if str(record_id).strip().isdigit():
        rid = str(record_id).strip()
    elif str(uuid).strip().isdigit():
        rid = str(uuid).strip()
    elif iri and isinstance(iri, str):
        s = iri.strip().split("?", 1)[0]
        head = s.split(":", 1)[0]
        if ":" in s and "/" not in head and head.strip().isalpha() \
                and s.partition(":")[2].strip().isdigit():
            # `incidents:560` shorthand with a numeric tail.
            rid = s.partition(":")[2].strip()
            mod_hint = mod_hint or head.strip()
        elif s.isdigit():
            rid = s

    path = ""
    id_lookup = False
    if rid:
        if not mod_hint:
            return {"ok": False, "code": "missing_module",
                    "message": (f"record id {rid!r} needs a `module` (e.g. "
                                "module='incidents') -- the sequential number "
                                "is only unique within a module")}
        id_lookup = True
    elif iri and isinstance(iri, str):
        s = iri.strip().split("?", 1)[0]
        head = s.split(":", 1)[0]
        if ":" in s and "/" not in head:
            # `module:uuid` shorthand (the colon form the triage prompt
            # uses, e.g. `alerts:54f2…`) -- the agent often pastes it
            # straight into `iri`. Expand to a real IRI instead of 404ing.
            mod, _, rest = s.partition(":")
            path = f"/api/3/{mod.strip()}/{rest.strip()}"
        else:
            # Full IRI, with or without a leading slash.
            path = "/" + s.lstrip("/")
        if len([x for x in path.split("/") if x]) < 4 or not path.startswith("/api/"):
            # A bare id (live: a card id) is no record route; fetched as-is it
            # hit a non-API page and the tool crashed on the reply.
            return {"ok": False, "code": "bad_iri",
                    "message": (f"{iri!r} is not a record IRI; pass "
                                "iri='/api/3/<module>/<uuid>', or module + uuid. "
                                "A card or run id is not a record id.")}
    elif module and uuid:
        bare = module.split("?", 1)[0].strip()
        if not bare:
            return {"ok": False, "code": "missing_module",
                    "message": f"module {module!r} is empty after stripping query string"}
        path = f"/api/3/{bare}/{uuid.strip()}"
    else:
        return {"ok": False, "code": "missing_target",
                "message": ("get_record requires an `iri`, both `module` and "
                            "`uuid`, or both `module` and `record_id`")}

    client = _shared._live_client()
    if client is None:
        return {"ok": False, "code": "no_fsr_configured",
                "message": "no FSR instance is configured -- run `fsrpb env set` first"}

    if id_lookup:
        data, url, err = _resolve_record_id(client, mod_hint, rid, relationships)
        if err is not None:
            return err
        assert data is not None
    else:
        url = f"{client.base_url}{path}"
        if relationships:
            url += "?$relationships=true"
        try:
            r = _get_with_reauth(client, url)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "code": "transport_error",
                    "message": f"GET {url} failed: {exc}", "url": url}
        if r.status_code == 404:
            # A 404 here is either a bad module route or a valid module with an
            # unknown id/uuid. Offer a nearest-module hint only when the module
            # segment isn't a known collection -- so a fabricated collection name
            # gets "did you mean", while a bad uuid in a real module doesn't get
            # a misleading module suggestion.
            seg = path.split("/")
            mod_seg = seg[3] if len(seg) > 3 else ""
            near = _nearest_modules(mod_seg) if mod_seg else []
            msg = f"no record at {path}"
            if near:
                msg += f" -- unknown module; did you mean: {', '.join(near)}?"
                return {"ok": False, "code": "not_found", "message": msg,
                        "suggestions": near, "url": url}
            # A real module and an unknown uuid: an invented identifier
            # (HARDEN-4). Name real records instead of leaving a guess to retry.
            from . import _record_lookup
            active = _shared.active_record_iri()
            candidates = _record_lookup.record_candidates(
                client, mod_seg, active) if mod_seg else []
            if candidates:
                msg += (" -- do NOT retry a guessed uuid: use one of "
                        "`candidates`, or find the record with "
                        f"search_module_records(module={mod_seg!r}, q=...)")
            close = _record_lookup.near_uuid(
                client, mod_seg, seg[-1] if len(seg) > 4 else "", active, candidates)
            out_nf = {"ok": False, "code": "not_found", "message": msg,
                      "suggestions": near, "candidates": candidates, "url": url}
            if close:
                out_nf["message"] += _record_lookup.did_you_mean_text(close)
                out_nf["did_you_mean"] = close
            return out_nf
        if r.status_code != 200:
            return {"ok": False, "code": f"http_{r.status_code}",
                    "message": (r.text[:500] or f"HTTP {r.status_code}"),
                    "url": url}
        try:
            data = r.json()
        except Exception:  # noqa: BLE001
            return {"ok": False, "code": "bad_json",
                    "message": "FSR returned 200 but body was not JSON", "url": url}

    out: dict[str, Any] = {
        "ok": True,
        "iri": data.get("@id", path),
        "url": url,
    }
    if fields:
        out.update(_verbatim_fields(data, fields))
    if full:
        # `full=True` is discouraged during triage -- the pruned projection
        # already carries every pivotable field. We honour the request for a
        # fuller body but NEVER return the raw ~100KB blob: strip the dead
        # weight (null/empty, SLA/boilerplate) and hard-cap the size so one
        # call can't blow the per-turn budget (the sess-uq31go5p waste). The
        # flags tell the agent it didn't get the verbatim body.
        cleaned = _clean_full_record(data)
        capped, truncated = _cap_json(cleaned)
        out["coerced_full"] = True
        if truncated:
            # A head/tail byte-chop of a 300KB record is unusable -- it hands the
            # model a JSON *fragment* string, which is exactly what let the agent
            # answer off a truncated head and hallucinate. Return the pruned
            # projection instead: every pivotable scalar field + a capped index
            # of related rows, at ~5% the size, as STRUCTURED data the model can
            # actually reason over. Deep nested sub-objects are dropped -- the
            # note tells the agent to fetch specifics with a follow-up tool call.
            out["record"] = _summarize_record(data)
            out["summarized"] = True
            out["truncated"] = True
            out["note"] = (
                "full=True body exceeded the size cap; returned the pruned "
                "projection (every pivotable field) instead of a raw "
                "byte-truncated fragment. Some deep/nested sub-objects were "
                "omitted -- if you need one, fetch it with a targeted follow-up "
                "(get_record on the related iri / search_module_records). Do "
                "NOT infer omitted values.")
        else:
            out["record"] = capped
            out["note"] = (
                "full=True returned a cleaned, size-capped body (null/empty + "
                "SLA/boilerplate dropped), not the raw hydrated record. The "
                "default pruned projection already has every pivotable field -- "
                "prefer get_record without full= during triage.")
    else:
        out["record"] = _summarize_record(data)
        out["summarized"] = True
    if out.get("summarized"):
        clipped = [k for k in _clipped_text_fields(data) if k not in (out.get("fields") or {})]
        if clipped:
            out["clipped_fields"] = clipped
            out["clipped_note"] = (
                f"{', '.join(clipped)} {'is' if len(clipped) == 1 else 'are'} shortened "
                "above (long text cut, HTML removed). Before reading one closely or "
                "editing it, call get_record again with fields=[...] for the whole text.")
    return out


# ---------------------------------------------------------------------------
# First-class FortiSIEM search tools
#
# Ergonomic, read-only wrappers over `run_op(_siem_connector(), …)`. The
# agent reliably reaches for these (single clean call, entity pre-filled)
# where it dodges raw `search_events`/`run_op` with its ~20 fiddly params.
# Every wrapper returns the SAME compact `evidence_events` digest the record
# normalizer emits, so the agent learns one event shape everywhere.
# ---------------------------------------------------------------------------

# Bytes + port + host added to the connector's stock columns so the digest can
# show exfil volume and the host pivot without a second call.
# NB: received-bytes is `recvBytes64` -- the pub/v2 engine 400s ("Internal
# Server Error") on the whole query if a single unknown attribute (`rcvdBytes64`)
# is in the SELECT, so this column name must match the FortiSIEM schema exactly.
_SIEM_SELECT = ("phRecvTime,reptDevIpAddr,eventType,eventName,srcIpAddr,"
                "destIpAddr,destIpPort,sentBytes64,recvBytes64,user,hostName")

_WINDOW_UNITS = {"m": "Minutes", "h": "Hours", "d": "Days"}


def _siem_connector() -> str:
    """The FortiSIEM connector to call: v2 (fortinet-fortisiemv2, which keeps
    every v1 operation under v1's name from 6.1.0) or v1, whichever this box
    has ready -- resolved by the same pass that gates the `siem_*` family."""
    return _shared.resolve_source_connector("fortisiem")


def _record_hunt_step(tool: str, echo: dict[str, Any], out: Any) -> None:
    """Record ONE logical SkillCall for a hunt tool, as a ``call_mcp_tool`` step
    on the host connector -- NOT the raw vendor op, which buries the IP inside a
    query payload the compiler can't value-match. ``call_mcp_tool`` takes
    {tool, args} with the tool's simple params at the top level of ``args``, so
    the compiler's nested-dict wiring can parameterize them. No host connector
    means no such step exists to record."""
    host = _shared.host_connector_name()
    if not host:
        return
    try:
        from fsr_playbooks.agent.skill_trace import record_run_op
        record_run_op(host, "call_mcp_tool", {"tool": tool, "args": echo}, out,
                      step_name=tool)
    except Exception:  # noqa: BLE001 -- tracing must never fail the tool
        pass


def _parse_window(window: str) -> tuple[str, int]:
    """'30m'|'2h'|'1d' → (rel_time unit, value) for search_events Relative Time.
    Falls back to (Hours, 2) on anything unrecognized."""
    m = re.fullmatch(r"\s*(\d+)\s*([mhd])\s*", str(window or "").lower())
    if not m:
        return "Hours", 2
    return _WINDOW_UNITS[m.group(2)], int(m.group(1))


def _as_int(value: Any, default: int) -> int:
    """Coerce a numeric tool arg to int, tolerating the string form the MCP
    layer hands us (a model that passes `limit="25"` must not crash a `min()`
    or a slice with `'<' not supported between instances of 'int' and 'str'`)."""
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _event_rows(data: Any) -> list[dict[str, Any]]:
    """Pull the list of event dicts out of a run_op `data` payload, wherever
    the connector parked it (shape varies by op/version)."""
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    if isinstance(data, dict):
        # `samples` is fsr_playbooks's own event-list digest (it collapses big
        # FortiSIEM/FAZ event lists into {_digest, count, samples, facets}).
        for key in ("samples", "events", "rows", "hydra:member", "data",
                    "results", "result", "records"):
            v = data.get(key)
            if isinstance(v, list):
                return [r for r in v if isinstance(r, dict)]
    return []


def _siem_run(op: str, params: dict[str, Any], limit: int,
              echo: dict[str, Any]) -> dict[str, Any]:
    """Shared body: run a read-only FortiSIEM op, digest its events, return a
    uniform envelope. `echo` describes the query for the agent's audit trail."""
    from fsr_playbooks.execution_api import (
        mute_recording,
        run_op,  # lazy: avoid import cycle at load
    )

    from .triage_normalize import _digest_event

    # Mute: this run_op is the implementation of a named MCP pivot tool
    # (siem_search_*/siem_events_for_incident), not an op the agent invoked
    # directly -- keep it off the build trace so the playbook stays grounded in
    # the analyst's actual run_op calls.
    with mute_recording():
        res = run_op(_siem_connector(), op, params)
    if not isinstance(res, dict) or not res.get("ok"):
        # pass the connector's own error straight through (unhealthy/timeout/etc)
        return _siem_error(op, echo, res)
    rows = _event_rows(res.get("data"))
    events = [d for d in (_digest_event(r) for r in rows) if d]
    out = _envelope(op, echo, events, limit)
    _record_hunt_step(op, echo, out)
    return out


def _siem_error(op: str, echo: dict[str, Any],
                underlying: Any) -> dict[str, Any]:
    """Build a SIEM-tool error that PROPAGATES the underlying run_op failure's
    detail (message, issues, suggestions) instead of collapsing it to a bare
    `code`. The opaque collapse is what made siem_search_ip/siem_raw_query
    unrecoverable in export sess-vtd15c5v: the agent saw only
    `code:"bad_params"` with no clue what was wrong, abandoned the first-class
    tool, and fell back to hand-built run_op calls (which then also failed). The
    real cause lives in `underlying` (e.g. a select-option mismatch on the
    execute_api_request submit) -- surface it so the agent (and we) can act."""
    u = underlying if isinstance(underlying, dict) else {}
    out: dict[str, Any] = {
        "ok": False, "op": op, "query": echo,
        "code": u.get("status") or u.get("code") or "siem_op_failed",
        "message": u.get("message") or "FortiSIEM op failed",
    }
    # Carry the actionable bits the connector/validator already computed so the
    # agent can self-correct rather than guess.
    for k in ("issues", "suggestions", "valid_params", "detail"):
        if u.get(k):
            out[k] = u[k]
    out["message"] = _strip_stack_trace(out["message"])
    if "where" in echo:
        # A hand-written clause is the one input we can't vet. Live: three
        # `A OR B OR userName=...` raw queries across fields drew FortiSIEM
        # "Internal Server Error" 400s and the turns stalled -- the model had
        # nothing to change. The structured searches build queries that work.
        out["suggestions"] = [
            "Don't retry this raw clause. Search each indicator with the "
            "structured form instead -- siem_search(by=\"ip\", value=\"<ip>\"), "
            "by=\"user\" or by=\"host\" -- one call per indicator.",
        ] + list(out.get("suggestions") or [])
    return out


def _strip_stack_trace(message: Any) -> str:
    """Keep a connector error's own `message`, drop its Python traceback.

    FortiSIEM's 4xx/5xx bodies embed `{"message": ..., "stack_trace": "..."}`;
    a traceback is noise to the model and pushes the useful part out of view.
    Structural: parse the JSON body, don't pattern-match prose."""
    import json as _json
    text = str(message or "")
    head, brace, body = text.partition("{")
    if not brace:
        return text
    try:
        parsed = _json.loads(brace + body)
    except ValueError:
        return text
    if isinstance(parsed, dict) and "stack_trace" in parsed:
        inner = str(parsed.get("message") or "").strip()
        return (head + inner).strip() if inner else head.strip()
    return text


def _envelope(op: str, echo: dict[str, Any], events: list[dict[str, Any]],
              limit: int) -> dict[str, Any]:
    """Uniform success envelope; `count` is what's returned, `total_found`
    appears only when the result was capped."""
    out = {
        "ok": True, "op": op, "query": echo,
        "count": min(len(events), limit),
        "events": events[:limit],
        "truncated": len(events) > limit,
    }
    if out["truncated"]:
        out["total_found"] = len(events)
    return out


# B3a folded `siem_events_for_incident` and `siem_raw_query` in as the
# `incident` and `raw` axes; they stay registered (not advertised) so an old
# session or a saved playbook that names them still dispatches.
@mcp.tool()
def siem_search(by: Literal["ip", "host", "user", "incident", "raw"], value: str,
                direction: str = "any",
                window: str = "2h", limit: int = 25, time_from: str = "",
                time_to: str = "", source_ip: str = "",
                select: str = "") -> dict[str, Any]:
    """Search FortiSIEM events -- ONE tool, `by` picks the axis: `ip`, `host`, `user` (value = the IP / host / user; `direction` src|dst|any for ip); `incident` (value = the FortiSIEM incident id: the raw events that drove it -- the pivot back into the SIEM that raised an alert; optional `source_ip`, `time_from`/`time_to`); `raw` (value = a native where-clause with BACKEND attribute names, e.g. srcIpAddr="10.1.1.1" AND destIpPort=443 -- the escape hatch when no axis fits; optional `select`). Every axis returns the standard event digest (ts/src/dst/bytes/service/action).

    Args:
      by: ``ip``, ``host``, ``user``, ``incident``, or ``raw``.
      value: what to search for on that axis (see above).
      direction: (``by=ip`` only) ``src``, ``dst``, or ``any`` (default).
      window: relative lookback like ``30m``, ``2h`` (default), ``1d``.
      limit: max digested events to return (default 25).
      time_from, time_to, source_ip: (``by=incident`` only).
      select: (``by=raw`` only) attributes to return.
    """
    by = by.lower().strip()
    if by == "incident":
        return siem_events_for_incident(incident_id=value, time_from=time_from,
                                        time_to=time_to, limit=limit,
                                        source_ip=source_ip)
    if by == "raw":
        where: Any = value
        if isinstance(value, str) and value.strip().startswith("{"):
            try:  # the {field: value} form, passed as JSON text
                where = json.loads(value)
            except ValueError:
                pass
        return siem_raw_query(where=where, select=select, window=window,
                              limit=limit)
    if by == "ip":
        clause = {"src": f"srcIpAddr={_q(value)}",
                  "dst": f"destIpAddr={_q(value)}"}
        if direction in clause:
            where = clause[direction]
        else:
            where = f"(srcIpAddr={_q(value)} OR destIpAddr={_q(value)})"
        return _siem_pubv2_query(where, window=window, limit=limit,
                                 op="siem_search",
                                 echo={"by": "ip", "value": value,
                                       "direction": direction, "window": window})
    if by == "host":
        return _siem_pubv2_query(f"hostName={_q(value)}", window=window,
                                 limit=limit, op="siem_search",
                                 echo={"by": "host", "value": value,
                                       "window": window})
    if by == "user":
        return _siem_pubv2_query(f"user={_q(value)}", window=window,
                                 limit=limit, op="siem_search",
                                 echo={"by": "user", "value": value,
                                       "window": window})
    return {"error": f"unsupported by={by!r}: use 'ip', 'host', 'user', "
                     f"'incident', or 'raw'"}


def siem_search_ip(ip: str, direction: str = "any", window: str = "2h",
                   limit: int = 25) -> dict[str, Any]:
    """Search FortiSIEM events for an IP over a recent window -- the easy pivot.

    Wraps the FortiSIEM connector's `search_events` with the right
    attribute + value param pre-filled and a sane column set, returning the
    standard event digest (ts/src/dst/bytes/service/action). Prefer this over
    hand-building a raw search_events call.

    Args:
      ip: the IPv4 to search for.
      direction: 'src' (source), 'dst' (destination), or 'any' (default --
        matches either end with a single OR query).
      window: relative lookback like '30m', '2h' (default), '1d'.
      limit: max digested events to return (default 25).
    """
    clause = {"src": f"srcIpAddr={_q(ip)}",
              "dst": f"destIpAddr={_q(ip)}"}
    if direction in clause:
        where = clause[direction]
    else:  # 'any' -- OR both ends (valid on the pub/v2 engine)
        where = f"(srcIpAddr={_q(ip)} OR destIpAddr={_q(ip)})"
    return _siem_pubv2_query(where, window=window, limit=limit,
                             op="siem_search_ip",
                             echo={"ip": ip, "direction": direction,
                                   "window": window})


def siem_search_host(host: str, window: str = "2h",
                     limit: int = 25) -> dict[str, Any]:
    """Search FortiSIEM events by host name over a recent window.

    Runs a pub/v2 query (attribute='hostName') and returns the standard event
    digest. Use to pull a compromised host's recent activity in one call.
    """
    return _siem_pubv2_query(f"hostName={_q(host)}", window=window, limit=limit,
                             op="siem_search_host",
                             echo={"host": host, "window": window})


def siem_search_user(user: str, window: str = "2h",
                     limit: int = 25) -> dict[str, Any]:
    """Search FortiSIEM events by user name over a recent window.

    Runs a pub/v2 query (attribute='user') and returns the standard event
    digest. Use to check a user account's recent activity / other sessions.
    """
    return _siem_pubv2_query(f"user={_q(user)}", window=window, limit=limit,
                             op="siem_search_user",
                             echo={"user": user, "window": window})


def _coerce_query_id(data: Any) -> str | None:
    if isinstance(data, dict):
        for k in ("queryId", "query_id", "id"):
            if data.get(k):
                return str(data[k])
        # connector may wrap the FortiSIEM body under data/result
        for k in ("data", "result", "response"):
            qid = _coerce_query_id(data.get(k))
            if qid:
                return qid
    return None


def _q(value: Any) -> str:
    """Quote a scalar for a FortiSIEM where clause, neutralizing embedded `"`."""
    return '"{}"'.format(str(value).replace('"', ""))


# Friendly / FortiSOAR-style field names → FortiSIEM backend attribute names, so
# a model that passes `where={"sourceIPv4": "1.2.3.4"}` (its natural shape) gets
# a valid clause instead of an engine error.
_WHERE_FIELD_ALIASES = {
    "sourceip": "srcIpAddr", "sourceipv4": "srcIpAddr", "srcip": "srcIpAddr",
    "srcipv4": "srcIpAddr", "source_ip": "srcIpAddr", "srcipaddr": "srcIpAddr",
    "destinationip": "destIpAddr", "destip": "destIpAddr",
    "destinationipv4": "destIpAddr", "destipv4": "destIpAddr",
    "dstip": "destIpAddr", "dest_ip": "destIpAddr", "destipaddr": "destIpAddr",
    "reportingdeviceip": "reptDevIpAddr", "deviceip": "reptDevIpAddr",
    "reptdevipaddr": "reptDevIpAddr",
    "destinationport": "destIpPort", "destport": "destIpPort",
    "port": "destIpPort", "destipport": "destIpPort",
    "user": "user", "username": "user",
    "host": "hostName", "hostname": "hostName",
    # Names models write that FortiSIEM rejects with a bare HTTP 400 (live on
    # 6.1.x, one attribute per query): dstIpAddr, srcHostName, destHostName,
    # srcUserName. The accepted spellings: destIpAddr, srcName/destName (the
    # host-name attributes), srcUser/destUser.
    "dstipaddr": "destIpAddr",
    "srchostname": "srcName", "desthostname": "destName", "dsthostname": "destName",
    "srcname": "srcName", "destname": "destName",
    "srcusername": "srcUser", "destusername": "destUser", "dstusername": "destUser",
    "srcuser": "srcUser", "destuser": "destUser",
}

# An attribute in a raw clause: an identifier OUTSIDE quotes, directly followed
# by a comparison. Values are quoted by convention (`_q`), so they never match.
_CLAUSE_ATTR_RE = re.compile(
    r"\b([A-Za-z_][A-Za-z0-9_]*)(?=\s*(?:!=|>=|<=|=|<|>|\s(?:IN|NOT|CONTAIN|IS|BETWEEN)\b))")


def _canon_attrs(clause: str) -> tuple[str, dict[str, str]]:
    """Map the attribute names in a raw clause through `_WHERE_FIELD_ALIASES`.

    A raw string used to pass through verbatim, so the alias map only helped
    the dict form. Live: 4 of 5 `by=raw` searches in a row 400'd on dstIpAddr /
    srcHostName / srcUserName -- FortiSIEM's error never names the attribute,
    so the model could not self-correct. Returns the clause and {old: new}
    for every rename, so the result can teach the real names."""
    renamed: dict[str, str] = {}

    def fix(m: re.Match) -> str:
        name = m.group(1)
        canon = _WHERE_FIELD_ALIASES.get(name.lower())
        if canon and canon != name:
            renamed[name] = canon
            return canon
        return name

    # Split on double-quoted strings; rewrite only the unquoted segments.
    parts = re.split(r'("(?:[^"\\]|\\.)*")', clause)
    out = "".join(p if i % 2 else _CLAUSE_ATTR_RE.sub(fix, p)
                  for i, p in enumerate(parts))
    return out, renamed


def _where_to_clause(where: Any) -> str:
    """Accept a where clause as a backend-attribute string (passed through) OR a
    ``{field: value}`` dict (the shape a model naturally emits) and return a
    FortiSIEM clause. Dict fields are mapped through ``_WHERE_FIELD_ALIASES``;
    list values become an OR group; multiple fields are AND-ed."""
    if isinstance(where, str):
        return where
    if isinstance(where, dict):
        parts: list[str] = []
        for raw_field, value in where.items():
            field = _WHERE_FIELD_ALIASES.get(str(raw_field).strip().lower(),
                                             str(raw_field).strip())
            if isinstance(value, (list, tuple, set)):
                ors = " OR ".join(f"{field}={_q(v)}" for v in value if v != "")
                if ors:
                    parts.append(f"({ors})")
            elif value != "" and value is not None:
                parts.append(f"{field}={_q(value)}")
        return " AND ".join(parts)
    return str(where or "")


def _siem_pubv2_query(where: str, *, select: str = "", window: str = "2h",
                      limit: int = 25, poll_max: int = 8,
                      op: str, echo: dict[str, Any]) -> dict[str, Any]:
    """Shared pub/v2 event-query engine: submit → poll progress → fetch results.

    The pub/v2 JSON API (`/rest/pub/v2/query/…`) is the ONLY working event-query
    path on FortiSIEM 6.0.0 -- the legacy XML `search_events` op 400s ("Content
    is not allowed in prolog") on this build, so every `siem_search_*` helper
    routes here too. Returns the standard `_envelope` (plus `query_id`) on
    success, or a typed error dict on submit/poll failure.
    """
    import time as _time

    from fsr_playbooks.execution_api import mute_recording, run_op

    from .triage_normalize import _digest_event

    # MCP hands numeric args through as strings; a string `limit`/`poll_max`
    # would crash `min(limit, 1000)` (int vs str) below.
    limit = _as_int(limit, 25)
    poll_max = _as_int(poll_max, 8)

    unit, value = _parse_window(window)
    secs = {"Minutes": 60, "Hours": 3600, "Days": 86400}[unit] * value
    now = int(_time.time())
    payload = {
        "select": select or _SIEM_SELECT,
        "where": where,
        "groupBy": "", "having": "", "orderBy": "phRecvTime DESC",
        "timeRange": {"from": now - secs, "to": now},
        # FortiSOC scope: include all customers, NO exclude (verified live).
        "customerScope": {"groupByEachCustomer": True, "include": {"all": True}},
    }
    # The connector's FortiSIEM base already includes `/phoenix` -- endpoint is
    # relative to that. `execute_api_request` is gated (unknown risk) so this
    # read-only query passes confirm=True. The engine is flaky; retry submit.
    #
    # NB: do NOT send `payload_format` -- the live FortiSIEM connector on the box
    # rejects it ('payload_format' is not a parameter of execute_api_request;
    # the reference store catalogs it but the deployed connector version has only
    # `payload`). That single bad arg failed EVERY first-class SIEM search
    # (siem_search_ip/host/user, siem_raw_query) in loop session loop-7969af87,
    # forcing the agent off its primary pivot path into run_op guessing. A dict
    # `payload` is serialized as JSON by default, so the format hint is moot.
    submit_args = {"endpoint": "/rest/pub/v2/query/eventQuery", "method": "POST",
                   "payload": payload}
    qid = None
    last = None
    for _ in range(3):
        # Mute trace recording: these submit/poll/fetch `execute_api_request`
        # calls implement ONE logical SIEM query -- they must not each land on
        # the session trace as a raw-HTTP playbook step (the grounding gap).
        with mute_recording():
            sub = run_op(_siem_connector(), "execute_api_request", submit_args,
                         confirm=True)
        last = sub
        if isinstance(sub, dict) and sub.get("ok"):
            qid = _coerce_query_id(sub.get("data"))
            if qid:
                break
        _time.sleep(1)
    if not qid:
        accepted = isinstance(last, dict) and last.get("ok")
        if accepted:
            # Submitted OK but no queryId came back -- a SIEM-side quirk, not a
            # caller error; no underlying validator detail to propagate.
            return {"ok": False, "op": op, "query": echo, "code": "no_query_id",
                    "message": "FortiSIEM accepted the query but returned no "
                               "queryId"}
        # The submit itself was rejected (e.g. bad_params on execute_api_request)
        # -- propagate the connector's actionable detail instead of an opaque code.
        return _siem_error(op, echo, last)

    # Poll + fetch on the SAME pub/v2 subsystem we submitted to (the connector's
    # get_events_by_query_id uses the legacy XML get_records path -- wrong id
    # space for a pub/v2 queryId).
    rows: list[dict[str, Any]] = []
    for _ in range(max(1, poll_max)):
        with mute_recording():
            prog = run_op(_siem_connector(), "execute_api_request", {
                "endpoint": "/rest/pub/v2/query/progress", "method": "GET",
                "query_params": {"queryId": qid}}, confirm=True)
        done = (isinstance(prog, dict) and isinstance(prog.get("data"), dict)
                and prog["data"].get("progress") == 100)
        if done:
            with mute_recording():
                res = run_op(_siem_connector(), "execute_api_request", {
                    "endpoint": "/rest/pub/v2/query/events/results", "method": "GET",
                    "query_params": {"queryId": qid, "offset": 0,
                                     "limit": min(limit, 1000)}}, confirm=True)
            if isinstance(res, dict) and res.get("ok"):
                rows = _event_rows(res.get("data"))
            break
        _time.sleep(1)
    events = [d for d in (_digest_event(r) for r in rows) if d]
    out = _envelope(op, echo, events, limit)
    out["query_id"] = qid
    _record_hunt_step(op, echo, out)
    return out


def siem_raw_query(where: str | dict[str, Any], select: str = "",
                   window: str = "2h", limit: int = 25,
                   poll_max: int = 8) -> dict[str, Any]:
    """Run a vetted *native* FortiSIEM event query -- the escape hatch.

    For when the attribute-based `siem_search_*` helpers can't express the
    filter you need. Goes through the connector (`run_op` execute_api_request
    against the pub/v2 query API -- submit, poll progress, fetch results), NOT a
    direct FSM call, and uses FortiSOC scope defaults (include all, NO customer
    exclude). Returns the standard event digest.

    Args:
      where: the filter, either form --
        * a raw FortiSIEM clause string with **backend** attribute names, e.g.
          `srcIpAddr="10.10.100.1" AND destIpPort=443` (find names under
          Admin → Device Support → Event Attributes), or
        * a ``{field: value}`` dict, e.g. `{"sourceIPv4": "1.2.3.4",
          "destPort": 443}` -- friendly field names are mapped to backend
          attributes, list values become an OR group, fields are AND-ed.
        `OR` across src/dst IP fields is fine on the pub/v2 engine.
      select: comma-separated backend field names (defaults to a sane set).
      window: relative lookback ('30m','2h','1d').
      limit: max digested events.
      poll_max: how many times to poll for query completion.
    """
    clause, renamed = _canon_attrs(_where_to_clause(where))
    if select:
        fields = [f.strip() for f in str(select).split(",") if f.strip()]
        canon = [_WHERE_FIELD_ALIASES.get(f.lower(), f) for f in fields]
        renamed.update({f: c for f, c in zip(fields, canon) if f != c})
        select = ",".join(canon)
    echo: dict[str, Any] = {"where": clause, "window": window}
    if renamed:
        echo["renamed_attributes"] = renamed
    return _siem_pubv2_query(clause, select=select, window=window, limit=limit,
                             poll_max=poll_max, op="siem_raw_query", echo=echo)


# `get_associated_events_new` (and get_incidents/get_incident_details) on the
# live FortiSIEM 6.0.0 connector reject anything but this microsecond-Z datetime
# format -- plain ISO 400s with "time data ... does not match format". And the op
# *requires* a timeFrom/timeTo window: omit it and the connector returns a
# MISLEADING "Invalid Incident Id" error (verified live, probe_siem_assoc_events
# -- incident 5 fails id-only, succeeds with a window). So this wrapper always
# supplies a window.
_SIEM_INC_DT = "%Y-%m-%dT%H:%M:%S.%fZ"
# The op caps the timeFrom/timeTo interval at 24h; we scope to the incident's own
# first/last-seen and never widen past this.
_SIEM_INC_MAX_WINDOW_SECS = 24 * 3600
# When we can't query the incident directly and fall back to a `now`-anchored IP
# event search, an old incident's triggering events sit well outside a 1d window.
# Widen progressively until we find events rather than wrongly reporting "none".
# The pub/v2 engine has NO hard window cap (verified live: 7d/30d/90d all return)
# but wide spans complete slowly, so each carries its own poll budget (the
# default 8 polls is why a 90d query appeared to "time out"): 30d≈27s/13 polls,
# 90d≈43s/20 polls live. (Contrast get_associated_events_new, which is a HARD 24h
# cap -- 48h/168h 400 -- hence the ≤24h incident-anchored window above.)
_SIEM_FALLBACK_WINDOWS = (("1d", 8), ("7d", 12), ("30d", 22), ("90d", 32))


def _to_siem_dt(value: Any) -> str:
    """Coerce an epoch (s or ms), ISO-8601 string, or datetime to the
    microsecond-Z format the FortiSIEM connector demands. Returns "" if it
    can't parse (caller then derives a window)."""
    import datetime as _dt

    if value in (None, ""):
        return ""
    if isinstance(value, _dt.datetime):
        d = value if value.tzinfo else value.replace(tzinfo=_dt.timezone.utc)
        return d.astimezone(_dt.timezone.utc).strftime(_SIEM_INC_DT)
    if isinstance(value, (int, float)) or str(value).replace(".", "", 1).isdigit():
        n = float(value)
        if n > 1e12:  # epoch ms
            n /= 1000.0
        return _dt.datetime.fromtimestamp(n, _dt.timezone.utc).strftime(_SIEM_INC_DT)
    s = str(value).strip().replace("Z", "+00:00")
    try:
        d = _dt.datetime.fromisoformat(s)
        d = d if d.tzinfo else d.replace(tzinfo=_dt.timezone.utc)
        return d.astimezone(_dt.timezone.utc).strftime(_SIEM_INC_DT)
    except ValueError:
        return ""


def _resolve_live_incident(incident_id: str,
                           source_ip: str = "") -> dict[str, Any] | None:
    """Find a *live* FortiSIEM incident to query for events.

    Demo/seeded FortiSOAR records carry an `incidentId` that may have aged out of
    the live SIEM (session sess-2avs5bgw passed id 17 -- not on the box; live ids
    were 5,6,10,12,13). This resolves the id the events API will actually accept:

      1. exact match on the requested id, else
      2. (coercion) most-recent live incident for `source_ip`.

    Returns {incident_id, time_from, time_to, source_ip, coerced} or None when no
    live incident is found (caller then falls back to an IP event search)."""
    import datetime as _dt

    from fsr_playbooks.execution_api import run_op

    now = _dt.datetime.now(_dt.timezone.utc)
    wide_from = (now - _dt.timedelta(days=180)).strftime(_SIEM_INC_DT)
    wide_to = now.strftime(_SIEM_INC_DT)
    # Every incident in the window, unfiltered: this is a lookup by id, and
    # the status list it used to send ("Cleared", "Open") is not a valid
    # option on either FortiSIEM connector -- run_op's select validation
    # rejected the call outright, so no window was ever derived and
    # by=incident failed `no_time_window` on every live incident.
    # summarize=False: the default digest keeps ~6 sample rows of the 500, and
    # the one being looked up is rarely among them.
    res = run_op(_siem_connector(), "get_incidents", {
        "timeFrom": wide_from, "timeTo": wide_to, "size": 500,
    }, summarize=False)
    rows = _event_rows(res.get("data")) if isinstance(res, dict) and res.get("ok") else []

    def _win(row: dict[str, Any]) -> tuple[str, str]:
        fs = row.get("incidentFirstSeen") or row.get("incidentLastSeen")
        ls = row.get("incidentLastSeen") or row.get("incidentFirstSeen")
        if not fs:
            return "", ""
        f = float(fs) / 1000.0
        t = float(ls) / 1000.0
        # pad a little and clamp the interval to the op's 24h ceiling
        f -= 60
        t += 60
        if t - f > _SIEM_INC_MAX_WINDOW_SECS:
            f = t - _SIEM_INC_MAX_WINDOW_SECS
        return (_dt.datetime.fromtimestamp(f, _dt.timezone.utc).strftime(_SIEM_INC_DT),
                _dt.datetime.fromtimestamp(t, _dt.timezone.utc).strftime(_SIEM_INC_DT))

    def _src(row: dict[str, Any]) -> str:
        s = row.get("incidentSrc")
        if isinstance(s, dict):
            return s.get("srcIpAddr") or ""
        return ""

    want = str(incident_id)
    for row in rows:
        if isinstance(row, dict) and str(row.get("incidentId")) == want:
            tf, tt = _win(row)
            return {"incident_id": want, "time_from": tf, "time_to": tt,
                    "source_ip": _src(row), "coerced": False}

    if source_ip:
        cand = [r for r in rows if isinstance(r, dict) and _src(r) == source_ip]
        cand.sort(key=lambda r: r.get("incidentLastSeen") or 0, reverse=True)
        if cand:
            row = cand[0]
            tf, tt = _win(row)
            return {"incident_id": str(row.get("incidentId")), "time_from": tf,
                    "time_to": tt, "source_ip": source_ip, "coerced": True}
    return None


def _ip_fallback_search(source_ip: str, incident_id: str,
                        limit: int) -> dict[str, Any]:
    """`now`-anchored pub/v2 event search on an IP, widening the lookback until
    events turn up (1d → 7d → 30d → 90d). Used when we can't query the incident's
    triggering events directly (stale id / no live incident): an old incident's
    events sit far outside a 1d window, so a single fixed window would wrongly
    report "no events". Each step gets a larger poll budget so wide spans finish
    instead of timing out. Stops at the first window that returns events."""
    where = f"(srcIpAddr={_q(source_ip)} OR destIpAddr={_q(source_ip)})"
    last: dict[str, Any] = {}
    for window, poll_max in _SIEM_FALLBACK_WINDOWS:
        out = _siem_pubv2_query(
            where, window=window, limit=limit, poll_max=poll_max,
            op="siem_events_for_incident",
            echo={"incident_id": incident_id, "source_ip": source_ip,
                  "window": window})
        last = out if isinstance(out, dict) else {}
        if not last.get("ok"):
            break  # a real submit/poll failure -- don't keep hammering
        if last.get("count"):
            last["fallback"] = "siem_search_ip"
            last["note"] = (
                f"incident {incident_id} not directly queryable on the live "
                f"FortiSIEM; returned source-IP ({source_ip}) events from a "
                f"{window} lookback instead.")
            return last
    # nothing found in any window (or a hard failure) -- tag the last envelope
    if last.get("ok"):
        last["fallback"] = "siem_search_ip"
        last["note"] = (
            f"incident {incident_id} not directly queryable, and no events were "
            f"found for source IP {source_ip} within "
            f"{_SIEM_FALLBACK_WINDOWS[-1][0]}.")
    return last


def _mounted_siem_context() -> dict[str, str]:
    """What the record this turn is mounted on says about FortiSIEM:
    {uuid, iri, incident_id, source_ip, source}. ``incident_id`` is its
    ``sourceId`` only when the record came from FortiSIEM and the id is an
    integer; empty otherwise. {} when nothing is mounted or it cannot be read.

    Live, the model passed the mounted incident's own uuid as the FortiSIEM
    incident id and, refused, stopped: it did not know where the real id
    lives. The record carries it, so the tool reads it there."""
    iri = _shared.active_record_iri()
    client = _shared._live_client() if iri else None
    if not iri or client is None:
        return {}
    try:
        r = _get_with_reauth(client, f"{client.base_url}{iri}")
        rec = r.json() if getattr(r, "status_code", None) == 200 else None
    except Exception:  # noqa: BLE001 -- an unreadable record resolves nothing
        rec = None
    if not isinstance(rec, dict):
        return {}
    source = str(rec.get("source") or "")
    sid = str(rec.get("sourceId") or "").strip()
    return {"uuid": str(rec.get("uuid") or iri.rstrip("/").rsplit("/", 1)[-1]),
            "iri": iri, "source": source,
            "incident_id": sid if sid.isdigit() and "siem" in source.lower() else "",
            "source_ip": str(rec.get("sourceIp") or rec.get("sourceIP") or "").strip()}


def siem_events_for_incident(incident_id: str, time_from: str = "",
                             time_to: str = "", limit: int = 25,
                             source_ip: str = "") -> dict[str, Any]:
    """Pull the raw FortiSIEM events that drove a specific incident.

    Wraps `get_associated_events_new` (incident triggeringEvents API) and
    returns the standard event digest. This is the canonical "pivot back into
    the originating SIEM" call when an alert came from FortiSIEM.

    Self-healing (so a stale/seeded id or a missing window no longer dead-ends --
    the failure mode in session sess-2avs5bgw):
      * The op *requires* a time window and a microsecond-Z datetime format. When
        you don't pass one, this resolves the incident's own first/last-seen
        window (≤24h) from `get_incidents` automatically.
      * If the requested `incident_id` isn't live but `source_ip` is given, it
        coerces to the most-recent live incident for that host.
      * If no live incident exists at all, it falls back to a pub/v2 event search
        on `source_ip`, **widening the lookback** (1d→7d→30d→90d) until events
        turn up, and tags the envelope (`fallback`, `note`) so the caller knows
        it pivoted instead of failing.

    Args:
      incident_id: the FortiSIEM incident id (from the alert's sourcedata /
        record `sourceId`).
      time_from / time_to: optional window. Accepts epoch (s/ms), ISO-8601, or
        the connector's microsecond-Z form; coerced automatically. Omit to let
        the wrapper derive the incident's window.
      limit: max digested events.
      source_ip: the incident's source IP (record `sourceIP`). STRONGLY
        recommended -- enables id-coercion and the IP-search fallback.
    """
    limit = _as_int(limit, 25)  # MCP may pass "25"; min()/slice below need int
    resolved_from = ""
    # FortiSIEM incident ids are integers. Live, the model passed the SOAR
    # record's uuid; FortiSIEM answered with a non-JSON body and the model got
    # "Expecting value: line 1 column 1" -- nothing it could correct from.
    if not str(incident_id).strip().isdigit():
        # The mounted record named by its own uuid or IRI: its sourceId IS the
        # FortiSIEM incident id, so use it and say so in the result.
        ctx = _mounted_siem_context()
        names_mounted = bool(ctx) and str(incident_id).strip() in (ctx["uuid"], ctx["iri"])
        if names_mounted and ctx["incident_id"]:
            resolved_from = str(incident_id).strip()
            incident_id = ctx["incident_id"]
            source_ip = source_ip or ctx["source_ip"]
        else:
            source_ip = source_ip or (ctx["source_ip"] if names_mounted else "")
            if source_ip:
                return _ip_fallback_search(source_ip, str(incident_id), limit)
    if not str(incident_id).strip().isdigit():
        not_siem = (f" The record it names came from {ctx['source'] or 'an unknown source'}, "
                    "not FortiSIEM, so it has no FortiSIEM incident id."
                    if names_mounted else "")
        return {
            "ok": False, "op": "get_associated_events_new",
            "query": {"incident_id": str(incident_id)},
            "code": "not_a_fortisiem_incident_id",
            "message": (f"{incident_id!r} is not a FortiSIEM incident id -- those "
                        "are integers (e.g. 39486). A SOAR record's uuid or IRI "
                        "is not one." + not_siem),
            "suggestions": [
                "Read the alert's `sourceId` (or the incident id in its "
                "sourcedata) and pass that as `value`.",
                "Or search by the record's IP / host with by=\"ip\" / by=\"host\".",
            ],
        }
    tf = _to_siem_dt(time_from)
    tt = _to_siem_dt(time_to)
    resolved_id = str(incident_id)
    coerced = False

    # Need a window for the op to work. If the caller didn't give a usable one,
    # resolve it (and validate / coerce the id) from the live incident list.
    if not (tf and tt):
        info = _resolve_live_incident(str(incident_id), source_ip)
        if info:
            resolved_id = info["incident_id"]
            tf = tf or info["time_from"]
            tt = tt or info["time_to"]
            coerced = info["coerced"]
            source_ip = source_ip or info["source_ip"]
        elif source_ip:
            # No live incident for this id/host -- pivot straight to a widening
            # IP event search.
            return _ip_fallback_search(source_ip, str(incident_id), limit)

    if not (tf and tt) and not source_ip:
        # The mounted record's own incident: its source IP is the fallback the
        # refusal below would ask the model to find.
        ctx = _mounted_siem_context()
        if ctx.get("incident_id") == resolved_id and ctx.get("source_ip"):
            out = _ip_fallback_search(ctx["source_ip"], resolved_id, limit)
            if isinstance(out, dict) and resolved_from:
                out["resolved_from"] = resolved_from
            return out

    echo = {"incident_id": resolved_id, "timeFrom": tf, "timeTo": tt}
    if coerced:
        echo["coerced_from"] = str(incident_id)
    if resolved_from:
        # Loud, not silent: the model sent a SOAR record id and the result
        # says which FortiSIEM incident that record stands for.
        echo["resolved_from"] = resolved_from

    if not (tf and tt):
        # Couldn't establish a window and have no IP to fall back on -- fail with
        # an ACCURATE hint (not the connector's misleading "Invalid Incident Id").
        return {
            "ok": False, "op": "get_associated_events_new", "query": echo,
            "code": "no_time_window",
            "message": (f"FortiSIEM incident {resolved_id} is not among its "
                        "incidents from the last 180 days, so its event window "
                        "can't be derived (the events API needs one). Nothing "
                        "was searched."),
            # Name the exact next call: a stuck turn (sess-jey64wuw) had the
            # parameters listed and still stopped here.
            "suggestions": [
                f"Call siem_search(by=\"incident\", value=\"{resolved_id}\", "
                "source_ip=\"<the alert's source IP>\") -- with an IP it finds "
                "the live incident or falls back to an IP event search.",
                f"Or siem_search(by=\"incident\", value=\"{resolved_id}\", "
                "time_from=..., time_to=...) with a window of 24h or less "
                "around the alert's time.",
            ],
        }

    params: dict[str, Any] = {"incident_id": resolved_id,
                              "perPage": min(limit, 50),
                              "timeFrom": tf, "timeTo": tt}
    out = _siem_run("get_associated_events_new", params, limit, echo)

    # Final self-heal: op still failed (or returned nothing) but we have an IP --
    # pivot to the widening pub/v2 event search rather than dead-ending.
    failed = not out.get("ok")
    if (failed or out.get("count") == 0) and source_ip:
        ip_out = _ip_fallback_search(source_ip, str(incident_id), limit)
        if isinstance(ip_out, dict) and ip_out.get("ok") and ip_out.get("count"):
            return ip_out
    return out


# ---------------------------------------------------------------------------
# First-class FortiAnalyzer search tools
#
# The FAZ analogue of the `siem_*` helpers: ergonomic, read-only wrappers over
# `run_op("fortinet-fortianalyzer", …)`. FAZ is reached synchronously (not
# agent-bound), but its log-search ops take ~20 fiddly params and two distinct
# datetime formats -- exactly the friction these tools remove. Each returns the
# same `{ok, op, query, count, events, truncated}` envelope as the SIEM tools,
# so the agent learns one event shape across both SIEMs.
# ---------------------------------------------------------------------------

# FAZ log-search ops (start_*/bulk) reject anything but this microsecond-Z
# format; get_alerts is happy with plain ISO. We feed both their own.
_FAZ_LOG_TIME = "%Y-%m-%dT%H:%M:%S.%fZ"
_FAZ_ALERT_TIME = "%Y-%m-%dT%H:%M:%S"


def _window_secs(window: str) -> int:
    """'30m'|'2h'|'1d' → seconds (default 2h), reusing the SIEM window grammar."""
    unit, value = _parse_window(window)
    return {"Minutes": 60, "Hours": 3600, "Days": 86400}[unit] * value


def _faz_window(window: str, fmt: str) -> tuple[str, str]:
    """(start, end) UTC strings for a relative lookback, formatted for FAZ."""
    import datetime
    import time as _time

    now = datetime.datetime.fromtimestamp(_time.time(), datetime.timezone.utc)
    start = now - datetime.timedelta(seconds=_window_secs(window))
    return start.strftime(fmt), now.strftime(fmt)


def _faz_rows(data: Any) -> list[dict[str, Any]]:
    """Dig the row list out of a FAZ run_op `data` payload. FAZ nests rows under
    JSON-RPC `result.data` (sometimes `result` is a list of such blocks); run_op
    may also pre-digest big lists into `{samples: [...]}`."""
    def dig(node: Any) -> list[dict[str, Any]]:
        if isinstance(node, list):
            return [r for r in node if isinstance(r, dict)]
        if isinstance(node, dict):
            for key in ("samples", "data"):
                v = node.get(key)
                if isinstance(v, list):
                    return [r for r in v if isinstance(r, dict)]
            res = node.get("result")
            if isinstance(res, dict):
                return dig(res)
            if isinstance(res, list):
                out: list[dict[str, Any]] = []
                for el in res:
                    out.extend(dig(el))
                return out
        return []
    return dig(data)


def _faz_digest_alert(ev: dict[str, Any]) -> dict[str, Any]:
    """Collapse one FAZ alert (get_alerts row) into a compact, model-friendly row."""
    def g(*keys):
        for k in keys:
            if k in ev and not _is_empty(ev[k]):
                return ev[k]
        return None

    row = {
        "ts": g("alerttime", "firstlogtime", "lastlogtime"),
        "alert_id": g("alertid"),
        "subject": g("subject", "alert", "eventtype"),
        "severity": g("severity"),
        "trigger": g("triggername"),
        "devname": g("devname"),
        "devid": g("devid"),
        "logtype": g("logtype"),
        "count": g("logcount", "numofmatch"),
        "tag": g("tag"),
    }
    return {k: v for k, v in row.items() if not _is_empty(v)}


def _faz_digest_log(ev: dict[str, Any]) -> dict[str, Any]:
    """Collapse one FAZ log row (traffic/event/etc) into the shared event shape."""
    def g(*keys):
        for k in keys:
            if k in ev and not _is_empty(ev[k]):
                return ev[k]
        return None

    row = {
        "ts": g("itime", "eventtime", "date"),
        "event_type": g("type", "subtype", "logid"),
        "src": g("srcip"),
        "dst": g("dstip"),
        "dport": g("dstport"),
        "service": g("service", "app"),
        "action": g("action"),
        "bytes_out": g("sentbyte"),
        "bytes_in": g("rcvdbyte"),
        "dst_country": g("dstcountry"),
        "src_host": g("srcname", "hostname", "devname"),
        "user": g("user", "unauthuser", "srcname"),
        "msg": g("msg"),
    }
    return {k: v for k, v in row.items() if not _is_empty(v)}


# `start_and_fetch_bulk_device_logs` takes two SELECT params, and a value
# outside either enum is rejected by the platform with an opaque "called with N
# invalid argument(s)" that names nothing. Live-verified on 8.0.0: across three
# sessions every `faz_search_device_events` call failed this way, and the agent
# could not self-correct from that message -- it abandoned the hunt in two.
#
# `devid` is a device *type bucket*, NOT a hostname. Constraining a search to a
# single device is done in `filter`, via the `devname=` log field.
_FAZ_DEVID_VALUES = (
    "All_FortiGate", "All_FortiMail", "All_FortiWeb", "All_FortiManager",
    "All_Syslog", "All_FortiClient", "All_FortiCache", "All_FortiProxy",
    "All_FortiAnalyzer", "All_FortiSandbox", "All_FortiAuthenticator",
    "All_FortiDDoS",
)
_FAZ_LOGTYPE_VALUES = (
    "Traffic", "Application control", "Attack", "Content", "DLP",
    "Email Filter", "Event", "History", "Virus", "VOIP", "Web Filter",
    "Netscan", "FCT Event", "FCT Traffic", "WAF", "GTP",
)
# Case/spacing drift is the common slip ("event" for "Event"), so fold it
# rather than rejecting -- a caller who means Event should get Event.
_FAZ_LOGTYPE_BY_FOLD = {v.lower().replace(" ", ""): v for v in _FAZ_LOGTYPE_VALUES}
# Common aliases that are not FAZ log types but read like them. FortiGate
# system/VPN records are Event-subtype logs.
_FAZ_LOGTYPE_BY_FOLD.update({"system": "Event", "vpn": "Event"})


def _faz_logtype(value: Any) -> str | None:
    """Canonical FAZ logtype, or None when it isn't one."""
    return _FAZ_LOGTYPE_BY_FOLD.get(str(value or "").lower().replace(" ", ""))


def _faz_devid(value: Any) -> str | None:
    """Canonical FAZ devid bucket, or None when it isn't one.

    Deliberately does NOT map a hostname onto a bucket: which product family a
    name belongs to is not knowable from the string, and guessing silently
    searches the wrong logs -- a worse failure than an honest one, because it
    returns a confident empty result. Callers holding a hostname filter on it.
    """
    fold = str(value or "").lower().replace("-", "").replace("_", "")
    for v in _FAZ_DEVID_VALUES:
        if v.lower().replace("_", "") == fold:
            return v
    return None


def _faz_select_error(op: str, echo: dict[str, Any],
                      bad: list) -> dict[str, Any]:
    """Name the offending select param(s) and their legal values.

    The platform's own rejection says only how MANY arguments were invalid,
    which is unactionable: the agent cannot tell which param to change, so it
    retries the identical call or gives up. Fail here instead -- before
    dispatch, with the parameter named and its enum listed.
    """
    parts = [f"{name}={value!r} is not one of: {', '.join(legal)}"
             for name, value, legal in bad]
    return {
        "ok": False, "op": op, "query": echo, "code": "bad_select_value",
        "message": f"{op} rejected before dispatch -- " + "; ".join(parts),
        "suggestions": [f"set {name} to one of: {', '.join(legal)}"
                        for name, _, legal in bad],
    }


def _faz_run(op: str, params: dict[str, Any], limit: int,
             echo: dict[str, Any], digest) -> dict[str, Any]:
    """Shared body: run a read-only FAZ op, digest its rows, return the uniform
    envelope (same shape as `_siem_run`). `digest` picks alert vs log shaping."""
    from fsr_playbooks.execution_api import run_op  # lazy: avoid import cycle at load

    # All FAZ helpers are read-only by construction; FAZ op categories aren't
    # always warmed in the safety cache, so pass confirm=True to avoid a
    # spurious requires_confirmation halt (mirrors siem_raw_query).
    res = run_op("fortinet-fortianalyzer", op, params, confirm=True)
    if not isinstance(res, dict) or not res.get("ok"):
        return {"ok": False, "op": op, "query": echo,
                "code": (res or {}).get("status") or (res or {}).get("code")
                or "faz_op_failed",
                "message": (res or {}).get("message")
                or "FortiAnalyzer op failed"}
    events = [d for d in (digest(r) for r in _faz_rows(res.get("data"))) if d]
    return _envelope(op, echo, events, limit)


def faz_get_alerts(adom: str = "root", window: str = "24h",
                   alert_filter: str = "", alertid: str = "",
                   limit: int = 25) -> dict[str, Any]:
    """List FortiAnalyzer event alerts for an ADOM over a recent window.

    Wraps `run_op("fortinet-fortianalyzer","get_alerts")` with the ADOM and
    time window pre-filled, returning a compact alert digest
    (ts/alert_id/subject/severity/trigger/devname/count). This is the canonical
    "what is FAZ alerting on right now" call.

    Args:
      adom: FAZ ADOM name (default 'root'). Use `get_adoms` via run_op to list.
      window: relative lookback like '30m', '2h', '24h' (default), '7d'.
      alert_filter: optional native FAZ alert filter (e.g. `severity>=3`).
      alertid: optional comma-separated alert id(s) to fetch exactly.
      limit: max digested alerts to return (default 25).
    """
    start, end = _faz_window(window, _FAZ_ALERT_TIME)
    params: dict[str, Any] = {"adom_name": adom, "start": start, "end": end,
                              "limit": min(limit, 1000)}
    if alert_filter:
        params["filter"] = alert_filter
    if alertid:
        params["alertid"] = alertid
    return _faz_run("get_alerts", params, limit,
                    {"adom": adom, "window": window, "filter": alert_filter,
                     "alertid": alertid}, _faz_digest_alert)


# B3a folded `faz_get_alerts`, `faz_event_summary` and `faz_raw_query` in as the
# `alerts`, `summary` and `raw` axes; they stay registered (not advertised) so
# an old session or a saved playbook that names them still dispatches.
@mcp.tool()
def faz_search(by: Literal["ip", "device", "serial", "summary", "alerts", "raw"],
               value: str = "", direction: str = "any",
               adom: str = "root", window: str = "24h",
               logtype: str = "", devid: str = "All_FortiGate",
               limit: int = 25) -> dict[str, Any]:
    """Search FortiAnalyzer -- ONE tool, `by` picks the axis: `ip` (value = the IP; `direction` src|dst|any), `device` (value = device hostname: its recent logs -- what it sent before going quiet), `serial` (value = device serial), `summary` (value = device name: its recent events rolled up by type/action/level -- the shape of the noise before drilling in), `alerts` (FAZ event alerts for the ADOM; value = optional alert filter), `raw` (value = a native FAZ JSON-RPC body as JSON text, read-only get/exec methods only -- the escape hatch). Log axes return the standard digest (ts/src/dst/dport/action/service/bytes).

    Args:
      by: ``ip``, ``device``, ``serial``, ``summary``, ``alerts``, or ``raw``.
      value: what to search for on that axis (see above).
      direction: (``by=ip`` only) ``src``, ``dst``, or ``any`` (default).
      adom: FAZ ADOM name (default 'root').
      window: relative lookback ('30m','2h','24h' (default),'7d').
      logtype: FAZ log type; default ``Event`` for ``summary``, else ``Traffic``.
      devid: device selector (default 'All_FortiGate').
      limit: max rows to return (default 25).
    """
    by = by.lower().strip()
    if not logtype:
        logtype = "Event" if by == "summary" else "Traffic"
    if by == "alerts":
        return faz_get_alerts(adom=adom, window=window, alert_filter=value,
                              limit=limit)
    if by == "raw":
        data: Any = value
        if isinstance(value, str):
            try:
                data = json.loads(value)
            except ValueError:
                return {"error": "by='raw' needs value = a FAZ JSON-RPC body "
                                 "as JSON text"}
        return faz_raw_query(data=data)
    if by == "summary":
        if not value:
            return {"error": "by='summary' requires value = a device name"}
        from .tools_noc import faz_event_summary
        return faz_event_summary(device=value, window=window, logtype=logtype,
                                 adom=adom, devid=devid, limit=max(limit, 200))
    if by == "ip":
        if direction == "src":
            flt = f"srcip={value}"
        elif direction == "dst":
            flt = f"dstip={value}"
        else:
            flt = f"srcip={value} or dstip={value}"
        start, end = _faz_window(window, _FAZ_LOG_TIME)
        return _faz_run(
            "start_and_fetch_bulk_device_logs",
            {"devid": devid, "adom_name": adom, "logtype": logtype,
             "start": start, "end": end, "filter": flt, "limit": min(limit, 1000),
             "wait_for_search_process_to_complete": True},
            limit, {"by": "ip", "value": value, "direction": direction,
                    "adom": adom, "window": window, "logtype": logtype,
                    "devid": devid}, _faz_digest_log)
    # Imported HERE, not at module scope: tools_noc imports _faz_run /
    # _faz_window / the digests from this module, so a top-level import back
    # would be a cycle. These two axes were NameError until the pre-push ruff
    # gate flagged them (F821) -- the merged tool advertised three axes and
    # only `ip` worked, while the per-axis tools that used to serve `device`
    # and `serial` had just been taken off the model surface.
    from .tools_noc import faz_search_by_serial, faz_search_device_events
    if by == "device":
        return faz_search_device_events(device=value, window=window,
                                         logtype=logtype, adom=adom,
                                         devid=devid, limit=limit)
    if by == "serial":
        return faz_search_by_serial(serial=value, window=window,
                                     logtype=logtype, adom=adom,
                                     devid=devid, limit=limit)
    return {"error": f"unsupported by={by!r}: use 'ip', 'device', 'serial', "
                     f"'summary', 'alerts', or 'raw'"}


def faz_search_ip(ip: str, direction: str = "any", adom: str = "root",
                  window: str = "24h", logtype: str = "Traffic",
                  devid: str = "All_FortiGate", limit: int = 25) -> dict[str, Any]:
    """Search FortiAnalyzer device logs for an IP over a recent window -- the
    easy pivot.

    Wraps `start_and_fetch_bulk_device_logs` (start search + wait + fetch in one
    synchronous call) with the IP filter, ADOM, log type and time window
    pre-filled, returning the standard event digest
    (ts/src/dst/dport/action/service/bytes). Prefer this over hand-building a
    bulk-log-search call.

    Args:
      ip: the IPv4 to search for.
      direction: 'src', 'dst', or 'any' (default -- matches either side via a
        FAZ `or` filter).
      adom: FAZ ADOM name (default 'root').
      window: relative lookback ('30m','2h','24h' (default),'7d').
      logtype: FAZ log type (default 'Traffic'; e.g. 'Event','Attack','Web Filter').
      devid: device selector (default 'All_FortiGate'; e.g. 'All_FortiProxy').
      limit: max digested events to return (default 25).
    """
    if direction == "src":
        flt = f"srcip={ip}"
    elif direction == "dst":
        flt = f"dstip={ip}"
    else:
        flt = f"srcip={ip} or dstip={ip}"
    start, end = _faz_window(window, _FAZ_LOG_TIME)
    return _faz_run(
        "start_and_fetch_bulk_device_logs",
        {"devid": devid, "adom_name": adom, "logtype": logtype,
         "start": start, "end": end, "filter": flt, "limit": min(limit, 1000),
         "wait_for_search_process_to_complete": True},
        limit, {"ip": ip, "direction": direction, "adom": adom,
                "window": window, "logtype": logtype, "devid": devid},
        _faz_digest_log)


def faz_raw_query(data: dict[str, Any] | str) -> dict[str, Any]:
    """Run a native FortiAnalyzer JSON-RPC request -- the escape hatch.

    For when the `faz_get_alerts` / `faz_search_ip` helpers can't express what
    you need. Wraps `json_rpc_freeform` ("Execute an API Request"), which takes
    a raw FAZ JSON-RPC body and returns its response. Read-only by intent -- use
    `get`/`exec` log-search methods, not config-changing `set`/`add`/`delete`.

    Args:
      data: the JSON-RPC request body (a dict, or a JSON string), e.g.
        `{"method": "get", "params": [{"url": "/eventmgmt/adom/root/alerts"}]}`.
        Whatever FAZ returns is row-digested when it looks like a list of rows,
        otherwise passed through under `raw`.
    """
    from fsr_playbooks.execution_api import run_op

    if isinstance(data, str):
        import json as _json
        try:
            data = _json.loads(data)
        except ValueError as e:
            return {"ok": False, "op": "faz_raw_query",
                    "code": "bad_json", "message": f"data is not valid JSON: {e}"}
    res = run_op("fortinet-fortianalyzer", "json_rpc_freeform",
                 {"data": data}, confirm=True)
    if not isinstance(res, dict) or not res.get("ok"):
        return {"ok": False, "op": "faz_raw_query", "query": {"data": data},
                "code": (res or {}).get("status") or (res or {}).get("code")
                or "faz_op_failed",
                "message": (res or {}).get("message")
                or "FortiAnalyzer op failed"}
    rows = _faz_rows(res.get("data"))
    # Only digest when the rows actually look like FAZ logs/alerts; arbitrary
    # RPC payloads (device lists, config blocks) pass through untouched.
    _LOG_KEYS = {"srcip", "dstip", "action", "itime", "logid", "alertid",
                 "subject", "triggername", "sentbyte", "rcvdbyte"}
    if rows and any(_LOG_KEYS & set(r) for r in rows[:5]):
        events = [d for d in (_faz_digest_log(r) for r in rows) if d]
        return _envelope("faz_raw_query", {"data": data}, events, 50)
    return {"ok": True, "op": "faz_raw_query", "query": {"data": data},
            "raw": res.get("data")}


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
