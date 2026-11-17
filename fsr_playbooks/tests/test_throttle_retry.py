"""A provider rate limit is waited out and retried (narrated), an exhausted
balance fails fast with a message naming the fix, and neither is dumped raw.

The classifier is structural (HTTP status + Retry-After + body code), so the
same loop policy covers Anthropic, OpenAI and the FortiAI proxy. These tests
drive the real OpenAIProvider loop with a fake stream whose first attempt raises
a 429-shaped exception.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from fsr_playbooks.llm import _throttle
from fsr_playbooks.llm.openai_provider import OpenAIProvider
from fsr_playbooks.llm.provider import (
    DoneEvent,
    ErrorEvent,
    Message,
    NoticeEvent,
)

# ── the classifier ──────────────────────────────────────────────────────────

class _Resp:
    def __init__(self, headers):
        self.headers = headers


class _Err(Exception):
    def __init__(self, *, status_code=None, code=None, body=None,
                 headers=None, message=""):
        super().__init__(message or code or "err")
        if status_code is not None:
            self.status_code = status_code
        if code is not None:
            self.code = code
        if body is not None:
            self.body = body
        if headers is not None:
            self.response = _Resp(headers)
        if message:
            self.message = message


def test_classify_insufficient_quota_is_out_of_credit():
    # OpenAI's exhausted balance is a 429 -- status alone would read as a
    # throttle, so the code must steer it to out_of_credit.
    e = _Err(status_code=429, code="insufficient_quota")
    assert _throttle.classify(e) == ("out_of_credit", None)


def test_classify_anthropic_credit_message_is_out_of_credit():
    e = _Err(status_code=400,
             message="Your credit balance is too low to access the Claude API")
    assert _throttle.classify(e)[0] == "out_of_credit"


def test_classify_rate_limit_is_throttled_with_retry_after():
    e = _Err(status_code=429, code="rate_limit_exceeded",
             headers={"retry-after": "7"})
    outcome, wait = _throttle.classify(e)
    assert outcome == "throttled"
    assert wait == 7.0


def test_classify_overloaded_529_is_throttled():
    assert _throttle.classify(_Err(status_code=529))[0] == "throttled"


def test_classify_other_is_other():
    assert _throttle.classify(_Err(status_code=400, code="invalid_request"))[0] == "other"


def test_wait_for_caps_and_backs_off():
    assert _throttle.wait_for(1, 999.0) == _throttle.PER_WAIT_CAP_SECS
    assert _throttle.wait_for(1, None) == _throttle._DEFAULT_BACKOFF[0]
    assert _throttle.wait_for(1, 3.0) == 3.0


# ── the loop ────────────────────────────────────────────────────────────────

def _delta_chunk(*, content=None, finish=None):
    delta = MagicMock(content=content, tool_calls=None)
    return MagicMock(choices=[MagicMock(delta=delta, finish_reason=finish)], usage=None)


def _usage_chunk():
    return MagicMock(choices=[], usage=MagicMock(prompt_tokens=10, completion_tokens=5))


class _FakeStream:
    def __init__(self, chunks):
        self._chunks = chunks

    def __aiter__(self):
        async def gen():
            for c in self._chunks:
                yield c
        return gen()


_OK = [_delta_chunk(content="Here is your answer."),
       _delta_chunk(finish="stop"), _usage_chunk()]


async def _drain(gen):
    out = []
    async for ev in gen:
        out.append(ev)
    return out


def _provider(create):
    client = MagicMock()
    client.chat = MagicMock()
    client.chat.completions = MagicMock(create=create)
    return OpenAIProvider(model="gpt-4.1-mini", base_url="http://x/v1",
                          api_key="x", client=client)


def _run(create):
    p = _provider(create)
    with patch("fsr_playbooks.llm.agent_loop.dispatch", MagicMock(return_value={"ok": True})), \
         patch("fsr_playbooks.llm.agent_loop._tier_for", return_value=0):
        return asyncio.run(_drain(p.stream(
            system="s", messages=[Message(role="user", content="hi")],
            tools=[], tags={})))


def test_throttle_retries_and_recovers_with_a_notice():
    # First attempt 429 (retry-after 0 so the test does not really sleep), then OK.
    rl = _Err(status_code=429, code="rate_limit_exceeded", headers={"retry-after": "0"})
    create = AsyncMock(side_effect=[rl, _FakeStream(_OK)])
    events = _run(create)
    notices = [e for e in events if isinstance(e, NoticeEvent)]
    errors = [e for e in events if isinstance(e, ErrorEvent)]
    assert len(notices) == 1, "the throttle should be narrated once"
    assert notices[0].reason == "throttled"
    assert not errors, "a recovered throttle must not surface an error"
    assert create.await_count == 2, "the request should have been retried once"
    assert isinstance(events[-1], DoneEvent)


def test_out_of_credit_fails_fast_with_a_clear_message():
    oc = _Err(status_code=429, code="insufficient_quota")
    create = AsyncMock(side_effect=[oc, _FakeStream(_OK)])
    events = _run(create)
    errors = [e for e in events if isinstance(e, ErrorEvent)]
    assert len(errors) == 1
    assert "credit" in errors[0].message.lower()
    assert "rate limit" not in errors[0].message.lower(), (
        "out-of-credit must not be mislabelled as a transient rate limit")
    # No retry: retrying a dead balance only delays the failure.
    assert create.await_count == 1


def test_throttle_gives_up_after_the_retry_budget():
    rl = _Err(status_code=429, code="rate_limit_exceeded", headers={"retry-after": "0"})
    # Always throttled: initial + MAX_THROTTLE_RETRIES attempts, then give up.
    create = AsyncMock(side_effect=[rl] * (_throttle.MAX_THROTTLE_RETRIES + 1))
    events = _run(create)
    errors = [e for e in events if isinstance(e, ErrorEvent)]
    assert len(errors) == 1
    assert "credit" not in errors[0].message.lower()
    assert create.await_count == _throttle.MAX_THROTTLE_RETRIES + 1
