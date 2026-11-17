"""Does the offline record bundle hold what the `invest_*` fixtures ask for?

`test_investigation_fixtures_are_servable` asks whether the required TOOLS can
be called. This asks the other half: whether, once called, they can return
anything. Both have to be true or an investigation row is unservable, and an
unservable row does not announce itself -- it looks exactly like a weak agent.
Measured: with the connector's tools registered but no bundle bound, the agent
made twelve record reads, got `null` every time, and scored recall 0.667 with
the shortfall reading as a param-flail.

The list of things to cover is DERIVED from the fixtures, not restated here.
A hand-kept list would pass forever after someone adds a sixth investigation
fixture with a new UUID -- the gate would select zero new files and look
exactly like a passing one.

The bundle cites two real captures out of the connector checkout, so without
`FSR_CONNECTOR_REPO` (or `FSR_FIXTURE_RECORD_ROOT`) this skips rather than
asserting a half-loaded table.
"""
from __future__ import annotations

import importlib
import re

import pytest

tasks_mod = importlib.import_module("evals.tasks")

BUNDLE = "soc_invest_surface"

_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
                   r"[0-9a-f]{4}-[0-9a-f]{12}", re.I)
_IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")

#: Indicators a fixture names in order to assert the agent must NOT chase them,
#: or that only an enrichment connector answers. The bundle owes nothing for
#: these -- they are reached through `run_op`, not a record read.
_NOT_RECORD_DATA: set[str] = set()


def _bundle():
    fb = importlib.import_module("fsr_playbooks.mcp_server._fixture_box")
    try:
        return fb.FixtureBox(fb.load_bundle(BUNDLE))
    except fb.FixtureBoxError as exc:
        if "no record file" in str(exc):
            pytest.skip("bundle cites captures in the connector checkout; set "
                        "FSR_CONNECTOR_REPO to run this")
        raise


def _investigation_tasks() -> list:
    return [t for t in tasks_mod.load_tasks() if t.mode == "investigation"]


def _record_facts(task) -> list:
    """The facts served by a record read, not by an enrichment connector."""
    return [f for f in (task.required_facts or [])
            if f.get("tool") in ("get_record", "search_module_records")]


def _uuids(task) -> set:
    out = set()
    for f in _record_facts(task):
        for a in f.get("args_contains") or []:
            out |= set(m.group(0) for m in _UUID.finditer(str(a)))
    out |= set(m.group(0) for m in _UUID.finditer(task.prompt or ""))
    return out


def test_there_are_investigation_fixtures_to_check():
    """A zero-length sweep passes vacuously; say so out loud instead."""
    assert _investigation_tasks(), "no investigation fixtures were collected"


@pytest.mark.parametrize("task", _investigation_tasks(),
                         ids=lambda t: t.name)
def test_every_pinned_record_is_in_the_bundle(task):
    box = _bundle()
    missing = [u for u in _uuids(task)
               if not any(box.record(m, u) for m in box.modules)]
    assert not missing, (
        f"{task.name} pins {missing} but no bundle record carries that uuid -- "
        f"its `get_record` returns 404 offline and the row measures the "
        f"harness, not the agent")


@pytest.mark.parametrize("task", _investigation_tasks(),
                         ids=lambda t: t.name)
def test_every_search_pivot_returns_something(task):
    """A pivot that finds nothing is a dead end the agent cannot route around.

    `search_module_records` facts name either a module (correlate *somewhere*)
    or a literal to search on. Both have to land somewhere in the table.
    """
    box = _bundle()
    for f in _record_facts(task):
        if f.get("tool") != "search_module_records":
            continue
        module = f.get("module")
        if module:
            assert module in box.modules, (
                f"{task.name} correlates in module {module!r}, which the "
                f"bundle does not hold at all")
            _, body = box.get(f"/api/3/{module}?$limit=30")
            assert body["hydra:totalItems"] >= 1, (
                f"{task.name}: module {module!r} is present but empty")
        for term in f.get("args_contains") or []:
            if _UUID.fullmatch(str(term)) or str(term) in _NOT_RECORD_DATA:
                continue
            hits = 0
            for mod in box.modules:
                _, body = box.get(f"/api/3/{mod}?$search={term}&$limit=30")
                hits += body["hydra:totalItems"]
            assert hits, (
                f"{task.name} pivots on {term!r} and nothing in the bundle "
                f"mentions it -- the correlation step dead-ends offline")


@pytest.mark.parametrize("task", _investigation_tasks(),
                         ids=lambda t: t.name)
def test_every_hunt_chain_hop_is_reachable(task):
    """`hunt_chain` / `min_hunt_depth` grade how FAR the agent pivots.

    Each hop past the first is only reachable if some record already surfaced
    carries the next hop's indicator. If the chain is not in the table, the
    depth score measures the bundle.
    """
    chain = (task.investigation_quality or {}).get("hunt_chain") or []
    if not chain:
        pytest.skip("no hunt_chain on this fixture")
    box = _bundle()
    for hop in chain:
        for term in hop.get("args_contains") or []:
            if _UUID.fullmatch(str(term)):
                assert any(box.record(m, str(term)) for m in box.modules), (
                    f"{task.name}: hunt-chain hop {term!r} is not a record "
                    f"the bundle holds")
                continue
            hits = 0
            for mod in box.modules:
                _, body = box.get(f"/api/3/{mod}?$search={term}&$limit=30")
                hits += body["hydra:totalItems"]
            assert hits, (
                f"{task.name}: hunt-chain hop {term!r} appears in no bundle "
                f"record; `min_hunt_depth` cannot be reached offline")


def test_forbidden_indicators_are_not_gratuitously_in_the_bundle():
    """A restraint fixture needs the box to give the agent nothing to chase.

    `invest_disk_latency_no_ti` forbids every threat-intel call. If its alert
    record carried an IP, the bundle would be handing the agent the bait and
    then scoring it for biting.
    """
    box = _bundle()
    tasks = {t.name: t for t in _investigation_tasks()}
    t = tasks.get("invest_disk_latency_no_ti")
    if t is None:
        pytest.skip("restraint fixture not collected")
    uuid = next(iter(_uuids(t)), None)
    rec = next((box.record(m, uuid) for m in box.modules
                if box.record(m, uuid)), None)
    assert rec is not None
    found = _IPV4.findall(str(rec))
    assert not found, (
        f"the disk-latency alert carries {found}; the restraint test then "
        f"measures whether the agent resisted bait the fixture put there")
