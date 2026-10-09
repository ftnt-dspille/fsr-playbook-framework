"""The analyst's "Modify this playbook / Create new playbook" answer is what
authorizes removing steps they never named, or a second playbook while one is
open. Structural (a bound session answer), never a parse of their wording."""
import pytest

pytest.importorskip("mcp.server.fastmcp", reason="mcp package not installed")

from fsr_playbooks.llm.turn_plan import TurnContext, plan_turn  # noqa: E402
from fsr_playbooks.mcp_server._shared import (  # noqa: E402
    SCOPE_CREATE_NEW,
    SCOPE_MODIFY,
    reset_playbook_scope,
    set_playbook_scope,
)
from fsr_playbooks.mcp_server.tools_enhancement import verify_enhancement  # noqa: E402

BEFORE = """collection: C
playbooks:
- name: test
  steps:
  - {name: Start, type: start, module: alerts, next: Placeholder}
  - {name: Placeholder, type: set_variable, vars: {a: 1}}
"""
AFTER = """collection: C
playbooks:
- name: test
  steps:
  - {name: Start, type: start, module: alerts, next: Stash}
  - {name: Stash, type: set_variable, vars: {ip: '{{ vars.input.records[0].sourceIp }}'}}
"""


def _drop_kinds(res):
    return [r["kind"] for r in res.get("regressions") or [] if r.get("step") == "Placeholder"]


def test_an_unnamed_step_removal_blocks_and_names_the_scope_choice():
    res = verify_enhancement(BEFORE, AFTER, user_message="create a playbook for malware alerts")
    assert _drop_kinds(res) == ["step_dropped"] and not res["ready_to_push"]
    msg = next(r["message"] for r in res["regressions"] if r["kind"] == "step_dropped")
    assert '"id": "playbook_scope"' in msg and "Modify this playbook" in msg


def test_modify_answer_authorizes_the_removal():
    tok = set_playbook_scope(SCOPE_MODIFY)
    try:
        res = verify_enhancement(BEFORE, AFTER, user_message="create a playbook for malware alerts")
    finally:
        reset_playbook_scope(tok)
    assert _drop_kinds(res) == ["step_deleted_as_requested"]
    assert res["ready_to_push"], res.get("required_fixes")
    assert res["acknowledged_drops"] == ["Placeholder"]


def test_create_new_answer_affords_a_second_playbook():
    plan = plan_turn("build", context=TurnContext(has_open_playbook=True))
    card = {"card_type": "playbook_offer"}
    assert plan.gate_refusal("emit_card", card)["code"] == "not_afforded"
    tok = set_playbook_scope(SCOPE_CREATE_NEW)
    try:
        assert plan.gate_refusal("emit_card", card) is None
    finally:
        reset_playbook_scope(tok)
