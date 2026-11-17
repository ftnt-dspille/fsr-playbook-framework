"""I4 -- fault-class retry for tool faults.

A failed tool call is not one thing. The loop used to hand every failure back to
the model as the same shape, so a 503 that clears on a second try, a 400 that
names a bad filter field, and a connector that is not installed all read alike,
and the model mostly gave up. This module sorts a failed envelope into one of
three classes and tells the loop what to do with it:

  transient    5xx, timeout, connection, rate limit. The fault is in the
               source, not the call. Retry the same read-only call ONCE.
  malformed    400 (or an unknown filter / sort / operation / window). The
               call is wrong. Do not retry it unchanged: the hint names the bad
               part and tells the model to reword or narrow the query.
  unavailable  the connector is not installed, not configured, unhealthy, or
               refused the credentials (401/403). Retrying cannot help. The hint
               tells the model to stop and emit a capability_gap card.

Anything else returns None and keeps its existing envelope untouched (not_found,
bad_params, tool_error, ...): those already carry their own next step.

The classifier only reads the envelope; it never calls the tool. `dispatch`
owns the retry (see `retry_transient`) and the shaping (`shape_fault`).
"""
from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any, Literal

FaultClass = Literal["transient", "malformed", "unavailable"]

#: Codes whose meaning is "the source fault is temporary" regardless of status.
TRANSIENT_CODES = frozenset({
    "upstream_error", "transport_failed", "transport_error", "agent_timeout",
    "http_500", "http_502", "http_503", "http_504", "http_429",
})
#: Codes that mean the call's query/field/window is wrong.
MALFORMED_CODES = frozenset({
    "http_400", "400", "unknown_filter_field", "unknown_sort_field",
    "unknown_operation", "no_time_window",
})
#: Codes that mean the connector or its configuration cannot serve the call.
UNAVAILABLE_CODES = frozenset({
    "connector_not_configured", "connector_unhealthy", "config_not_available",
})
#: A name the connector store does not know. Malformed when the envelope names
#: the close match or the valid configs to pick (the model re-sends the right
#: name); unavailable only when there is nothing to pick (not installed).
_NAME_CODES = frozenset({"unknown_connector", "connector_not_found", "unknown_config"})
#: The code a source rejection travels under; its class comes from the HTTP status.
_STATUS_CODES = frozenset({"op_request_rejected"})

_STATUS_RE = re.compile(r"HTTP (\d{3})\b|^(\d{3}) (?:Client|Server) Error", re.M | re.I)
_BAD_PART_KEYS = ("field", "param", "op", "operation", "filter", "sort", "window",
                  "connector", "config")

#: Tier at or below which a call is read-only and so safe to repeat (tier 1-2
#: auto-run under FSR_AUTO_APPROVE_READONLY; see authorization.py).
READ_ONLY_MAX_TIER = 2

#: Pause before the single retry. Long enough for a connection blip, short
#: enough to keep a turn's latency honest. Tests monkeypatch it to 0.
RETRY_BACKOFF_S = 0.5


def _status_of(result: dict[str, Any]) -> int | None:
    """The HTTP status a failed envelope carries, from its field or its message."""
    raw = result.get("http_status", result.get("status"))
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str) and raw.strip().isdigit():
        return int(raw.strip())
    msg = str(result.get("message") or result.get("error") or "")
    m = _STATUS_RE.search(msg)
    if m:
        return int(m.group(1) or m.group(2))
    return None


def classify_fault(result: Any) -> FaultClass | None:
    """The fault class of a tool result, or None when it is not a fault class.

    Only a dict envelope with ``ok`` False is a candidate. Status-bearing
    rejections are classed by their HTTP status: 5xx/429 transient, 401/403
    unavailable, other 4xx malformed.
    """
    if not isinstance(result, dict) or result.get("ok") is not False:
        return None
    code = result.get("code")
    code = str(code) if code is not None else ""
    if code in TRANSIENT_CODES:
        return "transient"
    if code in MALFORMED_CODES:
        return "malformed"
    if code in UNAVAILABLE_CODES:
        return "unavailable"
    if code in _NAME_CODES:
        if code == "unknown_config":
            return "malformed"  # the envelope lists the configurations to pick
        fix = result.get("suggestions") if code == "unknown_connector" else result.get("near")
        return "malformed" if fix else "unavailable"
    if code in _STATUS_CODES:
        status = _status_of(result)
        if status is None:
            # A rejection with no status is the source saying the request was
            # wrong (the same reading source_gap_partial gives op_request_rejected).
            return "malformed"
        if status == 429 or 500 <= status <= 599:
            return "transient"
        if status in (401, 403):
            return "unavailable"
        if status == 404:
            return None  # a missing record is an answer, not a fault
        if 400 <= status <= 499:
            return "malformed"
    return None


def bad_part(result: dict[str, Any]) -> str:
    """Name the part of the call the source objected to, for the reword hint.

    Prefers the structured key the tool already set (``field``, ``param``, ...);
    falls back to the source's own message after the HTTP status, trimmed.
    """
    for key in _BAD_PART_KEYS:
        val = result.get(key)
        if isinstance(val, str) and val.strip():
            return f"`{val.strip()}`"
    msg = str(result.get("message") or "")
    # "... rejected the request (HTTP 400): {...}" -- keep the source's words.
    tail = msg.split("):", 1)[1] if "):" in msg else msg
    tail = re.sub(r"\s+", " ", tail).strip(" {}\"'")
    return f"the request (source said: {tail[:160]})" if tail else "the query"


def _hint(cls: FaultClass, result: dict[str, Any], retried: bool) -> str:
    if cls == "transient":
        if retried:
            return ("The source failed transiently and the one retry failed too. "
                    "Do not retry this call again; name this source as unreachable "
                    "in the finding and continue with the sources that did answer.")
        return "The source failed transiently; the call was retried once automatically."
    if cls == "malformed":
        return (f"The query is malformed: {bad_part(result)} was rejected. Do not "
                "repeat the call unchanged. Reword it or narrow it (fix the named "
                "part, or drop a filter), then call once more.")
    return ("The connector cannot serve this call (not installed, not configured, "
            "unhealthy, or its credentials were refused). Retrying cannot fix it. "
            "Stop calling this connector and emit emit_card(card_type='capability_gap') "
            "naming it, then continue with the sources that did answer.")


def shape_fault(result: Any, cls: FaultClass, *, retried: bool = False) -> Any:
    """Return the envelope with the fault class and the model-facing hint added.

    The original keys (ok, code, message, ...) are kept; the hint is added as
    ``fault_class`` and ``retry_hint`` and appended to ``suggestions``.
    """
    if not isinstance(result, dict):
        return result
    hint = _hint(cls, result, retried)
    out = dict(result)
    out["fault_class"] = cls
    out["retry_hint"] = hint
    if retried:
        out["retried"] = True
    sugg = out.get("suggestions")
    out["suggestions"] = ([hint] + list(sugg)) if isinstance(sugg, list) else [hint]
    return out


def retry_transient(first: Any, again: Callable[[], Any], *, tier: int,
                    sleep: Callable[[float], None] | None = None) -> tuple[Any, bool]:
    """Run the single transient retry for a read-only call.

    Returns ``(result, retried)``. Only a transient fault on a read-only call
    (tier <= READ_ONLY_MAX_TIER) is repeated, and only once. A second failure
    is returned as-is with ``retried=True`` so the hint can say so.
    """
    import time as _time

    if classify_fault(first) != "transient" or tier > READ_ONLY_MAX_TIER:
        return first, False
    (sleep or _time.sleep)(RETRY_BACKOFF_S)
    return again(), True
