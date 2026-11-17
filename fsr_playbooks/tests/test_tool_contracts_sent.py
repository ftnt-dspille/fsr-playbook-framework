"""The call contract the model is SENT, per advertised tool (W1b).

`tool_description` caps a description and drops `Args:`/`Returns:` sections, so
anything a caller needs for a correct first call that lives only there is never
sent. These read `REGISTRY[name]` (what `anthropic_tools()` advertises), not the
docstring, and prove the accepted call shapes still pass the argument gate.
"""
from __future__ import annotations

import dataclasses
import inspect
import json
from pathlib import Path

import pytest

from fsr_playbooks.llm import tools as T
from fsr_playbooks.tests._tool_audit import audit, audit_tool

FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures" / "tool_contract_calls.json").read_text())

# --------------------------------------------------------------------- ratchet

# Every advertised tool whose docstring is not sent whole, with why the cut
# text is not needed for a first call. A tool that newly loses text and is not
# here fails `test_no_tool_silently_loses_contract_text`: either reorder the
# docstring so the contract is in the first 1,200 characters, carry it in the
# schema (`ARGS_IN_SCHEMA`), or add it here with the reason.
_RETURNS = "cut text is return-shape documentation"
_SCHEMA = "its Args contract is sent in the input schema, the rest is return-shape documentation"
CUT_TEXT_NOT_NEEDED: dict[str, str] = {
    "compose_playbook": "the plan's step contract is the input schema (steps_schema)",
    "edit_playbook": "the op list is the input schema (op enum and per-key descriptions); the rest is return shape",
    "get_record": _SCHEMA,
    "search_module_records": _SCHEMA + "; the child-by-parent filter recipe is a recipe, not a contract",
    "verify_enhancement": _SCHEMA + "; regression kinds are return-shape documentation",
    "verify_playbook": "cut text is the diagnostic-code catalogue (return shape); the argument contract is sent",
    "run_playbook": "its Args are the hand-written input schema; the rest is return shape",
    "resume_playbook": "its Args are the hand-written input schema; the rest is return shape",
    "create_record": "its Args are the hand-written input schema; the rest is return shape",
    "update_record": "its Args are the hand-written input schema; the rest is return shape",
    "run_op": "the confirm / destructive-op rules are in the sent text; the rest is return shape and the step_name tip",
    "build_playbook_from_trace": "trace_json and module are left empty by the agent (trace_json is not advertised); the rest is return shape",
    "list_configured_connectors": "`only` is not advertised; the rest is return shape",
    "why_did_playbook_fail": _RETURNS + " and a self-explanatory Args list",
    "list_module_playbooks": "cut text is a design note and return shape; the arguments are self-describing",
    "fmg_device": _RETURNS,
    "faz_search": _RETURNS,
    "edr_host": _RETURNS,
    "siem_search": _RETURNS,
    "list_playbook_runs": _RETURNS,
    "plan_playbook": _RETURNS,
}


def test_no_tool_silently_loses_contract_text():
    """A new tool (or a docstring grown past the cap) that loses text without
    an entry above fails here."""
    lost = {a.name for a in audit() if a.cut_text}
    unlisted = sorted(lost - set(CUT_TEXT_NOT_NEEDED))
    assert not unlisted, (
        f"{unlisted} lose docstring text to the cap or the Args drop and are "
        "not in CUT_TEXT_NOT_NEEDED: move the contract into the first 1,200 "
        "characters or the schema, or list the tool with a reason")


def test_the_not_needed_table_does_not_rot():
    advertised = {a.name for a in audit()}
    stale = sorted(n for n in CUT_TEXT_NOT_NEEDED
                   if n in advertised and not audit_tool(n).cut_text)
    gone = sorted(set(CUT_TEXT_NOT_NEEDED) - set(T.REGISTRY))
    assert not stale, f"nothing is cut any more, drop the entry: {stale}"
    assert not gone, f"not a tool: {gone}"
    assert all(r.strip() for r in CUT_TEXT_NOT_NEEDED.values())


def test_every_schema_carried_arg_is_a_real_parameter_with_a_docstring_entry():
    for name, params in T.ARGS_IN_SCHEMA.items():
        fn = T.REGISTRY[name].fn
        docs = T.docstring_arg_docs(inspect.getdoc(fn) or "")
        for p in params:
            assert p in inspect.signature(fn).parameters, (name, p)
            assert docs.get(p), f"{name}.{p} has no Args entry to send"


# ------------------------------------------------------- what is sent, per tool

def _prop(tool: str, key: str) -> dict:
    return T.REGISTRY[tool].input_schema["properties"][key]


def test_get_record_is_sent_how_to_identify_the_record():
    assert "required with `uuid` or `record_id`" in _prop("get_record", "module")["description"]
    assert "required if no `iri`" in _prop("get_record", "uuid")["description"]
    assert "needs `module`" in _prop("get_record", "record_id")["description"]
    assert "precedence" in _prop("get_record", "iri")["description"]


def test_search_module_records_is_sent_the_sort_and_filter_shapes():
    sort = _prop("search_module_records", "sort")["description"]
    assert '"direction"' in sort and "list form" in sort
    flt = _prop("search_module_records", "filters")["description"]
    assert "{field: value}" in flt and "list form" in flt and "empty" in flt


def test_verify_enhancement_is_sent_that_before_yaml_is_left_out():
    assert "omit it" in _prop("verify_enhancement", "before_yaml")["description"]
    assert "required" in _prop("verify_enhancement", "after_yaml")["description"]


def test_edit_playbook_is_sent_when_option_and_after_matter():
    after = _prop("edit_playbook", "operations")["items"]["properties"]["after"]
    option = _prop("edit_playbook", "operations")["items"]["properties"]["option"]
    assert "start step to an empty playbook" in after["description"]
    assert "several branches" in option["description"]


# -------------------------------------------------- accepted shapes still pass

@pytest.fixture
def reached():
    """Swap tools for stubs that record being called: a call that reaches the
    stub passed the argument gate."""
    seen: list[str] = []

    def install(monkeypatch, name: str):
        spec = T.REGISTRY[name]

        def fake(*a, **kw):
            seen.append(name)
            return {"ok": True}
        fake.__signature__ = inspect.signature(spec.fn)  # type: ignore[attr-defined]
        monkeypatch.setitem(T.REGISTRY, name, dataclasses.replace(spec, fn=fake))
    return seen, install


@pytest.mark.parametrize("tool", sorted(FIXTURES.keys() - {"_comment"}))
def test_accepted_call_shapes_still_pass_the_argument_gate(tool, reached, monkeypatch):
    seen, install = reached
    install(monkeypatch, tool)
    for args in FIXTURES[tool]:
        seen.clear()
        out = T.dispatch(tool, dict(args))
        assert seen == [tool], (tool, args, out)
