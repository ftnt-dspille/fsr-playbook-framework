"""tooling/harness: the LLM choice, transcript reading and turn classification
every chat-turn harness shares."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.classify import classify_turn  # noqa: E402
from harness.frames import assistant_summary, assistant_text, pending_halt  # noqa: E402
from harness.llm import DEFAULT_FRANK_MODEL, LLMConfigError, resolve_llm  # noqa: E402

FRANK_ENV = {"FRANK_BASE_URL": "https://gw.example.com/v1", "FRANK_API_KEY": "k-frank",
             "OPENAI_API_KEY": "k-openai"}


def test_model_source_is_named():
    r = resolve_llm("frank", env=FRANK_ENV)
    assert (r.model, r.model_source, r.api_key) == (DEFAULT_FRANK_MODEL, "default", "k-frank")
    r = resolve_llm("frank", env={**FRANK_ENV, "FRANK_MODEL": "coding-b200/eco"})
    assert (r.model, r.model_source) == ("coding-b200/eco", "env:FRANK_MODEL")
    assert resolve_llm("frank", "m", env=FRANK_ENV).model_source == "arg"


def test_openai_takes_the_openai_key_first():
    assert resolve_llm("openai", env=FRANK_ENV).api_key == "k-openai"


def test_missing_endpoint_raises_instead_of_falling_back():
    with pytest.raises(LLMConfigError):
        resolve_llm("frank", env={"FRANK_API_KEY": "k"})
    with pytest.raises(LLMConfigError):
        resolve_llm("gpt", env=FRANK_ENV)


def test_connector_config_matches_local_turn():
    cfg = resolve_llm("frank", env=FRANK_ENV).connector_config()
    assert cfg == {"llm_provider": "openai", "openai_api_key": "k-frank",
                   "openai_base_url": "https://gw.example.com/v1",
                   "openai_model": DEFAULT_FRANK_MODEL, "persona_models": False}


@pytest.mark.parametrize("envelope,kind", [
    ({"ok": True, "stop_reason": "end_turn",
      "transcript": [{"type": "text", "text": "done"}]}, "answered"),
    # A provider failure the connector returns as a normal reply.
    ({"ok": True, "stop_reason": "error", "transcript": [
        {"type": "error", "message": "Could not reach the OpenAI endpoint at "
                                     "https://gw.example.com -- check network"}]},
     "transport_error"),
    ({"ok": True, "stop_reason": "error", "transcript": [
        {"type": "error", "message": "Error code: 400 - invalid tool arguments"}]},
     "provider_error"),
    ({"ok": True, "stop_reason": "max_tokens", "transcript": []}, "truncated"),
    ({"ok": True, "stop_reason": "pending_approval", "transcript": [
        {"type": "approval_request", "approval_id": "a1"}]}, "halted"),
    ("<html>502</html>", "transport_error"),
])
def test_classify_turn(envelope, kind):
    assert classify_turn(envelope).kind == kind


def test_an_approval_outranks_a_card():
    t = {"transcript": [{"type": "action_card", "id": "c1"},
                        {"type": "approval_request", "approval_id": "a1"}]}
    assert pending_halt(t) == {"key": "approval_id", "value": "a1", "kind": "approval"}
    assert pending_halt({"transcript": [{"type": "action_card", "id": "c1"}]})["key"] == "card_id"


def test_text_deltas_coalesce_and_history_keeps_tool_ids():
    t = [{"type": "text", "text": "Hel"}, {"type": "text", "text": "lo"},
         {"type": "tool_use", "id": "t1", "name": "get_record", "input": {}},
         {"type": "tool_result", "tool_use_id": "t1", "content": {"ok": True}}]
    assert assistant_text(t) == "Hello"
    assert [b["type"] for b in assistant_summary(t)] == ["text", "tool_use", "tool_result"]


def test_chat_drive_resumes_the_halt_it_stopped_on(monkeypatch):
    from evals import chat_drive

    sent = []

    def fake_execute(client, op, params, version, config, timeout=290):
        sent.append((op, dict(params), version))
        if op == "chat_turn":
            return {"ok": True, "stop_reason": "approval_required",
                    "transcript": [{"type": "approval_request", "approval_id": "a9"}]}
        return {"ok": True, "stop_reason": "end_turn", "transcript": []}

    class _Cfg:
        def is_live(self):
            return True

    import types
    env = types.SimpleNamespace(get_config=lambda: _Cfg(), get_client=lambda: object())
    monkeypatch.setitem(sys.modules, "probes._env", env)
    monkeypatch.setattr(sys.modules["probes"] if "probes" in sys.modules else
                        __import__("probes"), "_env", env, raising=False)
    monkeypatch.setattr(chat_drive, "_execute", fake_execute)
    chat_drive.drive_scenario("block it", "triage", log=lambda *_: None)
    (_, turn, version), (op, resume, _) = sent
    assert version is None
    assert op == "chat_resume" and resume["approval_id"] == "a9"
