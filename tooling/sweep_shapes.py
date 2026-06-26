"""Oracle-growing sweep: run the examples/*.test.yaml suite live and fold every
step's measured output shape into the grounded oracle (pilot gap D, task #7).

Reuses the e2e runner for all the trigger/record-setup/manual-resume/cleanup
machinery, then captures shapes from each run's wf_pk. Each example both
validates the analyzer (the run either matches expectations or surfaces a real
failure) and strengthens `fsr_playbooks/_data/grounded_shapes.json`.

Usage (source .env.205 first):
    PYTHONPATH=. python tooling/sweep_shapes.py            # all examples
    PYTHONPATH=. python tooling/sweep_shapes.py code_snippet record_create
"""
from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tooling"))

from fsr_playbooks.compiler.grounded_shapes import (  # noqa: E402
    GroundedShapeStore, shape_from_value,
)
from ground_shapes import _fetch_env_raw, _step_connector_op  # noqa: E402
from e2e.runner import run_test  # noqa: E402

STORE_PATH = REPO / "fsr_playbooks" / "_data" / "grounded_shapes.json"
EXAMPLES = REPO / "examples"


def main(argv: list[str]) -> int:
    specs = sorted(EXAMPLES.glob("*.test.yaml"))
    if argv:
        specs = [s for s in specs if any(a in s.name for a in argv)]
    if not specs:
        print("no matching .test.yaml"); return 1

    store = GroundedShapeStore.load(STORE_PATH)
    before = len(store)
    summary: list[dict] = []

    for spec in specs:
        name = spec.stem.replace(".test", "")
        print(f"\n{'='*60}\n▶ {name}")
        # keep=True so cleanup never races the shape capture.
        try:
            res = run_test(spec, keep=True, verbose=False)
        except Exception as e:  # noqa: BLE001
            print(f"  runner raised: {e!r}")
            summary.append({"example": name, "status": "runner_error"})
            continue
        print(f"  run: ok={res.ok} status={res.status} wf_pk={res.wf_pk}"
              + (f"  failures={res.failures}" if res.failures else ""))
        if not res.wf_pk:
            summary.append({"example": name, "status": res.status or "no_pk",
                            "ok": res.ok})
            continue

        # Correlate step → connector/op from the fixture YAML.
        fixture = _load_spec(spec)
        fix_path = (REPO / fixture["fixture"]).resolve()
        if not fix_path.exists():
            fix_path = (spec.parent / Path(fixture["fixture"]).name).resolve()
        step_map = _step_connector_op(fix_path.read_text())

        env = _fetch_env_raw(res.wf_pk)
        if env.get("error"):
            print(f"  env: {env['error']}")
            summary.append({"example": name, "status": res.status,
                            "ok": res.ok, "env": "unavailable"})
            continue
        steps = (env.get("vars") or {}).get("steps") or {}
        observed = []
        for sname, result in steps.items():
            meta = step_map.get(sname)
            shape = shape_from_value(result)
            if meta and meta[1] and meta[2]:
                store.observe(meta[1], meta[2], result)
                observed.append(f"{meta[1]}:{meta[2]}")
            print(f"   • {sname} ({meta[0] if meta else '?'}): "
                  f"{json.dumps(shape)[:120]}")
        summary.append({"example": name, "status": env.get("status"),
                        "ok": res.ok, "ops": sorted(set(observed))})

    store.save(STORE_PATH)
    print(f"\n{'='*60}\nORACLE: {before} → {len(store)} op-shapes  ({STORE_PATH})")
    print("ops:", ", ".join(sorted(store.as_dict().keys())))
    print("\n=== sweep summary ===")
    for row in summary:
        print(" ", json.dumps(row))
    return 0


def _load_spec(spec_path: Path) -> dict:
    import yaml
    return yaml.safe_load(spec_path.read_text()) or {}


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
