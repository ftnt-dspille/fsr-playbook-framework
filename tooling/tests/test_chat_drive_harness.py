"""chat_drive resumes the halt it stopped on, through the shared harness frames."""
from __future__ import annotations

import sys
import types


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

    env = types.SimpleNamespace(get_config=lambda: _Cfg(), get_client=lambda: object())
    monkeypatch.setitem(sys.modules, "probes._env", env)
    monkeypatch.setattr(sys.modules["probes"] if "probes" in sys.modules else
                        __import__("probes"), "_env", env, raising=False)
    monkeypatch.setattr(chat_drive, "_execute", fake_execute)
    chat_drive.drive_scenario("block it", "triage", log=lambda *_: None)
    (_, turn, version), (op, resume, _) = sent
    assert version is None
    assert op == "chat_resume" and resume["approval_id"] == "a9"
