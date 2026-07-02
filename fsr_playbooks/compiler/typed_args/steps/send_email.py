"""Typed model for the ``send_email`` step (FSR handler ``SendEmail``).

Friendly SMTP email step. The normalizer (``_normalize_send_email_args``) owns
the friendly->canonical transform: ``body`` -> ``content``, ``from`` ->
``from_str``, with ``to``/``cc``/``bcc``/``subject`` passing through; it also
defaults ``from_str`` to "" (the FSR engine substitutes the SMTP config's
default-from at runtime). Canonical keys mirror the editor's SendEmail wire
shape (``docs/STEP_WIRE_SHAPES`` SendEmail).

This layer is *validation-only* (the ``connector`` / ``api_endpoint`` precedent):
``SendEmailArgs`` types the envelope scalars so an agent can introspect "what
does a send_email step take?" via ``get_step_arg_schema("send_email")`` (was
``None`` -- the discover gap this closes) and a wrong-typed scalar (e.g.
``to: "alice"`` instead of a list, ``subject: 42``) becomes a clean
``BAD_VALUE`` instead of riding through. The friendly->canonical transform stays
in the imperative normalizer; the typed layer does not shadow it.

DESIGN SPLIT (the manual_input / connector lesson, applied up front):
  * The typed model owns the **envelope schema** (introspection) + scalar
    validation. It does NOT shadow the resolver's richer messages.
  * The normalizer owns the ``body``/``from`` rename + ``from_str`` default +
    unknown-key check (``_check_unknown_keys``), which is the transform.
"""
from __future__ import annotations

from typing import Any, List, Optional, Union

from pydantic import ConfigDict

from ...errors import CompileError  # noqa: F401  (re-exported for symmetry)
from ..base import StrictArgs
from .._bridge import validate_args


class SendEmailArgs(StrictArgs):
    """Typed view of a send_email step's envelope scalars.

    ``to`` / ``cc`` / ``bcc`` are optional recipient lists (strings or IRIs the
    editor resolves); ``subject`` is an optional string; ``content`` is the
    rendered body (the normalizer moves the friendly ``body`` here); ``from_str``
    is the sender (the normalizer moves the friendly ``from`` here, defaulting
    to "" so the step compiles offline). ``attachments`` rides through as Any.
    The SMTP envelope keys (``connector``/``operation``/``config``/``version``/
    ``params``/``operationTitle``) are accepted via ``extra="allow"`` -- a
    ``send_email`` step is a connector-family call under the hood, but the
    *friendly* author surface is the email fields, so the typed model names
    those; the rest rides through.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    to: Optional[Union[str, List[str]]] = None
    cc: Optional[Union[str, List[str]]] = None
    bcc: Optional[Union[str, List[str]]] = None
    subject: Optional[str] = None
    content: Optional[Any] = None
    from_str: Optional[str] = None
    attachments: Optional[Any] = None


def expand_send_email(
    args: Any, path: str, errors: list[CompileError],
) -> Optional[dict]:
    """Type-validate a send_email step's envelope scalars.

    Validation-only: always returns ``None`` (the normalizer's
    ``_normalize_send_email_args`` owns the ``body``->``content`` /
    ``from``->``from_str`` transform + ``from_str`` default, so
    ``step.arguments`` is untouched here). A bad envelope scalar (e.g.
    ``subject: 42``) appends a ``BAD_VALUE`` and leaves the step for the
    normalizer's own checks to also run. The friendly ``body``/``from`` keys are
    accepted here too (``SendEmailArgs`` does not name them, so they ride
    ``extra="allow"``) -- the normalizer renames them before the typed call would
    re-check, but validating the canonical ``content``/``from_str`` form is the
    point.
    """
    if not isinstance(args, dict):
        return None
    validate_args(SendEmailArgs, args, f"{path}.arguments", errors)
    return None
