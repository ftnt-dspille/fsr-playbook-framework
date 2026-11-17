"""find(kind="action") answers in the model's budget: ranked, compact, capped.

Five things, each with its own test:

  a. a query ranks the action catalogs by word overlap and drops the rows that
     share no word with it (a management op that matched only the target noun
     no longer rides along);
  b. the row the model reads is a summary (names, tier, approval, the preferred
     branch), with the full signature left to get_op_schema;
  c. the answer is capped at 10 across families by default, clamped to 15, and
     says how many were cut;
  d. a bare device / agent / machine names an endpoint only beside a response
     verb;
  e. any provider's model-facing tool result is capped, while the host still
     receives the full result.
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from fsr_playbooks.llm.openai_provider import OpenAIProvider
from fsr_playbooks.llm.provider import Message, ToolResultEvent
from fsr_playbooks.mcp_server import _shared
from fsr_playbooks.mcp_server import tools_connector_discovery as tcd
from fsr_playbooks.mcp_server import tools_find as tf


def _row(op, title, *, connector="fortigate-cloud", cat="containment", tier=3,
         requires_approval=True, **extra):
    return {"connector": connector, "op": op, "title": title, "category": cat,
            "tier": tier, "requires_approval": requires_approval,
            "status": "Available", "deprecated": False,
            "required_params": [{"name": "ip", "type": "text"},
                                {"name": "vdom", "type": "text"}],
            "params": [{"name": "ip", "type": "text", "select": ["x" * 400]}],
            "runs_on_agent": False, **extra}


def _no_record(**_):
    raise AssertionError("record catalog should not be consulted here")


def _stub(rows_by_family):
    def make(name):
        return lambda target_type="", limit=25, **_: {
            "probed": True, "actions": list(rows_by_family.get(name, []))}
    return make("containment"), make("enrichment")


# ---------------------------------------------------------------- (a) ranking

def test_query_drops_the_management_op_that_shared_only_the_target_noun():
    containment, enrichment = _stub({
        "containment": [_row("add_device", "Add Device"),
                        _row("isolate_host", "Isolate Host", connector="fortiedr")],
        "enrichment": [_row("list_network_connections",
                            "List Outbound Connections", connector="fortiedr",
                            cat="investigation", requires_approval=False)],
    })
    out = tf._find_actions(
        containment, enrichment, _no_record,
        query="process creation outbound connections telemetry",
        target_type="endpoint", action_type="", module="", limit=10)
    ops = [a["op"] for a in out["actions"]]
    assert "add_device" not in ops
    assert ops == ["list_network_connections"]


def test_no_query_keeps_every_candidate_in_catalog_order():
    containment, enrichment = _stub({
        "containment": [_row("add_device", "Add Device")],
        "enrichment": [_row("list_network_connections", "List Connections",
                            cat="investigation", requires_approval=False)],
    })
    out = tf._find_actions(containment, enrichment, _no_record, query="",
                           target_type="endpoint", action_type="", module="",
                           limit=10)
    assert {a["op"] for a in out["actions"]} == {"add_device", "list_network_connections"}


def test_query_orders_by_overlap_before_catalog_order():
    containment, enrichment = _stub({
        "containment": [_row("isolate_host", "Isolate Host")],
        "enrichment": [_row("get_process_telemetry", "Get Process Telemetry",
                            cat="investigation", requires_approval=False),
                       _row("list_outbound_connections", "List Outbound Connections",
                            cat="investigation", requires_approval=False)],
    })
    out = tf._find_actions(containment, enrichment, _no_record,
                           query="process telemetry", target_type="endpoint",
                           action_type="", module="", limit=10)
    assert [a["op"] for a in out["actions"]] == ["get_process_telemetry"]


def test_query_with_no_word_in_common_says_so_instead_of_dead_ending():
    containment, enrichment = _stub({
        "containment": [_row("add_device", "Add Device")],
    })
    out = tf._find_actions(containment, enrichment, _no_record,
                           query="zebra migration", target_type="endpoint",
                           action_type="", module="", limit=10)
    assert out["actions"] == [] and out["count"] == 0
    assert "No action's name or title shares a word" in out["message"]


def test_a_query_without_a_target_type_is_not_sent_to_the_catalogs_as_one():
    seen = {}

    def containment(target_type="", limit=25, **_):
        seen["containment"] = target_type
        return {"probed": True, "actions": []}

    def enrichment(target_type="", limit=25, **_):
        seen["enrichment"] = target_type
        return {"probed": True, "actions": [
            _row("ip_reputation", "File Reputation Lookup", connector="virustotal",
                 cat="investigation", requires_approval=False)]}

    out = tf._find_actions(containment, enrichment, _no_record,
                           query="reputation of a file hash", target_type="",
                           action_type="", module="", limit=10)
    assert seen == {"containment": "", "enrichment": ""}
    assert [a["op"] for a in out["actions"]] == ["ip_reputation"]


# ------------------------------------------------------------- (b) compact row

_ROW_KEYS = {"action", "action_type", "connector", "op", "title", "tier",
             "requires_approval", "required", "runs_on_agent", "deprecated",
             "preferred_params", "preferred_params_why", "indicator_param",
             "collection", "params", "notes"}


def test_action_row_is_a_summary_and_the_signature_is_left_to_get_op_schema():
    containment, enrichment = _stub({
        "containment": [_row("block_ip_new", "Block IP Address",
                             connector="fortigate-firewall",
                             preferred_params={"ip_block_policy": "x"},
                             preferred_params_why="why")],
        "enrichment": [_row("ip_reputation", "IP Reputation", connector="virustotal",
                            cat="investigation", requires_approval=False,
                            indicator_param="ip")],
    })
    out = tf._find_actions(containment, enrichment, _no_record, query="",
                           target_type="ip", action_type="", module="", limit=10)
    rows = {a["op"]: a for a in out["actions"]}
    for row in rows.values():
        assert set(row) <= _ROW_KEYS, set(row) - _ROW_KEYS
        assert "params" not in row and "status" not in row
    block = rows["block_ip_new"]
    assert block["required"] == ["ip", "vdom"]
    assert block["requires_approval"] is True and block["tier"] == 3
    assert block["preferred_params"] == {"ip_block_policy": "x"}
    rep = rows["ip_reputation"]
    assert "requires_approval" not in rep and rep["indicator_param"] == "ip"
    assert "get_op_schema" in out["hint"]


def test_record_row_keeps_its_body_template():
    def record(action="", module="alerts", **_):
        return {"ok": True, "actions": [{
            "action": "comment", "connector": "cyops_utilities", "op": "create_comment",
            "title": "Add a comment", "tier": 3, "requires_approval": True,
            "collection": "/api/3/comments", "params": {"iri": "/api/3/comments",
                                                       "body": {"comment": "<text>"}},
            "required_params": [{"name": "comment", "type": "text"}],
            "notes": "a comment is a record in the comments module"}]}
    containment, enrichment = _stub({})
    out = tf._find_actions(containment, enrichment, record, query="",
                           target_type="", action_type="record", module="alerts",
                           limit=10)
    row = out["actions"][0]
    assert row["params"]["body"] == {"comment": "<text>"}
    assert row["collection"] == "/api/3/comments" and row["notes"]
    assert row["required"] == ["comment"]


# --------------------------------------------------------------- (c) the cap

def test_default_cap_is_ten_across_families_and_says_what_was_cut():
    many_c = [_row(f"block_ip_{i}", f"Block IP {i}") for i in range(30)]
    many_e = [_row(f"ip_lookup_{i}", f"IP Lookup {i}", cat="investigation",
                   requires_approval=False) for i in range(30)]
    containment, enrichment = _stub({"containment": many_c, "enrichment": many_e})
    out = tf._find_actions(containment, enrichment, _no_record, query="",
                           target_type="ip", action_type="", module="", limit=10)
    assert len(out["actions"]) == 10
    assert out["count"] == 60 and out["more"] == 50
    assert {a["action_type"] for a in out["actions"]} == {"containment", "enrichment"}
    assert "narrow" in out["hint"]


def test_limit_is_clamped_to_fifteen():
    many_c = [_row(f"block_ip_{i}", f"Block IP {i}") for i in range(40)]
    containment, enrichment = _stub({"containment": many_c})
    out = tf._find_actions(containment, enrichment, _no_record, query="",
                           target_type="ip", action_type="", module="", limit=99)
    assert len(out["actions"]) == 15 and out["more"] == 25


def test_no_more_key_when_nothing_was_cut():
    containment, enrichment = _stub({"containment": [_row("block_ip_new", "Block IP")]})
    out = tf._find_actions(containment, enrichment, _no_record, query="",
                           target_type="ip", action_type="", module="", limit=10)
    assert "more" not in out


# ----------------------------------------------------------- (d) the keywords

_ENDPOINT = tcd._TARGET_KEYWORDS["endpoint"]
_ENDPOINT_WEAK = tcd._WEAK_TARGET_WORDS["endpoint"]


@pytest.mark.parametrize("op,title", [
    ("isolate_machine", "Isolate Machine"),
    ("quarantine_device", "Quarantine Device"),
    ("remediate_device", "Remediate Device"),
    ("terminate_agent", "Terminate Agent"),
    ("isolate_host", "Isolate Host"),
    ("isolate_endpoint", "Isolate Endpoint"),
])
def test_a_host_noun_with_a_response_verb_is_endpoint_containment(op, title):
    assert tcd._names_target(op, title, _ENDPOINT, _ENDPOINT_WEAK)


@pytest.mark.parametrize("op,title", [
    ("add_device", "Add Device"),
    ("update_device", "Update Device"),
    ("wakeup_agent", "Wakeup Agent"),
    ("reboot_device", "Reboot Device"),
    ("assign_policy_to_device", "Assign Policy To Device"),
    ("generate_installer", "Generate Agent Installer"),
])
def test_a_bare_device_agent_or_machine_is_not_endpoint_containment(op, title):
    assert not tcd._names_target(op, title, _ENDPOINT, _ENDPOINT_WEAK)


def test_find_containment_does_not_offer_add_device_for_an_endpoint(monkeypatch, tmp_path):
    db = tmp_path / "ops.db"
    with sqlite3.connect(db) as c:
        c.execute("CREATE TABLE operations (connector_name, op_name, title, "
                  "category, enabled)")
        c.executemany("INSERT INTO operations VALUES (?,?,?,?,1)", [
            ("fortigate-cloud", "add_device", "Add Device", "containment"),
            ("fortiedr", "isolate_host", "Isolate Host", "containment"),
        ])
    monkeypatch.setattr(tcd, "DB_PATH", str(db))
    monkeypatch.setattr(tcd, "_required_params", lambda *a, **k: [])
    monkeypatch.setattr(tcd, "_param_sig", lambda *a, **k: [])
    monkeypatch.setattr(tcd, "list_configured_connectors", lambda **_: {
        "configured": [{"name": n, "status": "Completed", "version": "1.0.0"}
                       for n in ("fortigate-cloud", "fortiedr")]})
    monkeypatch.setattr(_shared, "_live_client", lambda: object())
    monkeypatch.setattr(tcd, "_healthcheck_many",
                        lambda client, targets, **_: {t[0]: "Available" for t in targets})
    import fsr_playbooks.llm.tools as llm_tools
    monkeypatch.setattr(llm_tools, "_tier_for_run_op", lambda _call: 3)
    out = tcd.find_containment_actions(target_type="endpoint", probe=True)
    assert {(a["connector"], a["op"]) for a in out["actions"]} == {
        ("fortiedr", "isolate_host")}


# ------------------------------------------------- (e) the per-result cap

_TOOLS = [{"type": "function", "function": {
    "name": "find", "description": "find",
    "parameters": {"type": "object", "properties": {"kind": {"type": "string"}}}}}]


class _FakeStream:
    def __init__(self, chunks):
        self._chunks = chunks

    def __aiter__(self):
        async def gen():
            for c in self._chunks:
                yield c
        return gen()


def _delta(*, content=None, tool_calls=None, finish=None):
    return MagicMock(choices=[MagicMock(delta=MagicMock(content=content,
                                                        tool_calls=tool_calls),
                                        finish_reason=finish)], usage=None)


def _tc(*, index, id, name, args):
    fn = MagicMock()
    fn.name = name
    fn.arguments = args
    return MagicMock(index=index, id=id, function=fn)


def _run_find_round_trip(result):
    call_round = [_delta(tool_calls=[_tc(index=0, id="c1", name="find",
                                         args=json.dumps({"kind": "action"}))]),
                  _delta(finish="tool_calls")]
    done_round = [_delta(content="ok"), _delta(finish="stop")]
    create = AsyncMock(side_effect=[_FakeStream(call_round), _FakeStream(done_round)])
    client = MagicMock()
    client.chat.completions = MagicMock(create=create)
    provider = OpenAIProvider(model="gpt-4.1-mini", base_url="http://x/v1",
                              api_key="x", client=client)
    with patch("fsr_playbooks.llm.agent_loop.dispatch", MagicMock(return_value=result)), \
         patch("fsr_playbooks.llm.agent_loop._tier_for", return_value=0):
        async def drain():
            return [ev async for ev in provider.stream(
                system="s", messages=[Message(role="user", content="find it")],
                tools=_TOOLS, tags={})]
        events = asyncio.run(drain())
    sent = create.await_args_list[1].kwargs["messages"]
    tool_msg = next(m for m in sent if m.get("role") == "tool")
    host = [e for e in events if isinstance(e, ToolResultEvent)]
    return tool_msg["content"], host


def test_openai_turn_caps_a_huge_find_result_for_the_model():
    big = {"ok": True, "kind": "action", "blob": "x" * 30000}
    content, host = _run_find_round_trip(big)
    assert len(content) <= 20000
    assert "[truncated" in content and "narrow the query" in content
    assert '"blob"' in content[:6000]
    # The host and widget still get the whole result.
    assert host and len(host[0].result["blob"]) == 30000


def test_a_build_sized_result_reaches_the_model_whole():
    """The cap is a backstop for outliers. Verify reports and edit_playbook
    results run to ~17k on a real box and the model repairs from them, so a
    result that size must not be clipped."""
    mid = {"ok": True, "kind": "action", "blob": "y" * 15000}
    content, _host = _run_find_round_trip(mid)
    assert "[truncated" not in content
    assert content.count("y") == 15000


def test_openai_turn_leaves_a_small_find_result_alone():
    content, _ = _run_find_round_trip({"ok": True, "kind": "action", "actions": []})
    assert "truncated" not in content
    assert json.loads(content[content.index("{"):])["actions"] == []
