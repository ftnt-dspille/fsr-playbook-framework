"""probe_filter_usage — mine real-world Jinja filter usage from live workflows.

Walks every workflow on the instance, extracts every `{{ … }}` and `{% … %}`
expression from each step's `arguments` blob, parses the filter chain, and
records canonical (filter, expression, source) tuples into
`jinja_filter_usage`.

Use: gives the agent + the docs realistic examples for the most common
filters (length, lower, tojson, json_query, default, …) instead of the
synthetic single-example-per-filter snippets we ship today.
"""
from __future__ import annotations

import json
import re
import sqlite3
import warnings
from pathlib import Path

from . import _env
from .common import probe_session

PROBE_NAME = "probe_filter_usage"

# Match any Jinja expression block — both `{{ … }}` and `{% … %}`.
# Non-greedy on the body so adjacent blocks don't merge.
_BLOCK_RE = re.compile(r"\{\{(.+?)\}\}|\{%(.+?)%\}", re.DOTALL)

# Within a Jinja expression, split on top-level pipes only — pipes inside
# strings/parens/brackets shouldn't split the chain.  Build the segments by
# scanning char-by-char (cheaper + more reliable than a regex for this).
def _split_pipeline(expr: str) -> list[str]:
    parts, cur, depth, in_str, str_ch = [], [], 0, False, ""
    i = 0
    while i < len(expr):
        c = expr[i]
        if in_str:
            cur.append(c)
            if c == "\\" and i + 1 < len(expr):
                cur.append(expr[i + 1]); i += 2; continue
            if c == str_ch:
                in_str = False; str_ch = ""
            i += 1; continue
        if c in ("'", '"'):
            in_str = True; str_ch = c; cur.append(c); i += 1; continue
        if c in "([{":
            depth += 1; cur.append(c); i += 1; continue
        if c in ")]}":
            depth -= 1; cur.append(c); i += 1; continue
        if c == "|" and depth == 0:
            parts.append("".join(cur).strip()); cur = []; i += 1; continue
        cur.append(c); i += 1
    if cur:
        parts.append("".join(cur).strip())
    return parts


# Filter call shape: name maybe followed by (args).  Strip args+everything
# after the filter name to get the canonical filter identifier.
_FILTER_HEAD_RE = re.compile(r"^\s*([a-zA-Z_][a-zA-Z0-9_]*)\b")


def _extract_filters(blob: str) -> list[tuple[str, str]]:
    """Return [(filter_name, surrounding_expression), …] for every filter
    call in `blob`. The expression is the full `{{ … }}` block so the
    agent sees realistic surrounding context (input shape + later
    pipeline steps).
    """
    out: list[tuple[str, str]] = []
    for m in _BLOCK_RE.finditer(blob):
        body = (m.group(1) or m.group(2) or "").strip()
        if not body:
            continue
        full = m.group(0)
        # Skip control-flow keywords ({% if %}, {% for %}, {% set %}, …)
        # — the filter chain we care about lives in the rhs of those.
        # Pipeline split still works correctly across them.
        segments = _split_pipeline(body)
        # First segment is the input expression, not a filter — skip it.
        for seg in segments[1:]:
            head = _FILTER_HEAD_RE.match(seg)
            if not head:
                continue
            fname = head.group(1)
            # Filter out obvious false positives: jinja keywords, Python
            # kwargs that happen to look like ids (rare since we already
            # split on top-level pipes), and the test-suffixes
            # (`is defined`, `is none`, etc — those use `is`, not `|`).
            if fname in {"and", "or", "not", "in", "is", "if", "else", "elif",
                          "endif", "endfor", "for", "set", "endset",
                          "endmacro", "macro", "true", "false", "none", "with",
                          "without", "context", "from", "import", "as"}:
                continue
            out.append((fname, full))
    return out


def _walk(node, hits: list, source: str, step_name: str, step_type: str) -> None:
    """Depth-first walk of any JSON-y blob; collect filter usages from
    every string leaf. Strings without `{{` are short-circuited.
    """
    if isinstance(node, str):
        if "{{" in node or "{%" in node:
            for fname, full in _extract_filters(node):
                hits.append({
                    "filter_name": fname,
                    "expression": full[:500],
                    "from_playbook": source,
                    "from_step": step_name,
                    "step_type": step_type,
                })
        return
    if isinstance(node, dict):
        for v in node.values():
            _walk(v, hits, source, step_name, step_type)
    elif isinstance(node, list):
        for v in node:
            _walk(v, hits, source, step_name, step_type)


def _ingest_workflow(wf: dict, hits: list) -> None:
    wf_name = wf.get("name") or wf.get("uuid") or "?"
    for s in (wf.get("steps") or []):
        st = s.get("stepType")
        st_name = (st.get("name") if isinstance(st, dict) else None) or "?"
        sname = s.get("name") or "?"
        args = s.get("arguments")
        if args is None:
            continue
        _walk(args, hits, source=wf_name, step_name=sname, step_type=st_name)


def main() -> int:
    warnings.filterwarnings("ignore")
    cfg = _env.get_config()
    if not cfg.is_live():
        print(f"[{PROBE_NAME}] env not configured; skipping")
        return 0
    client = _env.get_client()

    sources = [Path(cfg.base_url + "/api/3/workflows")]
    page_size = 100
    all_hits: list[dict] = []

    with probe_session(PROBE_NAME, sources) as conn:
        # Page through every workflow with $relationships=true so steps
        # inline. Cap at 5000 — well above today's ~1664 corpus.
        page = 1
        seen = 0
        while page <= 50:
            try:
                r = client.get("/api/3/workflows", params={
                    "$relationships": "true", "$limit": page_size, "$page": page,
                })
            except Exception as e:  # noqa: BLE001
                print(f"  page {page}: {e!r}")
                break
            members = r.get("hydra:member", []) if isinstance(r, dict) else []
            if not members:
                break
            for wf in members:
                _ingest_workflow(wf, all_hits)
                seen += 1
            if seen and seen % 200 == 0:
                print(f"  walked {seen} workflows, {len(all_hits)} usages so far")
            if len(members) < page_size:
                break
            page += 1

        # Wipe + repopulate.
        conn.execute("DELETE FROM jinja_filter_usage")
        # Roll up duplicates by (filter, expression) keeping the first source.
        rolled: dict[tuple[str, str], dict] = {}
        for h in all_hits:
            key = (h["filter_name"], h["expression"])
            if key in rolled:
                rolled[key]["occurrences"] += 1
            else:
                rolled[key] = {**h, "occurrences": 1}
        for v in rolled.values():
            conn.execute(
                """INSERT OR REPLACE INTO jinja_filter_usage
                   (filter_name, expression, from_playbook, from_step,
                    step_type, occurrences)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (v["filter_name"], v["expression"], v["from_playbook"],
                 v["from_step"], v["step_type"], v["occurrences"]),
            )

        # Also: pick the best (most-used) example per filter and stamp it
        # onto jinja_macros.example so the existing `find_jinja_filter`
        # tool surfaces a real example. Only overwrite when we have one.
        cursor = conn.execute(
            """SELECT filter_name,
                      (SELECT expression FROM jinja_filter_usage u2
                        WHERE u2.filter_name = u1.filter_name
                        ORDER BY occurrences DESC LIMIT 1) AS best_expr
               FROM jinja_filter_usage u1
               GROUP BY filter_name"""
        )
        promoted = 0
        for row in cursor.fetchall():
            fname, best = row[0], row[1]
            r = conn.execute(
                "UPDATE jinja_macros SET example = ? "
                "WHERE name = ? AND (example IS NULL OR example = '' "
                "                    OR example NOT LIKE '%{{%')",
                (best, fname),
            )
            promoted += r.rowcount

        notes = json.dumps({
            "workflows_walked": seen,
            "total_usages": len(all_hits),
            "unique_filter_expressions": len(rolled),
            "filters_with_examples": len(set(h["filter_name"] for h in all_hits)),
            "macros_example_promoted": promoted,
        })
        conn.execute(
            "UPDATE _probe_runs SET notes = ? "
            "WHERE id = (SELECT MAX(id) FROM _probe_runs WHERE probe_name = ?)",
            (notes, PROBE_NAME),
        )

        print(f"[{PROBE_NAME}] walked={seen} usages={len(all_hits)} "
              f"unique={len(rolled)} filters={len(set(h['filter_name'] for h in all_hits))} "
              f"promoted={promoted}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
