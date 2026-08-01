"""Boundary models for playbook JSON the **appliance** hands us.

`typed_args/` models the arguments we *generate*. This module models the
other direction: the crudhub responses we *consume*. Nothing covered that,
which is how a dict-vs-list `steps` shape crashed the pre-write loss gate
into refusing every edit of an affected playbook (`61a18c1`).

Three properties made that bug survivable, and this module targets each:

1. **`dict[str, Any]` admits everything.** `wf.get("steps")` is `Any`, so
   iterating it and indexing the result both type-check. mypy sat at zero
   errors the whole time. Declaring the shape once, here, is the only way a
   static or runtime check can see it at all.
2. **Two sources shared one type.** Compiler output and live platform JSON
   are both `dict[str, Any]`, so reusing a compiler-side helper on live data
   looked perfectly correct. `parse_live_collection` marks which is which.
3. **The caller failed closed.** A crash inside a guard that reports every
   exception as "refusing the save" presents as the guard *working*. So the
   rule here is: a shape problem must name the field and the observed shape
   (`WireShapeError`), never collapse into a generic failure.

## Why this validates but does not re-serialize

The obvious design -- parse into models, pass `model_dump()` inward -- is
wrong for this codebase. The decompiler reads dozens of wire keys we do not
model, and a declared field with a default would *inject* keys the appliance
never sent (`arguments: {}` on a step that had none), silently changing what
the round-trip corpus compares. So:

- the models declare the shape and are what the tests pin;
- `normalize_live_collection` returns the ORIGINAL dicts with only the
  nested-record containers coerced to lists -- no key is added, dropped, or
  retyped.

That keeps the boundary honest without making this module a second, subtly
different copy of the wire format.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, field_validator

__all__ = [
    "WireShapeError",
    "LiveStep",
    "LiveRoute",
    "LiveWorkflow",
    "LiveCollection",
    "LiveEnvelope",
    "as_record_list",
    "parse_live_collection",
    "normalize_live_collection",
]


class WireShapeError(ValueError):
    """A live response was not a shape we can read.

    Carries `field` and `observed` so a fail-closed caller can say *what*
    was wrong instead of "the check could not run". Never raise this with a
    message that omits both.
    """

    def __init__(self, field: str, observed: Any, detail: str = "") -> None:
        self.field = field
        self.observed = type(observed).__name__
        suffix = f": {detail}" if detail else ""
        super().__init__(
            f"live playbook JSON: `{field}` arrived as {self.observed}, "
            f"which is not a record list or an id-keyed record map{suffix}"
        )


def as_record_list(field: Any, *, path: str = "records") -> List[Dict[str, Any]]:
    """Nested records as a LIST, whichever wire shape they arrived in.

    A live crudhub GET can return `steps`/`routes` keyed by id
    (`{"<uuid>": {...}}`) where the export JSON returns a list. Iterating the
    dict form yields its string KEYS, so `s["uuid"]` raised
    `TypeError: string indices must be integers`.

    THE one place that coercion lives. Consumers call this (or take already
    normalized input) rather than each defending itself -- a defense repeated
    per consumer is a defense that will be missed at the next consumer.
    """
    if field is None:
        return []
    if isinstance(field, dict):
        return [v for v in field.values() if isinstance(v, dict)]
    if isinstance(field, list):
        return [v for v in field if isinstance(v, dict)]
    raise WireShapeError(path, field)


class _WireRecord(BaseModel):
    """Base for a crudhub record.

    `extra="allow"` because the appliance sends far more than we model
    (timestamps, ownership, layout, `@id`), and dropping unmodelled keys here
    would quietly delete data the decompiler reads. This layer's job is to
    assert the shape of what we DO read, not to define the wire format.
    """

    model_config = ConfigDict(extra="allow")


class LiveStep(_WireRecord):
    uuid: str = ""
    name: str = ""
    # An IRI string in export JSON, an expanded dict under
    # `?$relationships=true`. Both are real; neither is normalized here --
    # `_step_type_key` / `_to_uuid` already read both, and rewriting it would
    # change what the round-trip corpus compares.
    stepType: Any = None
    arguments: Optional[Dict[str, Any]] = None

    @field_validator("arguments", mode="before")
    @classmethod
    def _empty_args_may_arrive_as_a_list(cls, v: Any) -> Any:
        """An argument-less step can come back as `[]`, not `{}`.

        LIVE-VERIFIED: 9 of 1676 steps on a real appliance send
        `"arguments": []`. PHP/Doctrine serializes an empty associative array
        as a JSON array, so "no arguments" and "empty object" are the same
        value upstream. Typing this `Dict` alone would have rejected those
        steps -- i.e. this model, written from fixtures, was wrong about real
        data in exactly the way the bug it exists to prevent was.

        A NON-empty list is still an error: that would be a genuinely
        different shape, and silently discarding it is how arguments go
        missing.
        """
        if isinstance(v, list):
            if v:
                raise WireShapeError("step.arguments", v,
                                     "a non-empty list is not an argument map")
            return {}
        return v


class LiveRoute(_WireRecord):
    uuid: str = ""
    name: str = ""
    label: Optional[str] = None
    sourceStep: Any = None
    targetStep: Any = None


class LiveWorkflow(_WireRecord):
    uuid: str = ""
    name: str = ""
    steps: List[LiveStep] = []
    routes: List[LiveRoute] = []

    @field_validator("steps", "routes", mode="before")
    @classmethod
    def _coerce_records(cls, v: Any, info: Any) -> Any:
        return as_record_list(v, path=f"workflow.{info.field_name}")


class LiveCollection(_WireRecord):
    uuid: str = ""
    name: str = ""
    workflows: List[LiveWorkflow] = []

    @field_validator("workflows", mode="before")
    @classmethod
    def _coerce_workflows(cls, v: Any, info: Any) -> Any:
        return as_record_list(v, path=f"collection.{info.field_name}")


class LiveEnvelope(BaseModel):
    """The `{"data": [collection]}` envelope every consumer here expects."""

    model_config = ConfigDict(extra="allow")

    data: List[LiveCollection] = []


def parse_live_collection(payload: Any) -> LiveEnvelope:
    """Typed view of a live `{"data": [...]}` playbook pull.

    Raises `WireShapeError` (naming the field and shape) or pydantic's
    `ValidationError` (naming the field path) on anything unreadable. Callers
    that fail closed must surface that text -- see the module docstring.
    """
    if not isinstance(payload, dict):
        raise WireShapeError("<envelope>", payload, "expected a {\"data\": [...]} dict")
    return LiveEnvelope.model_validate(payload)


def normalize_live_collection(payload: Any) -> Dict[str, Any]:
    """Validate a live pull, then hand back the SAME dicts with nested record
    containers coerced to lists.

    Call this once at the seam where crudhub JSON enters -- everything inward
    (decompiler, roundtrip, the pre-write gate) then sees the single canonical
    shape instead of guessing per call site. Deliberately not a `model_dump`:
    see "Why this validates but does not re-serialize" above.
    """
    parse_live_collection(payload)  # raises, naming the field, if unreadable

    out = dict(payload)
    colls = []
    for coll in as_record_list(payload.get("data"), path="data"):
        c = dict(coll)
        wfs = []
        for wf in as_record_list(c.get("workflows"), path="collection.workflows"):
            w = dict(wf)
            if "steps" in w:
                w["steps"] = as_record_list(w.get("steps"), path="workflow.steps")
            if "routes" in w:
                w["routes"] = as_record_list(w.get("routes"), path="workflow.routes")
            wfs.append(w)
        if "workflows" in c:
            c["workflows"] = wfs
        colls.append(c)
    out["data"] = colls
    return out
