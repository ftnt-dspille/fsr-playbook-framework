"""Eval harness — task x model matrix runner.

Orchestrates: for each task, prompt each model, extract a YAML block,
score it, and emit a structured matrix. Everything below the LLM call
is deterministic, so the same task corpus can be rerun against new
models without changing the scoring.
"""
from __future__ import annotations

import json
import time
from typing import Any

from agent import load_system_prompt
from evals.providers import (ProviderFn, extract_yaml, get_provider)
from evals.scoring import score
from evals.tasks import Task, load_tasks


def _gold_lookup_for(tasks: list[Task]):
    """Build a `prompt -> gold_yaml_text` map for the gold provider."""
    by_prompt = {t.prompt: t.gold_yaml_text() for t in tasks}
    return lambda prompt: by_prompt.get(prompt)


def _compile_gold_json(yaml_text: str) -> dict[str, Any] | None:
    from mcp_server import compile_yaml
    out = compile_yaml(yaml_text)
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
            yaml_text = extract_yaml(raw)
            scored = score(
                yaml_text,
                gold_json=gold_json_by_task.get(t.name),
                live=live,
            )
            rows.append({
                "model": model_name,
                "task": t.name,
                "yaml": yaml_text,
                "elapsed_ms": int((time.time() - t0) * 1000),
                **scored,
            })

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
    header = f"{'model':<14} {'task':<28} L1 L2 L3 L4 gold  score  ms"
    lines.append(header)
    lines.append("-" * len(header))
    for r in matrix["rows"]:
        if "error" in r:
            lines.append(f"{r['model']:<14} {r['task']:<28} -- -- -- -- ----  "
                         f"ERR    {r.get('elapsed_ms', '-')}  ({r['error']})")
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
            f"{cell('L1')} {cell('L2')} {cell('L3')} {cell('L4')} "
            f"{cell('gold'):<4}  {score_str:<5}  {r['elapsed_ms']}"
        )
    lines.append("")
    lines.append("Per-model totals:")
    for m, s in matrix["summary"].items():
        lines.append(f"  {m:<14} {s['score']}/{s['max']} "
                     f"({s['fraction']*100:.0f}%)")
    return "\n".join(lines)
