"""Wiring-resolution eval dimension (SKILL_BASED_PLAYBOOK_PLAN §4, Phase 5).

Guards that the deterministic trace-compiled wiring fully resolves: every
value-matched wire verifies and no static undefined/unreachable ref
survives. Informational in `score()` so it doesn't perturb the
hand-author baseline during the parity campaign.
"""
from __future__ import annotations

import importlib

scoring = importlib.import_module("evals.scoring")

from fsr_playbooks.agent.skill_trace import SkillTrace


def _good_trace_json():
    t = SkillTrace()
    t.record_run_op(
        "virustotal", "get_ip_report", {"ip": "203.0.113.77"},
        {"attributes": {"network": "203.0.113.0/24"}}, ref_prefix="data",
    )
    t.record_run_op(
        "fortiedr", "isolate_host", {"host": "203.0.113.0/24"}, {"status": "ok"},
    )
    return t.to_json()


def test_all_wires_resolve_passes():
    lv = scoring.score_wiring_resolution(_good_trace_json())
    assert lv["passed"] is True
    assert lv["skipped"] is False
    assert lv["unresolved_wires"] == []


def test_empty_trace_is_skipped():
    lv = scoring.score_wiring_resolution(SkillTrace().to_json())
    assert lv["skipped"] is True


def test_score_includes_informational_wiring_level():
    out = scoring.score("", skill_trace_json=_good_trace_json())
    wr = out["levels"]["wiring_resolves"]
    assert wr["informational"] is True
    assert wr["passed"] is True
    # Informational → excluded from the pass/fail aggregate.
    assert "wiring_resolves" not in {
        k for k, v in out["levels"].items()
        if not v.get("skipped") and not v.get("informational")
    }


def test_score_skips_wiring_when_no_trace():
    out = scoring.score("", skill_trace_json=None)
    assert out["levels"]["wiring_resolves"]["skipped"] is True
