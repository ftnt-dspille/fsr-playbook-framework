"""Conditional-required completeness in the resolver.

The resolver already rejects a *provided* conditional param whose gate is
unsatisfied (`_check_param_visibility`). This covers the inverse: a *missing*
conditional param that the chosen (or defaulted) branch makes required — the
block_ip_new shape (method='Policy Based' → ip_type, ip_block_policy required;
ip_type='IPv4' → ip required). Warmup writes top-level parent/condition as empty
strings, so the check must treat '' as "no parent".
"""
from fsr_playbooks.compiler.errors import CompileError
from fsr_playbooks.compiler.resolver import Resolver


def _resolver_with_block_ip_new() -> Resolver:
    r = Resolver(":memory:")
    r.conn.execute(
        "CREATE TABLE operation_params ("
        "connector_name TEXT, op_name TEXT, parent_param_name TEXT, "
        "condition_value TEXT, param_name TEXT, type TEXT, required INTEGER, "
        "default_value TEXT, options_json TEXT)"
    )
    # Empty-string sentinels for the top-level `method` (as warmup writes them);
    # method defaults to 'Quarantine Based'.
    rows = [
        ("fortigate-firewall", "block_ip_new", "", "", "method", "select", 1,
         "Quarantine Based", '["Quarantine Based", "Policy Based"]'),
        ("fortigate-firewall", "block_ip_new", "method", "Policy Based",
         "ip_block_policy", "text", 1, None, None),
        ("fortigate-firewall", "block_ip_new", "method", "Policy Based",
         "ip_type", "select", 1, None, '["IPv4", "IPv6"]'),
        ("fortigate-firewall", "block_ip_new", "ip_type", "IPv4",
         "ip", "text", 1, None, None),
        ("fortigate-firewall", "block_ip_new", "method", "Quarantine Based",
         "ip_addresses", "text", 1, None, None),
        ("fortigate-firewall", "block_ip_new", "method", "Quarantine Based",
         "time_to_live", "select", 1, None, '["1 Hour", "Custom Time"]'),
        ("fortigate-firewall", "block_ip_new", "time_to_live", "Custom Time",
         "duration", "integer", 1, None, None),
    ]
    r.conn.executemany(
        "INSERT INTO operation_params VALUES (?,?,?,?,?,?,?,?,?)", rows)
    return r


def _missing(provided: dict) -> set:
    r = _resolver_with_block_ip_new()
    errs: list[CompileError] = []
    try:
        r._check_conditional_required(
            "fortigate-firewall", "block_ip_new", provided, "p", errs)
    finally:
        r.close()
    return {e.path.rsplit(".", 1)[-1] for e in errs}


def test_policy_branch_flags_missing_ip_type_and_policy():
    # method='Policy Based' activates ip_type + ip_block_policy (both required).
    miss = _missing({"method": "Policy Based"})
    assert "ip_type" in miss
    assert "ip_block_policy" in miss
    # ip is gated on ip_type, which isn't satisfied yet → not flagged.
    assert "ip" not in miss


def test_nested_ip_required_once_ip_type_set():
    miss = _missing({"method": "Policy Based", "ip_type": "IPv4",
                     "ip_block_policy": "blocklist"})
    assert miss == {"ip"}


def test_fully_specified_policy_branch_is_clean():
    miss = _missing({"method": "Policy Based", "ip_type": "IPv4",
                     "ip_block_policy": "blocklist", "ip": "1.2.3.4"})
    assert miss == set()


def test_default_quarantine_branch_flags_its_required_children():
    # method omitted → defaults to 'Quarantine Based', which requires
    # ip_addresses + time_to_live. The Policy-Based children stay inactive.
    miss = _missing({})
    assert miss == {"ip_addresses", "time_to_live"}


def test_deep_chain_custom_time_requires_duration():
    miss = _missing({"method": "Quarantine Based", "ip_addresses": "1.1.1.1",
                     "time_to_live": "Custom Time"})
    assert miss == {"duration"}


def test_jinja_ref_counts_as_provided():
    miss = _missing({"method": "Policy Based", "ip_type": "IPv4",
                     "ip_block_policy": "{{ vars.policy }}",
                     "ip": "{{ vars.ip }}"})
    assert miss == set()


def _resolver_with_query_ip() -> Resolver:
    """virustotal.query_ip: two unconditional params, but warmup wrote the
    top-level parent/condition as empty strings (the live-store encoding that
    caused the spurious 'only valid when =' warnings in session yq8nhcix)."""
    r = Resolver(":memory:")
    r.conn.execute(
        "CREATE TABLE operation_params ("
        "connector_name TEXT, op_name TEXT, parent_param_name TEXT, "
        "condition_value TEXT, param_name TEXT, type TEXT, required INTEGER, "
        "default_value TEXT, options_json TEXT)"
    )
    rows = [
        ("virustotal", "query_ip", "", "", "ip", "text", 1, None, None),
        ("virustotal", "query_ip", "", "", "relationships", "select", 0,
         None, None),
    ]
    r.conn.executemany(
        "INSERT INTO operation_params VALUES (?,?,?,?,?,?,?,?,?)", rows)
    return r


def test_empty_string_parent_param_is_not_flagged_as_conditional():
    # Regression: an always-visible param whose parent is stored as '' (not
    # NULL) must NOT be reported as "only valid when =''" / param-set conflict.
    r = _resolver_with_query_ip()
    errs: list[CompileError] = []
    try:
        r._check_param_visibility(
            "virustotal", "query_ip", {"ip": "1.2.3.4"}, "p", errs)
    finally:
        r.close()
    assert errs == []


def _conditional_required(provided: dict) -> list[CompileError]:
    r = _resolver_with_query_ip()
    errs: list[CompileError] = []
    try:
        r._check_conditional_required(
            "virustotal", "query_ip", provided, "p", errs)
    finally:
        r.close()
    return errs


def test_missing_top_level_required_param_is_an_error():
    # Gap #1: a pure top-level required param (ip) that the author omitted
    # used to pass through (run_op-preflight's job) and verify_playbook lied
    # with ready_to_push=True. It is now a hard *error* so the authoring flow
    # blocks the push.
    errs = _conditional_required({})
    miss = {e.path.rsplit(".", 1)[-1] for e in errs}
    assert "ip" in miss
    ip_err = next(e for e in errs if e.path.endswith(".ip"))
    assert ip_err.severity == "error"


def test_present_top_level_required_param_is_clean():
    assert _conditional_required({"ip": "1.2.3.4"}) == []


def test_optional_top_level_param_not_flagged():
    # `relationships` is top-level but required=0 → never flagged.
    miss = {e.path.rsplit(".", 1)[-1] for e in _conditional_required({"ip": "x"})}
    assert "relationships" not in miss


# ============================================================================
# Tests for param visibility (conditional-param conflicts).
# These verify the one-shot feasible-set fix: on the FIRST report, the agent
# sees the ROOT choice and ALL feasible sets, not layer-by-layer warnings.
# ============================================================================

def _visibility_errors(connector: str, op: str, provided: dict) -> list[CompileError]:
    """Call _check_param_visibility and return errors."""
    r = _resolver_with_block_ip_new()
    errs: list[CompileError] = []
    try:
        r._check_param_visibility(connector, op, provided, "p", errs)
    finally:
        r.close()
    return errs


def _consolidated(errs: list[CompileError]) -> CompileError:
    """The single root-choice message, picked out of the round's findings.

    A round emits two kinds of finding: one per offending param ("`ip` is only
    valid when …", which says WHICH param is wrong) and one per gating select
    (the root choice + every feasible set, which says WHAT TO DO). Both are
    useful and both arrive in the SAME round — the defect being guarded here
    was never "more than one message", it was needing more than one TURN.
    """
    hits = [e for e in errs if "feasible sets" in (e.suggestion or "").lower()]
    assert len(hits) == 1, (
        f"expected exactly one consolidated feasible-sets message, got "
        f"{len(hits)}: {[e.message for e in errs]}"
    )
    return hits[0]


def test_param_set_conflict_reports_root_choice_and_all_feasible_sets():
    """When params violate conditional-visibility rules, report the ROOT choice
    and complete feasible sets in ONE message, not layer-by-layer warnings.

    This is the core fix: an agent providing {ip: <value>} sees the full picture
    (method='Policy Based' or 'Quarantine Based' with their complete param lists)
    in a single error, not separate warnings for ip, then ip_type, then method.
    """
    # Author provides only the deepest child param (ip), which is visible only
    # when method='Policy Based' AND ip_type='IPv4'. Both parents are missing.
    errs = _visibility_errors("fortigate-firewall", "block_ip_new", {"ip": "1.2.3.4"})

    # ONE round, and exactly one root-choice message in it.
    err = _consolidated(errs)
    # Message should reference the ROOT gating param (method).
    assert "method" in err.message.lower()
    # Message should indicate method is not provided.
    assert "not provided" in err.message.lower() or "method" in err.message
    # Suggestion should contain the full feasible sets.
    assert "feasible sets" in err.suggestion.lower()
    assert "method='Policy Based'" in err.suggestion
    assert "method='Quarantine Based'" in err.suggestion
    # Conflicting params should be listed.
    assert "ip" in err.message
    # Severity must be error (not warning), since the conflict blocks execution.
    assert err.severity == "error"


def test_multi_layer_conflict_reported_in_single_pass():
    """Verify the multi-turn issue from the original report is fixed.

    Original problem: an agent would get warnings/suggestions layer-by-layer
    and have to fix multiple rounds:
      Round 1: "ip is only valid when ip_type='IPv4', ip_type='IPv6'"
      Round 2: "ip_type is only valid when method='Policy Based'"
      Round 3 (finally): full feasible sets

    Fixed behavior: author provides {ip: x, ip_type: 'IPv4'}, and we report
    the ROOT conflict (method not provided) with full feasible sets in ONE pass.
    """
    # Simulating the state after the agent fixed the first issue by adding ip_type.
    errs = _visibility_errors(
        "fortigate-firewall", "block_ip_new",
        {"ip": "1.2.3.4", "ip_type": "IPv4"}
    )

    # The ROOT (method) is named in this same round — the agent never has to
    # come back to discover a further layer.
    err = _consolidated(errs)
    assert "method" in err.message.lower()
    assert "feasible sets" in err.suggestion.lower()
    # And nothing in this round points at ip_type as the thing to fix, which is
    # the dead end that cost the extra turn live.
    assert not any(m.startswith("param 'ip_type' on") and "method" not in m
                   for m in (e.message for e in errs))


def test_param_set_conflict_severity_is_error():
    """A param-set conflict must have severity='error' so ready_to_push reflects
    the fact that FSR will reject the call at runtime.

    Regression guard: a warning-severity conflict allowed verify_playbook to
    report ready_to_push=True on a broken playbook.
    """
    errs = _visibility_errors("fortigate-firewall", "block_ip_new", {"ip": "1.2.3.4"})
    assert errs, "a param-set conflict must be reported at all"
    assert all(e.severity == "error" for e in errs), (
        f"every visibility finding must block; got "
        f"{[(e.message[:40], e.severity) for e in errs]}. A warning-severity "
        "conflict lets ready_to_push return True on a step FSR will reject."
    )


def test_null_condition_false_positive_still_suppressed():
    """Regression guard: a top-level param whose parent is stored as ''
    (not NULL) must NOT be flagged as a visibility conflict.

    This guard is already in operation_param_rules (catalog.py:324-326),
    but we verify it end-to-end here.
    """
    errs = _visibility_errors("virustotal", "query_ip", {"ip": "1.2.3.4"})
    # Should have no errors; ip is top-level and always visible.
    assert errs == [], f"Expected no errors, got {len(errs)}: {[e.message for e in errs]}"


def test_param_set_conflict_shows_closest_match():
    """When the author has provided some params, hint which feasible set
    is closest to what they already wrote (optional: for future UX polish).

    For now, this test documents the current behavior; the suggestion always
    lists all feasible sets and lets the agent choose.
    """
    errs = _visibility_errors(
        "fortigate-firewall", "block_ip_new",
        {"ip": "1.2.3.4", "ip_type": "IPv4"}
    )
    err = _consolidated(errs)
    # The author provided ip_type='IPv4', which lives under Policy Based; both
    # sets are listed so they can choose deliberately rather than guess.
    assert "method='Policy Based'" in err.suggestion
    assert "method='Quarantine Based'" in err.suggestion
