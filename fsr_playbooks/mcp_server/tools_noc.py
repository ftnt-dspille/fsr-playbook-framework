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

from ._shared import mcp
from .tools_triage import (
    _envelope,
    _faz_digest_log,
    _faz_run,
    _faz_window,
    _is_empty,
    _FAZ_LOG_TIME,
)

# FortiManager connector to drive. The json-rpc variant and all FMG builds
# (fortinet-fortimanager, *_dev, *-json-rpc) expose the
# json_rpc_get op this module relies on, so this is the only thing to change to
# retarget a differently-named build.
_FMG_CONNECTOR = "fortinet-fortimanager-json-rpc"


# ---------------------------------------------------------------------------
# FortiManager — device posture (all read-only via json_rpc_get)
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
    DISTINCT from 'down' (was up, now unreachable) — conflating them misleads a
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


#: dvmdb device fields the device digest needs — projected at the FMG query so
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
    from .tools_execution import run_op  # lazy: avoid import cycle at load

    params: dict[str, Any] = {"url": url}
    if fields:
        # Project at the source so name/sn/ip stay in the row and the payload
        # is small. Belt-and-suspenders with summarize=False below.
        params["data"] = {"fields": fields}
    # summarize=False: this wrapper digests + bounds the rows itself; run_op's
    # generic truncation drops dict keys past the first 40 (stripping
    # late-ordered FMG fields like name/sn/ip) and caps the list to 5 items.
    res = run_op(_FMG_CONNECTOR, "json_rpc_get", params,
                 confirm=True, summarize=False)
    if not isinstance(res, dict) or not res.get("ok"):
        return {"ok": False, "op": "json_rpc_get", "query": echo,
                "code": (res or {}).get("status") or (res or {}).get("code")
                or "fmg_op_failed",
                "message": (res or {}).get("message")
                or "FortiManager op failed"}
    rows = [d for d in (digest(r) for r in _fmg_rows(res.get("data"))) if d]
    env = _envelope("json_rpc_get", echo, rows, limit)
    # _envelope keys the list as `events`; re-key to the domain noun.
    env[key] = env.pop("events")
    return env


@mcp.tool()
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


@mcp.tool()
def fmg_get_device_status(device: str, adom: str = "root") -> dict[str, Any]:
    """Get one FortiManager-managed device's posture (is it reachable?).

    Wraps `json_rpc_get` on `/dvmdb/adom/<adom>/device/<device>`. Returns the
    single-device posture digest (conn_status up/down, conf_status, ha_mode,
    last_checked). Use this first when investigating a device-down alert.

    Args:
      device: the FMG device name (e.g. 'FGT-BRANCH-04').
      adom: FMG ADOM name (default 'root').
    """
    return _fmg_get(f"/dvmdb/adom/{adom}/device/{device}",
                    {"adom": adom, "device": device},
                    _fmg_digest_device, 1, "devices",
                    fields=_FMG_DEVICE_FIELDS)


@mcp.tool()
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


@mcp.tool()
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
# FortiAnalyzer — device-centric event hunt (reuses tools_triage FAZ plumbing)
# ---------------------------------------------------------------------------
@mcp.tool()
def faz_search_device_events(device: str, window: str = "6h",
                             logtype: str = "event", adom: str = "root",
                             event_filter: str = "",
                             limit: int = 25) -> dict[str, Any]:
    """Pull a managed device's own FortiAnalyzer logs over a recent window — the
    device-down hunt's headline call.

    Wraps `start_and_fetch_bulk_device_logs` scoped to a single `devid`,
    returning the standard event digest (ts/event_type/action/msg/...). Use it
    to find the last syslog a silent device sent and any link-down / HA / tunnel
    events just before it went quiet.

    Args:
      device: FAZ devid / device name (e.g. 'FGT-BRANCH-04').
      window: relative lookback ('30m','2h','6h' (default),'24h','7d').
      logtype: FAZ log type (default 'event'; e.g. 'traffic','vpn','system').
      adom: FAZ ADOM name (default 'root').
      event_filter: optional native FAZ filter (e.g. `level=critical`).
      limit: max digested events to return (default 25).
    """
    start, end = _faz_window(window, _FAZ_LOG_TIME)
    params: dict[str, Any] = {
        "devid": device, "adom_name": adom, "logtype": logtype,
        "start": start, "end": end, "limit": min(limit, 1000),
        "wait_for_search_process_to_complete": True,
    }
    if event_filter:
        params["filter"] = event_filter
    return _faz_run(
        "start_and_fetch_bulk_device_logs", params, limit,
        {"device": device, "window": window, "logtype": logtype,
         "adom": adom, "filter": event_filter},
        _faz_digest_log)


@mcp.tool()
def faz_search_by_serial(serial: str, window: str = "6h",
                         logtype: str = "event", adom: str = "root",
                         limit: int = 25) -> dict[str, Any]:
    """Pull FortiAnalyzer logs for a device by serial number — the pivot when the
    name is ambiguous or the device was re-registered.

    Wraps `start_and_fetch_bulk_device_logs` with a `devid` serial filter,
    returning the standard event digest. Use after `fmg_get_device_status`
    surfaces the serial, when a name-based FAZ search comes back thin.

    Args:
      serial: the device serial number (FMG `sn`).
      window: relative lookback ('30m','2h','6h' (default),'24h','7d').
      logtype: FAZ log type (default 'event').
      adom: FAZ ADOM name (default 'root').
      limit: max digested events to return (default 25).
    """
    start, end = _faz_window(window, _FAZ_LOG_TIME)
    return _faz_run(
        "start_and_fetch_bulk_device_logs",
        {"devid": serial, "adom_name": adom, "logtype": logtype,
         "start": start, "end": end, "limit": min(limit, 1000),
         "wait_for_search_process_to_complete": True},
        limit, {"serial": serial, "window": window, "logtype": logtype,
                "adom": adom},
        _faz_digest_log)


@mcp.tool()
def faz_event_summary(device: str, window: str = "6h", logtype: str = "event",
                      adom: str = "root", limit: int = 200) -> dict[str, Any]:
    """Summarize a device's recent FortiAnalyzer events by type/action/level —
    the "what's the shape of the noise" view before drilling in.

    Runs the same bulk-log search as `faz_search_device_events` but, instead of
    returning rows, returns rollup counts (by event_type, action, level) plus
    the first/last event timestamps. Cheap way to spot e.g. a burst of
    link-monitor failures right before silence without paying for every row.

    Args:
      device: FAZ devid / device name.
      window: relative lookback (default '6h').
      logtype: FAZ log type (default 'event').
      adom: FAZ ADOM name (default 'root').
      limit: max raw events to scan for the rollup (default 200).
    """
    res = faz_search_device_events(device, window=window, logtype=logtype,
                                   adom=adom, limit=limit)
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
