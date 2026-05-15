"""ConnectorArgsMixin — resolving connector and workflow reference arguments."""
from __future__ import annotations

import difflib
import sqlite3
from typing import Optional

from ..errors import CompileError, ErrorCode
from ..ir import Step


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
