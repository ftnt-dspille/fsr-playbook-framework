"""Typed-args model for the ``trigger_tenant_playbook`` step -- the P4
editor-palette gap closure for "Trigger Tenant Playbook" (canonical
``RemotePlaybookReference``): a cross-tenant call to a playbook on a peer
FortiSOAR instance.

It owns a distinct script handler (``/wf/workflow/tasks/remote_workflow_reference``),
so it is a real step type, not a connector-family alias. The friendly surface
is grounded in the **live** handler signature from the ``step_handlers``
table: ``remote_workflow_reference(playbook_alias_id, tenant_id=None, *args,
**kwargs)`` -- so ``playbook_alias_id`` is required and ``tenant_id`` optional.
These tests pin the registry contract, the discover win, the validation-only
scalar typing, the resolver's required-field message, and the e2e compile."""
from __future__ import annotations

from fsr_playbooks.compiler import compile_yaml
from fsr_playbooks.compiler.errors import ErrorCode
from fsr_playbooks.compiler.typed_args.schema import emit_step_arg_schema
from fsr_playbooks.compiler.typed_args.steps import (
    STEP_ARG_MODELS,
    TriggerTenantPlaybookArgs,
    expand_trigger_tenant_playbook,
    is_modeled,
)


def _expand(args, errs=None):
    return expand_trigger_tenant_playbook(
        args, "p.steps[0]", errs if errs is not None else [])


def test_registry_models_trigger_tenant_playbook():
    assert STEP_ARG_MODELS.get("trigger_tenant_playbook") is TriggerTenantPlaybookArgs
    assert is_modeled("trigger_tenant_playbook") is True


def test_schema_now_introspectable():
    # The discover win: an agent asking "what does a trigger_tenant_playbook
    # step take?" gets a JSON Schema, not None.
    s = emit_step_arg_schema("trigger_tenant_playbook")
    assert s is not None
    props = set(s.get("properties", {}))
    # The live handler contract: playbook_alias_id (required) + tenant_id.
    assert "playbook_alias_id" in props, props
    assert "tenant_id" in props, props
    # NOTE: playbook_alias_id is NOT in the schema's `required` -- declared
    # Optional so pydantic doesn't shadow the resolver's MISSING_FIELD message
    # (the manual_input / connector lesson). The resolver + arg_validator
    # enforce presence at runtime.


def test_validation_only_returns_none_and_does_not_mutate():
    args = {"playbook_alias_id": "remote-ir-playbook", "tenant_id": "acme"}
    snapshot = dict(args)
    assert _expand(args) is None
    assert args == snapshot


def test_valid_envelope_passes():
    errs = []
    _expand({"playbook_alias_id": "remote-ir-playbook"}, errs)
    assert not [e for e in errs if e.code is ErrorCode.BAD_VALUE]


def test_wrong_typed_alias_is_bad_value():
    errs = []
    _expand({"playbook_alias_id": 123}, errs)
    assert any(
        e.code is ErrorCode.BAD_VALUE
        and e.path.endswith("arguments.playbook_alias_id")
        for e in errs
    )


def test_wrong_typed_tenant_id_is_bad_value():
    errs = []
    _expand({"playbook_alias_id": "x", "tenant_id": 7}, errs)
    assert any(
        e.code is ErrorCode.BAD_VALUE
        and e.path.endswith("arguments.tenant_id")
        for e in errs
    )


def test_non_dict_returns_none():
    assert expand_trigger_tenant_playbook("nope", "p", []) is None


def test_resolver_missing_alias_message_unshadowed(db_path):
    # A MISSING playbook_alias_id surfaces the resolver's precise message, not
    # pydantic's "Field required" (the typed layer does not re-validate
    # presence -- the resolver owns that).
    text = """
collection: T
playbooks:
  - name: P
    steps:
      - name: start
        type: start
        next: ttp
      - name: ttp
        type: trigger_tenant_playbook
        arguments:
          tenant_id: acme
"""
    r = compile_yaml(text, db_path)
    missing = [e for e in r.errors
               if e.code is ErrorCode.MISSING_FIELD
               and e.path.endswith("arguments.playbook_alias_id")]
    assert missing, [e.to_dict() for e in r.errors]
    assert "trigger_tenant_playbook step requires 'playbook_alias_id'" in (missing[0].message or "")


def test_end_to_end_compile_trigger_tenant_playbook(db_path):
    # The full surface: alias + tenant_id compiles clean against the live
    # remote_workflow_reference handler signature (arg_validator enforces
    # playbook_alias_id is present + known; no unknown-arg warnings for the
    # modeled fields).
    text = """
collection: T
playbooks:
  - name: P
    steps:
      - name: start
        type: start
        next: ttp
      - name: ttp
        type: trigger_tenant_playbook
        arguments:
          playbook_alias_id: remote-ir-playbook
          tenant_id: tenant-acme
"""
    r = compile_yaml(text, db_path)
    assert not [e for e in r.errors if e.severity == "error"], \
        [e.to_dict() for e in r.errors]
