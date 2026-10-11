"""chat_drive, one test per behaviour in the driver inventory (CD rows).

The wire tests go through the real path: drive_scenario -> shared driver ->
BoxExec -> _execute -> client.post, with a fake probes client that records
every body. Nothing here reaches a box.
"""
from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
import types

import evals.chat_drive as cd
import pytest
from evals import scoring


class _Client:
    """A probes client: records each post and answers from a queue."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.posts: list[tuple[str, dict]] = []

    def post(self, path, body):
        self.posts.append((path, body))
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return {"status": "success", "data": answer}

    def ops(self):
        return [b["operation"] for _, b in self.posts]


@pytest.fixture
def live_env(monkeypatch):
    """Route `probes._env` to a fake config and the given client."""
    def install(client):
        cfg = types.SimpleNamespace(is_live=lambda: True)
        env = types.SimpleNamespace(get_config=lambda: cfg, get_client=lambda: client)
        probes_pkg = importlib.import_module("probes")
        monkeypatch.setattr(probes_pkg, "_env", env, raising=False)
        return client
    return install


_APPROVAL = {"ok": True, "stop_reason": "approval_required", "turn": 1, "transcript": [
    {"type": "text", "text": "a"},
    {"type": "approval_request", "approval_id": "a9", "tool": "run_op"}]}
_DONE = {"ok": True, "stop_reason": "end_turn", "turn": 1,
         "transcript": [{"type": "text", "text": "done"}]}


# ------------------------------------------------------------------ CLI / run
def test_cli_defaults_and_record_is_json_string(monkeypatch):
    seen = {}
    monkeypatch.setattr(cd, "run", lambda **kw: seen.update(kw) or 0)
    cd.main(["--message", "hi", "--record", '{"a": 1}'])
    assert seen["intent"] == "triage"
    assert seen["config"] == "fsrpb-live"
    assert seen["version"] is None
    assert seen["record"] == {"a": 1}
    assert seen["capture_fixture"] is False and seen["as_json"] is False


def test_cli_record_can_be_a_path(monkeypatch, tmp_path):
    seen = {}
    monkeypatch.setattr(cd, "run", lambda **kw: seen.update(kw) or 0)
    p = tmp_path / "rec.json"
    p.write_text('{"uuid": "u9"}')
    cd.main(["--message", "hi", "--record", str(p)])
    assert seen["record"] == {"uuid": "u9"}


def test_run_unknown_task_returns_2(monkeypatch):
    import evals.tasks as tasks
    monkeypatch.setattr(tasks, "load_tasks", lambda names: [])
    lines = []
    assert cd.run(task_name="nope", message=None, intent="triage", version=None,
                  config="c", capture_fixture=False, as_json=False,
                  log=lines.append) == 2
    assert any("no task fixture named 'nope'" in line for line in lines)


def test_run_needs_task_or_message_returns_2():
    lines = []
    assert cd.run(task_name=None, message=None, intent="triage", version=None,
                  config="c", capture_fixture=False, as_json=False,
                  log=lines.append) == 2
    assert any("need --task" in line for line in lines)


def test_run_investigation_fixture_drives_triage(monkeypatch, tmp_path):
    import evals.tasks as tasks
    task = types.SimpleNamespace(name="t1", prompt="p", mode="investigation",
                                 required_facts=[], forbidden_facts=[],
                                 investigation_quality={})
    monkeypatch.setattr(tasks, "load_tasks", lambda names: [task])
    seen = {}

    def fake_drive(message, intent, **kw):
        seen["intent"] = intent
        return {"session": "s", "transcript": [], "trace": [], "final_text": "",
                "stop_reason": "end_turn", "elapsed": 0.1}
    monkeypatch.setattr(cd, "drive_scenario", fake_drive)
    monkeypatch.setattr(cd, "render_validate", lambda t: {"skipped": "x"})
    monkeypatch.setattr(cd, "RUN_DIR", tmp_path)
    cd.run(task_name="t1", message=None, intent="build", version=None, config="c",
           capture_fixture=False, as_json=False, log=lambda *_: None)
    assert seen["intent"] == "triage"


def _fake_run_env(monkeypatch, tmp_path, *, render, drive_ok=True):
    monkeypatch.setattr(cd, "RUN_DIR", tmp_path / "runs")

    def fake_drive(message, intent, **kw):
        if not drive_ok:
            raise RuntimeError("box down")
        return {"session": "s1", "transcript": [], "trace": [{"name": "get_record"}],
                "final_text": "hi", "stop_reason": "end_turn", "elapsed": 0.5}
    monkeypatch.setattr(cd, "drive_scenario", fake_drive)
    monkeypatch.setattr(cd, "render_validate", lambda t: render)


def test_run_drive_failure_returns_1(monkeypatch, tmp_path):
    _fake_run_env(monkeypatch, tmp_path, render={"skipped": "x"}, drive_ok=False)
    lines = []
    assert cd.run(task_name=None, message="hi", intent="triage", version=None,
                  config="c", capture_fixture=False, as_json=False,
                  log=lines.append) == 1
    assert any(line.startswith("!! drive failed: box down") for line in lines)


def test_run_exit_code_follows_verdict(monkeypatch, tmp_path):
    _fake_run_env(monkeypatch, tmp_path, render={"ok": True, "events": 2, "violations": []})
    assert cd.run(task_name=None, message="hi", intent="triage", version=None,
                  config="c", capture_fixture=False, as_json=False,
                  log=lambda *_: None) == 0
    _fake_run_env(monkeypatch, tmp_path, render={"ok": False, "violations": ["bad"]})
    assert cd.run(task_name=None, message="hi", intent="triage", version=None,
                  config="c", capture_fixture=False, as_json=False,
                  log=lambda *_: None) == 1


def test_run_capture_fixture_skipped_for_task(monkeypatch, tmp_path):
    import evals.tasks as tasks
    task = types.SimpleNamespace(name="t2", prompt="p", mode="triage",
                                 required_facts=[], forbidden_facts=[],
                                 investigation_quality={})
    monkeypatch.setattr(tasks, "load_tasks", lambda names: [task])
    _fake_run_env(monkeypatch, tmp_path, render={"skipped": "x"})
    monkeypatch.setattr(cd, "score_result", lambda *a, **k: {
        "levels": {}, "score": 0, "max": 0, "fraction": 0.0})
    lines = []
    cd.run(task_name="t2", message=None, intent="triage", version=None, config="c",
           capture_fixture=True, as_json=False, log=lines.append)
    assert any("--capture-fixture is for ad-hoc" in line for line in lines)


def test_run_persists_summary_and_json(monkeypatch, tmp_path):
    _fake_run_env(monkeypatch, tmp_path, render={"skipped": "x"})
    lines = []
    cd.run(task_name=None, message="hi", intent="triage", version=None, config="c",
           capture_fixture=False, as_json=True, log=lines.append)
    (summary_path,) = (tmp_path / "runs").glob("chatdrive_*.summary.json")
    saved = json.loads(summary_path.read_text())
    assert saved["scenario"] == "ad-hoc" and saved["session"] == "s1"
    assert saved["trace"] == [{"name": "get_record", "args": None, "ok": None}]
    assert saved["passed"] is True
    assert any('"scenario": "ad-hoc"' in line for line in lines)


# -------------------------------------------------------------- drive_scenario
def test_drive_scenario_not_live_raises(monkeypatch):
    cfg = types.SimpleNamespace(is_live=lambda: False)
    env = types.SimpleNamespace(get_config=lambda: cfg, get_client=lambda: None)
    monkeypatch.setattr(importlib.import_module("probes"), "_env", env, raising=False)
    with pytest.raises(RuntimeError, match="not configured"):
        cd.drive_scenario("hi", "triage", log=lambda *_: None)


def test_drive_scenario_session_default_and_turn_params(live_env):
    client = live_env(_Client([_DONE]))
    res = cd.drive_scenario("hello", "triage", log=lambda *_: None)
    assert res["session"].startswith("chatdrive-")
    _, body = client.posts[0]
    assert body == {"connector": cd.CONN, "operation": "chat_turn", "config": "fsrpb-live",
                    "params": {"session_id": res["session"],
                               "messages": [{"role": "user", "content": "hello"}],
                               "intent": "triage", "mode": "live", "detached": False}}


def test_drive_scenario_sends_record_and_entity_only_when_given(live_env):
    client = live_env(_Client([_DONE, _DONE]))
    cd.drive_scenario("a", "triage", record={"uuid": "r1"}, entity={"iri": "/x"},
                      session="s-x", log=lambda *_: None)
    cd.drive_scenario("b", "triage", session="s-y", log=lambda *_: None)
    with_ctx, without = (b["params"] for _, b in client.posts)
    assert with_ctx["record"] == {"uuid": "r1"} and with_ctx["entity"] == {"iri": "/x"}
    assert "record" not in without and "entity" not in without


def test_drive_scenario_turn_error_raises_before_resume(live_env):
    client = live_env(_Client([{"ok": False, "error": "model_blocked",
                                "stop_reason": "approval_required",
                                "transcript": [{"type": "approval_request",
                                                "approval_id": "a1"}]}]))
    with pytest.raises(RuntimeError, match="chat_turn error: model_blocked"):
        cd.drive_scenario("hi", "triage", session="s", log=lambda *_: None)
    assert client.ops() == ["chat_turn"]


def test_scripted_resume_keeps_its_own_card_key(live_env):
    client = live_env(_Client([_APPROVAL, _DONE]))
    cd.drive_scenario("hi", "triage", session="s", log=lambda *_: None,
                      resume={"decision": "approve", "approval_id": "mine"})
    op, body = client.posts[1]
    assert body["operation"] == "chat_resume"
    assert body["params"]["approval_id"] == "mine"


def test_drive_scenario_auto_resume_answers_the_halt_it_stopped_on(live_env):
    client = live_env(_Client([_APPROVAL, _DONE]))
    cd.drive_scenario("hi", "triage", session="s", log=lambda *_: None)
    assert client.ops() == ["chat_turn", "chat_resume"]
    params = client.posts[1][1]["params"]
    assert params == {"session_id": "s", "decision": "approve", "approval_id": "a9"}


def test_scripted_resume_sent_even_without_a_halt(live_env):
    client = live_env(_Client([_DONE, _DONE]))
    cd.drive_scenario("hi", "triage", session="s", log=lambda *_: None,
                      resume={"decision": "reject", "card_id": "c1"})
    assert client.ops() == ["chat_turn", "chat_resume"]
    assert client.posts[1][1]["params"] == {"decision": "reject", "card_id": "c1",
                                            "session_id": "s"}


def test_drive_scenario_resume_transport_error_raises(live_env):
    live_env(_Client([_APPROVAL, RuntimeError("conn reset")]))
    with pytest.raises(RuntimeError, match="chat_resume error: RuntimeError: conn reset"):
        cd.drive_scenario("hi", "triage", session="s", log=lambda *_: None)


def test_drive_scenario_merges_resume_transcript_and_stop(live_env):
    resumed = {"ok": True, "stop_reason": "end_turn", "transcript": [
        {"type": "text", "text": "b"}]}
    live_env(_Client([_APPROVAL, resumed]))
    res = cd.drive_scenario("hi", "triage", session="s", log=lambda *_: None)
    assert [f.get("text") for f in res["transcript"] if f["type"] == "text"] == ["a", "b"]
    assert [f["type"] for f in res["transcript"]] == ["text", "approval_request", "text"]
    assert res["stop_reason"] == "end_turn"
    assert set(res) == {"session", "transcript", "trace", "final_text", "stop_reason",
                        "elapsed", "version", "config"}
    assert res["final_text"] == "ab"
    assert res["version"] is None and res["config"] == "fsrpb-live"


def test_drive_scenario_keeps_turn_stop_when_resume_has_none(live_env):
    live_env(_Client([_APPROVAL, {"ok": True, "transcript": []}]))
    res = cd.drive_scenario("hi", "triage", session="s", log=lambda *_: None)
    assert res["stop_reason"] == "approval_required"


def test_drive_scenario_log_lines(live_env):
    live_env(_Client([_APPROVAL, _DONE]))
    lines = []
    cd.drive_scenario("ping", "triage", session="sess-1", log=lines.append)
    text = "\n".join(lines)
    assert ">> chat_turn (sync) session=sess-1 intent=triage" in text
    assert ">> msg: ping" in text
    assert "stop_reason=approval_required" in text and "turn=1" in text
    assert ">> chat_resume decision=approve (stop_reason was approval_required)" in text
    assert ">> resume returned stop_reason=end_turn" in text


def test_drive_scenario_elapsed_is_rounded_to_a_tenth(live_env):
    live_env(_Client([_APPROVAL, _DONE]))
    res = cd.drive_scenario("hi", "triage", session="s", log=lambda *_: None)
    assert isinstance(res["elapsed"], float)
    assert round(res["elapsed"], 1) == res["elapsed"]


# ---------------------------------------------------------------- wire pieces
def test_execute_wire_omits_falsy_version_keeps_config():
    client = _Client([{"ok": True}] * 3)
    cd._execute(client, "chat_turn", {"x": 1}, None, "cfg")
    cd._execute(client, "chat_turn", {"x": 1}, "", "cfg")
    cd._execute(client, "chat_turn", {"x": 1}, "1.2.3", "cfg")
    bodies = [b for _, b in client.posts]
    assert all(p == "/api/integration/execute/" for p, _ in client.posts)
    assert "version" not in bodies[0] and "version" not in bodies[1]
    assert bodies[2]["version"] == "1.2.3"
    assert all(b["config"] == "cfg" and b["connector"] == cd.CONN for b in bodies)


def test_unwrap_peels_only_status_data_envelopes():
    assert cd._unwrap({"status": "success", "data": {"a": 1}}) == {"a": 1}
    assert cd._unwrap({"data": {"a": 1}}) == {"data": {"a": 1}}
    assert cd._unwrap({"status": "x", "data": "str"}) == {"status": "x", "data": "str"}
    assert cd._unwrap([1, 2]) == [1, 2]


def test_box_exec_refuses_a_non_dict_answer():
    class Bare:
        def post(self, path, body):
            return ["not", "an", "envelope"]

    with pytest.raises(RuntimeError, match="chat_turn returned non-dict"):
        cd.BoxExec(Bare()).execute("chat_turn", {})


def test_connector_name_env_override():
    code = "import evals.chat_drive as c; print(c.CONN)"
    tooling = os.path.dirname(os.path.dirname(os.path.abspath(cd.__file__)))
    base = {k: v for k, v in os.environ.items() if k != "FSR_BUILDER_CONNECTOR"}
    out = subprocess.run([sys.executable, "-c", code], env={**base, "PYTHONPATH": tooling},
                         capture_output=True, text=True, check=True).stdout.strip()
    assert out == "connector-fsr-soc-assistant"
    out = subprocess.run([sys.executable, "-c", code],
                         env={**base, "PYTHONPATH": tooling,
                              "FSR_BUILDER_CONNECTOR": "connector-x"},
                         capture_output=True, text=True, check=True).stdout.strip()
    assert out == "connector-x"


# ------------------------------------------------------------ transcript analysis
def test_trace_pairs_results_by_id_and_falls_back_to_last():
    transcript = [
        {"type": "tool_use", "id": "a", "name": "run_op", "input": {}},
        {"type": "tool_use", "id": "b", "name": "get_record", "input": {}},
        {"type": "tool_result", "tool_use_id": "b", "content": {"status": "success"}},
        {"type": "tool_result", "tool_use_id": "a", "content": {"status": "error"}},
    ]
    trace = cd.transcript_to_trace(transcript)
    assert [(c["name"], c["ok"]) for c in trace] == [("run_op", False), ("get_record", True)]
    fallback = cd.transcript_to_trace([
        {"type": "tool_use", "name": "x", "input": {}},
        {"type": "tool_result", "content": {"status": "ok"}},
    ])
    assert fallback[0]["ok"] is True


def test_trace_marks_guard_refusals():
    transcript = [
        {"type": "tool_use", "id": "g", "name": "run_op", "input": {}},
        {"type": "tool_result", "tool_use_id": "g",
         "content": json.dumps({"status": "error", "capability_guard": "no"})},
        {"type": "tool_use", "id": "h", "name": "run_op", "input": {}},
        {"type": "tool_result", "tool_use_id": "h", "content": {"status": "success"}},
        "not-a-frame",
    ]
    trace = cd.transcript_to_trace(transcript)
    assert [c["refused"] for c in trace] == [True, False]


def test_run_op_operation_and_args_map_to_op_and_params():
    args = cd._normalize_args("run_op", {"connector": "fg", "operation": "get_x",
                                         "args": {"ip": "1.2.3.4"}})
    assert args["op"] == "get_x" and args["params"] == {"ip": "1.2.3.4"}
    assert cd._normalize_args("get_record", {"uuid": "u"}) == {"uuid": "u"}
    assert cd._normalize_args("run_op", None) == {}


def test_result_ok_reads_status():
    assert cd._result_ok({"status": "success"}) is True
    assert cd._result_ok('{"status": "ERROR"}') is False
    assert cd._result_ok({"no": "status"}) is None
    assert cd._result_ok("not json") is None


def test_result_refused_markers():
    assert cd._result_refused({"duplicate_search_guard": True}) is True
    assert cd._result_refused(json.dumps({"action_card_staged": 1})) is True
    assert cd._result_refused({"status": "success"}) is False
    assert cd._result_refused("not json") is False


def test_render_validate_skips_without_bridge(monkeypatch):
    monkeypatch.setattr(cd, "_find_bridge", lambda: None)
    assert "render bridge not found" in cd.render_validate([])["skipped"]


def test_render_validate_node_missing_skips(monkeypatch, tmp_path):
    bridge = tmp_path / "render_check.cjs"
    bridge.write_text("")
    monkeypatch.setattr(cd, "_find_bridge", lambda: bridge)

    def no_node(*a, **k):
        raise FileNotFoundError("node")
    monkeypatch.setattr(cd.subprocess, "run", no_node)
    assert cd.render_validate([]) == {"skipped": "node not on PATH"}


def test_render_validate_timeout_and_non_json_fail(monkeypatch, tmp_path):
    bridge = tmp_path / "render_check.cjs"
    bridge.write_text("")
    monkeypatch.setattr(cd, "_find_bridge", lambda: bridge)

    def slow(*a, **k):
        raise subprocess.TimeoutExpired(cmd="node", timeout=60)
    monkeypatch.setattr(cd.subprocess, "run", slow)
    assert cd.render_validate([]) == {"ok": False,
                                      "violations": ["render bridge timed out"]}

    def junk(*a, **k):
        return types.SimpleNamespace(stdout="<html>", returncode=0)
    monkeypatch.setattr(cd.subprocess, "run", junk)
    out = cd.render_validate([])
    assert out["ok"] is False and out["violations"][0].startswith("bridge non-JSON")


def test_render_validate_returns_bridge_json(monkeypatch, tmp_path):
    bridge = tmp_path / "render_check.cjs"
    bridge.write_text("")
    monkeypatch.setattr(cd, "_find_bridge", lambda: bridge)
    seen = {}

    def ok(argv, input, **k):
        seen["input"] = json.loads(input)
        return types.SimpleNamespace(stdout='{"ok": true, "events": 3}', returncode=0)
    monkeypatch.setattr(cd.subprocess, "run", ok)
    assert cd.render_validate([{"type": "text"}]) == {"ok": True, "events": 3}
    assert seen["input"] == {"transcript": [{"type": "text"}]}


def test_extract_yaml_takes_last_fence():
    text = "first\n```yaml\na: 1\n```\nthen\n```yaml\nb: 2\n```\n"
    assert cd._extract_yaml(text) == "b: 2"
    assert cd._extract_yaml("no playbook here") == ""


def test_score_result_passes_task_fields(monkeypatch):
    seen = {}

    def fake_score(**kw):
        seen.update(kw)
        return {"levels": {}}
    monkeypatch.setattr(scoring, "score", fake_score)
    task = types.SimpleNamespace(mode="investigation", required_facts=["r"],
                                 forbidden_facts=["f"], investigation_quality={"q": 1})
    cd.score_result(task, [{"name": "get_record"}], "final")
    assert seen["mode"] == "investigation" and seen["required_facts"] == ["r"]
    assert seen["forbidden_facts"] == ["f"] and seen["investigation_quality"] == {"q": 1}
    assert seen["trace"] == [{"name": "get_record"}] and seen["final_text"] == "final"


def test_verdict_flags_failing_gates_and_render(monkeypatch):
    score = {"score": 1, "max": 2, "fraction": 0.5, "levels": {
        "zzz_gate": {"passed": False, "detail": "missed"},
        "passing": {"passed": True, "detail": "ok"},
        "skipped_one": {"skipped": True},
        "info_one": {"informational": True, "passed": False},
    }}
    lines = []
    ok = cd.print_verdict({"session": "s", "elapsed": 1.0, "stop_reason": "end_turn",
                           "trace": []}, score,
                          {"ok": False, "events": 4, "violations": ["bad"]},
                          scenario="sc", log=lines.append)
    text = "\n".join(lines)
    assert ok is False
    assert "[FAIL] zzz_gate" in text and "unmapped -- inspect trace" in text
    assert "[PASS] passing" in text
    assert "skipped_one" not in text and "info_one" not in text
    assert "[FAIL] render" in text and "bad" in text
    lines = []
    assert cd.print_verdict({"session": "s", "elapsed": 1.0, "stop_reason": "end_turn",
                             "trace": []}, None, {"skipped": "no node"},
                            scenario="sc", log=lines.append) is True
    assert any("[SKIP] render" in line for line in lines)


def test_external_ip_classification():
    assert cd._is_external_ip("8.8.8.8") is True
    assert cd._is_external_ip("10.1.2.3") is False
    assert cd._is_external_ip("192.168.1.1") is False
    assert cd._is_external_ip("127.0.0.1") is False
    assert cd._is_external_ip("not-an-ip") is False


def test_propose_fixture_facts_budget_deliverable():
    result = {"session": "s1", "stop_reason": "end_turn", "trace": [
        {"name": "get_record", "args": {"uuid": "u1"}, "ok": True},
        {"name": "run_op", "args": {"connector": "fg", "op": "x", "params": {"ip": "8.8.8.8"}},
         "ok": True},
        {"name": "run_op", "args": {"op": "y", "params": {"src": "10.0.0.5"}}, "ok": True},
        {"name": "emit_action_card", "args": {}, "ok": True},
    ]}
    out = cd.propose_fixture(result, name="invest_x", prompt="p")
    fixture = out["fixture"]
    assert {"tool": "get_record", "args_contains": ["u1"],
            "label": "pull the originating alert"} in fixture["required_facts"]
    assert any(r["args_contains"] == ["8.8.8.8"] and "EXTERNAL" in r["label"]
               for r in fixture["required_facts"])
    forbidden_conns = {f["connector"] for f in fixture["forbidden_facts"]}
    assert forbidden_conns == set(cd._TI_CONNECTORS)
    assert all(f["args_contains"] == ["10.0.0.5"] for f in fixture["forbidden_facts"])
    assert fixture["investigation_quality"]["tool_budget_max"] == 6
    assert fixture["investigation_quality"]["require_deliverable"] is True
    assert out["golden"]["stop_reason"] == "end_turn"
    assert len(out["golden"]["trace"]) == 4


def test_write_capture_uses_next_free_index(monkeypatch, tmp_path):
    tasks = tmp_path / "tasks"
    golden = tmp_path / "golden"
    tasks.mkdir()
    golden.mkdir()
    (tasks / "03_old.json").write_text("{}")
    monkeypatch.setattr(cd, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(cd, "TASKS_DIR", tasks)
    monkeypatch.setattr(cd, "GOLDEN_DIR", golden)
    lines = []
    paths = cd.write_capture({"fixture": {"name": "invest_x"}, "golden": {"fixture": "invest_x"}},
                             log=lines.append)
    assert paths["task_path"].endswith("04_invest_x.json")
    assert json.loads((golden / "invest_x.json").read_text()) == {"fixture": "invest_x"}
    assert any("wrote fixture" in line for line in lines)


def test_verdict_fails_on_a_failing_gate_alone():
    """A failing scoring gate fails the verdict even when the render is skipped."""
    score = {"score": 0, "max": 1, "fraction": 0.0,
             "levels": {"zzz_gate": {"passed": False, "detail": "missed"}}}
    ok = cd.print_verdict({"session": "s", "elapsed": 1.0, "stop_reason": "end_turn",
                           "trace": []}, score, {"skipped": "no node"},
                          scenario="sc", log=lambda *_: None)
    assert ok is False
