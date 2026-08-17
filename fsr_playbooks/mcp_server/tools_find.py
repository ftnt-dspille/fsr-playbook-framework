"""One discovery tool over the fragmented `find_*` / `search_*` cluster.

Phase 1 of the tool-surface consolidation (assessment 1b): the model was
choosing between 14+ overlapping discovery variants whose semantic boundaries
(containment vs enrichment vs record; find_api_example vs search_api_examples)
are taught nowhere. `find(kind, query, ...)` is the single entry point; the
existing specialized tools stay registered during the migration so nothing the
prompts or fixtures rely on breaks, and tool-gate arbitrates when the old
names are dropped from the advertised slice.
"""
from __future__ import annotations

from typing import Any

from ._shared import mcp

FIND_KINDS = (
    "connector", "operation", "action", "example", "recipe",
    "api", "jinja", "playbook",
)


@mcp.tool()
def find(kind: str, query: str = "", connector: str = "",
         target_type: str = "", action_type: str = "",
         module: str = "", limit: int = 10) -> dict[str, Any]:
    """ONE search tool for every discovery catalog -- pick `kind`, pass a
    plain-language `query`; each result names the follow-up call that uses it.

    Which kind to pick: `action` = what can be done to a TARGET on THIS
    instance, only what is configured and healthy -- containment (tier 3+,
    stage via emit_action_card), enrichment (read-only, run via run_op), or
    record writes (comment/update/create, tier 3+); prefer it over
    connector+operation whenever the analyst named a target or asked to act;
    filter with `target_type` (ip/host/user/url/domain/hash/file/email) and
    `action_type`, and read each result's `action_type` for its family.
    `connector` = which integration handles X; follow with kind=operation.
    `operation` = one named connector's ops (requires `connector`); follow
    with get_op_schema then run_op. `example` = a worked call (`connector`
    set: that connector's ops; empty: vendor API docs). `recipe` = a
    step-sequence pattern for a build intent. `api` = a vendor product's raw
    API surface for HTTP-fallback steps. `jinja` = a filter for a transform.
    `playbook` = existing playbooks matching the query.
    """
    k = (kind or "").strip().lower()
    if k not in FIND_KINDS:
        return {"ok": False, "code": "unknown_kind",
                "message": f"kind {kind!r} not recognized",
                "valid_kinds": list(FIND_KINDS)}

    from . import (  # noqa: PLC0415 - late import avoids a registration cycle
        find_api_product,
        find_connector,
        find_containment_actions,
        find_enrichment_actions,
        find_jinja_filter,
        find_operation,
        find_operation_example,
        find_recipe,
        find_record_actions,
        search_api_examples,
        search_playbooks,
    )

    out: dict[str, Any]
    if k == "connector":
        out = find_connector(query, limit=limit)
    elif k == "operation":
        if not connector:
            return {"ok": False, "code": "missing_connector",
                    "message": "kind='operation' needs `connector` -- use "
                               "kind='connector' first to find its name"}
        out = find_operation(connector, query, limit=limit)
    elif k == "action":
        out = _find_actions(
            find_containment_actions, find_enrichment_actions,
            find_record_actions, query=query, target_type=target_type,
            action_type=action_type, module=module, limit=limit)
    elif k == "example":
        if connector:
            out = find_operation_example(connector, op=query or None,
                                         limit=limit)
        else:
            out = search_api_examples(query, limit=limit)
    elif k == "recipe":
        out = find_recipe(query, limit=limit)
    elif k == "api":
        out = find_api_product(query, limit=limit)
    elif k == "jinja":
        out = find_jinja_filter(query, limit=limit)
    else:  # playbook
        out = search_playbooks(query, limit=limit)
    if isinstance(out, dict):
        out.setdefault("kind", k)
        return out
    # A few catalogs (e.g. the jinja filter search) return a bare list.
    return {"kind": k, "results": out}


def _find_actions(containment, enrichment, record, *, query: str,
                  target_type: str, action_type: str, module: str,
                  limit: int) -> dict[str, Any]:
    """Merge the three action catalogs into one list with a typed field.

    The three-way split (containment / enrichment / record) was a boundary the
    model had to memorize; here it is data. `action_type` restricts to one
    family; otherwise containment + enrichment are both consulted (record only
    when explicitly asked or `module` names a write target), and every action
    is tagged with the family it came from.
    """
    fam = (action_type or "").strip().lower()
    valid = ("containment", "enrichment", "record")
    if fam and fam not in valid:
        return {"ok": False, "code": "unknown_action_type",
                "message": f"action_type {fam!r} not recognized",
                "valid_action_types": list(valid)}
    target = (target_type or query or "").strip()
    merged: list[dict[str, Any]] = []
    sections: dict[str, Any] = {}

    def _take(name: str, res: dict[str, Any]) -> None:
        sections[name] = {kk: vv for kk, vv in res.items() if kk != "actions"}
        for a in (res.get("actions") or [])[:limit]:
            row = dict(a)
            row["action_type"] = name
            merged.append(row)

    if fam in ("", "containment"):
        _take("containment", containment(target_type=target, limit=limit))
    if fam in ("", "enrichment"):
        _take("enrichment", enrichment(target_type=target, limit=limit))
    if fam == "record" or (not fam and module):
        res = record(action=query, module=module or "alerts")
        if res.get("ok") is False:      # query was prose, not an action name
            res = record(action="", module=module or "alerts")
        _take("record", res)
    return {"target_type": target, "action_type": fam or "all",
            "actions": merged[: limit * 3 if not fam else limit],
            "count": len(merged), "sections": sections}
