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
    uv run python tooling/evals/calibrate_investigation.py
    uv run python tooling/evals/calibrate_investigation.py --only invest_outbound_cleartext_c2
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tooling"))
sys.path.insert(0, str(REPO_ROOT))

DEMO_MODEL = "claude-haiku-4-5-20251001"

GOLDEN_DIR = REPO_ROOT / "tooling" / "evals" / "golden_traces"
RUN_DIR = REPO_ROOT / "data" / "eval_runs"

# Each quality/recall failure points at the lever most likely to fix it, so a
# failed run is self-documenting: failure -> file/knob to change, no grep. The
# map is shared with chat_drive.py via evals.levers so the two tools can't drift.
from evals.levers import lever_for as _lever_for  # noqa: E402


def _load_baseline(stamp: str | None) -> dict | None:
    """Load a prior calibrate summary by stamp for delta comparison."""
    if not stamp:
        return None
    p = RUN_DIR / f"calibrate_{stamp}.summary.json"
    if not p.exists():
        log.warning("baseline %s not found at %s -- skipping delta", stamp, p)
        return None
    try:
        return json.loads(p.read_text())
    except Exception as exc:  # noqa: BLE001
        log.warning("baseline %s unreadable (%r) -- skipping delta", stamp, exc)
        return None


def _gate_states(entry: dict) -> dict[str, bool]:
    """Map gate-name -> passed for a summary entry's quality block (if present)."""
    q = entry.get("quality") or {}
    return {k: bool(v.get("passed")) for k, v in q.items()
            if isinstance(v, dict) and not v.get("skipped")}


def _compute_delta(baseline: dict, results: list[tuple[str, dict]]) -> dict:
    """Per-fixture recall change + gate PASS<->FAIL flips vs. baseline."""
    base_by_name = {e["fixture"]: e for e in baseline.get("results", [])}
    delta = {}
    for name, sc in results:
        b = base_by_name.get(name)
        if not b:
            delta[name] = {"new": True}
            continue
        d: dict = {}
        if b.get("recall") != sc.get("recall"):
            d["recall"] = {"from": b.get("recall"), "to": sc.get("recall")}
        if bool(b.get("passed")) != bool(sc.get("passed")):
            d["passed"] = {"from": bool(b.get("passed")), "to": bool(sc.get("passed"))}
        now_gates = {k: bool(v.get("passed")) for k, v in (sc.get("quality") or {}).items()
                     if isinstance(v, dict) and not v.get("skipped")}
        base_gates = _gate_states(b)
        flips = {g: {"from": base_gates[g], "to": now_gates[g]}
                 for g in now_gates if g in base_gates and base_gates[g] != now_gates[g]}
        if flips:
            d["gate_flips"] = flips
        if d:
            delta[name] = d
    return delta


def _median(xs: list[float]) -> float:
    """Plain median. n is 3-5 here, so sorting beats a dependency."""
    s = sorted(xs)
    n = len(s)
    if not n:
        return 0.0
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2.0


def _aggregate(runs: list[dict]) -> dict:
    """Collapse N repeats of one fixture into a single entry + a spread block.

    Single runs lie. One fixture was watched swinging 22 -> 31 -> 22 tool
    calls with nothing changed between them, which means a budget calibrated
    off one run is pinned to noise, and a later "the agent got worse" reading
    is a coin flip. So the reported cell is the MEDIAN run -- not the best,
    not the last -- and `passed` is a MAJORITY of repeats, not a single roll.
    `spread` carries what the median throws away: min/max, the per-gate
    k-of-n, and whether the fixture is flaky (some repeats passed, some
    didn't). A flaky fixture is a different object from a failing one and the
    summary must not flatten them together.
    """
    # Lost runs (stream died -- see the `lost` flag) are NOT results. Averaging
    # them in was how a dropped gateway became "the agent scored 0.0": one lost
    # repeat dragged fixture 29's median to 0.0 while its one real run scored
    # 18 and passed every gate. They are counted and reported, never scored.
    lost_runs = [r for r in runs if r.get("lost")]
    scored = [r for r in runs if not r.get("lost")]
    n_lost = len(lost_runs)
    if not scored:
        # Every repeat lost. There is no verdict to give, and reporting FAIL
        # here would be a claim about an agent that never ran.
        return {"recall": None, "passed": False, "calls": 0, "missing": [],
                "forbidden_hit": [], "quality": {}, "quality_failed": [],
                "no_data": True,
                "error": (lost_runs[0].get("error") if lost_runs else None),
                "spread": {"repeats": len(runs), "passes": 0, "flaky": False,
                           "lost": n_lost, "no_data": True,
                           "recall": None, "calls": None, "gate_k_of_n": {},
                           "approvals_seen": [], "resumes_ok": 0,
                           "substrate_misses": [], "runs": []}}

    runs = scored
    n = len(runs)
    recalls = [float(r.get("recall") or 0.0) for r in runs]
    calls = [int(r.get("calls") or 0) for r in runs]
    passes = [bool(r.get("passed")) for r in runs]
    n_pass = sum(passes)

    # The representative run = the one whose recall is the median. Ties break
    # toward the higher call count, so the reported trace is never the
    # flattering end of the spread.
    med_recall = _median(recalls)
    rep = sorted(runs, key=lambda r: (abs(float(r.get("recall") or 0.0) - med_recall),
                                      -int(r.get("calls") or 0)))[0]
    entry = dict(rep)

    gate_names: set[str] = set()
    for r in runs:
        gate_names |= {k for k, v in (r.get("quality") or {}).items()
                       if isinstance(v, dict) and not v.get("skipped")}
    gate_k_of_n = {
        g: sum(1 for r in runs
               if ((r.get("quality") or {}).get(g) or {}).get("passed"))
        for g in sorted(gate_names)
    }

    entry["passed"] = n_pass * 2 > n  # strict majority
    entry["spread"] = {
        "repeats": n,
        "passes": n_pass,
        # Scored repeats only. `lost` is carried alongside so a cell reading
        # "2/2" is never mistaken for a clean 3-repeat sweep.
        "lost": n_lost,
        "flaky": 0 < n_pass < n,
        "recall": {"min": min(recalls), "median": med_recall, "max": max(recalls)},
        "calls": {"min": min(calls), "median": _median([float(c) for c in calls]),
                  "max": max(calls)},
        "gate_k_of_n": gate_k_of_n,
        # Per repeat, so an approval that fires only SOMETIMES is visible.
        # A gate that is skipped on one roll of three is the worst possible
        # result for P2 and must not average away.
        "approvals_seen": [len(r.get("approvals") or []) for r in runs],
        "resumes_ok": sum(1 for r in runs
                          if any(x.get("resumed") for x in (r.get("resumes") or []))),
        # Deduped across repeats: a URL the substrate cannot serve is a
        # property of the BUNDLE, so it should be listed once, not N times.
        "substrate_misses": sorted({m for r in runs
                                    for m in (r.get("substrate_misses") or [])}),
        "runs": [{"recall": r.get("recall"), "calls": r.get("calls"),
                  "passed": bool(r.get("passed")),
                  "quality_failed": r.get("quality_failed", [])} for r in runs],
    }
    return entry


log = logging.getLogger("calibrate")


def _setup_logging(log_path: Path) -> None:
    """File + stdout logging with timestamps. Also routes the Anthropic
    SDK + httpx loggers to the file so rate-limit 429s / retry backoff
    (the usual reason a tier-1 multi-turn run stalls) are captured --
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
    # INFO (not DEBUG) keeps the "Retrying request … in Ns" backoff lines --
    # the usual tier-1 stall cause -- without dumping the multi-KB request
    # body (system prompt + tool schemas) on every call.
    logging.getLogger("anthropic").setLevel(logging.INFO)
    logging.getLogger("httpx").setLevel(logging.INFO)


def _active_box():
    """The bound FixtureBox, or None when the run is live/unbound."""
    try:
        from fsr_playbooks.mcp_server import _sim_client as sc
        return sc.active_box()
    except Exception:  # noqa: BLE001 -- live runs have no sim client at all
        return None


def _build_provider(kind: str, model: str):
    """Anthropic by default; `frank` points the OpenAI-compatible provider at
    the FRANK_* endpoint.

    Repeats multiply cost by N, and the screening doctrine is that the
    cheapest *consistent* model wins -- error bars are exactly the workload
    that should not be paid for per-token on a metered key. Reads FRANK_*
    rather than the global OPENAI_* config for the same reason the harness
    does: the two are different endpoints and silently sharing config is how
    a run measures a model nobody chose.
    """
    if kind == "frank":
        import os as _os
        from fsr_playbooks.llm.openai_provider import OpenAIProvider
        base_url = _os.environ.get("FRANK_BASE_URL")
        key = _os.environ.get("FRANK_API_KEY")
        if not base_url or not key:
            raise SystemExit("--provider frank needs FRANK_BASE_URL + "
                             "FRANK_API_KEY (see .env)")
        return OpenAIProvider(base_url=base_url, api_key=key,
                              model=model or _os.environ.get("FRANK_MODEL"))

    from anthropic import AsyncAnthropic
    from fsr_playbooks.llm.anthropic_provider import AnthropicProvider
    # Tier-1 org cap is 50k input tokens/min; a multi-turn investigation
    # resends growing history, so single turns can hit the per-minute
    # ceiling. Failed retries aren't billed -- crank max_retries so the
    # SDK's backoff rides out the per-minute window instead of the turn
    # ending early (which would look like a recall miss).
    return AnthropicProvider(model=model, client=AsyncAnthropic(max_retries=12))


# Only TRANSPORT failures make a run unscoreable. The distinction is
# load-bearing and was nearly lost: run 20260817T025645Z lost a repeat to a
# provider `400`, and that 400 arrived immediately after THREE `run_op` calls
# carrying `__bad_tool_arguments__` -- the model emitted malformed JSON until
# the request itself was invalid. Excluding that as "lost" would hide the exact
# agent defect the harness exists to catch. A rejection is a result; only a
# connection that never delivered one is a loss.
_TRANSPORT_FAILURE_MARKERS = (
    "connecterror", "connect error", "all connection attempts failed",
    "timed out", "timeout", "readerror", "read error",
    "remoteprotocolerror", "connection reset", "temporarily unavailable",
    "502", "503", "504",
)


def _is_transport_failure(message: str) -> bool:
    """True when the turn never got a response at all.

    A provider REJECTION (4xx other than 429) is deliberately NOT a transport
    failure: the request reached the model and was refused, usually because of
    what the agent put in it."""
    m = (message or "").lower()
    if "429" in m or "rate limit" in m:
        return True          # never delivered; retryable, not the agent's doing
    if any(k in m for k in ("400", "422", "bad request", "badrequest",
                            "invalid_request", "context length",
                            "maximum context")):
        return False         # the request was malformed -- that IS a result
    return any(k in m for k in _TRANSPORT_FAILURE_MARKERS)


async def _run_one(prompt: str, model: str, provider_kind: str = "anthropic",
                   approve: bool = False) -> dict:
    from probes._env import get_config
    get_config()  # load .env (FSR creds + ANTHROPIC_API_KEY)

    from fsr_playbooks.llm.run_turn import resume_agent_turn, run_agent_turn
    from fsr_playbooks.llm.provider import Message
    from fsr_playbooks.llm.intents import tools_for_intent
    from evals.prompt_source import resolve_triage_prompt

    provider = _build_provider(provider_kind, model)
    # NOT load_intent_prompt(): that resolves to a 583-char fallback stub in
    # this repo, so every run scored a prompt nobody ships. resolve_triage_prompt
    # raises instead of falling back -- see evals/prompt_source.py.
    system = resolve_triage_prompt().text
    tools = tools_for_intent("triage")

    trace: list[dict] = []
    final_chunks: list[str] = []
    approvals: list[dict] = []
    # Stream failures reach us as an ErrorEvent and NOTHING ELSE -- the turn
    # then returns normally with an empty trace. Until this was captured, a
    # gateway that dropped mid-sweep scored as `recall=0.0, 0 calls`, which is
    # indistinguishable from an agent that ran and reached nothing. Run
    # 20260817T020056Z lost four repeats to `httpx.ConnectError` and reported
    # `[FAIL] invest_intrusion_incident recall=0.0 missing=2` -- a finding
    # about an agent that never got a response.
    stream_errors: list[str] = []

    def on_event(ev):
        kind = getattr(ev, "kind", "")
        if kind == "error":
            msg = str(getattr(ev, "message", "") or "unknown stream error")
            stream_errors.append(msg)
            log.error("    !! STREAM ERROR: %s", msg[:200])
            return
        if kind == "approval_request":
            approvals.append({
                "approval_id": ev.approval_id, "tool": ev.tool,
                "tier": ev.tier, "tool_use_id": ev.tool_use_id,
                "preview": dict(getattr(ev, "preview", {}) or {}),
            })
            log.info("    ~~ APPROVAL REQUIRED tier=%s tool=%s id=%s",
                     ev.tier, ev.tool, ev.approval_id)
            return
        if kind == "tool_use":
            args = dict(getattr(ev, "arguments", {}) or {})
            trace.append({"name": ev.name, "args": args,
                          "call_id": getattr(ev, "call_id", None)})
            log.info("    -> %s(%s)", ev.name, json.dumps(args, default=str)[:110])
        elif kind == "tool_result":
            res = getattr(ev, "result", None)
            ok = res.get("ok") if isinstance(res, dict) else None
            # A discipline guard blocks the call without running it. Scoring
            # already excludes `refused` entries from the tool budget and from
            # the forbidden-pivot check -- but calibrate never SET the flag, so
            # a guard doing its job was charged to the agent as a tool call.
            from evals.chat_drive import _result_refused  # noqa: PLC0415
            refused = _result_refused(res)
            # Match by call_id, newest-first: the parallel read-only batch
            # emits ALL of a round's tool_use events before any tool_result,
            # so `trace[-1]` attributed every result of a batch to its last
            # call -- which is how three guard refusals scored as ordinary
            # agent spend (and one unrelated call as refused).
            cid = getattr(ev, "call_id", None)
            entry = next((t for t in reversed(trace)
                          if t.get("call_id") == cid), None) if cid else None
            if entry is None and trace:
                entry = trace[-1]
            if entry is not None:
                entry["ok"] = ok
                entry["refused"] = refused
            log.info("       <- %s ok=%s%s",
                     (entry or {}).get("name", "?"), ok,
                     "  (guard-refused)" if refused else "")
        elif kind == "text":
            final_chunks.append(ev.text)

    result = await run_agent_turn(
        provider=provider, system=system,
        messages=[Message(role="user", content=prompt)],
        tools=tools, on_event=on_event,
    )

    # The gate is dispatch logic, and a run that STOPS at it has only proven
    # the front half. Tier-3 tools run exclusively on the resume path, so a
    # guard living inside one is inert until the turn is actually resumed --
    # a suspended run scores as if the containment never happened, and the
    # deliverable gates fail for a reason that is not the agent's fault.
    resumes: list[dict] = []
    while (approve and getattr(result, "stop_reason", None) == "pending_approval"
           and approvals):
        from fsr_playbooks.llm import approvals as _appr
        pending = approvals[-1]
        susp = _appr.pop(pending["approval_id"])
        if susp is None:
            # Nothing to resume onto. Say so loudly rather than reporting the
            # turn as merely "suspended" -- an unpoppable approval is a
            # durability bug, not a policy outcome.
            log.warning("    !! approval %s not in the gateway -- cannot resume",
                        pending["approval_id"])
            resumes.append({**pending, "resumed": False,
                            "error": "approval not found in gateway"})
            break
        log.info("    ~~ APPROVING %s (%s) and resuming",
                 pending["tool"], pending["approval_id"])
        before = len(trace)
        result = await resume_agent_turn(
            provider=provider, suspended=susp, decision="approve",
            on_event=on_event,
        )
        resumes.append({**pending, "resumed": True,
                        "calls_after_resume": len(trace) - before,
                        "stop_reason": getattr(result, "stop_reason", None)})
        log.info("    ~~ resumed: %s more call(s), stop_reason=%s",
                 len(trace) - before, getattr(result, "stop_reason", None))

    return {"trace": trace, "final_text": "".join(final_chunks).strip(),
            "stop_reason": getattr(result, "stop_reason", None),
            "approvals": approvals, "resumes": resumes,
            "stream_errors": stream_errors}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=None,
                    help="comma-separated fixture names to run (default: all "
                         "investigation-mode fixtures). Selecting a subset is "
                         "how a read-only live sweep excludes the contain_* "
                         "rows, whose tools change state on a real box.")
    ap.add_argument("--model", default=None,
                    help=f"model id (default: {DEMO_MODEL} for anthropic, "
                         "$FRANK_MODEL for frank)")
    ap.add_argument("--provider", default="anthropic",
                    choices=("anthropic", "frank"),
                    help="which endpoint serves the agent. `frank` is the "
                         "free screening endpoint -- prefer it for --repeat, "
                         "where cost multiplies by N.")
    ap.add_argument("--pace", type=int, default=45,
                    help="seconds to wait between fixtures (rate-limit drain)")
    ap.add_argument("--capture", action="store_true",
                    help="bank each passing fixture's golden trace to "
                         "tooling/evals/golden_traces/ for the offline test")
    ap.add_argument("--baseline", default=None, metavar="STAMP",
                    help="prior calibrate run stamp to diff against (recall + "
                         "gate PASS<->FAIL flips); e.g. 20260530T120000Z")
    ap.add_argument("--repeat", type=int, default=1, metavar="N",
                    help="run each fixture N times and report the spread; the "
                         "reported cell is the MEDIAN run and pass is a "
                         "majority of repeats (default 1 = no error bars)")
    ap.add_argument("--approve", action="store_true",
                    help="APPROVE any tier-3 gate and resume the turn, instead "
                         "of stopping at pending_approval. Tier-3 tools only "
                         "run on the resume path, so without this the "
                         "containment fixtures never execute their action -- "
                         "and LIVE, this means the action really happens.")
    ap.add_argument("--offline", action="store_true",
                    help="bind the tools to the simulated client and seal the "
                         "FSR_* creds out of the env (= EVAL_OFFLINE=1). No "
                         "appliance is touched; still spends model credits.")
    ap.add_argument("--bundle", default=None, metavar="NAME",
                    help="fixture bundle backing the offline record surface "
                         "(e.g. soc_invest_surface). Without one the reads "
                         "answer empty-but-ok and the fixtures measure an "
                         "agent triaging an empty box.")
    ap.add_argument("--allow-unservable", action="store_true",
                    help="run fixtures whose required_facts name tools this "
                         "process does not register (they score 0.0 by "
                         "construction). Off by default: that 0.0 is "
                         "indistinguishable from an agent regression.")
    args = ap.parse_args()
    if args.repeat < 1:
        raise SystemExit("--repeat must be >= 1")
    # Order matters, twice over. get_config() reads .env and caches; offline
    # install() DELETES the FSR_* vars, so a dotenv read after the seal would
    # setdefault a live target straight back in. And the model default has to
    # be resolved AFTER that read, because FRANK_MODEL lives in .env -- doing
    # it before silently ran an unnamed model on the endpoint's own default,
    # which is the exact "measured a model nobody chose" failure this file
    # warns about elsewhere.
    from probes._env import get_config
    get_config()
    if args.model is None:
        args.model = (os.environ.get("FRANK_MODEL") if args.provider == "frank"
                      else DEMO_MODEL)
    if not args.model:
        raise SystemExit(f"no model resolved for --provider {args.provider} "
                         "(set FRANK_MODEL in .env or pass --model)")
    substrate = "live"
    if args.offline:
        import os as _os
        _os.environ["EVAL_OFFLINE"] = "1"
        if args.bundle:
            _os.environ["EVAL_FIXTURE_BUNDLE"] = args.bundle
        from evals import offline as _offline
        _offline.install()
        substrate = f"{_offline.active_client_name()} / {_offline.active_box_name()}"

    from evals.tasks import load_tasks
    from evals.scoring import (_score_investigation,
                               _score_investigation_quality,
                               unservable_required_tools)

    tasks = [t for t in load_tasks() if t.mode == "investigation"]
    if args.only:
        wanted = [n.strip() for n in args.only.split(",") if n.strip()]
        tasks = [t for t in tasks if t.name in wanted]
        missing = sorted(set(wanted) - {t.name for t in tasks})
        if missing:
            raise SystemExit(f"no such fixture(s): {', '.join(missing)}")
    if not tasks:
        raise SystemExit("no investigation fixtures matched")

    # A corrupt reference store makes `find_operation` raise on SOME queries
    # and answer others, so the agent re-searches for operations that exist and
    # the run reads as flailing. It happened twice in two days: on 2026-08-15 a
    # damaged `idx_ops_op` hid 72 real operations and drove this very fixture
    # from a median of 5 tool calls to 22. `doctor` detects it (health().intact)
    # but nothing made calibrate ask, and the numbers looked like agent
    # behaviour. Ask before spending a single model call.
    try:
        from fsr_playbooks.llm.tools import _DB_PATH  # noqa: PLC0415
        from fsr_playbooks.reference_db import health  # noqa: PLC0415
        _h = health(_DB_PATH)
    except Exception as exc:  # noqa: BLE001 -- never invent an env problem
        log.info("could not check the reference store (%s)", exc.__class__.__name__)
        _h = None
    if _h is not None and not _h.intact:
        raise SystemExit(
            f"refusing to run: {_h.summary}\n"
            "  Every number from this run would be the store's misses, not the "
            "agent's. Repair it (`sqlite3 <db> .recover | sqlite3 <new>`, then "
            "recreate the indexes) and re-run `make doctor` first.")

    # The invest_* fixtures pivot through the CONNECTOR's triage tools, which
    # are not part of this repo's registry and only appear once something calls
    # register_triage_tools(). Nothing here used to call it, so the tools were
    # simply absent and every fixture scored 0.0. Register them when the
    # connector is importable; the check below turns the remaining case into a
    # refusal instead of a silent zero.
    # `evals.harness` already owns this resolution (and honours
    # FSR_CONNECTOR_REPO); calibrate simply never called it.
    from evals.harness import register_triage_tools_if_available  # noqa: PLC0415
    tool_substrate = register_triage_tools_if_available()
    log.info("tool substrate: %s", tool_substrate)

    # Fail here, before a single credit is spent, if the prompt under test
    # cannot be resolved -- and SAY which prompt this run measured. A run whose
    # provenance is unstated cannot be compared to another run.
    from evals.prompt_source import PromptUnresolvable, resolve_triage_prompt
    try:
        _prompt = resolve_triage_prompt()
    except PromptUnresolvable as exc:
        log.error("prompt substrate: UNRESOLVABLE\n%s", exc)
        raise SystemExit(2) from None
    prompt_substrate = _prompt.summary
    log.info("prompt substrate: %s", prompt_substrate)

    # A fixture whose required_facts name a tool this process never registers
    # can only score recall 0.0, no matter how well the agent investigates.
    # `get_record` / `search_module_records` are the CONNECTOR's triage tools
    # (`fsr_soc_triage.registry.register_triage_tools()`), so every invest_*
    # fixture reads as a total agent regression when run from this repo alone.
    # The eval harness already labels those rows `unservable`; calibrate used
    # to print a bare 0.0, and that cost a full model sweep chasing a
    # regression that was a missing import path. Refuse BEFORE spending calls.
    unservable = {t.name: u for t in tasks
                  if (u := unservable_required_tools(t.required_facts))}
    if unservable and not args.allow_unservable:
        names = "\n".join(f"    {n:<34} needs {', '.join(u)}"
                          for n, u in sorted(unservable.items()))
        raise SystemExit(
            "refusing to run: these fixtures require tools that are NOT "
            f"registered in this process, so they can only score 0.0:\n{names}\n"
            "  Those are the connector's triage tools. Run calibrate with the "
            "connector on PYTHONPATH (its `scripts/` FIRST), or pass "
            "--allow-unservable to score them anyway and read every 0.0 as "
            "'unscoreable here', not 'the agent got worse'.")
    for name, u in sorted(unservable.items()):
        log.warning("UNSERVABLE: %s requires unregistered tool(s) %s -- its "
                    "recall is 0.0 by construction, not by behaviour",
                    name, ", ".join(u))

    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    _setup_logging(RUN_DIR / f"calibrate_{stamp}.log")
    if args.capture:
        GOLDEN_DIR.mkdir(parents=True, exist_ok=True)

    results = []
    for i, t in enumerate(tasks):
        runs: list[dict] = []
        for rep in range(1, args.repeat + 1):
            if i > 0 or rep > 1:
                # Let the per-minute token window drain between runs so the
                # next one starts with a clean rate-limit budget. Repeats pace
                # too: a repeat that stalls on a 429 measures the rate limiter,
                # not the agent, and that lands in the spread as noise.
                log.info("... pacing %ss before next run ...", args.pace)
                time.sleep(args.pace)
            log.info("=" * 72)
            log.info("FIXTURE: %s   run %s/%s   (model %s, substrate %s)",
                     t.name, rep, args.repeat,
                     f"{args.provider}:{args.model}", substrate)
            # Snapshot the substrate's miss log around the run. A 404 from the
            # fixture box is INDISTINGUISHABLE, in the trace, from an agent
            # pivoting somewhere pointless -- three dead limbs in this sim
            # already presented as agent overspend before anyone looked. So
            # the misses a run CAUSED become a field, not a log-grep.
            box = _active_box()
            miss_mark = len(getattr(box, "misses", [])) if box is not None else 0
            t0 = time.monotonic()
            try:
                out = asyncio.run(_run_one(t.prompt, args.model, args.provider,
                                           approve=args.approve))
            except Exception as exc:  # noqa: BLE001 -- bank the failure, keep going
                log.exception("FIXTURE %s RAISED: %r", t.name, exc)
                runs.append({"recall": 0.0, "passed": False, "calls": 0,
                             "missing": ["<run raised>"], "forbidden_hit": [],
                             "quality": {}, "quality_failed": [],
                             "error": repr(exc)})
                continue
            dt = time.monotonic() - t0
            # A run whose stream died never produced a verdict, so it must not
            # BE one. Scoring it anyway yields `recall=0.0, 0 calls`, which the
            # summary renders as the agent failing to reach its required ops --
            # a finding about a turn that never got a response. Mark it lost;
            # `_aggregate` drops lost runs from the tally rather than counting
            # them as failures.
            errs = out.get("stream_errors") or []
            if errs and all(_is_transport_failure(e) for e in errs):
                log.error("  RUN LOST -- %s transport error(s), NOT scored: %s",
                          len(errs), errs[0][:160])
                runs.append({"recall": None, "passed": False, "calls": 0,
                             "missing": [], "forbidden_hit": [],
                             "quality": {}, "quality_failed": [],
                             "lost": True, "error": errs[0]})
                continue
            if errs:
                # Rejected, not lost. Score it -- the request reached the model
                # and was refused, and what the agent put in the request is
                # usually why. Flagged so it is never mistaken for a clean run.
                log.error("  RUN REJECTED (scored, NOT lost) -- %s: %s",
                          len(errs), errs[0][:160])
            sc = _score_investigation(out["trace"], t.required_facts, t.forbidden_facts)
            quality = _score_investigation_quality(out["trace"], t.investigation_quality)
            # A fixture clears calibration only if recall AND every non-skipped
            # quality gate pass -- recall alone greenlit 20-call flailing (the
            # finding that motivated this strengthening).
            q_failed = [k for k, v in quality.items()
                        if not v.get("skipped") and not v.get("passed")]
            sc["quality"] = quality
            sc["quality_failed"] = q_failed
            sc["passed"] = sc["passed"] and not q_failed
            sc["calls"] = len(out["trace"])
            sc["approvals"] = out.get("approvals") or []
            sc["resumes"] = out.get("resumes") or []
            sc["substrate_misses"] = (
                list(box.misses[miss_mark:]) if box is not None else [])
            sc["rejected"] = list(errs)
            if sc["substrate_misses"]:
                log.info("  substrate 404s (%s): %s", len(sc["substrate_misses"]),
                         "; ".join(sc["substrate_misses"][:6]))
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
            # the tool-call layer (name+args+ok) is kept -- not response bodies,
            # which go stale; the fixture pins the indicators these match on.
            if args.capture and sc["passed"] and rep == 1:
                gp = GOLDEN_DIR / f"{t.name}.json"
                gp.write_text(json.dumps({
                    "fixture": t.name, "captured": stamp, "model": args.model,
                    "stop_reason": out["stop_reason"], "recall": sc["recall"],
                    "trace": [{"name": c["name"], "args": c.get("args", {}),
                               "ok": c.get("ok")} for c in out["trace"]],
                }, indent=2))
                log.info("  banked golden trace -> %s", gp.relative_to(REPO_ROOT))
            # Always bank FAILURE traces (the signal for the next fix) -- unlike
            # golden passes, these are unconditional, since a thrown-away failing
            # trace is exactly what forces an expensive re-run to diagnose. Records
            # the full arg-by-arg trace + the gates that tripped + their implicated
            # lever, so failure -> file-to-change is a field, not a log-grep.
            if not sc["passed"]:
                fdir = RUN_DIR / f"calibrate_{stamp}_failures"
                fdir.mkdir(parents=True, exist_ok=True)
                failed_keys = list(sc.get("quality_failed") or [])
                if sc.get("missing"):
                    failed_keys.append("investigation_recall")
                if sc.get("forbidden_hit"):
                    failed_keys.append("<forbidden>")
                fname = f"{t.name}.json" if args.repeat == 1 else f"{t.name}.run{rep}.json"
                (fdir / fname).write_text(json.dumps({
                    "fixture": t.name, "captured": stamp, "model": args.model,
                    "stop_reason": out["stop_reason"], "recall": sc["recall"],
                    "gate": sc["gate"], "matched": sc["matched"], "required": sc["required"],
                    "missing": sc["missing"], "forbidden_hit": sc["forbidden_hit"],
                    "quality": sc.get("quality", {}),
                    "failed_gates": [{"gate": k, "lever": _lever_for(k),
                                      "detail": (sc.get("quality", {}).get(k, {}) or {}).get("detail", "")}
                                     for k in failed_keys],
                    "trace": [{"name": c["name"], "args": c.get("args", {}),
                               "ok": c.get("ok")} for c in out["trace"]],
                }, indent=2))
                log.info("  banked FAILURE trace -> %s",
                         (fdir / fname).relative_to(REPO_ROOT))
                for k in failed_keys:
                    log.info("    lever[%s]: %s", k, _lever_for(k))
            runs.append(sc)
        results.append((t.name, _aggregate(runs)))

    log.info("=" * 72)
    log.info("SUMMARY")
    # A row measured against a substrate that 404'd is NOT a verdict on the
    # agent, and printing it as `FAIL` next to honest rows is how this has
    # been misread four times running (`agents`, the enrichment shortcut,
    # SIEM pub/v2, `assets` -- the last cost fixture 29 a 35-call median that
    # dropped to 19 the moment the module was bound). The miss list was
    # already collected and already footnoted below; a footnote under a table
    # of numbers loses every time. Disqualify the row instead.
    tainted = set()
    for name, sc in results:
        if (sc.get("spread") or {}).get("substrate_misses") or \
                sc.get("substrate_misses"):
            tainted.add(name)
    for name, sc in results:
        flag = "PASS" if sc["passed"] else "FAIL"
        extra = ""
        if sc["forbidden_hit"]:
            extra = f"  forbidden={len(sc['forbidden_hit'])}"
        elif sc.get("quality_failed"):
            extra = f"  quality_fail={','.join(sc['quality_failed'])}"
        elif sc["missing"]:
            extra = f"  missing={len(sc['missing'])}"
        sp = sc.get("spread") or {}
        if sp.get("flaky"):
            flag = "FLAKY"
        if name in tainted:
            flag = "SUBSTRATE"
            extra += "  <- numbers are NOT the agent's"
        # Same disqualification, different cause: the stream died, so there is
        # nothing to be a verdict ABOUT. Never print FAIL for a turn that never
        # got a response.
        n_lost = sp.get("lost") or 0
        if sp.get("no_data"):
            flag = "NO DATA"
            extra = (f"  all {sp.get('repeats')} repeat(s) lost to stream "
                     f"errors -- the agent never ran")
        elif n_lost:
            extra += f"  ({n_lost} repeat(s) lost to stream errors)"
        log.info("  [%s] %-34s recall=%s%s", flag, name, sc["recall"], extra)
    n_pass = sum(1 for _, sc in results if sc["passed"])
    no_data = [n for n, sc in results if (sc.get("spread") or {}).get("no_data")]
    lost_total = sum((sc.get("spread") or {}).get("lost") or 0
                     for _, sc in results)
    log.info("%s/%s fixtures clear the gate.", n_pass, len(results))
    if lost_total:
        log.warning("!! %s repeat(s) LOST to stream errors -- the gateway "
                    "dropped mid-sweep. Those runs are excluded, not scored as "
                    "0.0. Re-run before treating this sweep as a baseline.%s",
                    lost_total,
                    (f" No data at all for: {', '.join(no_data)}."
                     if no_data else ""))
    if tainted:
        log.info("%s fixture(s) ran against a substrate that could not serve "
                 "every read: %s. Bind the missing module(s) and re-run before "
                 "reading their call counts -- a 404 does not just waste its "
                 "own call, it sends the agent looking for another way round.",
                 len(tainted), ", ".join(sorted(tainted)))

    # Error bars. Without them a 22 -> 31 -> 22 call swing on an unchanged
    # agent reads as a regression, which is the exact misreading the
    # investigation gates exist to prevent.
    if args.repeat > 1:
        log.info("-" * 72)
        log.info("SPREAD over %s repeats (substrate: %s)", args.repeat, substrate)
        log.info("  %-34s %-6s %-18s %-14s %s",
                 "fixture", "pass", "recall min/med/max", "calls min/med/max",
                 "unstable gates")
        for name, sc in results:
            sp = sc.get("spread") or {}
            n_lost = sp.get("lost") or 0
            # `repeats` here is the SCORED count, so the pass cell must not
            # imply a full sweep when repeats were lost -- "2/2 (1 lost)".
            pass_cell = f"{sp.get('passes')}/{sp.get('repeats')}"
            if n_lost:
                pass_cell += f" (-{n_lost})"
            if sp.get("no_data"):
                log.info("  %-34s %-6s %s", name, "--",
                         f"NO DATA -- all {n_lost} repeat(s) lost to stream errors")
                continue
            r, c = sp.get("recall", {}), sp.get("calls", {})
            unstable = [f"{g} {k}/{sp['repeats']}"
                        for g, k in (sp.get("gate_k_of_n") or {}).items()
                        if 0 < k < sp["repeats"]]
            log.info("  %-34s %-6s %-18s %-14s %s",
                     name, pass_cell,
                     f"{r.get('min')}/{r.get('median')}/{r.get('max')}",
                     f"{c.get('min')}/{c.get('median')}/{c.get('max')}",
                     ", ".join(unstable) or "-")
        # A URL the bundle cannot serve costs the agent a pivot every single
        # run, and every gate here would blame the agent for it.
        by_url: dict[str, list[str]] = {}
        for name, sc in results:
            for m in (sc.get("spread") or {}).get("substrate_misses") or []:
                by_url.setdefault(m, []).append(name)
        if by_url:
            log.info("-" * 72)
            log.info("SUBSTRATE MISSES -- the bundle could not serve these; "
                     "the agent paid a pivot for each")
            for url, names in sorted(by_url.items(),
                                     key=lambda kv: (-len(kv[1]), kv[0])):
                log.info("  %-58s %s", url[:58], ", ".join(sorted(set(names))))

        flaky = [n for n, sc in results if (sc.get("spread") or {}).get("flaky")]
        if flaky:
            log.info("  FLAKY (some repeats passed, some did not): %s",
                     ", ".join(flaky))
        else:
            log.info("  no fixture flipped pass/fail across repeats.")

    # Baseline delta -- turns "3/5 PASS" into "mail_egress budget 19->11, now
    # clears": a verdict an agent can act on, vs. a snapshot to eyeball.
    baseline = _load_baseline(args.baseline)
    delta = _compute_delta(baseline, results) if baseline else {}
    if baseline:
        log.info("-" * 72)
        log.info("DELTA vs %s", args.baseline)
        if not delta:
            log.info("  no change in recall, pass/fail, or gates.")
        for name, d in delta.items():
            if d.get("new"):
                log.info("  [NEW] %s (not in baseline)", name)
                continue
            bits = []
            if "recall" in d:
                bits.append(f"recall {d['recall']['from']}->{d['recall']['to']}")
            if "passed" in d:
                arrow = "FIXED" if d["passed"]["to"] else "REGRESSED"
                bits.append(f"{arrow} (pass {d['passed']['from']}->{d['passed']['to']})")
            for g, gv in d.get("gate_flips", {}).items():
                arrow = "PASS" if gv["to"] else "FAIL"
                bits.append(f"{g}->{arrow} [{_lever_for(g)}]")
            log.info("  %-34s %s", name, "; ".join(bits))

    summary_path = RUN_DIR / f"calibrate_{stamp}.summary.json"
    summary_path.write_text(json.dumps(
        {"stamp": stamp, "model": args.model, "provider": args.provider, "baseline": args.baseline,
         # Two runs on different substrates are not comparable, and nothing
         # else in the file would say which one this was.
         "repeats": args.repeat, "substrate": substrate,
         "offline": bool(args.offline), "bundle": args.bundle,
         # An unservable row's 0.0 means "unscoreable here", not "the agent
         # got worse" -- the summary has to say so or the next diff relearns it.
         "unservable": unservable, "tool_substrate": tool_substrate,
         # Which PROMPT this run measured. Runs whose fingerprints differ are
         # measuring different agents; runs whose fingerprints match cannot
         # show a prompt effect, however different their scores look.
         "prompt_substrate": prompt_substrate,
         "prompt_fingerprint": _prompt.fingerprint,
         "results": [{"fixture": n, "spread": sc.get("spread"),
                      "unservable": unservable.get(n) or [],
                      **{k: sc.get(k) for k in
                         ("recall", "passed", "missing", "forbidden_hit", "error")},
                      "quality": sc.get("quality", {}),
                      "quality_failed": sc.get("quality_failed", []),
                      "failed_levers": {k: _lever_for(k)
                                        for k in (sc.get("quality_failed") or [])}}
                     for n, sc in results],
         "delta": delta}, indent=2))
    log.info("run summary -> %s", summary_path.relative_to(REPO_ROOT))


if __name__ == "__main__":
    main()
