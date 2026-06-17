"""MCP tools: Tools Analysis"""
from __future__ import annotations

import json
import sqlite3
from typing import Any

from . import _shared
from . import tools_execution
from . import tools_discovery
from .tools_picklists import (
    precheck_picklist_value,
    _persist_precheck_verification,
    _map_http_auth,
)
from ._shared import (
    mcp,
    _db,
)
# Import DB_PATH for type hints/direct use (non-patchable usage)
DB_PATH = _shared.DB_PATH

# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
def step_through_playbook(yaml_text: str,
                          playbook: str | None = None,
                          input: dict[str, Any] | None = None,
                          branch_choices: dict[str, str] | None = None,
                          manual_choices: dict[str, str] | None = None,
                          execute_safe_ops: bool = True,
                          execute_unsafe_ops: bool = False,
                          max_steps: int = 30) -> dict[str, Any]:
    """Pre-push stepper: walk a playbook step-by-step *without* pushing to FSR.

    For each step in the chosen execution path:
      1. Render its arguments against the accumulated `vars.steps.*` +
         `vars.input.*` context using the live FSR's Jinja engine.
      2. If the step is a query-class connector op AND `execute_safe_ops`
         is True, execute it live via `run_op` (read-only — same risk
         gate as `run_op` itself; destructive ops are skipped with a
         simulated placeholder).
      3. Otherwise simulate: record the rendered args and an empty
         `output` so downstream steps can keep rendering.
    Returns the per-step trace + the first error encountered (if any).
    Lets the agent see exactly where rendering or shape assumptions break
    before any live write happens.

    Args:
      yaml_text: the simplified-IR YAML.
      playbook: name of the workflow to step through (default: first one).
      input: vars.input.params.* values.
      branch_choices: {step_id: branch_label} pinning decision-step paths.
      execute_safe_ops: if False, every step is simulated (purely offline).
      execute_unsafe_ops: opt-in flag (HITL Phase 5). Default False keeps
        the simulator strictly read-only — unsafe steps return
        `{output: {_simulated: True, would_have_run: {connector, op,
        params}}}` so downstream Jinja keeps resolving. When True, the
        dispatch wrapper escalates the *call* to tier-3 (one approval
        card guards entry into the unsafe simulator); to commit any
        specific destructive step the agent then calls `run_op` per
        step, each of which carries its own per-call approval gate.
      max_steps: hard cap to prevent runaway loops.

    Response shape:
      { ok, playbook, trace: [ {step_id, type, rendered_args, output,
                                output_top_keys, status, note} ],
        first_error: {step_id, message} | None,
        steps_executed: int }
    """
    try:
        import yaml as _yaml
        doc = _yaml.safe_load(yaml_text) or {}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"yaml parse failed: {exc}"}

    pbs = doc.get("playbooks") or []
    if not pbs:
        return {"ok": False, "error": "no playbooks in YAML"}
    pb = next((p for p in pbs if p.get("name") == playbook), pbs[0])
    steps = pb.get("steps") or []
    # Accept simplified YAML where step identity is the `name` field
    # (the parser would derive id from name later anyway). Mutates
    # the in-memory step dicts so downstream lookups are uniform.
    for s in steps:
        if isinstance(s, dict) and "id" not in s and s.get("name"):
            s["id"] = s["name"]
    _normalize_friendly_steps(steps)
    by_id = {s["id"]: s for s in steps if isinstance(s, dict) and "id" in s}
    if not by_id:
        return {"ok": False, "error":
                "no steps with id or name in playbook"}

    start = next((s for s in steps if isinstance(s, dict)
                  and (s.get("type") or "").startswith("start")), steps[0])

    # Accumulated context for Jinja rendering. Mirrors the FSR runtime
    # contract: vars.steps.<step_jinja_key>.<output_keys>; vars.input.*.
    vars_ctx: dict[str, Any] = {
        "input": {"params": dict(input or {})},
        "steps": {},
    }

    trace: list[dict[str, Any]] = []
    first_error: dict[str, Any] | None = None
    branch_choices = branch_choices or {}

    cur = start
    for _ in range(max_steps):
        if cur is None:
            break
        sid = cur.get("id", "?")
        stype = cur.get("type", "")
        step_record: dict[str, Any] = {
            "step_id": sid,
            "name": cur.get("name") or sid,
            "type": stype,
            "rendered_args": {},
            "output": None,
            "output_top_keys": [],
            "output_shape": None,
            "consumed_paths": [],
            "simulated_from": "default_empty",
            "status": "skipped",
            "note": "",
        }
        # Static extractor — runs against raw (pre-render) args so we
        # see what the *author wrote*, not what jinja resolved to.
        # The analyzer (Phase 3) cross-references these against the
        # producer's output_shape.
        try:
            from fsr_playbooks.compiler.render_paths import (  # noqa: PLC0415
                consumed_paths_dict, extract_picklist_refs)
            raw_args_for_extract = (cur.get("arguments")
                                    or cur.get("args") or {})
            step_record["consumed_paths"] = consumed_paths_dict(
                raw_args_for_extract)
            step_record["picklist_refs"] = extract_picklist_refs(
                raw_args_for_extract)
        except Exception:  # noqa: BLE001
            pass

        # 1) Render args via the live FSR's Jinja engine, walking
        # nested dicts/lists. Falls back to raw values if no live FSR
        # (so the trace still shows what the agent wrote).
        raw_args = cur.get("arguments") or cur.get("args") or {}
        client = _shared._live_client()
        render_errors: list[str] = []

        def _render_walk(value: Any, path: str = "") -> Any:
            if isinstance(value, str):
                if "{{" not in value or client is None:
                    return value
                try:
                    out = client.post(
                        "/api/wf/api/jinja-editor/",
                        data={"template": value,
                              "values": {"vars": vars_ctx}},
                    )
                    if isinstance(out, dict):
                        for k in ("result", "output", "rendered", "value"):
                            if k in out:
                                return out[k]
                        return out
                    return out if out is not None else value
                except Exception as exc:  # noqa: BLE001
                    render_errors.append(f"{path}: {exc}")
                    return value
            if isinstance(value, dict):
                return {k: _render_walk(v, f"{path}.{k}" if path else k)
                        for k, v in value.items()}
            if isinstance(value, list):
                return [_render_walk(v, f"{path}[{i}]")
                        for i, v in enumerate(value)]
            return value

        rendered = (_render_walk(raw_args)
                    if isinstance(raw_args, dict) else {})

        # for_each iteration. Real FSR shape (live-verified at
        # reference_fsr_for_each_runtime_shape memory): the step's
        # output is a list of per-iteration dicts. We re-render the
        # step body once per item with `vars.item` bound, evaluate
        # the per-iteration `condition` (skip-iter when falsy) and
        # `break_loop` (exit AFTER the breaking iteration runs —
        # do-while semantics), then emit the collected list.
        fe = (cur.get("for_each")
              if isinstance(cur.get("for_each"), dict) else None)
        # parser hoists for_each into arguments, so check both spots
        if fe is None and isinstance(raw_args, dict):
            fe_in_args = raw_args.get("for_each")
            if isinstance(fe_in_args, dict):
                fe = fe_in_args
        if fe is not None:
            item_template = fe.get("item", "")
            rendered_item = _render_walk(item_template) \
                            if isinstance(item_template, str) \
                            else item_template
            items = _coerce_literal_list(rendered_item)
            cond_tpl = fe.get("condition") or ""
            break_tpl = fe.get("break_loop") or ""
            iterations: list[dict[str, Any]] = []
            for it in items:
                vars_ctx["item"] = it
                # Per-iteration filter. Empty / "{{}}" → run unconditionally.
                if cond_tpl:
                    if not _truthy(_render_walk(cond_tpl)):
                        continue
                # Re-render the step body now that vars.item is bound,
                # then map to a per-iteration output dict matching
                # FSR's runtime shape.
                body_rendered = (_render_walk(raw_args)
                                 if isinstance(raw_args, dict) else {})
                iterations.append(_simulate_loop_body(stype, body_rendered))
                # break_loop is do-while: evaluate AFTER appending.
                if break_tpl and _truthy(_render_walk(break_tpl)):
                    break
            vars_ctx.pop("item", None)
            step_record["rendered_args"] = rendered
            step_record["status"] = "simulated"
            step_record["simulated_from"] = "computed"
            step_record["loop_iterations"] = len(iterations)
            step_record["output"] = iterations
            step_record["output_shape"] = _infer_output_shape(iterations)
            jkey = (cur.get("name") or sid).replace(" ", "_")
            vars_ctx["steps"][jkey] = iterations
            trace.append(step_record)
            nxt_id = cur.get("next")
            if not nxt_id or nxt_id not in by_id:
                break
            cur = by_id[nxt_id]
            continue

        # Step-level skip condition. Most step types (record CRUD,
        # connector ops, set_variable, code_snippet) accept a
        # ``condition`` arg — when it renders falsy, FSR skips the
        # step entirely and downstream refs see an empty value. The
        # analyzer downgrades missing_key severity on skipped
        # producers, since they might not have run at runtime either.
        skip_condition = rendered.get("condition")
        if skip_condition not in (None, "") and not _truthy(skip_condition):
            step_record["conditionally_executed"] = True
            step_record["status"] = "skipped"
            step_record["simulated_from"] = "computed"
            step_record["note"] = (
                f"step-level condition resolved to {skip_condition!r}; "
                "FSR will bypass this step at runtime")
            step_record["rendered_args"] = rendered
            step_record["output"] = {}
            step_record["output_shape"] = _infer_output_shape({})
            jkey = (cur.get("name") or sid).replace(" ", "_")
            vars_ctx["steps"][jkey] = {}
            trace.append(step_record)
            nxt_id = cur.get("next")
            if not nxt_id or nxt_id not in by_id:
                break
            cur = by_id[nxt_id]
            continue
        if render_errors:
            step_record["note"] = "jinja render failed: " + "; ".join(
                render_errors[:3])
            if first_error is None:
                first_error = {"step_id": sid,
                               "message": render_errors[0]}
        step_record["rendered_args"] = rendered

        # 2) Execute or simulate. Order of precedence for the simulated
        # output (see RENDER_PATH_VALIDATOR_PLAN.md):
        #   1. arguments.mock_result (any step type that has one)
        #   2. computed output (set_variable / decision / manual_input)
        #   3. live run_op for safe connector ops
        #   4. default empty {}
        sim_output: Any = None
        chosen_branch: str | None = None  # populated by Decision

        # (a) mock_result short-circuit. Beats live execution because
        # the user explicitly asked for fake data; matches FSR's
        # useMockOutput semantics for the step kinds that honor it
        # (record_crud, connector op, code_snippet, fetch).
        mock_out = rendered.get("mock_result")
        # Trigger steps store mock_result on a sub-key, not at args root.
        if mock_out is not None and stype not in {"set_variable", "decision",
                                                   "manual_input"}:
            sim_output = mock_out
            step_record["status"] = "simulated"
            step_record["simulated_from"] = "mock_result"
        elif stype == "connector" and execute_safe_ops:
            cn = rendered.get("connector") or cur.get("connector")
            opn = rendered.get("operation") or cur.get("operation")
            cat = _shared._safe_op_category(cn or "", opn or "")
            risk = tools_discovery._op_risk(opn or "", cat)
            if risk == "safe" and cn and opn:
                try:
                    op_result = tools_execution.run_op(connector=cn, op=opn,
                                       params=rendered, confirm=False)
                    if op_result.get("ok"):
                        sim_output = op_result.get("data")
                        step_record["output_top_keys"] = (
                            op_result.get("output_top_keys") or [])
                        step_record["status"] = "executed"
                        step_record["simulated_from"] = "live_run"
                    else:
                        step_record["status"] = "exec_failed"
                        step_record["note"] = op_result.get("message", "")
                        if first_error is None:
                            first_error = {
                                "step_id": sid,
                                "message": step_record["note"]
                                or "connector exec failed",
                            }
                except Exception as exc:  # noqa: BLE001
                    step_record["status"] = "exec_failed"
                    step_record["note"] = str(exc)
                    if first_error is None:
                        first_error = {"step_id": sid, "message": str(exc)}
            else:
                # HITL Phase 5: emit a synthetic placeholder with the
                # canonical `_simulated: True` + `would_have_run`
                # payload so downstream Jinja keeps resolving and the
                # agent sees exactly what would have fired. The
                # `execute_unsafe_ops` flag is read by the dispatch
                # gate to escalate the *call* to tier-3 (one approval
                # card to enter the unsafe simulator); per-step
                # commits happen via separate `run_op` calls, each of
                # which carries its own gate.
                sim_output = {
                    "_simulated": True,
                    "would_have_run": {
                        "connector": cn or "",
                        "op": opn or "",
                        "params": {k: v for k, v in rendered.items()
                                   if k not in {"connector", "operation",
                                                "mock_result"}},
                    },
                }
                step_record["status"] = "simulated"
                step_record["simulated_from"] = "unsafe_placeholder"
                step_record["note"] = (
                    f"non-safe op (risk={risk}); simulated to keep "
                    "stepper read-only. "
                    + ("Re-run with execute_unsafe_ops=True + per-step run_op "
                       "(each gated) to commit." if not execute_unsafe_ops
                       else "execute_unsafe_ops=True; commit via run_op."))
        elif stype == "set_variable":
            # The handler writes each variable into vars.steps.<sid>.<name>.
            # Two source shapes are accepted: the post-parser form
            # `arguments.arg_list: [{name, value}, …]`, and the
            # human-source form `vars: {name: value, …}` at step level
            # (what the emitter writes out and what step-through sees
            # when fed raw draft YAML). Render the source-form values
            # too so chained refs resolve.
            sim_output: dict[str, Any] = {}
            arg_list = rendered.get("arg_list") or []
            if isinstance(arg_list, list) and arg_list:
                for item in arg_list:
                    if isinstance(item, dict) and "name" in item:
                        sim_output[item["name"]] = item.get("value")
            else:
                top_vars = cur.get("vars")
                if isinstance(top_vars, dict):
                    for k, v in top_vars.items():
                        sim_output[k] = (_render_walk(v, f"vars.{k}")
                                         if isinstance(v, str) else v)
                else:
                    sim_output = {k: v for k, v in rendered.items()
                                  if k != "step_variables"}
            # FSR runtime contract: set_variable also surfaces vars at
            # the TOP LEVEL — `{{ vars.<name> }}` — so downstream Jinja
            # rendering resolves chained refs without going through
            # `vars.steps.<step>.<name>`. Mirror that here.
            for k, v in sim_output.items():
                vars_ctx[k] = v
            step_record["status"] = "simulated"
            step_record["simulated_from"] = "computed"
        elif stype == "decision":
            # Decision is a gateway — its "output" is just the chosen
            # branch label. Real navigation happens in step (3) below
            # via _decision_pick_branch; we evaluate it here too so the
            # trace shows the resolved label, not just `{}`.
            step_branches = cur.get("branches") or {}
            _, chosen_branch = _decision_pick_branch(
                rendered, step_branches, branch_choices.get(sid))
            sim_output = {"branch": chosen_branch} if chosen_branch else {}
            step_record["status"] = "simulated"
            step_record["simulated_from"] = "computed"
            if chosen_branch:
                step_record["note"] = f"branch: {chosen_branch}"
        elif stype == "workflow_reference":
            # Recurse into the target playbook. Live-FSR shape (see
            # reference_fsr_workflow_reference_runtime_shape memory):
            # vars.steps.<ref> = the child's full env dict.
            target = rendered.get("target")
            if not target:
                # Cross-collection IRI ref — can't resolve offline.
                # Output an empty dict with weak provenance so the
                # analyzer downgrades downstream missing_key warnings.
                sim_output = {}
                step_record["status"] = "simulated"
                step_record["simulated_from"] = "default_empty"
                step_record["note"] = (
                    "workflow_reference target unresolvable (no local "
                    "name; cross-collection IRI refs need a live FSR)")
            elif rendered.get("apply_async") is True:
                sim_output = {}
                step_record["status"] = "simulated"
                step_record["simulated_from"] = "computed"
                step_record["note"] = (
                    f"async ref to {target!r}; fire-and-forget, "
                    "no value returned to parent")
            else:
                child_input = (rendered.get("arguments")
                               if isinstance(rendered.get("arguments"),
                                             dict) else {})
                child_result = step_through_playbook(
                    yaml_text=yaml_text,
                    playbook=target,
                    input=child_input,
                    execute_safe_ops=execute_safe_ops,
                    max_steps=max_steps,
                )
                if child_result.get("ok") is False and \
                   not child_result.get("trace"):
                    sim_output = {}
                    step_record["simulated_from"] = "default_empty"
                    step_record["note"] = (
                        f"workflow_reference target {target!r}: "
                        f"{child_result.get('error', 'unknown error')}")
                else:
                    sim_output = _collect_child_env(
                        child_result.get("trace") or [])
                    step_record["simulated_from"] = "computed"
                    step_record["nested_trace"] = (
                        child_result.get("trace") or [])
                    step_record["note"] = (
                        f"recursed into {target!r}, "
                        f"{len(child_result.get('trace') or [])} step(s)")
                step_record["status"] = "simulated"
        elif stype == "manual_input":
            # FSR pauses for the user; we resolve from manual_choices,
            # else first option as a deterministic default. Friendly
            # YAML keeps `options:` at the step level — _normalize_
            # friendly_steps mirrors them under arguments but we also
            # fall back to the step dict directly for safety.
            options = rendered.get("options") or cur.get("options") or []
            picked = (manual_choices or {}).get(sid)
            if isinstance(options, list) and options:
                if picked is None or not any(
                    isinstance(o, dict)
                    and (o.get("display") or o.get("option")) == picked
                    for o in options
                ):
                    first = next((o for o in options if isinstance(o, dict)), {})
                    picked = first.get("display") or first.get("option")
            sim_output = {"option": picked} if picked else {}
            step_record["status"] = "simulated"
            step_record["simulated_from"] = "computed"
            if picked:
                step_record["note"] = f"option: {picked}"
                # Route through the option's next: target by treating
                # the picked label as the chosen branch.
                chosen_branch = picked
        elif stype.startswith("start"):
            sim_output = {}
            step_record["status"] = "simulated"
            step_record["simulated_from"] = "computed"
            step_record["note"] = "trigger entry"
        elif stype in {"stop", "end"}:
            step_record["status"] = "simulated"
            step_record["simulated_from"] = "computed"
            step_record["note"] = "terminal"
            step_record["output"] = {}
            step_record["output_shape"] = _infer_output_shape({})
            trace.append(step_record)
            break
        else:
            sim_output = {}
            step_record["status"] = "simulated"
            step_record["simulated_from"] = "default_empty"
            step_record["note"] = (
                f"step type {stype!r} not executed; rendered args "
                "captured for downstream inspection")

        # Update context. Use jinja key (name with spaces → underscores)
        # to match the FSR runtime contract, falling back to id.
        jkey = (cur.get("name") or sid).replace(" ", "_")
        if step_record["status"] == "executed":
            vars_ctx["steps"][jkey] = sim_output
            sample = sim_output[0] if (
                isinstance(sim_output, list) and sim_output
            ) else sim_output
            if isinstance(sample, dict):
                step_record["output_top_keys"] = sorted(sample.keys())
        else:
            vars_ctx["steps"][jkey] = sim_output if sim_output is not None else {}
            if isinstance(sim_output, dict):
                step_record["output_top_keys"] = sorted(sim_output.keys())
        step_record["output"] = sim_output
        step_record["output_shape"] = _infer_output_shape(sim_output)
        trace.append(step_record)

        # 3) Advance. For Decision steps, use the auto-evaluated branch
        # when the caller didn't pin one — otherwise the stepper would
        # always take the first branch and miss the heuristic-chosen
        # path the analyzer needs to trace.
        nav_branch = (branch_choices.get(sid) or chosen_branch)
        nxt_id = _next_step(cur, nav_branch, by_id)
        if not nxt_id or nxt_id not in by_id:
            break
        cur = by_id[nxt_id]

    return {
        "ok": first_error is None,
        "playbook": pb.get("name"),
        "trace": trace,
        "first_error": first_error,
        "steps_executed": len(trace),
    }

@mcp.tool()
def analyze_playbook(yaml_text: str,
                     playbook: str | None = None,
                     input: dict[str, Any] | None = None,
                     branch_choices: dict[str, str] | None = None,
                     manual_choices: dict[str, str] | None = None,
                     execute_safe_ops: bool = False,
                     max_steps: int = 30) -> dict[str, Any]:
    """Render-path validator: simulate the playbook then run heuristic
    checks against the trace.

    Wraps `step_through_playbook` + `compiler.render_analyzer.analyze`
    so a single call returns:

      { ok, playbook, trace, diagnostics, error_count, warning_count,
        first_error }

    `execute_safe_ops` defaults to False here (vs. True on
    step_through_playbook) because the analyzer is meant to run
    purely offline — users explicitly opt in to live ops.

    See RENDER_PATH_VALIDATOR_PLAN.md for the catalog of checks.
    """
    sim = step_through_playbook(
        yaml_text=yaml_text,
        playbook=playbook,
        input=input,
        branch_choices=branch_choices,
        manual_choices=manual_choices,
        execute_safe_ops=execute_safe_ops,
        max_steps=max_steps,
    )
    if not sim.get("trace"):
        return {**sim, "diagnostics": [],
                "error_count": 0, "warning_count": 0}

    from fsr_playbooks.compiler.render_analyzer import diagnostics_dict  # noqa: PLC0415
    # Pull the parsed playbook node so the analyzer can reach into
    # `arguments.required_fields` style metadata if it ever needs to;
    # current C3 doesn't, but P5 will.
    try:
        import yaml as _yaml  # noqa: PLC0415
        doc = _yaml.safe_load(yaml_text) or {}
        pbs = doc.get("playbooks") or []
        pb_node = next((p for p in pbs
                        if p.get("name") == sim.get("playbook")),
                       pbs[0] if pbs else None)
    except Exception:  # noqa: BLE001
        pb_node = None

    # C4 picklist drift only fires when the caller opts in to live
    # ops (`execute_safe_ops=True`) — picklist validation needs the
    # live FSR. Otherwise the analyzer skips it silently.
    pv = (precheck_picklist_value if execute_safe_ops
          else None)
    diagnostics = diagnostics_dict(sim["trace"], pb_node,
                                   picklist_validator=pv)
    return {
        "ok": sim["ok"] and not any(
            d["severity"] == "error" for d in diagnostics),
        "playbook": sim.get("playbook"),
        "trace": sim["trace"],
        "diagnostics": diagnostics,
        "error_count": sum(1 for d in diagnostics if d["severity"] == "error"),
        "warning_count": sum(1 for d in diagnostics if d["severity"] == "warning"),
        "first_error": sim.get("first_error"),
        "steps_executed": sim.get("steps_executed", 0),
    }

@mcp.tool()
def suggest_fix_for_diagnostic(diagnostic: dict[str, Any]
                               ) -> dict[str, Any]:
    """Translate one render-path diagnostic into a structured patch
    proposal the agent or visual editor can apply with one click.

    Input is the dict shape `analyze_playbook` returns inside its
    `diagnostics:` list. Output:

      {
        "ok":          true if a confident proposal was found,
        "step_id":     where the patch applies,
        "location":    arguments.<...> dotted path to the value to change,
        "before":      the current value (best-effort) or null,
        "after":       the proposed new value,
        "confidence":  "high" | "medium" | "low",
        "explanation": human-readable rationale for the user,
        "kind":        echoes the diagnostic kind for routing,
      }

    Heuristic-only — the agent is responsible for verifying the
    patch with `analyze_playbook` after applying it. Returns
    `{ok: false, reason}` when the diagnostic doesn't match a known
    auto-fix recipe.
    """
    kind = diagnostic.get("kind", "")
    sid = diagnostic.get("step_id", "")
    loc = diagnostic.get("location", "")
    sugg = diagnostic.get("suggestion", "") or ""
    actual = diagnostic.get("actual")
    expected = diagnostic.get("expected") or []
    extra = diagnostic.get("extra") or {}

    if kind == "unreachable_var_path":
        # Suggestion text from C1 doesn't carry the close-match
        # explicitly — the diagnostic just says "rename or remove".
        # We can't rename without knowing valid step names; surface
        # a low-confidence proposal and let the agent call
        # find_close_step_name (or scan the trace) for the target.
        missing = extra.get("missing_step", "")
        return {
            "ok": False,
            "kind": kind,
            "reason": (
                f"reference to {missing!r} can't be auto-fixed without "
                "knowing the intended target — agent should pick the "
                "closest existing step name from the trace and rename "
                f"{missing!r} → <chosen_name> at {loc}"),
        }

    if kind == "missing_key":
        # Suggestion form: "did you mean 'real_key'?". Extract.
        import re as _re
        m = _re.search(r"did you mean ['\"]([^'\"]+)['\"]", sugg)
        if not m:
            return {"ok": False, "kind": kind,
                    "reason": "no close-key suggestion available; "
                              "user must pick the right key from "
                              f"expected={expected}"}
        # actual carries the bad segment; before/after operate on
        # the offending JINJA path. We can't surgically rewrite the
        # template without re-parsing the value at `location`, so
        # return a "swap this segment" intent the editor can apply.
        return {
            "ok": True,
            "kind": kind,
            "step_id": sid,
            "location": loc,
            "before": actual,
            "after": m.group(1),
            "confidence": "high",
            "explanation": (
                f"replace key {actual!r} with {m.group(1)!r} in the "
                f"template at {loc} — close-match against the producer's "
                f"known output keys"),
        }

    if kind == "picklist_drift":
        if not expected:
            return {"ok": False, "kind": kind,
                    "reason": "no close matches from the picklist "
                              "validator — user must pick a valid value"}
        return {
            "ok": True,
            "kind": kind,
            "step_id": sid,
            "location": loc,
            "before": actual,
            "after": expected[0],
            "confidence": "high" if len(expected) == 1 else "medium",
            "explanation": (
                f"swap picklist value {actual!r} → {expected[0]!r} at "
                f"{loc}" + (f" (other matches: {expected[1:3]})"
                            if len(expected) > 1 else "")),
        }

    if kind == "required_arg_empty":
        # Best we can do: emit a TODO scaffold the user fills in.
        field = diagnostic.get("path", "")
        return {
            "ok": True,
            "kind": kind,
            "step_id": sid,
            "location": loc,
            "before": actual,
            "after": f"TODO_set_{field}",
            "confidence": "low",
            "explanation": (
                f"required arg {field!r} rendered empty — set it to a "
                "literal or fix the upstream Jinja expression. "
                "The TODO placeholder will trip a CI check until set."),
        }

    return {
        "ok": False,
        "kind": kind,
        "reason": f"no auto-fix recipe for diagnostic kind {kind!r}",
    }

@mcp.tool()
def step_test(yaml_text: str,
              step_id: str,
              playbook: str | None = None,
              input: dict[str, Any] | None = None,
              execute_safe_ops: bool = True,
              confirm: bool = False) -> dict[str, Any]:
    """Single-step probe: render one step's args + (if safe) execute it.

    Targeted variant of `step_through_playbook` — pinpoints a single step
    by `id` (or by name with spaces→underscores). Useful for the visual
    editor's per-node Verify tab where the agent / user wants to confirm
    one step compiles and executes cleanly without walking the full
    playbook.

    Args:
      yaml_text: simplified-IR YAML.
      step_id: target step's `id:` field, or its `name:` (spaces collapse
        to underscores) — whichever matches first.
      playbook: which playbook to look in (defaults to the first).
      input: vars.input.params.* for jinja rendering.
      execute_safe_ops: if False, render only — never live-execute.
      confirm: if True, execute non-safe ops too (user has acknowledged
        the risk via the Verify-tab confirm dialog). Without this, a
        non-safe op short-circuits with `status="needs_confirm"` and a
        `risk` / `risk_category` payload the UI uses to render its
        warning. Safe ops execute either way.

    Returns:
      `{ok, step_id, type, rendered_args, output, output_top_keys,
        status, note}` — same per-step record shape `step_through_playbook`
      emits, plus a `verification_recorded` flag when run_op fired.
    """
    try:
        import yaml as _yaml
        doc = _yaml.safe_load(yaml_text) or {}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"yaml parse failed: {exc}"}

    pbs = doc.get("playbooks") or []
    if not pbs:
        return {"ok": False, "error": "no playbooks in YAML"}
    pb = next((p for p in pbs if p.get("name") == playbook), pbs[0])
    steps = pb.get("steps") or []

    # Match the IR's id-synthesis: when a step omits `id:`, the parser
    # slugifies `name:` (lowercase, non-alphanum → `_`). The visual layer
    # sends that synthesized id, so we must apply the same algorithm here.
    from fsr_playbooks.compiler.parser import _slugify  # local import: avoid cold-start cost
    target = None
    for s in steps:
        if not isinstance(s, dict):
            continue
        if s.get("id") == step_id:
            target = s
            break
        nm = s.get("name")
        if isinstance(nm, str) and nm and _slugify(nm) == step_id:
            target = s
            break
    if target is None:
        return {"ok": False, "error": f"step {step_id!r} not found"}

    sid = target.get("id") or (_slugify(target["name"]) if target.get("name") else step_id)
    stype = target.get("type", "")
    raw_args = target.get("arguments") or target.get("args") or {}
    vars_ctx: dict[str, Any] = {"input": {"params": dict(input or {})},
                                 "steps": {}}
    # Overlay manual_input samples + any future per-step synthetic values
    # from the `# fsrpb:samples` sidecar so downstream Jinja in this step
    # resolves against the author's test data without a live run.
    #
    # Samples are stored by step.id (slug), but FSR's runtime keys
    # `vars.steps.<key>` by `name.replace(" ", "_")` (see
    # `compiler.typed_walker._jinja_key`). Expose under both forms so a
    # template using either resolves correctly.
    from fsr_playbooks.compiler.samples import extract_samples_block, overlay_into_vars
    samples_map, _stripped = extract_samples_block(yaml_text)
    pb_samples = samples_map.get(pb.get("name") or "", {}) or {}
    expanded: dict[str, Any] = {}
    for s in steps:
        if not isinstance(s, dict):
            continue
        nm = s.get("name")
        # Distinct local name — outer `sid` (the target's id) must
        # survive this loop intact for the result record.
        sid_iter = s.get("id") or (_slugify(nm) if isinstance(nm, str) and nm else None)
        if not sid_iter:
            continue
        # Step-level mock_result wins over the sidecar sample for the
        # same step — authors typically save a mock right after a real
        # Test step run, so it's the freshest synthetic value we have.
        # Surfaced under the step output shape FSR exposes
        # (vars.steps.<key> directly = the connector's response body).
        s_args = s.get("arguments") if isinstance(s.get("arguments"), dict) else {}
        mock = s_args.get("mock_result") if isinstance(s_args, dict) else None
        payload = mock if mock is not None else pb_samples.get(sid_iter)
        if payload is None:
            continue
        expanded[sid_iter] = payload
        if isinstance(nm, str) and nm:
            expanded[nm.replace(" ", "_")] = payload
    overlay_into_vars(expanded, vars_ctx)

    client = _shared._live_client()
    render_errors: list[str] = []

    def _render(value: Any, path: str = "") -> Any:
        if isinstance(value, str):
            if "{{" not in value or client is None:
                return value
            try:
                out = client.post(
                    "/api/wf/api/jinja-editor/",
                    data={"template": value,
                          "values": {"vars": vars_ctx}},
                )
                if isinstance(out, dict):
                    for k in ("result", "output", "rendered", "value"):
                        if k in out:
                            return out[k]
                    return out
                return out if out is not None else value
            except Exception as exc:  # noqa: BLE001
                render_errors.append(f"{path}: {exc}")
                return value
        if isinstance(value, dict):
            return {k: _render(v, f"{path}.{k}" if path else k)
                    for k, v in value.items()}
        if isinstance(value, list):
            return [_render(v, f"{path}[{i}]") for i, v in enumerate(value)]
        return value

    rendered = _render(raw_args) if isinstance(raw_args, dict) else raw_args

    record: dict[str, Any] = {
        "ok": not render_errors,
        "step_id": sid,
        "type": stype,
        "rendered_args": rendered,
        "output": None,
        "output_top_keys": [],
        "status": "rendered",
        "note": "",
        "verification_recorded": False,
    }
    if render_errors:
        record["status"] = "render_failed"
        record["note"] = "; ".join(render_errors[:3])
        return record

    if not execute_safe_ops or stype != "connector":
        return record

    cn = (rendered.get("connector") if isinstance(rendered, dict) else None) \
        or target.get("connector")
    opn = (rendered.get("operation") if isinstance(rendered, dict) else None) \
        or target.get("operation")
    if not (cn and opn):
        record["note"] = "connector/operation missing — render-only"
        return record

    cat = _shared._safe_op_category(cn, opn)
    risk = tools_discovery._op_risk(opn, cat)
    if risk != "safe" and not confirm:
        # Surface the risk to the UI instead of silently skipping. The
        # Verify tab renders the warning + a "Run anyway" affordance that
        # re-invokes step_test with confirm=True.
        record["status"] = "needs_confirm"
        record["risk"] = risk
        record["risk_category"] = cat
        record["note"] = (
            f"{opn!r} is classified {risk} ({cat}). Re-run with confirm=true "
            "to execute against the live FSR instance."
        )
        return record

    # The rendered args envelope is `{connector, operation, config,
    # params: {...}}` — we have to pass just the inner connector params
    # to run_op. Sending the envelope as-is means the connector can't
    # find any of its declared params (it sees keys like `connector` /
    # `operation` / `params` at the top level instead).
    inner_params: dict[str, Any] = {}
    if isinstance(rendered, dict):
        p = rendered.get("params")
        if isinstance(p, dict):
            inner_params = p
        else:
            # Fallback for shapes that already pass the param dict
            # directly (older friendly form / non-standard YAML).
            inner_params = {k: v for k, v in rendered.items()
                            if k not in {"connector", "operation", "config", "params"}}
    try:
        op_result = tools_execution.run_op(connector=cn, op=opn,
                           params=inner_params,
                           confirm=confirm)
    except Exception as exc:  # noqa: BLE001
        tools_execution._record_verification(cn, opn, "tested_fail", str(exc)[:2000])
        record["ok"] = False
        record["status"] = "exec_failed"
        record["note"] = str(exc)
        record["verification_recorded"] = True
        return record

    if op_result.get("ok"):
        record["output"] = op_result.get("data")
        record["output_top_keys"] = op_result.get("output_top_keys") or []
        record["status"] = "executed"
        tools_execution._record_verification(cn, opn, "tested_pass",
                             f"step {sid!r} executed via step_test")
    else:
        record["ok"] = False
        record["status"] = "exec_failed"
        record["note"] = op_result.get("message", "") or "run_op returned ok=false"
        tools_execution._record_verification(cn, opn, "tested_fail",
                             record["note"][:2000])
    record["verification_recorded"] = True
    return record


# ---------------------------------------------------------------------------
# Recipe prechecks (building blocks for the Runs rung)
# ---------------------------------------------------------------------------

@mcp.tool()
def precheck_connector_installed(name: str,
                                 version: str | None = None) -> dict[str, Any]:
    """Verify a connector is installed on the live FSR before authoring
    a recipe or playbook against it.

    Catches the silent-failure case where a recipe ships compile-clean
    but the first connector step fails at runtime with "configuration
    not found." On miss, returns close-match suggestions drawn from the
    appliance's actual catalog.
    """
    client = _shared._live_client()
    if client is None:
        return {"ok": False, "code": "no_live_fsr",
                "message": "FSR instance not configured"}
    from recipes.prechecks import check_connector_installed
    result = check_connector_installed(client, name, version).to_dict()
    _persist_precheck_verification("connector", name, "live_api_get", result)
    return result

@mcp.tool()
def synthesize_http_step(entry_id: int,
                         step_name: str = "Call API") -> dict[str, Any]:
    """Translate a catalog entry into a FortiSOAR HTTP-connector step.

    Deterministic transformer (no LLM). Returns a YAML-ready dict shaped
    like the simplified IR for a `connector` step targeting the `http`
    connector's `http_request` op, with method/rest_api/auth_type/header/
    parameter pre-filled from the catalog entry.

    The agent should still review and fill in: secrets (basic_password,
    bearer_token, api_key), the base URL (catalog stores path only),
    response_path for nested payloads, and any body shape for write ops.
    """
    with _db() as conn:
        try:
            row = conn.execute(
                "SELECT e.id, p.name AS product, e.action, e.http_method, "
                "e.http_path, e.auth_method, e.parameters_json, "
                "e.description, e.source_url "
                "FROM catalog.entries e JOIN catalog.products p "
                "ON p.id = e.product_id WHERE e.id = ?",
                (entry_id,),
            ).fetchone()
        except sqlite3.OperationalError as exc:
            return {"error": f"catalog DB unavailable: {exc}"}
    if not row:
        return {"error": f"entry_id {entry_id} not found"}
    params_raw = row["parameters_json"] or "[]"
    try:
        params_list = json.loads(params_raw)
    except (TypeError, ValueError):
        params_list = []
    query_params: dict[str, str] = {}
    for p in params_list if isinstance(params_list, list) else []:
        if not isinstance(p, dict):
            continue
        loc = (p.get("in") or "").lower()
        nm = p.get("name")
        if nm and loc in ("query", ""):
            query_params[nm] = p.get("example") or f"<{nm}>"
    return {
        "step_type": "connector",
        "name": step_name,
        "connector": "http",
        "operation": "http_request",
        "args": {
            "method": (row["http_method"] or "GET").upper(),
            "rest_api": row["http_path"] or "",
            "auth_type": _map_http_auth(row["auth_method"]),
            "header": {},
            "parameter": query_params,
        },
        "_note": (
            f"Synthesized from {row['product']}/{row['action']}. "
            "TODO: fill secrets, prefix rest_api with base URL, set "
            "response_path for nested payloads, populate body for "
            "write operations."
        ),
        "_source_url": row["source_url"],
    }


# ---------------------------------------------------------------------------
# step_through_playbook — pre-push stepper (in-editor, no FSR writes)
# ---------------------------------------------------------------------------

# `dry_run_playbook` (compile + push + run + cleanup) is the full E2E loop
# and modifies live FSR state. The stepper below is a *pre-push* check:
# walk the playbook step-by-step against accumulated context, render each
# step's arguments, execute safe connector ops, simulate the rest, and
# surface per-step outputs so the agent can spot rendering failures and
# shape mismatches without touching the appliance's record store.

def _next_step(step: dict, taken_branch: str | None,
               by_id: dict[str, dict]) -> str | None:
    """Pick the next step id for the stepper.

    Linear: follow `next`. Decision: follow `branches[taken_branch]` if
    provided, else the first branch (deterministic default — agent can
    pin a path with branch_choices).
    """
    nxt = step.get("next")
    if nxt:
        return nxt
    branches = step.get("branches") or {}
    if not branches:
        return None
    if taken_branch and taken_branch in branches:
        return branches[taken_branch]
    # Deterministic default: lowest-key branch.
    first_key = sorted(branches.keys())[0]
    return branches[first_key]


def _infer_output_shape(value: Any) -> dict[str, Any]:
    """Summarize a simulated step output so downstream analyzer checks
    can reason about what keys exist, what types they are, and a small
    sample without re-walking the full payload.

    Used by render-path analyzer (RENDER_PATH_VALIDATOR_PLAN.md C2/C5/C6).
    """
    def _t(v: Any) -> str:
        if v is None: return "null"
        if isinstance(v, bool): return "bool"
        if isinstance(v, int): return "int"
        if isinstance(v, float): return "float"
        if isinstance(v, str): return "string"
        if isinstance(v, list): return "list"
        if isinstance(v, dict): return "dict"
        return type(v).__name__

    if isinstance(value, dict):
        return {
            "kind": "dict",
            "top_keys": sorted(value.keys()),
            "types": {k: _t(v) for k, v in value.items()},
            "sample": {k: (v if not isinstance(v, (dict, list)) else _t(v))
                       for k, v in list(value.items())[:8]},
        }
    if isinstance(value, list):
        head = value[0] if value else None
        return {
            "kind": "list",
            "length": len(value),
            "item_type": _t(head),
            "item_keys": (sorted(head.keys())
                          if isinstance(head, dict) else []),
        }
    return {"kind": _t(value), "value": value if isinstance(value,
            (str, int, float, bool, type(None))) else str(value)[:120]}


def _truthy(v: Any) -> bool:
    """Loose truthiness matching FSR's runtime behavior — strings like
    'false' / '0' / 'no' / '' / 'null' all count as falsy because Jinja
    rendering reduces booleans to strings before the engine sees them."""
    if v is None: return False
    if isinstance(v, bool): return v
    if isinstance(v, (int, float)): return v != 0
    if isinstance(v, str):
        return v.strip().lower() not in ("", "false", "0", "no", "null", "none")
    if isinstance(v, (list, dict)):
        return len(v) > 0
    return bool(v)


def _coerce_literal_list(value: Any) -> list[Any]:
    """Best-effort offline fallback for ``for_each.item`` — when the
    live Jinja engine is absent the renderer returns the template
    string verbatim. We parse trivial inline literals like
    ``"{{ [1, 2, 3] }}"`` via ``ast.literal_eval`` so the simulator
    can iterate without an FSR. Anything fancier resolves to ``[]``
    and the caller treats that as an unknown-length loop.
    """
    import ast as _ast
    if isinstance(value, list):
        return value
    if not isinstance(value, str):
        return []
    s = value.strip()
    if s.startswith("{{") and s.endswith("}}"):
        s = s[2:-2].strip()
    if not s:
        return []
    try:
        out = _ast.literal_eval(s)
    except (ValueError, SyntaxError):
        return []
    return out if isinstance(out, list) else []


def _collect_child_env(child_trace: list[dict[str, Any]]) -> dict[str, Any]:
    """Walk a child playbook's trace and produce the flat env dict
    that ``vars.steps.<ref_step>`` resolves to in real FSR.

    Live-FSR shape (per ref_sync_basic / ref_with_arguments fixtures):
    a single dict containing every set_variable / mock_result key any
    step in the child wrote, plus a ``task_id`` placeholder. Keys
    later in the trace win on conflict, mirroring FSR's last-write-
    wins semantics on env top-level.
    """
    env: dict[str, Any] = {}
    for rec in child_trace:
        out = rec.get("output")
        if isinstance(out, dict):
            for k, v in out.items():
                if k == "task_id":
                    continue
                env[k] = v
    env["task_id"] = "<simulated>"
    env.setdefault("debug", True)
    return env


def _simulate_loop_body(stype: str, rendered_body: dict[str, Any]) -> dict[str, Any]:
    """Per-iteration output for a step running inside a for_each.
    Mirrors the real-FSR shape captured by the render_path probe
    (see reference_fsr_for_each_runtime_shape memory): each
    iteration's output is a flat dict of the body's set_var /
    mock_result keys, augmented with a ``task_id`` placeholder so
    downstream consumers don't see a structurally-different value
    than they would at runtime.
    """
    out: dict[str, Any] = {}
    if stype == "set_variable":
        arg_list = rendered_body.get("arg_list")
        if isinstance(arg_list, list):
            for it in arg_list:
                if isinstance(it, dict) and "name" in it:
                    out[it["name"]] = it.get("value")
        else:
            for k, v in rendered_body.items():
                if k in ("for_each", "step_variables", "condition",
                         "mock_result"):
                    continue
                out[k] = v
    elif stype == "workflow_reference":
        # for_each + workflow_reference: each iteration's "body" is a
        # nested child run. We can't recurse here without yaml_text +
        # access to the simulator entry point, so emit a stub keyed
        # off the rendered child arguments. The non-loop case in the
        # main simulate block does the real recursion; this handler
        # is the simplification for high-volume per-iteration cases.
        # If the child can be reached statically we emit its declared
        # set_var keys; otherwise an empty dict.
        if isinstance(rendered_body.get("arguments"), dict):
            for k, v in rendered_body["arguments"].items():
                out[f"_arg_{k}"] = v
    elif "mock_result" in rendered_body:
        mock = rendered_body["mock_result"]
        if isinstance(mock, dict):
            out.update(mock)
    out.setdefault("task_id", "<simulated>")
    return out


def _decision_pick_branch(rendered_args: dict[str, Any],
                          step_branches: dict[str, str],
                          pinned: str | None) -> tuple[str | None, str | None]:
    """Auto-evaluate a Decision step's conditions to pick a branch.

    Returns ``(next_step_id, chosen_label)``. Falls back through:
      1. ``pinned`` from caller's branch_choices
      2. first condition whose rendered ``when`` is truthy
      3. condition flagged ``default: true``
      4. step's first branch (deterministic default)
    Empty result if no branches at all.
    """
    if not step_branches:
        return None, None

    if pinned and pinned in step_branches:
        return step_branches[pinned], pinned

    conditions = rendered_args.get("conditions") or []
    default_label: str | None = None
    if isinstance(conditions, list):
        for cond in conditions:
            if not isinstance(cond, dict):
                continue
            label = cond.get("display") or cond.get("label")
            if cond.get("default") is True and label and default_label is None:
                default_label = label
                continue
            when = cond.get("when")
            if when is None:
                continue
            if _truthy(when) and label and label in step_branches:
                return step_branches[label], label

    if default_label and default_label in step_branches:
        return step_branches[default_label], default_label
    first_key = sorted(step_branches.keys())[0]
    return step_branches[first_key], first_key


def _normalize_friendly_steps(steps: list[dict]) -> None:
    """Bridge from the visual editor's friendly YAML to the wire shape
    the stepper helpers (`_decision_pick_branch`, `_next_step`,
    manual_input simulator) expect. Mutates `steps` in-place.

    Two friendly-form shortcuts the simulator otherwise misses:

    * Decision: friendly form lists `conditions: [{display, when, next}]`
      with no top-level `branches:` map. Helpers look up
      `step.branches[label] -> step_id`; without it, every decision
      step terminates the walk. Synthesize the map from each
      condition's `next:` so authors don't have to maintain two forms.

    * manual_input: friendly form puts `options: [...]` at the step
      level. The simulator reads `rendered_args.options`; copy the
      step-level list into `arguments.options` so it surfaces, and
      mirror each option's `next:` into a `branches:` map so the
      stepper advances past the prompt to the chosen target.
    """
    for s in steps:
        if not isinstance(s, dict):
            continue
        stype = (s.get("type") or "").lower()
        if stype == "decision":
            if not s.get("branches"):
                conds = (s.get("conditions")
                         or (s.get("arguments") or {}).get("conditions")
                         or [])
                branches: dict[str, str] = {}
                for c in conds:
                    if not isinstance(c, dict):
                        continue
                    label = c.get("display") or c.get("label")
                    target = c.get("next")
                    if label and isinstance(target, str) and target:
                        branches[str(label)] = target
                if branches:
                    s["branches"] = branches
            # Surface the conditions list under arguments so the
            # rendered_args path the picker reads from finds it.
            args = s.setdefault("arguments", {})
            if isinstance(args, dict) and "conditions" not in args:
                friendly = s.get("conditions")
                if isinstance(friendly, list):
                    args["conditions"] = friendly
        elif stype == "manual_input":
            opts = s.get("options")
            if isinstance(opts, list) and opts:
                args = s.setdefault("arguments", {})
                if isinstance(args, dict):
                    args.setdefault("options", opts)
                # Mirror option targets into a branches map so the
                # stepper can advance to the chosen next step.
                if not s.get("branches"):
                    branches = {}
                    for o in opts:
                        if not isinstance(o, dict):
                            continue
                        label = o.get("display") or o.get("option")
                        target = o.get("next")
                        if label and isinstance(target, str) and target:
                            branches[str(label)] = target
                    if branches:
                        s["branches"] = branches

# =====================================================================
# Stateful debug-session tools (VISUAL_EDITOR_PLAN.md Phase 5.3-5.7).
# Wrap `debug_session.DebugSession` for the visual editor's debug
# drawer. The one-shot `step_through_playbook` above is kept as the
# stable façade for analyzer / verify_playbook / agent-loop callers.
# =====================================================================

@mcp.tool()
def start_debug_session(
    yaml_text: str,
    playbook: str | None = None,
    input: dict[str, Any] | None = None,
    branch_choices: dict[str, str] | None = None,
    manual_choices: dict[str, str] | None = None,
    breakpoints: list[str] | None = None,
    execute_safe_ops: bool = True,
    execute_unsafe_ops: bool = False,
    max_steps: int = 30,
) -> dict[str, Any]:
    """Create a fresh debug session at the playbook's start step.

    Returns `{ok, status}` where `status` includes `session_id`,
    `paused_at` (next step id about to run), and `done`. Use the
    `session_id` for subsequent `step_debug_session` /
    `continue_debug_session` / `stop_debug_session` calls.
    """
    from .debug_session import build_session, get_store  # noqa: PLC0415
    sess, err = build_session(
        yaml_text=yaml_text,
        playbook=playbook,
        input=input,
        branch_choices=branch_choices,
        manual_choices=manual_choices,
        breakpoints=breakpoints,
        execute_safe_ops=execute_safe_ops,
        execute_unsafe_ops=execute_unsafe_ops,
        max_steps=max_steps,
    )
    if sess is None:
        return {"ok": False, "error": err}
    # SessionStore.create allocates the session_id.
    store = get_store()
    # We already built the DebugSession; re-create through the store
    # so we get a fresh id and TTL bookkeeping.
    import secrets as _secrets  # noqa: PLC0415
    sess.session_id = _secrets.token_urlsafe(12)
    with store._lock:  # noqa: SLF001
        store._evict_expired_locked()  # noqa: SLF001
        store._sessions[sess.session_id] = sess  # noqa: SLF001
    return {"ok": True, "status": sess.as_status()}


@mcp.tool()
def step_debug_session(
    session_id: str,
    branch_choice_override: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Advance the session by exactly one step.

    `branch_choice_override` lets the caller pin a decision branch
    just for the upcoming step (merged into the session's persistent
    `branch_choices`). Returns `{ok, status}` — when `done=True` no
    further `advance` calls will produce records.
    """
    from .debug_session import get_store  # noqa: PLC0415
    sess = get_store().get(session_id)
    if sess is None:
        return {"ok": False, "error": f"unknown session {session_id!r}"}
    if branch_choice_override:
        sess.branch_choices.update(branch_choice_override)
    rec = sess.advance_one()
    return {"ok": True, "status": sess.as_status(),
            "advanced": rec is not None}


@mcp.tool()
def continue_debug_session(
    session_id: str,
    until_step_id: str | None = None,
    add_breakpoints: list[str] | None = None,
    max_advance: int = 100,
) -> dict[str, Any]:
    """Run steps until the session hits a breakpoint, the specified
    `until_step_id`, the session's `max_steps` cap, or `max_advance`
    (this-call cap to prevent UI hangs on infinite loops).

    `add_breakpoints` is merged into the session's persistent
    breakpoint set before continuing.
    """
    from .debug_session import get_store  # noqa: PLC0415
    sess = get_store().get(session_id)
    if sess is None:
        return {"ok": False, "error": f"unknown session {session_id!r}"}
    if add_breakpoints:
        sess.breakpoints.update(add_breakpoints)
    advanced = 0
    stop_reason = "done"
    for _ in range(max_advance):
        # Check breakpoint / until before advancing — if we're paused
        # AT this step, the caller wants control before it runs.
        peek = sess.peek_next_id()
        if peek is None:
            stop_reason = "done"
            break
        if advanced > 0 and peek in sess.breakpoints:
            stop_reason = "breakpoint"
            break
        if advanced > 0 and until_step_id and peek == until_step_id:
            stop_reason = "until_step"
            break
        rec = sess.advance_one()
        if rec is None:
            stop_reason = "done"
            break
        advanced += 1
    else:
        stop_reason = "max_advance"
    return {
        "ok": True,
        "status": sess.as_status(),
        "advanced": advanced,
        "stop_reason": stop_reason,
    }


@mcp.tool()
def stop_debug_session(session_id: str) -> dict[str, Any]:
    """Drop a debug session. Returns the final status snapshot."""
    from .debug_session import get_store  # noqa: PLC0415
    store = get_store()
    sess = store.get(session_id)
    if sess is None:
        return {"ok": False, "error": f"unknown session {session_id!r}"}
    snapshot = sess.as_status()
    snapshot["trace"] = list(sess.trace)
    store.drop(session_id)
    return {"ok": True, "status": snapshot}


@mcp.tool()
def get_debug_session(session_id: str) -> dict[str, Any]:
    """Return the current status snapshot + full trace so far.
    Touches `last_touched` (so the session stays alive while the UI
    is polling it)."""
    from .debug_session import get_store  # noqa: PLC0415
    sess = get_store().get(session_id)
    if sess is None:
        return {"ok": False, "error": f"unknown session {session_id!r}"}
    status = sess.as_status()
    status["trace"] = list(sess.trace)
    status["vars_keys"] = sorted(sess.vars_ctx.get("steps", {}).keys())
    return {"ok": True, "status": status}
