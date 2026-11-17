"""U6: the enhancement offer carries the catalog's display label for each
connector its diff names, so the card never shows a bare connector id."""
from __future__ import annotations

import pytest

pytest.importorskip(
    "mcp.server.mcpserver",
    reason="mcp package not installed; tool bodies are exercised elsewhere",
)

from fsr_playbooks.mcp_server import (  # noqa: E402
    _verified_yaml,
    emit_enhancement_offer,
    verify_enhancement,
)
from fsr_playbooks.mcp_server._citation_validator import (  # noqa: E402
    connector_labels_for,
    set_turn_connector_labels,
)

BEFORE = """collection: C
playbooks:
- name: PB
  trigger_step_id: start
  steps:
  - type: start
    name: Start
    module: alerts
    next: Lookup
  - type: connector
    name: Lookup
    connector: fortinet-fortiguard-threat-intelligence
    operation: ip_lookup
    params: {ip: '{{vars.ip}}'}
"""
AFTER = BEFORE.replace("    params: {ip: '{{vars.ip}}'}",
                       "    params: {ip: '{{vars.ip}}', verbose: true}")


@pytest.fixture(autouse=True)
def _clean():
    _verified_yaml.clear()
    set_turn_connector_labels(None)
    yield
    _verified_yaml.clear()
    set_turn_connector_labels(None)


def _offer() -> dict:
    r = verify_enhancement(BEFORE, AFTER, "add verbose")
    assert r["ready_to_push"], r.get("required_fixes")
    out = emit_enhancement_offer("o1", "Adds verbose output.", r["verified_id"])
    assert out["ok"] is True, out
    return out["card"]


def test_offer_carries_the_catalog_label_of_each_connector_it_names():
    set_turn_connector_labels({
        "fortinet-fortiguard-threat-intelligence": "FortiGuard Threat Intelligence",
        "servicenow": "ServiceNow"})
    card = _offer()
    # Only the connector the diff names; an unrelated configured one is left out.
    assert card["connector_labels"] == {
        "fortinet-fortiguard-threat-intelligence": "FortiGuard Threat Intelligence"}


def test_offer_has_no_label_map_when_the_host_reported_none():
    assert "connector_labels" not in _offer()


def test_offer_leaves_out_a_connector_the_catalog_has_no_label_for():
    set_turn_connector_labels({"servicenow": "ServiceNow"})
    assert "connector_labels" not in _offer()


def test_labels_for_ignores_blank_labels_and_dedupes():
    set_turn_connector_labels({"a": " Alpha ", "b": "", "c": "  "})
    assert connector_labels_for(["a", "a", "b", "c", "z"]) == {"a": "Alpha"}


def test_a_reader_is_called_only_when_an_offer_is_emitted():
    calls: list[int] = []

    def reader() -> dict[str, str]:
        calls.append(1)
        return {"fortinet-fortiguard-threat-intelligence": "FortiGuard Threat Intelligence"}
    set_turn_connector_labels(reader)
    assert calls == []
    assert _offer()["connector_labels"] == {
        "fortinet-fortiguard-threat-intelligence": "FortiGuard Threat Intelligence"}
    assert calls == [1]


def test_a_failing_reader_leaves_the_offer_without_labels():
    def boom() -> dict[str, str]:
        raise RuntimeError("catalog unreadable")
    set_turn_connector_labels(boom)
    assert "connector_labels" not in _offer()
    set_turn_connector_labels(lambda: None)
    assert "connector_labels" not in _offer()
