"""MCP tools: Tools Recipe"""
from __future__ import annotations
from . import _shared, tools_triage, tools_jinja

import difflib
import json
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any

from ._shared import (
    mcp,
    _err,
    _db,
    _rows,
    _verifications_for,
    _serialize_compiler_error,
    _infer_shape,
    _store_observed_schema,
    REPO_ROOT,
)
# Import DB_PATH for local use
DB_PATH = _shared.DB_PATH

# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
def assert_playbook_outcome(assertions: list[dict[str, Any]]) -> dict[str, Any]:
    """Verify a playbook produced its intended effect on the live FSR.

    Run a list of declarative assertions against the live FSR (typically
    after `run_playbook`/`dry_run_playbook`) to confirm the playbook did
    what its description says it does — closes Level 5 of the success
    ladder and gives the LLM-evaluation harness a deterministic scorer.

    Each assertion is a dict with one of three shapes:

    - `{"kind": "record_exists", "module": "alerts",
        "filters": {"name": "Demo alert", "severity.itemValue": "High"}}`
       passes when ≥1 matching record exists.

    - `{"kind": "record_count", "module": "indicators",
        "filters": {"sourceId": "feed-123"}, "op": "gte", "value": 10}`
       passes when the count satisfies the comparison. `op` is one of
       eq | ne | gt | gte | lt | lte.

    - `{"kind": "field_equals", "module": "alerts",
        "filters": {"name": "Demo alert"}, "field": "status.itemValue",
        "value": "Closed"}`
       requires exactly one matching record and checks a (dotted) field.

    `filters` accepts a friendly `{field: value, ...}` dict (AND-combined
    eq) OR a full `{logic, filters: [...]}` query body for OR / range /
    nested logic.

    Returns `{ok, total, passed, failed, results: [...]}` where each
    result has `ok`, `code`, `message`, plus echoed inputs and
    `observed`/`observed_count` so the agent can self-correct without
    a follow-up tool call.
    """
    if not isinstance(assertions, list) or not assertions:
        return {"ok": False, "code": "empty_assertions",
                "message": "assertions must be a non-empty list"}
    client = _shared._live_client()
    if client is None:
        return {"ok": False, "code": "no_live_fsr",
                "message": "FSR instance not configured"}
    results = [tools_triage._assert_one(client, a if isinstance(a, dict) else {})
               for a in assertions]
    passed = sum(1 for r in results if r.get("ok"))
    return {
        "ok": passed == len(results),
        "total": len(results), "passed": passed, "failed": len(results) - passed,
        "results": results,
    }

@mcp.tool()
def generate_recipe(
    kind: str,
    info_json_path: str,
    target_module: str = "alerts",
    fetch_op: str | None = None,
    dedup_field: str | None = None,
    severity_field: str = "severity",
    status_field: str = "status",
    severity_enum: list[str] | None = None,
    status_enum: list[str] | None = None,
    config_uuid: str = "REPLACE_WITH_CONFIG_UUID",
    persist: bool = False,
    when_to_use: str | None = None,
) -> dict[str, Any]:
    """Synthesize an ingestion playbook from a connector's `info.json`.

    Wraps the same generators `fsrpb generate-recipe` calls so an LLM
    agent can mint a recipe inline from a single tool call instead of
    shelling out. Returns both the FSR JSON (importable directly) and
    the decompiled YAML (so the agent can present an editable form to
    the user before pushing).

    Args:
        kind: `threat-feed` or `data-ingest`.
        info_json_path: filesystem path to the connector's info.json
            (typically pulled out of the RPM cache).
        target_module: data-ingest only — `alerts` (default) or
            `incidents`.
        fetch_op: explicit fetch op override (data-ingest); auto-detect
            scans the connector's ops by name when omitted.
        dedup_field: vendor field used as `sourceId` for upsert.
        severity_field, status_field: vendor fields carrying severity /
            status enum strings.
        severity_enum, status_enum: comma list of vendor enum values
            (data-ingest only) — needed for the picklist-resolve macro.
        config_uuid: connector configuration uuid; recipe ships
            `REPLACE_WITH_CONFIG_UUID` placeholder when omitted so the
            user can substitute post-import.
        persist: when True, decompile the FSR JSON to YAML and store
            into the `recipes` table keyed `<kind>:<connector>` so
            `find_recipe` can return it later.
        when_to_use: optional human-readable trigger description
            recorded with `persist=True`.

    Returns:
        {ok: true, kind, name, connector, fsr_json, yaml,
         persisted: bool} on success, or the standard error envelope
        with `code` ∈ {`bad_kind`, `info_json_missing`,
        `generator_failed`}.
    """
    if kind not in ("threat-feed", "data-ingest"):
        return _err("bad_kind",
                    f"unknown recipe kind {kind!r}",
                    suggestions=["threat-feed", "data-ingest"])
    p = Path(info_json_path)
    if not p.exists():
        return _err("info_json_missing",
                    f"info.json not found at {info_json_path}",
                    suggestions=["check the path",
                                 "extract from store/rpm_cache/"])
    try:
        info = json.loads(p.read_text())
    except Exception as exc:  # noqa: BLE001
        return _err("info_json_invalid", f"info.json parse failed: {exc}")

    sys.path.insert(0, str(REPO_ROOT / "python"))
    try:
        from recipes import (generate_data_ingest_recipe,  # noqa: PLC0415
                             generate_threat_feed_recipe)
        if kind == "threat-feed":
            fsr_json = generate_threat_feed_recipe(
                info, connector_config_uuid=config_uuid,
            )
        else:
            fsr_json = generate_data_ingest_recipe(
                info,
                target_module=target_module,
                fetch_op_name=fetch_op,
                dedup_field=dedup_field,
                severity_field=severity_field,
                status_field=status_field,
                severity_enum=severity_enum,
                status_enum=status_enum,
                connector_config_uuid=config_uuid,
            )
    except Exception as exc:  # noqa: BLE001
        return _err("generator_failed", repr(exc),
                    suggestions=["call list_configured_connectors to "
                                 "find a real config_uuid",
                                 "set fetch_op explicitly if auto-"
                                 "detect picked the wrong op"])

    # Decompile to YAML for the agent + (optional) persistence.
    try:
        from fsr_core.compiler.decompiler import decompile_to_yaml  # noqa: PLC0415
        yaml_text = decompile_to_yaml(fsr_json, _shared.DB_PATH)
    except Exception as exc:  # noqa: BLE001
        yaml_text = f"# decompile failed: {exc!r}\n"

    connector = info.get("name") or "unknown"
    name = f"{kind.replace('-', '_')}:{connector}"
    persisted = False
    if persist:
        try:
            with sqlite3.connect(_shared.DB_PATH) as conn:
                conn.execute(
                    """INSERT OR REPLACE INTO recipes
                       (name, kind, when_to_use, yaml_template, source_playbook)
                       VALUES (?,?,?,?,?)""",
                    (name, kind.replace("-", "_"),
                     when_to_use or f"{kind} ingestion for {connector}",
                     yaml_text, connector),
                )
                conn.commit()
            persisted = True
        except Exception:  # noqa: BLE001
            persisted = False

    return {
        "ok": True,
        "kind": kind,
        "name": name,
        "connector": connector,
        "fsr_json": fsr_json,
        "yaml": yaml_text,
        "persisted": persisted,
    }

@mcp.tool()
def find_recipe(query: str = "", kind: str | None = None,
                limit: int = 10) -> dict[str, Any]:
    """Look up persisted recipes by name / connector / kind.

    Returns recipes previously stored via `generate_recipe(persist=True)`
    or the CLI's `--persist`. `query` is a substring match against
    `name`, `source_playbook`, or `when_to_use`. `kind` filters to
    `threat_feed` / `data_ingest` etc. Returns the YAML template so
    the agent can paste it into the editor verbatim.
    """
    sql_parts = ["1=1"]
    args: list[Any] = []
    if query:
        sql_parts.append(
            "(name LIKE ? OR source_playbook LIKE ? OR when_to_use LIKE ?)"
        )
        like = f"%{query}%"
        args.extend([like, like, like])
    if kind:
        sql_parts.append("kind = ?")
        args.append(kind.replace("-", "_"))
    args.append(int(limit))
    with _db() as conn:
        rows = _rows(
            conn,
            "SELECT name, kind, when_to_use, yaml_template, source_playbook "
            f"FROM recipes WHERE {' AND '.join(sql_parts)} "
            "ORDER BY name LIMIT ?",
            tuple(args),
        )
    return {"ok": True, "count": len(rows), "recipes": rows}


_JINJA_BLOCK_RE = re.compile(r"\{\{.*?\}\}|\{%.*?%\}", re.DOTALL)


def _walk_args_with_path(
    value: Any, prefix: str = "",
) -> list[tuple[str, str]]:
    """Yield (dotted_path, string_value) for every string leaf in a
    nested dict/list. Used to find Jinja templates inside step args."""
    out: list[tuple[str, str]] = []
    if isinstance(value, str):
        out.append((prefix or "(root)", value))
    elif isinstance(value, dict):
        for k, v in value.items():
            out.extend(_walk_args_with_path(v, f"{prefix}.{k}" if prefix else str(k)))
    elif isinstance(value, list):
        for i, v in enumerate(value):
            out.extend(_walk_args_with_path(v, f"{prefix}[{i}]"))
    return out

@mcp.tool()
def diagnose_yaml_against_pb_execution(
    yaml_text: str, pb_execution: str,
) -> dict[str, Any]:
    """Diagnose why a playbook run failed by re-rendering each step's
    arguments against the run's actual `vars` env.

    Closes the failure-recovery loop: instead of squinting at FSR's
    per-step audit log, this tool pulls the run's `{vars: {...env,
    steps: {...}}}` context, then walks the YAML's step args and
    renders every embedded `{{ ... }}` block against that context.
    Surface output:

    - `run_status`: terminal status from the FSR side.
    - `step_diagnostics`: one row per (step, arg_path, template) with
      `rendered` on success or `code` + `message` on render failure.
      Common codes: `step_missing` (a referenced `vars.steps.<key>` has
      no entry in the run env — typo or unreached step), `render_error`
      (Jinja engine threw — bad filter/expr), `attribute_missing` (the
      template rendered "None" because a path traversed an empty leg).
    - `hints`: top-level suggestions distilled from the diagnostics
      (e.g. "step Foo references vars.steps.Bar but Bar didn't run").

    Args:
        yaml_text: the playbook YAML you want to diagnose.
        pb_execution: workflow PK (digits, e.g. "676747") OR task_id UUID
            of the failed (or completed) run to use as the env source.
    """
    env_out = tools_triage.get_run_env(pb_execution)
    if "error" in env_out or env_out.get("ok") is False:
        return _err(
            "run_env_unavailable",
            (env_out.get("error") or env_out.get("message")
             or "could not fetch run env"),
            suggestions=[
                "Confirm the pb_execution id / task_id is correct",
                "Historical runs are purged after ~60 min on most FSRs",
            ],
            pb_execution=pb_execution,
        )

    run_status = env_out.get("status")
    run_vars = env_out.get("vars") or {}
    steps_in_env = (run_vars.get("steps") or {}) if isinstance(run_vars, dict) else {}

    try:
        import yaml as _yaml
        doc = _yaml.safe_load(yaml_text) or {}
    except Exception as exc:  # noqa: BLE001
        return _err("yaml_parse_failed", f"YAML parse error: {exc}",
                    suggestions=["Run `validate_yaml` first to surface "
                                 "structural issues"])

    diagnostics: list[dict[str, Any]] = []
    referenced_step_keys: set[str] = set()
    vars_steps_re = re.compile(r"vars\.steps\.([A-Za-z0-9_]+)")

    playbooks = doc.get("playbooks") or []
    for pb in playbooks if isinstance(playbooks, list) else []:
        if not isinstance(pb, dict):
            continue
        pb_name = pb.get("name") or "<unnamed>"
        for s in (pb.get("steps") or []):
            if not isinstance(s, dict):
                continue
            step_name = s.get("name") or s.get("id") or "<unnamed>"
            args = s.get("arguments") or s.get("args") or {}
            for arg_path, leaf in _walk_args_with_path(args):
                blocks = _JINJA_BLOCK_RE.findall(leaf)
                if not blocks:
                    continue
                # Track every vars.steps.<key> reference for hints.
                for blk in blocks:
                    for m in vars_steps_re.finditer(blk):
                        referenced_step_keys.add(m.group(1))
                # Render the full leaf string (preserves surrounding text).
                try:
                    r = tools_jinja.render_jinja(template=leaf,
                                     context=None,
                                     from_pb_execution=pb_execution)
                except Exception as exc:  # noqa: BLE001
                    diagnostics.append({
                        "playbook": pb_name, "step": step_name,
                        "arg_path": arg_path, "template": leaf,
                        "ok": False, "code": "render_threw",
                        "message": repr(exc),
                    })
                    continue
                if isinstance(r, dict) and r.get("error"):
                    diagnostics.append({
                        "playbook": pb_name, "step": step_name,
                        "arg_path": arg_path, "template": leaf,
                        "ok": False, "code": "render_error",
                        "message": str(r.get("error"))[:400],
                    })
                else:
                    rendered = (r.get("output") if isinstance(r, dict) else r)
                    code = "ok"
                    if rendered in ("", None, "None"):
                        code = "empty_render"
                    diagnostics.append({
                        "playbook": pb_name, "step": step_name,
                        "arg_path": arg_path, "template": leaf,
                        "rendered": rendered, "ok": code == "ok",
                        "code": code,
                    })

    # Distill top-level hints.
    hints: list[str] = []
    available = sorted(steps_in_env.keys())
    for key in sorted(referenced_step_keys):
        if key not in steps_in_env:
            hints.append(
                f"step reference `vars.steps.{key}` has no entry in the "
                f"run env — either {key!r} did not execute, or the step "
                f"name in YAML doesn't match (use display name with "
                f"spaces→underscores). Available: "
                + (", ".join(available[:8]) or "(none)")
            )
    fail_n = sum(1 for d in diagnostics if not d.get("ok"))
    return {
        "ok": fail_n == 0 and run_status not in ("failed", "Failed"),
        "pb_execution": pb_execution,
        "run_status": run_status,
        "playbook_name": env_out.get("name"),
        "step_diagnostics": diagnostics,
        "available_step_keys": available,
        "summary": {
            "total_templates": len(diagnostics),
            "render_failures": fail_n,
            "referenced_step_keys": sorted(referenced_step_keys),
        },
        "hints": hints,
    }


_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
                      r"[0-9a-f]{4}-[0-9a-f]{12}$", re.I)


def _looks_like_run_id(s: str) -> bool:
    """Workflow PK (all digits) or task_id (UUID)."""
    return s.isdigit() or bool(_UUID_RE.match(s))


@mcp.tool()
def why_did_playbook_fail(
    playbook_or_id: str, yaml_text: str | None = None,
) -> dict[str, Any]:
    """One-shot triage: given a playbook name OR a run id, fetch the most
    recent failed run's env, pull the live YAML if not provided, and
    render every Jinja block in the YAML against the run's vars to
    surface the failure cause.

    Chains three existing tools (`list_recent_failed_runs` →
    `get_run_env` → `diagnose_yaml_against_pb_execution`) plus a
    decompile pass when the caller doesn't ship YAML.

    Args:
        playbook_or_id: a playbook display name ("Block Indicator"),
            workflow PK (e.g. "676747"), or task_id UUID.
        yaml_text: optional. If omitted, the tool pulls the playbook
            from the live FSR and decompiles it. Provide explicitly to
            diagnose an in-progress edit against a past run.

    Returns:
        {ok, pb_execution, run_status, playbook_name, error_message,
         summary{total_templates, render_failures, referenced_step_keys},
         step_diagnostics[], hints[]} — or {ok: False, code, message}
        on resolution failure.
    """
    # Step 1 — resolve playbook_or_id to a concrete run.
    run_match: dict[str, Any] | None = None
    error_message: str | None = None
    if _looks_like_run_id(playbook_or_id):
        pb_execution = playbook_or_id
    else:
        runs = tools_triage.list_recent_failed_runs(
            limit=1, playbook=playbook_or_id,
        )
        if not runs or runs[0].get("error"):
            msg = (runs[0].get("error") if runs else
                   "no recent failed runs matched")
            return _err(
                "no_failed_runs",
                f"no recent failed run found for {playbook_or_id!r}: {msg}",
                suggestions=[
                    "Confirm the playbook name (substring match, case-insensitive)",
                    "Try `list_recent_failed_runs(playbook=...)` directly",
                    "Pass a workflow PK or task_id UUID instead of a name",
                ],
                playbook_or_id=playbook_or_id,
            )
        run_match = runs[0]
        pb_execution = run_match.get("task_id") or str(run_match.get("pk") or "")
        error_message = run_match.get("error_message")
        if not pb_execution:
            return _err("missing_run_id",
                        "matched run has no task_id/pk",
                        run=run_match)

    # Step 2 — if YAML wasn't supplied, pull the live playbook + decompile.
    if not yaml_text:
        try:
            sys.path.insert(0, str(REPO_ROOT / "python"))
            from cli import (  # type: ignore
                _fetch_workflow_with_refs, _decompile_to_yaml,
            )
            from probes import _env as _env_mod  # type: ignore
        except Exception as exc:  # noqa: BLE001
            return _err("decompile_import_failed", repr(exc))
        cfg = _env_mod.get_config()
        if not cfg.is_live():
            return _err("fsr_not_configured",
                        "live FSR not configured; pass yaml_text= explicitly")
        client = _env_mod.get_client()
        # We have a run; get the playbook name to pull the live YAML.
        env_peek = tools_triage.get_run_env(pb_execution)
        pb_name = env_peek.get("name") if isinstance(env_peek, dict) else None
        if not pb_name:
            return _err(
                "run_name_unknown",
                "could not resolve playbook name from run env",
                pb_execution=pb_execution,
                env_error=env_peek.get("error") if isinstance(env_peek, dict) else None,
            )
        coll = _fetch_workflow_with_refs(client, pb_name)
        if coll is None:
            return _err(
                "playbook_not_found",
                f"could not pull playbook {pb_name!r} from FSR",
                suggestions=["Pass yaml_text= explicitly"],
            )
        try:
            yaml_text = _decompile_to_yaml(coll, DB_PATH)
        except Exception as exc:  # noqa: BLE001
            return _err("decompile_failed", repr(exc), playbook=pb_name)

    # Step 3 — diagnose.
    result = diagnose_yaml_against_pb_execution(yaml_text, pb_execution)
    if isinstance(result, dict) and error_message and "error_message" not in result:
        result["error_message"] = error_message
    if isinstance(result, dict) and run_match:
        result["matched_run"] = {
            "task_id": run_match.get("task_id"),
            "name": run_match.get("name"),
            "status": run_match.get("status"),
            "modified": run_match.get("modified"),
        }
    return result


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()