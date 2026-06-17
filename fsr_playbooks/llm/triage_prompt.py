"""Dynamic triage prompt builder — layer 2.

Assembles the system prompt the triage agent actually runs with:

    base triage prompt  (system_prompt_triage.md — the general instincts)
      + a grounded "what we know" block   (from the normalized record)
      + the matched scenario's guidance    (fragment + entity-filled recipes
        + verdict checklist)

The scenario block is always *appended* to the full base prompt, never a
replacement — so a misclassification degrades to plain triage, never worse.
The "what we know" block surfaces the indicators and the embedded driving
events (associated_events) as ground truth, so the agent doesn't re-derive
them from raw JSON or, worse, narrate evidence it never actually saw.
"""
from __future__ import annotations

from typing import Any

from .intents import load_intent_prompt
from .triage_normalize import normalize_record
from .triage_scenarios import classify_alert, render_recipes
from .triage_sources import build_source_routing_block


def _humanize_bytes(n: Any) -> str:
    try:
        n = float(n)
    except (TypeError, ValueError):
        return "?"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


def _fmt_event(e: dict[str, Any]) -> str:
    bits = []
    if e.get("src"):
        bits.append(str(e["src"]) + (f" ({e['src_host']})" if e.get("src_host") else ""))
    if e.get("dst"):
        dst = str(e["dst"]) + (f":{e['dport']}" if e.get("dport") else "")
        if e.get("dst_country"):
            dst += f" [{e['dst_country']}]"
        bits.append("→ " + dst)
    if e.get("service"):
        bits.append(str(e["service"]))
    vol = []
    if e.get("bytes_out"):
        vol.append("out " + _humanize_bytes(e["bytes_out"]))
    if e.get("bytes_in"):
        vol.append("in " + _humanize_bytes(e["bytes_in"]))
    if vol:
        bits.append("| " + " ".join(vol))
    return " ".join(bits) or str(e)


def _ind_line(ips: list[dict]) -> str:
    out = []
    for i in ips:
        tag = "internal" if i.get("internal") else "EXTERNAL"
        role = f", {i['role']}" if i.get("role") else ""
        out.append(f"{i['value']} ({tag}{role})")
    return ", ".join(out) or "(none)"


def build_what_we_know(norm: dict[str, Any], max_events: int = 5) -> str:
    """A compact, grounded summary of the normalized record."""
    ind = norm.get("indicators", {})
    lines = ["## What we already know about this record",
             "(auto-extracted from the record — treat as ground truth; "
             "don't re-derive it)"]
    head = []
    if norm.get("source_connector"):
        head.append(f"Source: {norm['source_connector']}")
    if norm.get("severity"):
        head.append(f"Severity: {norm['severity']}")
    if norm.get("status"):
        head.append(f"Status: {norm['status']}")
    if head:
        lines.append("- " + " | ".join(head))
    if norm.get("incident_id"):
        lines.append(
            f"- SIEM incident id: {norm['incident_id']} — the SIEM's OWN "
            "incident id (from sourcedata.incident_data.incidentId). Pass "
            "THIS to SIEM incident ops (siem_events_for_incident, "
            "get_incident_details, get_associated_events_new), NOT the "
            "FortiSOAR record id/@id.")
    if norm.get("mitre"):
        m = "; ".join(f"{x.get('id')} {x.get('name')}".strip()
                      for x in norm["mitre"])
        lines.append(f"- MITRE: {m}")
    lines.append(f"- IPs: {_ind_line(ind.get('ips', []))}")
    for label, key in (("Hosts", "hosts"), ("Users", "users"),
                       ("Hashes", "hashes"), ("Domains", "domains")):
        vals = ind.get(key) or []
        if vals:
            lines.append(f"- {label}: {', '.join(vals)}")
    evs = sorted(norm.get("evidence_events", []),
                 key=lambda e: (e.get("bytes_out", 0) or 0)
                 + (e.get("bytes_in", 0) or 0), reverse=True)[:max_events]
    if evs:
        lines.append("- Driving events already on the record "
                     "(do NOT re-query the SIEM for these):")
        for e in evs:
            lines.append("    - " + _fmt_event(e))
    return "\n".join(lines)


def build_scenario_block(scenario: dict[str, Any], norm: dict[str, Any]) -> str:
    if scenario.get("id") == "generic":
        # Still give the generic verdict checklist; no scenario header.
        cl = scenario.get("verdict_checklist", [])
        return ("## Before you conclude\n"
                + "\n".join(f"- {c}" for c in cl)) if cl else ""
    parts = [f"## Likely scenario: {scenario.get('title')}"]
    if scenario.get("fragment"):
        parts.append(scenario["fragment"])
    recipes = render_recipes(scenario, norm)
    if recipes:
        parts.append("**Known-good opening moves** (entities pre-filled for "
                     "this record — run the relevant ones first):")
        parts.extend(f"- {r}" for r in recipes)
    cl = scenario.get("verdict_checklist", [])
    if cl:
        parts.append("**Answer these before you conclude:**")
        parts.extend(f"- {c}" for c in cl)
    return "\n".join(parts)


def build_triage_prompt(raw_record: dict[str, Any]) -> dict[str, Any]:
    """Build the specialized triage system prompt for a record.

    Returns a dict so the caller (pre-flight) can also surface the
    classification + normalized facts as activity events:
        {"system": <str>, "normalized": <dict>, "scenario_id": <str>,
         "scenario_title": <str>}
    """
    norm = normalize_record(raw_record)
    scenario = classify_alert(norm)
    base = load_intent_prompt("triage")
    blocks = [base, build_what_we_know(norm)]
    routing = build_source_routing_block(norm)
    if routing:
        blocks.append(routing)
    scen = build_scenario_block(scenario, norm)
    if scen:
        blocks.append(scen)
    system = "\n\n---\n\n".join(b for b in blocks if b.strip())
    return {
        "system": system,
        "normalized": norm,
        "scenario_id": scenario.get("id"),
        "scenario_title": scenario.get("title"),
    }
