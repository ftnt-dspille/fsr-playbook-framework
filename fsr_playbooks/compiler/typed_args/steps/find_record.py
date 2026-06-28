"""Typed model for `find_record` step arguments.

A friendly find_record step is authored as::

    arguments:
      module: indicators
      query:
        logic: AND
        filters:
          - field: value
            operator: eq
            value: "{{ vars.input.params.indicator_value }}"
      partial: true

The handler is ``find_data(module, query, partial=True, **kw)``. Unlike
delay/code_snippet, find_record has **no friendly→canonical transform** — the
authored keys are already the wire keys. So this layer is *validation-only*:
``FindRecordArgs`` types the scalar fields (`module`, `partial`,
`checkboxFields`) so a wrong-typed value becomes a clean `BAD_VALUE` instead of
silently riding through to the runtime (the handler drops unknown/garbage
kwargs without complaint). `expand_find_record` never mutates `args` — it
returns ``None`` and the resolver keeps the original dict, its `_check_unknown_keys`
whitelist, and the editor's `query.__selectFields` cleanup rule.

`query` is left untyped (``Any``): it is normally a filter dict, but a whole-query
Jinja string (`"{{ vars.saved_query }}"`) renders to a dict at runtime, so
constraining it to `dict` would false-positive on valid authoring.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import ConfigDict

from ...errors import CompileError  # noqa: F401  (re-exported for symmetry)
from ..base import StrictArgs
from .._bridge import validate_args


class FindRecordArgs(StrictArgs):
    """Typed view of a find_record step's arguments.

    `module` is the target module name (a string, or a Jinja string that
    renders to one). `partial`/`checkboxFields` are boolean flags (pydantic
    coerces the usual `true`/`1`/`"true"` forms). `query` is passed through
    untyped. `extra="allow"` because sibling/canonical keys (`mock_result`,
    `condition`, `step_variables`, …) ride through untouched — the resolver's
    `_check_unknown_keys` has already rejected anything genuinely unknown.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    module: Optional[str] = None
    query: Optional[Any] = None
    partial: Optional[bool] = None
    checkboxFields: Optional[bool] = None


def expand_find_record(
    args: Any, path: str, errors: list[CompileError],
) -> Optional[dict]:
    """Type-validate a find_record step's arguments.

    Validation-only: always returns ``None`` (find_record has no
    friendly→canonical transform, so the resolver keeps `step.arguments`
    unchanged along with its whitelist + `__selectFields` cleanup). A bad scalar
    field (e.g. `partial: "maybe"`, `module: [1, 2]`) appends a `BAD_VALUE` and
    leaves the step for the author to fix — matching the leave-unchanged
    contract of the other step models.
    """
    if not isinstance(args, dict):
        return None
    validate_args(FindRecordArgs, args, f"{path}.arguments", errors)
    return None
