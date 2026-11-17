"""Who may run a tool call, decided in one place.

Every tool call the assistant makes goes through `authorize` before it runs:
dispatch for the model's calls, the agent loop when it splits a round at the
first call that will need approval, the batch collector, and the host's own
paths (an approved card, an autonomy rule that acts unattended, a playbook
calling a tool directly). Each of those used to apply its own rule -- the loop
and the batch collector hardcoded `tier >= 3` while dispatch honoured the
operator's read-only switch, so with that switch off a tier 1-2 call ran in the
parallel batch and its approval envelope came back as an ordinary tool result,
with no card.

The inputs, in the order they are applied:

1. The call's tier (`tools._resolve_tier`: the static table, run_op's
   per-operation category, the host's auto-run playbooks, MCP server tiers).
2. Someone already approved it (`approved_by`): a human on a card, the
   autonomy policy acting as `system:autonomy`, or a host path that runs on
   its own authority. Runs, and the audit row names who.
3. The approval floor (`FSR_AUTO_APPROVE_READONLY`): below it, runs.
4. A per-session grant ("once" / "always") for this tool or run_op operation.
5. The eval harness policy, when one is set.
6. Otherwise the call needs a card.

Who may *decide* a card (reviewer roles) is the host's check, made before it
calls back with `approved_by`; this module only knows that someone did.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from typing import Any, Literal

#: Actor for a human decision on a card.
HUMAN = "human"

Outcome = Literal["run", "card", "deny"]


@dataclass(frozen=True)
class Decision:
    outcome: Outcome
    tier: int
    #: The audit row's decision label: auto_allow | approved |
    #: auto_allow_grant | denied | pending.
    label: str
    #: Who allowed it, when someone did ("human", "system:autonomy", a grant,
    #: the eval policy). None for an auto-allowed or pending call.
    actor: str | None = None
    #: Why a denial was denied, in words the model can read.
    reason: str | None = None


# --- Read-only auto-approve (the approval floor) ---------------------------
#
#   FSR_AUTO_APPROVE_READONLY=1  (default) -- tier 1-2 auto-run, tier 3+ gated.
#   FSR_AUTO_APPROVE_READONLY=0            -- tier 1+ gated; only tier-0 local
#                                            tools auto-run.
_READONLY_AUTO_APPROVE_OVERRIDE: bool | None = None  # test/host override


def set_readonly_auto_approve(enabled: bool | None) -> None:
    """Programmatic override for the read-only auto-approve flag. `None`
    reverts to the env default."""
    global _READONLY_AUTO_APPROVE_OVERRIDE
    _READONLY_AUTO_APPROVE_OVERRIDE = enabled


def _readonly_auto_approve() -> bool:
    if _READONLY_AUTO_APPROVE_OVERRIDE is not None:
        return _READONLY_AUTO_APPROVE_OVERRIDE
    raw = os.environ.get("FSR_AUTO_APPROVE_READONLY")
    if raw is None:
        return True
    return raw.strip().lower() not in ("0", "false", "no", "off", "")


def _approval_floor() -> int:
    """Minimum tier that requires human approval."""
    return 3 if _readonly_auto_approve() else 1


def needs_approval(tier: int) -> bool:
    """Whether a call of this tier stops for a card (before grants and the
    eval policy). The loop and the batch collector split rounds on this."""
    return int(tier) >= _approval_floor()


# --- Eval harness policy ----------------------------------------------------
#
#   "suspend" (default)  -- production: a card.
#   "approve-all"        -- auto-approve every gated call.
#   "deny-tier-3+"       -- deny every gated call.
#   "auto-approve-tier:N" -- approve iff tier <= N, else deny.
_EVAL_POLICY_OVERRIDE: str | None = None


def set_eval_policy(policy: str | None) -> None:
    global _EVAL_POLICY_OVERRIDE
    _EVAL_POLICY_OVERRIDE = policy or None


def _active_eval_policy() -> str | None:
    if _EVAL_POLICY_OVERRIDE:
        return _EVAL_POLICY_OVERRIDE
    return os.environ.get("EVAL_APPROVAL_POLICY") or None


def _apply_eval_policy(policy: str, tier: int) -> str:
    """'approve' | 'deny' | 'suspend' for a policy and tier. Anything unknown
    suspends, so production behavior is the safe default."""
    p = policy.strip().lower()
    if p in ("approve-all", "approve"):
        return "approve"
    if p in ("deny-tier-3+", "deny"):
        return "deny"
    if p.startswith("auto-approve-tier:"):
        try:
            cap = int(p.split(":", 1)[1].split(",")[-1].strip())
            return "approve" if tier <= cap else "deny"
        except (ValueError, IndexError):
            return "suspend"
    return "suspend"


# --- Per-session grants -----------------------------------------------------
#
# Key: (session_id, tool_name, op_key); op_key is f"{connector}:{operation}"
# for run_op, else None. Value: "once" (consumed by the next match) or
# "always" (until the session ends). In memory only.
_APPROVAL_GRANTS: dict[tuple[str, str, str | None], str] = {}


def grant_tool_approval(
    session_id: str, tool_name: str, *, op_key: str | None = None, mode: str = "once"
) -> None:
    """Grant approval for a tool (or one run_op operation) in a session."""
    if mode not in ("once", "always"):
        raise ValueError(f"Invalid grant mode {mode!r}; must be 'once' or 'always'")
    _APPROVAL_GRANTS[(session_id, tool_name, op_key)] = mode


def _consume_grant(session_id: str, tool_name: str, op_key: str | None = None) -> bool:
    """True when a grant matches (a "once" grant is used up)."""
    key = (session_id, tool_name, op_key)
    mode = _APPROVAL_GRANTS.get(key)
    if mode is None:
        return False
    if mode == "once":
        del _APPROVAL_GRANTS[key]
    return True


def clear_session_grants(session_id: str) -> None:
    """Drop every grant for a session (session end / logout)."""
    for k in [k for k in _APPROVAL_GRANTS if k[0] == session_id]:
        del _APPROVAL_GRANTS[k]


def _op_key(name: str, args: dict[str, Any]) -> str | None:
    if name != "run_op":
        return None
    connector = (args or {}).get("connector") or ""
    op = (args or {}).get("op") or ""
    return f"{connector}:{op}" if connector and op else None


# --- Audit -----------------------------------------------------------------
#
# Per-process. Every authorized, carded or denied call appends one row.
AUDIT_LOG: list[dict[str, Any]] = []


def args_digest(name: str, args: dict[str, Any] | None) -> str:
    """SHA-256 of the call's canonical serialization. The approval token binds
    the full digest (a tamper check); logs and envelopes carry `_args_hash`."""
    payload = json.dumps({"tool": name, "args": args or {}}, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _args_hash(name: str, args: dict[str, Any]) -> str:
    return args_digest(name, args)[:16]


def record_audit(name: str, args: dict[str, Any], tier: int, decision: str, *,
                 result_preview: Any = None, actor: str | None = None) -> None:
    AUDIT_LOG.append({
        "ts": time.time(),
        "tool": name,
        "tier": tier,
        "args_hash": _args_hash(name, args),
        "decision": decision,
        "actor": actor,
        "result_preview": result_preview,
    })


def clear_audit_log() -> None:
    """Per-task reset for the eval harness."""
    AUDIT_LOG.clear()


def snapshot_audit_log() -> list[dict[str, Any]]:
    return [dict(r) for r in AUDIT_LOG]


# --- The decision -----------------------------------------------------------

def tier_of(name: str, args: dict[str, Any]) -> int:
    from .tools import _resolve_tier
    return _resolve_tier(name, args or {})


def authorize(name: str, args: dict[str, Any], *, approved_by: str | None = None,
              session_id: str | None = None, tier: int | None = None) -> Decision:
    """Decide whether `name(args)` runs now, needs a card, or is denied.

    A matching "once" grant is consumed when it decides the call, so call this
    once per call, right before running it. `tier` skips re-resolving when the
    caller already has it.
    """
    t = tier_of(name, args) if tier is None else int(tier)
    if approved_by:
        return Decision("run", t, "approved", actor=approved_by)
    if not needs_approval(t):
        return Decision("run", t, "auto_allow")
    if session_id and _consume_grant(session_id, name, _op_key(name, args)):
        return Decision("run", t, "auto_allow_grant", actor=f"grant:{session_id}")
    policy = _active_eval_policy()
    verdict = _apply_eval_policy(policy, t) if policy else "suspend"
    if verdict == "approve":
        return Decision("run", t, "approved", actor=f"eval:{policy}")
    if verdict == "deny":
        return Decision("deny", t, "denied", actor=f"eval:{policy}",
                        reason=f"Eval policy '{policy}' denied tier-{t} action.")
    return Decision("card", t, "pending")
