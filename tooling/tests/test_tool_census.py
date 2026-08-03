"""The census decides which tools get cut, so its harvesters need a floor.

Every verdict in `tool_census` is a zero being interpreted. `never-called`,
`unreachable-in-corpus` and `needs-box` are the SAME number with opposite
conclusions, and the thing that separates them is whether the harvester
actually read the evidence. A harvester that silently parses nothing produces a
census where every tool looks unused -- which reads exactly like a successful
run recommending a large, confident, wrong cut. These pin the parse.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import tool_census as tc  # noqa: E402


def _write(tmp_path: Path, payload: dict) -> Path:
    p = tmp_path / "probe.json"
    p.write_text(json.dumps(payload))
    return p


def test_harvest_probe_reads_guard_fire_rates_shape(tmp_path):
    """`{"rows": [...]}` -- what `scripts/guard_fire_rates.py --json` writes."""
    p = _write(tmp_path, {"rows": [
        {"scenario": "build_new", "tools_called": ["find_connector", "run_op"]},
        {"scenario": "build_new", "tools_called": ["find_connector"]},
    ]})
    stats, seen = tc.harvest_probe(p)
    assert stats["find_connector"]["calls"] == 2
    assert stats["run_op"]["calls"] == 1
    assert seen == {"build_new"}


def test_harvest_probe_reads_chat_sweep_shape(tmp_path):
    """`{"scenarios": [{"runs": [{"conversation": ...}]}]}` -- the connector's
    `chat_sweep.py --out --keep-conversations`. This is the shape that carries
    the P1/P2 rows, so a regression here is what re-hides the promises the
    product leads with."""
    p = _write(tmp_path, {"scenarios": [
        {"scenario": "invest_pivot_on_source_ip", "runs": [
            {"conversation": {"tools_called": ["siem_search_ip",
                                               "search_module_records"]}},
            {"conversation": {"tools_called": ["siem_search_ip"]}},
        ]},
        {"scenario": "contain_block_c2_destination", "runs": [
            {"conversation": {"tools_called": ["find_containment_actions"]}},
        ]},
    ]})
    stats, seen = tc.harvest_probe(p)
    assert stats["siem_search_ip"]["calls"] == 2
    assert stats["find_containment_actions"]["calls"] == 1
    assert seen == {"invest_pivot_on_source_ip", "contain_block_c2_destination"}


def test_harvest_probe_survives_a_dump_with_no_conversations(tmp_path):
    """`--keep-conversations` is opt-in. A dump without it must yield NO tool
    evidence rather than a crash -- but also must not be mistaken for one that
    observed zero calls, which is why the scenario names still come back."""
    p = _write(tmp_path, {"scenarios": [
        {"scenario": "triage_summarise_alert", "runs": [{"run": 1}]},
    ]})
    stats, seen = tc.harvest_probe(p)
    assert stats == {}
    assert seen == {"triage_summarise_alert"}


@pytest.mark.parametrize("name", sorted(tc._BOX_GATED))
def test_box_gated_tools_are_real_tools(name):
    """A typo in `_BOX_GATED` is invisible: the tool simply keeps grading as
    `never-called` and stays on the cut list for the wrong reason."""
    from fsr_playbooks.llm.tools import SAFE_TOOLS
    assert name in set(SAFE_TOOLS) | tc._RUNTIME_ONLY, (
        f"{name} is in neither SAFE_TOOLS nor the runtime-only set -- either "
        "it was renamed, or it never existed")


def test_box_gated_zero_is_not_never_called(tmp_path):
    """The distinction #67 asked for: unreachable offline vs unwanted."""
    rep = tc.census(runtime=None, probe=_write(tmp_path, {"scenarios": [
        {"scenario": "invest_pivot_on_source_ip", "runs": [
            {"conversation": {"tools_called": ["siem_search_ip"]}}]},
    ]}))
    verdicts = {r["tool"]: r["verdict"] for r in rep["tools"]}
    assert verdicts["push_playbook"] == "needs-box"
    assert verdicts["push_playbook"] != "never-called"


def test_probe_scenarios_count_toward_p1p2_coverage(tmp_path):
    """The archived eval matrices contain no invest_*/contain_* rows at all.
    If the probe's scenarios did not count, every P1/P2 tool would keep
    grading `unreachable-in-corpus` even after being observed -- the census
    would never be able to report progress on the gap it exists to name."""
    probe = _write(tmp_path, {"scenarios": [
        {"scenario": "contain_block_c2_destination", "runs": [
            {"conversation": {"tools_called": ["find_containment_actions"]}}]},
    ]})
    assert tc.census(runtime=None, probe=probe)["meta"]["p1p2_covered_by_corpus"]
