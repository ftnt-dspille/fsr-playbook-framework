"""A decision step's UNLABELED outgoing route must stay unlabeled.

Found by `probe_mapping_fidelity.py` -- the single semantic diff across 209
live collections, in a playbook nobody had thought to put in the corpus.

The chain: `_decompile_workflow` took the generic linear-step shortcut
(one outgoing route, no label -> `next:`), which is right for every step type
EXCEPT `decision`. On a decision, `next:` means "default branch": the parser
warns and synthesizes an `Else` default condition, and the emitter writes a
route LABELED "Else" where the appliance had an unlabeled one. That rewrites
the routing graph, which is the exact property the round-trip contract exists
to preserve.

`unlabeled_next` already represented this precisely; the decompiler just was
not reaching for it. Pinned here rather than only in the corpus because the
corpus is five playbooks we chose -- the same blind spot that hid this.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from fsr_playbooks._db import PACKAGED_SLIM_DB
from fsr_playbooks.compiler.decompiler import decompile
from fsr_playbooks.compiler.emitter import emit
from fsr_playbooks.compiler.roundtrip import diff, normalize_collection

_DECISION_UUID_STEP = "4f920f64-5927-4bb3-b2c1-426617b91536"


def _collection(*, route_label):
    """A decision with ONE outgoing route to its single condition target."""
    return {"type": "workflow_collections", "data": [{
        "@type": "WorkflowCollection",
        "name": "decision unlabeled route", "description": "", "visible": True,
        "uuid": "11111111-1111-1111-1111-111111111111",
        "workflows": [{
            "@type": "Workflow", "name": "wf", "uuid": "22222222-2222-2222-2222-222222222222",
            "tag": "", "description": "", "isActive": True,
            "triggerStep": "/api/3/workflow_steps/33333333-3333-3333-3333-333333333333",
            "steps": [
                {"uuid": "33333333-3333-3333-3333-333333333333", "name": "Start",
                 "stepType": {"uuid": "b2c0a4e9-4f1e-4a2c-9b8e-1d0f5a6c7b81",
                              "name": "cybersponse.abstract_trigger"},
                 "arguments": {"title": "Start"}},
                {"uuid": "44444444-4444-4444-4444-444444444444", "name": "test",
                 "stepType": {"uuid": "e26b1dcd-2b8c-4b3b-8b4a-5a5b1c4a9e01",
                              "name": "Decision"},
                 "arguments": {"conditions": [
                     {"step_iri": f"/api/3/workflow_steps/{_DECISION_UUID_STEP}",
                      "condition": "{{ true }}", "step_name": "test2"}]}},
                {"uuid": _DECISION_UUID_STEP, "name": "test2",
                 "stepType": {"uuid": "e6b8a0d2-8a1e-4d4b-9f2a-0c3d5e7f9a12",
                              "name": "SetVariable"},
                 "arguments": {"test": "test"}},
            ],
            "routes": [
                {"uuid": "55555555-5555-5555-5555-555555555555", "name": "Start -> test",
                 "label": None,
                 "sourceStep": "/api/3/workflow_steps/33333333-3333-3333-3333-333333333333",
                 "targetStep": "/api/3/workflow_steps/44444444-4444-4444-4444-444444444444"},
                {"uuid": "66666666-6666-6666-6666-666666666666", "name": "test -> test2",
                 "label": route_label,
                 "sourceStep": "/api/3/workflow_steps/44444444-4444-4444-4444-444444444444",
                 "targetStep": f"/api/3/workflow_steps/{_DECISION_UUID_STEP}"},
            ],
        }],
    }]}


@pytest.fixture(scope="module")
def db() -> Path:
    return PACKAGED_SLIM_DB


def test_unlabeled_decision_route_uses_unlabeled_next_not_next(db):
    ir = decompile(_collection(route_label=None), db)
    step = next(s for s in ir.playbooks[0].steps if s.name == "test")
    assert step.next is None, (
        "`next:` on a decision recompiles to an `Else`-LABELED route; an "
        "unlabeled live route must decompile to `unlabeled_next`")
    assert step.unlabeled_next, "the unlabeled route target was dropped entirely"


def test_the_route_survives_the_full_round_trip_unlabeled(db):
    live = _collection(route_label=None)
    regen = emit(decompile(live, db))
    diffs = diff(normalize_collection(live), normalize_collection(regen), "collection")
    assert not diffs, f"decision route did not round-trip: {diffs}"

    labels = [r["label"] for r in normalize_collection(regen)["workflows"][0]["routes"]]
    assert labels == [None, None], f"a label was invented on recompile: {labels}"


def test_a_genuinely_labeled_decision_route_still_round_trips(db):
    """The fix must not flip the other direction: a real branch label stays."""
    live = _collection(route_label="Yes")
    regen = emit(decompile(live, db))
    assert not diff(normalize_collection(live), normalize_collection(regen), "collection")
