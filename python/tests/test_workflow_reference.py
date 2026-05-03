from compiler import compile_yaml
from compiler.errors import ErrorCode


def test_parent_calls_child_compiles(db_path, repo_root):
    text = (repo_root / "examples" / "parent_calls_child.yaml").read_text()
    r = compile_yaml(text, db_path)
    assert r.ok, [e.to_dict() for e in r.errors]
    wfs = r.fsr_json["data"][0]["workflows"]
    parent = next(w for w in wfs if w["name"] == "Add Host And Resolve")
    child = next(w for w in wfs if w["name"] == "Resolve Hostname")

    # Child declares parameters in the emitted JSON.
    assert child["parameters"] == ["hostname", "dns_server"]

    # Parent's call step has its target rewritten to an IRI matching child's uuid.
    call_step = next(s for s in parent["steps"] if s["name"] == "Resolve via child playbook")
    assert "target" not in call_step["arguments"]
    assert call_step["arguments"]["workflowReference"] == f"/api/3/workflows/{child['uuid']}"
    assert call_step["arguments"]["arguments"] == {
        "hostname": "fsr-1", "dns_server": "8.8.8.8",
    }


def test_unknown_target_playbook_suggests(db_path):
    text = """
collection: T
playbooks:
  - name: Child
    parameters: [x]
    steps:
      - id: start
        type: start
  - name: Parent
    steps:
      - id: start
        type: start
        next: c
      - id: c
        type: workflow_reference
        arguments:
          target: Chld
          arguments: {x: 1}
"""
    r = compile_yaml(text, db_path)
    assert not r.ok
    e = next(e for e in r.errors if "target" in e.path)
    assert e.near == "Child"


def test_unknown_input_param(db_path):
    text = """
collection: T
playbooks:
  - name: Child
    parameters: [hostname]
    steps:
      - id: start
        type: start
  - name: Parent
    steps:
      - id: start
        type: start
        next: c
      - id: c
        type: workflow_reference
        arguments:
          target: Child
          arguments:
            hostnaem: x
"""
    r = compile_yaml(text, db_path)
    assert not r.ok
    e = next(e for e in r.errors if e.code is ErrorCode.UNKNOWN_PARAM)
    assert "hostnaem" in e.message
    assert e.near == "hostname"


def test_duplicate_playbook_name_rejected(db_path):
    """FSR enforces UniqueConstraint(name, collection) on workflows; catch
    it at compile time rather than letting import_jobs return a 500."""
    text = """
collection: T
playbooks:
  - name: Same Name
    steps:
      - id: start
        type: start
  - name: Same Name
    steps:
      - id: start
        type: start
"""
    r = compile_yaml(text, db_path)
    assert not r.ok
    assert any("duplicate playbook name" in e.message for e in r.errors)


def test_cross_collection_iri_passthrough(db_path):
    """When `workflowReference` IRI is given directly, no validation against
    a local target is attempted (it's a cross-collection ref)."""
    text = """
collection: T
playbooks:
  - name: Parent
    steps:
      - id: start
        type: start
        next: c
      - id: c
        type: workflow_reference
        arguments:
          workflowReference: /api/3/workflows/00000000-0000-0000-0000-000000000000
          arguments: {anything: goes}
"""
    r = compile_yaml(text, db_path)
    assert r.ok, [e.to_dict() for e in r.errors]
