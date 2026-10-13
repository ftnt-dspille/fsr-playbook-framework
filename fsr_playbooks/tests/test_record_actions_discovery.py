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


# ---- the persona's record-write tools are the one way ----------------------
#
# Live (Frank, ka_policy_would_close_fp): asked how to close an alert, this
# offered only cyops_utilities ops, never the host's update_record. The model
# either staged a cyops_utilities write -- no before/after card, no picklist
# check, and an autonomy rule naming update_record never matches it -- or,
# where it read cyops_utilities as missing, gave up with a capability gap.

class _Persona:
    def __init__(self, may_write=(), tools_allow=()):
        self.may_write = list(may_write)
        self.tools_allow = list(tools_allow)

    def may_write_module(self, module):
        return module in self.may_write


@pytest.fixture
def persona():
    from fsr_playbooks.llm import session_state
    tokens = []

    def bind(**kw):
        tokens.append(session_state.update(profile=_Persona(**kw)))
    yield bind
    for t in reversed(tokens):
        session_state.reset(t)


def test_a_persona_that_writes_the_module_gets_its_own_tools(offline_box, persona):
    persona(may_write=["alerts"], tools_allow=["update_record", "create_record"])
    got = _actions(find_record_actions(module="alerts", uuid="54f25f1f"))
    upd = got["update_field"]
    assert upd["tool"] == "update_record" and "connector" not in upd
    assert upd["args"] == {"module": "alerts", "uuid": "54f25f1f",
                           "fields": {"<field>": "<new value>"}}
    assert upd["requires_approval"] is True and "IRI" in upd["notes"]
    assert got["create_record"]["tool"] == "create_record"
    assert got["create_record"]["args"]["module"] == "alerts"
    # No tool for comments: that one stays the connector op (when the store
    # knows the comments link field; see the comment tests above).
    if "comment" in got:
        assert got["comment"]["connector"] == "cyops_utilities"


def test_a_single_tool_action_needs_no_connector(offline_box, persona, monkeypatch):
    persona(may_write=["alerts"], tools_allow=["update_record"])
    monkeypatch.setattr(offline_box, "list_configured_connectors",
                        lambda **_kw: {"configured": []})
    out = find_record_actions(action="update_field", module="alerts", uuid="u1")
    assert [a["tool"] for a in out["actions"]] == ["update_record"]
    assert "message" not in out


@pytest.mark.parametrize("kw", [
    {},                                                     # no write scope
    {"may_write": ["incidents"], "tools_allow": ["update_record"]},  # other module
    {"may_write": ["alerts"], "tools_allow": ["get_record"]},        # tool not offered
])
def test_without_the_tool_for_this_module_the_connector_op_stays(offline_box, persona, kw):
    persona(**kw)
    got = _actions(find_record_actions(module="alerts", uuid="54f25f1f"))
    assert got["update_field"]["connector"] == "cyops_utilities"
    assert "tool" not in got["update_field"]


def test_no_persona_keeps_the_connector_ops(offline_box):
    got = _actions(find_record_actions(module="alerts", uuid="54f25f1f"))
    assert got["update_field"]["op"] == "update_cyops_resource"


def test_find_keeps_the_tool_call_on_its_compact_row(offline_box, persona):
    """`find` trims rows to what the next call needs; a tool row's next call
    is the tool and its args."""
    from fsr_playbooks.mcp_server.tools_find import _compact_action
    persona(may_write=["alerts"], tools_allow=["update_record"])
    out = find_record_actions(action="update_field", module="alerts", uuid="u1")
    row = _compact_action({**out["actions"][0], "action_type": "record"})
    assert row["tool"] == "update_record"
    assert row["args"]["uuid"] == "u1"
