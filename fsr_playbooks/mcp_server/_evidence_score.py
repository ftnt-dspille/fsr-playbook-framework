"""Evidence score for a delivered verdict (Phase 2 step 2: SHADOW).

The score is computed in code from the turn's tool-result facts (the
``TurnEvidence`` registry) and the verdict's structure (disposition, cited ids,
the identifiers its text names). The model's own confidence is NOT an input.

It is recorded beside the model's confidence on the verdict card and in the
autonomy decision record, and NOTHING reads it for a decision yet: the policy
still compares the self-reported confidence. Step 3 will switch the comparison;
until then this is calibration data (does the score separate known-correct from
known-wrong verdicts?).

The values are a ladder, not a sum (calibrated on the step 2 sample: corroboration
weighs more than coverage, since it is the stronger guard against one poisoned
or wrong source):

    no independent substantive support ........ 0.50
    support ................................... 0.80
    support + coverage ........................ 0.85
    support + corroboration ................... 0.90
    support + corroboration + coverage ........ 0.95
    contradiction, unsourced identifier, or a
    hedge disposition (suspicious,
    needs_more_info) .......................... capped at 0.50

A log hit that only returns the alert's own events (same event or incident id,
or the same source, destination and moment as the mounted alert) is an echo, not
corroboration: see ``is_echo``.

Coverage counts only the ready sources that can hold evidence about the subject
(see ``_applicable``), and credits a native-MCP tool as a query of its source.
"""
from __future__ import annotations

import ipaddress
import json
import logging
import re
import time
from collections.abc import Iterable
from typing import Any

log = logging.getLogger(__name__)

TIER_NONE = 0.5
TIER_SUPPORT = 0.8
TIER_COVERED = 0.85
TIER_CORROBORATED = 0.9
TIER_FULL = 0.95

_IPV4 = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.]*\d)")
_HASH = re.compile(r"\b(?:[a-fA-F0-9]{64}|[a-fA-F0-9]{40}|[a-fA-F0-9]{32})\b")
_MAX_IDENTS = 40
_SCAN_LIMIT = 200_000

_MALICIOUS_SEV = frozenset({"error"})
_CLEAN_SEV = frozenset({"ok"})
_BENIGN_DISPOSITIONS = frozenset({"benign", "false_positive"})
#: A verdict that says it cannot conclude is not evidence-backed, whatever a
#: lookup returned: its score is capped, not laddered.
_HEDGE_DISPOSITIONS = frozenset({"suspicious", "needs_more_info"})
#: A detection-count rating ("3/94") is a weak malicious signal below this many
#: detections or this share of engines: it does not, by itself, contradict a
#: benign call backed by a record. Applies only to engine-count scales
#: (``_ENGINE_MIN_TOTAL`` or more), not to "2/3 feeds" style counts.
_WEAK_MAX_DETECTIONS = 5
_WEAK_MAX_RATIO = 0.05
_ENGINE_MIN_TOTAL = 20
_RATIO = re.compile(r"(\d+)\s*/\s*(\d+)")
_LOG_PRODUCTS = ("siem", "analyzer", "fortiedr", "splunk", "qradar", "sentinel", "elastic")
_CIDR = re.compile(r"(?<![\d.])((?:\d{1,3}\.){3}\d{1,3})/(\d{1,2})\b")
#: Log helpers (tool prefix) that cannot hold event evidence about an external
#: indicator: the management plane and the log aggregator.
_NOT_FOR_EXTERNAL = frozenset({"faz_", "fmg_"})


def identifiers(*blobs: Any) -> list[str]:
    """Identifier-shaped tokens (IPv4 addresses, file hashes) in the given
    values, sorted and bounded. Narrow on purpose: counts, times and prose
    never look like these."""
    found: set[str] = set()
    for blob in blobs:
        if blob is None:
            continue
        try:
            text = blob if isinstance(blob, str) else json.dumps(blob, default=str)
        except Exception:  # noqa: BLE001
            continue
        text = text[:_SCAN_LIMIT]
        for m in _IPV4.findall(text):
            if all(int(p) <= 255 for p in m.split(".")):
                found.add(m)
        found.update(h.lower() for h in _HASH.findall(text))
    return sorted(found)[:_MAX_IDENTS]


def weak_rating(finding: Any) -> bool:
    """True when a reader finding rates malicious on a detection-count scale
    but below the minimum count or share (a handful of engines out of ~90)."""
    if not isinstance(finding, dict):
        return False
    m = _RATIO.fullmatch(str(finding.get("score_str") or "").strip())
    if not m:
        return False
    hits, total = int(m.group(1)), int(m.group(2))
    if total < _ENGINE_MIN_TOTAL:
        return False
    return hits < _WEAK_MAX_DETECTIONS or hits / total < _WEAK_MAX_RATIO


#: Keys that name an event, incident or alert in a log row or a record body.
_ID_KEYS = frozenset({
    "incidentid", "incident_id", "eventid", "event_id", "alertid", "alert_id",
    "sourceid", "source_id", "id", "uuid", "sessionid", "session_id", "logid",
    "log_id", "incidentid", "eventseq", "ph_event_id", "phincidentid"})
_SRC_KEYS = frozenset({"srcipaddr", "sourceip", "src_ip", "srcip", "src", "source_ip",
                       "srcaddr", "src_addr", "sourceaddress"})
_DST_KEYS = frozenset({"destipaddr", "destinationip", "dest_ip", "dstip", "dst",
                       "destination_ip", "dstaddr", "dst_addr", "destip",
                       "destinationaddress"})
_TIME_KEYS = frozenset({"ts", "phrecvtime", "createdate", "timestamp", "time", "eventtime",
                        "_time", "@timestamp", "start_time", "starttime", "event_time",
                        "receivetime", "devtime", "date"})
#: Events at the same source and destination within this many seconds of the
#: alert are the alert's own; hours apart they are a pattern, not an echo.
_ECHO_WINDOW_SECONDS = 120
_MAX_EVENTS = 60
_MIN_ID_LEN = 4


def _epoch(v: Any) -> float | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        x = float(v)
        return x / 1000.0 if x > 1e11 else x
    if isinstance(v, str) and v.strip():
        t = v.strip()
        try:
            return _epoch(float(t))
        except ValueError:
            pass
        try:
            from datetime import datetime, timezone  # noqa: PLC0415
            dt = datetime.fromisoformat(t.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.timestamp()
        except ValueError:
            return None
    return None


def event_facts(blob: Any) -> list[dict[str, Any]]:
    """Event-shaped rows in a tool result or record body, bounded: each is
    ``{"ids": [...], "src": ip, "dst": ip, "t": epoch seconds}`` with only the
    keys the row carries. A row counts when it names an event id or a
    source/destination pair. Used to tell an alert's own events from new ones."""
    if isinstance(blob, str):
        try:
            blob = json.loads(blob)
        except ValueError:
            return []
    out: list[dict[str, Any]] = []
    budget = [800]

    def walk(node: Any, depth: int) -> None:
        if len(out) >= _MAX_EVENTS or depth > 6 or budget[0] <= 0:
            return
        budget[0] -= 1
        if isinstance(node, list):
            for x in node:
                walk(x, depth + 1)
        elif isinstance(node, dict):
            ids: list[str] = []
            src = dst = t = None
            for k, v in node.items():
                lk = str(k).lower()
                if lk in _ID_KEYS and isinstance(v, (str, int)) and not isinstance(v, bool):
                    sv = str(v).strip().lower()
                    if len(sv) >= _MIN_ID_LEN:
                        ids.append(sv)
                elif lk in _SRC_KEYS and isinstance(v, str):
                    src = v.strip()
                elif lk in _DST_KEYS and isinstance(v, str):
                    dst = v.strip()
                elif lk in _TIME_KEYS and t is None:
                    t = _epoch(v)
            row: dict[str, Any] = {}
            if ids:
                row["ids"] = sorted(set(ids))
            if src and dst:
                row["src"], row["dst"] = src, dst
                if t is not None:
                    row["t"] = t
            if row:
                out.append(row)
            for v in node.values():
                if isinstance(v, (list, dict)):
                    walk(v, depth + 1)

    walk(blob, 0)
    return out


def is_echo(events: list[dict[str, Any]], own: list[dict[str, Any]]) -> bool:
    """True when ``events`` (a log result's rows) are all the alert's own: each
    shares an event or incident id with a row of the alert, or has the alert's
    source and destination within ``_ECHO_WINDOW_SECONDS`` of it. An empty list
    (nothing parsed) is not an echo: it cannot be shown to be one."""
    if not events or not own:
        return False
    own_ids = {i for o in own for i in o.get("ids") or []}
    for ev in events:
        if own_ids & set(ev.get("ids") or []):
            continue
        t = ev.get("t")
        if t is not None and "src" in ev and any(
                o.get("src") == ev["src"] and o.get("dst") == ev["dst"]
                and o.get("t") is not None
                and abs(o["t"] - t) <= _ECHO_WINDOW_SECONDS for o in own):
            continue
        return False
    return True

# --- premise: the subject's own records ------------------------------------
#: Role and approval wording in a record about the subject. STRONG roles say the
#: subject is expected to touch hostile infrastructure (a sandbox, a honeypot);
#: SCOPED terms (approval, an approved change, an allow list, a scanner) explain
#: contact only with the address the record names; ALARM terms say the subject
#: itself is already known bad.
_STRONG_ROLES = {
    "sandbox": re.compile(r"sandbox", re.I),
    "honeypot": re.compile(r"honey[ -]?(?:pot|net)", re.I),
    "detonation": re.compile(r"detonat", re.I),
    "malware_analysis": re.compile(r"malware[ -]analysis|threat[ -]research", re.I),
    "pentest": re.compile(r"pen(?:etration)?[ -]?test|red[ -]team", re.I),
}
_SCOPED_ROLES = {
    "scanner": re.compile(r"\bscanner\b|vulnerability scan", re.I),
    "approved": re.compile(r"\bapproved\b|\bauthori[sz]ed\b|\bsanctioned\b", re.I),
    "change": re.compile(r"\bchg[- ]?\d+|change request|standing change", re.I),
    "allowlist": re.compile(r"allow[- ]?list|whitelist", re.I),
    "expected": re.compile(r"\bexpected\b", re.I),
}
_ALARM_ROLES = {
    "compromised": re.compile(r"compromised|infected|quarantin|re-?imag", re.I),
}
_HOST_KEYS = frozenset({"computername", "hostname", "host", "devicename", "devname",
                        "sourcehost", "assetname", "srchostname", "dsthostname",
                        "endpointname", "machinename"})
_HOSTLIKE = re.compile(r"(?<![\w-])[a-z][a-z0-9]*(?:-[a-z0-9]+)+(?![\w-])", re.I)
_MAX_ROWS = 20
_MAX_NAMES = 60
_ROW_TEXT_LIMIT = 4000


def _names(text: str, blob: Any = None) -> set[str]:
    """Subject-handle tokens in ``text``: IPv4 addresses and host names (a
    host-key value, or a hyphenated token with a digit such as ``mkt-ws-31``)."""
    out = set(identifiers(text))
    for m in _HOSTLIKE.findall(text):
        if any(c.isdigit() for c in m):
            out.add(m.lower())
    if isinstance(blob, dict):
        for k, v in blob.items():
            if str(k).lower() in _HOST_KEYS and isinstance(v, str) and len(v.strip()) >= 3:
                out.add(v.strip().lower())
    return out


def _nets(text: str) -> list[str]:
    out = []
    for base, bits in _CIDR.findall(text):
        try:
            out.append(str(ipaddress.ip_network(f"{base}/{bits}", strict=False)))
        except ValueError:
            continue
    return sorted(set(out))[:10]


_WINDOW_START_KEYS = frozenset({
    "start_date", "planned_start_date", "planned_start", "window_start", "work_start",
    "valid_from", "validfrom", "starts", "startdate", "start_time", "starttime",
    "scheduled_start", "scheduledstart", "begin", "begins", "effective_from"})
_WINDOW_END_KEYS = frozenset({
    "end_date", "planned_end_date", "planned_end", "window_end", "work_end",
    "valid_to", "validto", "valid_until", "validuntil", "expires", "expiry",
    "expiry_date", "enddate", "end_time", "endtime", "scheduled_end", "scheduledend",
    "effective_to", "ends"})
_STATE_KEYS = frozenset({"state", "status", "phase", "stage", "approval_state"})
_LAPSED_STATES = re.compile(r"^(?:expired|cancel+ed|rejected|withdrawn|revoked|lapsed)\b", re.I)


def _window(node: dict[str, Any]) -> tuple[list[float | None] | None, bool]:
    """The change window a record row states, as ``[start, end]`` epoch seconds
    (either may be None), and whether the row says it has lapsed outright
    (expired, cancelled, rejected, withdrawn). ``(None, False)`` when the row
    states neither."""
    start = end = None
    lapsed = False
    for k, v in node.items():
        lk = str(k).lower()
        if lk in _WINDOW_START_KEYS and start is None:
            start = _epoch(v)
        elif lk in _WINDOW_END_KEYS and end is None:
            end = _epoch(v)
        elif lk in _STATE_KEYS and isinstance(v, str) and _LAPSED_STATES.match(v.strip()):
            lapsed = True
    return ([start, end] if (start is not None or end is not None) else None), lapsed


def window_covers(row: dict[str, Any], times: Iterable[float]) -> bool:
    """Does a record row's change window cover the alert? A window that ended
    before the alert (or starts after it), or a row that says the change has
    lapsed, covers nothing: it neither explains the activity nor contradicts a
    conviction of it. A row with no stated window, or an alert whose time is not
    known, is taken as covering (nothing shows otherwise)."""
    if row.get("lapsed"):
        return False
    w = row.get("window")
    ts = list(times)
    if not w or not ts:
        return True
    s, e = w
    return any((s is None or t >= s) and (e is None or t <= e) for t in ts)


def _top_time(blob: Any) -> float | None:
    """The time a record states for itself (an alert's create date), from its own
    top-level keys; None for a list or a record without one."""
    if not isinstance(blob, dict):
        return None
    for k, v in list(blob.items()):
        if str(k).lower() in ("data", "result", "record") and isinstance(v, dict):
            t = _top_time(v)
            if t is not None:
                return t
    for k, v in blob.items():
        if str(k).lower() in _TIME_KEYS and not isinstance(v, (dict, list)):
            t = _epoch(v)
            if t is not None:
                return t
    return None


def _alert_times(registry: dict[str, dict[str, Any]], record_subject: str,
                 known_events: Iterable[dict[str, Any]] | None,
                 known_time: float | None) -> list[float]:
    """When the alert happened, as the turn knows it: the times of the record
    under triage as the turn read it, of the events the host bound, and the bound
    record's own time."""
    out: list[float] = []
    if known_time is not None:
        out.append(known_time)
    for ev in known_events or []:
        if ev.get("t") is not None:
            out.append(ev["t"])
    for e in registry.values():
        if isinstance(e, dict) and e.get("ok") is True and _reads_record(e, record_subject):
            p = e.get("premise") or {}
            if p.get("t") is not None:
                out.append(p["t"])
            out.extend(ev["t"] for ev in e.get("events") or [] if ev.get("t") is not None)
    return out


def premise_facts(blob: Any) -> dict[str, Any]:
    """What a result says about hosts and their roles, bounded, for the premise
    check. ``names``: every IPv4 address and host name in it. ``nets``: networks
    it names. ``rows``: each record row (dict) whose own text carries role or
    approval wording, as ``{roles, names, nets}``. Empty dict when there is
    nothing to say."""
    if isinstance(blob, str):
        try:
            blob = json.loads(blob)
        except ValueError:
            return {}
    try:
        text = json.dumps(blob, default=str)[:_SCAN_LIMIT]
    except Exception:  # noqa: BLE001
        return {}
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    budget = [800]

    def walk(node: Any, depth: int) -> None:
        if len(rows) >= _MAX_ROWS or depth > 6 or budget[0] <= 0:
            return
        budget[0] -= 1
        if isinstance(node, list):
            for x in node:
                walk(x, depth + 1)
        elif isinstance(node, dict):
            own = " ".join(v for v in node.values() if isinstance(v, str))[:_ROW_TEXT_LIMIT]
            roles = sorted(
                name for table in (_STRONG_ROLES, _SCOPED_ROLES, _ALARM_ROLES)
                for name, rx in table.items() if rx.search(own))
            if roles:
                sub = json.dumps(node, default=str)[:20000]
                row = {"roles": roles, "names": sorted(_names(sub, node))[:20],
                       "nets": _nets(sub)}
                win, lapsed = _window(node)
                if win:
                    row["window"] = win
                if lapsed:
                    row["lapsed"] = True
                key = json.dumps(row, sort_keys=True)
                if key not in seen:
                    seen.add(key)
                    rows.append(row)
            for v in node.values():
                if isinstance(v, (list, dict)):
                    walk(v, depth + 1)

    walk(blob, 0)
    names = sorted(_names(text, blob if isinstance(blob, dict) else None))[:_MAX_NAMES]
    out: dict[str, Any] = {}
    top_t = _top_time(blob)
    if top_t is not None:
        out["t"] = top_t
    if names:
        out["names"] = names
    nets = _nets(text)
    if nets:
        out["nets"] = nets
    if rows:
        out["rows"] = rows
    return out


def _verdict_text(card: dict[str, Any]) -> list[str]:
    parts = [str(card.get("summary") or "")]
    for f in card.get("findings") or []:
        if isinstance(f, dict):
            parts.append(str(f.get("claim") or ""))
    return parts


def _entry_idents(e: dict[str, Any]) -> set[str]:
    return set(e.get("idents") or []) | set(identifiers(e.get("args")))


def _source_class(e: dict[str, Any], ready_sources: dict[str, str],
                  ready_connectors: dict[str, dict[str, str]]) -> str:
    if isinstance(e.get("finding"), dict) and e["finding"]:
        return "intel"
    name = str(e.get("name") or "")
    for prefix in ready_sources:
        if name.startswith(prefix):
            return "log:" + prefix
    if name.startswith("mcp_") and "__" in name:
        # a native-MCP tool of a log product (its incident or event lookups) is a
        # log hit, same as the product's helper tools; other servers stay generic
        server = name[len("mcp_"):].split("__", 1)[0]
        if any(w in _norm(server) for w in _LOG_PRODUCTS):
            return "log:mcp_" + server
    connector = str((e.get("args") or {}).get("connector") or "")
    meta = ready_connectors.get(connector)
    if meta:
        return meta.get("kind") or ("connector:" + connector)
    if connector:
        # a log product reached through the generic runner is a log source
        # (an event hit is not exculpatory), same as its helper-tool prefix
        if any(w in _norm(connector) for w in _LOG_PRODUCTS):
            return "log:" + connector
        return "connector:" + connector
    return "other:" + _record_kind(e)


def _norm(text: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(text or "").lower())


_LABEL_NOISE = frozenset({"fortinet", "connector", "api", "rest", "v2", "v3"})


def _label_tokens(label: str) -> list[str]:
    toks = [_norm(t) for t in re.split(r"[\s_\-/]+", label)]
    return [t for t in toks if len(t) >= 4 and t not in _LABEL_NOISE]


#: Documentation ranges stand for real public addresses in examples, fixtures and
#: tests; the stdlib calls them non-global, so they are named here.
_DOC_NETS = tuple(ipaddress.ip_network(n) for n in
                  ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24",
                   "2001:db8::/32"))


def _is_external(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    if any(addr in n for n in _DOC_NETS if n.version == addr.version):
        return True
    return addr.is_global


def _scope(ips: Iterable[str]) -> tuple[bool, bool]:
    """(names an external IP, names only non-global IPs) for the IPs a verdict
    is about. No IPs: (False, False), i.e. nothing can be ruled out."""
    ext = priv = False
    for ip in ips:
        try:
            if _is_external(ip):
                ext = True
            else:
                priv = True
        except ValueError:
            continue
    return ext, priv and not ext


def _credited(label: str, registry: dict[str, dict[str, Any]], intel: bool) -> bool:
    """True when a successful call in the registry queried the source ``label``
    even though the connector ledger does not show it: a native-MCP tool
    (``mcp_<server>__<tool>``) of that product, a reader finding whose source
    names it, or (for threat intel) any rated native-MCP lookup."""
    toks = _label_tokens(label)
    for e in registry.values():
        if not isinstance(e, dict) or e.get("ok") is not True:
            continue
        name = str(e.get("name") or "")
        finding_v = e.get("finding")
        finding = finding_v if isinstance(finding_v, dict) else {}
        hay = _norm(name) + "|" + _norm(finding.get("source"))
        if any(t in hay for t in toks):
            return True
        if intel and name.startswith("mcp_") and finding.get("severity"):
            return True
    return False


def _applicable_unchecked(unchecked: list[str], registry: dict[str, dict[str, Any]],
                          ready_sources: dict[str, str],
                          ready_connectors: dict[str, dict[str, str]],
                          ips: Iterable[str], has_hash: bool) -> list[str]:
    """The ready, unqueried sources that could still hold evidence about the
    subject. Dropped: a management-plane or log-aggregator source when the
    question is an external indicator; external threat intel when every address
    named is internal; and any source a native-MCP tool already queried."""
    ext, internal_only = _scope(ips)
    kinds = {m.get("label"): m.get("kind") for m in ready_connectors.values()}
    prefixes = {lab: pre for pre, lab in ready_sources.items()}
    out = []
    for label in unchecked:
        if label in prefixes and ext and prefixes[label] in _NOT_FOR_EXTERNAL:
            continue
        kind = kinds.get(label)
        if kind == "intel" and internal_only and not has_hash:
            continue
        if _credited(label, registry, intel=(kind == "intel")):
            continue
        out.append(label)
    return out


_KIND_WORDS = (("change", "change"), ("prior_case", "prior_case"),
               ("asset", "asset"), ("cmdb", "asset"), ("inventory", "asset"),
               ("device", "asset"), ("ticket", "ticket"), ("incident", "ticket"),
               ("alert", "alert"))


def _record_kind(e: dict[str, Any]) -> str:
    """What kind of record a generic (class ``other``) read is about, from the
    call's own module, path or tool name: an asset record and a change record
    are different evidence though both arrive through the one generic class."""
    args_v = e.get("args")
    args = args_v if isinstance(args_v, dict) else {}
    parts = [str(e.get("name") or "")]
    for k in ("module", "module_name", "table", "resource", "iri", "uuid", "path",
              "endpoint", "op", "type", "collection"):
        v = args.get(k)
        if isinstance(v, str):
            parts.append(v)
    hay = " ".join(parts).lower()
    for word, kind in _KIND_WORDS:
        if word in hay:
            return kind
    return "record"


def _derived_addresses(text: str, unsourced: set[str], known: set[str]) -> set[str]:
    """Unsourced addresses that are network arithmetic on a sourced one, not a
    recital: ``192.0.2.0/24`` over a known 192.0.2.9, or a bare ``.0`` network
    address next to a known address of the same /24."""
    derived: set[str] = set()
    known_ips = []
    for k in known:
        try:
            known_ips.append(ipaddress.ip_address(k))
        except ValueError:
            continue
    for base, bits in _CIDR.findall(text):
        if base not in unsourced:
            continue
        try:
            net = ipaddress.ip_network(f"{base}/{bits}", strict=False)
        except ValueError:
            continue
        if any(ip in net for ip in known_ips if ip.version == net.version):
            derived.add(base)
    for u in unsourced:
        if u.endswith(".0") and any(str(ip).rsplit(".", 1)[0] == u.rsplit(".", 1)[0]
                                    for ip in known_ips if ip.version == 4):
            derived.add(u)
    return derived


def _reads_record(e: dict[str, Any], record_subject: str) -> bool:
    if not record_subject:
        return False
    try:
        return record_subject in json.dumps(e.get("args") or {}, default=str).lower()
    except Exception:  # noqa: BLE001
        return False


def score_verdict(card: dict[str, Any], registry: dict[str, dict[str, Any]], *,
                  record_subject: str | None = None,
                  unchecked_sources: list[str] | None = None,
                  ready_sources: dict[str, str] | None = None,
                  ready_connectors: dict[str, dict[str, str]] | None = None,
                  known_extra: Iterable[str] | None = None,
                  known_events: list[dict[str, Any]] | None = None,
                  known_time: float | None = None
                  ) -> dict[str, Any]:
    """The evidence score for ``card`` (a delivered verdict) against ``registry``.

    Pure. Returns {score, tier, components, missing, capped_by, ...}.
    ``unchecked_sources`` is the labels of ready sources the turn never queried
    (``unchecked_ready_sources``). ``record_subject`` is the uuid of the record
    under triage; a read of it is not independent evidence. ``known_extra`` is
    identifiers the turn was handed rather than looked up (the analyst's own
    message, the mounted record's body): they are sourced, not recited."""
    ready_sources = ready_sources or {}
    ready_connectors = ready_connectors or {}
    disposition = str(card.get("disposition") or "")
    subject_rec = (record_subject or "").strip().lower()
    # Subject entities: the identifiers the verdict itself names. None named
    # (a host-only verdict) means an entry cannot be tied to a subject by
    # identifier, so any other independent entry counts as about it.
    text_ids = set(identifiers(*_verdict_text(card)))
    text_ips = [i for i in text_ids if "." in i]
    has_hash = any("." not in i for i in text_ids)

    # The alert's own rows: the record under triage as the turn read it (a read
    # whose args name the record) and the body the host bound as known context.
    own_events: list[dict[str, Any]] = list(known_events or [])
    for e in registry.values():
        if isinstance(e, dict) and e.get("ok") is True and _reads_record(e, subject_rec):
            own_events.extend(e.get("events") or [])

    alert_at = _alert_times(registry, subject_rec, known_events, known_time)

    facts: dict[str, dict[str, Any]] = {}
    for eid, e in registry.items():
        if not isinstance(e, dict) or str(e.get("name") or "").startswith("emit_"):
            continue
        ok = e.get("ok") is True
        ids = _entry_idents(e)
        finding = e.get("finding")
        facts[eid] = {
            "substantive": ok and e.get("thin") is not True,
            "independent": not _reads_record(e, subject_rec),
            "about": (not text_ids) or bool(text_ids & ids),
            "sev": finding.get("severity") if isinstance(finding, dict) else None,
            "weak": weak_rating(finding),
            "cls": _source_class(e, ready_sources, ready_connectors),
            "ids": ids,
            "kind": _premise_kind(e) if e.get("ok") is True else "",
            "rows": (e.get("premise") or {}).get("rows") or [],
        }
        facts[eid]["echo"] = (facts[eid]["cls"].startswith("log:")
                              and is_echo(e.get("events") or [], own_events))

    def eligible(f: dict[str, Any]) -> bool:
        return f["substantive"] and f["independent"] and f["about"]

    def supportive(f: dict[str, Any]) -> bool:
        if not eligible(f):
            return False
        if disposition == "true_positive":
            return f["sev"] in _MALICIOUS_SEV
        if disposition in _BENIGN_DISPOSITIONS:
            # a clean rating, or an asset / ticket / change record naming the
            # subject; a log hit or a non-clean rating is not exculpatory
            return f["sev"] in _CLEAN_SEV or (
                f["sev"] is None and f["cls"] != "intel"
                and not f["cls"].startswith("log:"))
        return True

    cited = {str(x) for fd in card.get("findings") or [] if isinstance(fd, dict)
             for x in (fd.get("evidence") or []) if isinstance(x, str)}
    # Support may come from any lookup the turn ran, not only the ids the
    # verdict threaded into its findings (the policy's evidence rule does the
    # same: a dropped citation is bookkeeping, not missing evidence).
    support = [eid for eid, f in facts.items() if supportive(f)]
    classes = {facts[eid]["cls"] for eid in support}
    has_support = bool(support)
    # Corroboration: a second independent source class, substantive and about
    # the subject, that does not point the other way. For a conviction a log hit
    # (SIEM beaconing next to a C2 rating) counts though it carries no rating;
    # for a benign call only exculpatory sources count.
    if disposition in _BENIGN_DISPOSITIONS:
        same_way = classes
    else:
        # A generic record read or module search ("other:*") is not a second
        # source: it can only echo the alert, a prior alert or another module.
        # An echo (a log hit that only returns the alert's own events) says
        # nothing the alert did not already say.
        same_way = {f["cls"] for f in facts.values()
                    if eligible(f) and f["sev"] not in _CLEAN_SEV
                    and not f["cls"].startswith("other") and not f["echo"]}
    corroborated = has_support and len(same_way | classes) >= 2
    applicable_unchecked = _applicable_unchecked(
        list(unchecked_sources or []), registry, ready_sources, ready_connectors,
        text_ips, has_hash)
    covered = not applicable_unchecked

    # Which way the lookups that contradict the verdict rated. A weak
    # malicious rating (a few engines of ~90) does not overturn a benign call
    # that a record (asset, change, prior case) backs. A clean rating does not
    # overturn a conviction that rests on a log hit about the subject and has
    # no rated support of its own: a young address has no reputation yet.
    record_backed = bool(classes) and any(
        not c.startswith("log:") and c != "intel" for c in classes)
    log_hit = any(eligible(f) and f["cls"].startswith("log:") and not f["echo"]
                  for f in facts.values())
    echo_only = (disposition == "true_positive" and not log_hit
                 and any(f["echo"] for f in facts.values()))
    behavioural_only = (disposition == "true_positive" and log_hit
                        and not has_support)

    def explained(f: dict[str, Any]) -> bool:
        """True when a rating's address is named by an independent asset or change
        record that gives a role or an approval for it (an approved change that
        names the CDN, a reassigned vendor address): the rating is explained, so
        it does not contradict a benign call."""
        rated = set()
        for i in f["ids"]:
            try:
                if "." in i and _is_external(i):
                    rated.add(i)
            except ValueError:
                continue
        if not rated:
            return False
        for r in facts.values():
            if not (r["kind"] and r["substantive"] and r["independent"]):
                continue
            for row in r["rows"]:
                if not window_covers(row, alert_at):
                    continue  # a closed or expired window explains nothing
                if (set(row.get("names") or []) & rated
                        and set(row.get("roles") or []) & (set(_STRONG_ROLES) | set(_SCOPED_ROLES))):
                    return True
        return False

    def contradicts(f: dict[str, Any]) -> bool:
        if not eligible(f):
            return False
        if disposition == "true_positive":
            return f["sev"] in _CLEAN_SEV and not behavioural_only
        if disposition in _BENIGN_DISPOSITIONS and f["sev"] in _MALICIOUS_SEV:
            return not ((f["weak"] and record_backed) or explained(f))
        return False

    contradicted = any(contradicts(f) for f in facts.values())

    known: set[str] = set()
    for f in facts.values():
        known |= f["ids"]
    known |= {str(x) for x in (known_extra or [])}
    unsourced_set = text_ids - known
    unsourced_set -= _derived_addresses(" ".join(_verdict_text(card)), unsourced_set, known)
    unsourced = sorted(unsourced_set)

    if not has_support:
        score, tier = TIER_NONE, "no_independent_support"
    else:
        score, tier = {
            (False, False): (TIER_SUPPORT, "support"),
            (False, True): (TIER_COVERED, "support_covered"),
            (True, False): (TIER_CORROBORATED, "support_corroborated"),
            (True, True): (TIER_FULL, "support_corroborated_covered"),
        }[(corroborated, covered)]
    capped_by: list[str] = []
    if disposition in _HEDGE_DISPOSITIONS:
        capped_by.append("hedge_disposition")
    if contradicted:
        capped_by.append("contradiction")
    if unsourced:
        capped_by.append("unsourced_identifier")
    if capped_by:
        score = min(score, TIER_NONE)

    missing: list[str] = []
    if not has_support:
        missing.append("no independent, substantive source about the subject "
                       "points the same way")
    if behavioural_only:
        missing.append("conviction rests on log hits; no source rated the "
                       "subject malicious")
    if echo_only:
        missing.append("the only log hit returns the alert's own events")
    if has_support and not corroborated:
        missing.append("no second independent source class")
    if not covered:
        missing.append("ready sources not queried: " + ", ".join(applicable_unchecked))
    if contradicted:
        missing.append("a lookup about the subject rated the opposite way")
    if unsourced:
        missing.append("identifiers in the verdict appear in no tool result: "
                       + ", ".join(unsourced[:5]))
    return {
        "score": round(score, 2),
        "tier": tier,
        "components": {"support": has_support, "corroboration": corroborated,
                       "coverage": covered, "no_contradiction": not contradicted,
                       "provenance": not unsourced},
        "missing": missing,
        "capped_by": capped_by,
        "cited_support": sorted(set(support) & cited),
        "support_classes": sorted(classes),
        "echo": sorted(eid for eid, f in facts.items() if f["echo"]),
    }

def _record_hay(e: dict[str, Any]) -> str:
    args_v = e.get("args")
    args = args_v if isinstance(args_v, dict) else {}
    parts = [str(e.get("name") or "")]
    for k in ("module", "module_name", "table", "resource", "iri", "uuid", "path",
              "endpoint", "op", "type", "collection", "connector"):
        v = args.get(k)
        if isinstance(v, str):
            parts.append(v)
    return " ".join(parts).lower()


_ASSET_WORDS = ("asset", "cmdb", "inventory", "device", "host", "endpoint", "computer")


def _premise_kind(e: dict[str, Any]) -> str:
    """``asset`` or ``change`` when a call read the host's own record or a change
    record; "" otherwise (an alert, a prior case, a log, a rating)."""
    hay = _record_hay(e)
    if "change" in hay:
        return "change"
    if any(w in hay for w in _ASSET_WORDS):
        return "asset"
    return ""


def _in_nets(ip: str, nets: Iterable[str]) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    for n in nets:
        try:
            net = ipaddress.ip_network(n, strict=False)
        except ValueError:
            continue
        if net.version == addr.version and addr in net:
            return True
    return False


def _names_subject(names: Iterable[str], nets: Iterable[str], subject: set[str]) -> bool:
    nm = set(names)
    return bool(nm & subject) or any(_in_nets(s, nets) for s in subject if "." in s)


def _subject_names(card: dict[str, Any], registry: dict[str, dict[str, Any]],
                   record_subject: str, known_names: Iterable[str]) -> set[str]:
    """Host names and internal addresses of the subject: the alert as the turn
    read it and as the host bound it. Only when neither names one do the internal
    addresses and host names the verdict itself names stand in."""
    names: set[str] = set(known_names)
    for e in registry.values():
        if isinstance(e, dict) and e.get("ok") is True and _reads_record(e, record_subject):
            names |= set((e.get("premise") or {}).get("names") or [])

    def internal(found: Iterable[str]) -> set[str]:
        out = set()
        for n in found:
            try:
                if not _is_external(n):
                    out.add(n)
            except ValueError:
                out.add(n)  # a host name
        return out

    own = internal(names)
    if own:
        # The alert (or the host) named the subject: the verdict's prose adds
        # nothing, and a near-miss neighbour it mentions must not become the
        # subject (its record would then count as the subject's own).
        return own
    return internal(names | _names(" ".join(_verdict_text(card))))


def _record_rows(blob: Any) -> list[Any]:
    """The rows of a record lookup result: the lists inside it, else the blob as
    one row. Bounded."""
    if isinstance(blob, str):
        try:
            blob = json.loads(blob)
        except ValueError:
            return [blob]
    rows: list[Any] = []

    def walk(node: Any, depth: int) -> None:
        if len(rows) >= 50 or depth > 4:
            return
        if isinstance(node, list):
            if node and all(isinstance(x, dict) for x in node):
                rows.extend(node[:50 - len(rows)])
            else:
                for x in node:
                    walk(x, depth + 1)
        elif isinstance(node, dict):
            for v in node.values():
                if isinstance(v, (list, dict)):
                    walk(v, depth + 1)

    walk(blob, 0)
    return rows or ([blob] if blob not in (None, "", [], {}) else [])


def subject_records_exist(reader: Any, subject: set[str]) -> dict[str, bool | None]:
    """Ask the host whether the subject has an asset record and a change record.

    ``reader(names)`` returns ``{"asset": rows, "change": rows}``: the rows a
    bounded lookup for ``names`` found (an empty list when it found none, None
    when it could not look). A kind exists only when a returned row itself names
    the subject (a neighbour's record does not). ``{}`` when no reader is bound
    or it fails. Never raises."""
    if reader is None or not subject:
        return {}
    names = sorted(subject, key=lambda n: (n.replace(".", "").isdigit(), n))[:4]
    try:
        got = reader(names)
    except Exception:  # noqa: BLE001
        log.debug("subject records reader failed", exc_info=True)
        return {}
    out: dict[str, bool | None] = {}
    for kind in ("asset", "change"):
        v = (got or {}).get(kind) if isinstance(got, dict) else None
        if v is None:
            out[kind] = None
            continue
        found = False
        for row in _record_rows(v):
            try:
                text = json.dumps(row, default=str)[:20000]
            except Exception:  # noqa: BLE001
                continue
            if _names_subject(_names(text, row if isinstance(row, dict) else None),
                              _nets(text), subject):
                found = True
                break
        out[kind] = found
    return out


def premise_check(card: dict[str, Any], registry: dict[str, dict[str, Any]], *,
                  record_subject: str | None = None,
                  known_names: Iterable[str] | None = None,
                  known_events: Iterable[dict[str, Any]] | None = None,
                  known_time: float | None = None,
                  subject_reader: Any = None) -> dict[str, Any]:
    """Did the turn read the subject's OWN records (its asset record, a change
    record naming it), and does any of them contradict the verdict?

    ``read``: a successful asset or change read names the subject and nothing in
    it contradicts the disposition. ``contradicted``: a record naming the subject
    explains the activity the verdict calls hostile (a conviction against a
    sandbox, a honeypot, an approved change that names the address), or marks a
    benign host as compromised. When the turn read none, the host's
    ``subject_reader`` (a bounded lookup, called only then) says whether such a
    record exists: ``unread_exists`` (it exists and was not read) or
    ``none_exists`` (the host looked and there is none). ``unread`` is left for
    "the host did not say" (no reader, or a lookup that failed). Pure apart from
    the reader; a separate signal from the score, recorded beside it (shadow
    only)."""
    subject_rec = (record_subject or "").strip().lower()
    disposition = str(card.get("disposition") or "")
    subject = _subject_names(card, registry, subject_rec, known_names or [])
    verdict_external = set()
    for i in identifiers(*_verdict_text(card)):
        try:
            if "." in i and _is_external(i):
                verdict_external.add(i)
        except ValueError:
            continue
    alert_at = _alert_times(registry, subject_rec, known_events, known_time)
    read: list[str] = []
    contra: list[dict[str, Any]] = []
    for eid, e in registry.items():
        if (not isinstance(e, dict) or e.get("ok") is not True
                or _reads_record(e, subject_rec) or not _premise_kind(e)):
            continue
        p = e.get("premise") or {}
        if not _names_subject(p.get("names") or [], p.get("nets") or [], subject):
            continue
        read.append(eid)
        for row in p.get("rows") or []:
            if not _names_subject(row.get("names") or [], row.get("nets") or [], subject):
                continue
            roles = set(row.get("roles") or [])
            if not window_covers(row, alert_at):
                # a change window that ended before the alert (or has not begun,
                # or lapsed) neither explains the activity nor contradicts a
                # conviction of it; the record was still read
                roles &= set(_ALARM_ROLES)
            hit: list[str] = []
            if disposition == "true_positive":
                hit = sorted(roles & set(_STRONG_ROLES))
                if not hit and set(row.get("names") or []) & verdict_external:
                    hit = sorted(roles & set(_SCOPED_ROLES))
            elif disposition in _BENIGN_DISPOSITIONS:
                hit = sorted(roles & set(_ALARM_ROLES))
            if hit:
                contra.append({"call": eid, "roles": hit})
    status = "contradicted" if contra else ("read" if read else "unread")
    out: dict[str, Any] = {"status": status, "records": sorted(read),
                           "contradicted_by": contra, "subject": sorted(subject)[:6]}
    if status == "unread":
        asked: dict[str, Any] = {}

        def timed(names: list[str]) -> Any:
            t0 = time.monotonic()
            try:
                got = subject_reader(names)
                asked["got"] = got
                return got
            finally:
                asked["ms"] = int((time.monotonic() - t0) * 1000)

        exists = subject_records_exist(timed if subject_reader is not None else None, subject)
        if "ms" in asked:
            # What the existence lookup cost this turn (shadow telemetry): wall
            # time, plus whatever request counts the host reader reports.
            stats = (asked.get("got") or {}).get("stats") if isinstance(asked.get("got"), dict) else None
            out["lookup"] = {"ms": asked["ms"], **({k: v for k, v in stats.items()
                                                    if isinstance(v, int)} if isinstance(stats, dict) else {})}
        if exists:
            out["exists"] = exists
            vals = list(exists.values())
            if any(v is True for v in vals):
                out["status"] = "unread_exists"
            elif vals and all(v is False for v in vals):
                out["status"] = "none_exists"
    return out


def record_premise(card: dict[str, Any], premise: dict[str, Any]) -> None:
    """Put the premise check on ``card`` beside the score. Recording only."""
    card["premise"] = premise
    log.info("premise disposition=%s status=%s records=%s contradicted_by=%s",
             card.get("disposition"), premise.get("status"), premise.get("records"),
             premise.get("contradicted_by"))


def record_score(card: dict[str, Any], score: dict[str, Any]) -> None:
    """Put the score on ``card`` beside the model's confidence, and log both.
    Recording only: no decision reads it."""
    card["evidence_score"] = score
    log.info("evidence_score disposition=%s model_confidence=%s score=%s tier=%s "
             "missing=%s", card.get("disposition"), card.get("confidence"),
             score.get("score"), score.get("tier"), score.get("missing"))
