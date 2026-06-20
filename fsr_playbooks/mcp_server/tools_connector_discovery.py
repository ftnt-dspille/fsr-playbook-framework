"""MCP tools: connector & playbook-run discovery.

Connector-awareness tools shared by BOTH the agentic playbook-creation path and the
SOC triage path. Per RECONCILIATION_PLAN, connector-awareness is NOT triage, so it
stays in the public library (authoring needs to know what connectors are installed /
configured / running and what actions a step can call); only alert/incident
investigation (SIEM/FortiAnalyzer/FortiManager, record reads) lives in the
connector's fsr_soc_triage. Extracted (transitive closure) from the pre-carve tools_triage.
"""
from __future__ import annotations
from . import _shared

import json
import sqlite3
from typing import Any, Union

from ._shared import mcp, _capability_gap_suggestion
from .tools_execution import _fetch_runs_both, _shape_run

DB_PATH = _shared.DB_PATH


DB_PATH = _shared.DB_PATH


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


_CONTAINMENT_VERBS: tuple[str, ...] = (
    "block", "quarantine", "isolate", "disable", "revoke", "ban", "suspend",
    "kill", "terminate", "contain", "deactivate", "shutdown",
)


_NON_ACTION_PREFIXES: tuple[str, ...] = (
    "get_", "list_", "search_", "fetch_", "check_", "describe_", "count_",
    "enable_", "allow_", "unblock", "unquarantine", "unisolate", "unban",
    "unsuspend", "unrevoke", "undisable",
)


_TARGET_KEYWORDS: dict[str, tuple[str, ...]] = {
    "ip": ("ip", "address", "blacklist"),
    "host": ("host", "endpoint", "device", "machine", "asset", "agent", "collector"),
    "endpoint": ("endpoint", "host", "device", "agent", "machine", "collector"),
    "user": ("user", "account", "identity", "credential", "password", "login"),
    "url": ("url", "link", "uri"),
    "domain": ("domain", "fqdn", "dns"),
    "hash": ("hash", "file", "sample", "md5", "sha"),
    "file": ("file", "hash", "sample"),
    "email": ("email", "mail", "message"),
    "process": ("process", "task", "service"),
}


_CONTAINMENT_CATEGORIES = frozenset({"containment", "remediation"})


_INTEL_TOKENS: tuple[str, ...] = (
    "reputation", "ioc", "indicator", "intel", "threat", "enrich", "context",
    "lookup", "geo", "whois", "passive", "detection", "verdict",
)


_INDICATOR_TOKENS: dict[str, tuple[str, ...]] = {
    "ip": ("ip",),
    "host": ("host", "endpoint", "device", "machine", "asset"),
    "endpoint": ("endpoint", "host", "device", "machine", "agent"),
    "user": ("user", "account", "identity", "credential", "login"),
    "url": ("url", "uri"),
    "domain": ("domain", "fqdn", "dns"),
    "hash": ("hash", "md5", "sha", "sample"),
    "file": ("file", "hash", "sample", "md5", "sha"),
    "email": ("email",),
}


_ALL_INDICATOR_TOKENS: frozenset = frozenset(
    t for toks in _INDICATOR_TOKENS.values() for t in toks
)


_ENRICHMENT_EXCLUDE_VERBS: tuple[str, ...] = (
    "re_analyze", "reanalyze", "re_scan", "rescan", "re-scan", "upload",
    "submit", "detonate", "create", "add_", "delete_", "remove_", "update_",
    "set_", "post_", "put_", "scan_", "_scan",
)


_ENRICHMENT_NOISE: frozenset = frozenset({
    "execute_an_api_request", "custom_endpoint",
})


_ENRICHMENT_EXCLUDE_PREFIXES: tuple[str, ...] = (
    "get_output_schema", "get_widget", "get_feed",
)


_ENRICH_CONNECTOR_RANK: tuple[tuple[str, int], ...] = (
    ("virustotal", 0), ("fortiguard", 0), ("fortinet-fortiguard", 0),
    ("shodan", 1), ("ipqualityscore", 1), ("ip_quality", 1), ("ipqs", 1),
    ("greynoise", 1), ("abuseipdb", 1), ("urlscan", 1),
    ("alienvault", 9), ("otx", 9),
)


_ENRICH_RANK_DEFAULT = 5


_ENRICH_PER_CONNECTOR_CAP = 3


def _enrich_connector_rank(connector: str) -> int:
    c = (connector or "").lower()
    for frag, rank in _ENRICH_CONNECTOR_RANK:
        if frag in c:
            return rank
    return _ENRICH_RANK_DEFAULT


def _is_enrichment_op(nm: str, title_l: str, target: str | None) -> bool:
    """Name/title heuristic for "indicator enrichment lookup" ops, pre-tier.

    An op qualifies when it isn't a write-ish/plumbing op AND either carries a
    generic intel token (reputation/ioc/context/...) or names the requested
    indicator. With no target type we require the intel token, so the result
    stays bounded to clearly-intel ops. With a target type we ALSO reject ops
    that name only a *different* indicator — `get_domain_reputation`,
    `get_url_reputation`, `get_file_reputation` while enriching an IP — even
    though they carry an intel token, because they can't take this indicator.
    (`score` was dropped from the intel tokens and `address` from the ip
    tokens, so EPSS scoring and firewall `get_addresses` no longer slip in.)
    """
    if nm in _ENRICHMENT_NOISE or nm.startswith(_ENRICHMENT_EXCLUDE_PREFIXES):
        return False
    if any(v in nm for v in _ENRICHMENT_EXCLUDE_VERBS):
        return False
    hay = nm + " " + title_l
    generic = any(tok in hay for tok in _INTEL_TOKENS)
    if not target:
        return generic
    desired = _INDICATOR_TOKENS.get(target, ())
    names_desired = any(k in hay for k in desired)
    other = _ALL_INDICATOR_TOKENS - set(desired)
    if any(k in hay for k in other) and not names_desired:
        return False  # names only a different indicator — can't take this one
    return generic or names_desired


def _connectors_that_could_enrich(
        target: str | None,
        exclude: set[str],
        limit: int = 4) -> list[dict[str, str]]:
    """Across the WHOLE catalog, connectors carrying an enrichment op matching
    the target — minus the ones already configured. Turns an intel dead end
    into a concrete "configure connector X" recommendation. Best-effort: []."""
    found: dict[str, str] = {}
    try:
        with sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True) as conn:
            rows = conn.execute(
                "SELECT connector_name, op_name, title FROM operations "
                "WHERE (enabled IS NULL OR enabled NOT IN (0,'0'))"
            ).fetchall()
    except sqlite3.Error:
        return []
    for connector, op, title in rows:
        if not connector or connector in exclude or connector in found:
            continue
        if _is_enrichment_op((op or "").lower(), (title or "").lower(), target):
            found[connector] = op or ""
        if len(found) >= limit:
            break
    return [{"connector": c, "op": o} for c, o in found.items()]


def _required_params(conn: sqlite3.Connection, connector: str,
                     op: str) -> list[dict[str, Any]]:
    """The visible required input params for an op, so the agent can stage
    emit_action_card without a follow-up get_op_schema round-trip."""
    try:
        rows = conn.execute(
            "SELECT param_name, type, title FROM operation_params "
            "WHERE connector_name=? AND op_name=? "
            "AND required IN (1,'1','true','True') "
            "AND (visible IS NULL OR visible NOT IN (0,'0','false','False')) "
            "ORDER BY ord",
            (connector, op),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    # Dedupe by name: an op with conditional param groups (parent-gated
    # param-sets, e.g. block_ip_new's ip / ip_group_name) lists the same
    # required param once per group, which would otherwise read as a noisy
    # duplicated schema hint. First occurrence wins (preserves `ord`).
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for r in rows:
        if not r[0] or r[0] in seen:
            continue
        seen.add(r[0])
        out.append({"name": r[0], "type": r[1]})
    return out


def _param_sig(conn: sqlite3.Connection, connector: str,
               op: str) -> list[dict[str, Any]]:
    """Full visible param signature WITH select options + labels — so the agent
    picks valid param NAMES and valid select VALUES straight from the action
    finder, instead of guessing and bouncing off bad_params. Loop loop-998b86c1
    showed both failure modes the store could have prevented: the agent guessed
    `ioc` (the param is `indicator`) and `method='firewall'` (the select options
    were 'Quarantine Based'/'Policy Based'). Dedupes conditional param groups by
    name (first occurrence wins, preserving `ord`)."""
    try:
        rows = conn.execute(
            "SELECT param_name, type, title, required, options_json "
            "FROM operation_params WHERE connector_name=? AND op_name=? "
            "AND (visible IS NULL OR visible NOT IN (0,'0','false','False')) "
            "ORDER BY required DESC, ord",
            (connector, op),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for name, typ, title, required, options_json in rows:
        if not name or name in seen:
            continue
        seen.add(name)
        entry: dict[str, Any] = {"name": name}
        if required in (1, "1", "true", "True"):
            entry["required"] = True
        if typ:
            entry["type"] = typ
        if title and title != name:
            entry["label"] = title
        if options_json:
            try:
                opts = json.loads(options_json)
                if isinstance(opts, list) and opts:
                    entry["options"] = [str(o) for o in opts]
            except (ValueError, TypeError):
                pass
        out.append(entry)
    return out


def _connectors_that_could_contain(
        keywords: tuple[str, ...] | None,
        exclude: set[str],
        limit: int = 4) -> list[dict[str, str]]:
    """Across the WHOLE reference catalog (not just configured connectors),
    find connectors that carry a containment/response op matching the target —
    minus the ones already configured. This turns a dead end into a concrete
    "configure connector X to enable this" recommendation. Best-effort: any DB
    hiccup returns []."""
    found: dict[str, str] = {}  # connector -> sample op that would do the job
    try:
        with sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True) as conn:
            rows = conn.execute(
                "SELECT connector_name, op_name, title, category FROM operations "
                "WHERE (enabled IS NULL OR enabled NOT IN (0,'0'))"
            ).fetchall()
    except sqlite3.Error:
        return []
    for connector, op, title, category in rows:
        if not connector or connector in exclude or connector in found:
            continue
        nm = (op or "").lower()
        cat = (category or "").lower()
        if nm.startswith(_NON_ACTION_PREFIXES):
            continue
        is_action = (cat in _CONTAINMENT_CATEGORIES
                     or any(v in nm for v in _CONTAINMENT_VERBS))
        if not is_action:
            continue
        if keywords and not any(
                k in nm or k in (title or "").lower() for k in keywords):
            continue
        found[connector] = op or ""
        if len(found) >= limit:
            break
    return [{"connector": c, "op": o} for c, o in found.items()]


def _healthcheck_many(
        client,
        targets: list[Union[tuple[str, str], tuple[str, str, str]]],
        deadline_s: float = 20.0,
        timing: dict[str, Any] | None = None) -> dict[str, str]:
    """Healthcheck many (name, version) connectors CONCURRENTLY, returning
    {name: status}. Serial probing was the dominant latency in the live triage
    loop (~45 configured connectors × a blocking GET each, some slow/hung
    vendors = minutes per call, on both the eval and the analyst's screen).

    Two bounds keep a hung vendor from blowing the turn:
      • `_live_healthcheck` passes timeout=8 — but the ON-BOX crudhub session
        SILENTLY IGNORES that kwarg, so an unresponsive vendor healthcheck runs
        unbounded on the box (this is what made find_enrichment_actions take
        ~2 min in export sess-ei6esw96: ~13 candidate connectors, cold cache).
      • So we ALSO bound the whole fan-out by `deadline_s` wall-clock: we wait on
        the pool with a deadline and abandon any straggler probe (its worker
        thread is left to finish/die in the background). A connector we couldn't
        verify in time is simply omitted from the result → the caller FAILS OPEN
        on its listing status rather than dead-ending or hanging.

    When `timing` is provided it's populated with a per-probe breakdown
    (cache hits, live probes, timed-out connectors, slowest calls) so a slow
    finder is self-diagnosing from its own tool result — there was no per-op
    timing anywhere before, so a hang like the 2-min one above was un-triageable
    from the export alone.

    Read-only independent calls, so a thread pool is safe."""
    if not targets:
        if timing is not None:
            timing.update({"n": 0, "live": 0, "cached": 0, "timed_out": [],
                           "probe_ms": 0, "slowest": []})
        return {}
    import time as _time
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from .tools_execution import (_live_healthcheck, _cached_health,
                                  _store_health)

    per_probe: dict[str, dict[str, Any]] = {}

    def _probe(
            target: Union[tuple[str, str], tuple[str, str, str]]) -> tuple[str, str]:
        name, version = target[0], target[1]
        agent_id = target[2] if len(target) > 2 else ""
        t0 = _time.perf_counter()
        # Reuse the same warm health cache run_op's preflight uses (4h healthy /
        # 5min unhealthy, pre-populated by warmup). A cache hit collapses the
        # probe to a sqlite read; on a miss we probe once and store the verdict
        # so the next finder/turn is free.
        cached = _cached_health(name, version, "")
        if cached is not None:
            per_probe[name] = {"ms": round((_time.perf_counter() - t0) * 1000, 1),
                               "src": "cache"}
            return name, str(cached.get("status") or "error")
        try:
            hr = _live_healthcheck(client, name, version, agent_id=agent_id)
            status = str(hr.get("status") or "error")
            _store_health(name, version, status,
                          hr.get("message") or hr.get("error") or "", config="")
            per_probe[name] = {"ms": round((_time.perf_counter() - t0) * 1000, 1),
                               "src": "live"}
            return name, status
        except Exception as e:  # noqa: BLE001
            per_probe[name] = {"ms": round((_time.perf_counter() - t0) * 1000, 1),
                               "src": "error"}
            return name, f"error:{e!r}"

    out: dict[str, str] = {}
    timed_out: list[str] = []
    t_start = _time.perf_counter()
    # Don't leave the pool's __exit__ to join stragglers (that would re-impose the
    # unbounded wait we're trying to escape). Wait on futures with a shrinking
    # deadline and walk away from whatever hasn't landed.
    pool = ThreadPoolExecutor(max_workers=min(16, len(targets)))
    fut_to_name = {pool.submit(_probe, t): t[0] for t in targets}
    try:
        for fut in as_completed(list(fut_to_name), timeout=deadline_s):
            name, status = fut.result()
            out[name] = status
    except Exception:  # noqa: BLE001 — concurrent.futures.TimeoutError and friends
        pass
    finally:
        for fut, name in fut_to_name.items():
            if not fut.done():
                timed_out.append(name)
        # Threads with in-flight on-box probes can't be cancelled; let them drain
        # in the background instead of blocking this turn on shutdown(wait=True).
        pool.shutdown(wait=False)

    if timing is not None:
        slowest = sorted(per_probe.items(), key=lambda kv: kv[1]["ms"],
                         reverse=True)[:5]
        timing.update({
            "n": len(targets),
            "live": sum(1 for p in per_probe.values() if p["src"] == "live"),
            "cached": sum(1 for p in per_probe.values() if p["src"] == "cache"),
            "timed_out": timed_out,
            "probe_ms": round((_time.perf_counter() - t_start) * 1000, 1),
            "slowest": [[n, p["ms"], p["src"]] for n, p in slowest],
        })
    return out


@mcp.tool()
def find_containment_actions(target_type: str = "", probe: bool = True,
                             limit: int = 25) -> dict[str, Any]:
    """List the containment/response actions that are CONFIGURED (and, with
    probe, healthy) on this FortiSOAR instance — optionally for one indicator
    type. Use this to STAGE containment instead of hunting connector-by-
    connector with find_connector/find_operation.

    Given a host to isolate, an IP to block, or a user to disable, one call
    returns the destructive ops you can actually run here — with the connector,
    op, category, the approval tier, and the required params — so you can go
    straight to emit_action_card. Read-only: it discovers actions, it does not
    run them. Every action it returns is tier 3+ and MUST be staged via
    emit_action_card for analyst approval, never run silently.

    Args:
        target_type: indicator to contain — one of ip/host/endpoint/user/url/
            domain/hash/file/email/process. Empty returns every containment
            action across configured connectors.
        probe: healthcheck each configured connector (default True) and drop
            the ones that aren't Available, so you don't stage an action on a
            disconnected connector.
        limit: max actions to return (default 25).

    Returns:
        {"target_type", "actions": [{connector, op, title, category, tier,
         requires_approval, status, required_params:[{name,type}]}],
         "count", "probed"}. Deprecated ops sort last.
    """
    target = (target_type or "").strip().lower()
    keywords = _TARGET_KEYWORDS.get(target)
    if target and keywords is None:
        return {"ok": False, "code": "unknown_target_type",
                "message": f"target_type {target_type!r} not recognized",
                "valid": sorted(_TARGET_KEYWORDS)}

    # 1. Configured + active connectors on the live box. NOTE: list WITHOUT
    # probing — healthchecking all ~45 configured connectors here is the
    # latency trap (minutes on the live box). We narrow to the few connectors
    # that actually carry a matching containment op via the store first, then
    # healthcheck ONLY those (step 3).
    listing = list_configured_connectors(probe=False, verbose=True)
    if "error" in listing:
        return {"ok": False, "code": "no_fsr_configured",
                "message": listing["error"]}
    configured: dict[str, str] = {}  # name -> listing status
    version_of: dict[str, str] = {}  # name -> version (for the scoped probe)
    agent_of: dict[str, str] = {}    # name -> FortiSOAR Agent id, if proxied
    for c in listing.get("configured", []):
        name = c.get("name")
        if not name:
            continue
        configured[name] = str(c.get("status") or "")
        if c.get("version"):
            version_of[name] = c["version"]
        if c.get("_agent_id"):
            agent_of[name] = c["_agent_id"]
    if not configured:
        return {"ok": True, "target_type": target or None, "actions": [],
                "count": 0, "probed": probe,
                "message": "no configured/healthy connectors to contain with"}

    # 2. Pull each connector's destructive ops from the store, classify, filter.
    actions: list[dict[str, Any]] = []
    try:
        from fsr_playbooks.llm.tools import _tier_for_run_op as _tier  # type: ignore
    except Exception:  # noqa: BLE001
        _tier = None  # tier becomes best-effort
    placeholders = ",".join("?" * len(configured))
    with sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True) as conn:
        rows = conn.execute(
            f"SELECT connector_name, op_name, title, category FROM operations "
            f"WHERE connector_name IN ({placeholders}) "
            f"AND (enabled IS NULL OR enabled NOT IN (0,'0')) ",
            tuple(configured),
        ).fetchall()
        for connector, op, title, category in rows:
            nm = (op or "").lower()
            cat = (category or "").lower()
            if nm.startswith(_NON_ACTION_PREFIXES):
                continue
            is_action = (cat in _CONTAINMENT_CATEGORIES
                         or any(v in nm for v in _CONTAINMENT_VERBS))
            if not is_action:
                continue
            if keywords and not any(
                    k in nm or k in (title or "").lower() for k in keywords):
                continue
            # The decisive guard: a real response action is one the dispatch
            # gate would force through approval (tier >= 3). This drops
            # query/investigation-category false positives that merely share a
            # verb (e.g. delete_device, get_blocked_ip) without re-listing
            # every safe op.
            tier = _tier({"connector": connector, "op": op}) if _tier else 4
            if tier < 3:
                continue
            actions.append({
                "connector": connector,
                "op": op,
                "title": title or op,
                "category": category or "unknown",
                "tier": tier,
                "requires_approval": True,
                "status": configured.get(connector),
                "deprecated": "deprecat" in (title or "").lower(),
                "required_params": _required_params(conn, connector, op),
                # Full param signature WITH select options so the agent calls
                # run_op / emit_action_card with valid names AND valid select
                # values directly — no guess, no bad_params round-trip.
                "params": _param_sig(conn, connector, op),
                # When true, run_op routes this op through the agent force-fail
                # wrap (~30-60s). Tell the user it runs on a FortiSOAR agent and
                # may take a moment, THEN call run_op.
                "runs_on_agent": connector in agent_of,
            })

    # 3. Scoped healthcheck: probe ONLY the connectors that carry a candidate
    # action (a handful), not all configured ones. Drop actions whose connector
    # we actively probed and found unhealthy — so we never stage on a known-
    # disconnected connector. But FAIL OPEN: if a connector couldn't be probed
    # (no version to scope the probe, or no live client), fall back to its
    # listing status rather than silently dropping a valid containment action.
    # A probe gap must never manufacture a dead end out of a configured op.
    probe_timing: dict[str, Any] = {}
    if probe and actions:
        candidates = {a["connector"] for a in actions}
        targets = [(c, version_of[c], agent_of.get(c, ""))
                   for c in candidates if c in version_of]
        client = _shared._live_client() if targets else None
        health = (_healthcheck_many(client, targets, timing=probe_timing)
                  if client is not None else {})
        healthy_ok = {"available", "completed", "active", "connected",
                      "ok", "success"}
        kept = []
        for a in actions:
            # Probed result wins; otherwise trust the listing status we already
            # have (probe gap → fail open, don't drop).
            st = health.get(a["connector"], a.get("status") or "")
            if str(st).lower() not in healthy_ok:
                continue
            a["status"] = st
            kept.append(a)
        actions = kept

    # Non-deprecated first, then by connector/op for stable ordering.
    actions.sort(key=lambda a: (a["deprecated"], a["connector"], a["op"]))
    out: dict[str, Any] = {"ok": True, "target_type": target or None,
                           "actions": actions[:limit], "count": len(actions),
                           "probed": probe}
    if probe_timing:
        out["_timing"] = probe_timing
    if not actions:
        # Connectors are configured, but none can contain this (the set is
        # intel/utility only, or nothing matches the target type). Don't dead-
        # end the analyst: build a ready-to-emit `capability_gap` card that
        # names which connector to configure (looked up from the full catalog),
        # how to resume, and manual fallbacks. The agent forwards `suggested_card`
        # straight into emit_capability_gap_card; the prompt mandates it.
        scope = f" for target type {target!r}" if target else ""
        miss = f"{target} containment" if target else "containment / response"
        could = _connectors_that_could_contain(keywords, set(configured))
        if could:
            names = ", ".join(c["connector"] for c in could)
            fix_steps = [
                f"Configure one of these connectors under Settings → "
                f"Connectors: {names} (each carries a matching containment op, "
                f"e.g. {could[0]['connector']}.{could[0]['op']}).",
                "Save the configuration and confirm it shows as Available.",
            ]
        else:
            fix_steps = [
                "Install + configure a response connector for this target "
                "(e.g. fortigate-firewall for IP/host blocking) under "
                "Settings → Connectors.",
            ]
        out["suggested_card"] = _capability_gap_suggestion(
            id=f"capgap_{target or 'containment'}",
            missing=miss,
            why=(f"no tier-3 containment operation is available on any "
                 f"configured, healthy connector{scope}"),
            fix_steps=fix_steps,
            resume_value="recheck_containment",
            tips=[
                {"text": "Keep at least one response connector configured + "
                         "healthy so containment can be staged automatically.",
                 "hint": "Intel-only instances can enrich but never contain."},
                {"text": "Grant the connector probe access so I can confirm "
                         "it's reachable before staging an action."},
            ],
            alternatives=[
                {"label": "Escalate to T2", "value": "escalate_t2"},
                {"label": "Create remediation ticket", "value": "ticket"},
                {"label": "Acknowledge & document", "value": "document"},
            ],
        )
        out["message"] = (
            f"No containment/response action is configured on this FortiSOAR "
            f"instance{scope}. Don't keep searching and don't dead-end the "
            f"analyst: call `emit_capability_gap_card` with the `suggested_card` "
            f"payload returned here (it names which connector to configure and "
            f"includes a resume button), and note in your verdict that automated "
            f"containment isn't available here yet.")
    return out


@mcp.tool()
def find_enrichment_actions(target_type: str = "", probe: bool = True,
                            limit: int = 25) -> dict[str, Any]:
    """List the read-only ENRICHMENT/intel lookups that are CONFIGURED (and,
    with probe, healthy) on this FortiSOAR instance — optionally for one
    indicator type. Use this to enrich an indicator instead of guessing op
    names or hunting connector-by-connector with find_connector/find_operation.

    Given an IP, domain, URL, hash, or email to enrich, ONE call returns the
    reputation/context/IOC ops you can actually run here — with the connector,
    the real op name, category, and the required params — so you can go straight
    to run_op on each. This is the read-side mirror of find_containment_actions:
    every action it returns is tier <= 2 (read-only) and is meant to be RUN
    directly via run_op and summarized, NOT staged via emit_action_card.

    Fan out: the returned ops are independent, so issue their run_op calls
    together in one turn (the widget consolidates all sources for one indicator
    into a single enrichment card — more sources = a richer verdict).

    Args:
        target_type: indicator to enrich — one of ip/host/endpoint/user/url/
            domain/hash/file/email. Empty returns every intel lookup across
            configured connectors.
        probe: healthcheck each candidate connector (default True) and drop the
            ones that aren't Available, so you don't run on a dead connector.
        limit: max actions to return (default 25).

    Returns:
        {"target_type", "actions": [{connector, op, title, category, tier,
         requires_approval: false, status, required_params:[{name,type}],
         runs_on_agent}], "count", "probed"}. When nothing is configured to
        enrich this, returns a `suggested_card` for emit_capability_gap_card.
    """
    target = (target_type or "").strip().lower()
    keywords = _TARGET_KEYWORDS.get(target)
    if target and keywords is None:
        return {"ok": False, "code": "unknown_target_type",
                "message": f"target_type {target_type!r} not recognized",
                "valid": sorted(_TARGET_KEYWORDS)}

    # 1. Configured + active connectors (no probe yet — narrow via the store
    # first, healthcheck only the handful that carry a matching op in step 3).
    listing = list_configured_connectors(probe=False, verbose=True)
    if "error" in listing:
        return {"ok": False, "code": "no_fsr_configured",
                "message": listing["error"]}
    configured: dict[str, str] = {}
    version_of: dict[str, str] = {}
    agent_of: dict[str, str] = {}
    for c in listing.get("configured", []):
        name = c.get("name")
        if not name:
            continue
        configured[name] = str(c.get("status") or "")
        if c.get("version"):
            version_of[name] = c["version"]
        if c.get("_agent_id"):
            agent_of[name] = c["_agent_id"]
    if not configured:
        return {"ok": True, "target_type": target or None, "actions": [],
                "count": 0, "probed": probe,
                "message": "no configured connectors to enrich with"}

    # 2. Pull each connector's read ops from the store, classify, filter.
    actions: list[dict[str, Any]] = []
    try:
        from fsr_playbooks.llm.tools import _tier_for_run_op as _tier  # type: ignore
    except Exception:  # noqa: BLE001
        _tier = None
    placeholders = ",".join("?" * len(configured))
    with sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True) as conn:
        rows = conn.execute(
            f"SELECT connector_name, op_name, title, category FROM operations "
            f"WHERE connector_name IN ({placeholders}) "
            f"AND (enabled IS NULL OR enabled NOT IN (0,'0')) ",
            tuple(configured),
        ).fetchall()
        for connector, op, title, category in rows:
            nm = (op or "").lower()
            if not _is_enrichment_op(nm, (title or "").lower(), target):
                continue
            # Decisive read guard (inverse of containment's tier>=3): only
            # surface ops the dispatch gate treats as read-only (tier <= 2).
            # Drops anything that would force approval — we never present a
            # mutating op as enrichment.
            tier = _tier({"connector": connector, "op": op}) if _tier else 2
            if tier > 2:
                continue
            actions.append({
                "connector": connector,
                "op": op,
                "title": title or op,
                "category": category or "unknown",
                "tier": tier,
                "requires_approval": False,
                "status": configured.get(connector),
                "deprecated": "deprecat" in (title or "").lower(),
                "required_params": _required_params(conn, connector, op),
                # Full param signature WITH select options so the agent calls
                # run_op / emit_action_card with valid names AND valid select
                # values directly — no guess, no bad_params round-trip.
                "params": _param_sig(conn, connector, op),
                "runs_on_agent": connector in agent_of,
            })

    # 3. Scoped healthcheck: probe ONLY the connectors carrying a candidate op.
    # Drop actions whose connector we actively probed and found unhealthy, but
    # FAIL OPEN on a probe gap (no version / no live client) — never manufacture
    # a dead end out of a configured op.
    probe_timing: dict[str, Any] = {}
    if probe and actions:
        candidates = {a["connector"] for a in actions}
        targets = [(c, version_of[c], agent_of.get(c, ""))
                   for c in candidates if c in version_of]
        client = _shared._live_client() if targets else None
        health = (_healthcheck_many(client, targets, timing=probe_timing)
                  if client is not None else {})
        healthy_ok = {"available", "completed", "active", "connected",
                      "ok", "success"}
        kept = []
        for a in actions:
            st = health.get(a["connector"], a.get("status") or "")
            if str(st).lower() not in healthy_ok:
                continue
            a["status"] = st
            kept.append(a)
        actions = kept

    # Rank by connector preference (high-signal TI first, AlienVault last),
    # then name — so the preferred sources survive the `limit` cut instead of
    # losing to alphabetical order. Then cap per connector so one chatty
    # connector can't crowd the slate out of the budget.
    actions.sort(key=lambda a: (a["deprecated"],
                                _enrich_connector_rank(a["connector"]),
                                a["connector"], a["op"]))
    per_connector: dict[str, int] = {}
    capped: list[dict[str, Any]] = []
    for a in actions:
        n = per_connector.get(a["connector"], 0)
        if n >= _ENRICH_PER_CONNECTOR_CAP:
            continue
        per_connector[a["connector"]] = n + 1
        capped.append(a)
    actions = capped
    out: dict[str, Any] = {"ok": True, "target_type": target or None,
                           "actions": actions[:limit], "count": len(actions),
                           "probed": probe}
    if probe_timing:
        out["_timing"] = probe_timing
    if not actions:
        # No intel lookup is configured for this. Don't dead-end the analyst:
        # build a ready-to-emit capability_gap card naming a TI connector to
        # configure (from the full catalog), with a resume button.
        scope = f" for target type {target!r}" if target else ""
        miss = f"{target} enrichment" if target else "indicator enrichment"
        could = _connectors_that_could_enrich(target, set(configured))
        if could:
            names = ", ".join(c["connector"] for c in could)
            fix_steps = [
                f"Configure one of these threat-intel connectors under "
                f"Settings → Connectors: {names} (each carries a matching "
                f"lookup, e.g. {could[0]['connector']}.{could[0]['op']}).",
                "Save the configuration and confirm it shows as Available.",
            ]
        else:
            fix_steps = [
                "Install + configure a threat-intel connector for this "
                "indicator (e.g. virustotal for IP/domain/URL/file reputation) "
                "under Settings → Connectors.",
            ]
        out["suggested_card"] = _capability_gap_suggestion(
            id=f"capgap_{target or 'enrichment'}",
            missing=miss,
            why=(f"no read-only enrichment operation is available on any "
                 f"configured, healthy connector{scope}"),
            fix_steps=fix_steps,
            resume_value="recheck_enrichment",
            tips=[
                {"text": "Keep at least one threat-intel connector configured "
                         "+ healthy so indicators can be enriched automatically.",
                 "hint": "VirusTotal / Shodan / IP Quality Score / FortiGuard "
                         "all cover common indicator types."},
                {"text": "Grant the connector probe access so I can confirm "
                         "it's reachable before running a lookup."},
            ],
            alternatives=[
                {"label": "Skip enrichment", "value": "skip_enrichment"},
                {"label": "Document & continue", "value": "document"},
            ],
        )
        out["message"] = (
            f"No read-only enrichment lookup is configured on this FortiSOAR "
            f"instance{scope}. Don't keep searching and don't dead-end the "
            f"analyst: call `emit_capability_gap_card` with the `suggested_card` "
            f"payload returned here (it names which TI connector to configure "
            f"and includes a resume button).")
    return out


@mcp.tool()
def list_configured_connectors(probe: bool = False,
                               verbose: bool = False,
                               only: set[str] | None = None) -> dict[str, Any]:
    """List connectors that are configured AND active on the live FSR instance.

    A connector with no configuration cannot be called — it'll fail at runtime
    even if it appears in `find_connector`. Use this BEFORE picking which
    connector to put in a playbook.

    Args:
        probe: when True, also healthcheck each one (live HTTP per connector).
            Healthchecks run CONCURRENTLY (thread pool, per-call timeout) so a
            full probe is bounded by the slowest single vendor, not their sum.
        verbose: when True, include label, version, and config_count.
            Default returns only name + status to keep tool-result tokens low.
        only: internal — when set, healthcheck just this subset of connector
            names (the rest keep their listing status). Lets callers that have
            already narrowed to a handful of relevant connectors avoid probing
            all ~45 configured ones. Not exposed to the agent.

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
        rows = list((r.json().get("data") or []) if r.status_code == 200 else [])
    except Exception as e:  # noqa: BLE001
        return {"error": f"connector_details fetch failed: {e!r}"}

    try:
        from .tools_execution import _agent_configured_rows
        already = {x.get("name") for x in rows}
        rows += [x for x in _agent_configured_rows(client) if x.get("name") not in already]
    except Exception:  # noqa: BLE001
        pass

    out: list[dict] = []
    name_version: dict[str, str] = {}
    name_agent: dict[str, str] = {}
    for x in rows:
        item: dict[str, Any] = {
            "name": x.get("name"),
            "status": x.get("status"),
        }
        # `version` is needed locally for the probe call regardless of verbose.
        x_version = x.get("version")
        if x.get("name") and x_version:
            name_version[x["name"]] = x_version
        if x.get("name") and x.get("_agent_id"):
            name_agent[x["name"]] = x["_agent_id"]
            item["_agent_id"] = x["_agent_id"]
            # Heads-up for the agent: ops on this connector run on a FortiSOAR
            # agent and take ~30-60s (run_op routes them through the force-fail
            # playbook wrap). Narrate the delay to the user before calling.
            item["runs_on_agent"] = True
        if verbose:
            item["version"] = x_version
            item["label"] = x.get("label")
            item["config_count"] = x.get("config_count")
        out.append(item)

    # When `only` is given, healthcheck just that subset (the caller already
    # knows which connectors are relevant — e.g. find_containment_actions has
    # filtered to the few with a matching op). Otherwise probe all configured.
    if probe:
        targets = [(n, v, name_agent.get(n, "")) for n, v in name_version.items()
                   if only is None or n in only]
        health = _healthcheck_many(client, targets)
        for item in out:
            if item["name"] in health:
                item["status"] = health[item["name"]]
    # `ok: True` so the connector's result classifier doesn't read a
    # successful payload that happens to omit `ok` as a failure (it was
    # mislabeling this tool `(error)` despite returning valid data).
    return {"ok": True, "configured": out, "probed": probe, "count": len(out)}


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
