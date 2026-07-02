"""Typed model for the ``workflow_reference`` step (FSR handler
``WorkflowReference``) -- the local same-collection "Reference a Playbook" call.

A step that calls another playbook in the same FortiSOAR instance. Two ways to
express the target in YAML (the resolver's ``_resolve_workflow_reference_args``
enforces one-or-the-other)::

    target:           <playbook_name>  -- looked up in the same collection; the
                          emitter rewrites to /api/3/workflows/<uuid> via
                          deterministic UUID synthesis.
    workflowReference: /api/3/workflows/<uuid>  -- pass-through for cross-
                          collection references (not validated further).

The caller's ``arguments:`` map is validated against the target playbook's
``parameters:`` list when ``target`` is local.

This layer is *validation-only* (the ``connector`` / ``trigger_tenant_playbook``
precedent): ``WorkflowReferenceArgs`` types the envelope scalars so
``get_step_arg_schema("workflow_reference")`` returns the contract (was ``None``
-- the discover gap) and a wrong-typed scalar (e.g. ``target: 123``,
``workflowReference: False``) is a clean ``BAD_VALUE`` instead of riding through.
The resolver owns the required-target MISSING_FIELD check; ``target`` and
``workflowReference`` are declared **Optional** here so pydantic does NOT emit its
generic "Field required" and shadow that richer message (the manual_input /
connector lesson). The cross-tenant sibling is ``trigger_tenant_playbook``
(``RemotePlaybookReference``).
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import ConfigDict

from ...errors import CompileError  # noqa: F401  (re-exported for symmetry)
from ..base import StrictArgs
from .._bridge import validate_args


class WorkflowReferenceArgs(StrictArgs):
    """Typed view of a workflow_reference (local playbook call) step.

    ``target`` is the local playbook name (resolved via the same-collection
    name map); ``workflowReference`` is the pass-through workflow IRI for
    cross-collection references. Exactly one is required at runtime (the
    resolver enforces missing -> ``MISSING_FIELD`` with a precise message), but
    both are declared **Optional** here so pydantic does NOT emit its generic
    "Field required" and shadow that richer resolver message (the manual_input /
    connector lesson). A present-but-wrong-typed value (e.g. ``target: 123``) is
    still a clean ``BAD_VALUE``. ``arguments`` is ``Any`` -- the target's
    parameter map; validated against the target playbook's ``parameters`` by the
    resolver when ``target`` is local, so it stays loose here.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    target: Optional[str] = None
    workflowReference: Optional[str] = None
    arguments: Optional[Any] = None


def expand_workflow_reference(
    args: Any, path: str, errors: list[CompileError],
) -> Optional[dict]:
    """Type-validate a workflow_reference step's envelope scalars.

    Validation-only: always returns ``None`` (the resolver's
    ``_resolve_workflow_reference_args`` owns the target lookup + required-field
    check + parameter validation, so ``step.arguments`` is untouched). A bad
    envelope scalar (e.g. ``target: 123``) appends a ``BAD_VALUE`` and leaves the
    step for the resolver's checks to also run. Does NOT re-validate ``target``/
    ``workflowReference`` presence (the resolver's ``MISSING_FIELD`` message is
    more precise than pydantic's "Field required") -- it only flags a
    present-but-wrong-typed value.
    """
    if not isinstance(args, dict):
        return None
    validate_args(WorkflowReferenceArgs, args, f"{path}.arguments", errors)
    return None
