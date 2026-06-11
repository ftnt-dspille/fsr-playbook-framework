"""Scenario registry + classifier — layer 1 of dynamic triage.

A static triage prompt asks the agent to remember the right moves for *every*
alert archetype, and a small model obeys inconsistently. Instead we classify
the normalized record into a scenario and inject that scenario's known-good
moves — the specific SIEM queries (pre-filled with this record's entities), the
right TI connectors, and a verdict checklist — so the agent starts with the
best opening for *this* kind of alert.

Design rules:
  * Declarative + idempotent (c3charts-registry style). Add a scenario = add a
    dict; nothing else changes.
  * Classify on the *normalized* record (so alerts and cases score the same).
  * Always a safe fallback: an unmatched record gets ``generic``, and the
    builder (layer 2) *appends* the fragment to the full base prompt — so a
    misclassification degrades to current behavior, never worse.

A recipe references the first-class SIEM tools by name; ``render_recipes`` fills
in this record's entities so the agent sees a ready-to-run call, not a template.
"""
from __future__ import annotations

from typing import Any, Callable

# --- small helpers over the normalized shape -----------------------------

def _ips(norm: dict, *, internal: bool | None = None) -> list[dict]:
    ips = norm.get("indicators", {}).get("ips", [])
    if internal is None:
        return ips
    return [i for i in ips if bool(i.get("internal")) is internal]


def _first(values: list, default: Any = None) -> Any:
    return values[0] if values else default


def _max_bytes_out(norm: dict) -> int:
    return max((e.get("bytes_out", 0) or 0 for e in norm.get("evidence_events", [])),
              default=0)


def _text_blob(norm: dict) -> str:
    parts = [norm.get("name") or "", str(norm.get("incident_summary") or "")]
    return " ".join(parts).lower()


def _has_mitre(norm: dict, *ids: str) -> bool:
    have = {(m.get("id") or "").upper() for m in norm.get("mitre", [])}
    return bool(have & {i.upper() for i in ids})


# --- scenario registry ----------------------------------------------------
# Each scenario:
#   id, title
#   match(norm) -> int   (signal count; 0 = no match)
#   ti_targets           which indicator types to enrich externally
#   siem_recipes(norm)   -> list[str] of ready-to-run, entity-filled moves
#   verdict_checklist    -> list[str]
#   fragment             -> str   (terse scenario guidance; recipes/checklist
#                                  are appended by the builder)

def _c2_match(norm: dict) -> int:
    score = 0
    if _has_mitre(norm, "T1041"):
        score += 2
    if (norm.get("incident_summary", {}).get("tactic") or "").lower() == "exfiltration":
        score += 2
    blob = _text_blob(norm)
    if any(w in blob for w in ("c2", "exfil", "malware ip", "command and control",
                               "beacon")):
        score += 1
    # external destination + large outbound volume
    if _ips(norm, internal=False) and _max_bytes_out(norm) > 50_000_000:
        score += 1
    return score


def _c2_recipes(norm: dict) -> list[str]:
    # Route the log-search moves through the originating source's own tools
    # (FortiSIEM vs FortiAnalyzer), defaulting to FortiSIEM when unmapped.
    from .triage_sources import SOURCE_TOOLS, toolset_for

    ts = toolset_for(norm.get("source_connector")) or SOURCE_TOOLS["fortisiem"]
    out: list[str] = []
    inc = norm.get("incident_id")
    host = _first(norm.get("indicators", {}).get("hosts", []))
    ext = _first(_ips(norm, internal=False))
    intern = _first(_ips(norm, internal=True))
    if inc and "incident" in ts:
        # Pass source_ip so the wrapper can coerce a stale id / fall back to an
        # IP event search (see siem_events_for_incident).
        src = norm.get("source_ip") or (intern or {}).get("value")
        src_arg = f', source_ip="{src}"' if src else ""
        out.append(ts["incident"].format(incident_id=inc, source_ip=src_arg)
                   + "  — pull the raw events that drove this detection")
    if host and "host" in ts:
        out.append(ts["host"].format(host=host)
                   + "  — other recent activity from the compromised host")
    if ext:
        out.append(f"enrich EXTERNAL C2 {ext['value']} with virustotal, "
                   "fortinet-fortiguard-ioc, shodan (fan out in one turn)")
        if "ip" in ts:
            out.append(ts["ip"].format(ip=ext["value"], direction="dst")
                       + "  — OTHER internal hosts talking to this C2 "
                       "(blast radius)")
    if intern:
        out.append(f"run_op {ts['connector']} get_ip_context for INTERNAL "
                   f"{intern['value']} (do NOT run external TI on an RFC1918 IP)")
    return out


def _vpn_tunnel_down_match(norm: dict) -> int:
    """NOC VPN tunnel down: an IPsec/SSL VPN tunnel dropped (device still up)."""
    score = 0
    blob = _text_blob(norm)
    if any(w in blob for w in (
            "tunnel down", "tunnel is down", "vpn down", "vpn is down",
            "ipsec", "phase2", "phase 2", "phase1", "phase 1",
            "tunnel went down", "vpn tunnel", "site-to-site vpn",
            "branch isolated", "renegotiation failed")):
        score += 2
    src = (norm.get("source_connector") or "").lower()
    if "fortianalyzer" in src or "fortimanager" in src or "faz" in src:
        score += 1
    return score


def _vpn_tunnel_down_recipes(norm: dict) -> list[str]:
    # Tunnel-centric: confirm the device is reachable (rules out a device
    # outage), then read its VPN logs to see phase1 vs phase2 and the peer side.
    device = _first(norm.get("indicators", {}).get("hosts", []))
    if not device:
        return []
    return [
        f'fmg_get_device_status(device="{device}")'
        "  — confirm the DEVICE is up first (a reachable device + dead tunnel "
        "is a VPN failure, not an outage)",
        f'faz_search_device_events(device="{device}", logtype="vpn", '
        'window="6h")  — phase1/phase2-down events and the peer',
    ]


def _device_down_match(norm: dict) -> int:
    """NOC device-down: a managed device stopped reporting / went unreachable."""
    score = 0
    blob = _text_blob(norm)
    if any(w in blob for w in (
            "stopped reporting", "stopped logging", "device down",
            "device is down", "unreachable", "went offline", "is offline",
            "link down", "link is down", "not responding", "lost connection",
            "connection lost", "device disconnected", "no longer reporting")):
        score += 2
    src = (norm.get("source_connector") or "").lower()
    if "fortimanager" in src or "fmg" in src:
        score += 1
    return score


def _device_down_recipes(norm: dict) -> list[str]:
    # Device-centric moves: confirm reachability in FMG, then corroborate (HA /
    # policy push / last FAZ logs). The device name normalizes into hosts.
    from .triage_sources import SOURCE_TOOLS, toolset_for

    ts = toolset_for(norm.get("source_connector")) or SOURCE_TOOLS["fortimanager"]
    device = _first(norm.get("indicators", {}).get("hosts", []))
    out: list[str] = []
    if not device:
        return out
    if "device" in ts:
        out.append(ts["device"].format(device=device)
                   + "  — confirm the device is actually unreachable first")
        for tmpl in ts.get("device_extra", []):
            out.append(tmpl.format(device=device))
    else:
        out.append(f'faz_search_device_events(device="{device}", window="6h")'
                   "  — the last logs it sent before going silent")
    return out


SCENARIOS: list[dict[str, Any]] = [
    {
        "id": "device_down",
        "title": "NOC — managed device down / not reporting",
        "match": _device_down_match,
        "ti_targets": [],
        "siem_recipes": _device_down_recipes,
        "verdict_checklist": [
            "Is the device truly unreachable (FMG conn_status=down), or did HA "
            "fail over (peer up ⇒ traffic likely survived)?",
            "When did it go silent, and what was the LAST event before "
            "(WAN/link down, power, tunnel down)?",
            "Was the most recent policy-package install clean, or could a bad "
            "config push be the cause?",
            "Root cause: upstream/network/power vs config push — which does the "
            "evidence point to?",
            "Recommend the remediation; do NOT auto-run it — any fix goes "
            "through a tier-3 approval card.",
        ],
        "fragment": (
            "This is a **NOC device-down** event — a managed device stopped "
            "reporting. Troubleshoot, don't auto-remediate: (1) confirm "
            "reachability in FortiManager (`fmg_get_device_status`); (2) check "
            "HA (`fmg_get_ha_status`) — a healthy peer means traffic likely "
            "survived; (3) corroborate in FortiAnalyzer "
            "(`faz_search_device_events`/`faz_event_summary`) to find the last "
            "logs and any link/tunnel/power signal just before silence; (4) rule "
            "a bad config push in or out (`fmg_get_policy_package_status`). "
            "A device with `conn_status: unknown` and/or `is_model: true` is a "
            "MODEL device (defined in FMG, never deployed) — that is NOT an "
            "outage, so don't flag it as down. "
            "Conclude with a likely root cause (upstream/network/power vs "
            "config) and a RECOMMENDED fix — never run a reboot or re-install "
            "without an approval card."
        ),
    },
    {
        "id": "vpn_tunnel_down",
        "title": "NOC — site-to-site VPN tunnel down",
        "match": _vpn_tunnel_down_match,
        "ti_targets": [],
        "siem_recipes": _vpn_tunnel_down_recipes,
        "verdict_checklist": [
            "Is the DEVICE itself reachable (FMG conn_status=up)? A reachable "
            "device with a dead tunnel is a VPN failure, not a device outage.",
            "Phase1 or phase2 — where does negotiation fail (read the FAZ vpn "
            "logs)? Phase1 = peer/auth/IKE; phase2 = selectors/SA.",
            "Is the remote peer reachable, and when did the tunnel last come up?",
            "Blast radius — which subnets/services lost connectivity while the "
            "tunnel is down?",
            "Recommend the fix (re-enable phase1, fix selectors, check peer); "
            "do NOT auto-remediate — any change goes through a tier-3 card.",
        ],
        "fragment": (
            "This is a **NOC VPN-tunnel-down** event — a site-to-site tunnel "
            "dropped. Troubleshoot, don't auto-remediate: (1) confirm the device "
            "is actually UP in FortiManager (`fmg_get_device_status`) — a "
            "reachable device with a dead tunnel is a VPN failure, NOT a device "
            "outage; (2) read the device's VPN logs in FortiAnalyzer "
            "(`faz_search_device_events(logtype=\"vpn\")`) to see whether phase1 "
            "or phase2 is failing and when it last came up; (3) determine the "
            "blast radius (which subnets lost reachability). Conclude with the "
            "likely cause (phase1 disabled/peer down/auth vs phase2 selectors) "
            "and a RECOMMENDED fix — never enable/disable a tunnel without an "
            "approval card."
        ),
    },
    {
        "id": "c2_exfil",
        "title": "C2 / data exfiltration",
        "match": _c2_match,
        "ti_targets": ["external_ip", "domain", "hash"],
        "siem_recipes": _c2_recipes,
        "verdict_checklist": [
            "How much data left (sum bytes_out to the external IP)?",
            "Dwell time (first→last event to the C2)?",
            "Blast radius — any OTHER internal hosts talking to the same C2?",
            "Is the host's malware remediated?",
            "Containment: block the C2 IP AND isolate the host.",
        ],
        "fragment": (
            "This alert looks like **command-and-control / data exfiltration**. "
            "Confirm the egress, size it, and find the blast radius before you "
            "conclude. The driving SIEM events are often already on the record "
            "(evidence_events) — read them first; only query the SIEM live for "
            "what the record doesn't already show."
        ),
    },
]

GENERIC: dict[str, Any] = {
    "id": "generic",
    "title": "general triage",
    "match": lambda norm: 0,
    "ti_targets": ["external_ip", "domain", "hash", "url"],
    "siem_recipes": lambda norm: [],
    "verdict_checklist": [
        "What is the core claim of this alert, and is it grounded in evidence?",
        "Which entities are affected (host/user/IP)?",
        "Is containment warranted, and on what?",
    ],
    "fragment": "",
}


def classify_alert(norm: dict[str, Any]) -> dict[str, Any]:
    """Return the best-matching scenario dict (``generic`` if none score > 0)."""
    best, best_score = GENERIC, 0
    for sc in SCENARIOS:
        try:
            score = int(sc["match"](norm))
        except Exception:  # a bad matcher must never break triage
            score = 0
        if score > best_score:
            best, best_score = sc, score
    return best


def render_recipes(scenario: dict[str, Any], norm: dict[str, Any]) -> list[str]:
    """Concrete, entity-filled known-good moves for this record."""
    fn: Callable[[dict], list[str]] = scenario.get("siem_recipes", lambda n: [])
    try:
        return fn(norm) or []
    except Exception:
        return []
