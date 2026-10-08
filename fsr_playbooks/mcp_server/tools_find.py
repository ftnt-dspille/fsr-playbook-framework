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
    # B3a: three corpus searches that were their own tools, called 0 times in
    # 287 live sessions while each cost a schema on every turn.
    "step", "jinja_block", "filter_usage",
    # A module's fields, from the catalog -- the build-side answer to "what is
    # the alert's destination IP called?" (record reads are triage tools).
    "field",
)


@mcp.tool()
def find(kind: str, query: str = "", connector: str = "",
         target_type: str = "", action_type: str = "",
         module: str = "", limit: int = 10) -> dict[str, Any]:
    """ONE search tool for every discovery catalog -- pick `kind`, pass a
    plain-language `query`; each result names the follow-up call that uses it.

    Which kind to pick: `action` = what can be done to a TARGET here, only what is
    configured and healthy -- containment (stage via emit_card
    card_type='action'), enrichment (run_op), record writes; prefer it when
    the analyst named a target or asked to act; filter with `target_type`
    (ip/host/user/url/domain/hash/file/email) and `action_type`. `connector`
    = which integration handles X, then `operation` (needs `connector`) →
    get_op_schema → run_op. `example` = a worked call (`connector` set) or
    vendor API docs. `recipe` = a step-sequence pattern for a build. `api` =
    a vendor's raw API for HTTP-fallback steps. `playbook` = existing
    playbooks. `step` = real examples of one step type (query = the type).
    `jinja` = a filter for a transform; `filter_usage` = real usages of one
    named filter; `jinja_block` = whole {% set %}/{% for %} idioms.
    `field` = a module's record fields (`module` required, `query` ranks
    them) -- look one up before writing `vars.input.records[0].<field>`.
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
    elif k == "step":
        from .tools_corpus import find_step_examples  # noqa: PLC0415
        out = find_step_examples(query, limit=limit)
    elif k == "jinja_block":
        from .tools_jinja import find_jinja_pattern  # noqa: PLC0415
        out = find_jinja_pattern(query, limit=limit)
    elif k == "field":
        out = _find_fields(module, query, limit=limit)
    elif k == "filter_usage":
        from .tools_jinja import get_filter_examples  # noqa: PLC0415
        out = get_filter_examples(query, limit=limit)
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

    unavailable: list[dict[str, Any]] = []

    def _take(name: str, res: dict[str, Any]) -> None:
        sections[name] = {kk: vv for kk, vv in res.items() if kk != "actions"}
        # Lifted to the top: a dropped-but-capable connector buried in
        # `sections` was never read live (see find_containment_actions).
        unavailable.extend(res.get("unavailable") or [])
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
    out = {"target_type": target, "action_type": fam or "all",
           "actions": merged[: limit * 3 if not fam else limit],
           "count": len(merged), "sections": sections}
    if unavailable:
        out["unavailable"] = unavailable
    return out


def _find_fields(module: str, query: str, *, limit: int) -> dict[str, Any]:
    """A module's fields from the catalog, best match to `query` first.

    Live: build turns read `vars.input.records[0].destIp` (the field is
    `destinationIp`) because record reads are refused there and nothing else
    named the fields. Catalog-only: no record data, no box call."""
    import difflib  # noqa: PLC0415

    from fsr_playbooks import module_schema  # noqa: PLC0415

    from ._shared import _db  # noqa: PLC0415
    name = module_schema.module_name(module or "")
    if not name:
        return {"ok": False, "code": "missing_module",
                "message": "kind='field' needs `module` (e.g. alerts, incidents)"}
    conn = _db()
    try:
        rows = conn.execute(
            "SELECT field_name, title, type, picklist_name FROM module_fields "
            "WHERE module_name=? ORDER BY field_name", (name,)).fetchall()
    finally:
        conn.close()
    if not rows:
        return {"ok": False, "code": "module_not_in_catalog",
                "module": name,
                "message": (f"the catalog has no fields for {name!r} -- it is "
                            "not warmed for this module, or the name is wrong "
                            "(modules are plural: alerts, incidents, indicators)")}
    fields = [{"name": r[0], "title": r[1] or "", "type": r[2] or "",
               **({"picklist": r[3]} if r[3] else {})} for r in rows]
    q = (query or "").strip().lower()
    if q:
        words = q.replace("_", " ").split()

        def score(f: dict[str, Any]) -> float:
            hay = f"{f['name']} {f['title']}".lower()
            hits = sum(1 for w in words if w in hay)
            close = difflib.SequenceMatcher(None, q.replace(" ", ""),
                                            f["name"].lower()).ratio()
            return hits + close
        fields.sort(key=score, reverse=True)
    return {"ok": True, "module": name, "count": len(rows),
            "fields": fields[:max(1, limit)],
            "system_fields": sorted(module_schema.SYSTEM_FIELDS),
            "usage": ("the trigger record's field: vars.input.records[0].<name>; "
                      "a find_record result's: vars.steps.<Step>[0].<name>")}
