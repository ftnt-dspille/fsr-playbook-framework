"""Regression tests for TRIAGE_BUILD_AUDIT findings A2 and E1.

A2 — the triage tool slice must NOT advertise any build-only authoring/
mutation tool, so a triage session can't author YAML. (The provider also has
a dispatch-time backstop in anthropic_provider.py for names that slip through.)

E1 — `_required_params` must dedupe by name; an op with conditional param
groups otherwise lists the same required param once per group.
"""
from __future__ import annotations

import sqlite3

from fsr_playbooks.llm.intents import (
    BUILD_ONLY_TOOLS,
    tools_for_intent,
)
from fsr_playbooks.mcp_server.tools_triage import _required_params


# --- A2: triage slice excludes every build-only tool ------------------------

def test_build_intent_self_fills():
    # build returns [] so the provider expands to the full registry.
    assert tools_for_intent("build") == []


def test_triage_slice_excludes_all_build_only_tools():
    names = {t["name"] for t in tools_for_intent("triage")}
    assert names, "triage must advertise a non-empty tool slice"
    leaked = names & BUILD_ONLY_TOOLS
    assert not leaked, f"build-only tools leaked into triage: {sorted(leaked)}"


def test_triage_slice_keeps_core_discovery_tools():
    names = {t["name"] for t in tools_for_intent("triage")}
    # The triage hunt loop depends on these read/discovery tools.
    for keep in ("run_op", "find_operation", "get_record",
                 "find_enrichment_actions", "find_containment_actions"):
        assert keep in names, f"triage slice dropped essential tool {keep!r}"


# --- E1: required-params dedupe ---------------------------------------------

def _params_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE operation_params ("
        "connector_name TEXT, op_name TEXT, param_name TEXT, type TEXT, "
        "title TEXT, required TEXT, visible TEXT, ord INTEGER)"
    )
    # `ip` appears in two conditional param groups (parent-gated), the exact
    # block_ip_new shape from the audit — it must collapse to one row.
    rows = [
        ("fortigate", "block_ip_new", "ip", "text", "IP", "1", "1", 0),
        ("fortigate", "block_ip_new", "ip", "text", "IP", "1", "1", 1),
        ("fortigate", "block_ip_new", "ip_group_name", "text", "Grp", "1", "1", 2),
        ("fortigate", "block_ip_new", "ip_group_name", "text", "Grp", "1", "1", 3),
    ]
    conn.executemany(
        "INSERT INTO operation_params VALUES (?,?,?,?,?,?,?,?)", rows)
    return conn


def test_required_params_dedupes_by_name():
    conn = _params_db()
    try:
        params = _required_params(conn, "fortigate", "block_ip_new")
    finally:
        conn.close()
    names = [p["name"] for p in params]
    assert names == ["ip", "ip_group_name"], names
    assert len(names) == len(set(names)), "duplicates not collapsed"
