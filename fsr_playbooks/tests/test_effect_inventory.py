"""The effect inventory: what a playbook writes, and where the values come from.

A playbook can compile perfectly clean and still carry out no effect, or write a
verdict it never computed. These pin the inventory that surfaces both -- the
static half of effect verification (the runtime half is the box-run reading the
written field back).
"""
from __future__ import annotations

import pytest

from fsr_playbooks.compiler import parse_yaml
from fsr_playbooks.compiler.effect_inventory import (
    effect_inventory,
    unlinked_effects,
)


def _coll(yaml_text: str):
    coll, errs = parse_yaml(yaml_text)
    assert coll is not None, errs
    return coll


# An enrichment-then-write playbook: VT enriches, the verdict is written back
# into the alert. The write's value references the VT step -- linked.
_LINKED = """
collection: C
playbooks:
  - name: P
    steps:
      - {name: Start, type: start_on_create, module: alerts, next: VT}
      - name: VT
        type: connector
        connector: virustotal
        operation: query_ip
        params: {ip: "{{ vars.input.records[0].sourceIp }}"}
        next: Write
      - name: Write
        type: update_record
        module: alerts
        record: "{{ vars.input.records[0] }}"
        resource:
          comments: "verdict {{ vars.steps.VT.data.attributes.reputation }}"
          name: "triaged"
        next: Done
      - {name: Done, type: end}
"""

# Same shape but the verdict field is a literal -- the enrichment is dropped.
_UNLINKED = _LINKED.replace(
    'comments: "verdict {{ vars.steps.VT.data.attributes.reputation }}"',
    'comments: "verdict malicious"')

# A pure-triage playbook: enriches and ends, no write, no action.
_NO_EFFECT = """
collection: C
playbooks:
  - name: P
    steps:
      - {name: Start, type: start_on_create, module: alerts, next: VT}
      - name: VT
        type: connector
        connector: virustotal
        operation: query_ip
        params: {ip: "{{ vars.input.records[0].sourceIp }}"}
        next: Done
      - {name: Done, type: end}
"""


def test_a_record_write_is_inventoried_with_its_module_and_fields():
    inv = effect_inventory(_coll(_LINKED))
    writes = [e for e in inv if e["kind"] == "record_write"]
    assert len(writes) == 1
    w = writes[0]
    assert w["module"] == "alerts"
    assert w["mutating"] is True
    assert set(w["writes"]) == {"comments", "name"}


def test_a_written_value_is_linked_to_its_upstream_step():
    inv = effect_inventory(_coll(_LINKED))
    w = next(e for e in inv if e["kind"] == "record_write")
    # the verdict field carries the VT enrichment forward
    assert w["writes"]["comments"] == ["VT"]
    # the literal field carries nothing
    assert w["writes"]["name"] == []
    assert w["sources"] == ["VT"]
    assert unlinked_effects(inv) == []


def test_a_verdict_written_as_a_literal_is_flagged_unlinked():
    inv = effect_inventory(_coll(_UNLINKED))
    w = next(e for e in inv if e["kind"] == "record_write")
    assert w["sources"] == []            # nothing carried forward
    flagged = unlinked_effects(inv)
    assert len(flagged) == 1 and flagged[0]["step"] == "Write"


def test_a_pure_triage_playbook_has_no_effect():
    # No record write; the only connector op (query_ip) has no safety fact
    # here, so it stays as a potential action, not a proven effect.
    inv = effect_inventory(_coll(_NO_EFFECT))
    assert [e for e in inv if e["kind"] == "record_write"] == []


def test_op_safety_classifies_connector_actions():
    # A connector step whose op the catalog marks mutating is an effect; a
    # safe (read) op is dropped from the inventory.
    def safety(conn: str, op: str) -> str:
        return {"block_ip": "unsafe", "query_ip": "safe"}.get(op, "unknown")

    inv = effect_inventory(_coll(_NO_EFFECT), op_safety=safety)
    # query_ip is safe -> not an effect
    assert inv == []

    block = _NO_EFFECT.replace("operation: query_ip", "operation: block_ip")
    inv2 = effect_inventory(_coll(block), op_safety=safety)
    acts = [e for e in inv2 if e["kind"] == "connector_action"]
    assert len(acts) == 1
    assert acts[0]["mutating"] is True
    assert acts[0]["operation"] == "block_ip"
    assert acts[0]["sources"] == []   # params read trigger input, not a step


# --- verify_playbook wiring -------------------------------------------------

@pytest.fixture
def verify():
    pytest.importorskip("mcp.server.fastmcp", reason="mcp package not installed")
    from fsr_playbooks.mcp_server.tools_verify import verify_playbook
    return verify_playbook


def test_verify_surfaces_the_effect_inventory_as_evidence(verify):
    r = verify(_LINKED)
    effects = r["evidence"].get("effects")
    assert effects, "expected an effect inventory in evidence"
    w = next(e for e in effects if e["kind"] == "record_write")
    assert w["module"] == "alerts" and w["writes"]["comments"] == ["VT"]


def test_verify_warns_when_a_verdict_is_written_as_a_literal(verify):
    r = verify(_UNLINKED)
    codes = [w["code"] for w in r.get("warnings") or []]
    assert "effect_value_unlinked" in codes
    # a warning, never a blocker
    assert "effect_value_unlinked" not in [f["code"] for f in r["required_fixes"]]


def test_verify_can_suppress_effect_nudges(verify):
    r = verify(_UNLINKED, disable_checks=["effect"])
    codes = [w["code"] for w in r.get("warnings") or []]
    assert "effect_value_unlinked" not in codes
    assert r["suppressed_count"] >= 1
