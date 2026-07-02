"""Typed model for the ``approval`` step (FSR handler ``Approval``).

Friendly human-approval step. The normalizer (``_normalize_approval_args``) owns
the transform: the editor hardcodes ``collection: approvals`` (bundle line 37501)
and builds an ``approvals`` record under ``resource`` (assignedTo / owners /
userOwners / approvaldescription / status); the normalizer fills the collection
and defaults ``resource`` to ``{}``. Legacy ``approvers`` is accepted but not
synthesized (the editor migrates it into ``resource.assignedTo``/``owners`` on
save). ``response_mapping`` / ``timeout`` pass through.

This layer is *validation-only* (the ``connector`` precedent): ``ApprovalArgs``
types the envelope so ``get_step_arg_schema("approval")`` returns the contract
(was ``None`` -- the discover gap) and a wrong-typed scalar (e.g.
``resource: "x"`` instead of a mapping, ``timeout: "soon"`` instead of a number)
is a clean ``BAD_VALUE``. The normalizer owns the ``collection``/``resource``
setdefaults + unknown-key check; the typed layer does not shadow it.

DESIGN SPLIT: the typed model owns the envelope schema + scalar validation; the
normalizer owns the setdefaults + ``_check_unknown_keys``.
"""
from __future__ import annotations

from typing import Any, Optional, Union

from pydantic import ConfigDict

from ...errors import CompileError  # noqa: F401  (re-exported for symmetry)
from ..base import StrictArgs
from .._bridge import validate_args


class ApprovalArgs(StrictArgs):
    """Typed view of an approval step's envelope scalars.

    ``collection`` is the target module (the normalizer defaults it to
    ``"approvals"``); declared Optional so a missing value does NOT raise here.
    ``resource`` is the approval record body (a mapping); wrong-typed is a clean
    ``BAD_VALUE``. ``timeout`` is an optional number (seconds); a non-numeric
    value is a ``BAD_VALUE``. ``response_mapping`` is optional Any (the
    post-approval field map). Legacy ``approvers`` rides ``extra="allow"``.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    collection: Optional[str] = None
    resource: Optional[Any] = None
    timeout: Optional[Union[int, float]] = None
    response_mapping: Optional[Any] = None


def expand_approval(
    args: Any, path: str, errors: list[CompileError],
) -> Optional[dict]:
    """Type-validate an approval step's envelope scalars.

    Validation-only: always returns ``None`` (the normalizer's
    ``_normalize_approval_args`` owns the ``collection``/``resource`` setdefaults,
    so ``step.arguments`` is untouched here). A bad envelope scalar (e.g.
    ``timeout: "soon"``) appends a ``BAD_VALUE`` and leaves the step for the
    normalizer's own checks to also run.
    """
    if not isinstance(args, dict):
        return None
    validate_args(ApprovalArgs, args, f"{path}.arguments", errors)
    return None
