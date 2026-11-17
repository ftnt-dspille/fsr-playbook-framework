"""Guard-fire telemetry: the one list of every mechanism that steers a turn.

A guard, redirect, refusal, forced wrap-up or cap is a compensation for the
model (or the tool contract) getting something wrong. Whether each one still
earns its keep is an empirical question, and the transcript only answers it
if every one of them leaves the same trace. This module is that trace:

* `MECHANISMS` -- the registry. A mechanism name is stable (it is read from
  stored transcripts, `tags.guards_fired`, by `harness.frames.guards_fired`),
  and a site may only record a name that is registered here.
* `record_guard_fire(name)` -- note that `name` fired this turn.
* `refusal(name, payload)` -- record and hand the payload back, so a refusal
  site is `return refusal("dispatch.x", {...})` and cannot forget the record.

Process-local and best-effort, mirroring the HITL audit log
(`tools.clear_audit_log` / `snapshot_audit_log`): the turn driver clears before
a turn and snapshots after. Recording never affects control flow.

`tests/test_guard_sites_are_recorded.py` is the closure over this registry: a
guard site added without going through it fails there.

Names. The eleven that predate the registry keep the names they were already
recorded under (class names), so stored transcripts still read. New names are
`<family>.<what>`: `dispatch.` (the loop's dispatch wrapper), `triage.`
(TriageDiscipline), `tools.` (the dispatch stages in tools.py, incl. the turn
plan's gate), `turn.` (loop-level forced wrap-ups, caps and loop-run actions).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# What a mechanism is, for readers that group them.
ROUND_END = "round_end"          # nudge / forced delivery at the end of a round
STALL = "stall"                  # no-progress detector
TRIAGE_REDIRECT = "triage_redirect"
DISPATCH_REFUSAL = "dispatch_refusal"
FORCED_WRAPUP = "forced_wrapup"
CAP = "cap"
LOOP_ACTION = "loop_action"      # the loop acts in the model's place


@dataclass(frozen=True)
class Mechanism:
    name: str
    kind: str
    where: str


def _m(name: str, kind: str, where: str) -> tuple[str, Mechanism]:
    return name, Mechanism(name, kind, where)


MECHANISMS: dict[str, Mechanism] = dict([
    # -- round-end guards (_loop_helpers classes). Names predate the registry.
    _m("EnhanceDeliveryGuard", ROUND_END, "loop delivers the verified enhancement offer"),
    _m("EnhanceDeliveryGuard.failed_edit", ROUND_END, "last edit still has required fixes"),
    _m("CreateDeliveryGuard", ROUND_END, "loop delivers the verified playbook offer"),
    _m("BuildProgressGuard", ROUND_END, "researched, never drafted"),
    _m("BuildProgressGuard.incomplete", ROUND_END, "incomplete-draft notice shown"),
    _m("BuildProgressGuard.unverified_draft", ROUND_END, "draft left unverified"),
    _m("VerdictDeliveryGuard", ROUND_END, "triage gathered evidence, never concluded"),
    _m("ContainmentFollowThrough", ROUND_END, "unattended true positive, nothing staged"),
    _m("PromisedActionGuard", ROUND_END, "model wrote a fabricated call marker"),
    # -- stall detectors (ProgressMeter). The wrap-up they force is the same event.
    _m("ProgressMeter.flail", STALL, "rounds that only fail"),
    # -- dispatch refusals in the loop's guarded_dispatch
    _m("dispatch.bad_tool_arguments", DISPATCH_REFUSAL, "arguments were not a JSON object"),
    _m("dispatch.not_in_slice", DISPATCH_REFUSAL, "tool not advertised this turn"),
    _m("dispatch.answer_scope", DISPATCH_REFUSAL, "answer-scope turn past its lookup cap"),
    # -- triage discipline redirects (TriageDiscipline)
    _m("triage.duplicate_search", TRIAGE_REDIRECT, "same module search already run"),
    _m("triage.hunt_floor", TRIAGE_REDIRECT, "containment before the investigation floor"),
    # -- dispatch stages in tools.py and the turn plan's gate
    _m("tools.reserved_key_rejected", DISPATCH_REFUSAL, "wire-supplied _approved"),
    _m("tools.read_only_turn", DISPATCH_REFUSAL, "write frontier on a read-only turn"),
    _m("tools.not_a_playbook_tool", DISPATCH_REFUSAL, "triage tool on a playbook turn"),
    _m("tools.state_unresolved", DISPATCH_REFUSAL, "turn plan could not be derived"),
    _m("tools.not_afforded", DISPATCH_REFUSAL, "open-playbook frontier / create-new"),
    _m("tools.answer_scope", DISPATCH_REFUSAL, "hunt, write or verdict on a narrow question"),
    _m("tools.invalid_tool_args", DISPATCH_REFUSAL, "argument gate or cross-field rule"),
    # -- loop-level forced wrap-ups, caps, loop-run actions
    _m("turn.self_repair", LOOP_ACTION, "last yaml fence failed its checks; one repair round"),
    _m("turn.fence_neutralised", LOOP_ACTION, "a failing fence replaced by a note"),
    _m("turn.terminal_fence_verified", LOOP_ACTION, "loop verifies a clean unverified fence"),
    _m("turn.forced_containment", LOOP_ACTION, "loop forces the policy-defined block card"),
    _m("turn.max_tool_turns", CAP, "tool-round budget spent; forced wrap-up"),
    _m("turn.answer_scope_wrapup", LOOP_ACTION, "narrow question ended without text; one answer round"),
    _m("turn.budget_ask", CAP, "tool-round budget spent; continue-or-stop card"),
    # Connector-side offer salvage lives in the connector's own registry
    # (connector-fsr-agentic-assistant/ops_offers.py) and rides the same list.
])

#: A process-long caller (an MCP server dispatching tools with no turn driver
#: to clear the list) must not grow it without bound.
_MAX_FIRES = 500

_GUARD_FIRES: list[str] = []


def record_guard_fire(guard: str) -> None:
    """Note that `guard` (a registered mechanism name) fired this turn."""
    if len(_GUARD_FIRES) < _MAX_FIRES:
        _GUARD_FIRES.append(guard)


def refusal(guard: str, payload: Any) -> Any:
    """Record `guard` and return `payload` unchanged: the one-line form for a
    site that returns a refusal or redirect envelope."""
    record_guard_fire(guard)
    return payload


def snapshot_guard_fires() -> list[str]:
    """Mechanisms that fired since the last clear, in order."""
    return list(_GUARD_FIRES)


def clear_guard_fires() -> None:
    _GUARD_FIRES.clear()
