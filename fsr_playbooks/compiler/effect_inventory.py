"""Effect inventory -- what a playbook actually DOES, and where the written
values come from.

The rest of the compiler proves a playbook is well-wired: references resolve,
fields exist, every step is reachable. None of that answers the question an
analyst (or a grader) actually cares about: *does the playbook carry out the
action it was built for, with the right data?* A playbook that enriches an
alert and then forgets to write the verdict compiles perfectly clean.

This module lifts the playbook's **effects** -- its record writes and its
connector actions -- into a plain inventory, and for each written field records
which upstream steps feed the value. A verdict field whose value is a literal
(no upstream reference) is a red flag the static checks cannot see; so is a
"containment" playbook with no effect step at all.

It proves *linkage*, not runtime truth: that a mutating step's value references
an enrichment step, not that the enrichment actually produced a malicious
verdict at run time. That last mile is the box-run's job (push -> trigger ->
read the written field back). This inventory is what tells the box-run which
field on which record to read back.

Pure over the IR: no DB, no network. `op_safety` (optional) is the only outside
fact -- it marks a connector op as mutating; without it connector calls are
reported with `mutating=None` (unknown) and the caller decides.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .ir import Collection, Step
from .validator import _VARS_STEPS_RE, _VARS_STEPS_SUBSCRIPT_RE

# Record-mutating step types are a certain effect regardless of any catalog.
EFFECT_RECORD_TYPES = frozenset({"create_record", "update_record", "delete_record"})

# Connector-op safety values that mean "this op changes state on the target".
# The op_safety table's vocabulary; anything outside {safe, unknown, ""} is
# treated as mutating. We never hardcode op *names* -- classification is
# structural, from the catalog's safety fact.
_SAFE_OR_UNKNOWN = frozenset({"safe", "unknown", ""})

OpSafety = Callable[[str, str], str | None]


def _jinja_key(step: Step) -> str:
    """FSR builds vars.steps.<key> from a step's display name, spaces -> `_`."""
    return (step.name or step.id or "").strip().replace(" ", "_")


def _referenced_step_keys(value: Any) -> set[str]:
    """Every `vars.steps.<key>` referenced anywhere in a (possibly nested)
    argument value -- the upstream steps feeding it. Reuses the validator's
    reference regexes so static checks and this inventory agree on what a
    reference is."""
    keys: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, str):
            for m in _VARS_STEPS_RE.finditer(node):
                keys.add(m.group(1))
            for m in _VARS_STEPS_SUBSCRIPT_RE.finditer(node):
                # subscript form: the key is the display name, spaces and all;
                # normalise to the jinja-key so it matches _referenced producers.
                keys.add(m.group(2).strip().replace(" ", "_"))
        elif isinstance(node, dict):
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(value)
    return keys


def _written_fields(step: Step) -> dict[str, set[str]]:
    """For a record-write step, map each written field -> the set of upstream
    step keys that feed its value. A field fed by a literal maps to an empty
    set (a value the playbook invents, not one it carries forward)."""
    resource = step.arguments.get("resource")
    if not isinstance(resource, dict):
        # update_record sometimes carries `update_data`; create, `insert_data`.
        for alt in ("update_data", "insert_data", "data"):
            cand = step.arguments.get(alt)
            if isinstance(cand, dict):
                resource = cand
                break
    if not isinstance(resource, dict):
        return {}
    out: dict[str, set[str]] = {}
    for field, value in resource.items():
        if str(field).startswith("__"):
            continue  # write directives (__link, __replace, ...), not fields
        out[str(field)] = _referenced_step_keys(value)
    return out


def effect_inventory(coll: Collection,
                     op_safety: OpSafety | None = None) -> list[dict[str, Any]]:
    """Lift every effect step in the collection into an inventory entry.

    Each entry:
      {playbook, step, step_id, kind, module?, operation?, connector?,
       mutating, writes: {field: [source_step_key, ...]},
       sources: [all upstream step keys feeding this effect]}

    `kind` is 'record_write' (create/update/delete_record) or
    'connector_action' (a connector step). `mutating` is True for record
    writes; for connector steps it is the op_safety verdict (True/False) or
    None when no safety fact is available.
    """
    out: list[dict[str, Any]] = []
    for pb in coll.playbooks:
        for s in pb.steps:
            a = s.arguments or {}
            entry: dict[str, Any] | None = None
            if s.type in EFFECT_RECORD_TYPES:
                writes = _written_fields(s)
                entry = {
                    "kind": "record_write",
                    "module": a.get("module"),
                    "mutating": True,
                    "writes": {f: sorted(src) for f, src in writes.items()},
                }
            elif s.type in {"connector", "connector_op"}:
                connector = a.get("connector") or a.get("connector_name")
                op = a.get("operation") or a.get("op_name") or a.get("op")
                mutating: bool | None = None
                if op_safety and connector and op:
                    try:
                        verdict = op_safety(connector, op)
                    except Exception:  # noqa: BLE001 -- a catalog miss is not an effect fact
                        verdict = None
                    if verdict is not None:
                        mutating = (verdict or "").lower() not in _SAFE_OR_UNKNOWN
                # A read-only op (safety says safe) is not an effect; drop it.
                if mutating is False:
                    continue
                entry = {
                    "kind": "connector_action",
                    "connector": connector,
                    "operation": op,
                    "mutating": mutating,
                    "writes": {},
                }
                entry["sources"] = sorted(_referenced_step_keys(a.get("params")))
            if entry is None:
                continue
            entry["playbook"] = pb.name
            entry["step"] = s.name or s.id
            entry["step_id"] = s.id
            if "sources" not in entry:
                srcs: set[str] = set()
                for src in entry.get("writes", {}).values():
                    srcs.update(src)
                entry["sources"] = sorted(srcs)
            out.append(entry)
    return out


def unlinked_effects(inventory: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Effect entries whose written values reference no upstream step -- a
    record write built entirely from literals / trigger input, with nothing
    carried forward from an enrichment or decision. Often legitimate (a static
    status change), but the one shape worth surfacing: an enrichment playbook
    that computed a verdict and then wrote a hardcoded one."""
    return [e for e in inventory
            if e["kind"] == "record_write" and e["writes"] and not e["sources"]]
