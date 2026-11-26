"""NOC scaffolding: typed checks that keep a weak model on the by=diff data layer.

``fmg_device by=diff`` already returns the right facts (the newest configuration
objects and the install task they are tied to). A weak model still, live:

  1. stops at ``by=changes`` / ``by=status`` and never reads the content,
  2. does not name the install task the diff attributes the change to,
  3. calls a blackhole route that drops the very traffic asked about "benign",
  4. identifies the offending route and stages no fix.

Every check here reads TYPED facts off tool results (the ``by`` argument, a
route's ``blackhole`` flag, a task id, an address shape), never the model's or
the analyst's prose for meaning, and every one is bounded so it cannot loop:
the model-facing holds spend ``NOC_NUDGE_CAP`` per turn, the benign guard
refuses once and then caps the disposition itself.

Model-agnostic: a model that already read the diff, cited the task and did not
call a blackhole benign meets none of this.
"""
from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass, field
from typing import Any

#: Holds (a reply sent back, a verdict refused) per turn, over all kinds.
NOC_NUDGE_CAP = 3
#: A blackhole route counts as "what the install added" when it is among this
#: many newest items of its section (`by=diff` sorts newest first).
NEWEST_ITEMS = 3

_DIFF_TOOLS = {"fmg_device", "fmg_get_device_diff", "fmg_get_device_changes",
               "fmg_get_device_status"}
_BENIGN = frozenset({"benign", "false_positive"})
_NET = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?:/\d{1,2})?(?![\d])")


def _by(tool_name: str, args: dict[str, Any] | None) -> str:
    if tool_name == "fmg_get_device_diff":
        return "diff"
    if tool_name == "fmg_get_device_changes":
        return "changes"
    if tool_name == "fmg_get_device_status":
        return "status"
    return str((args or {}).get("by") or "").lower().strip()


def addresses_in(text: Any) -> list[str]:
    """IPv4 addresses and CIDR blocks in a text, by shape. Order kept, unique."""
    out: list[str] = []
    for tok in _NET.findall(str(text or "")):
        try:
            ipaddress.ip_network(tok, strict=False)
        except ValueError:
            continue
        if tok not in out:
            out.append(tok)
    return out[:12]


def _overlaps(dst: str, nets: list[str]) -> bool:
    try:
        d = ipaddress.ip_network(dst, strict=False)
    except ValueError:
        return False
    for n in nets:
        try:
            if d.overlaps(ipaddress.ip_network(n, strict=False)):
                return True
        except ValueError:
            continue
    return False


def _has_outofsync(node: Any, depth: int = 0) -> bool:
    if depth > 3:
        return False
    if isinstance(node, dict):
        if str(node.get("conf_status") or "").lower() == "outofsync":
            return True
        return any(_has_outofsync(v, depth + 1) for v in node.values())
    if isinstance(node, list):
        return any(_has_outofsync(v, depth + 1) for v in node[:10])
    return False


def noc_facts(tool_name: str, args: dict[str, Any] | None,
              result: Any) -> dict[str, Any] | None:
    """The typed fact a FortiManager device read left, or None. Stored in the
    turn registry next to the call."""
    if tool_name not in _DIFF_TOOLS or not isinstance(result, dict):
        return None
    if result.get("ok") is False or result.get("error"):
        return None
    by = _by(tool_name, args)
    q = result.get("query")
    echo: dict[str, Any] = q if isinstance(q, dict) else {}
    device = str((args or {}).get("device") or echo.get("device") or "")
    adom = str((args or {}).get("adom") or echo.get("adom") or "root")
    if not device:
        return None
    if by == "diff":
        last = result.get("last_install")
        last = last if isinstance(last, dict) else {}
        bad: list[dict[str, Any]] = []
        for sec in result.get("sections") or []:
            if not isinstance(sec, dict) or sec.get("kind") != "static_routes":
                continue
            for it in (sec.get("items") or [])[:NEWEST_ITEMS]:
                if not isinstance(it, dict):
                    continue
                if (str(it.get("blackhole")) == "enable"
                        and str(it.get("status") or "enable") != "disable"
                        and it.get("seq") is not None and it.get("dst")):
                    bad.append({"vdom": sec.get("vdom") or "root",
                                "seq": it.get("seq"), "dst": str(it.get("dst")),
                                "oid": it.get("oid"),
                                "comment": it.get("comment")})
        fact: dict[str, Any] = {"kind": "diff", "device": device, "adom": adom,
                                "bad": bad}
        if last.get("task_id") is not None:
            fact["task_id"] = last.get("task_id")
            fact["install"] = {k: last.get(k) for k in ("state", "user", "finished")
                               if last.get(k) is not None}
        return fact
    if by == "changes":
        installs = [c for c in result.get("changes") or []
                    if isinstance(c, dict) and c.get("kind") == "install"]
        if not installs:
            return {"kind": "changes", "device": device, "adom": adom,
                    "content_unread": False}
        return {"kind": "changes", "device": device, "adom": adom,
                "content_unread": True, "task_id": installs[0].get("task_id")}
    if by == "status":
        return {"kind": "status", "device": device, "adom": adom,
                "content_unread": _has_outofsync(result)}
    return None


def _facts(evidence: Any) -> list[tuple[str, dict[str, Any]]]:
    out = []
    for cid, e in evidence.valid_ids().items():
        f = (e or {}).get("noc")
        if isinstance(f, dict):
            out.append((cid, f))
    return out


def _diff_read(facts: list[tuple[str, dict[str, Any]]]) -> set[str]:
    return {f["device"].lower() for _, f in facts if f.get("kind") == "diff"}


def unread_devices(evidence: Any) -> list[str]:
    """Devices whose install history or sync state was read but whose
    configuration content never was: the case where by=diff is the next step."""
    facts = _facts(evidence)
    read = _diff_read(facts)
    seen: list[str] = []
    for _, f in facts:
        if (f.get("kind") in ("changes", "status") and f.get("content_unread")
                and f["device"].lower() not in read and f["device"] not in seen):
            seen.append(f["device"])
    return seen


def _diff_fact(evidence: Any) -> tuple[str, dict[str, Any]] | None:
    """The newest by=diff fact this turn."""
    found = [(c, f) for c, f in _facts(evidence) if f.get("kind") == "diff"]
    return found[-1] if found else None


def _unread_directive(devices: list[str]) -> str:
    return ("fmg_device by=changes (or by=status) says that an install ran or the "
            "device is out of sync, but it does not say what changed. Call "
            "fmg_device by=diff for " + ", ".join(devices) + " now: it lists the "
            "newest configuration objects (routes, interfaces) and the install "
            "task they belong to. Answer from that, and name the task id.")


def noc_hold(evidence: Any, reply_text: str = "", staged: bool = False) -> str:
    """The reason a turn that is about to end must go on, or "": the content of
    a device the turn only read the history of was never read, or the diff
    named an install task the reply (no verdict delivered, nothing staged)
    leaves out.
    Counts the hold, so each call that returns text spends one."""
    from ._citation_validator import TurnEvidence  # noqa: PLC0415
    if not isinstance(evidence, TurnEvidence) or evidence.noc_nudges() >= NOC_NUDGE_CAP:
        return ""
    devices = unread_devices(evidence)
    if devices:
        evidence.note_noc_nudge()
        return _unread_directive(devices)
    d = _diff_fact(evidence)
    if d is not None and not staged and not evidence.verdicts() and d[1].get("task_id") is not None:
        tid = str(d[1]["task_id"])
        if tid not in str(reply_text or "") and (reply_text or "").strip():
            evidence.note_noc_nudge()
            return (f"The diff ties this device's configuration to install task "
                    f"{tid}. Say so in your answer: name task {tid} as the install "
                    "the change came from.")
    return ""


@dataclass
class VerdictReview:
    """What the NOC checks decided about a verdict about to be delivered."""
    refusal: tuple[str, str] | None = None
    disposition: str | None = None
    severity: str | None = None
    summary: str | None = None
    findings: list[Any] | None = None
    unknowns: list[str] = field(default_factory=list)
    fired: list[str] = field(default_factory=list)


def _claims_text(summary: str, findings: list[Any]) -> str:
    parts = [summary or ""]
    for f in findings or []:
        if isinstance(f, dict):
            parts.append(str(f.get("claim") or ""))
    return " ".join(parts)


def review_verdict(evidence: Any, disposition: str, severity: str, summary: str,
                   findings: list[Any], cited: list[str],
                   summary_max: int = 600) -> VerdictReview:
    """The NOC checks on a verdict that passed shape and citation validation.

    1. content unread: refuse (shares the hold cap) until by=diff was read.
    2. benign over a blackhole: refuse once; after that the disposition is capped
       to ``suspicious`` here, so a model that repeats itself cannot ship it.
    3. the install task the diff attributes the change to is named in the card.
    """
    rev = VerdictReview(disposition=disposition, severity=severity, summary=summary,
                        findings=list(findings))
    facts = _facts(evidence)
    if not facts:
        return rev
    registry = evidence.valid_ids()
    cited_noc = [f for c, f in facts if c in cited]
    devices = unread_devices(evidence)
    if devices and evidence.noc_nudges() < NOC_NUDGE_CAP:
        evidence.note_noc_nudge()
        rev.refusal = ("diff_not_read", _unread_directive(devices))
        return rev
    d = _diff_fact(evidence)
    if d is None:
        return rev
    diff_id, diff = d
    # (2) benign while a blackhole the install added drops what was asked about.
    if disposition in _BENIGN and diff.get("bad"):
        text = _claims_text(summary, findings)
        nets = list(evidence.ask_nets) + addresses_in(text)
        for e in registry.values():
            nets += addresses_in((e or {}).get("args"))
        hits = [b for b in diff["bad"] if _overlaps(str(b["dst"]), nets)]
        first = evidence.blackhole_refusals() == 0
        if hits or first:
            blk = (hits or diff["bad"])[0]
            fact = (f"the route to {blk['dst']} (sequence {blk['seq']}) is a "
                    "blackhole: it silently DROPS that traffic")
            if first:
                evidence.note_blackhole_refusal()
                rev.fired.append("noc.benign_over_blackhole")
                rev.refusal = (
                    "benign_over_blackhole",
                    "A blackhole route among the newest configuration objects "
                    f"({fact}). A change that drops traffic is not benign when "
                    "the question is why traffic fails or what the install "
                    "changed. Name the route as the cause (suspicious or "
                    "true_positive, medium severity or higher), cite this "
                    "diff, and say what removing it would restore.")
                return rev
            rev.disposition = "suspicious"
            if severity in ("low", "info"):
                rev.severity = "medium"
            note = (f"disposition held at suspicious: {fact}, so it cannot be "
                    "called benign")
            rev.unknowns.append(note)
            rev.summary = (summary.rstrip() + " (Held from benign: " + fact
                           + ".)")[:summary_max]
            rev.fired.append("noc.benign_capped")
    # (3) the install task the diff attributes the change to is named.
    tid = diff.get("task_id")
    if tid is not None and (diff_id in cited or cited_noc):
        text = _claims_text(rev.summary or summary, findings)
        if not re.search(rf"(?<!\d){re.escape(str(tid))}(?!\d)", text):
            inst = diff.get("install") or {}
            by = (f", by {inst['user']}" if inst.get("user") else "")
            claim = (f"FortiManager install task {tid} ({inst.get('state', 'done')}"
                     f"{by}) is the install this device's configuration is tied to")
            bad = diff.get("bad") or []
            if bad:
                claim += (f"; it carries the blackhole route to {bad[0]['dst']} "
                          f"(sequence {bad[0]['seq']})")
            rev.findings = list(rev.findings or []) + [
                {"claim": claim, "evidence": [diff_id]}]
            rev.fired.append("noc.install_task_attached")
    return rev


# ---------------------------------------------------------------------------
# Fix: the approval card for the offending item
# ---------------------------------------------------------------------------
def remediation_payload(evidence: Any) -> dict[str, Any] | None:
    """The action card that removes the offending static route the turn's
    by=diff read found, or None. The card is staged for approval (tier 3): it
    changes FortiManager's device database; installing is a separate approval."""
    from ._citation_validator import TurnEvidence  # noqa: PLC0415
    if not isinstance(evidence, TurnEvidence):
        return None
    d = _diff_fact(evidence)
    if d is None or not d[1].get("bad"):
        return None
    diff = d[1]
    blk = diff["bad"][0]
    from .tools_noc import _FMG_CONNECTOR  # noqa: PLC0415
    url = (f"/pm/config/device/{diff['device']}/vdom/{blk['vdom']}"
           f"/router/static/{blk['seq']}")
    return {
        "connector": _FMG_CONNECTOR,
        "operation": "json_rpc_delete",
        "args": {"url": url},
        "editable_fields": [],
        "summary": (f"Remove the blackhole static route to {blk['dst']} "
                    f"(sequence {blk['seq']}) from {diff['device']} in "
                    "FortiManager. Installing the package afterwards applies "
                    "it to the device."),
    }
