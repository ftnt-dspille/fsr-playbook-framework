"""calibrate must never report a bare 0.0 for a fixture it cannot score.

Every `invest_*` fixture pivots through `get_record` / `search_module_records`,
which live in the CONNECTOR's `fsr_soc_triage.registry`. Run calibrate without
them and recall is 0.0 by construction -- indistinguishable, in the summary,
from the agent having gotten worse. That misreading cost a full model sweep:
five fixtures at 0.0 across two models read as a broken corpus, and the same
fixture scored 1.0 the moment the tools were registered.

So calibrate does two things, and both are pinned here:
  1. registers the connector's triage tools when they are importable;
  2. refuses to run any fixture whose required tools are still missing.
"""
from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CALIBRATE = REPO_ROOT / "tooling" / "evals" / "calibrate_investigation.py"
TASKS = REPO_ROOT / "tooling" / "evals" / "tasks"


def test_calibrate_registers_the_connector_triage_tools() -> None:
    """It must go through the harness resolver, not its own import."""
    src = CALIBRATE.read_text()
    assert "register_triage_tools_if_available" in src, (
        "calibrate no longer registers the connector's triage tools -- every "
        "invest_* fixture will score 0.0 and read as an agent regression")


def test_calibrate_refuses_unservable_fixtures_by_default() -> None:
    src = CALIBRATE.read_text()
    assert "unservable_required_tools" in src, (
        "calibrate must ask which required tools are unregistered")
    assert "--allow-unservable" in src, (
        "the refusal needs an explicit opt-out, or someone will delete the "
        "check instead of passing a flag")
    # The refusal has to precede the model calls; scoring 5 fixtures x 3
    # repeats before saying 'unscoreable' is the expensive half of the bug.
    assert src.index("refusing to run") < src.index("asyncio.run(_run_one"), (
        "the unservable refusal must fire BEFORE any model call")


def test_every_investigation_fixture_declares_a_servable_tool_or_is_known() -> None:
    """The connector-owned tool names are exactly the two we know about.

    A NEW unregistered tool name appearing in a fixture is worth a failure
    here: it means someone added a pivot this repo can never score, and the
    next 0.0 would restart the same investigation.
    """
    connector_owned = {"get_record", "search_module_records"}
    framework_local = {"run_op", "emit_action_card", "find_operation",
                       "find_enrichment_actions", "find_containment_actions",
                       "get_op_schema", "find_connector",
                       "list_configured_connectors", "emit_choice_card",
                       "emit_capability_gap_card", "siem_search",
                       "get_event_details"}
    unknown: dict[str, set[str]] = {}
    for path in sorted(TASKS.glob("*.json")):
        data = json.loads(path.read_text())
        if data.get("mode") != "investigation":
            continue
        names = {f["tool"] for f in (data.get("required_facts") or [])
                 if f.get("tool")}
        extra = names - connector_owned - framework_local
        if extra:
            unknown[path.name] = extra
    assert not unknown, (
        f"investigation fixtures name tool(s) this test does not know: "
        f"{unknown}. If they are connector-owned, add them to the set above "
        f"AND to the unservable refusal's guidance; if they are new framework "
        f"tools, confirm they are actually registered.")


# ---- a LOST run is not a 0.0 -------------------------------------------------
# Same doctrine as the module docstring, different cause. A stream failure
# reaches calibrate as an ErrorEvent and nothing else; the turn then returns
# normally with an empty trace. Scoring that yields `recall=0.0, 0 calls` --
# indistinguishable from an agent that ran and reached nothing. Run
# 20260817T020056Z lost four repeats to `httpx.ConnectError` and reported
# `[FAIL] invest_intrusion_incident recall=0.0 missing=2`, a finding about a
# turn that never got a response.

def _agg():
    import sys
    sys.path.insert(0, str(REPO_ROOT / "tooling"))
    from evals.calibrate_investigation import _aggregate
    return _aggregate


def _run(recall, calls, passed=True, lost=False):
    d = {"recall": recall, "calls": calls, "passed": passed, "quality": {},
         "quality_failed": [], "missing": [], "forbidden_hit": []}
    if lost:
        d.update({"lost": True, "recall": None, "calls": 0, "passed": False,
                  "error": "httpx.ConnectError: All connection attempts failed"})
    return d


def test_calibrate_captures_stream_errors() -> None:
    src = CALIBRATE.read_text()
    assert 'kind == "error"' in src, (
        "calibrate's on_event must handle ErrorEvent -- without it a dropped "
        "gateway scores as the agent reaching nothing")
    assert "stream_errors" in src


def test_lost_repeat_does_not_drag_the_median() -> None:
    """Fixture 29's real numbers must survive its lost siblings."""
    agg = _agg()([_run(None, 0, lost=True), _run(None, 0, lost=True),
                  _run(1.0, 18)])
    sp = agg["spread"]
    assert sp["lost"] == 2
    assert sp["repeats"] == 1, "repeats must count SCORED runs only"
    assert sp["recall"]["median"] == 1.0, "a lost run must not pull recall to 0"
    assert sp["calls"]["median"] == 18.0, "a lost run must not pull calls to 0"
    assert agg["passed"] is True


def test_all_repeats_lost_reports_no_data_never_fail() -> None:
    agg = _agg()([_run(None, 0, lost=True)] * 3)
    assert agg["spread"]["no_data"] is True
    assert agg["spread"]["lost"] == 3
    assert agg["recall"] is None, (
        "a fixture whose every repeat died has no recall -- reporting 0.0 "
        "makes a claim about an agent that never ran")


def test_clean_sweep_is_unchanged_by_the_lost_run_handling() -> None:
    agg = _agg()([_run(1.0, 12), _run(1.0, 12), _run(1.0, 11)])
    assert agg["spread"]["lost"] == 0
    assert agg["spread"]["repeats"] == 3
    assert agg["spread"]["calls"]["median"] == 12.0
