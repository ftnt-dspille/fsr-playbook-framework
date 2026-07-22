"""Triage discipline guards (fsr_playbooks.llm._loop_helpers.TriageDiscipline).

Model-agnostic structural enforcement layered on raw tool dispatch so a weak
model (gpt-4o-mini) can't shortcut a terse triage to
  get_record -> find_containment_actions -> emit_action_card
with no investigation, can't enrich an internal IP against external TI, and
can't re-call a one-shot discovery tool. Pure + offline.
"""
from __future__ import annotations

import pytest

from fsr_playbooks.llm._loop_helpers import (
    MIN_INVESTIGATION_BEFORE_CONTAINMENT,
    TriageDiscipline,
)

# Import the helper function to test (using direct import from the module)
# to avoid issues with private function visibility
try:
    from fsr_playbooks.llm.anthropic_provider import _is_error_result
except ImportError:
    # If not available in anthropic provider, it might be in another module
    _is_error_result = None


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


# ─────────────────── authoring/build exemption ───────────────────

def test_authoring_exempts_containment_discovery_from_floor():
    """In build/authoring the hunt-floor gate must NOT block
    find_containment_actions / find_enrichment_actions DISCOVERY — there is no
    live alert to investigate, and the build agent legitimately uses them to
    learn which ops exist (e.g. which connector op blocks an IP)."""
    d = TriageDiscipline(authoring=True)
    # Zero investigation done, yet discovery is allowed immediately.
    assert d.invest_attempts == 0
    assert _drive(d, "find_containment_actions", {"target_type": "ip"}) is None
    assert _drive(d, "find_enrichment_actions", {"target_type": "ip"}) is None


def test_authoring_still_gates_emit_action_card():
    """Belt-and-suspenders: even in authoring the actual STAGING tool stays
    floor-gated. It should never be in a build slice, but if it leaks in, the
    exemption is discovery-only — staging is still blocked."""
    d = TriageDiscipline(authoring=True)
    g = _drive(d, "emit_action_card", {})
    assert g is not None and g["hunt_floor_guard"] is True


def test_triage_default_still_gates_containment_discovery():
    """Regression: authoring defaults False, so triage is byte-unchanged —
    find_containment_actions is still floor-gated before investigation."""
    d = TriageDiscipline()  # authoring defaults False
    g = _drive(d, "find_containment_actions", {})
    assert g is not None and g["hunt_floor_guard"] is True


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


def test_call_once_is_per_target_type():
    """Regression: the call-once guard is scoped by target_type. These tools
    filter their result set by indicator type, so a call for `domain` and a
    call for `ip` are DISTINCT and both legitimate — only a repeat of the SAME
    target_type is a wasteful duplicate. (Live-observed: a triage that scoped
    find_containment_actions to `ip` then `endpoint` was wrongly blocked.)"""
    d = TriageDiscipline()
    # Two different indicator types → both allowed.
    assert _drive(d, "find_enrichment_actions", {"target_type": "domain"}) is None
    assert _drive(d, "find_enrichment_actions", {"target_type": "ip"}) is None
    # A repeat of an already-seen target_type → blocked.
    g = _drive(d, "find_enrichment_actions", {"target_type": "ip"})
    assert g is not None and g["call_once_guard"] is True

    # Same for containment (past the hunt floor).
    d2 = TriageDiscipline()
    for _ in range(MIN_INVESTIGATION_BEFORE_CONTAINMENT):
        _drive(d2, "run_op", {"connector": "virustotal", "params": {"ip": "8.8.8.8"}})
    assert _drive(d2, "find_containment_actions", {"target_type": "ip"}) is None
    assert _drive(d2, "find_containment_actions", {"target_type": "endpoint"}) is None
    g2 = _drive(d2, "find_containment_actions", {"target_type": "ip"})
    assert g2 is not None and g2["call_once_guard"] is True


def test_build_tools_unaffected():
    """Discipline fires only on triage tool names; build flows are untouched."""
    d = TriageDiscipline()
    for name in ("compile_yaml", "validate_yaml", "push_playbook", "get_op_schema"):
        assert d.evaluate(name, {}) is None


# ─────────────── P2: guard seeding + state mutation ────────────────

def test_guard_rejection_carries_kind_guard_redirect():
    """All three discipline rejections carry kind='guard_redirect' (design item 6)."""
    # 1. Hunt floor guard
    d = TriageDiscipline()
    g = d.evaluate("find_containment_actions", {})
    assert g is not None
    assert g.get("kind") == "guard_redirect"
    assert g.get("hunt_floor_guard") is True

    # 2. Forbidden pivot guard
    d2 = TriageDiscipline()
    g2 = d2.evaluate("run_op", {"connector": "virustotal", "params": {"ip": "10.0.0.1"}})
    assert g2 is not None
    assert g2.get("kind") == "guard_redirect"
    assert g2.get("forbidden_pivot_guard") is True

    # 3. Call-once guard
    d3 = TriageDiscipline()
    _drive(d3, "find_enrichment_actions", {})
    g3 = _drive(d3, "find_enrichment_actions", {})
    assert g3 is not None
    assert g3.get("kind") == "guard_redirect"
    assert g3.get("call_once_guard") is True


def test_seeded_discipline_floor_already_met():
    """When state.hunt_floor_met=True, the floor check is permanently satisfied (design item 3)."""
    from fsr_playbooks.agent.case_state import Investigation

    # Create a state where floor is already met
    state = Investigation(
        invest_attempts=MIN_INVESTIGATION_BEFORE_CONTAINMENT,
        hunt_floor_met=True,
    )

    # Create discipline seeded from state
    d = TriageDiscipline(state=state)

    # containment should NOT be blocked even on a fresh turn
    assert d.evaluate("find_containment_actions", {}) is None
    assert d.evaluate("emit_action_card", {}) is None


def test_seeded_discipline_counters_from_state():
    """When state is provided, invest_attempts and called_once_sigs are seeded (design item 3)."""
    from fsr_playbooks.agent.case_state import Investigation

    # Create state with prior progress
    state = Investigation(
        invest_attempts=2,
        called_once_sigs=["find_enrichment_actions\x00domain"],
    )

    d = TriageDiscipline(state=state)

    # invest_attempts should be seeded
    assert d.invest_attempts == 2

    # called_once_sigs should be seeded; a repeat of the same target_type is blocked
    g = d.evaluate("find_enrichment_actions", {"target_type": "domain"})
    assert g is not None and g.get("call_once_guard") is True

    # but a different target_type is allowed
    assert d.evaluate("find_enrichment_actions", {"target_type": "ip"}) is None


def test_discipline_mutates_shared_state():
    """As the turn progresses, the shared Investigation object is mutated (design item 3)."""
    from fsr_playbooks.agent.case_state import Investigation

    state = Investigation()
    d = TriageDiscipline(state=state)

    # Initially empty
    assert state.invest_attempts == 0
    assert len(state.called_once_sigs) == 0

    # Run some investigation tools
    d.evaluate("search_module_records", {"module": "alerts", "query": "host1"})
    d.evaluate("run_op", {"connector": "virustotal", "params": {"ip": "8.8.8.8"}})

    # Shared state should be mutated
    assert state.invest_attempts == 2
    assert "search_module_records" in state.called_once_sigs
    assert "run_op" in state.called_once_sigs

    # Run a call-once discovery tool
    d.evaluate("find_enrichment_actions", {"target_type": "domain"})

    # call_once_sig should be added
    sig = "find_enrichment_actions\x00domain"
    assert sig in state.called_once_sigs


def test_discipline_marks_hunt_floor_met_in_state():
    """When hunt floor is met, the shared state.hunt_floor_met is set to True (design item 3)."""
    from fsr_playbooks.agent.case_state import Investigation

    state = Investigation()
    d = TriageDiscipline(state=state)

    # Run investigation tools to meet the floor
    for _ in range(MIN_INVESTIGATION_BEFORE_CONTAINMENT):
        d.evaluate("search_module_records", {"module": "alerts", "query": "host"})

    # The shared state should now have hunt_floor_met=True
    assert state.hunt_floor_met is True

    # And subsequent containment calls should not be blocked
    assert d.evaluate("find_containment_actions", {}) is None


def test_no_state_behavior_unchanged():
    """Backward compat: when no state is provided, behavior is identical to before."""
    d = TriageDiscipline()  # No state parameter

    # Floor blocking works
    g = d.evaluate("find_containment_actions", {})
    assert g is not None and g["hunt_floor_guard"] is True

    # Forbidden pivot works
    g2 = d.evaluate("run_op", {"connector": "virustotal", "params": {"ip": "10.0.0.1"}})
    assert g2 is not None and g2["forbidden_pivot_guard"] is True

    # Call-once works
    d2 = TriageDiscipline()
    d2.evaluate("find_enrichment_actions", {})
    g3 = d2.evaluate("find_enrichment_actions", {})
    assert g3 is not None and g3["call_once_guard"] is True


# ──────────── provider rendering: guard_redirect is not is_error ─────────

@pytest.mark.skipif(_is_error_result is None, reason="_is_error_result not available")
def test_is_error_result_guards_not_errors():
    """Provider does NOT flag guard_redirect results as is_error (design item 6).

    Guard redirects are steering, not errors — they should be rendered
    as info-tone steering, not red errors.
    """
    # Regular errors are marked is_error
    assert _is_error_result({"ok": False, "error": "something failed"}) is True
    assert _is_error_result({"error": "missing resource"}) is True

    # Guard-redirect results are NOT marked is_error
    assert _is_error_result({
        "ok": False,
        "kind": "guard_redirect",
        "hunt_floor_guard": True,
        "error": "Do not call yet",
    }) is False

    assert _is_error_result({
        "ok": False,
        "kind": "guard_redirect",
        "forbidden_pivot_guard": True,
        "error": "Skipped: external TI on internal IP",
    }) is False

    assert _is_error_result({
        "ok": False,
        "kind": "guard_redirect",
        "call_once_guard": True,
        "error": "STOP calling this tool",
    }) is False

    # Non-dict results are not errors
    assert _is_error_result("just a string") is False
    assert _is_error_result(None) is False
    assert _is_error_result([]) is False


# ───────────────────── capability facts (§E / spine P3) ─────────────────────

def _caps():
    from fsr_playbooks.agent.case_state import Capabilities
    return Capabilities()


def test_capability_guard_short_circuits_known_unavailable():
    """A run_op against a connector already recorded unavailable is blocked
    with a guard_redirect — no live re-probe (design item 4)."""
    caps = _caps()
    caps.unavailable["whois-rdap"] = "connector_not_configured"
    d = TriageDiscipline(capabilities=caps)
    g = d.evaluate("run_op", {"connector": "whois-rdap", "op": "whois_ip"})
    assert g is not None
    assert g["kind"] == "guard_redirect"
    assert g.get("capability_guard") is True
    assert g["connector"] == "whois-rdap"
    assert "NOT re-attempted" in g["error"]


def test_capability_guard_other_connectors_unaffected():
    caps = _caps()
    caps.unavailable["whois-rdap"] = "connector_unhealthy"
    d = TriageDiscipline(capabilities=caps)
    assert d.evaluate("run_op", {"connector": "virustotal", "op": "ip_report"}) is None


def test_note_result_records_not_configured():
    """A connector_not_configured failure is learned; the second attempt
    short-circuits (the §E live-observed defect)."""
    caps = _caps()
    d = TriageDiscipline(capabilities=caps)
    args = {"connector": "whois-rdap", "op": "whois_ip"}
    assert d.evaluate("run_op", args) is None
    d.note_result("run_op", args, {
        "ok": False, "code": "connector_not_configured", "message": "x"})
    assert caps.unavailable == {"whois-rdap": "connector_not_configured"}
    assert caps.noted_at is not None
    g = d.evaluate("run_op", args)
    assert g is not None and g.get("capability_guard") is True


def test_note_result_records_unhealthy():
    caps = _caps()
    d = TriageDiscipline(capabilities=caps)
    d.note_result("run_op", {"connector": "fortisiem"}, {
        "ok": False, "code": "connector_unhealthy", "message": "x"})
    assert caps.unavailable == {"fortisiem": "connector_unhealthy"}


def test_note_result_success_confirms_and_clears():
    """A successful run_op confirms the connector and clears a stale
    unavailable entry (fixed mid-session)."""
    caps = _caps()
    caps.unavailable["virustotal"] = "connector_unhealthy"
    d = TriageDiscipline(capabilities=caps)
    d.note_result("run_op", {"connector": "virustotal"}, {"ok": True, "data": {}})
    assert "virustotal" not in caps.unavailable
    assert caps.confirmed == ["virustotal"]


def test_recheck_clears_unavailable():
    """list_configured_connectors success clears ALL unavailable entries —
    the capability-gap 'Re-check & continue' gesture (design item 4)."""
    caps = _caps()
    caps.unavailable.update({
        "whois-rdap": "connector_not_configured",
        "fortisiem": "connector_unhealthy",
    })
    d = TriageDiscipline(capabilities=caps)
    d.note_result("list_configured_connectors", {}, {"ok": True, "connectors": []})
    assert caps.unavailable == {}
    # and the previously-blocked call now proceeds
    assert d.evaluate("run_op", {"connector": "whois-rdap", "op": "x"}) is None


def test_note_result_other_failures_not_recorded():
    """Ordinary op failures (bad params, upstream 400s) are NOT capability facts."""
    caps = _caps()
    d = TriageDiscipline(capabilities=caps)
    d.note_result("run_op", {"connector": "virustotal"}, {
        "ok": False, "code": "op_failed", "message": "400"})
    assert caps.unavailable == {}


def test_no_capabilities_note_result_noop():
    """Without capabilities state, note_result is a safe no-op (backward compat)."""
    d = TriageDiscipline()
    d.note_result("run_op", {"connector": "x"}, {
        "ok": False, "code": "connector_not_configured"})
    assert d.evaluate("run_op", {"connector": "x"}) is None


# ───────────── hunt floor credits the connector's hunt families ─────────────

def test_fmg_faz_hunt_tools_credit_the_floor():
    """Regression (GA beat-5): an investigation driven entirely through the
    connector-registered FortiManager/FortiAnalyzer hunt tools scored **0 of 3**
    evidence calls, so the analyst's follow-up "isolate that host" was refused
    as un-scoped and the assistant never staged containment. Those names were
    never in the framework's hardcoded evidence list; the family prefixes are
    the structural fix."""
    d = TriageDiscipline()
    for name in ("fmg_get_device_status", "fmg_get_ha_status",
                 "faz_search_device_events"):
        assert _drive(d, name, {}) is None
    assert d.invest_attempts == MIN_INVESTIGATION_BEFORE_CONTAINMENT
    # Floor met → containment discovery is allowed.
    assert _drive(d, "find_containment_actions", {"target_type": "host"}) is None


def test_credit_as_investigation_registers_extra_names():
    from fsr_playbooks.llm import _loop_helpers as lh
    assert not lh.counts_as_investigation("edr_list_processes")
    lh.credit_as_investigation("edr_list_processes")
    try:
        assert lh.counts_as_investigation("edr_list_processes")
    finally:
        lh._INVESTIGATION_TOOLS.discard("edr_list_processes")


# ───────── destructive-op-name fail-safe for the approval tier ─────────

def test_containment_verb_in_op_name_escalates_tier():
    """Regression (GA beat-5): FortiEDR's `isolate_collector` is categorized
    `investigation` in the catalog and had NO op_safety verdict on the live box,
    so it resolved to tier 2 — `run_op` would have isolated a host with no
    approval card, and find_containment_actions dropped it from the tier>=3
    slice. The op name is the fail-safe signal."""
    from fsr_playbooks.llm.tools import _op_name_is_destructive, _tier_for_run_op

    assert _op_name_is_destructive("isolate_collector")
    assert _op_name_is_destructive("block_ip")
    assert _op_name_is_destructive("quarantine_file")
    # Un-doing containment and every read prefix stay non-destructive.
    assert not _op_name_is_destructive("unisolate_collector")
    assert not _op_name_is_destructive("get_blocked_ip")
    assert not _op_name_is_destructive("list_quarantined_files")
    assert not _op_name_is_destructive("ip_reputation")

    # An unclassified op whose name says "isolate" must require approval.
    assert _tier_for_run_op(
        {"connector": "fortinet-fortiedr", "op": "isolate_collector"}) >= 3
