"""Build the slim, shippable compile catalog from the full probed reference DB.

The full ``data/fsr_reference.db`` (~65 MB) mixes three kinds of data:

* **Globally-stable authoring catalog** — step types, handlers, jinja, recipes,
  api endpoints. Identical on every appliance for a given FSR version; safe to
  ship.
* **Per-install probed data** — connectors, operations, picklists, modules.
  Carry instance-specific UUIDs; warmed from the *target* SOAR (``warmup``),
  never shipped (shipping Instance A's UUIDs would mis-resolve on Instance B).
* **Heavy corpus / telemetry** — playbook_steps, verifications, *_probes. Mining
  and audit artifacts; irrelevant at compile time.

This copies the **full schema** (so every table the resolver might touch exists,
even if empty — a missing connector then yields a clean ``CompileError`` rather
than "no such table") but populates ONLY the stable tables, then VACUUMs.

The resolver has NO cache-miss → live-lookup fallback, so the slim DB compiles
only playbooks that reference solely the stable catalog; a connector/picklist/
module reference needs ``warmup`` against a live SOAR first.

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
)

# Deliberately EXCLUDED though globally stable: the authoring-hint corpus
# (jinja_expressions ~7.8k, jinja_filter_usage ~1.7k) and the REST reference
# catalog (api_endpoints* ~1.2k). The compiler reads none of them — only the
# tools_jinja MCP helper does, and it degrades to "no suggestions" on the empty
# (schema-present) tables. Keeping them out holds the slim DB near ~1 MB. To
# ship them, move the name here and rebuild.


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
    """Verify the slim DB exists, has the stable tables populated, and the
    per-install tables empty. Non-zero exit on any violation."""
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
        for t in ("connectors", "operations", "picklists", "modules"):
            n = conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
            if n != 0:
                problems.append(f"per-install table {t!r} has {n} rows (should be empty)")
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
