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
    """What the analyst asked this turn to end in."""

    requested_action: str = NONE
    condition: frozenset[str] = frozenset()

    def wants(self, disposition: str | None) -> bool:
        """True when the delivered verdict meets the request's condition."""
        return (self.requested_action != NONE and bool(disposition)
                and str(disposition).strip().lower() in self.condition)

    def to_dict(self) -> dict[str, Any]:
        return {"requested_action": self.requested_action,
                "condition": sorted(self.condition)}


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


def close_stage_directive(disposition: str, module: str, uuid: str) -> str:
    """The instruction sent with the pinned update_record round."""
    return (
        f"The analyst asked for this record to be closed if the verdict is a "
        f"false positive or benign. Your verdict is {disposition}, so stage that "
        f"close now with update_record on module {module}, uuid {uuid}. Set "
        "status to Closed, plus the closure reason and closure notes this "
        "record uses, written from your verdict. Change no other field. It goes "
        "to the analyst for approval; it does not run on its own.")


def contain_stage_directive(disposition: str) -> str:
    """The ask when the containment the analyst requested cannot be built in
    code (no policy rule names the connector and operation)."""
    return (
        f"The analyst asked for containment if this is a real threat. Your "
        f"verdict is {disposition} and nothing is staged. Stage the containment "
        "now, using the evidence you already have; do not re-investigate. Find "
        "the action with find(kind='action', action_type='containment') for the "
        "target, then stage it with emit_card(card_type='action') using the "
        "connector and operation that returns; never invent a connector name. "
        "If no containment applies, say why in one sentence.")


def split_subject(iri: str | None) -> tuple[str, str] | None:
    """(module, uuid) from a record IRI like ``/api/3/alerts/<uuid>``."""
    parts = [p for p in str(iri or "").split("/") if p]
    if len(parts) >= 2 and parts[-2] and parts[-1]:
        return parts[-2], parts[-1]
    return None


class RequestedActionPostcondition:
    """Watches a turn's executed results for the post-condition. Observer
    interface matches the loop's other guards (``note_result``)."""

    def __init__(self, spec: TaskSpec) -> None:
        self.spec = spec
        self._disposition: str | None = None
        self._staged = False
        self._fired = False

    def note_result(self, name: str, args: dict[str, Any], result: Any) -> None:
        if not isinstance(result, dict) or result.get("ok") is False:
            return
        a = args if isinstance(args, dict) else {}
        if name == "emit_card":
            ct = str(a.get("card_type") or "").strip().lower()
            if ct == "verdict":
                card = result.get("card") if isinstance(result.get("card"), dict) else {}
                payload = a.get("payload") if isinstance(a.get("payload"), dict) else {}
                d = str(card.get("disposition") or payload.get("disposition") or "")
                self._disposition = d.strip().lower() or self._disposition
            elif ct == "action":
                self._staged = True
        elif name in ("emit_action_card", "update_record", "run_op") or \
                result.get("pending_approval"):
            self._staged = True

    @property
    def disposition(self) -> str | None:
        return self._disposition

    def due(self) -> str | None:
        """The action the loop must stage now, or None."""
        if self._fired or self._staged or not self.spec.wants(self._disposition):
            return None
        return self.spec.requested_action

    def mark_fired(self) -> None:
        self._fired = True
        from .guard_fires import record_guard_fire
        record_guard_fire(type(self).__name__)
