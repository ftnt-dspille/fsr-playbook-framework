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
        out.append(ts["incident"].format(incident_id=inc)
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


SCENARIOS: list[dict[str, Any]] = [
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
