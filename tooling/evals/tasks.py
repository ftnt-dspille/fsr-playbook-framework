"""Declarative task fixtures for the eval harness.

Each task is a JSON file under `tooling/evals/tasks/` shaped:

    {
      "name": "manual_alert_create",
      "prompt": "<natural language brief for the LLM>",
      "gold_yaml_path": "examples/demo_alert_action.yaml",  // optional
      "notes": "..."
    }

The `gold_yaml_path` is resolved relative to the repo root. When set,
the harness compiles the gold YAML once for byte-equality comparison
in scoring.gold. When absent, the gold gate is skipped.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
TASKS_DIR = Path(__file__).resolve().parent / "tasks"


@dataclass(frozen=True)
class Task:
    name: str
    prompt: str
    gold_yaml_path: Optional[str] = None  # repo-relative
    notes: str = ""
    # Phase 3 HITL: per-task eval policy. None = use $EVAL_APPROVAL_POLICY
    # (or "suspend" if unset, but suspend in an eval is treated as a
    # tier-3+ call returning `pending_approval`).
    approval_policy: Optional[str] = None
    # Shape for the `appropriate_approval_requests` gate. None = default
    # ("exactly_zero" tier-3+ calls).
    expected_approvals: Optional[dict[str, Any]] = None
    # Scoring mode. `None` = standard authoring task. `"refuse"` = the
    # agent is expected to decline (e.g. `unknown_connector`); authoring
    # gates become informational and adherence inverts. `"investigation"`
    # = triage/hunt task scored on pivot recall (see `required_facts`).
    # `"tool_selection"` = scored on ONE thing: did the turn reach the
    # terminal tool this ask requires (see `terminal_tool`).
    mode: Optional[str] = None
    # Investigation-mode scoring inputs. Each entry is a tool-call matcher
    # (see scoring._fact_matches). `required_facts` = pivots the agent
    # SHOULD perform (recall numerator); `forbidden_facts` = pivots it must
    # NOT perform (e.g. external TI on an internal RFC1918 IP -- any hit
    # hard-fails the gate).
    required_facts: list[dict[str, Any]] = field(default_factory=list)
    forbidden_facts: list[dict[str, Any]] = field(default_factory=list)
    # Phase 1.4 strengthening: per-fixture quality knobs that recall can't
    # see (scoring._score_investigation_quality). Keys: `tool_budget_max`,
    # `max_param_retries`, `require_deliverable` (bool or a list of accepted
    # emit_* tool names). Absent knobs fall back to the module defaults.
    investigation_quality: dict[str, Any] = field(default_factory=dict)
    # --- Phase 1.2 tool-selection eval -------------------------------------
    # `terminal_tool` is the tool the turn MUST reach for the ask to have been
    # answered (any one of them, when several are acceptable). Scored by
    # scoring._score_tool_selection; `forbidden_facts` doubles as the decoy
    # list (e.g. `list_playbook_runs` standing in for `run_playbook`).
    terminal_tool: list[str] = field(default_factory=list)
    # Which system prompt the turn runs under: "build" / "triage" (the shipped
    # intent prompts) or "neutral" (tools + the ask, no persona mandate).
    # None = the harness default. This is what makes the Phase 1.4
    # build-vs-neutral experiment a pair of fixtures instead of a one-off
    # script: same prompt text, same tools, only the persona differs.
    prompt_variant: Optional[str] = None
    # Tool slice to advertise: "build" / "triage" (intents.tools_for_intent)
    # or None for the full registry the agentic provider defaults to.
    tool_slice: Optional[str] = None

    def gold_yaml_text(self) -> Optional[str]:
        if not self.gold_yaml_path:
            return None
        p = REPO_ROOT / self.gold_yaml_path
        if not p.exists():
            return None
        return p.read_text(encoding="utf-8")


def _as_list(value: Any) -> list[str]:
    """Accept a bare string or a list in the fixture JSON."""
    if not value:
        return []
    return [value] if isinstance(value, str) else [str(v) for v in value]


def load_tasks(filter_names: list[str] | None = None) -> list[Task]:
    """Load every `*.json` task fixture, optionally filtered by name."""
    tasks: list[Task] = []
    for p in sorted(TASKS_DIR.glob("*.json")):
        data = json.loads(p.read_text(encoding="utf-8"))
        tasks.append(Task(
            name=data["name"],
            prompt=data["prompt"],
            gold_yaml_path=data.get("gold_yaml_path"),
            notes=data.get("notes", ""),
            approval_policy=data.get("approval_policy"),
            expected_approvals=data.get("expected_approvals"),
            mode=data.get("mode"),
            required_facts=data.get("required_facts") or [],
            forbidden_facts=data.get("forbidden_facts") or [],
            investigation_quality=data.get("investigation_quality") or {},
            terminal_tool=_as_list(data.get("terminal_tool")),
            prompt_variant=data.get("prompt_variant"),
            tool_slice=data.get("tool_slice"),
        ))
    if filter_names:
        wanted = set(filter_names)
        tasks = [t for t in tasks if t.name in wanted]
    return tasks
