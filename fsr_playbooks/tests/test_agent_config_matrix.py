"""Every agent x config combination resolves to the config where the step runs.

Layout: the hub and two agents. Each holds AD configs, some sharing a name with
another location, and agent A holds two configs. A step's `config:` name must
resolve to the UUID of that name ON THE AGENT the step runs on; no config name
may fall back to another location's config of the same name.
"""
from __future__ import annotations

import shutil
import sqlite3

import pytest

from fsr_playbooks._db import PACKAGED_SLIM_DB
from fsr_playbooks.compiler import compile_yaml
from fsr_playbooks.warmup import apply_migrations

A, B, SELF = "a" * 32, "b" * 32, "5" * 32
U = lambda n: f"{n:08d}-0000-0000-0000-000000000000"  # noqa: E731

# (connector, name, uuid, is_default, agent)
CONFIGS = [
    ("activedirectory", "Shared AD", U(1), 0, ""),      # hub
    ("activedirectory", "Hub Only", U(2), 1, ""),
    ("activedirectory", "Shared AD", U(3), 1, A),       # agent A: two configs
    ("activedirectory", "A Second", U(4), 0, A),
    ("activedirectory", "Shared AD", U(5), 0, B),       # agent B
    ("activedirectory", "B Only", U(6), 1, B),
]


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "box.db"
    shutil.copy(PACKAGED_SLIM_DB, path)
    conn = sqlite3.connect(path)
    apply_migrations(conn)
    conn.execute("DELETE FROM connector_configs")
    rows = list(CONFIGS)
    for agent in ("", A, B):
        default = next(c[2] for c in CONFIGS if c[4] == agent and c[3])
        rows.append(("activedirectory", "__default__", default, 1, agent))
    conn.executemany("INSERT INTO connector_configs VALUES (?, ?, ?, ?, ?)", rows)
    conn.executemany("INSERT INTO agents (name, agent_id, is_self) VALUES (?, ?, ?)",
                     [("agent-a", A, 0), ("agent-b", B, 0), ("self", SELF, 1)])
    conn.commit()
    conn.close()
    return path


def _compile(db, on_remote: str | None, config: str | None):
    lines = ["  - type: connector", "    name: Lookup", "    connector: activedirectory",
             "    operation: global_search"]
    if on_remote is not None:
        lines.append(f"    on_remote: {on_remote}")
    if config is not None:
        lines.append(f"    config: '{config}'")
    lines.append("    params: {search_object: User, search_attr_name: SamAccount Name, "
                 "search_attr_value: jdoe}")
    y = ("collection: T\nplaybooks:\n- name: P\n  steps:\n  - type: start\n    name: Start\n"
         "    next: lookup\n" + "\n".join(lines) + "\n")
    res = compile_yaml(y, db)
    errs = [e for e in res.errors if e.severity != "warning"]
    args = None
    if res.fsr_json:
        wf = res.fsr_json["data"][0]["workflows"][0]
        args = next(s for s in wf["steps"] if s["name"] == "Lookup")["arguments"]
    return res.ok and not errs, args, errs


@pytest.mark.parametrize("on_remote,config,agent,uuid", [
    # same name in three places: each location gets its own
    (None, "Shared AD", None, U(1)),
    ("agent-a", "Shared AD", A, U(3)),
    ("agent-b", "Shared AD", B, U(5)),
    # agent given by id resolves the same as by name
    (A, "Shared AD", A, U(3)),
    # two configs on one agent: each name picks its own
    ("agent-a", "A Second", A, U(4)),
    # no config: that location's default, never another's
    (None, None, None, U(2)),
    ("agent-a", None, A, U(3)),
    ("agent-b", None, B, U(6)),
    # a UUID passes through untouched
    ("agent-a", U(4), A, U(4)),
    # no on_remote: a name only on one agent runs on that agent
    (None, "A Second", A, U(4)),
    (None, "B Only", B, U(6)),
    # the hub's own agent name runs locally
    ("self", "Hub Only", None, U(2)),
])
def test_config_resolves_on_the_agent_the_step_runs_on(db, on_remote, config, agent, uuid):
    ok, args, errs = _compile(db, on_remote, config)
    assert ok, errs
    assert args.get("agent") == agent
    assert args["config"] == uuid


@pytest.mark.parametrize("on_remote,config,where", [
    ("agent-a", "B Only", "agent-b"),       # another agent's config
    ("agent-b", "A Second", "agent-a"),
    ("agent-a", "Hub Only", "self"),        # hub config on an agent step
])
def test_config_from_another_location_is_refused_and_named(db, on_remote, config, where):
    ok, _, errs = _compile(db, on_remote, config)
    assert not ok
    assert any("does not exist on" in e.message and where in e.message for e in errs), errs


def test_unknown_agent_name_is_refused(db):
    ok, _, errs = _compile(db, "agent-c", "Shared AD")
    assert not ok and any("unknown agent 'agent-c'" in e.message for e in errs)


def test_name_on_hub_and_agents_defaults_to_hub_with_a_warning(db):
    ok, args, _ = _compile(db, None, "Shared AD")
    assert ok and args.get("agent") is None and args["config"] == U(1)
    res_warn = [e for e in _warnings(db, None, "Shared AD")]
    assert any("exists on the hub and on agent-a, agent-b; using the hub's" in e.message
               and e.suggestion == "set on_remote: agent-a to run it on that agent"
               for e in res_warn), res_warn


def test_name_on_several_agents_and_not_the_hub_is_refused(db):
    conn = sqlite3.connect(db)
    conn.execute("DELETE FROM connector_configs WHERE agent_id = '' AND config_name = 'Shared AD'")
    conn.commit()
    conn.close()
    ok, _, errs = _compile(db, None, "Shared AD")
    assert not ok
    assert any("exists on several agents (agent-a, agent-b) and not on the hub" in e.message
               for e in errs), errs


def _warnings(db, on_remote, config):
    lines = ["  - type: connector", "    name: Lookup", "    connector: activedirectory",
             "    operation: global_search", f"    config: '{config}'",
             "    params: {search_object: User, search_attr_name: SamAccount Name, "
             "search_attr_value: jdoe}"]
    y = ("collection: T\nplaybooks:\n- name: P\n  steps:\n  - type: start\n    name: Start\n"
         "    next: lookup\n" + "\n".join(lines) + "\n")
    return [e for e in compile_yaml(y, db).errors if e.severity == "warning"]
