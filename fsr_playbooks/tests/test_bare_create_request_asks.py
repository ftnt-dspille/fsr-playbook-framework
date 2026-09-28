"""A turn waiting on the analyst gets no forced draft and no Save card.

Live: "I want to create a new playbook." The model ran get_step_type x2, find,
validate_yaml and verify_playbook on an empty start -> end draft, and closed
with "Tell me what it should do". CreateDeliveryGuard saw a passing verify and
no offer, and forced a Save-as-Playbook card for a playbook that did nothing.

The guards read STRUCTURE, never wording: whether the model asked through a
choice card, whether the draft has any action steps, and whether a playbook is
open. None of these tests parse the analyst's message or the model's prose.
"""
from __future__ import annotations

import pytest

from fsr_playbooks.llm._loop_helpers import BuildProgressGuard, CreateDeliveryGuard
from fsr_playbooks.mcp_server._shared import reset_grounded_yaml, set_grounded_yaml
from fsr_playbooks.mcp_server.tools_emit import _offer_from_yaml

BUILD_SLICE = {"emit_card", "verify_playbook", "validate_yaml",
               "get_step_type", "find"}

EMPTY = """playbooks:
  - name: test1
    steps:
      - {name: Start, type: start, next: End}
      - {name: End, type: end}
"""

DOES_SOMETHING = """playbooks:
  - name: test1
    steps:
      - {name: Start, type: start, next: Note}
      - {name: Note, type: set_variable, vars: {note: ok}}
"""

ASK = ("emit_card", {"card_type": "choice",
                     "payload": {"prompt": "What should this playbook do?"}})
PASS = {"ok": True, "ready_to_push": True}


@pytest.fixture
def open_playbook():
    tok = set_grounded_yaml(EMPTY)
    yield
    reset_grounded_yaml(tok)


def _replay_screenshot_turn(guard):
    """The live turn's tool sequence, ending in a passing verify of EMPTY."""
    guard.note_result("get_step_type", {"name": "start"}, {"ok": True})
    guard.note_result("get_step_type", {"name": "end"}, {"ok": True})
    guard.note_result("find", {"kind": "example"}, {"ok": True})
    guard.note_result("validate_yaml", {"yaml_text": EMPTY}, {"ok": True})
    guard.note_result("verify_playbook", {"yaml_text": EMPTY}, PASS)


def test_screenshot_turn_forces_no_card():
    g = CreateDeliveryGuard()
    _replay_screenshot_turn(g)
    assert g.outstanding(BUILD_SLICE) is None


def test_create_delivery_still_forces_a_stalled_real_build():
    g = CreateDeliveryGuard()
    g.note_result("verify_playbook", {"yaml_text": DOES_SOMETHING}, PASS)
    assert g.outstanding(BUILD_SLICE) == DOES_SOMETHING


def test_a_later_real_draft_is_still_forced_after_an_empty_one():
    g = CreateDeliveryGuard()
    g.note_result("verify_playbook", {"yaml_text": EMPTY}, PASS)
    g.note_result("verify_playbook", {"yaml_text": DOES_SOMETHING}, PASS)
    assert g.outstanding(BUILD_SLICE) == DOES_SOMETHING


def test_asking_through_a_choice_card_stops_the_forced_offer():
    g = CreateDeliveryGuard()
    g.note_result("verify_playbook", {"yaml_text": DOES_SOMETHING}, PASS)
    g.note_result(*ASK, {"ok": True})
    assert g.outstanding(BUILD_SLICE) is None


def test_open_playbook_never_gets_a_forced_playbook_offer(open_playbook):
    # The right card there is enhancement_offer, which EnhanceDeliveryGuard owns.
    g = CreateDeliveryGuard()
    g.note_result("verify_playbook", {"yaml_text": DOES_SOMETHING}, PASS)
    assert g.outstanding(BUILD_SLICE) is None


def _researched() -> BuildProgressGuard:
    g = BuildProgressGuard()
    g.note_result("get_step_type", {"name": "start"}, {"ok": True})
    return g


def test_build_progress_still_nudges_a_real_stall():
    assert _researched().outstanding(BUILD_SLICE)


def test_build_progress_lets_the_model_ask():
    g = _researched()
    g.note_result(*ASK, {"ok": True})
    assert not g.outstanding(BUILD_SLICE)


def test_unverified_draft_lets_the_model_ask():
    g = BuildProgressGuard()
    g.note_result("validate_yaml", {"yaml_text": DOES_SOMETHING}, {"ok": True})
    assert g.unverified_draft(BUILD_SLICE)
    g.note_result(*ASK, {"ok": True})
    assert not g.unverified_draft(BUILD_SLICE)


def test_the_legacy_choice_tool_name_counts_as_asking():
    g = _researched()
    g.note_result("emit_choice_card", {"prompt": "What should it do?"}, {"ok": True})
    assert not g.outstanding(BUILD_SLICE)


def _offer(yaml_text):
    return _offer_from_yaml("c1", "save it", yaml_text,
                            title_suggestion=None, editable_title=True)


def test_offer_of_a_start_end_playbook_is_refused():
    res = _offer(EMPTY)
    assert res["ok"] is False
    assert res["code"] == "offer_has_no_actions"


def test_offer_of_a_playbook_that_does_something_is_made():
    assert _offer(DOES_SOMETHING)["ok"] is True
