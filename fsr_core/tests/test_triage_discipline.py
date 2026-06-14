"""Triage discipline guards (fsr_core.llm._loop_helpers.TriageDiscipline).

Model-agnostic structural enforcement layered on raw tool dispatch so a weak
model (gpt-4o-mini) can't shortcut a terse triage to
  get_record -> find_containment_actions -> emit_action_card
with no investigation, can't enrich an internal IP against external TI, and
can't re-call a one-shot discovery tool. Pure + offline.
"""
from __future__ import annotations

from fsr_core.llm._loop_helpers import (
    MIN_INVESTIGATION_BEFORE_CONTAINMENT,
    TriageDiscipline,
)


def _drive(d: TriageDiscipline, name: str, args: dict | None = None):
    """Mimic _guarded_dispatch: atomic check-and-record."""
    return d.evaluate(name, args or {})


# ───────────────────────── hunt floor ─────────────────────────

def test_containment_blocked_before_floor():
    d = TriageDiscipline()
    # The terse shortcut: pull the record, then immediately try to stage.
    assert _drive(d, "get_record", {"uuid": "abc"}) is None
    g = _drive(d, "find_containment_actions", {})
    assert g is not None and g["hunt_floor_guard"] is True
    assert g["investigation_calls"] == 0  # get_record doesn't count
    # emit_action_card is gated too.
    g2 = _drive(d, "emit_action_card", {})
    assert g2 is not None and g2["hunt_floor_guard"] is True


def test_containment_allowed_after_floor():
    d = TriageDiscipline()
    _drive(d, "get_record", {"uuid": "abc"})
    _drive(d, "search_module_records", {"module": "alerts", "query": "host1"})
    _drive(d, "search_module_records", {"module": "incidents", "query": "host1"})
    _drive(d, "run_op", {"connector": "virustotal", "op": "ip",
                         "params": {"ip": "8.8.8.8"}})
    assert d.invest_attempts == MIN_INVESTIGATION_BEFORE_CONTAINMENT
    assert _drive(d, "find_containment_actions", {}) is None
    assert _drive(d, "emit_action_card", {}) is None


def test_failed_investigation_attempts_still_count():
    """Attempts, not successes — a config gap can't deadlock the floor."""
    d = TriageDiscipline()
    for _ in range(MIN_INVESTIGATION_BEFORE_CONTAINMENT):
        _drive(d, "siem_search_ip", {"ip": "1.2.3.4"})
    assert _drive(d, "emit_action_card", {}) is None


# ───────────────────── forbidden TI pivot ─────────────────────

def test_internal_ip_ti_pivot_blocked():
    d = TriageDiscipline()
    g = d.evaluate("run_op", {"connector": "virustotal", "op": "ip",
                           "params": {"ip": "192.168.77.49"}})
    assert g is not None and g["forbidden_pivot_guard"] is True


def test_external_ip_ti_pivot_allowed():
    d = TriageDiscipline()
    assert d.evaluate("run_op", {"connector": "virustotal", "op": "ip",
                              "params": {"ip": "102.220.160.21"}}) is None


def test_mixed_ips_ti_pivot_allowed():
    """When a public IP is also present, it's a legit external lookup."""
    d = TriageDiscipline()
    assert d.evaluate("run_op", {"connector": "shodan", "op": "ip",
                              "params": {"ip": "8.8.8.8", "ctx": "192.168.1.1"}}) is None


def test_internal_ip_non_ti_connector_allowed():
    d = TriageDiscipline()
    # get_ip_context / SIEM pivots on internal IPs are exactly what we WANT.
    assert d.evaluate("run_op", {"connector": "fortinet-fortisiem", "op": "ctx",
                              "params": {"ip": "192.168.1.1"}}) is None


# ───────────────────── call-once discovery ─────────────────────

def test_find_containment_actions_call_once():
    d = TriageDiscipline()
    # Meet the floor so the call-once guard (not the floor) is what fires.
    for _ in range(MIN_INVESTIGATION_BEFORE_CONTAINMENT):
        _drive(d, "run_op", {"connector": "virustotal", "params": {"ip": "8.8.8.8"}})
    assert _drive(d, "find_containment_actions", {}) is None
    g = _drive(d, "find_containment_actions", {})
    assert g is not None and g["call_once_guard"] is True


def test_find_enrichment_actions_call_once():
    d = TriageDiscipline()
    assert _drive(d, "find_enrichment_actions", {}) is None
    g = _drive(d, "find_enrichment_actions", {})
    assert g is not None and g["call_once_guard"] is True


def test_build_tools_unaffected():
    """Discipline fires only on triage tool names; build flows are untouched."""
    d = TriageDiscipline()
    for name in ("compile_yaml", "validate_yaml", "push_playbook", "get_op_schema"):
        assert d.evaluate(name, {}) is None
