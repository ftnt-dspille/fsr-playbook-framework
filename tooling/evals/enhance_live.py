"""Live enhance-DELIVERY gate — the box-touching sibling of the offline
`tooling/tests/test_evals_enhance_delivery.py`.

Drives every `enhance_scenarios/*.json` through the deployed connector's real
chat_turn, mounting `before_yaml` as `entity.playbook_yaml` exactly as the
shipped widget does, and grades with `score_enhance_delivery`: did the edit
reach the open playbook via `emit_enhancement_offer`, or did the agent print
YAML at the analyst? This is the behaviour that failed live (the model narrating
"call emit_enhancement_offer …" instead of calling it) and that the
EnhanceDeliveryGuard now forces structurally — so this runner is the regression
gate that keeps it forced.

Needs `.env` FSR creds + a reachable, deployed connector (costs credits).

    python tooling/evals/enhance_live.py [--only e3] [--runs 5]
                                         [--config NAME] [--version X.Y.Z]

`--config ""` (default) lets the connector pick its default config — the
analyst's real surface. Exit 0 iff every GRADED (non-skipped) run delivered.
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCEN_DIR = Path(__file__).resolve().parent / "enhance_scenarios"
# Make `from evals.* import …` / `from probes import _env` resolve when run as a
# script, same as chat_drive's __main__ does.
sys.path.insert(0, str(REPO_ROOT / "tooling"))

from evals.chat_drive import drive_scenario  # noqa: E402
from evals.scoring import score_enhance_delivery  # noqa: E402


def _rich_trace(transcript: list) -> list[dict]:
    """[{name, args, result, ok}] with tool RESULTS threaded onto their calls.

    `transcript_to_trace` (chat_drive) keeps only ok/refused, dropping the
    payload — but `score_enhance_delivery` reads `verify_enhancement`'s
    `ready_to_push`/`verified_id` from the result to tell a stalled delivery
    (FAIL) from a correctly-declined one (PASS). Without the payload it degrades
    to a false PASS on exactly the regression this gate exists to catch, so pair
    each tool_result onto its tool_use by id here and keep the result dict.
    """
    trace, by_id = [], {}
    for e in transcript or []:
        if not isinstance(e, dict):
            continue
        if e.get("type") in ("tool_use", "tool_call"):
            entry = {"name": e.get("name") or "",
                     "args": e.get("input") or e.get("arguments") or {},
                     "result": None, "ok": None}
            trace.append(entry)
            if e.get("id"):
                by_id[e["id"]] = entry
        elif e.get("type") == "tool_result":
            content = e.get("content") if e.get("content") is not None else e.get("result")
            if isinstance(content, str):
                try:
                    content = json.loads(content)
                except Exception:
                    pass
            tgt = by_id.get(e.get("tool_use_id")) or (trace[-1] if trace else None)
            if tgt is not None:
                tgt["result"] = content if isinstance(content, dict) else {"raw": content}
                tgt["ok"] = content.get("ok") if isinstance(content, dict) else None
    return trace


def _entity(before_yaml: str) -> dict:
    """The widget-shaped open-playbook context: module `workflows` + the YAML
    seeded into the connector's OPEN PLAYBOOK block via `entity.playbook_yaml`.
    No real record is needed — verify/offer operate on the YAML text, and the
    offer `id` is a card id, not a lookup."""
    pb_name = "the open playbook"
    for line in before_yaml.splitlines():
        if line.strip().startswith("- name:"):
            pb_name = line.split("name:", 1)[1].strip()
            break
    return {
        "iri": f"/api/3/workflows/{uuid.uuid4()}",
        "module": "workflows",
        "uuid": str(uuid.uuid4()),
        "fields": {"name": pb_name},
        "playbook_yaml": before_yaml,
    }


def _run_one(scen: dict, version: str, config: str) -> dict:
    res = drive_scenario(
        scen["prompt"], intent="build", entity=_entity(scen["before_yaml"]),
        version=version, config=config, log=lambda *_: None)
    trace = _rich_trace(res.get("transcript") or [])
    verdict = score_enhance_delivery(trace, res.get("final_text") or "")
    return {
        "name": scen["name"], "tools": [t["name"] for t in trace],
        "has_fence": "```yaml" in (res.get("final_text") or "").lower(),
        "expect": scen.get("expect", {}).get("delivery"),
        "verdict": verdict,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="substring filter on scenario name")
    ap.add_argument("--runs", type=int, default=1, help="repeat each scenario n times")
    ap.add_argument("--config", default="", help="connector config; empty = box default")
    ap.add_argument("--version", default="", help="connector version; empty = drive_scenario default")
    args = ap.parse_args(argv)

    version = args.version or None
    scens = []
    for p in sorted(SCEN_DIR.glob("*.json")):
        scen = json.loads(p.read_text())
        if not args.only or args.only in scen["name"]:
            scens.append(scen)
    if not scens:
        print(f"no scenarios matched --only {args.only!r}", file=sys.stderr)
        return 2

    graded = passed = 0
    for scen in scens:
        for r in range(1, args.runs + 1):
            tag = f"{scen['name']}" + (f" run {r}" if args.runs > 1 else "")
            try:
                out = _run_one(scen, version, args.config)
            except Exception as e:
                print(f"  ERR  {tag}: {e!r}")
                graded += 1  # a drive failure is not a pass
                continue
            v = out["verdict"]
            if v.get("skipped"):
                print(f"  SKIP {tag}: {v.get('detail')}")
                continue
            graded += 1
            ok = v.get("passed")
            passed += 1 if ok else 0
            print(f"  {'PASS' if ok else 'FAIL'} {tag}  tools={out['tools']} "
                  f"fence={out['has_fence']} {v.get('code') or ''} — {v.get('detail')}")

    print(f"\n=== enhance-live: {passed}/{graded} graded run(s) delivered "
          f"({len(scens)} scenario(s) × {args.runs}) ===")
    return 0 if passed == graded else 1


if __name__ == "__main__":
    sys.exit(main())
