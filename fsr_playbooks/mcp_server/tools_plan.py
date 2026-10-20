"""Plan-then-ground: resolve a whole intended playbook in one read-only call.

The build census showed find + get_op_schema + the configured-connector check
are ~45% of all build calls, spent one step at a time, and that the costly
failures (unknown connector, wrong op, a step reading a field the upstream op
never returns) surface only at verify, after the YAML is already authored.

`plan_playbook` takes the ordered steps the model intends to write and grounds
them all at once against the warmed catalog: for each step it says whether the
step type, connector, operation and module resolve, offers a near match when
one does not, and hands back the op's recorded output fields so the next step
can bind a real path instead of a guessed one. It writes nothing and emits no
card -- it is the cheapest possible discovery pass, done before authoring, not
instead of verify.
"""
from __future__ import annotations

from typing import Any

from ._shared import mcp

# The verdict each step resolves to. `ok` means every named facet exists; the
# rest name exactly what is missing so the model can fix the plan, not guess.
_STATUS_OK = "ok"


def _resolve_step(step: dict[str, Any]) -> dict[str, Any]:
    from . import (  # late import avoids a registration cycle
        find_connector,
        get_op_schema,
        get_step_type,
    )
    purpose = str(step.get("purpose") or "").strip()
    out: dict[str, Any] = {"purpose": purpose, "status": _STATUS_OK, "resolved": {}}

    stype = (step.get("type") or "").strip()
    connector = (step.get("connector") or "").strip()
    operation = (step.get("operation") or "").strip()
    module = (step.get("module") or "").strip()

    # 1. Step type.
    if stype:
        st = get_step_type(stype)
        if st.get("ok") is False:
            out["status"] = "unknown_step_type"
            out["near"] = st.get("near") or []
            return out
        out["resolved"]["type"] = stype

    # 2. Connector (existence; near match when absent). The offline slim catalog
    #    has no configured-connector state, so `configured` is reported only when
    #    the catalog can answer it -- never guessed.
    if connector:
        fc = find_connector(connector)
        matches = fc.get("matches") or []
        exact = next((m for m in matches
                      if (m.get("name") or "").lower() == connector.lower()), None)
        if not exact and not matches:
            out["status"] = "unknown_connector"
            out["suggestion"] = fc.get("suggestion") or ""
            out["near"] = [m.get("name") for m in matches]
            return out
        chosen = exact or matches[0]
        out["resolved"]["connector"] = chosen.get("name")
        out["resolved"]["config_required"] = chosen.get("config_required")

    # 3. Operation on that connector (+ its recorded output fields).
    if connector and operation and out["resolved"].get("connector"):
        schema = get_op_schema(out["resolved"]["connector"], operation)
        if schema.get("ok") is False:
            out["status"] = "unknown_operation"
            out["near"] = schema.get("near") or []
            return out
        out["resolved"]["operation"] = schema.get("op_name") or operation
        osch = schema.get("output_schema")
        if isinstance(osch, str) and osch.lstrip().lower().startswith("unknown"):
            out["resolved"]["output_recorded"] = False
        else:
            out["resolved"]["output_recorded"] = True
            out["resolved"]["output"] = osch

    # 4. Module. `module_not_in_catalog` is the only verdict that means the name
    #    is wrong; an unwarmed field list still means the module exists, so it
    #    resolves (the fields fill in from a box warm, not a plan-time concern).
    if module:
        from .tools_find import _find_fields
        mf = _find_fields(module, "", limit=1)
        if mf.get("code") == "module_not_in_catalog":
            out["status"] = "unknown_module"
            return out
        out["resolved"]["module"] = mf.get("module") or module
        if mf.get("code") == "module_fields_unwarmed":
            out["resolved"]["fields_warmed"] = False

    return out


@mcp.tool()
def plan_playbook(steps: list[dict[str, Any]],
                  requirements: list[str] | None = None) -> dict[str, Any]:
    """Ground a whole intended playbook in ONE call BEFORE you author any YAML.

    Pass the ordered steps you mean to write, each a small dict:
    `{purpose, type?, connector?, operation?, module?}` -- `purpose` in plain
    words, the rest only when you already know them. Optionally pass the
    `requirements` the build must meet, and they are echoed back so later checks
    can report which step covers each.

    For every step this resolves the named step type, connector, operation and
    module against the catalog in a single pass and returns a verdict: `ok`, or
    `unknown_step_type` / `unknown_connector` / `unknown_operation` /
    `unknown_module`, each with a `near` list or `suggestion` so you can fix the
    plan. For a resolved connector operation it returns the op's recorded output
    fields, so the next step can bind a real `vars.steps...` path instead of a
    guessed one. Overall it returns `ready_to_build` or the list of `gaps`.

    It writes nothing and emits no card. Call it once at the start of a build
    instead of a find + get_op_schema round-trip per step; it surfaces an
    unknown connector or wrong operation here, not at verify after the YAML is
    written. Do NOT substitute a different vendor when a connector is unknown --
    report the gap.
    """
    if not isinstance(steps, list) or not steps:
        return {"ok": False, "code": "no_steps",
                "message": "pass a non-empty list of intended steps, each "
                           "{purpose, type?, connector?, operation?, module?}"}
    resolved = []
    for step in steps:
        if not isinstance(step, dict):
            resolved.append({"purpose": str(step), "status": "unknown_step_type",
                             "near": [], "message": "each step must be an object"})
            continue
        resolved.append(_resolve_step(step))
    gaps = [s for s in resolved if s.get("status") != _STATUS_OK]
    return {"ok": True,
            "ready_to_build": not gaps,
            "steps": resolved,
            "gaps": gaps,
            "requirements": list(requirements or [])}
