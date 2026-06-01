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
    observed_output: Any = None             # the real (full) run_op result

    def to_dict(self) -> Dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "step_name": self.step_name,
            "resolved_inputs": self.resolved_inputs,
            "observed_output": self.observed_output,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SkillCall":
        return cls(
            skill_id=d["skill_id"],
            step_name=d["step_name"],
            resolved_inputs=d.get("resolved_inputs") or {},
            observed_output=d.get("observed_output"),
        )


class SkillTrace:
    """Ordered record of the SkillCalls executed in one session.

    Order is dependency order (the agent ran the ops in the order it
    needed them), which §3 relies on for value-match wiring.
    """

    def __init__(self, calls: Optional[List[SkillCall]] = None) -> None:
        self.calls: List[SkillCall] = list(calls or [])
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
    ) -> SkillCall:
        """Record one `run_op` execution as a `run_connector_action`
        SkillCall. `params` are the resolved inputs the agent passed;
        `observed_output` MUST be the FULL op output (not the summarized
        payload returned to the LLM) so value-match wiring has the real
        shape to match against."""
        name = step_name or self._unique_name(_titleize_op(op))
        resolved = dict(params or {})
        resolved["connector"] = connector
        resolved["operation"] = op
        return self.record(SkillCall(
            skill_id="run_connector_action",
            step_name=name,
            resolved_inputs=resolved,
            observed_output=observed_output,
        ))

    def to_dict(self) -> Dict[str, Any]:
        return {"calls": [c.to_dict() for c in self.calls]}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), default=str)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SkillTrace":
        return cls([SkillCall.from_dict(c) for c in (d.get("calls") or [])])

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


def clear_active_trace() -> None:
    global _active
    _active = None


def record_run_op(
    connector: str,
    op: str,
    params: Optional[Dict[str, Any]],
    observed_output: Any,
    step_name: Optional[str] = None,
) -> Optional[SkillCall]:
    """Module-level convenience: record into the active trace if one is
    installed, else no-op. This is what `run_op` calls — so studio/tests
    (no active trace) stay on raw run_op, untouched."""
    if _active is None:
        return None
    return _active.record_run_op(connector, op, params, observed_output, step_name)
