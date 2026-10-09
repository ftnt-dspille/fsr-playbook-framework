"""Render a playbook's Jinja offline, and say which reads come out empty.

`step_through_playbook` renders through the box's Jinja endpoint; with no box it
used to hand the raw template back and report nothing, so "does this playbook
run" had no offline answer. This renders locally in a sandbox against sample
data -- a sample trigger record built from the module's fields, and connector
outputs built from shapes recorded on real runs -- and records every read that
resolves to nothing.

What it can and cannot say:

* A read that is EMPTY against known data is a real defect: the field is not on
  the module, or the path is not in the op's recorded output. Live (analyst
  sim), `vars.input.records[0].destIp` and
  `vars.steps.VT.data.data.attributes.last_analysis_stats.malicious | default(0)`
  -- the second never errors, it is just always 0, so the block never runs.
  That is why a value swallowed by `default` / `int` / `float` is reported too.
* Data nobody knows (an op with no recorded run, a module the catalog lacks) is
  an :class:`Opaque` placeholder: every read through it succeeds and is marked
  unverified, never empty. Guessing there would make the walk lie.
* A filter this sandbox does not implement (FortiSOAR ships the Ansible set)
  leaves that template unrendered, reported as such -- not as a failure.
"""
from __future__ import annotations

import contextvars
import json
import re
from typing import Any

from jinja2 import ChainableUndefined, TemplateError
from jinja2.sandbox import SandboxedEnvironment

# Reads that came out empty during the current render. A contextvar, not an
# attribute, because jinja creates Undefined objects deep inside its runtime.
_HITS: contextvars.ContextVar[list[str] | None] = contextvars.ContextVar(
    "_local_render_hits", default=None)

_EXPR_ONLY = re.compile(r"^\s*\{\{(.*)\}\}\s*$", re.S)


class Known(dict):
    """Data we actually know: a catalog sample record, or an output built from
    a recorded run. Only a key missing from one of THESE is reported -- a miss
    on anything else (button inputs, playbook parameters, values computed from
    unknown data) is a gap in the walk's context, not in the playbook."""

    # A catalog record lists every field the module has, so a miss there is
    # certain. A recorded output is ONE run: an optional key it happened not
    # to carry is not proof the key never appears.
    certain = True


class Recorded(Known):
    certain = False


def _hit(kind: str, name: Any) -> None:
    hits = _HITS.get()
    if hits is not None:
        hits.append(f"{kind}:{name}")


class _Empty(ChainableUndefined):
    """A missing value that remembers being USED (printed, tested, compared).
    Merely reaching it is fine -- `x is defined` and `x | default(y)` must not
    count as a read of `x`."""

    def _known_miss(self) -> bool:
        return isinstance(self._undefined_obj, Known)

    def _used(self) -> None:
        if self._known_miss():
            _hit("empty" if self._undefined_obj.certain else "empty?",
                 self._undefined_name)

    def __str__(self) -> str:
        self._used()
        return ""

    def __bool__(self) -> bool:
        self._used()
        return False

    def __iter__(self):
        self._used()
        return iter(())

    def __len__(self) -> int:
        self._used()
        return 0

    def __eq__(self, other: object) -> bool:
        self._used()
        return isinstance(other, _Empty)

    def __ne__(self, other: object) -> bool:
        return not self.__eq__(other)

    __hash__ = ChainableUndefined.__hash__


class Opaque:
    """Data whose shape nobody knows. Every attribute, index and filter reads
    through; it renders as a marker and counts as unverified, never empty."""

    __slots__ = ("label",)

    def __init__(self, label: str = "unknown"):
        self.label = label

    def __getattr__(self, name: str) -> Opaque:
        if name.startswith("__"):
            raise AttributeError(name)
        _hit("opaque", self.label)
        return self

    def __getitem__(self, _key: Any) -> Opaque:
        _hit("opaque", self.label)
        return self

    def __iter__(self):
        return iter((self,))

    def __len__(self) -> int:
        return 1

    def __bool__(self) -> bool:
        return True

    def __int__(self) -> int:
        return 1

    def __float__(self) -> float:
        return 1.0

    def __str__(self) -> str:
        return f"<{self.label}>"

    def __repr__(self) -> str:
        return f"Opaque({self.label!r})"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Opaque)

    def __hash__(self) -> int:
        return hash(self.label)


def _swallowing(name: str, fn):
    """Wrap a filter that turns a missing value into a fallback: the fallback
    is the symptom we are looking for, so note it before it disappears."""
    def wrapped(value, *a, **k):
        if isinstance(value, _Empty) and value._known_miss():
            _hit("defaulted" if value._undefined_obj.certain else "defaulted?",
                 f"{value._undefined_name} | {name}")
            hits = _HITS.get()
            if hits is not None:
                # It was not printed; drop the plain-empty note it may raise.
                token = _HITS.set([])
                try:
                    return fn(value, *a, **k)
                finally:
                    _HITS.reset(token)
        return fn(value, *a, **k)
    return wrapped


def _env() -> SandboxedEnvironment:
    env = SandboxedEnvironment(undefined=_Empty, autoescape=False,
                               extensions=["jinja2.ext.do",
                                           "jinja2.ext.loopcontrols"])
    for n in ("default", "d", "int", "float"):
        env.filters[n] = _swallowing(n, env.filters[n])
    # The FortiSOAR / Ansible filters playbooks use most that jinja lacks.
    env.filters.setdefault("to_json", lambda v, **_k: json.dumps(v, default=str))
    env.filters.setdefault("from_json", lambda v: json.loads(v) if isinstance(v, str) else v)
    env.filters.setdefault("bool", lambda v: str(v).lower() in ("1", "true", "yes", "on")
                           if not isinstance(v, bool) else v)
    env.filters.setdefault("regex_search", lambda v, p, *a: (
        m.group(0) if (m := re.search(p, str(v))) else None))
    env.filters.setdefault("regex_replace", lambda v, p="", r="", **_k: re.sub(p, r, str(v)))
    return env


_ENV = _env()


def render(template: str, context: dict[str, Any]) -> dict[str, Any]:
    """Render one template against `{"vars": ...}`-style context.

    Returns ``{value, empty: [...], defaulted: [...], opaque: bool,
    unrendered: str | None}``. A lone ``{{ expr }}`` keeps its native value
    (a list stays a list), like FortiSOAR's evaluator."""
    hits: list[str] = []
    token = _HITS.set(hits)
    try:
        m = _EXPR_ONLY.match(template)
        if m and "{{" not in m.group(1) and "{%" not in template:
            value = _ENV.compile_expression(m.group(1).strip(),
                                            undefined_to_none=False)(**context)
            if isinstance(value, _Empty):
                value._used()
                value = ""
        else:
            value = _ENV.from_string(template).render(**context)
    except TemplateError as exc:
        return {"value": template, "empty": [], "defaulted": [], "unconfirmed": [],
                "opaque": False, "unrendered": str(exc)}
    except Exception as exc:  # noqa: BLE001 -- a sandbox refusal, a bad call
        return {"value": template, "empty": [], "defaulted": [], "unconfirmed": [],
                "opaque": False, "unrendered": f"{type(exc).__name__}: {exc}"}
    finally:
        _HITS.reset(token)
    def names(*kinds: str) -> list[str]:
        return sorted({h.split(":", 1)[1] for h in hits
                       if h.split(":", 1)[0] in kinds})
    return {
        "value": value,
        "empty": names("empty", "empty?"),
        "defaulted": names("defaulted", "defaulted?"),
        # Misses on a recorded output only: real, or an optional key the
        # recording lacked. Everything else in empty/defaulted is certain.
        "unconfirmed": names("empty?", "defaulted?"),
        "opaque": any(h.startswith("opaque:") for h in hits),
        "unrendered": None,
    }


# --------------------------------------------------------------------------- #
# Sample data
# --------------------------------------------------------------------------- #

_SAMPLE_IP = "198.51.100.7"  # TEST-NET-2: never a real host


def sample_from_shape(shape: Any, _depth: int = 0) -> Any:
    """A value with the recorded shape (`grounded_shapes`). Non-empty scalars,
    one element per list, so every path the shape knows resolves."""
    if not isinstance(shape, dict) or _depth > 12:
        return Opaque("recorded shape too deep")
    kind = shape.get("kind")
    if isinstance(shape.get("keys"), dict) and kind in (None, "object"):
        return Recorded({k: sample_from_shape(v, _depth + 1)
                         for k, v in shape["keys"].items()})
    if kind == "list":
        item = shape.get("item")
        return [sample_from_shape(item, _depth + 1)] if item else []
    if kind == "unknown":
        return Opaque("unrecorded part of the output")
    t = shape.get("type")
    return {"integer": 1, "number": 1.0, "boolean": True,
            "null": None}.get(str(t), "sample")


def sample_record(fields: list[tuple[str, str, str | None]], module: str) -> dict[str, Any]:
    """A record of `module` with every catalog field filled: `fields` is
    `(name, type, picklist_name)` rows. System fields come along."""
    rec: dict[str, Any] = Known({
        "@id": f"/api/3/{module}/00000000-0000-4000-8000-0000000000aa",
        "@type": module.rstrip("s").capitalize(),
        "id": 1, "uuid": "00000000-0000-4000-8000-0000000000aa",
        "createDate": 1700000000, "modifyDate": 1700000000,
        "createUser": {"@id": "/api/3/people/00000000-0000-4000-8000-000000000001"},
        "recordTags": [], "owners": [], "tenant": None,
    })
    for name, ftype, picklist in fields:
        t = (ftype or "").lower()
        if picklist:
            rec[name] = {"@id": "/api/3/picklists/00000000-0000-4000-8000-000000000002",
                         "itemValue": "Sample"}
        elif t in ("integer", "decimal", "number", "datetime", "date"):
            rec[name] = 1700000000 if "date" in t else 1
        elif t in ("checkbox", "boolean"):
            rec[name] = True
        elif name.lower().endswith("ip") or "ipaddress" in name.lower():
            rec[name] = _SAMPLE_IP
        else:
            rec[name] = f"sample {name}"
    return rec
