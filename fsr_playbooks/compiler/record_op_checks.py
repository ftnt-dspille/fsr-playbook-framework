"""Static schema checks for record-write and connector steps.

Pure functions over *injected* catalog facts (required-field sets, declared
op-param names, connector-config status), so they stay offline-testable; the
MCP verify layer (`tools_verify._per_step_schema_checks`) supplies DB-backed
lookups from the warmed reference DB.

Each function returns a list of issue dicts in the `_per_step_schema_checks`
shape: ``{code, message, step, path, suggestion, severity, near?}``. An empty
list means "nothing to flag" — including the deliberate "no catalog data, so
don't guess" case (callers pass empty facts when the warm hasn't run).

Grounding (2026-06-26 pilot, .205 warm):
  - F  required_record_field_missing  → E7 (`source_id` absent from `resource`)
  - G  op_param_unknown_name / required_op_param_missing → E8 + the
        `body_type`-vs-`content_type` "wrong param name" class
  - connector_config_missing / _no_default → the empty-`config:` bind failure
"""
from __future__ import annotations

import difflib
from typing import Any, Iterable, Optional

# F applies to record *creation* only. `update_record` is a partial patch —
# an absent required field is legal there (you're updating a subset), so
# requiring completeness on update would false-positive.
RECORD_CREATE_TYPES = frozenset({"create_record", "insert_record"})

# Config-LESS built-in connectors: their ops run with an empty `config: ''` and
# they never carry a saved configuration, so a step that pins no config binds
# fine. Without this, `connector_config_missing` fires as a *required fix* on
# every such step (the connector has zero rows in `connector_configs`, which the
# check otherwise reads as "unconfigured → empty config can't bind"). That is a
# false positive that costs an authoring model several wasted turns fighting the
# gate — observed live: a build turn burned ~6 tool calls (retrying verify,
# mis-formatting `disable_checks`, tripping the repeated-call guard) before
# abandoning verify for `dry_run`. `cyops_utilities` is the FortiSOAR built-in
# Utilities connector — the same one that backs `no_op`/`stop`/`end` steps — and
# is universally present and config-less. (The catalog's `config_schema_json` is
# empty across the board even in warmed DBs, so it cannot distinguish config-less
# from config-required; this authoritative set is the reliable signal. Broaden it
# only for another connector proven config-less, and cover it with a test.)
CONFIG_LESS_CONNECTORS = frozenset({"cyops_utilities"})


def _is_dynamic(value: Any) -> bool:
    """A Jinja-templated value — we can't statically know what it renders to."""
    return isinstance(value, str) and ("{{" in value or "{%" in value)


def _iri_tail(value: str) -> str:
    """`/api/3/alerts?x` → `alerts`; a bare name passes through unchanged."""
    v = value
    if "/api/" in v:
        v = v.split("/api/", 1)[1]
        # drop a leading version segment like `3/`
        parts = [p for p in v.split("/") if p]
        if parts and parts[0].isdigit():
            parts = parts[1:]
        v = parts[0] if parts else v
    return v.split("?", 1)[0].strip()


def check_record_module(
    *,
    module: Any,
    known_modules: Iterable[str],
    step_id: str = "",
    path: str = "",
) -> list[dict[str, Any]]:
    """A `create_record`/`update_record` whose `module` is not a real module.

    Gated on the module catalog being warmed (``known_modules`` non-empty). A
    Jinja-templated module is skipped (can't resolve statically). Accepts the
    friendly name or an `/api/3/<module>` IRI.
    """
    known = {m for m in (known_modules or []) if m}
    if not isinstance(module, str) or not module.strip() or _is_dynamic(module):
        return []
    if not known:
        return []
    name = _iri_tail(module)
    if name in known:
        return []
    near = difflib.get_close_matches(name, sorted(known), n=3, cutoff=0.5)
    msg = f"module {name!r} does not exist on the target"
    sug = None
    if near:
        msg += f" — did you mean {', '.join(repr(n) for n in near)}?"
        sug = f"use module {near[0]!r}"
    return [{
        "code": "unknown_module",
        "message": msg,
        "step": step_id,
        "path": f"{path}.arguments.module" if path else "",
        "suggestion": sug,
        "near": near,
        "severity": "error",
    }]


def check_required_record_fields(
    *,
    module: Optional[str],
    resource: Any,
    required_fields: Iterable[str],
    step_id: str = "",
    path: str = "",
) -> list[dict[str, Any]]:
    """F — a `create_record` whose `resource` omits a required module field.

    Complements the render-path `required-arg-empty` check (which catches a
    *present* key that renders to ""/null): this catches a key that is
    *structurally absent*. Only fires when the module's required-field set is
    known (non-empty) — an unknown/un-warmed module yields no facts, no flags.
    """
    req = sorted({f for f in (required_fields or []) if f})
    if not module or not req or not isinstance(resource, dict):
        return []
    present = set(resource.keys())
    issues: list[dict[str, Any]] = []
    for field in req:
        if field not in present:
            issues.append({
                "code": "required_record_field_missing",
                "message": (f"create_record into {module!r} is missing required "
                            f"field {field!r} — the record API rejects this with "
                            f"'This value should not be blank'"),
                "step": step_id,
                "path": f"{path}.arguments.resource" if path else "",
                "suggestion": f"add {field!r} to arguments.resource",
                "severity": "error",
            })
    return issues


def check_unknown_record_fields(
    *,
    module: Optional[str],
    resource: Any,
    known_fields: Iterable[str],
    step_id: str = "",
    path: str = "",
) -> list[dict[str, Any]]:
    """A `resource` key that is not a field of the target module.

    The field-level analogue of `op_param_unknown_name`, and the inverse of
    `check_required_record_fields`. **Warning**, not error: our `module_fields`
    snapshot is a subset (e.g. it omits some system fields like `sourceData`),
    so a hard error would false-block legitimate writes. Gated on the module's
    field set being known (non-empty).
    """
    known = {f for f in (known_fields or []) if f}
    if not module or not known or not isinstance(resource, dict):
        return []
    issues: list[dict[str, Any]] = []
    for key in sorted(k for k in resource.keys() if k not in known):
        near = difflib.get_close_matches(key, sorted(known), n=1, cutoff=0.7)
        msg = f"module {module!r} has no field {key!r}"
        sug = None
        if near:
            msg += f" — did you mean {near[0]!r}?"
            sug = f"rename field {key!r} → {near[0]!r}"
        issues.append({
            "code": "unknown_record_field",
            "message": msg,
            "step": step_id,
            "path": f"{path}.arguments.resource.{key}" if path else "",
            "suggestion": sug,
            "near": near,
            "severity": "warning",
        })
    return issues


def check_op_params(
    *,
    connector: Optional[str],
    operation: Optional[str],
    params: Any,
    declared_params: Iterable[str],
    required_params: Iterable[str],
    step_id: str = "",
    path: str = "",
) -> list[dict[str, Any]]:
    """G — connector-op param completeness + name validity.

    Two checks, both gated on the op actually being in the catalog
    (``declared_params`` non-empty):

      - **unknown param name** (warning): a key in `params` that is not a
        declared param of this op — the "I typed `body_type` instead of
        `content_type`" class. Warning, not error: FSR tolerates some extras,
        and an over-eager error would block valid playbooks.
      - **required param missing** (error): a declared *unconditional* required
        param with no key present. (Conditionally-required params are excluded
        upstream — only top-level always-required names belong in
        ``required_params`` — so this never false-fires on a param that's only
        required when a sibling is set.)
    """
    declared = {p for p in (declared_params or []) if p}
    if not connector or not operation or not declared or not isinstance(params, dict):
        return []
    present = set(params.keys())
    issues: list[dict[str, Any]] = []

    for name in sorted(present - declared):
        near = difflib.get_close_matches(name, sorted(declared), n=1, cutoff=0.6)
        msg = (f"connector {connector!r} op {operation!r} has no param "
               f"{name!r}")
        sug = None
        if near:
            msg += f" — did you mean {near[0]!r}?"
            sug = f"rename param {name!r} → {near[0]!r}"
        issues.append({
            "code": "op_param_unknown_name",
            "message": msg,
            "step": step_id,
            "path": f"{path}.arguments.params.{name}" if path else "",
            "suggestion": sug,
            "near": near,
            "severity": "warning",
        })

    for name in sorted({p for p in (required_params or []) if p} - present):
        issues.append({
            "code": "required_op_param_missing",
            "message": (f"connector {connector!r} op {operation!r} requires "
                        f"param {name!r}, which is not set"),
            "step": step_id,
            "path": f"{path}.arguments.params" if path else "",
            "suggestion": f"add {name!r} to arguments.params",
            "severity": "error",
        })
    return issues


def check_connector_config(
    *,
    connector: Optional[str],
    config_value: Any,
    configs_known: bool,
    config_names: Iterable[str],
    has_default: bool,
    step_id: str = "",
    path: str = "",
) -> list[dict[str, Any]]:
    """Connector-config existence (offline analogue of pyfsr D3).

    When a connector step pins no `config:` it binds to the connector's
    *default* configuration at runtime. Flags two failure modes:

      - **no configuration at all** (error): the connector has zero configs on
        the target, so an empty `config:` cannot bind.
      - **configs but no default** (warning): an empty `config:` has nothing to
        fall back to and may bind to an arbitrary/none config.

    Skipped entirely when the catalog has no config data warmed
    (``configs_known=False``) — absence of data is not absence of a config.

    A non-empty `config:` *name* is validated against the connector's known
    config names (`unknown_connector_config` if absent). An IRI or a Jinja
    value is trusted as-is (can't resolve statically).
    """
    if not connector or not configs_known:
        return []
    # A config-less built-in (e.g. cyops_utilities) binds fine with an empty
    # `config:` and never carries a saved config — never flag it as missing one.
    # A non-empty config *name* still falls through to name validation below.
    if connector in CONFIG_LESS_CONNECTORS and not (
            isinstance(config_value, str) and config_value.strip()):
        return []
    names = [n for n in (config_names or []) if n]
    # An explicit, non-empty config pin.
    if isinstance(config_value, str) and config_value.strip():
        val = config_value.strip()
        if _is_dynamic(val) or "/api/" in val:
            return []  # IRI / templated → trust
        if names and val not in names:
            near = difflib.get_close_matches(val, sorted(names), n=3, cutoff=0.5)
            msg = (f"connector {connector!r} has no configuration named "
                   f"{val!r}")
            sug = None
            if near:
                msg += f" — did you mean {', '.join(repr(n) for n in near)}?"
                sug = f"use config {near[0]!r}"
            return [{
                "code": "unknown_connector_config",
                "message": msg,
                "step": step_id,
                "path": f"{path}.arguments.config" if path else "",
                "suggestion": sug,
                "near": near,
                "severity": "error",
            }]
        return []
    if config_value not in (None, "", [], {}):
        return []

    if not names:
        return [{
            "code": "connector_config_missing",
            "message": (f"connector {connector!r} has no configuration on the "
                        f"target — a step with an empty config cannot bind"),
            "step": step_id,
            "path": f"{path}.arguments.config" if path else "",
            "suggestion": (f"configure {connector!r} on the target, or pin an "
                           f"existing config name/IRI in arguments.config"),
            "severity": "error",
        }]
    if not has_default:
        return [{
            "code": "connector_config_no_default",
            "message": (f"connector {connector!r} has configuration(s) but none "
                        f"is marked default; an empty config may fail to bind"),
            "step": step_id,
            "path": f"{path}.arguments.config" if path else "",
            "suggestion": (f"pin one of [{', '.join(repr(n) for n in names[:5])}] "
                           f"in arguments.config, or mark one default"),
            "severity": "warning",
        }]
    return []
