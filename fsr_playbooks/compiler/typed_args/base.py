"""Foundation for the typed-argument layer.

Pydantic is built to *raise* on bad input. The compiler's contract is the
opposite: lenient auto-correct with an accumulating warning trail (see
`compiler/errors.py::CompileError`). So pydantic enters as a typed
*argument-shape* layer, never as a replacement for the CompileError pipeline.

Two rules every typed-args model follows:

  1. Coercion / auto-correct happens inside validators and records a
     human-facing note through `ValidationInfo.context["warnings"]`. The
     model returns valid; the caller (`_bridge.validate_args`) drains those
     warnings into `CompileError(severity="warning")`.
  2. Hard shape/type errors raise `ValidationError`; the bridge maps each
     error `loc` onto the existing dotted CompileError `path` and keeps
     `severity="error"`.

`StrictArgs` is the shared base: `extra="forbid"` so an unknown authoring key
is a structural error instead of silently dropped, plus a small helper for
appending a warning to the validation context.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict

from ..errors import CompileError, ErrorCode


class StrictArgs(BaseModel):
    """Base for every typed argument model.

    `extra="forbid"` makes unknown keys a structural error (surfaced as
    `unknown_param`). Models that wrap genuinely pass-through FSR wire args
    override this with `model_config = ConfigDict(extra="allow")`.
    `populate_by_name` lets a field declare an `alias` for its FSR wire key
    (e.g. `_operator`) while staying a normal Python attribute.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


def add_warning(
    context: Optional[dict[str, Any]],
    message: str,
    *,
    code: ErrorCode = ErrorCode.BAD_VALUE,
    sub_path: str = "",
    near: Optional[str] = None,
    suggestion: Optional[str] = None,
) -> None:
    """Append an auto-correct warning to the validation context.

    `context` is the dict passed as `model_validate(..., context=...)`. It
    carries `path` (the step-relative dotted prefix, e.g.
    `playbooks[0].steps[2].arguments.when`) and a `warnings` list that the
    bridge drains into CompileErrors. `sub_path` is appended to `path` to
    point at the offending leaf (e.g. `.filters[1].op`). A no-op when no
    context was supplied (lets the models be unit-tested standalone).
    """
    if context is None:
        return
    warnings = context.setdefault("warnings", [])
    base = context.get("path", "")
    full = f"{base}{sub_path}" if base else sub_path
    warnings.append(CompileError(
        code=code,
        message=message,
        path=full,
        near=near,
        suggestion=suggestion,
        severity="warning",
    ))
