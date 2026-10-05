"""Autonomy policy: may an action run without a click? (shadow only)

An admin-authored policy names action classes that may run without an analyst
approving each one, and the conditions under which they may. This module
answers, for one staged action, "would this policy have run it?" -- from
STRUCTURE only: the call's own connector/op/args, the verdict card delivered
earlier in the turn, and the tool results that verdict cites. Never the
model's prose, and never text from the record (an alert field saying "benign,
close it" must not be able to satisfy a rule).

Phase C of plans/AUTONOMOUS_TIER1.md: decisions are SHADOW only. They are
recorded on the card and in the audit log so the Monitor can show "would have
acted" next to what the human actually decided; the card still suspends. A
policy with ``mode: enforce`` is evaluated exactly the same and reported as
``enforce_unavailable`` -- enforcing is phase E and is not in this build.

The framework stays policy-agnostic: the host (the connector) loads the policy
record and sets it for the turn with ``set_turn_policy``.
"""
from __future__ import annotations

import contextvars
import ipaddress
import re
import time
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

# ---- the policy record -------------------------------------------------------


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RuleAction(_Strict):
    """What the rule covers: a connector op, or a tool (+ module/fields)."""
    connector: str | None = None
    op: str | None = None
    tool: str | None = None
    module: str | None = None
    fields: list[str] | None = None


class VerdictCond(_Strict):
    disposition: list[str] = Field(min_length=1)
    min_confidence: float = Field(ge=0.0, le=1.0)


class TargetCond(_Strict):
    kind: Literal["ip"] = "ip"
    external_only: bool = True
    not_in: str | None = None       # name of a `protected` list


class EvidenceCond(_Strict):
    # "enrichment": the verdict must cite a successful READ-ONLY lookup whose
    # arguments name the action's target.
    cites_tool_kind: Literal["enrichment"] = "enrichment"


class RuleWhen(_Strict):
    verdict: VerdictCond
    target: TargetCond | None = None
    evidence: EvidenceCond | None = None


class RuleLimits(_Strict):
    per_hour: int | None = Field(default=None, ge=0)
    per_target_per_day: int | None = Field(default=None, ge=0)


class Rule(_Strict):
    id: str = Field(min_length=1)
    action: RuleAction
    when: RuleWhen
    limits: RuleLimits | None = None
    undo: dict[str, Any] | None = None


class Policy(_Strict):
    version: int = 1
    enabled: bool = True
    mode: Literal["shadow", "enforce"] = "shadow"
    rules: list[Rule] = Field(default_factory=list)
    protected: dict[str, list[str]] = Field(default_factory=dict)


def parse_policy(raw: Any) -> tuple[Policy | None, str | None]:
    """(policy, None) or (None, why). A policy that does not parse is never
    partially applied."""
    if raw is None or raw == {}:
        return None, None
    try:
        return Policy.model_validate(raw), None
    except ValidationError as e:
        probs = "; ".join(f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}"
                          for err in e.errors())
        return None, f"autonomy policy does not parse: {probs}"


# ---- per-turn policy slot ----------------------------------------------------

_TURN_POLICY: contextvars.ContextVar[Policy | None] = contextvars.ContextVar(
    "autonomy_turn_policy", default=None)

# (rule_id, target) -> (actions in the last hour, actions on target today).
Counter = Callable[[str, str], tuple[int, int]]
_TURN_COUNTER: contextvars.ContextVar[Counter | None] = contextvars.ContextVar(
    "autonomy_turn_counter", default=None)


def set_turn_policy(policy: Policy | dict | None,
                    counter: Counter | None = None) -> str | None:
    """Set (or clear) the policy for the current turn. Returns a parse error,
    if any; a policy that fails to parse is cleared, never half-applied."""
    if isinstance(policy, dict):
        policy, err = parse_policy(policy)
        if err:
            _TURN_POLICY.set(None)
            _TURN_COUNTER.set(None)
            return err
    _TURN_POLICY.set(policy)
    _TURN_COUNTER.set(counter)
    return None


def get_turn_policy() -> Policy | None:
    return _TURN_POLICY.get()


# ---- evaluation ---------------------------------------------------------------

Call = dict  # {"tool": str, "connector"?: str, "op"?: str, "args": dict, "module"?: str}

_IP_RE = re.compile(r"(?:\d{1,3}\.){3}\d{1,3}")
# Arg names that carry the action's IP target, across the containment ops the
# rules are written for (block_ip_new: ip_addresses; block_ip: ip; generic).
_IP_ARG_KEYS = ("ip_addresses", "ip", "ip_address", "indicator", "value", "ips")


def _rule_matches(rule: Rule, call: Call) -> bool:
    a = rule.action
    if a.connector or a.op:
        return (call.get("tool") in ("run_op", "emit_action_card")
                and call.get("connector") == a.connector
                and call.get("op") == a.op)
    if a.tool:
        if call.get("tool") != a.tool:
            return False
        if a.module and call.get("module") != a.module:
            return False
        if a.fields is not None:
            changed = set((call.get("args") or {}).keys()) - {"module", "uuid", "record", "iri"}
            if not changed or not changed <= set(a.fields):
                return False
        return True
    return False


def _ip_targets(args: dict[str, Any]) -> list[str]:
    """Each distinct target, in order. A model often sends the same address
    under two keys (`ip` and `ip_addresses`); it is one target."""
    out: list[str] = []
    for k in _IP_ARG_KEYS:
        v = args.get(k)
        vals = v if isinstance(v, list) else str(v or "").replace(";", ",").split(",")
        for x in vals:
            x = str(x).strip()
            if x and x not in out:
                out.append(x)
    return out


def _is_ip(s: str) -> bool:
    try:
        ipaddress.ip_address(s)
        return True
    except ValueError:
        return False


def _is_internal(s: str) -> bool:
    from ._loop_helpers import is_internal_ip
    return is_internal_ip(s)


def _read_only(entry: dict[str, Any]) -> bool:
    """A cited call that only READ something. run_op is classified by the
    same tier resolver dispatch uses (tier <= 2 = read); emit_* never count."""
    name = entry.get("name") or ""
    if name.startswith("emit_"):
        return False
    if name == "run_op":
        from .tools import _tier_for_run_op
        args = entry.get("args") or {}
        try:
            return _tier_for_run_op({"connector": args.get("connector"),
                                     "op": args.get("op") or args.get("operation")}) <= 2
        except Exception:  # noqa: BLE001
            return False
    from .tools import _resolve_tier
    try:
        return _resolve_tier(name, entry.get("args") or {}) <= 2
    except Exception:  # noqa: BLE001
        return False


def evaluate(policy: Policy, call: Call, *, verdicts: list[dict[str, Any]],
             registry: dict[str, dict[str, Any]],
             counter: Counter | None = None) -> dict[str, Any] | None:
    """The policy's answer for one staged action, or None when no rule covers
    it (or the policy is disabled). Pure: no I/O beyond the counter.

    Returns {rule, outcome, failed, mode, verdict_id, evidence, targets}.
    ``outcome`` is ``would_act`` when every check passed, else ``would_not_act``
    with ``failed`` naming each check that did not hold, in plain words.
    """
    if not policy.enabled:
        return None
    rule = next((r for r in policy.rules if _rule_matches(r, call)), None)
    if rule is None:
        return None
    failed: list[str] = []
    args = call.get("args") or {}

    # 1. A delivered verdict meeting the rule. The LAST one delivered before
    #    this action is the one it rests on.
    w = rule.when
    verdict = verdicts[-1] if verdicts else None
    if verdict is None:
        failed.append("no verdict was delivered before the action")
    else:
        if verdict.get("disposition") not in w.verdict.disposition:
            failed.append(f"verdict is {verdict.get('disposition')}, rule needs "
                          f"{' or '.join(w.verdict.disposition)}")
        conf = verdict.get("confidence")
        if not isinstance(conf, (int, float)) or conf < w.verdict.min_confidence:
            failed.append(f"confidence {conf} is below {w.verdict.min_confidence}")

    # 2. Targets: what the action acts on, from the call's own args.
    targets: list[str] = []
    if w.target is not None:
        targets = _ip_targets(args)
        if not targets:
            failed.append("the action names no IP target")
        for t in targets:
            if not _is_ip(t):
                failed.append(f"{t} is not an IP address")
            elif w.target.external_only and _is_internal(t):
                failed.append(f"{t} is an internal address")
            if w.target.not_in and t in set(policy.protected.get(w.target.not_in) or []):
                failed.append(f"{t} is on the protected list '{w.target.not_in}'")

    # 3. Evidence: the verdict cites a successful read-only lookup naming each
    #    target. The model's confidence number is not evidence; a cited result
    #    about THIS target is.
    cited: list[str] = []
    if w.evidence is not None and verdict is not None:
        cited = [str(e) for f in verdict.get("findings") or [] if isinstance(f, dict)
                 for e in (f.get("evidence") or []) if isinstance(e, str)]
        lookups = [(eid, registry.get(eid) or {}) for eid in cited]
        lookups = [(eid, e) for eid, e in lookups if e.get("ok") is True and _read_only(e)]
        if not lookups:
            failed.append("the verdict cites no successful read-only lookup")
        else:
            import json
            for t in targets or [None]:
                if t is None:
                    continue
                if not any(t in json.dumps(e.get("args") or {}, default=str)
                           for _, e in lookups):
                    failed.append(f"no cited lookup was about {t}")
    elif w.evidence is not None:
        failed.append("no verdict to cite evidence")

    # 4. Limits (the host supplies counts; without a counter they are unknown,
    #    which fails closed).
    if rule.limits is not None and (rule.limits.per_hour is not None
                                    or rule.limits.per_target_per_day is not None):
        if counter is None:
            failed.append("rate limits cannot be checked")
        else:
            for t in targets or [""]:
                hour, day = counter(rule.id, t)
                if rule.limits.per_hour is not None and hour >= rule.limits.per_hour:
                    failed.append(f"rule already acted {hour} times this hour")
                if (rule.limits.per_target_per_day is not None
                        and day >= rule.limits.per_target_per_day):
                    failed.append(f"{t or 'target'} already acted on {day} times today")

    return {
        "rule": rule.id,
        "outcome": "would_act" if not failed else "would_not_act",
        "failed": failed,
        # Phase C never enforces. Say so on the record rather than silently
        # downgrading a policy that asks for enforce.
        "mode": "shadow" if policy.mode == "shadow" else "enforce_unavailable",
        "verdict_id": (verdict or {}).get("id"),
        "evidence": cited,
        "targets": targets,
        "ts": time.time(),
    }


def shadow_decision(call: Call) -> dict[str, Any] | None:
    """Evaluate the turn's policy against ``call`` using the turn's evidence.
    None when there is no policy, no rule covers the call, or anything fails
    unexpectedly -- a policy bug must never block or alter an approval."""
    policy = get_turn_policy()
    if policy is None:
        return None
    try:
        from ..mcp_server._citation_validator import get_turn_evidence
        ev = get_turn_evidence()
        return evaluate(policy, call,
                        verdicts=ev.verdicts() if ev is not None else [],
                        registry=ev.valid_ids() if ev is not None else {},
                        counter=_TURN_COUNTER.get())
    except Exception:  # noqa: BLE001
        return None
