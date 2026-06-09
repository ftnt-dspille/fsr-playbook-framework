"""Record normalizer — layer 0 of dynamic triage.

A FortiSOAR *alert* is field-rich (sourceIp/destinationIp/severity as
first-class columns) and often carries the originating SIEM payload in
``sourcedata`` (a JSON *string* holding ``incident_data`` + the raw
``associated_events``). A *case/incident* is the opposite: a thin shell whose
indicators live only in free-text ``name``/``description`` and in linked
records — ``sourcedata`` is usually null.

``normalize_record`` collapses both into one canonical shape so everything
downstream (the alert classifier, the scenario prompt builder, the SIEM search
tools) sees the same structure regardless of record type:

    {
      "module": "alerts",
      "source_connector": "Fortinet FortiSIEM",
      "severity": "High", "status": "Open",
      "incident_id": "10868",                 # FortiSIEM incident id, if present
      "mitre": [{"name": "...", "id": "T1041", "tactic": "Exfiltration"}],
      "indicators": {
        "ips":    [{"value": "10.50.60.70", "role": "src", "internal": true}, ...],
        "hosts":  ["smithDesktop"], "users": ["wendy.smith"],
        "hashes": [...], "domains": [...], "urls": [...],
      },
      "incident_summary": {"event_name": "...", "title": "...", "tactic": "..."},
      "evidence_events": [                     # digest of associated_events
        {"ts": ..., "event_type": "...", "src": "...", "dst": "...",
         "dport": 443, "service": "HTTPS", "action": "accept",
         "bytes_out": 1994596242, "bytes_in": 4849007121,
         "dst_country": "Nigeria", "src_host": "smithDesktop"}, ...
      ],
    }

The shape is JSON-serializable so it can be injected straight into the system
prompt as a grounded "what we know" block.
"""
from __future__ import annotations

import ipaddress
import json
import re
from typing import Any

# --- indicator extraction maps -------------------------------------------

# First-class scalar fields → indicator role (None = unknown direction).
_IP_FIELDS = {
    "sourceIp": "src", "sourceAddress": "src",
    "destinationIp": "dst", "destinationAddress": "dst",
    "ip": None, "ipAddress": None,
}
_HOST_FIELDS = ("sourceHostName", "destinationHostName", "hostName",
                "deviceName", "computerName", "host")
_USER_FIELDS = ("userName", "sourceUserName", "user", "username", "accountName")
_HASH_FIELDS = ("fileHash", "fileHashSha256", "fileHashSha1", "fileHashMd5",
                "hash", "sha256", "md5")

_IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_HASH = re.compile(r"\b(?:[a-fA-F0-9]{64}|[a-fA-F0-9]{40}|[a-fA-F0-9]{32})\b")
# FortiSIEM emits a synthetic "HOST-<ip>" when an event has no real hostname —
# not a usable host indicator.
_HOST_PLACEHOLDER = re.compile(r"^HOST-(?:\d{1,3}\.){3}\d{1,3}$", re.I)


def _is_internal(ip: str) -> bool:
    try:
        return ipaddress.ip_address(ip).is_private
    except ValueError:
        return False


def _unwrap(v: Any) -> Any:
    """Picklist objects hydrate as {itemValue, color, ...}; keep the value."""
    if isinstance(v, dict):
        return v.get("itemValue", v.get("value", v.get("name")))
    return v


def _is_empty(v: Any) -> bool:
    return v is None or v == "" or v == [] or v == {} or v == "None"


def _parse_sourcedata(raw: Any) -> dict[str, Any]:
    """sourcedata is a JSON *string* on alerts, dict on some records, null on
    cases. Return a dict either way (empty when absent/unparseable)."""
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except (ValueError, TypeError):
            return {}
    return raw if isinstance(raw, dict) else {}


def _module_of(rec: dict[str, Any]) -> str:
    iri = rec.get("@id", "")
    if isinstance(iri, str) and iri.startswith("/api/"):
        parts = iri.strip("/").split("/")
        if len(parts) >= 3:
            return parts[2]
    t = rec.get("@type")
    return (t.lower() + "s") if isinstance(t, str) else ""


# --- event digest ---------------------------------------------------------

def _digest_event(ev: dict[str, Any]) -> dict[str, Any]:
    """Collapse one FortiSIEM associated_event into a compact, model-friendly
    row. Events nest the useful fields under ``attributes``."""
    a = ev.get("attributes", ev) if isinstance(ev, dict) else {}

    def g(*keys):
        for k in keys:
            if k in a and not _is_empty(a[k]):
                return a[k]
        return None

    row = {
        # display-name keys come from alert.sourcedata.associated_events;
        # the lower-camel raw keys come from live search_events / native query.
        "ts": g("Device Time", "Event Receive Time", "receiveTime", "phRecvTime"),
        "event_type": g("Event Type", "eventType", "Event Name", "eventName"),
        "src": g("Source IP", "srcIpAddr"),
        "dst": g("Destination IP", "destIpAddr"),
        "dport": g("Destination TCP/UDP Port", "destIpPort"),
        "service": g("Service Name", "Application Group Name"),
        "action": g("Firewall Action"),
        "bytes_out": g("Sent Bytes64", "sentBytes64"),
        "bytes_in": g("Received Bytes64", "recvBytes64", "rcvdBytes64"),
        "dst_country": g("Destination Country"),
        "src_host": g("Source Host Name", "hostName", "srcName"),
    }
    if isinstance(row.get("src_host"), str) and _HOST_PLACEHOLDER.match(row["src_host"]):
        row["src_host"] = None  # drop synthetic HOST-<ip>
    return {k: v for k, v in row.items() if not _is_empty(v)}


# --- indicator collection -------------------------------------------------

class _Indicators:
    """Dedup-on-insert collector for the canonical indicator buckets."""

    def __init__(self) -> None:
        self.ips: dict[str, dict[str, Any]] = {}   # value -> {value, role, internal}
        self.hosts: set[str] = set()
        self.users: set[str] = set()
        self.hashes: set[str] = set()
        self.domains: set[str] = set()
        self.urls: set[str] = set()

    def add_ip(self, value: Any, role: str | None = None) -> None:
        if not value or not isinstance(value, str):
            return
        value = value.strip()
        if not _IPV4.fullmatch(value):
            return
        cur = self.ips.get(value)
        if cur is None:
            self.ips[value] = {"value": value, "internal": _is_internal(value)}
            cur = self.ips[value]
        # Prefer a concrete role over None; don't clobber an existing one.
        if role and not cur.get("role"):
            cur["role"] = role

    def add(self, bucket: set[str], value: Any) -> None:
        if isinstance(value, str) and value.strip() and value.strip() != "None":
            bucket.add(value.strip())

    def add_host(self, value: Any) -> None:
        if isinstance(value, str) and not _HOST_PLACEHOLDER.match(value.strip()):
            self.add(self.hosts, value)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ips": list(self.ips.values()),
            "hosts": sorted(self.hosts),
            "users": sorted(self.users),
            "hashes": sorted(self.hashes),
            "domains": sorted(self.domains),
            "urls": sorted(self.urls),
        }


# Relationship keys under which a case/incident inlines its member alerts when
# fetched with $relationships=true.
_RELATED_ALERT_KEYS = ("alerts", "correlatedAlerts", "relatedAlerts",
                       "childAlerts")


def _collect_related_alerts(
    raw: dict[str, Any], ind: "_Indicators"
) -> tuple[list[str], str | None]:
    """Harvest the distinct source labels of a record's member alerts, fold
    each inlined alert's first-class indicators into ``ind``, and recover the
    FortiSIEM incident id from any member alert that carries its ``sourcedata``.

    A case is a thin shell, but a $relationships=true fetch inlines its member
    alerts — each carrying its own ``source`` (FortiSIEM vs FortiAnalyzer vs …)
    and indicator scalars. Collecting the *set* of sources is what lets the
    curator recommend pivoting an indicator across every source the case spans.

    A case never has its own ``sourcedata.incident_data.incidentId`` (the SIEM's
    native id) — but a FortiSIEM-sourced member alert does. When the member
    alert has been hydrated with its ``sourcedata`` (the pre-flight back-fills
    it; a bare $relationships=true fetch does not), recover that incidentId so
    SIEM incident ops (``siem_events_for_incident``) get the id the engine
    expects instead of the FortiSOAR record id. Returns the FIRST one found.
    Best-effort: tolerates IRIs-only (no source recoverable) without raising.
    """
    sources: list[str] = []
    seen: set[str] = set()
    member_incident_id: str | None = None
    for key in _RELATED_ALERT_KEYS:
        items = raw.get(key)
        if not isinstance(items, list):
            continue
        for it in items:
            if not isinstance(it, dict):
                continue  # bare IRI string — nothing to harvest
            src = _unwrap(it.get("source"))
            if isinstance(src, str) and src.strip() and src not in seen:
                seen.add(src)
                sources.append(src)
            # fold the member alert's scalar indicators into the case's set
            for field, role in _IP_FIELDS.items():
                ind.add_ip(_unwrap(it.get(field)), role)
            for field in _HOST_FIELDS:
                ind.add_host(_unwrap(it.get(field)))
            for field in _USER_FIELDS:
                ind.add(ind.users, _unwrap(it.get(field)))
            for field in _HASH_FIELDS:
                ind.add(ind.hashes, _unwrap(it.get(field)))
            # recover the SIEM incident id from a hydrated member alert
            if member_incident_id is None:
                a_sd = _parse_sourcedata(it.get("sourcedata")
                                         or it.get("sourceData"))
                a_idd = (a_sd.get("incident_data", {})
                         if isinstance(a_sd, dict) else {})
                a_iid = a_idd.get("incidentId") if isinstance(a_idd, dict) else None
                if a_iid is not None:
                    member_incident_id = str(a_iid)
    return sources, member_incident_id


def normalize_record(raw: dict[str, Any]) -> dict[str, Any]:
    """Collapse a hydrated FSR alert/case into the canonical triage shape.

    Robust to both record types: pulls indicators from first-class fields,
    the parsed ``sourcedata.incident_data``, the ``associated_events`` digest,
    and (for sparse cases) free-text name/description. Never raises on a
    missing field — absent data simply yields empty buckets.
    """
    if not isinstance(raw, dict):
        return {"module": "", "indicators": _Indicators().to_dict(),
                "mitre": [], "evidence_events": [], "incident_summary": {}}

    ind = _Indicators()
    sd = _parse_sourcedata(raw.get("sourcedata") or raw.get("sourceData"))
    idd = sd.get("incident_data", {}) if isinstance(sd, dict) else {}

    # 1) first-class scalar fields
    for field, role in _IP_FIELDS.items():
        ind.add_ip(_unwrap(raw.get(field)), role)
    for field in _HOST_FIELDS:
        ind.add_host(_unwrap(raw.get(field)))
    for field in _USER_FIELDS:
        ind.add(ind.users, _unwrap(raw.get(field)))
    for field in _HASH_FIELDS:
        ind.add(ind.hashes, _unwrap(raw.get(field)))

    # 2) incident_data (FortiSIEM-sourced alerts)
    if isinstance(idd, dict):
        src = idd.get("incidentSrc") or {}
        tgt = idd.get("incidentTarget") or {}
        ind.add_ip(src.get("srcIpAddr"), "src")
        ind.add_ip(tgt.get("destIpAddr"), "dst")
        ind.add_ip(idd.get("incidentRptIp"), None)

    # 3) associated_events digest + their indicators
    events: list[dict[str, Any]] = []
    for ev in (sd.get("associated_events") or []) if isinstance(sd, dict) else []:
        d = _digest_event(ev)
        if d:
            events.append(d)
        ind.add_ip(d.get("src"), "src")
        ind.add_ip(d.get("dst"), "dst")
        ind.add_host(d.get("src_host"))

    # 3b) member alerts of a case/incident (inlined via $relationships=true):
    # harvest their distinct sources + fold in their indicators.
    related_sources, member_incident_id = _collect_related_alerts(raw, ind)

    # 4) free-text fallback (sparse cases: indicators only live in prose)
    text = " ".join(str(raw.get(k, "")) for k in ("name", "description",
                                                  "impactAssessments"))
    for m in _IPV4.findall(text):
        ind.add_ip(m, None)
    for m in _HASH.findall(text):
        ind.add(ind.hashes, m)

    # mitre
    mitre = []
    for t in (idd.get("attackTechnique") or []) if isinstance(idd, dict) else []:
        if isinstance(t, dict):
            mitre.append({"name": t.get("name"), "id": t.get("techniqueid"),
                          "tactic": idd.get("attackTactic")})

    # the record's own incidentId (FortiSIEM-sourced alert) wins; for a case,
    # fall back to the id recovered from a hydrated member alert.
    incident_id = idd.get("incidentId") if isinstance(idd, dict) else None
    if incident_id is None:
        incident_id = member_incident_id

    return {
        "module": _module_of(raw),
        "iri": raw.get("@id"),
        "name": raw.get("name"),
        "source_connector": _unwrap(raw.get("source")),
        "related_sources": related_sources,
        "severity": _unwrap(raw.get("severity")),
        "status": _unwrap(raw.get("status")),
        "incident_id": str(incident_id) if incident_id is not None else None,
        "mitre": mitre,
        "indicators": ind.to_dict(),
        "incident_summary": {
            "event_name": idd.get("eventName"),
            "title": idd.get("incidentTitle"),
            "tactic": idd.get("attackTactic"),
            "rule": idd.get("eventType"),
        } if isinstance(idd, dict) and idd else {},
        "evidence_events": events,
    }
