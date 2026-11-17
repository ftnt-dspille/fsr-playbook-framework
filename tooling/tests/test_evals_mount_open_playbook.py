"""The eval matrix mounts the open playbook the way the product does.

Every enhance fixture used to paste its playbook into the prompt only, so
`edit_playbook` answered `no_open_playbook` and the model re-typed the whole
playbook as a new Create offer -- which still scored 4/4. The matrix had never
measured the edit-then-Apply path the widget runs. These tests pin the mount
(the connector binds `entity.playbook_yaml` the same way), the opt-in for an
inline fixture, and the trace slice the scorer needs to see an edit-path
delivery at all.
"""
from __future__ import annotations

import importlib

from fsr_playbooks.mcp_server import edit_playbook
from fsr_playbooks.mcp_server._shared import get_grounded_yaml

harness = importlib.import_module("evals.harness")
providers = importlib.import_module("evals.providers")
scoring = importlib.import_module("evals.scoring")
tasks_mod = importlib.import_module("evals.tasks")

_OPEN = (
    "playbooks:\n"
    "  - name: Demo\n"
    "    steps:\n"
    "      - name: Start\n"
    "        type: start\n"
    "        module: alerts\n"
    "        run_mode: per_record\n"
    "        next: Read severity\n"
    "      - name: Read severity\n"
    "        type: set_variable\n"
    "        vars:\n"
    "          severity: \"{{ vars.input.records[0].severity }}\"\n"
)


def _task(**kw):
    base = {"name": "t", "mode": "tool_selection",
            "prompt": f"Here is the playbook I currently have open:\n\n```yaml\n{_OPEN}```\n\nAdd a delay."}
    base.update(kw)
    return tasks_mod.Task(**base)


def test_inline_fixture_opts_in_and_others_do_not():
    assert _task(prompt_yaml_is_open=True).open_yaml() == _OPEN
    assert _task().open_yaml() is None


def test_the_open_playbook_is_mounted_for_the_turn_only():
    seen = harness._with_open_playbook(_task(prompt_yaml_is_open=True),
                                       get_grounded_yaml)
    assert seen == _OPEN
    assert get_grounded_yaml() is None


def test_edit_playbook_works_on_the_mounted_playbook():
    def turn():
        return edit_playbook(operations=[{
            "op": "add_step", "after": "Read severity",
            "step": {"name": "Wait", "type": "delay", "seconds": 30}}])
    out = harness._with_open_playbook(_task(prompt_yaml_is_open=True), turn)
    assert out.get("code") != "no_open_playbook", out
    assert "Wait" in (out.get("after_yaml") or "")


def test_edit_result_reaches_the_scorer():
    entry = {"name": "edit_playbook", "args": {}}
    providers._thread_result(entry, "edit_playbook",
                             {"ok": True, "verified_id": "v1",
                              "ready_to_push": True, "after_yaml": "X: 1\n",
                              "regressions": ["big"] * 50})
    assert entry["result"] == {"ok": True, "verified_id": "v1",
                               "ready_to_push": True, "after_yaml": "X: 1\n"}
    assert scoring.delivered_yaml("", [entry]) == "X: 1\n"
    other = {"name": "find"}
    providers._thread_result(other, "find", {"ok": True})
    assert "result" not in other
