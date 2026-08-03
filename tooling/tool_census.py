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


# Tools that CANNOT be called offline no matter how wide the corpus gets:
# each one's whole job is to touch a live appliance. A sealed run reaches the
# tier gate or the client and stops, so they land in the same zero bucket as a
# tool nobody wants -- opposite conclusions from an identical number. Naming
# them is what keeps a box-free census from proposing to delete P3.
_BOX_GATED = frozenset({
    "push_playbook", "dry_run_playbook", "get_run_env",
    "healthcheck_connector", "diagnose_yaml_against_pb_execution",
    "run_playbook", "resume_playbook", "list_playbook_runs",
    "why_did_playbook_fail",
})

# Box-gated tools that exist ONLY once the connector registers them at runtime
# (see #67: the framework advertises 40, a deployed agent sees 62). They are
# absent from `SAFE_TOOLS` by design, so a membership check against it is the
# wrong test for them -- but they still must not read as `never-called`.
#
# The full 22 are read from the committed manifest at
# `data/connector_tool_registry.json` (see `_load_manifest`). `_RUNTIME_ONLY`
# is seeded from that manifest so the test that asserts every census tool is
# known (`SAFE_TOOLS | _RUNTIME_ONLY`) passes box-free. The manifest is the
# thing that made the census stop needing a live turn to learn the truth.
_MANIFEST_PATH = _REPO / "data" / "connector_tool_registry.json"


def _load_manifest() -> dict | None:
    """Read the committed connector tool-registry manifest, or None.

    The manifest is generated from the connector's ``register_*_tools``
    functions (see ``scripts/export_registry_manifest.py`` in the connector
    repo). It lists the 22 tools the connector adds to ``SAFE_TOOLS`` at
    runtime, with their tiers and the register function that adds each.

    Without this, a census built from the framework repo alone is blind to
    36% of the tool surface -- specifically the P1/P2 half (tracker #67).
    """
    try:
        return json.loads(_MANIFEST_PATH.read_text())
    except (OSError, ValueError):
        return None


_MANIFEST = _load_manifest()
_RUNTIME_ONLY = frozenset(_MANIFEST["tools"]) if _MANIFEST else frozenset({"resume_playbook"})


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


def harvest_probe(path: Path) -> tuple[dict, set]:
    """Per-tool call counts from a real-loop probe run. Returns (stats, names).

    Two shapes are accepted, because the two instruments that drive the real
    agent loop box-free write different files and neither is worth a converter:

      * `{"rows": [{"scenario": ..., "tools_called": [...]}]}` --
        `guard_fire_rates.py`, six authoring scenarios.
      * `{"scenarios": [{"scenario": ..., "runs": [{"conversation": {...}}]}]}`
        -- the connector's `chat_sweep.py --out --keep-conversations`, a
        twenty-eight scenario corpus that DOES cover triage, investigation and
        containment. That corpus is the whole point: the archived eval matrices
        contain no invest_*/contain_* rows at all, so every "unused" verdict on
        a P1/P2 tool so far was structural rather than observed.

    The returned name set is the scenario names, which is what lets the caller
    decide whether P1/P2 was actually reachable instead of assuming it.
    """
    stats: dict[str, dict[str, int]] = collections.defaultdict(
        lambda: {"calls": 0, "result_chars": 0, "fails": 0})
    seen: set = set()
    data = json.loads(path.read_text())

    def _count(names) -> None:
        for name in names or []:
            if name:
                stats[name]["calls"] += 1

    for row in data.get("rows") or []:
        seen.add(row.get("scenario"))
        _count(row.get("tools_called"))
    for sc in data.get("scenarios") or []:
        seen.add(sc.get("scenario") or sc.get("name"))
        for run in sc.get("runs") or []:
            conv = run.get("conversation") or {}
            _count(conv.get("tools_called"))
    return dict(stats), {s for s in seen if s}


def _registry(runtime: Optional[Path]) -> tuple[list, set]:
    """(all tool names, names the connector registered at runtime).

    The 22 connector-registered tools are read from the committed manifest
    (`data/connector_tool_registry.json`) by default, so the census is no
    longer blind to 36% of the surface without a live turn (tracker #67).
    A `--runtime` dump (if given) is merged on top -- it can add tools the
    manifest doesn't know about yet (e.g. native-MCP materializations)."""
    sys.path.insert(0, str(_REPO))
    from fsr_playbooks.llm.tools import SAFE_TOOLS
    base = set(SAFE_TOOLS)
    late: set = set()
    # The committed manifest -- the static truth for the connector's 22.
    if _MANIFEST is not None:
        late.update(_MANIFEST.get("tools", []))
    # A live runtime dump (optional, on top of the manifest).
    if runtime is not None:
        names = set(json.loads(runtime.read_text()))
        late.update(names - base)
    all_names = sorted(base | late)
    return all_names, late


def census(*, runtime: Optional[Path], probe: Optional[Path]) -> dict:
    names, late = _registry(runtime)
    eval_stats, tasks, rows = harvest_eval_runs(_REPO / "data" / "eval_runs")
    probe_stats, probe_tasks = harvest_probe(probe) if probe else ({}, set())

    # A task corpus with no investigation/containment fixtures cannot speak to
    # P1/P2 tools at all. Detect that rather than assume it -- and count the
    # probe's scenarios, since that is where the offline P1/P2 rows now live.
    covered_p1p2 = any(t and ("invest" in t or "contain" in t or "triage" in t)
                       for t in tasks | probe_tasks)

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
        elif name in _BOX_GATED:
            # Unreachable offline by construction, not unwanted. A cut list
            # that reads this zero as "never-called" deletes P3.
            verdict = "needs-box"
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
