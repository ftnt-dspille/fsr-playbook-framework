"""The probes themselves -- Phase 1 group A (write-through).

Each probe: seed a scratch playbook on the box, read ground truth, drive the
widget's exact payload, read ground truth again, and grade the DIFFERENCE.
No probe grades a card, a badge, or an `ok` flag.

Verdicts:
  PASS      the terminal effect is on the box
  FAIL      the affordance fired and the box did not change (or changed wrong)
  BLOCKED   the turn never produced the card under test -- the write path was
            never reached, so this run says nothing about the write. Named
            separately from FAIL because the cause is upstream (the model
            narrating the edit instead of carding it).
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


# A5 (the patch_proposal snippet-splice apply) was retired with the card in
# 2026-09: the model had stopped choosing it (BLOCKED every run), and A6 grades
# the same one-value edit through the path that replaced it.

NEW_IP = "203.0.113.99"


# ── A2 -- the enhancement_offer accept path ───────────────────────────

def probe_a2_enhancement_offer() -> Result:
    """An accepted `enhancement_offer` must reach the workflow record.

    Resumes through `_resume_enhancement_offer_accept` and the pre-write guard.
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
            return Result(rid, title, "BLOCKED",
                          "no enhancement_offer card -- delivery never "
                          "happened, so the write path is untested",
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
        card = drive.first_card(res, "enhancement_offer")
        if not card:
            return Result(rid, title, "BLOCKED",
                          "no enhancement_offer card -- the deletion was never "
                          "offered, so the guard is untested",
                          str(before), "", tools)

        reply = _reply(drive.accept_enhancement_offer(session, card, seeded["iri"]))
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


# ── A6 -- a value edit lands EXACTLY, whichever card carries it ─────────

def _block_ip_args(wf: dict | None) -> dict:
    st = scratch.step_by_name(wf, "Block IP")
    args = st.get("arguments") if isinstance(st, dict) else None
    return args if isinstance(args, dict) else {}


def probe_a6_value_edit_lands_exactly() -> Result:
    """"Change one value" must change that value and nothing else, on the box.

    The model's path is edit_playbook -> enhancement_offer; the probe grades
    only the effect. It exists because of a bug that path shipped: update_step
    with set={"params.ip_addresses": X} wrote a literal sibling key, verify
    passed it, and Accept would have "saved" with the old IP still in params.
    So besides the new value it checks the sibling params and that no junk
    key rode along.
    """
    rid, title = "A6", "a one-value edit lands exactly (any change card)"
    seeded, entity, coll = _seed("a6")
    try:
        was = _block_ip_args(seeded["workflow"])
        was_params = dict(was.get("params") or {})
        if "ip_addresses" not in was_params:
            return Result(rid, title, "BLOCKED",
                          "seed read-back has no params.ip_addresses on 'Block IP'",
                          str(was_params))
        session = drive.new_session("a6")
        res = drive.turn(
            f"In the step 'Block IP', change ip_addresses to {NEW_IP}. "
            "Change nothing else.", session=session, entity=entity)
        tools = drive.tool_names(res)
        card = drive.first_card(res, "enhancement_offer")
        if not card:
            return Result(rid, title, "BLOCKED", "no enhancement_offer card",
                          str(was_params), "", tools, _reply(res))
        reply = _reply(drive.accept_enhancement_offer(session, card, seeded["iri"]))
        after_wf = scratch.read_workflow(seeded["iri"])
        now = _block_ip_args(after_wf)
        now_params = dict(now.get("params") or {})
        want = {**was_params, "ip_addresses": NEW_IP}
        junk = sorted(k for k in now if "." in str(k))
        if str(now_params.get("ip_addresses")) != NEW_IP:
            return Result(rid, title, "FAIL",
                          f"Accept returned, ip_addresses is not {NEW_IP}"
                          + (f" (junk keys on the step: {junk})" if junk else ""),
                          str(was_params), str(now_params), tools, reply)
        if junk or now_params != want:
            return Result(rid, title, "FAIL",
                          f"the value landed but more changed: params "
                          f"{now_params} vs {want}; junk keys {junk}",
                          str(was_params), str(now_params), tools, reply)
        if scratch.step_names(after_wf) != scratch.step_names(seeded["workflow"]):
            return Result(rid, title, "FAIL", "the value landed but the step set changed",
                          str(was_params), str(now_params), tools, reply)
        return Result(rid, title, "PASS",
                      "only ip_addresses changed; no junk keys",
                      str(was_params), str(now_params), tools, reply)
    finally:
        scratch.purge(coll)


ALL = {
    "A2": probe_a2_enhancement_offer,
    "A3": probe_a3_delete_step,
    "A6": probe_a6_value_edit_lands_exactly,
}

# Phase 2 group T (triage write-through, #135) lives in triage.py; imported
# at the bottom so its `from probes.effect.probes import Result` works.
from probes.effect.triage import TRIAGE_PROBES  # noqa: E402

ALL.update(TRIAGE_PROBES)
