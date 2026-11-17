"""What the CALLING analyst may see: connector configurations by team.

The connector runs as a service account, so every box read the agent makes
sees every configuration. FortiSOAR scopes a configuration to teams, and the
agent must not offer, verify against or run on a configuration its analyst's
teams cannot see (live: a classroom box with one FortiAIGate config per
student team; the agent saw all of them).

The connector binds the caller (the gateway's X-User people uuid) with
`set_caller` for the length of one operation. With no caller bound -- a
playbook step, the CLI, tests -- nothing is filtered, as before. With a caller
bound, an unreadable team or configuration listing hides every team-owned
configuration: fail closed. A configuration with no teams is visible to all.
"""
from __future__ import annotations

import contextvars
import time
from typing import Any

_CALLER: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "fsr_caller_uuid", default=None)

_TTL_S = 60.0
_TEAMS_CACHE: dict[str, tuple[float, frozenset[str]]] = {}
_CONFIG_TEAMS: dict[str, Any] = {"ts": 0.0, "by_id": None}


def set_caller(uuid: str | None):
    """Bind the calling analyst's people uuid. Returns a reset token."""
    return _CALLER.set((uuid or "").rsplit("/", 1)[-1] or None)


def reset_caller(token) -> None:
    try:
        _CALLER.reset(token)
    except Exception:  # noqa: BLE001
        pass


def current_caller() -> str | None:
    return _CALLER.get()


def _uuid(iri: Any) -> str:
    if isinstance(iri, dict):
        iri = iri.get("@id") or iri.get("uuid") or ""
    return str(iri or "").rstrip("/").rsplit("/", 1)[-1]


def caller_teams(client) -> frozenset[str] | None:
    """Team uuids of the bound caller; None when no caller is bound (no
    filtering). An empty set when the lookup fails (fail closed)."""
    who = _CALLER.get()
    if not who:
        return None
    hit = _TEAMS_CACHE.get(who)
    if hit and time.time() - hit[0] < _TTL_S:
        return hit[1]
    teams: frozenset[str] = frozenset()
    try:
        r = client.session.get(
            client.base_url + f"/api/3/people/{who}?$relationships=true",
            verify=client.verify_ssl)
        if getattr(r, "status_code", 0) == 200:
            teams = frozenset(_uuid(t) for t in (r.json().get("teams") or []))
    except Exception:  # noqa: BLE001 -- fail closed
        teams = frozenset()
    _TEAMS_CACHE[who] = (time.time(), teams)
    return teams


def _config_teams(client) -> dict[str, frozenset[str]] | None:
    """{config_id: team uuids} for every configuration on the box. Reads only
    the id and teams -- the listing also carries each config body (secrets),
    which is never kept."""
    if (_CONFIG_TEAMS["by_id"] is not None
            and time.time() - _CONFIG_TEAMS["ts"] < _TTL_S):
        return _CONFIG_TEAMS["by_id"]
    try:
        r = client.session.get(
            client.base_url + "/api/integration/configuration/?format=json&limit=1000",
            verify=client.verify_ssl)
        if getattr(r, "status_code", 0) != 200:
            return None
        body = r.json()
        items = body.get("data", body.get("results")) if isinstance(body, dict) else body
        by_id = {}
        for it in items or []:
            if isinstance(it, dict) and it.get("config_id"):
                by_id[str(it["config_id"])] = frozenset(
                    _uuid(t) for t in (it.get("teams") or []))
    except Exception:  # noqa: BLE001
        return None
    _CONFIG_TEAMS.update(ts=time.time(), by_id=by_id)
    return by_id


def _cfg_id(c: Any) -> str:
    if isinstance(c, dict):
        return str(c.get("config_id") or c.get("uuid") or c.get("id") or "")
    return str(c or "")


def filter_rows(client, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """`rows` (connector_details shape) with each connector's configuration
    list cut to what the bound caller's teams can see. A connector left with
    no visible configuration is dropped: to this analyst it is not
    configured. Returns copies; the shared cache is never mutated."""
    mine = caller_teams(client)
    if mine is None:
        return rows
    owners = _config_teams(client)
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        cfgs = row.get("configuration")
        if not isinstance(cfgs, list) or not cfgs:
            out.append(row)
            continue
        keep = []
        for c in cfgs:
            teams = None if owners is None else owners.get(_cfg_id(c))
            # Unknown owner while a caller is bound: hide (fail closed).
            if teams is None:
                continue
            if not teams or teams & mine:
                keep.append(c)
        if keep:
            out.append({**row, "configuration": keep, "config_count": len(keep)})
    return out
