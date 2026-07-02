"""Typed model for the ``api_endpoint`` trigger (FSR handler
``cybersponse.api_call``) -- the Custom API Endpoint start variant.

A playbook whose start step is ``type: api_endpoint`` is invokable via
``POST /api/triggers/1/<route>``. Its friendly inputs::

    route:                  the endpoint name -> URL path segment. Token-based
                            auth (the default) exposes it at
                            ``/api/triggers/1/<route>``; the deferred modes
                            (anonymous / Basic) route at ``deferred/<route>``.
    authentication_methods: optional. Defaults to token-based (``[""]``) -- the
                            only mode that exposes the bare route. ``["anonymous"]``
                            = No-Auth, ``["Basic"]`` = HTTP Basic.

The canonical transform (the token-based auth default + the trigger-infra
``step_variables``/``triggerOnSource``/``triggerOnReplicate``/``__triggerLimit``
setdefaults) stays in the resolver (``_normalize_api_endpoint_args``), mirroring
the other trigger step types. So this layer is *validation-only* (the
``find_record`` / ``record_action`` precedent): ``ApiEndpointArgs`` types the
scalar fields so a wrong-typed value (e.g. ``route: 123``,
``authentication_methods: "token"`` instead of a list) is a clean ``BAD_VALUE``
instead of silently riding through to a malformed trigger.
``expand_api_endpoint`` never mutates ``args`` -- it returns ``None`` and the
resolver keeps the full transform.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import ConfigDict

from ...errors import CompileError  # noqa: F401  (re-exported for symmetry)
from ..base import StrictArgs
from .._bridge import validate_args


class ApiEndpointArgs(StrictArgs):
    """Typed view of an api_endpoint (Custom API Endpoint) trigger's args.

    `route` is the endpoint name (a string, or a Jinja string that renders to
    one). `authentication_methods` is the auth-mode list (token-based `[""]` is
    the compiler default, so it is optional here). Both ride through via
    ``extra="allow"`` -- the resolver's ``_check_unknown_keys`` has already
    rejected anything genuinely unknown, and the canonical trigger-infra keys
    are filled by the imperative transform after this walk.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    route: Optional[str] = None
    authentication_methods: Optional[list[str]] = None


def expand_api_endpoint(
    args: Any, path: str, errors: list[CompileError],
) -> Optional[dict]:
    """Type-validate an api_endpoint trigger's scalar arguments.

    Validation-only: always returns ``None`` (the friendly->canonical transform
    -- the token-based auth default + trigger-infra setdefaults -- stays in
    ``_normalize_api_endpoint_args``, so ``step.arguments`` is untouched). A bad
    scalar (e.g. ``route: 123``, ``authentication_methods: "token"``) appends a
    ``BAD_VALUE`` and leaves the step for the author to fix -- matching the
    leave-unchanged contract of the other validation-only trigger models.
    """
    if not isinstance(args, dict):
        return None
    validate_args(ApiEndpointArgs, args, f"{path}.arguments", errors)
    return None
