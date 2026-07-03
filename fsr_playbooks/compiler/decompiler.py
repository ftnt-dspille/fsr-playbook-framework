"""FSR WorkflowCollection JSON -> IR.

The inverse of `emitter.emit`. Used for the round-trip acceptance test
and (later) for "import an existing playbook into the YAML world."

Lossiness: FSR JSON carries fields the IR doesn't model (lastModifyDate,
deletedAt, layout coords, recordTags, ownership). Those are dropped
on the way in; the IR is the human-meaningful subset.
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any

from .ir import PRIORITY_LIST_NAME, Annotation, Collection, Playbook, Step
from .resolver import SHORT_TYPE_TO_FSR

_FSR_TO_SHORT = {v: k for k, v in SHORT_TYPE_TO_FSR.items()}

# Canonical FSR step-type names that share a friendly short name with another
# canonical, so they can't live in the 1:1 SHORT_TYPE_TO_FSR (which is keyed by
# friendly name for the forward compile direction). Overlay them here so the
# decompiler resolves them instead of falling through as raw canonicals.
#
# `cybersponse.action` (uuid f414d039, ManualStart / Execute-menu ACTION_TRIGGER)
# is the record-listing twin of `cybersponse.abstract_trigger` — both compile
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
# The codebase already agrees `cybersponse.action` is a `start` trigger —
# `step_param_audit.TYPE_NAME_TO_RESOLVER` and
# `tests/wire_shape_oracle._TITLE_TO_TYPE` both list it; only this reverse map
# was missing it.
#
# NOTE: the `cybersponse.pre_*` canonicals (pre_create/pre_update/pre_delete)
# exist in the step_types table but are deliberately NOT mapped here. They have
# no `start_on_*` twin — `start_on_create/update/delete` recompile to the
# `post_*` triggers, so aliasing `pre_create -> start_on_create` would silently
# flip a pre-event trigger to post-event. Those decompile as raw canonicals
# until a dedicated friendly short type exists for them.
#
# `Connectors` (uuid 0bfed618, the generic connector step) is a many-to-one
# forward collision: friendly `connector`, `stop`, `end`, AND `delete_record`
# all compile TO canonical `Connectors` (resolver/_constants.py).
# `_FSR_TO_SHORT = {v: k for k, v in SHORT_TYPE_TO_FSR.items()}` is a last-wins
# comprehension, so without this overlay it resolves `Connectors` to
# `delete_record` (the last entry) — mislabeling EVERY plain connector step on
# pull as `delete_record`. That mislabel is a live round-trip break:
# `delete_record` carries a strict argument whitelist (`_normalize_delete_record_args`
# `_FRIENDLY`/`_CANONICAL`) that rejects the box-injected envelope keys
# `step_variables`/`version` every connector step carries, tripping
# `unknown_param: delete_record: unknown argument(s) 'step_variables', 'version'`
# on recompile (3 errors in scheduled-daily-recon etc.). The generic `connector`
# type has no whitelist, so resolving `Connectors` -> `connector` clears them.
#
# `delete_record`/`stop`/`end` are one-way authoring sugars — they compile down
# to a `Connectors` step (cyops_utilities make_cyops_request DELETE / no_op) and
# have no distinct canonical type to recover on pull, so the round-trip contract
# for them is the authoring path, not the corpus round-trip
# (typed_args/steps/delete_record.py docstring). The codebase already agrees:
# `step_param_audit.TYPE_NAME_TO_RESOLVER["Connectors"] == "connector"` and its
# comment notes "pulled deletes map via Connectors above". Only this reverse
# map was the holdout. A pulled delete-shaped step still round-trips correctly
# as a `connector` step — its args are already in the expanded canonical wire
# shape (params.iri/method=DELETE); only the friendly sugar is not recovered.
_EXTRA_CANONICAL_TO_SHORT: dict[str, str] = {
    "cybersponse.action": "start",
    "Connectors": "connector",
}
_FSR_TO_SHORT.update(_EXTRA_CANONICAL_TO_SHORT)

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
# action-triggers — a plain `cybersponse.abstract_trigger` start has none of
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

    Single-source-of-truth for the YAML serialization shape — the CLI
    pull/diff/decompile commands and the `generate_recipe` MCP tool
    both go through here so a recipe stored to the DB looks identical
    to a recipe pulled from a live FSR.
    """
    import yaml

    ir = decompile(fsr_json, db_path)
    out = {
        "collection": ir.name,
        "description": ir.description,
        "visible": ir.visible,
        "playbooks": [
            {
                "name": pb.name,
                "description": pb.description or None,
                "tag": pb.tag or None,
                "is_active": pb.is_active,
                "trigger_step_id": pb.trigger_step_id,
                "parameters": list(pb.parameters) or None,
                "steps": [_decompile_step(s, pb_name=pb.name) for s in pb.steps],
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
        ],
    }

    def _clean(o):
        if isinstance(o, dict):
            return {k: _clean(v) for k, v in o.items() if v is not None}
        if isinstance(o, list):
            return [_clean(x) for x in o]
        return o

    return yaml.safe_dump(_clean(out), sort_keys=False, allow_unicode=True)


def _decompile_step(s, pb_name: str | None = None) -> dict:
    """Emit a step in the canonical authoring surface:
    `name:` only (no `id:`); `conditions:` / `options:` / `vars:` hoisted
    to step level; legacy `arguments.{conditions,options,arg_list}` and
    `branches:` collapsed away.

    ``pb_name`` is the owning playbook's name, used only for the action-trigger
    (``start`` + ``module``) minimification: the normalizer defaults the trigger
    button label to the playbook name, so we emit ``button_label`` only when the
    persisted label differs. ``None`` (direct test callers) suppresses that
    default-suppression — every distinct ``title`` is emitted."""

    out: dict = {"type": s.type, "name": s.name or s.id}
    args = dict(s.arguments) if isinstance(s.arguments, dict) else None
    branches_remaining = dict(s.branches)

    # Universal step envelope (Phase 4): the parser hoists these wire keys
    # out of `arguments:` to the step surface, so on pull we reverse that —
    # otherwise a connector's `when`/`do_until`/`agent` round-trips back as
    # raw `arguments.when`, which the editor never compiles to. Lift them
    # back to the step top level verbatim (canonical spelling, lossless).
    if isinstance(args, dict):
        for env_key in ("when", "ignore_errors", "do_until", "apply_async",
                        "agent", "agentId", "pickFromTenant", "step_variables",
                        "mock_result", "module", "modules"):
            if env_key in args:
                out[env_key] = args.pop(env_key)
        # Fold a pure `message: {content: "<text>"}` back to the friendlier
        # `post_comment: "<text>"` sugar (parser accepts both). Keep the full
        # `message:` block when it carries more than a plain content string.
        msg = args.get("message")
        if isinstance(msg, dict) and set(msg) == {"content"} \
                and isinstance(msg["content"], str):
            out["post_comment"] = args.pop("message")["content"]
        elif "message" in args:
            out["message"] = args.pop("message")

    # Action-trigger module binding (start + module -> cybersponse.action). The
    # parser hoists a friendly step-level `module:`/`modules:` into
    # `arguments.module(s)` and the normalizer rewrites `start` -> `cybersponse.action`
    # from it; the emitter then serializes that as `arguments.resources`. On the
    # reverse trip the live box hands back `resources` (the canonical wire shape)
    # with NO `module` key, so the hoist loop above misses it and `resources` stays
    # buried in `arguments:` — recompile then sees no `module` and downgrades the
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
        # — dropping it regenerates a different uuid5 (normalizer lines 251-253),
        # breaking the round-trip gate and orphaning the live button on
        # pull->edit->push. Lives under arguments: (the parser hoist list does
        # not include route; a step-level route is silently dropped).
        if args.get("route") is not None:
            friendly["route"] = args["route"]
        # requires_record (default True) / run_mode (default per_record) — reverse
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
        # only when it differs — otherwise the YAML repeats the playbook name.
        title = args.get("title")
        if title and (pb_name is None or title != pb_name):
            friendly["button_label"] = title
        # Declared input variables. When empty, both inputVariables and the
        # step_variables the normalizer derives from it are defaults — drop them
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
            out["arguments"] = friendly
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
            if tgt:
                entry["next"] = tgt
            new_conds.append(entry)
        if new_conds:
            out["conditions"] = new_conds
        if args:
            out["arguments"] = args
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
            if tgt:
                entry["next"] = tgt
            new_opts.append(entry)
        if new_opts:
            out["options"] = new_opts
        if args:
            out["arguments"] = args
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
        #     default — strip it (recompile re-adds it from the same catalog
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
        #     — keep it; drop only the empty default so the round-trip is
        #     byte-stable (an original step with no `config` would otherwise
        #     gain `config: ""` on the first recompile and drift).
        # This is the shared logic the delete_record fix relies on: with the
        # `Connectors -> connector` overlay above, pulled delete-shaped steps
        # arrive here as `connector` too, so this single branch retires
        # `fix_delete_record_mistype`'s envelope strip (the recipe becomes a
        # no-op). NOT stripped here: `name`/`operationTitle` (also re-derived
        # from catalog rows) — the decompiler has no connector catalog at hand
        # to tell a re-derived default label from an author-customized one, so
        # they pass through untouched (a follow-up could strip them given the
        # catalog). `connector`/`operation`/`params` are load-bearing wire the
        # author/source owns — never touched.
        #
        # SCOPE: friendly `connector` only. The raw-canonical `CyopsUtilites`
        # step type (uuid 0109f35d, the built-in cyops_utilities no_op terminal)
        # is deliberately NOT touched here: the compiler's connector re-add path
        # (`normalizers.py:157`) only covers `connector`/`stop`/`end`/
        # `delete_record`, NOT `CyopsUtilites`, so stripping `version` from a
        # CyopsUtilites step would change the wire (no re-add) — an unverified
        # runtime change. CyopsUtilites steps carry no `config` anyway (the
        # built-in utility needs none), and they're rare (1 in the tutorial
        # corpus), so leaving their envelope verbatim is safe and needs no live
        # verification. `scratch/promote_library.py::fix_delete_record_mistype`
        # never touched them either, so excluding them doesn't block retiring it.
        args.pop("version", None)
        if out.get("step_variables") == []:
            out.pop("step_variables", None)
        if args.get("config") == "":
            args.pop("config", None)
        if args:
            out["arguments"] = args
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
            out["arguments"] = args
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
            out["arguments"] = args
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
        if args:
            out["arguments"] = args
    elif args:
        out["arguments"] = args

    if s.next:
        out["next"] = s.next
    # Any leftover branches (no matching condition/option) — surface as
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
    s = re.sub(r"[^a-z0-9_]+", "_", (name or "step").lower()).strip("_") or "step"
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
    coll = fsr_json["data"][0]

    playbooks: list[Playbook] = []
    for wf in coll.get("workflows", []):
        playbooks.append(_decompile_workflow(wf, type_by_uuid, priority_by_iri))

    return Collection(
        name=coll.get("name", "") or "",
        description=coll.get("description", "") or "",
        visible=bool(coll.get("visible", True)),
        playbooks=playbooks,
    )


def _decompile_workflow(wf: dict[str, Any], type_by_uuid: dict[str, str],
                        priority_by_iri: dict[str, str] | None = None) -> Playbook:
    raw_steps = wf.get("steps", []) or []
    raw_routes = wf.get("routes", []) or []

    # Assign a stable id per step (slug of name)
    taken: set[str] = set()
    id_by_uuid: dict[str, str] = {}
    canonical_by_uuid: dict[str, str] = {}
    short_by_uuid: dict[str, str] = {}
    for s in raw_steps:
        u = s.get("uuid") or ""
        sid = _slugify(s.get("name", ""), taken)
        id_by_uuid[u] = sid
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
        if len(outs) == 1 and not outs[0][1]:
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
    for g in wf.get("groups", []) or []:
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

        # Auto-comment fold for notes — title pattern is
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
