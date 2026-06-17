"""Eval harness — task x model matrix runner.

Orchestrates: for each task, prompt each model, extract a YAML block,
score it, and emit a structured matrix. Everything below the LLM call
is deterministic, so the same task corpus can be rerun against new
models without changing the scoring.

Run archive: `save_run(matrix)` writes the matrix + a markdown report
to `store/eval_runs/<run_id>/`. `delta_vs(prior_run_id, current)` diffs
two runs cell-by-cell so a CI hook can red-flag regressions.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent import load_system_prompt
from evals.providers import (ProviderFn, extract_yaml, get_provider)
from evals.scoring import score
from evals.tasks import Task, load_tasks

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNS_DIR = REPO_ROOT / "store" / "eval_runs"


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


def run_matrix(
    *,
    model_names: list[str],
    task_names: list[str] | None = None,
    live: bool = False,
) -> dict[str, Any]:
    """Run every (task, model) cell and return a structured matrix."""
    tasks = load_tasks(task_names)
    if not tasks:
        raise SystemExit("no tasks matched")

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
        for t in tasks:
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
            try:
                raw = provider(system_prompt, t.prompt)
            except Exception as e:  # noqa: BLE001
                rows.append({
                    "model": model_name, "task": t.name,
                    "error": f"provider call: {e!r}",
                    "elapsed_ms": int((time.time() - t0) * 1000),
                    "score": 0, "max": 0, "fraction": 0.0,
                    "levels": {},
                })
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
            yaml_text = extract_yaml(final_text)
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
            )
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
                if usage is not None:
                    row["usage"] = usage
            rows.append(row)

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
        "tasks": [t.name for t in tasks],
        "models": list(model_names),
        "rows": rows,
        "summary": summary,
    }


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
    # final call return ready) — distinct from `verified`.
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
    """Persist the matrix under store/eval_runs/<run_id>/.

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
        f"Eval delta — prior {d.get('prior_run','?')} → "
        f"current {d.get('current_run','?')}",
        "",
        f"{'model':<14} {'task':<28} {'before':>7} {'after':>7}  status",
        "-" * 70,
    ]
    sym = {"improved": "+", "regressed": "-", "same": "=",
           "new": "*", "removed": "x"}
    for c in d["cells"]:
        b = c.get("before")
        a = c.get("after")
        lines.append(
            f"{c['model']:<14} {c['task']:<28} "
            f"{(f'{b*100:.0f}%' if b is not None else '   --'):>7} "
            f"{(f'{a*100:.0f}%' if a is not None else '   --'):>7}  "
            f"{sym.get(c['status'],'?')} {c['status']}"
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
                f"| `{r['model']}` | `{r['task']}` | ERR | – | – | – | "
                f"– | – | – | – | {r.get('elapsed_ms','-')} |"
            )
            continue
        lv = r.get("levels", {})

        def cell(level, _lv=lv):
            v = _lv.get(level, {})
            if v.get("skipped"):
                return "–"
            return "✓" if v.get("passed") else "✗"

        iters = lv.get("verify_iterations_until_ready", {}).get("iterations")
        iters_str = "–" if lv.get(
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
            f"- **{m}** — {s['score']}/{s['max']} "
            f"({s['fraction']*100:.0f}%)"
        )
    return "\n".join(lines) + "\n"
