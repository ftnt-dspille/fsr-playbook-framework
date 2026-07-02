"""Typed model for the ``create_task`` step (FSR handler ``ManualTask``).

Friendly "Manual Task" -- creates a record in the ``tasks`` module. The
normalizer (``_normalize_create_task_args``) owns the transform: the editor
hardcodes ``collection: tasks`` (bundle line 37569) and wraps the task-module
form fields into ``resource``; the normalizer fills the collection and defaults
``resource`` to ``{}``. The author's ``resource`` is POSTed as-is.

This layer is *validation-only* (the ``connector`` precedent): ``CreateTaskArgs``
types the envelope so ``get_step_arg_schema("create_task")`` returns the
contract (was ``None`` -- the discover gap) and a wrong-typed scalar (e.g.
``resource: "x"`` instead of a mapping, ``collection: 5``) is a clean
``BAD_VALUE``. The normalizer owns the ``collection`` default + unknown-key
check; the typed layer does not shadow it.

DESIGN SPLIT: the typed model owns the envelope schema + scalar validation; the
normalizer owns the ``collection``/``resource`` setdefaults + ``_check_unknown_keys``.
``collection`` is declared (string) but **Optional** -- the normalizer fills it,
so pydantic does not emit "Field required" and shadow the resolver.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import ConfigDict

from ...errors import CompileError  # noqa: F401  (re-exported for symmetry)
from ..base import StrictArgs
from .._bridge import validate_args


class CreateTaskArgs(StrictArgs):
    """Typed view of a create_task step's envelope scalars.

    ``collection`` is the target module (the normalizer defaults it to
    ``"tasks"``); declared Optional so a missing value does NOT raise here (the
    normalizer fills it). ``resource`` is the task record body (a mapping the
    editor builds from the task-module form fields); wrong-typed (e.g. a string)
    is a clean ``BAD_VALUE``. ``message`` rides through ``extra="allow"``.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    collection: Optional[str] = None
    resource: Optional[Any] = None


def expand_create_task(
    args: Any, path: str, errors: list[CompileError],
) -> Optional[dict]:
    """Type-validate a create_task step's envelope scalars.

    Validation-only: always returns ``None`` (the normalizer's
    ``_normalize_create_task_args`` owns the ``collection``/``resource``
    setdefaults, so ``step.arguments`` is untouched here). A bad envelope scalar
    (e.g. ``resource: "x"`` instead of a mapping) appends a ``BAD_VALUE`` and
    leaves the step for the normalizer's own checks to also run.
    """
    if not isinstance(args, dict):
        return None
    validate_args(CreateTaskArgs, args, f"{path}.arguments", errors)
    return None
