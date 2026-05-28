"""E2E test runner for the fsrpb compiler+push+execute loop.

Reads a sidecar `<fixture>.test.yaml`, compiles the referenced YAML
fixture, pushes it to the live FSR instance, runs optional setup
(insert tagged test records), triggers the playbook (manual `/notrigger`
or record-context `/action/<wf>`), polls until terminal, fetches the run
env, evaluates assertions, deletes setup records, and (optionally)
hard-purges the collection.

Test sidecar schema:

    fixture:    examples/<fixture>.yaml
    playbook:   <playbook name>

    # ----- setup (optional) -----
    setup:
      - kind: create_record
        module: alerts
        fields:
          name: fsrpb_e2e_test_alert
          severity: /api/3/picklists/<high-uuid>
        capture_as: alert            # exposes setup.alert.<field> to templates

    # ----- trigger (one of) -----
    input: {…}                       # /notrigger body (manual / abstract_trigger)
    record: "alerts:{{ setup.alert.uuid }}"   # /action/<wf> record-context fire

    timeout_s: 120

    expects:
      status: finished               # workflow.status (default)
      vars:   {tier: tier2}          # exact-match against env vars
      steps:                         # per-step assertions
        Branch_on_X: {status: finished, result_contains: '"ok"'}
      record:                        # post-run assertions on a setup record
        capture: alert
        fields:
          status: closed             # exact match (after re-fetching the record)

    cleanup: true                    # hard-purge collection (default true)
"""

from __future__ import annotations

import json
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import yaml

# probes/_env.py is the canonical .env+client loader used everywhere.
from probes import _env  # type: ignore
from fsr_core.compiler import compile_yaml


TERMINAL = {"finished", "failed", "terminated", "skipped",
            "finished_with_error", "rejected"}


@dataclass
class RunResult:
    run_id: str
    ok: bool
    status: str | None = None  # workflow status
    task_id: str | None = None
    wf_pk: str | None = None
    coll_uuid: str | None = None
    failures: list[str] = field(default_factory=list)
    log_dir: Path | None = None


def run_test(test_path: Path, *, log_root: Path | None = None,
             keep: bool = False, verbose: bool = True) -> RunResult:
    """Run a single .test.yaml. Returns a RunResult; never raises for
    expected failure modes (compile errors, push failure, run failed,
    assertion failure) — those land in `failures` and `ok=False`."""

    run_id = uuid.uuid4().hex[:8]
    log_dir = (log_root or _default_log_root()) / run_id
    log_dir.mkdir(parents=True, exist_ok=True)
    res = RunResult(run_id=run_id, ok=False, log_dir=log_dir)

    def _log(msg: str) -> None:
        (log_dir / "run.log").open("a").write(msg + "\n")
        if verbose:
            print(msg, file=sys.stderr)

    def _fail(msg: str) -> RunResult:
        res.failures.append(msg)
        _log(f"FAIL: {msg}")
        return res

    test_path = test_path.resolve()
    spec = yaml.safe_load(test_path.read_text()) or {}
    fixture_rel = spec.get("fixture")
    if not fixture_rel:
        return _fail("test spec missing 'fixture'")
    fixture_path = (test_path.parent / fixture_rel).resolve()
    if not fixture_path.exists():
        # try repo-relative as a fallback
        repo_root = Path(__file__).resolve().parents[2]
        fixture_path = (repo_root / fixture_rel).resolve()
    if not fixture_path.exists():
        return _fail(f"fixture not found: {fixture_rel}")

    playbook_name = spec.get("playbook")
    if not playbook_name:
        return _fail("test spec missing 'playbook'")
    trigger_input = spec.get("input") or {}
    trigger_record = spec.get("record")  # "module:uuid", may contain templates
    trigger_mutate = spec.get("mutate")  # {capture, fields} for post_update
    trigger_auto = bool(spec.get("auto_trigger"))  # post_create: setup POST fires it
    resume_spec = spec.get("resume_input")  # {option, vars} for manual_input auto-resume
    setup_steps = spec.get("setup") or []
    timeout_s = int(spec.get("timeout_s", 180))
    expects = spec.get("expects") or {}
    cleanup = bool(spec.get("cleanup", True)) and not keep
    setup_ctx: dict = {}        # capture_as → record dict
    cleanup_records: list[tuple[str, str]] = []  # (module, uuid)

    _log(f"[{run_id}] fixture={fixture_path.name} playbook={playbook_name}")

    # 1. Compile.
    db_path = _store_db_path()
    text = fixture_path.read_text()
    compiled = compile_yaml(text, db_path)
    if not compiled.ok:
        (log_dir / "compile_errors.json").write_text(
            json.dumps([e.__dict__ if hasattr(e, "__dict__") else str(e)
                        for e in compiled.errors], indent=2, default=str))
        return _fail(f"compile failed: {len(compiled.errors)} error(s)")
    coll_entity = compiled.fsr_json["data"][0]
    coll_uuid = coll_entity["uuid"]
    coll_name = coll_entity["name"]
    res.coll_uuid = coll_uuid
    (log_dir / "compiled.json").write_text(json.dumps(coll_entity, indent=2))
    _log(f"[{run_id}] compiled: {coll_name} uuid={coll_uuid[:8]} "
         f"({len(coll_entity['workflows'])} playbook(s))")

    # 2. Live env.
    cfg = _env.get_config()
    if not cfg.is_live():
        return _fail("FSR_BASE_URL / auth not configured (.env)")
    client = _env.get_client()

    # 3. Push (PUT → POST → PURGE+POST).
    try:
        _push(client, coll_entity, log_dir)
    except _PushError as e:
        return _fail(f"push failed: {e}")
    _log(f"[{run_id}] pushed")

    # 4. Resolve target workflow uuid (by name + collection).
    wf_uuid = _resolve_wf(client, coll_uuid, playbook_name)
    if not wf_uuid:
        if cleanup:
            _hard_purge(client, coll_uuid, coll_entity)
        return _fail(f"could not resolve workflow {playbook_name!r} in {coll_name}")

    # 4b. Setup steps: insert tagged test records, capture for templating + cleanup.
    # For auto_trigger mode (post_create), capture the timestamp BEFORE
    # setup runs — the setup POST itself fires the run.
    if trigger_auto:
        trigger_started = time.time()
    try:
        for i, step in enumerate(setup_steps):
            kind = step.get("kind")
            # Accept create_record (preferred) and the legacy insert_record alias.
            if kind not in ("create_record", "insert_record"):
                _log(f"[{run_id}] setup[{i}] unknown kind {kind!r}, skipping")
                continue
            module = step.get("module")
            fields = _render_templates(step.get("fields") or {}, setup_ctx)
            fields = _resolve_module_fields(client, module, fields)
            sr = client.session.post(client.base_url + f"/api/3/{module}",
                                     json=fields, verify=client.verify_ssl)
            if sr.status_code >= 400:
                raise RuntimeError(f"setup[{i}] insert {module} failed: "
                                   f"HTTP {sr.status_code}: {sr.text[:200]}")
            rec = sr.json()
            cap = step.get("capture_as") or module
            setup_ctx[cap] = rec
            cleanup_records.append((module, rec.get("uuid")))
            _log(f"[{run_id}] setup[{i}] inserted {module}/"
                 f"{(rec.get('uuid') or '?')[:8]} as {cap!r}")
    except Exception as e:  # noqa: BLE001
        _flush_cleanup(client, cleanup_records, _log, run_id)
        if cleanup:
            _hard_purge(client, coll_uuid, coll_entity)
        return _fail(f"setup failed: {e}")

    # 5. Trigger. Four modes:
    #    - auto:   the setup POST itself fires the run (post_create)
    #    - mutate: PUT a captured setup record to fire post_update
    #    - record: /action/<route> for cybersponse.action (record-context manual)
    #    - input:  /notrigger/<wf> for cybersponse.abstract_trigger (manual)
    rec_target = _render_templates(trigger_record, setup_ctx) if trigger_record else None
    if trigger_auto:
        _log(f"[{run_id}] auto-trigger (post_create) — setup POST fired the run")
        task_id = None
    elif trigger_mutate:
        cap = trigger_mutate.get("capture")
        if not cap or cap not in setup_ctx:
            _flush_cleanup(client, cleanup_records, _log, run_id)
            if cleanup:
                _hard_purge(client, coll_uuid, coll_entity)
            return _fail(f"mutate.capture {cap!r} not in setup captures "
                         f"({list(setup_ctx)})")
        target_rec = setup_ctx[cap]
        rec_uuid = target_rec.get("uuid")
        # Find module from cleanup_records (the setup step recorded it).
        module = next((m for m, u in cleanup_records if u == rec_uuid), None)
        if not module or not rec_uuid:
            _flush_cleanup(client, cleanup_records, _log, run_id)
            if cleanup:
                _hard_purge(client, coll_uuid, coll_entity)
            return _fail(f"mutate target {cap!r} missing module/uuid")
        mut_fields = _render_templates(trigger_mutate.get("fields") or {}, setup_ctx)
        mut_fields = _resolve_module_fields(client, module, mut_fields)
        trigger_started = time.time()
        pr = client.session.put(
            client.base_url + f"/api/3/{module}/{rec_uuid}",
            json=mut_fields, verify=client.verify_ssl)
        if pr.status_code >= 400:
            _flush_cleanup(client, cleanup_records, _log, run_id)
            if cleanup:
                _hard_purge(client, coll_uuid, coll_entity)
            (log_dir / "mutate_error.txt").write_text(f"{pr.status_code}\n{pr.text}")
            return _fail(f"mutate PUT failed: HTTP {pr.status_code}")
        _log(f"[{run_id}] mutated {module}/{rec_uuid[:8]} → "
             f"{list(mut_fields)} (post_update fire)")
        # Skip the POST /triggers branch entirely — FSR's event subscriber
        # spawns the workflow run from the PUT.
        task_id = None
    elif rec_target:
        if ":" not in rec_target:
            _flush_cleanup(client, cleanup_records, _log, run_id)
            if cleanup:
                _hard_purge(client, coll_uuid, coll_entity)
            return _fail(f"record trigger must be 'module:uuid', got {rec_target!r}")
        module, rec_uuid = rec_target.split(":", 1)
        # /action takes the trigger step's `route` UUID in the URL, NOT
        # the workflow uuid; and the body's misleadingly-named `__uuid`
        # is the WORKFLOW uuid (not the record). Confirmed against the
        # FSR UI's Run-Action request 2026-05-03. The route uuid lives
        # in arguments.route on the trigger step — fetch it.
        route_uuid = _fetch_trigger_route_uuid(client, wf_uuid)
        if not route_uuid:
            _flush_cleanup(client, cleanup_records, _log, run_id)
            if cleanup:
                _hard_purge(client, coll_uuid, coll_entity)
            return _fail(f"could not find trigger.route on wf {wf_uuid[:8]} "
                         f"(record-action playbook?)")
        trig_url = f"{client.base_url}/api/triggers/1/action/{route_uuid}"
        body = {"singleRecordExecution": True, "__resource": module,
                "__uuid": wf_uuid,
                "records": [f"/api/3/{module}/{rec_uuid}"]}
    else:
        # Resolve any {{ setup.<cap>.<field> }} templates in the input
        # values now that setup has run.
        resolved_input = _render_templates(trigger_input, setup_ctx)
        trig_url = f"{client.base_url}/api/triggers/1/notrigger/{wf_uuid}"
        body = {"input": {}, "request": {"data": resolved_input or {}},
                "useMockOutput": False, "globalMock": False}
    if not trigger_mutate and not trigger_auto:
        trigger_started = time.time()
        r = client.session.post(trig_url, json=body, verify=client.verify_ssl)
        if r.status_code >= 400:
            _flush_cleanup(client, cleanup_records, _log, run_id)
            if cleanup:
                _hard_purge(client, coll_uuid, coll_entity)
            (log_dir / "trigger_error.txt").write_text(f"{r.status_code}\n{r.text}")
            return _fail(f"trigger failed: HTTP {r.status_code}")
        task_id = (r.json() or {}).get("task_id") if rec_target is None else None
        if rec_target:
            _log(f"[{run_id}] triggered (action) wf={wf_uuid[:8]} record={rec_target}")
        else:
            if not task_id:
                _flush_cleanup(client, cleanup_records, _log, run_id)
                if cleanup:
                    _hard_purge(client, coll_uuid, coll_entity)
                return _fail("no task_id returned from /notrigger")
            res.task_id = task_id
            _log(f"[{run_id}] triggered task_id={task_id}")

    # 6. Poll to terminal. auto/mutate/record modes poll by template_iri;
    # notrigger polls by task_id.
    if trigger_auto or trigger_mutate or rec_target:
        final, pk = _poll_by_template(client, wf_uuid, trigger_started,
                                      timeout_s, log_dir, _log, run_id,
                                      resume_spec=resume_spec)
    else:
        final, pk = _poll(client, task_id, timeout_s, log_dir, _log, run_id,
                          resume_spec=resume_spec)
    if final is None:
        _flush_cleanup(client, cleanup_records, _log, run_id)
        if cleanup:
            _hard_purge(client, coll_uuid, coll_entity)
        return _fail(f"poll timeout after {timeout_s}s")
    res.wf_pk = pk
    status = final.get("status")
    res.status = status
    (log_dir / "final_record.json").write_text(json.dumps(final, indent=2, default=str))

    # 7. Assertions.
    failures = _check_expects(final, expects)
    rec_expects = (expects.get("record") or {}) if isinstance(expects, dict) else {}
    if rec_expects:
        cap = rec_expects.get("capture")
        if cap and cap in setup_ctx:
            module = next((m for m, u in cleanup_records
                          if u == setup_ctx[cap].get("uuid")), None)
            uuid_ = setup_ctx[cap].get("uuid")
            if module and uuid_:
                fr = client.session.get(client.base_url + f"/api/3/{module}/{uuid_}",
                                        verify=client.verify_ssl)
                if fr.status_code == 200:
                    fresh = fr.json()
                    for k, want in (rec_expects.get("fields") or {}).items():
                        got = _picklist_value(fresh.get(k))
                        if got != want:
                            failures.append(
                                f"record.{cap}.{k}: want {want!r}, got {got!r}")
                    for k, needle in (rec_expects.get("contains") or {}).items():
                        got = _picklist_value(fresh.get(k))
                        if not isinstance(got, str) or needle not in got:
                            failures.append(
                                f"record.{cap}.{k}: missing substring {needle!r}, "
                                f"got {got!r}")
                else:
                    failures.append(
                        f"record.{cap}: re-fetch failed HTTP {fr.status_code}")
    res.failures.extend(failures)

    # 8. Cleanup setup records + cleanup_query records, then collection.
    _flush_cleanup(client, cleanup_records, _log, run_id)
    for q in spec.get("cleanup_query") or []:
        _purge_by_query(client, q.get("module"), q.get("where") or {}, _log, run_id)
    if cleanup:
        _hard_purge(client, coll_uuid, coll_entity)
        _log(f"[{run_id}] purged collection")
    else:
        _log(f"[{run_id}] kept collection ({coll_uuid[:8]}) — pass keep=False to purge")

    res.ok = not failures and status == (expects.get("status", "finished"))
    _log(f"[{run_id}] {'PASS' if res.ok else 'FAIL'} status={status} "
         f"failures={len(failures)}")
    return res


# ---------- helpers ----------

class _PushError(Exception):
    pass


def _push(client, coll_entity: dict, log_dir: Path) -> None:
    """Idempotent push: PUT → POST on 404 → PURGE+POST on 409. Mirrors
    cmd_push --mode replace; pulled out so the runner doesn't shell out."""
    coll_uuid = coll_entity["uuid"]

    def _put():
        try:
            return True, client.put(f"/api/3/workflow_collections/{coll_uuid}", coll_entity)
        except Exception as e:  # noqa: BLE001
            return False, e

    def _post():
        try:
            return True, client.post("/api/3/workflow_collections", coll_entity)
        except Exception as e:  # noqa: BLE001
            return False, e

    ok, payload = _put()
    if not ok:
        r = getattr(payload, "response", None)
        status = getattr(r, "status_code", None)
        if status == 404:
            ok, payload = _post()
            if not ok:
                r2 = getattr(payload, "response", None)
                if getattr(r2, "status_code", None) == 409:
                    _hard_purge(client, coll_uuid, coll_entity)
                    ok, payload = _post()
        elif status == 409:
            _hard_purge(client, coll_uuid, coll_entity)
            ok, payload = _post()
    if not ok:
        e = payload
        r = getattr(e, "response", None)
        body = (r.text if r is not None else str(e))[:1000]
        (log_dir / "push_error.txt").write_text(body)
        raise _PushError(f"HTTP {getattr(r, 'status_code', '?')}: {body[:200]}")


def _hard_purge(client, coll_uuid: str, coll_entity: dict) -> None:
    """Hard-delete the collection and its (locally-known) workflows.

    Scope is strictly limited to UUIDs that came from the local just-
    compiled YAML — no server-side discovery, no name matching. Idempotent;
    individual failures swallowed (the followup POST will surface any
    remaining collision).

    Gated by FSR_ALLOW_HARD_DELETE or FSR_ALLOW_E2E so a misbehaving
    automation can't run this path silently.
    """
    import os
    _truthy = ("1", "true", "yes")
    if (
        os.environ.get("FSR_ALLOW_HARD_DELETE", "").lower() not in _truthy
        and os.environ.get("FSR_ALLOW_E2E", "").lower() not in _truthy
    ):
        raise _PushError(
            "hard-purge refused: set FSR_ALLOW_HARD_DELETE=true "
            "(or FSR_ALLOW_E2E=true) to enable"
        )
    try:
        client.session.delete(
            client.base_url + "/api/3/delete/workflow_collections?$hardDelete=true",
            json={"ids": [coll_uuid]}, verify=client.verify_ssl)
    except Exception:  # noqa: BLE001
        pass
    wf_uuids = [w.get("uuid") for w in coll_entity.get("workflows", []) if w.get("uuid")]
    if wf_uuids:
        try:
            client.session.delete(
                client.base_url + "/api/3/delete/workflows?$hardDelete=true",
                json={"ids": wf_uuids}, verify=client.verify_ssl)
        except Exception:  # noqa: BLE001
            pass


def _fetch_trigger_route_uuid(client, wf_uuid: str) -> str | None:
    """Pull the `route` arg from the workflow's trigger step. /action wires
    the action button to a workflow via this route uuid (separate from
    the workflow uuid)."""
    try:
        r = client.session.get(
            client.base_url + f"/api/3/workflows/{wf_uuid}?$relationships=true",
            verify=client.verify_ssl)
    except Exception:  # noqa: BLE001
        return None
    if r.status_code != 200:
        return None
    w = r.json()
    trig_iri = w.get("triggerStep") or ""
    for s in w.get("steps") or []:
        if s.get("@id") == trig_iri or trig_iri.endswith(s.get("uuid") or ""):
            args = s.get("arguments") if isinstance(s.get("arguments"), dict) else {}
            return args.get("route")
    return None


def _resolve_wf(client, coll_uuid: str, name: str) -> str | None:
    """Resolve a workflow uuid by name within a known collection uuid."""
    listing = client.get("/api/3/workflows", params={"name": name, "$limit": 50})
    members = listing.get("hydra:member") if isinstance(listing, dict) else []
    coll_iri = f"/api/3/workflow_collections/{coll_uuid}"
    for m in members:
        if m.get("name") == name and m.get("collection") == coll_iri:
            return m.get("uuid")
    return None


def _render_templates(value, ctx: dict):
    """Walk value and substitute `{{ setup.<key>.<field>… }}` against ctx.

    Templates are recognized as `{{ setup.X.Y }}` strings — a strict
    subset of Jinja, just enough for fixture wiring. Any other `{{ }}`
    is left as-is (it'll be resolved by FSR's runtime). Nested
    dicts/lists walked recursively.
    """
    if isinstance(value, str):
        import re
        def sub(m):
            expr = m.group(1).strip()
            if not expr.startswith("setup."):
                return m.group(0)
            parts = expr.split(".")
            cur = ctx
            for p in parts[1:]:
                if isinstance(cur, dict) and p in cur:
                    cur = cur[p]
                else:
                    return m.group(0)
            return str(cur)
        return re.sub(r"\{\{\s*([^}]+)\s*\}\}", sub, value)
    if isinstance(value, list):
        return [_render_templates(v, ctx) for v in value]
    if isinstance(value, dict):
        return {k: _render_templates(v, ctx) for k, v in value.items()}
    return value


def _resolve_module_fields(client, module: str, fields: dict) -> dict:
    """Resolve friendly picklist values in a record-fields dict to IRIs.
    Delegates to `picklists.resolve_module_fields`, which auto-discovers
    the picklist_name per (module, field) — no hardcoded map."""
    from picklists import resolve_module_fields as _shared
    return _shared(client, module, fields)


def _picklist_value(field):
    """When a re-fetched record field is a picklist dict, compare by
    itemValue or IRI; otherwise return the raw value."""
    if isinstance(field, dict):
        return field.get("itemValue") or field.get("@id") or field
    return field


def _purge_by_query(client, module: str, where: dict, log, run_id: str) -> None:
    """Find records matching `where` (field=value, exact match) and hard-delete.
    Uses POST /api/query/<module> to find, DELETE /api/3/delete/<module> to purge.
    """
    if not module or not where:
        return
    body = {"logic": "AND",
            "filters": [{"type": "primitive", "field": k, "value": v,
                         "operator": "eq", "_operator": "eq"}
                        for k, v in where.items()],
            "limit": 200}
    try:
        r = client.session.post(client.base_url + f"/api/query/{module}",
                                json=body, verify=client.verify_ssl)
    except Exception:  # noqa: BLE001
        return
    if r.status_code != 200:
        return
    members = r.json().get("hydra:member") or []
    uuids = [m.get("uuid") for m in members if m.get("uuid")]
    if not uuids:
        return
    try:
        client.session.delete(
            client.base_url + f"/api/3/delete/{module}?$hardDelete=true",
            json={"ids": uuids}, verify=client.verify_ssl)
    except Exception:  # noqa: BLE001
        pass
    log(f"[{run_id}] cleanup_query purged {len(uuids)} {module} record(s) "
        f"matching {where}")


def _flush_cleanup(client, cleanup_records: list[tuple[str, str]], log, run_id: str) -> None:
    for module, uuid_ in cleanup_records:
        if not uuid_:
            continue
        try:
            client.session.delete(
                client.base_url + f"/api/3/delete/{module}?$hardDelete=true",
                json={"ids": [uuid_]}, verify=client.verify_ssl)
        except Exception:  # noqa: BLE001
            pass
    if cleanup_records:
        log(f"[{run_id}] deleted {len(cleanup_records)} setup record(s)")


def _poll_by_template(client, wf_uuid: str, started_unix: float,
                      timeout_s: int, log_dir: Path, log, run_id: str,
                      *, resume_spec: dict | None = None,
                      ) -> tuple[dict | None, str | None]:
    """Poll for a workflow run matching template_iri=<wf_uuid> created
    after `started_unix`. Used for /action triggers which don't return
    a task_id. Race-window: if another run on the same playbook fires in
    the same second, we may grab the wrong one — fine for isolated test
    fixtures, fragile for shared playbooks."""
    import datetime
    template_iri = f"/api/3/workflows/{wf_uuid}"
    poll_url = (client.base_url + "/api/wf/api/workflows/?format=json"
                f"&limit=5&ordering=-modified&parent_wf__isnull=True"
                f"&template_iri={template_iri}")
    start = time.time()
    last = ""
    seen_pk: str | None = None
    while time.time() - start < timeout_s:
        r = client.session.get(poll_url, verify=client.verify_ssl)
        if r.status_code != 200:
            time.sleep(2)
            continue
        members = r.json().get("hydra:member") or []
        # Find newest run created after we triggered. The API returns
        # ISO-8601 'created' strings.
        candidate = None
        for m in members:
            created = m.get("created")
            if not created:
                continue
            try:
                ts = datetime.datetime.fromisoformat(created.replace("Z", "+00:00")).timestamp()
            except Exception:  # noqa: BLE001
                continue
            if ts >= started_unix - 5:  # 5s clock skew slack
                candidate = m
                break
        if candidate is None:
            time.sleep(2)
            continue
        status = candidate.get("status", "unknown")
        if status != last:
            log(f"[{run_id}]   status: {status}  ({int(time.time() - start)}s)")
            last = status
        if status == "awaiting" and resume_spec:
            wf_pk = (candidate.get("@id") or "").rstrip("/").rsplit("/", 1)[-1]
            _resume_awaiting(client, wf_pk, resume_spec, log, run_id)
        if status in TERMINAL:
            pk_url = candidate.get("@id") or ""
            full = candidate
            pk = None
            if pk_url:
                pk = pk_url.rstrip("/").rsplit("/", 1)[-1]
                try:
                    fr = client.session.get(
                        client.base_url + "/api" + pk_url + "?step_detail=true",
                        verify=client.verify_ssl)
                    if fr.status_code == 200:
                        full = fr.json()
                except Exception:  # noqa: BLE001
                    pass
            return full, pk
        time.sleep(2)
    return None, None


def _resume_awaiting(client, wf_pk: str, resume_spec: dict, log, run_id: str,
                     ) -> None:
    """When a run hits status='awaiting', find its pending manual_input
    and POST the canonical wfinput_resume body. resume_spec accepts:
        option: <button label>      (default: the option flagged primary)
        vars:   {<name>: <value>}   (only when inputVariables.required)
    Idempotent: if no pending input matches wf_pk, returns silently
    (the next poll iteration will retry).

    Match strategy: list_wfinput's `workflow` field is an opaque token,
    not the wf IRI. We instead fetch the wf record's current step_id
    (the one with status=processing/awaiting) and match against
    inputs[*].step_id, which is a stable workflow_step pk.
    """
    try:
        wfr = client.session.get(
            client.base_url + f"/api/wf/api/workflows/{wf_pk}/?format=json"
            f"&step_detail=true", verify=client.verify_ssl,
        )
        if wfr.status_code != 200:
            return
        wf_full = wfr.json()
    except Exception:  # noqa: BLE001
        return
    pending_step_ids = {
        s.get("id") for s in (wf_full.get("steps") or [])
        if s.get("status") in ("awaiting", "processing", "incipient")
    }
    try:
        r = client.session.post(
            client.base_url + "/api/wf/api/manual-wf-input/list_wfinput/"
            "?format=json&limit=200",
            json={}, verify=client.verify_ssl,
        )
        if r.status_code != 200:
            return
        items = r.json().get("hydra:member") or []
    except Exception:  # noqa: BLE001
        return
    target = next((it for it in items
                   if it.get("step_id") in pending_step_ids), None)
    # Fallback: if we couldn't link via step_id, take the newest input.
    if target is None and items:
        target = sorted(items, key=lambda i: i.get("created") or "",
                        reverse=True)[0]
    if target is None:
        return
    # The list endpoint omits response_mapping; fetch it via retrieve_wfinput.
    try:
        rr = client.session.post(
            client.base_url + f"/api/wf/api/manual-wf-input/{target['id']}/"
            f"retrieve_wfinput/?format=json",
            json={}, verify=client.verify_ssl,
        )
        if rr.status_code == 200:
            target = {**target, **rr.json()}
    except Exception:  # noqa: BLE001
        pass
    options = (target.get("response_mapping") or {}).get("options") or []
    want_label = resume_spec.get("option")
    chosen = None
    if want_label:
        chosen = next((o for o in options if o.get("option") == want_label), None)
    if chosen is None and options:
        chosen = next((o for o in options if o.get("primary")), options[0])
    body = {
        "input": resume_spec.get("vars") or {},
        "step_iri": (chosen or {}).get("step_iri"),
        "step_id": target.get("step_id"),
        "manual_input_id": int(target.get("id")),
    }
    if target.get("is_approval"):
        body["approved"] = bool((chosen or {}).get("primary"))
    pr = client.session.post(
        client.base_url + f"/api/wf/api/workflows/{wf_pk}/wfinput_resume/?format=json",
        json=body, verify=client.verify_ssl,
    )
    log(f"[{run_id}]   resumed manual_input #{target.get('id')} "
        f"option={(chosen or {}).get('option')!r} HTTP {pr.status_code}")


def _poll(client, task_id: str, timeout_s: int, log_dir: Path,
          log, run_id: str, *, resume_spec: dict | None = None,
          ) -> tuple[dict | None, str | None]:
    """Poll until terminal. Returns (full_record_with_steps, pk) or (None, None) on timeout."""
    poll_url = (client.base_url + "/api/wf/api/workflows/"
                "?format=json&limit=1&offset=0&ordering=-modified"
                f"&task_id={task_id}&parent_wf__isnull=True")
    start = time.time()
    last = ""
    while time.time() - start < timeout_s:
        r = client.session.get(poll_url, verify=client.verify_ssl)
        if r.status_code != 200:
            log(f"[{run_id}] poll HTTP {r.status_code}")
            time.sleep(2)
            continue
        members = r.json().get("hydra:member") or []
        if members:
            rec = members[0]
            status = rec.get("status", "unknown")
            if status != last:
                log(f"[{run_id}]   status: {status}  ({int(time.time() - start)}s)")
                last = status
            if status == "awaiting" and resume_spec:
                wf_pk = (rec.get("@id") or "").rstrip("/").rsplit("/", 1)[-1]
                _resume_awaiting(client, wf_pk, resume_spec, log, run_id)
            if status in TERMINAL:
                pk_url = rec.get("@id") or ""
                full = rec
                pk = None
                if pk_url:
                    pk = pk_url.rstrip("/").rsplit("/", 1)[-1]
                    try:
                        fr = client.session.get(
                            client.base_url + "/api" + pk_url + "?step_detail=true",
                            verify=client.verify_ssl)
                        if fr.status_code == 200:
                            full = fr.json()
                    except Exception:  # noqa: BLE001
                        pass
                return full, pk
        time.sleep(2)
    return None, None


def _check_expects(record: dict, expects: dict) -> list[str]:
    """Evaluate the expects: block against a final workflow record (with `steps[]`).
    Returns a list of failure strings (empty = all good)."""
    fails: list[str] = []
    want_status = expects.get("status", "finished")
    got_status = record.get("status")
    if got_status != want_status:
        fails.append(f"status: want {want_status!r}, got {got_status!r}")

    # vars: from the record's env (top-level vars FSR exposes to Jinja).
    want_vars = expects.get("vars") or {}
    if want_vars:
        env = record.get("env") or {}
        for k, expected in want_vars.items():
            if k not in env:
                fails.append(f"vars.{k}: missing (expected {expected!r})")
            elif env[k] != expected:
                fails.append(f"vars.{k}: want {expected!r}, got {env[k]!r}")

    # steps: per-step assertions keyed off step name with spaces→_.
    want_steps = expects.get("steps") or {}
    if want_steps:
        steps_arr = record.get("steps") or []
        by_name = {(s.get("name") or "").replace(" ", "_"): s for s in steps_arr}
        for sname, criteria in want_steps.items():
            s = by_name.get(sname)
            if s is None:
                fails.append(f"steps.{sname}: not present in run")
                continue
            if "status" in criteria and s.get("status") != criteria["status"]:
                fails.append(f"steps.{sname}.status: want {criteria['status']!r}, "
                             f"got {s.get('status')!r}")
            if "result_contains" in criteria:
                needle = criteria["result_contains"]
                hay = json.dumps(s.get("result") or {}, default=str)
                if needle not in hay:
                    fails.append(f"steps.{sname}.result: missing {needle!r}")
    return fails


def _store_db_path() -> Path:
    return Path(__file__).resolve().parents[2] / "store" / "fsr_reference.db"


def _default_log_root() -> Path:
    return Path(__file__).resolve().parents[2] / "store" / "e2e_runs"


def cleanup_all(client, patterns: list[str]) -> int:
    """Hard-delete any workflow_collections whose name matches a glob.
    Used by `fsrpb e2e cleanup`. Returns count purged."""
    import fnmatch
    listing = client.get("/api/3/workflow_collections",
                         params={"$limit": 200, "$showDeleted": "true"})
    members = listing.get("hydra:member") if isinstance(listing, dict) else []
    purged = 0
    for c in members:
        name = c.get("name") or ""
        if any(fnmatch.fnmatch(name, p) for p in patterns):
            uuid_ = c.get("uuid")
            wfs = c.get("workflows") or []
            wf_uuids = []
            for wf in wfs:
                if isinstance(wf, str):
                    wf_uuids.append(wf.rsplit("/", 1)[-1])
                elif isinstance(wf, dict) and wf.get("uuid"):
                    wf_uuids.append(wf["uuid"])
            try:
                client.session.delete(
                    client.base_url + "/api/3/delete/workflow_collections?$hardDelete=true",
                    json={"ids": [uuid_]}, verify=client.verify_ssl)
            except Exception:  # noqa: BLE001
                pass
            if wf_uuids:
                try:
                    client.session.delete(
                        client.base_url + "/api/3/delete/workflows?$hardDelete=true",
                        json={"ids": wf_uuids}, verify=client.verify_ssl)
                except Exception:  # noqa: BLE001
                    pass
            purged += 1
    return purged
