"""Unit tests for Tier 3 first slice: jinja_typing terminal inference
and the resolver compatibility helpers in connector_args."""
from __future__ import annotations

import sqlite3

import pytest

from fsr_playbooks.compiler.jinja_typing import (
    extract_pure_jinja, terminal_filter, infer_terminal_observed_type,
)
from fsr_playbooks.compiler.resolver.connector_args import (
    _param_target_observed_type, _types_compatible,
)


# --------------------------------------------------------------------- helpers


def _macros_conn() -> sqlite3.Connection:
    """Tiny in-memory jinja_macros fixture matching the live store's
    column shape — only the columns the inferrer reads."""
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE jinja_macros (
            name TEXT PRIMARY KEY,
            input_type_hint TEXT,
            output_type_declared TEXT
        )""")
    conn.executemany(
        "INSERT INTO jinja_macros (name, input_type_hint, output_type_declared) "
        "VALUES (?,?,?)",
        [("int",    None,      "integer"),
         ("float",  None,      "number"),
         ("string", None,      "string"),
         ("length", None,      "integer"),
         ("upper",  "string",  "string"),
         ("list",   None,      "list"),
         ("tojson", None,      "string"),
         ("first",  "list",    "any"),
         ("default", None,     "any")],
    )
    conn.commit()
    return conn


# --------------------------------------------------------------------- pure-jinja


@pytest.mark.parametrize("value,expected", [
    ("{{ x | int }}", "x | int"),
    ("  {{   foo.bar   }}  ", "foo.bar"),
    ("{{\n  multi\n  line\n}}", "multi\n  line"),
    ("{{ x }} extra", None),
    ("prefix {{ x }}", None),
    ("static", None),
    ("", None),
    (None, None),
    (42, None),
])
def test_extract_pure_jinja(value, expected):
    assert extract_pure_jinja(value) == expected


@pytest.mark.parametrize("expr,expected", [
    ("vars.x | int", "int"),
    ("vars.x | int | string", "string"),
    ("vars.x", None),
    ("foo.bar.baz", None),
    ("", None),
])
def test_terminal_filter(expr, expected):
    assert terminal_filter(expr) == expected


# --------------------------------------------------------------------- inferrer


def test_infer_returns_int_for_int_filter():
    assert infer_terminal_observed_type("{{ x | int }}", _macros_conn()) == "int"


def test_infer_returns_str_for_string_filter():
    assert infer_terminal_observed_type(
        "{{ x | upper | string }}", _macros_conn()) == "str"


def test_infer_returns_int_for_length_filter():
    assert infer_terminal_observed_type(
        "{{ items | length }}", _macros_conn()) == "int"


def test_infer_returns_json_array_for_list_filter():
    assert infer_terminal_observed_type(
        "{{ x | list }}", _macros_conn()) == "json_array"


def test_infer_none_for_unknown_filter():
    assert infer_terminal_observed_type(
        "{{ x | unknown_zzz }}", _macros_conn()) is None


def test_infer_none_for_any_typed_filter():
    # `| default` is declared as `any` — we deliberately don't claim a
    # type so the resolver doesn't false-positive on common patterns.
    assert infer_terminal_observed_type(
        "{{ x | default(0) }}", _macros_conn()) is None


def test_infer_none_for_no_filters():
    # A bare `{{ vars.x }}` is the walker's job — not this module's.
    assert infer_terminal_observed_type(
        "{{ vars.x }}", _macros_conn()) is None


def test_infer_none_for_mixed_text():
    assert infer_terminal_observed_type(
        "prefix-{{ x | int }}-suffix", _macros_conn()) is None


def test_infer_none_for_non_strings():
    conn = _macros_conn()
    assert infer_terminal_observed_type(None, conn) is None
    assert infer_terminal_observed_type(42, conn) is None
    assert infer_terminal_observed_type([], conn) is None


def test_infer_survives_missing_macros_table():
    """A DB without `jinja_macros` should yield None, not raise — for
    filters that aren't in the hand-curated map. Curated filters
    short-circuit before the DB is consulted, which is intentional."""
    empty = sqlite3.connect(":memory:")
    # `unknown_zzz` isn't in either source.
    assert infer_terminal_observed_type(
        "{{ x | unknown_zzz }}", empty) is None
    # Curated entries still resolve even without the DB:
    assert infer_terminal_observed_type(
        "{{ x | int }}", empty) == "int"


# --------------------------------------------------------------------- target


@pytest.mark.parametrize("widget,observed,expected", [
    ("integer", None, "int"),
    ("intger", None, "int"),
    ("decimal", None, "float"),
    ("checkbox", None, "bool"),
    ("json", None, "json_object"),
    ("text", "ipv4", "ipv4"),
    ("text", None, None),       # unprobed text param: no claim
    ("textarea", "str", "str"),
    ("unknown_widget", "ipv4", None),
])
def test_param_target_observed_type(widget, observed, expected):
    assert _param_target_observed_type(widget, observed) == expected


# --------------------------------------------------------------------- compat


@pytest.mark.parametrize("inferred,target,expected", [
    ("int", "int", True),
    ("int", "float", True),   # FSR float fields accept ints
    ("int", "str", True),
    ("str", "int", False),    # would catch `| string` into integer widget
    ("str", "ipv4", True),    # `| string` could be carrying a valid ip
    ("json_array", "json_object", False),
    ("bool", "int", False),
    ("float", "bool", False),
])
def test_types_compatible(inferred, target, expected):
    assert _types_compatible(inferred, target) is expected


# --------------------------------------------------------------------- curated


def test_hand_curated_overrides_db():
    """`int` and similar live in the DB, but `b64encode` only exists in
    the hand-curated map. Both should resolve to the same shape via
    `filter_signature`."""
    from fsr_playbooks.compiler.jinja_typing import filter_signature
    conn = _macros_conn()
    assert filter_signature("b64encode", conn) == (None, "string")
    # And the curated entry wins even when the DB disagrees:
    conn.execute(
        "INSERT INTO jinja_macros (name, input_type_hint, output_type_declared) "
        "VALUES ('b64encode', 'foo', 'integer')")
    assert filter_signature("b64encode", conn) == (None, "string")


def test_hand_curated_long_tail():
    """Spot-check several formerly-NULL macros now have signatures."""
    from fsr_playbooks.compiler.jinja_typing import _HAND_CURATED
    for name in ("b64encode", "json2html", "dict2items", "items2dict",
                 "fromIRI", "ipaddr", "from_yaml_all", "human_readable",
                 "bool", "count", "json_query"):
        assert name in _HAND_CURATED


# --------------------------------------------------------------------- chain


def test_validate_chain_ok_when_short():
    from fsr_playbooks.compiler.jinja_typing import validate_chain
    # No filters: nothing to validate.
    assert validate_chain("vars.x", _macros_conn()) is None
    # One filter: still nothing.
    assert validate_chain("vars.x | int", _macros_conn()) is None


def test_validate_chain_ok_compatible():
    from fsr_playbooks.compiler.jinja_typing import validate_chain
    # int -> string consumer is fine because string accepts anything.
    assert validate_chain("vars.x | int | tojson", _macros_conn()) is None


def test_validate_chain_flags_mismatch():
    from fsr_playbooks.compiler.jinja_typing import validate_chain
    # `length` produces integer; `upper` expects string.
    bad = validate_chain("vars.x | length | upper", _macros_conn())
    assert bad is not None
    prod, cons, want = bad
    assert prod == "length" and cons == "upper" and want == "string"


def test_validate_chain_silence_on_unknown():
    from fsr_playbooks.compiler.jinja_typing import validate_chain
    # `first` has output_type=any → no mismatch claim downstream.
    assert validate_chain("vars.x | first | int", _macros_conn()) is None


# --------------------------------------------------------------------- walker


def _walk(yaml_text: str):
    """Compile a playbook and run the typed walker. Returns the
    diagnostic codes (deduped) so tests can assert presence/absence."""
    import sys
    sys.path.insert(0, "tooling")
    from fsr_playbooks.compiler import parse_yaml
    from fsr_playbooks.compiler.typed_walker import walk_playbook
    coll, _errs = parse_yaml(yaml_text)
    assert coll is not None, "parse failed in test fixture"
    walk = walk_playbook(coll)
    return [d.code for d in walk.diagnostics]


def test_walker_flags_bad_chain_in_set_variable():
    codes = _walk("""
collection: T
playbooks:
  - name: pb
    is_active: true
    steps:
      - type: start
        name: Start
        next: SetIt
      - type: set_variable
        name: SetIt
        vars:
          oops: "{{ vars.input.foo | int | upper }}"
""")
    assert "bad_jinja_filter_chain" in codes


def test_walker_flags_bad_chain_in_for_each():
    codes = _walk("""
collection: T
playbooks:
  - name: pb
    is_active: true
    steps:
      - type: start
        name: Start
        next: Loop
      - type: set_variable
        name: Loop
        for_each:
          item: "{{ records | length | upper }}"
          parallel: false
        vars:
          x: "{{ vars.item }}"
""")
    assert "bad_jinja_filter_chain" in codes


def test_walker_silent_on_valid_jinja():
    codes = _walk("""
collection: T
playbooks:
  - name: pb
    is_active: true
    steps:
      - type: start
        name: Start
        next: SetIt
      - type: set_variable
        name: SetIt
        vars:
          n:  "{{ vars.input.items | length }}"
          up: "{{ vars.input.name | upper }}"
""")
    assert "bad_jinja_filter_chain" not in codes


def test_walker_does_not_double_fire_across_branches():
    """A step shared by two decision branches must not produce the
    same chain diagnostic twice."""
    codes = _walk("""
collection: T
playbooks:
  - name: pb
    is_active: true
    steps:
      - type: start
        name: Start
        next: Gate
      - type: decision
        name: Gate
        conditions:
          - label: "yes"
            condition: "{{ vars.input.flag == True }}"
            next: BadStep
          - label: "no"
            condition: "{{ vars.input.flag == False }}"
            next: BadStep
      - type: set_variable
        name: BadStep
        vars:
          oops: "{{ vars.x | int | upper }}"
""")
    assert codes.count("bad_jinja_filter_chain") == 1
