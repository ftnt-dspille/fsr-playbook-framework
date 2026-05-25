"""Unit tests for Tier 3 first slice: jinja_typing terminal inference
and the resolver compatibility helpers in connector_args."""
from __future__ import annotations

import sqlite3

import pytest

from compiler.jinja_typing import (
    extract_pure_jinja, terminal_filter, infer_terminal_observed_type,
)
from compiler.resolver.connector_args import (
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
            output_type_declared TEXT
        )""")
    conn.executemany(
        "INSERT INTO jinja_macros (name, output_type_declared) VALUES (?,?)",
        [("int", "integer"), ("float", "number"), ("string", "string"),
         ("length", "integer"), ("upper", "string"), ("list", "list"),
         ("tojson", "string"), ("first", "any"), ("default", "any")],
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
    """A DB without `jinja_macros` should yield None, not raise."""
    empty = sqlite3.connect(":memory:")
    assert infer_terminal_observed_type("{{ x | int }}", empty) is None


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
