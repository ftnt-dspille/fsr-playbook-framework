"""Smoke tests for chat-review pattern detectors.

Builds a synthetic in-memory history.db with one fake session per
pattern and asserts the right Finding fires.
"""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import chat_review  # noqa: E402


# Schema mirrors web/backend/history.py — we only need the tables the
# detectors read. Using a minimal subset keeps the fixture small.
_MINIMAL_SCHEMA = """
CREATE TABLE chat_sessions (
    id TEXT PRIMARY KEY, ts_first TEXT NOT NULL, ts_last TEXT NOT NULL,
    model TEXT, total_input INTEGER NOT NULL DEFAULT 0,
    total_output INTEGER NOT NULL DEFAULT 0,
    total_cache_read INTEGER NOT NULL DEFAULT 0,
    total_cache_write INTEGER NOT NULL DEFAULT 0,
    turn_count INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE chat_turns (
    session_id TEXT NOT NULL, turn INTEGER NOT NULL, ts TEXT NOT NULL,
    input_tokens INTEGER, output_tokens INTEGER, cache_read INTEGER,
    cache_write INTEGER, stop_reason TEXT, history_chars INTEGER,
    playbook_collection TEXT, yaml_sha TEXT,
    PRIMARY KEY (session_id, turn)
);
CREATE TABLE chat_tool_calls (
    session_id TEXT NOT NULL, turn INTEGER NOT NULL, seq INTEGER NOT NULL,
    name TEXT NOT NULL, args_chars INTEGER, result_chars INTEGER,
    PRIMARY KEY (session_id, turn, seq)
);
CREATE TABLE chat_messages (
    session_id TEXT NOT NULL, turn INTEGER NOT NULL, seq INTEGER NOT NULL,
    ts TEXT NOT NULL, kind TEXT NOT NULL, name TEXT, content TEXT,
    PRIMARY KEY (session_id, turn, seq)
);
CREATE TABLE pushes (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL,
    coll_uuid TEXT NOT NULL, coll_name TEXT, mode TEXT, action TEXT,
    ok INTEGER NOT NULL, http_status INTEGER, wf_count INTEGER,
    chat_session_id TEXT, source_yaml TEXT
);
CREATE TABLE chat_feedback (
    session_id TEXT PRIMARY KEY, rating TEXT NOT NULL, summary TEXT,
    tags TEXT, ts TEXT NOT NULL
);
"""


@pytest.fixture
def tmpdb(tmp_path: Path) -> Path:
    p = tmp_path / "history.db"
    conn = sqlite3.connect(p)
    conn.executescript(_MINIMAL_SCHEMA)
    conn.commit()
    conn.close()
    return p


def _session(conn: sqlite3.Connection, sid: str, *, turns: int = 3,
             model: str = "claude-opus-4-7") -> None:
    conn.execute(
        "INSERT INTO chat_sessions (id, ts_first, ts_last, model, turn_count) "
        "VALUES (?, ?, ?, ?, ?)",
        (sid, "2026-05-06T00:00:00Z", "2026-05-06T00:01:00Z", model, turns),
    )
    for t in range(1, turns + 1):
        conn.execute(
            "INSERT INTO chat_turns (session_id, turn, ts) VALUES (?, ?, ?)",
            (sid, t, "2026-05-06T00:00:00Z"),
        )


def _msg(conn: sqlite3.Connection, sid: str, turn: int, seq: int,
         kind: str, content: str, *, name: str | None = None) -> None:
    conn.execute(
        "INSERT INTO chat_messages (session_id, turn, seq, ts, kind, name, content) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (sid, turn, seq, "2026-05-06T00:00:00Z", kind, name, content),
    )


def _tool(conn: sqlite3.Connection, sid: str, turn: int, seq: int,
          name: str, *, args_chars: int = 50,
          result_chars: int = 100) -> None:
    conn.execute(
        "INSERT INTO chat_tool_calls (session_id, turn, seq, name, args_chars, result_chars) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (sid, turn, seq, name, args_chars, result_chars),
    )


def test_uuid_step_ids_detected(tmpdb: Path) -> None:
    conn = sqlite3.connect(tmpdb)
    _session(conn, "uuid_test")
    yaml_block = (
        "Here you go:\n```yaml\n"
        "collection: T\n"
        "playbooks:\n"
        "  - id: 550e8400-e29b-41d4-a716-446655440000\n"
        "    type: start\n"
        "```\n"
    )
    _msg(conn, "uuid_test", 2, 0, "assistant_text", yaml_block)
    conn.commit()
    conn.close()
    rep = chat_review.review_session("uuid_test", db_path=tmpdb)
    codes = [f.code for f in rep.findings]
    assert "uuid_step_ids" in codes


def test_set_variable_typo_detected(tmpdb: Path) -> None:
    conn = sqlite3.connect(tmpdb)
    _session(conn, "typo_test")
    yaml_block = (
        "```yaml\n"
        "collection: T\n"
        "playbooks:\n"
        "  - id: pb\n"
        "    steps:\n"
        "      - id: s\n"
        "        type: set_variable\n"
        "        arguments:\n"
        "          variables:\n"
        "            - {name: x, value: hi}\n"
        "```\n"
    )
    _msg(conn, "typo_test", 2, 0, "assistant_text", yaml_block)
    conn.commit()
    conn.close()
    rep = chat_review.review_session("typo_test", db_path=tmpdb)
    codes = [f.code for f in rep.findings]
    assert "set_variable_typo" in codes


def test_validate_spiral_detected(tmpdb: Path) -> None:
    conn = sqlite3.connect(tmpdb)
    _session(conn, "spiral", turns=4)
    # 4 validate_yaml calls, all returning errors (count never converges)
    for turn in range(1, 5):
        _tool(conn, "spiral", turn, 0, "validate_yaml",
              args_chars=500, result_chars=2000)
        _msg(conn, "spiral", turn, 1, "tool_use", "{}", name="validate_yaml")
        _msg(conn, "spiral", turn, 2, "tool_result",
             '{"ok": false, "errors": [{"code":"missing_field"},'
             '{"code":"missing_field"},{"code":"missing_field"}]}',
             name="toolu_x")
    conn.commit()
    conn.close()
    rep = chat_review.review_session("spiral", db_path=tmpdb)
    codes = [f.code for f in rep.findings]
    assert "validate_spiral" in codes


def test_thumbs_down_surfaces(tmpdb: Path) -> None:
    conn = sqlite3.connect(tmpdb)
    _session(conn, "downer")
    conn.execute(
        "INSERT INTO chat_feedback (session_id, rating, summary, ts) "
        "VALUES (?, 'down', 'agent picked wrong step type', '2026-05-06T00:01:00Z')",
        ("downer",),
    )
    conn.commit()
    conn.close()
    rep = chat_review.review_session("downer", db_path=tmpdb)
    assert rep.findings[0].code == "user_thumbs_down"
    assert rep.findings[0].severity == "error"
    assert "wrong step" in rep.findings[0].title


def test_clean_session_no_findings(tmpdb: Path) -> None:
    conn = sqlite3.connect(tmpdb)
    _session(conn, "happy", turns=2)
    conn.execute(
        "INSERT INTO pushes (ts, coll_uuid, coll_name, ok, chat_session_id) "
        "VALUES ('2026-05-06T00:01:00Z', 'uuid1', 'Hello', 1, 'happy')",
    )
    conn.commit()
    conn.close()
    rep = chat_review.review_session("happy", db_path=tmpdb)
    assert rep.findings == []
    assert "clean" in rep.headline.lower()


def test_no_editor_update_detected(tmpdb: Path) -> None:
    """Agent answered in prose only — no ```yaml block. From the user's
    perspective the editor never updated."""
    conn = sqlite3.connect(tmpdb)
    _session(conn, "no_yaml")
    _msg(conn, "no_yaml", 1, 0, "user",
         "Build a playbook to prompt for an IP and block it.")
    _msg(conn, "no_yaml", 2, 0, "assistant_text",
         "Here's how you'd do it: first you'd add a manual_input step, "
         "then a decision, then a connector call. Let me know if you "
         "want me to draft the YAML.")
    conn.commit()
    conn.close()
    rep = chat_review.review_session("no_yaml", db_path=tmpdb)
    codes = [f.code for f in rep.findings]
    assert "no_editor_update" in codes


def test_no_editor_update_only_for_authoring_intent(tmpdb: Path) -> None:
    """A chitchat turn ('explain my YAML') legitimately produces no new
    YAML block — must not fire."""
    conn = sqlite3.connect(tmpdb)
    _session(conn, "explain_only")
    _msg(conn, "explain_only", 1, 0, "user",
         "Explain what each step in my playbook does.")
    _msg(conn, "explain_only", 2, 0, "assistant_text",
         "Step 1 fetches alerts. Step 2 is a decision. Step 3 sends mail.")
    conn.commit()
    conn.close()
    rep = chat_review.review_session("explain_only", db_path=tmpdb)
    codes = [f.code for f in rep.findings]
    assert "no_editor_update" not in codes


def test_yaml_in_wrong_fence_detected(tmpdb: Path) -> None:
    """Agent put YAML in a plain ``` fence (no tag) — extractor misses
    it, editor doesn't update."""
    conn = sqlite3.connect(tmpdb)
    _session(conn, "wrong_fence")
    _msg(conn, "wrong_fence", 1, 0, "user", "Build a playbook")
    _msg(conn, "wrong_fence", 2, 0, "assistant_text",
         "Here you go:\n```\n"
         "collection: T\n"
         "playbooks:\n"
         "  - id: pb\n"
         "    steps:\n"
         "      - id: s\n"
         "        type: set_variable\n"
         "        arguments:\n"
         "          arg_list: []\n"
         "```\n")
    conn.commit()
    conn.close()
    rep = chat_review.review_session("wrong_fence", db_path=tmpdb)
    codes = [f.code for f in rep.findings]
    assert "yaml_in_wrong_fence" in codes


def test_unknown_session_raises(tmpdb: Path) -> None:
    with pytest.raises(LookupError):
        chat_review.review_session("nope", db_path=tmpdb)
