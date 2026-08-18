"""Phase 2 group T (triage write-through) -- #135.

Phase 1 proved the BUILD/ENHANCE writes (A2/A3/A5: does an accepted card
change the playbook?). These prove the TRIAGE writes: an approved containment
must land on the enforcement point, and an approved record-write must land on
the record. Both are the #130 arc, formalized from a hand-driven proof into a
repeatable probe.

Same doctrine as group A: every verdict is a box read, never a card or an
`ok` flag. The "box" differs per probe -- T1's ground truth is the FIREWALL's
own block/quarantine list, T2's is the record row re-read via crudhub.

Each probe seeds its own scratch ALERT (the record-not-the-capability lesson:
a live triage turn with nothing to ground on never reaches its card) and
deletes it afterwards. T1 additionally un-blocks its TEST-NET address from
the firewall, best-effort, so reruns start clean.
"""
from __future__ import annotations

import json
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT / "tooling") not in sys.path:
    sys.path.insert(0, str(ROOT / "tooling"))

from evals.chat_drive import _execute, _unwrap  # noqa: E402
from probes._env import get_client  # noqa: E402
from probes.effect import drive  # noqa: E402
from probes.effect.probes import Result, _reply  # noqa: E402

# TEST-NET-3: never routes, safe to quarantine on the lab firewall. The
# per-run suffix keeps a leftover block from an earlier run from reading as
# this run's write.
_CONTAIN_IP_PREFIX = "203.0.113."

_FG = "fortigate-firewall"


class _RecordSeedError(RuntimeError):
    pass


def _seed_alert(slug: str, description: str, source_ip: str | None = None) -> dict:
    """Create a scratch alert on the box; returns {iri, uuid, fields}."""
    client = get_client()
    if client is None:
        raise _RecordSeedError("not configured: no live client")
    body: dict = {"name": f"_fsrpb_effect_{slug}", "description": description}
    if source_ip:
        body["sourceIp"] = source_ip
    res = client.post("/api/3/alerts", body)
    data = getattr(res, "data", None) or (res if isinstance(res, dict) else {})
    iri = data.get("@id")
    if not iri:
        raise _RecordSeedError(f"alert create returned no @id: {str(data)[:200]}")
    return {"iri": iri, "uuid": data.get("uuid") or iri.rsplit("/", 1)[-1],
            "fields": body}


def _purge_record(iri: str) -> None:
    try:
        client = get_client()
        if client is not None:
            client.delete(iri)
    except Exception:  # noqa: BLE001 -- cleanup is best-effort
        pass


def _record_entity(seeded: dict) -> dict:
    return {"iri": seeded["iri"], "module": "alerts",
            "uuid": seeded["uuid"], "fields": dict(seeded["fields"])}


def _approve_action_card(session: str, card: dict) -> dict:
    """The widget's approve of an action_card, verbatim: chat_resume with
    decision=approve + card_id; the CONNECTOR executes the op (contract T6)."""
    return drive.resume({
        "session_id": session,
        "decision": "approve",
        "card_id": card.get("card_id") or card.get("id"),
    })


def _approve_gate(session: str, res: dict) -> tuple[dict | None, str]:
    """Approve whichever tier-3 gate the turn staged, the way the widget
    would. Two legitimate shapes reach the analyst:

      * an `action_card` (emit_action_card / emit_card) -- resumed by card_id;
      * an `approval_request` (a tier-3 tool suspended at the gate, e.g. a
        native `mcp_soc__*` containment) -- resumed by approval_id.

    Returns (resume_result, gate_label); (None, "") when the turn staged
    neither -- the probe is then BLOCKED, not failing."""
    card = drive.first_card(res, "action_card")
    if card:
        return _approve_action_card(session, card), "action_card"
    appr = drive.first_card(res, "approval_request")
    if appr and appr.get("approval_id"):
        return drive.resume({
            "session_id": session,
            "approval_id": appr["approval_id"],
            "decision": "approve",
        }), f"approval_request[{appr.get('tool')}]"
    return None, ""


def _run_op(connector: str, op: str, params: dict) -> dict:
    """A direct op execution on the box, outside the agent loop -- the ground
    truth read (and the cleanup write) for T1."""
    client = get_client()
    res = _unwrap(_execute(client, "call_mcp_tool", {
        "tool": "run_op",
        "args": {"connector": connector, "op": op, "params": params,
                 "confirm": True},
    }, drive.VERSION, drive.CONFIG))
    return res if isinstance(res, dict) else {"ok": False, "raw": str(res)[:300]}


def _firewall_holds(ip: str) -> bool:
    """Is `ip` on the firewall's blocked or quarantine list? Read from the
    box, never from the approve's own account of itself."""
    for op in ("get_blocked_ip", "get_quarantine_hosts"):
        res = _run_op(_FG, op, {})
        if ip in json.dumps(res, default=str):
            return True
    return False


def _unblock(ip: str) -> None:
    for op, params in (("unblock_ip", {"ip_addresses": ip}),
                       ("unquarantine_host", {"ip_addresses": ip})):
        try:
            _run_op(_FG, op, params)
        except Exception:  # noqa: BLE001 -- cleanup is best-effort
            pass


def _indicator_rows(ip: str) -> list[dict]:
    client = get_client()
    try:
        res = client.get(f"/api/3/indicators?value={ip}")
        data = getattr(res, "data", None) or (res if isinstance(res, dict) else {})
        rows = data.get("hydra:member") or data.get("data") or []
        return [r for r in rows if isinstance(r, dict)]
    except Exception:  # noqa: BLE001
        return []


def _indicator_blocked(ip: str) -> bool:
    """Does the box hold an indicator row for `ip` in a Blocked state? The
    enforcement point for the native `mcp_soc__block_indicator` route."""
    for row in _indicator_rows(ip):
        if "blocked" in json.dumps(row, default=str).lower():
            return True
    return False


def _purge_indicators(ip: str) -> None:
    for row in _indicator_rows(ip):
        iri = row.get("@id")
        if iri:
            _purge_record(iri)


# ── T1 -- approved containment lands on the enforcement point ─────────

def probe_t1_approved_containment() -> Result:
    """The #130 arc as a probe: order a block, approve the staged card, and
    read the FIREWALL for the address. A green card over a write that never
    reached the FortiGate is exactly the class this suite exists to catch
    (the wrong-param silent no-op reported Success, live)."""
    rid, title = "T1", "approved containment writes to the firewall"
    ip = _CONTAIN_IP_PREFIX + str(50 + int(time.time()) % 200)
    try:
        seeded = _seed_alert(
            "t1", f"Confirmed C2 beaconing to {ip} from workstation.",
            source_ip=ip)
    except _RecordSeedError as exc:
        return Result(rid, title, "ENV-SKIP", str(exc))
    try:
        if _firewall_holds(ip) or _indicator_blocked(ip):
            return Result(rid, title, "BLOCKED",
                          f"{ip} is already blocked before the turn -- a PASS "
                          "here would prove nothing; rerun (the suffix rotates)")
        session = drive.new_session("t1")
        res = drive.turn(
            f"Block {ip} on the FortiGate firewall now.",
            session=session, intent="triage", entity=_record_entity(seeded))
        tools = drive.tool_names(res)
        reply_res, gate = _approve_gate(session, res)
        if reply_res is None:
            gap = drive.first_card(res, "capability_gap")
            if gap:
                return Result(rid, title, "ENV-SKIP",
                              "capability_gap instead of a containment gate -- "
                              f"{_FG} is not usable on this box: "
                              f"{str(gap.get('why') or '')[:150]}",
                              tools=tools)
            return Result(rid, title, "BLOCKED",
                          "neither an action_card nor an approval_request was "
                          "staged for a direct containment order -- the "
                          "approve path was never reached",
                          tools=tools)

        reply = f"via {gate}; " + _reply(reply_res)
        # The write's home depends on the route the model chose: a fortigate
        # op lands on the firewall's lists, a native block_indicator lands as
        # a Blocked indicator row. Either is the containment landing; neither
        # is trusting the card. The native route is ASYNC (the tool returns a
        # task_id, the write happens behind it -- the agent-proxied-execute
        # pattern), so poll: too early a read scores a working write as FAIL.
        deadline = time.time() + 90
        where = ""
        while time.time() < deadline and not where:
            if _firewall_holds(ip):
                where = "firewall block/quarantine list"
            elif _indicator_blocked(ip):
                where = "Blocked indicator row"
            else:
                time.sleep(6)
        if where:
            return Result(rid, title, "PASS", f"{ip} is on the {where}",
                          "absent", where, tools, reply)
        return Result(rid, title, "FAIL",
                      f"approve returned but after 90s {ip} is on neither "
                      "the firewall lists nor a Blocked indicator row -- the "
                      "narrated block never landed",
                      "absent", "absent", tools, reply)
    finally:
        _unblock(ip)
        _purge_indicators(ip)
        _purge_record(seeded["iri"])


# ── T2 -- approved record-write lands on the record ───────────────────

def probe_t2_record_write() -> Result:
    """A record-update action card, approved, must change the ROW. The widget
    half of this card shipped unread for a full release cycle (#120/#78: the
    renderer ignored target/changes since they existed) -- the connector half
    gets the same standard: re-read the record, don't trust the card."""
    rid, title = "T2", "approved record-update writes the record row"
    nonce = "probe-" + uuid.uuid4().hex[:8]
    try:
        seeded = _seed_alert("t2", "Scratch alert for the record-write probe.")
    except _RecordSeedError as exc:
        return Result(rid, title, "ENV-SKIP", str(exc))
    try:
        session = drive.new_session("t2")
        res = drive.turn(
            f"Update this alert's description to exactly: {nonce}",
            session=session, intent="triage", entity=_record_entity(seeded))
        tools = drive.tool_names(res)
        card = drive.first_card(res, "action_card")
        if not card:
            return Result(rid, title, "BLOCKED",
                          "no action_card staged for a direct record-update "
                          "order -- the write path was never reached",
                          tools=tools)

        reply = _reply(_approve_action_card(session, card))
        client = get_client()
        row = client.get(seeded["iri"])
        data = getattr(row, "data", None) or (row if isinstance(row, dict) else {})
        desc = str(data.get("description") or "")
        if nonce in desc:
            return Result(rid, title, "PASS", "the row holds the new description",
                          "seed text", desc[:120], tools, reply)
        return Result(rid, title, "FAIL",
                      "approve returned but the row still holds the old "
                      "description",
                      "seed text", desc[:120], tools, reply)
    finally:
        _purge_record(seeded["iri"])


TRIAGE_PROBES = {
    "T1": probe_t1_approved_containment,
    "T2": probe_t2_record_write,
}
