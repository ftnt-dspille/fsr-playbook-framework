from compiler.errors import ErrorCode
from compiler.parser import parse_yaml


def test_minimal_ok():
    coll, errs = parse_yaml(
        "collection: A\nplaybooks:\n  - name: P\n    steps:\n      - id: s\n        type: start\n"
    )
    assert errs == []
    assert coll is not None
    assert coll.name == "A"
    assert coll.playbooks[0].steps[0].id == "s"


def test_yaml_syntax_error():
    coll, errs = parse_yaml("collection: A\n  bad indent: x\n")
    assert coll is None
    assert any(e.code is ErrorCode.PARSE_ERROR for e in errs)


def test_missing_collection_name():
    coll, errs = parse_yaml("playbooks:\n  - name: P\n    steps:\n      - id: s\n        type: start\n")
    assert coll is None
    assert any(e.code is ErrorCode.MISSING_FIELD and e.path == "collection" for e in errs)


def test_missing_playbooks():
    coll, errs = parse_yaml("collection: A\n")
    assert coll is None
    assert any(e.path == "playbooks" for e in errs)


def test_duplicate_step_id():
    text = """
collection: A
playbooks:
  - name: P
    steps:
      - id: s
        type: start
      - id: s
        type: set_variable
"""
    coll, errs = parse_yaml(text)
    assert coll is None
    assert any(e.code is ErrorCode.DUPLICATE_STEP_ID for e in errs)


def test_missing_step_id_or_type():
    text = """
collection: A
playbooks:
  - name: P
    steps:
      - type: start
      - id: x
"""
    coll, errs = parse_yaml(text)
    assert coll is None
    paths = {e.path for e in errs}
    assert "playbooks[0].steps[0].id" in paths
    assert "playbooks[0].steps[1].type" in paths


def test_branches_dict_required():
    text = """
collection: A
playbooks:
  - name: P
    steps:
      - id: s
        type: decision
        branches: not-a-dict
"""
    coll, errs = parse_yaml(text)
    assert coll is None
    assert any(e.code is ErrorCode.BAD_VALUE and "branches" in e.path for e in errs)
