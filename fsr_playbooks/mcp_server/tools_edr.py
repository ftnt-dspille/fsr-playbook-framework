"""MCP tools: what the EDR knows about one host.

Live (GA rehearsal, first-look triage of a FortiEDR alert): the model spent ten
serial rounds finding its way through FortiEDR -- two keyword searches for an
operation that matched nothing, a listing of all 31 operations, five event
counts with different filters, a schema read after the call, and an event list
refused over its date format -- to learn two things: is this host a known
collector, and what else has it raised. `edr_host` answers both in one call.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fsr_playbooks.mcp_server import _shared
from fsr_playbooks.mcp_server._shared import mcp
from fsr_playbooks.mcp_server.tools_triage import _record_hunt_step

#: Collector fields worth the model's attention; `systemInformation` alone is
#: kilobytes of CPU caches and memory sizes.
_COLLECTOR_FIELDS = ("id", "name", "ipAddress", "state", "lastSeenTime",
                     "loggedUsers", "operatingSystem", "osFamily",
                     "collectorGroupName", "organization", "version",
                     "macAddresses", "stateAdditionalInfo")
_WINDOW_DAYS = {"d": 1, "w": 7}
#: FortiEDR refuses any other datetime shape (HTTP 400, "time data ... does not
#: match format '%Y-%m-%dT%H:%M:%S.%fZ'").
_EDR_TIME_FMT = "%Y-%m-%dT%H:%M:%S.000Z"
# A tenant's whole collector roster when the lookup is by name: FortiEDR's
# collector list filters by IP but not by name.
_ROSTER_PAGE = 1000


def _edr_connector() -> str:
    return _shared.resolve_source_connector("fortiedr")


def _window_days(window: str) -> int:
    w = str(window or "").strip().lower()
    if len(w) >= 2 and w[:-1].isdigit() and w[-1] in _WINDOW_DAYS:
        return max(1, int(w[:-1]) * _WINDOW_DAYS[w[-1]])
    return 90


def _run(op: str, params: dict[str, Any]) -> dict[str, Any]:
    from fsr_playbooks.execution_api import mute_recording, run_op
    # The implementation of a named pivot tool, not an op the agent chose:
    # keep it off the build trace (see tools_triage._siem_run).
    with mute_recording():
        res = run_op(_edr_connector(), op, params)
    return res if isinstance(res, dict) else {"ok": False, "message": str(res)}


def _collector(row: dict[str, Any]) -> dict[str, Any]:
    return {k: row[k] for k in _COLLECTOR_FIELDS if row.get(k) not in (None, "", [])}


def _rows(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    if isinstance(data, dict):
        for key in ("samples", "data", "results", "collectors", "events"):
            if isinstance(data.get(key), list):
                return [r for r in data[key] if isinstance(r, dict)]
    return []


def _error(step: str, res: dict[str, Any], echo: dict[str, Any]) -> dict[str, Any]:
    out = {"ok": False, "op": "edr_host", "query": echo, "step": step,
           "code": res.get("code") or res.get("status") or "edr_op_failed",
           "message": res.get("message") or "FortiEDR request failed"}
    for k in ("issues", "suggestions"):
        if res.get(k):
            out[k] = res[k]
    return out


def _events(device: str, days: int, limit: int) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    res = _run("get_event_list_extended", {
        "device": device,
        "lastSeenFrom": (now - timedelta(days=days)).strftime(_EDR_TIME_FMT),
        "lastSeenTo": now.strftime(_EDR_TIME_FMT),
    })
    if not res.get("ok"):
        return res
    data = res.get("data")
    rows = _rows(data)
    out: dict[str, Any] = {"ok": True, "count": len(rows), "samples": rows[:limit]}
    if isinstance(data, dict) and data.get("_digest"):
        # The framework already digested a long list: keep its totals and
        # facets (users, actions, rules, severities) -- the counts the model
        # used to ask for one filter at a time.
        out["count"] = data.get("count", len(rows))
        for k in ("time_window", "facets"):
            if data.get(k):
                out[k] = data[k]
    return out


@mcp.tool()
def edr_host(host: str = "", ip: str = "", window: str = "90d",
             limit: int = 10) -> dict[str, Any]:
    """What FortiEDR knows about one host, in one call: its collector (state, last seen, logged-on users, OS, organization) and its security events over a recent window (total, who, what action, which rules, plus the latest few). Pass the host name, the IP, or both. Use it before deciding whether a host is known, quiet, or already compromised; its `collector.name` is the exact device name an isolate action needs.

    Args:
      host: the device name as FortiEDR knows it (e.g. the alert's host).
      ip: the host's IP; used to find the collector when the name is unknown.
      window: event lookback in days or weeks, e.g. ``30d``, ``12w`` (default ``90d``).
      limit: how many of the latest events to return in full (default 10).
    """
    host, ip = (host or "").strip(), (ip or "").strip()
    echo = {"host": host, "ip": ip, "window": window}
    if not host and not ip:
        return {"ok": False, "op": "edr_host", "code": "missing_host",
                "message": "Give the host name, its IP, or both."}

    params: dict[str, Any] = ({"ips": ip} if ip
                              else {"itemsPerPage": _ROSTER_PAGE})
    res = _run("get_collector_list", params)
    if not res.get("ok"):
        return _error("collector", res, echo)
    roster = _rows(res.get("data"))
    if host:
        named = [r for r in roster if str(r.get("name", "")).lower() == host.lower()]
        # An IP match under another name is still the answer when the name
        # finds nothing (DHCP, a renamed host); say so instead of hiding it.
        roster = named or (roster if ip else [])
    collectors = [_collector(r) for r in roster]
    out: dict[str, Any] = {"ok": True, "op": "edr_host", "query": echo,
                           "known_to_edr": bool(collectors),
                           "collectors": collectors}
    if host and collectors and all(c.get("name", "").lower() != host.lower()
                                   for c in collectors):
        out["note"] = (f"No collector is named {host!r}; these match the IP "
                       f"{ip!r} instead.")

    device = collectors[0].get("name") if collectors else host
    if device:
        ev = _events(device, _window_days(window), max(1, int(limit or 10)))
        out["events"] = ev if ev.get("ok") else _error("events", ev, echo)
    _record_hunt_step("edr_host", echo, out)
    return out
