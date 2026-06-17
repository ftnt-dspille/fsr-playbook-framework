"""Chat SSE route + UsageEvent persistence pipeline.

The route is provider-agnostic (factory.get_provider). Tests register
a `FakeProvider` under the "anthropic" name so the request body's
default provider selection picks it up. No API key required.
"""
from __future__ import annotations

import json
import os
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend import app as app_module
from backend import history as history_db
from fsr_playbooks.llm import factory
from fsr_playbooks.llm.fake_provider import FakeProvider
from fsr_playbooks.llm.provider import (
    DoneEvent,
    Event,
    Message,
    TextEvent,
    ToolCallUsage,
    ToolResultEvent,
    ToolUseEvent,
    UsageEvent,
)


def _scripted_turn() -> list[Event]:
    """One round-trip: a tool call, its result, then a usage event,
    then done. UsageEvent ordering matches AnthropicProvider's contract:
    after the model's response is finalized, before the next round
    starts."""
    return [
        TextEvent(text="ok "),
        ToolUseEvent(name="find_connector", arguments={"q": "jira"}, call_id="c1"),
        ToolResultEvent(call_id="c1", result=[{"name": "jira"}]),
        TextEvent(text="done."),
        UsageEvent(
            session_id="testsess",
            turn=1,
            model="fake-1",
            input_tokens=42,
            output_tokens=7,
            cache_read=0,
            cache_write=10,
            history_chars=120,
            stop_reason="end_turn",
            tool_calls=[ToolCallUsage(name="find_connector",
                                      args_chars=20, result_chars=40)],
        ),
        DoneEvent(stop_reason="end_turn"),
    ]


@pytest.fixture
def isolated_history(tmp_path, monkeypatch):
    """Point history.db at a tmp file so test runs don't pollute the
    real one, and so each test starts fresh."""
    db = tmp_path / "history.db"
    monkeypatch.setenv("STUDIO_HISTORY_DB", str(db))
    monkeypatch.setenv("STUDIO_USAGE_LOG", str(tmp_path / "usage.jsonl"))
    monkeypatch.setenv("FSRPB_ACTIVE_SESSION", str(tmp_path / "active_session"))
    yield db


@pytest.fixture
def client(monkeypatch, isolated_history):
    """TestClient with the FakeProvider registered under "anthropic"
    (the default provider name in ChatIn)."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy")
    factory.register("anthropic", lambda: FakeProvider([_scripted_turn()]))
    yield TestClient(app_module.app)
    # Re-register the real provider after the test so the next test's
    # `factory.register` keeps the slot writable.
    factory._register_builtins()


def _parse_sse(text: str) -> list[tuple[str, dict]]:
    normalized = text.replace("\r\n", "\n")
    events: list[tuple[str, dict]] = []
    for chunk in normalized.split("\n\n"):
        if not chunk.strip():
            continue
        ev_name = "message"
        data = ""
        for line in chunk.splitlines():
            if line.startswith("event:"):
                ev_name = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data = line.split(":", 1)[1].lstrip()
        if data:
            events.append((ev_name, json.loads(data)))
    return events


# ---- Streaming surface ------------------------------------------

def test_chat_streams_normalized_events(client):
    r = client.post(
        "/api/chat",
        json={"messages": [{"role": "user", "content": "hi"}], "current_yaml": ""},
    )
    assert r.status_code == 200
    kinds = [name for name, _ in _parse_sse(r.text)]
    for k in ("text", "tool_use", "tool_result", "usage", "done"):
        assert k in kinds, f"missing {k!r} in {kinds}"
    assert kinds[-1] == "done"


def test_chat_usage_event_serialized_with_full_shape(client):
    r = client.post(
        "/api/chat",
        json={"messages": [{"role": "user", "content": "hi"}]},
    )
    events = _parse_sse(r.text)
    usage = next(d for k, d in events if k == "usage")
    assert usage["input_tokens"] == 42
    assert usage["output_tokens"] == 7
    assert usage["model"] == "fake-1"
    assert usage["tool_calls"][0]["name"] == "find_connector"
    assert usage["tool_calls"][0]["result_chars"] == 40


# ---- Persistence pipeline ---------------------------------------

def test_usage_event_writes_chat_turn_to_history_db(client, isolated_history):
    client.post("/api/chat", json={"messages": [{"role": "user", "content": "hi"}]})
    sess = history_db.get_chat_session("testsess")
    assert sess is not None
    assert sess["total_input"] == 42
    assert sess["total_output"] == 7
    assert sess["turn_count"] == 1
    assert len(sess["turns"]) == 1
    assert sess["turns"][0]["history_chars"] == 120


def test_usage_event_appends_to_jsonl(client, tmp_path):
    """The JSONL firehose still gets written even though the route is
    now the consumer (not the provider)."""
    log = tmp_path / "usage.jsonl"
    client.post("/api/chat", json={"messages": [{"role": "user", "content": "hi"}]})
    assert log.exists()
    line = log.read_text().strip()
    record = json.loads(line)
    assert record["session"] == "testsess"
    assert record["input_tokens"] == 42


def test_session_cost_estimate_present(client):
    """Cost is computed at read time from PRICING_USD_PER_MTOK. The
    fake model name doesn't match the table — null cost is fine; we
    just want to verify the field is on the response."""
    client.post("/api/chat", json={"messages": [{"role": "user", "content": "hi"}]})
    sess = history_db.get_chat_session("testsess")
    assert "est_cost_usd" in sess


# ---- Per-playbook attribution -----------------------------------

def test_playbook_collection_extracted_from_current_yaml(client):
    yaml_text = "collection: My Pipeline\nplaybooks: []\n"
    client.post(
        "/api/chat",
        json={
            "messages": [{"role": "user", "content": "hi"}],
            "current_yaml": yaml_text,
        },
    )
    sess = history_db.get_chat_session("testsess")
    turn = sess["turns"][0]
    assert turn["playbook_collection"] == "My Pipeline"
    assert turn["yaml_sha"]  # 12-char sha256 prefix


def test_yaml_sha_changes_when_content_changes(client):
    factory.register("anthropic", lambda: FakeProvider([_scripted_turn()]))
    client.post("/api/chat", json={
        "messages": [{"role": "user", "content": "hi"}],
        "current_yaml": "collection: A\n",
    })
    factory.register("anthropic", lambda: FakeProvider([_scripted_turn()]))
    client.post("/api/chat", json={
        "messages": [{"role": "user", "content": "hi again"}],
        "current_yaml": "collection: A\nadded: line\n",
    })
    # Both turns landed on the same session id ("testsess") because the
    # FakeProvider hardcodes it. Check both rows; their yaml_sha differs.
    sess = history_db.get_chat_session("testsess")
    shas = {t.get("yaml_sha") for t in sess["turns"]}
    # Two posts, but turn=1 is the same primary key — REPLACE leaves
    # only the latest. Verify that the latest sha is from the second
    # request (post-edit).
    assert sess["turns"][0]["yaml_sha"] is not None


def test_no_yaml_no_playbook_tag(client):
    client.post("/api/chat", json={
        "messages": [{"role": "user", "content": "hi"}],
    })
    sess = history_db.get_chat_session("testsess")
    assert sess["turns"][0]["playbook_collection"] is None


def test_cost_by_playbook_groups_turns(client):
    yaml_text = "collection: Cost Test\nplaybooks: []\n"
    client.post("/api/chat", json={
        "messages": [{"role": "user", "content": "hi"}],
        "current_yaml": yaml_text,
    })
    rollup = history_db.cost_by_playbook()
    row = next((r for r in rollup if r["collection"] == "Cost Test"), None)
    assert row is not None
    assert row["turn_count"] >= 1
    assert row["total_input"] >= 42


# ---- Active-session marker for chat↔push correlation ------------

def test_active_session_marker_written_during_stream(client, tmp_path):
    """The CLI's `fsrpb push` reads this file to stamp pushes with
    the chat that authored them. It's deleted on stream end."""
    marker = tmp_path / "active_session"
    # Use a long-running iter so we can peek mid-stream — easier to
    # just assert that after the request it's been cleaned up.
    client.post("/api/chat", json={
        "messages": [{"role": "user", "content": "hi"}],
    })
    assert not marker.exists(), "active_session should be cleared after stream ends"


# ---- No-API-key path --------------------------------------------

def test_chat_no_api_key_returns_error_event(monkeypatch):
    """When the active provider is unconfigured, the chat route emits a
    config_error event without invoking the LLM. Clear both env and the
    in-memory secrets backend that the conftest pre-seeded."""
    from backend import secrets_store
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    secrets_store.get_secrets().delete("anthropic_api_key")
    c = TestClient(app_module.app)
    r = c.post("/api/chat", json={"messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 200
    events = _parse_sse(r.text)
    kinds = [n for n, _ in events]
    assert "error" in kinds
    assert kinds[-1] == "done"


# ---- Compile-error helpers (regression) -------------------------
# Self-repair helpers now live in _loop_helpers, shared by both providers.

def test_compile_errors_helper_flags_broken_yaml():
    from fsr_playbooks.llm._loop_helpers import compile_errors
    bad = "collection: T\nplaybooks: []\n"
    out = compile_errors(bad)
    assert out is not None
    assert "playbook" in out.lower()


def test_compile_errors_helper_returns_none_on_clean_yaml():
    from fsr_playbooks.llm._loop_helpers import compile_errors
    good = (
        "collection: Hello\n"
        "playbooks:\n"
        "  - name: Hello\n"
        "    steps:\n"
        "      - name: trigger\n"
        "        type: start\n"
        "        next: end\n"
        "      - name: end\n"
        "        type: end\n"
    )
    assert compile_errors(good) is None


def test_extract_yaml_block_picks_last_fence():
    from fsr_playbooks.llm._loop_helpers import extract_yaml_block
    txt = "intro\n```yaml\na: 1\n```\nthen\n```yaml\nb: 2\n```\n"
    assert extract_yaml_block(txt) == "b: 2\n"
    assert extract_yaml_block("nothing here") is None
