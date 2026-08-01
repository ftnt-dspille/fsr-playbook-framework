"""An unexpanded live pull must REFUSE the write, not approve a wipe.

LIVE-VERIFIED on two transports (REST via pyfsr, and the on-platform crudhub
loopback): `GET /api/3/workflow_collections/<uuid>` returns `workflows`
**absent** unless `?$relationships=true` is set -- not IRI strings, not `[]`.
Absent.

Before this guard, that absence read as "the live collection had nothing", so
`check_prewrite` compared a write against a blank, found nothing missing, and
returned `ok=True, "no field loss"` for a save that deletes every workflow in
the collection. The loss gate was disarmed by a missing query parameter, and
said so in the language of success.

The distinction the guard rests on: **key absent = we never learned what is
there; key present and empty = we looked, and it is empty.** Only the second
is safe to treat as empty. `normalize_live_collection` deliberately never
invents absent containers, which is what keeps the two distinguishable this
far down.
"""
from __future__ import annotations

import pytest

from fsr_playbooks.compiler.prewrite import check_prewrite
from fsr_playbooks.compiler.wire import (
    UnexpandedRelationshipsError,
    require_expanded_collection,
)

_WF = {"uuid": "w1", "name": "wf", "steps": [
    {"uuid": "s1", "name": "Start", "arguments": {"a": 1}}], "routes": []}


def _env(coll: dict) -> dict:
    return {"data": [coll]}


def test_unexpanded_live_pull_refuses_a_destructive_write():
    live = _env({"uuid": "c1", "name": "My Playbooks"})     # no `workflows` key
    outgoing = _env({"uuid": "c1", "name": "My Playbooks", "workflows": []})

    verdict = check_prewrite(live, outgoing)

    assert not verdict.ok, (
        "a write that deletes every workflow was approved because the live "
        "pull never expanded relationships")
    assert "relationships" in verdict.message
    assert "UNKNOWN" in verdict.message


def test_a_genuinely_empty_collection_still_compares():
    """`workflows: []` is knowledge, not absence -- it must not be refused,
    or every new/empty collection becomes un-writable."""
    live = _env({"uuid": "c1", "name": "c", "workflows": []})
    outgoing = _env({"uuid": "c1", "name": "c", "workflows": [_WF]})

    verdict = check_prewrite(live, outgoing)
    assert verdict.ok, verdict.message


def test_a_normal_expanded_pull_is_unaffected():
    live = _env({"uuid": "c1", "name": "c", "workflows": [_WF]})
    assert check_prewrite(live, live).ok


def test_real_loss_is_still_reported_not_masked_by_the_new_guard():
    live = _env({"uuid": "c1", "name": "c", "workflows": [_WF]})
    stripped = {**_WF, "steps": []}
    verdict = check_prewrite(live, _env({"uuid": "c1", "name": "c",
                                         "workflows": [stripped]}))
    assert not verdict.ok
    assert any("Start" in p for p in verdict.dropped), verdict.dropped


def test_require_expanded_names_the_collection():
    with pytest.raises(UnexpandedRelationshipsError) as exc:
        require_expanded_collection(_env({"uuid": "c1", "name": "Payroll PBs"}))
    assert "Payroll PBs" in str(exc.value)


def test_require_expanded_passes_an_expanded_envelope():
    require_expanded_collection(_env({"uuid": "c1", "name": "c", "workflows": []}))
