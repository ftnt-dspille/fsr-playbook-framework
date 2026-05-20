"""ConnectorArgsMixin — resolving connector and workflow reference arguments."""
from __future__ import annotations

import difflib
import ipaddress
import json as _json
import re
import sqlite3
from datetime import datetime
from typing import Optional

from ..errors import CompileError, ErrorCode
from ..ir import Step


# Observed-type validators (Tier 2.3). Each returns True iff the value
# is acceptable under that type. All accept native Python types straight
# through and fall back to coercion attempts on strings. None of them
# allocate beyond what Python's stdlib already costs — they run per
# param at compile time, so they need to stay cheap.

_URL_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]*://[^\s]+$")
# Pragmatic email regex — RFC 5322 is too permissive to be useful as a
# *typo* check, which is the goal here. The pattern matches the
# overwhelming-majority "local@host.tld" shape; anything weirder is
# unlikely to be intentional in a connector param.
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _is_ipv4(v) -> bool:
    if not isinstance(v, str):
        return False
    try:
        ipaddress.IPv4Address(v.strip())
        return True
    except (ipaddress.AddressValueError, ValueError):
        return False


def _is_url(v) -> bool:
    return isinstance(v, str) and bool(_URL_RE.match(v.strip()))


def _is_email(v) -> bool:
    return isinstance(v, str) and bool(_EMAIL_RE.match(v.strip()))


def _is_iso8601(v) -> bool:
    """True if v parses as ISO 8601 (with or without time).

    `fromisoformat` covers the standard variants that FSR connectors
    accept. Native datetime/date objects pass through. Epoch numbers
    are *not* accepted here — those have their own observed_type
    (`epoch_seconds` / `epoch_millis`); mixing them would dilute the
    diagnostic value.
    """
    if isinstance(v, datetime):
        return True
    if not isinstance(v, str):
        return False
    s = v.strip()
    if not s:
        return False
    try:
        datetime.fromisoformat(s)
        return True
    except ValueError:
        return False


def _is_json_object(v) -> bool:
    """True if v is a dict (or a string that parses to a dict).

    Connector params widget-typed `json` accept either form on the wire —
    the FSR runtime json.loads strings before passing through. List-of-
    items is handled separately via the `json_array` observed_type.
    """
    if isinstance(v, dict):
        return True
    if not isinstance(v, str):
        return False
    try:
        return isinstance(_json.loads(v), dict)
    except (_json.JSONDecodeError, TypeError):
        return False


def _is_json_array(v) -> bool:
    if isinstance(v, list):
        return True
    if not isinstance(v, str):
        return False
    try:
        return isinstance(_json.loads(v), list)
    except (_json.JSONDecodeError, TypeError):
        return False


# Map observed_type → (display_name, validator, suggestion-tail). The
# Tier 1 widget pass already covers `int` / `float` / `bool` / `picklist`
# / `str` (str is permissive). We only register here the *additional*
# types Tier 2 unlocks.
_OBSERVED_VALIDATORS: dict[str, tuple[str, "callable", str]] = {
    "ipv4": ("IPv4 address", _is_ipv4,
             "pass a dotted-quad address like '10.0.0.1'"),
    "url":  ("URL", _is_url,
             "pass a full URL including scheme, e.g. 'https://example.com/path'"),
    "email": ("email address", _is_email,
              "pass an address like 'user@example.com'"),
    "iso8601": ("ISO 8601 timestamp", _is_iso8601,
                "pass a timestamp like '2026-05-20T12:34:00Z' or '2026-05-20'"),
    "json_object": ("JSON object", _is_json_object,
                    "pass a YAML mapping or a JSON-encoded string"),
    "json_array": ("JSON array", _is_json_array,
                   "pass a YAML list or a JSON-encoded array string"),
}


def _coerces_to_int(v) -> bool:
    """True if value is something the FSR runtime can pass to int().
    Native ints (excluding bool, which is treated separately) pass; bare
    strings pass only if int(str) succeeds. Floats are rejected — author
    likely meant a decimal-typed param if they wrote 1.5."""
    if isinstance(v, bool):
        return False
    if isinstance(v, int):
        return True
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return False
        try:
            int(s)
            return True
        except (TypeError, ValueError):
            return False
    return False


def _coerces_to_float(v) -> bool:
    if isinstance(v, bool):
        return False
    if isinstance(v, (int, float)):
        return True
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return False
        try:
            float(s)
            return True
        except (TypeError, ValueError):
            return False
    return False


def _coerces_to_bool(v) -> bool:
    """True if value is bool-like. FSR's checkbox params accept native
    bools, 'true'/'false' (case-insensitive), and 0/1 ints."""
    if isinstance(v, bool):
        return True
    if isinstance(v, int) and v in (0, 1):
        return True
    if isinstance(v, str):
        return v.strip().lower() in {"true", "false", "yes", "no", "1", "0"}
    return False


class ConnectorArgsMixin:
    """Methods for resolving connector args and checking routing."""

    conn: sqlite3.Connection

    def _resolve_connector_args(
        self, step: Step, path: str, errors: list[CompileError],
    ) -> None:
        a = step.arguments
        connector = a.get("connector")
        operation = a.get("operation")
        if not connector:
            errors.append(CompileError(
                code=ErrorCode.MISSING_FIELD,
                message="connector step requires arguments.connector",
                path=f"{path}.arguments.connector",
            ))
            return
        if not operation:
            errors.append(CompileError(
                code=ErrorCode.MISSING_FIELD,
                message="connector step requires arguments.operation",
                path=f"{path}.arguments.operation",
            ))
            return

        crow = self.connector(connector)
        if crow is None:
            sug = self.suggest_connector(connector)
            errors.append(CompileError(
                code=ErrorCode.UNKNOWN_CONNECTOR,
                message=f"unknown connector: {connector!r}",
                path=f"{path}.arguments.connector",
                near=sug,
                suggestion=f"did you mean {sug!r}?" if sug else None,
            ))
            return

        orow = self.operation(connector, operation)
        if orow is None:
            sug = self.suggest_operation(connector, operation)
            if sug:
                suggestion = f"did you mean {sug!r}?"
            else:
                topn = self.suggest_operations_topn(connector, operation)
                suggestion = (
                    f"closest ops: {', '.join(repr(o) for o in topn)}"
                    if topn else
                    f"run `fsrpb find op {connector} <keyword>` to list operations"
                )
            errors.append(CompileError(
                code=ErrorCode.UNKNOWN_OPERATION,
                message=f"unknown operation {operation!r} on connector {connector!r}",
                path=f"{path}.arguments.operation",
                near=sug,
                suggestion=suggestion,
            ))
            return

        # Check params against operation_params.
        # When the store has zero rows for this op (catalog connector not
        # installed on the probe instance), skip validation and emit a
        # warning so the playbook still compiles.
        valid_params = set(self.operation_params(connector, operation))
        # Auto-lift flat args: agent often writes connector params at the
        # `arguments:` top level instead of under `arguments.params:`.
        # Lift any top-level key that matches a known op param into the
        # params dict (with a warning so the rule sticks). Reserved
        # canonical keys are left where they are.
        _CONNECTOR_RESERVED = {
            "connector", "operation", "operationTitle", "version", "config",
            "params", "step_variables", "pickFromTenant", "name",
            "mock_result", "useMockOutput",
            # Generic step-level skip gate. FSR evaluates it at runtime;
            # falsy → step is bypassed. Whitelisted here so the resolver
            # doesn't auto-lift it into params or flag it as unknown.
            "condition",
        }
        if valid_params:
            lifted: list[str] = []
            existing_params = a.get("params") if isinstance(a.get("params"), dict) else None
            for k in list(a.keys()):
                if k in _CONNECTOR_RESERVED:
                    continue
                if k in valid_params:
                    if existing_params is None:
                        existing_params = {}
                        a["params"] = existing_params
                    existing_params.setdefault(k, a.pop(k))
                    lifted.append(k)
            if lifted:
                errors.append(CompileError(
                    code=ErrorCode.BAD_VALUE,
                    message=(
                        f"connector params {', '.join(repr(k) for k in lifted)} "
                        f"were at `arguments:` top level — lifted into "
                        f"`arguments.params:` (write them there directly)"
                    ),
                    path=f"{path}.arguments",
                    severity="warning",
                ))
        provided = a.get("params") or {}
        if not isinstance(provided, dict):
            errors.append(CompileError(
                code=ErrorCode.BAD_VALUE,
                message="arguments.params must be a mapping",
                path=f"{path}.arguments.params",
            ))
            return
        if not valid_params:
            # Two sub-cases:
            #   1. Op genuinely takes no params (e.g. cyops_utilities.no_op,
            #      auto-injected by the compiler for `stop`/`end`). User
            #      passed nothing → silent.
            #   2. User passed params we can't verify because the param
            #      probe didn't capture this op. Emit the warning so they
            #      know something might be wrong.
            if provided:
                errors.append(CompileError(
                    code=ErrorCode.UNKNOWN_PARAM,
                    message=(
                        f"no param schema in store for {connector}.{operation} — "
                        f"params passed through unvalidated"
                    ),
                    path=f"{path}.arguments.params",
                    near=None,
                    suggestion="run `fsrpb run-op` or re-ingest the connector to populate the schema",
                    severity="warning",
                ))
        else:
            for p_name in provided:
                if p_name not in valid_params:
                    m = difflib.get_close_matches(p_name, list(valid_params), n=1, cutoff=0.6)
                    sug = m[0] if m else None
                    if sug:
                        suggestion = f"did you mean {sug!r}?"
                    else:
                        # Lexical match failed; just list the valid params.
                        # Param sets are small (median ~4) so this is cheap.
                        listed = ", ".join(repr(p) for p in sorted(valid_params))
                        suggestion = f"valid params: {listed}"
                    errors.append(CompileError(
                        code=ErrorCode.UNKNOWN_PARAM,
                        message=f"unknown param {p_name!r} on {connector}.{operation}",
                        path=f"{path}.arguments.params.{p_name}",
                        near=sug,
                        suggestion=suggestion,
                    ))
            # Conditional-visibility check: a known param may still be
            # invalid in the current arg set (e.g. block_ip_new's
            # ip_block_policy is only valid when method='Policy Based').
            self._check_param_visibility(
                connector, operation, provided, path, errors,
            )
            # Picklist enum validation. Only fires on literal string
            # values; Jinja expressions are skipped (we can't resolve
            # their value statically).
            for p_name, p_val in provided.items():
                if p_name not in valid_params:
                    continue
                _ptype, allowed = self.operation_param_enum(
                    connector, operation, p_name)
                if allowed is None:
                    continue
                # Multiselect accepts a list of strings; select accepts a
                # single string. Both forms get the same enum check.
                vals = p_val if isinstance(p_val, list) else [p_val]
                for v in vals:
                    if not isinstance(v, str):
                        continue
                    if "{{" in v or "{%" in v:
                        continue  # Jinja-templated; defer to runtime
                    if v in allowed:
                        continue
                    # Case-insensitive match → likely a casing typo.
                    case_match = next(
                        (a for a in allowed if a.lower() == v.lower()), None)
                    if case_match:
                        msg = (f"param {p_name!r} on "
                               f"{connector}.{operation}: value {v!r} "
                               f"not in enum (values are case-sensitive)"
                               f". Did you mean {case_match!r}?")
                        suggestion = f"replace with {case_match!r}"
                    else:
                        near = difflib.get_close_matches(
                            v, allowed, n=3, cutoff=0.4)
                        head = ", ".join(repr(o) for o in allowed[:10])
                        if near:
                            msg = (f"param {p_name!r} on "
                                   f"{connector}.{operation}: value "
                                   f"{v!r} not in enum. Did you mean: "
                                   f"{', '.join(repr(n) for n in near)}?")
                            suggestion = f"replace with {near[0]!r}"
                        else:
                            msg = (f"param {p_name!r} on "
                                   f"{connector}.{operation}: value "
                                   f"{v!r} not in enum. Allowed: {head}"
                                   + (" …" if len(allowed) > 10 else ""))
                            suggestion = (
                                f"use one of: {head}"
                                + (" …" if len(allowed) > 10 else ""))
                    errors.append(CompileError(
                        code=ErrorCode.BAD_VALUE,
                        message=msg,
                        path=f"{path}.arguments.params.{p_name}",
                        suggestion=suggestion,
                    ))
            # Scalar-type validation: integer / decimal / boolean.
            # Same skip-Jinja rule as enum. We only flag literal values
            # that *clearly* can't coerce; the FSR runtime does its own
            # string → target-type coercion for genuinely-numeric and
            # genuinely-boolean strings, so we tolerate them.
            for p_name, p_val in provided.items():
                if p_name not in valid_params:
                    continue
                ptype, _ = self.operation_param_enum(
                    connector, operation, p_name)
                if ptype is None:
                    continue
                ptype_low = ptype.lower()
                # Skip Jinja-templated scalars at the value level. Lists
                # (multiselect) are handled in the enum branch.
                if isinstance(p_val, str) and (
                        "{{" in p_val or "{%" in p_val):
                    continue
                # Numeric: integer / decimal / numeric / "intger" (typo).
                if ptype_low in {"integer", "intger"}:
                    if isinstance(p_val, bool) or not _coerces_to_int(p_val):
                        errors.append(CompileError(
                            code=ErrorCode.BAD_VALUE,
                            message=(
                                f"param {p_name!r} on "
                                f"{connector}.{operation} is type 'integer'"
                                f" but got {p_val!r} "
                                f"({type(p_val).__name__}) which does "
                                f"not coerce to int"),
                            path=f"{path}.arguments.params.{p_name}",
                            suggestion=("pass an integer literal, an "
                                        "integer-shaped string, or a "
                                        "Jinja expression that yields "
                                        "an int"),
                        ))
                elif ptype_low in {"decimal", "numeric"}:
                    if isinstance(p_val, bool) or not _coerces_to_float(p_val):
                        errors.append(CompileError(
                            code=ErrorCode.BAD_VALUE,
                            message=(
                                f"param {p_name!r} on "
                                f"{connector}.{operation} is type "
                                f"{ptype!r} but got {p_val!r} "
                                f"({type(p_val).__name__}) which does "
                                f"not coerce to a number"),
                            path=f"{path}.arguments.params.{p_name}",
                            suggestion="pass a number or numeric string",
                        ))
                # Tier 2.3: observed_type validators for types Tier 1's
                # widget pass doesn't cover (ipv4 / url / email /
                # iso8601 / json_object / json_array). Only fires on
                # `text`-widget params that the type probe lifted —
                # numeric/bool/picklist widgets are already handled
                # above.
                elif ptype_low in {"text", "textarea", "richtext"}:
                    obs, _coerces = self.operation_param_observed_type(
                        connector, operation, p_name)
                    spec = _OBSERVED_VALIDATORS.get(obs or "")
                    if spec is not None and not spec[1](p_val):
                        display, _, sug_tail = spec
                        errors.append(CompileError(
                            code=ErrorCode.BAD_VALUE,
                            message=(
                                f"param {p_name!r} on "
                                f"{connector}.{operation} expects an "
                                f"{display} but got {p_val!r} "
                                f"({type(p_val).__name__})"),
                            path=f"{path}.arguments.params.{p_name}",
                            suggestion=sug_tail,
                        ))
                # Boolean: checkbox / boolean.
                elif ptype_low in {"checkbox", "boolean"}:
                    if not _coerces_to_bool(p_val):
                        errors.append(CompileError(
                            code=ErrorCode.BAD_VALUE,
                            message=(
                                f"param {p_name!r} on "
                                f"{connector}.{operation} is type "
                                f"{ptype!r} but got {p_val!r} "
                                f"({type(p_val).__name__}) which does "
                                f"not coerce to a boolean"),
                            path=f"{path}.arguments.params.{p_name}",
                            suggestion=("pass true / false (or 'true' / "
                                        "'false' as a string)"),
                        ))

        # Stamp the connector version onto the step (FSR JSON requires it).
        if "version" not in a and crow["version"]:
            a["version"] = crow["version"]
        # The UI's connector-step header reads `arguments.name` (display
        # title) and `arguments.operationTitle`. Without them the canvas
        # shows "UNDEFINED <version>". The exporter writes them; we mirror.
        if "name" not in a and crow["label"]:
            a["name"] = crow["label"]
        if "operationTitle" not in a and orow["title"]:
            a["operationTitle"] = orow["title"]
        # FSR canonical default for step_variables on connector steps is
        # an empty list (observed in live exports).
        if "step_variables" not in a:
            a["step_variables"] = []
        # Tenant/agent picker — false unless the playbook author wires a
        # multi-tenant config.
        if "pickFromTenant" not in a:
            a["pickFromTenant"] = False

    def _resolve_workflow_reference_args(
        self, step: Step, path: str, errors: list[CompileError],
        pb_by_name: dict[str, "Playbook"],
    ) -> None:
        """Validate workflow_reference (call-another-playbook) step arguments.

        Two ways to express the target in YAML:
          - `target: <playbook_name>`  — looked up in same collection;
            emitter rewrites to /api/3/workflows/<uuid> via deterministic
            UUID synthesis.
          - `workflowReference: /api/3/workflows/<uuid>` — pass-through for
            cross-collection references (we can't validate further).

        Caller's `arguments: {key: value}` keys are validated against the
        target playbook's `parameters: [...]` list when target is local.
        """
        a = step.arguments
        target_name = a.get("target")
        ref_iri = a.get("workflowReference")

        if not target_name and not ref_iri:
            errors.append(CompileError(
                code=ErrorCode.MISSING_FIELD,
                message="workflow_reference step needs either 'target' (local playbook name) or 'workflowReference' (IRI)",
                path=f"{path}.arguments",
            ))
            return

        provided_args = a.get("arguments") or {}
        if not isinstance(provided_args, dict):
            errors.append(CompileError(
                code=ErrorCode.BAD_VALUE,
                message="workflow_reference.arguments must be a mapping",
                path=f"{path}.arguments.arguments",
            ))
            return

        if target_name:
            target_pb = pb_by_name.get(target_name)
            if target_pb is None:
                sug = difflib.get_close_matches(target_name, list(pb_by_name), n=1, cutoff=0.6)
                errors.append(CompileError(
                    code=ErrorCode.UNKNOWN_NEXT_STEP,  # close enough — unknown ref
                    message=f"target playbook {target_name!r} not found in this collection",
                    path=f"{path}.arguments.target",
                    near=sug[0] if sug else None,
                    suggestion=f"did you mean {sug[0]!r}?" if sug else None,
                ))
                return
            valid = set(target_pb.parameters)
            for k in provided_args:
                if k not in valid:
                    sug = difflib.get_close_matches(k, list(valid), n=1, cutoff=0.6) if valid else []
                    errors.append(CompileError(
                        code=ErrorCode.UNKNOWN_PARAM,
                        message=f"target playbook {target_name!r} has no parameter {k!r}; declared: {sorted(valid) or '[]'}",
                        path=f"{path}.arguments.arguments.{k}",
                        near=sug[0] if sug else None,
                        suggestion=f"did you mean {sug[0]!r}?" if sug else None,
                    ))

    def _check_routing(
        self, step: Step, seen_ids: set[str], path: str,
        errors: list[CompileError],
    ) -> None:
        if step.next and step.next not in seen_ids:
            errors.append(CompileError(
                code=ErrorCode.UNKNOWN_NEXT_STEP,
                message=f"step.next {step.next!r} does not match any step id",
                path=f"{path}.next",
            ))
        for option, target in step.branches.items():
            if target not in seen_ids:
                errors.append(CompileError(
                    code=ErrorCode.UNKNOWN_NEXT_STEP,
                    message=f"branch target {target!r} does not match any step id",
                    path=f"{path}.branches.{option}",
                ))
