"""Typed model for the ``trigger_tenant_playbook`` step (FSR handler
``RemotePlaybookReference``) -- the "Trigger Tenant Playbook" editor palette
entry: a cross-tenant call to a playbook in another FortiSOAR tenant.

It owns a distinct script handler (``/wf/workflow/tasks/remote_workflow_reference``,
uuid ``ab3b2e02-5e77-4ed6-8ebd-580f390063a5``), so it is a real step type --
not a connector-family alias. Unlike the local ``workflow_reference``
(``WorkflowReference``, which targets a same-collection playbook by name/IRI),
the remote task starts execution of a workflow on a *peer instance*. Its
handler signature (live-captured in the ``step_handlers`` table) is::

    remote_workflow_reference(playbook_alias_id, tenant_id=None, *args, **kwargs)

so the friendly inputs are::

    playbook_alias_id:   required. A playbook alias that points to the remote
                         workflow to be run (the cross-tenant target). FSR
                         resolves the alias to the peer workflow at runtime.
    tenant_id:           optional. The peer tenant to run the workflow in.

Everything else rides through ``extra="allow"`` (the handler accepts
``**kwargs``, so unknown keys are *warnings*, not errors -- surfaced by
``arg_validator`` against the live signature, not by this model).

DESIGN SPLIT (the manual_input / connector lesson): this layer is
*validation-only* -- ``TriggerTenantPlaybookArgs`` types the scalar fields so a
wrong-typed value (e.g. ``playbook_alias_id: 123``, ``tenant_id: 7``) is a
clean ``BAD_VALUE`` instead of silently riding through. The resolver
(``_resolve_trigger_tenant_playbook_args``) owns the runtime required-field
check (missing ``playbook_alias_id`` -> ``MISSING_FIELD``); ``playbook_alias_id``
is declared Optional here so pydantic does NOT emit its generic "Field
required" and shadow that richer message. The handler-signature pass in
``arg_validator`` independently enforces the same required arg against the live
DB -- belt and suspenders.

GROUNDING: the field set is the live ``remote_workflow_reference`` handler
signature from the ``step_handlers`` table (``inspect.signature()`` of the
FSR runtime function), not a docstring/guess.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import ConfigDict

from ...errors import CompileError  # noqa: F401  (re-exported for symmetry)
from ..base import StrictArgs
from .._bridge import validate_args


class TriggerTenantPlaybookArgs(StrictArgs):
    """Typed view of a trigger_tenant_playbook (cross-tenant reference) step.

    ``playbook_alias_id`` is the cross-tenant playbook alias -- required at
    runtime (the resolver enforces missing -> ``MISSING_FIELD`` with a precise
    message; the live ``remote_workflow_reference`` handler signature requires
    it too), but declared **Optional** here so pydantic does NOT emit its
    generic "Field required" and shadow that richer resolver message (the
    manual_input / connector lesson). A present-but-wrong-typed value (e.g.
    ``playbook_alias_id: 123``) is still a clean ``BAD_VALUE``. ``tenant_id``
    is the optional peer-tenant target. The rest of the envelope
    (``step_variables``, ``when``, ``for_each``, ``do_until``, ``message``,
    ``ignore_errors``, ``mock_result``, ``arguments``) rides through
    ``extra="allow"`` -- the handler accepts ``**kwargs``.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    playbook_alias_id: Optional[str] = None
    tenant_id: Optional[str] = None
    arguments: Optional[Any] = None


def expand_trigger_tenant_playbook(
    args: Any, path: str, errors: list[CompileError],
) -> Optional[dict]:
    """Type-validate a trigger_tenant_playbook step's envelope scalars.

    Validation-only: always returns ``None`` (the resolver's
    ``_resolve_trigger_tenant_playbook_args`` owns the required-field check,
    so ``step.arguments`` is untouched). A bad envelope scalar (e.g.
    ``playbook_alias_id: 123``, ``tenant_id: 7``) appends a ``BAD_VALUE`` and
    leaves the step for the resolver's checks to also run. Does NOT re-validate
    ``playbook_alias_id`` presence (the resolver's ``MISSING_FIELD`` message
    is more precise than pydantic's "Field required") -- it only flags a
    present-but-wrong-typed value.
    """
    if not isinstance(args, dict):
        return None
    validate_args(TriggerTenantPlaybookArgs, args, f"{path}.arguments", errors)
    return None
