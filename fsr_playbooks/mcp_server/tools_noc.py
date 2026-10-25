"""MCP tools: NOC / FortiManager + FortiAnalyzer device diagnostics.

Read-only (tier 1) helpers that let the SOC/NOC assistant talk to FortiManager
(device posture) and FortiAnalyzer (event hunting) the same way the `siem_*` /
`faz_*` triage tools talk to FortiSIEM:

  * thin named wrappers over ``run_op`` against ``fortinet-fortimanager`` /
    ``fortinet-fortianalyzer`` (live when configured, served from
    ``_sim_fixtures`` in simulation mode);
  * each shapes/truncates the raw payload into a compact, model-friendly digest;
  * each echoes its query for the activity trail.

All FortiManager reads go through ``json_rpc_get`` (every FMG connector variant
exposes it, so these stay portable across the json-rpc / utils / full
connectors). The FAZ device-hunt helpers reuse the FAZ plumbing already in
``tools_triage`` (``_faz_run`` / ``_faz_window`` / digests).
"""
from __future__ import annotations

from typing import Any

from fsr_playbooks.llm.tool_result import tool_err
from fsr_playbooks.mcp_server._shared import mcp

from .tools_triage import (
    _FAZ_DEVID_VALUES,
    _FAZ_LOG_TIME,
    _FAZ_LOGTYPE_VALUES,
    _envelope,
    _faz_devid,
    _faz_digest_log,
    _faz_logtype,
    _faz_run,
    _faz_select_error,
    _faz_window,
    _is_empty,
)

# FortiManager connector to drive. Live-verified against the json-rpc variant;
# all FMG builds (fortinet-fortimanager, *_dev, *-json-rpc) expose the
# json_rpc_get op this module relies on, so this is the only thing to change to
# retarget a differently-named build.
_FMG_CONNECTOR = "fortinet-fortimanager-json-rpc"


# ---------------------------------------------------------------------------
# FMG config + managed-device resolution
# ---------------------------------------------------------------------------
# Two production defects this guards (GA-demo C1, 2026-07):
#   * run_op with no `config` sends the framework's `get_default_config`
#     sentinel, which 400s (`INTEGRATION-12: Could not find a connector
#     configuration…`) when the FMG connector has multiple configs and none is
#     flagged default (GA `fortinet-fortimanager-json-rpc` has 3). We resolve a
#     usable config id up front instead.
#   * the agent applied FMG device-posture tools to an EDR endpoint host
#     ('ubuntu') FortiManager doesn't manage -- a device-type category error.
#     We gate the device-scoped tools on the FMG managed-device inventory so a
#     non-managed host is a CLEAN SKIP (ok:True), not a live call that 400s /
#     misses and burns the turn's error budget.
_FMG_CONFIG_CACHE: dict[str, str] = {}
_FMG_MANAGED_CACHE: dict[str, set[str]] = {}


def _fmg_config() -> str:
    """A usable config id for `_FMG_CONNECTOR`: the default/sole config, else the
    first of several when none is flagged default. "" in sim/offline (no live
    client) so run_op/fixtures take over. Cached per-process."""
    if "id" in _FMG_CONFIG_CACHE:
        return _FMG_CONFIG_CACHE["id"]
    cid = ""
    try:
        # `fsr_playbooks.execution_api` has no `live_client`: importing it
        # raised, the except below swallowed it, and every call fell back to
        # "" -- the default-config path -- even on a multi-config box.
        from fsr_playbooks.mcp_server import _shared
        from fsr_playbooks.mcp_server.tools_execution import (
            _configured_rows,
            _resolve_config_id,
            _row_config_ids,
        )
        client = _shared._live_client()
        if client is not None:
            rows = _configured_rows(client)
            cid = _resolve_config_id(rows, _FMG_CONNECTOR, "")  # default/sole
            if not cid:  # multi-config, no default → first configured one
                for row in rows:
                    if row.get("name") == _FMG_CONNECTOR:
                        ids = _row_config_ids(row)
                        cid = ids[0] if ids else ""
                        break
    except Exception:  # noqa: BLE001 -- best-effort; "" ⇒ run_op default path
        cid = ""
    _FMG_CONFIG_CACHE["id"] = cid
    return cid


def _fmg_managed_index(adom: str) -> set[str] | None:
    """Lowercased {name, serial, ip} of every FMG-managed device in `adom`, or
    None when the inventory can't be read (FMG unconfigured/unreachable). Cached
    per-process per-adom (only successful reads, so a transient failure re-tries
    on the next call)."""
    if adom in _FMG_MANAGED_CACHE:
        return _FMG_MANAGED_CACHE[adom]
    res = fmg_get_device_list(adom=adom, limit=500)
    if not isinstance(res, dict) or not res.get("ok"):
        return None  # transient/unavailable -- don't cache
    idx: set[str] = set()
    for d in res.get("devices") or []:
        for k in ("name", "serial", "ip"):
            v = d.get(k)
            if isinstance(v, str) and v.strip():
                idx.add(v.strip().lower())
    _FMG_MANAGED_CACHE[adom] = idx
    return idx


def _fmg_require_managed(device: str, adom: str, key: str,
                         what: str) -> dict[str, Any] | None:
    """Return a clean skip-envelope when `device` is POSITIVELY not an FMG-managed
    device, else None (proceed). FortiManager manages network devices (FortiGate/
    FortiAP/FortiSwitch), not endpoint hosts -- running a device-posture op on an
    endpoint is a category error that, unguarded, 400s or misses and burns the
    agent's error budget. ok:True (not an error) so the agent moves on. When the
    inventory can't be read we FAIL OPEN (proceed) rather than hide a real device
    on a transient FMG hiccup -- only a confirmed non-member is skipped."""
    idx = _fmg_managed_index(adom)
    if idx is None:
        return None  # inventory unreadable → don't block; let the op speak
    if device.strip().lower() not in idx:
        return {"ok": True, "op": "json_rpc_get",
                "query": {"adom": adom, "device": device}, key: [],
                "skipped": "not_fmg_managed",
                "note": (f"{device!r} is not a FortiManager-managed device "
                         f"(not in the FMG inventory for adom {adom!r}), so the "
                         f"FMG {what} was skipped. FortiManager manages network "
                         f"devices (FortiGate/FortiAP/FortiSwitch), not endpoint "
                         f"hosts -- use EDR/SIEM tools for an endpoint like this.")}
    return None


# ---------------------------------------------------------------------------
# FortiManager -- device posture (all read-only via json_rpc_get)
# ---------------------------------------------------------------------------
def _fmg_rows(data: Any) -> list[dict[str, Any]]:
    """Dig the row list out of an FMG json_rpc_get `data` payload. The
    `fortinet-fortimanager-json-rpc` connector nests rows under `get_response`
    (a list of devices, or a single device object). The named-op connector
    nests under JSON-RPC `result[].data`. run_op may also pre-digest big lists
    into `{samples: [...]}`. We recurse through wrapper envelopes (run_op's
    `{status, message, data: …}`) rather than treating the wrapper as a row."""
    def dig(node: Any) -> list[dict[str, Any]]:
        if isinstance(node, list):
            return [r for r in node if isinstance(r, dict)]
        if isinstance(node, dict):
            # Direct row-bearing keys: get_response (json-rpc connector) +
            # samples (run_op pre-digest).
            for key in ("get_response", "samples"):
                v = node.get(key)
                if isinstance(v, list):
                    return [r for r in v if isinstance(r, dict)]
                if isinstance(v, dict):
                    return [v]
            # Wrapper envelopes: recurse so a nested get_response/result is
            # found rather than returning the wrapper dict as a bogus row.
            res = node.get("result")
            if isinstance(res, list):
                out: list[dict[str, Any]] = []
                for el in res:
                    out.extend(dig(el))
                return out
            if isinstance(res, dict):
                return dig(res)
            d = node.get("data")
            if isinstance(d, (list, dict)):
                return dig(d)
        return []
    return dig(data)


def _fmg_conn_state(v: Any) -> Any:
    """Normalize FMG conn_status (1=up / 0=down int, or a string) to
    up/down/unknown. 'unknown' (never-connected / model device) is kept
    DISTINCT from 'down' (was up, now unreachable) -- conflating them misleads a
    device-down triage into flagging model devices as outages."""
    if isinstance(v, bool):
        return "up" if v else "down"
    if isinstance(v, (int, float)):
        return "up" if int(v) == 1 else "down"
    if isinstance(v, str):
        low = v.strip().lower()
        if low in ("1", "up", "connected"):
            return "up"
        if low in ("unknown", "unspecified", ""):
            return "unknown"
        if low in ("0", "down", "disconnected"):
            return "down"
        return v
    return v


def _fmg_digest_device(dev: dict[str, Any]) -> dict[str, Any]:
    """Collapse one FMG dvmdb device object into a compact posture row."""
    def g(*keys):
        for k in keys:
            if k in dev and not _is_empty(dev[k]):
                return dev[k]
        return None

    # FMG marks not-yet-deployed model devices with an `is_model` flag; their
    # conn_status is 'unknown' because no real hardware has ever checked in.
    # Surface this so a device-down triage doesn't mistake a model device for
    # an outage.
    flags = g("flags") or []
    is_model = isinstance(flags, list) and "is_model" in flags

    row = {
        "name": g("name"),
        "serial": g("sn", "serial"),
        "ip": g("ip"),
        "conn_status": _fmg_conn_state(g("conn_status")),
        "conf_status": g("conf_status"),
        "db_status": g("db_status"),
        "ha_mode": g("ha_mode"),
        "platform": g("platform_str", "platform"),
        "os_version": g("os_ver", "version"),
        "last_checked": g("last_checked", "last_resync"),
        "desc": g("desc"),
        "is_model": is_model or None,  # omitted unless true (None → filtered)
    }
    return {k: v for k, v in row.items() if not _is_empty(v)}


#: dvmdb device fields the device digest needs -- projected at the FMG query so
#: the response stays small (a full dvmdb row is ~100 keys / ~2KB each). FMG
#: honours `fields` inside the json_rpc_get `data` body.
_FMG_DEVICE_FIELDS = [
    "name", "sn", "ip", "conn_status", "conf_status", "db_status",
    "ha_mode", "platform_str", "os_ver", "last_checked", "desc", "flags",
]


def _fmg_get(url: str, echo: dict[str, Any], digest, limit: int,
             key: str, fields: list[str] | None = None) -> dict[str, Any]:
    """Shared body: run a read-only FMG json_rpc_get, digest its rows, return a
    uniform envelope (mirrors `_faz_run`). `key` names the returned list.
    `fields` (optional) projects the FMG query to just those columns."""
    from fsr_playbooks.execution_api import run_op  # lazy: avoid import cycle at load

    params: dict[str, Any] = {"url": url}
    if fields:
        # Project at the source so name/sn/ip stay in the row and the payload
        # is small. Belt-and-suspenders with summarize=False below.
        params["data"] = {"fields": fields}
    # summarize=False: this wrapper digests + bounds the rows itself; run_op's
    # generic truncation drops dict keys past the first 40 (stripping
    # late-ordered FMG fields like name/sn/ip) and caps the list to 5 items.
    res = run_op(_FMG_CONNECTOR, "json_rpc_get", params,
                 config=_fmg_config(), confirm=True, summarize=False)
    if not isinstance(res, dict) or not res.get("ok"):
        return tool_err(
            (res or {}).get("status") or (res or {}).get("code")
            or "fmg_op_failed",
            (res or {}).get("message") or "FortiManager op failed",
            op="json_rpc_get", query=echo)
    rows = [d for d in (digest(r) for r in _fmg_rows(res.get("data"))) if d]
    env = _envelope("json_rpc_get", echo, rows, limit)
    # _envelope keys the list as `events`; re-key to the domain noun.
    env[key] = env.pop("events")
    return env


@mcp.tool()
def fmg_device(by: str = "list", device: str = "", adom: str = "root",
               limit: int = 50) -> dict[str, Any]:
    """Query FortiManager-managed device posture -- list, status, or HA.

    The primary FMG device query. One tool with a discriminating ``by``
    argument instead of three near-identical tools competing for the model's
    attention. Use ``list`` for the roster, ``status`` for one device's
    posture, or ``ha`` for cluster members.

    Args:
      by: query type -- ``list`` (default), ``status``, ``ha``, or ``policy``.
      device: the FMG device name (required for ``status`` / ``ha``;
        optional filter for ``policy``).
      adom: FMG ADOM name (default 'root').
      limit: max rows to return (default 50 for ``list``, 25 for ``policy``).
    """
    by = by.lower().strip()
    if by == "list":
        return fmg_get_device_list(adom=adom, limit=limit)
    if by == "status":
        if not device:
            return {"error": "by='status' requires a device name"}
        return fmg_get_device_status(device=device, adom=adom)
    if by == "ha":
        if not device:
            return {"error": "by='ha' requires a device name"}
        return fmg_get_ha_status(device=device, adom=adom)
    if by == "policy":
        return fmg_get_policy_package_status(device=device, adom=adom,
                                              limit=min(limit, 25))
    return {"error": f"unsupported by={by!r}: use 'list', 'status', 'ha', or 'policy'"}


def fmg_get_device_list(adom: str = "root", limit: int = 50) -> dict[str, Any]:
    """List FortiManager-managed devices and their connection posture for an ADOM.

    Wraps `json_rpc_get` on `/dvmdb/adom/<adom>/device`, returning a compact
    posture digest per device (name/serial/ip/conn_status/conf_status/ha_mode/
    platform/os_version/last_checked). The canonical "what does FMG see right
    now, and which devices are down" call.

    Args:
      adom: FMG ADOM name (default 'root').
      limit: max devices to return (default 50).
    """
    return _fmg_get(f"/dvmdb/adom/{adom}/device",
                    {"adom": adom}, _fmg_digest_device, limit, "devices",
                    fields=_FMG_DEVICE_FIELDS)


def fmg_get_device_status(device: str, adom: str = "root") -> dict[str, Any]:
    """Get one FortiManager-managed device's posture (is it reachable?).

    Wraps `json_rpc_get` on `/dvmdb/adom/<adom>/device/<device>`. Returns the
    single-device posture digest (conn_status up/down, conf_status, ha_mode,
    last_checked). Use this first when investigating a device-down alert.

    Args:
      device: the FMG device name (e.g. 'FGT-BRANCH-04').
      adom: FMG ADOM name (default 'root').
    """
    skip = _fmg_require_managed(device, adom, "devices", "device-status lookup")
    if skip is not None:
        return skip
    return _fmg_get(f"/dvmdb/adom/{adom}/device/{device}",
                    {"adom": adom, "device": device},
                    _fmg_digest_device, 1, "devices",
                    fields=_FMG_DEVICE_FIELDS)


def fmg_get_ha_status(device: str, adom: str = "root") -> dict[str, Any]:
    """Get the HA cluster members of a FortiManager-managed device.

    Wraps `json_rpc_get` on `/dvmdb/adom/<adom>/device/<device>/ha_slave`,
    returning each cluster member (name/serial/role/conn_status). Use this to
    tell a true outage from an HA failover: if the peer is up, traffic likely
    survived.

    Args:
      device: the FMG device (cluster) name.
      adom: FMG ADOM name (default 'root').
    """
    skip = _fmg_require_managed(device, adom, "members", "HA-status lookup")
    if skip is not None:
        return skip

    def digest(m: dict[str, Any]) -> dict[str, Any]:
        def g(*keys):
            for k in keys:
                if k in m and not _is_empty(m[k]):
                    return m[k]
            return None
        row = {
            "name": g("name"),
            "serial": g("sn", "serial"),
            "role": g("role"),
            "prio": g("prio", "priority"),
            "conn_status": _fmg_conn_state(g("conn_status", "status")),
            "idx": g("idx"),
        }
        return {k: v for k, v in row.items() if not _is_empty(v)}

    return _fmg_get(f"/dvmdb/adom/{adom}/device/{device}/ha_slave",
                    {"adom": adom, "device": device}, digest, 10, "members")


def fmg_get_policy_package_status(device: str = "", adom: str = "root",
                                  limit: int = 25) -> dict[str, Any]:
    """Check policy-package install status for an ADOM (was the last push clean?).

    Wraps `json_rpc_get` on `/pm/config/adom/<adom>/_package/status`, returning
    each package's install state per device (package/device/status). Use this to
    rule a bad config push in or out as the cause of a device problem.

    Args:
      device: optional device name to filter the returned rows to.
      adom: FMG ADOM name (default 'root').
      limit: max status rows to return (default 25).
    """
    if device:
        skip = _fmg_require_managed(device, adom, "packages",
                                    "policy-package status")
        if skip is not None:
            return skip

    def digest(s: dict[str, Any]) -> dict[str, Any]:
        def g(*keys):
            for k in keys:
                if k in s and not _is_empty(s[k]):
                    return s[k]
            return None
        row = {
            "package": g("pkg", "name", "package"),
            "device": g("dev", "device", "name"),
            "status": g("status", "result"),
        }
        out = {k: v for k, v in row.items() if not _is_empty(v)}
        return out

    res = _fmg_get(f"/pm/config/adom/{adom}/_package/status",
                   {"adom": adom, "device": device}, digest, 1000, "packages")
    if device and res.get("ok"):
        rows = [r for r in res["packages"]
                if str(r.get("device", "")).lower() == device.lower()]
        res["packages"] = rows[:limit]
        res["count"] = len(res["packages"])
    elif res.get("ok"):
        res["packages"] = res["packages"][:limit]
        res["count"] = len(res["packages"])
    return res


# ---------------------------------------------------------------------------
# FortiAnalyzer -- device-centric event hunt (reuses tools_triage FAZ plumbing)
# ---------------------------------------------------------------------------
def faz_search_device_events(device: str, window: str = "6h",
                             logtype: str = "Event", adom: str = "root",
                             event_filter: str = "",
                             devid: str = "All_FortiGate",
                             limit: int = 25) -> dict[str, Any]:
    """Pull a managed device's own FortiAnalyzer logs over a recent window -- the
    device-down hunt's headline call.

    Wraps `start_and_fetch_bulk_device_logs`, constraining the search to one
    device via a `devname=` log filter and returning the standard event digest
    (ts/event_type/action/msg/...). Use it to find the last syslog a silent
    device sent and any link-down / HA / tunnel events just before it went
    quiet.

    Args:
      device: the device's hostname as it appears in FAZ logs
        (e.g. 'FGT-BRANCH-04'). Applied as a `devname=` filter -- the underlying
        op has no per-host parameter.
      window: relative lookback ('30m','2h','6h' (default),'24h','7d').
      logtype: FAZ log type (default 'Event'; e.g. 'Traffic','Attack').
        Case-insensitive; 'system'/'vpn' fold to 'Event'.
      adom: FAZ ADOM name (default 'root').
      event_filter: optional extra native FAZ filter (e.g. `level=critical`),
        ANDed with the device constraint.
      devid: FAZ device-TYPE bucket to search (default 'All_FortiGate'). Not a
        hostname -- pass that as `device`.
      limit: max digested events to return (default 25).
    """
    # This wrapper used to send `devid=<hostname>` and a lowercase logtype.
    # Both are SELECT params, so the platform rejected every call with the
    # unactionable "called with 2 invalid argument(s)" and the tool never once
    # succeeded in live use. `devid` is a device-type bucket; the hostname
    # belongs in `filter` as `devname=`, a field FAZ log rows actually carry.
    canon_logtype = _faz_logtype(logtype)
    canon_devid = _faz_devid(devid)
    echo: dict[str, Any] = {"device": device, "window": window,
                            "logtype": logtype, "adom": adom,
                            "filter": event_filter, "devid": devid}
    bad: list[tuple[str, Any, tuple[str, ...]]] = []
    if canon_logtype is None:
        bad.append(("logtype", logtype, _FAZ_LOGTYPE_VALUES))
    if canon_devid is None:
        bad.append(("devid", devid, _FAZ_DEVID_VALUES))
    if bad:
        err = _faz_select_error("start_and_fetch_bulk_device_logs", echo, bad)
        if canon_devid is None:
            # Passing a hostname as devid is the exact confusion this tool used
            # to institutionalise -- say what to do, not just what's wrong.
            err["suggestions"].append(
                "to search ONE device, leave devid as the product bucket "
                "(e.g. All_FortiGate) and pass the hostname as `device` -- it "
                "becomes a devname= filter")
        return err

    flt = f"devname={device}" if device else ""
    if event_filter:
        flt = f"{flt} and {event_filter}" if flt else event_filter

    start, end = _faz_window(window, _FAZ_LOG_TIME)
    params: dict[str, Any] = {
        "devid": canon_devid, "adom_name": adom, "logtype": canon_logtype,
        "start": start, "end": end, "limit": min(limit, 1000),
        "wait_for_search_process_to_complete": True,
    }
    if flt:
        params["filter"] = flt
    echo.update({"logtype": canon_logtype, "devid": canon_devid, "filter": flt})
    return _faz_run(
        "start_and_fetch_bulk_device_logs", params, limit, echo,
        _faz_digest_log)


def faz_search_by_serial(serial: str, window: str = "6h",
                         logtype: str = "Event", adom: str = "root",
                         devid: str = "All_FortiGate",
                         limit: int = 25) -> dict[str, Any]:
    """Pull FortiAnalyzer logs for a device by serial number -- the pivot when the
    name is ambiguous or the device was re-registered.

    Wraps `start_and_fetch_bulk_device_logs` with a `devid` serial filter,
    returning the standard event digest. Use after `fmg_get_device_status`
    surfaces the serial, when a name-based FAZ search comes back thin.

    Args:
      serial: the device serial number (FMG `sn`).
      window: relative lookback ('30m','2h','6h' (default),'24h','7d').
      logtype: FAZ log type (default 'Event'). Case-insensitive.
      adom: FAZ ADOM name (default 'root').
      devid: FAZ device-TYPE bucket to search (default 'All_FortiGate').
      limit: max digested events to return (default 25).
    """
    # Same defect as faz_search_device_events: the serial went into the `devid`
    # SELECT param, which only accepts product buckets. In FAZ log ROWS `devid`
    # IS the serial, so the serial belongs in `filter`.
    canon_logtype = _faz_logtype(logtype)
    canon_devid = _faz_devid(devid)
    echo: dict[str, Any] = {"serial": serial, "window": window,
                            "logtype": logtype, "adom": adom, "devid": devid}
    bad: list[tuple[str, Any, tuple[str, ...]]] = []
    if canon_logtype is None:
        bad.append(("logtype", logtype, _FAZ_LOGTYPE_VALUES))
    if canon_devid is None:
        bad.append(("devid", devid, _FAZ_DEVID_VALUES))
    if bad:
        return _faz_select_error("start_and_fetch_bulk_device_logs", echo, bad)

    flt = f"devid={serial}" if serial else ""
    start, end = _faz_window(window, _FAZ_LOG_TIME)
    params: dict[str, Any] = {
        "devid": canon_devid, "adom_name": adom, "logtype": canon_logtype,
        "start": start, "end": end, "limit": min(limit, 1000),
        "wait_for_search_process_to_complete": True,
    }
    if flt:
        params["filter"] = flt
    echo.update({"logtype": canon_logtype, "devid": canon_devid, "filter": flt})
    return _faz_run(
        "start_and_fetch_bulk_device_logs", params, limit, echo,
        _faz_digest_log)


def faz_event_summary(device: str, window: str = "6h", logtype: str = "Event",
                      adom: str = "root", devid: str = "All_FortiGate",
                      limit: int = 200) -> dict[str, Any]:
    """Summarize a device's recent FortiAnalyzer events by type/action/level --
    the "what's the shape of the noise" view before drilling in.

    Runs the same bulk-log search as `faz_search_device_events` but, instead of
    returning rows, returns rollup counts (by event_type, action, level) plus
    the first/last event timestamps. Cheap way to spot e.g. a burst of
    link-monitor failures right before silence without paying for every row.

    Args:
      device: the device's hostname as it appears in FAZ logs. Applied as a
        `devname=` filter (see `faz_search_device_events`).
      window: relative lookback (default '6h').
      logtype: FAZ log type (default 'Event'). Case-insensitive.
      adom: FAZ ADOM name (default 'root').
      devid: FAZ device-TYPE bucket (default 'All_FortiGate'). Not a hostname.
      limit: max raw events to scan for the rollup (default 200).
    """
    # Delegates, so it inherits the select-param normalisation + preflight
    # rather than carrying a second copy of the same enum knowledge.
    res = faz_search_device_events(device, window=window, logtype=logtype,
                                   adom=adom, devid=devid, limit=limit)
    if not res.get("ok"):
        return res
    events = res.get("events", [])

    def tally(field: str) -> dict[str, int]:
        out: dict[str, int] = {}
        for e in events:
            v = e.get(field)
            if not _is_empty(v):
                out[str(v)] = out.get(str(v), 0) + 1
        return dict(sorted(out.items(), key=lambda kv: -kv[1]))

    ts = [e.get("ts") for e in events if not _is_empty(e.get("ts"))]
    return {
        "ok": True, "op": "faz_event_summary",
        "query": {"device": device, "window": window, "logtype": logtype,
                  "adom": adom},
        "scanned": len(events),
        "first_ts": min(ts) if ts else None,
        "last_ts": max(ts) if ts else None,
        "by_event_type": tally("event_type"),
        "by_action": tally("action"),
    }
