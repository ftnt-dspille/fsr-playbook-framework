from fsr_playbooks.compiler.errors import ErrorCode
from fsr_playbooks.compiler.parser import parse_yaml


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


def test_missing_collection_name_defaults_to_studio_target():
    """Omitting both `collection:` and `into_collection:` now defaults
    to per-playbook mode with the studio bucket as the target. This is
    intentional — see preflight/per-playbook push docs."""
    coll, errs = parse_yaml("playbooks:\n  - name: P\n    steps:\n      - name: s\n        type: start\n")
    assert coll is not None
    assert coll.name == "00 - FSR Studio"
    assert coll.target_mode == "per_playbook"
    assert not any(e.severity != "warning" for e in errs)


def test_both_collection_keys_rejected():
    """Setting BOTH `collection:` (wrap mode) and `into_collection:`
    (per-playbook mode) is an authoring error — the modes are mutually
    exclusive."""
    text = (
        "collection: A\n"
        "into_collection: B\n"
        "playbooks:\n  - name: P\n    steps:\n      - name: s\n        type: start\n"
    )
    coll, errs = parse_yaml(text)
    assert coll is None
    assert any(e.code is ErrorCode.BAD_VALUE for e in errs)


def test_into_collection_sets_per_playbook_mode():
    text = (
        "into_collection: My Shared Bucket\n"
        "playbooks:\n  - name: P\n    steps:\n      - name: s\n        type: start\n"
    )
    coll, errs = parse_yaml(text)
    assert coll is not None
    assert coll.name == "My Shared Bucket"
    assert coll.target_mode == "per_playbook"


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


def test_priority_high_parses():
    coll, errs = parse_yaml(
        "collection: A\nplaybooks:\n  - name: P\n    priority: High\n"
        "    steps:\n      - name: s\n        type: start\n"
    )
    assert coll is not None
    assert errs == []
    assert coll.playbooks[0].priority == "High"


def test_priority_case_insensitive():
    coll, errs = parse_yaml(
        "collection: A\nplaybooks:\n  - name: P\n    priority: high\n"
        "    steps:\n      - name: s\n        type: start\n"
    )
    assert coll is not None
    assert coll.playbooks[0].priority == "High"


def test_priority_unknown_name_captured_at_parse():
    # The parser just captures the name; validation/resolution is the
    # resolver's job (it owns the DB). So an unknown name parses cleanly here.
    coll, errs = parse_yaml(
        "collection: A\nplaybooks:\n  - name: P\n    priority: Bogus\n"
        "    steps:\n      - name: s\n        type: start\n"
    )
    assert coll is not None
    assert coll.playbooks[0].priority == "Bogus"
    assert errs == []


# --- for_each loop max-parallel cap (FSR 8.0 concurrency level) ---------------

def _loop_for_each(max_parallel_line: str):
    """Parse a one-step parallel loop carrying the given cap line; return (for_each, errs)."""
    text = (
        "collection: A\n"
        "playbooks:\n"
        "  - name: P\n"
        "    steps:\n"
        "      - name: loop\n"
        "        type: create_record\n"
        "        for_each:\n"
        "          item: \"{{ vars.items }}\"\n"
        "          parallel: true\n"
        f"{max_parallel_line}"
        "        arguments:\n"
        "          module: alerts\n"
    )
    coll, errs = parse_yaml(text)
    fe = coll.playbooks[0].steps[0].for_each if coll else None
    return fe, errs


def test_for_each_max_parallel_emits_concurrency_pair():
    fe, errs = _loop_for_each("          max_parallel: 3\n")
    assert not any(e.severity != "warning" for e in errs)
    assert fe["concurrency"] is True
    assert fe["concurrencyCount"] == 3
    assert fe["parallel"] is True


def test_for_each_concurrency_count_alias():
    fe, errs = _loop_for_each("          concurrency_count: 4\n")
    assert fe["concurrency"] is True
    assert fe["concurrencyCount"] == 4


def test_for_each_max_parallel_on_sequential_loop_warns():
    text = (
        "collection: A\n"
        "playbooks:\n"
        "  - name: P\n"
        "    steps:\n"
        "      - name: loop\n"
        "        type: create_record\n"
        "        for_each:\n"
        "          item: \"{{ vars.items }}\"\n"
        "          parallel: false\n"
        "          max_parallel: 3\n"
        "        arguments:\n"
        "          module: alerts\n"
    )
    coll, errs = parse_yaml(text)
    fe = coll.playbooks[0].steps[0].for_each
    # still emitted, but a warning flags that the cap is ignored on a sequential loop
    assert fe["concurrencyCount"] == 3
    assert any(e.severity == "warning" and "parallel" in e.message for e in errs)


def test_for_each_max_parallel_below_minimum_warns():
    fe, errs = _loop_for_each("          max_parallel: 1\n")
    assert fe["concurrencyCount"] == 1
    assert any(e.severity == "warning" and "minimum" in e.message for e in errs)


def test_for_each_max_parallel_non_integer_errors():
    fe, errs = _loop_for_each("          max_parallel: abc\n")
    assert any(e.code is ErrorCode.BAD_VALUE and e.severity != "warning" for e in errs)
