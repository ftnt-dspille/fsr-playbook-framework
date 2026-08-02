"""Boundary models for playbook JSON the **appliance** hands us.

`typed_args/` models the arguments we *generate*. This module models the
other direction: the crudhub responses we *consume*. Nothing covered that,
which is how a nested-container shape crashed the pre-write loss gate into
refusing every edit of an affected playbook (`61a18c1`).

The most valuable thing this layer found was not a shape mismatch but the
opposite failure: an **unexpanded** pull (`workflows` absent, because
`?$relationships=true` was missing) read as "the live collection is empty",
so the loss gate approved a save that deletes every workflow and called it
"no field loss". See `UnexpandedRelationshipsError`. Absence and emptiness
are different facts, and only one of them is safe.

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

from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, field_validator

__all__ = [
    "WireShapeError",
    "UnexpandedRelationshipsError",
    "require_expanded_collection",
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


class UnexpandedRelationshipsError(ValueError):
    """A live pull came back without its nested records expanded.

    LIVE-VERIFIED on two transports: `/api/3/workflow_collections/<uuid>`
    returns `workflows` **absent** unless `?$relationships=true` is set --
    not as IRI strings, not as an empty list. Absent.

    That distinction is safety-critical. "Absent" means *we never learned what
    is on the appliance*; `[]` means *we looked and it is empty*. Collapse the
    two and the pre-write loss gate compares a write against a blank -- finds
    nothing missing, reports "no field loss", and waves through a save that
    deletes every workflow in the collection. Verified end to end: the guard
    returned `ok=True` for exactly that write.

    So an unexpanded pull is UNCOMPARABLE, and must be refused rather than
    treated as empty. This is the same lesson as the original wire bug from the
    other direction: the dangerous failures are the ones that look like success.
    """

    def __init__(self, detail: str) -> None:
        super().__init__(
            f"live playbook JSON has no expanded `workflows` ({detail}). "
            "The pull is missing `?$relationships=true`, so what is on the "
            "appliance is UNKNOWN -- it must not be read as 'nothing there'."
        )


def require_expanded_collection(payload: Any) -> None:
    """Raise unless a live envelope carries expanded nested records.

    Call before any comparison that treats absence as emptiness. A collection
    whose `workflows` key is present-but-empty passes: that is a real, known,
    empty collection.
    """
    for coll in as_record_list((payload or {}).get("data"), path="data"):
        if "workflows" not in coll:
            name = coll.get("name") or coll.get("uuid") or "<unnamed>"
            raise UnexpandedRelationshipsError(f"collection {name!r}")


def as_record_list(field: Any, *, path: str = "records") -> List[Dict[str, Any]]:
    """Nested records as a LIST, whichever wire shape they arrived in.

    Handles the id-keyed map form (`{"<uuid>": {...}}`) as well as a list,
    because iterating the map yields string KEYS and `s["uuid"]` then raises
    `TypeError: string indices must be integers` -- the crash behind `61a18c1`.

    **Status of that shape: UNCONFIRMED, kept as defence.** It was inferred
    from the TypeError, never captured. Probing since has not reproduced it on
    either transport -- REST returned lists for 7752 steps across 209
    collections, and the on-platform crudhub loopback returned lists for 1551
    steps across 25. Both omit the container entirely when
    `?$relationships=true` is absent (see `UnexpandedRelationshipsError`, which
    is the failure mode that turned out to be real). Tolerating the map costs
    nothing and the original crash is still unexplained, so it stays -- but do
    not cite it as observed behaviour.

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
    # Reusable-block membership. LIVE: `None` x2651 / `str` (IRI) x107 -- never
    # an expanded dict in the sample, but `decompiler._to_uuid` accepts both and
    # a stricter type here would refuse a save over a cosmetic field.
    group: Optional[Union[str, Dict[str, Any]]] = None
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
    # Runtime-executed flag on every route the box sends (6076/6076 in the
    # live census; always bool). The emitter writes `False`; the decompiler
    # does not read it (it is a run-state field, not a compile input). Typed
    # strictly so a shape drift -- the box sending a string or int where it
    # has always sent a bool -- is caught here rather than passing through
    # `extra="allow"` unseen (#32: type the remaining live wire keys).
    isExecuted: Optional[bool] = None


class LiveWorkflow(_WireRecord):
    uuid: str = ""
    name: str = ""
    steps: List[LiveStep] = []
    routes: List[LiveRoute] = []
    # Reusable-block records. Iterated bare at `decompiler.py:1118`, i.e. the
    # exact pattern behind 61a18c1 -- so it goes through the same coercion.
    groups: List[Dict[str, Any]] = []

    # Declared input names. Typed STRICTLY as `List[str]` on purpose: losing a
    # declared parameter is one of the two original silent-loss defects this
    # whole subsystem exists for, and every consumer filters to `str`
    # (`roundtrip._normalize_workflow`, `decompiler`), so a non-str member
    # would DISAPPEAR from the loss gate's comparison instead of blocking the
    # save. Refusing loudly is the right trade for a field whose loss is
    # invisible. LIVE: list in 600/600 workflows, every element `str`.
    parameters: Optional[List[str]] = None
    # LIVE: `str` (IRI) x599 and `None` x1 -- a workflow with no trigger step
    # is rare but real, so this must stay optional.
    triggerStep: Optional[str] = None

    @field_validator("steps", "routes", "groups", mode="before")
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
            if "groups" in w:
                w["groups"] = as_record_list(w.get("groups"), path="workflow.groups")
            wfs.append(w)
        if "workflows" in c:
            c["workflows"] = wfs
        colls.append(c)
    out["data"] = colls
    return out
