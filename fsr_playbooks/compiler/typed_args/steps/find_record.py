"""Typed model for `find_record` step arguments.

A friendly find_record step is authored as::

    module: indicators
    filters:
      - field: value
        operator: eq
        value: "{{ vars.input.params.indicator_value }}"
    limit: 1000          # optional, default 30
    logic: AND           # optional, default AND
    partial: true        # optional, default true
    sort:                # optional
      - field: createDate
        direction: DESC
    select: [name, status]   # optional field projection

The handler is ``find_data(module, query, partial=True, **kw)``.
``filters:`` / ``limit:`` / ``logic:`` / ``sort:`` / ``select:`` are
friendly keys that compile to the wire ``query:`` envelope; the raw
``query:`` key is still accepted for back-compat.

Two of these do not end up where a reader would expect, because the
platform ignores them in the obvious place:

* ``limit:`` is additionally appended to the module as ``?$limit=N``.
  The body value alone is ignored at execution -- every shipped Solution
  Pack playbook carries the suffix, and a body-only limit silently
  truncates the result set to 30 rows.
* ``select:`` sets ``checkboxFields: true`` alongside the projection,
  because the editor deletes ``__selectFields`` when that flag is false. This layer is validation-only for the scalar
fields; the friendly→canonical transform lives in the normalizer's
``_normalize_find_record_args``.
"""
from __future__ import annotations

from typing import Any

from pydantic import ConfigDict

from ...errors import CompileError  # noqa: F401  (re-exported for symmetry)
from .._bridge import validate_args
from ..base import StrictArgs


class FindRecordArgs(StrictArgs):
    """Typed view of a find_record step's arguments.

    `module` is the target module name. `partial`/`checkboxFields` are
    boolean flags. `filters`/`limit`/`logic` are the friendly form that
    compiles to the wire `query:` envelope. `query` is the raw wire form
    (still accepted). `extra="allow"` because sibling/canonical keys ride
    through untouched -- the resolver's `_check_unknown_keys` has already
    rejected anything genuinely unknown.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    module: str | None = None
    query: Any | None = None
    partial: bool | None = None
    checkboxFields: bool | None = None
    filters: Any | None = None
    limit: int | None = None
    logic: str | None = None
    relationships: bool | None = None
    sort: list | None = None
    select: list | None = None
    max_relations: int | None = None


def expand_find_record(
    args: Any, path: str, errors: list[CompileError],
) -> dict | None:
    """Type-validate a find_record step's arguments.

    Validation-only: always returns ``None`` (the friendly→canonical
    transform lives in the normalizer). A bad scalar field (e.g.
    `partial: "maybe"`, `module: [1, 2]`) appends a `BAD_VALUE` and
    leaves the step for the author to fix.
    """
    if not isinstance(args, dict):
        return None
    validate_args(FindRecordArgs, args, f"{path}.arguments", errors)
    return None
