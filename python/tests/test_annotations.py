"""Tests for annotations + step.comment auto-note behavior."""
from compiler import compile_yaml
from compiler.decompiler import decompile


def _yaml_with_comment() -> str:
    return """
collection: Annotation Test
playbooks:
  - name: pb
    steps:
      - id: start
        type: start
      - id: noop
        type: set_variable
        comment: |
          Sets a flag the next step branches on.
          AI-added 2026-05-03.
        arguments:
          variables:
            ready: 'true'
        next: start
"""


def _yaml_with_block() -> str:
    return """
collection: Annotation Test
playbooks:
  - name: pb
    steps:
      - id: start
        type: start
      - id: a
        type: set_variable
        arguments: { variables: { x: '1' } }
        next: b
      - id: b
        type: set_variable
        arguments: { variables: { y: '2' } }
    annotations:
      - id: setup_block
        kind: block
        title: Setup phase
        contains: [a, b]
"""


def test_step_comment_emits_note(db_path):
    r = compile_yaml(_yaml_with_comment(), db_path)
    assert r.ok, r.errors
    wf = r.fsr_json["data"][0]["workflows"][0]
    groups = wf["groups"]
    assert len(groups) == 1
    note = groups[0]
    assert note["type"] == "note"
    # Auto-comment notes are titled "<PREFIX>: <step name>" where the
    # prefix carries the comment category (Note/TODO/FIX/...). For a
    # plain comment body that doesn't start with a recognized keyword,
    # the prefix defaults to "Note".
    assert note["name"] == "Note: noop"
    assert "AI-added 2026-05-03" in note["description"]
    # Note positioned to the right of the step
    assert int(note["left"]) > 200


def test_block_attaches_step_group(db_path):
    r = compile_yaml(_yaml_with_block(), db_path)
    assert r.ok, r.errors
    wf = r.fsr_json["data"][0]["workflows"][0]
    groups = wf["groups"]
    assert len(groups) == 1
    block = groups[0]
    assert block["type"] == "block"
    assert block["name"] == "Setup phase"
    block_uuid = block["uuid"]
    # steps `a` and `b` carry the group IRI; `start` does not.
    by_name = {s["name"]: s for s in wf["steps"]}
    assert by_name["a"]["group"] == f"/api/3/workflow_groups/{block_uuid}"
    assert by_name["b"]["group"] == f"/api/3/workflow_groups/{block_uuid}"
    assert by_name["start"]["group"] is None


def test_round_trip_collapses_auto_comment(db_path):
    r = compile_yaml(_yaml_with_comment(), db_path)
    ir = decompile(r.fsr_json, db_path)
    pb = ir.playbooks[0]
    by_id = {s.id: s for s in pb.steps}
    # The auto-comment note is folded back into step.comment;
    # no leftover annotation should remain.
    assert by_id["noop"].comment is not None
    assert "AI-added" in by_id["noop"].comment
    assert pb.annotations == []


def test_round_trip_preserves_block(db_path):
    r = compile_yaml(_yaml_with_block(), db_path)
    ir = decompile(r.fsr_json, db_path)
    pb = ir.playbooks[0]
    assert len(pb.annotations) == 1
    ann = pb.annotations[0]
    assert ann.kind == "block"
    assert ann.title == "Setup phase"
    assert sorted(ann.contains) == ["a", "b"]
