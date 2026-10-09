"""Did a turn answer? One classification for every harness.

The policies this replaces disagreed about the same envelope: a dead gateway
arrives PRE-WRAPPED ("Could not reach the OpenAI endpoint ...", never the raw
`httpx.ConnectError`), a provider failure comes back as `ok: true` with
`stop_reason: "error"`, and a truncated turn looks like a finished one. One
harness aborted, one graded a failed check, one excluded the session, one
graded the error text as the model's answer.

Only a TRANSPORT failure makes a turn unscoreable. A provider REJECTION (a
4xx other than 429) is a result: the request reached the model and was
refused, usually because of what the agent put in it.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .frames import frames, pending_halt

_TRANSPORT_FAILURE_MARKERS = (
    "connecterror", "connect error", "all connection attempts failed",
    "could not reach", "connection refused", "network is unreachable",
    "name or service not known", "nodename nor servname",
    "timed out", "timeout", "readerror", "read error",
    "remoteprotocolerror", "connection reset", "temporarily unavailable",
    "502", "503", "504",
)
_REJECTION_MARKERS = ("400", "422", "bad request", "badrequest", "invalid_request",
                      "context length", "maximum context")

#: Stops that mean "cut off", not "finished". `max_turns` is the label sessions
#: recorded before the provider mapped `finish_reason: length` to `max_tokens`.
TRUNCATION_STOPS = {
    "max_turns": "output-token cap (pre-fix label for finish_reason='length')",
    "max_tokens": "output-token cap",
    "length": "output-token cap",
    "max_tool_turns": "tool-loop iteration cap",
}
ERROR_STOPS = frozenset({"error", "stream_error"})

#: Every outcome. `answered` and `halted` are scoreable; `provider_error` is
#: scoreable as a failure; `transport_error` and `truncated` are not results.
OUTCOMES = ("answered", "halted", "truncated", "provider_error", "transport_error")


def is_transport_failure(message: str) -> bool:
    """True when the turn never reached the model at all."""
    m = (message or "").lower()
    if "429" in m or "rate limit" in m:
        return True  # never delivered; retryable, not the agent's doing
    if any(k in m for k in _REJECTION_MARKERS):
        return False
    return any(k in m for k in _TRANSPORT_FAILURE_MARKERS)


@dataclass(frozen=True)
class TurnOutcome:
    kind: str
    detail: str = ""

    @property
    def scoreable(self) -> bool:
        """Whether grading this turn measures the app (not the network or a cap)."""
        return self.kind in ("answered", "halted", "provider_error")


def _error_message(envelope: Any) -> str | None:
    if isinstance(envelope, dict):
        if envelope.get("error"):
            return str(envelope["error"])
        if envelope.get("ok") is False:
            return "turn returned ok=False"
    for f in frames(envelope):
        if f.get("type") == "error":
            return str(f.get("message") or f)
    if isinstance(envelope, dict) and envelope.get("stop_reason") in ERROR_STOPS:
        return f"stop_reason={envelope.get('stop_reason')}"
    return None


def classify_turn(envelope: Any) -> TurnOutcome:
    if not isinstance(envelope, (dict, list)):
        return TurnOutcome("transport_error", f"no envelope: {envelope!r:.200}")
    err = _error_message(envelope)
    if err is not None:
        kind = "transport_error" if is_transport_failure(err) else "provider_error"
        return TurnOutcome(kind, err[:500])
    stop = str(envelope.get("stop_reason") or "") if isinstance(envelope, dict) else ""
    if stop in TRUNCATION_STOPS:
        return TurnOutcome("truncated", f"stop_reason={stop!r}: {TRUNCATION_STOPS[stop]}")
    halt = pending_halt(envelope)
    if halt is not None:
        return TurnOutcome("halted", f"{halt['kind']} {halt['key']}={halt['value']}")
    return TurnOutcome("answered")
