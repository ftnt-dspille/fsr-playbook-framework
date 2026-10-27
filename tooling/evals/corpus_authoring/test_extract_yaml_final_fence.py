"""_extract_yaml takes the LAST YAML in document order, tool input or prose fence.

A repair drive's last repair_playbook call carries the still-broken draft, then
the agent emits the corrected YAML in its final message. The corrected fence
comes later, so it must win -- otherwise a real fix is scored as no-fix (the
grader false-negative seen in a live runtime-dependency drive).
"""
from __future__ import annotations

from tooling.evals.corpus_authoring import drive

BROKEN = "steps:\n- desc: '{{ vars.steps.X.data.value }}'\n"
FIXED = "steps:\n- desc: '{{ vars.steps.X.data }}'\n"


def _tool(name, yaml_text):
    return {"message": {"content": [
        {"type": "tool_use", "name": f"mcp__{drive.SERVER}__{name}",
         "input": {"yaml_text": yaml_text}}]}}


def _text(body):
    return {"message": {"content": [{"type": "text", "text": body}]}}


def test_final_fence_after_repair_tool_wins():
    events = [_tool("repair_playbook", BROKEN),
              _text(f"The op returns a list, so .value fails.\n```yaml\n{FIXED}```")]
    yaml, tools = drive._extract_yaml(events)
    assert yaml.strip() == FIXED.strip(), yaml
    assert tools == ["repair_playbook"]


def test_later_tool_yaml_beats_earlier_prose_fence():
    # chronological: an early draft fence then a tool receives the newer YAML
    events = [_text(f"draft:\n```yaml\n{BROKEN}```"),
              _tool("build_playbook", FIXED)]
    yaml, _ = drive._extract_yaml(events)
    assert yaml.strip() == FIXED.strip(), yaml


def test_tool_yaml_used_when_no_answer_fence():
    events = [_tool("build_playbook", FIXED), _text("Done, published.")]
    yaml, _ = drive._extract_yaml(events)
    assert yaml.strip() == FIXED.strip(), yaml


def test_result_event_fence_counts():
    events = [_tool("repair_playbook", BROKEN),
              {"type": "result", "result": f"here is the fix\n```yaml\n{FIXED}```"}]
    yaml, _ = drive._extract_yaml(events)
    assert yaml.strip() == FIXED.strip(), yaml
