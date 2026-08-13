"""The fixture box, bound over the simulated client's record surface.

Three things are worth a gate here, and only the third is about record data:

  1. **Unbound is unchanged.** Binding is opt-in precisely so every offline row
     already measured keeps its substrate. If importing `_fixture_box` or
     landing the `_route_status` refactor moved the unbound answer even
     slightly, every historical offline number would silently mean something
     new.
  2. **A miss is loud.** A module the bundle does not hold answers 404 and a
     write answers 599 -- not the empty-but-ok envelope. An empty-but-ok read
     is indistinguishable from a box that holds nothing, which is the exact
     failure this whole seam exists to remove: the agent investigates
     competently against an empty table and the harness scores it as the
     agent.
  3. **The shipped bundle answers what the fixtures ask.** Each `invest_*` task
     pins a UUID and a pivot; a bundle that stopped serving one would make that
     fixture unservable while still LOOKING like a run.
"""
from __future__ import annotations

import pytest

from fsr_playbooks.mcp_server import _fixture_box as fb
from fsr_playbooks.mcp_server import _sim_client as sc

BUNDLE = "soc_invest_surface"

#: (module, uuid) each investigation fixture pulls first, and the pivot it then
#: searches on. Kept in step with `tooling/evals/tasks/2[5-9]_invest_*.json`.
PINNED = [
    ("alerts", "54f25f1f-808e-4bbb-8e20-e95855291184", "108.17.204.5"),
    ("alerts", "b62fb2d5-d27e-4d7e-8bd8-53e4878ba614", "35.189.45.227"),
    ("alerts", "8d74ff80-3b63-406b-b748-6aca1f1f30ff", "ORDERS-ERP"),
    ("incidents", "a0668705-9dc8-4797-a2c8-8f1e1f34942a", "192.168.77.30"),
]


@pytest.fixture
def box():
    """A tiny hand-built table -- no bundle file, no connector."""
    b = fb.FixtureBox({"modules": {"alerts": [
        {"uuid": "aaa", "name": "hello", "sourceIp": "1.2.3.4"},
        {"uuid": "bbb", "name": "other", "sourceIp": "5.6.7.8"},
    ]}})
    prev = sc.bind_box(b)
    yield b
    sc.bind_box(prev)


def test_unbound_record_surface_is_unchanged():
    assert sc.active_box() is None
    r = sc.get_client().session.get("/api/3/alerts/aaa")
    assert (r.status_code, r.json()) == (200, {"data": []})


def test_bound_box_serves_records(box):
    c = sc.get_client()
    assert c.session.get("/api/3/alerts/aaa").json()["name"] == "hello"

    coll = c.session.get("/api/3/alerts?$limit=5").json()
    assert coll["hydra:totalItems"] == 2

    q = c.session.post("/api/query/alerts", json={"filters": [
        {"field": "sourceIp", "operator": "eq", "value": "5.6.7.8"}]}).json()
    assert [r["uuid"] for r in q["hydra:member"]] == ["bbb"]


def test_binding_leaves_the_integration_endpoints_alone(box):
    """The box owns `/api/3` and `/api/query`; execute/healthcheck stay canned."""
    r = sc.get_client().session.post("/api/integration/execute/", json={
        "connector": "virustotal", "operation": "ip_reputation", "params": {}})
    assert r.status_code == 200 and "data" in r.json()


def test_an_unanswered_read_is_loud_not_empty(box):
    c = sc.get_client()
    assert c.session.get("/api/3/incidents").status_code == 404
    assert c.session.get("/api/3/alerts/nope").status_code == 404
    # A write must stop at the approval gate. A box that accepted one would
    # hide the gate not firing.
    assert c.session.post("/api/3/alerts", json={"name": "x"}).status_code == 599


def test_unbind_restores_the_empty_surface(box):
    sc.unbind_box()
    assert sc.get_client().session.get("/api/3/alerts/aaa").json() == {"data": []}


def _load_shipped_bundle():
    try:
        return fb.FixtureBox(fb.load_bundle(BUNDLE))
    except fb.FixtureBoxError as exc:
        if "$file" in str(exc) or "no record file" in str(exc):
            pytest.skip("bundle cites captures in the connector checkout; set "
                        "FSR_CONNECTOR_REPO (or FSR_FIXTURE_RECORD_ROOT) to "
                        "run this")
        raise


@pytest.mark.parametrize("module,uuid,pivot", PINNED)
def test_shipped_bundle_answers_each_pinned_fixture(module, uuid, pivot):
    b = _load_shipped_bundle()
    assert b.record(module, uuid) is not None, (
        f"{module}:{uuid} is pinned by an invest_* fixture but the bundle no "
        "longer holds it -- that fixture is unservable offline")
    status, body = b.get(f"/api/3/{module}?$search={pivot}&$limit=10")
    assert status == 200 and body["hydra:totalItems"] >= 1, (
        f"nothing to correlate on {pivot!r}; the fixture's pivot dead-ends")


def test_shipped_bundle_carries_the_smithdesktop_hunt_chain():
    """`min_hunt_depth: 3` needs host -> internal IP -> external C2 to exist.

    The pivot alert is the load-bearing hop: the captured incident names the
    host and nothing else, so without an alert tying smithDesktop to
    10.50.60.70 the search dead-ends and the depth score measures the bundle,
    not the agent.
    """
    b = _load_shipped_bundle()
    assert b.record("incidents", "b4a62c3b-3f60-44a5-b44d-f53a9244fa55")
    for hop in ("smithDesktop", "10.50.60.70", "102.220.160.21"):
        _, body = b.get(f"/api/3/alerts?$search={hop}&$limit=10")
        assert body["hydra:totalItems"] >= 1, f"hunt chain breaks at {hop}"
    _, body = b.get("/api/3/alerts?$search=smithDesktop&$limit=10")
    assert any("10.50.60.70" in str(r) for r in body["hydra:member"]), (
        "the host search returns rows but none carries the internal IP -- the "
        "agent cannot pivot from the host to the chain")
