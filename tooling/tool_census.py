"""Which tools earn their place -- a census against the RUNTIME registry.

The question this answers: of every tool the agent is actually offered, which
ones carry the four promises (P1 investigate / P2 gating / P3 reach / P4 bottle
it), which are never reached for, and which are near-duplicates worth merging.

**The denominator is the whole point, and it is not what the framework
shows.** `fsr_playbooks.llm.tools.SAFE_TOOLS` holds 39 names at import. The
connector's `register_*_tools()` appends 22 more the first time a turn runs --
record CRUD, five SIEM hunt tools, six FAZ, four FMG. So a deployed agent sees
**61**, and a census built from this repo alone is blind to 36% of the surface
-- specifically the P1/P2 half, which is the half the product leads with.
Cutting on the 39-tool view would have deleted `search_module_records` and
`get_record` as "unused" while a real triage turn calls them a dozen times.

Hence `--runtime <json>`: a dump of `SAFE_TOOLS` taken AFTER a turn has run, so
the late registrations are included. Produce one with::

    # in the connector repo, with FSRPB_DEV=1
    ./.venv/bin/python -c "
    import sys, json; sys.path.insert(0,'.')
    import fsr_playbooks.llm.tools as T
    from scripts.local_turn import local_turn
    local_turn(messages=[{'role':'user','content':'triage this'}],
               intent='triage', module='incidents', llm='fake')
    print(json.dumps(sorted(T.SAFE_TOOLS)))" > runtime_tools.json

Usage evidence is merged from every source that records what the model
actually called:

* `data/eval_runs/*/matrix.json` -- each row's `trace` carries
  `{name, args_chars, result_chars, ok, code}` per call.
* any real-loop probe JSON (`--probe`), which is the only source that can
  cover the connector-registered 22 (the eval never runs `run_agent_turn`).

**A zero here is not a verdict.** Read it with the coverage column: the
archived eval corpus contains ZERO investigation or containment tasks (25-31
route through a live appliance and were never run offline), so every P1/P2
tool reads as unused for a reason that has nothing to do with its value. The
census reports `unreachable-in-corpus` rather than folding that into "unused".
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path
from typing import Optional

_REPO = Path(__file__).resolve().parents[1]

# Which promise a tool serves, by prefix or exact name. Deliberately coarse:
# the point is to see whether a cut lands disproportionately on one promise,
# not to litigate individual assignments.
_PROMISE_RULES: tuple[tuple[str, str], ...] = (
    ("siem_", "P1 investigate"),
    ("faz_", "P1 investigate"),
    ("fmg_", "P3 reach"),
    ("find_enrichment_actions", "P1 investigate"),
    ("search_module_records", "P1 investigate"),
    ("get_record", "P1 investigate"),
    ("investigate", "P1 investigate"),
    ("find_containment_actions", "P2 gating"),
    ("run_op", "P2 gating"),
    ("emit_action_card", "P2 gating"),
    ("emit_choice_card", "P2 gating"),
    ("emit_manual_input", "P2 gating"),
    ("approval", "P2 gating"),
    ("healthcheck_connector", "P3 reach"),
    ("get_run_env", "P3 reach"),
    ("list_configured_connectors", "P3 reach"),
    ("propose_http_fallback", "P3 reach"),
    ("run_playbook", "P4 bottle it"),
    ("resume_playbook", "P4 bottle it"),
    ("push_playbook", "P4 bottle it"),
)


def _promise(name: str) -> str:
    for key, promise in _PROMISE_RULES:
        if name == key or name.startswith(key):
            return promise
    return "P4 bottle it"          # the authoring surface is the default


# Families whose members share a shape and differ only in the axis they search.
# These are where "combine" actually pays: one tool with a `source`/`by`
# argument instead of N near-identical descriptions competing for the model's
# attention. Listed so the census can price each family, not to prejudge it.
_FAMILIES: dict[str, tuple[str, ...]] = {
    "siem hunt": ("siem_search_ip", "siem_search_host", "siem_search_user",
                  "siem_events_for_incident", "siem_raw_query"),
    "faz hunt": ("faz_search_ip", "faz_search_device_events", "faz_get_alerts",
                 "faz_event_summary", "faz_raw_query", "faz_search_by_serial"),
    "fmg device": ("fmg_get_device_list", "fmg_get_device_status",
                   "fmg_get_ha_status", "fmg_get_policy_package_status"),
    "picklist": ("list_picklists", "get_picklist", "picklist_for_field",
                 "resolve_picklist_value", "precheck_picklist_value"),
    "jinja discovery": ("find_jinja_pattern", "find_jinja_example",
                        "find_jinja_filter", "get_filter_examples",
                        "suggest_jinja"),
    "api catalog": ("find_api_example", "find_api_fixture", "find_api_product",
                    "search_api_examples"),
}


def harvest_eval_runs(root: Path) -> tuple[dict, set, int]:
    """Per-tool call counts + payload cost from archived eval matrices.

    Returns (stats, tasks_seen, rows). `tasks_seen` is what makes a zero
    readable: it says which slice of the corpus these numbers came from.
    """
    stats: dict[str, dict[str, int]] = collections.defaultdict(
        lambda: {"calls": 0, "result_chars": 0, "fails": 0})
    tasks: set = set()
    rows = 0
    for matrix in sorted(root.glob("*/matrix.json")):
        try:
            data = json.loads(matrix.read_text())
        except (OSError, ValueError):
            continue
        for row in data.get("rows") or []:
            rows += 1
            tasks.add(row.get("task"))
            for call in row.get("trace") or []:
                if not isinstance(call, dict):
                    continue
                s = stats[call.get("name")]
                s["calls"] += 1
                s["result_chars"] += int(call.get("result_chars") or 0)
                if call.get("ok") is False:
                    s["fails"] += 1
    return dict(stats), tasks, rows


def harvest_probe(path: Path) -> dict:
    """Per-tool call counts from a real-loop probe run (`tools_called` rows)."""
    stats: dict[str, dict[str, int]] = collections.defaultdict(
        lambda: {"calls": 0, "result_chars": 0, "fails": 0})
    data = json.loads(path.read_text())
    for row in data.get("rows") or []:
        for name in row.get("tools_called") or []:
            stats[name]["calls"] += 1
    return dict(stats)


def _registry(runtime: Optional[Path]) -> tuple[list, set]:
    """(all tool names, names the connector registered at runtime)."""
    sys.path.insert(0, str(_REPO))
    from fsr_playbooks.llm.tools import SAFE_TOOLS
    base = list(SAFE_TOOLS)
    if runtime is None:
        return base, set()
    names = json.loads(runtime.read_text())
    return sorted(set(names) | set(base)), set(names) - set(base)


def census(*, runtime: Optional[Path], probe: Optional[Path]) -> dict:
    names, late = _registry(runtime)
    eval_stats, tasks, rows = harvest_eval_runs(_REPO / "data" / "eval_runs")
    probe_stats = harvest_probe(probe) if probe else {}

    # A task corpus with no investigation/containment fixtures cannot speak to
    # P1/P2 tools at all. Detect that rather than assume it.
    covered_p1p2 = any(t and ("invest" in t or "contain" in t or "triage" in t)
                       for t in tasks)

    out = []
    for name in names:
        e = eval_stats.get(name) or {}
        p = probe_stats.get(name) or {}
        calls = int(e.get("calls", 0)) + int(p.get("calls", 0))
        promise = _promise(name)
        if calls:
            verdict = "used"
        elif promise.startswith(("P1", "P2")) and not covered_p1p2:
            # The corpus structurally cannot reach it. Saying "unused" here is
            # how a census deletes the product's headline promises.
            verdict = "unreachable-in-corpus"
        elif name in late and not probe:
            verdict = "unreachable-in-corpus"
        else:
            verdict = "never-called"
        out.append({
            "tool": name, "promise": promise,
            "connector_registered": name in late,
            "calls": calls,
            "avg_result_chars": (int(e.get("result_chars", 0)) //
                                 max(int(e.get("calls", 0)), 1)),
            "fails": int(e.get("fails", 0)),
            "verdict": verdict,
        })
    out.sort(key=lambda r: (-r["calls"], r["tool"]))
    families = {
        fam: {"members": len(members),
              "present": [m for m in members if m in set(names)],
              "calls": sum((eval_stats.get(m) or {}).get("calls", 0) +
                           (probe_stats.get(m) or {}).get("calls", 0)
                           for m in members)}
        for fam, members in _FAMILIES.items()
    }
    return {
        "meta": {"tools": len(names), "connector_registered": len(late),
                 "eval_rows": rows, "eval_tasks": len(tasks),
                 "p1p2_covered_by_corpus": covered_p1p2,
                 "probe": str(probe) if probe else None},
        "tools": out, "families": families,
    }


def _print(rep: dict) -> None:
    m = rep["meta"]
    print(f"tool census -- {m['tools']} tools "
          f"({m['connector_registered']} registered by the connector at "
          f"runtime), evidence from {m['eval_rows']} eval rows across "
          f"{m['eval_tasks']} tasks")
    if not m["p1p2_covered_by_corpus"]:
        print("!! the evidence corpus contains NO investigation/containment "
              "tasks -- every P1/P2 zero below is 'not measured', NOT "
              "'not needed'. Do not cut on it.")
    print()
    print(f"{'tool':<32}{'promise':<16}{'calls':>7}{'avg_res':>9}  verdict")
    print("-" * 84)
    for r in rep["tools"]:
        star = "*" if r["connector_registered"] else " "
        print(f"{star}{r['tool']:<31}{r['promise']:<16}{r['calls']:>7}"
              f"{r['avg_result_chars']:>9}  {r['verdict']}")
    print("\nmerge candidates (same shape, different axis):")
    for fam, f in sorted(rep["families"].items(),
                         key=lambda kv: -len(kv[1]["present"])):
        if len(f["present"]) > 1:
            print(f"  {fam:<18} {len(f['present'])} tools, "
                  f"{f['calls']} calls -- {', '.join(f['present'])}")
    counts = collections.Counter(r["verdict"] for r in rep["tools"])
    print(f"\n{dict(counts)}")


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runtime", type=Path, default=None,
                    help="JSON list of SAFE_TOOLS dumped AFTER a turn ran "
                         "(includes the connector's late registrations)")
    ap.add_argument("--probe", type=Path, default=None,
                    help="real-loop probe JSON with per-row tools_called")
    ap.add_argument("--json", dest="json_out", type=Path, default=None)
    args = ap.parse_args(argv)
    rep = census(runtime=args.runtime, probe=args.probe)
    _print(rep)
    if args.json_out:
        args.json_out.write_text(json.dumps(rep, indent=2))
        print(f"\nwrote {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
