"""A step renamed in place is not a deleted step.

The pre-write guard identified steps by NAME only, so every rename read as
"steps[Old Name] deleted" and the Apply was refused (`would_drop_fields`).
Live: the analyst sim asked to rename a manual task on a real shipped
playbook three times in three voices; every Apply was refused, and the
analyst's own words were "that is expected when renaming a step".

Identity is the step uuid, which the designer mount carries. Matching on it
makes a rename an edit -- while everything the renamed step held is still
compared, so a rename that also drops an argument is still refused, and a
"rename" with no uuid to prove identity is still a delete plus an add.
"""
from __future__ import annotations

from fsr_playbooks.compiler import compile_yaml
from fsr_playbooks.compiler.prewrite import check_prewrite
from fsr_playbooks.mcp_server._shared import DB_PATH

U_START = "aaaaaaaa-0000-0000-0000-000000000001"
U_ASK = "aaaaaaaa-0000-0000-0000-000000000002"
U_NOTE = "aaaaaaaa-0000-0000-0000-000000000003"


def _doc(ask_name: str, *, ask_uuid: str | None = U_ASK, note_vars: str = '{a: "1", b: "2"}') -> dict:
    ask_id = f"uuid: {ask_uuid}, " if ask_uuid else ""
    y = f"""collection: C
playbooks:
- name: P
  steps:
  - {{uuid: {U_START}, name: Start, type: start, module: alerts, next: {ask_name}}}
  - {{{ask_id}name: {ask_name}, type: set_variable, vars: {note_vars}, next: Note}}
  - {{uuid: {U_NOTE}, name: Note, type: set_variable, vars: {{c: "3"}}}}
"""
    res = compile_yaml(y, DB_PATH)
    assert res.ok, [e.to_dict() for e in res.errors]
    return res.fsr_json


def test_the_compiler_keeps_an_authored_step_uuid():
    wf = _doc("Ask")["data"][0]["workflows"][0]
    assert U_ASK in {s.get("uuid") for s in wf["steps"]}


def test_a_rename_keeping_the_uuid_is_an_edit_not_a_loss():
    v = check_prewrite(_doc("Ask"), _doc("Approve Block"))
    assert v.ok, v.message


def test_a_rename_that_also_drops_an_argument_is_still_refused():
    v = check_prewrite(_doc("Ask"), _doc("Approve Block", note_vars='{a: "1"}'))
    assert not v.ok
    assert any("Approve Block" in p or "Ask" in p for p in v.dropped), v.dropped


def test_without_a_uuid_a_rename_is_still_a_delete_plus_an_add():
    v = check_prewrite(_doc("Ask", ask_uuid=None), _doc("Approve Block", ask_uuid=None))
    assert not v.ok
    assert any("steps[Ask]" in p for p in v.dropped), v.dropped


def test_renaming_the_trigger_step_is_an_edit_too():
    def doc(start):
        y = f"""collection: C
playbooks:
- name: P
  steps:
  - {{uuid: {U_START}, name: {start}, type: start, module: alerts, next: Note}}
  - {{uuid: {U_NOTE}, name: Note, type: set_variable, vars: {{c: "3"}}}}
"""
        res = compile_yaml(y, DB_PATH)
        assert res.ok, [e.to_dict() for e in res.errors]
        return res.fsr_json
    v = check_prewrite(doc("Start"), doc("On Alert"))
    assert v.ok, v.message


def test_a_rename_onto_a_live_name_cannot_hide_that_steps_deletion():
    """Ask (U_ASK) 'renamed' to Note while the real Note (U_NOTE) is deleted:
    mapping by uuid alone would show two Notes and the deletion vanishes."""
    y_before = f"""collection: C
playbooks:
- name: P
  steps:
  - {{uuid: {U_START}, name: Start, type: start, module: alerts, next: Ask}}
  - {{uuid: {U_ASK}, name: Ask, type: set_variable, vars: {{a: "1"}}, next: Note}}
  - {{uuid: {U_NOTE}, name: Note, type: set_variable, vars: {{c: "3"}}}}
"""
    y_after = f"""collection: C
playbooks:
- name: P
  steps:
  - {{uuid: {U_START}, name: Start, type: start, module: alerts, next: Note}}
  - {{uuid: {U_ASK}, name: Note, type: set_variable, vars: {{a: "1"}}}}
"""
    before, after = compile_yaml(y_before, DB_PATH), compile_yaml(y_after, DB_PATH)
    assert before.ok and after.ok
    v = check_prewrite(before.fsr_json, after.fsr_json)
    assert not v.ok, "the real Note's deletion must still refuse the write"
