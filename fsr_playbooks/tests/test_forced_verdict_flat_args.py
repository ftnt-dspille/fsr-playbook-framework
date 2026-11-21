"""The forced verdict round accepts fields sent flat and repairs an empty payload.

A forced verdict round emitted ``emit_card`` with an empty payload, then with
the verdict fields flat beside ``card_type``, and no verdict was delivered. The
schema keeps one shape (``payload``); the round folds the common slip into it,
and an empty payload gets a repair message that names the required fields.
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

from test_openai_build_progress_forced import _FakeStream
from test_verdict_forced_on_full_surface import (
    _TOOLS,
    _drain,
    _hunt_round,
    _prose,
)

from fsr_playbooks.llm._loop_helpers import (
    lift_flat_verdict_args,
    verdict_repair_directive,
)
from fsr_playbooks.llm.openai_provider import OpenAIProvider
from fsr_playbooks.llm.provider import Message

_FIELDS = {"disposition": "true_positive", "severity": "high", "confidence": 0.8,
           "summary": "Beacons to a known C2.",
           "findings": [{"claim": "beacons", "evidence": ["c2"]}], "unknowns": []}


def _response(args):
    fn = MagicMock()
    fn.name = "emit_card"
    fn.arguments = json.dumps(args)
    call = MagicMock(id="c_forced", function=fn)
    return MagicMock(choices=[MagicMock(message=MagicMock(tool_calls=[call]))])


def _run(forced_args):
    streams = [_FakeStream(r) for r in [_hunt_round(), _prose()]]
    forced = [_response(a) for a in forced_args]

    async def _create(*_a, **kw):
        return streams.pop(0) if kw.get("stream") else forced.pop(0)

    client = MagicMock()
    client.chat = MagicMock()
    client.chat.completions = MagicMock(create=AsyncMock(side_effect=_create))
    p = OpenAIProvider(model="gpt-5.4-mini", base_url="http://x/v1", api_key="x",
                       client=client)

    def _dispatch(name, args, *a, **k):
        if name == "emit_card" and args.get("card_type") == "verdict" \
                and not args.get("payload"):
            return {"ok": False, "message": "payload for card_type 'verdict' is missing"}
        return {"ok": True}

    with patch("fsr_playbooks.llm.agent_loop.dispatch", MagicMock(side_effect=_dispatch)) as disp, \
         patch("fsr_playbooks.llm.agent_loop._tier_for", return_value=0):
        asyncio.run(_drain(p.stream(
            system="s", messages=[Message(role="user", content="investigate this alert")],
            tools=_TOOLS, tags={})))
    return [c.args[1] for c in disp.call_args_list
            if c.args[0] == "emit_card" and c.args[1].get("card_type") == "verdict"]


def test_flat_fields_are_folded_into_the_payload():
    sent = _run([{"card_type": "verdict", **_FIELDS}])
    assert sent and sent[0]["payload"]["disposition"] == "true_positive"
    assert sent[0]["payload"]["findings"] == _FIELDS["findings"]
    assert "disposition" not in sent[0]


def test_flat_fields_after_an_empty_payload_still_deliver_without_a_repair_round():
    sent = _run([{"card_type": "verdict", "payload": {}, **_FIELDS}])
    assert len(sent) == 1 and sent[0]["payload"]["summary"] == _FIELDS["summary"]


def test_a_real_payload_is_untouched_and_wins_over_flat_copies():
    args = {"card_type": "verdict", "payload": {"disposition": "benign"},
            "disposition": "true_positive", "summary": "s"}
    lift_flat_verdict_args(args)
    assert args["payload"] == {"disposition": "benign", "summary": "s"}
    assert set(args) == {"card_type", "payload"}


def test_an_empty_payload_repair_names_the_required_fields():
    msg = verdict_repair_directive({"ok": False, "message": "invalid payload"},
                                   {"card_type": "verdict", "payload": {}})
    for field in ("disposition", "severity", "confidence", "summary", "findings"):
        assert field in msg
    assert "payload was empty" in msg
