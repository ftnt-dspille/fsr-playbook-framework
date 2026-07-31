"""Guards on the corpus-conformance probe's input handling.

The probe's value depends entirely on it actually loading the playbooks it
claims to test. Its first run reported a clean pass on 211 files it had never
compiled: pack bundles ship playbooks under `workflowSteps`, the decompiler
reads `steps`, so those files decompiled to zero steps and the round-trip
compared empty against empty. A conformance probe that silently tests nothing
is worse than no probe, so the shape handling is pinned here.
"""
import json

from tooling.probes.probe_corpus_conformance import _known_dangling, _load_playbook

STEP = {"@type": "WorkflowStep", "uuid": "s1", "name": "Start", "arguments": {}}


def test_pack_export_shape_is_normalized(tmp_path):
    """`workflowSteps` is the pack-export spelling of `steps`."""
    f = tmp_path / "pb.json"
    f.write_text(json.dumps({
        "name": "P", "workflowSteps": [STEP],
        "workflowRoutes": [{"uuid": "r1"}],
    }))
    doc = _load_playbook(f)
    assert doc is not None
    assert doc["steps"] == [STEP]
    assert doc["routes"] == [{"uuid": "r1"}]
    # The original spelling must not survive alongside the normalized one.
    assert "workflowSteps" not in doc


def test_api_shape_passes_through(tmp_path):
    f = tmp_path / "pb.json"
    f.write_text(json.dumps({"name": "P", "steps": [STEP], "routes": []}))
    assert _load_playbook(f)["steps"] == [STEP]


def test_stepless_file_is_skipped_not_silently_passed(tmp_path):
    """The exact trap: no steps means NOT a playbook, never a free pass."""
    f = tmp_path / "pb.json"
    f.write_text(json.dumps({"name": "P", "steps": []}))
    assert _load_playbook(f) is None


def test_notification_rule_is_not_a_playbook(tmp_path):
    """Pack bundles ship ~150 of these next to the playbooks."""
    f = tmp_path / "rule.json"
    f.write_text(json.dumps({
        "name": "Notify Failed", "entity_type": "workflow_logs",
        "event_type": "failed", "actions": [{"x": 1}],
    }))
    assert _load_playbook(f) is None


def test_unparseable_file_is_skipped(tmp_path):
    f = tmp_path / "bad.json"
    f.write_text("not json{{")
    assert _load_playbook(f) is None


def test_dangling_ref_attributed_to_the_source_pack():
    """A ref to a step the pack does not contain is the pack's bug, not ours."""
    doc = {"steps": [{"name": "Get Assets By Vendor"}]}
    msg = ("Jinja reference vars.steps.Get_Data_From_CSV_File.data in step 'x': "
           "no step with jinja-key")
    assert _known_dangling(msg, doc) is True


def test_resolvable_ref_is_not_blamed_on_the_pack():
    """Same message shape, but the step DOES exist -- that would be our bug."""
    doc = {"steps": [{"name": "Get Data From CSV File"}]}
    msg = "Jinja reference vars.steps.Get_Data_From_CSV_File.data in step 'x': no step with"
    assert _known_dangling(msg, doc) is False
