"""probe_op_safety — classify every connector op as safe / unsafe / unknown.

Reads `operations` + `operation_params` from the reference store and
writes one `op_safety` row per op. Used by `verify_playbook`'s typed
walker to decide which connector_ops are eligible for live `run_op`
probing (safe ⇒ probe, unsafe/unknown ⇒ type-check inputs only).

Classifier layers (later layers can override earlier when *stricter*):

  1. Explicit per-op flag on `operations` (rare today; reserved).
  2. HTTP method when known: GET/HEAD → safe.
  3. Op-name prefix safe-pattern → safe.
  4. Op-name prefix unsafe-pattern → unsafe (overrides 1–3).
  5. Connector-category bias (firewall/EDR/messaging unsafe-leaning;
     threat-intel/enrichment safe-leaning). Only nudges 'unknown'.
  6. Unclassified → 'unknown'. Treated as unsafe at verify time.

Idempotent. Re-running drops + repopulates the table. Manual overrides
(direct UPDATE) survive only if you bump `classifier_version`; the
default rerun rewrites every row.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from datetime import datetime, timezone
from typing import Any

from . import _env  # noqa: F401  (loads .env)
from .common import probe_session, wipe_probe_tables, SCHEMA_PATH

PROBE_NAME = "probe_op_safety"
# v2: added pure-compute transform verbs (convert/parse/format/extract/…) to
# SAFE_PREFIXES so those ops classify 'safe' and the verify live-probe can
# ground their real output shape. Bump signals a re-classify is due.
CLASSIFIER_VERSION = 2


# Verbs that *read* state. Trailing _details/_info/_status are also safe.
SAFE_PREFIXES = (
    "get", "list", "search", "find", "fetch", "lookup", "describe",
    "read", "check", "test", "status", "count", "enumerate", "query",
    "show", "export",
    # Pure-compute / in-memory transforms — read-only by nature: they take a
    # value and return a derived value with no external side effect (e.g.
    # cyops_utilities convert_/parse_/format_/extract_). Added so the safe
    # live-probe can ground their real output envelope; a pure op with an
    # incomplete static output_schema is exactly where a measured shape helps.
    # UNSAFE_PREFIXES still wins first, so a mutating verb is never captured.
    "convert", "parse", "format", "encode", "decode", "extract", "compute",
    "calculate", "normalize", "render", "compare", "diff", "hash",
    "serialize", "deserialize", "tokenize",
)
SAFE_SUFFIXES = ("_details", "_info", "_status")

# Verbs that *change* state. Trumps any safe match — conservative wins.
UNSAFE_PREFIXES = (
    "block", "allow", "quarantine", "isolate", "create", "update",
    "delete", "remove", "insert", "upsert", "send", "post", "put",
    "patch", "disable", "enable", "kill", "terminate", "revoke",
    "reset", "restart", "start", "stop", "run", "execute", "invoke",
    "trigger", "push", "publish", "notify", "set", "add", "drop",
    "attach", "detach", "assign", "unassign", "approve", "reject",
    "escalate",
)

# Category-level nudges. Only applied when name-based layers returned
# 'unknown'. A clearly-named op keeps its name-based classification.
UNSAFE_CATEGORIES = {"firewall", "edr", "messaging", "ticketing"}
SAFE_CATEGORIES = {"threat-intel", "threat_intel", "enrichment",
                   "reputation", "intel"}


_PREFIX_RE = re.compile(r"^([a-z]+)_")


def _name_prefix(op_name: str) -> str | None:
    m = _PREFIX_RE.match(op_name.lower())
    return m.group(1) if m else None


def _http_method_from_params(rows: list[sqlite3.Row]) -> str | None:
    """Some connectors expose `method` as a param with a fixed default
    (e.g. generic HTTP shim). Mine it conservatively."""
    for r in rows:
        if (r["param_name"] or "").lower() in {"method", "http_method"}:
            d = (r["default_value"] or "").strip().upper()
            if d in {"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"}:
                return d
    return None


def classify(
    op_name: str,
    op_params: list[sqlite3.Row],
    category: str | None,
) -> tuple[str, str, dict[str, Any]]:
    """Return (safety, reason, evidence)."""
    evidence: dict[str, Any] = {}
    name = op_name.lower()

    # Layer 4: unsafe-prefix wins outright.
    prefix = _name_prefix(name)
    if prefix in UNSAFE_PREFIXES:
        evidence["matched_pattern"] = f"prefix:{prefix}"
        evidence["source"] = "name_unsafe"
        return "unsafe", f"op name starts with '{prefix}_' (state-changing)", evidence

    # Layer 3: safe-prefix or safe-suffix.
    if prefix in SAFE_PREFIXES:
        evidence["matched_pattern"] = f"prefix:{prefix}"
        evidence["source"] = "name_safe"
        return "safe", f"op name starts with '{prefix}_' (read-only verb)", evidence
    if any(name.endswith(sfx) for sfx in SAFE_SUFFIXES):
        sfx = next(s for s in SAFE_SUFFIXES if name.endswith(s))
        evidence["matched_pattern"] = f"suffix:{sfx}"
        evidence["source"] = "name_safe"
        return "safe", f"op name ends with '{sfx}' (read-only)", evidence

    # Layer 2: HTTP method (from a connector param when the connector is
    # a generic HTTP shim).
    method = _http_method_from_params(op_params)
    if method in {"GET", "HEAD"}:
        evidence.update({"method": method, "source": "http_method"})
        return "safe", f"HTTP {method} (read-only)", evidence
    if method in {"POST", "PUT", "PATCH", "DELETE"}:
        evidence.update({"method": method, "source": "http_method"})
        return "unsafe", f"HTTP {method} (state-changing)", evidence

    # Layer 5: category bias — only nudges from 'unknown'.
    cat = (category or "").strip().lower()
    if cat in UNSAFE_CATEGORIES:
        evidence.update({"category": cat, "source": "category_bias"})
        return "unsafe", f"connector category '{cat}' is state-changing-leaning", evidence
    if cat in SAFE_CATEGORIES:
        evidence.update({"category": cat, "source": "category_bias"})
        return "safe", f"connector category '{cat}' is read-leaning", evidence

    # Layer 6: nothing matched.
    evidence["source"] = "unclassified"
    return "unknown", "no classifier layer matched", evidence


def run(conn: sqlite3.Connection) -> dict[str, int]:
    # The op_safety table may not exist yet on older DBs created before
    # this probe shipped. Re-apply schema.sql idempotently to add it.
    conn.executescript(SCHEMA_PATH.read_text())
    wipe_probe_tables(conn, PROBE_NAME)

    ops = conn.execute(
        "SELECT o.connector_name, o.op_name, c.category "
        "FROM operations o "
        "LEFT JOIN connectors c ON c.name = o.connector_name"
    ).fetchall()

    counts = {"safe": 0, "unsafe": 0, "unknown": 0}
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    for row in ops:
        params = conn.execute(
            "SELECT param_name, default_value FROM operation_params "
            "WHERE connector_name=? AND op_name=? AND parent_param_name IS NULL",
            (row["connector_name"], row["op_name"]),
        ).fetchall()
        safety, reason, evidence = classify(
            row["op_name"], params, row["category"],
        )
        counts[safety] += 1
        conn.execute(
            "INSERT INTO op_safety "
            "(connector_name, op_name, safety, reason, evidence, "
            " classifier_version, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                row["connector_name"], row["op_name"], safety, reason,
                json.dumps(evidence), CLASSIFIER_VERSION, now,
            ),
        )

    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    with probe_session(PROBE_NAME, source_paths=[], version=str(CLASSIFIER_VERSION)) as conn:
        counts = run(conn)
    print(f"op_safety: {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
