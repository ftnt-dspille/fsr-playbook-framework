"""Phase 3.2 — sqlite-backed approval gateway (restart durability).

A SuspendedSession stashed by one gateway instance must be readable by a
fresh instance over the same db file (simulating a worker restart), and the
3.1 HMAC binding must still verify when the secret is stable.
"""
from __future__ import annotations

import time

from fsr_core.llm import approvals as A


def _session(approval_id="ap-1", **over):
    base = dict(
        approval_id=approval_id,
        session_id="s-1",
        tool="run_op",
        tool_use_id="tu-1",
        args={"connector": "fortigate", "op": "block_ip",
              "params": {"ip": "10.0.0.5"}},
        tier=3,
        history_snapshot=[{"role": "user", "content": "x"}],
        prior_tool_result_blocks=[],
        remaining_tool_calls=[],
        system="sys",
        tags={"k": "v"},
    )
    base.update(over)
    return A.SuspendedSession(**base)


def test_session_survives_restart(tmp_path):
    db = str(tmp_path / "approvals.db")
    gw1 = A.SqliteApprovalGateway(db)
    s = _session()
    gw1.stash(s)

    # Fresh instance over the same file == a new worker after restart.
    gw2 = A.SqliteApprovalGateway(db)
    got = gw2.peek("ap-1")
    assert got is not None
    assert got.tool == "run_op"
    assert got.args["params"]["ip"] == "10.0.0.5"
    assert got.tags == {"k": "v"}


def test_pop_is_single_use(tmp_path):
    db = str(tmp_path / "approvals.db")
    gw = A.SqliteApprovalGateway(db)
    gw.stash(_session())
    assert gw.pop("ap-1") is not None
    assert gw.pop("ap-1") is None
    # And a fresh instance also sees it gone.
    assert A.SqliteApprovalGateway(db).peek("ap-1") is None


def test_expired_session_not_returned(tmp_path, monkeypatch):
    db = str(tmp_path / "approvals.db")
    gw = A.SqliteApprovalGateway(db)
    s = _session(created_at=time.time() - (A._TTL_SECONDS + 10))
    gw.stash(s)
    assert gw.peek("ap-1") is None


def test_hmac_survives_restart_with_stable_secret(tmp_path, monkeypatch):
    monkeypatch.setenv(A._SECRET_ENV, "stable-secret-for-persistence")
    db = str(tmp_path / "approvals.db")
    s = _session()
    A.bind(s)
    A.SqliteApprovalGateway(db).stash(s)

    restored = A.SqliteApprovalGateway(db).pop("ap-1")
    assert restored is not None
    # Same stable secret → binding still verifies after "restart".
    assert A.verify(restored) is True


def test_set_default_gateway_routes_module_functions(tmp_path):
    db = str(tmp_path / "approvals.db")
    gw = A.SqliteApprovalGateway(db)
    prev = A.get_default_gateway()
    try:
        A.set_default_gateway(gw)
        A.stash(_session(approval_id="ap-mod"))
        assert A.peek("ap-mod") is not None
        assert A.pop("ap-mod") is not None
        assert A.peek("ap-mod") is None
    finally:
        A.set_default_gateway(prev)
