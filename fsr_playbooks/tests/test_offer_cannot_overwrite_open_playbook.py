"""`emit_playbook_offer` must not be able to delete the open playbook's work.

Measured live (session sess-n3d7p4a1 on a lab box): "Explain what this playbook
does, step by step, in plain language" -- a read-only ask -- ended at a tier-3
offer whose YAML had replaced two real hunt steps with placeholders, summarised
as "ready for deployment". The tier gate asks a human to approve an ACTION; it
does not diff two documents, so nothing on that path could see the loss.

The guard is deliberately at the TOOL, not on the turn. The read-only tool
slice is keyed on a structured `quick_action` that only the widget's chips
send -- a free-typed ask or an MCP caller arrives here with the full authoring
surface. So these tests never mention intent, wording, or classification.
"""
from __future__ import annotations

import pytest

from fsr_playbooks.mcp_server._shared import (
    reset_grounded_yaml,
    set_grounded_yaml,
)
from fsr_playbooks.mcp_server.tools_emit import _offer_from_yaml

OPEN = """
playbooks:
  - name: Hunt Indicators
    steps:
      - name: Start
        type: start
      - name: Extract Indicators from Input
        type: connector
      - name: Hunt Domains
        type: connector
      - name: Hunt Files
        type: connector
      - name: Hunt IP address
        type: connector
"""

# What the live model actually offered: the two steps whose connectors are not
# installed on this box, swapped for placeholders.
PLACEHOLDERED = OPEN.replace("name: Hunt Domains",
                             "name: Hunt Domains Placeholder") \
                    .replace("name: Hunt Files",
                             "name: Hunt Files Placeholder")


@pytest.fixture
def grounded():
    """Bind an open playbook for the duration of a test, then unbind."""
    tokens = []

    def _bind(yaml_text):
        tokens.append(set_grounded_yaml(yaml_text))

    yield _bind
    for t in reversed(tokens):
        reset_grounded_yaml(t)


def _offer(yaml_text):
    return _offer_from_yaml("card-1", "ready for deployment", yaml_text,
                            title_suggestion="Hunt Indicators",
                            editable_title=True)


def test_an_offer_that_drops_open_steps_is_refused(grounded):
    """The live failure, verbatim: placeholders in place of real hunt steps."""
    grounded(OPEN)
    out = _offer(PLACEHOLDERED)

    assert out["ok"] is False
    assert out["code"] == "offer_drops_open_steps"
    # Name the casualties, or the model cannot act on the refusal.
    assert "Hunt Domains" in out["message"]
    assert "Hunt Files" in out["message"]


def test_the_refusal_points_at_the_tool_that_would_be_correct(grounded):
    """A refusal that dead-ends the turn just becomes a retry loop."""
    grounded(OPEN)
    out = _offer(PLACEHOLDERED)
    assert any("emit_enhancement_offer" in s for s in out.get("suggestions") or [])


def test_offering_a_new_playbook_with_nothing_open_is_untouched(grounded):
    """The silencing case that matters most: the tool's real job.

    No open playbook -> a genuine new build -> the guard must be invisible.
    """
    out = _offer(OPEN)
    assert out["ok"] is True
    assert out["card"]["type"] == "playbook_offer"
    assert out["card"]["final_yaml"] == OPEN


def test_an_edit_that_keeps_every_open_step_is_still_refused_as_an_edit(grounded):
    """Adding to the open playbook loses nothing, but it is still an EDIT.

    Separate code from the loss case on purpose -- this one is a routing
    mistake, not a destructive one, and telling them apart is what lets the
    model fix it instead of guessing.
    """
    grounded(OPEN)
    out = _offer(OPEN + "      - name: Notify\n        type: connector\n")
    assert out["ok"] is False
    assert out["code"] == "playbook_already_open"


def test_an_unreadable_open_document_does_not_block(grounded):
    """Fail OPEN, not closed. If we cannot read what is open we cannot claim a
    step was lost, and refusing on a parse failure would make a broken mount
    look like a forbidden build."""
    grounded("::: not yaml :::")
    out = _offer(OPEN)
    assert out["ok"] is True


def test_a_renamed_playbook_still_counts_its_steps(grounded):
    """The guard keys on STEPS, not the playbook title -- a model that renames
    the document while dropping steps must not slip through."""
    grounded(OPEN)
    out = _offer(PLACEHOLDERED.replace("name: Hunt Indicators",
                                       "name: Hunt Indicators v2"))
    assert out["ok"] is False
    assert out["code"] == "offer_drops_open_steps"
