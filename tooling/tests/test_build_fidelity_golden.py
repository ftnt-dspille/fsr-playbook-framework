"""B4 — frozen golden pin for the live-proven triage→build chain.

`python/tests/fixtures/build_goldens/b4_triage_build.json` is a FROZEN capture of
a real, known-good live run (connector 0.3.126, session `loop-f279bdb5`,
2026-06-07) — the run that proved `grounding 1.0` after muting the
`siem_events_for_incident` / `_siem_pubv2_query` internal `execute_api_request`
fan-out (commit `f7d0845`).

This replays that capture through the SAME offline scorer the live loop uses
(`scoring.score_build_fidelity`) and pins the contract: the built playbook
automates exactly the investigated ops + the staged action, with ZERO raw
`fortinet-fortisiem.execute_api_request` pollution.

SCOPE (per Chat Intelligence Plan A4/A6 fast-vs-live split): this is the
FAST/STRUCTURE guard. It pins the *scoring contract* against a real transcript
— it reddens if an edit to `score_build_fidelity`, `transcript_to_trace`, or
`_ops_from_yaml` breaks the verdict that was true live. It does NOT re-drive the
agent, so a *recorder/compiler* regression that reintroduces the fan-out is
caught by the `test_mute_recording_*` unit tests + a live re-drive, not here.
Green here means "the contract is intact", not "the agent still behaves".
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
for p in (REPO_ROOT / "tooling", REPO_ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from evals import scoring  # noqa: E402

FIXTURE = (Path(__file__).resolve().parent / "fixtures" / "build_goldens"
           / "b4_triage_build.json")


def _load() -> tuple[list[dict], set[tuple[str, str]], dict]:
    data = json.loads(FIXTURE.read_text())
    trace = data["trace"]
    built = scoring._ops_from_yaml(data["built_yaml"])
    fidelity = scoring.score_build_fidelity(trace, "", built_ops=built)
    return trace, built, fidelity


def test_b4_golden_scores_full_build_fidelity():
    """The frozen live capture still clears the build_fidelity gate end-to-end."""
    _, _, fidelity = _load()
    assert fidelity["skipped"] is False
    assert fidelity["passed"] is True
    assert fidelity["grounding"] == 1.0
    assert fidelity["action_coverage"] == 1.0
    assert fidelity["ungrounded_ops"] == []
    assert fidelity["missing_actions"] == []


def test_b4_golden_built_playbook_has_no_raw_execute_api_request():
    """The whole point of the mute fix: the siem_events_for_incident fan-out must
    NOT surface as raw `execute_api_request` steps in the built playbook."""
    _, built, _ = _load()
    assert built, "fixture lost its built-playbook ops"
    assert ("fortinet-fortisiem", "execute_api_request") not in built
    assert all(op != "execute_api_request" for _, op in built)


def test_b4_golden_built_ops_are_the_investigated_named_ops():
    """The built playbook automates the named investigation ops + the staged
    containment — a concrete pin on WHAT it built, not just the score."""
    _, built, _ = _load()
    assert built == {
        ("virustotal", "query_ip"),
        ("ip-quality-score", "get_ip_reputation"),
        ("fortinet-fortiguard-ioc", "ioc_search"),
        ("fortigate-firewall", "block_ip_new"),
    }
