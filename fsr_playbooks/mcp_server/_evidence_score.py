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

Coverage counts only the ready sources that can hold evidence about the subject
(see ``_applicable``), and credits a native-MCP tool as a query of its source.
"""
from __future__ import annotations

import ipaddress
import json
import logging
import re
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
        finding = e.get("finding") if isinstance(e.get("finding"), dict) else {}
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
    args = e.get("args") if isinstance(e.get("args"), dict) else {}
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
                  known_extra: Iterable[str] | None = None
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
        }

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
        same_way = {f["cls"] for f in facts.values()
                    if eligible(f) and f["sev"] not in _CLEAN_SEV
                    and not f["cls"].startswith("other")}
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
    log_hit = any(eligible(f) and f["cls"].startswith("log:") for f in facts.values())
    behavioural_only = (disposition == "true_positive" and log_hit
                        and not has_support)

    def contradicts(f: dict[str, Any]) -> bool:
        if not eligible(f):
            return False
        if disposition == "true_positive":
            return f["sev"] in _CLEAN_SEV and not behavioural_only
        if disposition in _BENIGN_DISPOSITIONS and f["sev"] in _MALICIOUS_SEV:
            return not (f["weak"] and record_backed)
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
    }


def record_score(card: dict[str, Any], score: dict[str, Any]) -> None:
    """Put the score on ``card`` beside the model's confidence, and log both.
    Recording only: no decision reads it."""
    card["evidence_score"] = score
    log.info("evidence_score disposition=%s model_confidence=%s score=%s tier=%s "
             "missing=%s", card.get("disposition"), card.get("confidence"),
             score.get("score"), score.get("tier"), score.get("missing"))
