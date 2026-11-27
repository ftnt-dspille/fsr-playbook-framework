"""TaskSpec -- the analyst's request as data (north-star plan, Phase 1).

The analyst often asks for an action conditioned on the verdict: "triage this,
and if it is a false positive close it", "if it's malicious, block it". Before
this module that request lived only in the transcript. Guards noticed
afterwards that nothing was staged and asked the model to stage it, and a
sampled model sometimes did not ("verdict delivered, no action staged").

Here the request is parsed once, from the analyst's own words (trusted input:
never record content), into a small frozen spec. The loop then checks a
post-condition in code:

    requested_action != none  and  delivered verdict in condition
        and nothing staged    =>  the loop stages the action itself

Whether to stage is the code's decision. The model still fills the values it
is judging (the closure reason and notes) in a round pinned to the write
tool, and the staged call goes through the normal approval tier and autonomy
policy, so this never acts on its own.

The parser is deliberately small and deterministic: no extra LLM call per
turn. A miss costs what it cost before (no code staging; the model may still
stage on its own). A false positive costs one staged card the analyst can
decline; it never executes anything.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

NONE = "none"
CLOSE = "close"
CONTAIN = "contain"

# Where a request came from. The analyst's words win; with no analyst
# watching, the request is the unattended triage contract (contain a confirmed
# threat) and the admin's autonomy policy (close what its close rule closes).
ANALYST = "analyst"
UNATTENDED = "unattended"
POLICY = "policy"

_FP = frozenset({"false_positive", "benign"})
_TP = frozenset({"true_positive"})

# Default condition when the analyst names the action but not the verdict.
_DEFAULT_CONDITION = {CLOSE: _FP, CONTAIN: _TP}

_CLOSE_VERBS = r"close|resolve|dismiss"
_CONTAIN_VERBS = r"block|contain|isolate|quarantine"

_COND_WORDS: tuple[tuple[str, frozenset[str]], ...] = (
    (r"false[\s-]*positive|\bfp\b|benign|harmless|not\s+malicious|legit(?:imate)?", _FP),
    (r"true[\s-]*positive|\btp\b|malicious|a\s+(?:real\s+)?threat|confirmed|compromised|c2", _TP),
)

_IF_RE = re.compile(r"\b(?:if|when|once|in\s+case)\b", re.IGNORECASE)
_ACTION_RE = re.compile(
    rf"\b(?P<close>{_CLOSE_VERBS})\b|\b(?P<contain>{_CONTAIN_VERBS})\b", re.IGNORECASE)
# The verb used without asking for anything: a question, a negation, a past
# report, or "close" as an adjective/preposition ("close to", "close call").
_NOT_A_REQUEST_RE = re.compile(
    r"\b(?:should|shall|would|could|can|may|might|do|did|does)\s+(?:i|we|you|it|they)\b"
    r"|\b(?:don'?t|do\s+not|never|no\s+need\s+to|without)\s+(?:\w+\s+){0,1}"
    rf"(?:{_CLOSE_VERBS}|{_CONTAIN_VERBS})\b"
    r"|\b(?:was|were|is|are|been|got|already)\s+(?:\w+\s+){0,2}"
    rf"(?:{_CLOSE_VERBS}|{_CONTAIN_VERBS})(?:ed|d)\b"
    r"|\bclose\s+(?:to|call|match|enough|look)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class TaskSpec:
    """What this turn was asked to end in."""

    requested_action: str = NONE
    condition: frozenset[str] = frozenset()
    #: The verdict's confidence must reach this (a policy rule's bar). 0 = any.
    min_confidence: float = 0.0
    source: str = ANALYST
    #: For a policy close: the fields the rule lets the write change, and the
    #: rule itself (its values go into the directive). Empty = not restricted.
    fields: tuple[str, ...] = ()
    rule: Any = None

    def wants(self, disposition: str | None, confidence: float | None = None) -> bool:
        """True when the delivered verdict meets the request's condition."""
        if self.requested_action == NONE or not disposition:
            return False
        if str(disposition).strip().lower() not in self.condition:
            return False
        if self.min_confidence > 0:
            return confidence is not None and confidence >= self.min_confidence
        return True

    def to_dict(self) -> dict[str, Any]:
        return {"requested_action": self.requested_action,
                "condition": sorted(self.condition), "source": self.source}


def _condition_in(text: str) -> frozenset[str]:
    found: set[str] = set()
    for pat, disp in _COND_WORDS:
        if re.search(pat, text, re.IGNORECASE):
            found |= disp
    return frozenset(found)


def parse_task_spec(user_text: str | None) -> TaskSpec:
    """The requested action and its verdict condition, from the analyst's
    message. ``TaskSpec()`` (none) when the message asks for no action."""
    text = (user_text or "").strip()
    if not text:
        return TaskSpec()
    for sentence in re.split(r"(?<=[.;!?\n])\s+", text):
        if not sentence.strip() or _NOT_A_REQUEST_RE.search(sentence):
            continue
        m = _ACTION_RE.search(sentence)
        if m is None:
            continue
        action = CLOSE if m.group("close") else CONTAIN
        cond: frozenset[str] = frozenset()
        if _IF_RE.search(sentence):
            cond = _condition_in(sentence)
        if not cond:
            cond = _DEFAULT_CONDITION[action]
        # "If it's malicious, close it" names a verdict the action does not
        # fit; trust the action's own meaning rather than stage a close of a
        # threat or a block of a false positive.
        cond = cond & _DEFAULT_CONDITION[action]
        if not cond:
            continue
        return TaskSpec(requested_action=action, condition=cond)
    return TaskSpec()


def specs_for_turn(user_text: str | None, *, unattended: bool = False,
                   policy: Any = None) -> tuple[TaskSpec, ...]:
    """Every request this turn carries, the analyst's first. Unattended, the
    turn also asks for containment of a true_positive, and for the close the
    admin's enabled policy would take on a false positive at its bar."""
    out: list[TaskSpec] = []
    asked = parse_task_spec(user_text)
    if asked.requested_action != NONE:
        out.append(asked)
    if not unattended:
        return tuple(out)
    out.append(TaskSpec(CONTAIN, _TP, source=UNATTENDED))
    if policy is not None and getattr(policy, "enabled", False):
        for rule in getattr(policy, "rules", ()) or ():
            act = rule.action
            v = getattr(rule.when, "verdict", None)
            if act.tool != "update_record" or v is None:
                continue
            cond = frozenset(str(d).lower() for d in v.disposition) & _FP
            if cond:
                out.append(TaskSpec(CLOSE, cond, min_confidence=float(v.min_confidence or 0),
                                    source=POLICY, fields=tuple(act.fields or ()), rule=rule))
                break
    return tuple(out)


def _field_list(spec: TaskSpec) -> str:
    values = (getattr(spec.rule.action, "values", None) or {}) if spec.rule is not None else {}
    parts = []
    for f in spec.fields:
        allowed = values.get(f)
        parts.append(f"{f} (to {' or '.join(allowed)})" if allowed else f)
    return ", ".join(parts)


def close_stage_directive(spec: TaskSpec, disposition: str, module: str, uuid: str) -> str:
    """The instruction sent with the pinned update_record round."""
    if spec.source == POLICY:
        return (
            f"Your verdict is {disposition} and nothing is staged. No analyst is "
            "watching this triage, and the admin's policy closes records like "
            f"this one. Stage the close now with update_record on module {module}, "
            f"uuid {uuid}, setting each of these fields and no others: "
            f"{_field_list(spec)}. Write the closure values from your verdict.")
    return (
        f"The analyst asked for this record to be closed if the verdict is a "
        f"false positive or benign. Your verdict is {disposition}, so stage that "
        f"close now with update_record on module {module}, uuid {uuid}. Set "
        "status to Closed, plus the closure reason and closure notes this "
        "record uses, written from your verdict. Change no other field. It goes "
        "to the analyst for approval; it does not run on its own.")


def contain_stage_directive(spec: TaskSpec, disposition: str) -> str:
    """The ask when the requested containment cannot be built in code (no
    policy rule names the connector and operation)."""
    who = ("No analyst is watching this triage, so containment you do not "
           "stage now is never proposed." if spec.source != ANALYST else
           "The analyst asked for containment if this is a real threat.")
    return (
        f"Your verdict is {disposition} and nothing is staged. {who} Stage the "
        "containment this threat calls for now (for example a block of the "
        "malicious external address), using the evidence you already have; do "
        "not re-investigate. Find the action first with "
        "find(kind='action', action_type='containment') for the target, then "
        "stage it with emit_card(card_type='action') using the connector and "
        "operation that returns; never invent a connector name. If no "
        "containment applies, say why in one sentence.")


_FIX_RE = re.compile(
    r"\b(?:fix|remediate|revert|undo|roll\s*back|rollback|remove|delete|restore)\b",
    re.IGNORECASE)
_FIX_NOT_A_REQUEST_RE = re.compile(
    r"\b(?:don'?t|do\s+not|never|no\s+need\s+to|without)\s+(?:\w+\s+){0,1}"
    r"(?:fix|remediate|revert|undo|roll\s*back|rollback|remove|delete|restore)\b"
    r"|\bhow\s+(?:to|do|can|would|should|might)\b"
    r"|\b(?:was|were|is|are|been|got|already)\s+(?:\w+\s+){0,2}"
    r"(?:fixed|reverted|removed|deleted|restored|undone)\b",
    re.IGNORECASE)


def asks_for_fix(user_text: str | None) -> bool:
    """True when the analyst's own message asks for a fix of what the turn
    found: "propose the fix", "stage a card to delete the route", "revert it".
    Trusted input like ``parse_task_spec``; the loop acts on it only when the
    turn's own read found the offending item, so a miss or a false hit costs at
    most one approval card the analyst can decline."""
    for sentence in re.split(r"(?<=[.;!?\n])\s+", (user_text or "").strip()):
        if (sentence.strip() and _FIX_RE.search(sentence)
                and not _FIX_NOT_A_REQUEST_RE.search(sentence)):
            return True
    return False


def split_subject(iri: str | None) -> tuple[str, str] | None:
    """(module, uuid) from a record IRI like ``/api/3/alerts/<uuid>``."""
    parts = [p for p in str(iri or "").split("/") if p]
    if len(parts) >= 2 and parts[-2] and parts[-1]:
        return parts[-2], parts[-1]
    return None


class RequestedActionPostcondition:
    """Watches a turn's executed results for the post-condition. Observer
    interface matches the loop's other guards (``note_result``)."""

    def __init__(self, specs: TaskSpec | tuple[TaskSpec, ...] | list[TaskSpec]) -> None:
        self.specs = (specs,) if isinstance(specs, TaskSpec) else tuple(specs)
        self._disposition: str | None = None
        self._confidence: float | None = None
        self._staged = False
        self._fired = False

    def note_result(self, name: str, args: dict[str, Any], result: Any) -> None:
        if not isinstance(result, dict) or result.get("ok") is False:
            return
        a = args if isinstance(args, dict) else {}
        if name == "emit_card":
            ct = str(a.get("card_type") or "").strip().lower()
            if ct == "verdict":
                card_v = result.get("card")
                card = card_v if isinstance(card_v, dict) else {}
                payload_v = a.get("payload")
                payload = payload_v if isinstance(payload_v, dict) else {}
                d = str(card.get("disposition") or payload.get("disposition") or "")
                if d.strip():
                    # The last delivered verdict wins, confidence with it.
                    self._disposition = d.strip().lower()
                    conf = card.get("confidence", payload.get("confidence"))
                    try:
                        self._confidence = float(conf) if conf is not None else None
                    except (TypeError, ValueError):
                        self._confidence = None
            elif ct == "action":
                self._staged = True
        elif name in ("emit_action_card", "update_record", "run_op") or \
                result.get("pending_approval"):
            self._staged = True

    @property
    def staged(self) -> bool:
        return self._staged

    @property
    def disposition(self) -> str | None:
        return self._disposition

    def due(self) -> TaskSpec | None:
        """The request the loop must stage now (the first one the delivered
        verdict meets), or None."""
        if self._fired or self._staged:
            return None
        return next((s for s in self.specs
                     if s.wants(self._disposition, self._confidence)), None)

    def mark_fired(self) -> None:
        self._fired = True
        from .guard_fires import record_guard_fire
        record_guard_fire(type(self).__name__)
