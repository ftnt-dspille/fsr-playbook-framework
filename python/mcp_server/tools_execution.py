"""MCP tools: Tools Execution"""
from __future__ import annotations
from . import _shared

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
def run_op(
    connector: str,
    op: str,
    params: dict[str, Any] | None = None,
    config: str = "",
    confirm: bool = False,
) -> dict[str, Any]:
    """Execute a single connector operation on the live FSR instance and return
    its real output.

    This is the authoritative way to discover what a step produces when
    info.json has no output_schema or the static schema is incomplete.

    **Guardrails** — operations are classified by their `category` field:
    - `query / investigation / utilities` → **safe**, runs automatically.
    - `remediation / containment / management` → **destructive**, requires
      `confirm=True`.  The tool returns `{requires_confirmation: true}` when
      confirm is omitted so the caller (agent or user) can decide explicitly.
    - Any other / unknown category → also requires `confirm=True`.

    Pass `confirm=True` only after the user has approved the action or you are
    certain it is a read-only probe with no side effects.

    On success:
    - Returns `{ok: true, data: <actual_output>, output_shape: <inferred_type_shape>}`
    - Stores the inferred shape in `output_schema_observed` so `get_op_schema`
      returns it on all future calls without re-running the operation.
    - Records a `live_op_exec / tested_pass` verification row.

    On failure:
    - Returns `{ok: false, status: <str>, message: <str>}` with the FSR error.
    - Records `live_op_exec / tested_fail` so the store tracks the attempt.

    `params` — dict of input parameter values for the operation.
    `config` — optional connector config name (leave empty for the default config).
    `confirm` — set True to execute operations that are not auto-safe.
    """
    sys.path.insert(0, str(REPO_ROOT / "python"))
    try:
        from probes._env import get_client, get_config
    except ImportError:
        return _err("probes_unavailable", "probes module not available")

    cfg = get_config()
    if not cfg.is_live():
        return _err(
            "no_live_fsr",
            "FSR instance not configured",
            suggestions=[
                "Set FSR_BASE_URL and FSR_API_KEY in .env",
                "Run `fsrpb env` to confirm the live target",
            ],
        )

    # Resolve connector version + op category from store
    with _db() as conn:
        conn.row_factory = sqlite3.Row
        crow = conn.execute(
            "SELECT version FROM connectors WHERE name=?", (connector,)
        ).fetchone()
        op_row = conn.execute(
            "SELECT category FROM operations WHERE connector_name=? AND op_name=?",
            (connector, op),
        ).fetchone()
        near = []
        if crow is None:
            near = [r[0] for r in conn.execute(
                "SELECT name FROM connectors WHERE name LIKE ? LIMIT 5",
                (f"%{connector}%",),
            ).fetchall()]
    if crow is None:
        return _err(
            "unknown_connector",
            f"connector '{connector}' not found in store",
            suggestions=near or [
                "Run `find_connector` to search the catalog",
            ],
            connector=connector,
        )
    version = crow["version"]

    category = op_row["category"] if op_row else None
    from .tools_discovery import _op_risk
    risk = _op_risk(op, category)
    if risk != "safe" and not confirm:
        return {
            "ok": False,
            "code": "requires_confirmation",
            "requires_confirmation": True,
            "risk": risk,
            "category": category or "unknown",
            "connector": connector,
            "op": op,
            "message": (
                f"Operation '{op}' on '{connector}' has risk level '{risk}' "
                f"(category: {category!r}). Re-call with confirm=True after the "
                "user has approved, or confirm this is a safe read-only probe."
            ),
            "suggestions": [
                f"If you're certain this is safe, retry with confirm=True",
                f"Otherwise ask the user before mutating state on the live FSR",
            ],
        }

    body = {
        "connector": connector,
        "operation": op,
        "version": version,
        "config": config,
        "params": params or {},
    }

    client = get_client()
    try:
        resp = client.post("/api/integration/execute/", body)
    except Exception as exc:  # noqa: BLE001
        r = getattr(exc, "response", None)
        status = getattr(r, "status_code", "?")
        msg = (r.text if r is not None else str(exc))[:600]
        _record_verification(connector, op, "tested_fail", msg[:2000])
        return _err(
            "transport_failed", msg,
            suggestions=[
                "Check FSR connectivity and `fsrpb health`",
                "Confirm the connector config is configured + active",
            ],
            status=str(status),
        )

    if not isinstance(resp, dict):
        return _err(
            "bad_response_shape",
            f"unexpected response type: {type(resp).__name__}",
        )

    exec_status = resp.get("status", "")
    if exec_status not in ("Success", "success", "Completed", "completed", ""):
        msg = resp.get("message", "") or json.dumps(resp)[:600]
        _record_verification(connector, op, "tested_fail", msg[:2000])
        return _err(
            "execution_failed", msg,
            suggestions=[
                "Inspect `params` against `get_op_schema` required fields",
                "If auth/scope error, verify the connector config on FSR",
            ],
            status=exec_status,
        )

    data = resp.get("data", resp)
    shape = _infer_shape(data)
    _store_observed_schema(connector, op, data)
    # Surface the observed top-level keys inline so the agent can wire
    # `{{ vars.steps.<step>.<key> }}` references in a follow-up step
    # without a round-trip back to get_op_schema. List payloads expose
    # the first element's keys (collection shape).
    sample = data[0] if isinstance(data, list) and data else data
    top_keys = sorted(sample.keys()) if isinstance(sample, dict) else []
    return {
        "ok": True,
        "data": data,
        "output_shape": shape,
        "output_top_keys": top_keys,
        "output_is_list": isinstance(data, list),
        "schema_cached": True,
    }


def _record_verification(connector: str, op: str, status: str, notes: str) -> None:
    import datetime
    ts = datetime.datetime.utcnow().isoformat()
    with sqlite3.connect(_shared.DB_PATH) as conn:
        conn.execute(
            """INSERT OR REPLACE INTO verifications (kind, key, method, status, ts, notes)
               VALUES ('operation', ?, 'live_op_exec', ?, ?, ?)""",
            (f"{connector}:{op}", status, ts, notes),
        )



@mcp.tool()
def push_playbook(yaml_text: str) -> dict[str, Any]:
    """Compile a YAML playbook and push it to the live FSR instance.

    Idempotent: PUT first, POST on 404, hard-purge + POST on 409 (matches
    `fsrpb push --mode replace`). Use after `validate_yaml` returns clean.

    Returns:
        {ok: true, collection_uuid, collection_name, workflows: [{name, uuid}],
         action: "put"|"post"|"purge_post"} on success.
        {ok: false, errors: [...]} on compile failure.
        {ok: false, error: str} on push failure.
    """
    sys.path.insert(0, str(REPO_ROOT / "python"))
    try:
        from compiler import compile_yaml as _compile
        from probes._env import get_client, get_config
        from e2e.runner import _push, _PushError
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"import failed: {e!r}"}
    if not get_config().is_live():
        return {"ok": False, "error": "FSR instance not configured"}
    result = _compile(yaml_text, _shared.DB_PATH)
    if not result.ok:
        return {"ok": False, "errors": [
            {"code": e.code.value, "path": e.path, "message": e.message,
             "suggestion": e.suggestion or ""}
            for e in result.errors
        ]}
    coll = result.fsr_json["data"][0]
    client = get_client()
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        try:
            _push(client, coll, Path(td))
        except _PushError as e:
            return {"ok": False, "error": str(e)}
    return {
        "ok": True,
        "collection_uuid": coll["uuid"],
        "collection_name": coll["name"],
        "workflows": [{"name": w.get("name"), "uuid": w.get("uuid")}
                      for w in coll.get("workflows", [])],
    }

@mcp.tool()
def run_playbook(playbook: str,
                 input: dict[str, Any] | None = None,
                 collection: str | None = None,
                 record: str | None = None,
                 follow: bool = True,
                 timeout_s: int = 180,
                 use_mock_output: bool = False) -> dict[str, Any]:
    """Trigger a deployed playbook and (optionally) poll until terminal.

    Args:
        playbook: workflow name OR uuid OR `Collection:Name` shorthand
        input: trigger params; FSR maps these to `vars.input.params.<k>`
        collection: collection name to disambiguate duplicate workflow names
        record: "<module>:<uuid>" for record-context (cybersponse.action)
            triggers; omit for /notrigger style (designer Run button)
        follow: if True, poll until terminal status (default 180s timeout)
        timeout_s: poll timeout when follow=True
        use_mock_output: honor each step's `arguments.mock_result` instead
            of running live (good for dry-running without external API calls)

    Returns:
        {ok, status, task_id, wf_uuid, wf_pk, error_message?, failed_steps?}.
        `ok` is True only when status == "finished"; "finished_with_error"
        and "failed" return ok=False with diagnostics.
    """
    sys.path.insert(0, str(REPO_ROOT / "python"))
    try:
        from probes._env import get_client, get_config
        from cli import _resolve_workflow_ident
        from e2e.runner import _fetch_trigger_route_uuid
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"import failed: {e!r}"}
    if not get_config().is_live():
        return {"ok": False, "error": "FSR instance not configured"}
    client = get_client()
    wf_uuid = _resolve_workflow_ident(client, playbook, collection)
    if not wf_uuid:
        return {"ok": False, "error": f"no playbook matching {playbook!r}"}

    if record:
        if ":" not in record:
            return {"ok": False, "error": "record must be '<module>:<uuid>'"}
        module, rec_uuid = record.split(":", 1)
        route_uuid = _fetch_trigger_route_uuid(client, wf_uuid)
        if not route_uuid:
            return {"ok": False, "error": (
                "no trigger.route on workflow — playbook is not a "
                "record-action style trigger; omit `record`"
            )}
        path = f"/api/triggers/1/action/{route_uuid}"
        body = {"singleRecordExecution": True, "__resource": module,
                "__uuid": wf_uuid,
                "records": [f"/api/3/{module}/{rec_uuid}"]}
    else:
        path = f"/api/triggers/1/notrigger/{wf_uuid}"
        body = {"input": {}, "request": {"data": input or {}},
                "useMockOutput": bool(use_mock_output), "globalMock": False}

    try:
        r = client.session.post(client.base_url + path, json=body,
                                verify=client.verify_ssl)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"trigger failed: {e!r}"}
    if r.status_code >= 400:
        return {"ok": False, "error": f"HTTP {r.status_code}: {r.text[:300]}"}
    try:
        resp = r.json()
    except Exception:  # noqa: BLE001
        resp = {}
    task_id = resp.get("task_id") if isinstance(resp, dict) else None
    if not follow or not task_id:
        return {"ok": True, "status": "triggered", "task_id": task_id,
                "wf_uuid": wf_uuid}

    import time
    terminal = {"finished", "failed", "terminated", "skipped",
                "finished_with_error", "rejected"}
    poll_url = (client.base_url + "/api/wf/api/workflows/?format=json"
                f"&limit=1&ordering=-modified&task_id={task_id}"
                "&parent_wf__isnull=True")
    start = time.time()
    while time.time() - start < timeout_s:
        try:
            pr = client.session.get(poll_url, verify=client.verify_ssl)
            members = (pr.json() or {}).get("hydra:member") or []
        except Exception:  # noqa: BLE001
            members = []
        if members:
            rec = members[0]
            status = rec.get("status", "unknown")
            if status in terminal:
                wf_pk = (rec.get("@id") or "").rstrip("/").rsplit("/", 1)[-1]
                ok = status == "finished"
                out: dict[str, Any] = {"ok": ok, "status": status,
                                       "task_id": task_id, "wf_uuid": wf_uuid,
                                       "wf_pk": wf_pk}
                if not ok:
                    # Pull the full record for step-level diagnostics.
                    try:
                        fr = client.session.get(
                            client.base_url + "/api" + (rec.get("@id") or ""),
                            verify=client.verify_ssl)
                        full = fr.json() if fr.status_code == 200 else rec
                    except Exception:  # noqa: BLE001
                        full = rec
                    top = full.get("result") or {}
                    out["error_message"] = (
                        (top.get("Error message") if isinstance(top, dict) else None)
                        or full.get("errorMessage") or full.get("error"))
                    failed = []
                    for s in full.get("steps") or []:
                        if s.get("status") in ("failed", "finished_with_error",
                                               "terminated"):
                            res = s.get("result") or {}
                            failed.append({
                                "name": s.get("name"),
                                "status": s.get("status"),
                                "error": (res.get("Error message")
                                          or res.get("error")
                                          or res.get("message")
                                          or json.dumps(res)[:300]
                                          if isinstance(res, dict) else str(res)),
                            })
                    out["failed_steps"] = failed
                return out
        time.sleep(2)
    return {"ok": False, "status": "timeout", "task_id": task_id,
            "wf_uuid": wf_uuid,
            "error_message": f"timeout after {timeout_s}s"}

@mcp.tool()
def dry_run_playbook(yaml_text: str, playbook: str,
                     input: dict[str, Any] | None = None,
                     timeout_s: int = 180,
                     cleanup: bool = True,
                     use_mock_output: bool = False) -> dict[str, Any]:
    """Compile + push + run + auto-cleanup. The agent's full E2E loop in one tool.

    Args:
        yaml_text: full YAML source.
        playbook: workflow name to trigger after push (one playbook in the
            collection — the agent picks which one).
        input: trigger params (mapped to `vars.input.params.<k>`).
        timeout_s: poll timeout (default 180s).
        cleanup: hard-purge the collection after the run (default True).
            Set False to keep the collection on the instance for inspection.
        use_mock_output: run with each step's `arguments.mock_result` instead
            of live external calls.

    Returns:
        {ok, status, task_id, wf_pk, collection_uuid, error_message?,
         failed_steps?, cleaned_up: bool}.
    """
    push = push_playbook(yaml_text)
    if not push.get("ok"):
        return {"ok": False, "stage": "push", **push}
    run = run_playbook(playbook, input=input,
                       collection=push.get("collection_name"),
                       follow=True, timeout_s=timeout_s,
                       use_mock_output=use_mock_output)
    coll_uuid = push["collection_uuid"]
    cleaned = False
    if cleanup:
        try:
            from probes._env import get_client
            from e2e.runner import _hard_purge
            client = get_client()
            # Re-fetch the workflow uuids in case the push reshaped them.
            sys.path.insert(0, str(REPO_ROOT / "python"))
            _hard_purge(client, coll_uuid,
                        {"workflows": [{"uuid": w["uuid"]}
                                       for w in push.get("workflows", [])]})
            cleaned = True
        except Exception:  # noqa: BLE001
            cleaned = False
    return {**run, "stage": "run", "collection_uuid": coll_uuid,
            "cleaned_up": cleaned}

@mcp.tool()
def healthcheck_connector(name: str, version: str | None = None,
                          config: str | None = None) -> dict[str, Any]:
    """Live-check whether a single connector configuration is reachable.

    Use after `list_configured_connectors` to confirm the upstream service
    is actually up before recommending an op to the user.

    Args:
        name: connector name
        version: optional — when omitted, the first configured version is used
        config: optional config UUID — required when the connector has more
            than one configuration and you want a specific one

    Returns:
        {status, message, name, version, config_id}
        status="Available" → green; "Disconnected" → connector configured but
        upstream is down; HTTP 404 → no configuration on this instance.
    """
    try:
        from probes._env import get_client, get_config
    except Exception as e:  # noqa: BLE001
        return {"error": f"could not import _env: {e!r}"}
    cfg = get_config()
    if not cfg.is_live():
        return {"error": "FSR instance not configured (FSR_BASE_URL / FSR_API_KEY missing in .env)"}
    client = get_client()
    if version is None:
        try:
            r = client.session.post(
                client.base_url
                + "/api/integration/connector_details/?format=json&configured=true&exclude=operation&active=true",
                json={}, verify=client.verify_ssl,
            )
            rows = (r.json().get("data") or []) if r.status_code == 200 else []
        except Exception as e:  # noqa: BLE001
            return {"error": f"version lookup failed: {e!r}"}
        cands = [x for x in rows if x.get("name") == name]
        if not cands:
            return {"error": f"no configured connector named {name!r}; pass version explicitly"}
        version = cands[0].get("version")
    url = f"/api/integration/connectors/healthcheck/{name}/{version}/"
    if config:
        url += f"?config={config}"
    try:
        r = client.session.get(client.base_url + url, verify=client.verify_ssl)
    except Exception as e:  # noqa: BLE001
        return {"error": f"healthcheck request failed: {e!r}"}
    if r.status_code == 404:
        return {"name": name, "version": version, "status": "no-config",
                "http_status": 404, "message": "no configuration on this instance"}
    try:
        return r.json()
    except Exception:  # noqa: BLE001
        return {"name": name, "version": version, "http_status": r.status_code,
                "raw": r.text[:500]}


def _fetch_runs_both(client, *, limit: int, extra_qs: str = "") -> list[dict[str, Any]]:
    """Fetch from /workflows/ AND /historical-workflows/, merge by modified desc.

    FSR purges live workflow logs to the historical table every ~30-60 min for
    performance, so any triage tool that only hits /workflows/ goes blind to
    older failures. Historical also returns richer fields (`result`, `steps`,
    `env`) inline. Dedup by `@id` in case a run is in both during the move.
    """
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in ("/api/wf/api/workflows/", "/api/wf/api/historical-workflows/"):
        url = (client.base_url + path
               + f"?format=json&limit={limit}&ordering=-modified"
               + f"&parent_wf__isnull=True{extra_qs}")
        try:
            r = client.session.get(url, verify=client.verify_ssl)
        except Exception:  # noqa: BLE001
            continue
        if r.status_code != 200:
            continue
        for m in (r.json().get("hydra:member") or []):
            iri = m.get("@id") or ""
            if iri and iri in seen:
                continue
            seen.add(iri)
            m["_source"] = "historical" if "historical" in path else "live"
            out.append(m)
    out.sort(key=lambda m: m.get("modified") or "", reverse=True)
    return out


def _shape_run(m: dict) -> dict:
    res = m.get("result") if isinstance(m.get("result"), dict) else {}
    err = ((res.get("Error message") or res.get("error")
            or res.get("message")) if isinstance(res, dict) else None)
    pk_url = m.get("@id") or ""
    pk = pk_url.rstrip("/").rsplit("/", 1)[-1] if pk_url else None
    return {
        "task_id": m.get("task_id"),
        "name": m.get("name"),
        "status": m.get("status"),
        "error_message": err,
        "modified": m.get("modified"),
        "uuid": m.get("uuid"),
        "pk": pk,
        "source": m.get("_source"),  # "live" or "historical"
    }