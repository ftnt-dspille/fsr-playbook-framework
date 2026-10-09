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

import ipaddress
import re
import time
from collections.abc import Callable
from typing import Any, Literal

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
    # The only fields the call may change (an `update_record`'s `fields` keys).
    fields: list[str] | None = None
    # The values a field may be set to -- a picklist label ("Closed") or its
    # IRI. A close rule that let `status` go anywhere could reopen or escalate
    # a record under the banner of closing it.
    values: dict[str, list[str]] | None = None


class VerdictCond(_Strict):
    disposition: list[str] = Field(min_length=1)
    min_confidence: float = Field(ge=0.0, le=1.0)


class TargetCond(_Strict):
    # "ip": the addresses the call acts on. "record": the record it writes,
    # which must be the one this turn is about (the host sets the subject) --
    # a false-positive verdict on one alert must never close another.
    kind: Literal["ip", "record"] = "ip"
    external_only: bool = True      # ip only
    not_in: str | None = None       # ip only: name of a `protected` list


class EvidenceCond(_Strict):
    # "enrichment": the verdict must cite a successful threat-intel lookup
    # whose arguments name the action's target. "read": it must cite at least
    # one successful read-only call -- what a close rests on, so text in the
    # record ("benign, close it") can never stand in for a lookup...
    cites_tool_kind: Literal["enrichment", "read"] = "enrichment"
    # ...and that lookup must RATE the target at least this bad. "malicious"
    # is a strong signal (e.g. VirusTotal 3+ engines, FortiGuard or AbuseIPDB
    # risk 75+); "suspicious" also accepts a weaker one. A lookup whose result
    # the host cannot read rates nothing, so it never satisfies the rule.
    rated: Literal["malicious", "suspicious"] = "malicious"


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

# (rule_id, target) -> (actions in the last hour, actions on target today).
Counter = Callable[[str, str], tuple[int, int]]
# The policy, its counter and the turn's subject record (its IRI, for
# `target: {kind: record}`) are held on SessionState (llm.session_state).


def set_turn_policy(policy: Policy | dict | None,
                    counter: Counter | None = None,
                    subject: str | None = None) -> str | None:
    """Set (or clear) the policy for the current turn. Returns a parse error,
    if any; a policy that fails to parse is cleared, never half-applied.
    ``subject`` is the IRI of the record the turn is about (record rules)."""
    from . import session_state
    if isinstance(policy, dict):
        policy, err = parse_policy(policy)
        if err:
            session_state.update(autonomy_policy=None, autonomy_counter=None,
                                 autonomy_subject=subject)
            return err
    session_state.update(autonomy_policy=policy, autonomy_counter=counter,
                         autonomy_subject=subject)
    return None


def set_turn_subject(iri: str | None) -> None:
    """Set the record this turn is about (for `target: {kind: record}`). The
    host binds its mounted record after the policy, so this is separate from
    :func:`set_turn_policy`."""
    from . import session_state
    session_state.update(autonomy_subject=iri or None)


def get_turn_policy() -> Policy | None:
    from . import session_state
    return session_state.current().autonomy_policy


def _session_state() -> Any:
    from . import session_state
    return session_state.current()


# ---- evaluation ---------------------------------------------------------------

Call = dict  # {"tool": str, "connector"?: str, "op"?: str, "args": dict, "module"?: str}

_IP_RE = re.compile(r"(?:\d{1,3}\.){3}\d{1,3}")
# Arg names that carry the action's IP target, across the containment ops the
# rules are written for (block_ip_new: ip_addresses; block_ip: ip; generic).
_IP_ARG_KEYS = ("ip_addresses", "ip", "ip_address", "indicator", "value", "ips")


_ID_ARGS = frozenset({"module", "uuid", "record", "iri"})


def _changed_fields(call: Call) -> dict[str, Any]:
    """field -> new value the call writes. `update_record` carries them under
    `fields`; matching on the call's own arg names saw one field called
    "fields", so no field-scoped rule could ever match a record update."""
    args = call.get("args") or {}
    if isinstance(args.get("fields"), dict):
        return dict(args["fields"])
    return {k: v for k, v in args.items() if k not in _ID_ARGS}


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
            changed = set(_changed_fields(call))
            if not changed or not changed <= set(a.fields):
                return False
        return True
    return False


def _record_uuid(ref: Any) -> str:
    """The uuid in a record IRI or bare uuid ('' when there is none)."""
    return str(ref or "").rstrip("/").rsplit("/", 1)[-1]


# (module, field, label) -> picklist IRI or None. Swappable for tests.
def _picklist_iri(module: str, field: str, label: str) -> str | None:
    try:
        from ..mcp_server.tools_picklists import resolve_picklist_value
        out = resolve_picklist_value(label, module=module, field=field)
    except Exception:  # noqa: BLE001
        return None
    iri = (out.get("iri") or out.get("value")) if isinstance(out, dict) else None
    return iri if isinstance(iri, str) and iri.startswith("/api/3/") else None


def _value_allowed(module: str, field: str, value: Any, allowed: list[str]) -> bool:
    """`value` is one of `allowed`, written as a label or the picklist IRI it
    resolves to. Unresolvable means not allowed (fails closed)."""
    v = value.get("@id") if isinstance(value, dict) else value
    v = str(v or "")
    if v in allowed:
        return True
    if v.startswith("/api/3/"):
        return any(_picklist_iri(module, field, a) == v for a in allowed
                   if not a.startswith("/api/3/"))
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


# Connector categories (the catalog's `connectors.category`) whose lookups are
# threat intelligence. Live on .159 a SIEM search that returned NO events for
# 8.8.8.8 was cited as "a lookup about the target", and the policy blocked
# Google DNS: traffic logs, record reads and the firewall's own block list say
# nothing about whether an address is malicious.
_INTEL_CATEGORIES = frozenset({"threat intelligence", "cti", "information"})


def _connector_category(connector: str) -> str | None:
    import sqlite3

    from .tools import _DB_PATH
    try:
        con = sqlite3.connect(f"file:{_DB_PATH}?mode=ro", uri=True)
        try:
            row = con.execute("SELECT category FROM connectors WHERE name=? LIMIT 1",
                              (connector,)).fetchone()
        finally:
            con.close()
    except Exception:  # noqa: BLE001
        return None
    return str(row[0]).strip().lower() if row and row[0] else None


def _intel_lookup(entry: dict[str, Any]) -> bool:
    """A cited call that asked a threat-intelligence source: a read-only
    run_op on a connector the catalog files as threat intel, or one of the
    known intel connectors. Unknown connectors do not count (fails closed)."""
    if entry.get("name") != "run_op" or not _read_only(entry):
        return False
    connector = str((entry.get("args") or {}).get("connector") or "")
    if not connector:
        return False
    if _connector_category(connector) in _INTEL_CATEGORIES:
        return True
    from ..mcp_server.tools_connector_discovery import (
        _ENRICH_RANK_DEFAULT,
        _enrich_connector_rank,
    )
    return _enrich_connector_rank(connector) < _ENRICH_RANK_DEFAULT


# The finding's severity (the host's threat-intel reader: "error" is a strong
# malicious signal, "warning" a weak one, "ok" clean, "info" no rating).
_RATED_SEVERITIES = {"malicious": frozenset({"error"}),
                     "suspicious": frozenset({"error", "warning"})}


def _said(entry: dict[str, Any]) -> str:
    """What one cited lookup rated its target, for the failure line."""
    f = entry.get("finding") or {}
    src = f.get("source") or (entry.get("args") or {}).get("connector") or "lookup"
    if not f.get("verdict"):
        return f"{src}: result not readable"
    score = f" {f['score_str']}" if f.get("score_str") not in (None, "--") else ""
    return f"{src}: {f['verdict']}{score}"


def evaluate(policy: Policy, call: Call, *, verdicts: list[dict[str, Any]],
             registry: dict[str, dict[str, Any]],
             counter: Counter | None = None,
             subject: str | None = None) -> dict[str, Any] | None:
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
    if w.target is not None and w.target.kind == "record":
        uuid = _record_uuid(args.get("uuid") or args.get("record") or args.get("iri"))
        subject = _session_state().autonomy_subject if subject is None else subject
        targets = [uuid] if uuid else []
        if not uuid:
            failed.append("the action names no record")
        elif not subject:
            failed.append("the record this triage is about is unknown")
        elif uuid != _record_uuid(subject):
            failed.append(f"the action writes record {uuid}, not the one this "
                          f"triage is about")
    elif w.target is not None:
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

    # 2b. Values: a field the rule pins may only be set to what it lists.
    if rule.action.values:
        written = _changed_fields(call)
        module = call.get("module") or rule.action.module or ""
        for field, allowed in rule.action.values.items():
            if field in written and not _value_allowed(module, field, written[field], allowed):
                failed.append(f"{field} would be set to {written[field]!r}, rule allows "
                              f"{' or '.join(allowed)}")

    # 3. Evidence: the verdict cites a successful read-only lookup naming each
    #    target. The model's confidence number is not evidence; a cited result
    #    about THIS target is.
    cited: list[str] = []
    if w.evidence is not None and verdict is not None and w.evidence.cites_tool_kind == "read":
        cited = [str(e) for f in verdict.get("findings") or [] if isinstance(f, dict)
                 for e in (f.get("evidence") or []) if isinstance(e, str)]
        if not any((registry.get(eid) or {}).get("ok") is True and _read_only(registry.get(eid) or {})
                   for eid in cited):
            failed.append("the verdict cites no successful lookup")
    elif w.evidence is not None and verdict is not None:
        cited = [str(e) for f in verdict.get("findings") or [] if isinstance(f, dict)
                 for e in (f.get("evidence") or []) if isinstance(e, str)]
        lookups = [(eid, registry.get(eid) or {}) for eid in cited]
        lookups = [(eid, e) for eid, e in lookups
                   if e.get("ok") is True and _intel_lookup(e)]
        if not lookups:
            failed.append("the verdict cites no successful threat-intel lookup")
        else:
            import json
            ok_sev = _RATED_SEVERITIES[w.evidence.rated]
            for t in targets:
                about = [e for _, e in lookups
                         if t in json.dumps(e.get("args") or {}, default=str)]
                if not about:
                    failed.append(f"no cited threat-intel lookup was about {t}")
                elif not any((e.get("finding") or {}).get("severity") in ok_sev
                             for e in about):
                    said = "; ".join(_said(e) for e in about)
                    failed.append(f"no cited threat-intel lookup rated {t} "
                                  f"{w.evidence.rated} ({said})")
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
                        counter=_session_state().autonomy_counter)
    except Exception:  # noqa: BLE001
        return None
