"""Phase 2 (STATIC_TYPE_FLOW_PLAN) -- branch-local vars.<name> typing + scoping.

The walker now (a) infers each set_variable output's type from its value using
the live Phase 1b coercion matrix and carries it per branch in `var_env`, and
(b) emits branch-scoped scoping diagnostics that the whole-playbook
validator._check_undefined_vars cannot: read-before-define, defined-on-other-
branch, and loop-var-outside-for_each. The never-defined-anywhere case stays
with the validator (disjoint -- no double report).
"""
from fsr_playbooks._db import default_db_path
from fsr_playbooks.compiler import compile_yaml
from fsr_playbooks.compiler.typed_walker import (
    _infer_literal_shape,
    walk_playbook,
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


# ---- Tier 3.5: terminal-type inference for set_variable Jinja values --------

def _walk_with_conn(text: str):
    """Walk with a DB connection so infer_terminal_observed_type is active."""
    import sqlite3
    cres = compile_yaml(text, DB)
    assert cres.ir is not None
    conn = sqlite3.connect(str(DB))
    try:
        return walk_playbook(cres.ir, conn=conn)
    finally:
        conn.close()


_TIER35_TYPED = """
collection: t
playbooks:
  - name: Tier35
    steps:
      - name: start
        type: start
        next: SV
      - name: SV
        type: set_variable
        next: End
        vars:
          count: "{{ vars.steps.start.input.records | length }}"
          label: "{{ vars.steps.start.input.records[0].source }}"
          number: "{{ '42' | int }}"
          flagged: "{{ 'true' | bool }}"
          textified: "{{ 42 | string }}"
"""


def test_set_variable_jinja_terminal_type_inferred():
    """With a DB connection, pure-Jinja values with known terminal
    filters are typed by their filter's declared output type, not 'any'."""
    w = _walk_with_conn(_TIER35_TYPED)
    env = w.branches[0].var_env
    # | length → integer
    assert env["count"]["type"] == "int", env["count"]
    # | int → integer
    assert env["number"]["type"] == "int", env["number"]
    # | bool → boolean
    assert env["flagged"]["type"] == "bool", env["flagged"]
    # | string → string
    assert env["textified"]["type"] == "str", env["textified"]
    # No terminal filter → still 'any' (we don't claim the shape of a
    # bare vars.steps.x.y reference -- that's the walker's job)
    assert env["label"]["type"] == "any", env["label"]


def test_set_variable_jinja_without_conn_degrades_to_any():
    """Without a DB connection, Jinja values degrade to 'any' -- the
    filter signature table is unavailable."""
    w = _walk(_TIER35_TYPED)
    env = w.branches[0].var_env
    assert env["count"]["type"] == "any"
    assert env["number"]["type"] == "any"


def test_type_mismatch_through_set_variable_indirection():
    """A set_variable producing int (via | length) fed into a connector
    param typed ipv4 must fire type_mismatch -- the core Tier 3.5 use case.
    Uses a mock param_type_fn since the slim DB may not have the
    connector's param types."""
    text = """
collection: t
playbooks:
  - name: Mismatch
    steps:
      - name: start
        type: start
        next: SV
      - name: SV
        type: set_variable
        next: Call
        vars:
          count: "{{ vars.steps.start.input.records | length }}"
      - name: Call
        type: connector
        connector: virustotal
        operation: query_ip
        params:
          ip: "{{ vars.count }}"
        next: End
      - name: End
        type: end
"""
    import sqlite3
    cres = compile_yaml(text, DB)
    assert cres.ir is not None
    conn = sqlite3.connect(str(DB))
    try:
        def mock_param_type(connector, op, param):
            if connector == "virustotal" and op == "query_ip" and param == "ip":
                return "ipv4"
            return None
        w = walk_playbook(cres.ir, conn=conn, param_type_fn=mock_param_type)
    finally:
        conn.close()
    mismatches = [d for d in w.diagnostics if d.code == "type_mismatch"]
    assert len(mismatches) == 1, [d.code for d in w.diagnostics]
    d = mismatches[0]
    assert d.step == "call"
    assert "ipv4" in d.message
    assert "int" in d.message


def test_type_match_through_set_variable_indirection_no_false_positive():
    """A set_variable producing string (via | string) fed into a text
    param must NOT fire -- confirming the check isn't over-firing."""
    text = """
collection: t
playbooks:
  - name: Match
    steps:
      - name: start
        type: start
        next: SV
      - name: SV
        type: set_variable
        next: Call
        vars:
          label: "{{ 42 | string }}"
      - name: Call
        type: connector
        connector: virustotal
        operation: query_ip
        params:
          ip: "{{ vars.label }}"
        next: End
      - name: End
        type: end
"""
    w = _walk_with_conn(text)
    mismatches = [d for d in w.diagnostics if d.code == "type_mismatch"]
    assert mismatches == [], [d.message for d in mismatches]


def test_per_step_shape_carries_inferred_types():
    """_synth_set_variable_shape (used by per_step_shapes) should also
    carry inferred types, not just var_env."""
    w = _walk_with_conn(_TIER35_TYPED)
    sv_shape = w.per_step_shapes.get("sv")
    assert sv_shape is not None
    keys = sv_shape.get("keys", {})
    assert keys.get("count", {}).get("type") == "int", keys.get("count")
    assert keys.get("label", {}).get("type") == "any", keys.get("label")
