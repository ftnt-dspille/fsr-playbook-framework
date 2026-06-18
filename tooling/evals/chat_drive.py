"""chat_drive — the one-command tuning loop (Chat Intelligence Plan, Track A1/A2).

Drive ONE real scenario through the deployed connector's synchronous `chat_turn`
(and `chat_resume` for approval / multi-turn flows), then in a single pass:

  1. capture the transcript,
  2. normalize it into a scoring trace,
  3. score it with the existing `evals.scoring` gates (when the scenario is an
     investigation fixture with required/forbidden facts),
  4. render-validate the raw transcript through the widget renderer
     (`fsrPbRender.buildAssistantMessage`, via the node bridge), and
  5. print a one-screen verdict — every failing gate annotated with the prompt
     LEVER most likely to fix it (`evals.levers`).

A scenario is either an existing task fixture (`--task <name>`, reusing its
prompt + facts + quality knobs) or an ad-hoc message (`--message … --intent …`,
trace + render verdict only, no scoring).

`--capture-fixture` (A2) turns a good run into a committable regression case:
a proposed `tasks/<NN>_<slug>.json` + a `golden_traces/<name>.json`.

Live: needs `.env` FSR creds and a reachable, deployed connector. Costs credits.
The offline regression guard is `python/tests/test_golden_traces_pin.py`.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT / "tooling") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "tooling"))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from evals.levers import lever_for  # noqa: E402

CONN = "fsr-playbook-builder"
DEFAULT_VERSION = "0.3.116"
DEFAULT_CONFIG = "fsrpb-live"
RUN_DIR = REPO_ROOT / "data" / "eval_runs"
TASKS_DIR = REPO_ROOT / "tooling" / "evals" / "tasks"
GOLDEN_DIR = REPO_ROOT / "tooling" / "evals" / "golden_traces"

# The node render bridge lives in the (sibling) widget repo. Path is overridable
# so the Python loop never hard-depends on the widget tree being present.
_DEFAULT_BRIDGES = [
    Path(os.environ["FSRPB_RENDER_BRIDGE"]) if os.environ.get("FSRPB_RENDER_BRIDGE") else None,
    REPO_ROOT.parent.parent / "WebstormProjects" / "fsr_all_widgets"
    / "widgets-src" / "fsrSocAssistant" / "tools" / "render_check.cjs",
    Path.home() / "WebstormProjects" / "fsr_all_widgets"
    / "widgets-src" / "fsrSocAssistant" / "tools" / "render_check.cjs",
]


# ───────────────────────── drive ─────────────────────────

def _execute(client, op: str, params: dict, version: str, config: str,
             timeout: int = 290) -> Any:
    body = {"connector": CONN, "operation": op, "version": version,
            "config": config, "params": params}
    return client.post("/api/integration/execute/", body)


def _unwrap(resp: Any) -> Any:
    """Peel the `{status, data}` integration-execute envelope."""
    if (isinstance(resp, dict) and isinstance(resp.get("data"), dict)
            and isinstance(resp.get("status"), str)):
        return resp["data"]
    return resp


def drive_scenario(message: str, intent: str, *, record: Any = None,
                   version: str = DEFAULT_VERSION, config: str = DEFAULT_CONFIG,
                   resume: dict | None = None, session: str | None = None,
                   log=print) -> dict:
    """Drive a sync chat_turn (+ optional chat_resume) and return the merged
    transcript plus derived trace/final_text. Raises on a non-dict / error
    response so the caller reports a clean failure (never hangs)."""
    from probes import _env  # type: ignore

    cfg = _env.get_config()
    if not cfg.is_live():
        raise RuntimeError("FSR_BASE_URL / auth not configured (.env)")
    client = _env.get_client()

    session = session or f"chatdrive-{int(time.time())}"
    params: dict[str, Any] = {
        "session_id": session,
        "messages": [{"role": "user", "content": message}],
        "intent": intent,
        "mode": "live",
        "detached": False,
    }
    if record is not None:
        params["record"] = record

    log(f">> chat_turn (sync) session={session} intent={intent}")
    log(f">> msg: {message}")
    t0 = time.time()
    res = _unwrap(_execute(client, "chat_turn", params, version, config))
    elapsed = time.time() - t0
    if not isinstance(res, dict):
        raise RuntimeError(f"chat_turn returned non-dict: {res!r:.300}")
    if res.get("ok") is False or res.get("error"):
        raise RuntimeError(f"chat_turn error: {res.get('error') or res}")

    transcript = list(res.get("transcript") or [])
    stop_reason = res.get("stop_reason")
    log(f">> returned in {elapsed:.1f}s  stop_reason={stop_reason}  "
        f"turn={res.get('turn')}  contract={res.get('contract_version')}")

    # Approval / multi-turn: fire chat_resume when the turn suspended, or when
    # the scenario explicitly scripts a resume decision.
    if resume or stop_reason == "approval_required":
        rp = dict(resume or {"decision": "approve"})
        rp["session_id"] = session
        log(f">> chat_resume decision={rp.get('decision')} "
            f"(stop_reason was {stop_reason})")
        t1 = time.time()
        res2 = _unwrap(_execute(client, "chat_resume", rp, version, config))
        elapsed += time.time() - t1
        if isinstance(res2, dict):
            transcript += list(res2.get("transcript") or [])
            stop_reason = res2.get("stop_reason", stop_reason)
            log(f">> resume returned stop_reason={stop_reason}")

    trace = transcript_to_trace(transcript)
    final_text = "".join(
        e.get("text", "") for e in transcript
        if isinstance(e, dict) and e.get("type") == "text").strip()
    return {
        "session": session, "transcript": transcript, "trace": trace,
        "final_text": final_text, "stop_reason": stop_reason,
        "elapsed": round(elapsed, 1), "version": version, "config": config,
    }


# ───────────────────── transcript → scoring trace ─────────────────────

def _normalize_args(name: str, raw_input: Any) -> dict:
    """Normalize a wire `tool_use.input` into the arg shape `evals.scoring`
    expects. The connector transcript nests run_op as
    `{connector, operation, args:{…}}`; scoring's matchers read `op` + `params`
    (and the in-process golden traces use that shape). Map operation→op and
    args→params so a chat_turn-captured trace scores identically to a
    calibrate-captured one. Other tools (`get_record`, `search_module_records`)
    already carry their matcher keys (`module`, ids) at the top level."""
    args = dict(raw_input) if isinstance(raw_input, dict) else {}
    if name == "run_op":
        if "operation" in args and "op" not in args:
            args["op"] = args["operation"]
        if "args" in args and "params" not in args and isinstance(args["args"], dict):
            args["params"] = args["args"]
    return args


def _result_ok(content: Any) -> bool | None:
    """Best-effort success flag from a tool_result payload (`{"status": …}`)."""
    if isinstance(content, dict):
        status = content.get("status")
    elif isinstance(content, str):
        try:
            status = (json.loads(content) or {}).get("status")
        except Exception:  # noqa: BLE001
            return None
    else:
        return None
    if status is None:
        return None
    return str(status).lower() in ("success", "ok", "true")


# Discipline-guard markers a tool_result carries when the connector refused to
# execute a call (TriageDiscipline). A refused call is in the trace (the model
# attempted it) but never ran, so scoring must not count it as a performed
# pivot — a guard-blocked forbidden pivot is a SUCCESS of the platform, not a
# violation by the agent.
_GUARD_MARKERS = ("forbidden_pivot_guard", "hunt_floor_guard", "call_once_guard")


def _result_refused(content: Any) -> bool:
    """True when a tool_result payload is a discipline-guard refusal envelope."""
    payload = content
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:  # noqa: BLE001
            return False
    return isinstance(payload, dict) and any(payload.get(m) for m in _GUARD_MARKERS)


def transcript_to_trace(transcript: list[dict]) -> list[dict]:
    """Build the `[{name, args, ok, refused}]` trace `evals.scoring` consumes
    from a wire transcript, pairing each `tool_result` onto its `tool_use` by
    id. `refused` flags a call the connector's discipline guard blocked."""
    trace: list[dict] = []
    by_id: dict[str, dict] = {}
    for e in transcript:
        if not isinstance(e, dict):
            continue
        if e.get("type") == "tool_use":
            name = e.get("name") or ""
            entry = {"name": name,
                     "args": _normalize_args(name, e.get("input") or e.get("arguments")),
                     "ok": None, "refused": False}
            trace.append(entry)
            if e.get("id"):
                by_id[e["id"]] = entry
        elif e.get("type") == "tool_result":
            content = (e.get("content") if e.get("content") is not None
                       else e.get("result"))
            ok = _result_ok(content)
            refused = _result_refused(content)
            tid = e.get("tool_use_id")
            target = by_id[tid] if (tid and tid in by_id) else (trace[-1] if trace else None)
            if target is not None:
                target["ok"] = ok
                target["refused"] = refused
    return trace


# ───────────────────────── render validation ─────────────────────────

def _find_bridge() -> Path | None:
    for cand in _DEFAULT_BRIDGES:
        if cand and Path(cand).exists():
            return Path(cand)
    return None


def render_validate(transcript: list[dict]) -> dict:
    """Replay the raw transcript through the widget renderer via the node
    bridge. Degrades to `{"skipped": …}` when node or the bridge is absent so
    the Python loop never hard-fails on a missing widget tree."""
    bridge = _find_bridge()
    if bridge is None:
        return {"skipped": "render bridge not found (set FSRPB_RENDER_BRIDGE)"}
    try:
        proc = subprocess.run(
            ["node", str(bridge), "-"],
            input=json.dumps({"transcript": transcript}),
            capture_output=True, text=True, timeout=60,
        )
    except FileNotFoundError:
        return {"skipped": "node not on PATH"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "violations": ["render bridge timed out"]}
    try:
        out = json.loads(proc.stdout or "{}")
    except Exception:  # noqa: BLE001
        return {"ok": False, "violations": [f"bridge non-JSON: {proc.stdout[:200]}"]}
    return out


# ───────────────────────── scoring + verdict ─────────────────────────

_YAML_FENCE_RE = re.compile(r"```ya?ml\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)


def _extract_yaml(final_text: str) -> str:
    """Pull the last fenced ```yaml block out of the agent's final answer so a
    build run can be scored (compile/verify + B4 build_fidelity). Empty when
    the run authored no playbook (e.g. a pure investigation)."""
    blocks = _YAML_FENCE_RE.findall(final_text or "")
    return blocks[-1].strip() if blocks else ""


def _offer_card(transcript: list[dict]) -> dict | None:
    """First `playbook_offer` card in the transcript (the built playbook the
    agent staged for save), or None. Handles both a top-level event and one
    nested under an event's `card`."""
    for e in transcript or []:
        if not isinstance(e, dict):
            continue
        if e.get("type") == "playbook_offer" and e.get("ops_summary") is not None:
            return e
        card = e.get("card")
        if isinstance(card, dict) and card.get("type") == "playbook_offer":
            return card
    return None


def attach_build_fidelity(score: dict | None, result: dict) -> dict | None:
    """B4: when the run produced a `playbook_offer` card (a triage→build
    chain), grade `build_fidelity` (ops the built playbook automates vs ops the
    investigation exercised) and fold it into the score levels so the verdict
    shows it. No-op when no playbook was offered."""
    from evals import scoring
    card = _offer_card(result.get("transcript") or [])
    if card is None:
        return score
    built_ops = scoring.ops_from_offer_card(card)
    fidelity = scoring.score_build_fidelity(result["trace"], "", built_ops=built_ops)
    if score is None:
        score = {"levels": {}, "score": 0, "max": 0, "fraction": 0.0}
    score["levels"]["build_fidelity"] = fidelity
    # Recompute the counted aggregate so the fraction reflects the new gate.
    counted = [v for v in score["levels"].values()
               if not v.get("skipped") and not v.get("informational")]
    score["score"] = sum(1 for v in counted if v.get("passed"))
    score["max"] = len(counted)
    score["fraction"] = (score["score"] / score["max"]) if score["max"] else 0.0
    return score


def score_result(task, trace: list[dict], final_text: str) -> dict:
    """Run the existing scoring gates over the captured trace. A build run's
    emitted ```yaml block is extracted and scored (compile/verify +
    B4 `build_fidelity` ops-overlap); investigation mode demotes the authoring
    tiers and force-skips fidelity, so passing the YAML there is harmless."""
    from evals import scoring
    return scoring.score(
        yaml_text=_extract_yaml(final_text),
        mode=task.mode,
        required_facts=task.required_facts,
        forbidden_facts=task.forbidden_facts,
        investigation_quality=task.investigation_quality,
        trace=trace,
        final_text=final_text,
    )


def _gate_lines(score: dict) -> list[tuple[str, bool, str, str]]:
    """Flatten the scoring levels into (name, passed, detail, lever) rows,
    skipping informational/skipped levels."""
    rows = []
    for name, lv in (score.get("levels") or {}).items():
        if lv.get("skipped") or lv.get("informational"):
            continue
        passed = bool(lv.get("passed"))
        lever = "" if passed else lever_for(name)
        # recall scorer raises forbidden hits under its own level; surface the
        # <forbidden> lever when that's the cause.
        if name == "investigation_recall" and lv.get("forbidden_hit"):
            lever = lever_for("<forbidden>")
        rows.append((name, passed, lv.get("detail", ""), lever))
    return rows


def print_verdict(result: dict, score: dict | None, render: dict,
                  *, scenario: str, log=print) -> bool:
    """One-screen verdict. Returns True when everything that was gated passed."""
    log("=" * 72)
    log(f"VERDICT  scenario={scenario}  session={result['session']}  "
        f"{result['elapsed']}s  stop_reason={result['stop_reason']}")
    log(f"  trace: {len(result['trace'])} tool call(s) -> "
        f"{[c['name'] for c in result['trace']]}")

    all_ok = True
    if score is not None:
        rows = _gate_lines(score)
        for name, passed, detail, lever in rows:
            flag = "PASS" if passed else "FAIL"
            if not passed:
                all_ok = False
            line = f"  [{flag}] {name:<32} {detail}"
            log(line)
            if lever:
                log(f"         ↳ lever: {lever}")
        log(f"  score: {score.get('score')}/{score.get('max')} "
            f"(fraction {score.get('fraction', 0):.2f})")
    else:
        log("  (ad-hoc scenario — no fixture facts, scoring skipped)")

    if render.get("skipped"):
        log(f"  [SKIP] render               {render['skipped']}")
    else:
        rok = bool(render.get("ok"))
        if not rok:
            all_ok = False
        log(f"  [{'PASS' if rok else 'FAIL'}] render               "
            f"{render.get('events', '?')} event(s); "
            f"{len(render.get('violations') or [])} violation(s)")
        for v in (render.get("violations") or [])[:10]:
            log(f"         ↳ {v}")
        if not rok:
            log(f"         ↳ lever: {lever_for('offer_timing')}  "
                "(or widget fsrPbRender contract drift)")
    log("=" * 72)
    return all_ok


# ───────────────────────── A2: capture fixture ─────────────────────────

def _is_external_ip(s: str) -> bool:
    try:
        ip = ipaddress.ip_address(s)
        return not (ip.is_private or ip.is_loopback or ip.is_link_local)
    except ValueError:
        return False


_INDICATOR_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_TI_CONNECTORS = ("virustotal", "shodan", "abuseipdb", "ipqualityscore")


def _next_task_index() -> int:
    mx = 0
    for p in TASKS_DIR.glob("*.json"):
        m = re.match(r"(\d+)_", p.name)
        if m:
            mx = max(mx, int(m.group(1)))
    return mx + 1


def propose_fixture(result: dict, *, name: str, prompt: str) -> dict:
    """Turn a captured run into a PROPOSED investigation fixture + golden trace.
    Heuristic and human-reviewed — never auto-committed.

    - required_facts: the record pull (get_record) + each external-IP enrichment
      the agent performed, using the same matcher vocabulary scoring consumes.
    - forbidden_facts: external-TI lookups against any RFC1918 source IP seen
      (the pivot-discipline rule the existing fixtures encode).
    - quality: tool_budget_max sized to the observed call count (+small slack),
      require_deliverable iff a deliverable card was actually staged.
    """
    trace = result["trace"]
    required: list[dict] = []
    internal_ips: set[str] = set()
    external_ips: set[str] = set()

    for c in trace:
        blob = json.dumps(c.get("args", {}), default=str)
        for ip in _INDICATOR_RE.findall(blob):
            (external_ips if _is_external_ip(ip) else internal_ips).add(ip)
        if c["name"] == "get_record":
            uuid = (c.get("args") or {}).get("uuid")
            if uuid:
                required.append({"tool": "get_record", "args_contains": [uuid],
                                 "label": "pull the originating alert"})

    for ip in sorted(external_ips):
        if any(c["name"] == "run_op" and ip in json.dumps(c.get("args", {}))
               for c in trace):
            required.append({"tool": "run_op", "args_contains": [ip],
                             "label": f"enrich the EXTERNAL indicator {ip}"})

    forbidden = [
        {"tool": "run_op", "connector": conn, "args_contains": [ip],
         "label": f"{conn} on internal RFC1918 source {ip}"}
        for ip in sorted(internal_ips) for conn in _TI_CONNECTORS
    ]

    deliverable = any(c["name"] in (
        "emit_action_card", "emit_choice_card", "emit_capability_gap_card")
        for c in trace)
    n = len(trace)

    fixture = {
        "name": name,
        "mode": "investigation",
        "prompt": prompt,
        "required_facts": required,
        "investigation_quality": {
            "tool_budget_max": max(n + 2, 6),
            "max_param_retries": 2,
            "require_deliverable": deliverable,
        },
        "forbidden_facts": forbidden,
        "notes": f"PROPOSED from a chat-drive capture (session {result['session']}). "
                 "Review required_facts/forbidden_facts before committing.",
    }
    golden = {
        "fixture": name,
        "captured": time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()),
        "model": "chat_turn-live",
        "stop_reason": result["stop_reason"],
        "recall": None,
        "trace": [{"name": c["name"], "args": c.get("args", {}), "ok": c.get("ok")}
                  for c in trace],
    }
    return {"fixture": fixture, "golden": golden}


def write_capture(proposal: dict, *, log=print) -> dict:
    """Write the proposed fixture + golden to disk (next free task index) and
    return the paths. The fixture is also echoed to stdout for review."""
    idx = _next_task_index()
    slug = proposal["fixture"]["name"]
    task_path = TASKS_DIR / f"{idx:02d}_{slug}.json"
    golden_path = GOLDEN_DIR / f"{slug}.json"
    task_path.write_text(json.dumps(proposal["fixture"], indent=2) + "\n")
    golden_path.write_text(json.dumps(proposal["golden"], indent=2) + "\n")
    log("\n--- PROPOSED FIXTURE (review before committing) ---")
    log(json.dumps(proposal["fixture"], indent=2))
    log(f"\nwrote fixture -> {task_path.relative_to(REPO_ROOT)}")
    log(f"wrote golden  -> {golden_path.relative_to(REPO_ROOT)}")
    return {"task_path": str(task_path), "golden_path": str(golden_path)}


# ───────────────────────── orchestration ─────────────────────────

def run(*, task_name: str | None, message: str | None, intent: str,
        record: Any = None, version: str, config: str,
        capture_fixture: bool, as_json: bool, log=print) -> int:
    from evals.tasks import load_tasks

    task = None
    if task_name:
        matches = load_tasks([task_name])
        if not matches:
            log(f"no task fixture named {task_name!r}")
            return 2
        task = matches[0]
        message = task.prompt
        intent = task.mode if task.mode in ("triage", "build") else intent
        # investigation/refuse fixtures still drive triage intent
        if task.mode == "investigation":
            intent = "triage"
        scenario = task.name
    else:
        if not message:
            log("need --task <name> or --message <text>")
            return 2
        scenario = "ad-hoc"

    try:
        result = drive_scenario(message, intent, record=record, version=version,
                                config=config, log=log)
    except Exception as exc:  # noqa: BLE001 — report cleanly, never hang
        log(f"!! drive failed: {exc}")
        return 1

    score = score_result(task, result["trace"], result["final_text"]) if task else None
    score = attach_build_fidelity(score, result)
    render = render_validate(result["transcript"])
    ok = print_verdict(result, score, render, scenario=scenario, log=log)

    # Persist the run (same dir family as calibrate, so an A5 trend can aggregate).
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    summary = {
        "stamp": stamp, "scenario": scenario, "session": result["session"],
        "stop_reason": result["stop_reason"], "elapsed": result["elapsed"],
        "trace": [{"name": c["name"], "args": c.get("args"), "ok": c.get("ok")}
                  for c in result["trace"]],
        "final_text": result["final_text"],
        "render": render,
        "score": ({"fraction": score.get("fraction"),
                   "levels": {k: {"passed": v.get("passed"),
                                  "detail": v.get("detail"),
                                  "lever": (lever_for(k) if not v.get("passed")
                                            and not v.get("skipped")
                                            and not v.get("informational") else None)}
                              for k, v in (score.get("levels") or {}).items()}}
                  if score else None),
        "passed": ok,
    }
    (RUN_DIR / f"chatdrive_{stamp}.summary.json").write_text(
        json.dumps(summary, indent=2))

    if capture_fixture:
        if task:
            log("!! --capture-fixture is for ad-hoc --message runs; the "
                "scenario is already a fixture. Skipping capture.")
        else:
            slug = re.sub(r"[^a-z0-9]+", "_", (message or "")[:40].lower()).strip("_")
            proposal = propose_fixture(result, name=f"invest_{slug}",
                                       prompt=message or "")
            write_capture(proposal, log=log)

    if as_json:
        log(json.dumps(summary, indent=2))
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="chat-drive", description=__doc__)
    ap.add_argument("--task", default=None, help="existing task fixture name")
    ap.add_argument("--message", default=None, help="ad-hoc scenario message")
    ap.add_argument("--intent", default="triage", help="triage | build")
    ap.add_argument("--record", default=None,
                    help="optional record context (JSON string or path)")
    ap.add_argument("--version", default=DEFAULT_VERSION)
    ap.add_argument("--config", default=DEFAULT_CONFIG)
    ap.add_argument("--capture-fixture", action="store_true",
                    help="(A2) propose a tasks/*.json + golden from this run")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    record = args.record
    if record:
        p = Path(record)
        record = json.loads(p.read_text()) if p.exists() else json.loads(record)

    return run(task_name=args.task, message=args.message, intent=args.intent,
               record=record, version=args.version, config=args.config,
               capture_fixture=args.capture_fixture, as_json=args.json)


if __name__ == "__main__":
    sys.exit(main())
