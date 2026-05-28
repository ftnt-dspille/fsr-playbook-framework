"""Catalog-backed MCP tools — read-only over `catalog.sqlite` (attached
as `catalog`).

Three lookups + one composer:
  find_api_product   — fuzzy vendor-name search across 6,927 products
  find_api_example   — FTS over 207k API entries
  find_api_fixture   — exact-shape HTTP fixture with schemas
  propose_http_fallback — deterministic decision tree
                          (native op > api_call > http fixture)

The catalog is attached in `_shared._db()` when `CATALOG_DB_PATH`
exists. If it isn't, these tools return a structured
`catalog_unavailable` envelope rather than throwing — the rest of
fsrpb keeps working.

Implements Phase 0 + 0.5 of `docs/plans/CONNECTOR_INTEGRATION_PLAN.md`.
"""
from __future__ import annotations

import difflib
import json
import re
import sqlite3
from typing import Any
from urllib.parse import urlparse

from ._shared import _db, _err, _rows, mcp
from .tools_discovery import find_operation


_BASE_URL_HINT = "{{ vars.input.params.<vendor>_base_url }}"
_TOKEN_HINT = "{{ vars.input.params.<vendor>_token }}"


# Auth-prelude endpoints that appear in test fixtures for almost every
# vendor (because tests run an auth call before the real one). They
# poison "give me a fixture for vendor X" because they're high-
# confidence and low-id. We demote them so the intent-relevant fixture
# wins. Not deleted: when intent IS auth (e.g. "get token"), we still
# need them.
_AUTH_PRELUDE_RE = re.compile(
    r"/(?:oauth2?/token|oauth2?/authorize|auth/login|authenticate|sessions?/login|"
    r"login/sessions|token/get|access_token|refresh_token|api/login|service_token|"
    r"oauth/access_token|connect/token|identity/connect|api/v\d/login)\b",
    re.IGNORECASE,
)


def _is_auth_prelude(url_template: str) -> bool:
    return bool(_AUTH_PRELUDE_RE.search(url_template or ""))


_INTENT_STOPWORDS = frozenset({
    "a", "an", "the", "of", "for", "with", "on", "in", "to", "from",
    "and", "or", "by", "at", "is", "are", "be", "this", "that",
    "endpoint", "api", "via",  # too generic for catalog ranking
})


def _intent_tokens(intent: str) -> list[str]:
    """Stem-ish tokens from a free-form intent string for url-template
    matching. Singular/plural collapse, stopwords filtered. Bag-of-words
    overlap is good enough — the catalog isn't deep enough for
    semantic embeddings to pay off."""
    raw = re.findall(r"[A-Za-z][A-Za-z0-9_]+", (intent or "").lower())
    tokens: list[str] = []
    seen: set[str] = set()
    for t in raw:
        if t in _INTENT_STOPWORDS or len(t) < 3:
            continue
        # Trim trailing 's' so "incidents" matches "/incident".
        stem = t[:-1] if t.endswith("s") and len(t) > 4 else t
        if stem in seen:
            continue
        seen.add(stem)
        tokens.append(stem)
    return tokens


def _intent_overlap_score(url_template: str, tokens: list[str]) -> int:
    """How many intent tokens appear in the url path. Higher is better.
    Trivial bag-of-words; effective in practice because path tokens
    line up with intent verbs+nouns (`/incident`, `/comment`, `/quarantine`)."""
    if not tokens:
        return 0
    lower = (url_template or "").lower()
    return sum(1 for t in tokens if t in lower)


# Map intent verbs to expected HTTP methods. Used as a soft tie-breaker
# when the catalog has multiple fixtures whose paths overlap the
# intent equally — a "create" intent that comes back as GET is almost
# always the wrong fixture (the GET being a setup/list call from the
# test).
_VERB_METHOD: dict[str, str] = {
    "create": "POST", "add": "POST", "post": "POST", "submit": "POST",
    "send": "POST", "publish": "POST", "open": "POST",
    "update": "PUT", "modify": "PUT", "edit": "PUT", "patch": "PATCH",
    "set": "PUT", "change": "PUT", "replace": "PUT",
    "delete": "DELETE", "remove": "DELETE", "close": "DELETE",
    "destroy": "DELETE",
    "get": "GET", "fetch": "GET", "list": "GET", "find": "GET",
    "search": "GET", "lookup": "GET", "show": "GET", "read": "GET",
    "query": "GET", "describe": "GET",
}


def _expected_method_for_intent(tokens: list[str]) -> str | None:
    """First intent token that maps to a method; None if no verb hit.
    Earlier tokens win because users typically lead with the verb
    ('create incident', 'block ip')."""
    for t in tokens:
        m = _VERB_METHOD.get(t)
        if m:
            return m
    return None


# ---------------------------------------------------------------------------
# Catalog availability — single source of truth
# ---------------------------------------------------------------------------


def _catalog_available(conn: sqlite3.Connection) -> bool:
    """The catalog ATTACH happens best-effort in `_db()`. Confirm it
    actually went through by checking the `catalog` schema."""
    try:
        row = conn.execute(
            "SELECT name FROM catalog.sqlite_master "
            "WHERE type='table' AND name='entries' LIMIT 1"
        ).fetchone()
        return row is not None
    except sqlite3.Error:
        return False


def _no_catalog_err() -> dict[str, Any]:
    return _err(
        "catalog_unavailable",
        "The api_examples_catalog DB is not attached. Set "
        "FSRPB_API_CATALOG to its path or download via `fsrpb train "
        "--with-api-catalog` (planned).",
        suggestions=[
            "Confirm $HOME/PycharmProjects/Miscellaneous/fortisoar/corpus_builder/catalog.sqlite exists (moved 2026-05 from api_examples_catalog/)",
            "Run `python -c \"from probes.common import CATALOG_DB_PATH; print(CATALOG_DB_PATH, CATALOG_DB_PATH.exists())\"`",
        ],
    )


# ---------------------------------------------------------------------------
# find_api_product
# ---------------------------------------------------------------------------


@mcp.tool()
def find_api_product(name: str, limit: int = 5) -> dict[str, Any]:
    """Fuzzy-search the 6,927 vendor products in the API catalog.

    Use when the user mentions a vendor and you need to confirm the
    canonical product key the rest of the catalog tools use. Misspellings
    are expected; this matches via normalized name + difflib fallback.

    Returns `{matches: [{id, name, normalized, category}], suggestion?}`.
    """
    conn = _db()
    try:
        if not _catalog_available(conn):
            return _no_catalog_err()
        needle = (name or "").strip()
        if not needle:
            return _err("empty_query", "name must be non-empty")
        norm = re.sub(r"\W+", "", needle.lower())
        rows = _rows(
            conn,
            """SELECT id, name, normalized, category
               FROM catalog.products
               WHERE normalized LIKE '%' || ? || '%'
               ORDER BY length(normalized) ASC
               LIMIT ?""",
            (norm, limit),
        )
        out: dict[str, Any] = {"matches": rows}
        if not rows:
            all_names = [
                r["name"] for r in conn.execute(
                    "SELECT name FROM catalog.products"
                ).fetchall()
            ]
            close = difflib.get_close_matches(needle, all_names, n=limit,
                                              cutoff=0.5)
            if close:
                out["suggestion"] = (
                    f"no product matched {needle!r}; closest: {close}"
                )
                out["near"] = close
            else:
                out["suggestion"] = (
                    f"no product matched {needle!r}; this vendor may not be "
                    "in the catalog (6,927 products total)"
                )
        return out
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# find_api_example
# ---------------------------------------------------------------------------


@mcp.tool()
def find_api_example(product: str, q: str = "", limit: int = 5,
                     verbose: bool = False) -> dict[str, Any]:
    """FTS5 search over the 207k API command-catalogue entries.

    Returns slim rows by default: `(action, http_method, http_path,
    source_url)`. `verbose=True` adds `description, parameters_json,
    code_snippet`.

    Use when the user wants to do an action against a vendor and you
    need to ground the call in a real example — e.g. "splunk run
    search", "servicenow create incident". For an exact request/
    response pair with schemas, use `find_api_fixture` instead.
    """
    conn = _db()
    try:
        if not _catalog_available(conn):
            return _no_catalog_err()
        cols = ("e.action, e.http_method, e.http_path, e.source_url"
                + (", e.description, e.parameters_json, e.code_snippet"
                   if verbose else ""))
        params: tuple
        sql: str
        if q:
            # FTS over entries_fts joined to entries + products.
            # FTS5's MATCH operator does not accept a schema-qualified
            # table name, so use the alias `f`.
            sql = f"""SELECT {cols}, p.name AS product
                      FROM catalog.entries_fts f
                      JOIN catalog.entries e ON e.id = f.rowid
                      JOIN catalog.products p ON p.id = e.product_id
                      WHERE p.normalized LIKE '%' || ? || '%'
                        AND entries_fts MATCH ?
                      ORDER BY rank
                      LIMIT ?"""
            params = (re.sub(r"\W+", "", product.lower()), q, limit)
        else:
            sql = f"""SELECT {cols}, p.name AS product
                      FROM catalog.entries e
                      JOIN catalog.products p ON p.id = e.product_id
                      WHERE p.normalized LIKE '%' || ? || '%'
                      ORDER BY e.example_quality DESC, e.id
                      LIMIT ?"""
            params = (re.sub(r"\W+", "", product.lower()), limit)
        try:
            rows = _rows(conn, sql, params)
        except sqlite3.OperationalError as exc:
            # FTS query syntax errors return a structured envelope rather
            # than blow up the chat turn.
            return _err("fts_query_error", f"{exc}",
                        suggestions=[
                            "Try a simpler keyword (no quotes / operators)",
                        ])
        out: dict[str, Any] = {"matches": rows}
        if not rows:
            out["suggestion"] = (
                f"no entries for product={product!r} q={q!r}. Try "
                "find_api_product first to confirm the vendor name."
            )
        return out
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# find_api_fixture
# ---------------------------------------------------------------------------


def _shape_fixture(row: dict[str, Any]) -> dict[str, Any]:
    """Slim fixture row → tool result shape. Schemas are decoded when
    present so the agent can read them as objects, not strings."""
    out: dict[str, Any] = {
        "fixture_id": row["id"],
        "method": row["method"],
        "url_template": row["url_template"],
        "confidence": row["confidence"],
        "auth_method": row["auth_method"],
        "source_repo": row["source_repo"],
        "operation_id": row.get("operation_id"),
        "summary": row.get("summary"),
    }
    for json_col, out_key in (
        ("response_schema_json", "response_schema"),
        ("parameters_schema_json", "parameters_schema"),
        ("query_params_json", "query_params"),
        ("request_body_json", "request_body"),
    ):
        raw = row.get(json_col)
        if raw:
            try:
                out[out_key] = json.loads(raw)
            except json.JSONDecodeError:
                pass  # skip mangled rows
    return out


@mcp.tool()
def find_api_fixture(product: str, method: str | None = None,
                     path_substring: str | None = None,
                     limit: int = 3) -> dict[str, Any]:
    """Find HTTP request/response fixtures for a product.

    The 36,015 fixtures table is OpenAPI-grounded and the right source
    when you need an exact request shape + a response schema (e.g.
    when authoring an `http` connector fallback step, or when the
    stored `operations.output_schema` looks stale).

    Filter by `method` (GET, POST, …) and/or by a `path_substring`
    that matches `url_template` (e.g. "/network_lists" for Akamai's
    block API). Higher-confidence rows are returned first.
    """
    conn = _db()
    try:
        if not _catalog_available(conn):
            return _no_catalog_err()
        clauses = ["p.normalized LIKE '%' || ? || '%'"]
        params: list[Any] = [re.sub(r"\W+", "", product.lower())]
        if method:
            clauses.append("UPPER(h.method) = ?")
            params.append(method.upper())
        if path_substring:
            clauses.append("h.url_template LIKE '%' || ? || '%'")
            params.append(path_substring)
        sql = f"""
            SELECT h.id, h.method, h.url_template, h.confidence,
                   h.auth_method, h.source_repo, h.operation_id,
                   h.summary, h.response_schema_json,
                   h.parameters_schema_json, h.query_params_json,
                   h.request_body_json
            FROM catalog.http_fixtures h
            JOIN catalog.products p ON p.id = h.product_id
            WHERE {' AND '.join(clauses)}
            ORDER BY CASE h.confidence
                       WHEN 'high' THEN 0
                       WHEN 'medium' THEN 1
                       ELSE 2 END,
                     h.id
            LIMIT ?
        """
        params.append(limit)
        rows = _rows(conn, sql, tuple(params))
        out: dict[str, Any] = {
            "matches": [_shape_fixture(r) for r in rows],
        }
        if not rows:
            out["suggestion"] = (
                "no http_fixtures matched. Try without `method=` first, "
                "then narrow with `path_substring=`. Confirm product "
                "name with find_api_product if unsure."
            )
        return out
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Phase 0.5 — propose_http_fallback
# ---------------------------------------------------------------------------


_METHOD_TO_HTTP_OP = {
    "GET": "http_get",
    "POST": "http_post",
    "PUT": "http_put",
    "PATCH": "http_patch",
    "DELETE": "http_delete",
    "HEAD": "http_head",
    "OPTIONS": "http_options",
}


def _looks_like_api_call_op(op_name: str) -> bool:
    """True for the various names connectors use for their generic
    'pass-through' escape-hatch operation."""
    lc = op_name.lower()
    return (
        "api_call" in lc
        or "generic_api" in lc
        or "raw_api" in lc
        or "http_request" in lc
    )


def _split_url_template(url_template: str) -> tuple[str, str]:
    """Split `https://host/path?query` into (base, path_with_query).

    Returns ('', url_template) if it isn't an absolute URL.
    """
    if not url_template:
        return "", ""
    if url_template.startswith(("http://", "https://")):
        parsed = urlparse(url_template)
        base = f"{parsed.scheme}://{parsed.netloc}"
        path = parsed.path or "/"
        if parsed.query:
            path += "?" + parsed.query
        return base, path
    return "", url_template


def _render_fallback_step(fixture: dict[str, Any], *,
                          step_name: str) -> tuple[dict[str, Any], list[str]]:
    """Materialize a ready-to-paste connector step from a fixture row.

    Returns (step_dict, warnings[]). The step is shaped for fsrpb YAML
    (friendly form), not raw FSR JSON.
    """
    warnings: list[str] = []
    method = (fixture.get("method") or "GET").upper()
    op = _METHOD_TO_HTTP_OP.get(method, "http_get")
    base, path = _split_url_template(fixture.get("url_template") or "")
    if base:
        url_expr = f"{_BASE_URL_HINT.replace('<vendor>', 'vendor')}{path}"
        warnings.append(
            f"fixture's base URL is {base!r}; the step uses "
            "`{{ vars.input.params.vendor_base_url }}` placeholder — wire the "
            "real base via connector config or workflow input."
        )
    else:
        url_expr = path

    auth_method = (fixture.get("auth_method") or "").lower()
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if auth_method in {"bearer", "oauth2", "token", "jwt"}:
        headers["Authorization"] = f"Bearer {_TOKEN_HINT.replace('<vendor>', 'vendor')}"
        warnings.append(
            "auth=bearer — fill `vars.input.params.vendor_token` from "
            "connector config or vault before running."
        )
    elif auth_method in {"basic", "basic_auth"}:
        headers["Authorization"] = "Basic {{ vars.input.params.vendor_basic_auth }}"
        warnings.append(
            "auth=basic — base64-encode user:password into "
            "`vars.input.params.vendor_basic_auth`."
        )
    elif auth_method in {"apikey", "api_key", "x-api-key"}:
        headers["X-Api-Key"] = "{{ vars.input.params.vendor_api_key }}"
        warnings.append(
            "auth=api_key — set `vars.input.params.vendor_api_key`."
        )
    elif auth_method:
        warnings.append(
            f"auth_method={auth_method!r} is not standard bearer/basic/"
            "apikey — adjust headers manually."
        )
    else:
        warnings.append(
            "fixture has no auth_method hint — confirm the API's auth "
            "requirement and add headers accordingly."
        )

    params_block: dict[str, Any] = {
        "rest_api": url_expr,
        "header": headers,
    }
    qp = fixture.get("query_params")
    if isinstance(qp, dict) and qp:
        params_block["parameter"] = qp
    body = fixture.get("request_body")
    if body is not None and method in {"POST", "PUT", "PATCH"}:
        params_block["data"] = body
        if isinstance(body, dict):
            warnings.append(
                "request body keys with `{path_param}`-style placeholders "
                "should be replaced with `{{ vars.steps.<predecessor>.<key> }}` "
                "or `{{ vars.input.params.<key> }}`."
            )

    step = {
        "type": "connector",
        "name": step_name,
        "connector": "http",
        "op": op,
        "arguments": {"params": params_block},
    }
    if fixture.get("confidence") not in (None, "high"):
        warnings.append(
            f"fixture confidence={fixture['confidence']!r} — verify the "
            "request shape against your tenant's API version before "
            "shipping to prod."
        )
    return step, warnings


def _intent_step_name(intent: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9 ]+", " ", intent.strip()).strip()
    if not cleaned:
        return "Http Fallback Call"
    words = [w.capitalize() for w in cleaned.split()][:5]
    return " ".join(words) or "Http Fallback Call"


@mcp.tool()
def propose_http_fallback(vendor: str, intent: str, *,
                          prefer_native: bool = True) -> dict[str, Any]:
    """Decide how to invoke `intent` against `vendor` and emit the step.

    Deterministic decision tree (LLM does NOT pick the path):

      1. `find_operation(vendor, intent)` returns a hit AND prefer_native
         → decision = `native_op`
      2. The connector exposes a generic api_call / generic_api_call
         / raw_api / http_request op
         → decision = `api_call` (auth + base URL already wired by FSR)
      3. `find_api_fixture(vendor, ...)` returns a catalog row
         → decision = `http_fixture`; emit `http` connector step
      4. Otherwise → decision = `no_grounded_shape` with suggestions

    The agent MUST NOT respond "FSR can't do this" while
    `decision != "no_grounded_shape"`. The fallback step is real and
    runnable; auth lives in `warnings`.
    """
    if not vendor or not intent:
        return _err("missing_args",
                    "both `vendor` and `intent` are required")

    warnings: list[str] = []

    # ---- 1. native op ----
    native: dict[str, Any] | None = None
    if prefer_native:
        op_search = find_operation(vendor, q=intent, limit=3)
        matches = op_search.get("matches") or []
        if matches and not op_search.get("suggestion"):
            top = matches[0]
            native = {
                "connector": vendor,
                "op_name": top.get("op_name"),
                "title": top.get("title"),
            }
            return {
                "ok": True,
                "decision": "native_op",
                "step": {
                    "type": "connector",
                    "name": _intent_step_name(intent),
                    "connector": vendor,
                    "op": top.get("op_name"),
                    "arguments": {"params": {}},
                },
                "native": native,
                "fixture": None,
                "warnings": [
                    "Step emitted with empty `arguments.params`; call "
                    "`get_op_schema` to fill required params.",
                ],
                "reason": (
                    f"native op {top.get('op_name')!r} on {vendor!r} matches "
                    f"intent {intent!r}; preferred over fallback."
                ),
            }

    # ---- 2. api_call escape hatch ----
    all_ops = find_operation(vendor, q="", limit=200)
    api_call_op = None
    for op in all_ops.get("matches") or []:
        if _looks_like_api_call_op(op.get("op_name") or ""):
            api_call_op = op
            break
    if api_call_op:
        warnings.append(
            "Using the connector's generic API-call op — auth + base URL "
            "are handled by the connector's config. Fill request `method`, "
            "`endpoint`, and `payload` from the catalog fixture you "
            "consulted (call find_api_fixture)."
        )
        return {
            "ok": True,
            "decision": "api_call",
            "step": {
                "type": "connector",
                "name": _intent_step_name(intent),
                "connector": vendor,
                "op": api_call_op["op_name"],
                "arguments": {"params": {}},
            },
            "native": None,
            "fixture": None,
            "warnings": warnings,
            "reason": (
                f"{vendor!r} has no op matching {intent!r}, but its generic "
                f"{api_call_op['op_name']!r} op can pass through the call "
                "with connector auth."
            ),
        }

    # ---- 3. catalog http fixture ----
    # Pull a wider candidate set than we'll keep so we can re-rank by
    # intent-token overlap and demote auth-prelude rows. find_api_fixture
    # alone orders by confidence + id only, which surfaces /oauth/token
    # for nearly every vendor (it's the most common high-confidence
    # fixture because tests always run an auth call first).
    fix_result = find_api_fixture(vendor, limit=25)
    if fix_result.get("ok") is False:
        return fix_result  # catalog_unavailable, propagated
    fixtures = fix_result.get("matches") or []
    intent_tokens = _intent_tokens(intent)
    expected_method = _expected_method_for_intent(intent_tokens)

    def _rank(f: dict[str, Any]) -> tuple[int, int, int, int, int]:
        url = f.get("url_template") or ""
        conf = f.get("confidence") or "low"
        # Sort key (Python ascending). Smaller = better.
        # 1. demote auth-prelude (unless the intent IS auth)
        is_auth = _is_auth_prelude(url)
        intent_is_auth = any(t in {"token", "auth", "login", "authent"}
                             for t in intent_tokens)
        auth_penalty = 1 if (is_auth and not intent_is_auth) else 0
        # 2. higher intent-token overlap = better (negate so smaller wins).
        # This DOMINATES the method tie-break: an agent can flip GET→POST
        # by hand, but cannot guess the correct path. Pinning the path
        # is the high-value signal — the catalog often has the path
        # for one method but not the other.
        overlap = -_intent_overlap_score(url, intent_tokens)
        # 3. method matches the intent verb (create→POST etc.)
        method = (f.get("method") or "").upper()
        method_penalty = (0 if expected_method is None
                          or method == expected_method else 1)
        # 4. confidence tier
        conf_rank = {"high": 0, "medium": 1}.get(conf, 2)
        # 5. fallback to fixture_id for deterministic tie-break
        return (auth_penalty, overlap, method_penalty, conf_rank,
                f.get("fixture_id") or 0)

    if fixtures:
        fixtures = sorted(fixtures, key=_rank)
        chosen = fixtures[0]
        step, fixture_warnings = _render_fallback_step(
            chosen, step_name=_intent_step_name(intent),
        )
        warnings.extend(fixture_warnings)
        return {
            "ok": True,
            "decision": "http_fixture",
            "step": step,
            "native": None,
            "fixture": {
                "fixture_id": chosen.get("fixture_id"),
                "method": chosen.get("method"),
                "url_template": chosen.get("url_template"),
                "confidence": chosen.get("confidence"),
                "auth_method": chosen.get("auth_method"),
                "source_repo": chosen.get("source_repo"),
                "operation_id": chosen.get("operation_id"),
            },
            "warnings": warnings,
            "reason": (
                f"{vendor!r} has neither a native op matching {intent!r} nor "
                f"a generic api_call op. Falling back to FSR's `http` "
                f"connector grounded in catalog fixture #{chosen.get('fixture_id')}."
            ),
        }

    # ---- 4. nothing ----
    return _err(
        "no_grounded_shape",
        f"could not propose a fallback for {vendor!r} / {intent!r}",
        suggestions=[
            "Call find_api_product(vendor) to confirm the vendor is in the catalog",
            "Call find_api_example(product=..., q=...) with a broader query",
            "Author a custom connector (see CONNECTOR_INTEGRATION_PLAN Phase 1+) if this vendor must be supported long-term",
        ],
        vendor=vendor,
        intent=intent,
    )
