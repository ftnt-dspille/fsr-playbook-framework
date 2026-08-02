"""MCP tools: Tools Corpus"""
from __future__ import annotations
from . import _shared

import json
import sqlite3
import sys
from typing import Any

from ._shared import (
    mcp,
    _err,
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
def search_playbooks(q: str, limit: int = 10,
                     verbose: bool = False) -> list[dict[str, Any]]:
    """Full-text search over playbooks seen in production -- pattern mining for
    "how do others build X". Returns names and collections of reference
    playbooks, NOT the analyst's own playbooks and NOT run history (that is
    list_playbook_runs). Use it for inspiration before authoring; slim by
    default, verbose=True adds descriptions and connector lists.

    Returns matching playbook names + collections -- useful for 'how do
    others do X' pattern mining.

    Args:
        verbose: when True, include `description` (FTS) /
            `uses_connectors_csv` + `step_count` (fallback). Default
            returns the slim row set so a top-of-funnel "what playbooks
            mention X" lookup costs few tokens.
    """
    with _db() as conn:
        # First try FTS table
        try:
            rows = _rows(
                conn,
                """SELECT kind, key, title, description
                   FROM fsr_fts
                   WHERE fsr_fts MATCH ?
                   LIMIT ?""",
                (q, limit),
            )
            if rows:
                if not verbose:
                    for r in rows:
                        r.pop("description", None)
                return rows
        except sqlite3.OperationalError:
            pass

        # Fallback: LIKE on playbooks_seen
        rows = _rows(
            conn,
            """SELECT collection, workflow, uses_connectors_csv, step_count
               FROM playbooks_seen
               WHERE collection LIKE '%'||?||'%' ESCAPE '\\'
                  OR workflow LIKE '%'||?||'%' ESCAPE '\\'
                  OR uses_connectors_csv LIKE '%'||?||'%' ESCAPE '\\'
               ORDER BY step_count DESC
               LIMIT ?""",
            (_like(q), _like(q), _like(q), limit),
        )
        if not rows:
            # A whole-string LIKE only ever matches a query that is already a
            # playbook NAME. The model asks in prose -- "phishing email
            # triage", "block ip on firewall" -- and a corpus of 1,600+
            # playbooks that certainly contains the pattern answers with a
            # bare `[]`, which reads as "nobody does this". Same failure and
            # same fix as find_jinja_pattern: match per token, rank by how
            # many distinct tokens a row hits.
            rows = _token_fallback(conn, q, limit)
        if not rows:
            return _no_playbooks(q)
        if not verbose:
            for r in rows:
                r.pop("uses_connectors_csv", None)
                r.pop("step_count", None)
        return rows


# Words that match half a playbook-name corpus and carry no signal.
_STOPWORDS = frozenset({
    "a", "an", "the", "of", "in", "on", "to", "for", "with", "from", "and",
    "how", "do", "i", "get", "use", "using", "my", "me", "it", "is", "are",
    "or", "into", "out", "up", "by", "at", "as", "be", "that", "this",
    "playbook", "playbooks", "workflow", "workflows", "example", "examples",
})


def _like(s: str) -> str:
    """Escape LIKE wildcards so a query holding `%`/`_` matches literally."""
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _tokens(q: str) -> list[str]:
    import re
    toks = [t for t in re.split(r"[^A-Za-z0-9_.-]+", q or "") if t]
    seen: dict[str, None] = {}
    for t in toks:
        if len(t) > 2 and t.lower() not in _STOPWORDS:
            seen.setdefault(t.lower(), None)
    return list(seen)[:8]


def _token_fallback(conn: sqlite3.Connection, q: str,
                    limit: int) -> list[dict[str, Any]]:
    """Rank playbooks by how many distinct tokens of `q` they mention.

    A 3+-token query must hit at least TWO: one incidental word match
    ("alert" in a corpus of alert playbooks) is not an answer, and surfacing
    it is worse than saying nothing -- the model reads a ranked list as a
    finding and follows it.
    """
    toks = _tokens(q)
    if not toks:
        return []
    hit = ("(CASE WHEN collection LIKE '%'||?||'%' ESCAPE '\\' "
           "OR workflow LIKE '%'||?||'%' ESCAPE '\\' "
           "OR COALESCE(uses_connectors_csv,'') LIKE '%'||?||'%' ESCAPE '\\' "
           "THEN 1 ELSE 0 END)")
    score = " + ".join([hit] * len(toks))
    params: list[Any] = []
    for t in toks:
        params.extend([_like(t)] * 3)
    sql = (f"""SELECT collection, workflow, uses_connectors_csv, step_count,
                      ({score}) AS matched_tokens
               FROM playbooks_seen
               WHERE ({score}) >= {2 if len(toks) >= 3 else 1}
               ORDER BY matched_tokens DESC, step_count DESC
               LIMIT ?""")
    rows = _rows(conn, sql, tuple(params + params + [limit]))
    for r in rows:
        r["match"] = "tokens"
    if rows:
        # The explanation goes on the first row only. Repeating a 20-word
        # note per row triples the payload of a result set whose rows are
        # two short strings each, and says nothing new on row 7.
        rows[0]["note"] = (
            f"no playbook name contains {q!r} verbatim -- these matched "
            f"{'/'.join(toks)} individually, ranked by how many "
            "(`matched_tokens`).")
    return rows


def _no_playbooks(q: str) -> list[dict[str, Any]]:
    """Never hand back a bare `[]` (AGENT_HARDENING_PLAN §H).

    An empty list reads as "no one builds this", and the model either
    rephrases (the search loop) or tells the user the pattern is unsupported.
    Say what this corpus actually holds -- playbook NAMES and collections,
    not step bodies -- and name the tool that answers the question it cannot.
    """
    toks = _tokens(q)
    return [{
        "no_match": True,
        "query": q,
        "searched_tokens": toks,
        "note": (
            f"no playbook in the corpus matches {q!r}"
            + (f" (searched tokens: {'/'.join(toks)})" if toks else "")
            + ". This corpus indexes playbook NAMES, collections and the "
              "connectors each uses -- not step bodies, so a search for what "
              "a playbook DOES will miss unless the name says it. For a "
              "buildable template use find_recipe; for how a step type is "
              "used in the wild use find_step_examples; for a vendor action "
              "use find_connector then find_operation."
        ),
    }]

@mcp.tool()
def review_chat_session(session_id: str) -> dict[str, Any]:
    """Mine one chat session for known failure patterns and return a
    structured report.

    Use this when the user asks "why did session X go wrong?" or when
    sweeping their thumbs-down feedback. Detectors covered:
    user feedback rating, validate-fix-validate spirals, empty/heavy
    tool results, UUID step ids, set_variable typos, missing
    `collection:` recurrences, unknown connector/op references, and
    sessions that never deployed. Source-of-truth for the patterns
    is `tooling/chat_review.py`.

    Returns: `{session_id, headline, findings[], stats}`. Each finding
    has `{severity: error|warning|info, code, title, detail, turn?,
    suggestion?}`. The headline is a one-liner suitable for chat output.
    """
    sys.path.insert(0, str(REPO_ROOT / "tooling"))
    try:
        import chat_review
    except ImportError as exc:
        return _err("chat_review_unavailable", f"chat_review not importable: {exc}")
    try:
        report = chat_review.review_session(session_id)
    except FileNotFoundError as e:
        return _err("history_db_missing", str(e))
    except LookupError as e:
        return _err("session_not_found", str(e))
    return report.to_dict()

@mcp.tool()
def review_recent_thumbs_down(limit: int = 10) -> dict[str, Any]:
    """Sweep the most recent thumbs-down sessions and run the chat-review
    pattern detectors against each. Useful for "what's been going wrong
    recently?" -- returns one row per session with its headline + top 3
    findings, plus a cross-session pattern frequency map.

    Returns:
      {
        sessions: [{session_id, rating, summary, headline, top_findings[]}, ...],
        common_patterns: {<code>: <count>, ...}
      }
    """
    import sqlite3 as _sql
    sys.path.insert(0, str(REPO_ROOT / "tooling"))
    try:
        import chat_review
    except ImportError as exc:
        return _err("chat_review_unavailable", f"chat_review not importable: {exc}")
    db_path = chat_review._DEFAULT_DB
    if not db_path.exists():
        return _err("history_db_missing", f"history db not found at {db_path}")
    conn = _sql.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = _sql.Row
    rows = conn.execute(
        "SELECT session_id, rating, summary, ts FROM chat_feedback "
        "WHERE rating='down' ORDER BY ts DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    out_sessions: list[dict[str, Any]] = []
    pattern_counts: dict[str, int] = {}
    for r in rows:
        try:
            rep = chat_review.review_session(r["session_id"])
        except Exception as e:  # noqa: BLE001
            out_sessions.append({
                "session_id": r["session_id"],
                "rating": r["rating"],
                "summary": r["summary"],
                "review_error": str(e),
            })
            continue
        for f in rep.findings:
            pattern_counts[f.code] = pattern_counts.get(f.code, 0) + 1
        out_sessions.append({
            "session_id": r["session_id"],
            "rating": r["rating"],
            "summary": r["summary"],
            "ts": r["ts"],
            "headline": rep.headline,
            "top_findings": [f.to_dict() for f in rep.findings[:3]],
            "stats": rep.stats,
        })
    common = sorted(pattern_counts.items(), key=lambda kv: -kv[1])
    return {
        "sessions": out_sessions,
        "common_patterns": dict(common),
    }

@mcp.tool()
def find_step_examples(step_type: str,
                       contains: str | None = None,
                       limit: int = 20) -> list[dict[str, Any]]:
    """Search the `playbook_steps` corpus for real-world examples of a step type.

    Backed by `probe_playbook_steps`, which indexes every step from every
    FSR playbook JSON export on disk (SP bundles + data/incoming drops).
    Use this when tightening linting/validation to mine real-world
    argument shapes -- e.g. "show me every ManualInput that uses
    formType=lookup" or "every Decision with a timeout block".

    Args:
        step_type: step_types.name, e.g. 'ManualInput', 'Decision',
                   'SetVariable', 'Connectors'.
        contains:  optional substring matched against the raw
                   arguments_json (case-sensitive). Examples:
                       'ipv4'                 -- any ipv4 input
                       '"formType": "lookup"' -- any lookup-typed field
                       '"default": true'      -- any default branch
                       '"timeout":'           -- any step with a timeout
        limit:     max rows (default 20).

    Returns: list of {step_name, playbook_name, source, source_path, arguments}.
    """
    with _db() as conn:
        sql = ("SELECT step_name, playbook_name, source, source_path, "
               "arguments_json FROM playbook_steps WHERE step_type_name = ?")
        params: list[Any] = [step_type]
        if contains:
            sql += " AND arguments_json LIKE ?"
            params.append(f"%{contains}%")
        sql += " LIMIT ?"
        params.append(limit)
        rows = _rows(conn, sql, tuple(params))
    for r in rows:
        try:
            r["arguments"] = json.loads(r.pop("arguments_json"))
        except (json.JSONDecodeError, KeyError):
            pass
    return rows


@mcp.tool()
def find_solution_packs(connector: str | None = None,
                        q: str | None = None,
                        limit: int = 15) -> dict[str, Any]:
    """Find shipped solution packs, by the connector they use or by name.

    Backed by the Content Hub pack record (`solution_packs`,
    `solution_pack_connectors`, `solution_pack_deps`), which the pack zips do
    not carry -- it is captured at harvest time by `harvest_solution_packs`.

    This answers a question step frequency cannot: *which packs actually use
    this connector*. A connector called a hundred times inside one pack and
    nowhere else looks dominant in `find_step_examples` but is in fact a
    single-pack idiom. Use this before treating a corpus pattern as canonical,
    and to find a shipped pack to read as a worked example.

    Args:
        connector: filter to packs using this connector, matched against both
                   apiName ('activedirectory') and label ('Active Directory').
        q:         substring matched against pack name, label, or category.
        limit:     max packs (default 15).

    Returns: `{packs: [...], total_matched}`, each pack carrying its
    connectors, its pack-level prerequisites, and `steps_ingested` -- how many
    of its steps are in the corpus (0 means the pack ships no playbooks, which
    is common for module/dashboard-only packs).
    """
    with _db() as conn:
        # A slim packaged catalog may predate these tables; say so rather than
        # surfacing a bare `no such table` from a tool that looks healthy.
        have = {r["name"] for r in _rows(
            conn, "SELECT name FROM sqlite_master WHERE type='table' "
                  "AND name LIKE 'solution_pack%'", ())}
        if "solution_packs" not in have:
            return _err("no_pack_catalog",
                        "This catalog has no solution-pack tables. Run "
                        "`python -m tooling.harvest_solution_packs --from-repo` "
                        "then `python -m tooling.probes.probe_playbook_steps`.")

        sql = ["SELECT DISTINCT p.name, p.label, p.version, p.category,"
               " p.dir_name, p.min_fsr FROM solution_packs p"]
        params: list[Any] = []
        if connector:
            sql.append("JOIN solution_pack_connectors c ON c.pack_name = p.name")
        where = []
        if connector:
            where.append("(c.connector LIKE '%' || ? || '%'"
                         " OR c.label LIKE '%' || ? || '%')")
            params += [connector, connector]
        if q:
            where.append("(p.name LIKE '%' || ? || '%' OR p.label LIKE '%' || ? ||"
                         " '%' OR p.category LIKE '%' || ? || '%')")
            params += [q, q, q]
        if where:
            sql.append("WHERE " + " AND ".join(where))
        sql.append("ORDER BY p.name LIMIT ?")
        params.append(limit)
        packs = _rows(conn, " ".join(sql), tuple(params))

        for p in packs:
            p["connectors"] = [
                r["connector"] for r in _rows(
                    conn, "SELECT connector FROM solution_pack_connectors "
                          "WHERE pack_name = ? ORDER BY connector", (p["name"],))]
            p["depends_on"] = [
                r["depends_on"] for r in _rows(
                    conn, "SELECT depends_on FROM solution_pack_deps "
                          "WHERE pack_name = ? ORDER BY depends_on", (p["name"],))]
            # sp_harvest source_path embeds the on-disk `<name>-<version>` dir,
            # which is the only link from an ingested step back to its pack.
            p["steps_ingested"] = _rows(
                conn, "SELECT COUNT(*) AS n FROM playbook_steps "
                      "WHERE source_path LIKE ?",
                (f"%/{p['dir_name']}/%",))[0]["n"]
    return {"packs": packs, "total_matched": len(packs)}


# ---------------------------------------------------------------------------
# find_step_recipe -- prebuilt + validated step fragments
# ---------------------------------------------------------------------------

@mcp.tool()
def find_step_recipe(intent: str = "",
                     connector: str | None = None,
                     step_type: str | None = None,
                     limit: int = 5) -> dict[str, Any]:
    """Look up prebuilt YAML step fragments by intent.

    Each recipe is a small block of one or more steps that is known to
    compile clean (CI-validated). Use this BEFORE drafting common
    patterns from scratch -- it eliminates the validate-fix-validate
    cascade for things like:

      - manual_input as the trigger (no `start` step)
      - approve/reject gates
      - FortiGate block_ip with the correct param set per method
      - set_variable shape (arg_list, not step_variables)

    Args:
        intent: natural-language description of what you're trying to
                build, e.g. "block an ip on fortigate using a policy".
        connector: optional filter -- only return recipes bound to this
                   connector (e.g. 'fortigate-firewall'). Generic
                   recipes (no connector binding) still match.
        step_type: optional filter -- only recipes that include this step
                   type (e.g. 'manual_input', 'connector', 'set_variable').
        limit: max recipes to return (default 5).

    Returns: {ok: true, matches: [{name, description, intent_keywords,
             connector, step_types, steps_yaml, notes}, ...]}.
    """
    sys.path.insert(0, str(REPO_ROOT / "tooling"))
    from recipes import step_lookup
    matches = step_lookup.find(
        intent=intent, connector=connector, step_type=step_type, limit=limit,
    )
    return {
        "ok": True,
        "matches": [r.to_dict() for r in matches],
        "hint": (
            "Each `steps_yaml` block is paste-ready. Replace placeholders "
            "(<UPPER_CASE> tokens) with your values; update step names "
            "and `next:` targets to fit your playbook. Recipes are "
            "compile-validated -- no validation cascade if you keep the "
            "selected param values consistent with the recipe's group."
        ),
    } if matches else {
        "ok": True,
        "matches": [],
        "hint": (
            f"No recipes matched intent={intent!r}. Fall back to "
            f"find_operation + get_op_schema; check `param_groups_by_select` "
            f"on the schema to pick a coherent param set in one shot."
        ),
    }


# ---------------------------------------------------------------------------
# validate_yaml
# ---------------------------------------------------------------------------

@mcp.tool()
def search_api_examples(query: str, product: str | None = None,
                        limit: int = 10) -> list[dict[str, Any]]:
    """Search the api_examples_catalog (207k entries / 6,927 products).

    Use when no native FortiSOAR connector exists for the target vendor.
    Pair the result with `synthesize_http_step` to emit an HTTP-connector
    step pre-filled with method/path/auth/params drawn from a real example.

    Returns: list of {entry_id, product, action, http_method, http_path,
    auth_method, description, source_url, code_snippet (if any)}.
    """
    with _db() as conn:
        try:
            sql = (
                "SELECT e.id AS entry_id, p.name AS product, e.action, "
                "e.http_method, e.http_path, e.auth_method, e.description, "
                "e.source_url, e.code_snippet, e.code_lang "
                "FROM catalog.entries_fts f "
                "JOIN catalog.entries e ON e.rowid = f.rowid "
                "JOIN catalog.products p ON p.id = e.product_id "
                "WHERE entries_fts MATCH ? "
            )
            params: list[Any] = [query]
            if product:
                sql += "AND p.normalized LIKE ? "
                params.append(f"%{product.lower()}%")
            sql += "ORDER BY e.example_quality DESC LIMIT ?"
            params.append(limit)
            return _rows(conn, sql, tuple(params))
        except sqlite3.OperationalError as exc:
            return [{"error": f"catalog DB unavailable: {exc}"}]