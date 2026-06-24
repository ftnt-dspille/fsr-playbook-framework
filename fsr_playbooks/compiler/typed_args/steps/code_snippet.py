"""Typed model for `code_snippet` step arguments.

A friendly code_snippet step is authored as::

    arguments:
      code: |
        print("hello")
      config: my_config    # optional connector-config name or UUID

and expands to FSR's canonical CodeSnippet step shape with defaults for
connector, operation, version, and params.python_function. Already-canonical
args (connector+operation+params present) pass through untouched.

`CodeSnippetArgs` types the friendly `code`/`python` fields so a non-string
value becomes a clean `BAD_VALUE` diagnostic. `expand_code_snippet` owns the
friendly→canonical transform, preserving the imperative `_normalize_code_snippet_args`
byte-for-byte for valid input (same defaults, same key order, same empty-check).

The config field is passed through as-is (name or UUID); the resolver's
`_normalize_code_snippet_args` detects which it is and calls `resolve_config_id`
to inject the real config UUID afterward. This separation keeps the typed layer
catalog-independent and byte-identical with the imperative path.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import ConfigDict

from ...errors import CompileError, ErrorCode  # noqa: F401  (re-exported for symmetry)
from ..base import StrictArgs
from .._bridge import validate_args


class CodeSnippetArgs(StrictArgs):
    """Typed view of a friendly code_snippet step's arguments.

    The `code` and `python` fields are optional strings (pydantic coerces any
    non-string as a clean BAD_VALUE). `config` is optional and passed through
    untouched (name or UUID). `extra="allow"` because canonical/sibling keys
    (connector, operation, operationTitle, version, params, step_variables,
    pickFromTenant, mock_result, condition) ride through untouched — the
    resolver's `_check_unknown_keys` has already rejected anything genuinely
    unknown.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    code: Optional[str] = None
    python: Optional[str] = None
    config: Optional[Any] = None


def expand_code_snippet(
    args: Any, path: str, errors: list[CompileError],
) -> Optional[dict]:
    """Expand friendly code args into the canonical CodeSnippet shape.

    Returns the canonical dict, or ``None`` to leave `step.arguments` unchanged
    — when the input is not a dict, is already canonical (connector+operation+params
    present), or a friendly field fails validation (a `BAD_VALUE` is appended
    and the step is left for the author to fix).

    The resolver's `_normalize_code_snippet_args` calls this to do the
    friendly→canonical transform, then handles config UUID resolution via
    `resolve_config_id`. This separation keeps the typed layer
    catalog-independent and byte-identical with the imperative path.

    The `config` field is NOT consumed here — it's left in the returned dict
    for the resolver to handle (detect if name vs UUID, pop it, resolve UUID).
    """
    if not isinstance(args, dict):
        return None

    # Already-canonical input passes through untouched (matches the imperative
    # early return before any transform).
    if args.get("connector") and args.get("operation") and args.get("params"):
        return None

    model = validate_args(CodeSnippetArgs, args, f"{path}.arguments", errors)
    if model is None:
        return None

    a = dict(args)  # copy: friendly keys are consumed, siblings preserved in order

    # Extract and consume the friendly code/python fields.
    code = a.pop("code", None) or a.pop("python", None) or ""

    # Set canonical defaults.
    a.setdefault("connector", "code-snippet")
    a.setdefault("operation", "python_inline_code_editor")
    a.setdefault("operationTitle", "Execute Python Code")
    a.setdefault("version", "2.1.4")
    a.setdefault("step_variables", [])

    # Build params dict with the code as python_function.
    params = a.get("params") if isinstance(a.get("params"), dict) else {}
    params.setdefault("python_function", code)
    a["params"] = params

    return a
