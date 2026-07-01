"""Build the slim, shippable compile catalog from the full probed reference DB.

The full ``data/fsr_reference.db`` (~65 MB) mixes three kinds of data:

* **Globally-stable authoring catalog** — step types, handlers, jinja, recipes,
  api endpoints. Identical on every appliance for a given FSR version; safe to
  ship.
* **Per-install probed data** — connectors, operations, picklists, modules.
  Carry instance-specific UUIDs; warmed from the *target* SOAR (``warmup``),
  never shipped *verbatim* (shipping Instance A's UUIDs would mis-resolve on
  Instance B). A **scrubbed subset** of connector *definitions* is shipped
  (see ``CONNECTOR_BASELINE``) — only the public operation/param schema the
  compiler validates against; the per-instance UUID/cred/host carriers
  (``info_json``, ``source_code``, ``rpm_fingerprint``, ``connector_configs``)
  are dropped or NULLed.
* **Heavy corpus / telemetry** — playbook_steps, verifications, *_probes. Mining
  and audit artifacts; irrelevant at compile time.

This copies the **full schema** (so every table the resolver might touch exists,
even if empty — a missing connector then yields a clean ``CompileError`` rather
than "no such table") but populates ONLY the stable tables (plus the scrubbed
``CONNECTOR_BASELINE`` connector definitions), then VACUUMs.

The resolver has NO cache-miss → live-lookup fallback, so the slim DB compiles
playbooks that reference the stable catalog or a baseline connector; any other
connector/picklist/module reference needs ``warmup`` against a live SOAR first.

Output: ``fsr_playbooks/_data/fsr_reference.db`` (tracked, shipped as
package-data). Run:

    uv run python -m tooling.catalog.build_compile_catalog          # build
    uv run python -m tooling.catalog.build_compile_catalog --check  # verify only
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_DB = _REPO_ROOT / "data" / "fsr_reference.db"
DST_DB = _REPO_ROOT / "fsr_playbooks" / "_data" / "fsr_reference.db"

# Globally-stable tables — populated in the slim DB. Everything else (per-install
# probed tables, corpus, telemetry, FTS shadow tables) ships with schema only,
# zero rows.
STABLE_TABLES = (
    "step_types",
    "step_handlers",
    "step_examples",
    "jinja_macros",
    "jinja_globals",
    "jinja_tests",
    "jinja_context_vars",
    "recipes",
    "connector_op_defs",
    # Module *type names* (alerts, incidents, indicators, …) are globally
    # stable for an FSR version and carry no per-install UUIDs — shipping
    # them lets the resolver validate/canonicalize module names offline
    # ('Alerts' → 'alerts', flag typos). A target's custom modules are still
    # picked up by `warmup`, which overwrites this baseline.
    "modules",
)

# Deliberately EXCLUDED though globally stable: the authoring-hint corpus
# (jinja_expressions ~7.8k, jinja_filter_usage ~1.7k) and the REST reference
# catalog (api_endpoints* ~1.2k). The compiler reads none of them — only the
# tools_jinja MCP helper does, and it degrades to "no suggestions" on the empty
# (schema-present) tables. Keeping them out holds the slim DB near ~1 MB. To
# ship them, move the name here and rebuild.


# Connector *definitions* shipped as a scrubbed baseline — the public
# operation/param schema the compiler validates connector steps against, so the
# in-repo example/library playbooks compile offline without a live ``warmup``.
# This is the same carve-out precedent as ``modules``: only the globally-stable,
# non-instance-specific parts ship; the per-install bits (config UUIDs, creds,
# hostnames) are stripped.
#
# Which connectors: the distinct set the example + library playbooks reference
# (pyfsr examples/playbooks/library/*). A connector not in this list still
# needs ``warmup`` against a target SOAR — the resolver reports a clean
# ``unknown_connector`` CompileError, never a crash.
#
# What ships per connector: the ``connectors`` row + its ``operations`` +
# ``operation_params`` rows. The compiler reads only those three tables for
# validation. The instance-specific / sensitive columns on ``connectors`` are
# NULLed (see ``_scrub_connector_row``); ``connector_configs`` (per-instance
# creds) stays empty — warmed, never shipped.
CONNECTOR_BASELINE: tuple[str, ...] = (
    "abuseipdb",
    "activedirectory",
    "cyops_utilities",
    "file-content-extraction",
    "fortigate-firewall",
    "fortinet-fortisiem",
    "ipinfo",
    "ipstack",
    "openai",
    "smtp",
    "ssh",
    "virustotal",
)

# Columns on ``connectors`` that carry instance-specific or sensitive data and
# are NULLed before shipping. ``info_json`` embeds the live ``configuration``
# array (per-instance config_id UUIDs) and sometimes a probe-time host URL
# (e.g. an appliance IP) — the compiler never reads it (only the MCP discovery
# tool does, as a fast-path cache), so NULLing is compile-safe and removes the
# only sensitive carrier. ``source_code``/``rpm_fingerprint`` are the
# connector's shipped code bundle + build fingerprint (large, not needed for
# validation). ``source`` is rewritten to ``"packaged"`` so shipped rows are
# distinguishable from live-warmed ones.
_CONNECTOR_NULL_COLUMNS = ("info_json", "source_code", "rpm_fingerprint")
_CONNECTOR_SOURCE_TAG = "packaged"


def _objects(conn: sqlite3.Connection, schema: str, kind: str) -> list[tuple[str, str]]:
    """Return (name, sql) for schema objects of ``kind`` in attached ``schema``,
    skipping internal and FTS virtual tables (their shadow tables can't be
    re-created by plain DDL)."""
    rows = conn.execute(
        f"SELECT name, sql FROM {schema}.sqlite_master "
        "WHERE type = ? AND sql IS NOT NULL "
        "AND name NOT LIKE 'sqlite_%' AND name NOT LIKE 'fsr_fts%' "
        "ORDER BY rowid",
        (kind,),
    ).fetchall()
    return [(n, s) for n, s in rows]


def _table_columns(conn: sqlite3.Connection, table: str, schema: str = "src") -> list[str]:
    """Column names of ``table`` in attached ``schema`` (in declared order)."""
    return [r[1] for r in conn.execute(f'PRAGMA {schema}.table_info("{table}")')]


def _copy_connector_baseline(dst: sqlite3.Connection) -> dict[str, int]:
    """Copy the ``CONNECTOR_BASELINE`` connector definitions from ``src`` to
    ``main``, scrubbing the instance-specific columns. Returns per-table row
    counts that were written. ``src`` must already be ATTACHed.

    Three tables: ``connectors`` (1 row each, sensitive cols NULLed) +
    ``operations`` + ``operation_params`` (all ops/params for the baseline
    connectors, verbatim — they carry only public schema).
    """
    if not CONNECTOR_BASELINE:
        return {"connectors": 0, "operations": 0, "operation_params": 0}
    placeholders = ",".join("?" * len(CONNECTOR_BASELINE))
    counts: dict[str, int] = {}

    # connectors — scrub the sensitive/instance columns and re-tag the source.
    cols = _table_columns(dst, "connectors")
    col_list = ",".join(f'"{c}"' for c in cols)
    sel = ", ".join(
        "NULL" if c in _CONNECTOR_NULL_COLUMNS
        else f"'{_CONNECTOR_SOURCE_TAG}'" if c == "source"
        else f'"{c}"'
        for c in cols
    )
    dst.execute(
        f'INSERT INTO main."connectors" ({col_list}) '
        f'SELECT {sel} FROM src."connectors" WHERE name IN ({placeholders})',
        CONNECTOR_BASELINE,
    )
    counts["connectors"] = dst.execute('SELECT COUNT(*) FROM main."connectors"').fetchone()[0]

    # operations + operation_params — public schema only; copy verbatim.
    for table, key in (("operations", "connector_name"), ("operation_params", "connector_name")):
        cols = _table_columns(dst, table)
        col_list = ",".join(f'"{c}"' for c in cols)
        dst.execute(
            f'INSERT INTO main."{table}" ({col_list}) '
            f'SELECT {col_list} FROM src."{table}" WHERE {key} IN ({placeholders})',
            CONNECTOR_BASELINE,
        )
        counts[table] = dst.execute(f'SELECT COUNT(*) FROM main."{table}"').fetchone()[0]
    return counts


def build() -> int:
    if not SRC_DB.exists():
        print(f"source DB missing: {SRC_DB} (run the probes / warmup first)", file=sys.stderr)
        return 2
    DST_DB.parent.mkdir(parents=True, exist_ok=True)
    if DST_DB.exists():
        DST_DB.unlink()

    dst = sqlite3.connect(DST_DB)
    try:
        dst.execute("ATTACH DATABASE ? AS src", (str(SRC_DB),))

        tables = _objects(dst, "src", "table")
        table_names = {n for n, _ in tables}
        for _name, sql in tables:
            dst.execute(sql)

        copied = {}
        for t in STABLE_TABLES:
            if t not in table_names:
                print(f"  warn: stable table {t!r} absent from source — skipped", file=sys.stderr)
                continue
            dst.execute(f'INSERT INTO main."{t}" SELECT * FROM src."{t}"')
            copied[t] = dst.execute(f'SELECT COUNT(*) FROM main."{t}"').fetchone()[0]

        # Scrubbed connector baseline (definitions only; instance cols NULLed).
        copied.update(_copy_connector_baseline(dst))

        # Indexes then views (views may reference tables; build after rows).
        for _name, sql in _objects(dst, "src", "index"):
            dst.execute(sql)
        for _name, sql in _objects(dst, "src", "view"):
            dst.execute(sql)

        dst.commit()
        dst.execute("DETACH DATABASE src")
        dst.execute("VACUUM")
        dst.commit()
    finally:
        dst.close()

    size_mb = DST_DB.stat().st_size / 1e6
    print(f"built {DST_DB.relative_to(_REPO_ROOT)}  ({size_mb:.2f} MB)")
    for t in STABLE_TABLES:
        if t in copied:
            print(f"  {copied[t]:>6}  {t}")
    return 0


def check() -> int:
    """Verify the slim DB exists, has the stable tables populated, the
    scrubbed connector baseline present and scrubbed, and the per-instance
    creds table empty. Non-zero exit on any violation."""
    if not DST_DB.exists():
        print(f"slim DB missing: {DST_DB}", file=sys.stderr)
        return 1
    conn = sqlite3.connect(f"file:{DST_DB}?mode=ro", uri=True)
    try:
        problems = []
        for t in STABLE_TABLES:
            n = conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
            if n == 0:
                problems.append(f"stable table {t!r} is empty")
        # Connector baseline: every name present, sensitive cols NULLed,
        # source re-tagged. Catches a regression that ships a live probe's
        # info_json (config UUIDs / host IPs) or un-scrubbed source code.
        shipped = [r[0] for r in conn.execute(
            'SELECT name FROM "connectors" ORDER BY name'
        ).fetchall()]
        missing = sorted(set(CONNECTOR_BASELINE) - set(shipped))
        if missing:
            problems.append(f"baseline connectors missing: {missing}")
        for name in CONNECTOR_BASELINE:
            row = conn.execute(
                'SELECT info_json, source_code, rpm_fingerprint, source '
                'FROM "connectors" WHERE name = ?', (name,)
            ).fetchone()
            if row is None:
                continue
            info_json, source_code, rpm_fingerprint, source = row
            if info_json is not None:
                problems.append(f"connector {name!r}: info_json not NULLed (sensitive)")
            if source_code is not None:
                problems.append(f"connector {name!r}: source_code not NULLed")
            if rpm_fingerprint is not None:
                problems.append(f"connector {name!r}: rpm_fingerprint not NULLed")
            if source != _CONNECTOR_SOURCE_TAG:
                problems.append(f"connector {name!r}: source={source!r} (expected {_CONNECTOR_SOURCE_TAG!r})")
        # The per-instance creds table stays empty — warmed, never shipped.
        n = conn.execute('SELECT COUNT(*) FROM "connector_configs"').fetchone()[0]
        if n != 0:
            problems.append(f"connector_configs has {n} rows (should be empty)")
        # picklists are still per-install (instance-specific picklist rows);
        # warmed, not shipped.
        n = conn.execute('SELECT COUNT(*) FROM "picklists"').fetchone()[0]
        if n != 0:
            problems.append(f"per-install table 'picklists' has {n} rows (should be empty)")
    finally:
        conn.close()
    if problems:
        for p in problems:
            print(f"  FAIL: {p}", file=sys.stderr)
        return 1
    print(f"ok: {DST_DB.relative_to(_REPO_ROOT)} ({DST_DB.stat().st_size / 1e6:.2f} MB)")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="verify the slim DB, don't rebuild")
    args = ap.parse_args(argv)
    return check() if args.check else build()


if __name__ == "__main__":
    sys.exit(main())
