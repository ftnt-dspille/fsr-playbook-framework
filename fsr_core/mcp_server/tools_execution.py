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
    _capability_gap_suggestion,
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


# Live op-definition cache. The per-connector detail POST that enumerates a
# connector's operations + their params is heavy, and op definitions change
# only on a connector UPGRADE — so cache the parsed ops list in sqlite (like
# health, this survives worker restarts and is visible across worker processes,
# which an in-process cache would not be). Keyed by (connector, version) so an
# upgrade naturally misses and re-fetches. Used by the un-synced grounding path
# (`validate_op_grounded`) and pre-warmed for un-synced connectors by
# `populate_op_definitions` — so the first grounding call in a hunt is a cache
# hit instead of a multi-second live fetch repeated every pivot.
_OP_DEFS_TTL_S = 24 * 3600


def _op_defs_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS connector_op_defs (
               connector  TEXT NOT NULL,
               version    TEXT NOT NULL,
               ops_json   TEXT,
               checked_ts REAL,
               PRIMARY KEY (connector, version)
           )"""
    )


def _cached_op_defs(connector: str,
                    version: str) -> list[dict[str, Any]] | None:
    """Cached live op list for (connector, version) within TTL, else None."""
    import time
    try:
        with sqlite3.connect(DB_PATH) as conn:
            _op_defs_table(conn)
            row = conn.execute(
                "SELECT ops_json, checked_ts FROM connector_op_defs "
                "WHERE connector=? AND version=?",
                (connector, version or ""),
            ).fetchone()
    except Exception:  # noqa: BLE001
        return None
    if not row or row[1] is None:
        return None
    if (time.time() - row[1]) > _OP_DEFS_TTL_S:
        return None
    try:
        ops = json.loads(row[0]) if row[0] else []
    except (ValueError, TypeError):
        return None
    return ops if isinstance(ops, list) else None


def _store_op_defs(connector: str, version: str,
                   ops: list[dict[str, Any]]) -> None:
    import time
    try:
        with sqlite3.connect(DB_PATH) as conn:
            _op_defs_table(conn)
            conn.execute(
                "INSERT OR REPLACE INTO connector_op_defs "
                "(connector, version, ops_json, checked_ts) VALUES (?,?,?,?)",
                (connector, version or "", json.dumps(ops), time.time()),
            )
    except Exception:  # noqa: BLE001
        pass


_CONFIGURED_CACHE: dict[str, Any] = {"ts": 0.0, "rows": None}
_CONFIGURED_TTL_S = 120.0


def _agent_configured_rows(client) -> list[dict[str, Any]]:
    """Return configured connector rows from agent-proxied installs.

    Agent-proxied connectors show config_count=0 in connector_details?configured=true
    and are invisible to preflight. Fix: list active agents via GET /api/3/agents,
    then POST connector_details?agent={id}&active=true&exclude=operation per agent —
    this returns real config_count. Only include rows with config_count > 0 and
    status=Completed (installed-but-unconfigured agent connectors have config_count=0)."""
    try:
        ra = client.session.get(
            client.base_url + "/api/3/agents",
            verify=client.verify_ssl,
        )
        if ra.status_code != 200:
            return []
        members = ra.json().get("hydra:member") or []
        agent_ids = [m["agentId"] for m in members
                     if m.get("active") and m.get("agentId")]
    except Exception:  # noqa: BLE001
        return []

    result = []
    for agent_id in agent_ids:
        try:
            r = client.session.post(
                client.base_url
                + f"/api/integration/connector_details/?format=json"
                f"&agent={agent_id}&active=true&exclude=operation",
                json={}, verify=client.verify_ssl,
            )
            if r.status_code != 200:
                continue
            for row in (r.json().get("data") or []):
                if (row.get("config_count", 0) > 0
                        and row.get("status") == "Completed"):
                    row["_agent_id"] = agent_id
                    result.append(row)
        except Exception:  # noqa: BLE001
            continue
    return result


def _configured_rows(client, force: bool = False) -> list[dict[str, Any]]:
    """Active, configured connectors on the live instance (by name+version).

    Cached in-process for a short TTL: preflight calls this on every `run_op`,
    and on a busy box the `connector_details` POST is non-trivial — re-fetching
    it per op during a multi-pivot hunt is pure overhead. The set rarely
    changes within a session; a 2-minute TTL keeps it fresh enough.

    Also merges agent-proxied connectors (missed by the configured=true filter).
    """
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
    rows = list(r.json().get("data") or [])
    already = {x.get("name") for x in rows}
    rows += [x for x in _agent_configured_rows(client) if x.get("name") not in already]
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


def _healthcheck_via_agents(client, connector: str,
                             version: str,
                             agent_id: str = "",
                             config: str = "") -> dict[str, Any]:
    """Return the real health status for an agent-proxied connector.

    Two paths:
    1. When `agent_id` is known: POST /api/integration/connectors/{name}/{version}/
       ?agent={agent_id} — returns the connector detail with configuration[].health_status.
       When `config` is also supplied, returns that specific config's health_status;
       otherwise aggregates (any Available wins).
    2. Fallback: POST /api/integration/connectors/agents/{name}/{version}/ — lists agent
       install rows and reads remote_status. Works when agent_id is unknown.

    Fails open on any error so a probe gap never silently drops a valid connector."""
    if agent_id:
        try:
            url = (client.base_url
                   + f"/api/integration/connectors/{connector}/{version}/"
                   f"?format=json&agent={agent_id}")
            r = client.session.post(url, json={}, verify=client.verify_ssl, timeout=10)
            if getattr(r, "status_code", 200) == 200:
                detail = r.json() if isinstance(r.json(), dict) else {}
                configs = detail.get("configuration") or []
                if config:
                    # Return the specific config's health_status (not an aggregate).
                    for cfg in configs:
                        if cfg.get("config_id") == config:
                            hs = cfg.get("health_status") or {}
                            st = hs.get("status")
                            if st:
                                return {"status": st, "message": hs.get("message", ""),
                                        "_via_agent_detail": True}
                # No specific config or config not found → aggregate across all.
                statuses = []
                for cfg in configs:
                    st = (cfg.get("health_status") or {}).get("status")
                    if st:
                        statuses.append(st)
                if statuses:
                    agg = next((s for s in statuses if _is_healthy_status(s)),
                               statuses[0])
                    return {"status": agg, "_via_agent_detail": True}
        except Exception:  # noqa: BLE001
            pass
    # Fallback: /connectors/agents/ endpoint (no agent_id needed)
    try:
        url = (client.base_url
               + f"/api/integration/connectors/agents/{connector}/{version}/"
               "?format=json&active=true")
        r = client.session.post(url, json={}, verify=client.verify_ssl, timeout=10)
        rows = r.json() if getattr(r, "status_code", 200) == 200 else []
        if not isinstance(rows, list):
            rows = []
        for row in rows:
            rs = (row.get("remote_status") or {}).get("status", "")
            if (row.get("status") == "Completed"
                    and rs in ("finished", "success", "")):
                return {"status": "Available", "_via_agents": True}
        if rows:
            return {"status": "Disconnected", "_via_agents": True}
    except Exception:  # noqa: BLE001
        pass
    return {"status": "Available", "_agents_unreachable": True}


def _live_healthcheck(client, connector: str, version: str,
                      config: str = "", agent_id: str = "") -> dict[str, Any]:
    """One live healthcheck call.

    `config` is an optional config UUID. `agent_id` is the FortiSOAR Agent's
    agentId — when provided we read the cached health from the agent-scoped
    connector detail (the sync healthcheck endpoint dispatches an async job
    when ?agent= is supplied, not a usable synchronous result).
    """
    # Agent-proxied connectors: the ?agent= param on the healthcheck URL
    # triggers an async job (remote_status: in-progress), not a sync result.
    # Read the last-known health from the agent-scoped connector detail instead.
    if agent_id:
        return _healthcheck_via_agents(client, connector, version,
                                       agent_id=agent_id, config=config)
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
            data = {}
            try:
                data = r.json()
            except Exception:  # noqa: BLE001
                pass
        else:
            data = r.json()
    except Exception as exc:  # noqa: BLE001
        # On-box crudhub raises on non-2xx; extract the JSON body from the
        # exception message if present so we can inspect the status field.
        msg = str(exc)
        data = {}
        try:
            # crudhub embeds the response JSON in the exception string after "::"
            import re as _re
            m = _re.search(r"\{.*\}", msg, _re.DOTALL)
            if m:
                data = json.loads(m.group())
        except Exception:  # noqa: BLE001
            pass
        if not data:
            return {"status": "error", "message": f"healthcheck request failed: {exc!r}"}

    # When the healthcheck signals it couldn't find a local config (agent-
    # proxied connector) or returns an async response, fall back to the agents
    # endpoint for the real per-agent status.
    _needs_agent_fallback = (
        (not data.get("status") and data.get("remote_status"))
        or (data.get("status") == "Disconnected"
            and "configuration" in (data.get("message") or "").lower())
    )
    if _needs_agent_fallback:
        return _healthcheck_via_agents(client, connector, version)
    return data


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
        agent_id = row.get("_agent_id") or ""
        config_ids = _row_config_ids(row)
        verdicts: list[str] = []
        # Per-config healthchecks (when we can see individual config UUIDs).
        for cid in config_ids:
            hc = _live_healthcheck(client, name, version, cid, agent_id=agent_id)
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
            hc = _live_healthcheck(client, name, version, agent_id=agent_id)
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


def populate_op_definitions(client, time_budget_s: float = 60.0,
                            force: bool = False) -> dict[str, Any]:
    """Pre-warm the live op-definition cache (operations + their parameters)
    for the box's configured connectors, so the agent works off real,
    instance-accurate op signatures at cache speed.

    The per-connector detail POST returns each operation WITH its parameter
    list, so one fetch captures operations + operation-params together. We warm
    **un-synced connectors first** — those absent from the bundled catalog
    (`store_ops_count == 0`, e.g. the sess-uq31go5p virustotal case) have no
    offline fallback, so the grounding path would otherwise do a multi-second
    live fetch on every pivot. Remaining budget then warms synced connectors
    too (the bundle can lag the live box), newest-need first.

    Bounded by `time_budget_s` (background pass — never blocks warmup);
    connectors with a fresh cache are skipped unless `force`. Anything not
    reached is filled lazily by `validate_op_grounded` on first use.
    Best-effort: returns a summary, never raises."""
    import time
    start = time.time()
    try:
        rows = _configured_rows(client)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"configured list failed: {exc!r}"}

    def _store_ops_count(name: str) -> int:
        try:
            with _db() as conn:
                return conn.execute(
                    "SELECT COUNT(*) FROM operations WHERE connector_name=?",
                    (name,),
                ).fetchone()[0]
        except sqlite3.Error:
            return 0

    # Un-synced connectors first: they have no offline grounding fallback.
    named = [r for r in rows if r.get("name")]
    named.sort(key=lambda r: _store_ops_count(r["name"]) != 0)

    warmed = skipped = fresh = budget_skipped = 0
    for row in named:
        name = row["name"]
        version = row.get("version") or ""
        if not force and _cached_op_defs(name, version) is not None:
            fresh += 1
            continue
        if (time.time() - start) > time_budget_s:
            budget_skipped += 1
            continue
        try:
            ops = _live_ops_for(client, name, force=True)
            if ops:
                warmed += 1
            else:
                skipped += 1
        except Exception:  # noqa: BLE001 — best-effort; grounding backfills
            skipped += 1
    return {"ok": True, "warmed": warmed, "empty_or_failed": skipped,
            "fresh_cached": fresh, "budget_skipped": budget_skipped,
            "elapsed_s": round(time.time() - start, 1)}


def _resolve_config_id(rows: list[dict[str, Any]], connector: str,
                       config_name: str) -> str:
    """Map a run_op `config` name/id to its UUID using configured rows.

    When `config_name` is empty, prefer the connector's default configuration
    and fall back to the sole configuration. This matters for agent-proxied
    connectors: the platform often has no local default, so execute must send
    the agent configuration UUID explicitly.
    """
    for row in rows:
        if row.get("name") != connector:
            continue
        for key in ("configs", "configurations", "config", "configuration"):
            configs = row.get(key) or []
            if config_name:
                for c in configs:
                    if isinstance(c, str) and c == config_name:
                        return c
                    if not isinstance(c, dict):
                        continue
                    cid = c.get("config_id") or c.get("id") or c.get("uuid")
                    if config_name in (c.get("name"), cid):
                        if cid:
                            return str(cid)
                continue
            for c in configs:
                if isinstance(c, dict) and c.get("default"):
                    cid = c.get("config_id") or c.get("id") or c.get("uuid")
                    if cid:
                        return str(cid)
            if len(configs) == 1:
                c = configs[0]
                if isinstance(c, str):
                    return c
                if isinstance(c, dict):
                    cid = c.get("config_id") or c.get("id") or c.get("uuid")
                    if cid:
                        return str(cid)
    return ""


def _live_ops_for(client, connector: str,
                  force: bool = False) -> list[dict[str, Any]]:
    """Live operation objects for a connector — cache-first.

    Reads the sqlite op-def cache (`connector_op_defs`, keyed by version), and
    only on a miss does the heavy per-connector detail POST (then caches it).
    The list endpoint omits operations, so the detail POST is the only way to
    enumerate them (same path the catalogue sync uses). Returns `[]` on any
    hiccup so callers fail open. `force=True` bypasses the cache (used by the
    warmup pass)."""
    rows = _configured_rows(client)
    row = next((r for r in rows if r.get("name") == connector), None)
    if not row:
        return []
    version = row.get("version") or ""
    if not force:
        cached = _cached_op_defs(connector, version)
        if cached is not None:
            return cached
    cid = row.get("id") or row.get("uuid")
    if not cid:
        return []
    detail = client.post(f"/api/integration/connectors/{cid}/", {}) or {}
    ops = detail.get("operations") or []
    if not isinstance(ops, list):
        ops = []
    _store_op_defs(connector, version, ops)
    return ops


def _fetch_live_op(client, connector: str,
                   op: str) -> tuple[dict[str, Any] | None, list[str]]:
    """Return `(op_def, op_names)` from the LIVE connector definition.

    `op_def` is the matching operation object (with its `parameters` list) or
    None; `op_names` is every op name on the connector. Backed by the cached
    `_live_ops_for`, so repeat grounding calls in a hunt don't re-fetch. One
    lookup shared by op-existence AND param grounding. Returns `(None, [])` on
    any hiccup so callers fail open."""
    ops = _live_ops_for(client, connector)
    op_names = [(o.get("operation") or o.get("name")) for o in ops]
    op_names = [n for n in op_names if n]
    op_def = next(
        (o for o in ops if (o.get("operation") or o.get("name")) == op), None)
    return op_def, op_names


def _op_not_in_live(connector: str, op: str,
                    op_names: list[str]) -> dict[str, Any] | None:
    """`unknown_operation` envelope when `op` isn't in a non-empty live op list,
    else None (an empty list can't prove non-existence)."""
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


def _validate_op_live(client, connector: str, op: str) -> dict[str, Any] | None:
    """Confirm `op` exists on the LIVE connector definition.

    Used as the fallback when the offline reference store has no ops
    catalogued for `connector` (so `_validate_op_exists` couldn't decide).

    Returns an `unknown_operation` error (with near-matches) when the live
    op list is non-empty and `op` isn't in it; None otherwise — including on
    ANY lookup failure, so a transient hiccup never false-rejects a real op
    (the execute call still reports genuine errors).
    """
    try:
        _op_def, op_names = _fetch_live_op(client, connector, op)
    except Exception:  # noqa: BLE001
        return None
    return _op_not_in_live(connector, op, op_names)


def _validate_op_params_live(op_def: dict[str, Any] | None, connector: str,
                             op: str,
                             params: dict[str, Any] | None) -> dict[str, Any] | None:
    """Validate `params` against a LIVE op definition's parameter list.

    The offline-store analog (`_shared._validate_op_params`) no-ops when the op
    has no params catalogued — exactly the un-synced case that lets the agent
    burn turns guessing param names live (`ip`→`ip_address`→`indicator`, the
    `invest_excessive_mail_egress` flail). This closes that gap: unknown-param
    (typo detector) + missing-required, validated against the live connector
    definition. Deliberately loose — select-option membership and type checks
    stay on the offline path; here we only reject names that don't exist and
    required names that are absent. Returns a `bad_params` envelope or None.

    Fails open (None) when the live op has no parameter list (can't prove a
    name is unknown), mirroring `_op_not_in_live`'s empty-list guard. Jinja
    template values are left alone — only top-level membership is judged."""
    params = params or {}
    plist = (op_def or {}).get("parameters") or []
    if not isinstance(plist, list) or not plist:
        return None
    known: dict[str, dict[str, Any]] = {}
    for p in plist:
        if not isinstance(p, dict):
            continue
        name = p.get("name") or p.get("title")
        if name:
            known[name] = p
    if not known:
        return None

    issues: list[dict[str, Any]] = []
    for key in params:
        if key not in known:
            close = difflib.get_close_matches(key, list(known), n=3, cutoff=0.5)
            issues.append({
                "param": key, "problem": "unknown", "near": close,
                "detail": (f"'{key}' is not a parameter of {connector}/{op}"
                           + (f"; did you mean {close}?" if close else "")),
            })
    for name, p in known.items():
        if not p.get("required"):
            continue
        val = params.get(name)
        if name not in params or val is None or val == "":
            issues.append({
                "param": name, "problem": "missing_required",
                "detail": f"required parameter '{name}' "
                          f"({p.get('title') or name}) is missing",
            })
    if not issues:
        return None
    return _err(
        "bad_params",
        f"operation '{op}' on '{connector}' called with {len(issues)} "
        f"invalid argument(s) (validated against the live connector definition)",
        suggestions=[
            f"Call get_op_schema({connector!r}, {op!r}) to see the exact "
            "parameter names, types, required flags, and select options",
            "Re-issue the call with corrected args (fix the issues below)",
        ],
        connector=connector,
        op=op,
        issues=issues,
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
            # Never dead-end the analyst: if this connector is the only way to
            # do what they need (no equivalent configured alternative), forward
            # this into emit_capability_gap_card. During a wide enrichment
            # fan-out, prefer skip-and-mention instead (see system prompt).
            suggested_card=_capability_gap_suggestion(
                id=f"capgap_cfg_{connector}",
                missing=f"the '{connector}' connector",
                why=(f"'{connector}' has no active configuration on this "
                     f"instance, so its operations can't run"),
                fix_steps=[
                    f"Add and activate a configuration for '{connector}' "
                    f"under Settings → Connectors.",
                    "Save it and confirm it shows as Available.",
                ],
                resume_value="recheck_connector",
                tips=[
                    {"text": f"Keep '{connector}' configured so I can use it "
                             f"without an approval round-trip next time."},
                ],
                alternatives=[
                    {"label": "Skip this & note the gap", "value": "skip_gap"},
                ],
            ),
        )
    version = cands[0].get("version") or ""
    agent_id = cands[0].get("_agent_id") or ""
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
        hc = _live_healthcheck(client, connector, version, config_id,
                               agent_id=agent_id)
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
            suggested_card=_capability_gap_suggestion(
                id=f"capgap_health_{connector}",
                missing=f"a healthy '{connector}' connector",
                why=(f"'{connector}' is configured but its healthcheck is "
                     f"failing (status {health.get('status')!r})"
                     + (f": {health.get('message')}" if health.get('message')
                        else "")),
                fix_steps=[
                    f"Open the '{connector}' configuration and check "
                    f"credentials, host, and network reachability.",
                    "Re-run its health check until it returns Available.",
                ],
                resume_value="recheck_connector",
                tips=[
                    {"text": "A connector that fails its healthcheck is caught "
                             "here in ~0.5s instead of timing out mid-op — fix "
                             "the config and I'll pick it straight back up."},
                ],
                alternatives=[
                    {"label": "Skip this & note the gap", "value": "skip_gap"},
                ],
            ),
        )
    return None


def _live_client_for_grounding():
    """Resolve a live FSR client for emit-time op grounding, or None when no
    live target is configured / probes are unavailable.

    Isolated so a caller without a client of its own (`emit_action_card`) shares
    `run_op`'s resolution path, and so tests can stub the live half. Never
    raises — any resolution problem yields None (fail open)."""
    try:
        sys.path.insert(0, str(REPO_ROOT / "python"))
        from probes._env import get_client, get_config
    except ImportError:
        return None
    try:
        if not get_config().is_live():
            return None
        return get_client()
    except Exception:  # noqa: BLE001
        return None


def validate_op_grounded(connector: str, op: str,
                         params: dict[str, Any] | None = None,
                         client=None) -> dict[str, Any] | None:
    """Grounding guarantee shared by `run_op` AND `emit_action_card`: a
    hallucinated/typo'd op — or, when `params` is supplied, a call with
    unknown/missing-required arguments — must NEVER reach the analyst (as an
    approval card) or the live box (as an execute). Returns an
    `unknown_operation` / `bad_params` error envelope or None to proceed.

    Two layers, matching the contract's "offline reference store, with a live
    connector-definition fallback":

    1. Offline store (`_validate_op_exists`) — decisive when the connector's
       ops are catalogued. Offline PARAM validation lives in the callers'
       `_shared._validate_op_params`, which is likewise decisive when params
       are catalogued.
    2. Live connector definition — used ONLY when the store has 0 ops for the
       connector (un-synced reference DB). A single detail fetch grounds BOTH
       the op name and (when `params` is given) the argument names, so the
       agent stops discovering param names by trial-and-error live (the
       `invest_excessive_mail_egress` flail / the deferred half of 1.6).
       Requires a configured live client; `run_op` passes its already-
       resolved+preflighted client, `emit_action_card` lets us resolve lazily.

    Fails OPEN (returns None) on any client/preflight/lookup hiccup, so a
    transient problem never false-rejects a real op. This is why the live half
    can be added to the emit path without risking a false reject on a flaky
    network."""
    off_err = _shared._validate_op_exists(connector, op)
    if off_err is not None:
        return off_err
    # Offline returned None: either the op genuinely exists, or the connector
    # has 0 ops catalogued. Only the latter needs the live fallback — avoid a
    # needless round-trip when the offline check was already decisive.
    try:
        with _db() as conn:
            store_ops_count = conn.execute(
                "SELECT COUNT(*) FROM operations WHERE connector_name=?",
                (connector,),
            ).fetchone()[0]
    except sqlite3.Error:
        return None  # store unreadable → fail open
    if store_ops_count != 0:
        return None  # op (and its params) are catalogued → offline is decisive
    # Un-synced connector → validate against the live definition.
    if client is None:
        client = _live_client_for_grounding()
    if client is None:
        return None  # no live target → can't prove non-existence → fail open
    try:
        preflight_err = _preflight_connector(client, connector)
    except Exception:  # noqa: BLE001
        return None
    if preflight_err is not None:
        # Connector itself isn't configured/healthy. We own only op-grounding
        # here, so fail open and let the caller's own preflight / the execute
        # surface the connector problem (run_op preflights separately; emit's
        # card will fail at execute-time preflight, which is the right gate).
        return None
    try:
        op_def, op_names = _fetch_live_op(client, connector, op)
    except Exception:  # noqa: BLE001
        return None
    op_err = _op_not_in_live(connector, op, op_names)
    if op_err is not None:
        return op_err
    if params is not None:
        try:
            return _validate_op_params_live(op_def, connector, op, params)
        except Exception:  # noqa: BLE001
            return None
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


# --- Event/alert list digest (FortiSIEM / FortiAnalyzer hunting) -----------
# A hunt op (search_events, get_associated_events, FAZ get_alerts /
# get_events_for_incident / get_alert_event_logs, run_report, …) returns many
# homogeneous rows, each carrying a raw log blob + dozens of parsed fields.
# Dumping the first 5 raw rows is both lossy and bulky. For triage the agent
# reasons over AGGREGATES — which IPs/users/hosts recur, what volume, what
# time spread — so we collapse a long row list into a digest: count, time
# window, top-N facets with counts, and a few pruned sample rows. Shape-gated
# (>= this many uniform dict rows) so small/structured results pass through
# untouched. The full observed schema is still stored for authoring, and the
# agent can get_event_details / get_record a single row when it needs depth.
_DIGEST_MIN_ROWS = 8
_DIGEST_TOP_N = 8
_DIGEST_SAMPLES = 3
# Raw log / message payloads — never worth echoing into context.
_RAW_BLOB_RE = re.compile(
    r"raw|_raw|rawmsg|rawevent|eventlog|logmessage|payload|rawmessage", re.I)
_TIME_HINT_RE = re.compile(r"time|date|timestamp|recv|epoch|seen", re.I)
# Facet families: indicator category → key-name substrings (matched
# case-insensitively against each row's keys). Covers FortiSIEM
# (srcIpAddr/destIpAddr/user/action/eventType) and FortiAnalyzer
# (srcip/dstip/user/devname/action/subtype) naming alike.
_FACET_FAMILIES: dict[str, tuple[str, ...]] = {
    "src_ip": ("srcipaddr", "srcip", "sourceip", "src_ip", "source_ip"),
    "dst_ip": ("destipaddr", "dstip", "destip", "destinationip", "dst_ip"),
    "user": ("username", "srcuser", "dstuser", "accountname", "user"),
    "host": ("hostname", "devname", "devicename", "computer", "endpoint",
             "host"),
    "action": ("action", "disposition"),
    "event": ("eventtype", "eventname", "event_type", "subtype", "rulename",
              "rule", "signature"),
    "severity": ("severity", "threatlevel", "priority", "level"),
    "dst_port": ("destport", "dstport", "destinationport", "dport"),
}


def _pick_family_keys(keys: list[str]) -> dict[str, str]:
    """Map each facet family to the best-matching key in `keys` (exact
    match preferred over substring), so we tally a consistent column."""
    low = {k: k.lower() for k in keys}
    chosen: dict[str, str] = {}
    for fam, subs in _FACET_FAMILIES.items():
        hit = next((k for k in keys if low[k] in subs), None)  # exact-ish
        if hit is None:
            hit = next((k for k in keys
                        if any(s in low[k] for s in subs)), None)
        if hit is not None:
            chosen[fam] = hit
    return chosen


def _prune_event(rec: dict[str, Any]) -> dict[str, Any]:
    """A single sample row with raw blobs dropped + strings capped."""
    out: dict[str, Any] = {}
    for k, v in rec.items():
        if _RAW_BLOB_RE.search(k) or v in (None, "", [], {}):
            continue
        out[k] = (v[:200] + "…") if isinstance(v, str) and len(v) > 200 else v
    return out


def _digest_record_list(data: Any) -> dict[str, Any] | None:
    """Collapse a long list of homogeneous event/alert rows into an
    aggregate digest. Returns None when `data` isn't a hunt-style row list."""
    if not (isinstance(data, list) and len(data) >= _DIGEST_MIN_ROWS
            and all(isinstance(x, dict) for x in data[:20])):
        return None
    keys = list(data[0].keys())
    fam_keys = _pick_family_keys(keys)
    from collections import Counter
    facets: dict[str, Any] = {}
    for fam, k in fam_keys.items():
        c: Counter = Counter()
        for rec in data:
            v = rec.get(k)
            if v not in (None, "", [], {}):
                c[str(v)[:80]] += 1
        if c:
            facets[fam] = {
                "field": k,
                "distinct": len(c),
                "top": [{"value": val, "count": ct}
                        for val, ct in c.most_common(_DIGEST_TOP_N)],
            }
    window = None
    time_key = next((k for k in keys if _TIME_HINT_RE.search(k)), None)
    if time_key:
        times = [rec.get(time_key) for rec in data if rec.get(time_key)]
        if times:
            window = {"field": time_key,
                      "min": str(min(times))[:40], "max": str(max(times))[:40]}
    return {
        "_digest": "event_list",
        "count": len(data),
        "time_window": window,
        "facets": facets,
        "samples": [_prune_event(r) for r in data[:_DIGEST_SAMPLES]],
        "note": (f"{len(data)} rows aggregated; {_DIGEST_SAMPLES} sample row(s) "
                 "shown. Use get_event_details / get_record for a single row's "
                 "full fields."),
    }


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
    else:
        # Hunt-style row lists (FortiSIEM/FAZ events & alerts, and any op
        # returning many uniform records): collapse to an aggregate digest
        # instead of dumping raw rows. Shape-gated, so small/structured
        # results are untouched.
        digest = _digest_record_list(data)
        if digest is not None:
            return digest, True
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

    # Validate the arguments against the op's parameter schema (required
    # fields, select-option membership, gross type errors) BEFORE we execute,
    # so a malformed call self-corrects up front instead of failing opaquely
    # at execute. No-op when the op has no params catalogued.
    param_err = _shared._validate_op_params(connector, op, params)
    if param_err is not None:
        return param_err

    # Preflight: the connector must be configured + healthy on the live box.
    # A misconfigured/disconnected connector is a user-fixable problem, so we
    # surface it as a structured error instead of firing the op blind.
    client = get_client()
    preflight_err = _preflight_connector(client, connector, config)
    if preflight_err is not None:
        return preflight_err
    try:
        exec_config = (
            _resolve_config_id(_configured_rows(client), connector, config)
            or config
        )
    except Exception:  # noqa: BLE001
        exec_config = config

    # Live op + param fallback. The offline checks above can only catch a
    # phantom op / bad args when the connector's ops are catalogued. When the
    # store has NO ops for it (un-synced reference DB), validate BOTH the op
    # name and the argument names against the LIVE connector definition now
    # that preflight has confirmed it's configured — so a hallucinated op or a
    # guessed param name is caught up front, before the confirm prompt and the
    # execute, instead of the agent discovering the real param names by trial
    # and error live. Shared with `emit_action_card` via validate_op_grounded
    # (pass our already-resolved client). Infra hiccups never block (fail open).
    if store_ops_count == 0:
        live_err = validate_op_grounded(connector, op, params=params,
                                        client=client)
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
        "config": exec_config,
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
