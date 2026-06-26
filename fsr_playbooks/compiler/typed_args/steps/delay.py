"""Typed model for `delay` step arguments.

A friendly delay step is authored as::

    arguments:
      seconds: 5      # and/or minutes / hours / days

and expands to FSR's canonical `TimeBased` rule shape with the instance-wide
`resume_playbook` channel UUID. Already-canonical args (top-level `type` /
`delay` / `rule`) pass through untouched.

`DelayArgs` types the friendly numeric fields so a non-numeric value becomes a
clean `BAD_VALUE` diagnostic instead of an uncaught `int()` crash mid-compile
(the imperative path did a raw `int(a.pop(k))`). `expand_delay` owns the
friendly→canonical transform, preserving `NormalizerMixin._normalize_delay_args`
byte-for-byte for valid input (same delay-dict key order, same defaults, same
`rule` block).

The unknown-key strict-whitelist guard stays in the resolver
(`_check_unknown_keys`, whose message is contract-tested) and runs *before* this
walk — mirroring how `set_variable` keeps its parser handoff in the resolver.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import ConfigDict

from ...errors import CompileError  # noqa: F401  (re-exported for symmetry)
from ..base import StrictArgs
from .._bridge import validate_args

# FSR-instance-wide constant; identical on every box.
_RESUME_CHANNEL_UUID = "e2ce87c2-c55a-11ec-9d64-0242ac120002"


class DelayArgs(StrictArgs):
    """Typed view of a friendly delay step's arguments.

    The four duration fields are optional ints (pydantic coerces `5` / `"5"`).
    `extra="allow"` because canonical/sibling keys (`type`, `step_variables`,
    `mock_result`, `condition`, `timeout`, an already-built `rule`/`delay`)
    ride through to the wire shape untouched — the resolver's
    `_check_unknown_keys` has already rejected anything genuinely unknown.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    seconds: Optional[int] = None
    minutes: Optional[int] = None
    hours: Optional[int] = None
    days: Optional[int] = None


def expand_delay(
    args: Any, path: str, errors: list[CompileError],
) -> Optional[dict]:
    """Expand friendly duration args into the canonical TimeBased rule shape.

    Returns the canonical dict, or ``None`` to leave `step.arguments` unchanged
    — when the input is not a dict, is already canonical (`rule` + `delay`
    present), or a duration value fails int validation (a `BAD_VALUE` is
    appended and the step is left for the author to fix).
    """
    if not isinstance(args, dict):
        return None
    # Already-canonical input passes through untouched (matches the imperative
    # early return before any transform).
    if "rule" in args and "delay" in args:
        return None
    # Author wrote the canonical nested `delay: {days,hours,minutes,seconds}`
    # but omitted the `rule`. Don't re-derive from (absent) friendly top-level
    # keys — that would zero the durations. Preserve them and just fill the
    # event-resume rule + type defaults.
    if isinstance(args.get("delay"), dict):
        a = dict(args)
        a["type"] = a.get("type", "TimeBased")
        a.setdefault("rule", _resume_rule())
        return a

    model = validate_args(DelayArgs, args, f"{path}.arguments", errors)
    if model is None:
        return None

    a = dict(args)  # copy: the time keys are consumed, siblings preserved in order
    delay = {"days": 0, "hours": 0, "minutes": 0, "seconds": 0}
    for k in ("days", "hours", "minutes", "seconds"):
        if k in a:
            a.pop(k)
            v = getattr(model, k)
            if v is not None:
                delay[k] = v
    if not any(delay.values()):
        delay["seconds"] = 1  # avoid zero-delay edge cases
    a["type"] = a.get("type", "TimeBased")
    a["delay"] = delay
    a.setdefault("rule", _resume_rule())
    return a


def _resume_rule() -> dict:
    """The canonical event-source rule FSR attaches to a TimeBased delay so the
    engine resumes the playbook when the timer fires."""
    return {
        "actions": [{
            "type": "resume_playbook", "enabled": True,
            "channel_uuid": _RESUME_CHANNEL_UUID,
        }],
        "is_active": True,
        "event_source": "crudhub",
    }
