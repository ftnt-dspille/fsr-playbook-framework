"""Conditional-required completeness in the resolver.

The resolver already rejects a *provided* conditional param whose gate is
unsatisfied (`_check_param_visibility`). This covers the inverse: a *missing*
conditional param that the chosen (or defaulted) branch makes required — the
block_ip_new shape (method='Policy Based' → ip_type, ip_block_policy required;
ip_type='IPv4' → ip required). Warmup writes top-level parent/condition as empty
strings, so the check must treat '' as "no parent".
"""
from fsr_core.compiler.errors import CompileError
from fsr_core.compiler.resolver import Resolver


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
