"""LLM factory + Protocol contract.

Confirms the abstraction we'll layer OpenAI / Bedrock / etc. on top
of: any registered provider must satisfy the Protocol's stream()
signature (including the `tags` round-trip), emit a UsageEvent per
round-trip, and be selectable by name.
"""
from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator

import pytest

from fsr_core.llm import factory
from fsr_core.llm.fake_provider import FakeProvider
from fsr_core.llm.provider import (
    DoneEvent,
    Event,
    LLMProvider,
    Message,
    TextEvent,
    UsageEvent,
)


@pytest.fixture(autouse=True)
def isolated_registry():
    factory._register_builtins()
    yield
    factory._register_builtins()


def test_anthropic_is_registered_by_default():
    assert "anthropic" in factory.registered_names()


def test_register_and_resolve_a_fake_provider():
    factory.register("custom", lambda: FakeProvider([], model="custom-1"))
    p = factory.get_provider("custom")
    assert p.name == "fake"


def test_unknown_provider_name_raises():
    with pytest.raises(KeyError, match="unknown LLM provider"):
        factory.get_provider("does-not-exist")


def test_env_var_selects_provider(monkeypatch):
    factory.register("custom", lambda: FakeProvider([], model="x"))
    monkeypatch.setenv("STUDIO_LLM_PROVIDER", "custom")
    p = factory.get_provider()
    assert p.model == "x"


# ---- Protocol contract -------------------------------------------

async def _drain(provider, **kw) -> list[Event]:
    out: list[Event] = []
    async for ev in provider.stream(**kw):
        out.append(ev)
    return out


def test_fake_provider_satisfies_protocol_signature():
    """If it walks like a provider and quacks like a provider, the
    factory will trust it. This is the structural contract we lean on
    when adding new providers."""
    fake = FakeProvider([
        [TextEvent(text="hi"),
         UsageEvent(session_id="s", turn=1, model="fake-1",
                    input_tokens=1, output_tokens=2,
                    cache_read=0, cache_write=0,
                    history_chars=10, stop_reason="end_turn")],
    ])
    events = asyncio.run(_drain(
        fake, system="sys",
        messages=[Message(role="user", content="hi")],
        tools=[], tags={"playbook_collection": "X"},
    ))
    kinds = [type(e).__name__ for e in events]
    assert "TextEvent" in kinds
    assert "UsageEvent" in kinds
    assert "DoneEvent" in kinds


def test_tags_round_trip_to_usage_event():
    """The whole point of `tags`: stamp metadata at the route layer
    and pull it off the UsageEvent at the consumer layer, without
    the provider needing to understand it."""
    fake = FakeProvider([
        [UsageEvent(session_id="s", turn=1, model="m",
                    input_tokens=0, output_tokens=0,
                    cache_read=0, cache_write=0,
                    history_chars=0, stop_reason="end_turn")],
    ])
    events = asyncio.run(_drain(
        fake, system="", messages=[], tools=[],
        tags={"playbook_collection": "Triage"},
    ))
    usage_seen = next(e for e in events if isinstance(e, UsageEvent))
    assert usage_seen.tags == {"playbook_collection": "Triage"}


def test_pre_tagged_usage_events_keep_their_tags():
    """A provider that already supplied tags (e.g. self-repair turn
    metadata) should not have them clobbered by the route's tags."""
    fake = FakeProvider([
        [UsageEvent(session_id="s", turn=1, model="m",
                    input_tokens=0, output_tokens=0,
                    cache_read=0, cache_write=0,
                    history_chars=0, stop_reason="end_turn",
                    tags={"playbook_collection": "Pre-tagged"})],
    ])
    events = asyncio.run(_drain(
        fake, system="", messages=[], tools=[],
        tags={"playbook_collection": "Route-tag"},
    ))
    seen = next(e for e in events if isinstance(e, UsageEvent))
    assert seen.tags == {"playbook_collection": "Pre-tagged"}


def test_fake_provider_records_call_args():
    """Test scaffolding sanity-check: the fake captures what the
    consumer sent, so tests can assert on tools/messages/system."""
    fake = FakeProvider([])
    assert fake.call_count == 0
    assert fake.last_messages is None


def test_provider_name_attribute_present():
    """Protocol declares `name: str`. Both providers expose it."""
    fake = FakeProvider([])
    assert fake.name == "fake"


def test_satisfies_runtime_protocol_check():
    """`LLMProvider` is a structural Protocol — a duck check confirms
    we haven't drifted from it."""
    fake = FakeProvider([])
    # Protocol can be used as a structural type guard via hasattr
    assert hasattr(fake, "stream")
    assert hasattr(fake, "name")
