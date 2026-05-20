"""Unit tests for probes.probe_param_types — Tier 2.0/2.1.

Covers:
  * widget_to_observed_type: pure widget → type mapping + picklist
    fallback when options_json is present.
  * classify_error: regex classifier across all rule branches.
  * run_widget_only: end-to-end against an in-memory DB so the
    PRAGMA-based migration path is exercised.
"""
from __future__ import annotations

import sqlite3

import pytest

from probes import probe_param_types as ppt


# ---------------------------------------------------------------------------
# widget_to_observed_type
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("widget,expected", [
    ("integer", "int"),
    ("intger", "int"),          # store typo
    ("INTEGER", "int"),         # case-insensitive
    ("decimal", "float"),
    ("numeric", "float"),
    ("checkbox", "bool"),
    ("boolean", "bool"),
    ("password", "str"),
    ("json", "json_object"),
    ("date", "iso8601"),
    ("datetime", "iso8601"),
    ("textarea", "str"),
    ("text", None),             # the Tier-2 target — stays untyped
    ("uncatalogued_widget", None),
    (None, None),
])
def test_widget_mapping(widget, expected):
    assert ppt.widget_to_observed_type(widget, None) == expected


def test_options_json_collapses_to_picklist():
    # A text widget with options_json (free-text-with-suggestions) is a
    # picklist semantically — enum membership applies.
    assert ppt.widget_to_observed_type(
        "text", '["a","b"]') == "picklist"
    assert ppt.widget_to_observed_type(
        "select", '["x"]') == "picklist"


# ---------------------------------------------------------------------------
# classify_error — one assertion per rule branch
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("msg,expected_type", [
    ("ValueError: invalid literal for int() with base 10: 'xyz'", "int"),
    ("TypeError: int() argument must be a string, a bytes-like object or a real number, not 'list'", "int"),
    ("ValueError: could not convert string to float: 'abc'", "float"),
    ("TypeError: float() argument must be a string or a real number", "float"),
    ("Expected boolean, got 'maybe' — invalid bool", "bool"),
    ("'10.0.0.X' does not appear to be an IPv4 or IPv6 address", "ipv4"),
    ("OSError: illegal IP address string passed to inet_aton", "ipv4"),
    ("validators.url failed: invalid URL 'not a url'", "url"),
    ("EmailNotValidError: 'x@' is not a valid email", "email"),
    ("dateutil: Unknown string format: 'yesterday'", "iso8601"),
    ("ValueError: Invalid isoformat string: '2026-13-99'", "iso8601"),
    ("json.JSONDecodeError: Expecting value: line 1 column 1", "json_object"),
    ("Value 'Foo' must be one of: A, B, C", "picklist"),
    ("'X' is not a valid choice", "picklist"),
    # FSR connector idioms (added after the 2026-05 nist-nvd pilot).
    ("resultsPerPage parameter must be an integer.", "int"),
    ("startIndex parameter must be an integer.", "int"),
    ("temperature parameter must be a number.", "float"),
    ("enabled parameter must be a boolean.", "bool"),
    ("Invalid eventName parameter.", "picklist"),
])
def test_classify_error_matches(msg, expected_type):
    observed, coerces = ppt.classify_error(msg)
    assert observed == expected_type
    # coerces_from is non-empty for every rule we ship.
    assert coerces


def test_classify_error_no_match():
    assert ppt.classify_error("Connection refused") == (None, None)
    assert ppt.classify_error("") == (None, None)


def test_classify_error_first_rule_wins():
    # An error mentioning both 'must be one of' and 'int()' should bind
    # to whichever rule comes first — confirms ordering is deterministic.
    # Today: int rules precede picklist rules.
    msg = "invalid literal for int() with base 10 — must be one of: 1,2,3"
    observed, _ = ppt.classify_error(msg)
    assert observed == "int"


# ---------------------------------------------------------------------------
# run_widget_only — in-memory end-to-end
# ---------------------------------------------------------------------------

def _seed_minimal(conn: sqlite3.Connection) -> None:
    """Minimal schema slice needed by run_widget_only. We deliberately
    create operation_params *without* observed_type/coerces_from so the
    PRAGMA migration branch in _ensure_columns is exercised."""
    conn.executescript("""
        CREATE TABLE operation_params (
            connector_name TEXT NOT NULL,
            op_name TEXT NOT NULL,
            parent_param_name TEXT,
            condition_value TEXT,
            param_name TEXT NOT NULL,
            type TEXT,
            options_json TEXT,
            PRIMARY KEY (connector_name, op_name, parent_param_name,
                         condition_value, param_name)
        );
    """)
    conn.executemany(
        "INSERT INTO operation_params "
        "(connector_name, op_name, parent_param_name, condition_value, "
        " param_name, type, options_json) VALUES (?,?,?,?,?,?,?)",
        [
            ("c1", "op1", None, None, "n",      "integer",  None),
            ("c1", "op1", None, None, "ratio",  "decimal",  None),
            ("c1", "op1", None, None, "flag",   "checkbox", None),
            ("c1", "op1", None, None, "label",  "text",     None),
            ("c1", "op1", None, None, "color",  "select",   '["red","blue"]'),
            # conditional sub-param — exercises non-NULL parent/condition cols.
            ("c1", "op1", "color", "red", "shade", "text", None),
        ],
    )


def test_run_widget_only_populates_and_migrates():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _seed_minimal(conn)

    counts = ppt.run_widget_only(conn)

    assert counts["total"] == 6
    assert counts["typed"] == 4    # integer, decimal, checkbox, select-picklist
    assert counts["untyped"] == 2  # the two text rows

    by_param = {
        r["param_name"]: r["observed_type"]
        for r in conn.execute(
            "SELECT param_name, observed_type FROM operation_params")
    }
    assert by_param == {
        "n": "int", "ratio": "float", "flag": "bool",
        "label": None, "color": "picklist", "shade": None,
    }


def test_run_widget_only_is_idempotent():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _seed_minimal(conn)
    first = ppt.run_widget_only(conn)
    second = ppt.run_widget_only(conn)
    assert first == second


# ---------------------------------------------------------------------------
# Live-probe (Phase 2.2) — exercised with a fake run_op so no FSR needed
# ---------------------------------------------------------------------------

def _seed_live_probe_db(conn: sqlite3.Connection) -> None:
    """Seed all tables the live-probe + promote pipeline touches.

    We don't `executescript(schema.sql)` because the schema file pulls
    in dozens of unrelated tables/views. Hand-roll the minimum needed.
    """
    conn.executescript("""
        CREATE TABLE operations (
            connector_name TEXT, op_name TEXT,
            PRIMARY KEY (connector_name, op_name)
        );
        CREATE TABLE operation_params (
            connector_name TEXT, op_name TEXT, parent_param_name TEXT,
            condition_value TEXT, param_name TEXT, type TEXT,
            options_json TEXT, observed_type TEXT, coerces_from TEXT,
            PRIMARY KEY (connector_name, op_name, parent_param_name,
                         condition_value, param_name)
        );
        CREATE TABLE op_safety (
            connector_name TEXT, op_name TEXT, safety TEXT,
            PRIMARY KEY (connector_name, op_name)
        );
        CREATE TABLE operation_examples (
            connector_name TEXT, op_name TEXT, source TEXT,
            example_kind TEXT, snippet TEXT
        );
        CREATE TABLE param_type_probes (
            connector_name TEXT, op_name TEXT, param_name TEXT,
            mutation_input TEXT, mutation_kind TEXT, response_status TEXT,
            error_message TEXT, inferred_type TEXT, inferred_coerces TEXT,
            classifier_version INTEGER NOT NULL DEFAULT 1,
            probed_at TEXT NOT NULL,
            PRIMARY KEY (connector_name, op_name, param_name, mutation_input)
        );
    """)
    conn.execute(
        "INSERT INTO operations VALUES ('acme', 'lookup_widget')")
    conn.execute(
        "INSERT INTO op_safety VALUES ('acme', 'lookup_widget', 'safe')")
    # A second op classified unsafe — must be excluded from the universe.
    conn.execute(
        "INSERT INTO operations VALUES ('acme', 'delete_widget')")
    conn.execute(
        "INSERT INTO op_safety VALUES ('acme', 'delete_widget', 'unsafe')")
    # And one safe op without a baseline example — must be skipped.
    conn.execute(
        "INSERT INTO operations VALUES ('acme', 'list_widgets')")
    conn.execute(
        "INSERT INTO op_safety VALUES ('acme', 'list_widgets', 'safe')")

    # Baseline call for lookup_widget. Params: count (int), name (str).
    conn.execute(
        "INSERT INTO operation_examples VALUES "
        "('acme', 'lookup_widget', 'pb_examples', 'json', ?)",
        (json.dumps({"params": {"count": 1, "name": "foo"}}),),
    )
    conn.executemany(
        "INSERT INTO operation_params VALUES (?,?,?,?,?,?,?,?,?)",
        [
            ("acme", "lookup_widget", None, None, "count", "integer", None, "int", None),
            ("acme", "lookup_widget", None, None, "name",  "text",    None, "str", None),
            # An unsafe op param: must not be probed.
            ("acme", "delete_widget", None, None, "id",    "integer", None, "int", None),
        ],
    )


import json  # local import keeps the top imports tidy


def test_live_probe_universe_filters_unsafe_and_no_baseline():
    """Universe = safe ∩ has-example. Unsafe + safe-without-example dropped."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _seed_live_probe_db(conn)

    universe = ppt._safe_op_universe(conn, only_connector=None, limit=None)
    assert [(r["connector_name"], r["op_name"]) for r in universe] == [
        ("acme", "lookup_widget")
    ]


def test_live_probe_dry_run_records_baseline_and_mutations():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _seed_live_probe_db(conn)

    calls: list[tuple[str, str, dict]] = []

    def fake_run_op(c, o, p):  # should NOT be called in dry-run
        calls.append((c, o, p))
        return {"ok": True}

    counts = ppt.run_live_probe(conn, fake_run_op, dry_run=True)
    assert calls == [], "dry-run must not call run_op"
    assert counts["ops_considered"] == 1
    # 3 mutations for int (count) + 3 for str (name) = 6 mutation rows
    assert counts["mutations_recorded"] == 6
    assert counts["mutations_classified"] == 0  # nothing classified in dry-run

    statuses = {r[0] for r in conn.execute(
        "SELECT DISTINCT response_status FROM param_type_probes")}
    assert "dry_run_baseline" in statuses
    assert "dry_run" in statuses


def test_live_probe_commit_classifies_and_promotes():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _seed_live_probe_db(conn)

    # The probe uses observed_type to choose mutations, so we leave
    # `count` widget-typed as 'int' for the mutation loop. We then
    # null out *after* probing but before promote(), to prove
    # promote() backfills from the ledger.

    # Fake FSR: baseline OK; mutating `count` always yields an int-error;
    # mutating `name` returns ok (permissive str field).
    def fake_run_op(c, o, params):
        # Baseline call: exactly the seeded params.
        if params == {"count": 1, "name": "foo"}:
            return {"ok": True, "data": {}}
        # `count` mutated → emit an int-coercion error every time.
        if params.get("count") != 1:
            return {
                "ok": False,
                "message": (
                    "ValueError: invalid literal for int() with base 10: "
                    f"{params.get('count')!r}"
                ),
            }
        # `name` mutated → connector is permissive, accepts anything.
        return {"ok": True}

    counts = ppt.run_live_probe(conn, fake_run_op, dry_run=False)
    assert counts["ops_baseline_ok"] == 1
    assert counts["mutations_classified"] == 3, \
        "all three int mutations should classify"

    # Null observed_type for count to prove promote() writes from the
    # ledger (rather than just matching the widget-derived value).
    conn.execute(
        "UPDATE operation_params SET observed_type = NULL "
        "WHERE param_name = 'count'")
    promo = ppt.promote(conn, threshold=3)
    assert promo["promoted"] == 1
    assert promo["below_threshold"] == 0

    row = conn.execute(
        "SELECT observed_type, coerces_from FROM operation_params "
        "WHERE param_name='count'"
    ).fetchone()
    assert row["observed_type"] == "int"
    # coerces_from comes from the matched classifier rule (`str` for the
    # 'invalid literal for int()' branch).
    assert row["coerces_from"] == "str"


def test_promote_respects_threshold():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _seed_live_probe_db(conn)

    # Insert exactly 2 classified mutation rows for one param.
    conn.executemany(
        "INSERT INTO param_type_probes VALUES "
        "(?,?,?,?,?,?,?,?,?,?,?)",
        [
            ("acme", "lookup_widget", "count", "'x1'", "string",
             "mutation_err", "err", "int", "str", 1, "now"),
            ("acme", "lookup_widget", "count", "'x2'", "list",
             "mutation_err", "err", "int", "str", 1, "now"),
        ],
    )
    counts = ppt.promote(conn, threshold=3)
    assert counts["promoted"] == 0
    assert counts["below_threshold"] == 1


def test_baseline_failure_skips_mutations():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _seed_live_probe_db(conn)

    def fake_run_op(c, o, p):
        return {"ok": False, "message": "connector misconfigured"}

    counts = ppt.run_live_probe(conn, fake_run_op, dry_run=False)
    assert counts["ops_baseline_fail"] == 1
    assert counts["mutations_recorded"] == 0
    rows = conn.execute(
        "SELECT response_status FROM param_type_probes").fetchall()
    assert [r[0] for r in rows] == ["baseline_fail"]


def test_pick_baseline_handles_bare_params_dict():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _seed_live_probe_db(conn)
    # Overwrite the example with a bare params dict (no envelope).
    conn.execute(
        "UPDATE operation_examples SET snippet = ? "
        "WHERE op_name='lookup_widget'",
        (json.dumps({"count": 7, "name": "bar"}),),
    )
    base = ppt._pick_baseline(conn, "acme", "lookup_widget")
    assert base == {"count": 7, "name": "bar"}
