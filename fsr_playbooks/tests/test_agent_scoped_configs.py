"""Config names and agents in YAML resolve to the ids of the box they compile for.

A connector config can live on the hub or on a remote agent. YAML names it
(`config: Lab Active Directory`, `on_remote: branch-agent`); the compiler turns
those into the agent's ``agentId`` and the UUID of the config ON THAT AGENT, and
refuses a step whose config does not exist where the step runs (on the box it
hangs or fails INTEGRATION-12). Decompile reverses both.
"""
from __future__ import annotations

import shutil
import sqlite3

import pytest

from fsr_playbooks._db import PACKAGED_SLIM_DB
from fsr_playbooks.compiler import compile_yaml
from fsr_playbooks.compiler.decompiler import _names_for_ids
from fsr_playbooks.mcp_server.tools_analysis import _branches_from_routes, _next_step
from fsr_playbooks.warmup import apply_migrations

AGENT = "a" * 32
SELF = "5" * 32


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "box.db"
    shutil.copy(PACKAGED_SLIM_DB, path)
    conn = sqlite3.connect(path)
    apply_migrations(conn)
    conn.execute("DELETE FROM connector_configs")
    conn.executemany(
        "INSERT INTO connector_configs (connector, config_name, config_id, is_default, agent_id) "
        "VALUES (?, ?, ?, ?, ?)",
        [
            ("activedirectory", "Lab AD", "11111111-1111-1111-1111-111111111111", 1, AGENT),
            ("activedirectory", "__default__", "11111111-1111-1111-1111-111111111111", 1, AGENT),
            ("servicenow", "Lab SNOW", "22222222-2222-2222-2222-222222222222", 1, ""),
            ("servicenow", "__default__", "22222222-2222-2222-2222-222222222222", 1, ""),
        ],
    )
    conn.executemany("INSERT INTO agents (name, agent_id, is_self) VALUES (?, ?, ?)",
                     [("branch-agent", AGENT, 0), ("self", SELF, 1)])
    conn.commit()
    conn.close()
    return path


def _yaml(step: str, first: str = "lookup") -> str:
    return f"""
collection: T
playbooks:
- name: P
  steps:
  - type: start
    name: Start
    next: {first}
{step}
"""


AD_STEP = """\
  - type: connector
    name: Lookup
    connector: activedirectory
    operation: global_search
    config: Lab AD
    params: {{search_object: User, search_attr_name: SamAccount Name, search_attr_value: jdoe}}
{extra}"""


def _step(res, name):
    wf = res.fsr_json["data"][0]["workflows"][0]
    return next(s for s in wf["steps"] if s["name"] == name)["arguments"]


def test_agent_name_and_config_name_resolve_to_that_agents_ids(db):
    res = compile_yaml(_yaml(AD_STEP.format(extra="    on_remote: branch-agent\n")), db)
    assert res.ok, [e for e in res.errors if e.severity != "warning"]
    args = _step(res, "Lookup")
    assert args["agent"] == AGENT
    assert args["config"] == "11111111-1111-1111-1111-111111111111"


def test_config_only_on_one_agent_runs_there_without_on_remote(db):
    res = compile_yaml(_yaml(AD_STEP.format(extra="")), db)
    assert res.ok, [e for e in res.errors if e.severity != "warning"]
    args = _step(res, "Lookup")
    assert args["agent"] == AGENT
    assert args["config"] == "11111111-1111-1111-1111-111111111111"


def test_unknown_agent_name_is_refused(db):
    res = compile_yaml(_yaml(AD_STEP.format(extra="    on_remote: no-such-agent\n")), db)
    assert any("unknown agent 'no-such-agent'" in e.message for e in res.errors)


def test_hub_config_name_resolves_with_no_agent(db):
    step = """\
  - type: connector
    name: Find
    connector: servicenow
    operation: search_record
    config: Lab SNOW
    params: {table_name: incident, column_name: number, value: INC1}
"""
    res = compile_yaml(_yaml(step, "find"), db)
    assert res.ok, [e for e in res.errors if e.severity != "warning"]
    args = _step(res, "Find")
    assert args["config"] == "22222222-2222-2222-2222-222222222222"
    assert "agent" not in args


def test_decompile_writes_names_for_ids(db):
    conn = sqlite3.connect(db)
    out = {"agent": AGENT, "pickFromTenant": False}
    args = {"config": "11111111-1111-1111-1111-111111111111"}
    _names_for_ids(out, args, conn)
    assert out == {"on_remote": "branch-agent"}
    assert args == {"config": "Lab AD"}
    # The hub's own agent id means "run locally": dropped, config named.
    out, args = {"agent": SELF}, {"config": "22222222-2222-2222-2222-222222222222"}
    _names_for_ids(out, args, conn)
    assert out == {} and args == {"config": "Lab SNOW"}
    conn.close()


def test_analyzer_follows_conditions_routes():
    steps = [{"id": "gate", "type": "decision", "arguments": {"conditions": [
        {"display": "yes", "when": "{{ true }}", "next": "a"},
        {"display": "Else", "default": True, "next": "b"}]}}]
    _branches_from_routes(steps)
    assert steps[0]["branches"] == {"yes": "a", "Else": "b"}
    assert _next_step(steps[0], "Else", {}) == "b"


def test_agent_name_is_refused_when_agents_are_not_warmed(db):
    # An unresolved name must never reach the wire: the hub cannot route it
    # ("No agent found with provided agent id" 404, or the step never returns).
    conn = sqlite3.connect(db)
    conn.execute("DELETE FROM agents")
    conn.commit()
    conn.close()
    res = compile_yaml(_yaml(AD_STEP.format(extra="    on_remote: branch-agent\n")), db)
    assert not res.ok
    assert any("agent 'branch-agent'" in e.message and "not warmed" in e.message
               for e in res.errors if e.severity != "warning")


def test_agent_id_passes_when_agents_are_not_warmed(db):
    conn = sqlite3.connect(db)
    conn.execute("DELETE FROM agents")
    conn.commit()
    conn.close()
    res = compile_yaml(_yaml(AD_STEP.format(extra=f"    on_remote: {AGENT}\n")), db)
    assert _step(res, "Lookup")["agent"] == AGENT
