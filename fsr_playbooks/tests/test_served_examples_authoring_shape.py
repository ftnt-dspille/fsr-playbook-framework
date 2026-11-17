"""Corpus step examples reach the author in AUTHORING shape -- never the native
`arguments:` wrapper.

step_examples / playbook_steps store steps in the native wire shape
({name, arguments:{...}}), and the compiler rejects that wrapper for every step
("hoist all step arguments to the step level"). An example that kept it taught a
shape the draft gate fails. The serving tools now flatten each example through
`_to_authoring_step` (which reuses the decompiler's hoist + editor-noise keys),
so no wrapper -- at any nesting depth -- ever reaches the model.
"""
from __future__ import annotations

import warnings

warnings.filterwarnings("ignore")

from fsr_playbooks.mcp_server.tools_discovery import _to_authoring_step, get_step_type


def test_hoists_a_simple_wrapper():
    out = _to_authoring_step(
        {"name": "setup", "arguments": {"ctx": "{{vars.x}}", "n": 1}})
    assert "arguments" not in out
    assert out == {"name": "setup", "ctx": "{{vars.x}}", "n": 1}


def test_flattens_a_double_nested_utility_wrapper():
    # Utility / child steps nest arguments.arguments; the author shape has none.
    out = _to_authoring_step(
        {"name": "util", "arguments": {"script": "/x",
                                       "arguments": {"connector": "cyops_utilities"}}})
    assert "arguments" not in out
    assert out["connector"] == "cyops_utilities"


def test_strips_editor_noise_keys():
    out = _to_authoring_step(
        {"name": "s", "arguments": {"resource": "alert", "__recommend": [],
                                    "_showJson": False}})
    assert "__recommend" not in out and "_showJson" not in out
    assert out["resource"] == "alert"


def test_passthrough_without_a_wrapper():
    assert _to_authoring_step({"name": "x", "connector": "c"}) == {
        "name": "x", "connector": "c"}
    assert _to_authoring_step("not a dict") == "not a dict"


def _examples_with_a_wrapper(step_type: str) -> int:
    out = get_step_type(step_type, verbose=True)
    exs = out.get("examples") or []
    return sum(1 for e in exs
               if isinstance(e.get("snippet_json"), dict)
               and "arguments" in e["snippet_json"])


def test_get_step_type_examples_carry_no_wrapper():
    # RED without the fix: the served examples keep the native `arguments:`
    # wrapper. Checked across the step types the slim DB actually has examples
    # for, so the test exercises real corpus rows, not a fixture.
    seen_any = False
    for st in ("SetVariable", "UpdateRecord", "Decision", "ManualInput",
               "cybersponse.action", "Connectors"):
        out = get_step_type(st, verbose=True)
        exs = out.get("examples") or []
        if exs:
            seen_any = True
        assert _examples_with_a_wrapper(st) == 0, (
            f"{st}: a served example still carries the arguments wrapper")
    assert seen_any, "no step type returned any example -- test exercised nothing"
