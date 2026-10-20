"""plan_playbook grounds a whole intended build in one read-only pass.

It collapses the per-step find + get_op_schema round-trips into a single call
and surfaces an unknown connector or wrong operation BEFORE authoring, not at
verify. These tests pin the verdicts, the registration (tier 0, build slice,
not triage) and that it reaches the catalog in one call.
"""
from __future__ import annotations

from fsr_playbooks.mcp_server import plan_playbook as _pp

plan_playbook = getattr(_pp, "fn", _pp)


def _by_purpose(res, purpose):
    return next(s for s in res["steps"] if s["purpose"] == purpose)


def test_mixed_plan_grounds_every_step_and_reports_gaps():
    res = plan_playbook(
        steps=[
            {"purpose": "trigger", "type": "start_on_create", "module": "alerts"},
            {"purpose": "reputation", "type": "connector",
             "connector": "virustotal", "operation": "analysis_file"},
            {"purpose": "isolate", "type": "connector",
             "connector": "crowdstrike_edr", "operation": "isolate_host"},
            {"purpose": "route", "type": "decizion"},
            {"purpose": "bad op", "type": "connector",
             "connector": "virustotal", "operation": "does_not_exist"},
        ],
        requirements=["email soc-leads"],
    )
    assert res["ok"] is True
    assert res["ready_to_build"] is False
    # Requirements are echoed so later checks can map each to a step.
    assert res["requirements"] == ["email soc-leads"]

    assert _by_purpose(res, "trigger")["status"] == "ok"
    assert _by_purpose(res, "reputation")["status"] == "ok"

    miss = _by_purpose(res, "isolate")
    assert miss["status"] == "unknown_connector"
    assert "crowdstrike" in (miss.get("suggestion") or "").lower()

    bad_type = _by_purpose(res, "route")
    assert bad_type["status"] == "unknown_step_type"
    assert "decision" in bad_type.get("near", [])  # the near list points the way

    bad_op = _by_purpose(res, "bad op")
    assert bad_op["status"] == "unknown_operation"

    # gaps is exactly the non-ok steps.
    assert {g["purpose"] for g in res["gaps"]} == {"isolate", "route", "bad op"}


def test_resolved_op_carries_output_fields_signal():
    res = plan_playbook(steps=[
        {"purpose": "vt", "type": "connector",
         "connector": "virustotal", "operation": "analysis_file"}])
    step = res["steps"][0]
    assert step["status"] == "ok"
    # For a resolved op the verdict says whether a real run's output is recorded,
    # so the next step knows whether it can bind a grounded path.
    assert "output_recorded" in step["resolved"]


def test_unknown_module_is_only_a_truly_absent_module():
    # An existing module whose fields are not warmed still resolves (fields fill
    # from a box warm); only a name the catalog never saw is a gap.
    ok = plan_playbook(steps=[{"purpose": "a", "type": "start_on_create",
                               "module": "alerts"}])["steps"][0]
    assert ok["status"] == "ok"
    gap = plan_playbook(steps=[{"purpose": "b", "type": "start_on_create",
                                "module": "no_such_module_xyz"}])["steps"][0]
    assert gap["status"] == "unknown_module"


def test_empty_steps_is_a_clear_error_not_a_crash():
    assert plan_playbook(steps=[])["code"] == "no_steps"


def test_registered_tier0_build_only_not_triage():
    from fsr_playbooks.llm import intents, tools
    assert "plan_playbook" in tools.SAFE_TOOLS
    assert tools.TOOL_TIERS["plan_playbook"] == 0  # read-only, no approval
    assert "plan_playbook" in intents.BUILD_ONLY_TOOLS
    build = {t["name"] for t in intents.tools_for_intent("build")}
    triage = {t["name"] for t in intents.tools_for_intent("triage")}
    assert "plan_playbook" in build
    assert "plan_playbook" not in triage
