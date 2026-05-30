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
    "host": ("host", "endpoint", "device", "machine", "asset", "agent"),
    "endpoint": ("endpoint", "host", "device", "agent", "machine"),
    "user": ("user", "account", "identity", "credential", "password", "login"),
    "url": ("url", "link", "uri"),
    "domain": ("domain", "fqdn", "dns"),
    "hash": ("hash", "file", "sample", "md5", "sha"),
    "file": ("file", "hash", "sample"),
    "email": ("email", "mail", "message"),
    "process": ("process", "task", "service"),
}
_CONTAINMENT_CATEGORIES = frozenset({"containment", "remediation"})


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
    return [{"name": r[0], "type": r[1]} for r in rows if r[0]]


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


def _healthcheck_many(client, targets: list[tuple[str, str]]) -> dict[str, str]:
    """Healthcheck many (name, version) connectors CONCURRENTLY, returning
    {name: status}. Serial probing was the dominant latency in the live triage
    loop (~45 configured connectors × a blocking GET each, some slow/hung
    vendors = minutes per call, on both the eval and the analyst's screen).
    `_live_healthcheck` caps each call at timeout=8; the pool collapses sum →
    max. Read-only independent calls, so a thread pool is safe; workers capped
    so we don't open dozens of sockets at once."""
    if not targets:
        return {}
    from concurrent.futures import ThreadPoolExecutor
    from .tools_execution import _live_healthcheck

    def _probe(target: tuple[str, str]) -> tuple[str, str]:
        name, version = target
        try:
            hr = _live_healthcheck(client, name, version)
            return name, str(hr.get("status") or "error")
        except Exception as e:  # noqa: BLE001
            return name, f"error:{e!r}"

    with ThreadPoolExecutor(max_workers=min(8, len(targets))) as pool:
        return dict(pool.map(_probe, targets))


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
    for c in listing.get("configured", []):
        name = c.get("name")
        if not name:
            continue
        configured[name] = str(c.get("status") or "")
        if c.get("version"):
            version_of[name] = c["version"]
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
            })

    # 3. Scoped healthcheck: probe ONLY the connectors that carry a candidate
    # action (a handful), not all configured ones. Drop actions whose connector
    # we actively probed and found unhealthy — so we never stage on a known-
    # disconnected connector. But FAIL OPEN: if a connector couldn't be probed
    # (no version to scope the probe, or no live client), fall back to its
    # listing status rather than silently dropping a valid containment action.
    # A probe gap must never manufacture a dead end out of a configured op.
    if probe and actions:
        candidates = {a["connector"] for a in actions}
        client = _shared._live_client()
        health = _healthcheck_many(
            client, [(c, version_of[c]) for c in candidates
                     if c in version_of]) if client is not None else {}
        healthy_ok = {"available", "completed", "active"}
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
        rows = (r.json().get("data") or []) if r.status_code == 200 else []
    except Exception as e:  # noqa: BLE001
        return {"error": f"connector_details fetch failed: {e!r}"}

    out: list[dict] = []
    name_version: dict[str, str] = {}
    for x in rows:
        item: dict[str, Any] = {
            "name": x.get("name"),
            "status": x.get("status"),
        }
        # `version` is needed locally for the probe call regardless of verbose.
        x_version = x.get("version")
        if x.get("name") and x_version:
            name_version[x["name"]] = x_version
        if verbose:
            item["version"] = x_version
            item["label"] = x.get("label")
            item["config_count"] = x.get("config_count")
        out.append(item)

    # When `only` is given, healthcheck just that subset (the caller already
    # knows which connectors are relevant — e.g. find_containment_actions has
    # filtered to the few with a matching op). Otherwise probe all configured.
    if probe:
        targets = [(n, v) for n, v in name_version.items()
                   if only is None or n in only]
        health = _healthcheck_many(client, targets)
        for item in out:
            if item["name"] in health:
                item["status"] = health[item["name"]]
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