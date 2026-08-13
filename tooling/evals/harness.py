"""Eval harness -- task x model matrix runner.

Orchestrates: for each task, prompt each model, extract a YAML block,
score it, and emit a structured matrix. Everything below the LLM call
is deterministic, so the same task corpus can be rerun against new
models without changing the scoring.

Run archive: `save_run(matrix)` writes the matrix + a markdown report
to `data/eval_runs/<run_id>/`. `delta_vs(prior_run_id, current)` diffs
two runs cell-by-cell so a CI hook can red-flag regressions.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent import load_system_prompt
from evals.providers import (ProviderFn, get_provider,
                             set_tool_slice)
from evals.scoring import delivered_yaml, score
from evals.tasks import Task, load_tasks

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNS_DIR = REPO_ROOT / "data" / "eval_runs"
CRASH_LOG = RUNS_DIR / ".in_progress_rows.jsonl"
"""Rows of the run currently executing. Moved into the run dir on success, so
its presence means the last run died before `save_run`."""


# The Phase 1.4 control arm. Deliberately says nothing about *how* to work --
# no research mandate, no authoring workflow, no persona. If a run request
# reaches `run_playbook` under this and not under the build prompt, the build
# prompt is what's overriding tool selection, and the fix is guidance, not the
# tool surface.
_NEUTRAL_PROMPT = (
    "You are a FortiSOAR assistant. You have tools available. Read the "
    "user's request, decide which tool actually answers it, and call that "
    "tool. Do not narrate a plan instead of acting."
)


def _prompt_for(task: Task, default: str) -> str:
    """Resolve the system prompt this task runs under.

    `prompt_variant` is None for every pre-existing fixture, which keeps them
    on the harness default they were baselined against."""
    variant = task.prompt_variant
    if not variant:
        return default
    if variant == "neutral":
        return _NEUTRAL_PROMPT
    from fsr_playbooks.llm.intents import load_intent_prompt  # noqa: PLC0415
    return load_intent_prompt(variant)


def _user_message_for(task: Task) -> str:
    """The user turn the model actually sees.

    A repair fixture's prompt is only half the ask -- the other half is the
    broken playbook. Appending it here (rather than pasting it into every
    fixture's prompt string) keeps the broken YAML in one file that the
    scorer also diffs against, so the prompt and the `before` can never
    drift apart.
    """
    broken = task.broken_yaml_text()
    if not broken:
        return task.prompt
    return f"{task.prompt}\n\nHere is the playbook:\n\n```yaml\n{broken}\n```"


def _gold_lookup_for(tasks: list[Task]):
    """Build a `prompt -> gold_yaml_text` map for the gold provider."""
    by_prompt = {t.prompt: t.gold_yaml_text() for t in tasks}
    return lambda prompt: by_prompt.get(prompt)


def _compile_gold_json(yaml_text: str) -> dict[str, Any] | None:
    from fsr_playbooks.mcp_server import compile_yaml
    out = compile_yaml(yaml_text, verbose=True)
    if not out.get("ok"):
        return None
    try:
        return json.loads(out["json"])
    except Exception:  # noqa: BLE001
        return None


def _progress(model: str, i: int, n: int, task: str, row: dict[str, Any]) -> None:
    """Emit one per-fixture line to STDERR as the matrix runs.

    A full-corpus run on a free gateway is minutes per fixture, and the
    harness otherwise prints nothing until the very end -- so a slow run and
    a hung one look identical. One 65-minute run was killed on that ambiguity
    having proven nothing.

    stderr, not stdout, so `--json` output stays machine-parseable.
    """
    # Report the SCORE, never the word "fail". `score` counts quality gates
    # passed (draft/verified/wiring_resolves/...); `max` counts those that
    # applied. 5/8 is a graded authoring result, not a broken run -- calling
    # it FAIL reads as a regression and invites exactly that misreading.
    # `ERR` is the one genuinely different outcome: the provider call raised.
    if "error" in row:
        mark = "ERR (provider call raised)"
    elif not row.get("max"):
        # max=0 = no gate applied. gold/echo make no terminal tool call, so
        # every tool_selection fixture scores 0/0 for them.
        mark = "n/a (nothing scored)"
    elif row["score"] == row["max"]:
        mark = f"{row['score']}/{row['max']} all gates"
    else:
        mark = f"{row['score']}/{row['max']} gates"
    # An unservable row is a real low score, and printing it bare invites the
    # reading that cost a session: "the agent scored 3/7 on investigation".
    # It scored 3/7 on an environment missing the tools the fixture requires.
    uns = row.get("unservable")
    if isinstance(uns, dict) and uns.get("missing_tools"):
        mark += f"  [UNSERVABLE: no {', '.join(uns['missing_tools'])}]"
    secs = row.get("elapsed_ms", 0) / 1000.0
    print(f"  [{model} {i}/{n}] {task} -- {mark} ({secs:.1f}s)",
          file=sys.stderr, flush=True)


def _checkpoint(path: Path | None, row: dict[str, Any]) -> None:
    """Append one finished row to the crash log, flushed to disk immediately.

    A long run holds everything in memory until `save_run` writes at the very
    end, so ANY failure -- a crash in the last task, a kill, an OOM -- discards
    every completed result. This is the cheap insurance: one JSON object per
    line, fsync'd, so a dead run can still be read back with `recover_rows`.

    Never raises. A checkpoint that can take the run down with it is worse than
    no checkpoint at all.
    """
    if path is None:
        return
    try:
        with path.open("a") as fh:
            fh.write(json.dumps(row, default=str) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
    except Exception:  # noqa: BLE001
        pass


def recover_rows(path: Path | str) -> list[dict[str, Any]]:
    """Read back the rows a crashed run checkpointed.

    Tolerates a torn final line -- the process may have died mid-write.
    """
    rows: list[dict[str, Any]] = []
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # torn tail from a hard kill
    return rows


def register_triage_tools_if_available() -> str:
    """Pull in the connector's triage tools when its repo is importable.

    `get_record`, `search_module_records` and the SIEM/FAZ hunt tools live in
    the connector's `fsr_soc_triage.registry`, which mutates the framework's
    global REGISTRY at import (the "Option-A posture" `intents.py` documents).
    Without them five investigation fixtures name tools nothing registers and
    score zero while the agent works competently -- measured 2026-08-13 as
    3/7 with recall 0.00.

    Returns the substrate name, which the matrix records. Two rules follow
    from it and both are load-bearing:

      - a run is only comparable to another run with the SAME substrate;
      - a registration that RAISES is reported, never swallowed. A silently
        half-registered registry is the "gate that selects zero files" shape
        -- it looks exactly like a passing one.

    `FSR_CONNECTOR_REPO` may point at the connector checkout; otherwise this
    relies on it already being importable.
    """
    try:
        from fsr_playbooks.llm.tools import REGISTRY
    except Exception:  # noqa: BLE001
        return "unknown (framework registry unreadable)"

    if "get_record" in REGISTRY:
        return "framework+connector (already registered)"

    repo = os.environ.get("FSR_CONNECTOR_REPO", "").strip()
    if repo:
        # `fsr_soc_triage` sits one level down, inside the connector PACKAGE
        # dir -- pointing at the repo root is the natural thing to pass and
        # on its own imports nothing, so accept both and let the caller be
        # right either way.
        for cand in (Path(repo) / "connector-fsr-soc-assistant", Path(repo)):
            if (cand / "fsr_soc_triage").is_dir() and str(cand) not in sys.path:
                # The connector's own modules must PRECEDE the framework on
                # the path or its shadowing copies resolve to the wrong one.
                sys.path.insert(0, str(cand))
                break

    try:
        from fsr_soc_triage.registry import (  # type: ignore[import-not-found]
            register_triage_tools,
        )
    except ImportError:
        return "framework-only (no fsr_soc_triage)"

    try:
        register_triage_tools()
    except Exception as exc:  # noqa: BLE001
        # Loud, not silent: a partial registration would leave some fixtures
        # servable and others not, with nothing saying which.
        return f"framework-only (register_triage_tools raised: {exc!r})"

    if "get_record" not in REGISTRY:
        return "framework-only (registration ran but added no record tools)"
    return "framework+connector"


def run_matrix(
    *,
    model_names: list[str],
    task_names: list[str] | None = None,
    live: bool = False,
    checkpoint_path: Path | None = None,
) -> dict[str, Any]:
    """Run every (task, model) cell and return a structured matrix.

    `checkpoint_path` appends each finished row as it lands, so a run that
    dies before `save_run` is still recoverable via `recover_rows`.
    """
    tasks = load_tasks(task_names)
    if not tasks:
        raise SystemExit("no tasks matched")

    # EVAL_OFFLINE=1 swaps the live seam for the simulated client and strips
    # the FSR_* credentials, so a degrading appliance can no longer score as
    # an agent regression. Done before any provider starts: a client cached
    # mid-run would outlive the swap.
    from evals import offline as _offline
    offline_run = _offline.enabled()
    record_substrate = "live" if not offline_run else "empty"
    if offline_run:
        _offline.install()
        record_substrate = _offline.active_box_name()
        print(f"  offline: tools bound to {_offline.active_client_name()}, "
              f"records from {record_substrate}", file=sys.stderr, flush=True)

    # Which TOOL SET scored this run. The alert/incident hunt tools
    # (get_record, search_module_records, siem_*, faz_*) are registered by the
    # connector, not by this repo -- so the same fixture measures different
    # things depending on whether the connector is importable, and five
    # investigation fixtures cannot score at all without it. Recorded rather
    # than assumed: a run comparing framework-only rows against
    # framework+connector rows is comparing environments, not agents.
    substrate = register_triage_tools_if_available()
    print(f"  tools: {substrate}", file=sys.stderr, flush=True)

    gold_lookup = _gold_lookup_for(tasks)
    system_prompt = load_system_prompt()

    gold_json_by_task: dict[str, dict[str, Any] | None] = {}
    for t in tasks:
        gy = t.gold_yaml_text()
        gold_json_by_task[t.name] = _compile_gold_json(gy) if gy else None

    rows: list[dict[str, Any]] = []
    for model_name in model_names:
        try:
            provider: ProviderFn = get_provider(model_name,
                                                gold_lookup=gold_lookup)
        except Exception as e:  # noqa: BLE001
            for t in tasks:
                rows.append({
                    "model": model_name, "task": t.name,
                    "error": f"provider init: {e!r}",
                    "score": 0, "max": 0, "fraction": 0.0,
                    "levels": {},
                })
            continue
        for ti, t in enumerate(tasks, 1):
            t0 = time.time()
            # HITL Phase 3: pin per-task approval policy + reset the
            # dispatch wrapper's audit log so the gate scores only this
            # task's escalation behavior. No-op when the studio tools
            # module isn't on sys.path (classic providers).
            try:
                from fsr_playbooks.llm.tools import (  # type: ignore
                    clear_audit_log as _clr, set_eval_policy as _set_pol,
                )
                _set_pol(t.approval_policy)
                _clr()
            except Exception:
                pass
            set_tool_slice(t.tool_slice)
            try:
                raw = provider(_prompt_for(t, system_prompt),
                               _user_message_for(t))
            except Exception as e:  # noqa: BLE001
                _err_row = {
                    "model": model_name, "task": t.name,
                    "error": f"provider call: {e!r}",
                    "elapsed_ms": int((time.time() - t0) * 1000),
                    "score": 0, "max": 0, "fraction": 0.0,
                    "levels": {},
                }
                rows.append(_err_row)
                _checkpoint(checkpoint_path, _err_row)
                _progress(model_name, ti, len(tasks), t.name, _err_row)
                continue
            # Agentic providers return a dict {text, trace, turns}; classic
            # providers return a string. Detect and route.
            if isinstance(raw, dict):
                final_text = raw.get("text", "")
                trace = raw.get("trace")
                turns = raw.get("turns")
                usage = raw.get("usage")
                audit = raw.get("audit")
            else:
                final_text = raw or ""
                trace = None
                turns = None
                usage = None
                audit = None
            # Score the playbook the turn DELIVERED (offer card / last gated
            # doc), falling back to a fenced block in chat. Reading the final
            # text alone punished every agent that obeyed
            # `emit_playbook_offer`'s "do not print YAML at the analyst".
            yaml_text = delivered_yaml(final_text, trace)
            try:
                scored = score(
                    yaml_text,
                    gold_json=gold_json_by_task.get(t.name),
                    live=live,
                    trace=trace,
                    final_text=final_text,
                    audit=audit,
                    expected_approvals=t.expected_approvals,
                    mode=t.mode,
                    required_facts=t.required_facts,
                    forbidden_facts=t.forbidden_facts,
                    investigation_quality=t.investigation_quality,
                    terminal_tool=t.terminal_tool,
                    ir_assertions=t.ir_assertions,
                    before_yaml=t.broken_yaml_text(),
                    user_message=_user_message_for(t),
                )
            except Exception as e:  # noqa: BLE001
                # Scoring compiles the delivered YAML, so it can raise for
                # reasons that have nothing to do with this task -- a transient
                # `sqlite3.OperationalError: disk I/O error` on the reference DB
                # once killed a 74-minute run at task 34/36 and, because
                # `save_run` only writes after ALL tasks finish, took every
                # completed result with it. One task must not be able to
                # discard the run: record it and keep going.
                _err_row = {
                    "model": model_name, "task": t.name,
                    "error": f"scoring: {e!r}",
                    "elapsed_ms": int((time.time() - t0) * 1000),
                    "score": 0, "max": 0, "fraction": 0.0,
                    "levels": {},
                }
                rows.append(_err_row)
                _checkpoint(checkpoint_path, _err_row)
                _progress(model_name, ti, len(tasks), t.name, _err_row)
                continue
            row = {
                "model": model_name,
                "task": t.name,
                "yaml": yaml_text,
                "elapsed_ms": int((time.time() - t0) * 1000),
                **scored,
            }
            if turns is not None:
                row["turns"] = turns
                row["tool_calls"] = len(trace or [])
                row["trace"] = trace or []
                # Persist every input `score()` took, so `replay_run` re-grades
                # the row identically. Without the audit log the approval gate
                # skips on replay and the row silently loses a counted gate --
                # a replay that scores differently from the run it replays is
                # a lying instrument.
                row["audit"] = audit or []
                row["final_text"] = final_text or ""
                if usage is not None:
                    row["usage"] = usage
            rows.append(row)
            _checkpoint(checkpoint_path, row)
            _progress(model_name, ti, len(tasks), t.name, row)
    set_tool_slice(None)

    summary: dict[str, dict[str, float]] = {}
    for m in model_names:
        m_rows = [r for r in rows if r["model"] == m]
        s = sum(r["score"] for r in m_rows)
        mx = sum(r["max"] for r in m_rows)
        summary[m] = {
            "score": s, "max": mx,
            "fraction": (s / mx) if mx else 0.0,
        }

    return {
        "live": live,
        # Which substrate produced these numbers. A run that does not say so
        # invites its rows being compared against ones taken on a box.
        "offline": offline_run,
        # ...and which TOOL SET. `offline` says where the bytes came from;
        # this says what the agent was even able to call. Five investigation
        # fixtures score zero without the connector's triage tools, so a
        # cross-substrate comparison reads a registry gap as a regression.
        "tool_substrate": substrate,
        # ...and which RECORDS it could read. `empty` means the record surface
        # answered every read empty-but-ok, which is indistinguishable from a
        # box holding nothing -- the investigation rows are unservable and
        # their zeros are the harness's, not the agent's.
        "record_substrate": record_substrate,
        "tasks": [t.name for t in tasks],
        "models": list(model_names),
        "rows": rows,
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# Model screening -- rule out inconsistent models, then pick the cheapest
# survivor. A model that passes 2 runs in 3 is not "mostly working"; it is
# unusable in a product where the analyst only gets one attempt. So the bar
# is unanimity across repeats, not an average.
# ---------------------------------------------------------------------------

def screen_models(
    *,
    model_names: list[str],
    task_names: list[str] | None = None,
    repeats: int = 3,
    live: bool = False,
) -> dict[str, Any]:
    """Run the matrix `repeats` times and report per-cell pass rates.

    Verdict per model:
      `consistent` -- every fixture passed every repeat
      `flaky`      -- at least one fixture passed sometimes (the dangerous
                      case: it demos fine and fails in front of a customer)
      `failing`    -- at least one fixture never passed
    """
    runs = []
    for _r in range(1, repeats + 1):
        print(f"-- repeat {_r}/{repeats} --", file=sys.stderr, flush=True)
        runs.append(run_matrix(model_names=model_names,
                               task_names=task_names, live=live))
    tasks = runs[0]["tasks"]
    cells: dict[str, dict[str, dict[str, Any]]] = {}
    for m in model_names:
        cells[m] = {}
        for t in tasks:
            passes, errors = 0, 0
            for r in runs:
                row = next((x for x in r["rows"]
                            if x["model"] == m and x["task"] == t), None)
                if row is None or "error" in row:
                    errors += 1
                    continue
                # A cell passes when every counted gate passed. For a
                # tool_selection fixture that is exactly the terminal call.
                if row.get("max") and row["score"] == row["max"]:
                    passes += 1
            cells[m][t] = {"passes": passes, "of": repeats, "errors": errors}
    verdicts: dict[str, str] = {}
    for m in model_names:
        rates = [c["passes"] for c in cells[m].values()]
        if all(p == repeats for p in rates):
            verdicts[m] = "consistent"
        elif any(p == 0 for p in rates):
            verdicts[m] = "failing"
        else:
            verdicts[m] = "flaky"
    return {"repeats": repeats, "tasks": tasks, "models": list(model_names),
            "cells": cells, "verdicts": verdicts, "runs": runs}


def render_screen(screen: dict[str, Any]) -> str:
    reps = screen["repeats"]
    lines = [f"Model screening -- {reps} repeat(s), "
             f"{len(screen['tasks'])} fixture(s)", ""]
    width = max([len(t) for t in screen["tasks"]] + [8])
    header = f"{'fixture':<{width}}  " + "  ".join(
        f"{m[:18]:>18}" for m in screen["models"])
    lines += [header, "-" * len(header)]
    for t in screen["tasks"]:
        row = f"{t:<{width}}  "
        row += "  ".join(
            f"{(str(screen['cells'][m][t]['passes']) + '/' + str(reps)):>18}"
            for m in screen["models"])
        lines.append(row)
    lines += ["", "Verdict:"]
    for m in screen["models"]:
        lines.append(f"  {m:<24} {screen['verdicts'][m]}")
    lines += ["",
              "A flaky model is not a cheaper consistent one -- the analyst "
              "gets one attempt."]
    return "\n".join(lines)


def render_text(matrix: dict[str, Any]) -> str:
    """Compact human-readable summary for the CLI."""
    lines = []
    lines.append(f"Eval matrix (live={matrix['live']}, "
                 f"{len(matrix['tasks'])} tasks x "
                 f"{len(matrix['models'])} models)")
    lines.append("")
    # Columns:
    #   draft  verified  live   example | vCalled vReady  score  ms
    # `draft` / `verified` / `live` are the three confidence tiers;
    # `example` is the orthogonal byte-equal check (matches the
    # hand-curated reference YAML in /examples/); the verify-behavior
    # columns measure agent discipline (did it call verify, did the
    # final call return ready) -- distinct from `verified`.
    header = (f"{'model':<14} {'task':<28} "
              f"draft verified live example  vCalled vReady  score  ms")
    lines.append(header)
    lines.append("-" * len(header))
    for r in matrix["rows"]:
        if "error" in r:
            lines.append(
                f"{r['model']:<14} {r['task']:<28} "
                f"---  ---      ---  ----    --       --      "
                f"ERR    {r.get('elapsed_ms', '-')}  ({r['error']})"
            )
            continue
        lv = r["levels"]

        def cell(level, _lv=lv):
            v = _lv.get(level, {})
            if v.get("skipped"):
                return "--"
            return "OK" if v.get("passed") else "X "

        score_str = f"{r['score']}/{r['max']}"
        lines.append(
            f"{r['model']:<14} {r['task']:<28} "
            f"{cell('draft'):<5} {cell('verified'):<8} "
            f"{cell('live_tested'):<4} {cell('matches_example'):<7} "
            f"{cell('verify_called_before_submit'):<8} "
            f"{cell('final_verify_ready_to_push'):<7} "
            f"{score_str:<5}  {r['elapsed_ms']}"
        )
    lines.append("")
    lines.append("Per-model totals:")
    for m, s in matrix["summary"].items():
        lines.append(f"  {m:<14} {s['score']}/{s['max']} "
                     f"({s['fraction']*100:.0f}%)")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Run archive + baseline delta (Phase 3C)
# ---------------------------------------------------------------------------

def _new_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def save_run(matrix: dict[str, Any], run_id: str | None = None) -> Path:
    """Persist the matrix under data/eval_runs/<run_id>/.

    Writes matrix.json + report.md. Returns the run directory."""
    run_id = run_id or _new_run_id()
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    matrix = {**matrix, "run_id": run_id, "ts": datetime.now(timezone.utc).isoformat()}
    (run_dir / "matrix.json").write_text(
        json.dumps(matrix, indent=2, default=str)
    )
    (run_dir / "report.md").write_text(_render_md(matrix))
    return run_dir


def load_run(run_id: str) -> dict[str, Any]:
    p = RUNS_DIR / run_id / "matrix.json"
    if not p.exists():
        raise FileNotFoundError(f"no eval run {run_id!r} at {p}")
    return json.loads(p.read_text())


def list_runs() -> list[str]:
    if not RUNS_DIR.exists():
        return []
    return sorted(p.name for p in RUNS_DIR.iterdir() if p.is_dir())


def _cell_key(row: dict[str, Any]) -> tuple[str, str]:
    return (row["model"], row["task"])


def delta_vs(prior: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    """Compute per-cell delta between two runs.

    For every (model, task) cell present in either run, classify as
    `improved` (score went up), `regressed` (score went down), `same`,
    or `new` / `removed`. Also returns per-model fraction deltas.

    A cell where either side's provider call RAISED is `errored`, never
    `regressed`. An ERR row scores 0/0 -- it is absent from the aggregate on
    purpose -- but its `fraction` is 0.0, so a naive comparison reads a read
    timeout as the agent falling from 100% to 0%. That already happened: every
    ERR in the 2026-08-13 session was our own client timeout firing, and Frank
    was called `failing` partly on that basis.
    """
    prior_rows = {_cell_key(r): r for r in prior.get("rows", [])}
    cur_rows = {_cell_key(r): r for r in current.get("rows", [])}
    keys = set(prior_rows) | set(cur_rows)
    cells: list[dict[str, Any]] = []
    for k in sorted(keys):
        p = prior_rows.get(k)
        c = cur_rows.get(k)
        if p and not c:
            cells.append({"model": k[0], "task": k[1], "status": "removed",
                          "before": p.get("fraction", 0.0)})
            continue
        if c and not p:
            cells.append({"model": k[0], "task": k[1], "status": "new",
                          "after": c.get("fraction", 0.0)})
            continue
        before = p.get("fraction", 0.0)
        after = c.get("fraction", 0.0)
        err = c.get("error") or p.get("error")
        if err:
            cells.append({"model": k[0], "task": k[1], "status": "errored",
                          "before": before, "after": after,
                          "detail": str(err)})
            continue
        # Same contract as `errored`, different cause: this row's required
        # tools are not registered in the process that scored it, so its
        # number measures the environment. Comparing it across runs -- or
        # worse, across REPOS, where the connector supplies those tools --
        # reads a missing registry as the agent regressing.
        uns = c.get("unservable") or p.get("unservable")
        if uns:
            miss = (uns.get("missing_tools") if isinstance(uns, dict) else None)
            cells.append({"model": k[0], "task": k[1], "status": "unservable",
                          "before": before, "after": after,
                          "detail": (f"required tools not registered: "
                                     f"{', '.join(miss)}" if miss
                                     else "required tools not registered")})
            continue
        if after > before:
            status = "improved"
        elif after < before:
            status = "regressed"
        else:
            status = "same"
        cells.append({"model": k[0], "task": k[1], "status": status,
                      "before": before, "after": after})
    per_model: dict[str, dict[str, float]] = {}
    for m in set(prior.get("summary", {})) | set(current.get("summary", {})):
        b = prior.get("summary", {}).get(m, {}).get("fraction", 0.0)
        a = current.get("summary", {}).get(m, {}).get("fraction", 0.0)
        per_model[m] = {"before": b, "after": a, "delta": a - b}
    return {
        "prior_run": prior.get("run_id"),
        "current_run": current.get("run_id"),
        "cells": cells,
        "per_model": per_model,
    }


def render_delta(d: dict[str, Any]) -> str:
    lines = [
        f"Eval delta -- prior {d.get('prior_run','?')} → "
        f"current {d.get('current_run','?')}",
        "",
        f"{'model':<14} {'task':<28} {'before':>7} {'after':>7}  status",
        "-" * 70,
    ]
    sym = {"improved": "+", "regressed": "-", "same": "=",
           "new": "*", "removed": "x", "errored": "!", "unservable": "~"}
    for c in d["cells"]:
        b = c.get("before")
        a = c.get("after")
        lines.append(
            f"{c['model']:<14} {c['task']:<28} "
            f"{(f'{b*100:.0f}%' if b is not None else '   --'):>7} "
            f"{(f'{a*100:.0f}%' if a is not None else '   --'):>7}  "
            f"{sym.get(c['status'],'?')} {c['status']}"
            + (f" -- {c['detail']}" if c.get("detail") else "")
        )
    lines.append("")
    lines.append("Per-model totals:")
    for m, s in d["per_model"].items():
        delta = s["delta"] * 100
        arrow = "↑" if delta > 0 else ("↓" if delta < 0 else "·")
        lines.append(
            f"  {m:<14} {s['before']*100:5.1f}% → {s['after']*100:5.1f}%  "
            f"{arrow} {delta:+.1f}pp"
        )
    return "\n".join(lines)


def _render_md(matrix: dict[str, Any]) -> str:
    """Markdown report saved alongside matrix.json."""
    lines = [f"# Eval run `{matrix.get('run_id','?')}`",
             "",
             f"- ts: {matrix.get('ts','')}",
             f"- live: {matrix.get('live')}",
             f"- tasks: {len(matrix.get('tasks', []))}",
             f"- models: {', '.join(matrix.get('models', []))}",
             "",
             "## Per-cell results",
             "",
             "| model | task | draft | verified | live | example | "
             "vCalled | vIters | vReady | score | ms |",
             "|---|---|---|---|---|---|---|---:|---|---:|---:|"]
    for r in matrix.get("rows", []):
        if "error" in r:
            lines.append(
                f"| `{r['model']}` | `{r['task']}` | ERR | - | - | - | "
                f"- | - | - | - | {r.get('elapsed_ms','-')} |"
            )
            continue
        lv = r.get("levels", {})

        def cell(level, _lv=lv):
            v = _lv.get(level, {})
            if v.get("skipped"):
                return "-"
            return "✓" if v.get("passed") else "✗"

        iters = lv.get("verify_iterations_until_ready", {}).get("iterations")
        iters_str = "-" if lv.get(
            "verify_iterations_until_ready", {}).get("skipped") else str(iters or 0)
        lines.append(
            f"| `{r['model']}` | `{r['task']}` | {cell('draft')} | "
            f"{cell('verified')} | {cell('live_tested')} | "
            f"{cell('matches_example')} | "
            f"{cell('verify_called_before_submit')} | "
            f"{iters_str} | "
            f"{cell('final_verify_ready_to_push')} | "
            f"{r['score']}/{r['max']} | {r['elapsed_ms']} |"
        )
    lines += ["", "## Per-model totals", ""]
    for m, s in matrix.get("summary", {}).items():
        lines.append(
            f"- **{m}** -- {s['score']}/{s['max']} "
            f"({s['fraction']*100:.0f}%)"
        )
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Replay: re-score an archived run with today's graders, no model (#127)
# ---------------------------------------------------------------------------

def replay_run(run_id: str, task_names: list[str] | None = None) -> dict[str, Any]:
    """Re-score an archived run's rows against the CURRENT scoring code.

    Generation and grading are separate problems, and only one of them needs a
    model. A saved row already carries the `yaml` the turn delivered and the
    `trace` it produced, which is every input `score()` takes -- so iterating on
    a grader (a new gate, a fixture's `ir_assertions`) does not need another
    agentic run. That distinction is the difference between a 10-minute loop and
    a sub-second one, and the slow loop is the reason grader bugs sat in the
    detail column unread.

    What replay CANNOT tell you: whether a prompt or tool-description change
    made the agent behave differently. The behaviour is frozen at capture time.
    Use it to develop graders; use a real run to measure the agent.

    Returns a matrix shaped like `run_matrix`, so every renderer, `delta_vs`
    and `save_run` work on it unchanged.
    """
    prior = load_run(run_id)
    from evals.tasks import load_tasks
    tasks = {t.name: t for t in load_tasks()}

    rows: list[dict[str, Any]] = []
    for old in prior.get("rows", []):
        if task_names and old.get("task") not in task_names:
            continue
        if "error" in old:
            # A row that never produced a candidate has nothing to re-grade.
            # Carry it through rather than dropping it: a replay that quietly
            # shrinks the corpus reads as an improvement.
            rows.append(dict(old))
            continue
        t = tasks.get(old.get("task", ""))
        if t is None:
            row = dict(old)
            row["error"] = "task no longer exists in the corpus"
            rows.append(row)
            continue
        gold_json = None
        try:
            scored = score(
                old.get("yaml") or "",
                gold_json=gold_json,
                live=False,
                trace=old.get("trace"),
                final_text=old.get("final_text") or "",
                audit=old.get("audit"),
                expected_approvals=t.expected_approvals,
                mode=t.mode,
                required_facts=t.required_facts,
                forbidden_facts=t.forbidden_facts,
                investigation_quality=t.investigation_quality,
                terminal_tool=t.terminal_tool,
                ir_assertions=t.ir_assertions,
                # Repair/enhance rows are graded against the playbook the turn
                # STARTED from. It lives in the fixture, not the row, so replay
                # can recover it -- but only if it asks. Without these two a
                # replayed repair row silently loses `no_collateral_damage`
                # and scores differently from the run it replays, which is the
                # definition of a lying instrument.
                before_yaml=t.broken_yaml_text(),
                user_message=_user_message_for(t),
            )
        except Exception as e:  # noqa: BLE001
            row = dict(old)
            row["error"] = f"scoring: {e!r}"
            rows.append(row)
            continue
        row = dict(old)
        row.update({k: scored[k] for k in ("levels", "score", "max", "fraction")})
        # Runs captured before rows carried `audit` cannot re-grade the
        # approval gate: it skips, and the row's `max` silently drops by one
        # against the run being replayed. Say so per row rather than let a
        # smaller denominator read as a cleaner result.
        if "audit" not in old and old.get("trace"):
            row.setdefault("replay_gaps", []).append(
                "appropriate_approval_requests: this run predates audit "
                "capture, so the gate is unjudgeable on replay")
        rows.append(row)

    models = sorted({r["model"] for r in rows})
    matrix: dict[str, Any] = {
        "models": models,
        "tasks": [r["task"] for r in rows if r["model"] == models[0]] if models else [],
        "rows": rows,
        "live": False,
        "replay_of": run_id,
    }
    matrix["summary"] = {
        m: {
            "score": sum(r.get("score", 0) for r in rows if r["model"] == m),
            "max": sum(r.get("max", 0) for r in rows if r["model"] == m),
        }
        for m in models
    }
    for m, s in matrix["summary"].items():
        s["fraction"] = (s["score"] / s["max"]) if s["max"] else 0.0
    gaps = sorted({g for r in rows for g in (r.get("replay_gaps") or [])})
    if gaps:
        matrix["replay_gaps"] = gaps
    return matrix
