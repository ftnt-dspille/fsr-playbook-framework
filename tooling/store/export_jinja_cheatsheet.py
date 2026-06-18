"""Generate `store/FSR_CUSTOM_JINJA.md` — agent-facing cheatsheet for the
filters / globals / tests that ship with FortiSOAR's workflow engine and
aren't in stock Jinja2 or Ansible.

Why this exists: SQLite is the source of truth, but agents grep markdown.
Without this file, an agent writing Jinja for a FortiSOAR playbook will
fall back to `now() - timedelta(days=7)` (which doesn't work in FSR's
Jinja env) instead of `currentDateMinus(7)`. This file makes the
FortiSOAR-specific surface area discoverable in one grep.

Run after `probe_jinja_backend` has populated jinja_macros / jinja_globals
/ jinja_tests with full signatures from the live FSR appliance.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from probes.common import DB_PATH, STORE_DIR

OUT_PATH = STORE_DIR / "FSR_CUSTOM_JINJA.md"

# Modules whose contents we treat as "FortiSOAR-specific". `workflow.*` is
# the cyops-workflow code; `sealab.*` is the inner Django package; anything
# else (jinja2.*, ansible.*, builtins, itertools) is generic.
FSR_MODULE_PREFIXES = ("workflow.", "sealab.")


def _is_fsr(module: str | None) -> bool:
    if not module:
        return False
    return any(module.startswith(p) for p in FSR_MODULE_PREFIXES)


def _params_lines(params_json: str | None) -> list[str]:
    if not params_json:
        return []
    try:
        params = json.loads(params_json)
    except Exception:
        return []
    out = []
    for p in params:
        if not isinstance(p, dict):
            continue
        line = f"- `{p.get('name', '?')}`"
        bits = []
        if p.get("annotation"):
            bits.append(f"type: `{p['annotation']}`")
        if p.get("default") is not None:
            bits.append(f"default: `{p['default']}`")
        kind = p.get("kind")
        if kind in ("VAR_POSITIONAL", "VAR_KEYWORD"):
            bits.append(f"kind: {kind}")
        if p.get("description"):
            bits.append(p["description"])
        if bits:
            line += " — " + ", ".join(bits)
        out.append(line)
    return out


def _section(
    rows: list[sqlite3.Row],
    *,
    invocation_template: str,
) -> list[str]:
    """Render one entry block per row, sorted by name."""
    lines: list[str] = []
    for row in sorted(rows, key=lambda r: r["name"].lower()):
        name = row["name"]
        sig = row["signature"] or ""
        doc = (row["description"] or "").strip()
        params = _params_lines(row["parameters_json"])
        observed = row["output_type_observed"] if "output_type_observed" in row.keys() else None
        module = row["module"] or "(unknown module)"

        lines.append(f"### `{name}{sig}`")
        lines.append(f"_{module}_")
        lines.append("")
        if doc:
            for para in doc.split("\n\n"):
                lines.append(para.strip())
                lines.append("")
        if params:
            lines.append("**Parameters:**")
            lines.extend(params)
            lines.append("")
        if observed:
            lines.append(f"**Observed output type:** `{observed}`")
            lines.append("")
        lines.append(f"**Usage:** `{invocation_template.format(name=name)}`")
        lines.append("")
        lines.append("---")
        lines.append("")
    return lines


def _row_keys(cursor) -> list[str]:
    return [c[0] for c in cursor.description]


def build_cheatsheet(db_path: Path = DB_PATH, out_path: Path = OUT_PATH) -> Path:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        filters = [
            r for r in conn.execute(
                "SELECT name, signature, description, parameters_json, "
                "       output_type_observed, module "
                "FROM jinja_macros WHERE module IS NOT NULL"
            )
            if _is_fsr(r["module"])
        ]
        globals_ = [
            r for r in conn.execute(
                "SELECT name, signature, description, parameters_json, module, "
                "       NULL AS output_type_observed "
                "FROM jinja_globals WHERE module IS NOT NULL"
            )
            if _is_fsr(r["module"])
        ]
        tests = [
            r for r in conn.execute(
                "SELECT name, signature, description, parameters_json, module, "
                "       NULL AS output_type_observed "
                "FROM jinja_tests WHERE module IS NOT NULL"
            )
            if _is_fsr(r["module"])
        ]
    finally:
        conn.close()

    parts: list[str] = []
    parts.append("# FortiSOAR-custom Jinja capabilities")
    parts.append("")
    parts.append("Generated from `store/fsr_reference.db` by "
                 "`python/store/export_jinja_cheatsheet.py`. Source-of-truth is the live "
                 "FSR appliance via `inspect.signature()` introspection on the workflow "
                 "service's Jinja Environment (`backend_introspect` method).")
    parts.append("")
    parts.append("**These filters / globals / tests are FortiSOAR-specific** "
                 "(modules `workflow.*` or `sealab.*`). They are *not* in stock Jinja2 "
                 "or Ansible. Reach for these first when writing FSR playbook Jinja — "
                 "they shortcut a lot of common date / IOC / connector-config patterns.")
    parts.append("")
    parts.append("For the full 170-filter / 15-global / 39-test catalog, query "
                 "`fsr_reference.db` directly:")
    parts.append("")
    parts.append("```sql")
    parts.append("SELECT name, signature, module FROM jinja_macros ORDER BY name;")
    parts.append("SELECT name, signature, module FROM jinja_globals ORDER BY name;")
    parts.append("SELECT name, signature, module FROM jinja_tests   ORDER BY name;")
    parts.append("```")
    parts.append("")

    parts.append(f"## Globals — invoked as `name(args)`, no pipe ({len(globals_)})")
    parts.append("")
    parts.append("Globals are callables in scope inside any `{{ ... }}`. They are *not* "
                 "piped — call them directly.")
    parts.append("")
    parts.extend(_section(globals_, invocation_template="{{{{ {name}(...) }}}}"))

    parts.append(f"## Filters — invoked as `value | name(args)` ({len(filters)})")
    parts.append("")
    parts.extend(_section(filters, invocation_template="{{{{ value | {name} }}}}"))

    if tests:
        parts.append(f"## Tests — invoked as `value is name(args)` ({len(tests)})")
        parts.append("")
        parts.extend(_section(tests, invocation_template="{{% if value is {name} %}}"))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(parts))
    return out_path


if __name__ == "__main__":
    p = build_cheatsheet()
    print(f"wrote {p}")
