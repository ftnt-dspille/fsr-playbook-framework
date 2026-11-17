"""Our own usage notes for vendor connector operation parameters.

The op catalog is built from each vendor connector's info.json, so the only
help a model sees for a parameter is the vendor's label. Some vendor
parameters are passed through verbatim to a remote API and fail silently when
given the wrong shape (a filter that is ignored, a timestamp that is
rejected). A note here is OUR guidance, shown next to the vendor description,
never in place of it.

To add a note: add one entry to ``OP_PARAM_NOTES`` keyed by
``(connector name, operation, parameter)``. Keep it to one or two lines with
one example. ``test_op_param_notes`` fails if a key no longer names a real
connector/op/param in the catalog, so notes cannot rot.

The table is read at render time (never stored in the catalog), so a note
shows up without re-warming a box's catalog. Both ``get_op_schema`` and the
op signature in ``find(kind='operation')`` call :func:`note_for`.
"""
from __future__ import annotations

from typing import Any

NOTE_PREFIX = "Guidance (ours, not the vendor's): "

_SNOW_QUERY = (
    "this value is appended to the request as a raw query string, so a bare "
    "encoded query is silently ignored and an unfiltered, oldest-first page "
    "comes back. Name the parameter: "
    "sysparm_query=short_descriptionLIKEphishing^active=true "
    "(add ^ORDERBYDESCsys_created_on for newest first)."
)

OP_PARAM_NOTES: dict[tuple[str, str, str], str] = {
    ("servicenow", "advance_search", "adv_query"): _SNOW_QUERY,
    ("servicenow", "get_SIR", "adv_query"): _SNOW_QUERY,
    ("servicenow", "fetch_incidents", "adv_query"): (
        "appended as a raw query string after the op's own sysparm_query "
        "(the created window), so a sysparm_query here is ignored. Use plain "
        "field=value pairs, e.g. priority=1&state=2. To search by text, use "
        "advance_search."
    ),
    ("servicenow", "fetch_incidents", "start_time"): (
        "ISO-shaped with a T between date and time, e.g. 2024-05-01T00:00:00; "
        "a value without the T fails."
    ),
    ("servicenow", "fetch_incidents", "end_time"): (
        "ISO-shaped with a T between date and time, e.g. 2024-05-02T00:00:00; "
        "a value without the T fails."
    ),
}


def note_for(connector: str, op: str, param: str) -> str | None:
    """The marked note for one parameter, or None."""
    text = OP_PARAM_NOTES.get((connector, op, param))
    return f"{NOTE_PREFIX}{text}" if text else None


def annotate(connector: str, op: str, params: list[dict[str, Any]]) -> None:
    """Set ``note`` on every param row (in place) that has one."""
    for p in params:
        n = note_for(connector, op, p.get("param_name") or "")
        if n:
            p["note"] = n
