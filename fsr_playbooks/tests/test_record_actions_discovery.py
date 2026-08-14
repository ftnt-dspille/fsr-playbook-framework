"""`find_record_actions` -- the inward-facing sibling of the two shortcuts.

`find_enrichment_actions` and `find_containment_actions` skip connector
discovery for the outward-facing halves of a turn: look the indicator up, and
act on the device. The third thing an analyst always wants -- write what you
found back onto the record -- had no shortcut, and the agent paid for it.

Measured on `invest_disk_latency_no_ti` (the RESTRAINT fixture, budget 8) in
runs 20260814T111633Z and 20260814T112533Z: SEVEN of thirteen calls --
find_connector x3, find_operation x3, get_op_schema -- spent working out how to
leave a comment.

This grants no new capability. Every action it returns is tier 3+ and still has
to be staged through `emit_action_card`; it sells discovery, not permission.
"""
from __future__ import annotations

import pytest

from fsr_playbooks.mcp_server.tools_connector_discovery import (
    find_record_actions,
)


@pytest.fixture
def offline_box(monkeypatch):
    """Answer the configured-connector listing from the simulated roster.

    Patched at `list_configured_connectors` rather than at the client, because
    what this module needs from a box is one question -- is cyops_utilities
    configured -- and stubbing the answer keeps the test about the record-action
    shapes instead of about client resolution.
    """
    import fsr_playbooks.mcp_server.tools_connector_discovery as tcd
    from fsr_playbooks.mcp_server import _sim_fixtures as fx

    rows = [{"name": r["name"], "status": "Available",
             "version": r.get("version", "1.0.0")}
            for r in fx.connector_rows()]
    rows.append({"name": "cyops_utilities", "status": "Available",
                 "version": "1.0.0"})
    monkeypatch.setattr(tcd, "list_configured_connectors",
                        lambda **_kw: {"configured": rows})
    return tcd


def _actions(out):
    assert out.get("ok") is not False, out
    return {a["action"]: a for a in out.get("actions", [])}


def test_a_comment_is_a_record_in_the_comments_module(offline_box):
    """The knowledge the agent could not find.

    A comment is not a field on the alert. It is a record in `comments` whose
    `content` holds the text and whose per-module link field attaches it -- and
    the link field is read from the store, never assumed, because a comment
    that attaches to nothing is written, returned as a success, and seen by
    nobody.
    """
    got = _actions(find_record_actions(action="comment", module="alerts",
                                       uuid="54f25f1f"))
    if not got:
        pytest.skip("cyops_utilities not configured in this environment")
    body = got["comment"]["params"]["body"]
    assert got["comment"]["params"]["iri"] == "/api/3/comments"
    assert "content" in body
    assert body["alerts"] == ["/api/3/alerts/54f25f1f"]


def test_the_link_field_follows_the_TARGET_module(offline_box):
    got = _actions(find_record_actions(action="comment", module="incidents",
                                       uuid="b4a62c3b"))
    if not got:
        pytest.skip("cyops_utilities not configured in this environment")
    assert got["comment"]["params"]["body"]["incidents"] == [
        "/api/3/incidents/b4a62c3b"]


def test_every_returned_action_still_needs_approval(offline_box):
    """P2. Discovery must never become a way around the gate: these are the
    same tier-3 ops the agent could have found the long way."""
    out = find_record_actions(module="alerts")
    for a in out.get("actions", []):
        assert a["tier"] >= 3, a
        assert a["requires_approval"] is True, a
    if out.get("actions"):
        assert out["stage_with"] == "emit_action_card"


def test_the_picklist_rule_is_stated_where_it_is_needed(offline_box):
    """The other thing that is easy to get wrong: a picklist field takes the
    picklist's IRI, never its label. A write with the label is ACCEPTED and
    sets nothing."""
    got = _actions(find_record_actions(action="update_field", module="alerts"))
    if not got:
        pytest.skip("cyops_utilities not configured in this environment")
    assert "resolve_picklist_value" in got["update_field"]["notes"]


def test_a_module_that_does_not_exist_is_refused(offline_box):
    """And the guard has to actually run.

    The first version queried `modules.module_name` -- that column belongs to
    `module_fields` -- so it raised OperationalError, hit the fail-open, and
    accepted every module name ever typed. A guard that cannot fail is the
    `gate that selects zero files` shape.
    """
    out = find_record_actions(module="definitely_not_a_module")
    assert out.get("ok") is False
    assert out.get("code") == "unknown_module"


def test_an_unknown_action_names_the_valid_ones(offline_box):
    out = find_record_actions(action="delete_everything")
    assert out.get("code") == "unknown_action"
    assert "comment" in out["valid"]
