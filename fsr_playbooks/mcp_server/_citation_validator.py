"""Citation validation for structured verdicts.

Verdicts cite evidence via tool_use ids. This module enforces that every cited
id is a real tool call from THIS turn with a successful result (to prevent
citations of errors or emit_* calls that are not evidence).

Per-turn evidence tracking: providers create a TurnEvidence object in stream(),
set it via contextvars (async-safe), and include it in suspended-session state
for resume. Deliberately minimal: only tracks id -> (name, ok), no full result
bodies (those are in history already).
"""
from __future__ import annotations

import contextvars
from typing import Any

# Async-safe context variable for the current turn's evidence registry.
# contextvars work across async boundaries, unlike threading.local.
_turn_evidence: contextvars.ContextVar[TurnEvidence | None] = contextvars.ContextVar(
    "turn_evidence", default=None
)


class TurnEvidence:
    """Per-turn evidence registry for citation validation.

    Tracks tool_use_ids and their success/failure status. Set via contextvars
    so citations can validate evidence within emit_verdict. Included in
    suspended-session state so citations survive approval-gate resume.
    """

    def __init__(self) -> None:
        self._registry: dict[str, dict[str, Any]] = {}
        # Verdict cards delivered this turn, in order. The autonomy policy
        # (llm/autonomy.py) tests the verdict an action rests on, so it needs
        # the delivered card, not the model's prose about it.
        self._verdicts: list[dict[str, Any]] = []

    def register(self, tool_use_id: str, tool_name: str, success: bool,
                 args: dict[str, Any] | None = None) -> None:
        """Record that a tool call succeeded or failed. ``args`` is kept so a
        policy can tell WHAT a cited call looked up (its target), not just
        which tool ran."""
        entry: dict[str, Any] = {"name": tool_name, "ok": success}
        if isinstance(args, dict):
            entry["args"] = _bounded_args(args)
        self._registry[tool_use_id] = entry

    def record_verdict(self, card: dict[str, Any]) -> None:
        """Record a verdict card that was delivered (validated + emitted)."""
        if isinstance(card, dict):
            self._verdicts.append(dict(card))

    def verdicts(self) -> list[dict[str, Any]]:
        return [dict(v) for v in self._verdicts]

    def valid_ids(self) -> dict[str, dict[str, Any]]:
        """Return the registry (id -> {name, ok[, args]})."""
        return dict(self._registry)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for suspended-session storage."""
        return {"_registry": dict(self._registry),
                "_verdicts": list(self._verdicts)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TurnEvidence:
        """Deserialize from suspended-session storage."""
        obj = cls()
        obj._registry = data.get("_registry", {})
        obj._verdicts = list(data.get("_verdicts") or [])
        return obj


def _bounded_args(args: dict[str, Any], limit: int = 2000) -> dict[str, Any]:
    """The call's args, or a stub when they are too big to keep per call (a
    whole playbook YAML is not a lookup target)."""
    import json
    try:
        blob = json.dumps(args, default=str)
    except Exception:  # noqa: BLE001
        return {}
    return args if len(blob) <= limit else {"_truncated": blob[:limit]}


def set_turn_evidence(evidence: TurnEvidence | None) -> None:
    """Set the current turn's evidence context (called by providers at stream start)."""
    _turn_evidence.set(evidence)


def get_turn_evidence() -> TurnEvidence | None:
    """Get the current turn's evidence context (called by emit_verdict for citations)."""
    return _turn_evidence.get()


def register_tool_result(tool_use_id: str, tool_name: str, success: bool,
                         args: dict[str, Any] | None = None) -> None:
    """Record that a tool call succeeded or failed.

    Called by the provider as tool results arrive. Routes to the contextvar
    based TurnEvidence object.
    """
    evidence = get_turn_evidence()
    if evidence is not None:
        evidence.register(tool_use_id, tool_name, success, args)


def record_delivered_verdict(card: dict[str, Any]) -> None:
    """Note a verdict card delivered this turn (called by emit_verdict)."""
    evidence = get_turn_evidence()
    if evidence is not None:
        evidence.record_verdict(card)


def clear_tool_registry() -> None:
    """Clear the tool registry at turn start (creates new TurnEvidence).

    Providers should call this at stream() start, then set_turn_evidence(evidence).
    Kept for backward compat but new code should use set_turn_evidence() directly.
    """
    set_turn_evidence(TurnEvidence())


# Emit tools whose results are NOT valid evidence (they're actions, not findings).
_EMIT_TOOLS = frozenset({
    "emit_choice_card", "emit_action_card", "emit_manual_input",
    "emit_capability_gap_card", "emit_playbook_offer",
    "emit_enhancement_offer", "emit_card",
    # Legacy names (consolidated into emit_card)
    "emit_decision_step",
})


def validate_evidence_ids(evidence_ids: list[str]) -> dict[str, Any] | None:
    """Validate that all evidence ids are valid tool_use ids from this turn.

    Returns an error dict (ok=False) if validation fails, None if all ids are
    valid. Checks that:
      1. Each id is a known tool_use_id
      2. The tool call succeeded (ok=True)
      3. The tool is NOT an emit_* (which are actions, not evidence)
    """
    from ._shared import _err

    evidence = get_turn_evidence()
    if evidence is None:
        return _err("no_turn_evidence", "No turn evidence context found")
    registry = evidence.valid_ids()

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
        # Live (session health 2026-09-30): models cite the TOOL, not the call
        # -- `functions.get_record`, `multi_tool_use.parallel#1` -- and needed a
        # retry to find the ids. Name the calls that tool made.
        for uid in unknown_ids:
            tool = str(uid or "").split("#")[0].rsplit(".", 1)[-1]
            calls = [eid for eid, info in registry.items()
                     if info.get("name") == tool and info.get("ok") is True]
            if calls:
                parts.append(f"'{uid}' names the tool {tool}, not a call: cite "
                             f"one of its call ids {calls[:5]}.")
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
        # Each id with the tool it called, so a claim can be matched to the
        # call that supports it.
        valid_ids = [
            f"{eid} ({info.get('name') or '?'})" for eid, info in registry.items()
            if info.get("ok") is True and (info.get("name") or "") not in _EMIT_TOOLS
        ]
        if valid_ids:
            suggestions.append(
                f"Valid tool_use_ids from this turn: {', '.join(valid_ids[:10])} "
                f"{'...' if len(valid_ids) > 10 else ''}")

    return _err("invalid_evidence_ids", message, suggestions=suggestions)
