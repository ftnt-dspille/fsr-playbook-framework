"""Reference store endpoints — for editor autocompletion + Browse tab.

Read-only against ../store/fsr_reference.db. Cheap queries; no caching
yet (the DB is local SQLite, sub-millisecond reads).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

REPO_ROOT = Path(__file__).resolve().parents[3]
DB_PATH = REPO_ROOT / "store" / "fsr_reference.db"

# Friendly shorthand types the YAML compiler accepts. Source of truth:
# python/compiler/resolver.py SHORT_TYPE_TO_FSR. Mirrored here so the
# editor doesn't have to import Python.
STEP_TYPE_HINTS: list[dict[str, str]] = [
    {"name": "start", "detail": "manual / designer trigger"},
    {"name": "start_on_create", "detail": "auto-fires on record create (cybersponse.post_create)"},
    {"name": "start_on_update", "detail": "auto-fires on record update (cybersponse.post_update)"},
    {"name": "set_variable", "detail": "store a value into vars"},
    {"name": "decision", "detail": "branch on conditions"},
    {"name": "connector", "detail": "call a connector operation"},
    {"name": "find_record", "detail": "query records from a module"},
    {"name": "create_record", "detail": "create a record in a module"},
    {"name": "update_record", "detail": "update an existing record"},
    {"name": "delay", "detail": "pause for N seconds"},
    {"name": "manual_input", "detail": "wait for human input"},
    {"name": "code_snippet", "detail": "run an inline Python snippet"},
    {"name": "workflow_reference", "detail": "call a child playbook"},
    {"name": "stop", "detail": "terminal no-op"},
    {"name": "end", "detail": "terminal no-op (alias of stop)"},
]


router = APIRouter(prefix="/api/ref", tags=["ref"])


def _conn() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise HTTPException(503, f"reference db missing at {DB_PATH}")
    c = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    return c


@router.get("/step-types")
def list_step_types() -> list[dict[str, str]]:
    return STEP_TYPE_HINTS


@router.get("/recipes")
def list_recipes() -> list[dict[str, Any]]:
    """Recipes available for drag/drop into the visual editor."""
    with _conn() as c:
        rows = c.execute(
            "SELECT name, kind, when_to_use FROM recipes ORDER BY kind, name"
        ).fetchall()
    return [{"name": r["name"], "kind": r["kind"], "when_to_use": r["when_to_use"]}
            for r in rows]


@router.get("/step-args/{step_type}")
def step_args_help(step_type: str) -> dict[str, Any]:
    """Hover docs for a friendly step type — what `arguments:` accepts.

    Powers the Monaco hover popup. Returns both the structured spec and
    a pre-rendered markdown blob so the frontend can show either.
    """
    from step_args_help import get_help, render_markdown
    spec = get_help(step_type)
    if spec is None:
        raise HTTPException(404, f"no help entry for step type {step_type!r}")
    return {"type": step_type,
            "spec": spec,
            "markdown": render_markdown(step_type)}


@router.get("/connectors")
def list_connectors(q: str = "", limit: int = 50) -> list[dict[str, Any]]:
    sql = (
        "SELECT name, label, category, description FROM connectors "
        "WHERE active = 1 "
    )
    args: list[Any] = []
    if q:
        sql += "AND (name LIKE ? OR label LIKE ?) "
        args += [f"%{q}%", f"%{q}%"]
    sql += "ORDER BY name LIMIT ?"
    args.append(limit)
    with _conn() as c:
        return [dict(r) for r in c.execute(sql, args)]


@router.get("/inventory")
def inventory_summary() -> dict[str, Any]:
    """Audit surface — what does the assistant know?

    Powers the front-end inventory dashboard (the "we're not just an LLM"
    proof). Reads through `python.inventory` so the CLI and web stay in
    sync.
    """
    import sys as _sys
    _py = REPO_ROOT / "python"
    if str(_py) not in _sys.path:
        _sys.path.insert(0, str(_py))
    import inventory as inv
    return {
        "summary": inv.summary(),
        "top_api_products": inv.list_api_example_products(limit=15),
    }


@router.get("/api-examples")
def api_examples(q: str, product: str | None = None,
                 limit: int = 10) -> list[dict[str, Any]]:
    """FTS search over the api_examples_catalog. Returns entry_id so the
    UI can call /synthesize-http-step on a specific row."""
    import sys as _sys
    _py = REPO_ROOT / "python"
    if str(_py) not in _sys.path:
        _sys.path.insert(0, str(_py))
    from mcp_server import search_api_examples as _search  # type: ignore
    return _search(query=q, product=product, limit=limit)


@router.get("/synthesize-http-step")
def synthesize_http_step(entry_id: int, step_name: str = "Call API") -> dict[str, Any]:
    """Translate an api_examples_catalog entry into a YAML HTTP-connector step.

    Powers the "Insert as HTTP step" button on the Inventory dashboard.
    Calls through to the same deterministic synthesizer the MCP server
    exposes — no LLM, just a catalog row → http_request step transform.
    """
    import sys as _sys
    _py = REPO_ROOT / "python"
    if str(_py) not in _sys.path:
        _sys.path.insert(0, str(_py))
    from mcp_server import synthesize_http_step as _synth  # type: ignore
    step = _synth(entry_id=entry_id, step_name=step_name)
    if step.get("error"):
        raise HTTPException(404, step["error"])
    args = step.get("args") or {}
    yaml_lines = [
        f"- id: call_api",
        f"  type: connector",
        f"  name: {step.get('name', step_name)!r}",
        f"  connector: {step.get('connector', 'http')}",
        f"  operation: {step.get('operation', 'http_request')}",
        f"  args:",
        f"    method: {args.get('method', 'GET')}",
        f"    rest_api: {args.get('rest_api', '')!r}",
        f"    auth_type: {args.get('auth_type', 'No Auth')!r}",
    ]
    if args.get("parameter"):
        yaml_lines.append("    parameter:")
        for k, v in args["parameter"].items():
            yaml_lines.append(f"      {k}: {v!r}")
    return {
        "step": step,
        "yaml": "\n".join(yaml_lines),
        "note": step.get("_note", ""),
        "source_url": step.get("_source_url", ""),
    }


@router.get("/inventory/search")
def inventory_search(q: str, limit: int = 15) -> dict[str, Any]:
    import sys as _sys
    _py = REPO_ROOT / "python"
    if str(_py) not in _sys.path:
        _sys.path.insert(0, str(_py))
    import inventory as inv
    return inv.cross_search(q, per_table_limit=limit)


@router.get("/connectors/{name}/operations")
def list_operations(name: str, q: str = "", limit: int = 100) -> list[dict[str, Any]]:
    sql = (
        "SELECT op_name, title, category, description FROM operations "
        "WHERE connector_name = ? AND visible = 1 "
    )
    args: list[Any] = [name]
    if q:
        sql += "AND (op_name LIKE ? OR title LIKE ?) "
        args += [f"%{q}%", f"%{q}%"]
    sql += "ORDER BY op_name LIMIT ?"
    args.append(limit)
    with _conn() as c:
        return [dict(r) for r in c.execute(sql, args)]


@router.get("/jinja-filters")
def list_jinja_filters(q: str = "", limit: int = 200) -> list[dict[str, Any]]:
    """Catalog of jinja filters for Monaco autocomplete inside `{{ … | }}`.

    Read-only over `jinja_macros`. Returns name + signature + a one-line
    description so the IDE can render hover docs without a second
    fetch. Limited to ~200 since the full corpus is ~170 filters.
    """
    sql = (
        "SELECT name, signature, description, output_type_observed "
        "FROM jinja_macros "
    )
    args: list[Any] = []
    if q:
        sql += "WHERE name LIKE ? OR description LIKE ? "
        args += [f"%{q}%", f"%{q}%"]
    sql += "ORDER BY name LIMIT ?"
    args.append(limit)
    with _conn() as c:
        return [dict(r) for r in c.execute(sql, args)]


@router.get("/modules")
def list_modules() -> list[dict[str, Any]]:
    """Module names + labels from the trained `modules` table.

    Powers the Resource (module) dropdown on trigger and record_crud
    inspector blocks. Empty list when the trained DB hasn't been
    populated yet (fresh install / pre-`fsrpb train`).
    """
    with _conn() as c:
        rows = c.execute(
            "SELECT name, label, plural FROM modules ORDER BY name"
        ).fetchall()
    return [{"name": r["name"], "label": r["label"], "plural": r["plural"]}
            for r in rows]


# Operator catalog per leaf-value type — trimmed from
# `store/QUERY_API.md` §2.1 to surface only the ops that make
# semantic sense for the field type. Keeps the UI from offering
# `like` on a boolean or `gt` on a picklist.
_OPERATORS_BY_TYPE: dict[str, list[str]] = {
    "default":    ["eq", "neq", "in", "nin", "like", "isnull"],
    "integer":    ["eq", "neq", "lt", "lte", "gt", "gte", "in", "nin", "isnull"],
    "decimal":    ["eq", "neq", "lt", "lte", "gt", "gte", "in", "nin", "isnull"],
    "number":     ["eq", "neq", "lt", "lte", "gt", "gte", "in", "nin", "isnull"],
    "checkbox":   ["eq", "neq", "isnull"],
    "boolean":    ["eq", "neq", "isnull"],
    "datetime":   ["eq", "neq", "lt", "lte", "gt", "gte", "isnull"],
    "date":       ["eq", "neq", "lt", "lte", "gt", "gte", "isnull"],
    "picklists":  ["eq", "neq", "in", "nin", "isnull"],
    "lookup":     ["eq", "neq", "in", "nin", "isnull"],
    "manyToMany": ["eq", "neq", "in", "nin", "isnull"],
    "manyToOne":  ["eq", "neq", "in", "nin", "isnull"],
    "oneToMany":  ["eq", "neq", "in", "nin", "isnull"],
    "json":       ["eq", "neq", "like", "contains", "exists", "isnull"],
    "object":     ["eq", "neq", "like", "contains", "exists", "isnull"],
}


@router.get("/modules/{module}/fields")
def get_module_fields(module: str) -> dict[str, Any]:
    """Field catalog for a single module.

    Each field carries its FSR type, required flag, picklist name (when
    applicable), tooltip, and the per-type operator catalog so the
    FilterTreeEditor can scope the operator dropdown by field type.
    """
    with _conn() as c:
        m = c.execute(
            "SELECT name, label, plural FROM modules WHERE name = ?",
            (module,),
        ).fetchone()
        if m is None:
            raise HTTPException(404,
                                f"module {module!r} not found in trained store")
        rows = c.execute(
            "SELECT field_name, title, type, required, picklist_options, tooltip "
            "FROM module_fields WHERE module_name = ? ORDER BY field_name",
            (module,),
        ).fetchall()
    fields = []
    for r in rows:
        ftype = r["type"] or "default"
        ops = _OPERATORS_BY_TYPE.get(ftype, _OPERATORS_BY_TYPE["default"])
        fields.append({
            "name": r["field_name"],
            "title": r["title"],
            "type": ftype,
            "required": bool(r["required"]),
            "picklist_options": r["picklist_options"],
            "tooltip": r["tooltip"],
            "operators": ops,
        })
    return {
        "module": m["name"],
        "label": m["label"],
        "plural": m["plural"],
        "fields": fields,
    }


@router.get("/step-examples/{step_type}")
def step_examples(step_type: str, limit: int = 10) -> dict[str, Any]:
    """Top-N corpus-mined skeletons for a step type, with summaries.

    Powers the Examples tab on every step type. See
    ``web/backend/step_examples.py`` for clustering + summariser.
    """
    from ..step_examples import cluster_examples, STEP_TYPE_TO_CORPUS
    if step_type not in STEP_TYPE_TO_CORPUS:
        raise HTTPException(404,
            f"step type {step_type!r} has no corpus mapping; "
            f"supported: {sorted(STEP_TYPE_TO_CORPUS)}")
    n = max(1, min(int(limit), 25))
    with _conn() as c:
        clusters = cluster_examples(c, step_type, limit=n)
    return {"step_type": step_type, "examples": clusters}


_GLOBAL_VARS_CACHE: dict[str, Any] = {"data": None, "ts": 0.0}
_GLOBAL_VARS_TTL = 60.0  # seconds; global vars change rarely


@router.get("/global-vars")
def list_global_vars() -> list[dict[str, Any]]:
    """FSR global ("dynamic") variables — `globalVars.<name>` autocomplete.

    Hits the live FSR at `/api/wf/api/dynamic-variable/`. Cached for
    60s so the editor doesn't pummel the appliance. Returns [] when
    the env is offline or the request fails — callers fall back to a
    buffer-scrape of names already referenced in the YAML.
    """
    import time as _time
    now = _time.monotonic()
    cached = _GLOBAL_VARS_CACHE["data"]
    if cached is not None and (now - float(_GLOBAL_VARS_CACHE["ts"])) < _GLOBAL_VARS_TTL:
        return cached  # type: ignore[no-any-return]
    try:
        from probes import _env  # type: ignore
        cfg = _env.get_config()
        if not cfg.is_live():
            return []
        client = _env.get_client()
        r = client.session.get(
            client.base_url + "/api/wf/api/dynamic-variable/?offset=0&limit=2147483647",
            verify=client.verify_ssl,
            timeout=4,
        )
        if r.status_code != 200:
            return []
        members = r.json().get("hydra:member", [])
        out = [
            {
                "name": m.get("name", ""),
                "value": m.get("value"),
                "default_value": m.get("default_value"),
            }
            for m in members
            if isinstance(m, dict) and m.get("name")
        ]
    except Exception:
        out = []
    _GLOBAL_VARS_CACHE["data"] = out
    _GLOBAL_VARS_CACHE["ts"] = now
    return out


@router.get("/recent-runs")
def recent_runs(
    playbook_iri: str | None = None,
    limit: int = 5,
) -> dict[str, Any]:
    """Last N playbook executions from FSR, optionally filtered to a
    single playbook. Used by the trigger-step sample picker so authors
    can pin "the record from the last run" without us needing to
    persist anything ourselves — FSR's workflow execution history is
    already the source of truth.

    Returns each run with its record IRIs (when present). The picker
    can then fetch the record body via /api/ref/record-by-iri.
    """
    try:
        from probes import _env  # type: ignore
        cfg = _env.get_config()
        if not cfg.is_live():
            return {"ok": False, "error": "FSR offline", "runs": []}
        client = _env.get_client()
        n = max(1, min(int(limit), 20))
        params = "?format=json&ordering=-created&limit=" + str(n)
        if playbook_iri:
            from urllib.parse import quote
            params += "&template_iri=" + quote(playbook_iri, safe="")
        r = client.session.get(
            client.base_url + "/api/wf/api/workflows/" + params,
            verify=client.verify_ssl,
            timeout=5,
        )
        if r.status_code != 200:
            return {"ok": False, "error": f"HTTP {r.status_code}", "runs": []}
        data = r.json() or {}
        items = data.get("hydra:member") or data.get("results") or []
        out = []
        for it in items[:n]:
            if not isinstance(it, dict):
                continue
            recs = it.get("records") or []
            if not isinstance(recs, list):
                recs = []
            out.append({
                "id": it.get("id"),
                "status": it.get("status"),
                "created": it.get("created"),
                "name": it.get("playbookName") or it.get("name") or "",
                "records": [str(x) for x in recs if isinstance(x, str)],
            })
        return {"ok": True, "runs": out}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}", "runs": []}


@router.get("/run-detail/{run_id}")
def run_detail(run_id: str) -> dict[str, Any]:
    """Full FSR workflow execution detail — used to seed the editor
    with the EXACT context a past run had (input records, step
    variables, step outputs). Lets authors iterate on a playbook
    against real production data without re-running anything.

    Returns the raw FSR response trimmed to a reasonable size; the
    frontend cherry-picks input records / step traces from it.
    """
    if not run_id or not run_id.isdigit():
        return {"ok": False, "error": "run_id must be a positive integer"}
    try:
        from probes import _env  # type: ignore
        cfg = _env.get_config()
        if not cfg.is_live():
            return {"ok": False, "error": "FSR offline"}
        client = _env.get_client()
        r = client.session.get(
            client.base_url + f"/api/wf/api/workflows/{run_id}/?format=json",
            verify=client.verify_ssl,
            timeout=8,
        )
        if r.status_code != 200:
            return {"ok": False, "error": f"HTTP {r.status_code}"}
        data = r.json() or {}
        # Pull common fields we care about; pass through unknown ones
        # so future FSR versions adding fields still work.
        return {
            "ok": True,
            "id": data.get("id"),
            "status": data.get("status"),
            "created": data.get("created"),
            "modified": data.get("modified"),
            "name": data.get("playbookName") or data.get("name") or "",
            "records": data.get("records") or [],
            # Step traces; field names vary by FSR version — we include
            # whichever the appliance returns so the frontend can probe.
            "wf_step_logs": data.get("wf_step_logs"),
            "step_logs": data.get("step_logs"),
            "stepInstances": data.get("stepInstances"),
            "input_parameters": data.get("input_parameters") or data.get("inputs"),
        }
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


@router.get("/record-by-iri")
def record_by_iri(iri: str) -> dict[str, Any]:
    """Fetch a single record by its IRI (e.g. `/api/3/alerts/<uuid>`).
    Wraps the appliance fetch so the browser doesn't need to talk to
    FSR directly (avoids mixed-content / cert issues). Returns the
    record body with the same noisy-key trimming as /sample-record."""
    if not iri or not iri.startswith("/api/"):
        return {"ok": False, "error": "iri must start with /api/", "record": None}
    try:
        from probes import _env  # type: ignore
        cfg = _env.get_config()
        if not cfg.is_live():
            return {"ok": False, "error": "FSR offline", "record": None}
        client = _env.get_client()
        r = client.session.get(
            client.base_url + iri,
            verify=client.verify_ssl,
            timeout=5,
        )
        if r.status_code != 200:
            return {"ok": False, "error": f"HTTP {r.status_code}", "record": None}
        rec = r.json() or {}
        if not isinstance(rec, dict):
            return {"ok": False, "error": "non-object response", "record": None}
        out = {}
        for k, v in rec.items():
            if isinstance(v, list) and len(v) > 3:
                out[k] = f"<list[{len(v)}]>"
            elif isinstance(v, dict) and "itemValue" in v:
                out[k] = v  # picklist — keep so itemValue stays accessible
            elif isinstance(v, dict) and len(v) > 8:
                out[k] = "<object>"
            else:
                out[k] = v
        return {"ok": True, "record": out}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}", "record": None}


@router.get("/sample-record/{module}")
def sample_record(module: str, limit: int = 5) -> dict[str, Any]:
    """Pull the N most recent records of `<module>` from the live FSR.

    Used by the variable picker / start-step UI to show *real* field
    values the user can use as a sample for `vars.input.records[0]`.
    The picker can offer one row as the "what `vars.input.records[0]`
    will look like at runtime" preview, so authors can validate that
    `.severity` (or whatever they're about to reference) actually
    exists on the trigger's records.

    Returns [] when offline. We strip noisy meta-keys to keep the JSON
    shape readable in the picker.
    """
    try:
        from probes import _env  # type: ignore
        cfg = _env.get_config()
        if not cfg.is_live():
            return {"ok": False, "error": "FSR offline", "records": []}
        client = _env.get_client()
        n = max(1, min(int(limit), 25))
        bare = module.split("?", 1)[0]
        r = client.session.get(
            client.base_url + f"/api/3/{bare}?$limit={n}&$orderby=-id",
            verify=client.verify_ssl,
            timeout=5,
        )
        if r.status_code != 200:
            return {"ok": False, "error": f"HTTP {r.status_code}", "records": []}
        data = r.json() or {}
        items = data.get("hydra:member") or data.get("data") or []
        # Drop large/noisy collections that overwhelm the picker. Keep
        # scalars + small dicts; preserve `@id` / `id` which authors use.
        # Picklist-shaped objects (have `itemValue`) are ALWAYS preserved
        # — they're how FSR stores severity / status / type etc., and
        # the frontend renders their `itemValue` as the display value.
        def _clean(rec):
            if not isinstance(rec, dict):
                return rec
            out = {}
            for k, v in rec.items():
                if isinstance(v, list) and len(v) > 3:
                    out[k] = f"<list[{len(v)}]>"
                elif isinstance(v, dict) and "itemValue" in v:
                    out[k] = v  # picklist — keep as-is
                elif isinstance(v, dict) and len(v) > 8:
                    out[k] = "<object>"
                else:
                    out[k] = v
            return out
        return {"ok": True, "module": bare, "records": [_clean(x) for x in items[:n]]}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}", "records": []}


@router.get("/example-prompts")
def list_example_prompts() -> list[dict[str, Any]]:
    """Sample chat prompts for testing the agent.

    Sourced from `python/evals/tasks/*.json` so the eval corpus and the
    UI picker stay in lockstep — adding a task file gives you a new
    option in the chat starter dropdown automatically.
    """
    import json as _json
    tasks_dir = REPO_ROOT / "python" / "evals" / "tasks"
    if not tasks_dir.exists():
        return []
    out: list[dict[str, Any]] = []
    for p in sorted(tasks_dir.glob("*.json")):
        try:
            data = _json.loads(p.read_text(encoding="utf-8"))
        except _json.JSONDecodeError:
            continue
        out.append({
            "name": data.get("name", p.stem),
            "prompt": data.get("prompt", ""),
            "notes": data.get("notes", ""),
            "has_gold": bool(data.get("gold_yaml_path")),
        })
    return out
