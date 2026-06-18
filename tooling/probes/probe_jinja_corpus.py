"""probe_jinja_corpus — mine ALL Jinja usage from the live workflow corpus.

Beyond filter usages, this captures:
  - `{{ expr | filter | … }}` expression blocks
  - `{% set name = … %}` control blocks (assignment patterns)
  - `{% for x in iter %}` loops (iteration patterns)
  - `{% if … %}` / `{% elif %}` / `{% else %}` (conditional patterns)
  - `{% macro %}` / `{% include %}` etc.

For each block we record:
  - kind          (expr | set | for | if | elif | else | macro | …)
  - head          (the leading expression — assignment target, loop iterable, condition)
  - filters_csv   (filter names used in any pipeline within the block)
  - vars_csv      (normalized vars.* paths referenced)
  - source        (playbook + step + step_type)
  - occurrences   (deduped by raw block)

The agent uses this to learn FSR's jinja idioms — `{% set x = vars.steps.find.records[0] %}`,
loop-with-paged-fetch, `{% if vars.input.records | length > 0 %}`, etc — instead of
guessing from synthetic single-line examples. Plus rolls up to a `jinja_filter_usage`
view for backwards compat with `get_filter_examples`.
"""
from __future__ import annotations

import json
import re
import warnings
from pathlib import Path

from . import _env
from .common import probe_session

PROBE_NAME = "probe_jinja_corpus"

# Match either kind of block. Kept non-greedy so adjacent blocks don't merge.
_BLOCK_RE = re.compile(r"\{\{(.+?)\}\}|\{%-?(.+?)-?%\}", re.DOTALL)

# Identify control-block kind by leading keyword.
_CONTROL_KEYWORDS = {
    "set": "set", "for": "for", "if": "if", "elif": "elif", "else": "else",
    "endif": "endif", "endfor": "endfor", "endset": "endset",
    "macro": "macro", "endmacro": "endmacro", "include": "include",
    "block": "block", "endblock": "endblock", "with": "with", "endwith": "endwith",
    "call": "call", "endcall": "endcall", "do": "do", "raw": "raw", "endraw": "endraw",
    "import": "import", "from": "from",
}

# vars.<path> walker — captures the head of any vars.* access. Includes
# bracket subscripts so `vars.input.records[0]['@id']` becomes
# `vars.input.records[0]['@id']` (no normalization beyond stripping spaces).
_VAR_RE = re.compile(
    r"vars\.[a-zA-Z0-9_]+(?:(?:\.[a-zA-Z0-9_]+)|(?:\[[^\]]+\]))*"
)

_FILTER_HEAD_RE = re.compile(r"^\s*([a-zA-Z_][a-zA-Z0-9_]*)\b")

_PIPELINE_KEYWORDS = {
    "and", "or", "not", "in", "is", "if", "else", "elif", "endif", "endfor",
    "for", "set", "endset", "endmacro", "macro", "true", "false", "none",
    "with", "without", "context", "from", "import", "as", "do", "endcall",
    "call", "block", "endblock", "raw", "endraw",
}


def _split_pipeline(expr: str) -> list[str]:
    """Split on top-level `|`s (skip inside strings / parens / brackets)."""
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
        if c in "([{": depth += 1; cur.append(c); i += 1; continue
        if c in ")]}": depth -= 1; cur.append(c); i += 1; continue
        if c == "|" and depth == 0:
            parts.append("".join(cur).strip()); cur = []; i += 1; continue
        cur.append(c); i += 1
    if cur:
        parts.append("".join(cur).strip())
    return parts


def _classify_block(body: str, is_control: bool) -> tuple[str, str]:
    """Return (kind, head). For an expression block we return ('expr', body).
    For a control block we read the leading keyword and split off the rest
    as `head` (the target, iterable, or condition).
    """
    body = body.strip()
    if not is_control:
        return "expr", body
    head_word = body.split(None, 1)[0] if body else ""
    kind = _CONTROL_KEYWORDS.get(head_word, "other")
    rest = body[len(head_word):].strip()
    return kind, rest


def _filters_from_segments(segments: list[str]) -> list[str]:
    out: list[str] = []
    for seg in segments[1:]:
        m = _FILTER_HEAD_RE.match(seg)
        if not m:
            continue
        fname = m.group(1)
        if fname in _PIPELINE_KEYWORDS:
            continue
        out.append(fname)
    return out


def _scan_block(raw: str) -> dict | None:
    """Return {raw, kind, head, filters_csv, vars_csv} for one block, or None."""
    m = _BLOCK_RE.fullmatch(raw)
    if not m:
        return None
    is_control = bool(m.group(2))
    body = (m.group(1) or m.group(2) or "").strip()
    if not body:
        return None
    kind, head = _classify_block(body, is_control)
    # Filter chain anywhere inside the block (handles `{% set x = a | b %}`).
    segments = _split_pipeline(body)
    filters = _filters_from_segments(segments)
    vars_found: list[str] = []
    for v in _VAR_RE.findall(body):
        if v not in vars_found:
            vars_found.append(v)
    return {
        "raw": raw[:600],
        "kind": kind,
        "head": head[:300],
        "filters_csv": ",".join(filters) if filters else None,
        "vars_csv": ",".join(vars_found) if vars_found else None,
    }


def _walk(node, hits: list, source: str, step_name: str, step_type: str) -> None:
    if isinstance(node, str):
        if "{{" not in node and "{%" not in node:
            return
        for m in _BLOCK_RE.finditer(node):
            block = _scan_block(m.group(0))
            if block:
                hits.append({**block, "from_playbook": source,
                             "from_step": step_name, "step_type": step_type})
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
                print(f"  walked {seen} workflows, {len(all_hits)} blocks so far")
            if len(members) < page_size:
                break
            page += 1

        # Repopulate jinja_expressions (dedupe by raw block, count occurrences).
        conn.execute("DELETE FROM jinja_expressions")
        rolled: dict[str, dict] = {}
        for h in all_hits:
            key = h["raw"]
            if key in rolled:
                rolled[key]["occurrences"] += 1
            else:
                rolled[key] = {**h, "occurrences": 1}
        for v in rolled.values():
            conn.execute(
                """INSERT OR REPLACE INTO jinja_expressions
                   (raw, kind, head, filters_csv, vars_csv,
                    from_playbook, from_step, step_type, occurrences)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (v["raw"], v["kind"], v["head"], v["filters_csv"], v["vars_csv"],
                 v["from_playbook"], v["from_step"], v["step_type"], v["occurrences"]),
            )

        # Repopulate the legacy filter-usage table from the new corpus, so
        # `get_filter_examples` and the MCP tool keep working.
        conn.execute("DELETE FROM jinja_filter_usage")
        # One row per (filter_name, raw block) — every filter mentioned
        # in any block produces a row. Sum occurrences when collapsing.
        for v in rolled.values():
            if not v["filters_csv"]:
                continue
            for fname in v["filters_csv"].split(","):
                conn.execute(
                    """INSERT OR REPLACE INTO jinja_filter_usage
                       (filter_name, expression, from_playbook, from_step,
                        step_type, occurrences)
                       VALUES (?, ?, ?, ?, ?,
                               COALESCE((SELECT occurrences + ? FROM jinja_filter_usage
                                          WHERE filter_name = ? AND expression = ?), ?))""",
                    (fname, v["raw"], v["from_playbook"], v["from_step"],
                     v["step_type"], v["occurrences"], fname, v["raw"], v["occurrences"]),
                )

        # Promote the most-used real example onto jinja_macros.example for
        # any filter that doesn't already have a real corpus example.
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

        kind_counts = {row[0]: row[1] for row in conn.execute(
            "SELECT kind, COUNT(*) FROM jinja_expressions GROUP BY kind"
        ).fetchall()}

        notes = json.dumps({
            "workflows_walked": seen,
            "total_blocks": len(all_hits),
            "unique_blocks": len(rolled),
            "by_kind": kind_counts,
            "macros_example_promoted": promoted,
        })
        conn.execute(
            "UPDATE _probe_runs SET notes = ? "
            "WHERE id = (SELECT MAX(id) FROM _probe_runs WHERE probe_name = ?)",
            (notes, PROBE_NAME),
        )

        print(f"[{PROBE_NAME}] walked={seen} blocks={len(all_hits)} "
              f"unique={len(rolled)} kinds={kind_counts} "
              f"promoted={promoted}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
