"""
Coverage for `_path_to_line` — the YAML error-path → line resolver.

This pins the contract that previously regressed: errors with paths
like `playbooks[0].steps[0].type` must surface on the actual `type:`
line inside the step, not on the step header (`- name: ...`).
"""
from backend.routes.yaml_routes import _path_to_line


YAML_WITH_STEPS = """\
collection: "test"
description: ""
playbooks:
- name: "test"
  description: ""
  is_active: true
  debug: true
  steps:
  - name: start
    type: star
  - name: second
    type: set_variable
    arguments:
      arg_list:
      - name: x
"""
# Line numbers (1-based) within YAML_WITH_STEPS:
# 1  collection
# 2  description
# 3  playbooks:
# 4  - name: "test"
# 5    description
# 6    is_active
# 7    debug
# 8    steps:
# 9    - name: start
# 10     type: star
# 11   - name: second
# 12     type: set_variable
# 13     arguments:
# 14       arg_list:
# 15       - name: x


def test_empty_path_returns_1():
    assert _path_to_line("", "") == 1
    assert _path_to_line(YAML_WITH_STEPS, "") == 1


def test_collection_path():
    assert _path_to_line(YAML_WITH_STEPS, "collection") == 1


def test_playbooks_path():
    assert _path_to_line(YAML_WITH_STEPS, "playbooks") == 3


def test_step_header_when_no_trailing_key():
    # Plain step index lands on the step's `- name:` line.
    assert _path_to_line(YAML_WITH_STEPS, "playbooks[0].steps[0]") == 9
    assert _path_to_line(YAML_WITH_STEPS, "playbooks[0].steps[1]") == 11


def test_step_dot_type_resolves_to_type_key_line():
    # Regression: previously returned the step header line (9), now
    # finds the actual `type:` line.
    assert _path_to_line(YAML_WITH_STEPS, "playbooks[0].steps[0].type") == 10
    assert _path_to_line(YAML_WITH_STEPS, "playbooks[0].steps[1].type") == 12


def test_step_dot_arguments_resolves_to_arguments_key_line():
    assert _path_to_line(
        YAML_WITH_STEPS, "playbooks[0].steps[1].arguments"
    ) == 13


def test_key_lookup_stays_within_step_block():
    # Looking for `name:` inside step 1 must NOT walk into step 1's
    # children or hop into step 2 — it should land on step 1's own
    # `name: second` line.
    assert _path_to_line(YAML_WITH_STEPS, "playbooks[0].steps[1].name") == 11


def test_missing_key_falls_back_to_step_header():
    # Key the step doesn't actually have → fallback to step header.
    assert _path_to_line(
        YAML_WITH_STEPS, "playbooks[0].steps[0].for_each"
    ) == 9


def test_nested_indices_dont_get_mistaken_for_step_index():
    # Paths with trailing indices like ...conditions[0] should still
    # extract steps[N], not match the trailing index.
    yaml = """\
collection: "x"
playbooks:
- name: p
  steps:
  - name: a
    type: decision
    arguments:
      conditions:
      - op: equals
"""
    # The error targets a condition inside step 0 — still must
    # resolve based on steps[0], not conditions[0].
    line = _path_to_line(
        yaml, "playbooks[0].steps[0].arguments.conditions[0]"
    )
    # Should land on the step header (5) since `conditions[0]` isn't
    # itself a top-level key of the step.
    assert line == 5
