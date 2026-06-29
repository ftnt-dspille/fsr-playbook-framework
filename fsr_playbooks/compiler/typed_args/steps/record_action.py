"""Typed model for the record-action trigger (`start` with a `module:`).

A `start` step that names a `module:` is the manual record-action trigger
(FSR handler ``cybersponse.action``) — the Execute-menu button on a module's
record listing. Its friendly inputs::

    button_label:     Trigger Button Label (str). Empty → FSR shows the playbook
                      name. `title:` is the same field under its wire name.
    module / modules: which module(s) the button appears on.
    requires_record:  bool, default True. False = "Does not require record input
                      to run".
    run_mode:         'per_record' (default) | 'once_for_all' — only meaningful
                      when requires_record is True.

Unlike delete_record/record_crud this has **no module→IRI transform** — the
canonical shape (route uuid5, `displayConditions`, `step_variables`, the
`noRecordExecution`/`singleRecordExecution` flag pair) is heavy and stays in the
resolver. So this layer is *validation-only* (the `find_record` precedent):
`RecordActionArgs` types the scalar flags so a wrong-typed value is a clean
`BAD_VALUE` instead of silently mis-routing. The big silent-failure it catches is
a mistyped `run_mode` — the imperative code does
``singleRecordExecution = (requires_record and run_mode == "per_record")``, so
``run_mode: "per record"`` (a space) would quietly flip the button to
once-for-all. `expand_record_action` never mutates `args` — it returns ``None``
and the resolver keeps the full transform.

`module`/`modules`/`resources` stay untyped (`Any`): `module:` may be a single
name OR a list, and `resources:` is the canonical list form.
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import ConfigDict

from ...errors import CompileError  # noqa: F401  (re-exported for symmetry)
from ..base import StrictArgs
from .._bridge import validate_args


class RecordActionArgs(StrictArgs):
    """Typed view of a record-action (`start` + `module:`) step's arguments.

    `button_label`/`title` are the Trigger Button Label (strings). `requires_record`
    toggles record-context requirement (pydantic coerces the usual
    ``true``/``1``/``"true"`` forms). `run_mode` is constrained to the two valid
    enum values so a typo is a clean `BAD_VALUE`. `module`/`modules`/`resources`
    and the canonical trigger keys ride through via ``extra="allow"``.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    button_label: Optional[str] = None
    title: Optional[str] = None
    requires_record: Optional[bool] = None
    run_mode: Optional[Literal["per_record", "once_for_all"]] = None


def expand_record_action(
    args: Any, path: str, errors: list[CompileError],
) -> Optional[dict]:
    """Type-validate a record-action step's scalar flags.

    Validation-only: always returns ``None`` (the canonical transform stays in
    the resolver, so `step.arguments` is untouched). A bad flag (e.g.
    `requires_record: "yes"`, `run_mode: "per record"`) appends a `BAD_VALUE`
    and leaves the step for the author to fix — matching the leave-unchanged
    contract of the other validation-only step models (`find_record`).
    """
    if not isinstance(args, dict):
        return None
    validate_args(RecordActionArgs, args, f"{path}.arguments", errors)
    return None
