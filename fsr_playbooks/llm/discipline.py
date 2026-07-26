"""Post-turn discipline check — detect skipped authoring tools.

Phase 7.3 of RENDER_PATH_VALIDATOR_PLAN.md. The system prompt tells the
agent to call ``get_step_type`` before drafting non-trivial step types,
and ``find_connector`` / ``find_operation`` before drafting connector
steps. But nothing enforces that — the agent can guess at args and emit
YAML without ever looking up the schema.

This module analyzes a completed turn's transcript (the list of
``Event`` objects from ``run_agent_turn``) and flags two patterns:

1. **Skipped step-type lookup** — the agent emitted a YAML block
   containing a step type that requires a schema lookup
   (``manual_input``, ``find_record``, ``update_record``, ``decision``,
   ``workflow_reference``) but never called ``get_step_type`` for that
   type during the turn.

2. **Skipped connector lookup** — the agent emitted a YAML block
   containing a ``connector`` step but never called ``find_connector``
   or ``find_operation`` during the turn.

3. **Guessing language** — the agent's text contains hedging phrases
   like "I think the args are", "probably", "I assume", suggesting it
   is inventing parameter shapes rather than having looked them up.

Returns a list of warnings that the caller can surface to the user,
inject into the next turn's context, or log for discipline tracking.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .provider import Event, TextEvent, ToolUseEvent


# Step types that the system prompt's "Required workflow" §1 says
# require a ``get_step_type`` call before drafting. Connector is
# handled separately (§2: find_connector → find_operation).
_STEP_TYPES_REQUIRING_LOOKUP = frozenset({
    "manual_input", "find_record", "update_record",
    "decision", "workflow_reference",
})

# Tools that satisfy the step-type lookup requirement.
_STEP_TYPE_TOOLS = frozenset({"get_step_type", "find_step_examples"})

# Tools that satisfy the connector lookup requirement.
_CONNECTOR_TOOLS = frozenset({
    "find_connector", "find_operation", "get_op_schema",
    "precheck_connector_installed",
})

# Hedging phrases that suggest the agent is guessing.
_GUESSING_RE = re.compile(
    r"\b(i think|probably|i assume|i guess|likely the|might be|"
    r"should be|i believe|perhaps|maybe the args)\b",
    re.IGNORECASE,
)

# Extract ``type: <step_type>`` from YAML blocks.
_YAML_TYPE_RE = re.compile(r"^\s*-\s*type:\s*(\w+)", re.MULTILINE)


@dataclass
class DisciplineWarning:
    """One skipped-tool or guessing-pattern finding."""
    kind: str           # "skipped_step_type" | "skipped_connector" | "guessing"
    message: str
    step_types: list[str] = field(default_factory=list)
    suggestion: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "message": self.message,
            "step_types": self.step_types,
            "suggestion": self.suggestion,
        }


def _extract_yaml_from_text(text: str) -> str:
    """Pull the last fenced ```yaml block from assistant text."""
    blocks = re.findall(r"```yaml\n(.*?)```", text, re.DOTALL)
    return blocks[-1] if blocks else ""


def detect_skipped_authoring_tools(
    transcript: list[Event],
) -> list[DisciplineWarning]:
    """Analyze a completed turn's transcript for skipped authoring tools.

    Args:
      transcript: the ``TurnResult.transcript`` list from
        ``run_agent_turn`` — a sequence of ``Event`` objects.

    Returns:
      A list of ``DisciplineWarning`` objects, possibly empty. The
      caller decides how to surface them (SSE frame, next-turn
      injection, log-only).
    """
    # Collect tool names called during the turn.
    tools_called: set[str] = set()
    for ev in transcript:
        if isinstance(ev, ToolUseEvent) and not ev.synthetic:
            tools_called.add(ev.name)

    # Collect all assistant text (for YAML extraction + guessing
    # language detection).
    assistant_text = "".join(
        ev.text for ev in transcript if isinstance(ev, TextEvent)
    )

    warnings: list[DisciplineWarning] = []

    # 1. Skipped step-type lookup.
    yaml_block = _extract_yaml_from_text(assistant_text)
    if yaml_block:
        emitted_types = set(_YAML_TYPE_RE.findall(yaml_block))
        looked_up = tools_called & _STEP_TYPE_TOOLS
        # If get_step_type was called, check which types were looked up
        # by inspecting the tool call arguments.
        looked_up_types: set[str] = set()
        for ev in transcript:
            if (isinstance(ev, ToolUseEvent) and not ev.synthetic
                    and ev.name == "get_step_type"):
                arg = ev.arguments.get("step_type") or ev.arguments.get("name")
                if isinstance(arg, str):
                    looked_up_types.add(arg)
        # Also count find_step_examples as satisfying the requirement
        # for any type it was called with.
        for ev in transcript:
            if (isinstance(ev, ToolUseEvent) and not ev.synthetic
                    and ev.name == "find_step_examples"):
                arg = ev.arguments.get("step_type")
                if isinstance(arg, str):
                    looked_up_types.add(arg)

        skipped_types = (
            emitted_types & _STEP_TYPES_REQUIRING_LOOKUP
        ) - looked_up_types
        if skipped_types and not looked_up:
            # No get_step_type / find_step_examples calls at all.
            warnings.append(DisciplineWarning(
                kind="skipped_step_type",
                message=(
                    f"YAML contains step types {sorted(skipped_types)} "
                    f"that require a schema lookup, but "
                    f"get_step_type / find_step_examples was never "
                    f"called this turn"),
                step_types=sorted(skipped_types),
                suggestion=(
                    "call get_step_type for each type before drafting "
                    "to learn the canonical argument shape"),
            ))
        elif skipped_types:
            warnings.append(DisciplineWarning(
                kind="skipped_step_type",
                message=(
                    f"YAML contains step types {sorted(skipped_types)} "
                    f"but get_step_type was only called for "
                    f"{sorted(looked_up_types)}"),
                step_types=sorted(skipped_types),
                suggestion=(
                    f"call get_step_type for: "
                    f"{', '.join(sorted(skipped_types))}"),
            ))

        # 2. Skipped connector lookup.
        if "connector" in emitted_types:
            connector_called = bool(tools_called & _CONNECTOR_TOOLS)
            if not connector_called:
                warnings.append(DisciplineWarning(
                    kind="skipped_connector",
                    message=(
                        "YAML contains a connector step but "
                        "find_connector / find_operation was never "
                        "called this turn"),
                    step_types=["connector"],
                    suggestion=(
                        "call find_connector → find_operation before "
                        "drafting the connector step to learn the "
                        "param schema"),
                ))

    # 3. Guessing language.
    if _GUESSING_RE.search(assistant_text):
        # Only flag if the agent also emitted YAML (guessing about
        # playbook args is the concern, not hedging in prose).
        if yaml_block:
            warnings.append(DisciplineWarning(
                kind="guessing",
                message=(
                    "assistant text contains hedging language "
                    "(\"I think\", \"probably\", \"I assume\") "
                    "alongside a YAML block — the agent may be "
                    "guessing at parameter shapes instead of looking "
                    "them up"),
                suggestion=(
                    "call get_step_type / find_operation to verify "
                    "parameter shapes rather than guessing"),
            ))

    return warnings


__all__ = [
    "DisciplineWarning",
    "detect_skipped_authoring_tools",
]
