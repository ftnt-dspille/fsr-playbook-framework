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
      - kind: insert_record
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
from compiler import compile_yaml


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
    try:
        for i, step in enumerate(setup_steps):
            kind = step.get("kind")
            if kind != "insert_record":
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

    # 5. Trigger. Two modes: /notrigger (manual) or /action (record-context).
    rec_target = _render_templates(trigger_record, setup_ctx) if trigger_record else None
    if rec_target:
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
        trig_url = f"{client.base_url}/api/triggers/1/notrigger/{wf_uuid}"
        body = {"input": {}, "request": {"data": trigger_input or {}},
                "useMockOutput": False, "globalMock": False}
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

    # 6. Poll to terminal.
    if rec_target:
        final, pk = _poll_by_template(client, wf_uuid, trigger_started,
                                      timeout_s, log_dir, _log, run_id)
    else:
        final, pk = _poll(client, task_id, timeout_s, log_dir, _log, run_id)
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
                else:
                    failures.append(
                        f"record.{cap}: re-fetch failed HTTP {fr.status_code}")
    res.failures.extend(failures)

    # 8. Cleanup setup records, then collection.
    _flush_cleanup(client, cleanup_records, _log, run_id)
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
    """Hard-delete the collection and its workflows. Idempotent; failures swallowed."""
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


_PICKLIST_CACHE: dict[str, str] = {}  # "ListName:ItemValue" → "/api/3/picklists/<uuid>"


def _resolve_picklist(client, list_name: str, item_value: str) -> str | None:
    """Look up a picklist item by display name; return its IRI or None.

    Cached per process. `list_name` matches `listName.name` (e.g.
    'Severity', 'Status', 'Threat Type'). `item_value` matches
    `itemValue` (case-insensitive).
    """
    key = f"{list_name}:{item_value.lower()}"
    if key in _PICKLIST_CACHE:
        return _PICKLIST_CACHE[key]
    import urllib.parse
    qs = urllib.parse.urlencode({"listName.name": list_name, "$limit": 50})
    r = client.session.get(client.base_url + f"/api/3/picklists?{qs}",
                           verify=client.verify_ssl)
    if r.status_code != 200:
        return None
    for m in r.json().get("hydra:member") or []:
        if (m.get("itemValue") or "").lower() == item_value.lower():
            iri = f"/api/3/picklists/{m.get('uuid')}"
            _PICKLIST_CACHE[key] = iri
            return iri
    return None


# Per-module picklist field map. When a setup.fields entry's value is a
# bare string like "High" and the field is in this map, the runner
# resolves it to the picklist IRI before posting. Field-specific lookup
# is required because itemValues collide across lists (e.g., 'Closed'
# exists in both Status and Closure Reason).
_MODULE_PICKLIST_FIELDS: dict[str, dict[str, str]] = {
    "alerts":    {"severity": "Severity", "status": "Status",
                  "type": "Alert Type", "source": "Source",
                  "phase": "Investigation Phase",
                  "closureReason": "Closure Reason"},
    "incidents": {"severity": "Severity", "status": "Status",
                  "type": "Incident Type",
                  "phase": "Investigation Phase"},
    "indicators": {"severity": "Severity",
                   "type": "Threat Type",
                   "reputation": "Reputation"},
}


def _resolve_module_fields(client, module: str, fields: dict) -> dict:
    """Walk a setup.fields dict and resolve picklist names → IRIs.

    Only fields listed in _MODULE_PICKLIST_FIELDS for this module are
    candidates. Strings that already look like an IRI (start with
    '/api/3/') are passed through unchanged.
    """
    pmap = _MODULE_PICKLIST_FIELDS.get(module, {})
    out = {}
    for k, v in fields.items():
        if k in pmap and isinstance(v, str) and not v.startswith("/api/"):
            iri = _resolve_picklist(client, pmap[k], v)
            if iri:
                out[k] = iri
                continue
        out[k] = v
    return out


def _picklist_value(field):
    """When a re-fetched record field is a picklist dict, compare by
    itemValue or IRI; otherwise return the raw value."""
    if isinstance(field, dict):
        return field.get("itemValue") or field.get("@id") or field
    return field


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
                      timeout_s: int, log_dir: Path, log, run_id: str
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


def _poll(client, task_id: str, timeout_s: int, log_dir: Path,
          log, run_id: str) -> tuple[dict | None, str | None]:
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
