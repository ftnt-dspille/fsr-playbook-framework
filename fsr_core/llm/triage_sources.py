"""Source-aware tool routing — the curation layer that matches *tools to data*.

An alert's evidence lives in whatever system raised it: a FortiSIEM alert's
driving events are in FortiSIEM, a FortiAnalyzer alert's are in FAZ device
logs. The first-class triage helpers come in matching pairs (``siem_search_ip``
↔ ``faz_search_ip``, ``siem_raw_query`` ↔ ``faz_raw_query``), so the right
pivot depends on the source. This module maps a record's originating
connector(s) to the correct toolset and renders entity-filled opening moves —
and, for a *case* that spans multiple sources, recommends pivoting the same
indicator across every source it spans.

Declarative + idempotent: add a source = add a dict to ``SOURCE_TOOLS``.
"""
from __future__ import annotations

from typing import Any

# Canonical source key → its first-class toolset. `templates` are format
# strings filled with the record's entities; `connector` is the FSR connector
# name to confirm via list_configured_connectors before recommending.
SOURCE_TOOLS: dict[str, dict[str, Any]] = {
    "fortisiem": {
        "label": "FortiSIEM",
        "connector": "fortinet-fortisiem",
        "ip": 'siem_search_ip(ip="{ip}", direction="{direction}")',
        "host": 'siem_search_host(host="{host}")',
        "user": 'siem_search_user(user="{user}")',
        "incident": 'siem_events_for_incident(incident_id="{incident_id}")',
        "raw": "siem_raw_query",
    },
    "fortianalyzer": {
        "label": "FortiAnalyzer",
        "connector": "fortinet-fortianalyzer",
        "ip": 'faz_search_ip(ip="{ip}", direction="{direction}")',
        "alerts": 'faz_get_alerts(adom="root")',
        "raw": "faz_raw_query",
    },
}

# Substrings (matched case-insensitively against a source label OR connector id)
# → canonical key. Covers display labels ("Fortinet FortiSIEM") and connector
# names ("fortinet-fortisiem") alike.
_SOURCE_ALIASES: tuple[tuple[str, str], ...] = (
    ("fortisiem", "fortisiem"),
    ("forti-siem", "fortisiem"),
    ("forti siem", "fortisiem"),
    ("fortianalyzer", "fortianalyzer"),
    ("forti-analyzer", "fortianalyzer"),
    ("forti analyzer", "fortianalyzer"),
    ("faz", "fortianalyzer"),
)


def canonical_source(label: Any) -> str | None:
    """Map a free-text source label / connector id to a canonical key, or None
    when the source has no first-class toolset (falls back to generic run_op)."""
    if not isinstance(label, str) or not label.strip():
        return None
    s = label.strip().lower()
    for alias, key in _SOURCE_ALIASES:
        if alias in s:
            return key
    return None


def toolset_for(label: Any) -> dict[str, Any] | None:
    """The toolset dict for a source label, or None if unmapped."""
    key = canonical_source(label)
    return SOURCE_TOOLS.get(key) if key else None


def _primary_ip(norm: dict[str, Any]) -> dict[str, Any] | None:
    """The most pivot-worthy IP: prefer an external one (likely adversary)."""
    ips = norm.get("indicators", {}).get("ips", [])
    ext = [i for i in ips if not i.get("internal")]
    return (ext or ips or [None])[0]


def _moves_for_source(ts: dict[str, Any], norm: dict[str, Any]) -> list[str]:
    """Entity-filled opening moves for one source's toolset, using whatever
    indicators the record actually has."""
    ind = norm.get("indicators", {})
    moves: list[str] = []
    if "incident" in ts and norm.get("incident_id"):
        moves.append(ts["incident"].format(incident_id=norm["incident_id"])
                     + "  — the events that drove this detection")
    ip = _primary_ip(norm)
    if "ip" in ts and ip:
        direction = "dst" if not ip.get("internal") else "any"
        moves.append(ts["ip"].format(ip=ip["value"], direction=direction)
                     + ("  — who else talked to this external IP"
                        if not ip.get("internal") else "  — this host's activity"))
    host = (ind.get("hosts") or [None])[0]
    if "host" in ts and host:
        moves.append(ts["host"].format(host=host))
    user = (ind.get("users") or [None])[0]
    if "user" in ts and user:
        moves.append(ts["user"].format(user=user))
    if not moves and "alerts" in ts:
        moves.append(ts["alerts"] + "  — recent alerts from this source")
    return moves


def record_sources(norm: dict[str, Any]) -> list[str]:
    """The distinct source labels this record/case spans (primary first)."""
    out: list[str] = []
    for s in [norm.get("source_connector"), *(norm.get("related_sources") or [])]:
        if isinstance(s, str) and s.strip() and s not in out:
            out.append(s)
    return out


def build_source_routing_block(norm: dict[str, Any]) -> str:
    """A source-aware routing block: for each source the record/case spans that
    has a first-class toolset, the right pre-filled pivots; plus a nudge to fan
    out across configured log sources. Empty when no source is recognized."""
    sources = record_sources(norm)
    if not sources:
        return ""

    mapped: list[tuple[dict[str, Any], list[str]]] = []
    unmapped: list[str] = []
    seen_keys: set[str] = set()
    for label in sources:
        ts = toolset_for(label)
        if ts is None:
            unmapped.append(label)
            continue
        key = canonical_source(label)
        if key in seen_keys:
            continue
        seen_keys.add(key)  # type: ignore[arg-type]
        mapped.append((ts, _moves_for_source(ts, norm)))

    if not mapped and not unmapped:
        return ""

    lines = ["## Search the right place — source-aware pivots"]
    multi = len(mapped) + len(unmapped) > 1
    if multi:
        spanned = ", ".join([ts["label"] for ts, _ in mapped] + unmapped)
        lines.append(
            f"This record spans **multiple sources** ({spanned}). The evidence "
            "for each alert lives in the system that raised it — pivot your key "
            "indicators in EACH source, don't assume one holds the whole story.")
    else:
        lines.append(
            f"Originating source: **{(mapped or [(None,)])[0][0]['label'] if mapped else unmapped[0]}**. "
            "Use that source's own tools for the driving events.")

    for ts, moves in mapped:
        lines.append(f"**{ts['label']}** (`{ts['connector']}`):")
        if moves:
            lines.extend(f"- {m}" for m in moves)
        else:
            lines.append(f"- (no entity pre-filled yet) use its tools / "
                         f"`{ts['raw']}` once you have an indicator")
    for label in unmapped:
        lines.append(f"**{label}**: no first-class helper — query it with "
                     f"`run_op` (resolve the op via find_operation first).")

    lines.append("Confirm each connector is configured & healthy "
                 "(`list_configured_connectors`) before relying on it; if one "
                 "is missing, surface it with `emit_capability_gap_card` rather "
                 "than silently skipping that source.")
    return "\n".join(lines)


__all__ = ["SOURCE_TOOLS", "canonical_source", "toolset_for",
           "record_sources", "build_source_routing_block"]
