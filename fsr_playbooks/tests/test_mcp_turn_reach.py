"""The discovery tools say which native-MCP servers a turn can reach.

`list_configured_connectors` and `find(enrichment)` list connectors only. With
TI reachable through FortiSIEM's MCP server and no TI connector, the model read
"FortiSIEM is not set up" off them, and the enrichment lookup told it to report
a capability gap -- it called a C2 beacon 'suspicious'.
"""
from __future__ import annotations

import pytest

from fsr_playbooks.mcp_server import materializer
from fsr_playbooks.mcp_server.tools_connector_discovery import annotate_mcp_reach


@pytest.fixture
def reach():
    token = materializer.set_turn_mcp_tools([
        "mcp_fortisiem__get_reputation_by_entity",
        "mcp_fortisiem__get_incidents_by_entity",
        "mcp_soc__get_alert",
        "get_record",          # not MCP: ignored
    ])
    yield
    materializer._TURN_MCP_TOOLS.reset(token)


def test_reach_groups_the_turns_mcp_tools_by_server(reach):
    assert materializer.turn_mcp_reach() == [
        {"server": "fortisiem",
         "tools": ["get_incidents_by_entity", "get_reputation_by_entity"]},
        {"server": "soc", "tools": ["get_alert"]},
    ]


def test_a_listing_carries_the_reach(reach):
    out = annotate_mcp_reach({"configured": []})
    assert [r["server"] for r in out["native_mcp"]] == ["fortisiem", "soc"]
    assert "not connectors" in out["native_mcp_note"]


def test_an_empty_lookup_is_not_a_gap_when_mcp_is_in_reach(reach):
    out = annotate_mcp_reach(
        {"actions": [], "suggested_card": {"type": "capability_gap"},
         "message": "call emit_capability_gap_card"}, lookup_empty=True)
    assert "suggested_card" not in out
    assert "before reporting a gap" in out["message"]


def test_no_mcp_reach_leaves_the_result_alone():
    before = {"actions": [], "suggested_card": {"x": 1}, "message": "gap"}
    assert annotate_mcp_reach(dict(before), lookup_empty=True) == before
