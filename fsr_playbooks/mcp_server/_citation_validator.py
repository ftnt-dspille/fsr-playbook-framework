"""Citation validation for structured verdicts.

Verdicts cite evidence via tool_use ids. This module enforces that every cited
id is a real tool call from THIS session with a successful result (to prevent
citations of errors or emit_* calls that are not evidence).

Per-turn tool tracking: the provider populates a thread-local registry as tool
results arrive. dispatch() consults it during emit_verdict citation validation.
Deliberately minimal: only tracks id → success, no full result bodies (those are
in the history already).
"""
from __future__ import annotations

import threading
from typing import Any

_session_tool_ids: threading.local = threading.local()


def _get_tool_registry() -> dict[str, dict[str, Any]]:
    """Get or create this turn's tool registry (id → {name, ok})."""
    if not hasattr(_session_tool_ids, "registry"):
        _session_tool_ids.registry = {}
    return _session_tool_ids.registry


def register_tool_result(tool_use_id: str, tool_name: str, success: bool) -> None:
    """Record that a tool call succeeded or failed.

    Called by the provider as tool results arrive. The registry is keyed by
    tool_use_id for fast lookup during emit_verdict citation checks.
    """
    registry = _get_tool_registry()
    registry[tool_use_id] = {"name": tool_name, "ok": success}


def clear_tool_registry() -> None:
    """Clear the tool registry at turn start."""
    _session_tool_ids.registry = {}


# Emit tools whose results are NOT valid evidence (they're actions, not findings).
_EMIT_TOOLS = frozenset({
    "emit_choice_card", "emit_action_card", "emit_manual_input",
    "emit_capability_gap_card", "emit_playbook_offer", "emit_patch_proposal",
    "emit_enhancement_offer", "emit_card",
    # Legacy names (consolidated into emit_card)
    "emit_decision_step",
})


def validate_evidence_ids(evidence_ids: list[str]) -> dict[str, Any] | None:
    """Validate that all evidence ids are valid tool_use ids from this session.

    Returns an error dict (ok=False) if validation fails, None if all ids are
    valid. Checks that:
      1. Each id is a known tool_use_id
      2. The tool call succeeded (ok=True)
      3. The tool is NOT an emit_* (which are actions, not evidence)
    """
    from ._shared import _err

    registry = _get_tool_registry()

    # Collect bad ids for a single refusal with suggestions.
    unknown_ids: list[str] = []
    failed_ids: list[str] = []
    emit_ids: list[str] = []

    for eid in evidence_ids:
        eid_str = str(eid or "").strip()
        if not eid_str:
            unknown_ids.append(eid)
            continue

        info = registry.get(eid_str)
        if info is None:
            unknown_ids.append(eid_str)
            continue

        if info.get("ok") is not True:
            failed_ids.append(eid_str)
            continue

        tool_name = info.get("name") or ""
        if tool_name in _EMIT_TOOLS:
            emit_ids.append(eid_str)

    # Assemble error message if any bad ids found.
    parts: list[str] = []
    if unknown_ids:
        parts.append(
            f"Unknown tool_use_ids: {unknown_ids}. These are not valid ids from "
            f"this turn.")
    if failed_ids:
        parts.append(
            f"Failed tool calls: {failed_ids}. Evidence must come from successful "
            f"tool results.")
    if emit_ids:
        parts.append(
            f"Emit tools are actions, not evidence: {emit_ids}. Use tool_use_ids "
            f"from investigation/enrichment tools (get_record, search_*, "
            f"siem_*, faz_*, run_op, mcp_* read tools).")

    if not parts:
        return None

    message = " ".join(parts)
    suggestions = []
    if unknown_ids or failed_ids:
        # List valid tool_use_ids that succeeded.
        valid_ids = [
            eid for eid, info in registry.items()
            if info.get("ok") is True
        ]
        if valid_ids:
            suggestions.append(
                f"Valid tool_use_ids from this turn: {', '.join(valid_ids[:10])} "
                f"{'...' if len(valid_ids) > 10 else ''}")

    return _err("invalid_evidence_ids", message, suggestions=suggestions)
