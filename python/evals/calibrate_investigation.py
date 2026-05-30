"""Calibrate the investigation-recall fixtures against a live agent run.

For each `mode=investigation` task fixture, drive the REAL triage agent
loop (same path demo_hunt.py / the connector use) on the fixture's own
prompt, capture the tool-use trace, and score it with the same
`_score_investigation` the eval harness applies. Prints per-fixture
recall, missing required pivots, and any forbidden pivots fired, then a
summary verdict (does each clear the 0.8 gate with no forbidden hits?).

Needs a live FSR (.env: FSR_BASE_URL/creds) + ANTHROPIC_API_KEY. Costs
credits. Read-only against pinned alert/incident UUIDs.

Usage:
    uv run python python/evals/calibrate_investigation.py
    uv run python python/evals/calibrate_investigation.py --only invest_outbound_cleartext_c2
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "python"))
sys.path.insert(0, str(REPO_ROOT))

DEMO_MODEL = "claude-haiku-4-5-20251001"


async def _run_one(prompt: str, model: str) -> dict:
    from probes._env import get_config
    get_config()  # load .env (FSR creds + ANTHROPIC_API_KEY)

    from anthropic import AsyncAnthropic
    from fsr_core.llm.anthropic_provider import AnthropicProvider
    from fsr_core.llm.run_turn import run_agent_turn
    from fsr_core.llm.provider import Message
    from fsr_core.llm.intents import load_intent_prompt, tools_for_intent

    # Tier-1 org cap is 50k input tokens/min; a multi-turn investigation
    # resends growing history, so single turns can hit the per-minute
    # ceiling. Failed retries aren't billed — crank max_retries so the
    # SDK's backoff rides out the per-minute window instead of the turn
    # ending early (which would look like a recall miss).
    client = AsyncAnthropic(max_retries=12)
    provider = AnthropicProvider(model=model, client=client)
    system = load_intent_prompt("triage")
    tools = tools_for_intent("triage")

    trace: list[dict] = []
    final_chunks: list[str] = []

    def on_event(ev):
        kind = getattr(ev, "kind", "")
        if kind == "tool_use":
            args = dict(getattr(ev, "arguments", {}) or {})
            trace.append({"name": ev.name, "args": args})
            print(f"    -> {ev.name}({json.dumps(args, default=str)[:110]})")
        elif kind == "tool_result":
            res = getattr(ev, "result", None)
            ok = res.get("ok") if isinstance(res, dict) else None
            if trace:
                trace[-1]["ok"] = ok
            print(f"       <- ok={ok}")
        elif kind == "text":
            final_chunks.append(ev.text)

    result = await run_agent_turn(
        provider=provider, system=system,
        messages=[Message(role="user", content=prompt)],
        tools=tools, on_event=on_event,
    )
    return {"trace": trace, "final_text": "".join(final_chunks).strip(),
            "stop_reason": getattr(result, "stop_reason", None)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=None, help="run a single fixture by name")
    ap.add_argument("--model", default=DEMO_MODEL)
    ap.add_argument("--pace", type=int, default=45,
                    help="seconds to wait between fixtures (rate-limit drain)")
    args = ap.parse_args()

    from evals.tasks import load_tasks
    from evals.scoring import _score_investigation

    tasks = [t for t in load_tasks() if t.mode == "investigation"]
    if args.only:
        tasks = [t for t in tasks if t.name == args.only]
    if not tasks:
        raise SystemExit("no investigation fixtures matched")

    import time
    results = []
    for i, t in enumerate(tasks):
        if i > 0:
            # Let the per-minute token window drain between fixtures so
            # the next run starts with a clean rate-limit budget.
            print(f"\n... pacing {args.pace}s before next fixture ...")
            time.sleep(args.pace)
        print("=" * 72)
        print(f"FIXTURE: {t.name}   (model {args.model})")
        print("-" * 72)
        out = asyncio.run(_run_one(t.prompt, args.model))
        sc = _score_investigation(out["trace"], t.required_facts, t.forbidden_facts)
        print(f"  stop_reason={out['stop_reason']}  pivots={len(out['trace'])}")
        print(f"  RECALL {sc['recall']} (gate {sc['gate']})  "
              f"matched {sc['matched']}/{sc['required']}  "
              f"PASS={sc['passed']}")
        if sc["missing"]:
            print(f"  MISSING required: {sc['missing']}")
        if sc["forbidden_hit"]:
            print(f"  !! FORBIDDEN fired: {sc['forbidden_hit']}")
        results.append((t.name, sc))

    print("=" * 72)
    print("SUMMARY")
    for name, sc in results:
        flag = "PASS" if sc["passed"] else "FAIL"
        extra = ""
        if sc["forbidden_hit"]:
            extra = f"  forbidden={len(sc['forbidden_hit'])}"
        elif sc["missing"]:
            extra = f"  missing={len(sc['missing'])}"
        print(f"  [{flag}] {name:<34} recall={sc['recall']}{extra}")
    n_pass = sum(1 for _, sc in results if sc["passed"])
    print(f"\n{n_pass}/{len(results)} fixtures clear the gate.")


if __name__ == "__main__":
    main()
