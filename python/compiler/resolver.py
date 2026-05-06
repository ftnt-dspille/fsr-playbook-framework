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


def _looks_like_uuid(s: str) -> bool:
    return isinstance(s, str) and len(s) == 36 and s.count("-") == 4

# Friendly short types -> canonical FSR step type names. v1 only covers
# the ones we have full handler signatures for + Start.
SHORT_TYPE_TO_FSR: dict[str, str] = {
    "connector": "Connectors",
    "set_variable": "SetVariable",
    "decision": "Decision",
    "start": "cybersponse.abstract_trigger",
    "find_record": "FindRecords",
    "update_record": "UpdateRecord",
    "create_record": "InsertData",
    # Bulk feed insertion — used by threat-feed ingestion recipes. Bypasses
    # on-create playbook triggers (intentional for high-volume feeds; do
    # NOT use this for Alerts ingestion where triggers must fire).
    "ingest_bulk_feed": "IngestBulkFeed",
    # Legacy alias kept so existing fixtures don't break; emit a hint via
    # the linter when authors use the old name.
    "insert_record": "InsertData",
    "delay": "Delay",
    "manual_input": "ManualInput",
    "code_snippet": "CodeSnippet",
    "approval": "Approval",
    "workflow_reference": "WorkflowReference",
    # `stop` / `end` — first-class no-op terminals. Compile to a connector
    # step calling `cyops_utilities.no_op` (FSR's canonical "Utils: No
    # Operation" idiom), so a decision branch that should do nothing has
    # an obvious YAML keyword instead of dangling or filler set_variable.
    "stop": "Connectors",
    "end": "Connectors",
    # Auto-fired record triggers (genuinely different from manual `start`):
    # event-driven, not invokable from the designer.
    "start_on_create": "cybersponse.post_create",
    "start_on_update": "cybersponse.post_update",
}

# `type: start` covers ALL manually-triggered playbooks. The compiler
# decides between the two underlying FSR step types based on whether a
# module is bound:
#   - no `module:` arg → `cybersponse.abstract_trigger` (designer / pure manual)
#   - `module:` arg    → `cybersponse.action` (also shows on the module's
#                         listing Execute menu and per-record right-click)
# Either way the playbook can still be run from the designer's Run button.


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
        # Score each op by max(ratio(input, op_name), ratio(input, snake_title)).
        # Title match catches the case where the agent guessed an op name from
        # the human-readable label (`get_ip_reputation` ≈ "Get IP Reputation"
        # = title of `query_ip`).
        rows = self.conn.execute(
            "SELECT op_name, title FROM operations WHERE connector_name = ?",
            (connector,),
        ).fetchall()
        if not rows:
            return None
        needle = op.lower()
        best_name, best_score = None, 0.0
        for r in rows:
            name = r["op_name"]
            title_snake = (r["title"] or "").lower().replace(" ", "_")
            score = max(
                difflib.SequenceMatcher(None, needle, name.lower()).ratio(),
                difflib.SequenceMatcher(None, needle, title_snake).ratio() if title_snake else 0.0,
            )
            if score > best_score:
                best_name, best_score = name, score
        return best_name if best_score >= 0.6 else None

    def suggest_operations_topn(self, connector: str, op: str, n: int = 5) -> list[str]:
        """Return top-N close-ish op names (using both op_name and title), for picklist hints."""
        rows = self.conn.execute(
            "SELECT op_name, title FROM operations WHERE connector_name = ?",
            (connector,),
        ).fetchall()
        needle = op.lower()
        scored = []
        for r in rows:
            name = r["op_name"]
            title_snake = (r["title"] or "").lower().replace(" ", "_")
            score = max(
                difflib.SequenceMatcher(None, needle, name.lower()).ratio(),
                difflib.SequenceMatcher(None, needle, title_snake).ratio() if title_snake else 0.0,
            )
            if score >= 0.3:
                scored.append((score, name))
        scored.sort(reverse=True)
        return [name for _, name in scored[:n]]

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

        # `type: start` covers both flavors of manual trigger. If the
        # author bound a module, switch the resolved step type to
        # `cybersponse.action` (record-listing Execute menu / right-click).
        # Otherwise stay on `cybersponse.abstract_trigger` (designer-only
        # manual). Either way the playbook is still runnable from the
        # designer Run button.
        if step.type == "start" and isinstance(step.arguments, dict):
            if step.arguments.get("module") or step.arguments.get("modules"):
                action_row = self.conn.execute(
                    "SELECT * FROM step_types WHERE name = ?",
                    ("cybersponse.action",),
                ).fetchone()
                if action_row is not None:
                    step.step_type_uuid = action_row["uuid"]
                    step.step_type_name = action_row["name"]
                    step.handler = self.handler_for_step_type(action_row)
                self._normalize_record_action_args(step, path, errors)

        if step.type in ("start_on_create", "start_on_update"):
            self._normalize_post_create_update_args(step, path, errors)

        if step.type in ("create_record", "insert_record", "update_record"):
            self._normalize_record_crud_args(step)

        if step.type == "delay":
            self._normalize_delay_args(step)

        if step.type == "code_snippet":
            self._normalize_code_snippet_args(step)

        if step.type == "manual_input":
            self._normalize_manual_input_args(step, path, errors)

        # `stop` / `end` synthesize the canonical Utils: No Operation call,
        # then fall through to connector arg resolution.
        if step.type in ("stop", "end"):
            a = step.arguments if isinstance(step.arguments, dict) else {}
            a.setdefault("connector", "cyops_utilities")
            a.setdefault("operation", "no_op")
            a.setdefault("config", "")
            a.setdefault("params", {})
            step.arguments = a

        # Per-step-type argument validation
        if step.type == "connector" or step.type in ("stop", "end"):
            self._resolve_connector_args(step, path, errors)
            return
        if step.type == "workflow_reference":
            self._resolve_workflow_reference_args(step, path, errors, pb_by_name or {})
        elif step.type == "set_variable":
            self._normalize_set_variable_args(step, path, errors)
        elif step.type == "start":
            self._normalize_start_args(step)
        # decision: no further ref-checking in v1 — args are free-form jinja.

    def _normalize_record_action_args(
        self, step: Step, path: str, errors: list[CompileError],
    ) -> None:
        """Fill canonical args for record-bound triggers.

        Friendly inputs:
          module:           single module name (or modules: [list])
          button_label:     Trigger Button Label — what the user sees in the
                            Execute menu. Defaults to blank, in which case FSR
                            shows the *playbook* name (NOT the step name).
                            Don't reuse the step's `name:` for this; that field
                            names the canvas node, not the button.
          requires_record:  bool, default True. False = "Does not require record
                            input to run" — button shows on the module listing's
                            Execute menu but no record context is passed.
          run_mode:         'per_record' (default) | 'once_for_all' — when
                            requires_record=True, controls whether the playbook
                            fires once per selected record or once for all.

        Everything else fills with the canonical defaults observed across the
        live FSR corpus.
        """
        import uuid as _uuidmod
        a = step.arguments if isinstance(step.arguments, dict) else {}
        # Trigger Button Label — separate from step.name. Empty means
        # FSR will show the playbook name in the Execute menu.
        button_label = a.pop("button_label", None) or a.pop("title", None) or ""
        modules_raw = a.pop("module", None) or a.pop("modules", None) or a.get("resources")
        if isinstance(modules_raw, str):
            modules = [modules_raw]
        elif isinstance(modules_raw, list):
            modules = [str(m) for m in modules_raw]
        else:
            modules = []
        if not modules:
            errors.append(CompileError(
                code=ErrorCode.MISSING_FIELD,
                message=f"{step.type} requires `module:` (or `modules:`)",
                path=f"{path}.arguments.module",
            ))
            modules = ["alerts"]  # let downstream emit succeed for diagnostics
        requires_record = bool(a.pop("requires_record", True))
        run_mode = a.pop("run_mode", "per_record")
        # FSR's `title` is the persisted Trigger Button Label.
        a["title"] = button_label
        a["resources"] = modules
        # Deterministic route UUID so re-pushes stay stable. Hash from
        # the title + resources keeps the action button identity consistent
        # across imports.
        if not a.get("route"):
            seed = (button_label or step.name or "") + "|" + ",".join(sorted(modules))
            a["route"] = str(_uuidmod.uuid5(_uuidmod.NAMESPACE_OID, seed))
        a.setdefault("inputVariables", [])
        a.setdefault("step_variables", {"input": {"params": [],
                                                  "records": "{{vars.input.records}}"}})
        a.setdefault("triggerOnSource", True)
        a.setdefault("triggerOnReplicate", False)
        # noRecordExecution: True = "Does not require record input to run".
        # singleRecordExecution: True = per-record run; False = once for all.
        # When requires_record=False, run_mode is irrelevant.
        a["noRecordExecution"] = not requires_record
        a["singleRecordExecution"] = (requires_record and run_mode == "per_record")
        a.setdefault("__triggerLimit", True)
        a.setdefault("executeButtonText", "Execute")
        a.setdefault("showToasterMessage", {"visible": False, "messageVisible": True})
        # Empty per-module display filter — button shows for all records.
        a.setdefault("displayConditions",
                     {m: {"sort": [], "limit": 30, "logic": "AND", "filters": []}
                      for m in modules})
        step.arguments = a

    def _normalize_post_create_update_args(
        self, step: Step, path: str, errors: list[CompileError],
    ) -> None:
        """Canonical args for cybersponse.post_create / post_update.

        Friendly inputs:
          module:  single module name (or modules: [list]).
          when:    optional fieldbasedtrigger filter — fires only when the
                   query matches the post-write record state, OR (for
                   post_update) when the listed fields *changed*.
                   Shape: {logic: AND|OR, filters: [{field, op, value?}]}
                   `op: changed` needs no value (post_update only).

        Emits the canonical FSR shape: resource/resources, step_variables,
        fieldbasedtrigger.
        """
        a = step.arguments if isinstance(step.arguments, dict) else {}
        modules_raw = a.pop("module", None) or a.pop("modules", None) \
            or a.get("resources") or a.get("resource")
        if isinstance(modules_raw, str):
            modules = [modules_raw]
        elif isinstance(modules_raw, list):
            modules = [str(m) for m in modules_raw]
        else:
            modules = []
        if not modules:
            errors.append(CompileError(
                code=ErrorCode.MISSING_FIELD,
                message=f"{step.type} requires `module:` (or `modules:`)",
                path=f"{path}.arguments.module",
            ))
            modules = ["alerts"]
        a["resource"] = modules[0]
        a["resources"] = modules
        a.setdefault("step_variables",
                     {"input": {"records": ["{{vars.input.records[0]}}"]}})
        a.setdefault("triggerOnSource", True)
        a.setdefault("triggerOnReplicate", False)
        a.setdefault("__triggerLimit", True)

        when = a.pop("when", None)
        if when is not None:
            fbt = self._expand_when(when, step.type, path, errors)
            if fbt is not None:
                a["fieldbasedtrigger"] = fbt
        elif "fieldbasedtrigger" not in a:
            a["fieldbasedtrigger"] = {
                "sort": [], "limit": 30, "logic": "AND", "filters": [],
            }
        step.arguments = a

    def _expand_when(
        self, when, step_type: str, path: str, errors: list[CompileError],
    ):
        if not isinstance(when, dict):
            errors.append(CompileError(
                code=ErrorCode.BAD_VALUE,
                message="`when:` must be a mapping with logic/filters",
                path=f"{path}.arguments.when",
            ))
            return None
        logic = str(when.get("logic", "AND")).upper()
        if logic not in ("AND", "OR"):
            logic = "AND"
        raw_filters = when.get("filters") or []
        if not isinstance(raw_filters, list):
            errors.append(CompileError(
                code=ErrorCode.BAD_VALUE,
                message="`when.filters` must be a list",
                path=f"{path}.arguments.when.filters",
            ))
            return None
        out_filters = []
        for i, f in enumerate(raw_filters):
            if not isinstance(f, dict):
                errors.append(CompileError(
                    code=ErrorCode.BAD_VALUE,
                    message="filter entries must be mappings",
                    path=f"{path}.arguments.when.filters[{i}]",
                ))
                continue
            field = f.get("field")
            op = f.get("op") or f.get("operator") or "eq"
            value = f.get("value")
            if not field:
                errors.append(CompileError(
                    code=ErrorCode.MISSING_FIELD,
                    message="filter requires `field:`",
                    path=f"{path}.arguments.when.filters[{i}].field",
                ))
                continue
            if op == "changed":
                if step_type != "start_on_update":
                    errors.append(CompileError(
                        code=ErrorCode.BAD_VALUE,
                        message="`op: changed` only valid on start_on_update",
                        path=f"{path}.arguments.when.filters[{i}].op",
                    ))
                    continue
                out_filters.append({
                    "type": "object", "field": field, "value": None,
                    "_value": {"display": "", "itemValue": ""},
                    "operator": "changed",
                })
            else:
                out_filters.append({
                    "type": "primitive", "field": field, "value": value,
                    "operator": op, "_operator": op,
                })
        return {"sort": [], "limit": 30, "logic": logic, "filters": out_filters}

    def _normalize_record_crud_args(self, step: Step) -> None:
        """Friendly `module: alerts` → canonical IRI keys.

        - create_record / insert_record (InsertData):
            module → collection ('/api/3/<m>')
        - update_record (UpdateRecord):
            module → collectionType ('/api/3/<m>')
            (`collection:` here is the *record* IRI; do not overwrite.)

        find_record's handler takes `module:` directly; nothing to do.
        Already-set canonical keys win — never clobber an explicit value.
        """
        a = step.arguments if isinstance(step.arguments, dict) else {}
        module = a.pop("module", None)
        if not module or not isinstance(module, str):
            step.arguments = a
            return
        iri = f"/api/3/{module}" if not module.startswith("/api/") else module
        if step.type in ("create_record", "insert_record"):
            a.setdefault("collection", iri)
        elif step.type == "update_record":
            a.setdefault("collectionType", iri)
        step.arguments = a

    # Friendly `kind:` → canonical (formType, dataType, type, templateUrl)
    # for the inputVariables section of a manual_input step. Each row was
    # picked by querying live FSR (`probe playbook-steps --live`) for the
    # dominant (formType, dataType, type, templateUrl) tuple — see the
    # SQL in MI_DECISION_VALIDATION_AUDIT.md §4.
    _WEBADDR = "app/components/form/fields/webAddress.html"
    _INPUT_HTML = "app/components/form/fields/input.html"
    _INPUT_FIELD_KINDS: dict[str, dict[str, Any]] = {
        # text family
        "text":     {"formType": "text",     "dataType": "text", "type": "string",  "templateUrl": _INPUT_HTML},
        "textarea": {"formType": "textarea", "dataType": "text", "type": "string",  "templateUrl": "app/components/form/fields/textarea.html"},
        "richtext": {"formType": "richtext", "dataType": "text", "type": "string",  "templateUrl": "app/components/form/fields/markdownEditor.html"},
        "html":     {"formType": "html",     "dataType": "text", "type": "string",  "templateUrl": "app/components/form/fields/htmlEditor.html"},
        "password": {"formType": "password", "dataType": "text", "type": "string",  "templateUrl": "app/components/form/fields/password.html"},
        # webAddress.html family — text dataType but typed sub-formats. Confirmed
        # against live FSR (ipv4/ipv6/domain present in store/fsr_reference.db).
        "ipv4":     {"formType": "ipv4",     "dataType": "text", "type": "string",  "templateUrl": _WEBADDR},
        "ipv6":     {"formType": "ipv6",     "dataType": "text", "type": "string",  "templateUrl": _WEBADDR},
        "domain":   {"formType": "domain",   "dataType": "text", "type": "string",  "templateUrl": _WEBADDR},
        "email":    {"formType": "email",    "dataType": "text", "type": "string",  "templateUrl": _WEBADDR},
        "url":      {"formType": "url",      "dataType": "text", "type": "string",  "templateUrl": _WEBADDR},
        "phone":    {"formType": "phone",    "dataType": "text", "type": "string",  "templateUrl": _WEBADDR},
        "filehash": {"formType": "filehash", "dataType": "text", "type": "string",  "templateUrl": _WEBADDR},
        # numeric
        "integer":  {"formType": "integer",  "dataType": "text", "type": "integer", "templateUrl": _INPUT_HTML},
        "number":   {"formType": "integer",  "dataType": "text", "type": "integer", "templateUrl": _INPUT_HTML},
        "decimal":  {"formType": "decimal",  "dataType": "text", "type": "number",  "templateUrl": _INPUT_HTML},
        # bool
        "checkbox": {"formType": "checkbox", "dataType": "checkbox", "type": "boolean", "templateUrl": "app/components/form/fields/checkbox.html"},
        "boolean":  {"formType": "checkbox", "dataType": "checkbox", "type": "boolean", "templateUrl": "app/components/form/fields/checkbox.html"},
        # date / time
        "datetime": {"formType": "datetime", "dataType": "text", "type": "string",  "templateUrl": _INPUT_HTML},
        "date":     {"formType": "date",     "dataType": "text", "type": "string",  "templateUrl": _INPUT_HTML},
        # selectors. `select` is the friendly name for FSR's "Dynamic List"
        # (static enum). Distinct from `picklist` (FSR-managed list) and
        # `multiselect`/`multiselectpicklist` (their multi-value variants).
        "select":             {"formType": "dynamicList",         "dataType": "dynamicList", "type": "array",     "templateUrl": "app/components/form/fields/dynamicList.html"},
        "multiselect":        {"formType": "multiselect",         "dataType": "dynamicList", "type": "array",     "templateUrl": "app/components/form/fields/dynamicList.html"},
        "picklist":           {"formType": "picklist",            "dataType": "picklist",    "type": "picklists", "templateUrl": "app/components/form/fields/typeahead.html"},
        "multiselectpicklist":{"formType": "multiselectpicklist", "dataType": "picklist",    "type": "picklists", "templateUrl": "app/components/form/fields/typeahead.html"},
        # lookup — `type` is overridden per-field with the target module name
        # (people / indicators / alerts / etc.); see _expand_input_variables.
        "lookup":   {"formType": "lookup", "dataType": "lookup", "type": "lookup", "templateUrl": "app/components/form/fields/typeahead.html"},
        # files / structured
        "file":     {"formType": "file",   "dataType": "file",   "type": "string", "templateUrl": "app/components/form/fields/file.html"},
        "image":    {"formType": "image",  "dataType": "file",   "type": "string", "templateUrl": "app/components/form/fields/file.html"},
        "json":     {"formType": "object", "dataType": "object", "type": "object", "templateUrl": "app/components/form/fields/json.html"},
        "object":   {"formType": "object", "dataType": "object", "type": "object", "templateUrl": "app/components/form/fields/json.html"},
    }

    # Per-kind humanised "title" shown next to the field in the FSR UI.
    _INPUT_FIELD_TITLE: dict[str, str] = {
        "text": "Text", "textarea": "Text Area", "richtext": "Rich Text",
        "html": "Rich Text (HTML)", "password": "Password",
        "ipv4": "IPv4", "ipv6": "IPv6", "domain": "Domain",
        "email": "Email", "url": "URL", "phone": "Phone Number",
        "filehash": "File Hash",
        "integer": "Integer", "number": "Integer", "decimal": "Decimal",
        "checkbox": "Checkbox", "boolean": "Checkbox",
        "datetime": "Datetime", "date": "Date",
        "select": "Dynamic List", "multiselect": "Multi Select",
        "picklist": "Picklist", "multiselectpicklist": "Multi Picklist",
        "lookup": "Lookup",
        "file": "File", "image": "Image",
        "json": "JSON", "object": "JSON",
    }

    def _expand_input_variables(
        self, raw: Any, path: str, errors: list[CompileError],
    ) -> list[dict[str, Any]]:
        """Expand the friendly `inputs:` list into FSR's canonical
        inputVariables shape.

        Friendly per-field keys:
          name      — required; variable name (referenced after resume as
                      `vars.steps.<step_name>.input.<name>`)
          kind      — required; one of text, textarea, richtext, email,
                      url, password, integer, checkbox, select, datetime,
                      json. Determines formType / dataType / templateUrl.
          label     — display label; defaults to `name`
          tooltip   — optional helper text
          required  — bool, default false
          default   — default value (literal or jinja)
          options   — for kind=select; list of strings or jinja that
                      resolves to a list

        Already-expanded entries (those carrying their own formType +
        templateUrl) pass through untouched, so authors who need a
        bespoke field shape can still drop in raw FSR inputVariable
        dicts.
        """
        if not isinstance(raw, list):
            errors.append(CompileError(
                code=ErrorCode.BAD_VALUE,
                message="manual_input.arguments.inputs must be a list",
                path=f"{path}.arguments.inputs",
            ))
            return []
        out: list[dict[str, Any]] = []
        for i, item in enumerate(raw):
            ipath = f"{path}.arguments.inputs[{i}]"
            if not isinstance(item, dict):
                errors.append(CompileError(
                    code=ErrorCode.BAD_VALUE,
                    message="each `inputs[]` entry must be a mapping",
                    path=ipath,
                ))
                continue
            # Pass-through escape hatch — if the author wrote the full
            # canonical shape (or anything close), trust them.
            if "formType" in item and "templateUrl" in item:
                out.append(item)
                continue
            name = item.get("name")
            kind = item.get("kind") or item.get("type")
            if not name:
                errors.append(CompileError(
                    code=ErrorCode.MISSING_FIELD,
                    message="`inputs[].name` is required",
                    path=f"{ipath}.name",
                ))
                continue
            if not kind or kind not in self._INPUT_FIELD_KINDS:
                errors.append(CompileError(
                    code=ErrorCode.BAD_VALUE,
                    message=(
                        f"`inputs[].kind` must be one of "
                        f"{', '.join(sorted(self._INPUT_FIELD_KINDS))}; "
                        f"got {kind!r}"
                    ),
                    path=f"{ipath}.kind",
                ))
                continue
            spec = self._INPUT_FIELD_KINDS[kind]
            # Strict per-entry whitelist — surface obvious typos.
            allowed = {"name", "kind", "type", "label", "tooltip",
                       "required", "default", "options", "module",
                       "picklist", "tooltip"}
            unknown = sorted(set(item) - allowed)
            if unknown:
                errors.append(CompileError(
                    code=ErrorCode.UNKNOWN_PARAM,
                    message=(
                        f"unknown key(s) on inputs[] entry: "
                        f"{', '.join(repr(k) for k in unknown)}"
                    ),
                    path=ipath,
                    suggestion=(
                        "friendly keys: name, kind, label, tooltip, "
                        "required, default, options"
                    ),
                ))
                continue
            field: dict[str, Any] = {
                "name": name,
                "type": spec["type"],
                "label": item.get("label") or name,
                "title": self._INPUT_FIELD_TITLE.get(kind, kind.title()),
                "usable": True,
                "tooltip": item.get("tooltip", ""),
                "dataType": spec["dataType"],
                "formType": spec["formType"],
                "required": bool(item.get("required", False)),
                "_expanded": True,
                "templateUrl": spec["templateUrl"],
                "defaultValue": item.get("default"),
                "_previousName": "",
                "playbookField": True,
                "jinjaExpressionView": True,
                "useRecordFieldDefault": False,
            }
            if kind in ("select", "multiselect"):
                opts = item.get("options")
                if opts is None:
                    errors.append(CompileError(
                        code=ErrorCode.MISSING_FIELD,
                        message=f"`kind: {kind}` needs `options:` (list or jinja)",
                        path=f"{ipath}.options",
                    ))
                    continue
                field["options"] = opts
            # lookup → `type` carries the FSR module name (people, alerts,
            # indicators, etc.). Live FSR keys typeahead lookups off this.
            if kind == "lookup":
                module = item.get("module") or item.get("type")
                if not module or module == "lookup":
                    errors.append(CompileError(
                        code=ErrorCode.MISSING_FIELD,
                        message=("`kind: lookup` needs `module: <name>` "
                                 "(e.g. people, alerts, indicators) — FSR "
                                 "keys the typeahead off this module"),
                        path=f"{ipath}.module",
                        suggestion="module: people",
                    ))
                    continue
                field["type"] = module
            # picklist → `picklist:` names the FSR-managed list to bind to.
            if kind in ("picklist", "multiselectpicklist"):
                pl = item.get("picklist") or item.get("options")
                if not pl:
                    errors.append(CompileError(
                        code=ErrorCode.MISSING_FIELD,
                        message=(f"`kind: {kind}` needs `picklist: "
                                 "<name>` to bind a managed FSR picklist"),
                        path=f"{ipath}.picklist",
                        suggestion="picklist: Severity",
                    ))
                    continue
                field["picklist"] = pl
            out.append(field)
        return out

    def _normalize_manual_input_args(
        self, step: Step, path: str, errors: list[CompileError],
    ) -> None:
        """Friendly manual_input authoring shape:

            arguments:
              title: "Approve?"
              description: "Optional markdown body"
              options: [Continue]                  # or [{option: yes, primary: true}, {option: no}]
              inputs:                              # optional fields to collect
                - {name: comment, kind: textarea, label: "Comment", required: true}
                - {name: severity, kind: select, options: [Low, Med, High]}

        Expands to FSR's canonical InputBased shape (input.schema +
        response_mapping + the dozen always-present sibling fields).
        Already-canonical args (with `input` + `response_mapping`)
        pass through untouched.
        """
        a = step.arguments if isinstance(step.arguments, dict) else {}
        # Hard rule: if `input` is provided, it MUST be a dict. FSR's
        # runtime calls .get() on it. Producing a string here is a common
        # LLM failure mode that previously slipped through to a runtime
        # crash (`'str' object has no attribute 'get'`).
        raw_input = a.get("input")
        if raw_input is not None and not isinstance(raw_input, dict):
            errors.append(CompileError(
                code=ErrorCode.BAD_VALUE,
                message=(
                    f"manual_input.arguments.input must be a mapping "
                    f"(got {type(raw_input).__name__}); FSR will crash with "
                    f"\"'str' object has no attribute 'get'\""
                ),
                path=f"{path}.arguments.input",
                suggestion='use: input: { title: "...", options: [...] }',
            ))
            return
        # Whitelist — friendly + canonical (incl. mode-driven extensions).
        # Each canonical key is permitted at the syntax level; the
        # mode-aware co-presence checker below catches incoherent
        # combinations (e.g. external email keys in an internal-only
        # prompt). See MI_DECISION_VALIDATION_AUDIT.md §0 for the model.
        _FRIENDLY = {"title", "description", "options", "inputs",
                     "mode", "audience", "assignee"}
        _CANONICAL = {
            "type", "input", "record", "is_approval", "isRecordLinked",
            "owner_detail", "step_variables", "response_mapping",
            "email_notification", "inline_channel_list",
            "external_channel_list", "unauthenticated_input", "resources",
            # Audience-mode + email-template keys (live in 13–142 of 168 MIs)
            "agent_id", "timeout", "inputExternalUser", "inputInternalUsers",
            "internal_email_subject", "external_email_subject",
            "customEmailExternal", "customEmailInternal",
            "custom_email_body_external", "custom_email_body_internal",
            "external_email_attachments", "internal_email_attachments",
            "message", "label",
        }
        unknown = sorted(set(a) - _FRIENDLY - _CANONICAL)
        if unknown:
            errors.append(CompileError(
                code=ErrorCode.UNKNOWN_PARAM,
                message=(
                    f"manual_input: unknown argument(s) "
                    f"{', '.join(repr(k) for k in unknown)}; "
                    f"FSR drops these silently at runtime"
                ),
                path=f"{path}.arguments",
                suggestion=(
                    "friendly form: title, description, options, inputs · "
                    "canonical form: type=InputBased|DecisionBased, "
                    "input.schema, response_mapping, record, owner_detail, "
                    "agent_id, timeout, …"
                ),
            ))
            return
        # `type` if provided must be one of the two FSR ManualInput
        # dispatch values. Live FSR uses both: InputBased for any
        # form-collecting prompt, DecisionBased for button-only flows
        # (no input form). Anything else is junk.
        t = a.get("type")
        if t is not None and t not in ("InputBased", "DecisionBased"):
            errors.append(CompileError(
                code=ErrorCode.BAD_VALUE,
                message=(
                    f"manual_input.arguments.type must be 'InputBased' "
                    f"or 'DecisionBased' (got {t!r}); FSR has no other "
                    f"dispatch paths"
                ),
                path=f"{path}.arguments.type",
                suggestion="omit `type:` to let the compiler choose "
                           "InputBased (the default for any form-collecting prompt)",
            ))
            return
        if isinstance(a.get("input"), dict) and isinstance(
                a.get("response_mapping"), dict):
            step.arguments = a
            return
        title = a.pop("title", None) or step.name or "Awaiting input"
        description = a.pop("description", "")
        raw_options = a.pop("options", None) or [{"option": "Continue", "primary": True}]
        options = []
        # Per-option `next:` — promote into the step's branch map so the
        # emitter can resolve label → step_iri the same way it does for
        # decision steps. Previously the key was silently stripped, leaving
        # multi-button prompts with no targets. See audit §3.
        author_set_primary = False
        for o in raw_options:
            if isinstance(o, str):
                options.append({"option": o})
            elif isinstance(o, dict):
                if o.get("primary"):
                    author_set_primary = True
                opt_next = o.get("next")
                opt_label = o.get("option")
                if opt_next and opt_label:
                    step.branches.setdefault(opt_label, opt_next)
                options.append({k: v for k, v in o.items() if k != "next"})
        # Only auto-promote the first option to primary when the author
        # left every option unmarked. ~31% of live MIs ship with no
        # primary marker at all (FSR renders them as plain buttons).
        if options and not author_set_primary and len(options) > 1:
            # Multi-option prompts in the wild always pick a primary.
            options[0]["primary"] = True
        inputs = a.pop("inputs", None) or []
        expanded_inputs = self._expand_input_variables(inputs, path, errors)
        a["type"] = a.get("type", "InputBased")
        a["input"] = {
            "schema": {
                "title": title,
                "description": description,
                "inputVariables": expanded_inputs,
            },
        }
        a.setdefault("record", "")
        a.setdefault("is_approval", False)
        a.setdefault("isRecordLinked", False)
        a.setdefault("owner_detail", {"isAssigned": False})
        a.setdefault("step_variables", [])
        a["response_mapping"] = {
            "options": options,
            "duplicateOption": False,
            "customSuccessMessage": "Awaiting Playbook resumed successfully.",
        }
        a.setdefault("email_notification", {"enabled": False, "smtpParameters": []})
        a.setdefault("inline_channel_list", [])
        a.setdefault("external_channel_list", [])
        a.setdefault("unauthenticated_input", False)
        # Mode-aware co-presence checks (audit §0). Run after canonical
        # form is in place so we test the same shape that ships to FSR.
        self._check_manual_input_modes(a, path, errors)
        step.arguments = a

    # External-distribution keys gated by audience=external. Internal-only
    # prompts shouldn't carry these; flag if they do.
    _MI_EXTERNAL_KEYS = (
        "customEmailExternal", "external_email_subject",
        "external_email_attachments", "custom_email_body_external",
    )

    def _check_manual_input_modes(
        self, a: dict[str, Any], path: str, errors: list[CompileError],
    ) -> None:
        """Enforce co-presence rules across the three UI-mode dimensions
        documented in MI_DECISION_VALIDATION_AUDIT.md §0:
          - Context: Record Linked vs Record Independent.
          - Audience: Internal vs External (open form to non-FSR users).
          - Assignment: owner_detail.isAssigned + exactly-one-target.
        """
        # Context — `isRecordLinked` ↔ `record`.
        is_linked = bool(a.get("isRecordLinked"))
        record = a.get("record")
        if is_linked and not record:
            errors.append(CompileError(
                code=ErrorCode.BAD_VALUE,
                message=("manual_input: isRecordLinked=true requires a "
                         "non-empty `record:` (the record IRI to attach "
                         "the prompt to)"),
                path=f"{path}.arguments.record",
                suggestion='record: "{{ vars.input.records[0][\'@id\'] }}"',
            ))
        if not is_linked and record:
            errors.append(CompileError(
                code=ErrorCode.BAD_VALUE,
                message=("manual_input: `record:` is set but "
                         "isRecordLinked=false; FSR ignores `record` "
                         "in Record-Independent mode"),
                path=f"{path}.arguments.isRecordLinked",
                severity="warning",
                suggestion="set isRecordLinked: true to attach the "
                           "prompt to the record",
            ))
        # Audience — internal vs external. External = unauthenticated_input
        # (link is publicly resolvable) OR inputExternalUser (form opens to
        # non-FSR users via channel).
        is_external = bool(a.get("unauthenticated_input")) or bool(a.get("inputExternalUser"))
        bad_ext = [k for k in self._MI_EXTERNAL_KEYS if a.get(k)]
        if not is_external and bad_ext:
            errors.append(CompileError(
                code=ErrorCode.BAD_VALUE,
                message=(
                    f"manual_input: external-distribution key(s) "
                    f"{', '.join(repr(k) for k in bad_ext)} are set, but "
                    f"the prompt is internal-only (unauthenticated_input "
                    f"+ inputExternalUser are both false). FSR will "
                    f"silently drop these at runtime."
                ),
                path=f"{path}.arguments",
                suggestion="set unauthenticated_input: true (and usually "
                           "inputExternalUser: true) to enable external "
                           "delivery, or remove the customEmail*/external_* keys",
            ))
        if is_external and not (a.get("external_channel_list") or
                                 a.get("inline_channel_list")):
            errors.append(CompileError(
                code=ErrorCode.BAD_VALUE,
                message=("manual_input: external-mode prompt has no "
                         "delivery channels (external_channel_list and "
                         "inline_channel_list both empty); recipients "
                         "won't be notified"),
                path=f"{path}.arguments.external_channel_list",
                severity="warning",
            ))
        # Assignment — owner_detail.isAssigned ↔ exactly-one-target.
        od = a.get("owner_detail") if isinstance(a.get("owner_detail"), dict) else {}
        is_assigned = bool(od.get("isAssigned"))
        targets = {
            "assignedToPerson": od.get("assignedToPerson"),
            "assignedToTeam":   od.get("assignedToTeam"),
            "assignedToRecord": od.get("assignedToRecord"),
            "assignedToField":  od.get("assignedToField"),
        }
        populated = [k for k, v in targets.items()
                     if v not in (None, [], False, "")]
        if is_assigned and len(populated) != 1:
            errors.append(CompileError(
                code=ErrorCode.BAD_VALUE,
                message=(
                    f"manual_input: owner_detail.isAssigned=true requires "
                    f"exactly one of assignedToPerson/Team/Record/Field "
                    f"populated (got {populated or 'none'})"
                ),
                path=f"{path}.arguments.owner_detail",
            ))
        if not is_assigned and populated:
            errors.append(CompileError(
                code=ErrorCode.BAD_VALUE,
                message=(
                    f"manual_input: owner_detail.isAssigned=false but "
                    f"{', '.join(populated)} populated; either set "
                    f"isAssigned=true or clear those keys"
                ),
                path=f"{path}.arguments.owner_detail",
            ))

    def _normalize_code_snippet_args(self, step: Step) -> None:
        """Friendly Python-snippet step:

            arguments:
              code: |
                print("hi")
              config: test          # optional connector-config name (defaults to default)

        FSR's CodeSnippet step type uses the connector dispatcher under
        the hood (`script: /wf/workflow/tasks/connector`, connector
        `code-snippet`, op `python_inline_code_editor`). Args fill:
            connector, operation, version, params.python_function, config,
            operationTitle, step_variables, pickFromTenant.

        config UUID is resolved via connector_configs (live, cached).
        Already-canonical args (`connector`+`operation`+`params`) pass
        through untouched.
        """
        from connector_configs import resolve_config_id
        a = step.arguments if isinstance(step.arguments, dict) else {}
        if a.get("connector") and a.get("operation") and a.get("params"):
            step.arguments = a
            return
        code = a.pop("code", None) or a.pop("python", None) or ""
        config_name = a.pop("config", None) if isinstance(
            a.get("config"), str) and not _looks_like_uuid(a.get("config")) \
            else None
        cid = resolve_config_id("code-snippet", config_name) or ""
        a.setdefault("connector", "code-snippet")
        a.setdefault("operation", "python_inline_code_editor")
        a.setdefault("operationTitle", "Execute Python Code")
        a.setdefault("version", "2.1.4")
        a.setdefault("config", cid)
        params = a.get("params") if isinstance(a.get("params"), dict) else {}
        params.setdefault("python_function", code)
        a["params"] = params
        a.setdefault("step_variables", [])
        step.arguments = a

    def _normalize_delay_args(self, step: Step) -> None:
        """Friendly delay step:

            arguments:
              seconds: 5      # or minutes/hours/days

        Expands to FSR's canonical TimeBased rule shape with the
        instance-wide `resume_playbook` channel UUID. Already-canonical
        args (top-level `type`, `delay`, `rule`) pass through untouched.
        """
        a = step.arguments if isinstance(step.arguments, dict) else {}
        # Don't clobber explicit canonical input.
        if "rule" in a and "delay" in a:
            step.arguments = a
            return
        delay = {"days": 0, "hours": 0, "minutes": 0, "seconds": 0}
        for k in ("days", "hours", "minutes", "seconds"):
            if k in a:
                delay[k] = int(a.pop(k))
        if not any(delay.values()):
            delay["seconds"] = 1  # avoid zero-delay edge cases
        a["type"] = a.get("type", "TimeBased")
        a["delay"] = delay
        a.setdefault("rule", {
            "actions": [{
                "type": "resume_playbook", "enabled": True,
                # FSR-instance-wide constant; same value on every box.
                "channel_uuid": "e2ce87c2-c55a-11ec-9d64-0242ac120002",
            }],
            "is_active": True,
            "event_source": "crudhub",
        })
        step.arguments = a

    def _normalize_start_args(self, step: Step) -> None:
        """abstract_trigger needs `arguments.step_variables.input.params`
        populated even when the playbook takes no input — without it FSR's
        runtime fails with `pop expected at most 1 argument, got 2` when it
        tries to extract the input shape (verified live 2026-05-03).
        Mirrors the canonical default observed in every live playbook.
        """
        a = step.arguments if isinstance(step.arguments, dict) else {}
        a.setdefault("step_variables", {"input": {"params": []}})
        step.arguments = a

    # Friendly-form keys we accept on set_variable. Anything else (most
    # common: `variables`, `vars`, `set`) gets caught with a "did you
    # mean?" suggestion. Without this gate the FSR runtime silently
    # drops the keys and the playbook ships with no variables set —
    # the bug that produced the down-rated session 60743f70.
    _SET_VARIABLE_FRIENDLY = {"arg_list"}
    _SET_VARIABLE_TYPOS: dict[str, str] = {
        "variables": "arg_list",
        "vars": "arg_list",
        "set": "arg_list",
        "values": "arg_list",
        "step_variables": "arg_list",
    }

    def _normalize_set_variable_args(
        self, step: Step, path: str, errors: list[CompileError],
    ) -> None:
        """Canonical SetVariable.arguments is a flat {var_name: value} dict.

        Verified against live import sample (Playbook - 00 - a Import
        testing): `{var1, var2, var3}` flat dict. Accept the friendly
        `arg_list: [{name, value}, ...]` form as back-compat sugar and
        unwrap it.

        Also flag common LLM typos (`variables:`, `vars:`, `set:`) that
        would otherwise be silently passed through as opaque var names.
        """
        a = step.arguments
        if not isinstance(a, dict):
            return
        # If the value is the friendly `[{name, value}, ...]` shape
        # under a typo key, surface a clear fix.
        for typo, canonical in self._SET_VARIABLE_TYPOS.items():
            if typo in a and isinstance(a[typo], list) and a[typo] and \
                    isinstance(a[typo][0], dict) and "name" in a[typo][0]:
                errors.append(CompileError(
                    code=ErrorCode.UNKNOWN_PARAM,
                    message=(
                        f"set_variable: {typo!r} is not a recognized key — "
                        f"FSR drops it silently at runtime, leaving the "
                        f"playbook with no variables set"
                    ),
                    path=f"{path}.arguments.{typo}",
                    suggestion=f"rename {typo!r} → {canonical!r}",
                    near=canonical,
                ))
                return
        if "arg_list" in a and isinstance(a["arg_list"], list):
            unwrapped: dict = {}
            for i, item in enumerate(a["arg_list"]):
                if not isinstance(item, dict) or "name" not in item:
                    errors.append(CompileError(
                        code=ErrorCode.BAD_VALUE,
                        message="arg_list entries must be {name, value} mappings",
                        path=f"{path}.arguments.arg_list[{i}]",
                    ))
                    return
                unwrapped[item["name"]] = item.get("value", "")
            siblings = {k: v for k, v in a.items() if k != "arg_list"}
            step.arguments = {**unwrapped, **siblings}

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
