"""MCP tools: Tools Execution"""
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
# Connector preflight (config presence + cached healthcheck)
# ---------------------------------------------------------------------------
# Before executing an op we confirm the connector actually has an active
# configuration AND that its healthcheck passes. A misconfigured / disconnected
# connector is a user-fixable problem, so we surface it as a structured error
# the agent relays back to the user — rather than firing the op blind and
# flailing to a different connector on the generic execution failure.
#
# Healthchecks hit the upstream vendor service, so we cache the result in
# sqlite (survives worker restarts): a healthy verdict is trusted for 4h; an
# unhealthy verdict only for 5 min so a fix the user just made is picked up
# quickly instead of being blocked for hours.
_HEALTH_TTL_HEALTHY_S = 4 * 3600
_HEALTH_TTL_UNHEALTHY_S = 5 * 60
_HEALTHY_STATUSES = {"available", "connected", "ok", "success"}


def _is_healthy_status(status: Any) -> bool:
    return isinstance(status, str) and status.strip().lower() in _HEALTHY_STATUSES


def _health_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS connector_health (
               connector  TEXT NOT NULL,
               version    TEXT NOT NULL,
               config     TEXT NOT NULL DEFAULT '',
               status     TEXT,
               message    TEXT,
               checked_ts REAL,
               PRIMARY KEY (connector, version, config)
           )"""
    )


def _cached_health(connector: str, version: str,
                   config: str = "") -> dict[str, Any] | None:
    """Return the cached health row if still within its TTL, else None.

    `config` is the per-configuration key ("" = the connector's default /
    any-config verdict written by warmup)."""
    import time
    try:
        with sqlite3.connect(DB_PATH) as conn:
            _health_table(conn)
            row = conn.execute(
                "SELECT status, message, checked_ts FROM connector_health "
                "WHERE connector=? AND version=? AND config=?",
                (connector, version, config or ""),
            ).fetchone()
    except Exception:  # noqa: BLE001
        return None
    if not row:
        return None
    status, message, ts = row
    if ts is None:
        return None
    ttl = _HEALTH_TTL_HEALTHY_S if _is_healthy_status(status) else _HEALTH_TTL_UNHEALTHY_S
    if (time.time() - ts) > ttl:
        return None
    return {"status": status, "message": message, "checked_ts": ts}


def _store_health(connector: str, version: str, status: Any, message: str,
                  config: str = "") -> None:
    import time
    try:
        with sqlite3.connect(DB_PATH) as conn:
            _health_table(conn)
            conn.execute(
                "INSERT OR REPLACE INTO connector_health "
                "(connector, version, config, status, message, checked_ts) "
                "VALUES (?,?,?,?,?,?)",
                (connector, version, config or "", status, message, time.time()),
            )
    except Exception:  # noqa: BLE001
        pass


_CONFIGURED_CACHE: dict[str, Any] = {"ts": 0.0, "rows": None}
_CONFIGURED_TTL_S = 120.0


def _configured_rows(client, force: bool = False) -> list[dict[str, Any]]:
    """Active, configured connectors on the live instance (by name+version).

    Cached in-process for a short TTL: preflight calls this on every `run_op`,
    and on a busy box the `connector_details` POST is non-trivial — re-fetching
    it per op during a multi-pivot hunt is pure overhead. The set rarely
    changes within a session; a 2-minute TTL keeps it fresh enough."""
    import time
    if (not force and _CONFIGURED_CACHE["rows"] is not None
            and (time.time() - _CONFIGURED_CACHE["ts"]) < _CONFIGURED_TTL_S):
        return _CONFIGURED_CACHE["rows"]
    r = client.session.post(
        client.base_url
        + "/api/integration/connector_details/?format=json&configured=true&exclude=operation&active=true",
        json={}, verify=client.verify_ssl,
    )
    if getattr(r, "status_code", 200) != 200:
        return _CONFIGURED_CACHE["rows"] or []
    rows = (r.json().get("data") or [])
    _CONFIGURED_CACHE["rows"] = rows
    _CONFIGURED_CACHE["ts"] = time.time()
    return rows


def _row_config_ids(row: dict[str, Any]) -> list[str]:
    """Best-effort extract of individual configuration UUIDs from a
    connector_details row. The shape varies across FSR builds, so probe the
    common keys and accept either bare ids or {id/config_id/...} objects."""
    for key in ("configs", "configurations", "config", "configuration"):
        val = row.get(key)
        if isinstance(val, list) and val:
            ids = []
            for c in val:
                if isinstance(c, str):
                    ids.append(c)
                elif isinstance(c, dict):
                    cid = c.get("config_id") or c.get("id") or c.get("uuid")
                    if cid:
                        ids.append(str(cid))
            if ids:
                return ids
    return []


def _live_healthcheck(client, connector: str, version: str,
                      config: str = "") -> dict[str, Any]:
    """One live healthcheck call. `config` is an optional config UUID."""
    url = f"/api/integration/connectors/healthcheck/{connector}/{version}/"
    if config:
        url += f"?config={config}"
    try:
        # timeout caps a single slow/hung vendor healthcheck (honored by the
        # requests-backed off-box client; the on-box crudhub session ignores
        # the kwarg harmlessly).
        r = client.session.get(client.base_url + url, verify=client.verify_ssl,
                               timeout=8)
        if getattr(r, "status_code", 200) != 200:
            return {"status": "error",
                    "message": f"HTTP {getattr(r, 'status_code', '?')}"}
        return r.json()
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "message": f"healthcheck request failed: {exc!r}"}


def populate_connector_health(client, time_budget_s: float = 60.0,
                              force: bool = False) -> dict[str, Any]:
    """Discover every configured+active connector and cache a healthcheck for
    each of its configs (plus a connector-level '' verdict = healthy if ANY
    config is healthy). Called by warmup so `run_op`'s preflight gets cache
    hits instead of probing the vendor service on the first use of each
    connector.

    Healthchecks hit the upstream vendor service and can be slow, so the pass
    is bounded by `time_budget_s` — once the budget is exhausted we stop and
    leave the rest to be filled lazily by `run_op`'s preflight on first use
    (so warmup never blows the platform's op timeout). Connectors whose cached
    verdict is still within its TTL are SKIPPED unless `force=True`, so repeat
    warmups within a version's lifetime don't re-hammer vendor services.
    Best-effort: returns a summary, never raises."""
    import time
    start = time.time()
    try:
        rows = _configured_rows(client)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"configured list failed: {exc!r}"}

    checked = healthy = 0
    skipped = fresh = 0
    summary: list[dict[str, Any]] = []
    for row in rows:
        name = row.get("name")
        version = row.get("version") or ""
        if not name:
            continue
        # Skip connectors already checked recently (cache still within TTL).
        if not force and _cached_health(name, version) is not None:
            fresh += 1
            continue
        if (time.time() - start) > time_budget_s:
            skipped += 1
            continue
        config_ids = _row_config_ids(row)
        verdicts: list[str] = []
        # Per-config healthchecks (when we can see individual config UUIDs).
        for cid in config_ids:
            hc = _live_healthcheck(client, name, version, cid)
            status = hc.get("status")
            _store_health(name, version, status, hc.get("message") or "", config=cid)
            verdicts.append(status)
            checked += 1
        # Connector-level (default) verdict. When we enumerated configs, the
        # '' key reflects "any config healthy"; otherwise it's a direct probe.
        if config_ids:
            agg = next((v for v in verdicts if _is_healthy_status(v)),
                       verdicts[0] if verdicts else "unknown")
            _store_health(name, version, agg, "aggregate of per-config checks")
        else:
            hc = _live_healthcheck(client, name, version)
            agg = hc.get("status")
            _store_health(name, version, agg, hc.get("message") or "")
            checked += 1
        if _is_healthy_status(agg):
            healthy += 1
        summary.append({"connector": name, "version": version,
                        "configs": len(config_ids), "status": agg})
    return {"ok": True, "checked": checked, "healthy": healthy,
            "unhealthy": len(summary) - healthy, "skipped": skipped,
            "fresh_cached": fresh, "elapsed_s": round(time.time() - start, 1),
            "connectors": summary}


def _resolve_config_id(rows: list[dict[str, Any]], connector: str,
                       config_name: str) -> str:
    """Map a run_op `config` NAME to its UUID using the configured rows; "" if
    not resolvable (preflight then checks the connector-level verdict)."""
    if not config_name:
        return ""
    for row in rows:
        if row.get("name") != connector:
            continue
        for key in ("configs", "configurations", "config", "configuration"):
            for c in (row.get(key) or []):
                if isinstance(c, dict) and c.get("name") == config_name:
                    cid = c.get("config_id") or c.get("id") or c.get("uuid")
                    if cid:
                        return str(cid)
    return ""


def _validate_op_live(client, connector: str, op: str) -> dict[str, Any] | None:
    """Confirm `op` exists on the LIVE connector definition.

    Used as the fallback when the offline reference store has no ops
    catalogued for `connector` (so `_validate_op_exists` couldn't decide).
    The list endpoint omits operations; the per-connector detail POST is the
    only way to enumerate them (same path the catalogue sync uses).

    Returns an `unknown_operation` error (with near-matches) when the live
    op list is non-empty and `op` isn't in it; None otherwise — including on
    ANY lookup failure, so a transient hiccup never false-rejects a real op
    (the execute call still reports genuine errors).
    """
    try:
        rows = _configured_rows(client)
        row = next((r for r in rows if r.get("name") == connector), None)
        cid = row and (row.get("id") or row.get("uuid"))
        if not cid:
            return None
        detail = client.post(f"/api/integration/connectors/{cid}/", {}) or {}
        op_names = [
            (o.get("operation") or o.get("name"))
            for o in (detail.get("operations") or [])
        ]
        op_names = [n for n in op_names if n]
    except Exception:  # noqa: BLE001
        return None
    if not op_names or op in op_names:
        return None
    close = difflib.get_close_matches(op, op_names, n=5, cutoff=0.4)
    suggestions = [
        f"Use find_operation(connector={connector!r}) to list the real ops",
        "Then get_op_schema(connector, op) before run_op/emit_action_card",
    ]
    if close:
        suggestions.insert(0, f"Did you mean one of: {close}?")
    return _err(
        "unknown_operation",
        f"operation '{op}' not found on live connector '{connector}' "
        f"({len(op_names)} ops available)",
        suggestions=suggestions,
        connector=connector,
        op=op,
        near=close,
    )


def _preflight_connector(client, connector: str,
                         config_name: str = "") -> dict[str, Any] | None:
    """Return a structured error dict if `connector` is not configured or not
    healthy on the live instance; None when it's good to run.

    Infrastructure hiccups (the preflight calls themselves failing) do NOT
    block — we let the actual execute surface those so we never false-negative
    a working connector on a transient lookup error.
    """
    try:
        rows = _configured_rows(client)
    except Exception:  # noqa: BLE001
        return None  # can't preflight → don't block; execute will report real errors
    cands = [x for x in rows if x.get("name") == connector]
    if not cands:
        return _err(
            "connector_not_configured",
            f"'{connector}' has no active configuration on this FortiSOAR "
            "instance, so its operations can't run.",
            suggestions=[
                f"Add and activate a configuration for '{connector}' under "
                "Settings → Connectors, then retry.",
                "Use `list_configured_connectors` to see what IS configured "
                "and pick an available alternative.",
            ],
            connector=connector,
        )
    version = cands[0].get("version") or ""
    config_id = _resolve_config_id(rows, connector, config_name)

    # Healthcheck the connector BEFORE running an op. This is cheap — the
    # healthcheck endpoint returns in ~0.5s (it's the connector's *ops* that
    # are slow when the upstream is down, not the healthcheck) — and it's the
    # whole point of the gate: a Disconnected connector (e.g. FortiSIEM whose
    # SIEM is unreachable) is caught here in half a second instead of the agent
    # burning minutes on op timeouts. Result is cached (4h healthy / 5min
    # unhealthy) and pre-warmed by warmup's background pass, so repeat calls in
    # a hunt are free; an 8s per-call timeout caps a pathologically slow check.
    health = _cached_health(connector, version, config_id)
    if health is None:
        hc = _live_healthcheck(client, connector, version, config_id)
        status = hc.get("status")
        message = hc.get("message") or hc.get("error") or ""
        _store_health(connector, version, status, message, config=config_id)
        health = {"status": status, "message": message}

    if not _is_healthy_status(health.get("status")):
        return _err(
            "connector_unhealthy",
            f"'{connector}' is configured but its healthcheck is failing "
            f"(status: {health.get('status')!r}). {health.get('message') or ''}".strip(),
            suggestions=[
                f"Check the '{connector}' connector configuration "
                "(credentials, host, network reachability) and re-run its "
                "health check, then retry.",
            ],
            connector=connector,
            version=version,
            health_status=health.get("status"),
        )
    return None


# ---------------------------------------------------------------------------
# Output summarization — keep enrichment blobs out of the LLM context
# ---------------------------------------------------------------------------
# Per-connector field whitelists. We prune to the fields that actually drive a
# verdict (and that the widget's ioc_card reads); everything else (per-engine
# results, whois, certificate chains, raw histograms) is dropped before the
# tool_result goes back into context.
_VT_ATTR_KEEP = {"last_analysis_stats", "reputation", "tags", "total_votes",
                 "categories", "country", "as_owner", "asn",
                 "last_analysis_date", "network", "regional_internet_registry"}
_SHODAN_KEEP = {"ip", "ip_str", "org", "isp", "asn", "country_name",
                "country_code", "city", "hostnames", "domains", "ports",
                "tags", "os", "last_update", "vulns"}
_ABUSEIPDB_KEEP = {"ipAddress", "abuseConfidenceScore", "countryCode",
                   "totalReports", "numDistinctUsers", "isTor",
                   "isWhitelisted", "usageType", "domain", "isp",
                   "lastReportedAt"}
_SUMMARIZE_MAX_BYTES = 6000


def _prune_known_enrichment(cn: str, data: Any) -> Any | None:
    """Field-whitelist prune for known threat-intel connectors. Preserves the
    original nesting (so downstream extractors keep working). None = not a
    known enricher."""
    if not isinstance(data, dict):
        return None
    if "virustotal" in cn and isinstance(data.get("attributes"), dict):
        kept = {k: data[k] for k in ("id", "type") if k in data}
        kept["attributes"] = {k: v for k, v in data["attributes"].items()
                              if k in _VT_ATTR_KEEP}
        return kept
    if "shodan" in cn and ("ip_str" in data or "ports" in data or "org" in data):
        return {k: v for k, v in data.items() if k in _SHODAN_KEEP}
    if "abuseipdb" in cn:
        inner = data.get("data") if isinstance(data.get("data"), dict) else data
        pruned = {k: v for k, v in inner.items() if k in _ABUSEIPDB_KEEP}
        return {"data": pruned} if "data" in data else pruned
    if "fortiguard" in cn and isinstance(data.get("data"), list):
        # Keep the per-indicator verdict block; drop the big `location`
        # country histogram and anything else at the top level.
        out_recs = []
        for rec in data["data"][:5]:
            if not isinstance(rec, dict):
                continue
            vals = rec.get("values") or {}
            kept_vals = {k: vals[k] for k in
                        ("threatinfo", "geoip", "asn", "ptr", "riskinfo")
                        if k in vals}
            out_recs.append({"ip": rec.get("ip"), "values": kept_vals})
        return {"data": out_recs}
    return None


def _truncate_generic(obj: Any, depth: int = 0) -> Any:
    """Bound an arbitrary payload: cap string length, list length, dict
    breadth, and recursion depth so an unknown op can't flood context."""
    if isinstance(obj, str):
        return obj if len(obj) <= 300 else obj[:300] + "…"
    if isinstance(obj, list):
        head = [_truncate_generic(x, depth + 1) for x in obj[:5]]
        if len(obj) > 5:
            head.append(f"…(+{len(obj) - 5} more items)")
        return head
    if isinstance(obj, dict):
        if depth >= 4:
            return {"…": "(truncated)"}
        return {k: _truncate_generic(v, depth + 1)
                for k, v in list(obj.items())[:40]}
    return obj


def _summarize_op_output(connector: str, op: str,
                         data: Any) -> tuple[Any, bool]:
    """Return (summarized_data, truncated?). Known enrichers are field-pruned;
    anything still over the byte budget is generically truncated."""
    pruned = _prune_known_enrichment(connector.lower(), data)
    truncated = pruned is not None
    if pruned is not None:
        data = pruned
    try:
        size = len(json.dumps(data, default=str))
    except Exception:  # noqa: BLE001
        return data, truncated
    if size <= _SUMMARIZE_MAX_BYTES:
        return data, truncated
    return _truncate_generic(data), True


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
def run_op(
    connector: str,
    op: str,
    params: dict[str, Any] | None = None,
    config: str = "",
    confirm: bool = False,
) -> dict[str, Any]:
    """Execute a single connector operation on the live FSR instance and return
    its real output.

    This is the authoritative way to discover what a step produces when
    info.json has no output_schema or the static schema is incomplete.

    **Guardrails** — operations are classified by their `category` field:
    - `query / investigation / utilities` → **safe**, runs automatically.
    - `remediation / containment / management` → **destructive**, requires
      `confirm=True`.  The tool returns `{requires_confirmation: true}` when
      confirm is omitted so the caller (agent or user) can decide explicitly.
    - Any other / unknown category → also requires `confirm=True`.

    Pass `confirm=True` only after the user has approved the action or you are
    certain it is a read-only probe with no side effects.

    On success:
    - Returns `{ok: true, data: <actual_output>, output_shape: <inferred_type_shape>}`
    - Stores the inferred shape in `output_schema_observed` so `get_op_schema`
      returns it on all future calls without re-running the operation.
    - Records a `live_op_exec / tested_pass` verification row.

    On failure:
    - Returns `{ok: false, status: <str>, message: <str>}` with the FSR error.
    - Records `live_op_exec / tested_fail` so the store tracks the attempt.

    `params` — dict of input parameter values for the operation.
    `config` — optional connector config name (leave empty for the default config).
    `confirm` — set True to execute operations that are not auto-safe.
    """
    sys.path.insert(0, str(REPO_ROOT / "python"))
    try:
        from probes._env import get_client, get_config
    except ImportError:
        return _err("probes_unavailable", "probes module not available")

    cfg = get_config()
    if not cfg.is_live():
        return _err(
            "no_live_fsr",
            "FSR instance not configured",
            suggestions=[
                "Set FSR_BASE_URL and FSR_API_KEY in .env",
                "Run `fsrpb env` to confirm the live target",
            ],
        )

    # Resolve connector version + op category from store
    with _db() as conn:
        conn.row_factory = sqlite3.Row
        crow = conn.execute(
            "SELECT version FROM connectors WHERE name=?", (connector,)
        ).fetchone()
        op_row = conn.execute(
            "SELECT category FROM operations WHERE connector_name=? AND op_name=?",
            (connector, op),
        ).fetchone()
        store_ops_count = conn.execute(
            "SELECT COUNT(*) FROM operations WHERE connector_name=?",
            (connector,),
        ).fetchone()[0]
        near = []
        if crow is None:
            near = [r[0] for r in conn.execute(
                "SELECT name FROM connectors WHERE name LIKE ? LIMIT 5",
                (f"%{connector}%",),
            ).fetchall()]
    if crow is None:
        return _err(
            "unknown_connector",
            f"connector '{connector}' not found in store",
            suggestions=near or [
                "Run `find_connector` to search the catalog",
            ],
            connector=connector,
        )
    version = crow["version"]

    # Reject a hallucinated/typo'd op BEFORE the risk gate, so a bad op name
    # surfaces as an actionable `unknown_operation` (with near-matches) the
    # agent can self-correct against — rather than tripping the unknown-category
    # confirm prompt and then failing opaquely at execute on a phantom op.
    op_err = _shared._validate_op_exists(connector, op)
    if op_err is not None:
        return op_err

    # Preflight: the connector must be configured + healthy on the live box.
    # A misconfigured/disconnected connector is a user-fixable problem, so we
    # surface it as a structured error instead of firing the op blind.
    client = get_client()
    preflight_err = _preflight_connector(client, connector, config)
    if preflight_err is not None:
        return preflight_err

    # Live op-existence fallback. The offline store check above can only catch
    # a phantom op when the connector's ops are catalogued. When the store has
    # NO ops for it (un-synced reference DB), validate against the LIVE
    # connector definition now that preflight has confirmed it's configured —
    # so a hallucinated op is still caught up front, before the confirm prompt
    # and the execute. Infra hiccups never block (we let execute report those).
    if store_ops_count == 0:
        live_err = _validate_op_live(client, connector, op)
        if live_err is not None:
            return live_err

    category = op_row["category"] if op_row else None
    from .tools_discovery import _op_risk
    risk = _op_risk(op, category)
    if risk != "safe" and not confirm:
        return {
            "ok": False,
            "code": "requires_confirmation",
            "requires_confirmation": True,
            "risk": risk,
            "category": category or "unknown",
            "connector": connector,
            "op": op,
            "message": (
                f"Operation '{op}' on '{connector}' has risk level '{risk}' "
                f"(category: {category!r}). Re-call with confirm=True after the "
                "user has approved, or confirm this is a safe read-only probe."
            ),
            "suggestions": [
                f"If you're certain this is safe, retry with confirm=True",
                f"Otherwise ask the user before mutating state on the live FSR",
            ],
        }

    body = {
        "connector": connector,
        "operation": op,
        "version": version,
        "config": config,
        "params": params or {},
    }

    try:
        resp = client.post("/api/integration/execute/", body)
    except Exception as exc:  # noqa: BLE001
        r = getattr(exc, "response", None)
        status = getattr(r, "status_code", "?")
        msg = (r.text if r is not None else str(exc))[:600]
        _record_verification(connector, op, "tested_fail", msg[:2000])
        return _err(
            "transport_failed", msg,
            suggestions=[
                "Check FSR connectivity and `fsrpb health`",
                "Confirm the connector config is configured + active",
            ],
            status=str(status),
        )

    if not isinstance(resp, dict):
        return _err(
            "bad_response_shape",
            f"unexpected response type: {type(resp).__name__}",
        )

    exec_status = resp.get("status", "")
    if exec_status not in ("Success", "success", "Completed", "completed", ""):
        msg = resp.get("message", "") or json.dumps(resp)[:600]
        _record_verification(connector, op, "tested_fail", msg[:2000])
        return _err(
            "execution_failed", msg,
            suggestions=[
                "Inspect `params` against `get_op_schema` required fields",
                "If auth/scope error, verify the connector config on FSR",
            ],
            status=exec_status,
        )

    data = resp.get("data", resp)
    shape = _infer_shape(data)
    # Store the FULL observed schema (accuracy matters for authoring), then
    # return a SUMMARIZED payload to the agent. Enrichment ops (VirusTotal,
    # Shodan, AbuseIPDB, …) can return huge blobs (per-engine analysis,
    # whois, certs) that would flood the LLM context with noise — we prune to
    # the fields that actually drive a verdict, and generically cap anything
    # still oversized. The widget's ioc_card reads this same summarized shape.
    _store_observed_schema(connector, op, data)
    # top_keys reflect the FULL shape so authoring references stay accurate.
    sample = data[0] if isinstance(data, list) and data else data
    top_keys = sorted(sample.keys()) if isinstance(sample, dict) else []
    summarized, truncated = _summarize_op_output(connector, op, data)
    out = {
        "ok": True,
        "data": summarized,
        "output_shape": shape,
        "output_top_keys": top_keys,
        "output_is_list": isinstance(data, list),
        "schema_cached": True,
    }
    if truncated:
        out["output_truncated"] = True
        out["note"] = ("Output summarized to keep context lean — full shape is "
                       "in the reference store via get_op_schema.")
    return out


def _record_verification(connector: str, op: str, status: str, notes: str) -> None:
    import datetime
    ts = datetime.datetime.utcnow().isoformat()
    with sqlite3.connect(_shared.DB_PATH) as conn:
        conn.execute(
            """INSERT OR REPLACE INTO verifications (kind, key, method, status, ts, notes)
               VALUES ('operation', ?, 'live_op_exec', ?, ?, ?)""",
            (f"{connector}:{op}", status, ts, notes),
        )



@mcp.tool()
def push_playbook(yaml_text: str) -> dict[str, Any]:
    """Compile a YAML playbook and push it to the live FSR instance.

    Idempotent: PUT first, POST on 404, hard-purge + POST on 409 (matches
    `fsrpb push --mode replace`). Use after `validate_yaml` returns clean.

    Returns:
        {ok: true, collection_uuid, collection_name, workflows: [{name, uuid}],
         action: "put"|"post"|"purge_post"} on success.
        {ok: false, errors: [...]} on compile failure.
        {ok: false, error: str} on push failure.
    """
    sys.path.insert(0, str(REPO_ROOT / "python"))
    try:
        from fsr_core.compiler import compile_yaml as _compile
        from probes._env import get_client, get_config
        from e2e.runner import _push, _PushError
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"import failed: {e!r}"}
    if not get_config().is_live():
        return {"ok": False, "error": "FSR instance not configured"}
    result = _compile(yaml_text, _shared.DB_PATH)
    if not result.ok:
        return {"ok": False, "errors": [
            {"code": e.code.value, "path": e.path, "message": e.message,
             "suggestion": e.suggestion or ""}
            for e in result.errors
        ]}
    coll = result.fsr_json["data"][0]
    client = get_client()
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        try:
            _push(client, coll, Path(td))
        except _PushError as e:
            return {"ok": False, "error": str(e)}
    return {
        "ok": True,
        "collection_uuid": coll["uuid"],
        "collection_name": coll["name"],
        "workflows": [{"name": w.get("name"), "uuid": w.get("uuid")}
                      for w in coll.get("workflows", [])],
    }

@mcp.tool()
def run_playbook(playbook: str,
                 input: dict[str, Any] | None = None,
                 collection: str | None = None,
                 record: str | None = None,
                 follow: bool = True,
                 timeout_s: int = 180,
                 use_mock_output: bool = False) -> dict[str, Any]:
    """Trigger a deployed playbook and (optionally) poll until terminal.

    Args:
        playbook: workflow name OR uuid OR `Collection:Name` shorthand
        input: trigger params; FSR maps these to `vars.input.params.<k>`
        collection: collection name to disambiguate duplicate workflow names
        record: "<module>:<uuid>" for record-context (cybersponse.action)
            triggers; omit for /notrigger style (designer Run button)
        follow: if True, poll until terminal status (default 180s timeout)
        timeout_s: poll timeout when follow=True
        use_mock_output: honor each step's `arguments.mock_result` instead
            of running live (good for dry-running without external API calls)

    Returns:
        {ok, status, task_id, wf_uuid, wf_pk, error_message?, failed_steps?}.
        `ok` is True only when status == "finished"; "finished_with_error"
        and "failed" return ok=False with diagnostics.
    """
    sys.path.insert(0, str(REPO_ROOT / "python"))
    try:
        from probes._env import get_client, get_config
        from cli import _resolve_workflow_ident
        from e2e.runner import _fetch_trigger_route_uuid
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"import failed: {e!r}"}
    if not get_config().is_live():
        return {"ok": False, "error": "FSR instance not configured"}
    client = get_client()
    wf_uuid = _resolve_workflow_ident(client, playbook, collection)
    if not wf_uuid:
        return {"ok": False, "error": f"no playbook matching {playbook!r}"}

    if record:
        if ":" not in record:
            return {"ok": False, "error": "record must be '<module>:<uuid>'"}
        module, rec_uuid = record.split(":", 1)
        route_uuid = _fetch_trigger_route_uuid(client, wf_uuid)
        if not route_uuid:
            return {"ok": False, "error": (
                "no trigger.route on workflow — playbook is not a "
                "record-action style trigger; omit `record`"
            )}
        path = f"/api/triggers/1/action/{route_uuid}"
        body = {"singleRecordExecution": True, "__resource": module,
                "__uuid": wf_uuid,
                "records": [f"/api/3/{module}/{rec_uuid}"]}
    else:
        path = f"/api/triggers/1/notrigger/{wf_uuid}"
        body = {"input": {}, "request": {"data": input or {}},
                "useMockOutput": bool(use_mock_output), "globalMock": False}

    try:
        r = client.session.post(client.base_url + path, json=body,
                                verify=client.verify_ssl)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"trigger failed: {e!r}"}
    if r.status_code >= 400:
        return {"ok": False, "error": f"HTTP {r.status_code}: {r.text[:300]}"}
    try:
        resp = r.json()
    except Exception:  # noqa: BLE001
        resp = {}
    task_id = resp.get("task_id") if isinstance(resp, dict) else None
    if not follow or not task_id:
        return {"ok": True, "status": "triggered", "task_id": task_id,
                "wf_uuid": wf_uuid}

    import time
    terminal = {"finished", "failed", "terminated", "skipped",
                "finished_with_error", "rejected"}
    poll_url = (client.base_url + "/api/wf/api/workflows/?format=json"
                f"&limit=1&ordering=-modified&task_id={task_id}"
                "&parent_wf__isnull=True")
    start = time.time()
    while time.time() - start < timeout_s:
        try:
            pr = client.session.get(poll_url, verify=client.verify_ssl)
            members = (pr.json() or {}).get("hydra:member") or []
        except Exception:  # noqa: BLE001
            members = []
        if members:
            rec = members[0]
            status = rec.get("status", "unknown")
            if status in terminal:
                wf_pk = (rec.get("@id") or "").rstrip("/").rsplit("/", 1)[-1]
                ok = status == "finished"
                out: dict[str, Any] = {"ok": ok, "status": status,
                                       "task_id": task_id, "wf_uuid": wf_uuid,
                                       "wf_pk": wf_pk}
                if not ok:
                    # Pull the full record for step-level diagnostics.
                    try:
                        fr = client.session.get(
                            client.base_url + "/api" + (rec.get("@id") or ""),
                            verify=client.verify_ssl)
                        full = fr.json() if fr.status_code == 200 else rec
                    except Exception:  # noqa: BLE001
                        full = rec
                    top = full.get("result") or {}
                    out["error_message"] = (
                        (top.get("Error message") if isinstance(top, dict) else None)
                        or full.get("errorMessage") or full.get("error"))
                    failed = []
                    for s in full.get("steps") or []:
                        if s.get("status") in ("failed", "finished_with_error",
                                               "terminated"):
                            res = s.get("result") or {}
                            failed.append({
                                "name": s.get("name"),
                                "status": s.get("status"),
                                "error": (res.get("Error message")
                                          or res.get("error")
                                          or res.get("message")
                                          or json.dumps(res)[:300]
                                          if isinstance(res, dict) else str(res)),
                            })
                    out["failed_steps"] = failed
                return out
        time.sleep(2)
    return {"ok": False, "status": "timeout", "task_id": task_id,
            "wf_uuid": wf_uuid,
            "error_message": f"timeout after {timeout_s}s"}

@mcp.tool()
def dry_run_playbook(yaml_text: str, playbook: str,
                     input: dict[str, Any] | None = None,
                     timeout_s: int = 180,
                     cleanup: bool = True,
                     use_mock_output: bool = False) -> dict[str, Any]:
    """Compile + push + run + auto-cleanup. The agent's full E2E loop in one tool.

    Args:
        yaml_text: full YAML source.
        playbook: workflow name to trigger after push (one playbook in the
            collection — the agent picks which one).
        input: trigger params (mapped to `vars.input.params.<k>`).
        timeout_s: poll timeout (default 180s).
        cleanup: hard-purge the collection after the run (default True).
            Set False to keep the collection on the instance for inspection.
        use_mock_output: run with each step's `arguments.mock_result` instead
            of live external calls.

    Returns:
        {ok, status, task_id, wf_pk, collection_uuid, error_message?,
         failed_steps?, cleaned_up: bool}.
    """
    push = push_playbook(yaml_text)
    if not push.get("ok"):
        return {"ok": False, "stage": "push", **push}
    run = run_playbook(playbook, input=input,
                       collection=push.get("collection_name"),
                       follow=True, timeout_s=timeout_s,
                       use_mock_output=use_mock_output)
    coll_uuid = push["collection_uuid"]
    cleaned = False
    if cleanup:
        try:
            from probes._env import get_client
            from e2e.runner import _hard_purge
            client = get_client()
            # Re-fetch the workflow uuids in case the push reshaped them.
            sys.path.insert(0, str(REPO_ROOT / "python"))
            _hard_purge(client, coll_uuid,
                        {"workflows": [{"uuid": w["uuid"]}
                                       for w in push.get("workflows", [])]})
            cleaned = True
        except Exception:  # noqa: BLE001
            cleaned = False
    return {**run, "stage": "run", "collection_uuid": coll_uuid,
            "cleaned_up": cleaned}

@mcp.tool()
def healthcheck_connector(name: str, version: str | None = None,
                          config: str | None = None) -> dict[str, Any]:
    """Live-check whether a single connector configuration is reachable.

    Use after `list_configured_connectors` to confirm the upstream service
    is actually up before recommending an op to the user.

    Args:
        name: connector name
        version: optional — when omitted, the first configured version is used
        config: optional config UUID — required when the connector has more
            than one configuration and you want a specific one

    Returns:
        {status, message, name, version, config_id}
        status="Available" → green; "Disconnected" → connector configured but
        upstream is down; HTTP 404 → no configuration on this instance.
    """
    try:
        from probes._env import get_client, get_config
    except Exception as e:  # noqa: BLE001
        return {"error": f"could not import _env: {e!r}"}
    cfg = get_config()
    if not cfg.is_live():
        return {"error": "FSR instance not configured (FSR_BASE_URL / FSR_API_KEY missing in .env)"}
    client = get_client()
    if version is None:
        try:
            r = client.session.post(
                client.base_url
                + "/api/integration/connector_details/?format=json&configured=true&exclude=operation&active=true",
                json={}, verify=client.verify_ssl,
            )
            rows = (r.json().get("data") or []) if r.status_code == 200 else []
        except Exception as e:  # noqa: BLE001
            return {"error": f"version lookup failed: {e!r}"}
        cands = [x for x in rows if x.get("name") == name]
        if not cands:
            return {"error": f"no configured connector named {name!r}; pass version explicitly"}
        version = cands[0].get("version")
    url = f"/api/integration/connectors/healthcheck/{name}/{version}/"
    if config:
        url += f"?config={config}"
    try:
        r = client.session.get(client.base_url + url, verify=client.verify_ssl)
    except Exception as e:  # noqa: BLE001
        return {"error": f"healthcheck request failed: {e!r}"}
    if r.status_code == 404:
        return {"name": name, "version": version, "status": "no-config",
                "http_status": 404, "message": "no configuration on this instance"}
    try:
        return r.json()
    except Exception:  # noqa: BLE001
        return {"name": name, "version": version, "http_status": r.status_code,
                "raw": r.text[:500]}


def _fetch_runs_both(client, *, limit: int, extra_qs: str = "") -> list[dict[str, Any]]:
    """Fetch from /workflows/ AND /historical-workflows/, merge by modified desc.

    FSR purges live workflow logs to the historical table every ~30-60 min for
    performance, so any triage tool that only hits /workflows/ goes blind to
    older failures. Historical also returns richer fields (`result`, `steps`,
    `env`) inline. Dedup by `@id` in case a run is in both during the move.
    """
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in ("/api/wf/api/workflows/", "/api/wf/api/historical-workflows/"):
        url = (client.base_url + path
               + f"?format=json&limit={limit}&ordering=-modified"
               + f"&parent_wf__isnull=True{extra_qs}")
        try:
            r = client.session.get(url, verify=client.verify_ssl)
        except Exception:  # noqa: BLE001
            continue
        if r.status_code != 200:
            continue
        for m in (r.json().get("hydra:member") or []):
            iri = m.get("@id") or ""
            if iri and iri in seen:
                continue
            seen.add(iri)
            m["_source"] = "historical" if "historical" in path else "live"
            out.append(m)
    out.sort(key=lambda m: m.get("modified") or "", reverse=True)
    return out


def _shape_run(m: dict) -> dict:
    res = m.get("result") if isinstance(m.get("result"), dict) else {}
    err = ((res.get("Error message") or res.get("error")
            or res.get("message")) if isinstance(res, dict) else None)
    pk_url = m.get("@id") or ""
    pk = pk_url.rstrip("/").rsplit("/", 1)[-1] if pk_url else None
    return {
        "task_id": m.get("task_id"),
        "name": m.get("name"),
        "status": m.get("status"),
        "error_message": err,
        "modified": m.get("modified"),
        "uuid": m.get("uuid"),
        "pk": pk,
        "source": m.get("_source"),  # "live" or "historical"
    }