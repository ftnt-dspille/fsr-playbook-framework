"""The agent sees only the connector configurations its analyst's teams can.

Live (classroom box): one FortiAIGate config per student team, and the agent,
running as the connector's service account, saw and could run on all of them.
The connector binds the analyst (X-User); `_configured_rows` -- the source for
run_op's config resolution, the offer gate and the configured listing -- keeps
only configs owned by one of the analyst's teams, or by no team.
"""
from __future__ import annotations

import pytest

from fsr_playbooks.mcp_server import caller_scope as cs
from fsr_playbooks.mcp_server import tools_execution as te

ROWS = [
    {"name": "fortinet-fortiaigate", "version": "1.0.0", "configuration": [
        {"config_id": "c4", "name": "student04 FortiAIGate", "default": False},
        {"config_id": "c10", "name": "student10 FortiAIGate", "default": True},
    ]},
    {"name": "smtp", "version": "1.0.0", "configuration": [
        {"config_id": "shared", "name": "localhost-postfix", "default": True}]},
    {"name": "only-team10", "version": "1.0.0", "configuration": [
        {"config_id": "x10", "name": "t10 only", "default": True}]},
]
CONFIG_TEAMS = [
    {"config_id": "c4", "teams": ["/api/3/teams/t04"], "config": {"secret": "s"}},
    {"config_id": "c10", "teams": ["/api/3/teams/t10"], "config": {"secret": "s"}},
    {"config_id": "shared", "teams": []},
    {"config_id": "x10", "teams": ["/api/3/teams/t10"]},
]
PEOPLE = {"u04": ["/api/3/teams/t04"], "u10": ["/api/3/teams/t10"]}


class _Resp:
    def __init__(self, code, body):
        self.status_code, self._b = code, body

    def json(self):
        return self._b


class _Session:
    def __init__(self, fail_people=False, fail_configs=False):
        self.fail_people, self.fail_configs = fail_people, fail_configs

    def get(self, url, verify=None):
        if "/api/3/people/" in url:
            who = url.split("/api/3/people/")[1].split("?")[0]
            if self.fail_people or who not in PEOPLE:
                return _Resp(404, {})
            return _Resp(200, {"teams": PEOPLE[who]})
        if "/api/integration/configuration/" in url:
            return _Resp(500, {}) if self.fail_configs else _Resp(200, CONFIG_TEAMS)
        raise AssertionError(url)


class _Client:
    base_url, verify_ssl = "https://soar.example", False

    def __init__(self, **kw):
        self.session = _Session(**kw)


@pytest.fixture(autouse=True)
def _rows(monkeypatch):
    monkeypatch.setattr(te, "_all_configured_rows", lambda c, force=False: ROWS)
    cs._TEAMS_CACHE.clear()
    cs._CONFIG_TEAMS.update(ts=0.0, by_id=None)


def _names(rows):
    return {r["name"]: [c["name"] for c in r["configuration"]] for r in rows}


def _as(uuid, **kw):
    tok = cs.set_caller(uuid)
    try:
        return _names(te._configured_rows(_Client(**kw)))
    finally:
        cs.reset_caller(tok)


def test_no_caller_bound_sees_everything():
    assert _names(te._configured_rows(_Client())) == _names(ROWS)


@pytest.mark.parametrize("who,expected", [
    ("u04", {"fortinet-fortiaigate": ["student04 FortiAIGate"],
             "smtp": ["localhost-postfix"]}),
    ("u10", {"fortinet-fortiaigate": ["student10 FortiAIGate"],
             "smtp": ["localhost-postfix"], "only-team10": ["t10 only"]}),
    # People IRI form, as the gateway may send it.
    ("/api/3/people/u04", {"fortinet-fortiaigate": ["student04 FortiAIGate"],
                           "smtp": ["localhost-postfix"]}),
])
def test_caller_sees_own_team_and_unowned_configs(who, expected):
    assert _as(who) == expected


@pytest.mark.parametrize("who,kw", [
    ("nobody", {}),                     # unknown / tampered caller
    ("u04", {"fail_people": True}),     # team lookup fails
    ("u04", {"fail_configs": True}),    # config ownership unreadable
])
def test_fails_closed_to_no_team_owned_configs(who, kw):
    got = _as(who, **kw)
    assert "fortinet-fortiaigate" not in got and "only-team10" not in got
    if kw.get("fail_configs"):
        assert "smtp" not in got        # owner unknown: hide even unowned
    else:
        assert got == {"smtp": ["localhost-postfix"]}


def test_shared_cache_is_not_mutated():
    _as("u04")
    assert len(ROWS[0]["configuration"]) == 2


def test_run_op_refuses_another_teams_config_by_name(monkeypatch):
    tok = cs.set_caller("u04")
    try:
        err = te._preflight_connector(_Client(), "fortinet-fortiaigate",
                                      "student10 FortiAIGate")
    finally:
        cs.reset_caller(tok)
    assert err is not None and err["code"] == "config_not_available"
    assert "student10" not in " ".join(err.get("suggestions") or [])
    assert any("student04 FortiAIGate" in s for s in err["suggestions"])


def test_offer_gate_uses_the_scoped_names(monkeypatch):
    from fsr_playbooks.mcp_server import tools_emit
    import probes._env as env
    monkeypatch.setattr(env, "get_client", lambda: _Client())
    tok = cs.set_caller("u04")
    try:
        names = tools_emit._box_config_names()
    finally:
        cs.reset_caller(tok)
    assert names["fortinet-fortiaigate"] == ["student04 FortiAIGate"]
