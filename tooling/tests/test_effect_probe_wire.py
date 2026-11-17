"""The effect probes' wire, box-free (EF rows of the driver inventory).

The probes are live by design. Their payloads are the part that can rot
silently (a widget field renamed, a version sent when it must not be), so these
tests pin what each helper puts on the wire, with a fake client that records
every post. Nothing here reaches a box.
"""
from __future__ import annotations

import json

import pytest
from evals import chat_drive as cd
from probes.effect import drive, runner, triage
from probes.effect.probes import Result


class _Client:
    def __init__(self, answers=None):
        self.answers = list(answers or [])
        self.posts: list[tuple[str, dict]] = []

    def post(self, path, body):
        self.posts.append((path, body))
        if self.answers:
            answer = self.answers.pop(0)
            if isinstance(answer, BaseException):
                raise answer
            return {"status": "success", "data": answer}
        return {"status": "success", "data": {"ok": True, "transcript": []}}

    def last_params(self):
        return self.posts[-1][1]["params"]


@pytest.fixture
def client(monkeypatch):
    fake = _Client()
    monkeypatch.setattr(drive, "get_client", lambda: fake)
    monkeypatch.setattr(triage, "get_client", lambda: fake)
    drive.reset_log()
    return fake


# ------------------------------------------------------------------- turn
def test_effect_turn_sends_live_sync_payload(client):
    drive.turn("add a step", session="s-1", entity={"iri": "/x"})
    path, body = client.posts[0]
    assert path == "/api/integration/execute/"
    assert body["operation"] == "chat_turn"
    assert body["params"] == {"session_id": "s-1",
                              "messages": [{"role": "user", "content": "add a step"}],
                              "intent": "build", "mode": "live", "detached": False,
                              "entity": {"iri": "/x"}}


def test_effect_turn_omits_empty_version_keeps_config(client):
    drive.turn("hi", session="s-2")
    body = client.posts[0][1]
    assert "version" not in body
    assert body["config"] == ""
    assert "record" not in body["params"] and "entity" not in body["params"]


def test_effect_turn_logs_every_call(client):
    client.answers = [{"ok": True, "transcript": [{"type": "text", "text": "x"}]}]
    res = drive.turn("hi", session="s-3", record={"uuid": "r"})
    (entry,) = drive.LOG
    assert entry["call"] == "chat_turn"
    assert entry["params"]["record"] == {"uuid": "r"}
    assert entry["result"] == res


def test_effect_turn_non_dict_raises_and_logs(monkeypatch):
    class Bare:
        def post(self, path, body):
            return ["not", "a", "dict"]

    monkeypatch.setattr(drive, "get_client", lambda: Bare())
    drive.reset_log()
    with pytest.raises(RuntimeError, match="chat_turn returned non-dict"):
        drive.turn("hi", session="s-4")
    (entry,) = drive.LOG
    assert "chat_turn returned non-dict" in entry["result"]


# ----------------------------------------------------------------- resume
def test_effect_resume_sets_live_mode_and_logs(client):
    client.answers = [{"ok": True, "transcript": []}]
    drive.resume({"session_id": "s-5", "approval_id": "ap", "decision": "approve"})
    body = client.posts[0][1]
    assert body["operation"] == "chat_resume"
    assert body["params"] == {"session_id": "s-5", "approval_id": "ap",
                              "decision": "approve", "mode": "live"}
    assert drive.LOG[-1]["call"] == "chat_resume"


def test_accept_enhancement_offer_payload(client):
    drive.accept_enhancement_offer("s-6", {"offer_id": "o1"}, "/api/3/workflows/w")
    assert client.last_params() == {"session_id": "s-6", "decision": "accept",
                                    "offer_id": "o1", "workflow_iri": "/api/3/workflows/w",
                                    "mode": "live"}
    drive.accept_enhancement_offer("s-7", {"id": "o2"}, "/w")
    assert client.last_params()["offer_id"] == "o2"


def test_new_session_and_entity_shape():
    sid = drive.new_session("a2")
    assert sid.startswith("effect-a2-")
    drive.LOG.append({"x": 1})
    drive.reset_log()
    assert drive.LOG == []
    ent = drive.open_playbook_entity("/api/3/workflows/w", "u1", "PB", "steps: []")
    assert ent == {"iri": "/api/3/workflows/w", "module": "workflows", "uuid": "u1",
                   "fields": {"name": "PB"}, "playbook_yaml": "steps: []"}


def test_transcript_helpers():
    res = {"transcript": [
        {"type": "tool_use", "name": "get_record", "id": "t1", "input": {}},
        {"type": "enhancement_offer", "offer_id": "o1"},
        {"type": "text", "text": "Done."},
    ]}
    assert drive.first_card(res, "enhancement_offer")["offer_id"] == "o1"
    assert drive.first_card(res, "approval_request") is None
    assert drive.tool_names(res) == ["get_record"]
    assert drive.final_text(res) == "Done."


# ------------------------------------------------------------------ runner
def test_runner_dump_writes_the_loop_log(client, monkeypatch, tmp_path):
    client.answers = [{"ok": True, "transcript": [{"type": "text", "text": "hi"}]}]
    monkeypatch.setattr(runner, "get_config",
                        lambda: type("C", (), {"is_live": lambda self: True,
                                               "base_url": "box"})())

    def probe():
        """A probe that drives one turn."""
        drive.turn("ping", session="s-r")
        return Result("ZZ", "zz", "PASS", "ok")

    monkeypatch.setattr(runner, "ALL", {"ZZ": probe})
    assert runner.main(["--only", "ZZ", "--dump", str(tmp_path)]) == 0
    dumped = json.loads((tmp_path / "zz.json").read_text())
    assert [e["call"] for e in dumped] == ["chat_turn"]
    assert dumped[0]["params"]["messages"][0]["content"] == "ping"


# ------------------------------------------------------------------ triage
def test_run_op_probe_payload(client):
    client.answers = [{"ok": True, "result": 1}]
    out = triage._run_op("fortigate-firewall", "get_blocked_ip", {"x": 1})
    assert out == {"ok": True, "result": 1}
    path, body = client.posts[0]
    assert body["operation"] == "call_mcp_tool"
    assert body["connector"] == cd.CONN
    assert "version" not in body
    assert body["config"] == drive.CONFIG
    assert body["params"] == {"tool": "run_op", "args": {
        "connector": "fortigate-firewall", "op": "get_blocked_ip",
        "params": {"x": 1}, "confirm": True}}


def test_run_op_non_dict_is_ok_false(monkeypatch):
    class Bare:
        def post(self, path, body):
            return "oops"

    monkeypatch.setattr(triage, "get_client", lambda: Bare())
    out = triage._run_op("fg", "op", {})
    assert out["ok"] is False and "non-dict" in out["raw"]


def test_firewall_holds_reads_both_lists(client, monkeypatch):
    client.answers = [{"blocked": []}, {"hosts": ["203.0.113.9"]}]
    assert triage._firewall_holds("203.0.113.9") is True
    ops = [b["params"]["args"]["op"] for _, b in client.posts]
    assert ops == ["get_blocked_ip", "get_quarantine_hosts"]


def test_firewall_holds_false_when_on_neither_list(client):
    client.answers = [{"blocked": []}, {"hosts": []}]
    assert triage._firewall_holds("203.0.113.9") is False


def test_unblock_is_best_effort(monkeypatch):
    calls = []

    def boom(connector, op, params):
        calls.append(op)
        raise RuntimeError("firewall unreachable")

    monkeypatch.setattr(triage, "_run_op", boom)
    triage._unblock("203.0.113.9")  # must not raise
    assert calls == ["unblock_ip", "unquarantine_host"]
