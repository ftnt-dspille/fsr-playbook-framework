"""Every `_FRIENDLY_FORMS[*]['example']` in mcp_server must compile clean.

Locks in the contract that get_step_type's authoring example is
something the validator actually accepts. Drift between the friendly
form and the resolver is the original cause of the d5fdb378 bad-syntax
session: the example taught a step-level `branches:` dict on
manual_input/decision that the parser hard-errors on.
"""
from __future__ import annotations

import yaml

from compiler import compile_yaml

from mcp_server import _FRIENDLY_FORMS


# Friendly forms that document a non-trigger step type. We synthesize a
# Start → <step> → End scaffold; trigger / terminator types are exercised
# elsewhere and don't fit this scaffold.
_TRIGGER_LIKE = {"start", "start_on_create", "start_on_update"}
_TERMINATOR_LIKE = {"end", "stop"}
_NEEDS_TARGET = {"workflow_reference"}  # references another playbook


def _scaffold(example: dict) -> str:
    """Wrap a friendly-form example in a minimal compilable playbook."""
    # The example may carry step-level keys (options:, conditions:,
    # next:, …) alongside arguments — preserve them verbatim. The parser
    # recognizes step-level options/conditions/vars/next/branches.
    middle = dict(example)
    middle.setdefault("name", "Middle")
    middle_name = middle["name"]
    stype = example.get("type")
    if stype not in {"decision", "manual_input"}:
        middle.setdefault("next", "End")

    pb = {
        "collection": "T",
        "playbooks": [
            {
                "name": "P",
                "is_active": False,
                "steps": [
                    {"type": "start", "name": "Start", "next": middle_name},
                    middle,
                    {"type": "end", "name": "End"},
                ],
            }
        ],
    }
    # If the example is decision/manual_input, ensure all referenced
    # next-targets resolve to End (avoid synthesizing extra steps).
    if stype == "decision":
        for c in middle.get("conditions", []) or []:
            if isinstance(c, dict):
                c["next"] = "End"
    if stype == "manual_input":
        for o in middle.get("options", []) or []:
            if isinstance(o, dict):
                o["next"] = "End"

    return yaml.safe_dump(pb, sort_keys=False)


def test_every_friendly_form_example_compiles_clean(db_path):
    failures: list[str] = []
    for short, entry in _FRIENDLY_FORMS.items():
        example = entry.get("example")
        if not example or short in _TRIGGER_LIKE | _TERMINATOR_LIKE | _NEEDS_TARGET:
            continue
        text = _scaffold(example)
        result = compile_yaml(text, db_path)
        errs = [e for e in (result.errors or [])
                if getattr(e, "severity", "error") != "warning"]
        if errs:
            msgs = "\n".join(f"  {e.code} {e.path}: {e.message}" for e in errs)
            failures.append(
                f"\n{short} friendly-form example fails to compile:\n{msgs}"
            )
    assert not failures, (
        "Friendly-form examples must validate cleanly so get_step_type "
        "responses are copy-pasteable:" + "".join(failures)
    )
