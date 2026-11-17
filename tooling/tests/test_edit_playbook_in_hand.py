"""Editing the playbook this conversation built, when nothing is open.

Live (build sweep, "build, then refine twice"): refining an unsaved draft had
no open playbook, so edit_playbook was refused and the model re-typed the
whole draft -- it dropped the incident's alert link, rewrote the escalation
condition, and said "everything else is unchanged". A host now grounds the
conversation's draft (or the playbook it saved) and says which via
`set_grounded_source`. An edit to a draft comes back as the draft's next
Create card; an edit to a saved playbook is an ordinary enhancement_offer; a
differently named new playbook is not blocked by either.
"""
from __future__ import annotations

import pytest

from fsr_playbooks.mcp_server._shared import (
    reset_grounded_source,
    reset_grounded_yaml,
    set_grounded_source,
    set_grounded_yaml,
)
from fsr_playbooks.mcp_server.tools_emit import emit_card
from fsr_playbooks.mcp_server.tools_enhancement import edit_playbook

DRAFT = """collection: Escalations
playbooks:
  - name: Escalated Alert to Incident
    steps:
      - name: Start
        type: start
        next: Set Source
      - name: Set Source
        type: set_variable
        vars: {source: auto}
        next: Mark
      - name: Mark
        type: set_variable
        vars: {link: "{{ vars.input.records[0]['@id'] }}"}
"""

OTHER = """collection: Phishing
playbooks:
  - name: Phishing Triage
    steps:
      - name: Start
        type: start
        next: Note
      - name: Note
        type: set_variable
        vars: {seen: "1"}
"""


@pytest.fixture
def in_hand(request):
    tokens = []

    def bind(source, yaml_text=DRAFT):
        tokens.append((set_grounded_yaml(yaml_text), set_grounded_source(source)))
    yield bind
    for g, s in reversed(tokens):
        reset_grounded_source(s)
        reset_grounded_yaml(g)


def _edit():
    res = edit_playbook(operations=[{
        "op": "add_step", "after": "Mark",
        "step": {"name": "Notified", "type": "set_variable",
                 "vars": {"notified": "true"}}}])
    assert res.get("verified_id"), res
    return res


def test_an_edit_to_a_draft_is_delivered_as_a_create_card(in_hand):
    in_hand("draft")
    res = _edit()
    out = emit_card("enhancement_offer", {
        "id": "esc", "summary": "added Notified",
        "verified_id": res["verified_id"]})
    assert out.get("ok") is True, out
    card = out["card"]
    assert card["type"] == "playbook_offer"
    # untouched fields survive byte-for-byte: the link the re-type lost
    assert "vars.input.records[0]['@id']" in card["final_yaml"]
    assert "Notified" in card["final_yaml"]


def test_an_edit_to_a_saved_playbook_stays_an_enhancement(in_hand):
    in_hand("saved")
    res = _edit()
    out = emit_card("enhancement_offer", {
        "id": "esc", "summary": "added Notified",
        "verified_id": res["verified_id"]})
    assert out["card"]["type"] == "enhancement_offer"
    assert out["card"]["steps_added"] == ["Notified"]


@pytest.mark.parametrize("source", ["draft", "saved"])
def test_a_differently_named_new_playbook_is_not_blocked(in_hand, source):
    in_hand(source)
    out = emit_card("playbook_offer", {"id": "pt", "summary": "s",
                                       "yaml": OTHER})
    assert out.get("ok") is True, out


@pytest.mark.parametrize("source", ["draft", "saved"])
def test_retyping_the_same_playbook_is_pointed_at_edit_playbook(in_hand, source):
    in_hand(source)
    retyped = DRAFT.replace('vars: {source: auto}', 'vars: {source: manual}')
    out = emit_card("playbook_offer", {"id": "esc", "summary": "s",
                                       "yaml": retyped})
    assert out.get("code") == "playbook_already_open", out
    assert "edit_playbook" in out["message"]


def test_an_open_playbook_still_blocks_a_new_one(in_hand):
    """Unchanged: with a playbook OPEN in the designer, a new offer is refused
    (that question is still the designer's, not this change's)."""
    in_hand(None)
    out = emit_card("playbook_offer", {"id": "pt", "summary": "s",
                                       "yaml": OTHER})
    assert out.get("ok") is False
