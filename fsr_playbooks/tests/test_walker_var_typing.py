"""Phase 2 (STATIC_TYPE_FLOW_PLAN) — branch-local vars.<name> typing + scoping.

The walker now (a) infers each set_variable output's type from its value using
the live Phase 1b coercion matrix and carries it per branch in `var_env`, and
(b) emits branch-scoped scoping diagnostics that the whole-playbook
validator._check_undefined_vars cannot: read-before-define, defined-on-other-
branch, and loop-var-outside-for_each. The never-defined-anywhere case stays
with the validator (disjoint — no double report).
"""
from fsr_playbooks._db import default_db_path
from fsr_playbooks.compiler import compile_yaml
from fsr_playbooks.compiler.typed_walker import (
    _infer_literal_shape, walk_playbook,
)

# Resolve via the standard order so CI falls back to the packaged slim DB.
DB = default_db_path()


def _walk(text: str):
    cres = compile_yaml(text, DB)
    assert cres.ir is not None
    return walk_playbook(cres.ir)


# ---- Phase 1b classifier (unit) -------------------------------------------

def test_literal_classifier_matches_matrix():
    sc = lambda s: _infer_literal_shape(s)["type"]  # noqa: E731
    assert sc("False") == "boolean"
    assert sc("true") == "boolean"
    assert sc("TRUE") == "string"          # all-caps NOT a bool token
    assert sc("123") == "integer"
    assert sc("007") == "string"           # leading zero
    assert sc(" 123 ") == "integer"        # ws-padded
    assert sc("0x1f") == "string"          # hex stays string
    assert sc("1.5") == "float"
    assert sc("1e3") == "float"
    assert sc("null") == "null"
    assert sc("None") == "null"
    assert sc("2026-06-06") == "string"    # dates stay string
    assert sc("hello") == "string"
    # jinja → degrade to any (render-then-recoerce not statically known)
    assert sc("{{ x | int }}") == "any"
    # native YAML values
    assert _infer_literal_shape(42)["type"] == "integer"
    assert _infer_literal_shape(True)["type"] == "boolean"
    assert _infer_literal_shape([1, 2])["kind"] == "list"
    assert _infer_literal_shape({"k": 1})["kind"] == "object"


# ---- var_env typing per branch --------------------------------------------

_TYPED = """
collection: t
playbooks:
  - name: Typed
    steps:
      - name: start
        type: start
        next: Set
      - name: Set
        type: set_variable
        vars:
          n: "123"
          flag: "true"
          items_list: "[1, 2, 3]"
          label: "hello"
"""


def test_var_env_carries_inferred_types():
    w = _walk(_TYPED)
    env = w.branches[0].var_env
    assert env["n"]["type"] == "integer"
    assert env["flag"]["type"] == "boolean"
    assert env["items_list"]["kind"] == "list"
    assert env["label"]["type"] == "string"


# ---- read-before-define ----------------------------------------------------

_READ_BEFORE = """
collection: t
playbooks:
  - name: ReadBefore
    steps:
      - name: start
        type: start
        next: Use It
      - name: Use It
        type: set_variable
        next: Define It
        vars:
          echo: "{{ vars.later }}"
      - name: Define It
        type: set_variable
        vars:
          later: "value"
"""


def test_read_before_definition_flagged():
    w = _walk(_READ_BEFORE)
    codes = [d.code for d in w.diagnostics]
    assert "var_read_before_definition" in codes
    assert all(d.severity == "warning"
               for d in w.diagnostics if d.code == "var_read_before_definition")


# ---- defined on other branch ----------------------------------------------

_OTHER_BRANCH = """
collection: t
playbooks:
  - name: OtherBranch
    steps:
      - name: start
        type: start
        next: Decide
      - name: Decide
        type: decision
        conditions:
          - display: hi
            when: "{{ 1 == 1 }}"
            next: Set On A
          - display: Else
            default: true
            next: Read On B
      - name: Set On A
        type: set_variable
        vars:
          only_a: "alpha"
      - name: Read On B
        type: set_variable
        vars:
          echo: "{{ vars.only_a }}"
"""


def test_defined_other_branch_flagged():
    w = _walk(_OTHER_BRANCH)
    hits = [d for d in w.diagnostics if d.code == "var_defined_other_branch"]
    assert hits, "ref to a sibling-arm var should be flagged"
    assert any(d.step == "read_on_b" for d in hits)


# ---- loop var outside for_each --------------------------------------------

_LOOP_VAR = """
collection: t
playbooks:
  - name: LoopVar
    steps:
      - name: start
        type: start
        next: Use Item
      - name: Use Item
        type: set_variable
        vars:
          x: "{{ vars.item }}"
"""


def test_loop_var_outside_for_each_flagged():
    w = _walk(_LOOP_VAR)
    assert any(d.code == "loop_var_outside_for_each" for d in w.diagnostics)


# ---- clean cases: no false positives --------------------------------------

_CLEAN = """
collection: t
playbooks:
  - name: Clean
    steps:
      - name: start
        type: start
        next: Define
      - name: Define
        type: set_variable
        next: Use
        vars:
          a: "alpha"
      - name: Use
        type: set_variable
        vars:
          b: "{{ vars.a }}"
"""


def test_predecessor_var_clean():
    w = _walk(_CLEAN)
    novel = {"var_read_before_definition", "var_defined_other_branch",
             "loop_var_outside_for_each"}
    assert not [d for d in w.diagnostics if d.code in novel]


def test_never_defined_left_to_validator():
    # vars.ghost is never defined anywhere → the WALKER must stay silent
    # (validator._check_undefined_vars owns this whole-playbook case).
    text = _CLEAN.replace('"{{ vars.a }}"', '"{{ vars.ghost }}"')
    w = _walk(text)
    novel = {"var_read_before_definition", "var_defined_other_branch"}
    assert not [d for d in w.diagnostics if d.code in novel]
