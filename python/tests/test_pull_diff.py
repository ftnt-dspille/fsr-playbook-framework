"""Unit-level tests for the live-shape decompile path.

`fsrpb pull` fetches via `?$relationships=true` which returns expanded
nested dicts for `stepType`, `sourceStep`, `targetStep`, `triggerStep`
instead of IRI strings. The decompiler must handle both shapes; the
corpus round-trip only exercises the IRI shape, so this test fills the
gap. Doesn't hit live FSR.
"""
from __future__ import annotations

from fsr_core.compiler.decompiler import decompile
from fsr_core.compiler.emitter import emit
from fsr_core.compiler.roundtrip import diff, normalize_collection

# Real step-type UUIDs from the live appliance — keep these stable so the
# fixture matches what `?$relationships=true` would return.
TRIGGER_UUID = "b348f017-9a94-471f-87f8-ce88b6a7ad62"   # cybersponse.abstract_trigger
SET_VAR_UUID = "04d0cf46-b6a8-42c4-8683-60a7eaa69e8f"   # SetVariable
CONNECTOR_UUID = "0bfed618-0316-11e7-93ae-92361f002671"  # Connectors


def _live_shape_fixture() -> dict:
    """Mimic what `_fetch_live_collection` returns: collection wrapping
    workflows whose nested fields are expanded dicts, not IRI strings."""
    start_uuid = "11111111-aaaa-4000-9000-000000000001"
    set_uuid = "22222222-aaaa-4000-9000-000000000002"
    return {
        "type": "workflow_collections",
        "macros": [],
        "exported_tags": [],
        "data": [{
            "@type": "WorkflowCollection",
            "name": "Live Shape Test",
            "description": "fixture",
            "visible": True,
            "uuid": "00000000-aaaa-4000-9000-000000000000",
            "workflows": [{
                "@type": "Workflow",
                "name": "Trivial",
                "tag": "",
                "description": "",
                "isActive": False,
                "parameters": ["payload"],
                "uuid": "33333333-aaaa-4000-9000-000000000003",
                # triggerStep is an expanded dict on live API
                "triggerStep": {
                    "uuid": start_uuid,
                    "name": "Start",
                    "stepType": {"uuid": TRIGGER_UUID, "name": "cybersponse.abstract_trigger"},
                },
                "steps": [
                    {
                        "@type": "WorkflowStep",
                        "uuid": start_uuid,
                        "name": "Start",
                        "arguments": {},
                        # stepType expanded as nested dict (not an IRI string)
                        "stepType": {"uuid": TRIGGER_UUID, "name": "cybersponse.abstract_trigger"},
                    },
                    {
                        "@type": "WorkflowStep",
                        "uuid": set_uuid,
                        "name": "Do",
                        "arguments": {"arg_list": [{"name": "x", "value": "1"}]},
                        "stepType": {"uuid": SET_VAR_UUID, "name": "SetVariable"},
                    },
                ],
                # routes likewise expanded
                "routes": [{
                    "@type": "WorkflowRoute",
                    "name": "start->do",
                    "sourceStep": {"uuid": start_uuid, "name": "Start"},
                    "targetStep": {"uuid": set_uuid, "name": "Do"},
                    "label": "",
                    "uuid": "44444444-aaaa-4000-9000-000000000004",
                }],
            }],
        }],
    }


def test_decompile_handles_expanded_dicts(db_path):
    """Live API shape (`?$relationships=true`) decompiles cleanly."""
    fixture = _live_shape_fixture()
    ir = decompile(fixture, db_path)
    assert ir.name == "Live Shape Test"
    assert len(ir.playbooks) == 1
    pb = ir.playbooks[0]
    assert pb.name == "Trivial"
    assert pb.parameters == ["payload"]
    assert pb.trigger_step_id == "start"
    assert [s.id for s in pb.steps] == ["start", "do"]
    assert pb.steps[0].type == "start"      # canonical -> short
    assert pb.steps[1].type == "set_variable"
    assert pb.steps[0].next == "do"


def test_live_shape_round_trips(db_path):
    """Decompile a live-shape collection, re-emit, semantically equal."""
    fixture = _live_shape_fixture()
    ir = decompile(fixture, db_path)
    regen = emit(ir)
    a = normalize_collection(fixture)
    b = normalize_collection(regen)
    diffs = diff(a, b, "collection")
    assert not diffs, "\n".join(diffs)


def test_diff_detects_drift(db_path):
    """`diff()` flags actual differences between two normalized collections."""
    fixture = _live_shape_fixture()
    ir = decompile(fixture, db_path)
    # Replace the arguments dict (rather than mutating in place) so we don't
    # also mutate the fixture — decompile shares the dict reference.
    ir.playbooks[0].steps[1].arguments = {"arg_list": [{"name": "x", "value": "999"}]}
    regen = emit(ir)
    a = normalize_collection(fixture)
    b = normalize_collection(regen)
    diffs = diff(a, b, "collection")
    assert diffs, "expected at least one drift to be reported"
    assert any("999" in d or "value" in d for d in diffs)
