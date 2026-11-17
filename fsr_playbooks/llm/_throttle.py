"""Provider-agnostic classification of an LLM request failure.

Every backend we ship (Anthropic, OpenAI-compatible, the FortiAI proxy) raises a
different exception type, but a rate limit and an exhausted balance look the same
on the wire: an HTTP status, an optional ``Retry-After`` header, and an error
``code``/``type`` in the body. This reads those STRUCTURALLY so one retry policy
in the loop covers all three -- and any future provider -- without keying on an
SDK's exception class.

Three outcomes, because they need different handling:

- ``throttled`` -- a transient rate limit (HTTP 429 ``rate_limit_exceeded``, or
  Anthropic's 529 ``overloaded``). Worth RETRYING after a short wait; the wait is
  the ``Retry-After`` header when the server sent one, else a backoff.
- ``out_of_credit`` -- the account balance/quota is exhausted (OpenAI returns a
  429 ``insufficient_quota``; Anthropic returns a 400 "credit balance is too
  low"). The SDK maps the OpenAI case to the SAME RateLimitError as a throttle,
  so status alone cannot tell them apart -- the code/message does. Retrying this
  only delays an inevitable failure, so it fails fast with a distinct message.
- ``other`` -- anything else; the caller's existing friendly-error path handles it.
"""
from __future__ import annotations

import email.utils
import time
from typing import Literal

#: Conservative retry policy (chosen with the user): honour ``Retry-After`` but
#: cap each wait so the analyst is not left on a spinner, and retry at most twice
#: on top of whatever the SDK already did. A 429 that outlived the SDK's own
#: backoff is not a one-off, so a couple of longer, narrated waits are the ceiling.
MAX_THROTTLE_RETRIES = 2
PER_WAIT_CAP_SECS = 20.0
#: Backoff when the server did not send a ``Retry-After`` (attempt is 1-based).
_DEFAULT_BACKOFF = (5.0, 12.0)

Outcome = Literal["throttled", "out_of_credit", "other"]

#: Substrings that mark an exhausted balance rather than a transient throttle.
_CREDIT_HINTS = (
    "insufficient_quota",
    "insufficient_credit",
    "credit balance",
    "credit_balance",
    "billing_hard_limit",
    "exceeded your current quota",
)


def _http_status(exc: Exception) -> int | None:
    """The HTTP status of a failed request, however the SDK exposes it."""
    v = getattr(exc, "status_code", None)
    if isinstance(v, int):
        return v
    resp = getattr(exc, "response", None)
    v = getattr(resp, "status_code", None)
    return v if isinstance(v, int) else None


def _error_code(exc: Exception) -> str:
    """The provider's error ``code``/``type``, lower-cased. OpenAI puts it on
    ``.code`` (and in ``body.error.code``); Anthropic uses ``body.error.type``."""
    code = getattr(exc, "code", None)
    if isinstance(code, str) and code:
        return code.lower()
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict):
            return str(err.get("code") or err.get("type") or "").lower()
    return ""


def _message_text(exc: Exception) -> str:
    """Best-effort human message from the exception, lower-cased."""
    msg = getattr(exc, "message", None)
    if isinstance(msg, str) and msg:
        return msg.lower()
    return str(exc).lower()


def retry_after_seconds(exc: Exception) -> float | None:
    """Seconds to wait from a ``Retry-After`` header (numeric or HTTP-date), or
    None when the server did not send one."""
    resp = getattr(exc, "response", None)
    headers = getattr(resp, "headers", None)
    if not headers:
        return None
    try:
        ra = headers.get("retry-after") or headers.get("Retry-After")
    except Exception:  # noqa: BLE001 -- a non-mapping headers object
        return None
    if not ra:
        return None
    try:
        return max(0.0, float(ra))
    except (TypeError, ValueError):
        pass
    try:
        dt = email.utils.parsedate_to_datetime(ra)
    except (TypeError, ValueError):
        return None
    if dt is None:
        return None
    return max(0.0, dt.timestamp() - time.time())


def classify(exc: Exception) -> tuple[Outcome, float | None]:
    """Classify a request failure. Returns ``(outcome, retry_after)`` where
    ``retry_after`` is the server's requested wait for a ``throttled`` outcome
    (None when it sent none), and always None otherwise."""
    status = _http_status(exc)
    code = _error_code(exc)
    msg = _message_text(exc)

    # Credit/quota first: OpenAI's exhausted-balance case is a 429 that would
    # otherwise read as a transient throttle, so the code/message decides.
    if any(h in code for h in _CREDIT_HINTS) or any(h in msg for h in _CREDIT_HINTS):
        return "out_of_credit", None

    if (status in (429, 529)
            or "rate_limit" in code or "rate limit" in msg
            or "overloaded" in code or "overloaded" in msg):
        return "throttled", retry_after_seconds(exc)

    return "other", None


def wait_for(attempt: int, retry_after: float | None) -> float:
    """The actual wait before retry ``attempt`` (1-based): the server's
    ``Retry-After`` when given, else a backoff -- both capped."""
    if retry_after is not None:
        return min(retry_after, PER_WAIT_CAP_SECS)
    idx = min(attempt, len(_DEFAULT_BACKOFF)) - 1
    return min(_DEFAULT_BACKOFF[idx], PER_WAIT_CAP_SECS)


def out_of_credit_message(provider_label: str) -> str:
    """Analyst-facing message for an exhausted balance -- names the cause and the
    fix, never the raw provider envelope."""
    return (
        f"{provider_label} rejected the request because the account is out of "
        f"credit. Add funds to the API account (or switch the configured model "
        f"to one with available credit), then try again."
    )


def throttled_give_up_message(provider_label: str) -> str:
    """Analyst-facing message when retries were spent and the throttle held."""
    return (
        f"{provider_label} is rate-limiting requests and did not recover after a "
        f"short wait. Please try again in a few minutes."
    )


def throttle_notice(provider_label: str, wait_secs: float) -> str:
    """Non-terminal status line shown while the loop waits out a throttle."""
    secs = max(1, int(round(wait_secs)))
    return f"{provider_label} is busy; retrying in {secs}s."
