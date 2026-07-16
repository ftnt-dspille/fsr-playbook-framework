"""P4 — the tool-output envelope contract.

Every tool dispatched through `llm.tools.dispatch` returns its result straight
back to the agent loop as a `tool_result` block. Historically the *shape* of
that result was a de-facto convention — a dict, usually carrying some of
``{ok, code, message, error, record, ...}`` — enforced nowhere. A tool that
returned a bare string or ``None`` would slip through and confuse the model (or
the widget) downstream. This module turns that convention into a checked
contract.

**The contract.** A tool result is one of:
  1. a **dict** — the standard envelope (status/error/payload keys below), OR
  2. a **list of dicts** — a collection result (the ``find_*`` / ``search_*``
     tools return a ranked list of hit dicts).

Anything else — a naked scalar (``str``/``int``/``bool``), ``None``, or a list
whose members aren't dicts — is a contract violation: an untyped return the
downstream can't reason about.

**Roll-out posture (fail-open → strict).** `dispatch` validates every tool
output through :func:`validate_tool_output`. By default it is *fail-open*: a
violation is logged (so we can find and type the offenders) and the original
result is returned unchanged — a validation bug must never break a live turn.
Setting ``FSRPB_STRICT_TOOL_OUTPUT`` to a truthy value flips it *strict*: a
violation is replaced with a well-formed error envelope so the contract is hard.

`ToolResult` documents the recognized envelope keys for authors; runtime
validation is structural (dict / list-of-dict) so the heterogeneous real
payloads (triage ``{record: {...}}``, the ZTPF render output, card emitters'
``{ok, card}``) all validate without each being pinned to a rigid schema here.
"""
from __future__ import annotations

import logging
import os
from typing import Any, TypedDict

logger = logging.getLogger(__name__)


class ToolResult(TypedDict, total=False):
    """The recognized keys of a dict-shaped tool envelope (all optional).

    Documentation, not a runtime schema — a tool may carry domain payload keys
    beyond these (e.g. ``record``, ``card``, ``schema``, ``runs``). The status
    trio ``ok``/``code``/``message`` and the ``error`` key are the cross-cutting
    convention every consumer keys off.
    """

    ok: bool
    code: str
    message: str
    error: str
    # Common domain payloads (non-exhaustive; here so authors see the pattern).
    record: dict[str, Any]
    card: dict[str, Any]
    # Dispatch-level envelopes (dispatch emits these, not the tool fn).
    pending_approval: bool


def is_valid_tool_output(result: Any) -> bool:
    """True when ``result`` conforms to the envelope contract (dict, or a list
    whose every member is a dict)."""
    if isinstance(result, dict):
        return True
    if isinstance(result, list):
        return all(isinstance(item, dict) for item in result)
    return False


def describe_violation(name: str, result: Any) -> str:
    """A one-line reason a result violates the contract (for logs / strict
    error envelopes). Assumes the caller already knows it's invalid."""
    if isinstance(result, list):
        return (f"tool '{name}' returned a list with non-dict member(s) "
                f"(types: {sorted({type(i).__name__ for i in result})}) — "
                f"a collection result must be a list of dicts")
    return (f"tool '{name}' returned a bare {type(result).__name__} — "
            f"tool outputs must be a dict envelope or a list of dict envelopes")


def _strict_mode() -> bool:
    """Whether the tool-output contract is enforced strictly (violations become
    error envelopes) vs fail-open (violations logged, result passed through).
    Off by default — see the module docstring's roll-out posture."""
    raw = os.environ.get("FSRPB_STRICT_TOOL_OUTPUT")
    if raw is None:
        return False
    return raw.strip().lower() in ("1", "true", "yes", "on")


def validate_tool_output(name: str, result: Any) -> Any:
    """Validate a tool's output against the envelope contract and return the
    result to hand back to the agent loop.

    Conforming output is returned unchanged. A violation is always logged; in
    fail-open mode (default) the original result is still returned, in strict
    mode it is replaced with a ``{ok: False, code: "tool_output_contract"}``
    error envelope. This is the single chokepoint `dispatch` routes tool-fn
    results through."""
    if is_valid_tool_output(result):
        return result
    reason = describe_violation(name, result)
    if _strict_mode():
        logger.error("tool-output contract (strict): %s", reason)
        return {"ok": False, "code": "tool_output_contract", "error": reason}
    logger.warning("tool-output contract (fail-open): %s", reason)
    return result
