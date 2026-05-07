"""History store — sqlite-backed log of pushes + chat sessions.

One file, two writers (CLI `fsrpb push`, the chat backend), one reader
(the `/api/history` endpoints). Schema is conservative: TEXT for
timestamps (ISO-8601 UTC), TEXT for the YAML snapshot (gzip is overkill
for ~50 KB rows). Writes are best-effort — telemetry must never break
the path it instruments.

Tables:

  pushes                 one row per `fsrpb push` invocation
  push_workflows         one row per workflow inside a push
  chat_sessions          one row per `provider.stream()` call
  chat_turns             one row per LLM round-trip within a session
  chat_tool_calls        one row per tool_use inside a turn

`history_db_path()` is the single source of truth for the file
location; `STUDIO_HISTORY_DB` env var overrides it.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import sqlite3
from pathlib import Path
from typing import Any


_SCHEMA = """
CREATE TABLE IF NOT EXISTS pushes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    source_path TEXT,
    coll_uuid TEXT NOT NULL,
    coll_name TEXT,
    mode TEXT,
    action TEXT,
    ok INTEGER NOT NULL,
    http_status INTEGER,
    wf_count INTEGER,
    chat_session_id TEXT,
    source_yaml TEXT
);
CREATE INDEX IF NOT EXISTS pushes_coll_uuid_ts ON pushes(coll_uuid, ts DESC);
CREATE INDEX IF NOT EXISTS pushes_ts ON pushes(ts DESC);

CREATE TABLE IF NOT EXISTS push_workflows (
    push_id INTEGER NOT NULL,
    wf_uuid TEXT NOT NULL,
    wf_name TEXT,
    link_url TEXT,
    link_ok INTEGER,
    PRIMARY KEY (push_id, wf_uuid),
    FOREIGN KEY (push_id) REFERENCES pushes(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS chat_sessions (
    id TEXT PRIMARY KEY,
    ts_first TEXT NOT NULL,
    ts_last TEXT NOT NULL,
    model TEXT,
    total_input INTEGER NOT NULL DEFAULT 0,
    total_output INTEGER NOT NULL DEFAULT 0,
    total_cache_read INTEGER NOT NULL DEFAULT 0,
    total_cache_write INTEGER NOT NULL DEFAULT 0,
    turn_count INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS chat_sessions_ts ON chat_sessions(ts_last DESC);

CREATE TABLE IF NOT EXISTS chat_turns (
    session_id TEXT NOT NULL,
    turn INTEGER NOT NULL,
    ts TEXT NOT NULL,
    input_tokens INTEGER,
    output_tokens INTEGER,
    cache_read INTEGER,
    cache_write INTEGER,
    stop_reason TEXT,
    history_chars INTEGER,
    playbook_collection TEXT,
    yaml_sha TEXT,
    PRIMARY KEY (session_id, turn),
    FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS chat_turns_playbook
    ON chat_turns(playbook_collection);

CREATE TABLE IF NOT EXISTS chat_tool_calls (
    session_id TEXT NOT NULL,
    turn INTEGER NOT NULL,
    seq INTEGER NOT NULL,
    name TEXT NOT NULL,
    args_chars INTEGER,
    result_chars INTEGER,
    PRIMARY KEY (session_id, turn, seq)
);

-- Full per-message transcript. One row per emitted text/tool block
-- inside a session, so a complete chat replay is achievable from the
-- DB alone (as opposed to chat_turns, which only carries token
-- accounting). `kind` ∈ {user, assistant_text, tool_use, tool_result, ladder}.
-- `content` is text for user/assistant_text, JSON for tool_use args /
-- tool_result payloads / per-turn ladder snapshots. Capped at the
-- column's TEXT limit.
CREATE TABLE IF NOT EXISTS chat_messages (
    session_id TEXT NOT NULL,
    turn INTEGER NOT NULL,
    seq INTEGER NOT NULL,
    ts TEXT NOT NULL,
    kind TEXT NOT NULL,
    name TEXT,
    content TEXT,
    PRIMARY KEY (session_id, turn, seq)
);
CREATE INDEX IF NOT EXISTS chat_messages_session
    ON chat_messages(session_id);

-- User feedback per chat session. One row per session; re-rating
-- upserts. `rating` ∈ {up, down}. `summary` is the user's free-form
-- review notes — what worked, what broke, what to investigate.
-- `tags` is a comma-separated set of short labels (e.g. "wrong_step,
-- missed_branch"); UI may build out of these later.
CREATE TABLE IF NOT EXISTS chat_feedback (
    session_id TEXT PRIMARY KEY,
    rating TEXT NOT NULL,
    summary TEXT,
    tags TEXT,
    ts TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS chat_feedback_rating ON chat_feedback(rating);
"""

# Anthropic public list pricing (per million tokens). Update when
# pricing changes. Used by /api/history endpoints to compute estimated
# cost; never persisted, so a price change retroactively reprices.
PRICING_USD_PER_MTOK: dict[str, dict[str, float]] = {
    "claude-sonnet-4-5":  {"input": 3.00, "output": 15.00, "cache_read": 0.30, "cache_write": 3.75},
    "claude-sonnet-4-6":  {"input": 3.00, "output": 15.00, "cache_read": 0.30, "cache_write": 3.75},
    "claude-opus-4-7":    {"input": 15.0, "output": 75.0,  "cache_read": 1.50, "cache_write": 18.75},
    "claude-haiku-4-5":   {"input": 1.00, "output": 5.00,  "cache_read": 0.10, "cache_write": 1.25},
}


def history_db_path() -> Path:
    env = os.environ.get("STUDIO_HISTORY_DB")
    if env:
        return Path(env).expanduser()
    return Path(__file__).resolve().parent / "history.db"


def _now() -> str:
    return (
        _dt.datetime.now(_dt.timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _connect() -> sqlite3.Connection:
    path = history_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


# ---- writers ------------------------------------------------------

def record_push(
    *,
    source_path: str | None,
    coll_uuid: str,
    coll_name: str,
    mode: str,
    action: str,
    ok: bool,
    http_status: int | None,
    workflows: list[dict[str, Any]],
    source_yaml: str | None,
    chat_session_id: str | None = None,
) -> int | None:
    """Insert one push + N workflow rows. Returns push id or None on
    failure. Each `workflows[i]` is `{uuid, name, link_url, link_ok}`."""
    try:
        conn = _connect()
        cur = conn.execute(
            """INSERT INTO pushes
               (ts, source_path, coll_uuid, coll_name, mode, action,
                ok, http_status, wf_count, chat_session_id, source_yaml)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (_now(), source_path, coll_uuid, coll_name, mode, action,
             1 if ok else 0, http_status, len(workflows),
             chat_session_id, source_yaml),
        )
        push_id = cur.lastrowid
        for wf in workflows:
            conn.execute(
                """INSERT OR REPLACE INTO push_workflows
                   (push_id, wf_uuid, wf_name, link_url, link_ok)
                   VALUES (?,?,?,?,?)""",
                (push_id, wf["uuid"], wf.get("name"),
                 wf.get("link_url"), 1 if wf.get("link_ok") else 0),
            )
        conn.close()
        return push_id
    except Exception:
        return None


def record_chat_turn(record: dict[str, Any]) -> None:
    """Upsert chat_sessions row + insert chat_turns + chat_tool_calls.
    Called from the provider after each LLM round-trip."""
    try:
        conn = _connect()
        sid = record["session"]
        ts = record.get("ts") or _now()
        conn.execute(
            """INSERT INTO chat_sessions (id, ts_first, ts_last, model)
               VALUES (?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET ts_last=excluded.ts_last""",
            (sid, ts, ts, record.get("model")),
        )
        tags = record.get("tags") or {}
        conn.execute(
            """INSERT OR REPLACE INTO chat_turns
               (session_id, turn, ts, input_tokens, output_tokens,
                cache_read, cache_write, stop_reason, history_chars,
                playbook_collection, yaml_sha)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (sid, record["turn"], ts,
             record.get("input_tokens", 0),
             record.get("output_tokens", 0),
             record.get("cache_read", 0),
             record.get("cache_write", 0),
             record.get("stop_reason"),
             record.get("history_chars", 0),
             tags.get("playbook_collection"),
             tags.get("yaml_sha")),
        )
        for seq, t in enumerate(record.get("tool_calls") or []):
            conn.execute(
                """INSERT OR REPLACE INTO chat_tool_calls
                   (session_id, turn, seq, name, args_chars, result_chars)
                   VALUES (?,?,?,?,?,?)""",
                (sid, record["turn"], seq, t.get("name", "?"),
                 t.get("args_chars", 0), t.get("result_chars", 0)),
            )
        # Recompute session totals from this turn forward (cheap; ≤ low
        # tens of turns per session).
        conn.execute(
            """UPDATE chat_sessions SET
                 total_input      = (SELECT COALESCE(SUM(input_tokens),0)  FROM chat_turns WHERE session_id=?),
                 total_output     = (SELECT COALESCE(SUM(output_tokens),0) FROM chat_turns WHERE session_id=?),
                 total_cache_read = (SELECT COALESCE(SUM(cache_read),0)    FROM chat_turns WHERE session_id=?),
                 total_cache_write= (SELECT COALESCE(SUM(cache_write),0)   FROM chat_turns WHERE session_id=?),
                 turn_count       = (SELECT COUNT(*) FROM chat_turns WHERE session_id=?)
               WHERE id=?""",
            (sid, sid, sid, sid, sid, sid),
        )
        conn.close()
    except Exception:
        pass


# ---- full transcript capture -------------------------------------

# Cap any single message body at this many chars to keep the DB bounded
# even when a tool returns a 200 KB JSON blob. The token-count row in
# `chat_turns` already records the full size, so the cap here doesn't
# lose accounting — only the textual replay tail.
_MESSAGE_CHAR_CAP = 64_000


def record_chat_message(
    session_id: str, turn: int, seq: int,
    kind: str, content: str, *, name: str | None = None,
) -> None:
    """Persist one transcript row (user prompt, assistant text, tool
    use/result). Best-effort; never raises."""
    if not session_id:
        return
    text = (content or "")
    if len(text) > _MESSAGE_CHAR_CAP:
        text = text[:_MESSAGE_CHAR_CAP] + f"\n…[truncated {len(content) - _MESSAGE_CHAR_CAP} chars]"
    try:
        conn = _connect()
        conn.execute(
            """INSERT OR REPLACE INTO chat_messages
               (session_id, turn, seq, ts, kind, name, content)
               VALUES (?,?,?,?,?,?,?)""",
            (session_id, turn, seq, _now(), kind, name, text),
        )
        conn.close()
    except Exception:
        pass


def get_chat_messages(session_id: str) -> list[dict[str, Any]]:
    """Read all transcript rows for a session, in order."""
    try:
        conn = _connect()
        rows = conn.execute(
            "SELECT * FROM chat_messages WHERE session_id=? "
            "ORDER BY turn, seq",
            (session_id,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


# ---- chat ↔ push correlation -------------------------------------

def _active_session_path() -> Path:
    return Path(os.environ.get(
        "FSRPB_ACTIVE_SESSION",
        str(Path.home() / ".fsrpb" / "active_session"),
    )).expanduser()


def write_active_session(session_id: str | None) -> None:
    """Called by the chat backend at session start/end. `None` clears."""
    path = _active_session_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if session_id:
            path.write_text(session_id)
        elif path.exists():
            path.unlink()
    except Exception:
        pass


def read_active_session() -> str | None:
    """Called by `fsrpb push` to stamp the chat session that authored
    the playbook (best-effort; pushes outside a chat session land with
    NULL chat_session_id)."""
    try:
        path = _active_session_path()
        if not path.exists():
            return None
        s = path.read_text().strip()
        return s or None
    except Exception:
        return None


# ---- readers (used by /api/history) ------------------------------

def list_pushes(limit: int = 100, coll_uuid: str | None = None) -> list[dict[str, Any]]:
    conn = _connect()
    if coll_uuid:
        rows = conn.execute(
            """SELECT id, ts, source_path, coll_uuid, coll_name,
                      mode, action, ok, http_status, wf_count,
                      chat_session_id
               FROM pushes
               WHERE coll_uuid=?
               ORDER BY ts DESC LIMIT ?""",
            (coll_uuid, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT id, ts, source_path, coll_uuid, coll_name,
                      mode, action, ok, http_status, wf_count,
                      chat_session_id
               FROM pushes ORDER BY ts DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    out = [dict(r) for r in rows]
    conn.close()
    return out


def get_push(push_id: int) -> dict[str, Any] | None:
    conn = _connect()
    row = conn.execute("SELECT * FROM pushes WHERE id=?", (push_id,)).fetchone()
    if row is None:
        conn.close()
        return None
    push = dict(row)
    push["workflows"] = [
        dict(r) for r in conn.execute(
            "SELECT wf_uuid, wf_name, link_url, link_ok "
            "FROM push_workflows WHERE push_id=? ORDER BY wf_name",
            (push_id,),
        ).fetchall()
    ]
    conn.close()
    return push


def previous_push(coll_uuid: str, before_id: int) -> dict[str, Any] | None:
    conn = _connect()
    row = conn.execute(
        """SELECT * FROM pushes
           WHERE coll_uuid=? AND id < ?
           ORDER BY id DESC LIMIT 1""",
        (coll_uuid, before_id),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def list_chat_sessions(limit: int = 50) -> list[dict[str, Any]]:
    conn = _connect()
    rows = conn.execute(
        """SELECT s.*,
                  (SELECT MAX(t.ts) FROM chat_turns t WHERE t.session_id=s.id) as last_turn_ts
           FROM chat_sessions s ORDER BY ts_last DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    out = [_session_with_cost(dict(r)) for r in rows]
    conn.close()
    return out


def get_chat_session(session_id: str,
                     include_messages: bool = True) -> dict[str, Any] | None:
    """Return a full session record: token accounting, per-turn metadata,
    every tool call, the message transcript, the latest push (carrying
    the deployed YAML), and the user's feedback if any.

    `include_messages=False` keeps the response small for list views
    that don't need the full transcript.
    """
    conn = _connect()
    row = conn.execute(
        "SELECT * FROM chat_sessions WHERE id=?", (session_id,),
    ).fetchone()
    if row is None:
        conn.close()
        return None
    sess = _session_with_cost(dict(row))
    sess["turns"] = [
        dict(r) for r in conn.execute(
            "SELECT * FROM chat_turns WHERE session_id=? ORDER BY turn",
            (session_id,),
        ).fetchall()
    ]
    sess["tool_calls"] = [
        dict(r) for r in conn.execute(
            "SELECT * FROM chat_tool_calls WHERE session_id=? "
            "ORDER BY turn, seq",
            (session_id,),
        ).fetchall()
    ]
    if include_messages:
        sess["messages"] = [
            dict(r) for r in conn.execute(
                "SELECT * FROM chat_messages WHERE session_id=? "
                "ORDER BY turn, seq",
                (session_id,),
            ).fetchall()
        ]
    # Latest push from this session (carries the YAML the agent landed on).
    push_row = conn.execute(
        "SELECT * FROM pushes WHERE chat_session_id=? "
        "ORDER BY id DESC LIMIT 1",
        (session_id,),
    ).fetchone()
    sess["latest_push"] = dict(push_row) if push_row else None
    fb_row = conn.execute(
        "SELECT * FROM chat_feedback WHERE session_id=?",
        (session_id,),
    ).fetchone()
    sess["feedback"] = dict(fb_row) if fb_row else None
    conn.close()
    return sess


def set_feedback(session_id: str, rating: str,
                 summary: str | None = None,
                 tags: str | None = None) -> dict[str, Any]:
    """Upsert thumb-up/thumb-down + review summary for a session."""
    if rating not in ("up", "down"):
        raise ValueError(f"rating must be 'up' or 'down', got {rating!r}")
    conn = _connect()
    # Confirm the session exists; surface a friendly error if not.
    if not conn.execute(
        "SELECT 1 FROM chat_sessions WHERE id=?", (session_id,),
    ).fetchone():
        conn.close()
        raise LookupError(f"no chat session {session_id!r}")
    conn.execute(
        "INSERT INTO chat_feedback (session_id, rating, summary, tags, ts) "
        "VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(session_id) DO UPDATE SET "
        "  rating=excluded.rating, "
        "  summary=excluded.summary, "
        "  tags=excluded.tags, "
        "  ts=excluded.ts",
        (session_id, rating, summary, tags, _now()),
    )
    row = conn.execute(
        "SELECT * FROM chat_feedback WHERE session_id=?", (session_id,),
    ).fetchone()
    conn.close()
    return dict(row)


def clear_feedback(session_id: str) -> bool:
    conn = _connect()
    cur = conn.execute(
        "DELETE FROM chat_feedback WHERE session_id=?", (session_id,),
    )
    conn.close()
    return cur.rowcount > 0


def list_feedback(rating: str | None = None,
                  limit: int = 100) -> list[dict[str, Any]]:
    """List sessions that have feedback, joined with the session
    summary fields the review UI needs (model, turn count, last_ts,
    playbook collection if known)."""
    conn = _connect()
    where = "WHERE 1=1"
    params: list[Any] = []
    if rating:
        where += " AND f.rating=?"
        params.append(rating)
    rows = conn.execute(
        f"""SELECT f.session_id, f.rating, f.summary, f.tags, f.ts AS feedback_ts,
                  s.model, s.turn_count, s.ts_last,
                  (SELECT t.playbook_collection FROM chat_turns t
                   WHERE t.session_id=f.session_id AND t.playbook_collection IS NOT NULL
                   ORDER BY t.turn DESC LIMIT 1) AS playbook_collection
           FROM chat_feedback f
           JOIN chat_sessions s ON s.id = f.session_id
           {where}
           ORDER BY f.ts DESC LIMIT ?""",
        (*params, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def list_chat_sessions_with_feedback(limit: int = 50) -> list[dict[str, Any]]:
    """Variant of list_chat_sessions that joins in feedback for the
    list view's thumb indicator + a count of tool calls per session."""
    conn = _connect()
    rows = conn.execute(
        """SELECT s.*,
                  (SELECT MAX(t.ts) FROM chat_turns t WHERE t.session_id=s.id) as last_turn_ts,
                  (SELECT t.playbook_collection FROM chat_turns t
                   WHERE t.session_id=s.id AND t.playbook_collection IS NOT NULL
                   ORDER BY t.turn DESC LIMIT 1) AS playbook_collection,
                  (SELECT COUNT(*) FROM chat_tool_calls c WHERE c.session_id=s.id) AS tool_call_count,
                  f.rating AS feedback_rating,
                  f.summary AS feedback_summary
           FROM chat_sessions s
           LEFT JOIN chat_feedback f ON f.session_id = s.id
           ORDER BY ts_last DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    out = [_session_with_cost(dict(r)) for r in rows]
    conn.close()
    return out


def _session_with_cost(s: dict[str, Any]) -> dict[str, Any]:
    """Annotate a chat_sessions row with an estimated USD cost based on
    PRICING_USD_PER_MTOK. Cost is computed on read so a pricing change
    retroactively reprices history."""
    s["est_cost_usd"] = _estimate_cost(
        s.get("model") or "",
        s.get("total_input", 0) or 0,
        s.get("total_output", 0) or 0,
        s.get("total_cache_read", 0) or 0,
        s.get("total_cache_write", 0) or 0,
    )
    return s


def timeline(limit: int = 50) -> list[dict[str, Any]]:
    """Mixed pushes + chat sessions, newest first. Each item carries
    `kind: 'push'|'chat'` plus the row's columns."""
    pushes = [{"kind": "push", **p} for p in list_pushes(limit)]
    chats = [{"kind": "chat", **c, "ts": c.get("ts_last")}
             for c in list_chat_sessions(limit)]
    items = pushes + chats
    items.sort(key=lambda x: x.get("ts") or "", reverse=True)
    return items[:limit]


def cost_by_playbook(limit: int = 50) -> list[dict[str, Any]]:
    """Token + estimated USD cost grouped by `playbook_collection`
    tag. Drives the per-playbook cost view: 'this YAML has cost
    you $X across N chat turns'."""
    conn = _connect()
    rows = conn.execute(
        """SELECT
              t.playbook_collection AS collection,
              COUNT(*) AS turn_count,
              COUNT(DISTINCT t.session_id) AS session_count,
              SUM(t.input_tokens)   AS total_input,
              SUM(t.output_tokens)  AS total_output,
              SUM(t.cache_read)     AS total_cache_read,
              SUM(t.cache_write)    AS total_cache_write,
              MAX(t.ts) AS last_ts
           FROM chat_turns t
           WHERE t.playbook_collection IS NOT NULL
             AND t.playbook_collection != ''
           GROUP BY t.playbook_collection
           ORDER BY MAX(t.ts) DESC
           LIMIT ?""",
        (limit,),
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        # Resolve a representative model for the collection — pick the
        # most recent session that touched it. SQLite forbids
        # correlated subqueries referencing aggregates, so do it as a
        # follow-up query.
        model_row = conn.execute(
            """SELECT s.model FROM chat_sessions s
               JOIN chat_turns ct ON ct.session_id = s.id
               WHERE ct.playbook_collection = ?
               ORDER BY ct.ts DESC LIMIT 1""",
            (d["collection"],),
        ).fetchone()
        model = model_row["model"] if model_row else ""
        d["model"] = model
        d["est_cost_usd"] = _estimate_cost(
            model or "",
            d.get("total_input", 0) or 0,
            d.get("total_output", 0) or 0,
            d.get("total_cache_read", 0) or 0,
            d.get("total_cache_write", 0) or 0,
        )
        out.append(d)
    conn.close()
    return out


def _estimate_cost(model: str, in_tok: int, out_tok: int,
                   cache_r: int, cache_w: int) -> float | None:
    p = _resolve_pricing(model)
    if p is None:
        return None
    cost = (in_tok * p["input"] + out_tok * p["output"]
            + cache_r * p["cache_read"] + cache_w * p["cache_write"])
    return round(cost / 1_000_000, 5)


def _resolve_pricing(model: str) -> dict[str, float] | None:
    """Match a model id (with or without date suffix) to the pricing
    table. Try exact, then strip a trailing 8-digit date, then any
    rsplit-by-`-` prefix, in that order."""
    if not model:
        return None
    if model in PRICING_USD_PER_MTOK:
        return PRICING_USD_PER_MTOK[model]
    # Strip a trailing date suffix like `-20250929`.
    parts = model.rsplit("-", 1)
    if len(parts) == 2 and parts[1].isdigit() and len(parts[1]) == 8:
        if parts[0] in PRICING_USD_PER_MTOK:
            return PRICING_USD_PER_MTOK[parts[0]]
    # Fall back to longest prefix match (in case future versions add
    # extra suffixes we don't anticipate).
    candidates = [k for k in PRICING_USD_PER_MTOK if model.startswith(k)]
    if candidates:
        return PRICING_USD_PER_MTOK[max(candidates, key=len)]
    return None


def yaml_diff(left_yaml: str, right_yaml: str,
              left_label: str = "before", right_label: str = "after") -> str:
    """Unified diff between two YAML snapshots. Returns plain text;
    rendering to a side-by-side view is the frontend's problem."""
    import difflib
    return "".join(difflib.unified_diff(
        (left_yaml or "").splitlines(keepends=True),
        (right_yaml or "").splitlines(keepends=True),
        fromfile=left_label, tofile=right_label,
        n=3,
    ))
