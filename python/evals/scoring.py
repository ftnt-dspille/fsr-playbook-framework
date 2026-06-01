"""Score a candidate playbook YAML on three confidence tiers + an
example-match check + agent-behavior gates.

Confidence tiers (what a human means by "is this playbook good?"):

  draft        — YAML parses + compiles to FSR JSON. "It would import
                 without an error." Says nothing about whether it works.
  verified     — Statically sound: references resolve, branches
                 reachable, connectors/ops exist, picklists valid.
                 Equivalent to `verify_playbook.ready_to_push=True`.
                 "I would ship this without testing it manually."
  live_tested  — Actually executes on a real FSR (dry-run passes).
                 Strongest signal short of pushing. Skipped offline.

Orthogonal:

  matches_example — byte-equal compile output to the hand-curated
                    reference YAML in /examples/. Only meaningful for
                    tasks that have a reference; says nothing about
                    novel playbooks.

Agent-behavior gates (apply only when a tool-use `trace` is supplied):

  verify_called_before_submit
  verify_iterations_until_ready   (record only — not pass/fail)
  final_verify_ready_to_push
  tool_budget
  no_spiral
  adherence                       (final text included a YAML block)
"""
from __future__ import annotations

import json
import os
import re
from typing import Any

_YAML_BLOCK_RE = re.compile(r"```ya?ml\s*\n", re.IGNORECASE)


def _verify(yaml_text: str, *, live: bool) -> dict[str, Any]:
    from fsr_core.mcp_server import verify_playbook
    return verify_playbook(yaml_text=yaml_text, live_probe=live)


def _live_tested_blocker(yaml_text: str) -> tuple[str, str] | None:
    """Detect playbook structures the /notrigger dry-run path cannot
    actually run to completion. Returns (code, summary) for skip, or
    None when the playbook is safe to dry-run.

    - `manual_input` steps suspend waiting for a human; eval polling
      will always hit the 180s timeout.
    - `start_on_create` / `start_on_update` / `start_on_action`
      triggers fire on real record events and need an actual record
      IRI in body; /notrigger has no record context.
    """
    try:
        import yaml as _yaml
        doc = _yaml.safe_load(yaml_text)
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(doc, dict):
        return None
    pbs = doc.get("playbooks") or []
    if not isinstance(pbs, list) or not pbs:
        return None
    record_triggers = {"start_on_create", "start_on_update",
                       "start_on_action", "cybersponse.action"}
    for pb in pbs:
        if not isinstance(pb, dict):
            continue
        steps = pb.get("steps") or []
        if not isinstance(steps, list):
            continue
        for s in steps:
            if not isinstance(s, dict):
                continue
            t = s.get("type") or ""
            if t == "manual_input":
                return ("manual_input_blocks_dry_run",
                        "playbook contains manual_input — /notrigger "
                        "dry-run will block awaiting human input")
            if t in record_triggers:
                return ("record_trigger_requires_record",
                        f"trigger {t!r} fires on real record events; "
                        "/notrigger dry-run has no record context")
    return None


def _first_playbook_name(yaml_text: str) -> str | None:
    """Best-effort: pull the first playbook's name out of the YAML so
    the scoring harness can dry-run without an explicit override."""
    try:
        import yaml as _yaml
        doc = _yaml.safe_load(yaml_text)
        if isinstance(doc, dict):
            pbs = doc.get("playbooks") or []
            if pbs and isinstance(pbs[0], dict):
                name = pbs[0].get("name")
                return name if isinstance(name, str) and name else None
    except Exception:  # noqa: BLE001
        return None
    return None


def _compile_obj(yaml_text: str) -> dict[str, Any]:
    from fsr_core.mcp_server import compile_yaml
    return compile_yaml(yaml_text, verbose=True)


_VOLATILE_KEYS = frozenset({"lastModifyDate"})


def _strip_volatile(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _strip_volatile(v) for k, v in obj.items()
                if k not in _VOLATILE_KEYS}
    if isinstance(obj, list):
        return [_strip_volatile(x) for x in obj]
    return obj


# Agentic gate thresholds. Sourced from docs/AGENT_TOOL_USAGE.md p95s —
# raise via env if a model is intentionally chatty.
TOOL_BUDGET_MAX = int(os.environ.get("EVAL_TOOL_BUDGET_MAX", "20"))
NO_SPIRAL_MAX_CONSECUTIVE = int(
    os.environ.get("EVAL_NO_SPIRAL_MAX_CONSECUTIVE", "4"))
# Phase 1.4: investigation-quality family. Recall = required pivots the
# agent actually performed / required pivots. Gate at 0.8 per the plan.
INVESTIGATION_RECALL_GATE = float(
    os.environ.get("EVAL_INVESTIGATION_RECALL_GATE", "0.8"))
# Recall alone greenlights a run that flails for 20 calls and never stages a
# deliverable (live calibration 2026-05-30: 5/5 at recall 1.0 told us nothing).
# These per-fixture quality knobs are the teeth. Defaults apply to every
# investigation task; a fixture's `investigation_quality` block overrides them.
INVESTIGATION_TOOL_BUDGET_MAX = int(
    os.environ.get("EVAL_INVESTIGATION_TOOL_BUDGET_MAX", "12"))
# >N distinct arg-sets for the SAME (connector, op) = the grounding-flail
# signature (agent guessing param names live: ip -> ip_address -> indicator).
INVESTIGATION_MAX_PARAM_RETRIES = int(
    os.environ.get("EVAL_INVESTIGATION_MAX_PARAM_RETRIES", "2"))
# Tools that count as "staged a concrete deliverable for the analyst". A
# capability gap / choice card IS a valid ending when no containment op is
# configured on the box — credit it, don't demand an action card that can't
# exist here.
_DELIVERABLE_TOOLS = (
    "emit_action_card", "emit_choice_card", "emit_capability_gap_card",
)


def _fact_matches(fact: dict[str, Any], call: dict[str, Any]) -> bool:
    """Does a single trace tool-call satisfy a required/forbidden fact?

    A fact is a matcher, e.g.::

        {"tool": "run_op", "connector": "virustotal",
         "op": "get_ip_reputation", "args_contains": ["203.0.113.5"]}
        {"tool": "get_record", "module": "alerts"}

    `tool` matches the tool name; `connector`/`op`/`module` are matched
    case-insensitively against the call's top-level args; `args_contains`
    is a list of substrings that must ALL appear in the JSON-serialized
    args (so an indicator buried in `params.ip` still matches without the
    fixture needing to know the exact nesting)."""
    if fact.get("tool") and call.get("name") != fact["tool"]:
        return False
    args = call.get("args") or call.get("input") or {}
    if not isinstance(args, dict):
        args = {}
    for key in ("connector", "op", "module"):
        if key in fact and str(args.get(key, "")).lower() != str(fact[key]).lower():
            return False
    needles = fact.get("args_contains") or []
    if needles:
        blob = json.dumps(args, default=str).lower()
        if not all(str(n).lower() in blob for n in needles):
            return False
    return True


def _fact_label(fact: dict[str, Any]) -> str:
    return fact.get("label") or " ".join(
        str(fact.get(k)) for k in ("tool", "connector", "op", "module")
        if fact.get(k)) or json.dumps(fact, default=str)


def _score_investigation(trace: list[dict[str, Any]],
                         required_facts: list[dict[str, Any]] | None,
                         forbidden_facts: list[dict[str, Any]] | None,
                         ) -> dict[str, Any]:
    """Recall over required investigation pivots, with a hard fail on any
    forbidden pivot (e.g. external TI lookup on an internal RFC1918 IP)."""
    required_facts = required_facts or []
    matched, missing = [], []
    for f in required_facts:
        if any(_fact_matches(f, c) for c in trace):
            matched.append(f)
        else:
            missing.append(f)
    recall = (len(matched) / len(required_facts)) if required_facts else 0.0
    forbidden_hit = [f for f in (forbidden_facts or [])
                     if any(_fact_matches(f, c) for c in trace)]
    passed = recall >= INVESTIGATION_RECALL_GATE and not forbidden_hit
    detail = f"recall {recall:.2f} (>= {INVESTIGATION_RECALL_GATE})"
    if forbidden_hit:
        detail = (f"performed {len(forbidden_hit)} forbidden pivot(s): "
                  + ", ".join(_fact_label(f) for f in forbidden_hit))
    return {
        "passed": passed, "skipped": False,
        "recall": round(recall, 3), "gate": INVESTIGATION_RECALL_GATE,
        "matched": len(matched), "required": len(required_facts),
        "missing": [_fact_label(f) for f in missing],
        "forbidden_hit": [_fact_label(f) for f in forbidden_hit],
        "detail": detail,
    }


def _call_args(call: dict[str, Any]) -> dict[str, Any]:
    args = call.get("args") or call.get("input") or {}
    return args if isinstance(args, dict) else {}


def _param_flail(trace: list[dict[str, Any]]) -> tuple[int, str | None]:
    """Worst-offender count of DISTINCT arg-sets for a single (connector, op).

    The grounding-flail signature: the agent re-invokes the same op cycling
    param names (`ip` -> `ip_address` -> `indicator`) because it's discovering
    the real schema live by trial and error. One op called once with the right
    params yields 1; a 3-way param guess yields 3. Returns (worst, label)."""
    from collections import defaultdict
    seen: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for c in trace:
        if c.get("name") != "run_op":
            continue
        args = _call_args(c)
        key = (
            "run_op",
            str(args.get("connector", "")).lower(),
            str(args.get("op", "")).lower(),
        )
        params = args.get("params")
        if not isinstance(params, dict):
            params = {k: v for k, v in args.items()
                      if k not in ("connector", "op", "confirm")}
        seen[key].add(json.dumps(params, sort_keys=True, default=str))
    if not seen:
        return 0, None
    worst_key = max(seen, key=lambda k: len(seen[k]))
    worst = len(seen[worst_key])
    label = f"{worst_key[1]}.{worst_key[2]}" if worst_key[1] else worst_key[2]
    return worst, (label or None)


# Discovery tools that reveal an op's real param schema. A run_op retry that
# follows any of these for the same op is "informed"; one that doesn't is blind.
_SCHEMA_DISCOVERY_TOOLS = ("get_op_schema", "find_operation", "find_operation_example")


def _blind_param_retry(trace: list[dict[str, Any]]) -> tuple[int, str | None]:
    """Worst case of run_op retried with corrected params for an op the agent
    NEVER pulled a schema for — the avoidable flail (vs. _param_flail, which
    counts retries regardless of whether discovery happened).

    Walks the trace in order: a `get_op_schema`/`find_operation*` call for a
    connector/op marks it 'discovered' from that point on. A run_op with a new
    distinct arg-set for an op that has NOT been discovered yet is a blind
    retry. Returns (worst_blind_argsets, label). 1 blind arg-set is fine (first
    attempt); ≥2 means the agent hammered corrections without ever looking up
    the schema — the signal that get_op_schema is too costly/undiscoverable, or
    that the inline `valid_params` on the first bad_params error isn't landing."""
    from collections import defaultdict
    discovered: set[tuple[str, str]] = set()
    blind: dict[tuple[str, str], set[str]] = defaultdict(set)
    for c in trace:
        name = c.get("name")
        args = _call_args(c)
        conn = str(args.get("connector", "")).lower()
        op = str(args.get("op", "")).lower()
        if name in _SCHEMA_DISCOVERY_TOOLS and conn:
            # find_operation may not carry an op (list mode) — mark all-of-connector
            discovered.add((conn, op))
            if not op:
                discovered.add((conn, ""))
        elif name == "run_op" and conn and op:
            if (conn, op) in discovered or (conn, "") in discovered:
                continue
            params = args.get("params")
            if not isinstance(params, dict):
                params = {k: v for k, v in args.items()
                          if k not in ("connector", "op", "confirm")}
            blind[(conn, op)].add(json.dumps(params, sort_keys=True, default=str))
    if not blind:
        return 0, None
    worst_key = max(blind, key=lambda k: len(blind[k]))
    worst = len(blind[worst_key])
    return worst, f"{worst_key[0]}.{worst_key[1]}"


def _score_investigation_quality(
    trace: list[dict[str, Any]],
    quality: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    """Quality gates that recall can't see (Phase 1.4 strengthening).

    Each gate is opt-in per fixture via the `investigation_quality` block; an
    absent knob falls back to the module default, and a knob set to a falsey
    value (e.g. `"require_deliverable": false`) marks that gate `skipped` so a
    fixture with no possible deliverable on this box isn't penalized."""
    quality = quality or {}
    gates: dict[str, dict[str, Any]] = {}

    # --- tool-budget ceiling (tighter than the authoring TOOL_BUDGET_MAX) ----
    budget = quality.get("tool_budget_max", INVESTIGATION_TOOL_BUDGET_MAX)
    n = len(trace)
    gates["investigation_tool_budget"] = {
        "passed": n <= budget, "skipped": False,
        "calls": n, "limit": budget,
        "detail": f"{n} tool call(s) (limit {budget})",
    }

    # --- no param-grounding flail -------------------------------------------
    max_retries = quality.get("max_param_retries", INVESTIGATION_MAX_PARAM_RETRIES)
    worst, label = _param_flail(trace)
    flail_ok = worst <= max_retries
    gates["investigation_no_param_flail"] = {
        "passed": flail_ok, "skipped": False,
        "worst_distinct_argsets": worst, "limit": max_retries, "op": label,
        "detail": (f"{label} called with {worst} distinct arg-sets "
                   f"(limit {max_retries})" if not flail_ok
                   else f"no op exceeded {max_retries} distinct arg-sets"),
    }

    # --- no BLIND param retry (hammered run_op without ever pulling a schema) -
    # Distinct from no_param_flail: this only counts retries the agent made
    # WITHOUT calling get_op_schema/find_operation for that op first. ≥2 blind
    # arg-sets = the agent guessed, failed, and guessed again instead of looking
    # it up — the avoidable flail. Shares the max_param_retries knob.
    blind_worst, blind_label = _blind_param_retry(trace)
    blind_ok = blind_worst <= max_retries
    gates["investigation_blind_param_retry"] = {
        "passed": blind_ok, "skipped": False,
        "worst_blind_argsets": blind_worst, "limit": max_retries, "op": blind_label,
        "detail": (f"{blind_label} retried with {blind_worst} distinct arg-sets "
                   f"and NO get_op_schema/find_operation for it (limit {max_retries})"
                   if not blind_ok
                   else "no op was blind-retried without a schema lookup"),
    }

    # --- staged a concrete deliverable --------------------------------------
    req = quality.get("require_deliverable", True)
    if not req:
        gates["investigation_deliverable"] = {"passed": True, "skipped": True}
    else:
        allowed = req if isinstance(req, (list, tuple)) else _DELIVERABLE_TOOLS
        allowed = tuple(allowed)
        hit = [c.get("name") for c in trace if c.get("name") in allowed]
        gates["investigation_deliverable"] = {
            "passed": bool(hit), "skipped": False,
            "staged": sorted(set(hit)), "accepted": list(allowed),
            "detail": (f"staged {', '.join(sorted(set(hit)))}" if hit
                       else "no deliverable card staged for the analyst "
                            f"(accepts: {', '.join(allowed)})"),
        }
    return gates


def _verify_metrics(trace: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Three metrics about the agent's use of `verify_playbook` from
    the call trace. Distinct from the `verified` confidence tier —
    these measure agent *behavior*, not playbook quality. The agent
    can technically ship a YAML it never ran through verify; this gate
    catches that."""
    verifies = [t for t in trace if t.get("name") == "verify_playbook"]
    called = len(verifies) >= 1
    last_ready = bool(verifies[-1].get("verify", {}).get("ready_to_push")) if verifies else False
    iters = len(verifies)
    for i, v in enumerate(verifies, start=1):
        if v.get("verify", {}).get("ready_to_push"):
            iters = i
            break
    return {
        "verify_called_before_submit": {
            "passed": called, "skipped": False,
            "detail": (f"{len(verifies)} verify_playbook call(s)" if called
                       else "agent never called verify_playbook"),
        },
        "verify_iterations_until_ready": {
            "passed": called, "skipped": False,
            "iterations": iters if called else 0,
            "detail": (f"{iters} verify cycle(s) until ready"
                       if called and last_ready
                       else "never reached ready_to_push=True"
                       if called else "no verify calls"),
        },
        "final_verify_ready_to_push": {
            "passed": last_ready, "skipped": False,
            "detail": ("last verify returned ready_to_push=True" if last_ready
                       else "last verify did NOT return ready_to_push=True"),
        },
    }


def _score_approval_requests(
    audit: list[dict[str, Any]],
    expected: dict[str, Any] | None,
) -> dict[str, Any]:
    """`appropriate_approval_requests` gate (HITL_GUARDRAILS_PLAN Phase 3).

    Reads the dispatch wrapper's per-task audit log and scores the
    agent's escalation behavior against the task's expected pattern.

    `expected` shape:
      {"tier_3_plus": "exactly_zero" | "at_least_one" | {"min": N, "max": M}}

    Default: "exactly_zero" — most authoring tasks shouldn't fire any
    tier-3+ tool calls. Tasks that genuinely require remediation set
    `at_least_one` or a range to opt in.

    PASS: tier-3+ count matches expectations.
    FAIL: agent over-escalated (audit fatigue) or under-escalated
          (e.g. fired run_op when the task was authoring-only)."""
    expected = expected or {"tier_3_plus": "exactly_zero"}
    tier3 = sum(1 for r in audit if r.get("tier", 0) >= 3)
    spec = expected.get("tier_3_plus", "exactly_zero")

    ok: bool
    detail: str
    if spec == "exactly_zero":
        ok = tier3 == 0
        detail = (f"{tier3} tier-3+ call(s) — expected zero"
                  if not ok else "no tier-3+ calls, as expected")
    elif spec == "at_least_one":
        ok = tier3 >= 1
        detail = (f"{tier3} tier-3+ call(s)"
                  if ok else "agent never requested approval for a tier-3+ action")
    elif isinstance(spec, dict):
        lo = int(spec.get("min", 0))
        hi = int(spec.get("max", lo))
        ok = lo <= tier3 <= hi
        detail = f"{tier3} tier-3+ call(s); expected {lo}..{hi}"
    else:
        ok = False
        detail = f"unrecognized expected spec: {spec!r}"

    return {"passed": ok, "skipped": False,
            "tier_3_plus_calls": tier3, "detail": detail}


def _score_agentic(*, trace: list[dict[str, Any]],
                   text: str,
                   audit: list[dict[str, Any]] | None = None,
                   expected_approvals: dict[str, Any] | None = None,
                   ) -> dict[str, dict[str, Any]]:
    """tool_budget / no_spiral / adherence + verify-behavior metrics."""
    n = len(trace)
    longest = 0
    cur_name = None
    cur_run = 0
    longest_name = ""
    for call in trace:
        name = call.get("name", "")
        if name == cur_name:
            cur_run += 1
        else:
            cur_name = name
            cur_run = 1
        if cur_run > longest:
            longest = cur_run
            longest_name = name

    has_yaml = bool(_YAML_BLOCK_RE.search(text or ""))
    out_gates: dict[str, dict[str, Any]] = {
        **_verify_metrics(trace),
        "tool_budget": {
            "passed": n <= TOOL_BUDGET_MAX, "skipped": False,
            "calls": n, "limit": TOOL_BUDGET_MAX,
        },
        "no_spiral": {
            "passed": longest <= NO_SPIRAL_MAX_CONSECUTIVE, "skipped": False,
            "longest_run": longest, "tool": longest_name,
            "limit": NO_SPIRAL_MAX_CONSECUTIVE,
        },
        "adherence": {
            "passed": has_yaml, "skipped": False,
            "detail": ("yaml block present" if has_yaml
                       else "no fenced ```yaml block in final text"),
        },
    }
    if audit is not None:
        out_gates["appropriate_approval_requests"] = _score_approval_requests(
            audit, expected_approvals)
    else:
        out_gates["appropriate_approval_requests"] = {
            "passed": False, "skipped": True}
    return out_gates


def score(
    yaml_text: str,
    *,
    gold_json: dict[str, Any] | None = None,
    live: bool = False,
    dry_run_kwargs: dict[str, Any] | None = None,
    trace: list[dict[str, Any]] | None = None,
    final_text: str | None = None,
    audit: list[dict[str, Any]] | None = None,
    expected_approvals: dict[str, Any] | None = None,
    mode: str | None = None,
    required_facts: list[dict[str, Any]] | None = None,
    forbidden_facts: list[dict[str, Any]] | None = None,
    investigation_quality: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Score a candidate YAML across confidence tiers + agent gates.

    `mode="refuse"` flips the success criteria for graceful-failure tasks
    (e.g. `unknown_connector`): success = no YAML emitted, no verify call,
    zero tier-3+ approvals. All authoring-tier gates become informational
    so they neither help nor hurt the score.

    `mode="investigation"` scores a triage/hunt task on **pivot recall**
    (`required_facts` matched in the tool-use trace) instead of YAML shape.
    All authoring tiers + adherence become informational; the single gate
    is `investigation_recall` (>= 0.8, with a hard fail on `forbidden_facts`).
    """
    out: dict[str, Any] = {"levels": {}}
    refuse = (mode == "refuse")
    investigation = (mode == "investigation")

    # ----------------- confidence tier 1: draft (compile clean) ------------
    comp = _compile_obj(yaml_text)
    draft_ok = bool(comp.get("ok"))
    out["levels"]["draft"] = {
        "passed": draft_ok,
        "skipped": False,
        "detail": ("compiles" if draft_ok else "compile failed"),
        "errors": comp.get("errors", []) if not draft_ok else [],
    }

    # ----------------- confidence tier 2: verified -------------------------
    # Runs the same fan-out the agent is supposed to call: compile +
    # typed walk + per-step schema checks. live_probe follows the eval
    # mode so offline runs stay deterministic.
    verify = _verify(yaml_text, live=live)
    verified_ok = bool(verify.get("ready_to_push"))
    out["levels"]["verified"] = {
        "passed": verified_ok,
        "skipped": False,
        "required_fix_count": len(verify.get("required_fixes") or []),
        "warning_count": len(verify.get("warnings") or []),
        "detail": ("verify_playbook ready_to_push=True" if verified_ok
                   else f"{len(verify.get('required_fixes') or [])} required fix(es)"),
    }

    # ----------------- confidence tier 3: live_tested ----------------------
    if live:
        # Structural skip: playbooks that block on human input or need
        # a real record context can't reach a terminal state via the
        # eval's /notrigger dry-run. Marking these as skipped (with a
        # specific reason) keeps the harness honest and avoids 180s
        # timeouts per task. The agent-loop gates still grade these.
        blocker = _live_tested_blocker(yaml_text)
        if blocker is not None:
            out["levels"]["live_tested"] = {
                "passed": False, "skipped": True, "code": blocker[0],
                "summary": blocker[1],
            }
        else:
            try:
                from fsr_core.mcp_server import dry_run_playbook  # noqa: PLC0415
                kw = dict(dry_run_kwargs or {})
                # Infer playbook name from the YAML when the caller didn't
                # pin one. Lets re-baseline runs exercise tier-3 without
                # every task carrying a `dry_run_kwargs.playbook` override.
                if "playbook" not in kw:
                    inferred = _first_playbook_name(yaml_text)
                    if inferred:
                        kw["playbook"] = inferred
                dr = dry_run_playbook(yaml_text, **kw) if kw else None
                if dr is None:
                    dr = {"ok": False, "code": "no_dry_run_target",
                          "message": "dry_run_kwargs missing `playbook` name"}
                out["levels"]["live_tested"] = {
                    "passed": bool(dr.get("ok")),
                    "skipped": False,
                    "code": dr.get("code"),
                    "summary": dr.get("status") or dr.get("message"),
                }
            except Exception as exc:  # noqa: BLE001
                out["levels"]["live_tested"] = {
                    "passed": False, "skipped": False,
                    "detail": f"dry-run raised: {exc!r}",
                }
    else:
        out["levels"]["live_tested"] = {"passed": False, "skipped": True}

    # ----------------- example check (orthogonal) --------------------------
    if gold_json is not None:
        if comp.get("ok"):
            try:
                got = json.loads(comp["json"])
            except Exception:  # noqa: BLE001
                got = {}
            a = _strip_volatile(got)
            b = _strip_volatile(gold_json)
            out["levels"]["matches_example"] = {
                "passed": a == b, "skipped": False,
                "detail": ("match" if a == b
                           else "compiled JSON differs from the reference example"),
            }
        else:
            out["levels"]["matches_example"] = {
                "passed": False, "skipped": False,
                "detail": "compile failed — see draft errors",
            }
    else:
        out["levels"]["matches_example"] = {"passed": False, "skipped": True}

    # ----------------- agent-behavior gates --------------------------------
    if trace is not None:
        out["levels"].update(_score_agentic(
            trace=trace, text=final_text or "",
            audit=audit, expected_approvals=expected_approvals,
        ))
    else:
        for k in ("tool_budget", "no_spiral", "adherence",
                  "verify_called_before_submit",
                  "verify_iterations_until_ready",
                  "final_verify_ready_to_push",
                  "appropriate_approval_requests"):
            out["levels"][k] = {"passed": False, "skipped": True}

    # `verify_iterations_until_ready` is informational, not a gate —
    # exclude from the pass/fail aggregate. Same logic as the old
    # `skipped` flag, but here we mark it `passed=True` if it ran at
    # all so it doesn't drag the fraction.
    iters_lv = out["levels"].get("verify_iterations_until_ready", {})
    if not iters_lv.get("skipped"):
        # not counted toward fraction
        iters_lv["informational"] = True

    # `matches_example` is byte-equality of compiled IR against a gold
    # reference: useful diagnostic, but free-form LLM generation cannot
    # reliably match cosmetic IR differences (optional fields, default
    # values, step ordering). Demote to informational — `draft` and
    # `verified` already gate functional correctness.
    mex = out["levels"].get("matches_example", {})
    if not mex.get("skipped"):
        mex["informational"] = True

    # Refuse-mode: the agent is expected to NOT produce a playbook. Flip
    # the gates so the authoring tiers are informational and adherence
    # passes when no YAML block is present.
    if refuse:
        for k in ("draft", "verified", "live_tested",
                  "verify_called_before_submit",
                  "final_verify_ready_to_push"):
            lv = out["levels"].get(k, {})
            if not lv.get("skipped"):
                lv["informational"] = True
        adh = out["levels"].get("adherence", {})
        if not adh.get("skipped"):
            # Invert: success = NO yaml block emitted.
            had_yaml = bool(adh.get("passed"))
            adh["passed"] = not had_yaml
            adh["detail"] = ("correctly refused — no YAML emitted"
                             if not had_yaml
                             else "fabricated YAML for a refuse-mode task")

    # Investigation-mode: grade on pivot recall, not YAML. Authoring tiers
    # and adherence (a YAML block) are irrelevant to a triage/hunt task, so
    # demote them to informational and add the single recall gate.
    if investigation:
        # The authoring tiers + the loose authoring `tool_budget` (20) are
        # irrelevant or superseded here: investigation gets its own tighter
        # ceiling (`investigation_tool_budget`). Demote, don't count twice.
        for k in ("draft", "verified", "live_tested", "matches_example",
                  "adherence", "verify_called_before_submit",
                  "final_verify_ready_to_push", "tool_budget"):
            lv = out["levels"].get(k, {})
            if not lv.get("skipped"):
                lv["informational"] = True
        if trace is not None:
            out["levels"]["investigation_recall"] = _score_investigation(
                trace, required_facts, forbidden_facts)
            out["levels"].update(
                _score_investigation_quality(trace, investigation_quality))
        else:
            for k in ("investigation_recall", "investigation_tool_budget",
                      "investigation_no_param_flail",
                      "investigation_deliverable"):
                out["levels"][k] = {
                    "passed": False, "skipped": True,
                    "detail": "no tool-use trace supplied"}

    counted = [v for k, v in out["levels"].items()
               if not v.get("skipped") and not v.get("informational")]
    out["score"] = sum(1 for v in counted if v["passed"])
    out["max"] = len(counted)
    out["fraction"] = (out["score"] / out["max"]) if out["max"] else 0.0
    return out
