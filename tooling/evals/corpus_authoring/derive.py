"""Derive an authoring task (spec + ir_assertions) from a real playbook's IR.

A corpus playbook is wire JSON. We decompile it to YAML, compile that to the
RESOLVED IR (the same representation ir_assertions grades against), and read the
required structure off it: trigger, connector operations, decisions, loops,
sub-playbook references, manual-input / approval gates. The spec restates those
requirements in prose for the agent; the assertions grade exactly the same
things, no more -- so a correct author is never failed for cosmetic choices and
the real playbook, by construction, satisfies its own assertions (the sampler
self-checks this).

This module adds NO new grading vocabulary: every assertion it emits is one the
framework's ir_assertions.check_ir_assertions already understands.
"""
from __future__ import annotations

import re
from typing import Any

# Step types common enough that "has one" says nothing about intent, plus
# "unknown" -- a type the decompiler could not classify, which an author cannot
# be asked to reproduce.
_UNINTERESTING = {"start", "set_variable", "unknown"}


def _op_of(step) -> tuple[str, str]:
    """(connector, operation) for a resolved connector step, best-effort."""
    a = step.arguments if isinstance(step.arguments, dict) else {}
    conn = str(a.get("name") or a.get("connector") or step.step_type_name or "")
    op = str(a.get("operation") or a.get("operationTitle") or "")
    return conn, op


def _loop_expr(step) -> str | None:
    """The text a for_each loops over, if the step loops."""
    fe = step.for_each
    if not isinstance(fe, dict):
        return None
    for key in ("item", "items", "value", "expression", "iterate_on", "iterable"):
        v = fe.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    # fall back to any string value in the for_each block
    for v in fe.values():
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


# Most specific first: a playbook with a start_on_create step triggers on
# create, not plain "start", and the spec/assertion must say so.
_START_FAMILY = ("start_on_create", "start_on_update", "start_on_delete",
                 "start_on_comment", "start_manual", "start")


def _trigger_type(pb) -> str:
    """The resolved trigger step's type (start, start_on_create, ...).

    Use the explicit trigger step when the playbook names one; else the most
    specific start-family step actually present (so a create-triggered playbook
    is not mislabeled "start"); else the declared short-name trigger. Never the
    first step's type -- a child playbook's first step is often a set_variable."""
    if pb.trigger_step_id:
        for s in pb.steps or []:
            if s.id == pb.trigger_step_id:
                return s.type
    present = {s.type for s in (pb.steps or [])}
    for t in _START_FAMILY:
        if t in present:
            return t
    return pb.trigger or "start"


def derive_assertions(pb) -> list[dict[str, Any]]:
    """Behavioral assertions the authored playbook must satisfy, in the
    framework's ir_assertions vocabulary."""
    out: list[dict[str, Any]] = []
    steps = list(pb.steps or [])

    trig = _trigger_type(pb)
    if trig != "unknown":
        out.append({"kind": "step_type_present", "type": trig, "min": 1,
                    "note": f"triggers on {trig}"})

    # distinctive step-type presence (not start/set_variable)
    type_counts: dict[str, int] = {}
    for s in steps:
        if s.type not in _UNINTERESTING:
            type_counts[s.type] = type_counts.get(s.type, 0) + 1
    for t, n in type_counts.items():
        if t == trig:
            continue
        out.append({"kind": "step_type_present", "type": t, "min": 1,
                    "note": f"uses a {t} step"})

    # connector operations (the strongest intent signal)
    seen_ops = set()
    for s in steps:
        if s.type != "connector":
            continue
        conn, op = _op_of(s)
        if op and (conn, op) not in seen_ops:
            seen_ops.add((conn, op))
            a: dict[str, Any] = {"kind": "connector_op",
                                 "operation_contains": op,
                                 "note": f"calls {conn or 'a connector'} {op}"}
            if conn:
                a["connector"] = conn
            out.append(a)

    # loops: assert iteration over the same expression text
    for s in steps:
        expr = _loop_expr(s)
        if expr:
            # grade on a stable fragment of the expression (the field being looped)
            frag = _loop_fragment(expr)
            out.append({"kind": "for_each_over", "contains": frag,
                        "note": f"loops over {frag}"})

    # decisions: at least as many arms as the real one
    for s in steps:
        if s.type == "decision":
            arms = len(s.branches or {}) or len(s.unlabeled_next or [])
            if arms >= 2:
                out.append({"kind": "branch_count", "type": "decision",
                            "min": 2, "note": f"a decision with >= 2 arms"})
            break

    return out


_FIELD_FRAG = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*")


def _loop_fragment(expr: str) -> str:
    """A stable substring of a loop expression to grade on -- prefer the last
    dotted field (e.g. vars.input.records.iPAddresses -> iPAddresses)."""
    tokens = _FIELD_FRAG.findall(expr)
    if not tokens:
        return expr.strip()[:40]
    last = tokens[-1]
    return last.split(".")[-1]


_DISTINCTIVE_LABEL = {
    "decision": "a decision branch", "manual_input": "a manual-input step",
    "approval_manual_input": "an approval gate",
    "workflow_reference": "a reference to another playbook",
    "code_snippet": "a code snippet step", "run_script": "a script step",
    "ingest_bulk_feed": "an ingest-bulk-feed step", "find_record": "a find-record step",
    "create_record": "a create-record step", "update_record": "an update-record step",
    "delay": "a delay step",
}


def derive_spec(pb, assertions: list[dict[str, Any]]) -> str:
    """A prose build request restating EXACTLY the kept assertions, so the spec
    and the grader never contradict each other (the trigger, ops, loops and
    distinctive steps the spec names are precisely those that are graded)."""
    trig = next((a["type"] for a in assertions
                 if a["kind"] == "step_type_present" and a.get("type") in _START_FAMILY), None)
    head = f"Build a FortiSOAR playbook named \"{pb.name}\""
    head += f" that triggers on {trig}." if trig else "."
    lines = [head]
    if pb.description:
        lines.append(f"Purpose: {pb.description.strip()}")

    ops = []
    for a in assertions:
        if a["kind"] == "connector_op":
            op = a.get("operation_contains", "")
            conn = a.get("connector")
            ops.append(f"{op}" + (f" (connector {conn})" if conn else ""))
    if ops:
        lines.append("It must call these connector operations: " + "; ".join(dict.fromkeys(ops)) + ".")

    loops = [a["contains"] for a in assertions if a["kind"] == "for_each_over"]
    if loops:
        lines.append("It must loop over: " + ", ".join(dict.fromkeys(loops)) + ".")

    distinctive = []
    for a in assertions:
        if a["kind"] == "step_type_present":
            lbl = _DISTINCTIVE_LABEL.get(a.get("type"))
            if lbl and lbl not in distinctive:
                distinctive.append(lbl)
    if any(a["kind"] == "branch_count" for a in assertions) and "a decision branch" not in distinctive:
        distinctive.append("a decision branch")
    if distinctive:
        lines.append("It must include: " + ", ".join(distinctive) + ".")

    lines.append("Author the YAML and make it pass verify_playbook (ready_to_push).")
    return "\n".join(lines)
