"""Resolver — looks up references against the SQLite reference store.

The resolver is the only compiler component that touches the DB. It
turns short YAML names into FSR-canonical identifiers (step type UUIDs,
connector versions, handler functions) and surfaces structured errors
with "did you mean…" suggestions.
"""
from __future__ import annotations

import difflib
import json
import sqlite3
from pathlib import Path
from typing import Optional

from .errors import CompileError, ErrorCode
from .ir import Collection, Step

# Friendly short types -> canonical FSR step type names. v1 only covers
# the ones we have full handler signatures for + Start.
SHORT_TYPE_TO_FSR: dict[str, str] = {
    "connector": "Connectors",
    "set_variable": "SetVariable",
    "decision": "Decision",
    "start": "cybersponse.abstract_trigger",
    "find_record": "FindRecords",
    "update_record": "UpdateRecord",
    "insert_record": "InsertData",
    "delay": "Delay",
    "manual_input": "ManualInput",
    "code_snippet": "CodeSnippet",
    "approval": "Approval",
    "workflow_reference": "WorkflowReference",
}


class Resolver:
    def __init__(self, db_path: Path):
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row

    def close(self) -> None:
        self.conn.close()

    # ---- step types ----

    def step_type(self, short_or_canonical: str) -> Optional[sqlite3.Row]:
        canonical = SHORT_TYPE_TO_FSR.get(short_or_canonical, short_or_canonical)
        return self.conn.execute(
            "SELECT * FROM step_types WHERE name = ?", (canonical,),
        ).fetchone()

    def suggest_step_type(self, name: str) -> Optional[str]:
        rows = self.conn.execute("SELECT name FROM step_types").fetchall()
        names = list(SHORT_TYPE_TO_FSR.keys()) + [r["name"] for r in rows]
        m = difflib.get_close_matches(name, names, n=1, cutoff=0.6)
        return m[0] if m else None

    def handler_for_step_type(self, step_type_row: sqlite3.Row) -> Optional[str]:
        schema = step_type_row["args_schema_json"]
        if not schema:
            return None
        try:
            obj = json.loads(schema)
        except Exception:
            return None
        script = obj.get("script") if isinstance(obj, dict) else None
        if not isinstance(script, str):
            return None
        return script.rsplit("/", 1)[-1]

    # ---- connectors / operations ----

    def connector(self, name: str) -> Optional[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM connectors WHERE name = ?", (name,),
        ).fetchone()

    def suggest_connector(self, name: str) -> Optional[str]:
        rows = self.conn.execute("SELECT name FROM connectors").fetchall()
        m = difflib.get_close_matches(name, [r["name"] for r in rows], n=1, cutoff=0.6)
        return m[0] if m else None

    def operation(self, connector: str, op: str) -> Optional[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM operations WHERE connector_name = ? AND op_name = ?",
            (connector, op),
        ).fetchone()

    def suggest_operation(self, connector: str, op: str) -> Optional[str]:
        rows = self.conn.execute(
            "SELECT op_name FROM operations WHERE connector_name = ?", (connector,),
        ).fetchall()
        m = difflib.get_close_matches(op, [r["op_name"] for r in rows], n=1, cutoff=0.6)
        return m[0] if m else None

    def operation_params(self, connector: str, op: str) -> list[str]:
        rows = self.conn.execute(
            "SELECT param_name FROM operation_params "
            "WHERE connector_name = ? AND op_name = ?",
            (connector, op),
        ).fetchall()
        return [r["param_name"] for r in rows]

    # ---- main entry ----

    def resolve(self, collection: Collection) -> list[CompileError]:
        errors: list[CompileError] = []
        # Build name→Playbook map for in-collection workflow_reference targets.
        pb_by_name = {pb.name: pb for pb in collection.playbooks}
        for pi, pb in enumerate(collection.playbooks):
            seen_ids = {s.id for s in pb.steps}
            for si, step in enumerate(pb.steps):
                path = f"playbooks[{pi}].steps[{si}]"
                self._resolve_step(step, path, errors, pb_by_name)
                self._check_routing(step, seen_ids, path, errors)
        return errors

    def _resolve_step(
        self, step: Step, path: str, errors: list[CompileError],
        pb_by_name: dict[str, "Playbook"] | None = None,
    ) -> None:
        st = self.step_type(step.type)
        if st is None:
            sug = self.suggest_step_type(step.type)
            errors.append(CompileError(
                code=ErrorCode.UNKNOWN_STEP_TYPE,
                message=f"unknown step type: {step.type!r}",
                path=f"{path}.type",
                near=sug,
                suggestion=f"did you mean {sug!r}?" if sug else None,
            ))
            return
        step.step_type_uuid = st["uuid"]
        step.step_type_name = st["name"]
        step.handler = self.handler_for_step_type(st)

        # Per-step-type argument validation
        if step.type == "connector":
            self._resolve_connector_args(step, path, errors)
        elif step.type == "workflow_reference":
            self._resolve_workflow_reference_args(step, path, errors, pb_by_name or {})
        # set_variable, decision: no further ref-checking in v1 — args are
        # free-form jinja; reference linting is a future TODO.

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
            errors.append(CompileError(
                code=ErrorCode.UNKNOWN_OPERATION,
                message=f"unknown operation {operation!r} on connector {connector!r}",
                path=f"{path}.arguments.operation",
                near=sug,
                suggestion=f"did you mean {sug!r}?" if sug else None,
            ))
            return

        # Check params against operation_params
        valid_params = set(self.operation_params(connector, operation))
        provided = a.get("params") or {}
        if not isinstance(provided, dict):
            errors.append(CompileError(
                code=ErrorCode.BAD_VALUE,
                message="arguments.params must be a mapping",
                path=f"{path}.arguments.params",
            ))
            return
        for p_name in provided:
            if p_name not in valid_params:
                sug = None
                if valid_params:
                    m = difflib.get_close_matches(p_name, list(valid_params), n=1, cutoff=0.6)
                    sug = m[0] if m else None
                errors.append(CompileError(
                    code=ErrorCode.UNKNOWN_PARAM,
                    message=f"unknown param {p_name!r} on {connector}.{operation}",
                    path=f"{path}.arguments.params.{p_name}",
                    near=sug,
                    suggestion=f"did you mean {sug!r}?" if sug else None,
                ))

        # Stamp the connector version onto the step (FSR JSON requires it).
        if "version" not in a and crow["version"]:
            a["version"] = crow["version"]

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
