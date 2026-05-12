"""Round-trip integration probe for the visual editor's authoring
surface. For each scenario:

  1. Synthesise a YAML playbook that exercises a specific feature
     (multi-trigger, On-Create with nested filters, On-Update with
     `changed`, Find Record with $relationships URL params, …).
  2. Compile it via the real resolver and push to the live FSR.
  3. Pull the pushed collection back as canonical JSON.
  4. Walk the JSON and assert the structural claims survive the
     round-trip (operator tokens, URL params, branch labels,
     trigger field paths …).

This is the test that catches resolver/emitter drift end-to-end —
unit tests on either side miss bugs that only show up when FSR
re-canonicalises what we sent.

Usage:
    python python/probes/probe_round_trip.py
    python python/probes/probe_round_trip.py --keep   # leave probe collection on FSR
"""
from __future__ import annotations

import argparse
import json
import sys
import textwrap
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from probes._env import get_client  # noqa: E402

# Each scenario uses its own unique collection name so the resolver's
# deterministic uuid5 (keyed on collection name) never collides with
# a previous run's leftover record. FSR keeps deleted UUIDs reserved
# in a recycle layer that doesn't expose a clear API path on this
# version, so re-using collection names triggers spurious 409s on
# every push after the first.
PROBE_COLLECTION_PREFIX = "_fsrpb_rt_"
DB = ROOT / "store" / "fsr_reference.db"


# ── HTTP / push helpers ───────────────────────────────────────────────

def _push_yaml(yaml_text: str) -> tuple[bool, str]:
    """Compile + push via the same path `fsrpb push` uses."""
    try:
        from compiler import compile_yaml as _compile
        from probes._env import get_client as _get
        from e2e.runner import _push, _PushError
    except Exception as exc:
        return False, f"import failed: {exc!r}"
    result = _compile(yaml_text, DB)
    if not result.ok:
        msgs = "; ".join(f"{e.code.value}: {e.message}" for e in result.errors)
        return False, f"compile: {msgs}"
    coll = result.fsr_json["data"][0]
    client = _get()
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        try:
            _push(client, coll, Path(td))
        except _PushError as e:
            return False, f"push: {e}"
    return True, f"pushed"


def _pull_collection(client, name: str) -> dict | None:
    """Return the freshly-pushed probe collection from FSR with all
    its workflows + steps inlined ($relationships=true expands the
    nested objects), or None when not found.
    """
    url = (f"{client.base_url}/api/3/workflow_collections"
           f"?name={name}&$limit=1&$relationships=true")
    r = client.session.get(url, verify=client.verify_ssl, timeout=30)
    if r.status_code != 200:
        return None
    members = r.json().get("hydra:member", [])
    if not members:
        return None
    coll = members[0]
    # Workflows come back as IRIs by default; expand each so the
    # assertion helpers can read steps + arguments inline.
    expanded = []
    for wf in coll.get("workflows", []):
        if isinstance(wf, str):
            wr = client.session.get(
                client.base_url + wf + "?$relationships=true",
                verify=client.verify_ssl, timeout=30,
            )
            if wr.status_code == 200:
                expanded.append(wr.json())
        elif isinstance(wf, dict):
            expanded.append(wf)
    coll["workflows"] = expanded
    return coll


def _purge(client, name: str = PROBE_COLLECTION_PREFIX) -> None:
    """Best-effort cleanup. `name` is matched as a prefix when the
    URL filter supports it, else as an exact match.
    """
    """Hard-delete the probe collection AND every probe workflow.

    Soft-deleting just the collection leaves the workflows orphaned;
    the next scenario's POST then 409s on workflow UUID uniqueness
    (resolver emits deterministic uuid5 from playbook name). Wipe by
    name pattern (`rt_*`) so we cover every scenario's workflows in
    one shot.
    """
    try:
        # 1. Find + hard-delete the collection.
        r = client.session.get(
            f"{client.base_url}/api/3/workflow_collections"
            f"?name={name}&$limit=10",
            verify=client.verify_ssl, timeout=30,
        )
        coll_uuids: list[str] = []
        if r.status_code == 200:
            for c in r.json().get("hydra:member", []):
                if c.get("uuid"):
                    coll_uuids.append(c["uuid"])
        if coll_uuids:
            client.session.delete(
                f"{client.base_url}/api/3/delete/workflow_collections"
                f"?$hardDelete=true",
                json={"ids": coll_uuids},
                verify=client.verify_ssl, timeout=30,
            )

        # 2. Find + hard-delete any orphan probe workflows. Resolver
        # produces deterministic UUIDs from playbook name, so an
        # orphaned workflow blocks the next push.
        for prefix in ("rt_",):
            wr = client.session.get(
                f"{client.base_url}/api/3/workflows"
                f"?name${{startswith}}={prefix}&$limit=50",
                verify=client.verify_ssl, timeout=30,
            )
            if wr.status_code != 200:
                # Server filter rejected; fetch all and match client-side.
                wr = client.session.get(
                    f"{client.base_url}/api/3/workflows?$limit=200",
                    verify=client.verify_ssl, timeout=30,
                )
                if wr.status_code != 200:
                    continue
            # CRITICAL: ALWAYS filter client-side on the prefix, even on
            # the 200 path. FSR silently ignores unknown query filters
            # and returns ALL workflows - trusting the server-side filter
            # caused a mass-delete on 2026-05-08 (every workflow on the
            # appliance was hard-deleted because rt_-prefix filter was
            # ignored). NEVER hard-delete based on an unverified filter.
            wfs = [w for w in wr.json().get("hydra:member", [])
                   if isinstance(w.get("name"), str)
                   and w["name"].startswith(prefix)]
            wf_uuids = [w["uuid"] for w in wfs if w.get("uuid")]
            if wf_uuids:
                client.session.delete(
                    f"{client.base_url}/api/3/delete/workflows"
                    f"?$hardDelete=true",
                    json={"ids": wf_uuids},
                    verify=client.verify_ssl, timeout=30,
                )
    except Exception:  # noqa: BLE001 — cleanup best-effort
        pass


# ── Walking helpers ───────────────────────────────────────────────────

def workflow_by_name(coll: dict, name: str) -> dict | None:
    for wf in coll.get("workflows", []):
        if isinstance(wf, dict) and wf.get("name") == name:
            return wf
    return None


def step_by_type(wf: dict, step_type_uuid_or_name: str) -> dict | None:
    """Find the first step in the workflow whose stepType matches
    either the literal UUID or the resolved name (e.g. 'Decision')."""
    for st in wf.get("steps", []):
        if not isinstance(st, dict):
            continue
        stype = st.get("stepType")
        if isinstance(stype, dict):
            if (stype.get("name") == step_type_uuid_or_name
                or stype.get("uuid") == step_type_uuid_or_name):
                return st
        elif isinstance(stype, str):
            # IRI form: /api/3/workflow_step_types/<uuid>
            if step_type_uuid_or_name in stype:
                return st
    return None


def first_filter_leaf(args: dict, key: str = "fieldbasedtrigger") -> dict | None:
    """Return the first leaf in the filter tree under `key`, walking
    into nested groups depth-first."""
    block = args.get(key) if isinstance(args, dict) else None
    if not isinstance(block, dict):
        return None
    def walk(g: dict) -> dict | None:
        for f in g.get("filters") or []:
            if not isinstance(f, dict):
                continue
            if "logic" in f and "filters" in f:
                inner = walk(f)
                if inner:
                    return inner
            elif f.get("operator"):
                return f
        return None
    return walk(block)


# ── Scenarios ─────────────────────────────────────────────────────────

# Each scenario is a tuple (name, yaml, [(claim_label, fn(coll) -> ok|str)]).
# `fn` returns True on pass, or a string explaining the failure.

def _yaml_two_triggers(coll: str) -> str:
    return textwrap.dedent(f"""\
        collection: "{coll}"
        description: "round-trip probe — two trigger options"
        playbooks:
          - name: "rt_two_triggers"
            description: "manual + on-create both route to one set_variable"
            steps:
              - name: "Manual Start"
                type: start
                next: "Note It"
              - name: "On New Alert"
                type: start_on_create
                arguments:
                  resource: alerts
                  resources: [alerts]
                  triggerOnSource: true
                next: "Note It"
              - name: "Note It"
                type: set_variable
                vars:
                  fired: "{{{{ true }}}}"
        """)


def _check_two_triggers(coll: dict) -> bool | str:
    """This scenario verifies a *negative* claim: the compiler must
    reject the two-trigger playbook (FSR allows exactly one trigger
    per workflow). The scenario harness inverts: a successful push
    here is a regression — we WANT the compile_failure path."""
    wf = workflow_by_name(coll, "rt_two_triggers")
    if wf is not None:
        return "two-trigger playbook unexpectedly pushed; FSR allows only one"
    return True


def _yaml_on_create_nested_filter(coll: str) -> str:
    return textwrap.dedent(f"""\
        collection: "{coll}"
        description: "round-trip probe — on-create with nested AND/OR"
        playbooks:
          - name: "rt_on_create_nested"
            description: "fires on alerts where severity is high OR critical AND escalated is not yes"
            steps:
              - name: "On New Alert"
                type: start_on_create
                arguments:
                  resource: alerts
                  resources: [alerts]
                  triggerOnSource: true
                  fieldbasedtrigger:
                    logic: AND
                    limit: 30
                    sort: []
                    filters:
                      - logic: OR
                        filters:
                          - field: severity
                            operator: eq
                            type: primitive
                            value: "high"
                          - field: severity
                            operator: eq
                            type: primitive
                            value: "critical"
                      - field: name
                        operator: like
                        type: primitive
                        value: "%phish%"
                next: "Note It"
              - name: "Note It"
                type: set_variable
                vars:
                  fired: "{{{{ true }}}}"
        """)


def _check_on_create_nested(coll: dict) -> bool | str:
    wf = workflow_by_name(coll, "rt_on_create_nested")
    if wf is None:
        return "workflow not found"
    # Find the trigger step. FSR's stepType.name varies by version;
    # we look for the one that has `fieldbasedtrigger` in its args.
    trig = None
    for st in wf.get("steps", []):
        a = st.get("arguments") or {}
        if isinstance(a, dict) and "fieldbasedtrigger" in a:
            trig = st
            break
    if trig is None:
        return "no trigger step with fieldbasedtrigger"
    fbt = trig["arguments"]["fieldbasedtrigger"]
    if fbt.get("logic") != "AND":
        return f"top-level logic={fbt.get('logic')} (want AND)"
    has_or = any(isinstance(f, dict) and f.get("logic") == "OR"
                 for f in fbt.get("filters") or [])
    if not has_or:
        return "no nested OR group"
    leaf = first_filter_leaf(trig["arguments"])
    if leaf is None:
        return "no leaf filter"
    if leaf.get("operator") != "eq":
        return f"first leaf operator={leaf.get('operator')}"
    return True


def _yaml_on_update_changed(coll: str) -> str:
    return textwrap.dedent(f"""\
        collection: "{coll}"
        description: "round-trip probe — on-update with `changed` operator"
        playbooks:
          - name: "rt_on_update_changed"
            description: "fires when an alert's status field changes"
            steps:
              - name: "On Status Change"
                type: start_on_update
                arguments:
                  resource: alerts
                  resources: [alerts]
                  triggerOnSource: true
                  fieldbasedtrigger:
                    logic: AND
                    limit: 30
                    sort: []
                    filters:
                      - field: status
                        operator: changed
                        type: primitive
                next: "Note It"
              - name: "Note It"
                type: set_variable
                vars:
                  fired: "{{{{ true }}}}"
        """)


def _check_changed_operator(coll: dict) -> bool | str:
    wf = workflow_by_name(coll, "rt_on_update_changed")
    if wf is None:
        return "workflow not found"
    leaf = None
    for st in wf.get("steps", []):
        if "fieldbasedtrigger" in (st.get("arguments") or {}):
            leaf = first_filter_leaf(st["arguments"])
            break
    if leaf is None:
        return "no trigger leaf"
    if leaf.get("operator") != "changed":
        return f"operator={leaf.get('operator')!r} (expected 'changed')"
    if leaf.get("field") != "status":
        return f"field={leaf.get('field')!r} (expected 'status')"
    return True


def _yaml_find_record_correlated(coll: str) -> str:
    return textwrap.dedent(f"""\
        collection: "{coll}"
        description: "round-trip probe — find_record with $relationships URL params"
        playbooks:
          - name: "rt_find_correlated"
            description: "find alerts with correlated records, capped at 5"
            steps:
              - name: "Manual"
                type: start
                next: "Find Alerts"
              - name: "Find Alerts"
                type: find_record
                arguments:
                  module: "alerts?$limit=10&$relationships=true&$fsr_max_relation_count=5"
                  query:
                    logic: AND
                    limit: 10
                    sort: []
                    filters:
                      - field: severity
                        operator: eq
                        type: primitive
                        value: "high"
        """)


def _check_find_correlated(coll: dict) -> bool | str:
    wf = workflow_by_name(coll, "rt_find_correlated")
    if wf is None:
        return "workflow not found"
    find_step = None
    for st in wf.get("steps", []):
        a = st.get("arguments") or {}
        if isinstance(a, dict) and isinstance(a.get("module"), str) \
                and a["module"].startswith("alerts"):
            find_step = st
            break
    if find_step is None:
        return "no find_record step with module=alerts*"
    mod = find_step["arguments"]["module"]
    if "$relationships=true" not in mod:
        return f"$relationships=true missing from module URL: {mod!r}"
    if "$fsr_max_relation_count=5" not in mod:
        return f"$fsr_max_relation_count=5 missing from module URL: {mod!r}"
    return True


def _yaml_decision_branches(coll: str) -> str:
    return textwrap.dedent(f"""\
        collection: "{coll}"
        description: "round-trip probe — decision with 3 conditions + default"
        playbooks:
          - name: "rt_decision_three_way"
            description: "high → escalate; medium → ack; default → log"
            steps:
              - name: "Manual"
                type: start
                next: "Branch"
              - name: "Branch"
                type: decision
                conditions:
                  - display: high
                    when: "{{{{ vars.input.records[0].severity == 'high' }}}}"
                    next: "Escalate"
                  - display: medium
                    when: "{{{{ vars.input.records[0].severity == 'medium' }}}}"
                    next: "Ack"
                  - display: Else
                    default: true
                    next: "Log"
              - name: "Escalate"
                type: set_variable
                vars: {{ branch: "esc" }}
              - name: "Ack"
                type: set_variable
                vars: {{ branch: "ack" }}
              - name: "Log"
                type: set_variable
                vars: {{ branch: "log" }}
        """)


def _yaml_on_create_fires(coll: str, marker: str) -> str:
    """Fires when a record is created with `name == <marker>`. The
    playbook's only step after the trigger sets a vars value, which
    we don't actually need to read — we just want to confirm the run
    transitioned to `finished` (i.e. the trigger fired AND completed).
    """
    return textwrap.dedent(f"""\
        collection: "{coll}"
        description: "round-trip probe — on_create fires + completes"
        playbooks:
          - name: "rt_on_create_fires"
            description: "fires on alerts where name matches the marker"
            is_active: true
            steps:
              - name: "On New Alert"
                type: start_on_create
                arguments:
                  resource: alerts
                  resources: [alerts]
                  triggerOnSource: true
                  triggerOnReplicate: false
                  fieldbasedtrigger:
                    logic: AND
                    limit: 30
                    sort: []
                    filters:
                      - field: name
                        operator: eq
                        type: primitive
                        value: "{marker}"
                next: "Note It"
              - name: "Note It"
                type: set_variable
                vars:
                  fired: "{{{{ true }}}}"
        """)


def _fire_and_check(client, coll_name: str, marker: str,
                    timeout_s: int = 60) -> bool | str:
    """End-to-end fire test:
    1. Push the on-create playbook (already done by run_one).
    2. Find the workflow's IRI so we can scope the run-poll query.
    3. POST a fresh alert with `name == marker` to fire the trigger.
    4. Poll `/api/wf/api/workflows/?template_iri=<wf>` for a terminal
       run that started after our POST.
    5. Clean up the test record.

    Returns True on success or a string explaining the failure.
    """
    import time

    # 2. Find the workflow IRI by scanning the just-pushed collection.
    coll = _pull_collection(client, coll_name)
    if coll is None:
        return "collection not found after push"
    wf = workflow_by_name(coll, "rt_on_create_fires")
    if wf is None:
        return "workflow not found"
    wf_iri = wf.get("@id")
    if not wf_iri:
        return "workflow has no @id"

    # 3. Create a record that matches the trigger filter.
    fire_t0 = time.time()
    create_url = f"{client.base_url}/api/3/alerts"
    body = {"name": marker, "description": "fsrpb round-trip probe"}
    cr = client.session.post(create_url, json=body, verify=client.verify_ssl,
                             timeout=30)
    if cr.status_code not in (200, 201):
        return f"alert create failed: HTTP {cr.status_code} {cr.text[:200]}"
    record_iri = (cr.json() or {}).get("@id")

    try:
        # 4. Poll for a workflow run instance scoped to this template
        # IRI. The runner polls by task_id for /notrigger flows, but
        # event-driven on-create triggers don't issue a task_id —
        # FSR's internal subscriber spawns the run, and we have to
        # query by `template_iri` (the workflow IRI itself).
        poll_url = (
            f"{client.base_url}/api/wf/api/workflows/"
            f"?format=json&limit=1&offset=0&ordering=-modified"
            f"&template_iri={wf_iri}&parent_wf__isnull=True"
        )
        deadline = time.time() + timeout_s
        seen_status: str | None = None
        while time.time() < deadline:
            r = client.session.get(poll_url, verify=client.verify_ssl, timeout=15)
            if r.status_code == 200:
                members = r.json().get("hydra:member") or []
                if members:
                    rec = members[0]
                    status = rec.get("status", "unknown")
                    seen_status = status
                    # Confirm this run actually started after we
                    # posted the record — otherwise an old run from
                    # a previous probe could short-circuit the check.
                    started = rec.get("started") or rec.get("created") or 0
                    if status in {"finished", "failed", "terminated", "skipped",
                                  "finished_with_error", "rejected"}:
                        if status == "finished":
                            return True
                        return f"workflow run terminated as {status!r}"
            time.sleep(2)
        return (f"timed out after {timeout_s}s; last status={seen_status!r}"
                f" (trigger may not have fired)")
    finally:
        # 5. Clean up the test record so we don't pollute the alerts
        # module. Best-effort.
        if record_iri:
            try:
                client.session.delete(client.base_url + record_iri,
                                      verify=client.verify_ssl, timeout=15)
            except Exception:
                pass


def _check_decision_branches(coll: dict) -> bool | str:
    wf = workflow_by_name(coll, "rt_decision_three_way")
    if wf is None:
        return "workflow not found"
    decision = None
    for st in wf.get("steps", []):
        if "conditions" in (st.get("arguments") or {}):
            decision = st
            break
    if decision is None:
        return "no decision step"
    conds = decision["arguments"]["conditions"]
    if len(conds) != 3:
        return f"expected 3 conditions, got {len(conds)}"
    defaults = sum(1 for c in conds if c.get("default") is True)
    if defaults != 1:
        return f"expected exactly 1 default, got {defaults}"
    return True


# Tuple shape: (name, yaml_fn, check_fn, expect_compile_failure?)
# `expect_compile_failure=True` means the scenario passes when the
# compiler rejects the YAML — used for negative tests where we're
# asserting the resolver's guards work.
SCENARIOS = [
    ("two_triggers", _yaml_two_triggers, _check_two_triggers, True),
    ("on_create_nested_filter", _yaml_on_create_nested_filter,
     _check_on_create_nested, False),
    ("on_update_changed", _yaml_on_update_changed,
     _check_changed_operator, False),
    ("find_record_correlated", _yaml_find_record_correlated,
     _check_find_correlated, False),
    ("decision_three_way", _yaml_decision_branches,
     _check_decision_branches, False),
]

# Live-fire scenarios: push + actually trigger + verify the run hit
# `finished` state. Slower (60s timeout per) and produces real records
# on the live FSR — kept separate from the structural-only SCENARIOS
# above so a quick run can skip them.
LIVE_FIRE_SCENARIOS = [
    ("on_create_fires_and_completes",
     _yaml_on_create_fires,
     _fire_and_check),
]


# ── Main ──────────────────────────────────────────────────────────────

def run_one(client, name: str,
            yaml_fn: Callable[[str], str],
            check_fn: Callable[[dict], Any],
            expect_compile_failure: bool = False) -> dict:
    coll_name = f"{PROBE_COLLECTION_PREFIX}{name}"
    yaml_text = yaml_fn(coll_name)
    pushed, msg = _push_yaml(yaml_text)
    if expect_compile_failure:
        # Negative test: a clean push means the compiler missed a
        # rule we know FSR enforces.
        if pushed:
            return {"name": name, "ok": False, "stage": "negative",
                    "detail": "expected compile failure but push succeeded"}
        if msg.startswith("compile:"):
            return {"name": name, "ok": True, "stage": "negative",
                    "detail": f"compiler correctly rejected: {msg[9:80]}…"}
        return {"name": name, "ok": False, "stage": "negative",
                "detail": f"expected compile rejection, got: {msg}"}

    if not pushed:
        return {"name": name, "ok": False, "stage": "push", "detail": msg}
    coll = _pull_collection(client, coll_name)
    if coll is None:
        return {"name": name, "ok": False, "stage": "pull",
                "detail": "collection not found after push"}
    verdict = check_fn(coll)
    if verdict is True:
        return {"name": name, "ok": True, "stage": "check",
                "detail": "structural claims survived round-trip"}
    return {"name": name, "ok": False, "stage": "check", "detail": str(verdict)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keep", action="store_true",
                        help="leave the probe collection on FSR after the run")
    parser.add_argument("--only", nargs="*", default=None,
                        help="run only the named scenario(s)")
    parser.add_argument("--no-fire", action="store_true",
                        help="skip the live-fire scenarios (faster, no records created)")
    args = parser.parse_args()

    client = get_client()
    if client is None:
        print("ERROR: no FSR client configured (check .env)")
        return 1

    print(f"Round-tripping against {client.base_url}\n")

    results: list[dict] = []
    # One up-front purge — each scenario uses its own unique collection
    # name (`PROBE_COLLECTION_PREFIX + scenario`), so per-scenario
    # purging isn't needed during the run; we only have to clear any
    # leftovers from a prior interrupted run before we start.
    for name, _, _, _ in SCENARIOS:
        _purge(client, f"{PROBE_COLLECTION_PREFIX}{name}")

    for name, yaml_fn, check_fn, expect_fail in SCENARIOS:
        if args.only and name not in args.only:
            continue
        results.append(run_one(client, name, yaml_fn, check_fn, expect_fail))

    if not args.no_fire:
        import secrets
        for name, yaml_fn, fire_fn in LIVE_FIRE_SCENARIOS:
            if args.only and name not in args.only:
                continue
            coll_name = f"{PROBE_COLLECTION_PREFIX}{name}"
            _purge(client, coll_name)
            # Generate a per-run marker so two runs on the same FSR
            # don't fire each other's playbooks. 8 hex bytes (16
            # chars) is well below FSR's name length cap.
            marker = f"fsrpb-rt-{secrets.token_hex(8)}"
            yaml_text = yaml_fn(coll_name, marker)
            pushed, msg = _push_yaml(yaml_text)
            if not pushed:
                results.append({"name": name, "ok": False, "stage": "push",
                                "detail": msg})
                continue
            verdict = fire_fn(client, coll_name, marker)
            if verdict is True:
                results.append({"name": name, "ok": True, "stage": "fire",
                                "detail": "trigger fired and run finished cleanly"})
            else:
                results.append({"name": name, "ok": False, "stage": "fire",
                                "detail": str(verdict)})

    if not args.keep:
        for name, _, _, _ in SCENARIOS:
            _purge(client, f"{PROBE_COLLECTION_PREFIX}{name}")
        for name, _, _ in LIVE_FIRE_SCENARIOS:
            _purge(client, f"{PROBE_COLLECTION_PREFIX}{name}")

    width = max(len(r["name"]) for r in results) if results else 10
    failures = sum(1 for r in results if not r["ok"])
    for r in results:
        mark = "OK " if r["ok"] else "FAIL"
        print(f"  [{mark}] {r['name']:<{width}}  ({r['stage']}) {r['detail']}")
    print()
    if failures:
        print(f"{failures}/{len(results)} scenarios failed")
        return 1
    print(f"{len(results)}/{len(results)} scenarios round-tripped cleanly")
    return 0


if __name__ == "__main__":
    sys.exit(main())
