"""Typed model for the ``send_email`` step (FSR handler ``SendMail``).

Friendly SMTP email step — a `SendMail` connector-family alias. The normalizer
(``_normalize_send_email_args`` + the caller's connector-family defaulting
block) defaults `connector: smtp` + `operation: send_email`; `_resolve_connector_args`
auto-lifts the flat email fields into `params:` + stamps `version`/`operationTitle`
from the catalog. The smtp connector's `send_email` op takes `body`/`from` natively
(verified live on 8.0), so there is NO `body`->`content` / `from`->`from_str`
rename — the friendly author surface IS the canonical email field shape.

This layer is *validation-only* (the ``connector`` / ``api_endpoint`` precedent):
``SendEmailArgs`` types the envelope scalars so an agent can introspect "what
does a send_email step take?" via ``get_step_arg_schema("send_email")`` and a
wrong-typed scalar (e.g. ``to: "alice"`` instead of a list, ``subject: 42``)
becomes a clean ``BAD_VALUE`` instead of riding through.

DESIGN SPLIT (the manual_input / connector lesson, applied up front):
  * The typed model owns the **envelope schema** (introspection) + scalar
    validation. It does NOT shadow the resolver's richer messages.
  * The normalizer owns the unknown-key check (``_check_unknown_keys``) +
    connector/op defaulting; the connector resolver owns the auto-lift + catalog
    stamp + op/param checks.
"""
from __future__ import annotations

from typing import Any, List, Optional, Union

from pydantic import ConfigDict, Field

from ...errors import CompileError  # noqa: F401  (re-exported for symmetry)
from ..base import StrictArgs
from .._bridge import validate_args


class SendEmailArgs(StrictArgs):
    """Typed view of a send_email step's envelope scalars.

    ``to`` / ``cc`` / ``bcc`` are optional recipient lists (strings or IRIs the
    editor resolves); ``subject`` is an optional string; ``body`` is the rendered
    body; ``from`` is the sender. ``attachments`` rides through as Any. The SMTP
    connector envelope keys (``connector``/``operation``/``config``/``version``/
    ``params``/``operationTitle``) are accepted via ``extra="allow"`` -- a
    ``send_email`` step is a connector-family call under the hood (smtp/
    send_email), but the *friendly* author surface is the email fields, so the
    typed model names those; the rest rides through.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    to: Optional[Union[str, List[str]]] = None
    cc: Optional[Union[str, List[str]]] = None
    bcc: Optional[Union[str, List[str]]] = None
    subject: Optional[str] = None
    body: Optional[Any] = None
    from_: Optional[str] = Field(default=None, alias="from")
    attachments: Optional[Any] = None


def expand_send_email(
    args: Any, path: str, errors: list[CompileError],
) -> Optional[dict]:
    """Type-validate a send_email step's envelope scalars.

    Validation-only: always returns ``None`` (the normalizer's
    ``_normalize_send_email_args`` owns the unknown-key check + connector/op
    defaulting, and the connector resolver owns the auto-lift + catalog checks,
    so ``step.arguments`` is untouched here). A bad envelope scalar (e.g.
    ``subject: 42``) appends a ``BAD_VALUE`` and leaves the step for the
    normalizer's own checks to also run.
    """
    if not isinstance(args, dict):
        return None
    validate_args(SendEmailArgs, args, f"{path}.arguments", errors)
    return None
