"""One approval card for the gated calls a model emits together.

A build is N writes in one assistant turn -- seven step creates for a
seven-step profile. Only the first used to card and the rest were dropped, so
the analyst faced seven cards for one request (and, before the drop was
reported honestly, the model claimed all seven were done). Now the gated calls
right behind the first share its card: approve runs them all in order, deny
runs none, and every listed call is HMAC-bound.

What must NOT ride along: a call that would not card (an ungated read runs
out of order if it is swept in) or one its pre-card validator refuses (it
would run under an approval it never had). Both end the batch and are dropped
exactly as before.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

from fsr_playbooks.llm import approvals as A
from fsr_playbooks.llm.approvals import InMemoryApprovalGateway
from fsr_playbooks.llm.provider import (
    ApprovalRequestEvent, Message, ToolResultEvent, ToolUseEvent,
)
from fsr_playbooks.tests.test_openai_provider import (
    _BLOCK_IP_TOOLS, _delta_chunk, _drain, _provider, _tool_call_delta,
    _usage_chunk,
)


def _envelope(aid="appr_b", summary="Block"):
    return {"pending_approval": True, "approval_id": aid, "tier": 3,
            "tool": "block_ip", "preview": {}, "args_hash": "h",
            "summary": summary, "requires_step_up": False}


def _turn(ips):
    calls = [_tool_call_delta(index=i, id=f"call_{i}", name="block_ip",
                              args=f'{{"ip":"{ip}"}}') for i, ip in enumerate(ips)]
    return [_delta_chunk(tool_calls=calls), _delta_chunk(finish="tool_calls"),
            _usage_chunk()]


def _suspend(ips, *, dispatch_side_effect=None, tier_side_effect=None):
    gw = InMemoryApprovalGateway()
    post = [_delta_chunk(content="Done."), _delta_chunk(finish="stop"), _usage_chunk()]
    p = _provider([_turn(ips), post], gateway=gw)
    with patch("fsr_playbooks.llm.openai_provider.dispatch",
               side_effect=dispatch_side_effect or (lambda n, a: _envelope(summary=f"Block {a['ip']}"))), \
         patch("fsr_playbooks.llm.openai_provider._tier_for",
               side_effect=tier_side_effect or (lambda n, a: 3)):
        events = asyncio.run(_drain(p.stream(
            system="sys", messages=[Message(role="user", content="block them")],
            tools=_BLOCK_IP_TOOLS, tags={})))
    appr = next(e for e in events if isinstance(e, ApprovalRequestEvent))
    return p, gw.pop(appr.approval_id), appr


def test_gated_calls_behind_the_first_share_its_card():
    _, s, appr = _suspend(["1.1.1.1", "2.2.2.2", "3.3.3.3"])
    assert [b["args"]["ip"] for b in appr.batch] == ["2.2.2.2", "3.3.3.3"]
    assert [b["summary"] for b in appr.batch] == ["Block 2.2.2.2", "Block 3.3.3.3"]
    assert [b.call_id for b in s.batch] == ["call_1", "call_2"]
    assert s.remaining_tool_calls == []


def test_approve_runs_every_listed_call_in_order():
    p, s, _ = _suspend(["1.1.1.1", "2.2.2.2", "3.3.3.3"])
    ran = []

    def fake(name, args, _internal=False):
        ran.append((args["ip"], args.get("_approved"), _internal))
        return {"ok": True, "blocked": args["ip"]}
    with patch("fsr_playbooks.llm.openai_provider.dispatch", side_effect=fake), \
         patch("fsr_playbooks.llm.tools.dispatch", side_effect=fake):
        events = asyncio.run(_drain(p.resume(suspended=s, decision="approve")))
    assert ran == [("1.1.1.1", True, True), ("2.2.2.2", True, True),
                   ("3.3.3.3", True, True)]
    results = {e.call_id: e.result for e in events if isinstance(e, ToolResultEvent)}
    assert all(results[f"call_{i}"]["ok"] for i in range(3))
    # Each batched result is preceded by a named tool_use, as the pending one is.
    uses = [e.call_id for e in events if isinstance(e, ToolUseEvent)]
    assert uses[:3] == ["call_0", "call_1", "call_2"]


def test_deny_runs_none():
    p, s, _ = _suspend(["1.1.1.1", "2.2.2.2"])
    with patch("fsr_playbooks.llm.openai_provider.dispatch") as d1, \
         patch("fsr_playbooks.llm.tools.dispatch") as d2:
        events = asyncio.run(_drain(p.resume(suspended=s, decision="deny")))
    d1.assert_not_called()
    d2.assert_not_called()
    codes = [e.result.get("code") for e in events if isinstance(e, ToolResultEvent)]
    assert codes[:2] == ["user_denied", "user_denied"]


def test_an_ungated_call_ends_the_batch_and_is_never_probed():
    probed = []

    def disp(n, a):
        probed.append(a["ip"])
        return _envelope()
    _, s, appr = _suspend(
        ["1.1.1.1", "2.2.2.2", "3.3.3.3"], dispatch_side_effect=disp,
        tier_side_effect=lambda n, a: 1 if a.get("ip") == "2.2.2.2" else 3)
    assert appr.batch == [] and s.batch == []
    # The ungated call never ran at suspension -- it would have run out of order.
    assert probed == ["1.1.1.1"]
    assert [c.call_id for c in s.remaining_tool_calls] == ["call_1", "call_2"]


def test_a_refused_call_ends_the_batch():
    def disp(n, a):
        if a["ip"] == "3.3.3.3":
            return {"ok": False, "code": "unknown_record"}
        return _envelope()
    _, s, appr = _suspend(["1.1.1.1", "2.2.2.2", "3.3.3.3", "4.4.4.4"],
                          dispatch_side_effect=disp)
    assert [b["args"]["ip"] for b in appr.batch] == ["2.2.2.2"]
    assert [c.call_id for c in s.remaining_tool_calls] == ["call_2", "call_3"]


def test_a_tampered_batch_member_fails_the_binding():
    _, s, _ = _suspend(["1.1.1.1", "2.2.2.2"])
    assert A.verify(s)
    s.batch[0].args = {"ip": "6.6.6.6"}
    assert not A.verify(s)


def test_a_single_call_token_is_unchanged_by_batching():
    """Sessions stashed before batching existed must still verify."""
    s = A.SuspendedSession(
        approval_id="a", session_id="s", tool="t", tool_use_id="u", args={"x": 1},
        tier=3, history_snapshot=[], prior_tool_result_blocks=[],
        remaining_tool_calls=[], system="", tags={}, created_at=1.0)
    legacy = A._bind_token("a", "t", {"x": 1}, 1.0)
    A.bind(s)
    assert s.token == legacy


def test_every_provider_batches_the_same_way():
    """Parallel implementations drift; a provider that still drops the batch
    would bring back seven cards (or seven lost writes) for that provider."""
    llm = Path(A.__file__).parent
    for name in ("openai_provider.py", "anthropic_provider.py",
                 "fortiai_proxy_provider.py"):
        text = (llm / name).read_text()
        assert "_approvals.collect_batch(" in text, name
        assert "_approvals.resolve_batch" in text, name
        assert "batch=batch" in text and "batch=[b.card() for b in batch]" in text, name
