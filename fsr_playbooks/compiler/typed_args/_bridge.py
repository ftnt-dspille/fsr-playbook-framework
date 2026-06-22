"""The single seam between pydantic and the CompileError pipeline.

No typed-args model leaks a `ValidationError` into the compiler. Everything
goes through `validate_args`, which:

  * runs `model_cls.model_validate(raw, context=...)` with a fresh warnings
    list threaded through the context,
  * on success, drains the context warnings into `errors` and returns the
    validated model,
  * on `ValidationError`, maps every error `loc` onto the existing dotted
    CompileError `path` (preserving `severity="error"`) and returns `None`.

This keeps rule 1 (auto-correct → warning) and rule 2 (hard shape error →
error) from `base.py` in one place.
"""
from __future__ import annotations

from typing import Any, Optional, TypeVar

from pydantic import BaseModel, ValidationError

from ..errors import CompileError, ErrorCode

M = TypeVar("M", bound=BaseModel)

# pydantic error "type" → our ErrorCode. Anything unmapped falls back to
# BAD_VALUE, which is the right default for a malformed value/shape.
_TYPE_TO_CODE: dict[str, ErrorCode] = {
    "missing": ErrorCode.MISSING_FIELD,
    "extra_forbidden": ErrorCode.UNKNOWN_PARAM,
}


def loc_to_path(prefix: str, loc: tuple[Any, ...]) -> str:
    """Join a pydantic error `loc` onto a dotted/bracketed compiler path.

    int → `[i]` (list index), str → `.key`. Discriminated-union tag segments
    (e.g. the literal `'primitive'`) read as a normal `.primitive` and are
    harmless context for the reader. Example:
    prefix=`...arguments.when`, loc=`('filters', 1, 'op')`
    → `...arguments.when.filters[1].op`.
    """
    path = prefix
    for part in loc:
        if isinstance(part, int):
            path += f"[{part}]"
        else:
            path += f".{part}"
    return path


def validate_args(
    model_cls: type[M],
    raw: Any,
    path: str,
    errors: list[CompileError],
    *,
    extra_context: Optional[dict[str, Any]] = None,
) -> Optional[M]:
    """Validate `raw` against `model_cls`, bridging to CompileErrors.

    `path` is the step-relative dotted prefix the warnings/errors hang off
    (e.g. `playbooks[0].steps[2].arguments.when`). Returns the validated
    model on success (warnings already appended to `errors`), or `None` if a
    hard ValidationError fired (its errors appended to `errors`).
    """
    context: dict[str, Any] = {"path": path, "warnings": []}
    if extra_context:
        context.update(extra_context)
    try:
        model = model_cls.model_validate(raw, context=context)
    except ValidationError as e:
        for err in e.errors():
            code = _TYPE_TO_CODE.get(err["type"], ErrorCode.BAD_VALUE)
            errors.append(CompileError(
                code=code,
                message=err["msg"],
                path=loc_to_path(path, err["loc"]),
                severity="error",
            ))
        # Still surface any warnings recorded before the raise.
        errors.extend(context["warnings"])
        return None
    errors.extend(context["warnings"])
    return model
