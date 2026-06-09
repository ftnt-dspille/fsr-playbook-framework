"""Per-step argument-shape validation against canonical handler signatures.

The `step_handlers` table holds `inspect.signature()` output for every
entry in `workflow.eval.FUNCTION_MAP`. Each step type's handler is
discovered by suffix-stripping `args_schema_json.script`. We use those
signatures to enforce two rules:

  1. Required user-facing params (no default, not framework-injected,
     not VAR_*) must appear in `step.arguments`.
  2. If the handler has no `**kwargs`, unknown keys in `step.arguments`
     are errors. If it does have `**kwargs`, unknown keys are skipped
     (FSR's runtime allows arbitrary extras for these handlers).

`Connector` validation is handled in detail by the resolver against the
operation_params table — this validator only handles the residual case
of confirming `arguments.connector` and `arguments.operation` exist
(already enforced upstream) and skips deeper inspection.

Framework-injected params (e.g. `step`, `step_id`, `wf_id`, `env`) are
populated by the FSR runtime, never by the user; we exclude them from
the "required" check. List comes from `workflow.eval.IGNORED_ARGS` plus
a few known runtime injectables that the dispatcher prepends.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Optional

from .errors import CompileError, ErrorCode
from .ir import Collection, Step

# Framework-injected: names that appear in handler signatures but FSR
# fills in at runtime. Drawn from workflow.eval.IGNORED_ARGS and a few
# leading positional params we observed (e.g. `cond(step, conditions)`
# where `step` is the running step record).
_FRAMEWORK_PARAMS = frozenset({
    "step", "step_id", "wf_id", "env", "audit_info", "child_step_id",
    "step_variables", "do_until", "ignore_errors", "when",
    "for_each", "cyops_playbook_iri", "cyops_playbook_name",
    "collaborationNote", "inputVariables", "displayConditions",
    "__bulk", "_showJson", "fieldOperation",
    # Auto-injected by the resolver for manual_input — never user-supplied
    # in the friendly YAML, but live on the step by the time arg_validator
    # runs. Listing them here keeps the unknown-arg warning quiet for them.
    "is_approval", "isRecordLinked", "owner_detail", "email_notification",
    "inline_channel_list", "external_channel_list", "unauthenticated_input",
    "response_mapping",
})


class ArgValidator:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self._cache: dict[str, Optional[dict]] = {}

    def _handler(self, name: str) -> Optional[dict]:
        if name in self._cache:
            return self._cache[name]
        row = self.conn.execute(
            "SELECT signature, parameters_json FROM step_handlers WHERE name = ?",
            (name,),
        ).fetchone()
        if not row:
            self._cache[name] = None
            return None
        params = json.loads(row[1]) if row[1] else []
        self._cache[name] = {"signature": row[0], "parameters": params}
        return self._cache[name]

    def validate(self, collection: Collection) -> list[CompileError]:
        errors: list[CompileError] = []
        for pi, pb in enumerate(collection.playbooks):
            for si, step in enumerate(pb.steps):
                self._validate_step(step, f"playbooks[{pi}].steps[{si}]", errors)
        return errors

    def _validate_step(
        self, step: Step, path: str, errors: list[CompileError],
    ) -> None:
        # The resolver does its own per-handler arg normalization and
        # validation (and injects FSR-required wire-format keys like
        # `name`, `operationTitle`, `operation`, `collectionType`, `type`,
        # `rule`). For those handlers, a generic signature pass produces
        # false positives on the injected keys. Skip them.
        # set_variable's arguments is a flat {var_name: value} payload —
        # the keys ARE the variables to set, not handler kwargs.
        _RESOLVER_VALIDATES = frozenset({
            "connector",       # connector / stop / end (no_op)
            "update_data",     # update_record
            "insert_data",     # create_record
            "delay",
            "code_snippet",
            "manual_input",
            "set_multiple",    # set_variable
        })
        if step.handler in _RESOLVER_VALIDATES or not step.handler:
            return
        h = self._handler(step.handler)
        if h is None:
            return  # handler not in FUNCTION_MAP (workflow_reference, map, etc.)

        params = h["parameters"]
        accepts_kwargs = any(p["kind"] == "VAR_KEYWORD" for p in params)
        named_params = {p["name"] for p in params if p["kind"] not in ("VAR_POSITIONAL", "VAR_KEYWORD")}

        required = [
            p["name"] for p in params
            if p["kind"] in ("POSITIONAL_OR_KEYWORD", "KEYWORD_ONLY")
            and p["default"] is None
            and p["name"] not in _FRAMEWORK_PARAMS
        ]
        # Actually `default is None` here means inspect.signature() reported
        # no default — Parameter.empty serialized as None in the dump. Verify:
        # required == params with default field literally None in JSON.
        # (Parameters that default to the python value None render as 'None'
        # string in the dump, not null.)

        provided = step.arguments or {}
        for r in required:
            if r not in provided:
                errors.append(CompileError(
                    code=ErrorCode.MISSING_FIELD,
                    message=f"step type {step.step_type_name!r} (handler {step.handler!r}) requires argument {r!r}",
                    path=f"{path}.arguments.{r}",
                ))

        for k in provided:
            if k in named_params or k in _FRAMEWORK_PARAMS:
                continue
            if accepts_kwargs:
                # Handler accepts **kwargs so technically the arg is legal
                # syntactically — but in practice FSR's runtime often errors
                # on unrecognised top-level keys (manual_input is a notorious
                # offender). Warn so the author can see it before runtime.
                errors.append(CompileError(
                    code=ErrorCode.UNKNOWN_PARAM,
                    message=(
                        f"unknown argument {k!r} for handler {step.handler!r} — "
                        f"FSR may ignore or error at runtime"
                    ),
                    path=f"{path}.arguments.{k}",
                    suggestion=(
                        f"known args: {', '.join(sorted(named_params - _FRAMEWORK_PARAMS))}"
                    ),
                    severity="warning",
                ))
            else:
                errors.append(CompileError(
                    code=ErrorCode.UNKNOWN_PARAM,
                    message=f"unknown argument {k!r} for handler {step.handler!r}",
                    path=f"{path}.arguments.{k}",
                ))

        # manual_input: `input` MUST be a dict at runtime — FSR calls .get()
        # on it. We've seen the LLM produce `input: "some string"` which
        # passes generic shape checks but crashes the workflow.
        if step.handler == "manual_input":
            inp = provided.get("input")
            if inp is not None and not isinstance(inp, dict):
                errors.append(CompileError(
                    code=ErrorCode.BAD_VALUE,
                    message=(
                        f"manual_input.arguments.input must be a mapping "
                        f"(got {type(inp).__name__}); FSR will crash with "
                        f"\"'str' object has no attribute 'get'\""
                    ),
                    path=f"{path}.arguments.input",
                    suggestion='use: input: { title: "...", options: [...] }',
                ))
