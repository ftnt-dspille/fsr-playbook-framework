"""B4 — triage→build fidelity scorer (Chat Intelligence Plan).

`scoring.score_build_fidelity` grades whether a built playbook automates what
the investigation actually did: every connector op in the playbook must be one
the trace exercised (grounding), and the staged response action must appear as
a step (action_coverage). These are pure, offline, deterministic checks — they
belong in `make chat-fast`.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
for p in (REPO_ROOT / "tooling", REPO_ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from evals import scoring  # noqa: E402
from evals.levers import lever_for  # noqa: E402

# An investigation that enriched an IP via two TI ops and staged a firewall
# block as the response action.
TRACE = [
    {"name": "get_record", "args": {"module": "alerts", "uuid": "x"}, "ok": True},
    {"name": "run_op", "args": {"connector": "virustotal", "op": "query_ip",
                                "params": {"ip": "203.0.113.5"}}, "ok": True},
    {"name": "run_op", "args": {"connector": "shodan", "op": "search_ip",
                                "params": {"ip": "203.0.113.5"}}, "ok": True},
    {"name": "emit_action_card", "args": {"connector": "fortigate-firewall",
                                          "operation": "block_ip_new"}, "ok": True},
]


def _pb(*conn_ops: tuple[str, str]) -> str:
    steps = ["      - name: Start\n        type: start\n        next: s0"]
    for i, (conn, op) in enumerate(conn_ops):
        steps.append(
            f"      - name: s{i}\n        type: connector\n"
            f"        arguments:\n          connector: {conn}\n"
            f"          operation: {op}\n          params: {{}}")
    body = "\n".join(steps)
    return f"playbooks:\n  - name: Auto Respond\n    steps:\n{body}\n"


def test_grounded_playbook_with_action_passes():
    yaml = _pb(("virustotal", "query_ip"), ("fortigate-firewall", "block_ip_new"))
    r = scoring.score_build_fidelity(TRACE, yaml)
    assert not r["skipped"] and r["passed"], r
    assert r["grounding"] == 1.0 and r["action_coverage"] == 1.0


def test_invented_op_fails_grounding():
    # `disable_user` was never run during the investigation.
    yaml = _pb(("fortigate-firewall", "block_ip_new"), ("activedirectory", "disable_user"))
    r = scoring.score_build_fidelity(TRACE, yaml)
    assert not r["passed"] and r["grounding"] < 1.0
    assert "activedirectory.disable_user" in r["ungrounded_ops"]


def test_missing_staged_action_fails_coverage():
    # Playbook only re-runs enrichment; never automates the staged block.
    yaml = _pb(("virustotal", "query_ip"), ("shodan", "search_ip"))
    r = scoring.score_build_fidelity(TRACE, yaml)
    assert not r["passed"]
    assert "fortigate-firewall.block_ip_new" in r["missing_actions"]


def test_skips_when_no_playbook_or_no_ops():
    assert scoring.score_build_fidelity(TRACE, "")["skipped"]
    assert scoring.score_build_fidelity([], _pb(("x", "y")))["skipped"]


def test_score_counts_fidelity_in_build_mode_only():
    yaml = _pb(("virustotal", "query_ip"), ("fortigate-firewall", "block_ip_new"))
    build = scoring.score(yaml, trace=TRACE, final_text="```yaml\n```")
    lv = build["levels"].get("build_fidelity", {})
    assert not lv.get("skipped") and lv.get("passed"), lv
    # Investigation mode never grades fidelity (no playbook expected there).
    inv = scoring.score(yaml, mode="investigation", trace=TRACE,
                        required_facts=[{"any": ["x"]}], forbidden_facts=[])
    assert inv["levels"]["build_fidelity"]["skipped"]


def test_build_fidelity_has_a_lever():
    assert lever_for("build_fidelity") != lever_for("__nope__")


# ── offer-card path (triage→build chain) ────────────────────────────────

OFFER_CARD = {
    "type": "playbook_offer",
    "ops_summary": [
        {"connector": "virustotal", "operation": "query_ip", "verified": True},
        {"connector": "fortigate-firewall", "operation": "block_ip_new",
         "verified": True},
    ],
}


def test_ops_from_offer_card_reads_connector_operation():
    ops = scoring.ops_from_offer_card(OFFER_CARD)
    assert ("virustotal", "query_ip") in ops
    assert ("fortigate-firewall", "block_ip_new") in ops
    assert scoring.ops_from_offer_card(None) == set()


def test_built_ops_param_grades_chain_without_yaml():
    built = scoring.ops_from_offer_card(OFFER_CARD)
    r = scoring.score_build_fidelity(TRACE, "", built_ops=built)
    assert not r["skipped"] and r["passed"], r


def test_chat_drive_attaches_fidelity_from_offer_card():
    from evals.chat_drive import attach_build_fidelity
    result = {"trace": TRACE, "transcript": [{"type": "text", "text": "hi"}, OFFER_CARD]}
    score = attach_build_fidelity(None, result)
    assert score is not None
    lv = score["levels"]["build_fidelity"]
    assert not lv["skipped"] and lv["passed"], lv


def test_chat_drive_no_offer_card_is_noop():
    from evals.chat_drive import attach_build_fidelity
    result = {"trace": TRACE, "transcript": [{"type": "text", "text": "no offer"}]}
    assert attach_build_fidelity(None, result) is None
