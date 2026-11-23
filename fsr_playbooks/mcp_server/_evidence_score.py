"""Evidence score for a delivered verdict (Phase 2 step 2: SHADOW).

The score is computed in code from the turn's tool-result facts (the
``TurnEvidence`` registry) and the verdict's structure (disposition, cited ids,
the identifiers its text names). The model's own confidence is NOT an input.

It is recorded beside the model's confidence on the verdict card and in the
autonomy decision record, and NOTHING reads it for a decision yet: the policy
still compares the self-reported confidence. Step 3 will switch the comparison;
until then this is calibration data (does the score separate known-correct from
known-wrong verdicts?).

The values are a ladder, not a sum, and are placeholders to be calibrated:

    no independent substantive support ........ 0.50
    support ................................... 0.80
    support + one of (corroboration, coverage)  0.88
    support + corroboration + coverage ........ 0.95
    any contradiction or unsourced identifier . capped at 0.50
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

log = logging.getLogger(__name__)

TIER_NONE = 0.5
TIER_SUPPORT = 0.8
TIER_PARTIAL = 0.88
TIER_FULL = 0.95

_IPV4 = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.]*\d)")
_HASH = re.compile(r"\b(?:[a-fA-F0-9]{64}|[a-fA-F0-9]{40}|[a-fA-F0-9]{32})\b")
_MAX_IDENTS = 40
_SCAN_LIMIT = 200_000

_MALICIOUS_SEV = frozenset({"error"})
_CLEAN_SEV = frozenset({"ok"})
_BENIGN_DISPOSITIONS = frozenset({"benign", "false_positive"})


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
    connector = str((e.get("args") or {}).get("connector") or "")
    meta = ready_connectors.get(connector)
    if meta:
        return meta.get("kind") or ("connector:" + connector)
    if connector:
        return "connector:" + connector
    return "other"


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
                  ready_connectors: dict[str, dict[str, str]] | None = None
                  ) -> dict[str, Any]:
    """The evidence score for ``card`` (a delivered verdict) against ``registry``.

    Pure. Returns {score, tier, components, missing, capped_by, ...}.
    ``unchecked_sources`` is the labels of ready sources the turn never queried
    (``unchecked_ready_sources``). ``record_subject`` is the uuid of the record
    under triage; a read of it is not independent evidence."""
    ready_sources = ready_sources or {}
    ready_connectors = ready_connectors or {}
    disposition = str(card.get("disposition") or "")
    subject_rec = (record_subject or "").strip().lower()
    # Subject entities: the identifiers the verdict itself names. None named
    # (a host-only verdict) means an entry cannot be tied to a subject by
    # identifier, so any other independent entry counts as about it.
    text_ids = set(identifiers(*_verdict_text(card)))

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
        same_way = {f["cls"] for f in facts.values()
                    if eligible(f) and f["sev"] not in _CLEAN_SEV}
    corroborated = has_support and len(same_way | classes) >= 2
    covered = not (unchecked_sources or [])

    contradicted = any(
        eligible(f) and ((disposition == "true_positive" and f["sev"] in _CLEAN_SEV)
                         or (disposition in _BENIGN_DISPOSITIONS
                             and f["sev"] in _MALICIOUS_SEV))
        for f in facts.values())

    known: set[str] = set()
    for f in facts.values():
        known |= f["ids"]
    unsourced = sorted(text_ids - known)

    if not has_support:
        score, tier = TIER_NONE, "no_independent_support"
    else:
        steps = int(corroborated) + int(covered)
        score, tier = ((TIER_SUPPORT, "support"), (TIER_PARTIAL, "support_partial"),
                       (TIER_FULL, "support_corroborated_covered"))[steps]
    capped_by: list[str] = []
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
    if has_support and not corroborated:
        missing.append("no second independent source class")
    if not covered:
        missing.append("ready sources not queried: " + ", ".join(unchecked_sources or []))
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
