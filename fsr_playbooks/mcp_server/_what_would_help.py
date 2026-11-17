"""X7: the "What would help" lines on an uncertain verdict card.

Computed from facts, never written by the model:

* a source TYPE that is not connected at all (no ticket system, no threat
  intelligence source), named only when the host told the turn which
  connectors are configured and the verdict has an unknown that type could
  settle;
* a connected source that failed this turn (every call to it errored);
* a data gap: a source was searched and every call came back empty.

At most three lines, each tied to one of the verdict's unknowns. Confident
verdicts get none. The wording uses the connector catalog's labels and never a
tool name or id.
"""
from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

MAX_LINES = 3

# Source types the "not connected" line can name: the analyst sentence for the
# gap, what the missing source would settle, and the words in an unknown that
# say the verdict is waiting on that kind of answer.
_TYPES: dict[str, dict[str, Any]] = {
    "tickets": {
        "gap": "No ticket system is connected",
        "benefit": "past tickets could show whether this activity was approved or already reported",
        "words": ("approv", "authoriz", "authoris", "change", "maintenance", "expected",
                  "owner", "prior", "previous", "earlier", "ticket", "legitimate",
                  "scheduled", "pentest", "penetration", "known to", "intended", "sanction"),
    },
    "intel": {
        "gap": "No threat intelligence source is connected",
        "benefit": "a reputation lookup could show whether this indicator is known to be malicious",
        "words": ("reputation", "malicious", "threat intel", "indicator", "ioc", "known bad",
                  "known-bad", "blocklist", "blacklist", "flagged", "campaign", "attribut",
                  "ip address", "domain", "hash", "url", "rated"),
    },
}
# Log sources are matched by the ready-source roster (tool-prefix families), not
# the connector roster, so they have their own entry and check.
_LOGS = {
    "gap": "No log source such as a SIEM or firewall log store is connected",
    "benefit": "session logs could show whether these connections completed and how much data moved",
    "words": ("logs", "log data", "log source", "sessions", "flows", "netflow", "firewall",
              "siem", "traffic", "bytes", "packet"),
}
_ORDER = ("tickets", "intel")


def _match_unknown(unknowns: list[str], words: Sequence[str]) -> str:
    for u in unknowns:
        low = u.lower()
        if any(w in low for w in words):
            return u
    return ""


_SEARCH_OP = re.compile(r"search|query|find|lookup|look_up|list|fetch|get_|hunt|retriev", re.I)


def _input_absent(args: dict[str, Any]) -> bool:
    """The call named its inputs and every one was blank, so the lookup had
    nothing to search for (an outbreak lookup that needs a campaign tag the
    alert did not carry). An op called with no `params` key at all is left
    alone: many reads take none."""
    params = args.get("params")
    if params is None and "params" not in args:
        return False
    if not isinstance(params, dict):
        return params in (None, "")
    return all(v in (None, "", [], {}) for v in params.values())


def _searched(entry: dict[str, Any]) -> bool:
    """A call that ran a search and matched nothing. A log-source tool is a
    search by nature; a connector operation counts only when its name says it
    reads (a create or action op that hands back an empty body searched
    nothing)."""
    if entry.get("empty") is not True:
        return False
    if str(entry.get("name") or "") != "run_op":
        return True
    args = entry.get("args") or {}
    if _input_absent(args):
        return False
    return bool(_SEARCH_OP.search(str(args.get("op") or args.get("operation") or "")))


def _plural(labels: list[str], one: str, many: str) -> str:
    return one if len(labels) == 1 else many


def _join(labels: list[str]) -> str:
    if len(labels) <= 1:
        return "".join(labels)
    return ", ".join(labels[:-1]) + " and " + labels[-1]


def build(*, disposition: str, unknowns: list[str], registry: dict[str, dict[str, Any]],
          ready_sources: dict[str, str] | None,
          ready_connectors: dict[str, dict[str, str]] | None) -> list[dict[str, Any]]:
    """The what-would-help entries for one verdict card, [] when none apply.

    ``ready_connectors`` is None when the host did not report which connectors
    are configured: then nothing can be said about a type being absent."""
    unknowns = [u.strip() for u in unknowns if isinstance(u, str) and u.strip()]
    if disposition != "needs_more_info" or not unknowns:
        return []
    out: list[dict[str, Any]] = []

    # (a) a source type with no connector at all.
    if ready_sources is not None and not ready_sources:
        unknown = _match_unknown(unknowns, _LOGS["words"])
        if unknown:
            out.append({"kind": "logs", "state": "not_connected",
                        "line": f"{_LOGS['gap']}; {_LOGS['benefit']}.",
                        "unknown": unknown, "sources": []})
    if ready_connectors is not None:
        present = {m.get("kind") for m in ready_connectors.values()}
        for kind in _ORDER:
            if kind in present:
                continue
            spec = _TYPES[kind]
            unknown = _match_unknown(unknowns, spec["words"])
            if unknown:
                out.append({"kind": kind, "state": "not_connected",
                            "line": f"{spec['gap']}; {spec['benefit']}.",
                            "unknown": unknown, "sources": []})

    # Per source label: the calls made to it this turn.
    calls: dict[str, list[dict[str, Any]]] = {}
    for entry in registry.values():
        entry = entry or {}
        name = str(entry.get("name") or "")
        label = ""
        for prefix, lbl in (ready_sources or {}).items():
            if name.startswith(prefix):
                label = lbl
        conn = str((entry.get("args") or {}).get("connector") or "")
        if conn and conn in (ready_connectors or {}):
            label = (ready_connectors or {})[conn].get("label") or conn
        if label:
            calls.setdefault(label, []).append(entry)

    # (b) connected, but every call to it failed.
    failed = sorted(lbl for lbl, es in calls.items() if all(e.get("ok") is False for e in es))
    if failed:
        out.append({"kind": "source_failed", "state": "failed",
                    "line": (f"{_join(failed)} "
                             + _plural(failed,
                                       "returned an error this turn, so its answer is "
                                       "missing; fixing the connection would let me check it.",
                                       "returned an error this turn, so their answers are "
                                       "missing; fixing the connections would let me check them.")),
                    "unknown": unknowns[0], "sources": failed})
    # (c) searched, nothing came back.
    # Only a search that ran and matched nothing counts: an error or an
    # operation the connector does not offer is not "searched, nothing".
    empty = sorted(lbl for lbl, es in calls.items()
                   if any(_searched(e) for e in es)
                   and not any(e.get("ok") is True and e.get("thin") is not True for e in es)
                   and lbl not in failed)
    if empty:
        out.append({"kind": "data_gap", "state": "no_data",
                    "line": (f"{_join(empty)} "
                             + _plural(empty,
                                       "was searched and returned nothing, so there is no data "
                                       "from it either way; a wider time window or another "
                                       "source of the same data would help.",
                                       "were searched and returned nothing, so there is no data "
                                       "from them either way; a wider time window or another "
                                       "source of the same data would help.")),
                    "unknown": unknowns[0], "sources": empty})
    return out[:MAX_LINES]
