"""SkillCall trace recorder — capture the typed action trace of a session.

The agent **already runs the connector ops** during triage, so their real
outputs sit in the tool loop's `run_op` results. This module is the thin
recorder (SKILL_BASED_PLAYBOOK_PLAN §2) that captures, per executed
action, what is already there:

    SkillCall = {skill_id, step_name, resolved_inputs, observed_output}

`observed_output` is the asset that makes everything downstream reliable:
it is both the **wiring source** (§3, value-match over captured outputs)
and the **render context** for verification (§4). No `output_schema`
declaration is needed up front — the real output *is* the schema for
this session.

Design: there is no session handle inside the global `run_op` MCP tool,
so the connector's per-session wrapper installs a process-local active
trace via `set_active_trace()`; `record_run_op()` is a no-op when no
trace is active (studio, tests, eval harness), keeping live triage on raw
`run_op` untouched. The connector persists `trace.to_json()` next to the
transcript and rehydrates with `SkillTrace.from_json()` for the
session→YAML compile.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# Step-name charset rule (mirrors tools_emit._NAME_RE): letters, digits,
# spaces, underscores. The recorder generates names that already satisfy
# it so a recorded step_name can be used as a YAML step name unedited.
_NAME_OK = re.compile(r"[^A-Za-z0-9 _]+")


def _titleize_op(op: str) -> str:
    """`isolate_host` -> `Isolate Host`. Sanitized to the step-name charset."""
    words = re.split(r"[_\-\s]+", op or "")
    pretty = " ".join(w.capitalize() for w in words if w) or "Step"
    return _NAME_OK.sub("", pretty).strip() or "Step"


@dataclass
class SkillCall:
    skill_id: str
    step_name: str                          # stable; becomes the YAML step name
    resolved_inputs: Dict[str, Any] = field(default_factory=dict)
    observed_output: Any = None             # the real (full) run_op result (the data payload)
    # How the captured `observed_output` nests under the FSR runtime step
    # record. run_op captures `resp.get("data", resp)`: when the raw op
    # response carried a `data` key, the runtime reference is
    # `vars.steps.<name>.data.<path>` (ref_prefix="data"); otherwise the
    # payload sits directly at `vars.steps.<name>.<path>` (ref_prefix="").
    # The wiring compiler (§3) uses this so generated paths match runtime,
    # and the verify loop (§4) keys its render context the same way.
    ref_prefix: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "step_name": self.step_name,
            "resolved_inputs": self.resolved_inputs,
            "observed_output": self.observed_output,
            "ref_prefix": self.ref_prefix,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SkillCall":
        return cls(
            skill_id=d["skill_id"],
            step_name=d["step_name"],
            resolved_inputs=d.get("resolved_inputs") or {},
            observed_output=d.get("observed_output"),
            ref_prefix=d.get("ref_prefix") or "",
        )


class SkillTrace:
    """Ordered record of the SkillCalls executed in one session.

    Order is dependency order (the agent ran the ops in the order it
    needed them), which §3 relies on for value-match wiring.
    """

    def __init__(
        self,
        calls: Optional[List[SkillCall]] = None,
        module: Optional[str] = None,
    ) -> None:
        self.calls: List[SkillCall] = list(calls or [])
        # Friendly module name of the record the triage session ran on
        # (e.g. "alerts", "incidents") — set by the connector when it opens
        # the per-turn trace scope from the triaged record. NOT derivable
        # from the recorded ops; it's the investigation's subject. The
        # trace-build path binds the playbook's start trigger to it so the
        # playbook runs from that module's record listing (a manual
        # cybersponse.action trigger) instead of a designer-only Referenced
        # trigger. None → bare `start` (legacy behavior).
        self.module: Optional[str] = module
        # Tracks how many times each base step name has been used so
        # repeated ops get stable, unique names (`Get Record`, `Get Record 2`).
        self._name_counts: Dict[str, int] = {}
        for c in self.calls:
            base = c.step_name.rsplit(" ", 1)[0] if c.step_name[-1:].isdigit() else c.step_name
            self._name_counts[base] = self._name_counts.get(base, 0) + 1

    def _unique_name(self, base: str) -> str:
        n = self._name_counts.get(base, 0) + 1
        self._name_counts[base] = n
        return base if n == 1 else f"{base} {n}"

    def record(self, call: SkillCall) -> SkillCall:
        self.calls.append(call)
        return call

    def record_run_op(
        self,
        connector: str,
        op: str,
        params: Optional[Dict[str, Any]],
        observed_output: Any,
        step_name: Optional[str] = None,
        ref_prefix: str = "",
    ) -> SkillCall:
        """Record one `run_op` execution as a `run_connector_action`
        SkillCall. `params` are the resolved inputs the agent passed;
        `observed_output` MUST be the FULL op output (not the summarized
        payload returned to the LLM) so value-match wiring has the real
        shape to match against. `ref_prefix` is "data" when the raw op
        response wrapped its payload in a `data` key (so runtime refs are
        `vars.steps.<name>.data.*`), else "" (refs sit directly)."""
        name = step_name or self._unique_name(_titleize_op(op))
        resolved = dict(params or {})
        resolved["connector"] = connector
        resolved["operation"] = op
        return self.record(SkillCall(
            skill_id="run_connector_action",
            step_name=name,
            resolved_inputs=resolved,
            observed_output=observed_output,
            ref_prefix=ref_prefix,
        ))

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"calls": [c.to_dict() for c in self.calls]}
        # Emit `module` only when set so a legacy reader (and golden
        # fixtures) see the same shape they always did.
        if self.module:
            d["module"] = self.module
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), default=str)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SkillTrace":
        return cls(
            [SkillCall.from_dict(c) for c in (d.get("calls") or [])],
            module=d.get("module"),
        )

    @classmethod
    def from_json(cls, text: str) -> "SkillTrace":
        if not text:
            return cls()
        return cls.from_dict(json.loads(text))

    def __len__(self) -> int:
        return len(self.calls)


# ---------------------------------------------------------------------------
# Process-local active trace — installed by the connector's session wrapper
# ---------------------------------------------------------------------------

_active: Optional[SkillTrace] = None


def set_active_trace(trace: Optional[SkillTrace]) -> None:
    """Install (or clear, with None) the trace that `record_run_op` feeds."""
    global _active
    _active = trace


def get_active_trace() -> Optional[SkillTrace]:
    return _active


def set_active_trace_module(module: Optional[str]) -> None:
    """Stamp the triaged module on the active trace (no-op if none active).

    Lets the connector record the investigation's subject module once it
    knows the triaged record's type, without rebuilding the trace. The
    trace-build path reads it to bind the playbook's start trigger.
    `module` is normalized to the friendly short name (an IRI like
    `/api/3/alerts/<uuid>` collapses to `alerts`)."""
    if _active is None or not module:
        return
    m = module
    if "/api/3/" in m:
        m = m.split("/api/3/", 1)[1]
    m = m.split("/", 1)[0].split("?", 1)[0].strip()
    if m:
        _active.module = m


def clear_active_trace() -> None:
    global _active
    _active = None


def record_run_op(
    connector: str,
    op: str,
    params: Optional[Dict[str, Any]],
    observed_output: Any,
    step_name: Optional[str] = None,
    ref_prefix: str = "",
) -> Optional[SkillCall]:
    """Module-level convenience: record into the active trace if one is
    installed, else no-op. This is what `run_op` calls — so studio/tests
    (no active trace) stay on raw run_op, untouched."""
    if _active is None:
        return None
    return _active.record_run_op(
        connector, op, params, observed_output, step_name, ref_prefix
    )
