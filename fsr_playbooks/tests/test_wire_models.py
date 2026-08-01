"""Pin the boundary models for playbook JSON the appliance hands us.

The defect these exist for: `dict[str, Any]` at the seam made a dict-keyed
`steps` container indistinguishable from a list one, so the pre-write loss
gate crashed and reported the crash as "refusing the save" -- a guard whose
output looked right with a shape bug inside it.

What is pinned here:
  * both wire shapes normalize to the same list, on every entry path;
  * an UNREADABLE shape raises and NAMES the field, instead of degrading to
    `[]` (which the loss gate would read as "the live playbook was empty" and
    wave every deletion through);
  * normalization does not add, drop, or retype any key -- the decompiler
    reads far more of the wire than we model.

Live grounding for the shapes asserted here: `tooling/probes/probe_wire_shapes.py`.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from fsr_playbooks.compiler.wire import (
    LiveCollection,
    WireShapeError,
    as_record_list,
    normalize_live_collection,
    parse_live_collection,
)

_STEP_A = {"uuid": "u1", "name": "Start", "arguments": {"x": 1}}
_STEP_B = {"uuid": "u2", "name": "Notify", "arguments": {}}


def _envelope(steps, routes=None):
    return {"data": [{
        "uuid": "c1", "name": "coll",
        "workflows": [{"uuid": "w1", "name": "wf",
                       "steps": steps, "routes": routes if routes is not None else []}],
    }]}


# --- coercion ---------------------------------------------------------------

def test_list_and_dict_keyed_records_normalize_identically():
    as_list = as_record_list([_STEP_A, _STEP_B])
    as_map = as_record_list({"u1": _STEP_A, "u2": _STEP_B})
    assert as_list == as_map == [_STEP_A, _STEP_B]


def test_missing_container_is_empty_not_an_error():
    """A workflow with no routes is ordinary, not a malformed response."""
    assert as_record_list(None) == []


@pytest.mark.parametrize("bad", ["u1,u2", 7, True])
def test_unreadable_shape_raises_and_names_the_field(bad):
    with pytest.raises(WireShapeError) as exc:
        as_record_list(bad, path="workflow.steps")
    # The whole point: the message identifies the field AND what arrived.
    assert "workflow.steps" in str(exc.value)
    assert type(bad).__name__ in str(exc.value)
    assert exc.value.field == "workflow.steps"


# --- models -----------------------------------------------------------------

def test_model_accepts_the_dict_keyed_wire_shape():
    coll = LiveCollection.model_validate({
        "uuid": "c1", "name": "coll",
        "workflows": {"w1": {"uuid": "w1", "name": "wf",
                             "steps": {"u1": _STEP_A}, "routes": {}}},
    })
    assert [w.name for w in coll.workflows] == ["wf"]
    assert [s.name for s in coll.workflows[0].steps] == ["Start"]


def test_unmodelled_wire_keys_survive():
    """`extra="allow"` is load-bearing: the decompiler reads keys we do not
    model, so dropping them here would delete real data."""
    step = LiveCollection.model_validate({
        "workflows": [{"steps": [{"uuid": "u1", "name": "s",
                                  "recordTags": ["t"], "@id": "/api/3/x"}]}],
    }).workflows[0].steps[0]
    assert step.recordTags == ["t"]  # type: ignore[attr-defined]


def test_wrong_scalar_type_is_a_validation_error_not_a_silent_coercion():
    with pytest.raises(ValidationError) as exc:
        LiveCollection.model_validate({"workflows": [{"steps": [{"name": {"a": 1}}]}]})
    assert "name" in str(exc.value)


def test_empty_arguments_may_arrive_as_a_list():
    """LIVE-VERIFIED against a real appliance: an argument-less step sends
    `"arguments": []`, not `{}`. Found by `probe_wire_shapes.py` on the first
    run -- the model, written from fixtures, was wrong about real data."""
    step = LiveCollection.model_validate(
        {"workflows": [{"steps": [{"uuid": "u1", "name": "s", "arguments": []}]}]}
    ).workflows[0].steps[0]
    assert step.arguments == {}


def test_non_empty_argument_list_is_still_refused():
    """Tolerating `[]` must not become tolerating any list -- dropping a
    populated one is how arguments go missing silently."""
    with pytest.raises((WireShapeError, ValidationError)):
        LiveCollection.model_validate(
            {"workflows": [{"steps": [{"arguments": [{"a": 1}]}]}]})


def test_normalize_does_not_rewrite_the_empty_argument_list():
    """The model tolerates `[]`; normalization must not CHANGE it. Downstream
    already reads `s.get("arguments") or {}`, and rewriting live values here
    would alter what the round-trip corpus compares."""
    raw = _envelope([{"uuid": "u1", "name": "s", "arguments": []}])
    assert normalize_live_collection(raw)["data"][0]["workflows"][0]["steps"][0][
        "arguments"] == []


def test_parse_rejects_a_non_envelope():
    with pytest.raises(WireShapeError):
        parse_live_collection([{"uuid": "c1"}])


# --- normalization fidelity -------------------------------------------------

def test_normalize_coerces_containers_and_touches_nothing_else():
    raw = _envelope({"u1": _STEP_A, "u2": _STEP_B})
    raw["data"][0]["workflows"][0]["ownerId"] = 3
    raw["data"][0]["deletedAt"] = None

    out = normalize_live_collection(raw)
    wf = out["data"][0]["workflows"][0]

    assert wf["steps"] == [_STEP_A, _STEP_B]
    assert wf["ownerId"] == 3
    assert out["data"][0]["deletedAt"] is None
    assert set(wf) == set(raw["data"][0]["workflows"][0])


def test_normalize_does_not_invent_absent_containers():
    """A model default would inject `steps: []`/`arguments: {}` where the
    appliance sent nothing, silently changing what the round-trip corpus
    compares. That is why this is not a `model_dump`."""
    raw = {"data": [{"uuid": "c1", "name": "coll",
                     "workflows": [{"uuid": "w1", "name": "wf"}]}]}
    wf = normalize_live_collection(raw)["data"][0]["workflows"][0]
    assert "steps" not in wf and "routes" not in wf and "arguments" not in wf


def test_normalize_leaves_the_list_shape_byte_identical():
    raw = _envelope([_STEP_A, _STEP_B])
    assert normalize_live_collection(raw) == raw
