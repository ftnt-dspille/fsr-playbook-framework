"""Unit tests for cross-collection target: UUID resolution (Enhancement #5)."""
from fsr_playbooks._db import default_db_path
from fsr_playbooks.compiler import compile_yaml

DB = default_db_path()

# A valid FortiSOAR UUID shape.
REMOTE_UUID = "bff221c6-1a9b-4486-8180-6841e7a59f34"


def _compile(target_value: str):
    y = f"""
collection: Test
playbooks:
- name: Caller
  is_active: true
  steps:
  - {{name: Start, type: start, next: Call}}
  - {{name: Call, type: workflow_reference, target: {target_value}}}
"""
    return compile_yaml(y, DB)


def _get_call_step(result):
    coll = result.fsr_json["data"][0]
    wf = coll["workflows"][0]
    for s in wf.get("steps", []):
        if s.get("name") == "Call":
            return s
    return None


def test_cross_collection_uuid_target_compiles():
    """A UUID target that isn't in the local collection compiles without error."""
    r = _compile(REMOTE_UUID)
    assert r.ok, f"expected OK, got errors: {[e.message for e in r.errors]}"


def test_cross_collection_uuid_target_emits_iri():
    """The emitted workflowReference is /api/3/workflows/<uuid>."""
    r = _compile(REMOTE_UUID)
    step = _get_call_step(r)
    assert step is not None
    args = step.get("arguments") or {}
    assert args.get("workflowReference") == f"/api/3/workflows/{REMOTE_UUID}"


def test_cross_collection_uuid_target_key_popped():
    """The friendly 'target' key is removed from the emitted JSON."""
    r = _compile(REMOTE_UUID)
    step = _get_call_step(r)
    assert step is not None
    args = step.get("arguments") or {}
    assert "target" not in args


def test_local_name_target_still_works():
    """A local in-collection name target still resolves via deterministic UUID."""
    y = """
collection: Test
playbooks:
- name: Caller
  is_active: true
  steps:
  - {name: Start, type: start, next: Call}
  - {name: Call, type: workflow_reference, target: Target}
- name: Target
  is_active: true
  steps:
  - {name: Start, type: start}
"""
    r = compile_yaml(y, DB)
    assert r.ok, f"expected OK, got errors: {[e.message for e in r.errors]}"
    step = _get_call_step(r)
    assert step is not None
    args = step.get("arguments") or {}
    ref = args.get("workflowReference", "")
    assert ref.startswith("/api/3/workflows/")
    assert "target" not in args


def test_unknown_name_target_still_errors():
    """A non-UUID, non-local-name target still raises the 'not found' error."""
    r = _compile("Nonexistent Playbook")
    assert not r.ok
    assert any("not found in this collection" in e.message for e in r.errors)


def test_uppercase_uuid_accepted():
    """UUIDs with uppercase hex are accepted (FortiSOAR emits mixed case)."""
    r = _compile(REMOTE_UUID.upper())
    assert r.ok, f"expected OK, got errors: {[e.message for e in r.errors]}"
    step = _get_call_step(r)
    assert step is not None
    args = step.get("arguments") or {}
    # Emitted IRI should use the original case
    assert args.get("workflowReference") == f"/api/3/workflows/{REMOTE_UUID.upper()}"
