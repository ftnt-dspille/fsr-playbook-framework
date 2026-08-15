"""The probes themselves -- Phase 1 group A (write-through).

Each probe: seed a scratch playbook on the box, read ground truth, drive the
widget's exact payload, read ground truth again, and grade the DIFFERENCE.
No probe grades a card, a badge, or an `ok` flag.

Verdicts:
  PASS      the terminal effect is on the box
  FAIL      the affordance fired and the box did not change (or changed wrong)
  BLOCKED   the turn never produced the card under test -- the write path was
            never reached, so this run says nothing about the write. Named
            separately from FAIL because the cause is upstream (usually #132,
            the model narrating instead of calling emit_patch_proposal).
  ENV-SKIP  the box/connector is unreachable -- not a product signal
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT / "tooling") not in sys.path:
    sys.path.insert(0, str(ROOT / "tooling"))

from probes.effect import drive, scratch  # noqa: E402


@dataclass
class Result:
    id: str
    title: str
    verdict: str
    detail: str
    before: str = ""
    after: str = ""
    tools: list[str] = field(default_factory=list)
    # What the resume ITSELF said. A write that did not land and a resume that
    # refused are different defects, and a probe that reports only the box diff
    # cannot tell them apart -- that ambiguity is how `ok: True` on a refused
    # save survived two sessions.
    reply: str = ""


def _reply(res: dict | None) -> str:
    """One line of the resume's own account of itself."""
    if not isinstance(res, dict):
        return f"resume returned {res!r:.120}"
    bits = [f"ok={res.get('ok')}", f"stop={res.get('stop_reason')}"]
    if res.get("error"):
        bits.append(f"error={str(res['error'])[:200]}")
    text = drive.final_text(res)
    if text:
        bits.append(f"said={text[:900]!r}")
    return " ".join(bits)


def _yaml(collection: str, playbook: str) -> str:
    """One shared scratch playbook: a value to edit, a step to delete, and
    neighbours whose survival proves the edit was surgical."""
    return f"""collection: "{collection}"
playbooks:
- name: {playbook}
  is_active: false
  trigger_step_id: start
  steps:
  - type: start
    name: Start
    module: alerts
    button_label: Effect Probe
    next: Enrich IP
  - type: connector
    name: Enrich IP
    connector: cyops_utilities
    operation: no_op
    params: {{}}
    next: Block IP
  - type: connector
    name: Block IP
    connector: fortigate-firewall
    operation: block_ip
    params:
      method: Quarantine Based
      ip_addresses: 198.51.100.10
    next: Dead End
  - type: connector
    name: Dead End
    connector: cyops_utilities
    operation: no_op
    params: {{}}
    next: End
  - type: connector
    name: End
    connector: cyops_utilities
    operation: no_op
    params: {{}}
"""


def _seed(slug: str):
    coll = f"{scratch.COLLECTION_PREFIX}{slug}"
    pb = f"{scratch.WORKFLOW_PREFIX}{slug}"
    seeded = scratch.seed(coll, _yaml(coll, pb))
    entity = drive.open_playbook_entity(
        seeded["iri"], seeded["uuid"], pb, seeded["yaml"])
    return seeded, entity, coll


# ── A5 -- the snippet-splice apply path ───────────────────────────────

NEW_IP = "203.0.113.99"


def probe_a5_snippet_apply() -> Result:
    """A value-level edit applied through `patch_proposal` -> `apply_patch`.

    The documented NORMAL case: the card's `after_yaml` is a minimal SNIPPET,
    spliced into the stored playbook by `_splice_patch_snippet`. Only
    `apply_mode: whole_doc` was ever live-validated, so this branch has shipped
    with zero live coverage over a normal write path -- the reason it is first.
    """
    rid, title = "A5", "snippet-splice apply writes the edited arg"
    seeded, entity, coll = _seed("a5")
    try:
        before = scratch.step_arg(seeded["workflow"], "Block IP", "ip_addresses")
        if before is None:
            return Result(rid, title, "BLOCKED",
                          "seed read-back has no ip_addresses arg on 'Block IP' -- "
                          "the probe cannot tell a write from a miss", str(before))

        session = drive.new_session("a5")
        res = drive.turn(
            f"In the step 'Block IP', change ip_addresses to {NEW_IP}. "
            "Change nothing else.",
            session=session, entity=entity)
        tools = drive.tool_names(res)
        card = drive.first_card(res, "patch_proposal")
        if not card:
            other = ("enhancement_offer" if drive.first_card(res, "enhancement_offer")
                     else "none")
            return Result(rid, title, "BLOCKED",
                          f"no patch_proposal card (other card: {other}); the "
                          "splice path was never reached -- see #132",
                          str(before), "", tools)

        reply = _reply(drive.accept_patch_proposal(session, card, seeded["iri"]))
        after_wf = scratch.read_workflow(seeded["iri"])
        after = scratch.step_arg(after_wf, "Block IP", "ip_addresses")
        names_before = scratch.step_names(seeded["workflow"])
        names_after = scratch.step_names(after_wf)

        if after is None or NEW_IP not in str(after):
            return Result(rid, title, "FAIL",
                          "Apply returned, the box still holds the OLD value",
                          str(before), str(after), tools, reply)
        if names_after != names_before:
            return Result(rid, title, "FAIL",
                          "the value landed but the step set changed: "
                          f"{names_before} -> {names_after}",
                          str(before), str(after), tools, reply)
        return Result(rid, title, "PASS", "edited arg is on the box, steps intact",
                      str(before), str(after), tools, reply)
    finally:
        scratch.purge(coll)


# ── A2 -- the enhancement_offer accept path ───────────────────────────

def probe_a2_enhancement_offer() -> Result:
    """An accepted `enhancement_offer` must reach the workflow record.

    The enhance twin of the apply_patch bug: a different resume branch
    (`_resume_enhancement_offer_accept`) over the same pre-write guard.
    """
    rid, title = "A2", "accepted enhancement_offer writes the new step"
    seeded, entity, coll = _seed("a2")
    try:
        before = scratch.step_names(seeded["workflow"])
        session = drive.new_session("a2")
        res = drive.turn(
            "Add a set-variable step named 'Stamp Verdict' right after 'Enrich IP' "
            "that sets verdict to malicious. Keep every other step.",
            session=session, entity=entity)
        tools = drive.tool_names(res)
        card = drive.first_card(res, "enhancement_offer")
        if not card:
            other = ("patch_proposal" if drive.first_card(res, "patch_proposal")
                     else "none")
            return Result(rid, title, "BLOCKED",
                          f"no enhancement_offer card (other card: {other}) -- "
                          "delivery never happened, so the write path is untested",
                          str(before), "", tools)

        reply = _reply(drive.accept_enhancement_offer(session, card, seeded["iri"]))
        after_wf = scratch.read_workflow(seeded["iri"])
        after = scratch.step_names(after_wf)

        if len(after) <= len(before):
            return Result(rid, title, "FAIL",
                          "accept returned, the box gained no step",
                          str(before), str(after), tools, reply)
        missing = [n for n in before if n not in after]
        if missing:
            return Result(rid, title, "FAIL",
                          f"a step was added but these were LOST: {missing}",
                          str(before), str(after), tools, reply)
        return Result(rid, title, "PASS", "new step on the box, originals intact",
                      str(before), str(after), tools, reply)
    finally:
        scratch.purge(coll)


# ── A3 -- the guard's inverse: a legitimate deletion still passes ─────

def probe_a3_delete_step() -> Result:
    """Deleting a step must still be possible.

    `_rename_only_drops` made deletions harder on purpose (a rename reads, by
    path alone, as a deletion). A guard is only correct if the legitimate
    operation it constrains still goes through -- otherwise the fix for the
    rename bug is a new bug with better manners.
    """
    rid, title = "A3", "a legitimate step deletion is not blocked by the guard"
    seeded, entity, coll = _seed("a3")
    try:
        before = scratch.step_names(seeded["workflow"])
        if "Dead End" not in before:
            return Result(rid, title, "BLOCKED",
                          "seed has no 'Dead End' step to delete", str(before))
        session = drive.new_session("a3")
        res = drive.turn(
            "Delete the step named 'Dead End' and wire 'Block IP' straight to "
            "'End'. Change nothing else.",
            session=session, entity=entity)
        tools = drive.tool_names(res)
        card = (drive.first_card(res, "patch_proposal")
                or drive.first_card(res, "enhancement_offer"))
        if not card:
            return Result(rid, title, "BLOCKED",
                          "no patch_proposal or enhancement_offer card -- the "
                          "deletion was never offered, so the guard is untested",
                          str(before), "", tools)

        if card.get("type") == "patch_proposal":
            reply = _reply(drive.accept_patch_proposal(session, card, seeded["iri"]))
        else:
            reply = _reply(drive.accept_enhancement_offer(session, card, seeded["iri"]))
        reply = f"via {card.get('type')}; {reply}"
        after_wf = scratch.read_workflow(seeded["iri"])
        after = scratch.step_names(after_wf)

        if "Dead End" in after:
            return Result(rid, title, "FAIL",
                          "the deletion was accepted and the step is still on the box",
                          str(before), str(after), tools, reply)
        lost = [n for n in before if n not in after and n != "Dead End"]
        if lost:
            return Result(rid, title, "FAIL",
                          f"the deletion took other steps with it: {lost}",
                          str(before), str(after), tools, reply)
        return Result(rid, title, "PASS", "only the named step is gone",
                      str(before), str(after), tools, reply)
    finally:
        scratch.purge(coll)


ALL = {
    "A5": probe_a5_snippet_apply,
    "A2": probe_a2_enhancement_offer,
    "A3": probe_a3_delete_step,
}
