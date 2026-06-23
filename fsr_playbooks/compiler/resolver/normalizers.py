"""NormalizerMixin — step argument normalization and step type dispatching."""
from __future__ import annotations

import sqlite3
from typing import Any

from ..errors import CompileError, ErrorCode
from ..ir import Playbook, Step
from ._constants import _looks_like_uuid
# Field-based-trigger `when:` typing now lives in the typed-args layer. The
# operator tables + `_wrap_like_value` are re-exported here for backward
# compatibility (tests and any callers import them from this module).
from ..typed_args.trigger import (  # noqa: F401
    expand_when as _expand_when_typed,
    _TRIGGER_OPS,
    _TRIGGER_OP_ALIASES,
    _TRIGGER_OP_REWRITE,
    _wrap_like_value,
)
# set_variable arg-shape typing lives in the typed-args layer too (Phase 2,
# first per-step-type model). The reserved-key rename still runs earlier in
# the RewriterMixin; this only owns the arg_list → flat-dict unwrap.
from ..typed_args.steps import expand_set_variable as _expand_set_variable_typed
# decision branch-promotion + condition-key typo check (Phase 2 model).
from ..typed_args.steps import expand_decision as _expand_decision_typed
# field/value validation for trigger filters against the warmed catalog.
from ..typed_args import FieldValueValidator


class NormalizerMixin:
    """Methods for normalizing step arguments and dispatching by step type."""

    conn: sqlite3.Connection

    def _resolve_step(
        self, step: Step, path: str, errors: list[CompileError],
        pb_by_name: dict[str, "Playbook"] | None = None,
        pb_name: str | None = None,
    ) -> None:
        st = self.step_type(step.type)
        if st is None:
            sug = self.suggest_step_type(step.type)
            # Common authoring mistake: `type: for_each` (or `forEach`,
            # `for-each`, `foreach`). `for_each` is a step *modifier*,
            # not a step type — surface that explicitly so the agent
            # doesn't waste turns guessing alternative step names.
            if step.type and step.type.lower().replace("-", "_") in {
                "for_each", "foreach"
            }:
                msg = (
                    "for_each is a step modifier, not a step type. "
                    "Remove `type: for_each` and instead attach a "
                    "`for_each:` block (sibling to `arguments:`) on the "
                    "step you want to iterate — e.g. `type: "
                    "create_record` / `update_record` / "
                    "`workflow_reference` with `for_each: {item: '{{ "
                    "vars.list }}', parallel: false}`."
                )
                errors.append(CompileError(
                    code=ErrorCode.UNKNOWN_STEP_TYPE,
                    message=msg,
                    path=f"{path}.type",
                    suggestion=msg,
                ))
                return
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
                self._normalize_record_action_args(step, path, errors, pb_name)

        if step.type in ("start_on_create", "start_on_update"):
            self._normalize_post_create_update_args(step, path, errors, pb_name)

        if step.type in ("create_record", "insert_record", "update_record"):
            self._normalize_record_crud_args(step, path, errors)

        if step.type == "find_record":
            self._normalize_find_record_args(step, path, errors)

        if step.type == "delay":
            self._normalize_delay_args(step, path, errors)

        if step.type == "code_snippet":
            self._normalize_code_snippet_args(step, path, errors)

        if step.type == "manual_input":
            self._normalize_manual_input_args(step, path, errors)
        if step.type == "decision":
            self._normalize_decision_args(step, path, errors)

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
            # message block still applies to connector steps — fall through.
        elif step.type == "workflow_reference":
            self._resolve_workflow_reference_args(step, path, errors, pb_by_name or {})
        elif step.type == "set_variable":
            self._normalize_set_variable_args(step, path, errors)
        elif step.type == "start":
            self._normalize_start_args(step)
        # decision: no further ref-checking in v1 — args are free-form jinja.

        # message: posts a collaboration comment after the step runs.
        # Supported on all step types except delay (Wait) and set_api_keys,
        # which the FSR engine doesn't wire a post_message call for.
        _NO_MESSAGE_TYPES = {
            "delay", "set_api_keys",
            "start", "start_on_create", "start_on_update",
        }
        if (step.type not in _NO_MESSAGE_TYPES
                and isinstance(step.arguments, dict)
                and isinstance(step.arguments.get("message"), dict)):
            self._normalize_message_block(step, path, errors)

    def _normalize_record_action_args(
        self, step: Step, path: str, errors: list[CompileError],
        pb_name: str | None = None,
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
        if not button_label and pb_name:
            button_label = pb_name
            errors.append(CompileError(
                code=ErrorCode.MISSING_FIELD,
                message=(f"`button_label:` not set on {step.type} — "
                         f"defaulting to playbook name {pb_name!r}; set "
                         "`button_label:` explicitly to override"),
                path=f"{path}.arguments.button_label",
                severity="warning",
            ))
        modules_raw = a.pop("module", None) or a.pop("modules", None) or a.get("resources")
        if isinstance(modules_raw, str):
            modules = [modules_raw]
        elif isinstance(modules_raw, list):
            modules = [str(m) for m in modules_raw]
        else:
            modules = []
        if not modules:
            modules = ["alerts", "incidents"]
            errors.append(CompileError(
                code=ErrorCode.MISSING_FIELD,
                message=(f"`module:` not set on {step.type} — defaulting to "
                         "[alerts, incidents]; set `module:` explicitly to "
                         "override"),
                path=f"{path}.arguments.module",
                severity="warning",
            ))
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
        pb_name: str | None = None,
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
        _FRIENDLY = {"module", "modules", "when", "mock_result", "condition"}
        _CANONICAL = {
            "resource", "resources", "step_variables", "triggerOnSource",
            "triggerOnReplicate", "__triggerLimit", "fieldbasedtrigger",
            "useMockOutput",
            # Trigger schema version (post-update only in corpus, e.g. "2.0.2").
            "version",
        }
        if self._check_unknown_keys(
            a, step.type, _FRIENDLY, _CANONICAL, path, errors,
        ):
            return
        modules_raw = a.pop("module", None) or a.pop("modules", None) \
            or a.get("resources") or a.get("resource")
        if isinstance(modules_raw, str):
            modules = [modules_raw]
        elif isinstance(modules_raw, list):
            modules = [str(m) for m in modules_raw]
        else:
            modules = []
        if not modules:
            modules = ["alerts", "incidents"]
            errors.append(CompileError(
                code=ErrorCode.MISSING_FIELD,
                message=(f"`module:` not set on {step.type} — defaulting to "
                         "[alerts, incidents]; set `module:` explicitly to "
                         "override"),
                path=f"{path}.arguments.module",
                severity="warning",
            ))
        # Canonicalize each module name against the catalog (case-fix
        # 'Alerts' → 'alerts', warn on unknowns). Silent no-op when the
        # modules table is unwarmed/empty.
        modules = [
            self.resolve_module_name(m, f"{path}.arguments.module", errors)
            for m in modules
        ]
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
        # Field/value validation against the warmed catalog. Runs after the
        # filter tree is structurally valid. With multiple resolved modules a
        # field may legitimately exist on only some of them, so a finding is
        # emitted only when it holds for *every* module (invalid everywhere).
        self._validate_trigger_fields(a, modules, path, errors)
        step.arguments = a

    def _validate_trigger_fields(
        self, a: dict, modules: list[str], path: str,
        errors: list[CompileError],
    ) -> None:
        """Validate `fieldbasedtrigger` filters against the catalog.

        Silent no-op when there are no filters or no resolved modules. Each
        module is validated into its own bucket; a finding is promoted only
        when present for every module. Buckets are keyed by error `path`
        (stable across modules for a given filter) — the messages embed the
        module name and per-module valid lists, so they would never intersect.
        A field/value valid on any one module is therefore never flagged.
        """
        fbt = a.get("fieldbasedtrigger")
        if not isinstance(fbt, dict):
            return
        filters = fbt.get("filters")
        if not isinstance(filters, list) or not filters or not modules:
            return
        validator = FieldValueValidator(self.conn)
        per_module: list[dict[str | None, CompileError]] = []
        for m in modules:
            bucket: list[CompileError] = []
            validator.validate_trigger_filters(filters, m, path, bucket)
            per_module.append({e.path: e for e in bucket})
        common = set(per_module[0])
        for keys in per_module[1:]:
            common &= set(keys)
        for key in sorted(common, key=lambda p: p or ""):
            errors.append(per_module[0][key])

    def _expand_when(
        self, when, step_type: str, path: str, errors: list[CompileError],
    ):
        """Compile a friendly `when:` block into a `fieldbasedtrigger` dict.

        Delegates to the typed-args layer (`typed_args.trigger.expand_when`),
        which owns the `WhenGroup`/`WhenLeaf` models, the operator
        alias/rewrite/wildcard-wrap semantics, and nested AND/OR authoring.
        """
        return _expand_when_typed(when, step_type, path, errors)

    def _normalize_record_crud_args(
        self, step: Step, path: str, errors: list[CompileError],
    ) -> None:
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
        _FRIENDLY = {"module", "mock_result", "condition"}
        _CANONICAL = {
            "collection", "collectionType", "resource", "operation",
            "fieldOperation", "__recommend", "_showJson", "step_variables",
            "__bulk", "for_each",
            # Tag merge semantics on record writes; observed enum value:
            # "OverwriteTags" (other values exist in the FSR UI).
            "tagsOperation",
            # Upsert mode flag (InsertData with is_upsert=true).
            "is_upsert",
            # Connector-mode insert/update: config UUID + version string.
            "config", "version",
        }
        if self._check_unknown_keys(
            a, step.type, _FRIENDLY, _CANONICAL, path, errors,
        ):
            return
        module = a.pop("module", None)
        if module and isinstance(module, str):
            module = self.resolve_module_name(
                module, f"{path}.arguments.module", errors)
            iri = f"/api/3/{module}" if not module.startswith("/api/") else module
            if step.type in ("create_record", "insert_record"):
                a.setdefault("collection", iri)
            elif step.type == "update_record":
                a.setdefault("collectionType", iri)
        step.arguments = a

        # Friendly picklist tokens → IRIs. If the resource payload sets a
        # picklist-backed field to a bare string label (e.g. status:
        # "Closed"), rewrite to the canonical /api/3/picklists/<uuid>
        # IRI so callers don't have to spell out the `| picklist(...)`
        # filter in every write. Jinja expressions and existing IRIs
        # pass through untouched.
        self._resolve_picklist_friendly_tokens(step, path, errors)

    def _normalize_find_record_args(
        self, step: Step, path: str, errors: list[CompileError],
    ) -> None:
        """Strict-whitelist guard for find_record.

        Handler signature is `find_data(module, query, partial=True, **kw)`.
        Unknown keys silently disappear at runtime, so reject misspellings
        (e.g. `filter:` instead of `query:`) at compile time.
        """
        a = step.arguments if isinstance(step.arguments, dict) else {}
        _FRIENDLY: set[str] = set()
        _CANONICAL = {
            "module", "query", "partial", "mock_result", "condition",
            "step_variables", "checkboxFields",
        }
        self._check_unknown_keys(
            a, step.type, _FRIENDLY, _CANONICAL, path, errors,
        )

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
                # Common aliases the agent reaches for first; mapped to
                # the canonical kind. Catches the most frequent typos
                # before falling through to difflib.
                _ALIASES = {
                    "hostname": "domain", "host": "domain", "fqdn": "domain",
                    "ip": "ipv4", "ipaddress": "ipv4", "ipv": "ipv4",
                    "hash": "filehash", "sha256": "filehash",
                    "sha1": "filehash", "md5": "filehash",
                    "string": "text", "str": "text", "phone": "phonenumber",
                    "tel": "phonenumber", "bool": "checkbox",
                    "boolean": "checkbox", "int": "integer", "num": "integer",
                    "number": "integer", "dropdown": "select",
                    "list": "select", "datetime-local": "datetime",
                    "date": "datetime", "time": "datetime",
                }
                import difflib as _difflib
                guess = _ALIASES.get(str(kind or "").lower())
                if not guess:
                    matches = _difflib.get_close_matches(
                        str(kind or ""),
                        sorted(self._INPUT_FIELD_KINDS),
                        n=1, cutoff=0.6,
                    )
                    guess = matches[0] if matches else None
                msg = (
                    f"`inputs[].kind` must be one of "
                    f"{', '.join(sorted(self._INPUT_FIELD_KINDS))}; "
                    f"got {kind!r}"
                )
                errors.append(CompileError(
                    code=ErrorCode.BAD_VALUE,
                    message=msg,
                    path=f"{ipath}.kind",
                    suggestion=(f"did you mean {guess!r}?"
                                if guess else None),
                    near=guess,
                ))
                continue
            # Hint: warn when a text-typed field's name/label clearly maps
            # to a more specific kind (ipv4, email, url, domain, filehash).
            # FSR validates the user's input against formType, so picking
            # the wrong kind silently accepts garbage.
            if kind == "text":
                hint = self._suggest_specific_kind(
                    str(item.get("name", "")),
                    str(item.get("label", "")),
                )
                if hint:
                    errors.append(CompileError(
                        code=ErrorCode.BAD_VALUE,
                        message=(f"input field {name!r} looks like a {hint!r} "
                                 f"value but kind is 'text' — switch to "
                                 f"kind: {hint} so FSR validates the format"),
                        path=f"{ipath}.kind",
                        severity="warning",
                    ))
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

    def _normalize_decision_args(
        self, step: Step, path: str, errors: list[CompileError],
    ) -> None:
        """Promote inline `next:` on each condition into `step.branches`.

        Friendly authoring shape that avoids the parallel `branches:` map:

            arguments:
              conditions:
                - option: "Greater Than 10"
                  condition: "{{ vars.input.value > 10 }}"
                  next: greater_step
                - option: "Else"
                  default: true
                  next: not_greater_step

        The `next:` key is stripped from the emitted condition entry and
        copied into `step.branches[option] = next` so the existing emitter
        path (which resolves label → step_iri off `step.branches`) handles
        wiring without authors having to maintain a parallel map.

        Delegates to the typed-args layer (`typed_args.steps.expand_decision`),
        which owns the `DecisionArgs`/`DecisionCondition` models. Beyond the
        byte-identical branch-promotion, the typed condition model now catches
        a mistyped condition key (e.g. `nxt:`) that previously dropped the
        branch silently. Mutates `step.arguments`/`step.branches` in place.
        """
        _expand_decision_typed(step.arguments, step.branches, path, errors)

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
        unknown = sorted(set(a) - _FRIENDLY - _CANONICAL
                         - self._UNIVERSAL_STEP_KEYS)
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

    def _normalize_code_snippet_args(
        self, step: Step, path: str, errors: list[CompileError],
    ) -> None:
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

        config UUID is resolved offline from the warmed `connector_configs`
        catalog table (Resolver.resolve_config_id) — no live lookup, no
        dev-only `tooling/` import. Already-canonical args
        (`connector`+`operation`+`params`) pass through untouched.
        """
        a = step.arguments if isinstance(step.arguments, dict) else {}
        if a.get("connector") and a.get("operation") and a.get("params"):
            self._require_nonempty_snippet(a.get("params"), path, errors)
            step.arguments = a
            return
        # Config resolution reads the warmed `connector_configs` table via the
        # CatalogLookupMixin (in-package, offline). When that table is unwarmed
        # it returns None and we degrade to an unresolved config UUID (`""`) so
        # the friendly `code:` form still compiles offline — warmup fills the
        # real UUID later. This used to import the dev-only `tooling/`
        # connector_configs module, which crashed every code_snippet compile in
        # a fresh wheel.
        _FRIENDLY = {"code", "python", "config", "mock_result", "condition"}
        _CANONICAL = {
            "connector", "operation", "operationTitle", "version",
            "params", "step_variables", "pickFromTenant",
        }
        if self._check_unknown_keys(
            a, "code_snippet", _FRIENDLY, _CANONICAL, path, errors,
        ):
            return
        code = a.pop("code", None) or a.pop("python", None) or ""
        config_name = a.pop("config", None) if isinstance(
            a.get("config"), str) and not _looks_like_uuid(a.get("config")) \
            else None
        cid = self.resolve_config_id("code-snippet", config_name) or ""
        a.setdefault("connector", "code-snippet")
        a.setdefault("operation", "python_inline_code_editor")
        a.setdefault("operationTitle", "Execute Python Code")
        a.setdefault("version", "2.1.4")
        a.setdefault("config", cid)
        params = a.get("params") if isinstance(a.get("params"), dict) else {}
        params.setdefault("python_function", code)
        a["params"] = params
        a.setdefault("step_variables", [])
        self._require_nonempty_snippet(params, path, errors)
        step.arguments = a

    @staticmethod
    def _require_nonempty_snippet(
        params, path: str, errors: list[CompileError],
    ) -> None:
        """Reject a code_snippet step whose resolved ``python_function`` is
        empty/whitespace.

        Two authoring paths land here with an empty snippet: a step-level
        ``connector:``/``operation:``/``params:`` block (which the parser
        does NOT hoist into ``arguments`` for non-connector steps, so the
        body is dropped), or a friendly form with no ``code:``/``python:``.
        Either way the step used to compile green and deploy a no-op
        snippet. Fail it with an actionable message instead.
        """
        code = ""
        if isinstance(params, dict):
            code = params.get("python_function") or ""
        if isinstance(code, str) and code.strip():
            return
        errors.append(CompileError(
            code=ErrorCode.MISSING_FIELD,
            message=(
                "code_snippet step has an empty `python_function` — no code "
                "to run"
            ),
            path=f"{path}.arguments.params.python_function",
            suggestion=(
                "put the code under `arguments.params.python_function:` "
                "(canonical) or use the friendly `arguments.code:` form"
            ),
        ))

    def _normalize_delay_args(
        self, step: Step, path: str, errors: list[CompileError],
    ) -> None:
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
        _FRIENDLY = {"seconds", "minutes", "hours", "days", "mock_result",
                     "condition"}
        # `timeout`: branch-resume variant {days, hours, minutes, step_iri};
        # used when a Delay anchors an "after timeout, resume at step X" path.
        _CANONICAL = {"type", "delay", "rule", "step_variables", "timeout"}
        if self._check_unknown_keys(
            a, "delay", _FRIENDLY, _CANONICAL, path, errors,
        ):
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

    def _normalize_set_variable_args(
        self, step: Step, path: str, errors: list[CompileError],
    ) -> None:
        """Unwrap the parser-emitted `arg_list:` list into a flat
        {var_name: value} dict, matching FSR's wire format.

        The parser converts top-level `vars:` into `arguments.arg_list =
        [{name, value}, ...]`; we collapse that back into the flat shape
        FSR expects on the wire. `arg_list` is an internal handoff key —
        users write `vars:` at the step level (parser rejects anything
        else for set_variable steps).

        Delegates to the typed-args layer (`typed_args.steps.
        expand_set_variable`), which owns the `SetVariableArgs` model and the
        unwrap walk. A ``None`` return means "leave arguments unchanged"
        (no arg_list, non-list arg_list, or a malformed entry).
        """
        a = step.arguments
        if not isinstance(a, dict):
            return
        new = _expand_set_variable_typed(a, path, errors)
        if new is not None:
            step.arguments = new

    # FSR's built-in "Comment Type" picklist — drives the message kind on
    # the record's collaboration panel. Only the Comment value is used;
    # the IRI is stable across stock FSR installs (sourced from
    # `fsrpb picklist show "Comment Type"`). If a deployment customizes
    # this picklist, authors can pass a full IRI instead of a name.
    _MESSAGE_TYPE_IRIS = {
        "comment": "/api/3/picklists/ff599189-3eeb-4c86-acb0-a7915e85ac3b",
    }
    _DEFAULT_MESSAGE_TYPE_IRI = _MESSAGE_TYPE_IRIS["comment"]

    def _normalize_message_block(
        self, step: Step, path: str, errors: list[CompileError],
    ) -> None:
        a = step.arguments
        msg = a["message"]
        mpath = f"{path}.arguments.message"
        _ALLOWED = {"content", "tags", "type", "thread", "record", "records"}
        unknown = sorted(set(msg) - _ALLOWED)
        if unknown:
            errors.append(CompileError(
                code=ErrorCode.UNKNOWN_PARAM,
                message=(f"set_variable.message: unknown key(s) "
                         f"{', '.join(repr(k) for k in unknown)}"),
                path=mpath,
                suggestion="allowed: content, tags, record(s), type, thread",
            ))
            return
        content = msg.get("content")
        if not content or not isinstance(content, str):
            errors.append(CompileError(
                code=ErrorCode.MISSING_FIELD,
                message="set_variable.message requires `content:` (string)",
                path=f"{mpath}.content",
            ))
            return
        # Wrap plain text in a <p> block — the FSR comment widget renders
        # HTML and a bare string shows as one inline run.
        if "<" not in content:
            content = f"<p>{content}</p>"
        # Tags: friendly names → /api/3/tags/<name>. Already-IRI strings
        # pass through. FSR resolves the slug at import time.
        raw_tags = msg.get("tags") or []
        if not isinstance(raw_tags, list):
            errors.append(CompileError(
                code=ErrorCode.BAD_VALUE,
                message="set_variable.message.tags must be a list",
                path=f"{mpath}.tags",
            ))
            return
        # Live tag verification — if the reference store has been
        # populated via `fsrpb probe modules` (which now also hydrates
        # the tags table), warn on names that don't exist on the FSR
        # instance. Skip the check when the table is empty or missing
        # so the resolver degrades gracefully on a fresh install.
        known_tags: dict[str, str] = {}
        try:
            known_tags = {
                row["name"].lower(): row["iri"]
                for row in self.conn.execute(
                    "SELECT name, iri FROM tags"
                ).fetchall()
            }
        except sqlite3.Error:
            pass
        tag_iris: list[str] = []
        for t in raw_tags:
            if not isinstance(t, str):
                continue
            if t.startswith("/api/"):
                tag_iris.append(t)
                continue
            lookup = known_tags.get(t.lower())
            if lookup:
                tag_iris.append(lookup)
            else:
                if known_tags:
                    errors.append(CompileError(
                        code=ErrorCode.BAD_VALUE,
                        message=(
                            f"set_variable.message.tags: tag {t!r} not "
                            "found on the FSR instance; it will be "
                            "auto-created on first use — confirm the "
                            "spelling or pre-create the tag in the UI"
                        ),
                        path=f"{mpath}.tags",
                        severity="warning",
                    ))
                tag_iris.append(f"/api/3/tags/{t}")
        msg_type_raw = msg.get("type")
        # Live picklist lookup first — probe_modules hydrates the
        # picklists table per-deployment, so deployments that customized
        # the Comment Type picklist resolve correctly here. The
        # _MESSAGE_TYPE_IRIS map is a fallback when the reference store
        # has not been populated.
        live_map: dict[str, str] = {}
        live_options: list[str] = []
        try:
            rows = self.conn.execute(
                "SELECT item_value, item_iri FROM picklists "
                "WHERE list_name = 'Comment Type'",
            ).fetchall()
            for row in rows:
                val = row["item_value"]
                live_options.append(val)
                live_map[val.strip().lower().replace(" ", "")] = row["item_iri"]
        except sqlite3.Error:
            pass
        default_iri = live_map.get("comment") or self._DEFAULT_MESSAGE_TYPE_IRI
        if msg_type_raw is None:
            msg_type = default_iri
        elif str(msg_type_raw).startswith("/api/"):
            msg_type = msg_type_raw
        else:
            key = str(msg_type_raw).strip().lower().replace(" ", "")
            if key in live_map:
                msg_type = live_map[key]
            elif key in self._MESSAGE_TYPE_IRIS:
                msg_type = self._MESSAGE_TYPE_IRIS[key]
            else:
                msg_type = default_iri
                known = ", ".join(live_options) if live_options else "Comment"
                errors.append(CompileError(
                    code=ErrorCode.BAD_VALUE,
                    message=(f"set_variable.message.type {msg_type_raw!r} is "
                             f"not a known Comment Type value ({known}) "
                             "or an IRI; defaulting to Comment"),
                    path=f"{mpath}.type",
                    severity="warning",
                ))
        thread = bool(msg.get("thread", False))
        # Record IRI: friendly `record:` (single) → `records:` jinja
        # string. The wire field is `records:` (singular IRI value, not a
        # list — FSR templates the IRI in directly).
        rec_single = msg.get("record")
        rec_explicit = msg.get("records")
        rec_value: str | None
        if rec_explicit is not None:
            rec_value = rec_explicit
        elif rec_single is not None:
            rec_value = rec_single
        else:
            rec_value = None
        wire: dict = {
            "tags": tag_iris,
            "type": msg_type,
            "thread": thread,
            "content": content,
            "records": rec_value if rec_value is not None else "",
        }
        a["message"] = wire

    def _summarize_visible_set(
        self, rules: list[tuple[str, str | None, str | None]],
        select_param: str, value: str,
    ) -> list[str]:
        """Param names that become visible when `select_param == value`.

        Includes unconditional siblings (no parent rule) and the direct
        and transitive children gated by this choice. Used for consolidated
        param_set_conflict suggestions so the agent can replace a whole
        argument set in one pass.
        """
        from collections import defaultdict
        children_of: dict[tuple[str, str], list[str]] = defaultdict(list)
        for n, p, c in rules:
            if p is not None:
                children_of[(p, str(c))].append(n)
        all_names = {n for n, _, _ in rules}
        # Unconditional names that are not the select itself.
        cond_names = {n for n, p, _ in rules if p is not None}
        unconditional = sorted(all_names - cond_names - {select_param})
        visible = list(unconditional)
        seen = set(visible)
        # Walk gated children; include every option of any nested select
        # so the agent sees the full feasible neighborhood.
        frontier = [(select_param, value)]
        while frontier:
            sp, sv = frontier.pop()
            for child in children_of.get((sp, sv), []):
                if child in seen:
                    continue
                visible.append(child)
                seen.add(child)
                # Nested select: enqueue all of its options to expand
                # transitive children.
                for (ssp, ssv) in list(children_of.keys()):
                    if ssp == child:
                        frontier.append((ssp, ssv))
        return visible

    def _check_param_visibility(
        self, connector: str, operation: str,
        provided: dict, path: str, errors: list[CompileError],
    ) -> None:
        """Flag provided params whose visibility predicate is false.

        Each operation_params row that has a parent_param_name is only
        visible when that parent's value equals condition_value. If the
        author provides a conditional param without satisfying its rule,
        FSR still ships the value but the field is hidden in the UI and
        the operation typically rejects it at runtime — silent failures.
        """
        rules = self.operation_param_rules(connector, operation)
        if not rules:
            return
        # Group by param name; a param can have multiple visibility rules
        # (any one of them being satisfied makes the param visible).
        from collections import defaultdict
        rules_by_name: dict[str, list[tuple[str | None, str | None]]] = defaultdict(list)
        for name, parent, cond in rules:
            rules_by_name[name].append((parent, cond))
        # Track conflicts grouped by their *gating* parent param so we can
        # emit one consolidated `param_set_conflict` summary at the end.
        conflicts_by_parent: dict[str, list[str]] = {}
        for p_name, p_value in provided.items():
            entries = rules_by_name.get(p_name)
            if not entries:
                continue  # already handled by unknown-param branch
            # Top-level param (parent is NULL) → always visible.
            if any(parent is None for parent, _ in entries):
                continue
            # Conditional — at least one rule must match the provided
            # parent value. If parent isn't provided, we can't satisfy.
            satisfied = False
            for parent, cond in entries:
                if parent in provided and str(provided[parent]) == str(cond):
                    satisfied = True
                    break
            if satisfied:
                continue
            # Build a "valid only when …" hint from all the rules.
            conds = ", ".join(
                f"{parent}={cond!r}" for parent, cond in entries
            )
            errors.append(CompileError(
                code=ErrorCode.BAD_VALUE,
                message=(
                    f"param {p_name!r} on {connector}.{operation} is only "
                    f"valid when {conds}; FSR will hide the field at "
                    f"runtime and likely reject the call"
                ),
                path=f"{path}.arguments.params.{p_name}",
                suggestion=f"set the parent param to match, or remove {p_name!r}",
                severity="warning",
            ))
            # Pick the first parent listed as the gating select for
            # grouping; visibility cascades, so the top-of-chain parent
            # gives the agent the most actionable feasible-set view.
            gating = entries[0][0]
            conflicts_by_parent.setdefault(gating, []).append(p_name)

        # One consolidated diagnostic per gating select — lists the full
        # feasible param neighborhood under each option so the agent can
        # converge in one fix instead of cascading turn-by-turn.
        for gating, conflicting in conflicts_by_parent.items():
            chosen = provided.get(gating)
            # Discover all option values this select can take from rules.
            option_values = sorted({
                str(c) for n, p, c in rules if p == gating and c is not None
            })
            sets_by_option = {
                opt: self._summarize_visible_set(rules, gating, opt)
                for opt in option_values
            }
            chosen_str = (
                f"chosen value {gating}={chosen!r}"
                if chosen is not None else
                f"{gating!r} not provided"
            )
            valid_sets_blob = "; ".join(
                f"{gating}={opt!r} → {sets_by_option[opt]}"
                for opt in option_values
            )
            errors.append(CompileError(
                code=ErrorCode.BAD_VALUE,
                message=(
                    f"param-set conflict on {connector}.{operation}: "
                    f"{chosen_str} is incompatible with provided "
                    f"params {conflicting!r}"
                ),
                path=f"{path}.arguments.params",
                suggestion=(
                    f"pick one option for {gating!r} and use ONLY the "
                    f"params under it. Feasible sets: {valid_sets_blob}"
                ),
                severity="warning",
            ))

    def _check_conditional_required(
        self, connector: str, operation: str,
        provided: dict, path: str, errors: list[CompileError],
    ) -> None:
        """Flag conditionally-required params that the chosen branch activates
        but the author omitted.

        The inverse of `_check_param_visibility`: there we reject a provided
        param whose gate is unsatisfied; here we reject a *missing* param that
        the chosen (or defaulted) parent value makes required. Visibility
        cascades, so this walks the chain — e.g. block_ip_new(method='Policy
        Based') requires `ip_type` + `ip_block_policy`; ip_type='IPv4' then
        requires `ip`. A param with its own default_value is satisfied by the
        default (FSR pre-fills it) and is not flagged.
        """
        rules = self.operation_param_required_rules(connector, operation)
        if not rules:
            return
        # Per-param: default value, and the (parent, condition, required) rows.
        from collections import defaultdict
        rows_by_name: dict[str, list[tuple[str | None, str | None, bool]]] = defaultdict(list)
        default_of: dict[str, str | None] = {}
        for name, parent, cond, required, default in rules:
            # Warmup writes top-level parent/condition as empty strings (not
            # NULL); normalize so '' reads as "no parent / no condition".
            parent = parent or None
            cond = cond if cond not in (None, "") else None
            rows_by_name[name].append((parent, cond, required))
            if default not in (None, "") and name not in default_of:
                default_of[name] = default

        def effective(param: str):
            """Provided value if set & non-empty, else the param's default."""
            v = provided.get(param)
            if v not in (None, ""):
                return v
            return default_of.get(param)

        # A param is "active" (FSR would render + enforce it) iff it has a row
        # whose parent is None, or whose parent is active AND the parent's
        # effective value matches the condition. Memoized; cycle-guarded.
        active_cache: dict[str, bool] = {}

        def active(param: str, stack: frozenset) -> bool:
            if param in active_cache:
                return active_cache[param]
            if param in stack:  # defensive: a malformed cyclic schema
                return False
            result = False
            for parent, cond, _req in rows_by_name.get(param, []):
                if parent is None:
                    result = True
                    break
                if active(parent, stack | {param}) and \
                        str(effective(parent)) == str(cond):
                    result = True
                    break
            active_cache[param] = result
            return result

        for name, entries in rows_by_name.items():
            # Top-level required params (every row has parent None) used to be
            # deferred to the run_op preflight (_validate_op_params). But the
            # authoring flow (compile → verify_playbook → push) never runs that
            # preflight, so a missing top-level-required param compiled clean
            # and verify_playbook reported ready_to_push=True — then FSR
            # rejected the call at runtime. We now flag it here as an *error*
            # (conditional/gated misses below stay warnings).
            pure_top_level = all(parent is None for parent, _cond, _req in entries)
            # Already supplied (non-empty literal/ref) → nothing to require.
            if provided.get(name) not in (None, ""):
                continue
            # A default satisfies the requirement (FSR ships the default).
            if default_of.get(name) not in (None, ""):
                continue
            if not active(name, frozenset()):
                continue
            # Required under the *active* branch? A param can be required in
            # one branch and optional in another; only the active row counts.
            req_here = False
            gate_desc = ""
            for parent, cond, required in entries:
                if not required:
                    continue
                if parent is None or (
                        active(parent, frozenset()) and
                        str(effective(parent)) == str(cond)):
                    req_here = True
                    gate_desc = (f" (required when {parent}={cond!r})"
                                 if parent is not None else " (required)")
                    break
            if not req_here:
                continue
            errors.append(CompileError(
                code=ErrorCode.MISSING_FIELD,
                message=(
                    f"required param {name!r} on {connector}.{operation} is "
                    f"missing{gate_desc}; FSR will reject the call at runtime"
                ),
                path=f"{path}.arguments.params.{name}",
                suggestion=f"add {name!r} to arguments.params",
                severity="error" if pure_top_level else "warning",
            ))

