"""FSR WorkflowCollection JSON -> IR.

The inverse of `emitter.emit`. Used for the round-trip acceptance test
and (later) for "import an existing playbook into the YAML world."

Lossiness: FSR JSON carries fields the IR doesn't model (lastModifyDate,
deletedAt, layout coords, recordTags, ownership). Those are dropped
on the way in; the IR is the human-meaningful subset.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from .ir import PRIORITY_LIST_NAME, Annotation, Collection, Playbook, Step
from .resolver import SHORT_TYPE_TO_FSR
from .wire import as_record_list

_FSR_TO_SHORT = {v: k for k, v in SHORT_TYPE_TO_FSR.items()}

# Canonical FSR step-type names that share a friendly short name with another
# canonical, so they can't live in the 1:1 SHORT_TYPE_TO_FSR (which is keyed by
# friendly name for the forward compile direction). Overlay them here so the
# decompiler resolves them instead of falling through as raw canonicals.
#
# `cybersponse.action` (uuid f414d039, ManualStart / Execute-menu ACTION_TRIGGER)
# is the record-listing twin of `cybersponse.abstract_trigger` -- both compile
# FROM friendly `start` (the forward map's `SHORT_TYPE_TO_FSR["start"]`); the
# split happens at emit time in `resolver/normalizers.py`, where a `start` step
# bound to a `module` is rewritten to `cybersponse.action`. On the reverse
# (decompile) trip the live box hands back `cybersponse.action` as the canonical
# name; without this overlay entry `_FSR_TO_SHORT` misses it and the step's
# `type` falls through as the raw canonical `cybersponse.action`, which on
# recompile fails validation as `no_trigger`. Mapping it to `start` is
# non-lossy: the normalizer re-derives `cybersponse.action` from the `module`
# argument on recompile (round-trip verified).
#
# The codebase already agrees `cybersponse.action` is a `start` trigger --
# `step_param_audit.TYPE_NAME_TO_RESOLVER` and
# `tests/wire_shape_oracle._TITLE_TO_TYPE` both list it; only this reverse map
# was missing it.
#
# NOTE: the `cybersponse.pre_*` canonicals (pre_create/pre_update/pre_delete)
# exist in the step_types table but are deliberately NOT mapped here. They have
# no `start_on_*` twin -- `start_on_create/update/delete` recompile to the
# `post_*` triggers, so aliasing `pre_create -> start_on_create` would silently
# flip a pre-event trigger to post-event. Those decompile as raw canonicals
# until a dedicated friendly short type exists for them.
#
# `Connectors` (uuid 0bfed618, the generic connector step) is a many-to-one
# forward collision: friendly `connector`, `stop`, `end`, AND `delete_record`
# all compile TO canonical `Connectors` (resolver/_constants.py).
# `_FSR_TO_SHORT = {v: k for k, v in SHORT_TYPE_TO_FSR.items()}` is a last-wins
# comprehension, so without this overlay it resolves `Connectors` to
# `delete_record` (the last entry) -- mislabeling EVERY plain connector step on
# pull as `delete_record`. That mislabel is a live round-trip break:
# `delete_record` carries a strict argument whitelist (`_normalize_delete_record_args`
# `_FRIENDLY`/`_CANONICAL`) that rejects the box-injected envelope keys
# `step_variables`/`version` every connector step carries, tripping
# `unknown_param: delete_record: unknown argument(s) 'step_variables', 'version'`
# on recompile (3 errors in scheduled-daily-recon etc.). The generic `connector`
# type has no whitelist, so resolving `Connectors` -> `connector` clears them.
#
# `delete_record`/`stop`/`end` are one-way authoring sugars -- they compile down
# to a `Connectors` step (cyops_utilities make_cyops_request DELETE / no_op) and
# have no distinct canonical type to recover on pull, so the round-trip contract
# for them is the authoring path, not the corpus round-trip
# (typed_args/steps/delete_record.py docstring). The codebase already agrees:
# `step_param_audit.TYPE_NAME_TO_RESOLVER["Connectors"] == "connector"` and its
# comment notes "pulled deletes map via Connectors above". Only this reverse
# map was the holdout. A pulled delete-shaped step still round-trips correctly
# as a `connector` step -- its args are already in the expanded canonical wire
# shape (params.iri/method=DELETE); only the friendly sugar is not recovered.
_EXTRA_CANONICAL_TO_SHORT: dict[str, str] = {
    "cybersponse.action": "start",
    "Connectors": "connector",
    # `ApprovalManualInput` (uuid a19333c2) is the DISTINCT canonical the
    # normalizer now stamps for an approval gate (`is_approval: true`), sharing
    # the `manual_input` dispatcher + InputBased render mode with plain
    # `ManualInput` (uuid fc04082a) -- see resolver/normalizers.py and
    # mi_output_catalog.APPROVAL_MI_STEP_TYPES. `SHORT_TYPE_TO_FSR` is 1:1
    # (`manual_input -> ManualInput`), so `_FSR_TO_SHORT` misses this variant
    # and a pulled approval step would fall through as raw
    # `type: ApprovalManualInput` (fails friendly revalidation). Map it back to
    # `manual_input`; the `is_approval: true` flag rides in `arguments`, so the
    # forward path re-derives the ApprovalManualInput step type on recompile --
    # a clean round-trip.
    "ApprovalManualInput": "manual_input",
    # `CyopsUtilites` (uuid 0109f35d) is the live-box canonical the FortiSOAR
    # editor emits for the built-in cyops_utilities no-op terminal (the editor's
    # "Utility No-Op" palette item; the wire-shape oracle pairs it with `stop`).
    # It is a DISTINCT canonical from `Connectors` (0bfed618), so without this
    # entry a pulled `CyopsUtilites` step falls through as `type: CyopsUtilites`
    # (raw) with its full re-derived envelope (version/name/operationTitle/...)
    # passed through verbatim -- boilerplate, and `type: CyopsUtilites` fails
    # friendly revalidation. Mapping it to `connector` collapses it into the
    # connector family the same way `stop`/`end`/`delete_record` already do
    # (they all compile to `Connectors` -> `connector` on pull), so it hits the
    # `connector` branch below and gets its envelope stripped (recompile re-adds
    # it via the `utilities`/connector re-add path -- normalizers.py:215-237).
    #
    # LIVE-VERIFIED on 8.0.0: the recompile emits canonical `Connectors`
    # (0bfed618), NOT the original `CyopsUtilites` (0109f35d). The two are
    # editor-distinct (the wire-shape oracle keeps them separate), so this is a
    # canonical step-type change on pull->push -- but it is runtime-equivalent,
    # proven on a live appliance two ways:
    #
    #   1. STRUCTURAL -- the two step types differ ONLY by a default arg seed:
    #        Connectors.arguments    == {"script": "/wf/workflow/tasks/connector"}
    #        CyopsUtilites.arguments == {"script": "/wf/workflow/tasks/connector",
    #                                    "arguments": {"connector": "cyops_utilities"}}
    #      Same dispatcher script, same `RunScript` parent. `CyopsUtilites` is a
    #      palette prefill seeding `connector: cyops_utilities` into a new step's
    #      form -- exactly as `CodeSnippet` seeds `code-snippet` and `SendMail`
    #      seeds `smtp`. It is a connector step against the utilities connector,
    #      not a distinct runtime path. A decompiled step always carries
    #      `connector: cyops_utilities` EXPLICITLY in its own arguments, so the
    #      seed is redundant and the swap changes nothing the engine reads.
    #   2. BEHAVIOURAL -- a controlled A/B: two playbooks identical but for the
    #      utilities step's canonical, byte-identical arguments, both pushed and
    #      triggered. Both reached `status=finished` with the utilities step
    #      itself `status=finished` under BOTH canonicals.
    #
    # Rare in the corpus (~1 step), so the blast radius was small either way.
    "CyopsUtilites": "connector",
}
_FSR_TO_SHORT.update(_EXTRA_CANONICAL_TO_SHORT)

# Pure editor-only UI-state keys the FSR designer auto-adds to a step's
# `arguments:` but which carry NO runtime meaning: `__recommend` (the schema-
# derived field-name suggestions the form shows) and `_showJson` (the JSON-vs-
# form toggle). The wire oracle lists both in `EDITOR_ONLY_KEYS` ("never emit --
# editor-only or layout noise"); no compiler branch reads them and no ruleset
# requires them (`rulesets/_shared.py` gates only `operation`, noting these two
# are "auto-added by the FSR designer to both step types"). On pull they ride
# through the record-write whitelist verbatim as boilerplate (~2 lines/step
# across the record-write corpus). Strip them so a pulled step surfaces only the
# load-bearing wire; recompile never re-adds them, so decompile->recompile stays
# idempotent once the library is regenerated. NOT stripped: keys a branch DOES
# consume to derive a friendly field (`displayConditions`/`singleRecordExecution`/
# `noRecordExecution` -> start trigger; `__triggerLimit` -> api_endpoint).
_EDITOR_NOISE_KEYS: tuple[str, ...] = ("__recommend", "_showJson")

# NOTE: `RemotePlaybookReference` (Trigger Tenant Playbook) needs NO overlay
# here. Unlike `Connectors` (a many-to-one forward collision: connector/stop/
# end/delete_record/utilities all compile TO `Connectors`, so the last-wins
# reverse comprehension mislabels every plain connector step), `RemotePlaybookReference`
# is a clean 1:1 mapping -- only `trigger_tenant_playbook` compiles to it -- so
# `_FSR_TO_SHORT = {v: k for k, v in SHORT_TYPE_TO_FSR.items()}` already resolves
# it correctly, the same way `WorkflowReference -> workflow_reference` and
# `ManualTask -> create_task` resolve with no overlay. A pulled remote-reference
# step decompiles to `trigger_tenant_playbook` (not raw canonical) and recompiles
# losslessly.

# Canonical argument keys only an action-trigger (start + module ->
# cybersponse.action) carries. Used to scope the start-step minimification to
# action-triggers -- a plain `cybersponse.abstract_trigger` start has none of
# these, so it falls through to the generic `arguments:` pass-through.
_ACTION_TRIGGER_CANONICAL_MARKERS = frozenset({
    "noRecordExecution", "singleRecordExecution", "executeButtonText",
    "route", "__triggerLimit", "triggerOnSource",
})

# The default `step_variables` the api_endpoint normalizer setdefaults
# (`_normalize_api_endpoint_args`) to bind the inbound HTTP request body + query
# params at `vars.steps.<name>.input.params.{api_body,api_params}`. On decompile,
# drop it when it equals this default so a pulled api_endpoint step surfaces just
# `route` (+ non-default auth); recompile re-adds it via the same setdefault.
_API_ENDPOINT_DEFAULT_STEP_VARS = {
    "input": {
        "params": {
            "api_body": "{{vars.request.data}}",
            "api_params": "{{vars.request.params}}",
        },
    },
}


def _step_modules(out: dict) -> list[str]:
    """The module list a decompiled step is bound to, from its hoisted
    `module`/`modules` surface (set by the resources->module lift)."""
    if "modules" in out:
        m = out["modules"]
        return list(m) if isinstance(m, list) else [str(m)]
    if "module" in out:
        m = out["module"]
        return list(m) if isinstance(m, list) else [str(m)]
    return []


def decompile_to_yaml(fsr_json: dict[str, Any], db_path: Path) -> str:
    """Decompile FSR WorkflowCollection JSON into authored-style YAML.

    Single-source-of-truth for the YAML serialization shape -- the CLI
    pull/diff/decompile commands and the `generate_recipe` MCP tool
    both go through here so a recipe stored to the DB looks identical
    to a recipe pulled from a live FSR.
    """
    import yaml

    ir = decompile(fsr_json, db_path)
    # A read connection for catalog-gated envelope minimification: stripping
    # re-derived `name`/`operationTitle` only when they equal the catalog
    # default (see the `connector` branch in `_decompile_step`). Separate from
    # `decompile()`'s connection (which it closes after building the IR).
    # Direct `_decompile_step` calls (e.g. unit tests) pass db=None and the
    # catalog-gated strips fall through (safe).
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        playbooks = [
            {
                "name": pb.name,
                "description": pb.description or None,
                "tag": pb.tag or None,
                "is_active": pb.is_active,
                "trigger_step_id": pb.trigger_step_id,
                "parameters": list(pb.parameters) or None,
                "steps": [_decompile_step(s, pb_name=pb.name, db=conn) for s in pb.steps],
                "annotations": [
                    {
                        "id": a.id,
                        "kind": a.kind if a.kind != "note" else None,
                        "title": a.title if a.title != "Note" else None,
                        "body": a.body or None,
                        "contains": list(a.contains) or None,
                        "position": (
                            {"top": a.top, "left": a.left,
                             "height": a.height or None, "width": a.width}
                            if a.top is not None or a.left is not None
                            else None
                        ),
                        "collapsed": a.collapsed or None,
                    }
                    for a in pb.annotations
                ] or None,
            }
            for pb in ir.playbooks
        ]
    finally:
        conn.close()

    out = {
        "collection": ir.name,
        "description": ir.description,
        "visible": ir.visible,
        "playbooks": playbooks,
    }

    def _clean(o):
        if isinstance(o, dict):
            return {k: _clean(v) for k, v in o.items() if v is not None}
        if isinstance(o, list):
            return [_clean(x) for x in o]
        return o

    return yaml.safe_dump(_clean(out), sort_keys=False, allow_unicode=True)


# Phase G: hoist remaining step args to the step's top level (no `arguments:`
# wrapper). Strip wire-envelope keys that would collide with IR step fields:
# `name` (connector display label -- re-derived by the compiler from the
# connector catalog; the step's `name` is the canvas node name) and
# `description` (if already at step level as an IR field).
_STEP_IR_FIELD_NAMES = frozenset({
    "type", "name", "next", "branches", "unlabeled_next", "comment",
    "description", "for_each", "id",
})


def _hoist_args(out: dict, args: dict) -> None:
    """Merge `args` into `out` at step level, skipping IR-field collisions."""
    # `name` in args is the connector display label -- collides with step.name.
    # Preserve as `display_name:` if it differs from the step name (custom
    # label); strip if it matches (re-derived by the compiler from catalog).
    # Must run before the IR-field loop below, which would otherwise pop it.
    conn_label = args.pop("name", None)
    if conn_label is not None and conn_label != out.get("name"):
        args["display_name"] = conn_label
    # Phase G: workflow_reference stores child-playbook input params under a
    # nested `arguments` key. Flatten them to step level (the parser's
    # resolver re-separates envelope keys from child params on recompile).
    if "arguments" in args:
        child = args.pop("arguments")
        if isinstance(child, dict):
            for k, v in child.items():
                args.setdefault(k, v)
        # If it's a list (empty []), just drop it -- no child params.
    for k in list(args):
        if k in _STEP_IR_FIELD_NAMES and k in out:
            args.pop(k)
    out.update(args)


def _decompile_step(s, pb_name: str | None = None,
                     db: "sqlite3.Connection | None" = None) -> dict:
    """Emit a step in the canonical authoring surface:
    `name:` only (no `id:`); `conditions:` / `options:` / `vars:` hoisted
    to step level; legacy `arguments.{conditions,options,arg_list}` and
    `branches:` collapsed away.

    ``pb_name`` is the owning playbook's name, used only for the action-trigger
    (``start`` + ``module``) minimification: the normalizer defaults the trigger
    button label to the playbook name, so we emit ``button_label`` only when the
    persisted label differs. ``None`` (direct test callers) suppresses that
    default-suppression -- every distinct ``title`` is emitted."""

    out: dict = {"type": s.type, "name": s.name or s.id}
    args = dict(s.arguments) if isinstance(s.arguments, dict) else None
    branches_remaining = dict(s.branches)

    # Phase G: step args are emitted at the step's top level (no `arguments:`
    # wrapper). The envelope keys (when, module, etc.) are hoisted to `out`
    # first; the remaining args are merged via `out.update(args)` at the end
    # of each branch, skipping keys that collide with IR step fields.
    if isinstance(args, dict):
        for env_key in ("when", "ignore_errors", "do_until", "apply_async",
                        "agent", "agentId", "pickFromTenant", "step_variables",
                        "mock_result", "module", "modules"):
            if env_key in args:
                out[env_key] = args.pop(env_key)
        msg = args.get("message")
        if isinstance(msg, dict) and set(msg) == {"content"} \
                and isinstance(msg["content"], str):
            out["post_comment"] = args.pop("message")["content"]
        elif "message" in args:
            # Strip wire-internal fields from the message block (the live
            # box stamps parentstepid, stepId, etc. that the compiler rejects).
            msg_dict = args.pop("message")
            if isinstance(msg_dict, dict):
                for _wire_k in ("parentstepid", "stepId", "stepiri"):
                    msg_dict.pop(_wire_k, None)
            out["message"] = msg_dict

        for _noise_key in _EDITOR_NOISE_KEYS:
            args.pop(_noise_key, None)

    # Strip empty-string `timeout` -- the live box stamps `timeout: ""` as a
    # default; the compiler's typed-args model expects int and rejects "".
    # An empty timeout is always a no-op, so strip it unconditionally.
    # Also strip dict timeout (branch-resume variant {days, hours, minutes,
    # step_iri}) -- wire-internal routing data the box stamps on manual_input
    # steps; the typed-args model expects int, not dict.
    if isinstance(args, dict):
        tv = args.get("timeout")
        if tv == "" or isinstance(tv, dict):
            args.pop("timeout", None)

    # Strip empty-string values from connector `params:` for enum/select
    # and integer params. The live box stamps `param: ""` for unset values;
    # the compiler rejects them (enum: "" not in allowed, int: "" doesn't
    # coerce). These are always no-op defaults the box auto-fills at runtime.
    if isinstance(args, dict) and isinstance(args.get("params"), dict) and db is not None:
        params = args["params"]
        connector = args.get("connector")
        operation = args.get("operation")
        if isinstance(connector, str) and isinstance(operation, str):
            for p_name in list(params):
                if params[p_name] != "":
                    continue
                try:
                    row = db.execute(
                        "SELECT type FROM operation_params "
                        "WHERE connector_name=? AND op_name=? AND param_name=?",
                        (connector, operation, p_name),
                    ).fetchone()
                except Exception:
                    row = None
                if row and row[0] and row[0].lower() in (
                    "select", "multiselect", "integer", "intger",
                    "decimal", "numeric", "boolean", "checkbox",
                ):
                    params.pop(p_name)

    # Strip conditionally-hidden params: the live box stamps params whose
    # parent_param condition isn't met (e.g. task_timeout when track_task
    # is false). The compiler's visibility check would reject them; strip
    # them here so the pulled YAML recompiles cleanly.
    if isinstance(args, dict) and isinstance(args.get("params"), dict) and db is not None:
        params = args["params"]
        connector = args.get("connector")
        operation = args.get("operation")
        if isinstance(connector, str) and isinstance(operation, str):
            for p_name in list(params):
                try:
                    row = db.execute(
                        "SELECT parent_param_name, condition_value "
                        "FROM operation_params "
                        "WHERE connector_name=? AND op_name=? AND param_name=?",
                        (connector, operation, p_name),
                    ).fetchone()
                except Exception:
                    row = None
                if not row or not row[0]:
                    continue  # no parent → always visible
                parent, cond = row
                if parent is None:
                    continue  # top-level → always visible
                parent_val = params.get(parent)
                if parent_val is None or str(parent_val) != str(cond):
                    params.pop(p_name, None)

    # Action-trigger module binding (start + module -> cybersponse.action). The
    # parser hoists a friendly step-level `module:`/`modules:` into
    # `arguments.module(s)` and the normalizer rewrites `start` -> `cybersponse.action`
    # from it; the emitter then serializes that as `arguments.resources`. On the
    # reverse trip the live box hands back `resources` (the canonical wire shape)
    # with NO `module` key, so the hoist loop above misses it and `resources` stays
    # buried in `arguments:` -- recompile then sees no `module` and downgrades the
    # trigger to plain `cybersponse.abstract_trigger`, losing the Execute-menu
    # button identity. Lift `resources` back to a friendly `module:` (single) /
    # `modules:` (list) so the round-trip is non-lossy. `module` already set by the
    # universal hoist above wins (an authored `module:` is the source of truth).
    if s.type == "start" and isinstance(args, dict) and "resources" in args \
            and "module" not in out and "modules" not in out:
        resources = args.pop("resources")
        if isinstance(resources, list) and len(resources) == 1:
            out["module"] = resources[0]
        elif isinstance(resources, list):
            out["modules"] = list(resources)
        elif isinstance(resources, str):
            out["module"] = resources
    if isinstance(s.description, str) and s.description.strip():
        out["description"] = s.description

    if s.type == "start" and isinstance(args, dict) and (
            _ACTION_TRIGGER_CANONICAL_MARKERS & args.keys()):
        # Action-trigger minimification (start + module -> cybersponse.action,
        # the Execute-menu record trigger). The live box hands back ~11 raw
        # canonical arg keys; the forward normalizer `_normalize_record_action_args`
        # re-derives ALL of them via setdefault/direct assignment from a tiny set
        # of friendly inputs (module, button_label, requires_record, run_mode).
        # Reverse-translate to that minimal friendly surface so the step emits
        # ~4-6 lines instead of ~20-40, and round-trips cleanly.
        #
        # This is not just cosmetic: the canonical noRecordExecution /
        # singleRecordExecution flag pair does NOT round-trip on its own. The
        # normalizer OVERWRITES them from requires_record/run_mode, so a
        # canonical-only form (no friendly requires_record) re-derives them with
        # the default (requires_record=True) and drifts the JSON. The
        # requires_record=False case (e.g. scheduled-daily-recon) is a live
        # round-trip break without this reverse-translation.
        friendly: dict = {}
        # route: the Execute-menu button identity. ALWAYS preserve when present
        # -- dropping it regenerates a different uuid5 (normalizer lines 251-253),
        # breaking the round-trip gate and orphaning the live button on
        # pull->edit->push. Lives under arguments: (the parser hoist list does
        # not include route; a step-level route is silently dropped).
        if args.get("route") is not None:
            friendly["route"] = args["route"]
        # requires_record (default True) / run_mode (default per_record) -- reverse
        # the noRecordExecution/singleRecordExecution pair the normalizer writes
        # (normalizer lines 272-273). Emit only the non-default value.
        no_rec = bool(args.get("noRecordExecution", False))
        single_rec = bool(args.get("singleRecordExecution", True))
        if no_rec:
            friendly["requires_record"] = False
        elif not single_rec:
            friendly["run_mode"] = "once_for_all"
        # button_label: the persisted Trigger Button Label (FSR's `title`). The
        # normalizer defaults title to the playbook name (lines 215-217), so emit
        # only when it differs -- otherwise the YAML repeats the playbook name.
        title = args.get("title")
        if title and (pb_name is None or title != pb_name):
            friendly["button_label"] = title
        # Declared input variables. When empty, both inputVariables and the
        # step_variables the normalizer derives from it are defaults -- drop them
        # (the normalizer re-creates them). When non-empty, keep inputVariables
        # and the already-hoisted step_variables (it carries the per-var jinja refs).
        input_vars = args.get("inputVariables") or []
        if input_vars:
            friendly["inputVariables"] = input_vars
        else:
            out.pop("step_variables", None)
        # displayConditions: drop the per-module empty default the normalizer
        # setdefaults (lines 278-280); keep only a customized filter.
        dc = args.get("displayConditions")
        mods = _step_modules(out)
        default_dc = {m: {"sort": [], "limit": 30, "logic": "AND", "filters": []}
                      for m in mods}
        if dc and dc != default_dc:
            friendly["displayConditions"] = dc
        if friendly:
            out.update(friendly)
    elif s.type == "decision" and isinstance(args, dict):
        conds = args.pop("conditions", None) or []
        new_conds = []
        for c in conds:
            if not isinstance(c, dict):
                continue
            entry = {}
            label = c.get("option")
            if label is not None:
                entry["display"] = label
            if c.get("default"):
                entry["default"] = True
            cond = c.get("condition")
            if cond is not None and not c.get("default"):
                entry["when"] = cond
            tgt = branches_remaining.pop(label, None) if label else None
            if tgt is None and c.get("__resolved_next"):
                tgt = c.pop("__resolved_next")
            if tgt:
                entry["next"] = tgt
            new_conds.append(entry)
        if new_conds:
            out["conditions"] = new_conds
        if args:
            _hoist_args(out, args)
    elif s.type == "manual_input" and isinstance(args, dict):
        rmap = args.pop("response_mapping", None)
        opts: list = []
        if isinstance(rmap, dict):
            opts = rmap.get("options") or []
        new_opts = []
        for o in opts:
            if not isinstance(o, dict):
                continue
            entry = {}
            label = o.get("option")
            if label is not None:
                entry["display"] = label
            if o.get("primary"):
                entry["primary"] = True
            tgt = branches_remaining.pop(label, None) if label else None
            if tgt is None and o.get("__resolved_next"):
                tgt = o.pop("__resolved_next")
            if tgt:
                entry["next"] = tgt
            new_opts.append(entry)
        if new_opts:
            out["options"] = new_opts
        # Phase D1: reverse friendly `email:` / `assign_to:` forms.
        # The forward normalizer turns `email: {enabled, subject, recipients,
        # body, from}` into wire `email_notification: {enabled,
        # smtpParameters: [{to, subject, body, from}]}` and `assign_to:
        # {person|team|record_field}` into wire `owner_detail: {isAssigned,
        # assignedToPerson/assignedToTeam/assignedToRecord}`. Reverse so a
        # pulled step surfaces the friendly form. Skip the default unassigned
        # / disabled envelopes (recompile re-creates them via setdefault).
        en = args.pop("email_notification", None)
        if isinstance(en, dict):
            is_default = (
                en.get("enabled") is False
                and not en.get("smtpParameters")
            )
            if not is_default:
                email_out: dict[str, Any] = {}
                if "enabled" in en:
                    email_out["enabled"] = en["enabled"]
                params = en.get("smtpParameters") or []
                if params and isinstance(params[0], dict):
                    p = params[0]
                    if p.get("to") is not None:
                        email_out["recipients"] = p["to"]
                    for k in ("subject", "body", "from"):
                        if p.get(k) is not None:
                            email_out[k] = p[k]
                args["email"] = email_out
        od = args.pop("owner_detail", None)
        if isinstance(od, dict):
            is_default = (
                od.get("isAssigned") is False
                and not any(
                    od.get(k) for k in
                    ("assignedToPerson", "assignedToTeam", "assignedToRecord")
                )
            )
            if not is_default:
                assign_out: dict[str, Any] = {}
                if od.get("assignedToPerson"):
                    assign_out["person"] = od["assignedToPerson"]
                team = od.get("assignedToTeam")
                if isinstance(team, list) and team:
                    assign_out["team"] = team[0]
                elif isinstance(team, str) and team:
                    assign_out["team"] = team
                if od.get("assignedToRecord"):
                    assign_out["record_field"] = True
                if assign_out:
                    args["assign_to"] = assign_out
        if args:
            _hoist_args(out, args)
    elif s.type == "set_variable" and isinstance(args, dict):
        # Resolver flattens arg_list into the args dict; treat every key
        # as a variable assignment.
        if args:
            out["vars"] = args
    elif s.type == "connector" and isinstance(args, dict):
        # Connector-envelope minimification. Three envelope keys on a friendly
        # `connector` step are pure re-derived defaults the friendly authoring
        # surface never needs to spell:
        #   - `version`: the installed connector's version. The forward
        #     compiler re-stamps it from the connector catalog row
        #     (`connector_args.py::_resolve_connector_action_args`:
        #     `if "version" not in a and crow["version"]: a["version"]=...`),
        #     and an author never sets it, so it is ALWAYS a re-derived
        #     default -- strip it (recompile re-adds it from the same catalog
        #     row; round-trip stable warm AND cold).
        #   - `step_variables: []`: the empty default input-binding envelope
        #     (hoisted to step level above). A NON-empty `step_variables`
        #     (e.g. `{'openaiOutput': '{{...}}'}`) is a real per-step input
        #     binding the author declared, so keep those; drop only the empty
        #     default (`if "step_variables" not in a: a["step_variables"]=[]`
        #     in connector_args.py re-creates it).
        #   - `config: ""`: the "use the connector's default config" sentinel
        #     (`if "config" not in a: a["config"]=""` in connector_args.py). A
        #     real config UUID (a specific chosen configuration) is load-bearing
        #     -- keep it; drop only the empty default so the round-trip is
        #     byte-stable (an original step with no `config` would otherwise
        #     gain `config: ""` on the first recompile and drift).
        # This is the shared logic the delete_record fix relies on: with the
        # `Connectors -> connector` overlay above, pulled delete-shaped steps
        # arrive here as `connector` too, so this single branch retires
        # `fix_delete_record_mistype`'s envelope strip (the recipe becomes a
        # no-op). `name`/`operationTitle` (also re-derived from catalog rows --
        # `crow["label"]`/`orow["title"]`, connector_args.py:653-656) are
        # stripped ONLY when a catalog (the `db` connection threaded from
        # `decompile_to_yaml`) confirms the value equals the re-derived
        # default; an author-customized label is preserved. When `db` is None
        # (direct `_decompile_step` call / unwarmed catalog) they pass through
        # untouched -- safe, round-trip stable as-is. `connector`/`operation`/
        # `params` are load-bearing wire the author/source owns -- never touched.
        #
        # SCOPE: friendly `connector` only. The raw-canonical `CyopsUtilites`
        # step type (uuid 0109f35d, the built-in cyops_utilities no_op terminal)
        # is mapped to `connector` via `_EXTRA_CANONICAL_TO_SHORT` above, so a
        # pulled `CyopsUtilites` step arrives here as `type: connector` and its
        # envelope is stripped by this branch (recompile re-adds it via the
        # `utilities` re-add path, normalizers.py:215-237). That mapping is a
        # canonical step-type change on recompile (`CyopsUtilites` -> `Connectors`)
        # -- see the LIVE-VERIFY PENDING note on the overlay entry.
        args.pop("version", None)
        if out.get("step_variables") == []:
            out.pop("step_variables", None)
        if args.get("config") == "":
            args.pop("config", None)
        # Catalog-gated strip of the re-derived display labels `name`/
        # `operationTitle`. The forward path stamps them from catalog rows
        # only when absent (`if "name" not in a and crow["label"]` etc.), so
        # a value that matches the catalog default is provably re-derived and
        # safe to drop (recompile re-stamps it). A mismatch is an author
        # customization -- keep it. Skipped entirely without a catalog (db is
        # None on direct calls / unwarmed slim DB) -- round-trip stable as-is.
        if db is not None:
            _c = args.get("connector")
            _o = args.get("operation")
            if isinstance(_c, str):
                _crow = db.execute(
                    "SELECT label FROM connectors WHERE name = ?", (_c,)
                ).fetchone()
                if (_crow and _crow["label"]
                        and args.get("name") == _crow["label"]):
                    args.pop("name", None)
                if isinstance(_o, str):
                    _orow = db.execute(
                        "SELECT title FROM operations "
                        "WHERE connector_name = ? AND op_name = ?",
                        (_c, _o),
                    ).fetchone()
                    if (_orow and _orow["title"]
                            and args.get("operationTitle") == _orow["title"]):
                        args.pop("operationTitle", None)
        if args:
            _hoist_args(out, args)
    elif s.type == "api_endpoint" and isinstance(args, dict):
        # api_endpoint (Custom API Endpoint trigger) minimification. The forward
        # normalizer (`_normalize_api_endpoint_args`) setdefaults five
        # trigger-infra fields to the canonical shape FSR's designer emits, so
        # the minimal clean form -- a step like:
        # - name: Start
        # - type: api_endpoint
        # - arguments.route: lookup_ip
        # (kept flat: mypy 2.1.0's parser false-positives "Expected an indented
        # block" on a comment-only body carrying a deeply-indented YAML sketch.)
        # compiles to a fully-specified token-based trigger. On decompile, drop
        # those re-derived defaults so a pulled api_endpoint step surfaces just
        # `route` (+ non-default `authentication_methods`); recompile re-adds
        # them via the same setdefaults (round-trip stable). Drop ONLY when the
        # value equals the default -- an author who customized
        # `triggerOnSource: false` or set a non-token auth mode owns that value.
        # `step_variables` was already hoisted to `out` by the universal envelope
        # loop above, so drop the default there; the other four stay in `args`.
        if args.get("authentication_methods") == [""]:
            args.pop("authentication_methods", None)
        if args.get("triggerOnSource") is True:
            args.pop("triggerOnSource", None)
        if args.get("triggerOnReplicate") is False:
            args.pop("triggerOnReplicate", None)
        if args.get("__triggerLimit") is True:
            args.pop("__triggerLimit", None)
        if out.get("step_variables") == _API_ENDPOINT_DEFAULT_STEP_VARS:
            out.pop("step_variables", None)
        if args:
            _hoist_args(out, args)
    elif s.type == "code_snippet" and isinstance(args, dict):
        # code_snippet (CodeSnippet) minimification. The forward normalizer
        # (`_normalize_code_snippet_args` -> `expand_code_snippet`) expands the
        # friendly `code:` surface into the canonical connector-envelope shape:
        # connector=code-snippet, operation=python_inline_code_editor,
        # operationTitle="Execute Python Code", version, params.python_function,
        # config (UUID), step_variables=[]. On decompile, reverse to the
        # friendly `code:` surface, dropping the re-derived envelope keys
        # (recompile re-adds them via the same setdefaults/defaults -- round-
        # trip stable). `config: ""` (the default-config sentinel) is dropped;
        # a real config UUID is kept (can't reverse-resolve to the name without
        # the connector_configs catalog -- round-trip stable as a UUID, like the
        # connector branch's `operationTitle`). Only minimize when the canonical
        # `params.python_function` is present -- a hand-authored canonical step
        # without it falls through to the generic pass-through.
        params = args.get("params")
        if isinstance(params, dict) and "python_function" in params:
            args["code"] = params.pop("python_function")
            if not params:
                args.pop("params", None)
            for _env_k in ("connector", "operation", "operationTitle", "version"):
                args.pop(_env_k, None)
            if args.get("config") == "":
                args.pop("config", None)
            if out.get("step_variables") == []:
                out.pop("step_variables", None)
        if args:
            _hoist_args(out, args)
    elif s.type == "send_email" and isinstance(args, dict):
        # send_email minimification. The forward normalizer turns the friendly
        # `send_email` step into a `SendMail` connector-family call: it defaults
        # `connector: smtp` + `operation: send_email`, and `_resolve_connector_args`
        # auto-lifts the flat email fields into `params:` + stamps `version`/
        # `operationTitle` from the catalog (mirror of `code_snippet`). On
        # decompile, reverse to the friendly surface: unwrap `params` back to
        # flat email fields and drop the re-derived envelope keys (recompile
        # re-adds them via the same setdefaults -- round-trip stable). The smtp
        # connector's `send_email` op takes `body` natively, so there is NO
        # `content`<->`body` / `from_str`<->`from` rename (the dedicated-handler
        # path is gone). `config: ""` (default-config sentinel) is dropped; a
        # real config UUID is kept (can't reverse-resolve to a name without the
        # connector_configs catalog -- round-trip stable as a UUID). Only
        # minimize when the canonical `params` is present and this is the
        # smtp/send_email signature -- a hand-authored canonical step without
        # `params` falls through to the generic pass-through.
        params = args.get("params")
        if (
            isinstance(params, dict)
            and args.get("connector") == "smtp"
            and args.get("operation") == "send_email"
        ):
            for k, v in params.items():
                args.setdefault(k, v)
            args.pop("params", None)
            for _env_k in ("connector", "operation", "operationTitle", "version"):
                args.pop(_env_k, None)
            if args.get("config") == "":
                args.pop("config", None)
            if out.get("step_variables") == []:
                out.pop("step_variables", None)
        # Strip stale legacy `from_str` -- older smtp connectors used this
        # as a top-level argument; the current schema has `from` in params.
        # The real value lives in params.from (hoisted above); from_str is
        # always a stale leftover the compiler rejects as unknown.
        args.pop("from_str", None)
        if args:
            _hoist_args(out, args)
    elif s.type in ("create_record", "update_record") and isinstance(args, dict):
        # Phase A1: reverse the friendly record-CRUD surface. The forward
        # `expand_record_crud` rewrites friendly `module:` -> wire `collection`
        # (create) / `collectionType` (update), and friendly `record:` -> wire
        # `collection` (update). Reverse so a pulled step surfaces the friendly
        # keys (`module:` / `record:`) instead of the wire IRIs -- and so the
        # compiler's A1 rules (`module:` mandatory; `collection:` rejected on
        # update) accept the decompiled YAML on recompile. On update,
        # `collectionType:` (wire module IRI) -> `module:` and `collection:`
        # (wire record IRI) -> `record:`. On create, `collection:` (wire module
        # IRI) -> `module:`; `/api/3/upsert/<m>` -> `module: <m>` + `is_upsert:
        # true`; a non-`/api/3/` collection can't reverse to a module name and
        # passes through as `collection:` (the compiler still accepts it on
        # create as the canonical module IRI).
        if s.type == "update_record":
            ct = args.pop("collectionType", None)
            if isinstance(ct, str):
                args["module"] = ct[len("/api/3/"):] if ct.startswith("/api/3/") else ct
            rec = args.pop("collection", None)
            if rec is not None:
                args["record"] = rec
        else:  # create_record (InsertData)
            coll = args.pop("collection", None)
            if isinstance(coll, str):
                if coll.startswith("/api/3/upsert/"):
                    args["module"] = coll[len("/api/3/upsert/"):]
                    args["is_upsert"] = True
                elif coll.startswith("/api/3/"):
                    args["module"] = coll[len("/api/3/"):]
                else:
                    args["collection"] = coll
        # `resource:` is the wire key for the record payload -- emit the
        # friendly `fields:` alias instead. Both compile to the same wire
        # key, so recompile accepts either.
        if "resource" in args:
            args["fields"] = args.pop("resource")
        # Phase C1: strip wire-internal defaults from record-CRUD steps.
        # These are re-derived by the compiler on recompile, so emitting
        # them is pure noise the agent may copy.
        if args.get("fieldOperation") == []:
            args.pop("fieldOperation", None)
        if args.get("tagsOperation") == "Overwrite":
            args.pop("tagsOperation", None)
        if args.get("__recommend") == []:
            args.pop("__recommend", None)
        if args.get("_showJson") is False:
            args.pop("_showJson", None)
        if out.get("step_variables") == []:
            out.pop("step_variables", None)
        if args:
            _hoist_args(out, args)
    elif s.type == "find_record" and isinstance(args, dict):
        # Phase B1: reverse the friendly `filters:` form. The forward
        # normalizer builds the wire `query: {sort, limit, logic, filters:
        # [{type, field, value, operator, _operator}]}` envelope from flat
        # `filters:` / `limit:` / `logic:`. Reverse it so a pulled step
        # surfaces the friendly form, not the raw wire envelope.
        q = args.pop("query", None)
        if isinstance(q, dict):
            filters_out = []
            for f in q.get("filters") or []:
                if not isinstance(f, dict):
                    filters_out.append(f)
                    continue
                wf = {}
                wf["field"] = f.get("field")
                wf["value"] = f.get("value")
                op = f.get("operator", "eq")
                wf["operator"] = op
                # carry through any extra keys (e.g. __selectFields)
                for k, v in f.items():
                    if k not in ("type", "field", "value", "operator",
                                 "_operator"):
                        wf.setdefault(k, v)
                filters_out.append(wf)
            if filters_out:
                args["filters"] = filters_out
            else:
                # Empty filters -- keep the wire `query:` envelope so the
                # validator's required-`query` check passes on recompile.
                args["query"] = q
            limit = q.get("limit")
            if limit is not None and limit != 30:
                args["limit"] = limit
            logic = q.get("logic")
            if logic is not None and logic != "AND":
                args["logic"] = logic
        # Strip the wire-only `checkboxFields: false` the normalizer defaults
        if args.get("checkboxFields") is False:
            args.pop("checkboxFields", None)
        if args:
            _hoist_args(out, args)
    elif args:
        _hoist_args(out, args)

    # `for_each` is lifted OUT of `arguments:` when the IR is built from the
    # wire, so it must be put back on the step surface here or the loop is
    # simply gone. This is data loss with teeth: the widget saves the agent's
    # last ```yaml fence back OVER the open record, so a pull -> edit -> push of
    # a looping playbook silently turns "run this for every incident" into "run
    # it once". The parser accepts `for_each:` at step level, so emitting it
    # here round-trips.
    if getattr(s, "for_each", None):
        out["for_each"] = dict(s.for_each)

    if s.next:
        out["next"] = s.next
    # Any leftover branches (no matching condition/option) -- surface as
    # an explicit `branches:` so info isn't lost; the parser rejects this
    # shape so a user must rewrite by hand. Rare in practice.
    if branches_remaining:
        out["branches"] = branches_remaining
    if s.unlabeled_next:
        out["unlabeled_next"] = list(s.unlabeled_next)
    if s.comment:
        out["comment"] = s.comment
    return out


def _slugify(name: str, taken: set[str]) -> str:
    """Derive a step id from its name, collision-suffixed.

    The base rule MUST be the parser's `_slugify`, because these two have to
    agree: the decompiler writes `next: <slug>` into the YAML, and the parser
    re-derives each step's id from its `name:` when the author left `id:` off.
    If they disagree, the emitted reference points at an id no step will ever
    have and the playbook fails to recompile with UNKNOWN_NEXT_STEP.

    They disagreed. This function used to strip `[^a-z0-9_]+`, keeping `_` as
    an allowed character, so a name like "Create Domain Indicator _ Deduplicated"
    became `create_domain_indicator___deduplicated` (space, kept underscore,
    space) while the parser collapsed the whole run to a single `_`. Seven step
    names in the shipped-pack corpus hit it, breaking 42 references across the
    Threat Intel and indicator-dedup playbooks.

    Importing the parser's rule instead of re-spelling it is the point: a copy
    is what drifted. The collision suffixing stays here -- the decompiler must
    disambiguate silently, where the parser reports duplicate ids as an error.
    """
    from .parser import _slugify as _base_slugify

    s = _base_slugify(name or "step")
    base = s
    i = 2
    while s in taken:
        s = f"{base}_{i}"
        i += 1
    taken.add(s)
    return s


def decompile(fsr_json: dict[str, Any], db_path: Path) -> Collection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        type_by_uuid = {
            r["uuid"]: r["name"] for r in conn.execute(
                "SELECT uuid, name FROM step_types"
            )
        }
        # IRI → name for workflow priority (reverse of the resolver's lookup).
        priority_by_iri = {
            r["item_iri"]: r["item_value"] for r in conn.execute(
                "SELECT item_iri, item_value FROM picklists WHERE list_name=?",
                (PRIORITY_LIST_NAME,),
            )
        }
    finally:
        conn.close()

    if "data" not in fsr_json or not fsr_json["data"]:
        raise ValueError("not an FSR WorkflowCollection JSON (missing data[])")
    coll = as_record_list(fsr_json.get("data"), path="data")[0]

    playbooks: list[Playbook] = []
    for wf in as_record_list(coll.get("workflows"), path="collection.workflows"):
        playbooks.append(_decompile_workflow(wf, type_by_uuid, priority_by_iri))

    return Collection(
        name=coll.get("name", "") or "",
        description=coll.get("description", "") or "",
        visible=bool(coll.get("visible", True)),
        playbooks=playbooks,
    )


def _decompile_workflow(wf: dict[str, Any], type_by_uuid: dict[str, str],
                        priority_by_iri: dict[str, str] | None = None) -> Playbook:
    # Both wire shapes, coerced in ONE place (`compiler/wire.py`). A live
    # crudhub GET can key `steps`/`routes` by id where the export JSON lists
    # them; iterating the dict form yields strings, and every `s.get(...)`
    # below would raise. This path (pull / decompile) carried the same latent
    # defect the pre-write gate hit in 61a18c1 -- it just had not been pointed
    # at such a playbook yet.
    raw_steps = as_record_list(wf.get("steps"), path="workflow.steps")
    raw_routes = as_record_list(wf.get("routes"), path="workflow.routes")

    # Assign a stable id per step (slug of name)
    taken: set[str] = set()
    id_by_uuid: dict[str, str] = {}
    canonical_by_uuid: dict[str, str] = {}
    short_by_uuid: dict[str, str] = {}
    # Raw arguments per step uuid -- the trigger's `inputVariables` are read back
    # out of this to recover the playbook's declared parameters (see below).
    _step_args_by_uuid: dict[str, dict[str, Any]] = {}
    for s in raw_steps:
        u = s.get("uuid") or ""
        sid = _slugify(s.get("name", ""), taken)
        id_by_uuid[u] = sid
        if isinstance(s.get("arguments"), dict):
            _step_args_by_uuid[u] = s["arguments"]
        # `stepType` is an IRI string in export JSON, but a nested dict
        # when fetched via /api/3/workflows?$relationships=true. Handle both.
        st_field = s.get("stepType")
        if isinstance(st_field, dict):
            st_uuid = st_field.get("uuid", "")
            canonical = st_field.get("name") or type_by_uuid.get(st_uuid, "")
        elif isinstance(st_field, str):
            st_uuid = st_field.rsplit("/", 1)[-1]
            canonical = type_by_uuid.get(st_uuid, "")
        else:
            st_uuid = ""
            canonical = ""
        canonical_by_uuid[u] = canonical
        short_by_uuid[u] = _FSR_TO_SHORT.get(canonical, canonical)

    def _to_uuid(field):
        """Normalize an IRI string or expanded dict to a uuid."""
        if isinstance(field, dict):
            return field.get("uuid") or ""
        if isinstance(field, str):
            return field.rsplit("/", 1)[-1]
        return ""

    # Build adjacency (source uuid -> [(target uuid, label)])
    adj: dict[str, list[tuple[str, str | None]]] = {}
    for r in raw_routes:
        s_uuid = _to_uuid(r.get("sourceStep"))
        t_uuid = _to_uuid(r.get("targetStep"))
        if not s_uuid or not t_uuid:
            continue
        adj.setdefault(s_uuid, []).append((t_uuid, r.get("label")))

    steps_out: list[Step] = []
    for s in raw_steps:
        u = s.get("uuid") or ""
        sid = id_by_uuid[u]
        outs = adj.get(u, [])
        nxt: str | None = None
        branches: dict[str, str] = {}
        unlabeled: list[str] = []
        # A DECISION step never takes the linear-`next` shortcut, even with a
        # single unlabeled route out. `next:` means something different on a
        # decision: the parser warns and synthesizes an `Else` DEFAULT
        # condition for it, so the emitter writes a route LABELED "Else" where
        # the appliance had an unlabeled one. That silently rewrites the
        # routing graph -- the one thing the round-trip contract exists to
        # preserve -- and `unlabeled_next` already represents this exactly.
        #
        # Found by `probe_mapping_fidelity.py`, the single semantic diff in
        # 209 live collections. It survived because the five-fixture corpus
        # has no decision step with an unlabeled outgoing route.
        is_decision = short_by_uuid.get(u) == "decision"
        if len(outs) == 1 and not outs[0][1] and not is_decision:
            t_uuid, _ = outs[0]
            nxt = id_by_uuid.get(t_uuid)
        else:
            for t_uuid, label in outs:
                tgt_id = id_by_uuid.get(t_uuid)
                if not tgt_id:
                    continue
                if label:
                    branches[label] = tgt_id
                else:
                    unlabeled.append(tgt_id)

        # for_each lives inside arguments on the wire; lift it out into
        # its own IR field so authors see it as a step-level mapping.
        raw_args = dict(s.get("arguments") or {})
        fe_raw = raw_args.pop("for_each", None)
        for_each = dict(fe_raw) if isinstance(fe_raw, dict) and fe_raw else None

        # Resolve step_iri → step id in decision conditions and manual_input
        # options. The emitter stamps step_iri on each condition/option as a
        # direct UUID pointer to the target step (more reliable than the route
        # label, which is often None). Without this, branches lose their `next`
        # targets when routes are unlabeled -- steps become "unreachable from
        # the trigger" on recompile.
        for _key in ("conditions",):
            _list = raw_args.get(_key)
            if isinstance(_list, list):
                for _c in _list:
                    if isinstance(_c, dict) and _c.get("step_iri"):
                        _tu = _to_uuid(_c["step_iri"])
                        _ti = id_by_uuid.get(_tu)
                        if _ti:
                            _c["__resolved_next"] = _ti
        _rmap = raw_args.get("response_mapping")
        if isinstance(_rmap, dict):
            _opts = _rmap.get("options")
            if isinstance(_opts, list):
                for _o in _opts:
                    if isinstance(_o, dict) and _o.get("step_iri"):
                        _tu = _to_uuid(_o["step_iri"])
                        _ti = id_by_uuid.get(_tu)
                        if _ti:
                            _o["__resolved_next"] = _ti

        steps_out.append(Step(
            id=sid,
            type=short_by_uuid.get(u, "") or "unknown",
            name=s.get("name", "") or sid,
            description=s.get("description") or "",
            arguments=raw_args,
            next=nxt,
            branches=branches,
            unlabeled_next=unlabeled,
            step_type_uuid=(
                s["stepType"].get("uuid") if isinstance(s.get("stepType"), dict)
                else (s.get("stepType") or "").rsplit("/", 1)[-1] or None
            ),
            step_type_name=canonical_by_uuid.get(u),
            for_each=for_each,
        ))

    trigger_uuid = _to_uuid(wf.get("triggerStep"))
    trigger_id = id_by_uuid.get(trigger_uuid)

    # Decompile workflow_groups: blocks own steps via WorkflowStep.group,
    # notes are positional (no FK link) and may fold into step.comment.
    annotations: list[Annotation] = []
    ann_id_taken: set[str] = set()

    # Block-owned steps: index by group uuid → list of step ids.
    block_uuid_to_step_ids: dict[str, list[str]] = {}
    for s in raw_steps:
        gu = _to_uuid(s.get("group")) if s.get("group") else ""
        if gu:
            sid = id_by_uuid.get(s.get("uuid", ""), "")
            if sid:
                block_uuid_to_step_ids.setdefault(gu, []).append(sid)

    # Step canvas positions (id -> (top, left)) for the note→step heuristic.
    step_pos: dict[str, tuple[int, int]] = {}
    for s in raw_steps:
        sid = id_by_uuid.get(s.get("uuid", ""), "")
        if not sid:
            continue
        try:
            step_pos[sid] = (int(s.get("top") or 0), int(s.get("left") or 0))
        except (TypeError, ValueError):
            pass

    step_by_id = {st.id: st for st in steps_out}
    # Coerced, not iterated bare: `groups` is a nested record container like
    # `steps`/`routes`, and every `g.get(...)` below would raise on a member
    # that is not a dict. Same pattern as 61a18c1; there is no reason for this
    # one to be the exception.
    for g in as_record_list(wf.get("groups"), path="workflow.groups"):
        gtype = g.get("type") or "note"
        gtitle = g.get("name") or "Note"
        gbody = g.get("description") or ""
        guuid = g.get("uuid") or ""
        try:
            top_v = int(g.get("top") or 0)
            left_v = int(g.get("left") or 0)
            h_v = int(g.get("height") or 0)
            w_v = int(g.get("width") or 0)
        except (TypeError, ValueError):
            top_v = left_v = 0
            h_v = w_v = 0

        if gtype == "block":
            contains = block_uuid_to_step_ids.get(guuid, [])
        else:
            contains = []

        # Auto-comment fold for notes -- title pattern is
        # "<PREFIX>: <step display name>" where PREFIX ∈
        # {Note, TODO, FIX, NOTE, WARN, HACK, XXX}. The prefix carries
        # the comment category and is preserved in the body via the
        # original first word, so we don't need to round-trip the
        # prefix separately. Legacy "Note" (no colon) → positional.
        _AUTO_PREFIXES = ("Note", "TODO", "FIX", "NOTE", "WARN", "HACK", "XXX")
        if gtype == "note":
            target_name = None
            for p in _AUTO_PREFIXES:
                if gtitle.startswith(p + ": "):
                    target_name = gtitle[len(p) + 2:]
                    break
            if target_name:
                matches = [sid for sid, st in step_by_id.items()
                           if (st.name or sid) == target_name
                           and st.comment is None]
                if len(matches) == 1:
                    step_by_id[matches[0]].comment = gbody
                    continue
                # Ambiguous or no match: keep as a regular note rather
                # than dropping the body.
        if gtype == "note" and gtitle == "Note":
            candidates = [
                sid for sid, (st_top, st_left) in step_pos.items()
                if abs(st_top - top_v) <= 50 and left_v > st_left + 100
                and step_by_id.get(sid) and step_by_id[sid].comment is None
            ]
            if len(candidates) == 1:
                step_by_id[candidates[0]].comment = gbody
                continue
            if len(candidates) > 1:
                candidates.sort(key=lambda sid: left_v - step_pos[sid][1])
                step_by_id[candidates[0]].comment = gbody
                continue

        aid = _slugify(gtitle if gtitle != "Note" else g.get("type", "note"),
                       ann_id_taken)
        annotations.append(Annotation(
            id=aid,
            kind=gtype,
            title=gtitle,
            body=gbody,
            top=top_v or None,
            left=left_v or None,
            height=h_v,
            width=w_v or 300,
            collapsed=bool(g.get("isCollapsed", False)),
            hide_in_logs=bool(g.get("hideInLogs", gtype == "note")),
            contains=contains,
        ))

    # FSR is inconsistent here: parameters is either `{}` (empty) or a
    # list of parameter names. Normalize to a list of strings.
    raw_params = wf.get("parameters") or []
    if isinstance(raw_params, list):
        params = [p for p in raw_params if isinstance(p, str)]
    else:
        params = []

    # …but that field is only HALF the declaration. The manual-trigger form is
    # built from the TRIGGER step's `arguments.inputVariables[]`, and on real
    # appliance content the two sources disagree: some playbooks have an empty
    # top-level `parameters` with everything declared on the trigger, and some
    # have a non-empty one that still OMITS parameters the trigger declares.
    # Reading only the top-level field therefore lost declarations, and a
    # pulled playbook came back referencing `vars.input.params.X` with nothing
    # declaring X -- the compiler (correctly) rejecting its own decompiler's
    # output.
    #
    # So union the two rather than treating either as authoritative. Same
    # silent-data-loss class as the dropped `for_each`, and destructive the
    # same way: the widget saves the agent's last fence back OVER the record,
    # so pull -> one-field edit -> save would strip the playbook's input form.
    # Found by pulling 400 stock playbooks from a live appliance, where this
    # single bug accounted for 42 of 122 hard compile failures.
    _seen_p = set(params)
    trigger_args = _step_args_by_uuid.get(trigger_uuid) or {}
    for iv in (trigger_args.get("inputVariables") or []):
        if not isinstance(iv, dict):
            continue
        pname = iv.get("name")
        if isinstance(pname, str) and pname and pname not in _seen_p:
            _seen_p.add(pname)
            params.append(pname)

    # priority IRI → name via the live-synced picklists map.
    raw_priority = wf.get("priority")
    priority = (priority_by_iri or {}).get(raw_priority) if isinstance(raw_priority, str) else None

    return Playbook(
        name=wf.get("name", "") or "",
        description=wf.get("description", "") or "",
        tag=wf.get("tag", "") or "",
        is_active=bool(wf.get("isActive", False)),
        priority=priority,
        priority_iri=raw_priority if isinstance(raw_priority, str) else None,
        trigger="start",
        trigger_step_id=trigger_id,
        parameters=params,
        steps=steps_out,
        annotations=annotations,
    )
