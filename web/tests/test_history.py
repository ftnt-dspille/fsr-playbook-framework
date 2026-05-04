"""history.py — push log, chat-turn log, per-playbook cost rollup,
chat↔push correlation marker, YAML diff.
"""
from __future__ import annotations

import pytest

from backend import history


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Every test gets a fresh history.db so they don't bleed."""
    monkeypatch.setenv("STUDIO_HISTORY_DB", str(tmp_path / "history.db"))
    monkeypatch.setenv("FSRPB_ACTIVE_SESSION", str(tmp_path / "active_session"))
    yield


# ---- push log ---------------------------------------------------

def test_record_push_round_trip():
    pid = history.record_push(
        source_path="examples/foo.yaml",
        coll_uuid="abc-coll",
        coll_name="Foo",
        mode="replace",
        action="POST",
        ok=True,
        http_status=200,
        workflows=[
            {"uuid": "wf-1", "name": "Hello",
             "link_url": "https://x/playbooks/wf-1", "link_ok": True},
        ],
        source_yaml="collection: Foo\n",
    )
    assert pid is not None
    p = history.get_push(pid)
    assert p["coll_name"] == "Foo"
    assert p["ok"] == 1
    assert p["source_yaml"] == "collection: Foo\n"
    assert len(p["workflows"]) == 1
    assert p["workflows"][0]["wf_name"] == "Hello"
    assert p["workflows"][0]["link_ok"] == 1


def test_record_push_failure_still_logs():
    """Failed pushes are valuable history — record them too."""
    pid = history.record_push(
        source_path="examples/bad.yaml",
        coll_uuid="bad-coll", coll_name="Bad",
        mode="upsert", action="BULKUPSERT",
        ok=False, http_status=400,
        workflows=[],
        source_yaml="collection: Bad\n",
    )
    p = history.get_push(pid)
    assert p["ok"] == 0
    assert p["http_status"] == 400


def test_list_pushes_filters_by_collection():
    history.record_push(
        source_path="a.yaml", coll_uuid="A", coll_name="A",
        mode="replace", action="POST", ok=True, http_status=200,
        workflows=[], source_yaml="collection: A\n",
    )
    history.record_push(
        source_path="b.yaml", coll_uuid="B", coll_name="B",
        mode="replace", action="POST", ok=True, http_status=200,
        workflows=[], source_yaml="collection: B\n",
    )
    only_a = history.list_pushes(coll_uuid="A")
    assert len(only_a) == 1
    assert only_a[0]["coll_name"] == "A"


def test_previous_push_finds_prior_version():
    p1 = history.record_push(
        source_path="x.yaml", coll_uuid="X", coll_name="X",
        mode="replace", action="POST", ok=True, http_status=200,
        workflows=[], source_yaml="v1\n",
    )
    p2 = history.record_push(
        source_path="x.yaml", coll_uuid="X", coll_name="X",
        mode="replace", action="POST", ok=True, http_status=200,
        workflows=[], source_yaml="v2\n",
    )
    prev = history.previous_push("X", p2)
    assert prev is not None
    assert prev["id"] == p1
    assert prev["source_yaml"] == "v1\n"


def test_previous_push_returns_none_for_first():
    p = history.record_push(
        source_path="x.yaml", coll_uuid="X", coll_name="X",
        mode="replace", action="POST", ok=True, http_status=200,
        workflows=[], source_yaml="v1\n",
    )
    assert history.previous_push("X", p) is None


# ---- chat-turn log ----------------------------------------------

def test_record_chat_turn_creates_session_and_turn():
    history.record_chat_turn({
        "session": "abc12345", "turn": 1, "model": "claude-sonnet-4-5",
        "input_tokens": 100, "output_tokens": 20,
        "cache_read": 0, "cache_write": 50,
        "stop_reason": "end_turn", "history_chars": 200,
        "tool_calls": [], "tags": {},
    })
    s = history.get_chat_session("abc12345")
    assert s["total_input"] == 100
    assert s["turn_count"] == 1
    assert s["model"] == "claude-sonnet-4-5"


def test_record_chat_turn_aggregates_multi_turn():
    for turn in (1, 2, 3):
        history.record_chat_turn({
            "session": "agg", "turn": turn, "model": "claude-sonnet-4-5",
            "input_tokens": 10 * turn, "output_tokens": 5,
            "cache_read": 0, "cache_write": 0,
            "stop_reason": "tool_use", "history_chars": 100 * turn,
            "tool_calls": [], "tags": {},
        })
    s = history.get_chat_session("agg")
    assert s["turn_count"] == 3
    assert s["total_input"] == 60  # 10+20+30


def test_chat_turn_persists_per_tool_call_costs():
    history.record_chat_turn({
        "session": "tools", "turn": 1, "model": "claude-sonnet-4-5",
        "input_tokens": 1, "output_tokens": 1, "cache_read": 0,
        "cache_write": 0, "stop_reason": "tool_use", "history_chars": 1,
        "tool_calls": [
            {"name": "search_playbooks", "args_chars": 50, "result_chars": 48000},
            {"name": "get_op_schema", "args_chars": 30, "result_chars": 3200},
        ],
        "tags": {},
    })
    s = history.get_chat_session("tools")
    by_name = {t["name"]: t for t in s["tool_calls"]}
    assert by_name["search_playbooks"]["result_chars"] == 48000
    assert by_name["get_op_schema"]["result_chars"] == 3200


def test_session_cost_estimate_uses_pricing_table():
    history.record_chat_turn({
        "session": "priced", "turn": 1, "model": "claude-sonnet-4-5-20250929",
        "input_tokens": 1_000_000, "output_tokens": 0,
        "cache_read": 0, "cache_write": 0,
        "stop_reason": "end_turn", "history_chars": 0,
        "tool_calls": [], "tags": {},
    })
    s = history.get_chat_session("priced")
    # 1M input tokens × $3/MTok = $3.00
    assert s["est_cost_usd"] == 3.0


def test_session_cost_unknown_model_returns_none():
    history.record_chat_turn({
        "session": "unknown", "turn": 1, "model": "not-a-real-model",
        "input_tokens": 100, "output_tokens": 10,
        "cache_read": 0, "cache_write": 0,
        "stop_reason": "end_turn", "history_chars": 0,
        "tool_calls": [], "tags": {},
    })
    s = history.get_chat_session("unknown")
    assert s["est_cost_usd"] is None


# ---- per-playbook attribution -----------------------------------

def test_chat_turn_persists_playbook_tags():
    history.record_chat_turn({
        "session": "tagged", "turn": 1, "model": "claude-sonnet-4-5",
        "input_tokens": 10, "output_tokens": 5,
        "cache_read": 0, "cache_write": 0,
        "stop_reason": "end_turn", "history_chars": 30,
        "tool_calls": [],
        "tags": {"playbook_collection": "Triage", "yaml_sha": "abc123"},
    })
    s = history.get_chat_session("tagged")
    t = s["turns"][0]
    assert t["playbook_collection"] == "Triage"
    assert t["yaml_sha"] == "abc123"


def test_cost_by_playbook_groups_and_estimates():
    # Two sessions both tagged with the same playbook.
    for session, turn, in_tok in [("s1", 1, 100_000), ("s1", 2, 50_000),
                                  ("s2", 1, 200_000)]:
        history.record_chat_turn({
            "session": session, "turn": turn,
            "model": "claude-sonnet-4-5",
            "input_tokens": in_tok, "output_tokens": 0,
            "cache_read": 0, "cache_write": 0,
            "stop_reason": "end_turn", "history_chars": 0,
            "tool_calls": [],
            "tags": {"playbook_collection": "Phish Triage", "yaml_sha": "x"},
        })
    rollup = history.cost_by_playbook()
    row = next(r for r in rollup if r["collection"] == "Phish Triage")
    assert row["turn_count"] == 3
    assert row["session_count"] == 2
    assert row["total_input"] == 350_000
    # 350k tokens × $3/MTok = $1.05
    assert row["est_cost_usd"] == 1.05


def test_cost_by_playbook_skips_untagged_turns():
    history.record_chat_turn({
        "session": "untagged", "turn": 1, "model": "claude-sonnet-4-5",
        "input_tokens": 50, "output_tokens": 5,
        "cache_read": 0, "cache_write": 0,
        "stop_reason": "end_turn", "history_chars": 0,
        "tool_calls": [], "tags": {},  # no playbook_collection
    })
    rollup = history.cost_by_playbook()
    assert all(r["collection"] for r in rollup)
    assert "untagged" not in [r["collection"] for r in rollup]


# ---- chat ↔ push correlation marker -----------------------------

def test_active_session_round_trip():
    history.write_active_session("sess-xyz")
    assert history.read_active_session() == "sess-xyz"


def test_active_session_clear_with_none():
    history.write_active_session("sess-1")
    history.write_active_session(None)
    assert history.read_active_session() is None


def test_active_session_returns_none_when_unset():
    assert history.read_active_session() is None


# ---- YAML diff helper -------------------------------------------

def test_yaml_diff_produces_unified_diff():
    out = history.yaml_diff("a: 1\nb: 2\n", "a: 1\nb: 3\n",
                            "before", "after")
    assert "before" in out
    assert "after" in out
    assert "-b: 2" in out
    assert "+b: 3" in out


def test_yaml_diff_identical_returns_empty():
    assert history.yaml_diff("a: 1\n", "a: 1\n") == ""
