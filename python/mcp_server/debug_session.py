"""Stateful debug-session machinery for the visual editor's debug runner.

Wraps the same step-by-step simulator that `step_through_playbook`
runs in a single call, but persists state across calls so the
frontend can drive ⏭ / ⏯ / ⏹ controls, set breakpoints, and override
branch choices mid-run.

The one-shot `step_through_playbook` tool is intentionally left
untouched (parallel implementation) — it would otherwise have to
ship as part of this refactor and risk regressing the analyzer /
verify_playbook / agent-loop callers that depend on its exact
behavior today. The duplication is acknowledged tech debt; track
under VISUAL_EDITOR_PLAN.md Phase 5.

Helpers (`_next_step`, `_simulate_loop_body`, `_decision_pick_branch`,
`_truthy`, `_coerce_literal_list`, `_collect_child_env`,
`_infer_output_shape`) are imported from `tools_analysis` so the
two implementations share the same primitives.
"""
from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field
from threading import RLock
from typing import Any


# Sessions auto-expire after this many seconds of inactivity. Touched
# on every access (start/step/continue/stop/get).
_SESSION_TTL_SECONDS = 30 * 60


@dataclass
class DebugSession:
    """One in-flight playbook simulation.

    State is mutated by `advance_one()`. Inspect via `as_status()`.
    """
    session_id: str
    yaml_text: str
    pb_name: str
    steps: list[dict[str, Any]]
    by_id: dict[str, dict[str, Any]]
    cur: dict[str, Any] | None
    vars_ctx: dict[str, Any]
    trace: list[dict[str, Any]] = field(default_factory=list)
    first_error: dict[str, Any] | None = None
    branch_choices: dict[str, str] = field(default_factory=dict)
    manual_choices: dict[str, str] = field(default_factory=dict)
    breakpoints: set[str] = field(default_factory=set)
    execute_safe_ops: bool = True
    execute_unsafe_ops: bool = False
    max_steps: int = 30
    steps_advanced: int = 0
    done: bool = False
    last_touched: float = field(default_factory=time.time)

    # ----- introspection -------------------------------------------------

    def peek_next_id(self) -> str | None:
        if self.done or self.cur is None:
            return None
        return self.cur.get("id")

    def as_status(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "playbook": self.pb_name,
            "done": self.done,
            "paused_at": self.peek_next_id(),
            "steps_advanced": self.steps_advanced,
            "trace_len": len(self.trace),
            "first_error": self.first_error,
            "breakpoints": sorted(self.breakpoints),
            "last_step": self.trace[-1] if self.trace else None,
            "trace": list(self.trace),
        }

    # ----- core stepping -------------------------------------------------

    def advance_one(self) -> dict[str, Any] | None:
        """Run exactly one step. Returns the step's trace record (or
        None if already done / max_steps reached)."""
        self.last_touched = time.time()
        if self.done or self.cur is None:
            self.done = True
            return None
        if self.steps_advanced >= self.max_steps:
            self.done = True
            return None
        # Delegate to the same helper logic the one-shot tool uses.
        rec = _execute_one_step(self)
        self.steps_advanced += 1
        if rec is not None:
            self.trace.append(rec)
        # _execute_one_step is responsible for advancing self.cur and
        # setting self.done on terminal / dead-end / break.
        return rec


# =====================================================================
# Per-step execution — extracted from tools_analysis.step_through_playbook
# loop body. Mutates session.vars_ctx / session.cur / session.done /
# session.first_error.
# =====================================================================

def _execute_one_step(s: DebugSession) -> dict[str, Any] | None:
    # Late imports to avoid a circular dep with tools_analysis (which
    # imports debug_session for the new tool surfaces).
    from . import _shared
    from . import tools_discovery
    from . import tools_execution
    from .tools_analysis import (
        _next_step, _infer_output_shape, _truthy,
        _coerce_literal_list, _collect_child_env,
        _simulate_loop_body, _decision_pick_branch,
        step_through_playbook,
    )

    cur = s.cur
    if cur is None:
        s.done = True
        return None

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

    try:
        from compiler.render_paths import (  # noqa: PLC0415
            consumed_paths_dict, extract_picklist_refs)
        raw_args_for_extract = cur.get("arguments") or cur.get("args") or {}
        step_record["consumed_paths"] = consumed_paths_dict(
            raw_args_for_extract)
        step_record["picklist_refs"] = extract_picklist_refs(
            raw_args_for_extract)
    except Exception:  # noqa: BLE001
        pass

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
                          "values": {"vars": s.vars_ctx}},
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

    # for_each iteration
    fe = (cur.get("for_each")
          if isinstance(cur.get("for_each"), dict) else None)
    if fe is None and isinstance(raw_args, dict):
        fe_in_args = raw_args.get("for_each")
        if isinstance(fe_in_args, dict):
            fe = fe_in_args
    if fe is not None:
        item_template = fe.get("item", "")
        rendered_item = (_render_walk(item_template)
                         if isinstance(item_template, str)
                         else item_template)
        items = _coerce_literal_list(rendered_item)
        cond_tpl = fe.get("condition") or ""
        break_tpl = fe.get("break_loop") or ""
        iterations: list[dict[str, Any]] = []
        for it in items:
            s.vars_ctx["item"] = it
            if cond_tpl:
                if not _truthy(_render_walk(cond_tpl)):
                    continue
            body_rendered = (_render_walk(raw_args)
                             if isinstance(raw_args, dict) else {})
            iterations.append(_simulate_loop_body(stype, body_rendered))
            if break_tpl and _truthy(_render_walk(break_tpl)):
                break
        s.vars_ctx.pop("item", None)
        step_record["rendered_args"] = rendered
        step_record["status"] = "simulated"
        step_record["simulated_from"] = "computed"
        step_record["loop_iterations"] = len(iterations)
        step_record["output"] = iterations
        step_record["output_shape"] = _infer_output_shape(iterations)
        jkey = (cur.get("name") or sid).replace(" ", "_")
        s.vars_ctx["steps"][jkey] = iterations
        nxt_id = cur.get("next")
        s.cur = s.by_id.get(nxt_id) if nxt_id else None
        if s.cur is None:
            s.done = True
        return step_record

    # Step-level skip condition
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
        s.vars_ctx["steps"][jkey] = {}
        nxt_id = cur.get("next")
        s.cur = s.by_id.get(nxt_id) if nxt_id else None
        if s.cur is None:
            s.done = True
        return step_record

    if render_errors:
        step_record["note"] = "jinja render failed: " + "; ".join(
            render_errors[:3])
        if s.first_error is None:
            s.first_error = {"step_id": sid,
                             "message": render_errors[0]}
    step_record["rendered_args"] = rendered

    sim_output: Any = None
    chosen_branch: str | None = None

    mock_out = rendered.get("mock_result")
    if mock_out is not None and stype not in {"set_variable", "decision",
                                              "manual_input"}:
        sim_output = mock_out
        step_record["status"] = "simulated"
        step_record["simulated_from"] = "mock_result"
    elif stype == "connector" and s.execute_safe_ops:
        cn = rendered.get("connector") or cur.get("connector")
        opn = rendered.get("operation") or cur.get("operation")
        cat = _shared._safe_op_category(cn or "", opn or "")
        risk = tools_discovery._op_risk(opn or "", cat)
        if risk == "safe" and cn and opn:
            try:
                op_result = tools_execution.run_op(
                    connector=cn, op=opn, params=rendered, confirm=False)
                if op_result.get("ok"):
                    sim_output = op_result.get("data")
                    step_record["output_top_keys"] = (
                        op_result.get("output_top_keys") or [])
                    step_record["status"] = "executed"
                    step_record["simulated_from"] = "live_run"
                else:
                    step_record["status"] = "exec_failed"
                    step_record["note"] = op_result.get("message", "")
                    if s.first_error is None:
                        s.first_error = {
                            "step_id": sid,
                            "message": step_record["note"]
                            or "connector exec failed",
                        }
            except Exception as exc:  # noqa: BLE001
                step_record["status"] = "exec_failed"
                step_record["note"] = str(exc)
                if s.first_error is None:
                    s.first_error = {"step_id": sid, "message": str(exc)}
        else:
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
                   "(each gated) to commit." if not s.execute_unsafe_ops
                   else "execute_unsafe_ops=True; commit via run_op."))
    elif stype == "set_variable":
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
        for k, v in sim_output.items():
            s.vars_ctx[k] = v
        step_record["status"] = "simulated"
        step_record["simulated_from"] = "computed"
    elif stype == "decision":
        step_branches = cur.get("branches") or {}
        _, chosen_branch = _decision_pick_branch(
            rendered, step_branches, s.branch_choices.get(sid))
        sim_output = {"branch": chosen_branch} if chosen_branch else {}
        step_record["status"] = "simulated"
        step_record["simulated_from"] = "computed"
        if chosen_branch:
            step_record["note"] = f"branch: {chosen_branch}"
    elif stype == "workflow_reference":
        target = rendered.get("target")
        if not target:
            sim_output = {}
            step_record["status"] = "simulated"
            step_record["simulated_from"] = "default_empty"
            step_record["note"] = (
                "workflow_reference target unresolvable")
        elif rendered.get("apply_async") is True:
            sim_output = {}
            step_record["status"] = "simulated"
            step_record["simulated_from"] = "computed"
            step_record["note"] = (
                f"async ref to {target!r}; fire-and-forget")
        else:
            child_input = (rendered.get("arguments")
                           if isinstance(rendered.get("arguments"),
                                         dict) else {})
            child_result = step_through_playbook(
                yaml_text=s.yaml_text,
                playbook=target,
                input=child_input,
                execute_safe_ops=s.execute_safe_ops,
                max_steps=s.max_steps,
            )
            if (child_result.get("ok") is False
                    and not child_result.get("trace")):
                sim_output = {}
                step_record["simulated_from"] = "default_empty"
                step_record["note"] = (
                    f"workflow_reference {target!r}: "
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
        # Friendly YAML puts `options:` at the step level; _normalize_
        # friendly_steps mirrors them into arguments, but fall back to
        # the step dict here too for safety on un-normalized callers.
        options = rendered.get("options") or cur.get("options") or []
        picked = s.manual_choices.get(sid)
        if isinstance(options, list) and options:
            if picked is None or not any(
                isinstance(o, dict)
                and (o.get("display") or o.get("option")) == picked
                for o in options
            ):
                first = next((o for o in options if isinstance(o, dict)), {})
                picked = first.get("display") or first.get("option")
        sim_output = {"option": picked} if picked else {}
        # Carry sample answers (overlaid in build_session) into the step
        # output so the debug pane shows `input.<field>` alongside `option`
        # — that's the shape FSR exposes at runtime for manual_input.
        jkey_mi = (cur.get("name") or sid).replace(" ", "_")
        existing_sample = (s.vars_ctx.get("steps", {}).get(jkey_mi)
                           or s.vars_ctx.get("steps", {}).get(sid) or {})
        if (isinstance(existing_sample, dict)
                and isinstance(existing_sample.get("input"), dict)):
            sim_output["input"] = existing_sample["input"]
        step_record["status"] = "simulated"
        step_record["simulated_from"] = "computed"
        if picked:
            step_record["note"] = f"option: {picked}"
            # Route the stepper through the option's `next:` target by
            # treating the picked option label as the chosen branch.
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
        s.cur = None
        s.done = True
        return step_record
    else:
        sim_output = {}
        step_record["status"] = "simulated"
        step_record["simulated_from"] = "default_empty"
        step_record["note"] = (
            f"step type {stype!r} not executed; rendered args "
            "captured for downstream inspection")

    jkey = (cur.get("name") or sid).replace(" ", "_")
    if step_record["status"] == "executed":
        s.vars_ctx["steps"][jkey] = sim_output
        sample = sim_output[0] if (
            isinstance(sim_output, list) and sim_output
        ) else sim_output
        if isinstance(sample, dict):
            step_record["output_top_keys"] = sorted(sample.keys())
    else:
        s.vars_ctx["steps"][jkey] = (sim_output
                                     if sim_output is not None else {})
        if isinstance(sim_output, dict):
            step_record["output_top_keys"] = sorted(sim_output.keys())
    step_record["output"] = sim_output
    step_record["output_shape"] = _infer_output_shape(sim_output)

    nav_branch = (s.branch_choices.get(sid) or chosen_branch)
    nxt_id = _next_step(cur, nav_branch, s.by_id)
    if not nxt_id or nxt_id not in s.by_id:
        s.cur = None
        s.done = True
    else:
        s.cur = s.by_id[nxt_id]
    return step_record


# =====================================================================
# Session store
# =====================================================================

class SessionStore:
    """In-memory session store with TTL eviction. Process-local; not
    safe for multi-worker deployments — debug runner is a developer
    tool in a single-process MCP server."""

    def __init__(self, ttl_seconds: float = _SESSION_TTL_SECONDS) -> None:
        self._sessions: dict[str, DebugSession] = {}
        self._lock = RLock()
        self._ttl = ttl_seconds

    def create(self, **kwargs: Any) -> DebugSession:
        sid = secrets.token_urlsafe(12)
        kwargs.setdefault("session_id", sid)
        sess = DebugSession(**kwargs)
        with self._lock:
            self._evict_expired_locked()
            self._sessions[sess.session_id] = sess
        return sess

    def get(self, session_id: str) -> DebugSession | None:
        with self._lock:
            self._evict_expired_locked()
            sess = self._sessions.get(session_id)
            if sess is not None:
                sess.last_touched = time.time()
            return sess

    def drop(self, session_id: str) -> bool:
        with self._lock:
            return self._sessions.pop(session_id, None) is not None

    def _evict_expired_locked(self) -> None:
        cutoff = time.time() - self._ttl
        expired = [sid for sid, sess in self._sessions.items()
                   if sess.last_touched < cutoff]
        for sid in expired:
            self._sessions.pop(sid, None)

    def __len__(self) -> int:
        return len(self._sessions)


# Singleton used by the MCP tool surface.
_STORE = SessionStore()


def get_store() -> SessionStore:
    return _STORE


# =====================================================================
# Session bootstrap — parses YAML, picks the playbook, finds the start
# step. Mirrors the prelude of step_through_playbook.
# =====================================================================

def build_session(
    *,
    yaml_text: str,
    playbook: str | None = None,
    input: dict[str, Any] | None = None,
    branch_choices: dict[str, str] | None = None,
    manual_choices: dict[str, str] | None = None,
    breakpoints: list[str] | None = None,
    execute_safe_ops: bool = True,
    execute_unsafe_ops: bool = False,
    max_steps: int = 30,
) -> tuple[DebugSession | None, str | None]:
    """Parse the YAML and construct a `DebugSession`. Returns
    `(session, None)` on success or `(None, error_message)` on
    parse / shape failure. Caller owns persisting the session via
    `get_store().create(...)` (or `start_session` does both in one
    call)."""
    try:
        import yaml as _yaml  # noqa: PLC0415
        doc = _yaml.safe_load(yaml_text) or {}
    except Exception as exc:  # noqa: BLE001
        return None, f"yaml parse failed: {exc}"

    pbs = doc.get("playbooks") or []
    if not pbs:
        return None, "no playbooks in YAML"
    pb = next((p for p in pbs if p.get("name") == playbook), pbs[0])
    steps = pb.get("steps") or []
    for s in steps:
        if isinstance(s, dict) and "id" not in s and s.get("name"):
            s["id"] = s["name"]
    # Same friendly-YAML bridge step_through_playbook applies — share
    # the helper so both paths walk decisions / manual_input the same.
    from .tools_analysis import _normalize_friendly_steps  # noqa: PLC0415
    _normalize_friendly_steps(steps)
    by_id = {s["id"]: s for s in steps
             if isinstance(s, dict) and "id" in s}
    if not by_id:
        return None, "no steps with id or name in playbook"
    start = next((s for s in steps if isinstance(s, dict)
                  and (s.get("type") or "").startswith("start")), steps[0])

    # Overlay `# fsrpb:samples` sidecar + per-step `mock_result` into the
    # vars context so manual_input answers / fake connector outputs flow
    # into downstream Jinja from step 1, same as step_through_playbook.
    #
    # Samples are saved keyed by the slugified step name (e.g.
    # `get_ip_address` for "Get IP Address") — same convention
    # `tools_analysis.step_test` uses. We try both forms here so authors
    # who hand-key the block by raw name still hit, and we mirror the
    # payload under every alias (raw id, slug, jkey) so downstream
    # `vars.steps.<X>` Jinja resolves regardless of which form the
    # template author picked.
    from compiler.parser import _slugify  # noqa: PLC0415
    from compiler.samples import extract_samples_block, overlay_into_vars  # noqa: PLC0415
    vars_ctx: dict[str, Any] = {"input": {"params": dict(input or {})},
                                 "steps": {}}
    samples_map, _ = extract_samples_block(yaml_text)
    pb_samples = samples_map.get(pb.get("name") or "", {}) or {}
    expanded: dict[str, Any] = {}
    for st in steps:
        if not isinstance(st, dict):
            continue
        sid_iter = st.get("id")
        nm = st.get("name") if isinstance(st.get("name"), str) else None
        slug = _slugify(nm) if nm else None
        s_args = st.get("arguments") if isinstance(st.get("arguments"),
                                                    dict) else {}
        mock = (s_args.get("mock_result")
                if isinstance(s_args, dict) else None)
        sample = None
        for key in (sid_iter, slug, nm):
            if key and key in pb_samples:
                sample = pb_samples[key]
                break
        payload = mock if mock is not None else sample
        if payload is None:
            continue
        for alias in (sid_iter, slug, nm.replace(" ", "_") if nm else None):
            if alias:
                expanded[alias] = payload
    overlay_into_vars(expanded, vars_ctx)

    return DebugSession(
        session_id="",  # filled by SessionStore.create
        yaml_text=yaml_text,
        pb_name=pb.get("name") or "",
        steps=steps,
        by_id=by_id,
        cur=start,
        vars_ctx=vars_ctx,
        branch_choices=dict(branch_choices or {}),
        manual_choices=dict(manual_choices or {}),
        breakpoints=set(breakpoints or []),
        execute_safe_ops=execute_safe_ops,
        execute_unsafe_ops=execute_unsafe_ops,
        max_steps=max_steps,
    ), None
