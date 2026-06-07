"""MCP tools: Tools Triage"""
from __future__ import annotations
from . import _shared

import json
import re
import sqlite3
from typing import Any, Union

from ._shared import (
    mcp,
    _capability_gap_suggestion,
    _db,
    _rows,
    _VERIF_RANK,
)
from .tools_execution import _fetch_runs_both, _shape_run
# Import DB_PATH for local use
DB_PATH = _shared.DB_PATH

# ---------------------------------------------------------------------------
# Record summarization — keep get_record cheap for the agent loop
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
    populated field otherwise (this is the debug path — it must stay faithful),
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
        if "sla" in k.lower():  # *SLA* timers/dates — plumbing, not signal
            continue
        if _is_empty(v):
            continue
        out[k] = v
    return out


def _cap_json(obj: Any, max_bytes: int = _REC_FULL_MAX_BYTES):
    """Bound a value's serialized size. Returns (value, truncated). When the
    JSON exceeds `max_bytes`, replaces it with a head/tail-truncated marker so
    a single tool result can't blow the token budget — the agent still sees the
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
    identity (@id/uuid/name) and every populated scalar field — which is
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

# ---------------------------------------------------------------------------
# Containment-action discovery — one call, no connector-by-connector hunting
# ---------------------------------------------------------------------------
# Containment verbs that mark an op as a response action (not a read/reversal).
_CONTAINMENT_VERBS: tuple[str, ...] = (
    "block", "quarantine", "isolate", "disable", "revoke", "ban", "suspend",
    "kill", "terminate", "contain", "deactivate", "shutdown",
)
# Op-name prefixes that are reads or the UNDO of a containment action — never
# what "stage containment" wants.
_NON_ACTION_PREFIXES: tuple[str, ...] = (
    "get_", "list_", "search_", "fetch_", "check_", "describe_", "count_",
    "enable_", "allow_", "unblock", "unquarantine", "unisolate", "unban",
    "unsuspend", "unrevoke", "undisable",
)
# Indicator type -> op-name/title keywords. The agent passes the type of the
# thing it wants to contain; we match it to the right family of ops.
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

# --- Read/enrichment discovery (mirror of the containment side) -------------
# An enrichment op takes an indicator (IP / domain / URL / hash / email / host)
# and returns intel about it — reputation, context, IOC lookup, geo/whois. It's
# read-only: the agent runs it directly via run_op and summarizes, never cards
# it. Most read ops carry the catch-all `investigation` category, so category
# alone can't select them; we match indicator/intel tokens in the op name+title
# and use a tier<=2 read guard, the inverse of the containment tier>=3 guard.
_INTEL_TOKENS: tuple[str, ...] = (
    "reputation", "ioc", "indicator", "intel", "threat", "enrich", "context",
    "lookup", "geo", "whois", "passive", "detection", "verdict",
)
# Tokens that NAME a specific indicator type. Used to (a) confirm a candidate
# op is about the requested indicator and (b) reject ops that name only a
# *different* indicator (e.g. get_domain_reputation when enriching an IP).
# Note: "address" is deliberately NOT an ip token — it matches firewall
# address-objects (`get_addresses`), MAC/email addresses, etc.
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
# Write-ish / plumbing ops that share the `investigation` category but aren't an
# indicator lookup — re-scans, submissions, detonations, raw API passthroughs.
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
# Connector preference for enrichment ranking. High-signal TI connectors first
# so they survive the `limit` cut; AlienVault OTX is de-prioritized (slow,
# noisy, frequently times out — see memory `agent_no_alienvault_otx`). Lower
# rank value = preferred. Substring match against the connector name; anything
# unlisted lands in the middle band so a chatty deprioritized connector can't
# bury an unknown-but-neutral one.
_ENRICH_CONNECTOR_RANK: tuple[tuple[str, int], ...] = (
    ("virustotal", 0), ("fortiguard", 0), ("fortinet-fortiguard", 0),
    ("shodan", 1), ("ipqualityscore", 1), ("ip_quality", 1), ("ipqs", 1),
    ("greynoise", 1), ("abuseipdb", 1), ("urlscan", 1),
    ("alienvault", 9), ("otx", 9),
)
_ENRICH_RANK_DEFAULT = 5
# Cap per connector so one chatty connector can't crowd the slate.
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
        from fsr_core.llm.tools import _tier_for_run_op as _tier  # type: ignore
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
        from fsr_core.llm.tools import _tier_for_run_op as _tier  # type: ignore
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
               relationships: bool = True, full: bool = False) -> dict[str, Any]:
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
      full: leave this false. The default pruned projection already
        contains every triage-relevant field — all indicator scalars
        (sourceIp/destinationIp/host/user/hashes), severity/status, and a
        capped {iri,label} index of related records — at ~5% the size.
        ``full=True`` does NOT return the raw ~100KB body: it returns a
        cleaned (null/empty + SLA/boilerplate stripped), hard size-capped
        body with ``coerced_full=true`` set. It exists only for rare
        schema-debugging; do NOT set it during normal triage — the pruned
        default has every pivotable field already.

    Returns:
      ``{"ok": true, "iri": ..., "record": {...}, "url": ...}`` on a 200,
      else ``{"ok": false, "code": ..., "message": ...}``. When pruned,
      ``"summarized": true`` is set so callers know it isn't the raw body.
    """
    path = ""
    if iri and isinstance(iri, str):
        s = iri.strip().split("?", 1)[0]
        head = s.split(":", 1)[0]
        if ":" in s and "/" not in head:
            # `module:uuid` shorthand (the colon form the triage prompt
            # uses, e.g. `alerts:54f2…`) — the agent often pastes it
            # straight into `iri`. Expand to a real IRI instead of 404ing.
            mod, _, rest = s.partition(":")
            path = f"/api/3/{mod.strip()}/{rest.strip()}"
        else:
            # Full IRI, with or without a leading slash.
            path = "/" + s.lstrip("/")
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

    out: dict[str, Any] = {
        "ok": True,
        "iri": data.get("@id", path),
        "url": url,
    }
    if full:
        # `full=True` is discouraged during triage — the pruned projection
        # already carries every pivotable field. We honour the request for a
        # fuller body but NEVER return the raw ~100KB blob: strip the dead
        # weight (null/empty, SLA/boilerplate) and hard-cap the size so one
        # call can't blow the per-turn budget (the sess-uq31go5p waste). The
        # flags tell the agent it didn't get the verbatim body.
        cleaned = _clean_full_record(data)
        capped, truncated = _cap_json(cleaned)
        out["record"] = capped
        out["coerced_full"] = True
        out["note"] = (
            "full=True returned a cleaned, size-capped body (null/empty + "
            "SLA/boilerplate dropped), not the raw hydrated record. The "
            "default pruned projection already has every pivotable field — "
            "prefer get_record without full= during triage.")
        if truncated:
            out["truncated"] = True
    else:
        out["record"] = _summarize_record(data)
        out["summarized"] = True
    return out


# ---------------------------------------------------------------------------
# First-class FortiSIEM search tools
#
# Ergonomic, read-only wrappers over `run_op("fortinet-fortisiem", …)`. The
# agent reliably reaches for these (single clean call, entity pre-filled)
# where it dodges raw `search_events`/`run_op` with its ~20 fiddly params.
# Every wrapper returns the SAME compact `evidence_events` digest the record
# normalizer emits, so the agent learns one event shape everywhere.
# ---------------------------------------------------------------------------

# Bytes + port + host added to the connector's stock columns so the digest can
# show exfil volume and the host pivot without a second call.
# NB: received-bytes is `recvBytes64` — the pub/v2 engine 400s ("Internal
# Server Error") on the whole query if a single unknown attribute (`rcvdBytes64`)
# is in the SELECT, so this column name must match the FortiSIEM schema exactly.
_SIEM_SELECT = ("phRecvTime,reptDevIpAddr,eventType,eventName,srcIpAddr,"
                "destIpAddr,destIpPort,sentBytes64,recvBytes64,user,hostName")

_WINDOW_UNITS = {"m": "Minutes", "h": "Hours", "d": "Days"}


def _parse_window(window: str) -> tuple[str, int]:
    """'30m'|'2h'|'1d' → (rel_time unit, value) for search_events Relative Time.
    Falls back to (Hours, 2) on anything unrecognized."""
    m = re.fullmatch(r"\s*(\d+)\s*([mhd])\s*", str(window or "").lower())
    if not m:
        return "Hours", 2
    return _WINDOW_UNITS[m.group(2)], int(m.group(1))


def _event_rows(data: Any) -> list[dict[str, Any]]:
    """Pull the list of event dicts out of a run_op `data` payload, wherever
    the connector parked it (shape varies by op/version)."""
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    if isinstance(data, dict):
        # `samples` is fsr_core's own event-list digest (it collapses big
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
    from .tools_execution import run_op  # lazy: avoid import cycle at load
    from ..agent.skill_trace import mute_recording
    from ..llm.triage_normalize import _digest_event

    # Mute: this run_op is the implementation of a named MCP pivot tool
    # (siem_search_*/siem_events_for_incident), not an op the agent invoked
    # directly — keep it off the build trace so the playbook stays grounded in
    # the analyst's actual run_op calls.
    with mute_recording():
        res = run_op("fortinet-fortisiem", op, params)
    if not isinstance(res, dict) or not res.get("ok"):
        # pass the connector's own error straight through (unhealthy/timeout/etc)
        return _siem_error(op, echo, res)
    rows = _event_rows(res.get("data"))
    events = [d for d in (_digest_event(r) for r in rows) if d]
    return _envelope(op, echo, events, limit)


def _siem_error(op: str, echo: dict[str, Any],
                underlying: Any) -> dict[str, Any]:
    """Build a SIEM-tool error that PROPAGATES the underlying run_op failure's
    detail (message, issues, suggestions) instead of collapsing it to a bare
    `code`. The opaque collapse is what made siem_search_ip/siem_raw_query
    unrecoverable in export sess-vtd15c5v: the agent saw only
    `code:"bad_params"` with no clue what was wrong, abandoned the first-class
    tool, and fell back to hand-built run_op calls (which then also failed). The
    real cause lives in `underlying` (e.g. a select-option mismatch on the
    execute_api_request submit) — surface it so the agent (and we) can act."""
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
    return out


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


@mcp.tool()
def siem_search_ip(ip: str, direction: str = "any", window: str = "2h",
                   limit: int = 25) -> dict[str, Any]:
    """Search FortiSIEM events for an IP over a recent window — the easy pivot.

    Wraps `run_op("fortinet-fortisiem","search_events")` with the right
    attribute + value param pre-filled and a sane column set, returning the
    standard event digest (ts/src/dst/bytes/service/action). Prefer this over
    hand-building a raw search_events call.

    Args:
      ip: the IPv4 to search for.
      direction: 'src' (source), 'dst' (destination), or 'any' (default —
        matches either end with a single OR query).
      window: relative lookback like '30m', '2h' (default), '1d'.
      limit: max digested events to return (default 25).
    """
    clause = {"src": f"srcIpAddr={_q(ip)}",
              "dst": f"destIpAddr={_q(ip)}"}
    if direction in clause:
        where = clause[direction]
    else:  # 'any' — OR both ends (valid on the pub/v2 engine)
        where = f"(srcIpAddr={_q(ip)} OR destIpAddr={_q(ip)})"
    return _siem_pubv2_query(where, window=window, limit=limit,
                             op="siem_search_ip",
                             echo={"ip": ip, "direction": direction,
                                   "window": window})


@mcp.tool()
def siem_search_host(host: str, window: str = "2h",
                     limit: int = 25) -> dict[str, Any]:
    """Search FortiSIEM events by host name over a recent window.

    Runs a pub/v2 query (attribute='hostName') and returns the standard event
    digest. Use to pull a compromised host's recent activity in one call.
    """
    return _siem_pubv2_query(f"hostName={_q(host)}", window=window, limit=limit,
                             op="siem_search_host",
                             echo={"host": host, "window": window})


@mcp.tool()
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
    return '"{0}"'.format(str(value).replace('"', ""))


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
}


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
    path on FortiSIEM 6.0.0 — the legacy XML `search_events` op 400s ("Content
    is not allowed in prolog") on this build, so every `siem_search_*` helper
    routes here too. Returns the standard `_envelope` (plus `query_id`) on
    success, or a typed error dict on submit/poll failure.
    """
    import time as _time

    from .tools_execution import run_op
    from ..agent.skill_trace import mute_recording
    from ..llm.triage_normalize import _digest_event

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
    # The connector's FortiSIEM base already includes `/phoenix` — endpoint is
    # relative to that. `execute_api_request` is gated (unknown risk) so this
    # read-only query passes confirm=True. The engine is flaky; retry submit.
    #
    # NB: do NOT send `payload_format` — the live FortiSIEM connector on the box
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
        # calls implement ONE logical SIEM query — they must not each land on
        # the session trace as a raw-HTTP playbook step (the grounding gap).
        with mute_recording():
            sub = run_op("fortinet-fortisiem", "execute_api_request", submit_args,
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
            # Submitted OK but no queryId came back — a SIEM-side quirk, not a
            # caller error; no underlying validator detail to propagate.
            return {"ok": False, "op": op, "query": echo, "code": "no_query_id",
                    "message": "FortiSIEM accepted the query but returned no "
                               "queryId"}
        # The submit itself was rejected (e.g. bad_params on execute_api_request)
        # — propagate the connector's actionable detail instead of an opaque code.
        return _siem_error(op, echo, last)

    # Poll + fetch on the SAME pub/v2 subsystem we submitted to (the connector's
    # get_events_by_query_id uses the legacy XML get_records path — wrong id
    # space for a pub/v2 queryId).
    rows: list[dict[str, Any]] = []
    for _ in range(max(1, poll_max)):
        with mute_recording():
            prog = run_op("fortinet-fortisiem", "execute_api_request", {
                "endpoint": "/rest/pub/v2/query/progress", "method": "GET",
                "query_params": {"queryId": qid}}, confirm=True)
        done = (isinstance(prog, dict) and isinstance(prog.get("data"), dict)
                and prog["data"].get("progress") == 100)
        if done:
            with mute_recording():
                res = run_op("fortinet-fortisiem", "execute_api_request", {
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
    return out


@mcp.tool()
def siem_raw_query(where: str | dict[str, Any], select: str = "",
                   window: str = "2h", limit: int = 25,
                   poll_max: int = 8) -> dict[str, Any]:
    """Run a vetted *native* FortiSIEM event query — the escape hatch.

    For when the attribute-based `siem_search_*` helpers can't express the
    filter you need. Goes through the connector (`run_op` execute_api_request
    against the pub/v2 query API — submit, poll progress, fetch results), NOT a
    direct FSM call, and uses FortiSOC scope defaults (include all, NO customer
    exclude). Returns the standard event digest.

    Args:
      where: the filter, either form —
        * a raw FortiSIEM clause string with **backend** attribute names, e.g.
          `srcIpAddr="10.10.100.1" AND destIpPort=443` (find names under
          Admin → Device Support → Event Attributes), or
        * a ``{field: value}`` dict, e.g. `{"sourceIPv4": "1.2.3.4",
          "destPort": 443}` — friendly field names are mapped to backend
          attributes, list values become an OR group, fields are AND-ed.
        `OR` across src/dst IP fields is fine on the pub/v2 engine.
      select: comma-separated backend field names (defaults to a sane set).
      window: relative lookback ('30m','2h','1d').
      limit: max digested events.
      poll_max: how many times to poll for query completion.
    """
    clause = _where_to_clause(where)
    return _siem_pubv2_query(clause, select=select, window=window, limit=limit,
                             poll_max=poll_max, op="siem_raw_query",
                             echo={"where": clause, "window": window})


# `get_associated_events_new` (and get_incidents/get_incident_details) on the
# live FortiSIEM 6.0.0 connector reject anything but this microsecond-Z datetime
# format — plain ISO 400s with "time data ... does not match format". And the op
# *requires* a timeFrom/timeTo window: omit it and the connector returns a
# MISLEADING "Invalid Incident Id" error (verified live, probe_siem_assoc_events
# — incident 5 fails id-only, succeeds with a window). So this wrapper always
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
# cap — 48h/168h 400 — hence the ≤24h incident-anchored window above.)
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
    the live SIEM (session sess-2avs5bgw passed id 17 — not on the box; live ids
    were 5,6,10,12,13). This resolves the id the events API will actually accept:

      1. exact match on the requested id, else
      2. (coercion) most-recent live incident for `source_ip`.

    Returns {incident_id, time_from, time_to, source_ip, coerced} or None when no
    live incident is found (caller then falls back to an IP event search)."""
    from .tools_execution import run_op
    import datetime as _dt

    now = _dt.datetime.now(_dt.timezone.utc)
    wide_from = (now - _dt.timedelta(days=180)).strftime(_SIEM_INC_DT)
    wide_to = now.strftime(_SIEM_INC_DT)
    res = run_op("fortinet-fortisiem", "get_incidents", {
        "timeFrom": wide_from, "timeTo": wide_to,
        "incidentStatus": ["Active", "Cleared", "Open"],
        "severity": ["High", "Medium", "Low"], "size": 500,
    })
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
            break  # a real submit/poll failure — don't keep hammering
        if last.get("count"):
            last["fallback"] = "siem_search_ip"
            last["note"] = (
                f"incident {incident_id} not directly queryable on the live "
                f"FortiSIEM; returned source-IP ({source_ip}) events from a "
                f"{window} lookback instead.")
            return last
    # nothing found in any window (or a hard failure) — tag the last envelope
    if last.get("ok"):
        last["fallback"] = "siem_search_ip"
        last["note"] = (
            f"incident {incident_id} not directly queryable, and no events were "
            f"found for source IP {source_ip} within "
            f"{_SIEM_FALLBACK_WINDOWS[-1][0]}.")
    return last


@mcp.tool()
def siem_events_for_incident(incident_id: str, time_from: str = "",
                             time_to: str = "", limit: int = 25,
                             source_ip: str = "") -> dict[str, Any]:
    """Pull the raw FortiSIEM events that drove a specific incident.

    Wraps `get_associated_events_new` (incident triggeringEvents API) and
    returns the standard event digest. This is the canonical "pivot back into
    the originating SIEM" call when an alert came from FortiSIEM.

    Self-healing (so a stale/seeded id or a missing window no longer dead-ends —
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
        recommended — enables id-coercion and the IP-search fallback.
    """
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
            # No live incident for this id/host — pivot straight to a widening
            # IP event search.
            return _ip_fallback_search(source_ip, str(incident_id), limit)

    echo = {"incident_id": resolved_id, "timeFrom": tf, "timeTo": tt}
    if coerced:
        echo["coerced_from"] = str(incident_id)

    if not (tf and tt):
        # Couldn't establish a window and have no IP to fall back on — fail with
        # an ACCURATE hint (not the connector's misleading "Invalid Incident Id").
        return {
            "ok": False, "op": "get_associated_events_new", "query": echo,
            "code": "no_time_window",
            "message": ("get_associated_events_new requires a timeFrom/timeTo "
                        "window on this FortiSIEM build, and none could be "
                        "derived for this incident."),
            "suggestions": [
                "Pass `source_ip` so the wrapper can find the live incident / "
                "fall back to an IP event search.",
                "Or pass an explicit `time_from`/`time_to` window (≤24h) around "
                "the incident.",
            ],
        }

    params: dict[str, Any] = {"incident_id": resolved_id,
                              "perPage": min(limit, 50),
                              "timeFrom": tf, "timeTo": tt}
    out = _siem_run("get_associated_events_new", params, limit, echo)

    # Final self-heal: op still failed (or returned nothing) but we have an IP —
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
# datetime formats — exactly the friction these tools remove. Each returns the
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


def _faz_run(op: str, params: dict[str, Any], limit: int,
             echo: dict[str, Any], digest) -> dict[str, Any]:
    """Shared body: run a read-only FAZ op, digest its rows, return the uniform
    envelope (same shape as `_siem_run`). `digest` picks alert vs log shaping."""
    from .tools_execution import run_op  # lazy: avoid import cycle at load

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


@mcp.tool()
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


@mcp.tool()
def faz_search_ip(ip: str, direction: str = "any", adom: str = "root",
                  window: str = "24h", logtype: str = "Traffic",
                  devid: str = "All_FortiGate", limit: int = 25) -> dict[str, Any]:
    """Search FortiAnalyzer device logs for an IP over a recent window — the
    easy pivot.

    Wraps `start_and_fetch_bulk_device_logs` (start search + wait + fetch in one
    synchronous call) with the IP filter, ADOM, log type and time window
    pre-filled, returning the standard event digest
    (ts/src/dst/dport/action/service/bytes). Prefer this over hand-building a
    bulk-log-search call.

    Args:
      ip: the IPv4 to search for.
      direction: 'src', 'dst', or 'any' (default — matches either side via a
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


@mcp.tool()
def faz_raw_query(data: Any) -> dict[str, Any]:
    """Run a native FortiAnalyzer JSON-RPC request — the escape hatch.

    For when the `faz_get_alerts` / `faz_search_ip` helpers can't express what
    you need. Wraps `json_rpc_freeform` ("Execute an API Request"), which takes
    a raw FAZ JSON-RPC body and returns its response. Read-only by intent — use
    `get`/`exec` log-search methods, not config-changing `set`/`add`/`delete`.

    Args:
      data: the JSON-RPC request body (a dict, or a JSON string), e.g.
        `{"method": "get", "params": [{"url": "/eventmgmt/adom/root/alerts"}]}`.
        Whatever FAZ returns is row-digested when it looks like a list of rows,
        otherwise passed through under `raw`.
    """
    from .tools_execution import run_op

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
