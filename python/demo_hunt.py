"""Live hunting + agentic-response demo (Phase 1.4 MVP).

Drives the REAL triage agent loop (`fsr_playbooks.llm.run_turn.run_agent_turn`
+ `AnthropicProvider`) against a live FortiSOAR record, using the same
triage system prompt and tool slice the connector ships. It prints the
agent's pivots (every tool call), the final analyst-facing text, and any
staged action card — i.e. a watchable "investigate this alert and stage
containment" run.

This is intentionally thin: it reuses production code paths so what you
see in the demo is what the connector does. It doubles as the manual
harness behind the investigation-recall eval (scoring.mode='investigation').

Usage:
    uv run python python/demo_hunt.py \
        --record alerts:d39ecc9a-2968-42d5-948d-ce96fd76b227
    uv run python python/demo_hunt.py --prompt "Investigate ... and stage containment"

Needs a live FSR (.env: FSR_BASE_URL/creds) and ANTHROPIC_API_KEY.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "python"))
sys.path.insert(0, str(REPO_ROOT))  # fsr_playbooks lives at the repo root

# Default model: Haiku, to keep demo cost low.
DEMO_MODEL = "claude-haiku-4-5-20251001"


def _default_prompt(record: str) -> str:
    return (
        f"You are triaging FortiSOAR record `{record}`. Investigate it end to "
        "end: pull the record, extract its indicators (IPs, user, host), find "
        "related activity across alerts/indicators/assets/identities, enrich any "
        "EXTERNAL indicators with the threat-intel connectors, and correlate what "
        "you find into a short verdict. If containment is warranted, stage it for "
        "analyst approval with emit_action_card — do not execute it yourself."
    )


async def _run(prompt: str, model: str = DEMO_MODEL,
               record: str | None = None) -> dict:
    # Trigger .env load (FSR creds + ANTHROPIC_API_KEY) before constructing
    # the provider/client.
    from probes._env import get_config
    get_config()

    from fsr_playbooks.llm.anthropic_provider import AnthropicProvider
    from fsr_playbooks.llm.run_turn import run_agent_turn
    from fsr_playbooks.llm.provider import Message
    # Single source of truth for the tool slice (same helper the connector
    # uses); the triage *prompt* now comes from the dynamic pre-flight below.
    from fsr_playbooks.llm.intents import load_intent_prompt, tools_for_intent
    from fsr_playbooks.llm.triage_preflight import triage_preflight

    provider = AnthropicProvider(model=model)
    tools = tools_for_intent("triage")

    # Pre-flight: land the record once, normalize + classify it, and build the
    # scenario-aware system prompt. Activity events are printed inline so the
    # demo shows what the backend grounded on before the model ran.
    def _emit_activity(ev: dict) -> None:
        print(f"  [pre-flight] {ev.get('phase'):>9}: {ev.get('message')}")

    system = load_intent_prompt("triage")
    scenario_id = None
    if record:
        bundle = triage_preflight(target=record, user_message=prompt,
                                  emit=_emit_activity)
        system = bundle["system"]
        scenario_id = bundle.get("scenario_id")
        print()

    trace: list[dict] = []
    final_chunks: list[str] = []
    cards: list[dict] = []
    # Timing: stamp each tool_use; on its tool_result, charge the gap to that
    # call (≈ the live tool's execution time). The gaps NOT covered by a tool
    # call are model latency. perf_counter is monotonic + wall-clock.
    t0 = time.perf_counter()
    pending_start: dict[str, float] = {}

    def _now() -> float:
        return time.perf_counter() - t0

    def on_event(ev):
        kind = getattr(ev, "kind", "")
        if kind == "tool_use":
            args = dict(getattr(ev, "arguments", {}) or {})
            cid = getattr(ev, "call_id", "")
            pending_start[cid] = time.perf_counter()
            trace.append({"name": ev.name, "args": args, "call_id": cid,
                          "started_at_s": round(_now(), 2)})
            preview = json.dumps(args, default=str)
            print(f"  [{_now():6.1f}s] → {ev.name}({preview[:120]})")
        elif kind == "tool_result":
            res = getattr(ev, "result", None)
            cid = getattr(ev, "call_id", "")
            dur = (time.perf_counter() - pending_start.pop(cid, time.perf_counter()))
            ok = res.get("ok") if isinstance(res, dict) else None
            if trace:
                trace[-1]["ok"] = ok
                trace[-1]["code"] = res.get("code") if isinstance(res, dict) else None
                trace[-1]["exec_s"] = round(dur, 2)
            print(f"  [{_now():6.1f}s]   ← {dur:5.1f}s  ok={ok}")
            if isinstance(res, dict) and isinstance(res.get("card"), dict):
                cards.append(res["card"])
        elif kind == "text":
            final_chunks.append(ev.text)
        elif kind == "approval_request":
            print(f"  [{_now():6.1f}s] ⏸ approval requested: "
                  f"{getattr(ev, 'tool', '?')} (tier {getattr(ev, 'tier', '?')})")

    result = await run_agent_turn(
        provider=provider, system=system,
        messages=[Message(role="user", content=prompt)],
        tools=tools, on_event=on_event,
    )
    total_s = _now()
    tool_s = sum(e.get("exec_s", 0.0) for e in trace)
    return {
        "trace": trace,
        "final_text": "".join(final_chunks).strip(),
        "cards": cards,
        "stop_reason": getattr(result, "stop_reason", None),
        "scenario_id": scenario_id,
        "total_s": round(total_s, 1),
        "tool_s": round(tool_s, 1),
        "model_s": round(total_s - tool_s, 1),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--record", default="alerts:d39ecc9a-2968-42d5-948d-ce96fd76b227",
                    help="module:uuid to investigate (default: the C2 scenario alert)")
    ap.add_argument("--prompt", default=None, help="override the full prompt")
    ap.add_argument("--model", default=DEMO_MODEL,
                    help=f"Anthropic model (default: {DEMO_MODEL})")
    args = ap.parse_args()

    record = args.record.replace(":", "/", 1) if ":" in args.record else args.record
    prompt = args.prompt or _default_prompt(f"/api/3/{record}"
                                            if not record.startswith("/") else record)

    print("=" * 72)
    print("LIVE HUNT — triage agent")
    print("=" * 72)
    print(f"model:  {args.model}")
    print(f"prompt: {prompt}\n\nPRE-FLIGHT + PIVOTS:")
    out = asyncio.run(_run(prompt, model=args.model, record=args.record))

    if out.get("scenario_id"):
        print(f"\nscenario: {out['scenario_id']}")
    print(f"\nstop_reason: {out['stop_reason']}  ·  {len(out['trace'])} tool call(s)")
    print(f"TIMING: total {out['total_s']}s  =  tools {out['tool_s']}s  +  "
          f"model/other {out['model_s']}s")
    # Per-pivot breakdown, slowest first — shows what to optimize.
    slow = sorted([e for e in out["trace"] if "exec_s" in e],
                  key=lambda e: e["exec_s"], reverse=True)
    if slow:
        print("  slowest pivots:")
        for e in slow[:8]:
            a = e.get("args", {})
            tag = a.get("op") or a.get("module") or a.get("connector") or ""
            print(f"    {e['exec_s']:6.1f}s  {e['name']} {tag}")
    print("\nFINAL (analyst-facing):\n" + (out["final_text"] or "(no text)"))
    if out["cards"]:
        print("\nSTAGED CARDS:")
        for c in out["cards"]:
            print("  " + json.dumps(c, default=str)[:400])


if __name__ == "__main__":
    main()
