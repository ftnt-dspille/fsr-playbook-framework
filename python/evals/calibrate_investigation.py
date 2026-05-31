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
import logging
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "python"))
sys.path.insert(0, str(REPO_ROOT))

DEMO_MODEL = "claude-haiku-4-5-20251001"

GOLDEN_DIR = REPO_ROOT / "python" / "evals" / "golden_traces"
RUN_DIR = REPO_ROOT / "store" / "eval_runs"

log = logging.getLogger("calibrate")


def _setup_logging(log_path: Path) -> None:
    """File + stdout logging with timestamps. Also routes the Anthropic
    SDK + httpx loggers to the file so rate-limit 429s / retry backoff
    (the usual reason a tier-1 multi-turn run stalls) are captured —
    'what went wrong' lands in the log instead of a buffered black box."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s",
                            datefmt="%H:%M:%S")
    fh = logging.FileHandler(log_path)
    fh.setFormatter(fmt)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(fh)
    root.addHandler(sh)
    # Surface SDK retry/backoff + each HTTP request (429s included).
    # INFO (not DEBUG) keeps the "Retrying request … in Ns" backoff lines —
    # the usual tier-1 stall cause — without dumping the multi-KB request
    # body (system prompt + tool schemas) on every call.
    logging.getLogger("anthropic").setLevel(logging.INFO)
    logging.getLogger("httpx").setLevel(logging.INFO)


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
            log.info("    -> %s(%s)", ev.name, json.dumps(args, default=str)[:110])
        elif kind == "tool_result":
            res = getattr(ev, "result", None)
            ok = res.get("ok") if isinstance(res, dict) else None
            if trace:
                trace[-1]["ok"] = ok
            log.info("       <- ok=%s", ok)
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
    ap.add_argument("--capture", action="store_true",
                    help="bank each passing fixture's golden trace to "
                         "python/evals/golden_traces/ for the offline test")
    args = ap.parse_args()

    from evals.tasks import load_tasks
    from evals.scoring import _score_investigation, _score_investigation_quality

    tasks = [t for t in load_tasks() if t.mode == "investigation"]
    if args.only:
        tasks = [t for t in tasks if t.name == args.only]
    if not tasks:
        raise SystemExit("no investigation fixtures matched")

    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    _setup_logging(RUN_DIR / f"calibrate_{stamp}.log")
    if args.capture:
        GOLDEN_DIR.mkdir(parents=True, exist_ok=True)

    results = []
    for i, t in enumerate(tasks):
        if i > 0:
            # Let the per-minute token window drain between fixtures so
            # the next run starts with a clean rate-limit budget.
            log.info("... pacing %ss before next fixture ...", args.pace)
            time.sleep(args.pace)
        log.info("=" * 72)
        log.info("FIXTURE: %s   (model %s)", t.name, args.model)
        t0 = time.monotonic()
        try:
            out = asyncio.run(_run_one(t.prompt, args.model))
        except Exception as exc:  # noqa: BLE001 — bank the failure, keep going
            log.exception("FIXTURE %s RAISED: %r", t.name, exc)
            results.append((t.name, {"recall": 0.0, "passed": False,
                                     "missing": ["<run raised>"], "forbidden_hit": [],
                                     "error": repr(exc)}))
            continue
        dt = time.monotonic() - t0
        sc = _score_investigation(out["trace"], t.required_facts, t.forbidden_facts)
        quality = _score_investigation_quality(out["trace"], t.investigation_quality)
        # A fixture clears calibration only if recall AND every non-skipped
        # quality gate pass — recall alone greenlit 20-call flailing (the
        # finding that motivated this strengthening).
        q_failed = [k for k, v in quality.items()
                    if not v.get("skipped") and not v.get("passed")]
        sc["quality"] = quality
        sc["quality_failed"] = q_failed
        sc["passed"] = sc["passed"] and not q_failed
        log.info("  stop_reason=%s  pivots=%s  elapsed=%.0fs",
                 out["stop_reason"], len(out["trace"]), dt)
        log.info("  RECALL %s (gate %s)  matched %s/%s",
                 sc["recall"], sc["gate"], sc["matched"], sc["required"])
        for k, v in quality.items():
            if v.get("skipped"):
                continue
            log.info("  %-30s %s  (%s)",
                     k, "PASS" if v["passed"] else "FAIL", v.get("detail", ""))
        log.info("  OVERALL PASS=%s", sc["passed"])
        if sc["missing"]:
            log.info("  MISSING required: %s", sc["missing"])
        if sc["forbidden_hit"]:
            log.info("  !! FORBIDDEN fired: %s", sc["forbidden_hit"])

        # Bank the golden trace the moment the fixture completes, so a
        # later stall/kill never loses an already-paid-for fixture. Only
        # the tool-call layer (name+args+ok) is kept — not response bodies,
        # which go stale; the fixture pins the indicators these match on.
        if args.capture and sc["passed"]:
            gp = GOLDEN_DIR / f"{t.name}.json"
            gp.write_text(json.dumps({
                "fixture": t.name, "captured": stamp, "model": args.model,
                "stop_reason": out["stop_reason"], "recall": sc["recall"],
                "trace": [{"name": c["name"], "args": c.get("args", {}),
                           "ok": c.get("ok")} for c in out["trace"]],
            }, indent=2))
            log.info("  banked golden trace -> %s", gp.relative_to(REPO_ROOT))
        elif args.capture:
            log.warning("  NOT banking golden trace for %s (did not pass)", t.name)
        results.append((t.name, sc))

    log.info("=" * 72)
    log.info("SUMMARY")
    for name, sc in results:
        flag = "PASS" if sc["passed"] else "FAIL"
        extra = ""
        if sc["forbidden_hit"]:
            extra = f"  forbidden={len(sc['forbidden_hit'])}"
        elif sc.get("quality_failed"):
            extra = f"  quality_fail={','.join(sc['quality_failed'])}"
        elif sc["missing"]:
            extra = f"  missing={len(sc['missing'])}"
        log.info("  [%s] %-34s recall=%s%s", flag, name, sc["recall"], extra)
    n_pass = sum(1 for _, sc in results if sc["passed"])
    log.info("%s/%s fixtures clear the gate.", n_pass, len(results))

    summary_path = RUN_DIR / f"calibrate_{stamp}.summary.json"
    summary_path.write_text(json.dumps(
        {"stamp": stamp, "model": args.model,
         "results": [{"fixture": n, **{k: sc.get(k) for k in
                      ("recall", "passed", "missing", "forbidden_hit", "error")}}
                     for n, sc in results]}, indent=2))
    log.info("run summary -> %s", summary_path.relative_to(REPO_ROOT))


if __name__ == "__main__":
    main()
