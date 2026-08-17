"""Consolidated-tool calls score as their constituents (Phase 1 shim).

Every name-keyed scorer (terminal tools, decoys, offer timing,
delivered_yaml) predates `find`/`picklist`/`connector_health`/`emit_card`.
`canonicalize_trace` rewrites those calls back to the constituent names, so a
model that adopts the consolidated surface cannot read as "never called
emit_playbook_offer". The literal maps here must track the tool modules --
the parity tests pin that.
"""
from __future__ import annotations

from evals.scoring import (
    _CARD_TYPE_TO_TOOL,
    _FIND_KIND_TO_TOOL,
    canonicalize_trace,
    delivered_yaml,
)


def test_emit_card_scores_as_its_constituent():
    trace = [{"name": "emit_card",
              "args": {"card_type": "playbook_offer",
                       "payload": {"id": "p1", "summary": "s",
                                   "yaml": "steps: []"}}}]
    [c] = canonicalize_trace(trace)
    assert c["name"] == "emit_playbook_offer" and c["via"] == "emit_card"
    assert c["args"]["yaml"] == "steps: []"
    # And the yaml-bearing scorer sees the delivered playbook through it.
    assert delivered_yaml("", canonicalize_trace(trace)) == "steps: []"


def test_find_kinds_map_to_the_old_names():
    trace = [
        {"name": "find", "args": {"kind": "connector", "query": "fortigate"}},
        {"name": "find", "args": {"kind": "action", "action_type": "record"}},
        {"name": "find", "args": {"kind": "action"}},
        {"name": "find", "args": {"kind": "example", "connector": "x"}},
        {"name": "find", "args": {"kind": "example"}},
    ]
    names = [c["name"] for c in canonicalize_trace(trace)]
    assert names == ["find_connector", "find_record_actions",
                     "find_containment_actions", "find_operation_example",
                     "search_api_examples"]


def test_picklist_modes_map_to_the_old_names():
    trace = [
        {"name": "picklist", "args": {}},
        {"name": "picklist", "args": {"name": "Severity"}},
        {"name": "picklist", "args": {"module": "alerts", "field": "status"}},
        {"name": "picklist", "args": {"name": "Severity", "value": "High"}},
        {"name": "connector_health", "args": {"name": "fortinet-fortigate"}},
    ]
    names = [c["name"] for c in canonicalize_trace(trace)]
    assert names == ["list_picklists", "get_picklist", "picklist_for_field",
                     "resolve_picklist_value", "healthcheck_connector"]


def test_unconsolidated_calls_pass_through_untouched():
    trace = [{"name": "run_op", "args": {"connector": "x", "op": "y"}},
             {"name": "find", "args": {"kind": "frobnicate"}}]
    out = canonicalize_trace(trace)
    assert out[0] == trace[0]
    assert out[1]["name"] == "find" and "via" not in out[1]


def test_card_map_tracks_the_tool_module():
    from fsr_playbooks.mcp_server.tools_emit import CARD_TYPES
    assert _CARD_TYPE_TO_TOOL == CARD_TYPES


def test_find_map_tracks_the_tool_module():
    from fsr_playbooks.mcp_server.tools_find import FIND_KINDS
    covered = set(_FIND_KIND_TO_TOOL) | {"action", "example"}
    assert covered == set(FIND_KINDS)


def test_retired_names_stay_dispatchable_but_unadvertised():
    from fsr_playbooks.llm.tools import (
        CONSOLIDATED_AWAY,
        REGISTRY,
        anthropic_tools,
    )
    advertised = {t["name"] for t in anthropic_tools()}
    for name in CONSOLIDATED_AWAY:
        assert name in REGISTRY, f"{name} left the registry -- resumes break"
        assert name not in advertised, f"{name} is still advertised"
    for name in ("find", "picklist", "connector_health", "emit_card"):
        assert name in advertised
