"""Typed model for `decision` step arguments.

A decision step branches on an ordered list of conditions. By the time the
resolver sees it, the parser has rewritten the friendly authoring keys
(`display`→`option`, `when`→`condition`) and may have synthesized a
step-level `default:` else-row. Each condition carries a `next:` branch
target.

`expand_decision` reproduces `NormalizerMixin._normalize_decision_args`
byte-for-byte: it promotes each `{option, next}` into the step's branch map
and strips `next` from the emitted condition (the emitter later injects
`step_iri`/`step_name`). The cleaned conditions are rebuilt from the ORIGINAL
dicts — not the typed model — so key order and content stay byte-identical
(a `model_dump` would inject `None` defaults and reorder keys).

The `DecisionCondition` model adds the structural check the imperative path
lacked: a mistyped condition key (`nxt:`, `whne:`, `defualt:`) silently
dropped the branch wiring before; `extra="forbid"` now catches it at compile
time. The check is additive — output is still built leniently, matching the
legacy behaviour for valid playbooks (zero corpus-emit diff).
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import ConfigDict

from ...errors import CompileError
from ..base import StrictArgs
from .._bridge import validate_args


class DecisionCondition(StrictArgs):
    """One decision branch row (post-parser, pre-emit).

    `display`/`when` were rewritten to `option`/`condition` by the parser;
    `next` is the branch target (promoted to `step.branches`, then stripped);
    `default` flags the else row. `step_iri`/`step_name` are listed so a
    round-tripped condition stays lax under `extra="forbid"` — the emitter
    injects them and they don't normally reach the resolver, but accepting
    them keeps the model tolerant of real exported input.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    option: Any = None
    condition: Any = None
    next: Optional[str] = None
    default: Any = None
    step_iri: Optional[str] = None
    step_name: Optional[str] = None


class DecisionArgs(StrictArgs):
    """Typed view of a decision step's arguments.

    `conditions` is the branch table; sibling arg keys (mock_result,
    step_variables, message, a step-level condition, …) survive untouched,
    so `extra="allow"`.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    conditions: Optional[list[DecisionCondition]] = None


def expand_decision(
    args: Any, branches: dict, path: str, errors: list[CompileError],
) -> Optional[dict]:
    """Promote each condition's `next:` into `branches` and strip it.

    Drop-in for the imperative `_normalize_decision_args`: mutates `args` in
    place (cleaning `conditions`) and `branches` (option → next, via
    `setdefault`), then returns `args`. Returns ``None`` — leaving everything
    untouched — when `args` is empty / not a dict, or `conditions` is not a
    list, matching the legacy early-returns. Non-dict condition entries pass
    through verbatim.
    """
    if not isinstance(args, dict) or not args:
        return None
    conds = args.get("conditions")
    if not isinstance(conds, list):
        return None
    apath = f"{path}.arguments"
    cleaned = []
    for i, c in enumerate(conds):
        if not isinstance(c, dict):
            cleaned.append(c)
            continue
        # Additive structural typo check; output below is still built
        # leniently from the original dict (legacy parity for valid input).
        validate_args(DecisionCondition, c, f"{apath}.conditions[{i}]", errors)
        opt_next = c.get("next")
        opt_label = c.get("option")
        if opt_next and opt_label:
            branches.setdefault(opt_label, opt_next)
        cleaned.append({k: v for k, v in c.items() if k != "next"})
    args["conditions"] = cleaned
    return args
