"""Triage pre-flight — land the record, then build the dynamic prompt.

One entry point, shared by every live caller (the `demo_hunt` runner and the
connector's `chat_turn` dispatch), so the agent loop always starts from the
same grounded footing:

    1. Fetch the FULL raw record (we need the embedded ``sourcedata`` /
       ``associated_events`` the pruned ``get_record`` projection drops — that
       is where the driving-event evidence lives).
    2. Normalize → classify → ``build_triage_prompt`` (layers 0–2).
    3. Emit a short trail of *activity* events (normalize → classify → ground)
       so the widget/CLI can show the analyst what the backend did before the
       model said a word.

Returns the same dict ``build_triage_prompt`` does, plus the ``raw`` record, so
the caller can reuse the classification + facts for its own UI:

    {"system", "normalized", "scenario_id", "scenario_title", "raw"}

The fetch is best-effort: if no live FSR is configured (dev/offline) or the
GET fails, we fall back to building the prompt from whatever ``raw`` we were
handed (possibly empty) so the caller never has to special-case it — a missing
record degrades to plain triage, never an exception.
"""
from __future__ import annotations

from typing import Any, Callable

from .intents import DIRECTIVE, classify_message, gate_directive
from .triage_normalize import _RELATED_ALERT_KEYS, normalize_record
from .triage_prompt import build_triage_prompt

# An activity-event sink: called with a small JSON-serializable dict per phase.
EmitFn = Callable[[dict[str, Any]], None]

# Cap on member-alert fetches when recovering a case's SIEM incident id — a
# case rarely has more than a couple FortiSIEM-sourced alerts and we stop at
# the first hit, so this only bounds the pathological wide-case scan.
_MAX_ALERT_BACKFILL = 3


def _activity(emit: EmitFn | None, phase: str, message: str, **extra: Any) -> None:
    if emit is None:
        return
    try:
        emit({"type": "activity", "phase": phase, "message": message, **extra})
    except Exception:  # noqa: BLE001 — telemetry must never break the turn
        pass


def _iri_to_path(target: str) -> str:
    """Normalize ``module:uuid`` / ``module/uuid`` / a full IRI to an API path,
    matching the shorthand ``get_record`` already accepts."""
    s = (target or "").strip().split("?", 1)[0]
    head = s.split(":", 1)[0]
    if ":" in s and "/" not in head:
        mod, _, rest = s.partition(":")
        return f"/api/3/{mod.strip()}/{rest.strip()}"
    s = s.lstrip("/")
    if s.startswith("api/"):
        return "/" + s
    # bare `module/uuid`
    return "/api/3/" + s


def fetch_raw_record(target: str) -> dict[str, Any] | None:
    """GET the full hydrated record (relationships inline), unsummarized.

    Returns the raw JSON dict on a 200, else ``None``. Unlike the
    ``get_record`` tool this does NOT prune/summarize — the normalizer needs
    the verbatim ``sourcedata`` blob that the pruned projection strips.
    """
    from fsr_playbooks.mcp_server import _shared

    client = _shared._live_client()
    if client is None:
        return None
    path = _iri_to_path(target)
    url = f"{client.base_url}{path}?$relationships=true"
    try:
        r = client.session.get(url, verify=client.verify_ssl)
        if r.status_code != 200:
            return None
        data = r.json()
        return data if isinstance(data, dict) else None
    except Exception:  # noqa: BLE001
        return None


def _member_alert_iri(entry: Any) -> str | None:
    """The API path of an inlined member-alert entry — a dict (``iri``/``@id``)
    or a bare IRI string."""
    if isinstance(entry, str) and entry.strip():
        return entry.strip()
    if isinstance(entry, dict):
        for k in ("iri", "@id"):
            v = entry.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
    return None


def backfill_siem_incident_id(
    raw: dict[str, Any],
    *,
    fetch: Callable[[str], dict[str, Any] | None] = fetch_raw_record,
    emit: EmitFn | None = None,
) -> dict[str, Any]:
    """Recover a case's native FortiSIEM incident id and inline it into ``raw``.

    A case/incident never carries its own ``sourcedata.incident_data.incidentId``
    — that lives on its FortiSIEM-sourced *member alerts*, and a
    $relationships=true fetch returns those alerts THIN (no ``sourcedata``). So
    the normalizer can't see the id and the agent ends up passing the FortiSOAR
    record id to SIEM incident ops, which the engine rejects ("Invalid Incident
    Id").

    Here we fetch member alerts (best-effort, capped, stop at first hit), and
    when one yields an ``incidentId`` we splice its hydrated ``sourcedata`` back
    into the matching member entry in ``raw`` so ``normalize_record`` surfaces
    the id downstream. No-op when the record already exposes an incident id, has
    no member alerts, or no live FSR is reachable. Mutates and returns ``raw``.
    """
    if not isinstance(raw, dict):
        return raw
    # already resolvable (record-level id, or a member alert arrived hydrated)?
    if normalize_record(raw).get("incident_id"):
        return raw

    fetched = 0
    for key in _RELATED_ALERT_KEYS:
        members = raw.get(key)
        if not isinstance(members, list):
            continue
        for idx, entry in enumerate(members):
            if fetched >= _MAX_ALERT_BACKFILL:
                return raw
            iri = _member_alert_iri(entry)
            if not iri:
                continue
            fetched += 1
            full = fetch(iri)
            if not isinstance(full, dict):
                continue
            sd = full.get("sourcedata") or full.get("sourceData")
            if not sd:
                continue
            # splice the hydrated sourcedata (+ source) onto the member entry so
            # the normalizer reads the incidentId from it.
            hydrated = dict(entry) if isinstance(entry, dict) else {"iri": iri}
            hydrated["sourcedata"] = sd
            if full.get("source") and not hydrated.get("source"):
                hydrated["source"] = full.get("source")
            members[idx] = hydrated
            if normalize_record(raw).get("incident_id"):
                _activity(emit, "resolve",
                          "Resolved FortiSIEM incident id from member alert",
                          incident_id=normalize_record(raw).get("incident_id"))
                return raw
    return raw


def triage_preflight(
    target: str | None = None,
    *,
    raw_record: dict[str, Any] | None = None,
    user_message: str | None = None,
    emit: EmitFn | None = None,
) -> dict[str, Any]:
    """Run pre-flight for a record and return the dynamic-prompt bundle.

    Pass either ``target`` (``module:uuid`` / IRI — we fetch it) or a
    pre-fetched ``raw_record`` (the connector already has the entity in hand
    and may not want a second GET). ``emit`` receives one activity event per
    phase for live transparency.

    ``user_message`` (P3 low-signal gate): when supplied, the message is
    classified (``trivial`` / ``continue`` / ``directive``) and, for the two
    low-signal classes, a gate directive is appended to the system prompt so
    the agent orients/advances instead of launching a full auto-investigation.
    The bundle carries ``message_class`` so callers can branch their UI too.
    """
    raw = raw_record
    if raw is None and target:
        _activity(emit, "fetch", f"Pulling record {target}")
        raw = fetch_raw_record(target)
    if not isinstance(raw, dict):
        raw = {}

    # Recover the native FortiSIEM incident id from a member alert before we
    # normalize, so SIEM incident ops get the id the engine expects (not the
    # FortiSOAR record id). Best-effort; no-op offline or when already present.
    raw = backfill_siem_incident_id(raw, emit=emit)

    _activity(emit, "normalize", "Normalizing record")
    bundle = build_triage_prompt(raw)
    norm = bundle.get("normalized") or {}

    ind = norm.get("indicators", {}) or {}
    ip_n = len(ind.get("ips") or [])
    host_n = len(ind.get("hosts") or [])
    ev_n = len(norm.get("evidence_events") or [])
    _activity(
        emit, "classify",
        f"Classified as {bundle.get('scenario_title') or bundle.get('scenario_id')}",
        scenario_id=bundle.get("scenario_id"),
    )
    _activity(
        emit, "ground",
        f"Grounded on {ip_n} IP(s), {host_n} host(s), {ev_n} driving event(s)",
        ips=ip_n, hosts=host_n, events=ev_n,
    )

    # P3 — low-signal input gate. Classify the analyst's message and, for
    # trivial/continue, append a directive that suppresses the auto-hunt.
    msg_class = DIRECTIVE
    if user_message is not None:
        msg_class = classify_message(user_message)
        addend = gate_directive(msg_class, bundle.get("scenario_title"))
        if addend:
            bundle["system"] = (bundle.get("system") or "") + addend
            _activity(
                emit, "gate",
                f"Low-signal input ({msg_class}) — orienting instead of "
                f"auto-investigating",
                message_class=msg_class,
            )
    bundle["message_class"] = msg_class

    bundle["raw"] = raw
    return bundle


__all__ = ["triage_preflight", "fetch_raw_record",
           "backfill_siem_incident_id", "EmitFn"]
