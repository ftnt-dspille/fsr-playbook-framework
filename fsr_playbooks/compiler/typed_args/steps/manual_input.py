"""Typed model for `manual_input` step arguments.

A friendly manual_input step is authored as::

    arguments:
      title: "Approve?"
      description: "Optional markdown body"
      options: [Continue]                 # or [{option: yes, primary: true}, ...]
      inputs:                             # optional fields to collect
        - {name: comment, kind: textarea, label: "Comment", required: true}

and expands to FSR's canonical InputBased shape (`input.schema` +
`response_mapping` + a dozen always-present sibling fields).

Unlike decision/record_crud, this layer is **validation-only**: the
friendly→canonical transform (branch-label promotion, mode-aware co-presence
checks, the InputBased default, the empty-description fallback) is large,
battle-tested, and was the F3 bug site — it stays in the imperative normalizer
(`resolver/normalizers.py::_normalize_manual_input_args`). `ManualInputArgs`
exists for two jobs the imperative path doesn't do:

  * It is the **introspection surface**: `STEP_ARG_MODELS["manual_input"]` makes
    `emit_step_arg_schema("manual_input")` emit a JSON Schema (the friendly form
    is the public authoring contract).
  * It **types the scalar fields** so a wrong-typed value (e.g.
    `is_approval: "maybe"`, `timeout: "soon"`, `title: [1, 2]`) becomes a clean
    `BAD_VALUE` instead of riding silently through the transform.

`extra="allow"` because the canonical sibling keys (`input`, `record`,
`owner_detail`, `response_mapping`, the email-template keys, …) ride through
untouched — the imperative normalizer's whitelist already owns unknown-key
rejection, so this model must not re-reject them. Structural/ambiguous fields
(`input`, `record`, `options`, `inputs`, `type`) are left untyped (`Any`):
their shape rules and the `type` dispatch-value check are owned by the
imperative path, and typing them here would either duplicate those errors or
false-positive on valid authoring (e.g. `record` is `""` *or* a record ref;
an `options` entry is a bare string *or* a dict).
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import ConfigDict

from ...errors import CompileError  # noqa: F401  (re-exported for symmetry)
from ..base import StrictArgs
from .._bridge import validate_args


class ManualInputArgs(StrictArgs):
    """Typed view of a manual_input step's friendly arguments.

    Only the unambiguous scalar fields are typed; everything structural rides
    through as extra (`extra="allow"`). See the module docstring for why the
    transform and the `input`/`type` shape rules stay in the imperative
    normalizer.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    # Friendly authoring scalars.
    title: Optional[str] = None
    description: Optional[str] = None
    # Canonical scalar flags (FSR booleans; pydantic coerces true/false/0/1/"yes"…).
    is_approval: Optional[bool] = None
    isRecordLinked: Optional[bool] = None
    unauthenticated_input: Optional[bool] = None
    # Audience/email-template scalars.
    timeout: Optional[int] = None
    internal_email_subject: Optional[str] = None
    external_email_subject: Optional[str] = None


def expand_manual_input(
    args: Any, path: str, errors: list[CompileError],
) -> Optional[dict]:
    """Type-validate a manual_input step's scalar arguments.

    Validation-only: always returns ``None``. The friendly→canonical transform
    stays in `_normalize_manual_input_args`, so the resolver keeps `step.arguments`
    and runs the transform after this check. A bad scalar (e.g. `timeout: "soon"`)
    appends a `BAD_VALUE` and leaves the step for the author to fix — matching the
    leave-unchanged contract of `expand_find_record`.
    """
    if not isinstance(args, dict):
        return None
    validate_args(ManualInputArgs, args, f"{path}.arguments", errors)
    return None
