"""Typed model for the ``set_api_keys`` step (FSR handler ``SetAPIKeys``).

Friendly "Set API Keys" -- niche step exposing ``public_key``/``private_key``
(both jinja-capable). The normalizer (``_normalize_set_api_keys_args``) does no
compile-time transform: the controller only validates UI state, and the only
normalizer work is the unknown-key check against ``{public_key, private_key}``.

This layer is *validation-only* (the ``connector`` precedent): ``SetApiKeysArgs``
types the two scalars so ``get_step_arg_schema("set_api_keys")`` returns the
contract (was ``None`` -- the discover gap) and a wrong-typed value (e.g.
``public_key: 123`` instead of a string/jinja) is a clean ``BAD_VALUE``. Low
authoring frequency -- the win is schema introspection, not correction.

DESIGN SPLIT: the typed model owns the envelope schema + scalar validation; the
normalizer owns the ``_check_unknown_keys`` against the two-key canonical set.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import ConfigDict

from ...errors import CompileError  # noqa: F401  (re-exported for symmetry)
from ..base import StrictArgs
from .._bridge import validate_args


class SetApiKeysArgs(StrictArgs):
    """Typed view of a set_api_keys step's envelope scalars.

    ``public_key`` and ``private_key`` are optional strings (jinja-capable, so a
    ``{{ ... }}`` value is valid). Wrong-typed (e.g. a list) is a clean
    ``BAD_VALUE``. Both declared Optional -- the controller validates UI state at
    runtime, not compile, so neither is required here.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    public_key: Optional[str] = None
    private_key: Optional[str] = None


def expand_set_api_keys(
    args: Any, path: str, errors: list[CompileError],
) -> Optional[dict]:
    """Type-validate a set_api_keys step's envelope scalars.

    Validation-only: always returns ``None`` (the normalizer does no transform).
    A bad scalar (e.g. ``public_key: 123``) appends a ``BAD_VALUE``.
    """
    if not isinstance(args, dict):
        return None
    validate_args(SetApiKeysArgs, args, f"{path}.arguments", errors)
    return None
