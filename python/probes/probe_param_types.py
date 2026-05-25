"""probe_param_types — populate operation_params.observed_type / coerces_from.

For the live-probe pass, evidence lands in `param_type_probes` first;
the promote() step reads ≥3 corroborating rows per param before
writing to `operation_params.observed_type`.

Tier 2 of the static type validation plan
(`docs/plans/STATIC_TYPE_VALIDATION_PLAN.md`). The resolver uses
`observed_type` to validate `text`-widget params and Jinja-templated
values where Tier 1's widget-type column gave no signal.

Two passes:

  * **widget-only** (Phase 2.0, default): derive `observed_type` from
    `operation_params.type` (the form widget) + `options_json`.
    Pure-static — no FSR calls. Idempotent rewrite of every row.

  * **live-probe** (Phase 2.2, not enabled here): mutate one param at
    a time with type-mismatched values against `safe`-classified ops,
    capture the runtime error, run it through `classify_error`, and
    promote when ≥3 mutations corroborate. Gated on
    `op_safety.safety = 'safe'` (the 'safe_with_dry_run' tier from the
    plan doc does not exist on this schema; pilot subset is the
    `safe`-only slice).

Phase 2.1 deliverable is `classify_error()` — a pure regex-driven
classifier callable without any DB. The probe wires it up but does
not invoke it from the widget-only pass.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Callable

from . import _env  # noqa: F401  (loads .env)
from .common import probe_session, SCHEMA_PATH

PROBE_NAME = "probe_param_types"
CLASSIFIER_VERSION = 1


# ---------------------------------------------------------------------------
# Widget → observed_type mapping (Phase 2.0)
# ---------------------------------------------------------------------------
# Source of truth for widget names: a `SELECT DISTINCT type FROM
# operation_params` on the live store. The picklist branch is keyed on
# `options_json IS NOT NULL` because some `text` widgets carry options
# (free-text-with-suggestions) and we want to treat those as picklists
# too. `text` falls through to NULL — that is what Tier 2 live-probing
# is meant to lift.
_WIDGET_MAP: dict[str, str] = {
    "integer": "int",
    "intger": "int",            # observed typo in the store
    "decimal": "float",
    "numeric": "float",
    "checkbox": "bool",
    "boolean": "bool",
    "password": "str",
    "json": "json_object",
    "object": "json_object",
    "date": "iso8601",
    "datetime": "iso8601",
    "richtext": "str",
    "textarea": "str",
}


def widget_to_observed_type(
    widget: str | None, options_json: str | None,
) -> str | None:
    """Pure mapping used by the widget-only pass.

    Returns None for `text` and unknown widgets so the row stays
    eligible for Tier 2 live-probing later.
    """
    if options_json:
        # select / multiselect / text-with-options all collapse here.
        return "picklist"
    if not widget:
        return None
    return _WIDGET_MAP.get(widget.lower())


# ---------------------------------------------------------------------------
# Param-name → observed_type (Phase 2.0+ — name-pattern pass)
# ---------------------------------------------------------------------------
# The widget pass classifies ~45% of operation_params. The residue is
# almost entirely `type='text'` (14k+ rows), and 54% of *those* carry
# names that are strong evidence by themselves — `url`, `ip`,
# `ip_address`, `domain`, `endpoint`, `epoch_*`. This pass lifts those
# names into typed rows without spending a single FSR call.
#
# Rules: regex on lowercased param_name. Order matters — more specific
# patterns first (e.g. `ip_address` before `address`). Each rule emits
# an observed_type that the resolver already has a validator for
# (see `connector_args.py::_OBSERVED_VALIDATORS`). Conservative:
# anything ambiguous (`name`, `id`, `value`, `query`) stays None so
# the row is still eligible for Tier 2.2 live probing.

_NAME_RULES: list[tuple[re.Pattern[str], str]] = [
    # IPv4 / IPv6 — match `ip`, `ip_address`, `src_ip`, `dst_ipv4`, etc.
    # Anchored on word-boundary at the right to avoid `ip` matching
    # words like `script`, `recipient`, `clip`.
    (re.compile(r"(^|_)ipv6(_|$)"),                    "ipv6"),
    (re.compile(r"(^|_)(ip|ip_addr|ip_address|"
                r"src_ip|dst_ip|source_ip|dest_ip|"
                r"client_ip|server_ip|host_ip|peer_ip|"
                r"remote_ip|local_ip|public_ip|private_ip)(_|$)"), "ipv4"),
    # URLs / endpoints — require the name to *end* in url/uri/endpoint
    # or contain `_url`/`_uri` so we don't pick up tokens that happen
    # to share substrings.
    (re.compile(r"(^|_)(url|uri|endpoint|webhook|callback_url|"
                r"redirect_url|api_url|api_endpoint|base_url|"
                r"base_uri|server_url)(_|$)"),         "url"),
    # Email — `email`, `recipient_email`, `from_email`, etc.
    (re.compile(r"(^|_)(email|email_address|from_email|"
                r"to_email|recipient_email|sender_email|"
                r"cc_email|bcc_email|user_email)(_|$)"), "email"),
    # ISO timestamps — date / datetime / *_at / *_time, but NOT
    # `timeout` / `time_limit` (those are durations).
    (re.compile(r"(^|_)(timestamp|created_at|updated_at|"
                r"modified_at|deleted_at|start_time|end_time|"
                r"start_date|end_date|from_date|to_date|"
                r"date_from|date_to|iso_date|datetime)(_|$)"), "iso8601"),
    # JSON payload — `payload`, `body`, `json_body`, `request_body`.
    # Skip when the widget already classified to json_object via the
    # widget map; this is for text-widget rows that *carry* a JSON blob.
    (re.compile(r"(^|_)(json_body|request_body|response_body|"
                r"json_payload|raw_payload|raw_json)(_|$)"),     "json_object"),
]


def name_to_observed_type(param_name: str | None) -> str | None:
    """Match param_name against the name-rule table.

    Returns None when no rule fires — keeps the row eligible for
    Phase 2.2 live probing. Pure; no DB access; safe to call from the
    resolver as a fallback if a row was somehow probed before this
    pass ran.
    """
    if not param_name:
        return None
    n = param_name.strip().lower()
    for pat, observed in _NAME_RULES:
        if pat.search(n):
            return observed
    return None


# ---------------------------------------------------------------------------
# Error classifier (Phase 2.1)
# ---------------------------------------------------------------------------
# Each rule: (compiled regex, observed_type, coerces_from-hint).
# Rules are evaluated in order; first match wins. The regex set is
# small and hand-derived from a) Python's stdlib coercion errors
# (int/float/bool); b) common validator libraries the FSR connector
# corpus uses (validators, ipaddress, email_validator, dateutil).
#
# Adding rules: keep them anchored on stable error text. Prefer
# something the runtime *quotes literally* — connector authors rarely
# rewrite error messages from stdlib helpers, so `invalid literal for
# int()` is far more stable than a connector's wrapping prose.

ClassifierRule = tuple[re.Pattern[str], str, str | None]

_RULES: list[ClassifierRule] = [
    # --- int / float coercion (stdlib) -------------------------------
    (re.compile(
        r"invalid literal for int\(\) with base \d+",
        re.IGNORECASE,
    ), "int", "str"),
    (re.compile(
        r"int\(\) argument must be a string,? a bytes-like object",
        re.IGNORECASE,
    ), "int", "str,int"),
    (re.compile(
        r"could not convert string to float",
        re.IGNORECASE,
    ), "float", "str"),
    (re.compile(
        r"float\(\) argument must be a string",
        re.IGNORECASE,
    ), "float", "str,int,float"),

    # --- bool --------------------------------------------------------
    (re.compile(
        r"(invalid bool|must be (a )?bool(ean)?|expected (a )?bool)",
        re.IGNORECASE,
    ), "bool", "bool,str"),

    # --- IP addresses (ipaddress / socket.inet_*) --------------------
    (re.compile(
        r"does not appear to be an IPv4 or IPv6 address",
        re.IGNORECASE,
    ), "ipv4", "str"),  # caller refines to ipv6 when context disambiguates
    (re.compile(
        r"(illegal IP address string|inet_aton)",
        re.IGNORECASE,
    ), "ipv4", "str"),

    # --- URL / email / domain ---------------------------------------
    (re.compile(
        r"(invalid URL|not a valid URL|validators\.url)",
        re.IGNORECASE,
    ), "url", "str"),
    (re.compile(
        r"(not a valid email|email-validator|EmailNotValidError)",
        re.IGNORECASE,
    ), "email", "str"),

    # --- datetime ---------------------------------------------------
    (re.compile(
        r"(Unknown string format|Invalid isoformat string|not a valid (date|datetime|ISO))",
        re.IGNORECASE,
    ), "iso8601", "str"),

    # --- JSON -------------------------------------------------------
    (re.compile(
        r"(JSONDecodeError|Expecting value|Expecting property name)",
        re.IGNORECASE,
    ), "json_object", "str,dict,list"),

    # --- picklist / enum -------------------------------------------
    (re.compile(
        r"(must be one of|is not a valid choice|invalid (option|choice|value).{0,40}allowed)",
        re.IGNORECASE,
    ), "picklist", "str"),

    # --- FSR-connector idioms (observed in 2026-05 pilot) ---------
    # Many connectors wrap parameter validation as
    # "<paramName> parameter must be an integer." (.) The phrasing is
    # consistent enough across connectors that one regex covers them.
    (re.compile(
        r"parameter must be an integer\.?",
        re.IGNORECASE,
    ), "int", "str"),
    (re.compile(
        r"parameter must be a (number|float|decimal)\.?",
        re.IGNORECASE,
    ), "float", "str"),
    (re.compile(
        r"parameter must be a bool(ean)?\.?",
        re.IGNORECASE,
    ), "bool", "bool,str"),
    # "Invalid <paramName> parameter." — used when an enum-typed param
    # is given an unknown value. Distinct from the int/float/bool
    # phrasing above (which is shape-only).
    (re.compile(
        r"Invalid \w+ parameter\.?",
        re.IGNORECASE,
    ), "picklist", "str"),
]


def classify_error(message: str) -> tuple[str | None, str | None]:
    """Map a runtime error string to (observed_type, coerces_from).

    Returns (None, None) when no rule matches. Always pure; safe to
    call from tests without any DB / network.
    """
    if not message:
        return (None, None)
    for pat, observed, coerces in _RULES:
        if pat.search(message):
            return (observed, coerces)
    return (None, None)


# ---------------------------------------------------------------------------
# Phase 2.0 — widget-only pass
# ---------------------------------------------------------------------------

def _ensure_columns(conn: sqlite3.Connection) -> None:
    """Make the new columns exist on existing DBs (PRAGMA-driven, idempotent).

    Newly-created stores get the columns from schema.sql's CREATE TABLE;
    older stores need ALTER. We don't run the full schema.sql here
    because operation_params has FK constraints and recreating it would
    cascade — ALTER is cheap and safe.
    """
    cols = {r[1] for r in conn.execute(
        "PRAGMA table_info(operation_params)").fetchall()}
    if "observed_type" not in cols:
        conn.execute(
            "ALTER TABLE operation_params ADD COLUMN observed_type TEXT")
    if "coerces_from" not in cols:
        conn.execute(
            "ALTER TABLE operation_params ADD COLUMN coerces_from TEXT")


def run_widget_only(conn: sqlite3.Connection) -> dict[str, int]:
    """Phase 2.0 pass: populate observed_type from widget type alone.

    Touches every row in operation_params. Idempotent — re-running
    overwrites prior widget-only values; live-probe results (Phase
    2.2, future) would be merged from a separate ledger so they
    survive this pass.
    """
    _ensure_columns(conn)
    rows = conn.execute(
        "SELECT connector_name, op_name, parent_param_name, "
        "       condition_value, param_name, type, options_json "
        "FROM operation_params"
    ).fetchall()
    counts: dict[str, int] = {"total": len(rows), "typed": 0,
                              "typed_by_widget": 0, "typed_by_name": 0,
                              "untyped": 0}
    for r in rows:
        obs = widget_to_observed_type(r["type"], r["options_json"])
        if obs is not None:
            counts["typed_by_widget"] += 1
        else:
            # Name-pattern fallback — covers text-widget rows where the
            # param_name carries the type signal (url / ip / domain / ...).
            obs = name_to_observed_type(r["param_name"])
            if obs is not None:
                counts["typed_by_name"] += 1
        if obs is None:
            counts["untyped"] += 1
        else:
            counts["typed"] += 1
        # parent_param_name / condition_value are NULL-able PK columns —
        # IS NULL comparison required, '= NULL' silently matches nothing.
        conn.execute(
            "UPDATE operation_params "
            "SET observed_type = ? "
            "WHERE connector_name = ? AND op_name = ? "
            "  AND (parent_param_name IS ? OR parent_param_name = ?) "
            "  AND (condition_value IS ? OR condition_value = ?) "
            "  AND param_name = ?",
            (obs,
             r["connector_name"], r["op_name"],
             r["parent_param_name"], r["parent_param_name"],
             r["condition_value"], r["condition_value"],
             r["param_name"]),
        )
    return counts


# ---------------------------------------------------------------------------
# Phase 2.2 — live-probe pass
# ---------------------------------------------------------------------------
#
# A `RunOpFn` is the only thing this pass needs from the outside world.
# Production wires it to `mcp_server.tools_execution.run_op`. Tests pass
# a fake that returns canned errors — that's where the synthetic
# regression for the mutation-loop comes from.
#
# Contract (mirrors run_op's actual response shape):
#   fn(connector, op, params) ->
#     {"ok": True, "data": ...}                          # baseline success
#   | {"ok": False, "message": "..."}                    # FSR-side error
#   | {"ok": False, "code": "transport_failed", ...}     # network blew up

RunOpFn = Callable[[str, str, dict[str, Any]], dict[str, Any]]


# Per the plan: each observed_type maps to ~3 mutation values that
# should trigger the corresponding stdlib coercion error if the
# connector relies on stdlib int/float/bool/etc. The point is to
# cross-confirm — three mutations agreeing on one inferred type beats
# one rich error.
_MUTATIONS_BY_TYPE: dict[str, list[tuple[str, Any]]] = {
    "int": [
        ("string", "not-a-number"),
        ("list",   [1, 2]),
        ("dict",   {"a": 1}),
    ],
    "float": [
        ("string", "not-a-number"),
        ("list",   [1.0]),
        ("dict",   {"a": 1.0}),
    ],
    "bool": [
        ("string", "maybe"),
        ("int",    42),
        ("list",   [True]),
    ],
    "picklist": [
        ("enum_invalid", "__no_such_value_zzzz__"),
    ],
    # `str`-typed params: the runtime usually str()-coerces anything,
    # so a list/dict is what tends to trip type-checked connectors.
    "str": [
        ("list", [1]),
        ("dict", {"k": "v"}),
        ("int",  12345),
    ],
}


def _pick_baseline(
    conn: sqlite3.Connection, connector: str, op: str,
) -> dict[str, Any] | None:
    """Return the first JSON-shaped operation_examples row as a param dict.

    operation_examples stores snippets as opaque text; for `example_kind
    = 'json'` we expect the snippet to be either the full
    `{"connector", "operation", "params": {...}}` envelope (matches what
    backfill_operation_examples emits) or a bare params dict. We accept
    both and return only the params dict.
    """
    row = conn.execute(
        "SELECT snippet FROM operation_examples "
        "WHERE connector_name = ? AND op_name = ? AND example_kind = 'json' "
        "ORDER BY rowid LIMIT 1",
        (connector, op),
    ).fetchone()
    if row is None:
        return None
    try:
        obj = json.loads(row["snippet"] if isinstance(row, sqlite3.Row) else row[0])
    except (json.JSONDecodeError, TypeError):
        return None
    if isinstance(obj, dict) and isinstance(obj.get("params"), dict):
        return dict(obj["params"])
    if isinstance(obj, dict):
        return dict(obj)
    return None


def _safe_op_universe(
    conn: sqlite3.Connection,
    only_connector: str | None,
    limit: int | None,
) -> list[sqlite3.Row]:
    """Return ops that are (a) classified safe and (b) have a baseline
    example in operation_examples. Plan calls for hard-gating on the
    safety classifier — no exceptions, even for ops the user thinks
    are safe but classifier marked unknown."""
    q = (
        "SELECT DISTINCT s.connector_name, s.op_name "
        "FROM op_safety s "
        "JOIN operation_examples e USING (connector_name, op_name) "
        "WHERE s.safety = 'safe'"
    )
    args: list[Any] = []
    if only_connector:
        q += " AND s.connector_name = ?"
        args.append(only_connector)
    q += " ORDER BY s.connector_name, s.op_name"
    if limit:
        q += " LIMIT ?"
        args.append(limit)
    return conn.execute(q, args).fetchall()


def _record_probe(
    conn: sqlite3.Connection,
    *,
    connector: str,
    op: str,
    param: str,
    mutation_kind: str,
    mutation_input: Any,
    response_status: str,
    error_message: str | None,
    now: str,
) -> None:
    """Insert (or replace) one mutation row. Replace-on-conflict makes
    re-runs idempotent at the (param, mutation_input) granularity."""
    inferred, coerces = classify_error(error_message or "")
    conn.execute(
        "INSERT OR REPLACE INTO param_type_probes "
        "(connector_name, op_name, param_name, mutation_input, mutation_kind,"
        " response_status, error_message, inferred_type, inferred_coerces,"
        " classifier_version, probed_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (
            connector, op, param, repr(mutation_input), mutation_kind,
            response_status,
            (error_message or "")[:800] or None,
            inferred, coerces,
            CLASSIFIER_VERSION, now,
        ),
    )


def _extract_error(resp: dict[str, Any]) -> str:
    """Pull the most informative human string out of a run_op error
    envelope. run_op normalises FSR errors into `message`; if not set,
    fall back to the JSON dump."""
    if not isinstance(resp, dict):
        return str(resp)
    for k in ("message", "error", "status"):
        v = resp.get(k)
        if isinstance(v, str) and v:
            return v
    try:
        return json.dumps(resp)[:600]
    except (TypeError, ValueError):
        return str(resp)[:600]


def run_live_probe(
    conn: sqlite3.Connection,
    run_op_fn: RunOpFn,
    *,
    only_connector: str | None = None,
    limit: int | None = None,
    dry_run: bool = True,
) -> dict[str, int]:
    """Phase 2.2 mutation loop.

    For each safe op with a baseline example: confirm the baseline call
    succeeds, then for each typed top-level param mutate the value with
    each mutation in _MUTATIONS_BY_TYPE[observed_type]. Record every
    attempt to param_type_probes; classify_error() runs at record time
    so the ledger captures both raw evidence and the classifier's
    derived type for that classifier version.

    `dry_run=True` (default) skips the HTTP call and instead synthesises
    a `{"ok": True}` baseline + records mutation rows as
    `response_status='dry_run'` with no inference. The dry pass exists
    to validate enumeration math (which ops/params/mutations *would*
    fire) without spending FSR call budget.
    """
    _ensure_columns(conn)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    ops = _safe_op_universe(conn, only_connector, limit)
    counts: dict[str, int] = {
        "ops_considered": len(ops),
        "ops_baseline_ok": 0,
        "ops_baseline_fail": 0,
        "ops_skipped_no_baseline": 0,
        "mutations_recorded": 0,
        "mutations_classified": 0,
    }

    for op_row in ops:
        connector, op = op_row["connector_name"], op_row["op_name"]
        baseline = _pick_baseline(conn, connector, op)
        if baseline is None:
            counts["ops_skipped_no_baseline"] += 1
            continue

        if dry_run:
            base_ok = True
            base_msg = None
        else:
            base_resp = run_op_fn(connector, op, dict(baseline))
            base_ok = bool(base_resp.get("ok"))
            base_msg = None if base_ok else _extract_error(base_resp)

        _record_probe(
            conn, connector=connector, op=op, param="__baseline__",
            mutation_kind="baseline",
            mutation_input="<baseline>",
            response_status=("dry_run_baseline" if dry_run
                             else ("baseline_ok" if base_ok else "baseline_fail")),
            error_message=base_msg, now=now,
        )
        if not base_ok:
            counts["ops_baseline_fail"] += 1
            # Per plan: don't treat mutation errors as evidence when the
            # baseline didn't succeed — could just be a broken op.
            continue
        counts["ops_baseline_ok"] += 1

        # Pull typed top-level params for this op. Sub-params (parent_param
        # set) need conditional context we don't synthesise here; punt.
        params = conn.execute(
            "SELECT param_name, observed_type FROM operation_params "
            "WHERE connector_name=? AND op_name=? "
            "  AND parent_param_name IS NULL AND condition_value IS NULL "
            "  AND observed_type IS NOT NULL",
            (connector, op),
        ).fetchall()
        for prow in params:
            p_name = prow["param_name"]
            mutations = _MUTATIONS_BY_TYPE.get(prow["observed_type"], [])
            if not mutations or p_name not in baseline:
                continue
            for kind, value in mutations:
                if dry_run:
                    status = "dry_run"
                    err = None
                else:
                    payload = dict(baseline)
                    payload[p_name] = value
                    resp = run_op_fn(connector, op, payload)
                    if resp.get("ok"):
                        # Connector accepted the mutated value — that's
                        # evidence the param is permissive, but we can't
                        # derive a type from it. Record as no-error.
                        status = "mutation_ok"
                        err = None
                    elif resp.get("code") == "transport_failed":
                        status = "transport_err"
                        err = _extract_error(resp)
                    else:
                        status = "mutation_err"
                        err = _extract_error(resp)
                _record_probe(
                    conn, connector=connector, op=op, param=p_name,
                    mutation_kind=kind, mutation_input=value,
                    response_status=status, error_message=err, now=now,
                )
                counts["mutations_recorded"] += 1
                if err and classify_error(err)[0] is not None:
                    counts["mutations_classified"] += 1

    return counts


# ---------------------------------------------------------------------------
# Promotion: param_type_probes → operation_params.observed_type
# ---------------------------------------------------------------------------

PROMOTION_THRESHOLD = 3  # ≥3 corroborating mutations → promote


def promote(
    conn: sqlite3.Connection,
    threshold: int = PROMOTION_THRESHOLD,
) -> dict[str, int]:
    """Walk param_type_probes, count classifier votes per param, and
    write the majority observed_type back to operation_params *only
    when it differs from the widget-derived value*. Widget-derived
    types are kept as the floor — live probing refines, doesn't
    contradict, unless it has the votes.
    """
    _ensure_columns(conn)
    # Group classified probes by (connector, op, param) → list of inferred_type
    rows = conn.execute(
        "SELECT connector_name, op_name, param_name, inferred_type, "
        "       inferred_coerces "
        "FROM param_type_probes "
        "WHERE inferred_type IS NOT NULL "
        "  AND response_status = 'mutation_err'"
    ).fetchall()

    by_key: dict[tuple[str, str, str], list[tuple[str, str | None]]] = {}
    for r in rows:
        key = (r["connector_name"], r["op_name"], r["param_name"])
        by_key.setdefault(key, []).append(
            (r["inferred_type"], r["inferred_coerces"]))

    counts = {"considered": len(by_key), "promoted": 0, "below_threshold": 0,
              "unchanged": 0}
    for (connector, op, param), votes in by_key.items():
        type_counter = Counter(v[0] for v in votes)
        top_type, top_n = type_counter.most_common(1)[0]
        if top_n < threshold:
            counts["below_threshold"] += 1
            continue
        # Pick the coerces hint from any vote that landed on top_type.
        coerces = next(
            (c for t, c in votes if t == top_type and c), None,
        )
        cur = conn.execute(
            "SELECT observed_type FROM operation_params "
            "WHERE connector_name=? AND op_name=? "
            "  AND parent_param_name IS NULL AND condition_value IS NULL "
            "  AND param_name=?",
            (connector, op, param),
        ).fetchone()
        if cur is None:
            continue
        if cur["observed_type"] == top_type:
            counts["unchanged"] += 1
            # Still backfill coerces_from if absent — cheap.
            conn.execute(
                "UPDATE operation_params SET coerces_from = "
                "  COALESCE(coerces_from, ?) "
                "WHERE connector_name=? AND op_name=? "
                "  AND parent_param_name IS NULL AND condition_value IS NULL "
                "  AND param_name=?",
                (coerces, connector, op, param),
            )
            continue
        conn.execute(
            "UPDATE operation_params "
            "SET observed_type = ?, coerces_from = ? "
            "WHERE connector_name=? AND op_name=? "
            "  AND parent_param_name IS NULL AND condition_value IS NULL "
            "  AND param_name=?",
            (top_type, coerces, connector, op, param),
        )
        counts["promoted"] += 1
    return counts


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=["widget-only", "live-probe", "promote"],
        default="widget-only",
        help=("`widget-only` populates observed_type from the widget "
              "column. `live-probe` runs the Phase 2.2 mutation loop "
              "(defaults to --dry-run; pass --commit to call FSR). "
              "`promote` walks param_type_probes and promotes by "
              "majority vote to operation_params.observed_type."),
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help=("Required to actually call the live FSR in live-probe "
              "mode. Without it, --dry-run is forced."),
    )
    parser.add_argument(
        "--connector",
        help="Restrict live-probe to one connector (e.g. 'virustotal').",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Cap the number of ops considered.",
    )
    parser.add_argument(
        "--threshold", type=int, default=PROMOTION_THRESHOLD,
        help=f"Promotion threshold (default {PROMOTION_THRESHOLD}).",
    )
    args = parser.parse_args(argv)

    with probe_session(PROBE_NAME, source_paths=[],
                       version=str(CLASSIFIER_VERSION)) as conn:
        _ensure_columns(conn)
        conn.executescript(SCHEMA_PATH.read_text())

        if args.mode == "widget-only":
            counts = run_widget_only(conn)
            print(f"param_types(widget-only): {counts}")
            return 0

        if args.mode == "promote":
            counts = promote(conn, threshold=args.threshold)
            print(f"param_types(promote, threshold={args.threshold}): {counts}")
            return 0

        # live-probe
        if not args.commit:
            run_op_fn: RunOpFn = lambda *a, **kw: {"ok": True, "data": {}}  # noqa: E731
            counts = run_live_probe(
                conn, run_op_fn,
                only_connector=args.connector,
                limit=args.limit,
                dry_run=True,
            )
            print(f"param_types(live-probe, DRY RUN): {counts}")
            print("Re-run with --commit to actually call FSR.")
            return 0

        # --commit: drive the FSR client directly. We deliberately do
        # NOT route through `mcp_server.tools_execution.run_op` because
        # that wrapper opens its own write connection to record per-op
        # verifications and deadlocks against the probe_session's
        # outer write transaction. For type probing we only need the
        # raw response — verification ledger pollution is unwanted.
        from probes._env import get_config, get_client
        cfg = get_config()
        if not cfg.is_live():
            print("FSR_BASE_URL / FSR_API_KEY not set — refusing live probe.")
            return 2
        client = get_client()
        # Cache connector version lookups so we don't requery per call.
        _ver_cache: dict[str, str | None] = {}

        def _connector_version(name: str) -> str | None:
            if name not in _ver_cache:
                row = conn.execute(
                    "SELECT version FROM connectors WHERE name=?", (name,),
                ).fetchone()
                _ver_cache[name] = row["version"] if row else None
            return _ver_cache[name]

        def _run_op(c: str, o: str, p: dict[str, Any]) -> dict[str, Any]:
            body = {
                "connector": c, "operation": o,
                "version": _connector_version(c) or "",
                "config": "", "params": p,
            }
            try:
                resp = client.post("/api/integration/execute/", body)
            except Exception as exc:  # noqa: BLE001
                # FSR maps connector validation failures to HTTP 4xx
                # with a JSON body like
                # {"message":"... parameter must be an integer."}.
                # That's classifier-grade evidence — not a transport
                # failure. Only fall through to transport_err for
                # network/5xx/HTML responses.
                r = getattr(exc, "response", None)
                if r is not None and 400 <= getattr(r, "status_code", 0) < 500:
                    text = (r.text or "")[:1500]
                    msg = text
                    try:
                        import json as _json
                        body_json = _json.loads(text)
                        if isinstance(body_json, dict) and body_json.get("message"):
                            msg = body_json["message"]
                    except (ValueError, TypeError):
                        pass
                    return {"ok": False, "message": msg}
                txt = (r.text if r is not None else str(exc))[:600]
                return {"ok": False, "code": "transport_failed", "message": txt}
            if not isinstance(resp, dict):
                return {"ok": False, "message": f"bad response: {type(resp).__name__}"}
            status = resp.get("status", "")
            if status in ("Success", "success", "Completed", "completed", ""):
                return {"ok": True, "data": resp.get("data", resp)}
            return {
                "ok": False,
                "message": resp.get("message") or json.dumps(resp)[:600],
            }

        counts = run_live_probe(
            conn, _run_op,
            only_connector=args.connector,
            limit=args.limit,
            dry_run=False,
        )
        print(f"param_types(live-probe, COMMITTED): {counts}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
