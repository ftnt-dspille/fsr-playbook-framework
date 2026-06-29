"""MCP tools: Tools Discovery"""
from __future__ import annotations
from . import _shared

import difflib
import json
import sqlite3
import sys
from typing import Any

from ._shared import (
    mcp,
    _err,
    _db,
    _rows,
    _verifications_for,
    REPO_ROOT,
    catalog_override,
)
# Import DB_PATH for local use
DB_PATH = _shared.DB_PATH

# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
def get_step_arg_schema(step_type: str) -> dict[str, Any]:
    """JSON Schema for a step type's `arguments`, for pre-compile validation.

    Returns `{step_type, json_schema}` when the type is modeled (coverage grows
    over time as Phase 2 lands more step models; the live set is always returned
    in `modeled_types`), else
    `{step_type, json_schema: null, modeled: false, note, modeled_types}` so the
    caller can tell "not modeled yet" from an empty schema and discover what IS
    available.
    """
    from ..compiler.typed_args.schema import emit_step_arg_schema, list_modeled_step_types

    schema = emit_step_arg_schema(step_type)
    if schema is None:
        return {
            "step_type": step_type,
            "json_schema": None,
            "modeled": False,
            "note": f"{step_type!r} has no typed-args model yet; arguments are "
                    "validated imperatively at compile time.",
            "modeled_types": list_modeled_step_types(),
        }
    return {"step_type": step_type, "json_schema": schema, "modeled": True}


@mcp.tool()
def find_connector(q: str, limit: int = 15,
                   verbose: bool = False,
                   db_path: str | None = None) -> dict[str, Any]:
    """Fuzzy-search connectors by name, label, category, or description.

    Default response is terse (name/label/category only) to keep tool
    cost down. Pass `verbose=True` for full descriptions.

    Returns `{matches, suggestion?}`. When the query has zero hits we
    suggest a near-match instead of leaving the agent guessing.

    `db_path` (optional): search a specific catalog (e.g. a pyfsr warmed cache)
    instead of the packaged slim one.
    """
    if db_path is not None:
        with catalog_override(db_path):
            return find_connector(q, limit, verbose, db_path=None)
    with _db() as conn:
        cols = ("name, label, category, description" if verbose
                else "name, label, category")
        rows = _rows(
            conn,
            f"""SELECT {cols}
               FROM connectors
               WHERE name   LIKE '%' || ? || '%'
                  OR label  LIKE '%' || ? || '%'
                  OR category LIKE '%' || ? || '%'
                  OR description LIKE '%' || ? || '%'
               ORDER BY
                 (name LIKE ? || '%') DESC,
                 name
               LIMIT ?""",
            (q, q, q, q, q, limit),
        )
        if not rows:
            # Broaden: word-by-word
            words = q.split()
            if words:
                w = words[0]
                rows = _rows(
                    conn,
                    f"""SELECT {cols}
                       FROM connectors
                       WHERE name LIKE '%'||?||'%' OR label LIKE '%'||?||'%'
                       ORDER BY name LIMIT ?""",
                    (w, w, limit),
                )
        failed: list[str] = []
        if rows:
            verifs = _verifications_for(
                conn, "connector", [r["name"] for r in rows]
            )
            for r in rows:
                v = verifs.get(r["name"])
                if v:
                    r["verification"] = v
                    if v["status"] == "tested_fail":
                        failed.append(r["name"])
            rows.sort(key=lambda r: (
                0 if (r.get("verification") or {}).get("status") == "tested_pass" else
                2 if (r.get("verification") or {}).get("status") == "tested_fail" else 1
            ))
        out: dict[str, Any] = {"matches": rows}
        if failed:
            out["warning"] = (
                f"connector(s) {failed} have a tested_fail verification "
                "in the reference store; investigate before authoring."
            )
        if not rows:
            # Surface a near-match so the agent doesn't loop guessing
            # connector names. Same difflib pass the resolver uses.
            all_names = [r["name"] for r in _rows(
                conn, "SELECT name FROM connectors", ()
            )]
            close = difflib.get_close_matches(q, all_names, n=3, cutoff=0.45)
            if close:
                out["suggestion"] = (
                    f"no exact matches for {q!r}; did you mean one of "
                    f"{close}? Pass one of those as `q=` to retry."
                )
                out["near"] = close
            else:
                out["suggestion"] = (
                    f"no matches and no close suggestions for {q!r}. "
                    f"Try a broader keyword (vendor name, action verb)."
                )
        return out


# ---------------------------------------------------------------------------
# find_operation
# ---------------------------------------------------------------------------

@mcp.tool()
def find_operation(connector: str, q: str = "", limit: int = 10,
                   verbose: bool = False,
                   db_path: str | None = None) -> dict[str, Any]:
    """List or search operations for a connector.

    Pass `connector` as the connector name (from find_connector).
    `q` is an optional substring filter on op name, title, or description.

    Default response is terse (op_name + title only). Pass `verbose=True`
    for descriptions. Returns `{matches, suggestion?}`. On zero hits,
    suggests near-matching ops so the agent doesn't loop guessing.

    When the query matches exactly one op, the response also embeds a
    slim `schema` — skip the follow-up `get_op_schema` call in that
    case. Multi-match responses stay terse so the agent can still
    disambiguate before pulling a schema.

    `db_path` (optional): search a specific catalog (e.g. a pyfsr warmed cache).
    """
    if db_path is not None:
        with catalog_override(db_path):
            return find_operation(connector, q, limit, verbose, db_path=None)
    with _db() as conn:
        cols = ("op_name, title, description, annotation" if verbose
                else "op_name, title")
        if q:
            rows = _rows(
                conn,
                f"""SELECT {cols}
                   FROM operations
                   WHERE connector_name = ?
                     AND (op_name LIKE '%'||?||'%'
                          OR title LIKE '%'||?||'%'
                          OR description LIKE '%'||?||'%')
                   ORDER BY op_name LIMIT ?""",
                (connector, q, q, q, limit),
            )
        else:
            rows = _rows(
                conn,
                f"""SELECT {cols}
                   FROM operations
                   WHERE connector_name = ?
                   ORDER BY op_name LIMIT ?""",
                (connector, limit),
            )
        op_failed: list[str] = []
        if rows:
            keys = [f"{connector}:{r['op_name']}" for r in rows]
            verifs = _verifications_for(conn, "operation", keys)
            for r in rows:
                v = verifs.get(f"{connector}:{r['op_name']}")
                if v:
                    r["verification"] = {k: vv for k, vv in v.items()
                                          if k != "notes_excerpt"
                                          or v["status"] == "tested_fail"}
                    if v["status"] == "tested_fail":
                        op_failed.append(r["op_name"])
            rows.sort(key=lambda r: (
                0 if (r.get("verification") or {}).get("status") == "tested_pass" else
                2 if (r.get("verification") or {}).get("status") == "tested_fail" else 1
            ))
        out: dict[str, Any] = {"matches": rows}
        if op_failed:
            out["warning"] = (
                f"op(s) {op_failed} on {connector!r} have a tested_fail "
                "verification (live execution failed previously); confirm "
                "params or pick another op."
            )
        if not rows:
            all_ops = [r["op_name"] for r in _rows(
                conn,
                "SELECT op_name FROM operations WHERE connector_name = ?",
                (connector,),
            )]
            if not all_ops:
                # Connector is itself unknown — bigger problem.
                out["suggestion"] = (
                    f"connector {connector!r} has no operations in the "
                    f"reference store. Verify the connector name with "
                    f"find_connector before searching its ops."
                )
            elif q:
                close = difflib.get_close_matches(q, all_ops, n=5, cutoff=0.4)
                out["suggestion"] = (
                    f"no operations matching {q!r} on {connector!r}; "
                    + (f"closest: {close}" if close
                       else f"this connector has {len(all_ops)} ops total — "
                            f"omit `q=` to list them all (or pass a more "
                            f"general keyword).")
                )
                if close:
                    out["near"] = close
        # Multi-match: attach a compact param SIGNATURE per op so the agent sees
        # each op's real param names BEFORE it picks one and calls run_op —
        # pre-empting the "choose an op, then guess its params" flail that wasted
        # ~8 calls in export sess-vtd15c5v (the agent guessed `ip`/`srcIP`/`host`
        # when the real param was `value (IP Address)`). One batched query,
        # top-level params only (sub-params stay in get_op_schema). Each entry is
        # {name, required, type, label} — the `label` (the param's human title,
        # e.g. "IP Address") is the disambiguator that stops the model from
        # substituting its own guessed name for an unintuitive one like `value`.
        # Single-match skips this; it gets the full slim schema below.
        if len(rows) > 1:
            names = [r["op_name"] for r in rows if r.get("op_name")]
            if names:
                ph = ",".join("?" * len(names))
                prows = _rows(
                    conn,
                    f"""SELECT op_name, param_name, title, type, required
                       FROM operation_params
                       WHERE connector_name = ?
                         AND op_name IN ({ph})
                         AND (parent_param_name IS NULL OR parent_param_name = '')
                       ORDER BY required DESC, ord""",
                    (connector, *names),
                )
                sig_by_op: dict[str, list[dict[str, Any]]] = {}
                for pr in prows:
                    entry: dict[str, Any] = {"name": pr["param_name"]}
                    if pr["required"]:
                        entry["required"] = True
                    if pr["type"]:
                        entry["type"] = pr["type"]
                    if pr["title"] and pr["title"] != pr["param_name"]:
                        entry["label"] = pr["title"]
                    sig_by_op.setdefault(pr["op_name"], []).append(entry)
                for r in rows:
                    # Only when known; absence stays silent (un-probed op) rather
                    # than asserting "no params" we can't prove.
                    if r.get("op_name") in sig_by_op:
                        r["params"] = sig_by_op[r["op_name"]]

        # When the search narrows to a single op, fold the slim schema
        # into the response so the agent can skip the follow-up
        # get_op_schema round-trip (saves ~1 LLM turn + ~6KB of cache).
        # Only triggers when there is exactly one match — multi-match
        # results stay terse so the agent can still disambiguate.
        if len(rows) == 1 and rows[0].get("op_name"):
            try:
                schema = get_op_schema(connector, rows[0]["op_name"],
                                       verbose=False)
                if isinstance(schema, dict) and schema.get("ok") is not False:
                    out["schema"] = schema
            except Exception:
                pass
        return out


# ---------------------------------------------------------------------------
# get_op_schema helpers — param dedup + per-select param groups
# ---------------------------------------------------------------------------

def _dedupe_params(params: list[dict]) -> list[dict]:
    """Collapse duplicate param_name rows into one entry per name.

    The reference store has one row per (param_name, parent_param_name,
    condition_value) — so a param visible under multiple conditions
    appears two or three times with the same name. The agent only needs
    one entry; aggregate the visibility rules into `applies_when`.
    """
    out: list[dict] = []
    by_name: dict[str, dict] = {}
    for p in params:
        name = p.get("param_name")
        if not name:
            out.append(p)
            continue
        existing = by_name.get(name)
        rule = None
        # Surface visibility predicates only when both columns exist on the
        # row (verbose path). Slim path drops parent/condition columns, so
        # this is a no-op there — applies_when stays empty.
        parent = p.get("parent_param_name")
        cond = p.get("condition_value")
        if parent:
            rule = {"parent": parent, "value": cond}
        if existing is None:
            entry = {k: v for k, v in p.items()
                     if k not in ("parent_param_name", "condition_value")}
            entry["applies_when"] = [rule] if rule else []
            by_name[name] = entry
            out.append(entry)
        else:
            if rule and rule not in existing["applies_when"]:
                existing["applies_when"].append(rule)
    # Drop empty applies_when so unconditional params stay clean.
    for entry in out:
        if entry.get("applies_when") == []:
            entry.pop("applies_when", None)
    return out


def _build_param_groups_by_select(
    rules: list[tuple[str, str | None, str | None]],
    param_types: dict[str, str],
    param_options: dict[str, list[str]],
    param_defaults: dict[str, str | None],
) -> dict[str, Any]:
    """Compute {select_param: {option_value: {params, nested_selects}}}.

    Walks the parent_param→child adjacency. For each top-level select
    (parent is None, type='select'), enumerates each option value and
    lists every param that becomes visible under that choice. Nested
    selects (selects whose own visibility depends on the parent option)
    are surfaced with their own option→param map so the agent can see
    the whole feasible neighborhood without iterating.

    Returns {} when no top-level select gates other params — most ops.
    """
    from collections import defaultdict
    children_of: dict[tuple[str, str], list[str]] = defaultdict(list)
    for name, parent, cond in rules:
        if parent is not None:
            children_of[(parent, str(cond))].append(name)
    # Top-level params (no parent rule).
    {n for n, p, _ in rules if p is not None}
    top_level = [n for n, p, _ in rules if p is None]
    # Top-level params that are NOT themselves conditioned by anyone are
    # the candidate gating selects. Among them, pick the ones of type
    # 'select' that have at least one child rule.
    gating: list[str] = []
    for n in top_level:
        if param_types.get(n) != "select":
            continue
        if any(parent == n for _, parent, _ in rules):
            gating.append(n)

    # Always-visible (top-level) non-select params and unconditional
    # nested params get included in every group too.
    unconditional = [n for n in top_level if n not in gating]

    groups: dict[str, Any] = {}
    for sel in gating:
        options = param_options.get(sel) or []
        per_option: dict[str, Any] = {}
        for opt in options:
            visible = list(unconditional)
            nested: dict[str, dict[str, list[str]]] = {}
            # Direct children of this select+option.
            direct = list(children_of.get((sel, opt), []))
            for child in direct:
                if child in visible:
                    continue
                visible.append(child)
                # If a child is itself a select with its own option-keyed
                # children, expose them as a nested map.
                if param_types.get(child) == "select":
                    child_options = param_options.get(child) or []
                    child_map: dict[str, list[str]] = {}
                    for c_opt in child_options:
                        c_kids = children_of.get((child, c_opt), [])
                        if c_kids:
                            child_map[c_opt] = list(c_kids)
                    if child_map:
                        nested[child] = child_map
            entry: dict[str, Any] = {"params": visible}
            if nested:
                entry["nested_selects"] = nested
            per_option[opt] = entry
        per_option["_options"] = options
        if param_defaults.get(sel):
            per_option["_default"] = param_defaults[sel]
        groups[sel] = per_option
    return groups


def _build_visibility_block(
    rules: list[tuple[str, str | None, str | None]],
) -> dict[str, Any]:
    """Flat-view sibling of `param_groups_by_select`.

    Returns `{always: [...], when: {"<select>=<option>": [...], ...}}`.
    `always` lists params that have no gating rule. `when` keys are
    human-readable "<gating_param>=<option_value>" strings so the agent
    can scan once and pick the right branch.

    Returns `{}` when no params have visibility rules — most ops.
    """
    always: list[str] = []
    when: dict[str, list[str]] = {}
    any_gated = False
    seen_always: set[str] = set()
    for name, parent, cond in rules:
        if parent is None:
            if name not in seen_always:
                always.append(name)
                seen_always.add(name)
        else:
            any_gated = True
            key = f"{parent}={cond}" if cond is not None else f"{parent}=*"
            when.setdefault(key, []).append(name)
    if not any_gated:
        return {}
    out: dict[str, Any] = {"always": always}
    if when:
        out["when"] = when
    return out


def _parse_options(blob: Any) -> list[str]:
    if not blob:
        return []
    if isinstance(blob, list):
        return [str(x) for x in blob]
    try:
        parsed = json.loads(blob)
        return [str(x) for x in parsed] if isinstance(parsed, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _strip_default(raw: Any) -> str | None:
    """default_value rows in the store are JSON-quoted strings."""
    if raw in (None, ""):
        return None
    if isinstance(raw, str):
        try:
            v = json.loads(raw)
            return str(v) if v is not None else None
        except (json.JSONDecodeError, TypeError):
            return raw
    return str(raw)


# ---------------------------------------------------------------------------
# get_op_schema
# ---------------------------------------------------------------------------

def _short_desc(p: dict) -> str:
    """First sentence (or 120-char clip) of description, falling back
    to tooltip when description is missing. Keeps the slim response
    self-explanatory without hauling vendor doc paragraphs verbatim."""
    raw = p.get("description") or p.get("tooltip") or ""
    if not raw:
        return ""
    txt = " ".join(raw.split())  # collapse whitespace
    cut = txt.split(". ", 1)[0]
    if len(cut) > 120:
        cut = cut[:117].rstrip() + "..."
    return cut.rstrip(".")


def _format_param_line(p: dict, indent: int = 0) -> str:
    pad = "  " * indent
    name = p.get("param_name", "?")
    typ = p.get("type") or "?"
    req = "required" if p.get("required") else "optional"
    opts = p.get("options_json")
    if isinstance(opts, list) and opts:
        typ = f"select({' | '.join(str(o) for o in opts)})"
    default = _strip_default(p.get("default_value"))
    extras = []
    if default not in (None, ""):
        extras.append(f"default={default}")
    desc = _short_desc(p)
    head = f"{pad}- {name} ({typ}, {req})"
    if extras:
        head += f" [{', '.join(extras)}]"
    if desc:
        head += f" — {desc}"
    return head


def _render_op_schema_md(
    op_row: dict,
    params: list[dict],
    visibility: dict,
) -> str:
    """Compact markdown skeleton for an op — replaces the 5KB nested-JSON
    response with the same information in YAML-author-facing form."""
    name = op_row.get("op_name", "?")
    connector = op_row.get("connector_name", "?")
    title = op_row.get("title") or ""
    desc = op_row.get("description") or ""
    head = f"`{name}` — {title}".rstrip(" —")
    by_name = {p["param_name"]: p for p in params}

    lines = [f"# {head}", f"connector: {connector}"]
    if desc:
        first = " ".join(desc.split()).split(". ", 1)[0]
        if len(first) > 240:
            first = first[:237].rstrip() + "..."
        lines.append(f"_{first}_")
    lines.append("")

    if not visibility:
        lines.append("## params")
        for p in params:
            lines.append(_format_param_line(p))
    else:
        always = visibility.get("always", [])
        when = visibility.get("when", {})
        if always:
            lines.append("## always")
            for n in always:
                if n in by_name:
                    lines.append(_format_param_line(by_name[n]))
            lines.append("")
        # Group `when` entries by gating select so each branch reads as
        # one block instead of N flat `select=value` lines.
        by_gate: dict[str, dict[str, list[str]]] = {}
        for key, plist in when.items():
            if "=" in key:
                sel, val = key.split("=", 1)
            else:
                sel, val = key, "*"
            by_gate.setdefault(sel, {})[val] = plist
        for sel, branches in by_gate.items():
            lines.append(f"## when {sel} = …")
            for val, plist in branches.items():
                lines.append(f"### {val}")
                for n in plist:
                    if n in by_name:
                        lines.append(_format_param_line(by_name[n]))
            lines.append("")

    # Skeleton: required params from `always` + the first option of each
    # gating select. Keeps the skeleton runnable rather than 50/50 guessed.
    required_lines: list[str] = []
    chosen_branch: dict[str, str] = {}
    if visibility:
        for n in visibility.get("always", []):
            p = by_name.get(n)
            if not p:
                continue
            if p.get("required") and p.get("type") == "select":
                opts = p.get("options_json") or []
                if isinstance(opts, list) and opts:
                    chosen_branch[n] = str(opts[0])
                    required_lines.append(f"      {n}: {opts[0]}")
                else:
                    required_lines.append(f"      {n}: <value>")
            elif p.get("required"):
                required_lines.append(f"      {n}: <value>")
        # Walk picked branches recursively in case of nested selects.
        pending = list(chosen_branch.items())
        seen_gates = set(chosen_branch.keys())
        while pending:
            sel, val = pending.pop(0)
            for key, plist in visibility.get("when", {}).items():
                if key != f"{sel}={val}":
                    continue
                for n in plist:
                    p = by_name.get(n)
                    if not p or not p.get("required"):
                        continue
                    if p.get("type") == "select":
                        opts = p.get("options_json") or []
                        if isinstance(opts, list) and opts:
                            required_lines.append(f"      {n}: {opts[0]}")
                            if n not in seen_gates:
                                pending.append((n, str(opts[0])))
                                seen_gates.add(n)
                        else:
                            required_lines.append(f"      {n}: <value>")
                    else:
                        required_lines.append(f"      {n}: <value>")
    else:
        for p in params:
            if p.get("required"):
                required_lines.append(f"      {p['param_name']}: <value>")

    skeleton = [
        "## skeleton",
        "```yaml",
        "- type: connector",
        f"  name: {name}",
        f"  connector: {connector}",
        f"  operation: {name}",
        "  params:",
        *required_lines,
        "```",
    ]
    lines.extend(skeleton)
    return "\n".join(lines)


@mcp.tool()
def get_op_schema(connector: str, op: str,
                  verbose: bool = False,
                  db_path: str | None = None) -> dict[str, Any]:
    """Return the parameter schema for a connector operation.

    Slim by default (~1.5 KB): `op_name`, `title`, `description`, and a
    trimmed `params` list (name/type/required/options/description). The
    raw `output_schema_json` and `conditional_output_schema_json` blobs
    are summarized to top-level keys only. Pass `verbose=True` for the
    full row with all output schemas.

    Returns the canonical `_err()` envelope (`ok:false, code, ...`) on
    miss:
    - `code: "connector_not_found"` when the connector itself is
      unknown — call `find_connector` first.
    - `code: "not_found"` when the connector exists but the op doesn't
      — the response includes a `near` list of close op names.

    `db_path` (optional): read from a specific catalog (e.g. a pyfsr warmed cache).
    """
    if db_path is not None:
        with catalog_override(db_path):
            return get_op_schema(connector, op, verbose, db_path=None)
    with _db() as conn:
        op_row = _rows(
            conn,
            "SELECT * FROM operations WHERE connector_name=? AND op_name=?",
            (connector, op),
        )
        if not op_row:
            connector_ops = [r["op_name"] for r in _rows(
                conn,
                "SELECT op_name FROM operations WHERE connector_name=?",
                (connector,),
            )]
            if not connector_ops:
                all_connectors = [r["name"] for r in _rows(
                    conn, "SELECT name FROM connectors", ()
                )]
                near = difflib.get_close_matches(
                    connector, all_connectors, n=3, cutoff=0.5
                )
                return _err(
                    "connector_not_found",
                    f"connector {connector!r} has no operations in the "
                    f"reference store",
                    suggestions=[
                        "call find_connector first to confirm the name"
                        + (f" — close matches: {near}" if near else "")
                    ],
                    near=near,
                )
            near = difflib.get_close_matches(op, connector_ops, n=5, cutoff=0.4)
            return _err(
                "not_found",
                f"operation {op!r} not found on connector {connector!r}",
                suggestions=[
                    f"closest ops: {near}" if near else
                    f"call find_operation(connector={connector!r}) to "
                    f"list its {len(connector_ops)} ops"
                ],
                near=near,
            )

        params = _rows(
            conn,
            """SELECT param_name, title, type, required, editable, visible,
                      description, tooltip, placeholder, default_value,
                      options_json, parent_param_name, condition_value
               FROM operation_params
               WHERE connector_name=? AND op_name=?
               ORDER BY ord""",
            (connector, op),
        )
        for p in params:
            if p.get("options_json"):
                try:
                    p["options_json"] = json.loads(p["options_json"])
                except (json.JSONDecodeError, TypeError):
                    pass

        # Build the rules tuple list once; used for param_groups_by_select
        # (callable from both verbose and slim branches below). Param-name
        # → type / options / default lookups for groups.
        rules_for_groups: list[tuple[str, str | None, str | None]] = [
            (
                p["param_name"],
                p.get("parent_param_name") or None,
                p.get("condition_value") or None,
            )
            for p in params
        ]
        param_types: dict[str, str] = {}
        param_options: dict[str, list[str]] = {}
        param_defaults: dict[str, str | None] = {}
        for p in params:
            name = p["param_name"]
            if name not in param_types and p.get("type"):
                param_types[name] = p["type"]
            opts = p.get("options_json")
            if name not in param_options and opts:
                param_options[name] = _parse_options(opts)
            if name not in param_defaults:
                param_defaults[name] = _strip_default(p.get("default_value"))
        param_groups = _build_param_groups_by_select(
            rules_for_groups, param_types, param_options, param_defaults,
        )
        visibility = _build_visibility_block(rules_for_groups)

        if verbose:
            result = dict(op_row[0])
            # FortiSOAR's static operation output schema is an untyped scaffold
            # (every leaf is an empty string) and runs ~1000 lines for chatty
            # connectors — pure context/export bloat with no usable type info.
            # Drop it entirely; only the run-derived `output_schema_observed`
            # carries a trustworthy shape. To learn an op's output, run it (if
            # safe) and read the observed schema. (TRIAGE_BUILD_AUDIT_PLAN E3)
            for col in ("output_schema_json", "conditional_output_schema_json"):
                result.pop(col, None)
            if result.get("output_schema_observed"):
                try:
                    result["output_schema_observed"] = json.loads(
                        result["output_schema_observed"])
                except (json.JSONDecodeError, TypeError):
                    pass
            result["params"] = _dedupe_params(params)
            if param_groups:
                result["param_groups_by_select"] = param_groups
            if visibility:
                result["visibility"] = visibility
            return result

        # Slim path: markdown skeleton. The agent reads YAML; returning
        # YAML-shaped guidance instead of nested JSON cuts ~70% off the
        # response and matches the format it's about to write.
        deduped = _dedupe_params(params)
        md = _render_op_schema_md(op_row[0], deduped, visibility)
        out: dict[str, Any] = {
            "op_name": op_row[0].get("op_name"),
            "connector_name": op_row[0].get("connector_name"),
            "markdown": md,
        }
        # Only the run-derived observed schema is trustworthy; the static
        # FortiSOAR output schema is excluded as untyped scaffolding (E3).
        if op_row[0].get("output_schema_observed"):
            out["output_schema"] = "observed — pass verbose=True for the run-derived shape"
        elif _op_risk(op, op_row[0].get("category")) == "safe":
            out["output_schema"] = (
                "none yet — this op is read-only; run_op to observe its real output shape"
            )
        else:
            out["output_schema"] = (
                "none — static schema is untyped and excluded; run_op in a safe "
                "context to observe the real shape"
            )
        return out


# Op-name prefixes that are almost certainly read-only API calls.
_SAFE_NAME_PREFIXES: tuple[str, ...] = (
    "get_", "list_", "search_", "fetch_", "query_", "check_",
    "describe_", "lookup_", "find_", "read_", "show_", "view_",
)
# Op-name substrings that indicate destructive / side-effecting calls.
_DESTRUCTIVE_NAME_PARTS: tuple[str, ...] = (
    "delete_", "remove_", "block_", "quarantine_", "isolate_",
    "kill_", "terminate_", "disable_", "revoke_", "purge_",
    "wipe_", "destroy_", "reset_", "clear_", "close_",
    "ban_", "suspend_", "decommission_",
)
# Category strings that signal destructive intent.
_DESTRUCTIVE_CATEGORIES: frozenset[str] = frozenset(
    {"remediation", "Remediation", "containment", "management"}
)
# Category strings that signal a read-only / investigative op. Mirrors
# `fsr_playbooks.llm.tools._SAFE_CATEGORIES` so run_op's own confirm gate agrees
# with the dispatch tier gate (and with what find_enrichment_actions surfaces
# as a tier<=2, run-it-directly action). Without this, an op whose name lacks
# a safe prefix (e.g. `ioc_search`) but whose category is `investigation` fell
# through to 'unknown' and was needlessly gated as requires_confirmation —
# blocking enrichment the finder had just told the agent to run.
_SAFE_CATEGORIES: frozenset[str] = frozenset(
    {"investigation", "query", "utilities", "enrichment", "verification"}
)
# Read-only name substrings (not just prefixes) — a lookup is a lookup wherever
# the verb sits. `ioc_search` / `domain_lookup` / `ip_reputation` are reads even
# though the safe verb isn't the prefix. Destructive name/category checks run
# first, so a `block_ioc` still resolves destructive.
_SAFE_NAME_SUBSTRINGS: tuple[str, ...] = (
    "search", "lookup", "reputation", "enrich", "_ioc", "ioc_",
    "geoip", "whois", "_context", "context_",
)
# Generic raw-HTTP passthrough ops — classified by their HTTP method, not name.
_HTTP_PASSTHROUGH_OPS: frozenset[str] = frozenset(
    {"execute_api_request", "execute_api", "api_request", "make_rest_call",
     "generic_api_call", "invoke_api", "rest_api"}
)
# HTTP methods with no server-side side effect → safe to run / present without a
# confirm prompt. Everything else (POST/PUT/PATCH, or no method given) stays
# `unknown` so the human-in-the-loop confirm gate fires.
_SAFE_HTTP_METHODS: frozenset[str] = frozenset({"GET", "HEAD", "OPTIONS"})


def _op_risk(op_name: str, category: str | None,
             params: dict[str, Any] | None = None) -> str:
    """Return 'safe', 'destructive', or 'unknown'.

    Order (most reliable first): safe name prefix → safe; destructive name part
    → destructive; destructive category → destructive; raw-HTTP passthrough →
    classify by HTTP method (GET/HEAD/OPTIONS safe, DELETE destructive, else
    unknown); read-only name substring → safe; safe category → safe; else
    unknown. `unknown` is deliberate — run_op's confirm gate prompts the human
    on it, so an op we can't prove read-only keeps a human in the loop.

    `params` (the resolved op inputs) is consulted only for HTTP passthrough
    ops, where the side-effect is the method, not the op name.
    """
    name_lower = op_name.lower()
    # A `get_`/`list_`/`search_`… prefix is the strongest read signal — it wins
    # over an incidental destructive substring (e.g. `get_close_events`).
    if any(name_lower.startswith(p) for p in _SAFE_NAME_PREFIXES):
        return "safe"
    if any(p in name_lower for p in _DESTRUCTIVE_NAME_PARTS):
        return "destructive"
    cat_lower = category.lower() if category else ""
    if cat_lower in {c.lower() for c in _DESTRUCTIVE_CATEGORIES}:
        return "destructive"
    # Generic HTTP escape hatch: a GET is read-only by HTTP semantics; a POST/
    # PUT/PATCH (or unspecified) could mutate, so keep it gated. DELETE is a
    # mutation regardless.
    if name_lower in _HTTP_PASSTHROUGH_OPS or "api_request" in name_lower \
            or "rest_call" in name_lower:
        method = ""
        if isinstance(params, dict):
            method = str(params.get("method") or params.get("http_method")
                         or params.get("request_method") or "").strip().upper()
        if method in _SAFE_HTTP_METHODS:
            return "safe"
        if method == "DELETE":
            return "destructive"
        return "unknown"
    if any(s in name_lower for s in _SAFE_NAME_SUBSTRINGS):
        return "safe"
    if cat_lower in _SAFE_CATEGORIES:
        return "safe"
    return "unknown"


# ---------------------------------------------------------------------------
# get_connector_source
# ---------------------------------------------------------------------------
# TODO: Find and wire the DELETE endpoint for dev copies so we can clean up
# after fetching source. DELETE /api/integration/connector/development/entity/{dev_id}/
# returns 403 with current API-key auth — needs an admin-scoped key or a
# different route. Until then, each connector accumulates at most one dev copy
# (FSR returns the same dev_id on repeat calls to edit_repo_connector).

# ---------------------------------------------------------------------------
# get_connector_icon
# ---------------------------------------------------------------------------
# In-process cache: connector name → {icon_small, icon_large, version}.
# Backed by the SQLite `connector_icons` sidecar table for persistence
# across process restarts. Icons are small base64 PNGs (~2–5 KB each)
# and never change for a given connector version.
_ICON_CACHE: dict[str, dict[str, Any]] = {}


def _ensure_icons_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS connector_icons (
            name        TEXT PRIMARY KEY,
            version     TEXT NOT NULL,
            icon_small  TEXT,
            icon_large  TEXT,
            fetched_at  INTEGER NOT NULL
        )"""
    )

@mcp.tool()
def get_connector_icon(connector: str) -> dict[str, Any]:
    """Return the connector's icon_small / icon_large as base64 PNG strings.

    Cache hierarchy:
      1. in-process dict (instant)
      2. `connector_icons` SQLite table (persists across restarts)
      3. live FSR `/api/integration/connectors/<name>/<version>/?format=json`
         (cold ~300 ms after the live client warms up; first call ~1.6 s
         due to TLS + auth handshake)

    Hit (3) → write through to (2) and (1).
    """
    cached = _ICON_CACHE.get(connector)
    if cached:
        return {"ok": True, "cached": "memory", **cached}

    # SQLite-backed cache lookup
    with _db() as conn:
        _ensure_icons_table(conn)
        row = conn.execute(
            "SELECT version, icon_small, icon_large FROM connector_icons WHERE name=?",
            (connector,),
        ).fetchone()
        if row:
            out = {
                "version": row["version"],
                "icon_small": row["icon_small"],
                "icon_large": row["icon_large"],
            }
            _ICON_CACHE[connector] = out
            return {"ok": True, "cached": "disk", **out}
        # Not cached — need the version to address the live endpoint.
        ver_row = conn.execute(
            "SELECT version FROM connectors WHERE name=?", (connector,)
        ).fetchone()
    if not ver_row:
        return {"ok": False, "error": f"connector {connector!r} not found in store"}
    version = ver_row["version"]

    client = _shared._live_client()
    if client is None:
        return {"ok": False, "error": "FSR instance not configured"}

    try:
        # FSR rejects GET on this endpoint ("Get method for this API
        # is forbidden, Please use POST method for same API"), so we
        # POST with an empty body — same pattern as the rest of the
        # connector-detail callers in this module.
        detail = client.post(
            f"/api/integration/connectors/{connector}/{version}/?format=json", {}
        )
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"live fetch failed: {exc}"}
    if not isinstance(detail, dict):
        return {"ok": False, "error": "unexpected response shape"}

    out = {
        "version": version,
        "icon_small": detail.get("icon_small"),
        "icon_large": detail.get("icon_large"),
    }
    # Persist for next time. Use INSERT OR REPLACE so a version bump
    # transparently overwrites the stale icon row.
    with _db() as conn:
        _ensure_icons_table(conn)
        conn.execute(
            """INSERT OR REPLACE INTO connector_icons
               (name, version, icon_small, icon_large, fetched_at)
               VALUES (?, ?, ?, ?, strftime('%s','now'))""",
            (connector, version, out["icon_small"], out["icon_large"]),
        )
        conn.commit()
    _ICON_CACHE[connector] = out
    return {"ok": True, "cached": "live", **out}


# In-process cache for connector configurations. Configs change rarely
# but can be added/removed by the user, so we don't persist to disk —
# a server restart re-syncs.
_CONFIG_CACHE: dict[str, list[dict[str, Any]]] = {}

@mcp.tool()
def list_connector_configurations(connector: str,
                                   refresh: bool = False) -> dict[str, Any]:
    """List the configurations the user has set up for `connector`.

    Source preference:
      1. in-process cache
      2. local `connectors.info_json` (captured at probe time —
         includes a full `configuration` array with config_id, name,
         default flag, the inline config dict, and live status)
      3. live FSR fetch via `connector_configs.list_configurations`

    `refresh=True` skips (1) and (2) and forces a live re-fetch — use
    it after the user adds a configuration in another tab.
    """
    if not refresh and connector in _CONFIG_CACHE:
        return {"ok": True, "source": "memory",
                "configurations": _CONFIG_CACHE[connector]}

    if not refresh:
        # Prefer the locally-cached info_json — instant, and we already
        # paid the network cost during the connector probe.
        try:
            with _db() as conn:
                row = conn.execute(
                    "SELECT info_json FROM connectors WHERE name=?",
                    (connector,),
                ).fetchone()
            if row and row["info_json"]:
                blob = json.loads(row["info_json"])
                raw = blob.get("configuration") or []
                configs = [
                    {"config_id": c.get("config_id"),
                     "name": c.get("name"),
                     "default": bool(c.get("default"))}
                    for c in raw
                ]
                if configs:
                    _CONFIG_CACHE[connector] = configs
                    return {"ok": True, "source": "sqlite",
                            "configurations": configs}
        except Exception:
            # Fall through to live fetch on any parse / DB hiccup.
            pass

    try:
        from connector_configs import list_configurations  # type: ignore
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"connector_configs unavailable: {exc}"}
    try:
        configs = list_configurations(connector)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"live fetch failed: {exc}"}
    _CONFIG_CACHE[connector] = configs
    return {"ok": True, "source": "live", "configurations": configs}

@mcp.tool()
def get_connector_source(connector: str, file: str = "operations.py") -> dict[str, Any]:
    """Fetch the Python source code for a connector from the live FSR instance.

    Returns the raw content of `operations.py` (or another file in the connector
    package — `connector.py`, `info.json`, `release_notes.md`).

    **Use this sparingly** — only when the op name and parameter schema are not
    sufficient to understand what the connector actually does (e.g. undocumented
    side effects, ambiguous return shape, or a newly added op with no description).

    **How it works:**
    FSR has no direct file-read API for installed connectors. This tool calls
    `POST /api/integration/connector/development/entity/{id}/` with
    `{edit_repo_connector: true}` to create a development copy, then reads the
    file from that copy.  The result is cached in the local reference store so
    subsequent calls return immediately without hitting the FSR instance again.

    On success: `{ok: true, source: "...", cached: bool}`
    On failure: `{ok: false, error: "..."}`
    """
    sys.path.insert(0, str(REPO_ROOT / "tooling"))
    try:
        from probes._env import get_client
    except ImportError:
        return {"error": "probes module not available"}

    # --- cache hit ---
    with _db() as conn:
        row = conn.execute(
            "SELECT source_code, version FROM connectors WHERE name=?", (connector,)
        ).fetchone()
        if row and row["source_code"] and file == "operations.py":
            return {"ok": True, "source": row["source_code"], "cached": True}
        version = row["version"] if row else None
    if not version:
        return {"ok": False, "error": f"connector '{connector}' not found in store"}

    client = get_client()
    if client is None:
        return {"ok": False, "error": "FSR instance not configured"}

    # --- Step 1: resolve the connector's numeric entity id ---
    try:
        detail = client.post(f"/api/integration/connectors/{connector}/{version}/?format=json", {})
        entity_id = detail.get("id") if isinstance(detail, dict) else None
    except Exception as exc:
        return {"ok": False, "error": f"could not resolve connector entity id: {exc}"}
    if not entity_id:
        return {"ok": False, "error": f"connector '{connector}' not found on FSR instance"}

    # --- Step 2: get or create the dev copy ---
    try:
        meta = client.post(
            f"/api/integration/connector/development/entity/{entity_id}/?format=json",
            {"edit_repo_connector": True},
        )
    except Exception as exc:
        return {"ok": False, "error": f"dev-copy creation failed: {exc}"}

    if not isinstance(meta, dict):
        return {"ok": False, "error": f"unexpected response from dev-copy endpoint: {meta!r:.200}"}

    dev_id = meta.get("id")
    if not dev_id:
        return {"ok": False, "error": "dev-copy response missing entity id"}

    # Derive the dev directory name from the tree key
    tree = meta.get("tree", {})
    dev_dir = next(iter(tree), None)
    if not dev_dir:
        # Fallback: construct it from name + version
        version_str = meta.get("version", "")
        dev_dir = f"{connector}_{version_str.replace('.', '_')}_dev"

    # --- Step 2: fetch the file ---
    xpath = f"/{dev_dir}/{file}"
    try:
        file_resp = client.post(
            f"/api/integration/connector/development/entity/{dev_id}/files/?format=json",
            {"xpath": xpath},
        )
    except Exception as exc:
        return {"ok": False, "error": f"file fetch failed (xpath={xpath}): {exc}"}

    if isinstance(file_resp, dict):
        content = file_resp.get("fileContent")
    elif isinstance(file_resp, str):
        content = file_resp
    else:
        return {"ok": False, "error": f"unexpected file response type: {type(file_resp).__name__}"}

    if not content:
        return {"ok": False, "error": f"empty response for {xpath}"}

    # --- Cache operations.py ---
    if file == "operations.py":
        with sqlite3.connect(_shared.DB_PATH) as conn:
            conn.execute(
                "UPDATE connectors SET source_code=? WHERE name=?",
                (content, connector),
            )

    return {"ok": True, "source": content, "cached": False}


# ---------------------------------------------------------------------------
# get_step_type
# ---------------------------------------------------------------------------

# Friendly YAML short names → canonical FSR step type names. Mirrors
# compiler.resolver.SHORT_TYPE_TO_FSR; duplicated here to avoid a
# resolver import in the MCP layer.
_SHORT_TO_CANONICAL: dict[str, str] = {
    "connector": "Connectors",
    "set_variable": "SetVariable",
    "decision": "Decision",
    "start": "cybersponse.abstract_trigger",
    "find_record": "FindRecords",
    "update_record": "UpdateRecord",
    "create_record": "InsertData",
    "insert_record": "InsertData",
    "delay": "Delay",
    "manual_input": "ManualInput",
    "code_snippet": "CodeSnippet",
    "approval": "Approval",
    "workflow_reference": "WorkflowReference",
    "stop": "Connectors",
    "end": "Connectors",
    "start_on_create": "cybersponse.post_create",
    "start_on_update": "cybersponse.post_update",
}

# Friendly authoring forms the compiler resolver normalizes. The AI
# should prefer these over the wire form when both work — they're
# shorter, more readable, and harder to malform. Keys that aren't in
# the friendly schema are rejected by the resolver. Coverage matches
# every short type the resolver handles in compiler.resolver.
_FRIENDLY_FORMS: dict[str, dict[str, Any]] = {
    "start": {
        "accepted_keys": ["module", "modules", "button_label",
                          "requires_record", "run_mode"],
        "note": (
            "Manual / designer trigger. With NO `module:` it's a pure "
            "designer trigger (cybersponse.abstract_trigger). With a "
            "`module:` set it becomes a record-context Execute action "
            "(cybersponse.action) — `button_label:` is what the user "
            "sees in the Execute menu (NOT the step name). "
            "`run_mode: per_record` (default) or `once_for_all`."
        ),
        "example": {
            "type": "start",
            "name": "Run",
            "arguments": {
                "module": "alerts",
                "button_label": "Enrich This Alert",
                "run_mode": "per_record",
            },
        },
    },
    "start_on_create": {
        "accepted_keys": ["module", "modules", "when"],
        "note": (
            "Auto-fires whenever a record is created in `module`. "
            "Optional `when:` filters by post-write field state."
        ),
        "when_shape": (
            "{logic: AND|OR, filters: [{field, op, value?}, ...]} — "
            "use string-typed fields or `op: changed` (changed only on "
            "start_on_update); LIKE against picklist fields will not match."
        ),
        "example": {
            "type": "start_on_create",
            "arguments": {
                "module": "alerts",
                "when": {
                    "logic": "AND",
                    "filters": [{"field": "name", "op": "contains",
                                 "value": "phish"}],
                },
            },
        },
    },
    "start_on_update": {
        "accepted_keys": ["module", "modules", "when"],
        "note": (
            "Auto-fires whenever a record in `module` is updated. "
            "`op: changed` lets you fire only when a specific field "
            "changed value (no `value:` needed)."
        ),
        "example": {
            "type": "start_on_update",
            "arguments": {
                "module": "alerts",
                "when": {
                    "logic": "AND",
                    "filters": [{"field": "status", "op": "changed"}],
                },
            },
        },
    },
    "set_variable": {
        "accepted_keys_step_level": ["vars", "message", "record"],
        "shape": (
            "Variables go under a step-level `vars:` mapping (not under "
            "`arguments:`). The parser hoists `vars:` into the wire-form "
            "`arg_list`. Optional `message:` posts a comment to the "
            "triggered record's collaboration panel; `record:` is only "
            "needed when the playbook has no triggered record."
        ),
        "message_block": {
            "shape": (
                "Optional sibling of `vars:` at the step level. Posts a "
                "comment / Action Log entry to a record. If the playbook "
                "was triggered on a record, FSR auto-attaches the message "
                "and `record(s):` may be omitted. Otherwise supply "
                "`record:` (single IRI / Jinja) or `records:` (list)."
            ),
            "accepted_keys": [
                "content", "tags", "type", "thread", "record", "records",
            ],
            "keys": {
                "content": (
                    "required string; plain text auto-wraps in <p>…</p>, "
                    "or pass an HTML fragment for rich formatting."
                ),
                "tags": (
                    "optional list of tag names or `/api/3/tags/<slug>` "
                    "IRIs; friendly names are resolved at import."
                ),
                "type": (
                    "optional — 'comment' (default), or a "
                    "full `/api/3/picklists/<uuid>` IRI from the "
                    "'Comment Type' picklist."
                ),
                "thread": (
                    "optional bool; true keeps the comment threaded "
                    "with prior automated messages on the record."
                ),
                "record": (
                    "single record IRI or Jinja string. Use when the "
                    "playbook has no triggered-record context."
                ),
                "records": (
                    "list of record IRIs (or a Jinja list expression). "
                    "Use to post the same message to multiple records."
                ),
            },
            "example": {
                "message": {
                    "content": "<p>Verdict: {{ vars.verdict }}</p>",
                    "tags": ["automation", "verdict"],
                    "type": "comment",
                    "thread": True,
                },
            },
        },
        "example": {
            "type": "set_variable",
            "name": "Stash Inputs",
            "vars": {
                "source_ip": "{{ vars.input.records[0].sourceIp }}",
                "verdict": "pending",
            },
            "message": {
                "content": "Triaging {{ vars.input.records[0].sourceIp }}",
                "tags": ["automation"],
            },
        },
        "do_not_use": [
            "set: / values: / variables: at step level — only `vars:` is "
            "the recognized sugar key",
            "putting variables under `arguments:` — use step-level `vars:`",
            "arg_list: [{name, value}, ...] at step level — legacy wire "
            "form, the parser writes it for you",
            "putting message:{} keys under arguments: — `message:` is a "
            "step-level sibling of `vars:`",
        ],
    },
    "decision": {
        "accepted_keys": ["conditions"],
        "shape": (
            "`conditions:` lives at the step level (sugar) or under "
            "`arguments:` (wire form). Each non-default entry has "
            "`display`, `when`, `next`. Exactly one entry must be the "
            "default (`default: true`, no `when`) and supply `next:` for "
            "the else branch. Do NOT use a step-level `branches:` dict — "
            "the parser hard-errors on it."
        ),
        "example": {
            "type": "decision",
            "name": "Score Check",
            "conditions": [
                {"display": "Critical",
                 "when": "{{ vars.score > 50 }}",
                 "next": "Set Critical"},
                {"display": "Else", "default": True, "next": "Set Low"},
            ],
        },
        "do_not_use": [
            "step-level `branches:` dict — write `next:` on each "
            "conditions[] entry instead",
            "bare step-level `next:` — declare an explicit `default: true` "
            "row in `conditions:` and put `next:` on it",
        ],
    },
    "connector": {
        "accepted_keys": ["connector", "operation", "config", "params",
                          "agent", "version", "pickFromTenant"],
        "note": (
            "Always look up the operation first via "
            "find_operation/get_op_schema — `params` keys are validated "
            "against the operation_params catalog. `config: \"\"` "
            "selects the default connector configuration."
        ),
        "step_outputs": (
            "Reference results as `vars.steps.<step_name>.<key>` where "
            "<step_name> is the step's display NAME with spaces → "
            "underscores (NOT the YAML id:)."
        ),
        "example": {
            "type": "connector",
            "name": "Query VirusTotal",
            "arguments": {
                "connector": "virustotal",
                "operation": "query_ip",
                "config": "",
                "params": {"ip": "{{ vars.input.params.ip }}"},
            },
        },
    },
    "stop": {
        "accepted_keys": [],
        "example": {"type": "stop", "name": "End"},
        "note": (
            "Compiles to the connector handler's no_op (cyops_utilities). "
            "Use as a decision-branch terminator instead of dangling "
            "steps or filler set_variable."
        ),
    },
    "end": {
        "accepted_keys": [],
        "example": {"type": "end", "name": "End"},
        "note": "Alias for stop.",
    },
    "find_record": {
        "accepted_keys": ["module", "query", "partial"],
        "note": (
            "Returns a hydra envelope. Records are at "
            "`vars.steps.<name>['hydra:member']`, NOT `.records`. "
            "`partial: true` returns first page only."
        ),
        "query_shape": (
            "{logic: AND|OR, filters: [{field, operator, value}, ...]}"
        ),
        "example": {
            "type": "find_record",
            "name": "find",
            "arguments": {
                "module": "indicators",
                "query": {
                    "logic": "AND",
                    "filters": [{"field": "value", "operator": "eq",
                                 "value": "{{ vars.input.params.indicator }}"}],
                },
                "partial": True,
            },
        },
    },
    "create_record": {
        "accepted_keys": ["module", "resource"],
        "note": (
            "`module:` is the friendly module name (alerts, incidents, "
            "indicators, ...) — compiler converts to the IRI form. "
            "`resource:` is a flat dict of {field: value}."
        ),
        "example": {
            "type": "create_record",
            "name": "Create alert",
            "arguments": {
                "module": "alerts",
                "resource": {
                    "name": "Phishing - {{ vars.input.params.subject }}",
                    "severity": "{{ 'High' | picklist('severity') }}",
                },
            },
        },
    },
    "insert_record": {
        "accepted_keys": ["module", "resource"],
        "note": "Alias for create_record (legacy short name).",
        "example": {
            "type": "create_record",
            "name": "Create alert",
            "arguments": {
                "module": "alerts",
                "resource": {"name": "Test alert"},
            },
        },
    },
    "update_record": {
        "accepted_keys": ["module", "collection", "resource"],
        "note": (
            "`module:` (or `collectionType:`) names the module being "
            "updated. `collection:` is the RECORD IRI to update — "
            "usually `\"{{ vars.input.records[0]['@id'] }}\"`. Don't "
            "confuse the two."
        ),
        "example": {
            "type": "update_record",
            "name": "Update alert severity",
            "arguments": {
                "module": "alerts",
                "resource": {
                    "severity": "{{ 'Critical' | picklist('severity') }}",
                },
            },
        },
    },
    "delay": {
        "accepted_keys": ["seconds", "minutes", "hours", "days"],
        "note": (
            "Provide one or more units; the compiler builds the canonical "
            "TimeBased rule with the instance-wide resume_playbook channel."
        ),
        "example": {
            "type": "delay",
            "name": "Wait",
            "arguments": {"minutes": 5},
        },
    },
    "manual_input": {
        "accepted_keys_arguments": ["title", "description", "inputs"],
        "accepted_keys_step_level": ["options"],
        "shape": (
            "Prompt body (title, description, inputs) goes under "
            "`arguments:`. Branch buttons go under a STEP-LEVEL `options:` "
            "list (NOT under `arguments:`). Each option carries its own "
            "`next:` — do not use a step-level `branches:` dict."
        ),
        "type_value": "InputBased (only valid value; omit to let compiler fill)",
        "options_shape": (
            "list of {display, next, primary?} dicts. The first option "
            "is treated as primary unless another carries `primary: true`."
        ),
        "inputs_shape": (
            "list of {name, kind, label?, tooltip?, required?, default?, "
            "options?} — kind is one of: text, textarea, richtext, email, "
            "url, password, ipv4, ipv6, domain, filehash, integer, "
            "checkbox, select, datetime, json, picklist, lookup. After "
            "the operator submits, fields are read at "
            "`vars.steps.<step_name>.input.<name>`. `kind: select` "
            "requires `options:` (list of strings or jinja that resolves "
            "to a list). Prefer the most specific kind for typed values "
            "(ipv4 over text for IP addresses, etc.)."
        ),
        "example": {
            "type": "manual_input",
            "name": "Triage Decision",
            "arguments": {
                "title": "Confirm triage",
                "description": "Review the alert details and approve.",
                "inputs": [
                    {"name": "comment", "kind": "textarea",
                     "label": "Analyst comment", "required": True},
                    {"name": "severity", "kind": "select",
                     "label": "Severity",
                     "options": ["Low", "Medium", "High"]},
                ],
            },
            "options": [
                {"display": "Approve", "primary": True, "next": "Act"},
                {"display": "Reject", "next": "Drop"},
            ],
        },
        "do_not_use": [
            "step-level `branches:` dict — put `next:` on each option",
            "`options:` nested under `arguments:` — it must be at the "
            "step level (the parser hard-errors on this)",
            "type: textarea / single-select / free-text (no such dispatch — "
            "use `inputs: [{kind: textarea, ...}]` for a textarea field)",
            "label, message (not valid keys — use title/description)",
            "timeout (FSR ignores it)",
            "vars.steps.<id>.input.choice (does not exist; the option's "
            "`next:` is what routes the playbook)",
        ],
    },
    "code_snippet": {
        "accepted_keys": ["code", "config"],
        "note": (
            "`code:` is the Python body. `config:` is an optional named "
            "code-snippet connector config; defaults to the default config."
        ),
        "example": {
            "type": "code_snippet",
            "name": "Compute",
            "arguments": {"code": "result = inputs['x'] * 2"},
        },
    },
    "workflow_reference": {
        "accepted_keys": ["target", "workflowReference", "arguments"],
        "note": (
            "Either `target: <playbook_name>` (resolved within the same "
            "collection) OR `workflowReference: /api/3/workflows/<uuid>` "
            "for cross-collection refs. `arguments:` keys must match the "
            "target's declared `parameters:` list. Child output is at "
            "`vars.steps.<call_step_name>.<key>` — does NOT auto-merge "
            "into parent vars."
        ),
        "example": {
            "type": "workflow_reference",
            "name": "Call Score Multiplier",
            "arguments": {
                "target": "FSRPB Score Multiplier",
                "arguments": {"score": "{{ vars.input.params.base_score }}"},
            },
        },
    },
    "approval": {
        "accepted_keys": "pass-through (canonical FSR Approval shape)",
        "note": (
            "No friendly form yet. Use the canonical Approval wire shape "
            "from `args_schema_json` / `examples`."
        ),
    },
}


# Reverse lookup: canonical FSR name → friendly short name. Built once
# so get_step_type can slim responses regardless of which spelling the
# caller used (the agent often passes the canonical name it saw in a
# corpus row, not the friendly form).
_CANONICAL_TO_SHORT: dict[str, str] = {v: k for k, v in _SHORT_TO_CANONICAL.items()
                                       if k != "stop" and k != "end"}


def _render_step_type_md(short: str, ff: dict, st_row: dict) -> str:
    """Compact markdown for a step type. Replaces the nested
    friendly_form JSON with a single annotated YAML skeleton + the
    facts that aren't already in the YAML."""
    canonical = st_row.get("name") or _SHORT_TO_CANONICAL.get(short, short)
    label = st_row.get("label") or canonical
    lines = [f"# step type: {short}  (canonical: `{canonical}` · {label})"]

    note = ff.get("note") or ff.get("shape")
    if note:
        note = " ".join(note.split())
        if len(note) > 320:
            note = note[:317].rstrip() + "..."
        lines.append("")
        lines.append(note)

    yaml_ex = ff.get("yaml_example")
    if yaml_ex:
        lines.append("")
        lines.append("## skeleton")
        lines.append("```yaml")
        lines.append(yaml_ex.rstrip())
        lines.append("```")

    # Output-read hint when present (manual_input style steps consume
    # input via `vars.steps.<name>.input.*`).
    for k in ("reads_outputs_at", "reads_inputs_at"):
        if ff.get(k):
            lines.append("")
            lines.append(f"reads at: `{ff[k]}`")
            break

    # Surface single-string supplementary shapes the friendly_form
    # carries — `inputs_shape` for manual_input documents the `kind:`
    # enum, `when_shape` for start_on_* documents the filter object,
    # etc. Nested-dict extras (`message_block`) are too detailed for
    # slim mode and stay verbose-only.
    skip = {"note", "shape", "example", "yaml_example",
            "accepted_keys", "accepted_keys_arguments",
            "accepted_keys_step_level", "do_not_use",
            "reads_outputs_at", "reads_inputs_at"}
    extras: list[tuple[str, str]] = []
    for k, val in ff.items():
        if k in skip or not isinstance(val, str):
            continue
        extras.append((k, " ".join(val.split())))
    if extras:
        lines.append("")
        lines.append("## notes")
        for k, val in extras:
            lines.append(f"- **{k}**: {val}")

    pitfalls = ff.get("do_not_use") or ff.get("pitfalls")
    if isinstance(pitfalls, list) and pitfalls:
        lines.append("")
        lines.append("## pitfalls")
        for p in pitfalls:
            lines.append(f"- {p}")

    return "\n".join(lines)


def _render_yaml_example(example: Any) -> str | None:
    """Render a friendly_form `example` dict as a YAML string.

    Authoring is YAML; the agent translating a Python/JSON dict to YAML
    is exactly where indentation and scalar-quoting bugs creep in.
    Pre-rendering removes that step.
    """
    if not isinstance(example, dict):
        return None
    try:
        import yaml as _yaml
        return _yaml.safe_dump(
            example,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        ).rstrip() + "\n"
    except Exception:  # noqa: BLE001
        return None


# Inject `yaml_example` next to every `example` so the agent can copy
# the YAML form directly. Done at import time so the cost is paid once.
for _entry in _FRIENDLY_FORMS.values():
    _ex = _entry.get("example")
    if _ex is not None:
        _y = _render_yaml_example(_ex)
        if _y:
            _entry["yaml_example"] = _y

@mcp.tool()
def get_step_type(name: str, verbose: bool = False) -> dict[str, Any]:
    """Return schema and examples for a playbook step type.

    `name` can be the friendly YAML short type (`manual_input`,
    `set_variable`, `decision`, ...) or the canonical FSR name
    (`ManualInput`, `SetVariable`, `Decision`). Friendly short names
    map to their canonical form. The response includes a
    `friendly_form` block with the YAML-author-facing schema (the
    keys our compiler accepts) — prefer that over the wire-format
    `args_schema_json` when authoring YAML.

    By default the response is slim (~1–2 KB): the friendly_form
    suffices for authoring and raw corpus examples are omitted. Pass
    `verbose=True` for the full corpus dump (3 examples, no caps) —
    only useful when debugging an unusual case the friendly_form
    doesn't cover.
    """
    short = name
    canonical = _SHORT_TO_CANONICAL.get(name, name)
    with _db() as conn:
        rows = _rows(
            conn,
            """SELECT * FROM step_types
               WHERE name = ?
                  OR name LIKE '%'||?||'%'
               ORDER BY (name=?) DESC
               LIMIT 1""",
            (canonical, canonical, canonical),
        )
        if not rows:
            rows = _rows(
                conn,
                "SELECT * FROM step_types WHERE name LIKE '%'||?||'%' LIMIT 1",
                (canonical,),
            )
        if not rows:
            known = list(_SHORT_TO_CANONICAL.keys()) + [
                r["name"] for r in _rows(
                    conn, "SELECT name FROM step_types", ()
                )
            ]
            near = difflib.get_close_matches(name, known, n=3, cutoff=0.4)
            return _err(
                "not_found",
                f"step type {name!r} not found",
                suggestions=[
                    f"did you mean {', '.join(near)}?" if near else
                    "use a canonical FSR name like ManualInput, "
                    "Decision, SetVariable, Connectors, UpdateRecord"
                ],
                near=near,
            )

        st = rows[0]
        for col in ("args_schema_json", "ui_schema_json"):
            if st.get(col):
                try:
                    st[col] = json.loads(st[col])
                except (json.JSONDecodeError, TypeError):
                    pass

        # Slim path: a markdown skeleton beats nested JSON every time —
        # the agent is about to author YAML and reads the rendered form
        # the same way. Verbose mode keeps the full row + corpus
        # examples for debugging unusual cases.
        #
        # Look up friendly form by EITHER the friendly short name the
        # caller passed OR the canonical name it resolved to (the agent
        # often passes canonical names it saw in corpus rows).
        ff_key = short if short in _FRIENDLY_FORMS else \
                 _CANONICAL_TO_SHORT.get(canonical) if \
                 _CANONICAL_TO_SHORT.get(canonical) in _FRIENDLY_FORMS else None
        if ff_key and not verbose:
            return {
                "name": st["name"],
                "label": st.get("label"),
                "occurrences": st.get("occurrences"),
                "markdown": _render_step_type_md(
                    ff_key, _FRIENDLY_FORMS[ff_key], st
                ),
            }
        if ff_key:
            st["friendly_form"] = _FRIENDLY_FORMS[ff_key]

        limit = 3 if verbose else 1
        examples = _rows(
            conn,
            """SELECT from_playbook, snippet_json FROM step_examples
               WHERE step_type_name=? LIMIT ?""",
            (st["name"], limit),
        )
        for ex in examples:
            if ex.get("snippet_json"):
                try:
                    ex["snippet_json"] = json.loads(ex["snippet_json"])
                except (json.JSONDecodeError, TypeError):
                    pass
            if not verbose:
                blob = json.dumps(ex.get("snippet_json"), default=str)
                if len(blob) > 2048:
                    ex["snippet_json"] = (
                        f"<{len(blob)} chars truncated — call with "
                        f"verbose=True for full payload>"
                    )
        st["examples"] = examples
        if not verbose:
            # Strip null / internal fields the LLM doesn't author against.
            for k in ("uuid", "category", "description", "common_pitfalls",
                      "ui_schema_json", "args_schema_json"):
                if st.get(k) in (None, "", {}):
                    st.pop(k, None)
        return st


# ---------------------------------------------------------------------------
# find_jinja_filter
# ---------------------------------------------------------------------------

@mcp.tool()
def find_operation_example(connector: str, op: str | None = None,
                            limit: int = 5) -> dict[str, Any]:
    """Return real-world (connector, op) param snippets observed in
    actual playbooks indexed in this store.

    Sourced from `playbook_steps`-derived `operation_examples`. When
    `op` is omitted, returns one example per op for the connector.
    Use this BEFORE `get_op_schema` if the agent wants idiomatic
    params (e.g. typical jinja patterns, common picklist literals)
    rather than just the schema's required/optional split.
    """
    with _db() as conn:
        if op:
            rows = _rows(
                conn,
                """SELECT op_name, snippet, notes
                   FROM operation_examples
                   WHERE connector_name=? AND op_name=? AND source='pb_examples'
                   LIMIT ?""",
                (connector, op, limit),
            )
        else:
            rows = _rows(
                conn,
                """SELECT op_name, snippet, notes
                   FROM operation_examples
                   WHERE connector_name=? AND source='pb_examples'
                   GROUP BY op_name
                   LIMIT ?""",
                (connector, limit),
            )
    out: dict[str, Any] = {"matches": rows, "count": len(rows)}
    if not rows:
        out["suggestion"] = (
            f"no playbook examples stored for {connector}"
            + (f":{op}" if op else "")
            + ". Use get_op_schema for the param contract instead."
        )
    return out
