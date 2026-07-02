"""Phase 4 — decompiler fidelity for the universal step envelope.

On pull (FSR JSON → friendly YAML) the decompiler must surface the envelope
wire keys back out of `arguments:` to the step surface — otherwise a
connector's `when`/`do_until`/`agent` round-trips as raw `arguments.when`,
a shape the editor never compiles. Also covers per-step `description`
round-trip and the `message: {content}` → `post_comment:` fold.
"""
from __future__ import annotations

import yaml

from fsr_playbooks.compiler import compile_yaml
from fsr_playbooks.compiler.decompiler import decompile_to_yaml, _decompile_step
from fsr_playbooks.compiler.ir import Step
from fsr_playbooks._db import PACKAGED_SLIM_DB


def _roundtrip_steps(yaml_text: str):
    """Compile → decompile → parse, returning {step name: step dict}."""
    res = compile_yaml(yaml_text, PACKAGED_SLIM_DB)
    assert res.ok, [e.message for e in res.errors if e.severity != "warning"]
    doc = yaml.safe_load(decompile_to_yaml(res.fsr_json, PACKAGED_SLIM_DB))
    steps = doc["playbooks"][0]["steps"]
    return {s["name"]: s for s in steps}


def test_envelope_keys_hoisted_back_to_step_level():
    by_name = _roundtrip_steps(
        """
collection: T
playbooks:
  - name: PB
    steps:
      - name: Start
        type: start_on_create
        module: alerts
        next: Set
      - name: Set
        type: set_variable
        when: "{{ vars.score > 70 }}"
        ignore_errors: true
        vars:
          foo: bar
"""
    )
    s = by_name["Set"]
    assert s["when"] == "{{ vars.score > 70 }}"
    assert s["ignore_errors"] is True
    # The envelope keys must NOT linger inside arguments.
    assert "when" not in (s.get("arguments") or {})
    assert "ignore_errors" not in (s.get("arguments") or {})


def test_step_description_round_trips():
    by_name = _roundtrip_steps(
        """
collection: T
playbooks:
  - name: PB
    steps:
      - name: Start
        type: start_on_create
        module: alerts
        next: Set
      - name: Set
        type: set_variable
        description: "explains this step"
        vars:
          foo: bar
"""
    )
    assert by_name["Set"]["description"] == "explains this step"


def test_message_block_lifted_out_of_arguments():
    by_name = _roundtrip_steps(
        """
collection: T
playbooks:
  - name: PB
    steps:
      - name: Start
        type: start_on_create
        module: alerts
        next: Comment
      - name: Comment
        type: set_variable
        post_comment: "auto note"
        vars:
          foo: bar
"""
    )
    s = by_name["Comment"]
    # message surfaces at the step level, never buried in arguments.
    assert "message" not in (s.get("arguments") or {})
    assert "message" in s or "post_comment" in s


def test_pure_message_content_folds_to_post_comment():
    """A bare `message: {content: str}` (e.g. from a hand-authored pull)
    reverses to the friendlier `post_comment:` sugar."""
    step = Step(id="c", type="set_variable", name="Comment",
                arguments={"message": {"content": "hello"}, "foo": "bar"})
    out = _decompile_step(step)
    assert out["post_comment"] == "hello"
    assert "message" not in out
    assert "message" not in (out.get("arguments") or {})


def test_enriched_message_kept_as_block():
    """An enriched message (more than `content`) stays a full block — folding
    to post_comment would drop tags/type/thread."""
    step = Step(id="c", type="set_variable", name="Comment",
                arguments={"message": {"content": "<p>hi</p>", "tags": [],
                                       "thread": False}})
    out = _decompile_step(step)
    assert "post_comment" not in out
    assert out["message"]["content"] == "<p>hi</p>"


def test_action_trigger_decompiles_to_start():
    """A `start` step bound to a module compiles to the `cybersponse.action`
    canonical (ManualStart / Execute-menu trigger, uuid f414d039). The live box
    hands that canonical name back on pull, so the decompiler's reverse map must
    resolve it to friendly `start` — not leak the raw canonical as the step's
    `type`, which fails recompile validation as `no_trigger`.

    Guards the `_EXTRA_CANONICAL_TO_SHORT` overlay in decompiler.py. Round-trip
    is non-lossy: the normalizer re-derives `cybersponse.action` from the
    `module` argument on recompile."""
    by_name = _roundtrip_steps(
        """
collection: T
playbooks:
  - name: PB
    steps:
      - name: Triage
        type: start
        module: alerts
        arguments:
          button_label: Triage Alert
          requires_record: true
          run_mode: per_record
        next: Set
      - name: Set
        type: set_variable
        vars:
          y: 1
"""
    )
    assert by_name["Triage"]["type"] == "start", (
        f"action trigger should decompile to friendly 'start', "
        f"got {by_name['Triage']['type']!r} (overlay missing cybersponse.action?)"
    )


# UUIDs from the step_types table (resolved by the catalog at decompile time).
_ABSTRACT_TRIGGER = "b348f017-9a94-471f-87f8-ce88b6a7ad62"  # cybersponse.abstract_trigger
_ACTION_TRIGGER = "f414d039-bb0d-4e59-9c39-a8f1e880b18a"  # cybersponse.action
_SET_VARIABLE = "04d0cf46-b6a8-42c4-8683-60a7eaa69e8f"  # SetVariable (non-trigger)


def _step_iri(uuid: str, idx: int = 1) -> str:
    return f"/api/3/workflow_steps/{uuid[:-1]}{idx}"


def _action_trigger_json(resources, step_name="Triage"):
    """Build a minimal WorkflowCollection JSON whose trigger step is a
    `cybersponse.action` (Execute-menu) step bound to `resources` — the wire
    shape a live box hands back on pull. Carries NO `module` key; the module
    list lives only in `arguments.resources`."""
    return {
        "data": [{
            "name": "T",
            "workflows": [{
                "name": "PB",
                "triggerStep": _step_iri(_ACTION_TRIGGER, 7),
                "steps": [
                    {
                        "name": step_name,
                        "uuid": _step_iri(_ACTION_TRIGGER, 7).rsplit("/", 1)[1],
                        "stepType": f"/api/3/workflow_step_types/{_ACTION_TRIGGER}",
                        "arguments": {
                            "resources": list(resources),
                            "executeButtonText": "Execute",
                            "triggerOnSource": True,
                            "singleRecordExecution": True,
                        },
                        "nextStep": "End",
                    },
                    {
                        "name": "End",
                        "uuid": _step_iri(_SET_VARIABLE, 8).rsplit("/", 1)[1],
                        # SetVariable — a non-trigger terminal the slim DB models.
                        "stepType": f"/api/3/workflow_step_types/{_SET_VARIABLE}",
                        "arguments": {"vars": {"y": 1}},
                    },
                ],
            }],
        }]
    }


def test_action_trigger_resources_lifted_to_module_on_pull():
    """A live `cybersponse.action` step serializes its module list as
    `arguments.resources` (the canonical wire shape) — there is no `module` key.
    The decompiler must lift `resources` back to a friendly step-level
    `module:` (single) / `modules:` (list) so recompile re-derives
    `cybersponse.action` via the normalizer's `start + module` rewrite.

    Without this lift the round-trip is lossy: recompile sees no `module` and
    downgrades the trigger to plain `cybersponse.abstract_trigger` (designer
    Run button only), silently dropping the record Execute-menu button."""
    from fsr_playbooks.compiler import compile_yaml

    # Single module -> friendly `module:`.
    doc = yaml.safe_load(decompile_to_yaml(
        _action_trigger_json(["alerts"]), PACKAGED_SLIM_DB))
    triage = doc["playbooks"][0]["steps"][0]
    assert triage["type"] == "start", (
        f"action trigger must decompile to friendly 'start', got {triage['type']!r}")
    assert triage.get("module") == "alerts", (
        f"single-module action trigger should lift to `module: alerts`, "
        f"got module={triage.get('module')!r} (resources left in arguments?)")
    assert "resources" not in (triage.get("arguments") or {}), (
        "resources must be lifted out of arguments, not duplicated")

    # Multiple modules -> friendly `modules: [...]`.
    doc = yaml.safe_load(decompile_to_yaml(
        _action_trigger_json(["alerts", "incidents"]), PACKAGED_SLIM_DB))
    triage = doc["playbooks"][0]["steps"][0]
    assert triage.get("modules") == ["alerts", "incidents"], (
        f"multi-module action trigger should lift to `modules: [...]`, "
        f"got modules={triage.get('modules')!r}")

    # Recompile must re-derive cybersponse.action (uuid f414d039), not the
    # plain abstract_trigger (b348f017) — the lossy downgrade this guards.
    res = compile_yaml(yaml.safe_dump(doc, sort_keys=False), PACKAGED_SLIM_DB)
    assert res.ok, [e.message for e in res.errors]
    step_types = {
        s["stepType"].rsplit("/", 1)[1]
        for wf in res.fsr_json["data"][0]["workflows"]
        for s in wf["steps"]
    }
    assert _ACTION_TRIGGER in step_types, (
        "recompile should re-derive cybersponse.action from `module:`; "
        "trigger downgraded to plain abstract_trigger (lossy round-trip)")
    assert _ABSTRACT_TRIGGER not in step_types, (
        "no step should resolve to the plain abstract_trigger here")


# --- manual-start minimification --------------------------------------------
# The live box hands an action-trigger step back with ~11 raw canonical arg
# keys; the forward normalizer `_normalize_record_action_args` re-derives ALL of
# them from a few friendly inputs. The decompiler reverse-translates to that
# minimal friendly surface. These tests guard both the minimification AND the
# round-trip stability the canonical-only form broke (noRecordExecution /
# singleRecordExecution drift because the normalizer overwrites them from
# requires_record / run_mode, which the canonical form omits).

_DROPPED_BOILERPLATE = frozenset({
    "resources", "title", "__triggerLimit", "inputVariables",
    "triggerOnSource", "triggerOnReplicate", "executeButtonText",
    "noRecordExecution", "singleRecordExecution", "showToasterMessage",
    "displayConditions",
})


def _full_action_trigger_json(resources, *, route=None, title=None,
                               no_record_execution=False,
                               single_record_execution=True,
                               input_variables=None,
                               display_conditions=None, step_name="Triage",
                               playbook_name="PB"):
    """A live-box-shaped `cybersponse.action` step with the full canonical arg
    set the normalizer emits — the bloated form the decompiler must minimize."""
    modules = [resources] if isinstance(resources, str) else list(resources)
    args = {
        "resources": modules,
        "inputVariables": list(input_variables or []),
        "step_variables": {"input": {"params": [], "records": "{{vars.input.records}}"}},
        "triggerOnSource": True,
        "triggerOnReplicate": False,
        "noRecordExecution": bool(no_record_execution),
        "singleRecordExecution": bool(single_record_execution),
        "__triggerLimit": True,
        "executeButtonText": "Execute",
        "showToasterMessage": {"visible": False, "messageVisible": True},
        "displayConditions": display_conditions or {
            m: {"sort": [], "limit": 30, "logic": "AND", "filters": []}
            for m in modules
        },
    }
    if route is not None:
        args["route"] = route
    if title is not None:
        args["title"] = title
    return {
        "data": [{
            "name": "T",
            "workflows": [{
                "name": playbook_name,
                "triggerStep": _step_iri(_ACTION_TRIGGER, 7),
                "steps": [
                    {
                        "name": step_name,
                        "uuid": _step_iri(_ACTION_TRIGGER, 7).rsplit("/", 1)[1],
                        "stepType": f"/api/3/workflow_step_types/{_ACTION_TRIGGER}",
                        "arguments": args,
                        "nextStep": "End",
                    },
                    {
                        "name": "End",
                        "uuid": _step_iri(_SET_VARIABLE, 8).rsplit("/", 1)[1],
                        "stepType": f"/api/3/workflow_step_types/{_SET_VARIABLE}",
                        "arguments": {"vars": {"y": 1}},
                    },
                ],
            }],
        }]
    }


def test_manual_start_minimized_to_friendly_fields():
    """The decompiler must emit only the minimal friendly surface for an
    action-trigger — `module` + a small `arguments:` of non-defaults — and
    drop every canonical boilerplate key the normalizer re-derives."""
    doc = yaml.safe_load(decompile_to_yaml(
        _full_action_trigger_json("alerts", route="e94851e1-1184-4abb-a2b2-1ce8a48048e7",
                                   title="Triage Alert", no_record_execution=True),
        PACKAGED_SLIM_DB))
    triage = doc["playbooks"][0]["steps"][0]
    assert triage["type"] == "start"
    assert triage.get("module") == "alerts"
    # route + requires_record + button_label survive (non-default); nothing else does.
    assert triage["arguments"] == {
        "route": "e94851e1-1184-4abb-a2b2-1ce8a48048e7",
        "requires_record": False,
        "button_label": "Triage Alert",
    }, f"unexpected arguments: {triage.get('arguments')!r}"
    leaked = _DROPPED_BOILERPLATE & set((triage.get("arguments") or {}))
    assert not leaked, f"boilerplate keys leaked into arguments: {leaked}"
    # the default step_variables (empty params) is dropped, not hoisted.
    assert "step_variables" not in triage


def test_requires_record_false_round_trips():
    """The load-bearing case: a `requires_record: false` trigger must survive
    compile->decompile->recompile with noRecordExecution/singleRecordExecution
    unchanged. The canonical-only form drifts here (normalizer overwrites the
    flags from requires_record, which is absent)."""
    from fsr_playbooks.compiler import compile_yaml

    j = _full_action_trigger_json("alerts", no_record_execution=True)
    r1 = compile_yaml(decompile_to_yaml(j, PACKAGED_SLIM_DB), PACKAGED_SLIM_DB)
    assert r1.ok, [e.message for e in r1.errors]
    r2 = compile_yaml(decompile_to_yaml(r1.fsr_json, PACKAGED_SLIM_DB), PACKAGED_SLIM_DB)
    assert r2.ok, [e.message for e in r2.errors]
    a1, a2 = _trigger_args(r1), _trigger_args(r2)
    assert a1["noRecordExecution"] is True and a2["noRecordExecution"] is True, (
        f"noRecordExecution drifted: {a1.get('noRecordExecution')} -> {a2.get('noRecordExecution')}")
    assert a1["singleRecordExecution"] == a2["singleRecordExecution"] is False, (
        f"singleRecordExecution drifted: {a1.get('singleRecordExecution')} -> {a2.get('singleRecordExecution')}")


def test_run_mode_once_for_all_round_trips():
    """requires_record=True + singleRecordExecution=False reverse-translates to
    `run_mode: once_for_all` and round-trips stably."""
    from fsr_playbooks.compiler import compile_yaml

    j = _full_action_trigger_json("alerts", single_record_execution=False)
    r1 = compile_yaml(decompile_to_yaml(j, PACKAGED_SLIM_DB), PACKAGED_SLIM_DB)
    assert r1.ok, [e.message for e in r1.errors]
    # the decompiled step should carry run_mode: once_for_all.
    triage = yaml.safe_load(decompile_to_yaml(r1.fsr_json, PACKAGED_SLIM_DB))["playbooks"][0]["steps"][0]
    assert triage["arguments"].get("run_mode") == "once_for_all", (
        f"once_for_all should survive as run_mode, got {triage['arguments']!r}")
    r2 = compile_yaml(decompile_to_yaml(r1.fsr_json, PACKAGED_SLIM_DB), PACKAGED_SLIM_DB)
    assert r2.ok and _trigger_args(r1) == _trigger_args(r2), (
        f"once_for_all round-trip drifted: {_trigger_args(r1)} vs {_trigger_args(r2)}")


def test_route_preserved_when_present():
    """A live route UUID must survive decompile->recompile unchanged, and stay
    under `arguments:` (a step-level route is silently dropped — the parser
    hoist list does not include route)."""
    from fsr_playbooks.compiler import compile_yaml

    custom = "123e4567-e89b-12d3-a456-426614174000"
    j = _full_action_trigger_json("alerts", route=custom)
    doc = yaml.safe_load(decompile_to_yaml(j, PACKAGED_SLIM_DB))
    triage = doc["playbooks"][0]["steps"][0]
    assert triage["arguments"]["route"] == custom, "route must be under arguments:"
    assert "route" not in triage, "route must NOT be at step top level"
    r = compile_yaml(yaml.safe_dump(doc, sort_keys=False), PACKAGED_SLIM_DB)
    assert r.ok, [e.message for e in r.errors]
    assert _trigger_args(r)["route"] == custom, "route drifted on recompile"


def test_route_omitted_when_absent():
    """An action-trigger with no route decompiles without a `route` key — the
    normalizer regenerates the deterministic uuid5 on compile. (Authored
    playbooks have no route; this keeps their YAML clean.)"""
    j = _full_action_trigger_json("alerts")  # no route
    triage = yaml.safe_load(decompile_to_yaml(j, PACKAGED_SLIM_DB))["playbooks"][0]["steps"][0]
    assert "route" not in (triage.get("arguments") or {}), (
        f"route should be omitted when absent, got {triage.get('arguments')!r}")


def test_button_label_emitted_only_when_not_playbook_name():
    """The normalizer defaults the trigger button label (`title`) to the
    playbook name, so the decompiler emits `button_label` only when the
    persisted label differs — otherwise the YAML would just repeat the name."""
    # title == playbook name -> dropped (default).
    j = _full_action_trigger_json("alerts", title="PB", playbook_name="PB")
    triage = yaml.safe_load(decompile_to_yaml(j, PACKAGED_SLIM_DB))["playbooks"][0]["steps"][0]
    assert "button_label" not in (triage.get("arguments") or {}), (
        "title == playbook name should be dropped, not emitted as button_label")
    # title != playbook name -> emitted as button_label.
    j2 = _full_action_trigger_json("alerts", title="Triage Alert", playbook_name="PB")
    triage2 = yaml.safe_load(decompile_to_yaml(j2, PACKAGED_SLIM_DB))["playbooks"][0]["steps"][0]
    assert triage2["arguments"].get("button_label") == "Triage Alert", (
        f"distinct title should become button_label, got {triage2.get('arguments')!r}")


def test_default_display_conditions_dropped():
    """The per-module empty displayConditions the normalizer setdefaults is
    dropped; a customized filter is kept."""
    # default -> dropped.
    j = _full_action_trigger_json("alerts")
    triage = yaml.safe_load(decompile_to_yaml(j, PACKAGED_SLIM_DB))["playbooks"][0]["steps"][0]
    assert "displayConditions" not in (triage.get("arguments") or {}), (
        "default displayConditions should be dropped")
    # customized -> kept.
    custom_dc = {"alerts": {"sort": [], "limit": 50, "logic": "AND", "filters": []}}
    j2 = _full_action_trigger_json("alerts", display_conditions=custom_dc)
    triage2 = yaml.safe_load(decompile_to_yaml(j2, PACKAGED_SLIM_DB))["playbooks"][0]["steps"][0]
    assert triage2["arguments"].get("displayConditions") == custom_dc, (
        f"custom displayConditions should be kept, got {triage2.get('arguments')!r}")


def _trigger_args(res):
    """The compiled trigger step's `arguments` (canonical) from a CompileResult."""
    for col in res.fsr_json["data"]:
        for wf in col["workflows"]:
            for s in wf["steps"]:
                if s["stepType"].endswith(_ACTION_TRIGGER):
                    return s["arguments"]
    raise AssertionError("no action-trigger step in compiled result")


def test_trigger_tenant_playbook_round_trips():
    """RemotePlaybookReference is a clean 1:1 canonical mapping (only
    `trigger_tenant_playbook` compiles to it, unlike the Connectors collision),
    so a pulled remote-reference step decompiles to `trigger_tenant_playbook`
    (not raw canonical) and recompiles losslessly. This is the P4 read-loop win:
    the editor's "Trigger Tenant Playbook" palette entry now has a friendly
    surface on BOTH directions."""
    by_name = _roundtrip_steps(
        """
collection: T
playbooks:
  - name: PB
    steps:
      - name: Start
        type: start
        next: TTP
      - name: TTP
        type: trigger_tenant_playbook
        arguments:
          playbook_alias_id: remote-ir-playbook
          tenant_id: tenant-acme
"""
    )
    s = by_name["TTP"]
    assert s["type"] == "trigger_tenant_playbook", (
        f"RemotePlaybookReference should decompile to trigger_tenant_playbook, "
        f"got {s.get('type')!r}")
    assert s["arguments"]["playbook_alias_id"] == "remote-ir-playbook"
    assert s["arguments"]["tenant_id"] == "tenant-acme"




def test_api_endpoint_minified_drops_trigger_boilerplate():
    """The forward normalizer setdefaults five trigger-infra fields
    (`authentication_methods`->[''], `step_variables`->default, `triggerOnSource`
    ->True, `triggerOnReplicate`->False, `__triggerLimit`->True) so the minimal
    `route:`-only form compiles to a fully-specified token-based trigger. On
    decompile, drop those re-derived defaults so a pulled api_endpoint step
    surfaces just `route` -- recompile re-adds them via the same setdefaults
    (round-trip stable). This is the G10 Tier-2 api_endpoint minimification."""
    by_name = _roundtrip_steps(
        """
collection: T
playbooks:
  - name: PB
    steps:
      - name: Start
        type: api_endpoint
        arguments:
          route: lookup_ip
      - name: Do
        type: set_variable
        vars: {x: 1}
"""
    )
    s = by_name["Start"]
    assert s["type"] == "api_endpoint"
    args = s.get("arguments") or {}
    # route is the one friendly scalar -- always preserved.
    assert args.get("route") == "lookup_ip", args
    # The five re-derived defaults must be dropped (not surfaced as boilerplate).
    assert "authentication_methods" not in args, args
    assert "triggerOnSource" not in args, args
    assert "triggerOnReplicate" not in args, args
    assert "__triggerLimit" not in args, args
    # step_variables is hoisted to the step level by the universal envelope loop;
    # the default shape is dropped there too.
    assert "step_variables" not in s, s


def test_api_endpoint_minified_preserves_non_default_auth():
    """A non-default `authentication_methods` (e.g. ['anonymous'] for No-Auth)
    and a customized `triggerOnSource` are author-owned values -- the
    minimification must PRESERVE them (drop only values that equal the
    setdefault default)."""
    by_name = _roundtrip_steps(
        """
collection: T
playbooks:
  - name: PB
    steps:
      - name: Start
        type: api_endpoint
        arguments:
          route: webhook_in
          authentication_methods: [anonymous]
          triggerOnSource: false
      - name: Do
        type: set_variable
        vars: {x: 1}
"""
    )
    s = by_name["Start"]
    args = s.get("arguments") or {}
    assert args.get("route") == "webhook_in"
    assert args.get("authentication_methods") == ["anonymous"], args   # preserved
    assert args.get("triggerOnSource") is False, args                  # preserved
    # The still-default infra keys are dropped.
    assert "triggerOnReplicate" not in args, args
    assert "__triggerLimit" not in args, args
    assert "step_variables" not in s, s


def test_code_snippet_minified_to_code_surface():
    """The forward normalizer expands the friendly `code:` surface into the
    full canonical connector envelope (connector=code-snippet, operation=
    python_inline_code_editor, operationTitle, version, params.python_function,
    config, step_variables). On decompile, reverse to just `code:` -- recompile
    re-adds the envelope via the same defaults (round-trip stable). This is the
    G10 Tier-2 code_snippet minimification."""
    by_name = _roundtrip_steps(
        """
collection: T
playbooks:
  - name: PB
    steps:
      - name: Start
        type: start
        next: CS
      - name: CS
        type: code_snippet
        arguments:
          code: |
            print("hi")
"""
    )
    s = by_name["CS"]
    assert s["type"] == "code_snippet"
    args = s.get("arguments") or {}
    # The code body is recovered to the friendly `code:` surface.
    assert args.get("code", "").strip() == 'print("hi")', args
    # The re-derived envelope keys are dropped (not surfaced as boilerplate).
    for env_k in ("connector", "operation", "operationTitle", "version",
                  "params", "config"):
        assert env_k not in args, (env_k, args)
    # step_variables is hoisted to step level; the empty default is dropped.
    assert "step_variables" not in s, s


def test_code_snippet_minified_preserves_real_config_uuid():
    """A real config UUID (a specific chosen connector configuration) is
    load-bearing -- the minimification must PRESERVE it (can't reverse-resolve
    to the name without the catalog; round-trip stable as a UUID). Only the
    empty default `config: ""` is dropped."""
    from fsr_playbooks.compiler.ir import Step
    from fsr_playbooks.compiler.decompiler import _decompile_step
    s = Step(id="cs", type="code_snippet", name="cs", arguments={
        "connector": "code-snippet", "operation": "python_inline_code_editor",
        "operationTitle": "Execute Python Code", "version": "2.1.4",
        "config": "abc-123-uuid", "params": {"python_function": "x"},
    })
    out = _decompile_step(s)
    assert out["arguments"]["config"] == "abc-123-uuid"   # preserved
    assert out["arguments"]["code"] == "x"


def test_code_snippet_without_python_function_passes_through():
    """A canonical code_snippet step with NO `params.python_function` (no code
    body to recover) falls through to the generic pass-through -- its envelope
    is preserved, not stripped (the minimification only fires when there is a
    code body to extract)."""
    from fsr_playbooks.compiler.ir import Step
    from fsr_playbooks.compiler.decompiler import _decompile_step
    s = Step(id="cs", type="code_snippet", name="cs", arguments={
        "connector": "code-snippet", "operation": "python_inline_code_editor",
        "version": "2.1.4",
    })
    out = _decompile_step(s)
    assert out["arguments"]["connector"] == "code-snippet"   # envelope intact
    assert "code" not in out["arguments"]
