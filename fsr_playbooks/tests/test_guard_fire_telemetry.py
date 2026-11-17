"""Guard-fire telemetry.

A guard forcing a terminal tool call is a compensation for the model not
choosing that tool on its own. Whether each guard still earns its keep is
an empirical question, and nothing recorded the answer until this counter.
A guard that never fires across a corpus is a deletion candidate; one that
fires often points at a description or prompt still worth fixing.
"""
from __future__ import annotations

import pytest

from fsr_playbooks.llm import _loop_helpers as lh


@pytest.fixture(autouse=True)
def _clean():
    lh.clear_guard_fires()
    yield
    lh.clear_guard_fires()


def test_starts_empty():
    assert lh.snapshot_guard_fires() == []


def test_records_in_order():
    lh.record_guard_fire("A")
    lh.record_guard_fire("B")
    assert lh.snapshot_guard_fires() == ["A", "B"]


def test_snapshot_is_a_copy():
    """A caller mutating the snapshot must not corrupt the counter."""
    lh.record_guard_fire("A")
    lh.snapshot_guard_fires().append("B")
    assert lh.snapshot_guard_fires() == ["A"]


def test_clear_resets():
    lh.record_guard_fire("A")
    lh.clear_guard_fires()
    assert lh.snapshot_guard_fires() == []


@pytest.mark.parametrize("guard_cls", [
    lh.EnhanceDeliveryGuard,
    lh.CreateDeliveryGuard,
    lh.BuildProgressGuard,
])
def test_every_guard_records_when_it_forces(guard_cls):
    """mark_forced is the single choke point every forcing path goes through,
    so instrumenting it must cover all three guards."""
    guard_cls().mark_forced()
    assert lh.snapshot_guard_fires() == [guard_cls.__name__]


def test_forcing_is_still_capped_at_once():
    """Telemetry must not change control flow: the guard still refuses to
    fire twice."""
    allowed = {"emit_enhancement_offer"}
    g = lh.EnhanceDeliveryGuard()
    g.note_result("verify_enhancement", {},
                  {"ready_to_push": True, "verified_id": "abc"})
    assert g.outstanding(allowed) is not None
    g.mark_forced()
    assert g.outstanding(allowed) is None
