"""Suspended-session store for the HITL approval flow.

When a provider loop hits a tier-3+ tool call, it stashes everything
needed to resume — history snapshot, system prompt, tools list, tags,
the pending tool_use id, and the original tool args — under the
`approval_id` minted by `tools.dispatch`. A subsequent POST to
`/api/approvals/{approval_id}` resolves the decision: on approve we
re-dispatch with the internal `_approved=True` sentinel and patch the
synthetic tool_result; on deny we substitute `{ok: false,
code: "user_denied"}` and resume. The HITL guardrails plan calls for
single-use scope, so each entry is consumed (popped) on resolution.

This is in-memory: the chat backend is single-process today. If we
later run multiple workers, swap the dict for Redis or sqlite-backed
storage — the public surface (`stash`, `pop`, `peek`) is small enough
that the migration is mechanical.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets as _secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SkippedToolCall:
    """A tool call from the same assistant turn that was not dispatched
    because an earlier call in the same turn triggered an approval gate.

    On resume, these are synthesized as superseded_by_approval results
    so the model receives one tool_result per tool_use it emitted.
    """
    call_id: str
    name: str
    args: dict[str, Any]


# 10 minutes. Long enough that a user can context-switch to read the
# args; short enough that a stale approval doesn't sit around for hours
# if someone walks away.
_TTL_SECONDS = 600


# --- HMAC binding (Phase 3.1) ---------------------------------------------
#
# The in-memory record already binds the decision to its args (resume
# re-dispatches `suspended.args`, never request-supplied args). HMAC closes
# the *store-tampering* gap: if the session store leaks or is writable
# (e.g. the persisted/sqlite-backed gateway in 3.2), an attacker could swap
# the stored args before the human approves and the server would re-dispatch
# the substituted call. We bind `approval_id + tool + args_hash + created_at`
# under a server-side secret at stash time; `verify()` recomputes the token
# at resume and `compare_digest`s it. Tampered args change `args_hash`, so
# the token no longer matches and resume fails closed.
#
# Secret resolution, in order:
#   1. `FSR_APPROVAL_HMAC_KEY` env var — explicit, deployment-controlled.
#   2. A per-host key FILE (default ~/.fsr_approval_hmac_key, 0600), created once
#      and read by every worker. This is what makes the persisted gateway work
#      across FortiSOAR's MULTIPLE worker processes: chat_turn stashes a session
#      on one worker and chat_resume pops it on another, so the token must verify
#      under a secret ALL workers agree on. A per-process random key cannot do
#      that — cross-worker resume fails closed with approval_not_found — which is
#      exactly the bug this replaces. The file also survives worker restarts.
#   3. Per-process random key — last resort, only if the file can't be read or
#      created (e.g. a read-only FS). Degrades to the old cross-worker behavior
#      rather than crashing.
_SECRET_ENV = "FSR_APPROVAL_HMAC_KEY"
_SECRET_FILE_ENV = "FSR_APPROVAL_HMAC_KEY_FILE"
_RUNTIME_SECRET = _secrets.token_bytes(32)
_PERSISTENT_SECRET: bytes | None = None


def _default_key_file():
    from pathlib import Path
    return Path.home() / ".fsr_approval_hmac_key"


def _persistent_secret() -> bytes:
    """A stable 32-byte secret shared by every worker on the host.

    Provisioned once into a 0600 key file; concurrent workers race to create it
    via O_CREAT|O_EXCL and the losers read the winner's key, so every worker ends
    up with the same secret. Cached after the first resolution. Falls back to the
    per-process key if the filesystem is unavailable."""
    global _PERSISTENT_SECRET
    if _PERSISTENT_SECRET is not None:
        return _PERSISTENT_SECRET
    from pathlib import Path
    path = Path(os.environ.get(_SECRET_FILE_ENV) or _default_key_file())
    try:
        if path.exists():
            key = bytes.fromhex(path.read_text().strip())
            if len(key) >= 16:
                _PERSISTENT_SECRET = key
                return key
        path.parent.mkdir(parents=True, exist_ok=True)
        key = _secrets.token_bytes(32)
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            try:
                os.write(fd, key.hex().encode("ascii"))
            finally:
                os.close(fd)
        except FileExistsError:
            # Another worker created it first — adopt its key.
            key = bytes.fromhex(path.read_text().strip())
        _PERSISTENT_SECRET = key
        return key
    except Exception:
        # Read-only / unavailable FS: keep working with the per-process key.
        _PERSISTENT_SECRET = _RUNTIME_SECRET
        return _PERSISTENT_SECRET


def _secret() -> bytes:
    env = os.environ.get(_SECRET_ENV)
    if env:
        return env.encode("utf-8")
    return _persistent_secret()


def _canonical_args_hash(tool: str, args: dict[str, Any] | None) -> str:
    # Same canonical serialization as tools._args_hash, kept local to avoid
    # a tools→approvals import cycle. Full digest (not truncated) here since
    # this is a tamper check, not a log key.
    payload = json.dumps(
        {"tool": tool, "args": args or {}}, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _bind_token(approval_id: str, tool: str,
                args: dict[str, Any] | None, created_at: float) -> str:
    msg = "|".join((
        approval_id, tool, _canonical_args_hash(tool, args), repr(created_at),
    )).encode("utf-8")
    return hmac.new(_secret(), msg, hashlib.sha256).hexdigest()


def bind(s: "SuspendedSession") -> None:
    """Compute and attach the HMAC token. Call once, after construction,
    before stashing."""
    s.token = _bind_token(s.approval_id, s.tool, s.args, s.created_at)


def verify(s: "SuspendedSession") -> bool:
    """True iff the session's token matches a freshly computed HMAC over its
    current fields. A missing token fails closed."""
    if not s.token:
        return False
    expected = _bind_token(s.approval_id, s.tool, s.args, s.created_at)
    return hmac.compare_digest(s.token, expected)


@dataclass
class SuspendedSession:
    approval_id: str
    session_id: str
    tool: str
    tool_use_id: str
    args: dict[str, Any]
    tier: int
    # Wire-form history up to (but NOT including) the user turn that
    # would carry the tool_result blocks for the just-stopped assistant
    # turn. The assistant turn (text + tool_use blocks) IS included.
    history_snapshot: list[Any]
    # tool_result blocks for tool_uses that resolved before the
    # pending one. Resume appends these + the resolved pending result
    # + placeholder denials for `remaining_tool_calls` into a single
    # user turn before re-entering the provider loop.
    prior_tool_result_blocks: list[dict[str, Any]]
    # Tool calls from the same assistant turn that hadn't run yet
    # when we suspended. Stored as (call_id, name, args). On resume
    # they're synthesized as `{ok: false, code: "superseded_by_approval"}`
    # so the model sees one tool_result per tool_use it emitted.
    remaining_tool_calls: list[SkippedToolCall]
    system: str
    tags: dict[str, Any]
    summary: str | None = None
    created_at: float = field(default_factory=time.time)
    # HMAC token binding (approval_id, tool, args_hash, created_at) under the
    # server secret. Set by `bind()` before stash; checked by `verify()` on
    # resume. Empty until bound (verify fails closed on empty).
    token: str = ""

    def expired(self, now: float | None = None) -> bool:
        return (now or time.time()) - self.created_at > _TTL_SECONDS


class InMemoryApprovalGateway:
    """In-process implementation of the ApprovalGateway protocol.
    Single-process workers only; for multi-worker / connector use,
    swap in a sqlite- or Redis-backed gateway."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._store: dict[str, SuspendedSession] = {}

    def stash(self, s: SuspendedSession) -> None:
        with self._lock:
            self._gc_locked()
            self._store[s.approval_id] = s

    def peek(self, approval_id: str) -> SuspendedSession | None:
        with self._lock:
            self._gc_locked()
            return self._store.get(approval_id)

    def pop(self, approval_id: str) -> SuspendedSession | None:
        """Single-use consume. Returns None if missing or expired."""
        with self._lock:
            self._gc_locked()
            s = self._store.pop(approval_id, None)
            if s and s.expired():
                return None
            return s

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    def _gc_locked(self) -> None:
        now = time.time()
        dead = [k for k, v in self._store.items() if v.expired(now)]
        for k in dead:
            self._store.pop(k, None)


class SqliteApprovalGateway:
    """Phase 3.2 — sqlite-backed gateway so suspended HITL sessions survive a
    worker restart. The web backend installs one at startup via
    `set_default_gateway`; the connector has its own equivalent in
    `storage.py`.

    Each op opens a short-lived connection (sqlite handles its own locking),
    so the gateway is cheap to construct and safe across threads. Sessions
    are pickled — both writer and reader are this same process family, and an
    attacker who can write our sqlite file already has code-exec; the HMAC
    binding (3.1) is what guards against *content* tampering. For tokens to
    survive a restart the process must run with a stable
    `FSR_APPROVAL_HMAC_KEY` (else `verify()` fails closed afterward — safe,
    the analyst just re-issues)."""

    _SCHEMA = (
        "CREATE TABLE IF NOT EXISTS suspended_sessions ("
        " approval_id TEXT PRIMARY KEY,"
        " created_at REAL NOT NULL,"
        " payload BLOB NOT NULL)"
    )

    def __init__(self, db_path: str) -> None:
        self.db_path = str(db_path)
        self._lock = threading.Lock()
        with self._conn() as c:
            c.execute(self._SCHEMA)

    def _conn(self):  # sqlite3.Connection
        import sqlite3
        c = sqlite3.connect(self.db_path, timeout=5.0)
        return c

    def _gc(self, c) -> None:
        c.execute("DELETE FROM suspended_sessions WHERE created_at < ?",
                  (time.time() - _TTL_SECONDS,))

    def stash(self, s: SuspendedSession) -> None:
        import pickle  # noqa: S403 — round-trips our own dataclass, same process family
        blob = pickle.dumps(s, protocol=pickle.HIGHEST_PROTOCOL)
        with self._lock, self._conn() as c:
            self._gc(c)
            c.execute(
                "INSERT OR REPLACE INTO suspended_sessions"
                " (approval_id, created_at, payload) VALUES (?, ?, ?)",
                (s.approval_id, s.created_at, blob),
            )

    def _load(self, c, approval_id: str) -> SuspendedSession | None:
        import pickle  # noqa: S403
        row = c.execute(
            "SELECT payload FROM suspended_sessions WHERE approval_id = ?",
            (approval_id,),
        ).fetchone()
        if row is None:
            return None
        s = pickle.loads(row[0])  # noqa: S301 — our own file, see class docstring
        return None if s.expired() else s

    def peek(self, approval_id: str) -> SuspendedSession | None:
        with self._lock, self._conn() as c:
            self._gc(c)
            return self._load(c, approval_id)

    def pop(self, approval_id: str) -> SuspendedSession | None:
        with self._lock, self._conn() as c:
            self._gc(c)
            s = self._load(c, approval_id)
            c.execute("DELETE FROM suspended_sessions WHERE approval_id = ?",
                      (approval_id,))
            return s

    def clear(self) -> None:
        with self._lock, self._conn() as c:
            c.execute("DELETE FROM suspended_sessions")


# Backwards-compat facade. Existing callers (web/backend/routes/chat.py,
# tests, and the provider's fallback path) use the module-level functions
# against a process-wide default gateway. `set_default_gateway` lets the web
# backend swap in a SqliteApprovalGateway at startup so both the stash side
# (provider) and the resolve side (chat route) share one persisted store
# without any further wiring. The connector instantiates its own gateway and
# passes it to the provider explicitly rather than touching this singleton.
_DEFAULT: InMemoryApprovalGateway | SqliteApprovalGateway = (
    InMemoryApprovalGateway()
)


def set_default_gateway(
    gw: "InMemoryApprovalGateway | SqliteApprovalGateway",
) -> None:
    global _DEFAULT
    _DEFAULT = gw


def get_default_gateway() -> "InMemoryApprovalGateway | SqliteApprovalGateway":
    return _DEFAULT


def stash(s: SuspendedSession) -> None:
    _DEFAULT.stash(s)


def peek(approval_id: str) -> SuspendedSession | None:
    return _DEFAULT.peek(approval_id)


def pop(approval_id: str) -> SuspendedSession | None:
    return _DEFAULT.pop(approval_id)


def clear() -> None:
    _DEFAULT.clear()
