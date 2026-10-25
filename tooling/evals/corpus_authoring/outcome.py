"""Derive goal-evaluation assertions from what a playbook WRITES.

The survey of the toolkit's run/debug/goal-eval found the missing link:
`verify_effect` / `assert_playbook_outcome` can check whether a playbook hit
its goal, but the expected values must be hand-fed -- nothing derives them from
the playbook itself. `effect_inventory` already names every record a playbook
writes and which fields are literals vs carried from upstream. This lifts that
static inventory into the outcome-assertion vocabulary so goal evaluation can be
generated, not hand-written.

Pure and offline. The assertions it emits are the live-checkable shapes
`assert_playbook_outcome` consumes (record_exists / field_equals); running them
against a box is a separate, opt-in step.
"""
from __future__ import annotations

import re
from typing import Any

from fsr_playbooks.compiler.effect_inventory import effect_inventory

_JINJA = re.compile(r"\{\{|\{%|vars\.")


def _literal_fields(writes_resource: dict[str, Any]) -> dict[str, Any]:
    """Fields whose written value is a static literal (no Jinja / vars ref) --
    the only values we can predict without running the playbook, so the only
    ones safe to assert as field_equals."""
    out: dict[str, Any] = {}
    for field, value in (writes_resource or {}).items():
        if str(field).startswith("__"):
            continue
        if isinstance(value, str) and _JINJA.search(value):
            continue
        if isinstance(value, (dict, list)):
            continue  # nested / linked writes: not a scalar we can match on
        out[str(field)] = value
    return out


def _module_of(entry: dict[str, Any], step) -> str | None:
    """The module a write targets. effect_inventory reads `module`, but the
    compiler normalizes `module: alerts` to `collection: /api/3/alerts` and
    drops `module`, leaving the inventory's module None -- recover it from the
    collection IRI's last segment."""
    if entry.get("module"):
        return entry["module"]
    args = (step.arguments or {}) if step is not None else {}
    coll = args.get("collection") or args.get("module")
    if isinstance(coll, str) and coll:
        return coll.rstrip("/").rsplit("/", 1)[-1] or None
    return None


def _resource_of(step) -> dict[str, Any]:
    args = step.arguments or {}
    for key in ("resource", "update_data", "insert_data", "data"):
        cand = args.get(key)
        if isinstance(cand, dict):
            return cand
    return {}


def derive_outcome_assertions(coll) -> list[dict[str, Any]]:
    """One outcome assertion per record-writing step, in the
    assert_playbook_outcome vocabulary.

    create/update_record -> record_exists on its module, with filters built
    from the step's literal fields; plus a field_equals per literal field so a
    run that creates the record but leaves a literal field wrong is caught.
    A write with no literal fields yields a bare record_exists (weakest useful
    goal check: 'the record got made').
    """
    out: list[dict[str, Any]] = []
    inv = effect_inventory(coll)
    steps_by_id = {s.id: s for pb in coll.playbooks for s in pb.steps}
    for entry in inv:
        if entry.get("kind") != "record_write":
            continue
        step = steps_by_id.get(entry.get("step_id"))
        module = _module_of(entry, step)
        if not module:
            continue
        literals = _literal_fields(_resource_of(step)) if step is not None else {}
        note = f"{entry['step']} writes {module}"
        out.append({"kind": "record_exists", "module": module,
                    "filters": dict(literals), "note": note})
        for field, value in literals.items():
            out.append({"kind": "field_equals", "module": module,
                        "filters": dict(literals), "field": field, "value": value,
                        "note": f"{note}: {field} == {value!r}"})
    return out
