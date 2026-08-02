"""MCP tools: Tools Jinja"""
from __future__ import annotations
from . import _shared

import json
import sys
from typing import Any

from ._shared import (
    mcp,
    _db,
    _rows,
    REPO_ROOT,
)
# Import DB_PATH for local use
DB_PATH = _shared.DB_PATH

# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
def find_jinja_filter(q: str, limit: int = 15,
                      verbose: bool = False) -> list[dict[str, Any]]:
    """Look up a Jinja FILTER by name, description, or example -- what it does,
    its signature, its observed output type, and how often it appears in
    real playbooks. Use this when you know the filter you want; to discover
    whole expression idioms instead, use find_jinja_pattern. Follow with
    get_filter_examples(name) for the long-form doc and more real usages of
    one filter.

    Returns name, signature, description, example, output_type_observed,
    is_trusted (1 = live-tested), and corpus_uses (real-world occurrence
    count in the live playbook corpus).

    Use `get_filter_examples(name)` after this to pull the curated
    long-form doc and more real-world usages for a specific filter.

    Args:
        verbose: when True, include `curated_doc` (rich long-form notes
            for complex filters like json_query, picklist, fromIRI,
            resolveRange) inline. Default omits it -- fetch via
            `get_filter_examples` once you've picked a filter.
    """
    with _db() as conn:
        rows = _rows(
            conn,
            """SELECT jm.name, jm.signature, jm.description, jm.example,
                      jm.output_type_observed, jm.returns, jm.curated_doc,
                      COALESCE(vv.is_trusted, 0) AS is_trusted,
                      COALESCE((SELECT SUM(occurrences) FROM jinja_filter_usage u
                                WHERE u.filter_name = jm.name), 0) AS corpus_uses
               FROM jinja_macros jm
               LEFT JOIN v_verification_state vv
                 ON vv.kind='jinja_macro' AND vv.key=jm.name
               WHERE jm.name LIKE '%'||?||'%'
                  OR jm.description LIKE '%'||?||'%'
                  OR jm.example LIKE '%'||?||'%'
               ORDER BY (jm.name=?) DESC, corpus_uses DESC, is_trusted DESC, jm.name
               LIMIT ?""",
            (q, q, q, q, limit),
        )
        if not verbose:
            for r in rows:
                r.pop("curated_doc", None)
        if rows:
            return rows
    # Never return a bare [] (AGENT_HARDENING_PLAN §H): fall back to the
    # authoritative name catalog (jinja2 builtins ∪ FSR ∪ Ansible -- the same
    # set validate_yaml checks against) so a real-but-uncorpused filter like
    # json_query is still discoverable, with near-name suggestions on a typo.
    return _catalog_fallback(q, limit)


def _catalog_fallback(q: str, limit: int) -> list[dict[str, Any]]:
    import difflib

    from fsr_playbooks.compiler.jinja_checks import _KNOWN_FILTERS

    ql = q.lower()
    hits = sorted(n for n in _KNOWN_FILTERS if ql in n.lower())
    if not hits:
        hits = difflib.get_close_matches(q, _KNOWN_FILTERS, n=limit, cutoff=0.5)
    note = ("no corpus entry -- matched against the known-filter catalog "
            "(jinja2 builtins + FSR + Ansible); the filter is valid but has "
            "no curated doc/examples here")
    return [{"name": n, "source": "catalog", "note": note} for n in hits[:limit]]

@mcp.tool()
def find_jinja_pattern(q: str, kind: str | None = None,
                      limit: int = 12) -> list[dict[str, Any]]:
    """Search the corpus of real Jinja BLOCKS mined from live workflows --
    whole idioms like `{% set x = vars.steps.foo %}` or `{% for r in
    vars.input.records %}`. Use this when you need to know how something is
    expressed in FortiSOAR playbooks. For a single filter's meaning or
    signature use find_jinja_filter, and for more usages of one named filter
    use get_filter_examples.

    Use this when you want to learn FSR idioms -- `{% set x = vars.steps.foo %}`,
    `{% for r in vars.input.records %}`, conditional guards, etc -- instead of
    only looking up filters. The corpus contains ~7,800 unique blocks mined
    from 1,669 live workflows.

    Args:
        q: substring to match against the raw block, head, vars, or filter chain
        kind: optional -- restrict to one block kind. Useful values:
            "expr"   -- `{{ … }}` expression blocks (most common)
            "set"    -- `{% set var = … %}` assignments
            "for"    -- `{% for x in … %}` loops
            "if"     -- `{% if cond %}` guards (`elif` is a separate kind)
            "macro"  -- `{% macro name(args) %}` definitions
            (omit kind to search across all)
        limit: max results (default 12, ordered by occurrences desc)

    Returns:
        list of {raw, kind, head, filters_csv, vars_csv, from_playbook,
                 from_step, step_type, occurrences}
    """
    # Precision ranking: an exact `head` match (the canonical idiom) ranks
    # above a starts-with match, which ranks above a bare substring match --
    # all before occurrences DESC. Without this, a broad query like
    # `vars.steps` returns 12 low-occurrence blocks that happen to contain
    # the substring, the canonical `{% set x = vars.steps.foo.output %}`
    # idiom is buried, and the model re-queries with different substrings
    # hoping for something more specific (8 near-identical calls in one
    # build turn -- #48). find_jinja_filter has the same boost on `name`;
    # `head` is the equivalent here. A LIKE pattern with no ESCAPE clause
    # treats `%` and `_` as wildcards, so bind the user's `q` literally via
    # a parameterized LIKE with ESCAPE for the starts-with tier only.
    sql = (
        """SELECT raw, kind, head, filters_csv, vars_csv,
                  from_playbook, from_step, step_type, occurrences
           FROM jinja_expressions
           WHERE (raw LIKE '%'||?||'%' ESCAPE '\\'
              OR head LIKE '%'||?||'%' ESCAPE '\\'
              OR COALESCE(filters_csv,'') LIKE '%'||?||'%' ESCAPE '\\'
              OR COALESCE(vars_csv,'') LIKE '%'||?||'%' ESCAPE '\\')"""
    )
    like_q = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    params: list = [like_q, like_q, like_q, like_q]
    if kind:
        sql += " AND kind = ?"
        params.append(kind)
    # `head = ?` is equality, not LIKE -- bind the RAW q. Binding the escaped
    # form would silently kill the boost for any query holding `_` or `%`
    # (`set_variable` arrives as `set\_variable`, which equals no head), and a
    # ranking that never fires looks exactly like one that found no exact hit.
    sql += (
        " ORDER BY (head = ?) DESC,"
        " occurrences DESC, head LIMIT ?"
    )
    params.extend([q, limit])
    with _db() as conn:
        rows = _rows(conn, sql, tuple(params))
        if rows:
            return rows
        # Whole-string LIKE can only ever match a query that is already Jinja
        # text. A model asking in WORDS -- "for record in loop", "join loop
        # list string", "current date time now" -- matches nothing, gets a bare
        # [], and rephrases. Measured on the #48 repro: 7 of 11 distinct
        # find_jinja_pattern queries in one build turn returned zero, and the
        # tool was called 7-10 times per turn circling two unanswered
        # questions. An empty result is not "no such idiom", it is the search
        # being literal about a question asked in prose.
        #
        # So fall back to per-token matching, ranked by how many distinct query
        # tokens a block hits. Same rows, a query shape the model actually uses.
        return _token_fallback(conn, q, kind, limit)


# Words that match half the corpus and carry no signal for a Jinja search.
_STOPWORDS = frozenset({
    "a", "an", "and", "the", "of", "in", "on", "to", "for", "with", "from",
    "how", "do", "i", "get", "use", "using", "my", "me", "it", "is", "are",
    "or", "into", "out", "up", "by", "at", "as", "be", "that", "this",
})


def _token_fallback(conn: Any, q: str, kind: str | None,
                    limit: int) -> list[dict[str, Any]]:
    """Rank blocks by how many distinct tokens of `q` they contain.

    A block matching 3 of the query's 4 words beats one matching 1, and ties
    break on corpus frequency -- so a prose question lands on the canonical
    idiom rather than on nothing. A 3+-word query must hit at least TWO
    tokens: one 4-letter accident ("here" inside "where") is not an answer,
    and surfacing it is worse than saying nothing -- the model chases it."""
    import re as _re

    toks = [t for t in _re.split(r"[^A-Za-z0-9_:.]+", q or "") if t]
    toks = [t for t in toks if len(t) > 1 and t.lower() not in _STOPWORDS]
    # De-dupe case-insensitively, keep order, and cap: each token costs a LIKE.
    seen: dict[str, None] = {}
    for t in toks:
        seen.setdefault(t.lower(), None)
    toks = list(seen)[:8]
    if not toks:
        return _no_pattern(q, [])

    def _esc(t: str) -> str:
        return t.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

    hit = ("(CASE WHEN raw LIKE '%'||?||'%' ESCAPE '\\' "
           "OR COALESCE(head,'') LIKE '%'||?||'%' ESCAPE '\\' "
           "OR COALESCE(filters_csv,'') LIKE '%'||?||'%' ESCAPE '\\' "
           "OR COALESCE(vars_csv,'') LIKE '%'||?||'%' ESCAPE '\\' "
           "THEN 1 ELSE 0 END)")
    score = " + ".join([hit] * len(toks))
    params: list = []
    for t in toks:
        params.extend([_esc(t)] * 4)
    sql = (f"""SELECT raw, kind, head, filters_csv, vars_csv,
                      from_playbook, from_step, step_type, occurrences,
                      ({score}) AS matched_tokens
               FROM jinja_expressions
               WHERE ({score}) >= {2 if len(toks) >= 3 else 1}""")
    params = params + list(params)          # score appears in SELECT and WHERE
    if kind:
        sql += " AND kind = ?"
        params.append(kind)
    sql += " ORDER BY matched_tokens DESC, occurrences DESC, head LIMIT ?"
    params.append(limit)
    rows = _rows(conn, sql, tuple(params))
    note = (f"no block contains {q!r} verbatim -- these matched "
            f"{'/'.join(toks)} individually, ranked by how many. If none fits, "
            "the idiom may be a FILTER: try find_jinja_filter.")
    if not rows:
        return _no_pattern(q, toks)
    return _cap(rows, note)


# Payload budget for the fallback, in serialized characters. The exact-match
# path is self-limiting -- a query that matches verbatim matches few things.
# The fallback is the opposite: it deliberately widens, so it returns `limit`
# rows every time, and it fires on the prose queries the model asks in bulk.
# Measured at ~9 KB for a 4-token query, which is a fifth of a turn's context
# spent on a guess, repeated 7-10 times in the #48 build turn.
_FALLBACK_CHAR_BUDGET = 6000
# Below this many rows the answer stops being a ranked list, so the budget
# yields rather than cutting deeper.
_FALLBACK_MIN_ROWS = 3
_RAW_CHARS = 400


def _cap(rows: list[dict[str, Any]], note: str) -> list[dict[str, Any]]:
    """Trim a fallback result set to `_FALLBACK_CHAR_BUDGET`.

    Three cuts, cheapest first: the note goes on the first row only (it says
    nothing new on row 9, and repeating it cost ~30% of the payload); an
    outsized `raw` block is truncated with its length stated, since a
    400-char idiom is already past the point of being an example; and rows
    beyond the budget are dropped with a count, never silently
    (AGENT_HARDENING_PLAN §H -- a truncated list that looks complete is a
    worse answer than a short one that says so).
    """
    import json as _json

    kept: list[dict[str, Any]] = []
    used = 0
    for i, r in enumerate(rows):
        r["match"] = "tokens"
        raw = r.get("raw")
        if isinstance(raw, str) and len(raw) > _RAW_CHARS:
            r["raw"] = raw[:_RAW_CHARS] + f"… <{len(raw)} chars, truncated>"
        if i == 0:
            r["note"] = note
        cost = len(_json.dumps(r, default=str))
        if kept and len(kept) >= _FALLBACK_MIN_ROWS and used + cost > _FALLBACK_CHAR_BUDGET:
            kept[0]["truncated"] = (
                f"{len(rows) - len(kept)} more matches omitted to stay within "
                "the response budget -- narrow `q` or set `kind` for the rest")
            break
        used += cost
        kept.append(r)
    return kept


def _no_pattern(q: str, toks: list[str]) -> list[dict[str, Any]]:
    """Never hand back a bare `[]` (AGENT_HARDENING_PLAN §H).

    An empty list reads as "there is no such idiom", so the model rephrases and
    asks again -- which is the loop #48 is about. Say what was searched, and
    name the ONE thing a block search structurally cannot find: a filter. Most
    of the unanswered #48 queries (`get_current_date`, `to_datetime`,
    `strftime`) were filter questions asked of the block corpus."""
    from fsr_playbooks.compiler.jinja_checks import _KNOWN_FILTERS

    near = sorted(n for n in _KNOWN_FILTERS
                  if any(t in n.lower() for t in toks or [q.lower()]))[:5]
    msg = (f"no Jinja BLOCK in the corpus matches {q!r}"
           + (f" (searched tokens: {'/'.join(toks)})" if toks else "")
           + ". This corpus holds whole `{% %}`/`{{ }}` blocks only.")
    if near:
        msg += (f" {q!r} looks like a FILTER name -- call "
                f"find_jinja_filter or get_filter_examples for: "
                f"{', '.join(near)}.")
    else:
        msg += (" If you are after a single filter's meaning or signature, "
                "that is find_jinja_filter, not this tool.")
    return [{"no_match": True, "query": q, "note": msg,
             "candidate_filters": near}]

@mcp.tool()
def get_filter_examples(name: str, limit: int = 8) -> dict[str, Any]:
    """Real-world usages of ONE named Jinja filter, mined from live playbooks,
    plus its curated long-form doc. Use after find_jinja_filter when you
    have the filter name and need to see it used in context. Each example is
    a full `{{ … }}` block from a real workflow, so the input shape and
    downstream chain are visible.

    Returns the filter's curated long-form doc (when present) plus the top
    `limit` distinct expressions where it's used, ordered by frequency.
    Each example is a full `{{ … }}` block from a real workflow so the
    surrounding context (input shape, downstream chain) is visible.

    Args:
        name: filter name (exact match, e.g. "json_query")
        limit: how many distinct expressions to return (default 8)
    """
    with _db() as conn:
        meta = _rows(
            conn,
            """SELECT name, signature, description, curated_doc, output_type_observed,
                      output_type_declared, parameters_json
               FROM jinja_macros WHERE name = ? LIMIT 1""",
            (name,),
        )
        if not meta:
            return {"error": f"unknown filter {name!r}"}
        examples = _rows(
            conn,
            """SELECT expression, from_playbook, from_step, step_type, occurrences
               FROM jinja_filter_usage
               WHERE filter_name = ?
               ORDER BY occurrences DESC LIMIT ?""",
            (name, limit),
        )
        return {**meta[0], "examples": examples,
                "total_corpus_uses": sum(e["occurrences"] for e in examples)}


# ---------------------------------------------------------------------------
# render_jinja
# ---------------------------------------------------------------------------

@mcp.tool()
def render_jinja(template: str, context: dict[str, Any] | None = None,
                 from_pb_execution: str | None = None) -> dict[str, Any]:
    """Render a Jinja template against the live FSR Jinja engine.

    Uses the same engine as FSR's playbook runtime, so FSR-custom filters
    (`| tojson`, `| b64encode`, `| yaql`, etc.) all work.

    Args:
        template: Jinja source -- e.g. `"{{ vars.steps.Get_org.records[0].id }}"`.
        context: dict of variable bindings (e.g. `{"value": [1, 2, 3]}`).
        from_pb_execution: optional workflow PK (string of digits) or task_id UUID.
            When set, the run's `{vars: {...env, steps: {<Name_us>: result}}}`
            is fetched and used as the base context. `context` is then merged
            on top so callers can override individual values for what-if tests.

    Returns:
        `{output: <value>}` on success -- value preserves its native type
        (str, int, float, bool, list, dict). `{error: str}` if the engine
        errored (template syntax issues, missing var, etc).

    Typical use: after triggering a playbook via `run-playbook`, pass the
    task_id here with the candidate Jinja for the NEXT step's argument to
    confirm it resolves correctly before wiring it into the YAML.
    """
    sys.path.insert(0, str(REPO_ROOT / "tooling"))
    try:
        from probes._env import get_client
    except ImportError:
        return {"error": "pyfsr / probes module not available in this environment"}

    client = get_client()
    if client is None:
        return {"error": "FSR instance not configured (FSR_BASE_URL / FSR_API_KEY missing in .env)"}

    values: dict[str, Any] = {}
    if from_pb_execution:
        try:
            from .tools_triage import get_run_env
        except ImportError:
            return {"error": "from_pb_execution requires the investigation tools (tools_triage), which are not part of the authoring library"}
        run_env = get_run_env(from_pb_execution)  # reuse the same transform
        if "error" in run_env:
            return {"error": f"from_pb_execution lookup failed: {run_env['error']}"}
        values = run_env.get("vars") and {"vars": run_env["vars"]} or {}
    if context:
        # Merge: vars-key deep-merges so caller can override individual fields
        # without losing the run's steps map.
        for k, v in context.items():
            if k == "vars" and isinstance(v, dict) and isinstance(values.get("vars"), dict):
                values["vars"] = {**values["vars"], **v}
            else:
                values[k] = v
    endpoint = "/api/wf/api/jinja-editor/"
    try:
        r = client.post(endpoint, data={"template": template, "values": values})
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)[:400]}

    # FSR sometimes returns the body as a JSON-encoded string (when the
    # response Content-Type is text/plain but the payload is `{"result":
    # 5}`). Unwrap so callers see the native scalar, not a quoted blob.
    if isinstance(r, str):
        s = r.strip()
        if s and s[0] in "{[":
            try:
                r = json.loads(s)
            except Exception:
                return {"output": r}
        else:
            return {"output": r}
    if isinstance(r, dict):
        for k in ("result", "output", "rendered", "value"):
            if k in r:
                return {"output": r[k]}
        return {"output": r}
    return {"output": r}


# ---------------------------------------------------------------------------
# search_playbooks
# ---------------------------------------------------------------------------

@mcp.tool()
def find_jinja_example(filter: str | None = None,
                        var_path: str | None = None,
                        intent: str | None = None,
                        step_type: str | None = None,
                        limit: int = 8) -> dict[str, Any]:
    """Search 7,789 real `{{…}}` / `{%…%}` expressions observed in
    actual FSR playbooks plus 1,690 indexed filter usages.

    At least one of `filter`, `var_path`, or `intent` must be set.
    - `filter`: filter name (`replace`, `tojson`, `picklist`,
      `json_query`, …) -- narrows to expressions using that filter.
    - `var_path`: substring match against normalized `vars_csv`
      (e.g. `vars.input.records`, `vars.steps.fetch_alerts`).
    - `intent`: substring against the raw expression -- useful for
      finding patterns like `replace('T', ' ')` or
      `picklist('AlertStatus'`.
    - `step_type`: optional filter to expressions found in a given
      step type (`SetVariable`, `Decision`, `UpdateRecord`, …).

    Results ranked by observed `occurrences` (most-used first) so the
    agent gets the idiomatic form rather than a one-off.
    """
    if not (filter or var_path or intent):
        return {"ok": False, "code": "missing_query",
                "message": "pass at least one of filter / var_path / intent"}
    where: list[str] = []
    args: list[Any] = []
    if filter:
        where.append("(filters_csv LIKE '%'||?||'%')")
        args.append(filter)
    if var_path:
        where.append("(vars_csv LIKE '%'||?||'%')")
        args.append(var_path)
    if intent:
        where.append("(raw LIKE '%'||?||'%')")
        args.append(intent)
    if step_type:
        where.append("step_type = ?")
        args.append(step_type)
    args.append(limit)
    sql = (
        "SELECT raw, kind, filters_csv, vars_csv, step_type, "
        "from_playbook, from_step, occurrences "
        "FROM jinja_expressions WHERE "
        + " AND ".join(where)
        + " ORDER BY occurrences DESC, length(raw) ASC LIMIT ?"
    )
    with _db() as conn:
        rows = _rows(conn, sql, tuple(args))
        out: dict[str, Any] = {"matches": rows, "count": len(rows)}
        if filter and not rows:
            usage = _rows(
                conn,
                """SELECT expression, from_playbook, from_step, occurrences
                   FROM jinja_filter_usage
                   WHERE filter_name=?
                   ORDER BY occurrences DESC LIMIT ?""",
                (filter, limit),
            )
            if usage:
                out["matches"] = usage
                out["count"] = len(usage)
                out["note"] = (
                    f"no jinja_expressions hit; falling back to "
                    f"jinja_filter_usage rows for filter {filter!r}."
                )
        if filter and not out["count"]:
            out["suggestion"] = (
                f"no usage of filter {filter!r} on record. Check "
                f"get_jinja_filters for the canonical name."
            )
    return out


# ---------------------------------------------------------------------------
# E3: Jinja expression generator -- suggest patterns for a task
# ---------------------------------------------------------------------------

@mcp.tool()
def suggest_jinja(
    task: str,
    context: str | None = None,
    limit: int = 5,
) -> dict[str, Any]:
    """Suggest Jinja expression patterns for a task an agent needs to implement.

    Instead of guessing at Jinja syntax, an AI agent that's authoring a
    playbook describes the task (e.g. ``"resolve a picklist IRI in a query
    body"``) and gets back real-world patterns from 8,500+ expressions mined
    from 1,800+ live playbooks -- each with its source playbook, filter chain,
    and variable access paths.

    Args:
        task: natural-language description of what the Jinja expression needs
            to do (e.g. ``"resolve picklist IRI"``, ``"loop over records and
            filter by severity"``, ``"format date as ISO 8601"``)
        context: optional extra context (e.g. ``"AlertState picklist in a
            query Record State step"``) -- narrows the search
        limit: max patterns to return (default 5)

    Returns:
        ``{patterns: [{raw, kind, filters_csv, vars_csv, from_playbook,
        from_step, occurrences}], filter_hints: [{name, signature, doc}],
        count}``

        Each pattern is a real Jinja block from a live playbook. The
        ``filter_hints`` section lists filters mentioned in the matched
        patterns with their signatures, so the agent can learn the exact
        parameter shapes without a separate lookup.

    Example:
        An agent asks ``suggest_jinja("resolve picklist IRI in query body")``
        and gets back patterns like
        ``{{"AlertState" | picklist("Indicator Extracted", "@id")}}``
        with the hint that ``picklist`` takes a ``key`` parameter where
        ``"@id"`` returns the IRI string.
    """
    # Build a search query from the task + context
    query_terms: list[str] = []
    # Extract likely filter/keyword tokens from the task
    task_lower = task.lower()
    # Map common task phrases to filter names
    _TASK_FILTER_MAP = {
        "picklist": "picklist",
        "iri": "picklist",
        "date": "arrow",
        "time": "arrow",
        "json": "tojson",
        "to_json": "tojson",
        "base64": "b64encode",
        "encode": "b64encode",
        "regex": "regex_replace",
        "replace": "regex_replace",
        "split": "split",
        "join": "join",
        "length": "length",
        "count": "length",
        "default": "default",
        "flatten": "flatten",
        "map": "map",
        "select": "selectattr",
        "filter": "selectattr",
        "sort": "sort",
        "group": "groupby",
        "query": "json_query",
        "yaql": "yaql",
    }
    for phrase, filter_name in _TASK_FILTER_MAP.items():
        if phrase in task_lower:
            query_terms.append(filter_name)

    # Also add any context-provided filter names
    if context:
        for word in context.lower().split():
            if len(word) > 2:
                query_terms.append(word)

    with _db() as conn:
        # Strategy 1: Search jinja_filter_usage by filter name
        usage_rows: list[dict[str, Any]] = []
        if query_terms:
            placeholders = ",".join("?" * len(query_terms))
            usage_rows = _rows(
                conn,
                f"""SELECT filter_name, expression, from_playbook, from_step,
                           step_type, occurrences
                    FROM jinja_filter_usage
                    WHERE filter_name IN ({placeholders})
                    ORDER BY occurrences DESC LIMIT ?""",
                (*query_terms, limit * 3),
            )

        # Strategy 2: Full-text search jinja_expressions
        # Build LIKE conditions for each word in the task
        words = [w for w in task.replace(",", " ").split() if len(w) > 2]
        if context:
            words.extend(w for w in context.replace(",", " ").split() if len(w) > 2)
        expr_rows: list[dict[str, Any]] = []
        if words:
            like_conditions = " OR ".join(
                ["raw LIKE '%' || ? || '%'" for _ in words]
            )
            expr_rows = _rows(
                conn,
                f"""SELECT raw, kind, filters_csv, vars_csv,
                           from_playbook, from_step, step_type, occurrences
                    FROM jinja_expressions
                    WHERE {like_conditions}
                    ORDER BY occurrences DESC, length(raw) ASC LIMIT ?""",
                (*words, limit * 2),
            )

        # Merge and deduplicate by raw expression
        seen: set[str] = set()
        patterns: list[dict[str, Any]] = []
        for row in usage_rows:
            raw = row.get("expression") or ""
            if raw and raw not in seen:
                seen.add(raw)
                patterns.append({
                    "raw": raw,
                    "kind": "expr",
                    "filters_csv": row.get("filter_name"),
                    "from_playbook": row.get("from_playbook"),
                    "from_step": row.get("from_step"),
                    "occurrences": row.get("occurrences", 1),
                })
        for row in expr_rows:
            raw = row.get("raw") or ""
            if raw and raw not in seen:
                seen.add(raw)
                patterns.append(row)
        patterns = patterns[:limit]

        # Collect filter hints from the matched patterns
        filter_names: set[str] = set()
        for p in patterns:
            fcsv = p.get("filters_csv") or ""
            for f in fcsv.split(","):
                f = f.strip()
                if f and f not in ("", "None"):
                    filter_names.add(f)

        filter_hints: list[dict[str, Any]] = []
        if filter_names:
            placeholders = ",".join("?" * len(filter_names))
            hint_rows = _rows(
                conn,
                f"""SELECT name, signature, description,
                           output_type_declared, curated_doc
                    FROM jinja_macros
                    WHERE name IN ({placeholders})""",
                tuple(filter_names),
            )
            for h in hint_rows:
                filter_hints.append({
                    "name": h.get("name"),
                    "signature": h.get("signature"),
                    "doc": (h.get("curated_doc") or h.get("description") or "")[:300],
                })

        return {
            "patterns": patterns,
            "filter_hints": filter_hints,
            "count": len(patterns),
        }