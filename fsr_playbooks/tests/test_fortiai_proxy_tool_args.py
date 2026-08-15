"""FortiAI-proxy provider: how a tool call's arguments survive the wire.

This provider had no test coverage at all, and it was quietly dropping
arguments in two places at once:

  1. `_call_proxy` coerced any non-dict `tool_args` to `{}`. The proxy hands
     tool arguments back as a JSON *string*, so the coercion emptied real
     calls before the caller's parser (which handles strings) ever saw them.
  2. the caller then dispatched that `{}` as if the model had asked for it.

Seen live as three consecutive `run_op({})` dispatches on
`contain_block_ip_direct` (calibrate run 20260815T153152Z) -- a third of the
fixture's tool budget spent on calls the model never made, and a turn that
ended with no approval card staged.
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock, patch

import pytest

from fsr_playbooks.llm.fortiai_proxy_provider import FortiAIProxyProvider
from fsr_playbooks.llm.provider import Message, ToolResultEvent, ToolUseEvent

_TOOLS = [{
    "type": "function",
    "function": {"name": "run_op", "description": "Run a connector operation",
                 "parameters": {"type": "object", "properties": {}}},
}]


def _payload(**data):
    resp = MagicMock(status_code=200)
    resp.json = MagicMock(return_value={"status": "Success", "data": data})
    return resp


def _provider(responses):
    client = MagicMock()

    async def _post(*_a, **_kw):
        return responses.pop(0)

    client.post = _post
    return FortiAIProxyProvider(base_url="http://x", api_key="k",
                                model="m", client=client)


async def _drain(gen):
    return [ev async for ev in gen]


def _run(responses, dispatch_result=None):
    p = _provider(responses)
    with patch("fsr_playbooks.llm.fortiai_proxy_provider.dispatch",
               return_value=dispatch_result or {"ok": True}) as disp:
        events = asyncio.run(_drain(p.stream(
            system="s", messages=[Message(role="user", content="block it")],
            tools=_TOOLS, tags={})))
    return events, disp


def test_json_string_tool_args_reach_the_tool() -> None:
    """The regression itself: a stringly-typed payload is a REAL call."""
    args = {"connector": "fortigate-firewall", "op": "get_blocked_ip"}
    events, disp = _run([
        _payload(tool_name="run_op", tool_args=json.dumps(args)),
        _payload(content="done"),
    ])
    assert disp.called, "a well-formed call was dropped on the floor"
    assert disp.call_args[0][1] == args
    use = next(e for e in events if isinstance(e, ToolUseEvent))
    assert use.arguments == args


def test_dict_tool_args_still_work() -> None:
    args = {"connector": "fortigate-firewall", "op": "get_blocked_ip"}
    _events, disp = _run([
        _payload(tool_name="run_op", tool_args=dict(args)),
        _payload(content="done"),
    ])
    assert disp.call_args[0][1] == args


@pytest.mark.parametrize("bad", ['{"connector":', "not json", ["a", "b"], 7])
def test_unreadable_args_bounce_instead_of_running_empty(bad) -> None:
    events, disp = _run([
        _payload(tool_name="run_op", tool_args=bad),
        _payload(content="done"),
    ])
    assert not disp.called, f"dispatched with emptied args for {bad!r}"
    results = [e for e in events if isinstance(e, ToolResultEvent)]
    assert results, "the model got no feedback and cannot re-emit"
    assert results[0].result.get("code") == "bad_tool_arguments", results[0].result
