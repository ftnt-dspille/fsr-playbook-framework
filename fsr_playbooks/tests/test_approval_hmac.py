"""Phase 3.1 — HMAC-bound approvals.

The suspended-session store binds (approval_id, tool, args_hash, created_at)
under a server secret at stash time. `verify()` recomputes the token at resume
and `compare_digest`s it, so store tampering (swapping the stored args before a
human approves) is detected and resume fails closed.

Covers the binding logic directly + the provider's resume() rejection path.
"""
from __future__ import annotations

import asyncio
import secrets
import stat


from fsr_playbooks.llm import approvals as A
from fsr_playbooks.llm.anthropic_provider import AnthropicProvider
from fsr_playbooks.llm.provider import DoneEvent, ErrorEvent, ToolResultEvent


def _session(**over):
    base = dict(
        approval_id="ap-1",
        session_id="s-1",
        tool="run_op",
        tool_use_id="tu-1",
        args={"connector": "fortigate", "op": "block_ip",
              "params": {"ip": "10.0.0.5"}},
        tier=3,
        history_snapshot=[],
        prior_tool_result_blocks=[],
        remaining_tool_calls=[],
        system="sys",
        tags={},
    )
    base.update(over)
    return A.SuspendedSession(**base)


# --- unit: bind / verify ---------------------------------------------------

def test_bind_then_verify_ok():
    s = _session()
    assert s.token == ""
    A.bind(s)
    assert s.token  # populated
    assert A.verify(s) is True


def test_unbound_session_fails_closed():
    # A session that was never bound must not verify.
    assert A.verify(_session()) is False


def test_arg_tamper_is_detected():
    s = _session()
    A.bind(s)
    # Attacker swaps the target IP in the leaked/writable store.
    s.args = {"connector": "fortigate", "op": "block_ip",
              "params": {"ip": "8.8.8.8"}}
    assert A.verify(s) is False


def test_tool_tamper_is_detected():
    s = _session()
    A.bind(s)
    s.tool = "delete_record"
    assert A.verify(s) is False


def test_token_tamper_is_detected():
    s = _session()
    A.bind(s)
    s.token = s.token[:-1] + ("0" if s.token[-1] != "0" else "1")
    assert A.verify(s) is False


def test_secret_from_env_is_stable_across_processes(monkeypatch):
    # With a fixed env secret, a token minted "before a restart" still
    # verifies "after" — the property 3.2 relies on for persistence.
    monkeypatch.setenv(A._SECRET_ENV, "stable-test-secret")
    s = _session()
    A.bind(s)
    tok = s.token
    # Recompute independently (simulating a fresh process with same env).
    assert A._bind_token(s.approval_id, s.tool, s.args, s.created_at) == tok


# --- persistent per-host key (cross-worker resume) -------------------------

def _use_key_file(monkeypatch, key_file):
    monkeypatch.delenv(A._SECRET_ENV, raising=False)          # no explicit env key
    monkeypatch.setenv(A._SECRET_FILE_ENV, str(key_file))
    monkeypatch.setattr(A, "_PERSISTENT_SECRET", None)         # clear the cache


def test_persistent_key_shared_across_workers(tmp_path, monkeypatch):
    # The core fix: a session stashed by one worker (random per-process key)
    # verifies on ANOTHER worker, because both read the same key file. Without
    # it, cross-worker resume fails closed → approval_not_found.
    kf = tmp_path / "hmac.key"
    _use_key_file(monkeypatch, kf)
    monkeypatch.setattr(A, "_RUNTIME_SECRET", secrets.token_bytes(32))  # worker A
    s = _session()
    A.bind(s)
    assert A.verify(s) is True
    assert kf.exists()

    # Worker B: different per-process key + cold cache, SAME key file.
    monkeypatch.setattr(A, "_PERSISTENT_SECRET", None)
    monkeypatch.setattr(A, "_RUNTIME_SECRET", secrets.token_bytes(32))
    assert A.verify(s) is True


def test_persistent_key_file_is_0600(tmp_path, monkeypatch):
    kf = tmp_path / "k.key"
    _use_key_file(monkeypatch, kf)
    A._persistent_secret()
    assert stat.S_IMODE(kf.stat().st_mode) == 0o600


def test_env_key_takes_precedence_over_file(tmp_path, monkeypatch):
    kf = tmp_path / "k.key"
    _use_key_file(monkeypatch, kf)
    A._persistent_secret()  # provision the file
    monkeypatch.setenv(A._SECRET_ENV, "env-secret")
    assert A._secret() == b"env-secret"


def test_unwritable_key_file_falls_back_to_runtime(tmp_path, monkeypatch):
    # A read-only / bad path must degrade to the per-process key, never crash.
    not_a_dir = tmp_path / "not_a_dir"
    not_a_dir.write_text("x")
    monkeypatch.delenv(A._SECRET_ENV, raising=False)
    monkeypatch.setenv(A._SECRET_FILE_ENV, str(not_a_dir / "k.key"))  # parent is a file
    rt = secrets.token_bytes(32)
    monkeypatch.setattr(A, "_RUNTIME_SECRET", rt)
    monkeypatch.setattr(A, "_PERSISTENT_SECRET", None)
    assert A._persistent_secret() == rt


# --- provider resume() fail-closed -----------------------------------------

def test_resume_rejects_unverified_session():
    """A tampered (or unbound) session must not re-dispatch; resume emits an
    ErrorEvent + DoneEvent(approval_unverified) and never calls dispatch."""
    called = {"dispatch": False}

    def _boom(name, args):  # pragma: no cover - must not run
        called["dispatch"] = True
        return {"ok": True}

    provider = AnthropicProvider(model="fake", client=object())

    s = _session()  # never bound → verify() is False

    async def _drain():
        evs = []
        # patch dispatch on the module to detect any execution attempt
        import fsr_playbooks.llm.anthropic_provider as mod
        orig = mod.dispatch
        mod.dispatch = _boom
        try:
            async for ev in provider.resume(suspended=s, decision="approve"):
                evs.append(ev)
        finally:
            mod.dispatch = orig
        return evs

    events = asyncio.run(_drain())

    assert called["dispatch"] is False
    assert any(isinstance(e, ErrorEvent) for e in events)
    done = [e for e in events if isinstance(e, DoneEvent)]
    assert done and done[-1].stop_reason == "approval_unverified"
    # No tool result was produced for the (unexecuted) action.
    assert not [e for e in events if isinstance(e, ToolResultEvent)]
