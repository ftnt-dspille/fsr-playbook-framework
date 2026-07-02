"""Per-step-type typed argument models (Phase 2).

The migration lands type-by-type behind a registry + fallback: a step type
with a model routes its arguments through the typed layer; everything else
keeps using the imperative normalizer in `resolver/normalizers.py`. This keeps
every intermediate commit shippable (zero corpus-emit diff at each step).

`STEP_ARG_MODELS` maps an FSR-friendly step type to its pydantic model — the
introspection surface Phase 4 will emit JSON Schema from. Types whose wire
output is not a fixed-field record (e.g. set_variable, whose flat output keys
are the author's variable names) also expose an `expand_*` walk that owns the
semantic transform + precise CompileError paths, mirroring the trigger layer's
`expand_when`. The resolver calls that walk; the model backs it.
"""
from __future__ import annotations

from ..base import StrictArgs  # noqa: F401  (re-export for symmetry)
from .set_variable import SetVariableArgs, ArgListEntry, expand_set_variable
from .decision import DecisionArgs, DecisionCondition, expand_decision
from .delay import DelayArgs, expand_delay
from .code_snippet import CodeSnippetArgs, expand_code_snippet
from .find_record import FindRecordArgs, expand_find_record
from .delete_record import DeleteRecordArgs, expand_delete_record
from .record_crud import RecordCrudArgs, expand_record_crud
from .record_action import RecordActionArgs, expand_record_action
from .post_create_update import (
    PostCreateUpdateArgs,
    expand_post_create_update,
)
from .api_endpoint import ApiEndpointArgs, expand_api_endpoint
from .connector import ConnectorArgs, expand_connector
from .manual_input import (
    ManualInputArgs,
    InputVariableArgs,
    InputFieldKind,
    expand_manual_input,
)
from .trigger_tenant_playbook import (
    TriggerTenantPlaybookArgs,
    expand_trigger_tenant_playbook,
)
from .send_email import SendEmailArgs, expand_send_email
from .create_task import CreateTaskArgs, expand_create_task
from .set_api_keys import SetApiKeysArgs, expand_set_api_keys
from .approval import ApprovalArgs, expand_approval
from .workflow_reference import WorkflowReferenceArgs, expand_workflow_reference
from .ingest_bulk_feed import IngestBulkFeedArgs, expand_ingest_bulk_feed

# Step type → typed argument model. Grows incrementally through Phase 2.
#
# Keys are FSR-friendly step types. `record_action` is the one entry that is not
# a distinct *authoring* type — it is authored as `type: start` with a `module:`
# (the manual record-action trigger; see `validator.py` TRIGGER_TYPES and the
# `cybersponse.action` mapping). It is keyed here so its schema is discoverable
# via `get_step_arg_schema("record_action")`; the resolver wires its validation
# into the `start`+`module` normalizer, not by a type-map lookup.
STEP_ARG_MODELS: dict[str, type[StrictArgs]] = {
    "set_variable": SetVariableArgs,
    "decision": DecisionArgs,
    "delay": DelayArgs,
    "code_snippet": CodeSnippetArgs,
    "find_record": FindRecordArgs,
    "delete_record": DeleteRecordArgs,
    "create_record": RecordCrudArgs,
    "insert_record": RecordCrudArgs,
    "update_record": RecordCrudArgs,
    "record_action": RecordActionArgs,
    # `start` covers TWO of the 6 trigger variants: Manual (start + module ->
    # cybersponse.action, validated via the `record_action` call site in the
    # resolver) and Referenced (plain start -> cybersponse.abstract_trigger,
    # no friendly scalars). RecordActionArgs is the Manual-variant contract;
    # its all-Optional fields let the plain Referenced form validate clean too.
    # Registered under the real step type `start` so `get_step_arg_schema("start")`
    # surfaces the Manual contract (the docstring scopes it to start+module).
    "start": RecordActionArgs,
    "start_on_create": PostCreateUpdateArgs,
    "start_on_update": PostCreateUpdateArgs,
    "start_on_delete": PostCreateUpdateArgs,
    # Custom API Endpoint trigger (cybersponse.api_call). Validation-only --
    # the token-based auth default + trigger-infra setdefaults stay imperative.
    "api_endpoint": ApiEndpointArgs,
    # The connector envelope (the keystone -- shared backbone for the whole
    # connector family: Connector/Code Snippet/Utilities/Send Email). Static
    # envelope typed; params stays Any (per-op catalog). Validation-only --
    # the resolver's catalog checks (op/param/enum/visibility/required) own
    # the richer runtime messages.
    "connector": ConnectorArgs,
    # `utilities` — the editor's "Utilities" palette entry (CyopsUtilices). A
    # connector-family alias: it routes through ConnectorStepCtrl + connector.html,
    # so its wire shape IS the connector envelope; the normalizer defaults
    # `connector: cyops_utilities` (one of 55 utility ops) and falls through to
    # `_resolve_connector_args`. Reuses the P3 ConnectorArgs model (the way
    # create/insert/update share RecordCrudArgs). Read = sugar-not-recovered
    # (a pulled Utilities step round-trips as `connector`, like stop/end).
    "utilities": ConnectorArgs,
    # Validation-only model (the friendly→canonical transform stays in the
    # imperative normalizer; see manual_input.py). Registered for the JSON-schema
    # introspection surface + typed scalar validation.
    "manual_input": ManualInputArgs,
    # Trigger Tenant Playbook (RemotePlaybookReference) — cross-tenant call to
    # a playbook in another FortiSOAR tenant. Owns a distinct script handler
    # (`/wf/workflow/tasks/remote_workflow_reference`), so a real step type
    # (not a connector alias). Validation-only envelope; the resolver owns the
    # required-`workflowReference` MISSING_FIELD check.
    "trigger_tenant_playbook": TriggerTenantPlaybookArgs,
    # P5 lighter envelope models (validation-only; the friendly->canonical
    # transform stays in the imperative normalizer). Registered for the JSON-
    # schema introspection surface + typed scalar validation. Each mirrors the
    # connector design split: the typed model owns the envelope schema + scalar
    # checks; the normalizer/resolver owns the runtime transform + richer
    # messages.
    "send_email": SendEmailArgs,
    "create_task": CreateTaskArgs,
    "set_api_keys": SetApiKeysArgs,
    "approval": ApprovalArgs,
    # Local same-collection playbook call (WorkflowReference). Validation-only;
    # the resolver's _resolve_workflow_reference_args owns the target/name
    # lookup + required-field check + parameter validation. target/
    # workflowReference declared Optional so pydantic doesn't shadow the
    # resolver's MISSING_FIELD. (Cross-tenant sibling = trigger_tenant_playbook.)
    "workflow_reference": WorkflowReferenceArgs,
    # Ingest Bulk Feed (IngestBulkFeed) -- the bulk-ingest sibling of Create
    # Record (inherits InsertDataCtrl; POSTs to /api/ingest-feeds/<module>,
    # deletes operation/fieldOperation). Validation-only; the lint layer
    # (rulesets/_shared.py) owns the collection-prefix + no-operation checks,
    # and the emitter (_clean_step_arguments) owns the for_each loop-mode
    # normalization, so for_each stays Any here.
    "ingest_bulk_feed": IngestBulkFeedArgs,
}


def is_modeled(step_type: str) -> bool:
    """True if `step_type` has a typed-args model (vs. the imperative path)."""
    return step_type in STEP_ARG_MODELS


__all__ = [
    "STEP_ARG_MODELS",
    "is_modeled",
    "SetVariableArgs",
    "ArgListEntry",
    "expand_set_variable",
    "DecisionArgs",
    "DecisionCondition",
    "expand_decision",
    "DelayArgs",
    "expand_delay",
    "CodeSnippetArgs",
    "expand_code_snippet",
    "FindRecordArgs",
    "expand_find_record",
    "DeleteRecordArgs",
    "expand_delete_record",
    "RecordCrudArgs",
    "expand_record_crud",
    "RecordActionArgs",
    "expand_record_action",
    "PostCreateUpdateArgs",
    "expand_post_create_update",
    "ApiEndpointArgs",
    "expand_api_endpoint",
    "ConnectorArgs",
    "expand_connector",
    "ManualInputArgs",
    "InputVariableArgs",
    "InputFieldKind",
    "expand_manual_input",
    "TriggerTenantPlaybookArgs",
    "expand_trigger_tenant_playbook",
    "SendEmailArgs",
    "expand_send_email",
    "CreateTaskArgs",
    "expand_create_task",
    "SetApiKeysArgs",
    "expand_set_api_keys",
    "ApprovalArgs",
    "expand_approval",
    "WorkflowReferenceArgs",
    "expand_workflow_reference",
    "IngestBulkFeedArgs",
    "expand_ingest_bulk_feed",
]
