"""Driver YAML-extraction logic, box-free, no LLM.

The driver must take the authored YAML from the last tool call that carried
`yaml_text` (what the toolkit actually received), and fall back to a ```yaml
fence in the final message only when no tool carried YAML. These pin that.
"""
from __future__ import annotations

from tooling.evals.corpus_authoring.drive import SERVER, _extract_yaml


def _tool_use(name, **inp):
    return {"message": {"content": [
        {"type": "tool_use", "name": f"mcp__{SERVER}__{name}", "input": inp}]}}


def _text(t):
    return {"message": {"content": [{"type": "text", "text": t}]}}


def test_prefers_last_tool_yaml_over_fence():
    events = [
        _text("here is a draft\n```yaml\nname: wrong\n```"),
        _tool_use("build_playbook", yaml_text="name: right\nsteps: []\n"),
        _text("done"),
    ]
    y, tools = _extract_yaml(events)
    assert y == "name: right\nsteps: []\n"
    assert tools == ["build_playbook"]


def test_falls_back_to_fence_when_no_tool_yaml():
    events = [
        _tool_use("orient", goal="x"),
        _text("final\n```yaml\nname: fenced\nsteps: []\n```\n"),
    ]
    y, tools = _extract_yaml(events)
    assert "name: fenced" in y
    assert tools == ["orient"]


def test_result_event_counts_as_final_text():
    events = [
        {"type": "result", "result": "```yaml\nname: from_result\n```"},
    ]
    y, _ = _extract_yaml(events)
    assert "from_result" in y


def test_last_tool_yaml_wins_across_multiple_builds():
    events = [
        _tool_use("build_playbook", yaml_text="name: v1\n"),
        _tool_use("verify_playbook", yaml_text="name: v2_final\n"),
    ]
    y, tools = _extract_yaml(events)
    assert y == "name: v2_final\n"
    assert tools == ["build_playbook", "verify_playbook"]


def test_no_yaml_anywhere_returns_empty():
    y, tools = _extract_yaml([_tool_use("orient", goal="x"), _text("no yaml here")])
    assert y == ""
    assert tools == ["orient"]
