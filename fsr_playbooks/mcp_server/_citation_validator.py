"""Citation validation for structured verdicts.

Verdicts cite evidence via tool_use ids. This module enforces that every cited
id is a real tool call from THIS turn with a successful result (to prevent
citations of errors or emit_* calls that are not evidence).

Per-turn evidence tracking: providers create a TurnEvidence object in stream(),
set it via contextvars (async-safe), and include it in suspended-session state
for resume. Deliberately minimal: only tracks id -> (name, ok), no full result
bodies (those are in history already).
"""
from __future__ import annotations

import contextvars
from collections.abc import Callable
from typing import Any

# Async-safe context variable for the current turn's evidence registry.
# contextvars work across async boundaries, unlike threading.local.
_turn_evidence: contextvars.ContextVar[TurnEvidence | None] = contextvars.ContextVar(
    "turn_evidence", default=None
)


class TurnEvidence:
    """Per-turn evidence registry for citation validation.

    Tracks tool_use_ids and their success/failure status. Set via contextvars
    so citations can validate evidence within emit_verdict. Included in
    suspended-session state so citations survive approval-gate resume.
    """

    def __init__(self) -> None:
        self._registry: dict[str, dict[str, Any]] = {}
        # Verdict cards delivered this turn, in order. The autonomy policy
        # (llm/autonomy.py) tests the verdict an action rests on, so it needs
        # the delivered card, not the model's prose about it.
        self._verdicts: list[dict[str, Any]] = []
        # Committed verdicts refused because every cited source was thin. The
        # first is the coverage round; after it the disposition is capped.
        self._thin_refusals = 0

    def thin_refusals(self) -> int:
        return self._thin_refusals

    def note_thin_refusal(self) -> None:
        self._thin_refusals += 1

    def register(self, tool_use_id: str, tool_name: str, success: bool,
                 args: dict[str, Any] | None = None,
                 finding: dict[str, Any] | None = None,
                 thin: bool | None = None, empty: bool | None = None) -> None:
        """Record that a tool call succeeded or failed. ``args`` is kept so a
        policy can tell WHAT a cited call looked up (its target), not just
        which tool ran; ``finding`` is what a threat-intel lookup SAID (see
        ``set_result_reader``)."""
        entry: dict[str, Any] = {"name": tool_name, "ok": success}
        if isinstance(args, dict):
            entry["args"] = _bounded_args(args)
        if isinstance(finding, dict):
            entry["finding"] = finding
        if thin is not None:
            entry["thin"] = bool(thin)
        if empty:
            entry["empty"] = True
        self._registry[tool_use_id] = entry

    def record_verdict(self, card: dict[str, Any]) -> None:
        """Record a verdict card that was delivered (validated + emitted)."""
        if isinstance(card, dict):
            self._verdicts.append(dict(card))

    def verdicts(self) -> list[dict[str, Any]]:
        return [dict(v) for v in self._verdicts]

    def valid_ids(self) -> dict[str, dict[str, Any]]:
        """Return the registry (id -> {name, ok[, args]})."""
        return dict(self._registry)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for suspended-session storage."""
        return {"_registry": dict(self._registry),
                "_verdicts": list(self._verdicts),
                "_thin_refusals": self._thin_refusals}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TurnEvidence:
        """Deserialize from suspended-session storage."""
        obj = cls()
        obj._registry = data.get("_registry", {})
        obj._verdicts = list(data.get("_verdicts") or [])
        obj._thin_refusals = int(data.get("_thin_refusals") or 0)
        return obj


def result_is_thin(result: Any) -> bool:
    """True when a SUCCESSFUL call handed back nothing to reason from: no body,
    a typed empty (code no_events, empty true), a zero count or total, or an
    empty events/results/records/data list. Used only for the evidence cap."""
    if result is None:
        return True
    if isinstance(result, list):
        return len(result) == 0
    if not isinstance(result, dict):
        return False
    if result.get("ok") is False or result.get("error"):
        return True
    if result.get("code") == "no_events" or result.get("empty") is True:
        return True
    for k in ("count", "total", "total_count", "returned", "event_count"):
        v = result.get(k)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return v <= 0
    for k in ("events", "results", "records", "data", "items", "matches"):
        if k in result:
            return result[k] in (None, [], {}, "")
    return False


_NO_SEARCH_FLAGS = ("skipped", "refused", "noop", "no_op", "not_run", "not_executed")
#: Structured status values (an enum a connector sets, not prose).
_NO_SEARCH_STATUS = frozenset({"skipped", "refused", "noop", "no-op", "no_op",
                               "not_run", "not_executed"})


def result_did_not_search(result: Any) -> bool:
    """True when a call that did not fail still never ran its search: it was
    skipped or refused, or was a no-op, by a structured flag or status. A
    connector that explains itself only in prose is not read: that call stays
    counted as a search. Such an empty body is not "searched and found
    nothing"."""
    if not isinstance(result, dict):
        return False
    if any(result.get(f) is True for f in _NO_SEARCH_FLAGS):
        return True
    if str(result.get("status") or "").strip().lower() in _NO_SEARCH_STATUS:
        return True
    data = result.get("data")
    return isinstance(data, dict) and result_did_not_search(data)


def result_is_empty_set(result: Any) -> bool:
    """True only for a search that RAN and matched nothing: a typed empty, a zero
    count or an empty events/results/records list. An error, an unavailable
    operation or a missing body is not an empty set (X7 must not say a source
    "returned nothing" when it never searched)."""
    if isinstance(result, list):
        return len(result) == 0
    if not isinstance(result, dict):
        return False
    if result.get("ok") is False or result.get("error"):
        return False
    if result_did_not_search(result):
        return False
    if result.get("code") == "no_events" or result.get("empty") is True:
        return True
    for k in ("count", "total", "total_count", "returned", "event_count"):
        v = result.get(k)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return v <= 0
    for k in ("events", "results", "records", "data", "items", "matches"):
        if k in result:
            return result[k] in (None, [], {}, "")
    return False


def _bounded_args(args: dict[str, Any], limit: int = 2000) -> dict[str, Any]:
    """The call's args, or a stub when they are too big to keep per call (a
    whole playbook YAML is not a lookup target)."""
    import json
    try:
        blob = json.dumps(args, default=str)
    except Exception:  # noqa: BLE001
        return {}
    return args if len(blob) <= limit else {"_truncated": blob[:limit]}


def set_turn_evidence(evidence: TurnEvidence | None) -> None:
    """Set the current turn's evidence context (called by providers at stream start)."""
    _turn_evidence.set(evidence)


def get_turn_evidence() -> TurnEvidence | None:
    """Get the current turn's evidence context (called by emit_verdict for citations)."""
    return _turn_evidence.get()


# Log sources this turn can reach, as {tool-name prefix: analyst label}, e.g.
# {"siem_": "FortiSIEM"}. Set by the host (the connector knows which source
# connectors are installed and healthy). Used by the evidence cap to name the
# ready sources a thin verdict never queried.
_turn_ready_sources: contextvars.ContextVar[dict[str, str] | None] = contextvars.ContextVar(
    "turn_ready_sources", default=None
)


def set_turn_ready_sources(sources: dict[str, str] | None) -> None:
    # None = the host did not report; {} = it did and nothing is ready.
    _turn_ready_sources.set(dict(sources) if sources is not None else None)


# Configured connectors this turn can query that are not log sources, as
# {connector name: {"label": analyst label, "kind": "tickets" | "intel"}}.
# Set by the host from connector metadata (the catalog category). A log source
# is spotted by its tool prefix; these are reached through the generic operation
# runner, so a call counts when its `connector` argument names the connector.
_turn_ready_connectors: contextvars.ContextVar[dict[str, dict[str, str]] | None] = (
    contextvars.ContextVar("turn_ready_connectors", default=None)
)

_KINDS = ("tickets", "intel")


def set_turn_ready_connectors(sources: dict[str, dict[str, str]] | None) -> None:
    clean = {str(c): {"label": str((v or {}).get("label") or c),
                      "kind": str((v or {}).get("kind") or "")}
             for c, v in (sources or {}).items()
             if isinstance(v, dict) and (v or {}).get("kind") in _KINDS}
    # None = the host did not report which connectors are configured (nothing
    # can be said about a missing type); {} = it did and there are none.
    _turn_ready_connectors.set(clean if sources is not None else None)


# U6: display labels for connector ids, {connector name: catalog label}, from
# the box's connector catalog. The enhancement offer carries the labels of the
# connectors its diff names, so the card never shows a bare id. The host hands
# either the map or a zero-argument reader of it: the reader is called only when
# an offer is emitted, so a turn that never offers a change never reads the
# catalog. None = the host did not report (the widget then humanizes the id).
_turn_connector_labels: contextvars.ContextVar[
    dict[str, str] | Callable[[], dict[str, str] | None] | None] = (
    contextvars.ContextVar("turn_connector_labels", default=None)
)


def set_turn_connector_labels(
        labels: dict[str, str] | Callable[[], dict[str, str] | None] | None) -> None:
    _turn_connector_labels.set(labels)


def connector_labels_for(ids: Any) -> dict[str, str]:
    """The catalog labels of the connector ids in ``ids`` the host knows, {} when
    it reported none or its reader failed. An id with no catalog label is left
    out, never guessed."""
    held = _turn_connector_labels.get()
    try:
        known = held() if callable(held) else held
    except Exception:  # noqa: BLE001 - a label is cosmetic; never fail an offer over it
        known = None
    clean = {str(k): v.strip() for k, v in (known or {}).items()
             if isinstance(v, str) and v.strip()}
    return {i: clean[i] for i in sorted({str(x) for x in ids}) if i in clean}


def what_would_help(disposition: str, unknowns: list[str],
                    registry: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """X7: the card's "What would help" entries (see ``_what_would_help``)."""
    from ._what_would_help import build  # noqa: PLC0415
    return build(disposition=disposition, unknowns=unknowns, registry=registry,
                 ready_sources=_turn_ready_sources.get(),
                 ready_connectors=_turn_ready_connectors.get())


def _ready_source_split(registry: dict[str, dict[str, Any]]) -> tuple[list[str], list[str]]:
    """(checked, unchecked) labels of this turn's ready sources, by whether the
    turn's registry holds a call under that source's tool prefix (log sources)
    or a call naming that connector (ticket and intel connectors)."""
    sources = _turn_ready_sources.get() or {}
    called = [str((e or {}).get("name") or "") for e in registry.values()]
    checked = {label for prefix, label in sources.items()
               if any(n.startswith(prefix) for n in called)}
    unchecked = {label for prefix, label in sources.items()
                 if not any(n.startswith(prefix) for n in called)}
    queried = {str(((e or {}).get("args") or {}).get("connector") or "")
               for e in registry.values()}
    for connector, meta in (_turn_ready_connectors.get() or {}).items():
        (checked if connector in queried else unchecked).add(meta["label"])
    return sorted(checked), sorted(unchecked)


def _unchecked_kinds(registry: dict[str, dict[str, Any]]) -> set[str]:
    queried = {str(((e or {}).get("args") or {}).get("connector") or "")
               for e in registry.values()}
    return {m["kind"] for c, m in (_turn_ready_connectors.get() or {}).items()
            if c not in queried}


def unchecked_ready_sources(registry: dict[str, dict[str, Any]]) -> list[str]:
    """Labels of ready sources with no call in this turn's registry."""
    return _ready_source_split(registry)[1]


def checked_ready_sources(registry: dict[str, dict[str, Any]]) -> list[str]:
    """Labels of ready sources this turn queried (the verdict card's ledger)."""
    return _ready_source_split(registry)[0]


def unchecked_ready_note(registry: dict[str, dict[str, Any]]) -> str:
    """The per-round tail note naming ready sources not yet queried, or "".

    Ticket and intel connectors join the note only once the turn has queried a
    source itself, i.e. the agent chose to investigate. A plain question ("what
    is this alert's name") reads the record and answers; nudging it toward every
    intel connector turned a one-call lookup into a fifteen-call investigation
    that sometimes never answered the question."""
    checked, names = _ready_source_split(registry)
    investigating = bool(checked) or any(
        str((e or {}).get("name") or "") == "run_op" for e in registry.values())
    if not investigating:
        conn_labels = {m["label"] for m in (_turn_ready_connectors.get() or {}).values()}
        names = [n for n in names if n not in conn_labels]
    if not names:
        return ""
    note = ("[ready, not yet queried this turn: " + ", ".join(names)
            + ". Query them before concluding, or say why not.")
    if investigating and "tickets" in _unchecked_kinds(registry):
        empty = any((e or {}).get("thin") is True for e in registry.values())
        note += (" Earlier tickets can hold the deciding fact (an approved test,"
                 " a known owner, a prior report)"
                 + (", and the log searches so far came back empty" if empty else "")
                 + ". Search the ticket system by the host name and by the"
                 " indicator before you conclude.")
    return note + "]"


# (connector, op, params, result) -> {verdict, severity, source, ...} | None.
# Installed by the host (the Agentic Assistant connector installs its threat-intel
# card reader), so the autonomy policy can test what a cited lookup SAID, not
# just that one ran: live, a block was justified by lookups that rated the
# target clean or found nothing at all.
ResultReader = Callable[[str, str, dict[str, Any], dict[str, Any]], "dict[str, Any] | None"]
_RESULT_READER: ResultReader | None = None

_FINDING_KEYS = ("indicator", "source", "verdict", "severity", "score_str")


def set_result_reader(reader: ResultReader | None) -> None:
    global _RESULT_READER
    _RESULT_READER = reader


def read_finding(tool_name: str, args: dict[str, Any] | None,
                 result: Any) -> dict[str, Any] | None:
    """What a successful lookup said, via the installed reader. None when there
    is no reader, it is neither a run_op nor a declared MCP intel tool, or the
    reader cannot tell. A reader bug never fails the call.

    A declared MCP intel tool reaches the reader as connector ``mcp:<server>``,
    op ``<tool>``, its own arguments as params, and its result wrapped in the
    run_op envelope (``{"ok": True, "data": result}``)."""
    if _RESULT_READER is None or not isinstance(args, dict):
        return None
    if tool_name == "run_op" and isinstance(result, dict):
        params = args.get("params")
        if not isinstance(params, dict):
            params = {}
        connector = str(args.get("connector") or "")
        op = str(args.get("op") or args.get("operation") or "")
    elif tool_name.startswith("mcp_") and "__" in tool_name:
        from .materializer import turn_intel_mcp_tools
        if tool_name not in turn_intel_mcp_tools():
            return None
        server, op = tool_name[len("mcp_"):].split("__", 1)
        connector, params, result = f"mcp:{server}", args, {"ok": True, "data": result}
    else:
        return None
    try:
        rec = _RESULT_READER(connector, op, params, result)
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(rec, dict):
        return None
    return {k: rec.get(k) for k in _FINDING_KEYS if rec.get(k) is not None}


def register_tool_result(tool_use_id: str, tool_name: str, success: bool,
                         args: dict[str, Any] | None = None,
                         result: Any = None) -> None:
    """Record that a tool call succeeded or failed.

    Called by the provider as tool results arrive. Routes to the contextvar
    based TurnEvidence object.
    """
    evidence = get_turn_evidence()
    if evidence is not None:
        finding = read_finding(tool_name, args, result) if success else None
        thin = result_is_thin(result) if (success and result is not None) else None
        empty = result_is_empty_set(result) if success else False
        evidence.register(tool_use_id, tool_name, success, args, finding, thin, empty)


def record_delivered_verdict(card: dict[str, Any]) -> None:
    """Note a verdict card delivered this turn (called by emit_verdict)."""
    evidence = get_turn_evidence()
    if evidence is not None:
        evidence.record_verdict(card)


def clear_tool_registry() -> None:
    """Clear the tool registry at turn start (creates new TurnEvidence).

    Providers should call this at stream() start, then set_turn_evidence(evidence).
    Kept for backward compat but new code should use set_turn_evidence() directly.
    """
    set_turn_evidence(TurnEvidence())


# Emit tools whose results are NOT valid evidence (they're actions, not findings).
_EMIT_TOOLS = frozenset({
    "emit_choice_card", "emit_action_card", "emit_manual_input",
    "emit_capability_gap_card", "emit_playbook_offer",
    "emit_enhancement_offer", "emit_card",
    # Legacy names (consolidated into emit_card)
    "emit_decision_step",
})


def rated_intel_ids(evidence: TurnEvidence | None = None) -> list[str]:
    """The tool_use ids of this turn's threat-intelligence lookups that
    succeeded AND the installed reader rated (``finding`` with a severity) --
    i.e. a lookup that actually SAID something about its target.

    A verdict that concludes ``true_positive`` is nudged to cite one of these
    in-turn, so the human-facing card shows its evidence and the model forms
    the habit. (The autonomy policy itself credits a rated lookup ABOUT the
    action's target from this same registry whether or not the verdict threaded
    its id in -- ``llm/autonomy.py`` evidence rule -- so a dropped citation no
    longer silently loses a confirmed block; the two read the same registry and
    cannot disagree.)"""
    evidence = get_turn_evidence() if evidence is None else evidence
    if evidence is None:
        return []
    out: list[str] = []
    for eid, entry in evidence.valid_ids().items():
        finding = entry.get("finding")
        if entry.get("ok") is True and isinstance(finding, dict) and finding.get("severity"):
            out.append(eid)
    return out


def validate_evidence_ids(evidence_ids: list[str]) -> dict[str, Any] | None:
    """Validate that all evidence ids are valid tool_use ids from this turn.

    Returns an error dict (ok=False) if validation fails, None if all ids are
    valid. Checks that:
      1. Each id is a known tool_use_id
      2. The tool call succeeded (ok=True)
      3. The tool is NOT an emit_* (which are actions, not evidence)
    """
    from ._shared import _err

    evidence = get_turn_evidence()
    if evidence is None:
        return _err("no_turn_evidence", "No turn evidence context found")
    return check_evidence_ids(evidence, evidence_ids)


def check_evidence_ids(evidence: TurnEvidence,
                       evidence_ids: list[str]) -> dict[str, Any] | None:
    """`validate_evidence_ids` against an explicit registry rather than the
    turn's context var. Workflows (`fsr_playbooks.workflows`) hold their own
    TurnEvidence and validate findings through this same rule."""
    from ._shared import _err

    registry = evidence.valid_ids()

    # Collect bad ids for a single refusal with suggestions.
    unknown_ids: list[str] = []
    failed_ids: list[str] = []
    emit_ids: list[str] = []

    for eid in evidence_ids:
        eid_str = str(eid or "").strip()
        if not eid_str:
            unknown_ids.append(eid)
            continue

        info = registry.get(eid_str)
        if info is None:
            unknown_ids.append(eid_str)
            continue

        if info.get("ok") is not True:
            failed_ids.append(eid_str)
            continue

        tool_name = info.get("name") or ""
        if tool_name in _EMIT_TOOLS:
            emit_ids.append(eid_str)

    # Assemble error message if any bad ids found.
    parts: list[str] = []
    if unknown_ids:
        parts.append(
            f"Unknown tool_use_ids: {unknown_ids}. These are not valid ids from "
            f"this turn.")
        # Live (session health 2026-09-30): models cite the TOOL, not the call
        # -- `functions.get_record`, `multi_tool_use.parallel#1` -- and needed a
        # retry to find the ids. Name the calls that tool made.
        for uid in unknown_ids:
            tool = str(uid or "").split("#")[0].rsplit(".", 1)[-1]
            calls = [eid for eid, info in registry.items()
                     if info.get("name") == tool and info.get("ok") is True]
            if calls:
                parts.append(f"'{uid}' names the tool {tool}, not a call: cite "
                             f"one of its call ids {calls[:5]}.")
    if failed_ids:
        parts.append(
            f"Failed tool calls: {failed_ids}. Evidence must come from successful "
            f"tool results.")
    if emit_ids:
        parts.append(
            f"Emit tools are actions, not evidence: {emit_ids}. Use tool_use_ids "
            f"from investigation/enrichment tools (get_record, search_*, "
            f"siem_*, faz_*, run_op, mcp_* read tools).")

    if not parts:
        return None

    message = " ".join(parts)
    suggestions = []
    if unknown_ids or failed_ids:
        # List valid tool_use_ids that succeeded.
        # Each id with the tool it called, so a claim can be matched to the
        # call that supports it.
        valid_ids = [
            f"{eid} ({info.get('name') or '?'})" for eid, info in registry.items()
            if info.get("ok") is True and (info.get("name") or "") not in _EMIT_TOOLS
        ]
        if valid_ids:
            suggestions.append(
                f"Valid tool_use_ids from this turn: {', '.join(valid_ids[:10])} "
                f"{'...' if len(valid_ids) > 10 else ''}")

    return _err("invalid_evidence_ids", message, suggestions=suggestions)
