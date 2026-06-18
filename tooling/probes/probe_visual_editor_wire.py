"""Live-FSR verification of the four wire shapes the visual editor
emits. Run after any change to the inspector that touches:

  1. ``operator: changed``           — On-Update trigger predicate
  2. ``operator: in_all``            — multi-value membership (trigger-only)
  3. ``?$relationships=true``        — Find Record correlated toggle
  4. ``?$fsr_max_relation_count=N``  — Find Record correlated max

Items 1 and 2 are trigger-only operators (verified against the
trained corpus: 56 + 2 occurrences in `cybersponse.post_*` rows,
zero in FindRecords). FSR's ``/api/query/<module>`` endpoint
rejects them with 500 — that's by design, they only run inside the
trigger evaluator. So we verify them by **synthesising a one-step
playbook**, compiling it through the real resolver, and pushing
it via ``/api/integration/workflow_collections/`` — a 200 means
FSR's compiler accepts the operator.

Items 3 and 4 are ``GET /api/3/<module>`` URL params that are
trivially testable: a 200 response confirms the parser recognises
them.

Usage:
    python python/probes/probe_visual_editor_wire.py [--module alerts]
    python python/probes/probe_visual_editor_wire.py --skip-push   # URL checks only

Cleans up the test collection on success (or leaves it on failure
for inspection). Exits 0 when every check passes, 1 otherwise.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tooling"))

from probes._env import get_client  # noqa: E402

PROBE_COLLECTION = "_fsrpb_wire_probe"


# ── HTTP helpers ──────────────────────────────────────────────────────

def _get_with_params(client, module: str, params: str) -> tuple[int, dict | str]:
    url = f"{client.base_url}/api/3/{module}?{params}"
    r = client.session.get(url, verify=client.verify_ssl, timeout=30)
    try:
        return r.status_code, r.json() if r.text else {}
    except json.JSONDecodeError:
        return r.status_code, r.text[:300]


def _push_yaml(yaml_text: str) -> tuple[bool, str]:
    """Compile + push via the same path `fsrpb push` uses. Returns
    (ok, message). Side effects on the live FSR are reverted by the
    caller via ``_purge_collection``."""
    try:
        from fsr_playbooks.compiler import compile_yaml as _compile
        from probes._env import get_client as _get
        from e2e.runner import _push, _PushError
    except Exception as exc:
        return False, f"import failed: {exc!r}"
    db = ROOT / "data" / "fsr_reference.db"
    result = _compile(yaml_text, db)
    if not result.ok:
        msgs = "; ".join(f"{e.code.value}: {e.message}" for e in result.errors)
        return False, f"compile failed: {msgs}"
    coll = result.fsr_json["data"][0]
    client = _get()
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        try:
            _push(client, coll, Path(td))
        except _PushError as e:
            return False, f"push failed: {e}"
    return True, f"pushed collection {coll['name']!r}"


def _purge_collection(client, name: str) -> None:
    """Best-effort: find the collection by name, hard-delete it.
    Silent on errors — this is cleanup, not the test surface."""
    try:
        url = (f"{client.base_url}/api/3/workflow_collections"
               f"?name={name}&$limit=10")
        r = client.session.get(url, verify=client.verify_ssl, timeout=30)
        if r.status_code != 200:
            return
        for c in r.json().get("hydra:member", []):
            iri = c.get("@id")
            if iri:
                client.session.delete(client.base_url + iri,
                                      verify=client.verify_ssl, timeout=30)
    except Exception:  # noqa: BLE001 — cleanup best-effort
        pass


# ── Synthetic playbooks ───────────────────────────────────────────────

def _trigger_yaml(operator: str, field: str, value: str = "") -> str:
    """Tiny one-step trigger playbook: starts on update of alerts,
    fires when <field> matches the operator, runs a no-op set_variable.
    Uses the friendly authoring shape the compiler resolver expects
    (`collection:` is a string, steps key off `name:`, no `id:`).
    """
    val_line = f'              value: "{value}"\n' if value else ""
    return f"""
collection: "{PROBE_COLLECTION}"
description: "fsrpb visual-editor wire-shape probe"

playbooks:
  - name: "wire_probe_{operator}"
    description: "verifies the {operator} trigger operator round-trips"
    steps:
      - name: "On Update"
        type: start_on_update
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
              - field: "{field}"
                operator: "{operator}"
                type: primitive
{val_line}        next: "noop"
      - name: "noop"
        type: set_variable
        vars:
          ok: "{{{{ true }}}}"
""".lstrip()


# ── Checks ────────────────────────────────────────────────────────────

def check_url_param(client, module: str, params: str, descr: str) -> dict:
    code, data = _get_with_params(client, module, params)
    ok = code == 200
    return {
        "name": descr,
        "ok": ok,
        "status": str(code),
        "detail": (
            f"hydra:totalItems={data.get('hydra:totalItems')}"
            if ok and isinstance(data, dict)
            else f"body={data}"
        ),
    }


def check_trigger_operator(operator: str, field: str, value: str) -> dict:
    yaml_text = _trigger_yaml(operator, field, value)
    ok, msg = _push_yaml(yaml_text)
    return {
        "name": f"trigger operator={operator}",
        "ok": ok,
        "status": "push",
        "detail": msg,
    }


# ── Main ──────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--module", default="alerts",
                        help="module to probe URL params against (default: alerts)")
    parser.add_argument("--skip-push", action="store_true",
                        help="skip the trigger-operator push checks")
    args = parser.parse_args()

    client = get_client()
    if client is None:
        print("ERROR: no FSR client configured (check .env)")
        return 1

    print(f"Probing {client.base_url} on module={args.module!r}\n")

    checks: list[dict] = []

    if not args.skip_push:
        # Best-effort cleanup before we start in case a prior failed
        # run left the collection lying around.
        _purge_collection(client, PROBE_COLLECTION)

        # 1. `changed` — On-Update trigger fires when the field's
        # value differs from the prior write. No `value:` side.
        checks.append(check_trigger_operator("changed", "name", ""))

        # 2. `in_all` — multi-value membership. Use a known list-typed
        # field on alerts. Empty array stays valid syntactically.
        checks.append(check_trigger_operator("in_all", "tags", ""))

        # Cleanup pushed collection.
        _purge_collection(client, PROBE_COLLECTION)

    # 3. `?$relationships=true` — toggle for "Include correlated
    # records" on FindRecords. Inspector writes this into the
    # module URL.
    checks.append(check_url_param(client, args.module,
                                  "$limit=1&$relationships=true",
                                  "?$relationships=true"))

    # 4. `?$fsr_max_relation_count=N` — cap on correlated records.
    # Pair with $relationships=true since it's only meaningful when
    # relationships are expanded.
    checks.append(check_url_param(client, args.module,
                                  "$limit=1&$relationships=true&$fsr_max_relation_count=5",
                                  "?$fsr_max_relation_count=5"))

    width = max(len(c["name"]) for c in checks)
    failures = sum(1 for c in checks if not c["ok"])
    for c in checks:
        mark = "OK " if c["ok"] else "FAIL"
        print(f"  [{mark}] {c['name']:<{width}}  {c['status']:>5}  {c['detail']}")
    print()
    if failures:
        print(f"{failures}/{len(checks)} checks failed")
        return 1
    print(f"{len(checks)}/{len(checks)} wire shapes verified against live FSR")
    return 0


if __name__ == "__main__":
    sys.exit(main())
