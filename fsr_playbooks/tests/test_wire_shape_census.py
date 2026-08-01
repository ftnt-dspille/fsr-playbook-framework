"""Hold the wire models to what a real appliance actually sends -- box-free.

`probe_wire_shapes.py` needs a box. This test does not: it reads the committed
census (`fixtures/wire_shape_census.json`, types and counts only -- no playbook
content, no host) and asserts the models still accept every shape the census
records. So the live grounding keeps paying off in CI, and a future "tighten
the types" change that would reject real data fails here instead of on a
customer's appliance.

The census is regenerated with:

    python tooling/probes/probe_wire_shapes.py --census \\
        fsr_playbooks/tests/fixtures/wire_shape_census.json

Regenerate it deliberately -- it is the record of what the platform does, so
an unexplained change to it is a finding, not a chore.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from fsr_playbooks.compiler.wire import LiveCollection, normalize_live_collection

CENSUS = Path(__file__).parent / "fixtures" / "wire_shape_census.json"

# One concrete value per Python type name the census can record, so an
# observed type can be turned back into a payload the models must accept.
_SAMPLE = {
    "str": "x",
    "NoneType": None,
    "dict": {"uuid": "t1"},
    "list": [],
    "int": 1,
    "bool": True,
    "float": 1.0,
}


@pytest.fixture(scope="module")
def census() -> dict:
    assert CENSUS.exists(), f"missing census fixture: {CENSUS}"
    return json.loads(CENSUS.read_text())


def test_census_is_a_real_sample_not_a_stub(census):
    """A census of three playbooks would pass everything and prove nothing."""
    assert census["collections"] >= 50, "census too small to be evidence"
    assert census["steps"] >= 1000


def test_every_observed_field_type_is_accepted(census):
    """The core claim: no type the appliance actually emits is rejected."""
    for key, types in census["field_types"].items():
        kind, field = key.split(".", 1)
        for type_name in types:
            assert type_name in _SAMPLE, (
                f"census records an unhandled type `{type_name}` for {key}; "
                "add a sample value here and confirm the model accepts it")
            rec = {field: _SAMPLE[type_name]}
            payload = {"workflows": [{"uuid": "w1", "name": "wf"}]}
            if kind == "workflow":
                payload["workflows"][0].update(rec)
            elif kind == "step":
                payload["workflows"][0]["steps"] = [rec]
            elif kind == "route":
                payload["workflows"][0]["routes"] = [rec]
            else:  # pragma: no cover - guards a census format change
                pytest.fail(f"unknown census record kind: {kind}")

            LiveCollection.model_validate(payload)  # must not raise


def test_empty_argument_list_is_in_the_census(census):
    """Pins the live finding itself, so nobody 'cleans up' the `[]` branch as
    dead code: 64 of 7752 steps on a real box send `"arguments": []`."""
    assert census["field_types"]["step.arguments"].get("list", 0) > 0


def test_container_shapes_recorded_are_all_handled(census):
    for key, shapes in census["containers"].items():
        for shape in shapes:
            assert shape in ("list", "id-keyed map", "absent/null"), (
                f"{key} was returned as `{shape}`, which the coercion does not "
                "handle -- as_record_list would raise on it")


def test_unmodelled_keys_survive_normalization(census):
    """Every key the census saw but we do not model must still come out the
    other side. `extra="allow"` plus a normalization that rewrites nothing is
    what makes that true; this proves it over the real key set."""
    step_keys = list(census["unmodelled_keys"].get("step", {}))
    raw = {"data": [{"uuid": "c1", "name": "c", "workflows": [
        {"uuid": "w1", "name": "wf",
         "steps": [{"uuid": "s1", "name": "s", **{k: "v" for k in step_keys}}]}]}]}
    out = normalize_live_collection(raw)
    got = out["data"][0]["workflows"][0]["steps"][0]
    for k in step_keys:
        assert got.get(k) == "v", f"normalization dropped live key `{k}`"
