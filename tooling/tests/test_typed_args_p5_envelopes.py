"""Typed-args models for the P5 lighter envelope step types.

P5 closed the discover gap for the lighter action/notify steps
(send_email/create_task/set_api_keys/approval/workflow_reference): each now
has a validation-only envelope model so ``get_step_arg_schema(<type>)`` returns
a JSON Schema instead of ``None``. The friendly->canonical transform stays in
the imperative normalizer (the connector design split); the typed layer types
the envelope scalars and flags present-but-wrong-typed values as ``BAD_VALUE``
without shadowing the resolver's richer runtime messages (required fields are
declared Optional so pydantic does not emit its generic "Field required").

Grounded in each step's normalizer (``resolver/normalizers.py`` /
``resolver/connector_args.py``) and the captured editor wire shapes
(``docs/STEP_WIRE_SHAPES``).
"""
from __future__ import annotations

from fsr_playbooks.compiler import compile_yaml
from fsr_playbooks.compiler.errors import ErrorCode
from fsr_playbooks.compiler.typed_args.schema import emit_step_arg_schema
from fsr_playbooks.compiler.typed_args.steps import (
    STEP_ARG_MODELS,
    SendEmailArgs,
    CreateTaskArgs,
    SetApiKeysArgs,
    ApprovalArgs,
    WorkflowReferenceArgs,
    expand_send_email,
    expand_create_task,
    expand_set_api_keys,
    expand_approval,
    expand_workflow_reference,
    is_modeled,
)


# ---------------------------------------------------------------------------
# send_email
# ---------------------------------------------------------------------------

def _se(args, errs=None):
    return expand_send_email(args, "p.steps[0]", errs if errs is not None else [])


def test_send_email_registry_and_schema():
    assert STEP_ARG_MODELS.get("send_email") is SendEmailArgs
    assert is_modeled("send_email") is True
    s = emit_step_arg_schema("send_email")
    assert s is not None
    props = set(s.get("properties", {}))
    for k in ("to", "cc", "bcc", "subject", "content", "from_str", "attachments"):
        assert k in props, k


def test_send_email_validation_only_no_mutation():
    args = {"to": ["a@x.com"], "subject": "hi", "content": "body"}
    snap = dict(args)
    assert _se(args) is None
    assert args == snap


def test_send_email_wrong_typed_subject_is_bad_value():
    errs = []
    _se({"to": ["a@x.com"], "subject": 42}, errs)
    assert any(e.code is ErrorCode.BAD_VALUE
               and e.path.endswith("arguments.subject") for e in errs)


def test_send_email_wrong_typed_to_is_bad_value():
    # to is Union[str, List[str]]; pydantic reports a BAD_VALUE per union
    # member, at a path suffixed with the member (`.str`, `.list[str]`). A bare
    # int matches neither member.
    errs = []
    _se({"to": 123}, errs)
    assert any(e.code is ErrorCode.BAD_VALUE
               and "arguments.to" in (e.path or "") for e in errs)


def test_send_email_jinja_subject_passes():
    # subject is jinja-capable -> a string with {{ }} is valid.
    errs = []
    _se({"to": ["a@x.com"], "subject": "{{ alert.name }}"}, errs)
    assert not [e for e in errs if e.code is ErrorCode.BAD_VALUE]


# ---------------------------------------------------------------------------
# create_task
# ---------------------------------------------------------------------------

def _ct(args, errs=None):
    return expand_create_task(args, "p.steps[0]", errs if errs is not None else [])


def test_create_task_registry_and_schema():
    assert STEP_ARG_MODELS.get("create_task") is CreateTaskArgs
    s = emit_step_arg_schema("create_task")
    assert s is not None
    props = set(s.get("properties", {}))
    assert {"collection", "resource"} <= props


def test_create_task_resource_is_any_accepts_freeform():
    # resource is Any -- the editor builds the task-module form fields into it,
    # so it is genuinely free-form (a mapping, but the typed layer does not
    # constrain the shape). A string value passes; the normalizer's own
    # unknown-key check owns the surface, not the typed layer.
    errs = []
    _ct({"resource": {"name": "do thing"}}, errs)
    assert not [e for e in errs if e.code is ErrorCode.BAD_VALUE]
    errs2 = []
    _ct({"resource": "freeform"}, errs2)
    assert not [e for e in errs2 if e.code is ErrorCode.BAD_VALUE]


# ---------------------------------------------------------------------------
# set_api_keys
# ---------------------------------------------------------------------------

def _sak(args, errs=None):
    return expand_set_api_keys(args, "p.steps[0]", errs if errs is not None else [])


def test_set_api_keys_registry_and_schema():
    assert STEP_ARG_MODELS.get("set_api_keys") is SetApiKeysArgs
    s = emit_step_arg_schema("set_api_keys")
    assert s is not None
    props = set(s.get("properties", {}))
    assert {"public_key", "private_key"} <= props


def test_set_api_keys_wrong_typed_is_bad_value():
    errs = []
    _sak({"public_key": 123}, errs)
    assert any(e.code is ErrorCode.BAD_VALUE
               and e.path.endswith("arguments.public_key") for e in errs)


def test_set_api_keys_jinja_passes():
    errs = []
    _sak({"public_key": "{{ vault.key }}", "private_key": "{{ vault.secret }}"}, errs)
    assert not [e for e in errs if e.code is ErrorCode.BAD_VALUE]


# ---------------------------------------------------------------------------
# approval
# ---------------------------------------------------------------------------

def _ap(args, errs=None):
    return expand_approval(args, "p.steps[0]", errs if errs is not None else [])


def test_approval_registry_and_schema():
    assert STEP_ARG_MODELS.get("approval") is ApprovalArgs
    s = emit_step_arg_schema("approval")
    assert s is not None
    props = set(s.get("properties", {}))
    assert {"collection", "resource", "timeout", "response_mapping"} <= props


def test_approval_wrong_typed_timeout_is_bad_value():
    # timeout is Union[int, float]; a non-numeric string matches neither member.
    # pydantic reports a BAD_VALUE per union member at a suffixed path.
    errs = []
    _ap({"timeout": "soon"}, errs)
    assert any(e.code is ErrorCode.BAD_VALUE
               and "arguments.timeout" in (e.path or "") for e in errs)


def test_approval_numeric_timeout_passes():
    errs = []
    _ap({"timeout": 300}, errs)
    assert not [e for e in errs if e.code is ErrorCode.BAD_VALUE]


# ---------------------------------------------------------------------------
# workflow_reference
# ---------------------------------------------------------------------------

def _wr(args, errs=None):
    return expand_workflow_reference(args, "p.steps[0]", errs if errs is not None else [])


def test_workflow_reference_registry_and_schema():
    assert STEP_ARG_MODELS.get("workflow_reference") is WorkflowReferenceArgs
    s = emit_step_arg_schema("workflow_reference")
    assert s is not None
    props = set(s.get("properties", {}))
    assert {"target", "workflowReference", "arguments"} <= props


def test_workflow_reference_wrong_typed_target_is_bad_value():
    errs = []
    _wr({"target": 123}, errs)
    assert any(e.code is ErrorCode.BAD_VALUE
               and e.path.endswith("arguments.target") for e in errs)


def test_workflow_reference_missing_target_not_shadowed():
    # Neither target nor workflowReference -> the typed layer does NOT raise
    # (they're Optional); the resolver owns the MISSING_FIELD message.
    errs = []
    _wr({"arguments": {"x": 1}}, errs)
    assert not [e for e in errs if e.code is ErrorCode.MISSING_FIELD]


def test_workflow_reference_valid_target_passes():
    errs = []
    _wr({"target": "DoThing", "arguments": {"k": "v"}}, errs)
    assert not [e for e in errs if e.code is ErrorCode.BAD_VALUE]


# ---------------------------------------------------------------------------
# end-to-end: the resolver's richer messages still own presence checks.
# ---------------------------------------------------------------------------

def test_send_email_e2e_compiles(db_path):
    text = """
collection: T
playbooks:
  - name: P
    steps:
      - name: start
        type: start
        next: mail
      - name: mail
        type: send_email
        arguments:
          to: [a@x.com]
          subject: hi
          body: hello
"""
    r = compile_yaml(text, db_path)
    assert not [e for e in r.errors if e.severity == "error"], \
        [e.to_dict() for e in r.errors]


def test_approval_e2e_compiles(db_path):
    text = """
collection: T
playbooks:
  - name: P
    steps:
      - name: start
        type: start
        next: appr
      - name: appr
        type: approval
        arguments:
          resource:
            approvaldescription: please
"""
    r = compile_yaml(text, db_path)
    assert not [e for e in r.errors if e.severity == "error"], \
        [e.to_dict() for e in r.errors]
