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

from typing import Any, Literal, Optional, TypeAlias

from pydantic import ConfigDict

from ...errors import CompileError  # noqa: F401  (re-exported for symmetry)
from ..base import StrictArgs
from .._bridge import validate_args

# The closed set of input-field `kind:` values, derived from the single source
# of truth -- the resolver's live-grounded `PicklistMixin._INPUT_FIELD_KINDS`
# dict (each row picked by probing real FSR; see that dict's docstring). We
# derive the pydantic `Literal` here instead of re-listing the kinds so the two
# can NEVER drift. If a kind is added/removed in the resolver, this `Literal`
# and the JSON Schema it emits track it automatically.
from ...resolver.picklists import PicklistMixin

# Build the Literal[...] from the dict keys at import time. `Literal.__getitem__`
# accepts the tuple of kind strings and returns the parametrized type.
_KIND_KEYS = tuple(sorted(PicklistMixin._INPUT_FIELD_KINDS))
InputFieldKind: TypeAlias = Literal[_KIND_KEYS]  # type: ignore[valid-type]


class InputVariableArgs(StrictArgs):
    """Typed view of a single ``manual_input.arguments.inputs[]`` entry.

    The friendly per-field contract a manual_input form collects. ``name`` is
    required (the variable name, referenced after resume as
    ``vars.steps.<step_name>.input.<name>``); ``kind`` is one of the 29 live-
    grounded FSR field kinds (see ``InputFieldKind`` above). ``label``/``tooltip``
    are display strings, ``required`` is a bool. ``default`` stays ``Any`` (it
    may be a literal OR a Jinja expression, so strict per-kind typing would
    false-positive). ``options``/``module``/``picklist`` are the per-kind
    required siblings (see ``_KIND_REQUIRES`` below) -- typed ``Any`` because
    the runtime co-presence check owns the cleaner suggestion-bearing error.

    ``extra="forbid"`` mirrors the resolver's per-entry whitelist
    (``_expand_input_variables``), so a typo'd entry key (``tooptip:``,
    ``requred:``) is caught here as ``UNKNOWN_PARAM`` -- additive to the
    resolver's own check. The already-expanded pass-through (an entry carrying
    its own ``formType`` + ``templateUrl``) is handled by the resolver BEFORE
    this model sees it, so it never round-trips through here.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    name: str
    kind: InputFieldKind
    label: Optional[str] = None
    tooltip: Optional[str] = None
    required: Optional[bool] = None
    default: Optional[Any] = None
    options: Optional[Any] = None
    module: Optional[Any] = None
    picklist: Optional[Any] = None
    # `type` is the canonical formType/dataType escape hatch the resolver's
    # pass-through uses; friendly authoring rarely sets it, but it is in the
    # resolver's whitelist, so we allow it to avoid a false UNKNOWN_PARAM.
    type: Optional[Any] = None


# Which per-kind sibling is REQUIRED for the field to be usable. Mirrors the
# runtime co-presence checks in `_expand_input_variables` (select/multiselect
# -> options, lookup -> module, picklist/multiselectpicklist -> picklist). The
# runtime check owns the suggestion-bearing error; this map is the
# introspection surface an agent reads via the schema (a future enhancement
# could emit a per-kind discriminated union advertising it -- for now it lives
# here as the single documented truth).
_KIND_REQUIRES: dict[str, str] = {
    "select": "options",
    "multiselect": "options",
    "lookup": "module",
    "picklist": "picklist",
    "multiselectpicklist": "picklist",
}


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
    # The friendly form fields a manual_input collects. Nested typing makes the
    # 29-kind contract introspectable via `get_step_arg_schema("manual_input")`
    # -- the discover win (was: `inputs` was `Any`, schema emitted `{}`). The
    # friendly→canonical transform (inputVariables expansion) stays in the
    # resolver; this is the introspection + per-entry validation surface. A
    # wrong-typed entry (`name: 123`, unknown `kind`) is a clean BAD_VALUE /
    # UNKNOWN_PARAM here, additive to the resolver's own checks.
    inputs: Optional[list[InputVariableArgs]] = None


def expand_manual_input(
    args: Any, path: str, errors: list[CompileError],
) -> Optional[dict]:
    """Type-validate a manual_input step's scalar arguments.

    Validation-only: always returns ``None``. The friendly->canonical transform
    stays in `_normalize_manual_input_args`, so the resolver keeps `step.arguments`
    and runs the transform after this check. A bad scalar (e.g. `timeout: "soon"`)
    appends a ``BAD_VALUE`` and leaves the step for the author to fix -- matching the
    leave-unchanged contract of ``expand_find_record``.

    ``inputs`` is intentionally NOT runtime-validated here even though the model
    types it: the resolver's ``_expand_input_variables`` owns the per-entry errors
    and produces richer, suggestion-bearing messages (```inputs[].name` is
    required``, ``unknown key(s) on inputs[] entry: 'bogus'``, difflib kind
    suggestions) than pydantic's generic ``Field required`` / ``Extra inputs are
    not permitted``. Validating here would shadow them. The model still types
    ``inputs`` so ``emit_step_arg_schema`` describes the 28-kind contract (the
    discover win); we just strip it before ``validate_args`` so only the scalar
    fields run through the typed layer at compile time. The per-entry co-presence
    + alias checks stay the resolver's job.
    """
    if not isinstance(args, dict):
        return None
    # Validate only the scalar fields; strip `inputs` so the resolver's richer
    # per-entry errors own that surface. (Schema emission reads the model, not
    # this stripped dict, so the introspection win is unaffected.)
    scalar_only = {k: v for k, v in args.items() if k != "inputs"}
    validate_args(ManualInputArgs, scalar_only, f"{path}.arguments", errors)
    return None
