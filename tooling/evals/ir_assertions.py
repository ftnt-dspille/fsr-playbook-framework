"""Behavioral assertions on a built playbook's IR (#127).

WHY THIS EXISTS. Until now a `build` fixture was `{name, notes, prompt}` and the
grading was `draft` (it compiles) + `verified` (it is statically sound). Both
are real, and neither asks the question the fixture's prompt actually poses.
Fixture 17 asks for a loop over `sender_ips`, a VirusTotal lookup, a threshold,
and an approval gate BEFORE the block. A playbook that loops the wrong field,
or blocks before the gate, compiled and verified exactly as well as a correct
one -- so "the agent got better at building playbooks" had no way to show up.

WHY NOT GOLD YAML. `matches_example` already tried byte-equality of compiled IR
against a reference and is demoted to informational for good reason: free-form
generation cannot match cosmetic IR differences (optional fields, defaults,
step ordering) and punishing that measures formatting, not competence. These
assertions grade the handful of things the prompt actually REQUIRES, and stay
silent about everything it left to the author.

WHAT THEY RUN AGAINST. The RESOLVED IR (`compile_yaml(...).ir`), not the parsed
one: `branches` is filled by the resolver, so a parse-level check cannot follow
a decision's arms and every reachability assertion would be blind. A fixture
whose YAML does not compile gets `passed: False` with a note pointing at
`draft` -- behavior is unjudgeable, not satisfied.

Assertion kinds (all take an optional `note` describing what the prompt asked):

  step_type_present   {type, min=1}      -- at least `min` steps of this type
  step_type_absent    {type}             -- no step of this type
  connector_op        {connector?, operation_contains?}
                                         -- a connector step whose resolved
                                            connector/operation matches
  for_each_over       {contains}         -- some step loops over an expression
                                            containing this text
  arg_text_contains   {contains, type?}  -- the text appears in the arguments of
                                            (a step of that type / any step)
  branch_count        {type=decision, min}
                                         -- a step of that type with >= min arms
  reachable           {from:{...}, to:{...}}
                                         -- `to` is reachable from `from` by
                                            following next/branches. Ordering as
                                            the ENGINE sees it, not list order.

A selector (`from`/`to`, and the optional `type` above) is a dict of
{type, connector, operation_contains, name_contains}; every key given must
match. Unknown assertion kinds fail loudly rather than passing vacuously -- a
typo'd assertion that silently passes is worse than no assertion.
"""
from __future__ import annotations

import json
from typing import Any


def _steps(pb) -> list:
    return list(pb.steps or [])


def _arg_text(step) -> str:
    """Every argument value flattened to searchable text."""
    try:
        return json.dumps(step.arguments or {}, default=str)
    except Exception:  # noqa: BLE001 -- diagnostics only, never blocks
        return str(step.arguments or {})


def _matches(step, sel: dict[str, Any]) -> bool:
    if not isinstance(sel, dict):
        return False
    if "type" in sel and step.type != sel["type"]:
        return False
    text = _arg_text(step).lower()
    if "connector" in sel and str(sel["connector"]).lower() not in text:
        return False
    if "operation_contains" in sel:
        if str(sel["operation_contains"]).lower() not in text:
            return False
    if "name_contains" in sel:
        hay = f"{step.name or ''} {step.id or ''}".lower()
        if str(sel["name_contains"]).lower() not in hay:
            return False
    return True


def _outgoing(step) -> list[str]:
    out = list(step.branches.values()) if step.branches else []
    out += list(step.unlabeled_next or [])
    if step.next:
        out.append(step.next)
    return [s for s in out if s]


def _reachable(pb, src_sel: dict, dst_sel: dict) -> bool:
    by_id = {s.id: s for s in _steps(pb)}
    starts = [s for s in _steps(pb) if _matches(s, src_sel)]
    if not starts:
        return False
    for start in starts:
        seen: set[str] = set()
        stack = list(_outgoing(start))
        while stack:
            sid = stack.pop()
            if sid in seen:
                continue
            seen.add(sid)
            nxt = by_id.get(sid)
            if nxt is None:
                continue
            if _matches(nxt, dst_sel):
                return True
            stack.extend(_outgoing(nxt))
    return False


def _check_one(pb, a: dict[str, Any]) -> tuple[bool, str]:
    kind = str(a.get("kind") or "")
    label = str(a.get("note") or kind)
    steps = _steps(pb)

    if kind == "step_type_present":
        want = int(a.get("min", 1))
        n = sum(1 for s in steps if s.type == a.get("type"))
        return n >= want, f"{label}: found {n} {a.get('type')} step(s), need {want}"

    if kind == "step_type_absent":
        n = sum(1 for s in steps if s.type == a.get("type"))
        return n == 0, f"{label}: found {n} {a.get('type')} step(s), expected none"

    if kind == "connector_op":
        sel = {k: v for k, v in a.items()
               if k in ("connector", "operation_contains")}
        sel["type"] = "connector"
        hit = any(_matches(s, sel) for s in steps)
        return hit, f"{label}: no connector step matching {sel}" if not hit else label

    if kind == "for_each_over":
        # `for_each` is a DICT on the resolved IR ({item, condition, parallel,
        # ...}), not the bare expression -- match the `item` expression when it
        # is one, and fall back to the whole mapping otherwise.
        needle = str(a.get("contains", "")).lower()

        def _fe(s) -> str:
            fe = s.for_each
            if isinstance(fe, dict):
                return str(fe.get("item") or fe).lower()
            return str(fe or "").lower()

        hit = any(needle in _fe(s) for s in steps)
        return hit, (label if hit else
                     f"{label}: no step loops over anything containing "
                     f"{needle!r} (for_each values: "
                     f"{[_fe(s) for s in steps if s.for_each]})")

    if kind == "arg_text_contains":
        needle = str(a.get("contains", "")).lower()
        pool = [s for s in steps
                if "type" not in a or s.type == a.get("type")]
        hit = any(needle in _arg_text(s).lower() for s in pool)
        return hit, (label if hit else
                     f"{label}: {needle!r} appears in no "
                     f"{a.get('type') or 'step'} arguments")

    if kind == "branch_count":
        want = int(a.get("min", 2))
        best = max((len(s.branches or {}) for s in steps
                    if s.type == a.get("type", "decision")), default=0)
        return best >= want, (f"{label}: widest {a.get('type', 'decision')} has "
                              f"{best} arm(s), need {want}")

    if kind == "reachable":
        ok = _reachable(pb, a.get("from") or {}, a.get("to") or {})
        return ok, (label if ok else
                    f"{label}: nothing matching {a.get('to')} is reachable "
                    f"from {a.get('from')}")

    # A typo must not pass vacuously.
    return False, f"unknown assertion kind {kind!r}"


def check_ir_assertions(yaml_text: str,
                        assertions: list[dict[str, Any]] | None,
                        db_path: Any = None) -> dict[str, Any]:
    """Grade `yaml_text` against a fixture's behavioral assertions.

    Returns a level dict. Skipped when the fixture declares none -- most
    fixtures do not yet, and a fixture with nothing to assert must not be
    scored as if it passed something.
    """
    if not assertions:
        return {"passed": False, "skipped": True,
                "detail": "fixture declares no ir_assertions"}
    try:
        from fsr_playbooks._db import default_db_path
        from fsr_playbooks.compiler import compile_yaml
    except ImportError as exc:  # pragma: no cover
        return {"passed": False, "skipped": True, "detail": f"unavailable: {exc}"}

    cres = compile_yaml(yaml_text or "", db_path or default_db_path())
    ir = getattr(cres, "ir", None)
    if ir is None or not ir.playbooks:
        return {
            "passed": False, "skipped": False,
            "checked": 0, "failures": ["did not compile -- see draft"],
            "detail": ("the YAML did not compile, so its behavior cannot be "
                       "judged (this is not the same as behaving wrongly)"),
        }

    # Assertions describe ONE playbook's behavior. Grade the first -- every
    # build fixture asks for exactly one -- but say so, so a multi-playbook
    # answer cannot quietly satisfy them from a sibling.
    pb = ir.playbooks[0]
    failures: list[str] = []
    for a in assertions:
        ok, why = _check_one(pb, a if isinstance(a, dict) else {})
        if not ok:
            failures.append(why)
    passed = not failures
    return {
        "passed": passed,
        "skipped": False,
        "checked": len(assertions),
        "playbook": pb.name,
        "failures": failures,
        "detail": (f"all {len(assertions)} behavioral assertion(s) hold"
                   if passed else
                   f"{len(failures)}/{len(assertions)} failed: "
                   + "; ".join(failures[:3])),
    }
