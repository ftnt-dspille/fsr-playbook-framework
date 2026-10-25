"""Inject known defect classes into a good playbook, to measure PROBLEM SOLVING.

Authoring from scratch is one skill; fixing a broken playbook is another, and
the toolkit's debug_run / repair_playbook path had no eval at all. This takes a
playbook that compiles+verifies clean and produces a deliberately-broken variant
plus the signal a correct diagnosis must surface, so a repair can be graded:
  - did verify/compile DETECT the defect (the expected code appears)?
  - after repair, is the defect gone AND the structure preserved?

Every defect here is statically detectable offline (no live run needed), so the
detection half grades without a box. Each injector returns None when the source
has no suitable target, so a caller tries several and keeps what applies.

Operates on the parsed collection dict (collection/playbooks/steps). Steps carry
`name` and `next` (a name reference); connector steps carry connector/operation.
"""
from __future__ import annotations

import copy
import re
from typing import Any, Callable

import yaml


def _load(text: str) -> dict:
    return yaml.safe_load(text)


def _dump(obj: dict) -> str:
    return yaml.safe_dump(obj, sort_keys=False, allow_unicode=True)


def _steps(coll: dict) -> list[dict]:
    pbs = coll.get("playbooks") or []
    return pbs[0].get("steps") or [] if pbs else []


# --- injectors: (broken_coll | None, defect) -------------------------------
def inject_unknown_step_reference(coll: dict) -> dict | None:
    """Point some step's `next` at a step that does not exist."""
    c = copy.deepcopy(coll)
    for s in _steps(c):
        nxt = s.get("next")
        if isinstance(nxt, str) and nxt:
            s["next"] = nxt + "_DOES_NOT_EXIST"
            return {"yaml": _dump(c), "kind": "unknown_step_reference",
                    "expect_codes": ["unknown_next_step", "unknown_step_reference",
                                     "branch_target_missing", "unreachable_step"],
                    "detail": f"step {s.get('name')!r} next -> missing target"}
    return None


def inject_missing_required_field(coll: dict) -> dict | None:
    """Drop `operation` from a connector step -- a required field."""
    c = copy.deepcopy(coll)
    for s in _steps(c):
        if s.get("type") in ("connector", "connector_op") and "operation" in s:
            removed = s.pop("operation")
            return {"yaml": _dump(c), "kind": "missing_required_field",
                    "expect_codes": ["missing_field", "bad_value"],
                    "detail": f"step {s.get('name')!r} lost operation {removed!r}"}
    return None


def inject_orphan_step(coll: dict) -> dict | None:
    """Remove the only edge into a mid-graph step so it becomes unreachable."""
    c = copy.deepcopy(coll)
    steps = _steps(c)
    names = [s.get("name") for s in steps]
    # find a step that is some other step's `next` target (has an incoming edge)
    for s in steps:
        nxt = s.get("next")
        if isinstance(nxt, str) and nxt in names and nxt != s.get("name"):
            # cut this edge; if nxt has no other incoming edge it is orphaned
            incoming = [o for o in steps
                        if o is not s and o.get("next") == nxt]
            if not incoming:
                s["next"] = None
                return {"yaml": _dump(c), "kind": "orphan_step",
                        "expect_codes": ["unreachable_step", "unreachable_step_reference"],
                        "detail": f"orphaned step {nxt!r} (cut edge from {s.get('name')!r})"}
    return None


_IRI_TARGET = re.compile(r"(\{\{\s*vars\.)")


def inject_doubled_iri(coll: dict) -> dict | None:
    """Prefix a Jinja record reference with a doubled /api/3/<module>/ -- the
    one defect repair_playbook auto-fixes, so it also tests the auto-repair."""
    c = copy.deepcopy(coll)
    for s in _steps(c):
        args = s.get("arguments")
        if not isinstance(args, dict):
            continue
        for k, v in list(args.items()):
            if isinstance(v, str) and _IRI_TARGET.search(v) and "/api/3/" not in v:
                args[k] = _IRI_TARGET.sub(r"/api/3/alerts//api/3/alerts/\1", v, count=1)
                return {"yaml": _dump(c), "kind": "doubled_iri",
                        "expect_codes": ["doubled_iri", "bad_value", "render_error"],
                        "detail": f"doubled IRI on {s.get('name')!r}.{k}",
                        "auto_repairable": True}
    return None


INJECTORS: list[Callable[[dict], dict | None]] = [
    inject_unknown_step_reference,
    inject_missing_required_field,
    inject_orphan_step,
    inject_doubled_iri,
]


def make_defects(good_yaml: str) -> list[dict]:
    """Every defect that applies to this playbook, one per injector that fit."""
    coll = _load(good_yaml)
    out = []
    for inj in INJECTORS:
        d = inj(coll)
        if d:
            d["injector"] = inj.__name__
            out.append(d)
    return out
