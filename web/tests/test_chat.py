"""Chat SSE route — uses a fake provider so no API key required."""
from __future__ import annotations

import json
import os
from typing import Any, AsyncIterator

import pytest
from fastapi.testclient import TestClient

from backend import app as app_module
from backend.llm import anthropic_provider
from backend.llm.provider import (
    DoneEvent,
    Event,
    Message,
    TextEvent,
    ToolResultEvent,
    ToolUseEvent,
)


class FakeProvider:
    name = "fake"

    async def stream(
        self, *, system: str, messages: list[Message], tools: list[dict[str, Any]]
    ) -> AsyncIterator[Event]:
        yield TextEvent(text="ok ")
        yield ToolUseEvent(
            name="find_connector", arguments={"q": "jira"}, call_id="c1"
        )
        yield ToolResultEvent(call_id="c1", result=[{"name": "jira"}])
        yield TextEvent(text="done.")
        yield DoneEvent(stop_reason="end_turn")


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy")
    monkeypatch.setattr(anthropic_provider, "AnthropicProvider", FakeProvider)
    # Re-import the route to pick up the patched provider class
    from importlib import reload

    from backend.routes import chat as chat_route

    reload(chat_route)
    app_module.app.router.routes = [
        r for r in app_module.app.router.routes if getattr(r, "path", "") != "/api/chat"
    ]
    app_module.app.include_router(chat_route.router)
    return TestClient(app_module.app)


def _parse_sse(text: str) -> list[tuple[str, dict]]:
    normalized = text.replace("\r\n", "\n")
    events: list[tuple[str, dict]] = []
    for chunk in normalized.split("\n\n"):
        if not chunk.strip():
            continue
        ev_name = "message"
        data = ""
        for line in chunk.splitlines():
            if line.startswith("event:"):
                ev_name = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data = line.split(":", 1)[1].lstrip()
        if data:
            events.append((ev_name, json.loads(data)))
    return events


def test_chat_streams_normalized_events(client):
    r = client.post(
        "/api/chat",
        json={"messages": [{"role": "user", "content": "hi"}], "current_yaml": ""},
    )
    assert r.status_code == 200
    events = _parse_sse(r.text)
    kinds = [name for name, _ in events]
    assert "text" in kinds
    assert "tool_use" in kinds
    assert "tool_result" in kinds
    assert kinds[-1] == "done"


def test_chat_no_api_key_returns_error_event(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    c = TestClient(app_module.app)
    r = c.post("/api/chat", json={"messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 200
    events = _parse_sse(r.text)
    kinds = [n for n, _ in events]
    assert "error" in kinds
    assert kinds[-1] == "done"
