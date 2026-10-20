"""A record trigger's module must survive compile -> decompile -> compile.

The post-create/update/delete trigger carries its module as `resource` /
`resources` on the wire. The decompiler lifted that back to a friendly
`module:` only for `type: start`; the record-trigger branch popped it as a
re-derivable default. Recompiling then defaulted the trigger to
[alerts, incidents], so a designer round trip silently widened what fires the
playbook (tracker #186).
"""
from __future__ import annotations

import pytest
import yaml

from fsr_playbooks._db import PACKAGED_SLIM_DB
from fsr_playbooks.compiler import compile_yaml
from fsr_playbooks.compiler.decompiler import decompile_to_yaml

_PB = """
collection: T
playbooks:
  - name: PB
    steps:
      - name: Start
        type: {trigger}
        {module_line}
        next: Note
      - name: Note
        type: set_variable
        vars:
          seen: "{{{{ vars.input.records[0].name }}}}"
"""


def _trigger_args(fsr_json: dict) -> dict:
    wf = fsr_json["data"][0]["workflows"][0] if "data" in fsr_json else fsr_json["workflows"][0]
    start = next(s for s in wf["steps"] if s["name"] == "Start")
    return start["arguments"]


def _compile(text: str):
    res = compile_yaml(text, PACKAGED_SLIM_DB)
    assert res.ok, [e.message for e in res.errors if e.severity != "warning"]
    return res


@pytest.mark.parametrize("trigger", ["start_on_create", "start_on_update", "start_on_delete"])
@pytest.mark.parametrize("module_line,expected", [
    ("module: incidents", ["incidents"]),
    ("modules: [alerts, indicators]", ["alerts", "indicators"]),
])
def test_record_trigger_module_round_trips(trigger, module_line, expected):
    first = _compile(_PB.format(trigger=trigger, module_line=module_line))
    assert _trigger_args(first.fsr_json)["resources"] == expected

    pulled = decompile_to_yaml(first.fsr_json, PACKAGED_SLIM_DB)
    step = next(s for s in yaml.safe_load(pulled)["playbooks"][0]["steps"]
                if s["name"] == "Start")
    friendly = [step["module"]] if "module" in step else step.get("modules")
    assert friendly == expected, f"module lost on pull: {step}"

    second = _compile(pulled)
    assert _trigger_args(second.fsr_json)["resources"] == expected
    assert not any("defaulting to [alerts, incidents]" in e.message for e in second.errors)
