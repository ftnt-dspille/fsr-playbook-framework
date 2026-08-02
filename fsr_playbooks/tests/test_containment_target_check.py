"""A compiled containment step whose target renders empty must not run (#61).

The engine has no validator for this: FortiGate's `block_ip_new` iterating an
empty target list returns all-empty outcome buckets and `status: Success` with
the ban list unchanged. `run_op` refuses that call during triage; these tests
pin the playbook-side half, which has to be carried in the artifact.
"""
from __future__ import annotations

from fsr_playbooks.agent.skill_trace import SkillTrace
from fsr_playbooks.compiler import skill_compiler as sc
from fsr_playbooks.compiler import skill_verify as sv


def _wired_containment() -> dict:
    """enrich → block, with the block's target WIRED to the enrichment output.

    `method: Quarantine Based` is the discriminator that makes `ip_addresses`
    visible; without it the catalog prunes the param away entirely.
    """
    t = SkillTrace()
    t.record_run_op("virustotal", "query_ip", {"ip": "9.9.9.9"},
                    {"attributes": {"last_analysis_stats": {"malicious": 14}},
                     "bad_ip": "6.6.6.6"}, ref_prefix="data")
    t.record_run_op("fortigate-firewall", "block_ip_new",
                    {"method": "Quarantine Based", "ip_addresses": "6.6.6.6"},
                    {"newly_blocked": ["6.6.6.6"]})
    return sv.compile_and_verify(t)


def _by_name(compiled: dict) -> dict:
    return {s["name"]: s for s in compiled["steps"]}


def test_target_check_gates_containment_on_a_non_empty_render():
    c = sc.insert_containment_target_check(_wired_containment())
    steps = _by_name(c)
    dec = steps["Containment Target Present"]
    assert dec["type"] == "decision"
    assert dec["conditions"][0]["next"] == "Block Ip New"
    assert dec["default"] == "Containment Target Empty"
    # The assertion names the wired target, not the literal discriminator.
    when = dec["conditions"][0]["when"]
    assert "vars.steps.Query_Ip.data.bad_ip" in when
    assert "Quarantine" not in when
    assert "| length) > 0" in when
    # The enrichment now flows into the check, not straight to the block.
    assert steps["Query Ip"]["next"] == "Containment Target Present"


def test_empty_branch_marks_the_reason_and_does_not_fail_the_run():
    """Stop's destination, plus a reason -- not a failure terminal. A failed run
    carries a null `error_message` far too often to be worth routing to."""
    c = sc.insert_containment_target_check(_wired_containment())
    empty = _by_name(c)["Containment Target Empty"]
    assert empty["type"] == "set_variable"
    assert empty["vars"] == {"containment_skipped": True,
                             "containment_skipped_reason": "empty_target"}


def test_check_runs_before_the_human_gate():
    """Order matters: assert the target, THEN ask. An analyst is never asked to
    approve a containment that would act on nothing."""
    c = _wired_containment()
    c = sc.insert_containment_target_check(c)
    c = sc.insert_containment_confirm(c)
    steps = _by_name(c)
    assert (steps["Containment Target Present"]["conditions"][0]["next"]
            == "Confirm Containment")
    assert steps["Confirm Containment"]["options"][0]["next"] == "Block Ip New"


def test_idempotent():
    c = sc.insert_containment_target_check(_wired_containment())
    n = len(c["steps"])
    assert len(sc.insert_containment_target_check(c)["steps"]) == n


def test_no_check_when_no_param_is_a_bare_reference():
    """Every target param is a literal -- nothing renders, so there is nothing
    to assert. Emit no decision rather than guess one."""
    t = SkillTrace()
    t.record_run_op("shodan", "host_information", {"ip": "9.9.9.9"},
                    {"org": "Acme"}, ref_prefix="")
    t.record_run_op("fortigate-firewall", "block_ip_new",
                    {"method": "Quarantine Based", "ip_addresses": "1.2.3.4"},
                    {"newly_blocked": ["1.2.3.4"]})
    c = sc.insert_containment_target_check(sv.compile_and_verify(t))
    assert not any(s["type"] == "decision" for s in c["steps"])


def test_no_check_without_containment():
    t = SkillTrace()
    t.record_run_op("virustotal", "query_ip", {"ip": "9.9.9.9"},
                    {"bad_ip": "6.6.6.6"}, ref_prefix="data")
    t.record_run_op("virustotal", "query_ip_two", {"ip": "6.6.6.6"}, {})
    c = sc.insert_containment_target_check(sv.compile_and_verify(t))
    assert not any(s["type"] == "decision" for s in c["steps"])


def test_sole_jinja_expr_rejects_mixed_and_multi_block_values():
    """Only a value that is ENTIRELY one reference is asserted: a literal mixed
    in could make the check pass while the reference itself renders empty."""
    assert sc._sole_jinja_expr("{{ vars.a }}") == "vars.a"
    assert sc._sole_jinja_expr("  {{ vars.a }}  ") == "vars.a"
    assert sc._sole_jinja_expr("ip={{ vars.a }}") is None
    assert sc._sole_jinja_expr("{{ vars.a }}{{ vars.b }}") is None
    assert sc._sole_jinja_expr("9.9.9.9") is None
    assert sc._sole_jinja_expr(["{{ vars.a }}"]) is None
