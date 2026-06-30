"""Compile-time reference lint — catch a bad ``vars.steps.X.foo`` offline.

The typed walker (:mod:`fsr_playbooks.compiler.typed_walker`) already resolves
every ``vars.steps.<step>.<key>`` reference against the statically-synthesized
output shapes of the steps that produce them (``manual_input`` →
``.input.<name>``, ``set_variable`` vars, ``workflow_reference`` child output,
…). Until now that power only ran in the heavy MCP *verify* path. This module
wires the **reference-existence** subset of that walk into the default compile so
the common foot-gun — a reference to a step that doesn't exist, runs too late, or
doesn't expose the key you asked for — is flagged at compile time as a
**warning** (never blocking; the runtime may still accept shapes the static walk
can't fully model).

Only high-confidence, shape-independent codes are surfaced (see
``_REFERENCE_CODES``); type-flow / picklist heuristics stay in the verify path.
The walk runs without resolver hooks, so it relies on the statically-known step
shapes — exactly the cross-step / parent→child references this is meant to catch
— and degrades silently on anything it can't model.
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Optional

from .errors import CompileError, ErrorCode

if TYPE_CHECKING:
    from .ir import Collection

# `vars.steps.<step>.<path>` token, used to dedupe against checks (e.g. the
# validator's intra-playbook jinja-reference check) that already flagged the
# same reference — both embed the token verbatim in their message.
_VARS_STEPS_TOKEN = re.compile(r"vars\.steps\.[A-Za-z0-9_]+(?:[.\[][^\s'\"]*)?")

# typed_walker Diagnostic codes that mean "this vars.steps.* reference can't
# resolve" — independent of connector/module probing, so safe to surface from a
# plain offline compile. Type-flow codes (type_mismatch, non_list_indexed, …)
# need probed shapes to avoid false positives and stay in the verify path.
_REFERENCE_CODES = frozenset({
    "unknown_step_reference",        # X doesn't exist (or wrong case/punctuation)
    "unreachable_step_reference",    # X is on a different branch
    "missing_field_on_step_output",  # X exists but doesn't expose .foo
    "var_read_before_definition",    # vars.<name> used before any step sets it
    "var_defined_other_branch",      # vars.<name> only set on a sibling branch
})


def reference_lint(
    coll: "Collection",
    existing: Optional[list[CompileError]] = None,
) -> list[CompileError]:
    """Return compile warnings for unresolvable ``vars.steps.*`` references.

    Walks every playbook in ``coll`` and converts the walker's
    reference-existence diagnostics into :class:`CompileError` warnings. Never
    raises and never blocks: any internal failure yields an empty list so the
    lint can't break a compile that would otherwise succeed.

    ``existing`` is the list of diagnostics already produced this compile; a
    reference whose ``vars.steps.X.Y`` token is already mentioned there (e.g. by
    the validator's intra-playbook jinja check) is skipped so it isn't reported
    twice.
    """
    seen_tokens: set[str] = set()
    for e in existing or []:
        seen_tokens.update(_VARS_STEPS_TOKEN.findall(e.message or ""))
    # Imported lazily: the walker pulls in jinja typing machinery we don't want
    # to load on every import of the errors/pipeline modules.
    try:
        from .typed_walker import walk_playbook
    except Exception:  # pragma: no cover - defensive; walker is always present
        return []

    out: list[CompileError] = []
    for pb in coll.playbooks:
        try:
            result = walk_playbook(coll, pb.name)
        except Exception:  # noqa: BLE001 - a walker hiccup must not break compile
            continue
        for d in result.diagnostics:
            if d.code not in _REFERENCE_CODES:
                continue
            tokens = _VARS_STEPS_TOKEN.findall(d.message or "")
            if tokens and any(t in seen_tokens for t in tokens):
                continue  # already flagged by an earlier check
            seen_tokens.update(tokens)
            path = f"{pb.name}.{d.step}" if d.step else pb.name
            out.append(CompileError(
                code=ErrorCode.BAD_VAR_REFERENCE,
                message=d.message,
                path=path,
                suggestion=d.suggestion,
                severity="warning",
            ))
    return out
