"""find_containment_actions — configured + tier>=3 response-action discovery.

These exercise the library-owned connector-discovery surface
(`fsr_playbooks.mcp_server.tools_connector_discovery`) against the full
reference catalog. They were carved out of the SOC-triage connector suite when
`find_containment_actions` / `list_configured_connectors` moved into the library
(RECONCILIATION_PLAN D6: connector-awareness is authoring, not investigation).
"""
from __future__ import annotations

import sqlite3

import pytest

from fsr_playbooks.llm.tools import _DB_PATH
from fsr_playbooks.mcp_server import tools_connector_discovery as cd
from fsr_playbooks.mcp_server import tools_emit as tt_emit


def _has(connector: str, op: str) -> bool:
    try:
        with sqlite3.connect(f"file:{_DB_PATH}?mode=ro", uri=True) as c:
            return c.execute(
                "SELECT 1 FROM operations WHERE connector_name=? AND op_name=?",
                (connector, op)).fetchone() is not None
    except Exception:
        return False


def test_find_containment_actions_filters_to_destructive(monkeypatch):
    if not _has("fortigate-firewall", "block_ip_new"):
        pytest.skip("fortigate-firewall not in reference DB")
    # Pretend fortigate-firewall is configured + available on the box.
    monkeypatch.setattr(cd, "list_configured_connectors", lambda **k: {
        "configured": [{"name": "fortigate-firewall", "status": "Available"}],
        "probed": k.get("probe"), "count": 1})

    out = cd.find_containment_actions(target_type="ip", probe=True)
    assert out["ok"] is True
    ops = {a["op"] for a in out["actions"]}
    # real containment ops surface, every one tier>=3 + approval-gated
    assert "block_ip_new" in ops
    assert all(a["tier"] >= 3 and a["requires_approval"] for a in out["actions"])
    # read/reversal ops never show up
    assert "get_blocked_ip" not in ops and "unblock_ip" not in ops


def test_find_containment_actions_empty_when_no_response_connector(monkeypatch):
    # Intel-only configured set → no containment, with a guiding message.
    monkeypatch.setattr(cd, "list_configured_connectors", lambda **k: {
        "configured": [{"name": "virustotal", "status": "Available"},
                       {"name": "shodan", "status": "Available"}],
        "probed": k.get("probe"), "count": 2})
    out = cd.find_containment_actions(target_type="host", probe=True)
    assert out["ok"] is True and out["count"] == 0
    # never dead-ends: steers the agent to emit a capability_gap card and
    # hands it a ready-to-forward suggested_card payload.
    assert "emit_capability_gap_card" in out["message"]
    card = out.get("suggested_card")
    assert card and card["missing"] and card["why"]
    assert card["fix_steps"]  # at least one concrete step
    # resume button so the analyst can fix the gap and continue
    assert card["resume"]["value"] == "recheck_containment"
    # manual fallbacks present, values distinct from the resume value
    alt_values = {a["value"] for a in card["alternatives"]}
    assert alt_values and card["resume"]["value"] not in alt_values
    # the suggested payload must pass the emitter's own validation
    emitted = tt_emit.emit_capability_gap_card(**card)
    assert emitted["ok"] is True
    assert emitted["card"]["type"] == "capability_gap"
    assert "no containment" in out["message"].lower()


def test_find_containment_actions_rejects_bad_target():
    out = cd.find_containment_actions(target_type="banana")
    assert out["ok"] is False and out["code"] == "unknown_target_type"
