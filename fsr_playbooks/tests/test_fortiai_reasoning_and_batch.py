"""FortiAI-proxy: reasoning selection, batched tool calls, and honest errors.

Three defects fixed together, because each hides the next:

  1. `_call_proxy` tested `isinstance(payload["error"], str)`, but the live
     error envelope is a DICT. The check never fired, so a failed call became
     an empty-content turn with no exception and the agent narrated it as an
     answer.
  2. the provider never sent `params.config`, so every turn ran whatever the
     connector configuration defaulted to -- on a stock box the "Low
     Reasoning" (AI_MODEL_MEDIUM) profile. The high-reasoning profile was
     unreachable from the agent loop.
  3. the response's `tools` array carries EVERY elected tool call;
     `tool_name`/`tool_args` are only the first. Reading the singular pair
     silently discarded the rest of the batch.

Defect 2 is also a live generator of defect 1: `reasoning_effort` against a
non-LARGE profile is a hard 400 from FortiAI, which is exactly the dict-shaped
envelope that used to pass through unnoticed.

Wire shapes live-verified on 8.0.0.
"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

from fsr_playbooks.llm.fortiai_proxy_provider import (
    FEATURE_LARGE,
    FEATURE_MEDIUM,
    FortiAIProxyProvider,
    _normalize_tool_calls,
    _resolve_llm_config,
)
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


def _provider(responses, **kw):
    """A provider whose transport records every body it was handed."""
    client = MagicMock()
    sent: list[dict] = []

    async def _post(_url, json=None, headers=None):  # noqa: A002
        sent.append(json)
        return responses.pop(0)


    client.post = _post
    p = FortiAIProxyProvider(base_url="http://x", api_key="k", model="m",
                             client=client, **kw)
    return p, sent


async def _drain(gen):
    return [ev async for ev in gen]


def _run(responses, dispatch_result=None, **kw):
    p, sent = _provider(responses, **kw)
    with patch("fsr_playbooks.llm.fortiai_proxy_provider.dispatch",
               return_value=dispatch_result or {"ok": True}) as disp:
        events = asyncio.run(_drain(p.stream(
            system="s", messages=[Message(role="user", content="go")],
            tools=_TOOLS, tags={})))
    return events, disp, sent


# -- 1. the config overlay resolver -----------------------------------------

def test_no_knobs_sends_no_overlay() -> None:
    """Default path is unchanged: no `config` key, connector config decides."""
    assert _resolve_llm_config(None, None) == {}
    assert _resolve_llm_config("", "") == {}


def test_feature_alone_passes_through() -> None:
    assert _resolve_llm_config(FEATURE_MEDIUM, None) == {"model": FEATURE_MEDIUM}


def test_effort_implies_large() -> None:
    """The one compatibility rule, in the one place it lives.

    `reasoning_effort` on a non-LARGE profile is a hard 400 from FortiAI, so
    asking for depth upgrades the profile rather than failing at the wire."""
    assert _resolve_llm_config(None, "high") == {
        "reasoning_effort": "high", "model": FEATURE_LARGE}
    # ... including when a smaller profile was explicitly named.
    assert _resolve_llm_config(FEATURE_MEDIUM, "high")["model"] == FEATURE_LARGE


def test_overlay_reaches_the_wire() -> None:
    _events, _disp, sent = _run([_payload(content="hi")],
                                feature=FEATURE_LARGE,
                                reasoning_effort="high")
    assert sent[0]["params"]["config"] == {
        "reasoning_effort": "high", "model": FEATURE_LARGE}


def test_no_config_key_when_unconfigured() -> None:
    """A bare provider must not start sending a key it never sent before."""
    _events, _disp, sent = _run([_payload(content="hi")])
    assert "config" not in sent[0]["params"]


# -- 2. errors are errors, whatever shape they arrive in --------------------

def test_dict_error_envelope_is_raised() -> None:
    """THE regression: the live envelope is a dict, and it used to sail past.

    The turn must not end as a normal empty answer."""
    events, _disp, _sent = _run([_payload(
        content="", usage=None,
        error={"status": "Failure", "status_code": "400",
               "error_code": "-30000",
               "error_desc": "The request payload is invalid."})])
    errors = [e for e in events if type(e).__name__ == "ErrorEvent"]
    assert errors, "a dict-shaped proxy error must surface as an ErrorEvent"
    assert "The request payload is invalid." in errors[0].message
    assert "-30000" in errors[0].message


def test_string_error_still_raised() -> None:
    """The shape the old check DID handle must keep working."""
    events, _disp, _sent = _run([_payload(content="", error="boom")])
    errors = [e for e in events if type(e).__name__ == "ErrorEvent"]
    assert errors and "boom" in errors[0].message


# -- 3. batched tool calls ---------------------------------------------------

def test_normalize_prefers_the_full_batch() -> None:
    calls = _normalize_tool_calls("a", {"x": 1}, [
        {"name": "a", "args": {"x": 1}}, {"name": "b", "args": {"y": 2}}])
    assert calls == [("a", {"x": 1}), ("b", {"y": 2})]


def test_normalize_falls_back_to_the_singular_pair() -> None:
    """An older proxy build with no `tools` field behaves exactly as before."""
    assert _normalize_tool_calls("a", {"x": 1}, None) == [("a", {"x": 1})]
    assert _normalize_tool_calls(None, None, None) == []


def test_every_call_in_the_batch_is_dispatched() -> None:
    """The silent-drop regression: two elected calls, two dispatches."""
    events, disp, _sent = _run([
        _payload(tool_name="run_op", tool_args={"op": "first"},
                 tools=[{"name": "run_op", "args": {"op": "first"}},
                        {"name": "run_op", "args": {"op": "second"}}]),
        _payload(content="done"),
    ])
    dispatched = [c.args[1].get("op") for c in disp.call_args_list]
    assert dispatched == ["first", "second"]
    uses = [e for e in events if isinstance(e, ToolUseEvent)]
    results = [e for e in events if isinstance(e, ToolResultEvent)]
    assert len(uses) == 2 and len(results) == 2


def test_batched_calls_get_distinct_call_ids() -> None:
    """The widget matches results to calls by id; a collision loses one."""
    events, _disp, _sent = _run([
        _payload(tool_name="run_op", tool_args={"op": "first"},
                 tools=[{"name": "run_op", "args": {"op": "first"}},
                        {"name": "run_op", "args": {"op": "second"}}]),
        _payload(content="done"),
    ])
    ids = [e.call_id for e in events if isinstance(e, ToolUseEvent)]
    assert len(ids) == len(set(ids)) == 2


def test_one_unreadable_call_does_not_void_its_siblings() -> None:
    """A bad-args call reports itself and the batch continues."""
    events, disp, _sent = _run([
        _payload(tool_name="run_op", tool_args="not-json",
                 tools=[{"name": "run_op", "args": "not-json"},
                        {"name": "run_op", "args": {"op": "second"}}]),
        _payload(content="done"),
    ])
    dispatched = [c.args[1].get("op") for c in disp.call_args_list]
    assert dispatched == ["second"]
    bad = [e for e in events if isinstance(e, ToolResultEvent)
           and isinstance(e.result, dict)
           and e.result.get("code") == "bad_tool_arguments"]
    assert len(bad) == 1


# -- 4. the forced assessment reaches the analyst ---------------------------


def test_forced_assessment_text_is_delivered() -> None:
    """Tools ran, then an empty reply: the wrap-up round's text must be yielded.

    The wrap-up unpacked `_call_proxy`'s 3-tuple into four names. The
    ValueError was swallowed by the round's `except Exception`, so the analyst
    got silence exactly when the round exists to prevent it.
    """
    from fsr_playbooks.llm.provider import TextEvent
    events, _disp, _sent = _run([
        _payload(tool_name="run_op", tool_args={"op": "lookup"}),
        _payload(content=""),
        _payload(content="Benign; close it."),
    ])
    texts = [e.text for e in events if isinstance(e, TextEvent)]
    assert "Benign; close it." in texts, texts
