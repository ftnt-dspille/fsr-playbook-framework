"""Live capture → grounded output-shape oracle (pilot gap D).

Pushes a playbook to the live FSR, triggers it, pulls the run env (per-step
results), measures each step's output shape, and folds it into the persistent
GroundedShapeStore. Also dumps the raw env so we can ground data-presence and
namespace (E5/E6) facts against what the box ACTUALLY produced — not inference.

Usage (source .env.205 first):
    PYTHONPATH=tooling:fsr_playbooks python -m ground_shapes examples/demo_code_snippet.yaml \
        --playbook "FSRPB Demo - Code Snippet" --input first_name=Dylan

Run id mode (capture an already-finished run by pk/task_id):
    PYTHONPATH=tooling:fsr_playbooks python -m ground_shapes --pk 676747
"""
from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

REPO = Path(__file__).resolve().parent.parent
STORE_PATH = REPO / "fsr_playbooks" / "_data" / "grounded_shapes.json"

sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tooling"))

from fsr_playbooks.compiler.grounded_shapes import (  # noqa: E402
    GroundedShapeStore, shape_from_value,
)


def _fetch_env_raw(pk: str) -> dict:
    """Fetch a run's env + per-step results via the raw wf-api endpoint.

    Robust replacement for tools_connector_discovery.get_run_env, which calls
    `client.playbooks.get_execution` — absent on the installed pyfsr version.
    Mirrors the same shape: {status, name, vars:{...env, steps:{name_→result}}}.
    """
    from probes._env import get_client
    cl = get_client()
    data = None
    for ep in (f"/api/wf/api/workflows/{pk}/?step_detail=true&format=json",
               f"/api/wf/api/historical-workflows/{pk}/?step_detail=true&format=json"):
        try:
            r = cl.session.get(cl.base_url.rstrip("/") + ep,
                               verify=cl.verify_ssl, timeout=30)
        except Exception as e:  # noqa: BLE001
            continue
        if r.status_code == 200:
            d = r.json()
            if isinstance(d, dict) and (d.get("steps") or d.get("env")):
                data = d
                break
    if data is None:
        return {"error": f"could not fetch run {pk} (wf-api may be 503/purged)"}
    env_obj = data.get("env") or {}
    steps_map = {}
    for s in (data.get("steps") or []):
        name = s.get("name")
        if isinstance(name, str):
            steps_map[name.replace(" ", "_")] = s.get("result") or {}
    return {"status": data.get("status"), "name": data.get("name"),
            "vars": dict(env_obj, steps=steps_map)}


def _step_connector_op(src_yaml: str) -> dict[str, tuple[str, str, str]]:
    """Map a step's env key (name, spaces→_) → (type, connector, op) from YAML.

    code_snippet steps resolve to the code-snippet connector/op so their
    measured shape keys the oracle by the same (connector, op) the walker probes.
    """
    import yaml as _yaml
    doc = _yaml.safe_load(src_yaml) or {}
    out: dict[str, tuple[str, str, str]] = {}
    for pb in (doc.get("playbooks") or []):
        for s in (pb.get("steps") or []):
            name = (s.get("name") or s.get("id") or "").replace(" ", "_")
            stype = s.get("type") or ""
            args = s.get("arguments") or {}
            if stype == "code_snippet":
                conn, op = "code-snippet", "python_inline_code_editor"
            else:
                conn = args.get("connector") or stype
                op = args.get("operation") or ""
            out[name] = (stype, conn, op)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("yaml", nargs="?", help="playbook YAML to push+run")
    ap.add_argument("--playbook", help="workflow name to trigger")
    ap.add_argument("--input", action="append", default=[],
                    help="trigger param k=v (repeatable)")
    ap.add_argument("--pk", help="capture an already-finished run by pk/task_id")
    ap.add_argument("--no-store", action="store_true",
                    help="don't write the shape store (dry capture)")
    args = ap.parse_args()

    from fsr_playbooks.mcp_server import tools_execution as te

    src_yaml = ""
    step_map: dict = {}
    if args.yaml:
        src_yaml = Path(args.yaml).read_text()
        step_map = _step_connector_op(src_yaml)
    if args.pk:
        pk = args.pk
    else:
        if not args.yaml or not args.playbook:
            ap.error("provide YAML + --playbook, or --pk")
        print(f"→ pushing {args.playbook!r} …")
        pushed = te.push_playbook(src_yaml)
        if not pushed.get("ok", True) and pushed.get("error"):
            print("  push error:", pushed.get("error")); return 1
        inp = dict(kv.split("=", 1) for kv in args.input)
        print(f"→ triggering with input={inp} …")
        run = te.run_playbook(args.playbook, input=inp, follow=True, timeout_s=120)
        print("  run:", {k: run.get(k) for k in ("ok", "status", "wf_pk", "task_id", "error_message")})
        pk = str(run.get("wf_pk") or run.get("task_id") or "")
        if not pk:
            print("  no run id returned"); return 1

    print(f"→ pulling run env for {pk} …")
    env = _fetch_env_raw(pk)
    if env.get("error"):
        print("  env error:", env["error"]); return 1
    steps = (env.get("vars") or {}).get("steps") or {}
    top_vars = {k: v for k, v in (env.get("vars") or {}).items() if k != "steps"}
    print(f"  status={env.get('status')}  steps={list(steps)}")
    print("  top-level env keys (NON-steps):", sorted(top_vars))
    # Surface the input namespace ground truth (E6): what's actually populated.
    for k in ("input", "inputs"):
        if k in top_vars:
            print(f"  env[{k}] =", json.dumps(top_vars[k])[:200])

    store = GroundedShapeStore.load(STORE_PATH)
    print("\n=== measured per-step output shapes ===")
    for sname, result in steps.items():
        shape = shape_from_value(result)
        meta = step_map.get(sname)
        print(f"\n• {sname}  ({meta[0] if meta else '?'})")
        print("  raw result:", json.dumps(result)[:300])
        print("  shape:", json.dumps(shape)[:300])
        if meta and meta[1] and meta[2]:
            merged = store.observe(meta[1], meta[2], result)
            print(f"  → oracle[{meta[1]}:{meta[2]}] := {json.dumps(merged)[:200]}")

    if not args.no_store:
        store.save(STORE_PATH)
        print(f"\n✓ stored {len(store)} grounded op-shapes → {STORE_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
