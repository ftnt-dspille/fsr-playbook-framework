"""Guards the trace-compiler side of the default-flip parity evidence: every
sim-replayed trace fixture must build into a playbook that clears the SAME
`verify_playbook.ready_to_push` bar a hand-authored gold does — with no static
errors and no wire downgraded to a literal (repaired=0). Deterministic; the live
model-authoring rate is gathered separately (see parity_report's docstring).
"""
from __future__ import annotations

import importlib

pr = importlib.import_module("evals.parity_report")


def test_trace_built_playbooks_reach_ready_to_push():
    rows = pr.trace_rows()
    assert rows, "no trace fixtures found to verify"
    for r in rows:
        assert r["build_ok"] is True, r
        assert r["ready_to_push"] is True, r
        assert r["static_errors"] == 0, r
        assert r["repaired"] == 0, r
        assert r["wires_verified"] == r["wires_total"], r


def test_gold_baseline_does_not_regress():
    rows = pr.gold_rows()
    assert rows, "no hand-authored connector examples found"
    assert all(r["ready_to_push"] for r in rows), \
        [r for r in rows if not r["ready_to_push"]]
