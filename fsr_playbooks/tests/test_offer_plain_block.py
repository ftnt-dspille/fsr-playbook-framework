"""A YAML offer carries an honest mutating flag and a deterministic `plain` block.

The flag used to be hard-coded False for every hand-built YAML offer, so a
Block-IP playbook (connector step `block_ip_new`) read as read-only. The
`plain` block is built from the same YAML: 3 to 5 "what it does" sentences,
whether it changes things, whether it asks to confirm, and a capped summary.
"""
from __future__ import annotations

from fsr_playbooks.mcp_server.tools_emit import (
    _offer_from_yaml,
    _plain_block,
    _yaml_has_destructive_op,
)

BLOCK_IP = """
collection: C
playbooks:
  - name: Block Malicious IP on FortiGate
    steps:
      - name: Start
        type: start
        next: Containment Target Present
      - name: Containment Target Present
        type: decision
        conditions:
          - display: target present
            when: "{{ vars.input.records[0].destinationIp | length > 0 }}"
            next: Confirm Containment
        default: Containment Skipped
      - name: Confirm Containment
        type: manual_input
        message: "Run containment? Choose Stop to skip it."
        options:
          - display: Confirm
            next: Block IP on FortiGate
          - display: Stop
            next: Containment Skipped
      - name: Block IP on FortiGate
        type: connector
        connector: fortigate-firewall
        operation: block_ip_new
        method: Quarantine Based
        ip_addresses: "{{ vars.input.records[0].destinationIp }}"
        time_to_live: 12 Hour
        next: Containment Skipped
      - name: Containment Skipped
        type: set_variable
        vars: {containment_skipped: "true"}
"""

READ_ONLY = """
collection: C
playbooks:
  - name: Enrich Source
    steps:
      - name: Start
        type: start
        next: Look Up Source
      - name: Look Up Source
        type: connector
        connector: fortinet-fortisiem
        operation: search_events
        next: Done
      - name: Done
        type: end
"""


def _offer(yaml_text: str) -> dict:
    return _offer_from_yaml("c1", "Blocks the destination IP on FortiGate.", yaml_text,
                            title_suggestion=None, editable_title=True)


def test_block_ip_yaml_is_flagged_mutating():
    # Red without the fix: _offer_from_yaml hard-coded has_mutating_action False.
    assert _yaml_has_destructive_op(BLOCK_IP) is True
    res = _offer(BLOCK_IP)
    assert res["ok"] is True, res
    assert res["card"]["has_mutating_action"] is True


def test_read_only_yaml_is_not_flagged():
    assert _yaml_has_destructive_op(READ_ONLY) is False


def test_plain_block_for_block_ip():
    plain = _plain_block(BLOCK_IP, "Blocks the destination IP on FortiGate.", True)
    assert plain is not None
    assert 3 <= len(plain["steps"]) <= 5, plain["steps"]
    assert plain["changes"] is True
    assert plain["asks_confirm"] is True
    # Humanized decision wording, no raw field label, no tool or field token.
    joined = " ".join(plain["steps"])
    assert "Containment Target Present" not in joined
    assert "containment target present" in joined
    assert "block_ip_new" not in joined and "_" not in joined
    assert plain["summary"] == "Blocks the destination IP on FortiGate."


def test_plain_block_for_read_only():
    plain = _plain_block(READ_ONLY, "Looks up the source.", False)
    assert plain["changes"] is False
    assert plain["asks_confirm"] is False
    assert 1 <= len(plain["steps"]) <= 5


def test_plain_block_rides_on_the_offer_card():
    card = _offer(BLOCK_IP)["card"]
    assert card["plain"]["changes"] is True
    assert card["plain"]["asks_confirm"] is True


def test_plain_summary_is_capped_and_drops_tokens():
    long = "Blocks the destination IP. " + ("It also checks the record. " * 40)
    plain = _plain_block(BLOCK_IP, long, True)
    assert len(plain["summary"]) <= 200
    bad = _plain_block(BLOCK_IP, "Runs block_ip_new on the sourceIp field.", True)
    assert "block_ip_new" not in bad["summary"] and "sourceIp" not in bad["summary"]
