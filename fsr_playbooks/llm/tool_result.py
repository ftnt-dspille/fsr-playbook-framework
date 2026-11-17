"""P4 -- the tool-output envelope contract.

Every tool dispatched through `llm.tools.dispatch` returns its result straight
back to the agent loop as a `tool_result` block. Historically the *shape* of
that result was a de-facto convention -- a dict, usually carrying some of
``{ok, code, message, error, record, ...}`` -- enforced nowhere. A tool that
returned a bare string or ``None`` would slip through and confuse the model (or
the widget) downstream. This module turns that convention into a checked
contract.

**The contract.** A tool result is one of:
  1. a **dict** -- the standard envelope (status/error/payload keys below), OR
  2. a **list of dicts** -- a collection result (the ``find_*`` / ``search_*``
     tools return a ranked list of hit dicts).

Anything else -- a naked scalar (``str``/``int``/``bool``), ``None``, or a list
whose members aren't dicts -- is a contract violation: an untyped return the
downstream can't reason about.

**Roll-out posture (fail-open → strict).** `dispatch` validates every tool
output through :func:`validate_tool_output`. By default it is *fail-open*: a
violation is logged (so we can find and type the offenders) and the original
result is returned unchanged -- a validation bug must never break a live turn.
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
from typing import Any, Literal, TypedDict

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

logger = logging.getLogger(__name__)


class ToolResult(TypedDict, total=False):
    """The recognized keys of a dict-shaped tool envelope (all optional).

    Documentation, not a runtime schema -- a tool may carry domain payload keys
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


class ToolErr(BaseModel):
    """A failed tool envelope: the vocabulary the agent retries against.

    `code` is for the agent's control flow (and for our own grep-the-sessions
    analysis, which buckets by it); `message` is the human/model-readable
    reason. Both required -- an error envelope missing one is the defect this
    model exists to prevent, since the model then has nothing stable to branch
    on and falls back to re-reading prose.
    """
    model_config = ConfigDict(extra="allow")

    ok: Literal[False] = False
    code: str
    message: str


def tool_err(code: str, message: str, **extra: Any) -> dict[str, Any]:
    """Build a tool error envelope THROUGH `ToolErr`.

    The win is not the type check, it is that a hand-written literal can
    silently omit a key and nothing notices. Extra keys are the tool's own
    context (`op`, `query`, `module`, `suggestions`, ...) and pass through
    untouched.
    """
    return ToolErr(code=code, message=message, **extra).model_dump()


class PartialResult(BaseModel):
    """A gap-condition envelope: what was delivered, what is unknown, what next.

    Used when a tool hits a gap it cannot close itself (a missing connector or
    FSR configuration, an empty result, an unreachable source, truncated data).
    The model gets a result it can reason from instead of a refusal:

      delivered  what the call did obtain (may be empty, but it is always said)
      unknowns   what could not be established, one plain sentence each (>= 1)
      next       what to do about it, one concrete step each (>= 1)

    ``ok`` stays False and ``code`` stays the stable control-flow key, so every
    consumer that keys off ``ok`` / ``code`` / ``message`` keeps working;
    ``partial: true`` marks the shape. ``suggestions`` mirrors ``next`` for the
    older consumers that read it.
    """
    model_config = ConfigDict(extra="allow")

    ok: Literal[False] = False
    partial: Literal[True] = True
    code: str
    message: str
    delivered: dict[str, Any]
    unknowns: list[str] = Field(min_length=1)
    next: list[str] = Field(min_length=1)

    @field_validator("unknowns", "next")
    @classmethod
    def _no_blank(cls, v: list[str]) -> list[str]:
        if any(not isinstance(x, str) or not x.strip() for x in v):
            raise ValueError("entries must be non-empty strings")
        return v


def partial_result(code: str, message: str, *, unknowns: list[str],
                   next: list[str],  # noqa: A002 - the contract's key name
                   delivered: dict[str, Any] | None = None,
                   **extra: Any) -> dict[str, Any]:
    """Build a gap-condition envelope THROUGH `PartialResult`.

    Raises pydantic's ValidationError when ``unknowns`` or ``next`` is empty:
    a gap result that names no unknown and no next step is the bare refusal
    this shape exists to replace.
    """
    out = PartialResult(code=code, message=message, delivered=delivered or {},
                        unknowns=unknowns, next=next, **extra).model_dump()
    out.setdefault("suggestions", list(next))
    return out


NO_FSR_CODES = frozenset({"no_fsr_configured", "no_live_fsr"})


def no_fsr_partial(what: str, *, code: str = "no_fsr_configured",
                   message: str = "no FSR instance is configured -- run `fsrpb env set` first",
                   delivered: dict[str, Any] | None = None,
                   **extra: Any) -> dict[str, Any]:
    """The gap result for a tool that needs a live FSR instance and has none.

    ``what`` names the thing that could not be obtained ("the matching alerts
    records"). Nothing was fetched, so ``delivered`` is empty unless the tool
    has a static part to hand back.
    """
    return partial_result(
        code, message, delivered=delivered,
        unknowns=[f"{what}: no FSR instance is configured"],
        next=["Configure the FSR instance (`fsrpb env set`, or FSR_BASE_URL and "
              "FSR_API_KEY), then repeat this call.",
              "Until then, work from the data already in the conversation and "
              "name this as an open unknown in the finding."],
        **extra)


def unreachable_partial(what: str, method: str, url: str, exc: Any,
                        **extra: Any) -> dict[str, Any]:
    """The gap result for a read whose source could not be reached (transport
    failure): nothing was obtained, the source may recover, so say how to go on."""
    return partial_result(
        "transport_error", f"{method} {url} failed: {exc}",
        unknowns=[f"{what}: the source could not be reached"],
        next=["Retry the call once; a transient network fault often clears.",
              "If it fails again, report this source as unreachable, name it as "
              "an open unknown in the finding, and continue with the sources "
              "that did answer."],
        url=url, **extra)


#: run_op failure codes that mean "the source did not answer", by what to do.
_UNREACHABLE_CODES = frozenset({"transport_failed", "transport_error", "agent_timeout"})
_UPSTREAM_CODES = frozenset({"upstream_error"})
_REJECTED_CODES = frozenset({"op_request_rejected"})
_CONNECTOR_CODES = frozenset({"connector_unhealthy", "connector_not_configured",
                              "config_not_available"})
SOURCE_GAP_CODES = (_UNREACHABLE_CODES | _UPSTREAM_CODES | _REJECTED_CODES
                    | _CONNECTOR_CODES)
_OWN_KEYS = frozenset({"ok", "code", "message", "partial", "delivered", "unknowns",
                       "next", "suggestions", "status"})


def source_gap_partial(what: str, underlying: Any, **extra: Any) -> dict[str, Any] | None:
    """Convert a failed ``run_op`` answer that is a SOURCE gap into a partial result.

    Covers the failures where the data source did not answer: the connector is
    unhealthy or not configured, the request never got a response (transport,
    agent timeout), the source errored (HTTP 5xx) or rejected the request
    (HTTP 4xx). Returns None for every other failure (bad params, unknown op,
    ...), which stay ordinary actionable errors. The underlying ``code`` is kept
    as the stable control-flow key, and the underlying's own context (status,
    health_status, suggested_card, ...) rides along.
    """
    if not isinstance(underlying, dict) or underlying.get("ok") is not False:
        return None
    code = underlying.get("code")
    if code not in SOURCE_GAP_CODES:
        return None
    msg = str(underlying.get("message") or code)
    if code in _UNREACHABLE_CODES:
        unknown = f"{what}: the source could not be reached"
        nxt = ["Retry the call once; a transient network fault often clears.",
               "If it fails again, report this source as unreachable, name it as "
               "an open unknown in the finding, and continue with the sources "
               "that did answer."]
    elif code in _UPSTREAM_CODES:
        unknown = f"{what}: the source answered with a server error"
        nxt = ["Retry once with a narrower window or simpler filter; a source "
               "error on a heavy query often clears.",
               "If it errors again, name this source as an open unknown in the "
               "finding and continue with the sources that did answer."]
    elif code in _REJECTED_CODES:
        unknown = f"{what}: the source rejected the request"
        nxt = ["Fix the argument the message names and repeat the call once; the "
               "source is up, the request was wrong.",
               "If it is rejected again, name this as an open unknown in the "
               "finding rather than guessing more arguments."]
    else:
        unknown = f"{what}: the connector for this source is not usable"
        nxt = ["Ask the analyst or an admin to fix the connector configuration "
               "or its health check; this call cannot be retried into working.",
               "Until then, work from the sources that did answer and name this "
               "one as an open unknown in the finding."]
    carried = {k: v for k, v in underlying.items() if k not in _OWN_KEYS}
    if underlying.get("status") is not None:
        carried["http_status"] = underlying["status"]
    under_next = [x for x in (underlying.get("suggestions") or [])
                  if isinstance(x, str) and x.strip()]
    return partial_result(code, msg, unknowns=[unknown], next=nxt + under_next,
                          **{**carried, **extra})


def carry_partial(underlying: Any, **extra: Any) -> dict[str, Any] | None:
    """If a wrapped call answered a partial result, return it (plus the wrapper's
    own context) so the gap survives the wrapper; otherwise None.

    A wrapper that rebuilds its own error envelope from a partial would drop
    ``delivered`` / ``unknowns`` / ``next``; call this first and return it."""
    if isinstance(underlying, dict) and underlying.get("partial") is True \
            and not partial_problems(underlying):
        return {**underlying, **extra}
    return None


def partial_problems(result: Any) -> list[str]:
    """Why ``result`` is not a well-formed partial result (empty list = it is)."""
    if not isinstance(result, dict):
        return [f"result is {type(result).__name__}, not a dict"]
    try:
        PartialResult.model_validate(result)
    except ValidationError as e:
        return [f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}"
                for err in e.errors()]
    return []


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
                f"(types: {sorted({type(i).__name__ for i in result})}) -- "
                f"a collection result must be a list of dicts")
    return (f"tool '{name}' returned a bare {type(result).__name__} -- "
            f"tool outputs must be a dict envelope or a list of dict envelopes")


def _strict_mode() -> bool:
    """Whether the tool-output contract is enforced strictly (violations become
    error envelopes) vs fail-open (violations logged, result passed through).
    Off by default -- see the module docstring's roll-out posture."""
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
