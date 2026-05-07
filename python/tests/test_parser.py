from compiler.errors import ErrorCode
from compiler.parser import parse_yaml


def test_minimal_ok():
    coll, errs = parse_yaml(
        "collection: A\nplaybooks:\n  - name: P\n    steps:\n      - name: s\n        type: start\n"
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
    coll, errs = parse_yaml("playbooks:\n  - name: P\n    steps:\n      - name: s\n        type: start\n")
    assert coll is None
    assert any(e.code is ErrorCode.MISSING_FIELD and e.path == "collection" for e in errs)


def test_missing_playbooks():
    coll, errs = parse_yaml("collection: A\n")
    assert coll is None
    assert any(e.path == "playbooks" for e in errs)


def test_duplicate_step_name():
    text = """
collection: A
playbooks:
  - name: P
    steps:
      - name: s
        type: start
      - name: s
        type: set_variable
"""
    coll, errs = parse_yaml(text)
    assert coll is None
    assert any(e.code is ErrorCode.DUPLICATE_STEP_ID for e in errs)


def test_missing_step_name_or_type():
    text = """
collection: A
playbooks:
  - name: P
    steps:
      - type: start
      - name: x
"""
    coll, errs = parse_yaml(text)
    assert coll is None
    paths = {e.path for e in errs}
    assert "playbooks[0].steps[0].name" in paths
    assert "playbooks[0].steps[1].type" in paths


def test_id_derived_from_name():
    text = """
collection: A
playbooks:
  - name: P
    steps:
      - type: start
        name: "Start Here"
        next: greater_than_10
      - type: end
        name: "Greater Than 10"
"""
    coll, errs = parse_yaml(text)
    assert coll is not None, errs
    ids = [s.id for s in coll.playbooks[0].steps]
    names = [s.name for s in coll.playbooks[0].steps]
    assert ids == ["start_here", "greater_than_10"]
    assert names == ["Start Here", "Greater Than 10"]


def test_id_collision_from_slug():
    text = """
collection: A
playbooks:
  - name: P
    steps:
      - type: start
        name: "Pick One"
      - type: end
        name: "pick-one"
"""
    coll, errs = parse_yaml(text)
    assert coll is None
    assert any("slugify to the same id" in e.message for e in errs)


def test_next_can_reference_name_verbatim():
    text = """
collection: A
playbooks:
  - name: P
    steps:
      - type: start
        name: Start
        next: Greater Than 10
      - type: end
        name: Greater Than 10
"""
    coll, errs = parse_yaml(text)
    assert coll is not None, errs
    s = coll.playbooks[0].steps[0]
    assert s.next == "greater_than_10"


def test_decision_step_level_conditions():
    text = """
collection: A
playbooks:
  - name: P
    steps:
      - type: start
        name: Start
        next: check
      - type: decision
        name: check
        conditions:
          - display: "Yes"
            when: "{{ true }}"
            next: Greater Than 10
          - display: "Else"
            default: true
            next: Greater Than 10
      - type: end
        name: Greater Than 10
"""
    coll, errs = parse_yaml(text)
    assert coll is not None, errs
    decision = coll.playbooks[0].steps[1]
    conds = decision.arguments["conditions"]
    # display→option, when→condition translation
    assert conds[0]["option"] == "Yes"
    assert conds[0]["condition"] == "{{ true }}"
    assert conds[1].get("default") is True
    # inline next resolved through the name map
    assert conds[0]["next"] == "greater_than_10"
    assert conds[1]["next"] == "greater_than_10"


def test_legacy_id_rejected():
    text = """
collection: A
playbooks:
  - name: P
    steps:
      - id: s
        type: start
"""
    coll, errs = parse_yaml(text)
    assert coll is None
    assert any("step.id is not allowed" in e.message for e in errs)


def test_legacy_branches_map_rejected():
    text = """
collection: A
playbooks:
  - name: P
    steps:
      - type: decision
        name: D
        branches:
          yes: target
"""
    coll, errs = parse_yaml(text)
    assert coll is None
    assert any("step-level `branches:`" in e.message for e in errs)


def test_legacy_arguments_conditions_rejected():
    text = """
collection: A
playbooks:
  - name: P
    steps:
      - type: decision
        name: D
        arguments:
          conditions:
            - option: x
              condition: "{{ true }}"
"""
    coll, errs = parse_yaml(text)
    assert coll is None
    assert any("`conditions:` at the step level" in e.message for e in errs)


def test_legacy_set_variable_arguments_rejected():
    text = """
collection: A
playbooks:
  - name: P
    steps:
      - type: set_variable
        name: P
        arguments:
          x: 1
"""
    coll, errs = parse_yaml(text)
    assert coll is None
    assert any("top-level `vars:` mapping" in e.message for e in errs)


def test_stop_step_type_auto_rewritten_to_end():
    """`stop` and `end` are equivalent (both map to no_op); the parser
    rewrites `stop` → `end` and emits a warning rather than failing."""
    text = """
collection: A
playbooks:
  - name: P
    steps:
      - type: stop
        name: bye
"""
    coll, errs = parse_yaml(text)
    assert coll is not None
    assert coll.playbooks[0].steps[0].type == "end"
    assert any(e.severity == "warning" and "auto-rewritten" in e.message
               for e in errs)


def test_decision_step_level_next_warns_and_synthesizes():
    """Bare step-level `next:` on a Decision is auto-converted to an
    `Else` default condition by the emitter — parser emits a warning
    instead of hard-failing."""
    text = """
collection: A
playbooks:
  - name: P
    steps:
      - type: decision
        name: D
        next: somewhere
        conditions:
          - display: "Yes"
            when: "{{ true }}"
            next: somewhere
"""
    coll, errs = parse_yaml(text)
    assert coll is not None
    warnings = [e for e in errs if e.severity == "warning"]
    assert any("auto-synthesizing" in w.message for w in warnings)
    assert not any(e.severity != "warning" for e in errs)


def test_uid_rejected():
    text = """
collection: A
playbooks:
  - name: P
    uid: foo
    steps:
      - type: start
        name: s
"""
    coll, errs = parse_yaml(text)
    assert coll is None
    assert any("playbook.uid is not allowed" in e.message for e in errs)
