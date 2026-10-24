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


# Capability language: how a USER describes a need, never the FSR step-type
# enum the grader checks. Leaking the enum ("add a manual_input step") turns a
# design task into a lookup, so specs translate requirements to intent and the
# agent must map intent -> structure itself.
_CAPABILITY = {
    "decision": "branch depending on a condition",
    "manual_input": "pause to collect input from a person",
    "approval_manual_input": "require a person's approval before continuing",
    "workflow_reference": "hand off to another, existing playbook",
    "code_snippet": "run a small piece of custom logic",
    "run_script": "run a script",
    "ingest_bulk_feed": "pull in a batch of records from a feed",
    "find_record": "look up an existing record",
    "create_record": "create a record",
    "update_record": "update a record",
    "delay": "wait before continuing",
}

# Internal tokens a user-voice spec must NEVER contain (the leakage guard
# checks these). The step-type enums and the loop-expression/op ids.
LEAK_TOKENS = sorted(set(list(_CAPABILITY) + list(_START_FAMILY) + [
    "connector_op", "for_each", "step_type", "set_variable", "yaml_text",
    "ready_to_push", "workflow_reference", "manual_input", "ir_assertions",
]))


def _trigger_phrase(assertions: list[dict[str, Any]]) -> str:
    trig = next((a["type"] for a in assertions
                 if a["kind"] == "step_type_present" and a.get("type") in _START_FAMILY), None)
    return {
        "start_on_create": "It should run automatically whenever a new record of its type is created.",
        "start_on_update": "It should run automatically whenever a record is updated.",
        "start_on_delete": "It should run automatically whenever a record is deleted.",
        "start": "An analyst will run it on demand.",
    }.get(trig, "")


def _capabilities(assertions: list[dict[str, Any]]) -> list[str]:
    """Required capabilities in user language, deduped, no enum/op-id leakage."""
    caps: list[str] = []
    for a in assertions:
        if a["kind"] == "step_type_present":
            c = _CAPABILITY.get(a.get("type"))
            if c and c not in caps:
                caps.append(c)
        elif a["kind"] == "for_each_over":
            c = "repeat the work for each item it is handling"
            if c not in caps:
                caps.append(c)
        elif a["kind"] == "branch_count":
            c = "branch depending on a condition"
            if c not in caps:
                caps.append(c)
    return caps


def _purpose(pb) -> str:
    """A usable real-world purpose, or "" when the description is junk (empty,
    a placeholder like "test", or just the name restated)."""
    p = (pb.description or "").strip()
    if len(p) < 10 or p.lower() in {"test", "todo", "tbd", (pb.name or "").lower()}:
        return ""
    return p


# --- personas: a wide variety of real users, each asking the SAME underlying
# playbook in their own voice and at their own level of detail. Every builder
# takes (pb, assertions) and returns a spec or None; none may contain an FSR
# step-type enum / op id / loop variable (the leakage guard enforces this).

def derive_terse_spec(pb, assertions: list[dict[str, Any]]) -> str | None:
    """A hurried user who types a single curt line and expects it handled."""
    p = _purpose(pb)
    if not p:
        return None
    return p if p.endswith(".") else p + "."


def derive_goal_spec(pb, assertions: list[dict[str, Any]] | None = None) -> str | None:
    """Non-expert user: states only the real-world goal, no structure at all."""
    purpose = _purpose(pb)
    if not purpose:
        return None
    return (
        f"I need a FortiSOAR playbook. Here is what it should accomplish:\n"
        f"{purpose}\n"
        "Please design and build it -- you decide what steps and integrations it needs."
    )


def derive_verbose_spec(pb, assertions: list[dict[str, Any]] | None = None) -> str | None:
    """A wordy, non-technical business owner: lots of context, no specifics."""
    purpose = _purpose(pb)
    if not purpose:
        return None
    return (
        "Hi! I lead part of our security operations and we keep doing this by hand, "
        "which really burns our analysts' time and causes mistakes. What I'm hoping "
        f"you can set up for us is an automation that will: {purpose} "
        "I'm honestly not a technical person, so I'll leave the how up to you -- just "
        "please build something that actually works for us."
    )


def derive_operational_spec(pb, assertions: list[dict[str, Any]]) -> str | None:
    """Analyst user: describes the workflow in operational, plain language --
    the behaviours it needs, never FSR step-type names."""
    caps = _capabilities(assertions)
    if not caps:
        return None
    purpose = _purpose(pb)
    lines = [f'I want to automate a workflow in FortiSOAR ("{pb.name}").']
    if purpose:
        lines.append(f"What it is for: {purpose}")
    trig = _trigger_phrase(assertions)
    if trig:
        lines.append(trig)
    lines.append("Along the way it needs to:")
    lines.extend(f"  - {c}" for c in caps)
    lines.append("Build the playbook so it is sound and ready to run.")
    return "\n".join(lines)


def derive_expert_spec(pb, assertions: list[dict[str, Any]]) -> str | None:
    """A precise, technical user who still speaks in behaviours, not FSR enums:
    one tight paragraph describing trigger + flow + production-readiness."""
    caps = _capabilities(assertions)
    if not caps:
        return None
    purpose = _purpose(pb)
    trig = _trigger_phrase(assertions).replace("It should ", "").replace(
        "An analyst will run it on demand.", "It is run on demand.").strip()
    bits = [f'Build the "{pb.name}" playbook.']
    if purpose:
        bits.append(purpose if purpose.endswith(".") else purpose + ".")
    flow = (trig + " " if trig else "") + "It needs to " + ", then ".join(caps) + "."
    bits.append(flow[0].upper() + flow[1:])
    bits.append("It should be statically sound and ready to run in production.")
    return " ".join(bits)


#: name -> (builder, strict_ir). All user-voice styles grade sound+runnable;
#: structural overlap with the real playbook is tracked, not gated.
SPEC_BUILDERS = [
    ("terse", derive_terse_spec, False),
    ("goal", derive_goal_spec, False),
    ("verbose", derive_verbose_spec, False),
    ("operational", derive_operational_spec, False),
    ("expert", derive_expert_spec, False),
]
