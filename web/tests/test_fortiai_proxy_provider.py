"""FortiAI Proxy provider — non-streaming transport, tool-call round-trip,
approval gate, error mapping. The httpx client is mocked so tests don't
need a FortiSOAR appliance.

These tests target the wire-format translation layer and the flattened-text
round-trip, not the agent loop semantics (those are covered by FakeProvider).
"""
from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from fsr_playbooks.llm.fortiai_proxy_provider import (
    FortiAIProxyProvider,
    _normalize_tools_fortiai,
    _stringify,
)
from fsr_playbooks.llm.provider import (
    ApprovalRequestEvent,
    DoneEvent,
    ErrorEvent,
    Message,
    TextEvent,
    ToolResultEvent,
    ToolUseEvent,
    UsageEvent,
)


# ---- Helpers ----------------------------------------------------

def _mock_response(*, content=None, tool_name=None, tool_args=None,
                   usage=None, error=None, status="Success"):
    """Build a mock httpx.Response for a successful proxy call."""
    resp = MagicMock()
    resp.status_code = 200
    data_body = {
        "content": content,
        "tool_name": tool_name,
        "tool_args": tool_args,
        "usage": usage or {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        "model": "fortiai-proxy",
        "provider": "FSRAI",
        "error": error,
    }
    resp.json.return_value = {
        "status": status,
        "data": data_body,
    }
    return resp


def _error_response(*, status_code=400, message="Invalid params provided"):
    """Build a mock httpx.Response for a failed proxy call."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = message
    resp.json.side_effect = TypeError("not json")
    return resp


class _MockAsyncClient:
    """Fake httpx.AsyncClient that returns canned responses in order."""

    def __init__(self, *responses):
        self._responses = list(responses)
        self._index = 0
        self._calls: list[dict] = []

    async def post(self, url, *, json=None, headers=None):
        body = json or {}
        self._calls.append({
            "url": url,
            "json": body,
            "headers": headers,
        })
        resp = self._responses[self._index]
        self._index += 1
        return resp

    async def aclose(self):
        pass


def _provider_with_responses(*responses, **kwargs) -> FortiAIProxyProvider:
    client = _MockAsyncClient(*responses)
    return FortiAIProxyProvider(client=client, **kwargs)


async def _drain(provider, **kw):
    out = []
    try:
        async for ev in provider.stream(**kw):
            out.append(ev)
    finally:
        await provider.aclose()
    return out


# ---- Tool normalization -------------------------------------------

def test_normalize_tools_fortiai_from_anthropic_shape():
    tools = [
        {"name": "find_connector", "description": "Find a connector",
         "input_schema": {"type": "object", "properties": {"q": {"type": "string"}}}},
    ]
    out = _normalize_tools_fortiai(tools)
    assert len(out) == 1
    assert out[0]["name"] == "find_connector"
    assert out[0]["schema"]["type"] == "object"
    assert "input_schema" not in out[0]


def test_normalize_tools_fortiai_from_openai_shape():
    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_step_type",
                "description": "Get step type schema",
                "parameters": {"type": "object", "properties": {"name": {"type": "string"}}},
            },
        },
    ]
    out = _normalize_tools_fortiai(tools)
    assert len(out) == 1
    assert out[0]["name"] == "get_step_type"
    assert out[0]["schema"]["type"] == "object"


def test_normalize_tools_fortiai_passthrough():
    tools = [{"name": "x", "description": "X", "schema": {"type": "object"}}]
    out = _normalize_tools_fortiai(tools)
    assert out[0]["schema"] == {"type": "object"}


def test_normalize_tools_drops_no_name():
    out = _normalize_tools_fortiai([{"description": "no name"}])
    assert not out


def test_stringify_plain_string():
    assert _stringify("hello") == "hello"


def test_stringify_dict():
    result = {"key": "value", "num": 42}
    out = _stringify(result)
    assert json.loads(out) == result


def test_stringify_unserializable_returns_json_quoted_str():
    """default=str in json.dumps handles unserializable objects by quoting.
    The _stringify function uses default=str, so Weird() -> '\"Weird()\"'."""
    class Weird:
        def __str__(self):
            return "Weird()"
    out = _stringify(Weird())
    assert json.loads(out) == "Weird()"


# ---- Pure-text turn -----------------------------------------------

def test_pure_text_turn():
    resp = _mock_response(content="The answer is 42", tool_name=None)
    p = _provider_with_responses(resp)
    events = asyncio.run(_drain(p, system="You are helpful.",
                                messages=[Message(role="user", content="What is the answer?")],
                                tools=[], tags={}))
    text_events = [e for e in events if isinstance(e, TextEvent)]
    assert "".join(e.text for e in text_events) == "The answer is 42"
    assert any(isinstance(e, DoneEvent) and e.stop_reason == "end_turn" for e in events)
    usage = next(e for e in events if isinstance(e, UsageEvent))
    assert usage.input_tokens == 10
    assert usage.output_tokens == 5


def test_call_includes_system_prompt():
    """The proxy call's messages list must start with the system prompt."""
    resp = _mock_response(content="ok", tool_name=None)
    p = _provider_with_responses(resp)
    asyncio.run(_drain(p, system="You are a SOC analyst.",
                       messages=[Message(role="user", content="hi")],
                       tools=[], tags={}))
    call = p._client._calls[0]
    msgs = call["json"]["params"]["messages"]
    assert msgs[0] == {"role": "system", "content": "You are a SOC analyst."}
    assert msgs[1] == {"role": "user", "content": "hi"}


def test_call_includes_tools():
    """Tool schemas are translated to fortiai shape in the proxy call."""
    resp = _mock_response(content="ok", tool_name=None)
    p = _provider_with_responses(resp)
    tools = [{"name": "test_tool", "description": "A test tool",
              "input_schema": {"type": "object"}}]
    asyncio.run(_drain(p, system="", messages=[], tools=tools, tags={}))
    call = p._client._calls[0]
    sent_tools = call["json"]["params"]["tools"]
    assert len(sent_tools) == 1
    assert sent_tools[0]["name"] == "test_tool"
    assert "schema" in sent_tools[0]
    assert "input_schema" not in sent_tools[0]


# ---- Single tool call round-trip ----------------------------------

def test_single_tool_call_and_continue():
    """Call 1 returns a tool call; provider flattens and calls again.
    Call 2 returns text content."""
    call1 = _mock_response(content=None, tool_name="find_connector",
                           tool_args={"q": "virustotal"})
    call2 = _mock_response(content="Found 2 connectors matching 'virustotal'.",
                           tool_name=None)
    p = _provider_with_responses(call1, call2)
    with patch("fsr_playbooks.llm.fortiai_proxy_provider.dispatch",
               return_value={"matches": [{"name": "virustotal"}]}):
        events = asyncio.run(_drain(p, system="", messages=[], tools=[], tags={}))

    # First round: ToolUseEvent + ToolResultEvent
    tool_uses = [e for e in events if isinstance(e, ToolUseEvent)]
    assert len(tool_uses) == 1
    assert tool_uses[0].name == "find_connector"
    assert tool_uses[0].arguments == {"q": "virustotal"}

    tool_results = [e for e in events if isinstance(e, ToolResultEvent)]
    assert len(tool_results) == 1
    assert tool_results[0].result == {"matches": [{"name": "virustotal"}]}

    # Second round: text
    text_events = [e for e in events if isinstance(e, TextEvent)]
    assert text_events[0].text == "Found 2 connectors matching 'virustotal'."

    # Two proxy calls made
    assert p._client._index == 2

    # Second call includes the flattened text messages
    call2_body = p._client._calls[1]["json"]["params"]["messages"]
    assert any("called find_connector" in (m.get("content") or "")
               for m in call2_body)
    assert any("Tool result:" in (m.get("content") or "")
               for m in call2_body)


def test_malformed_tool_args_become_empty_dict():
    """String tool_args that aren't valid JSON should become {}."""
    call1 = _mock_response(content=None, tool_name="find_connector",
                           tool_args="not-valid-json{{")
    call2 = _mock_response(content="ok", tool_name=None)
    p = _provider_with_responses(call1, call2)
    with patch("fsr_playbooks.llm.fortiai_proxy_provider.dispatch",
               return_value={}) as mock_dispatch:
        events = asyncio.run(_drain(p, system="", messages=[], tools=[], tags={}))
    # Dispatch received empty dict for malformed args
    mock_dispatch.assert_called_with("find_connector", {})


def test_tool_args_dict_pass_through():
    """When tool_args is already a dict, it should pass through."""
    call1 = _mock_response(content=None, tool_name="get_step_type",
                           tool_args={"name": "start"})
    call2 = _mock_response(content="ok", tool_name=None)
    p = _provider_with_responses(call1, call2)
    with patch("fsr_playbooks.llm.fortiai_proxy_provider.dispatch",
               return_value={}) as mock_dispatch:
        asyncio.run(_drain(p, system="", messages=[], tools=[], tags={}))
    mock_dispatch.assert_called_with("get_step_type", {"name": "start"})


def test_tool_call_turn_emits_real_token_counts():
    """The tool-call turn's UsageEvent must carry the proxy's reported
    token counts, not zeros. Regression guard for a bug where _emit_usage
    hardcoded input_tokens=0/output_tokens=0, so every tool-call round
    reported 0 tokens even though the proxy returned real usage."""
    call1 = _mock_response(
        content=None, tool_name="find_connector", tool_args={"q": "x"},
        usage={"prompt_tokens": 111, "completion_tokens": 22, "total_tokens": 133},
    )
    call2 = _mock_response(
        content="done", tool_name=None,
        usage={"prompt_tokens": 222, "completion_tokens": 33, "total_tokens": 255},
    )
    p = _provider_with_responses(call1, call2)
    with patch("fsr_playbooks.llm.fortiai_proxy_provider.dispatch",
               return_value={"matches": []}):
        events = asyncio.run(_drain(p, system="", messages=[], tools=[], tags={}))
    usages = [e for e in events if isinstance(e, UsageEvent)]
    assert len(usages) == 2
    # Tool-call turn usage (first round-trip)
    assert usages[0].input_tokens == 111
    assert usages[0].output_tokens == 22
    assert usages[0].stop_reason == "tool_calls"
    # Terminal text turn usage (second round-trip)
    assert usages[1].input_tokens == 222
    assert usages[1].output_tokens == 33
    assert usages[1].stop_reason == "end_turn"


def test_tool_call_usage_records_tool_name_and_chars():
    """The terminal UsageEvent should carry ToolCallUsage entries for
    each dispatched tool, with the tool name and arg/result char counts."""
    call1 = _mock_response(content=None, tool_name="get_step_type",
                          tool_args={"name": "start"})
    call2 = _mock_response(content="ok", tool_name=None)
    p = _provider_with_responses(call1, call2)
    with patch("fsr_playbooks.llm.fortiai_proxy_provider.dispatch",
               return_value={"name": "start", "label": "Trigger"}):
        events = asyncio.run(_drain(p, system="", messages=[], tools=[], tags={}))
    usages = [e for e in events if isinstance(e, UsageEvent)]
    # The tool-call turn's usage should record the dispatched tool
    tool_turn_usage = usages[0]
    assert tool_turn_usage.tool_calls, "tool_call_usage empty on tool turn"
    assert any(tc.name == "get_step_type" for tc in tool_turn_usage.tool_calls)


# ---- Approval gate ------------------------------------------------

def test_tier3_tool_yields_approval_request():
    """A tier-3+ tool return a pending_approval envelope → ApprovalRequestEvent."""
    call1 = _mock_response(content=None, tool_name="run_op",
                           tool_args={"connector": "test", "op": "block_ip",
                                      "params": {"ip": "1.2.3.4"}})
    p = _provider_with_responses(call1)
    with patch("fsr_playbooks.llm.fortiai_proxy_provider.dispatch", return_value={
        "pending_approval": True,
        "approval_id": "test-approval-1",
        "tier": 4,
        "preview": {"tool": "run_op", "args": {"connector": "test", "op": "block_ip"}},
        "args_hash": "abc123",
        "summary": "Block IP 1.2.3.4",
    }):
        events = asyncio.run(_drain(p, system="", messages=[], tools=[], tags={}))

    approval_events = [e for e in events if isinstance(e, ApprovalRequestEvent)]
    assert len(approval_events) == 1
    assert approval_events[0].approval_id == "test-approval-1"
    assert approval_events[0].tool == "run_op"
    assert approval_events[0].tier == 4

    done = [e for e in events if isinstance(e, DoneEvent)]
    assert any(d.stop_reason == "pending_approval" for d in done)


# ---- Error handling -----------------------------------------------

def test_http_400_surfaces_error_event():
    """A non-200 response from the proxy yields an ErrorEvent."""
    resp = _error_response(status_code=400, message="Invalid params provided")
    p = _provider_with_responses(resp)
    events = asyncio.run(_drain(p, system="", messages=[], tools=[], tags={}))
    err = next(e for e in events if isinstance(e, ErrorEvent))
    assert "400" in err.message
    assert "Invalid params" in err.message


def test_data_error_surfaces_error_event():
    """A 200 response with data.error string yields an ErrorEvent."""
    resp = _mock_response(content=None, tool_name=None, error="Model timeout")
    p = _provider_with_responses(resp)
    events = asyncio.run(_drain(p, system="", messages=[], tools=[], tags={}))
    err = next(e for e in events if isinstance(e, ErrorEvent))
    assert "Model timeout" in err.message


def test_failed_status_surfaces_error_event():
    """A 200 response with status != 'Success' yields an ErrorEvent."""
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "status": "failed",
        "data": {},
    }
    resp.text = "Something went wrong"
    p = _provider_with_responses(resp)
    events = asyncio.run(_drain(p, system="", messages=[], tools=[], tags={}))
    err = next(e for e in events if isinstance(e, ErrorEvent))
    assert "failed" in err.message.lower()


# ---- Model parameter ----------------------------------------------

def test_model_param_is_passed_when_set():
    """When provider.model is set, it's included in the proxy call."""
    resp = _mock_response(content="ok", tool_name=None)
    p = _provider_with_responses(resp, model="gpt-4.1")
    asyncio.run(_drain(p, system="", messages=[], tools=[], tags={}))
    call = p._client._calls[0]
    assert call["json"]["params"]["model"] == "gpt-4.1"


def test_default_model_fortiai_proxy():
    """Provider defaults to 'fortiai-proxy' model when none is set."""
    p = FortiAIProxyProvider()
    assert p.model == "fortiai-proxy"


# ---- Max tool turns -----------------------------------------------

def test_max_tool_turns_exhaustion():
    """After MAX_TOOL_TURNS, the loop emits DoneEvent('max_tool_turns')."""
    # Create a provider that keeps returning tool calls forever
    p = _provider_with_responses(
        *[_mock_response(content=None, tool_name="find_connector",
                         tool_args={"q": "test"}) for _ in range(100)]
    )
    with patch("fsr_playbooks.llm.fortiai_proxy_provider.dispatch",
               return_value={"matches": []}):
        events = asyncio.run(_drain(p, system="", messages=[], tools=[], tags={}))

    done = [e for e in events if isinstance(e, DoneEvent)]
    assert any(d.stop_reason == "max_tool_turns" for d in done)


# ---- Auth header ---------------------------------------------------

def test_auth_header_included_when_api_key_set():
    """When api_key is set, Authorization: Bearer header is sent."""
    resp = _mock_response(content="ok", tool_name=None)
    p = FortiAIProxyProvider(base_url="https://fsr.example.com",
                             api_key="test-token")
    p._client = _MockAsyncClient(resp)
    asyncio.run(_drain(p, system="", messages=[], tools=[], tags={}))
    call = p._client._calls[0]
    assert call["headers"]["Authorization"] == "Bearer test-token"


def test_no_auth_header_without_api_key():
    """When api_key is None, no Authorization header is sent."""
    resp = _mock_response(content="ok", tool_name=None)
    p = FortiAIProxyProvider()
    p._client = _MockAsyncClient(resp)
    asyncio.run(_drain(p, system="", messages=[], tools=[], tags={}))
    call = p._client._calls[0]
    assert "Authorization" not in (call["headers"] or {})


# ---- Name constant -------------------------------------------------

def test_provider_name():
    assert FortiAIProxyProvider.name == "fortiai-proxy"
