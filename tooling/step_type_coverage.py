"""Step-type coverage matrix — the north-star instrument for the agentic
playbook assistant.

The fsr_playbooks project exists to make FortiSOAR playbooks simple for
agents: a friendly YAML, a compiler that is static-analysis + validator, and
feedback that tells the agent what to correct. For an agent to create / read
/ modify / troubleshoot a playbook of a given step type, three loops must be
closed for that type:

  * **author**   — friendly YAML -> canonical wire. Is there a typed arg
                   model (`STEP_ARG_MODELS`) behind the imperative normalizer,
                   so the shape is introspectable + scalar-validated?
  * **discover** — can an agent ask "what can this step take?" and get an
                   answer? `emit_step_arg_schema` returns a non-None JSON
                   Schema for modeled types, None for the rest.
  * **read**     — does the decompiler recover a friendly shape from an
                   existing playbook (`minimified`), pass canonical args
                   through unchanged (`pass-through`), or is the friendly
                   sugar one-way — compiled down to a shared canonical with
                   no distinct type to recover (`sugar-not-recovered`)?

`COVERAGE` is the single source of truth for "which of the 24 friendly step
types are fully served, and which still have a dark loop." It is the backlog
as much as the dashboard: `priority` flags the next work.

Two invariants are *enforced* by `tooling/tests/test_step_type_coverage.py`:

  1. Every friendly step type (`SHORT_TYPE_TO_FSR`) has an explicit COVERAGE
     entry — adding a step type without a coverage decision fails the gate.
     No accidental gaps.
  2. The derived facts (`typed`, `schema`, `read`) match the live code — a
     claim the registries don't back up fails the gate. No false claims.

The `example` axis (worked examples in the pyfsr foundational library) is
tracked in the plan doc, not here, to keep this gate framework-self-contained
and DB-free.
"""
from __future__ import annotations

from dataclasses import dataclass, field

READ_MINIMIFIED = "minimified"
READ_PASS_THROUGH = "pass-through"
READ_SUGAR_NOT_RECOVERED = "sugar-not-recovered"
_READ_VALUES = {READ_MINIMIFIED, READ_PASS_THROUGH, READ_SUGAR_NOT_RECOVERED}

PRI_DONE = "done"
PRI_HIGH = "high"
PRI_MED = "med"
PRI_LOW = "low"
_PRI_VALUES = {PRI_DONE, PRI_HIGH, PRI_MED, PRI_LOW}


@dataclass(frozen=True)
class StepCoverage:
    """Per-step-type coverage of the author/discover/read loops."""

    typed: bool
    schema: bool
    read: str
    priority: str
    note: str = ""
    tags: frozenset[str] = field(default_factory=frozenset)

    def validate_literal(self) -> None:
        if self.read not in _READ_VALUES:
            raise ValueError(f"read={self.read!r} not in {_READ_VALUES}")
        if self.priority not in _PRI_VALUES:
            raise ValueError(f"priority={self.priority!r} not in {_PRI_VALUES}")


# The matrix. One row per friendly step type in SHORT_TYPE_TO_FSR (24).
# `typed`/`schema` are verified against the live registries by the gate test,
# so they cannot drift; `read` is verified against the decompiler source.
# `priority` + `note` are the human-maintained backlog.
COVERAGE: dict[str, StepCoverage] = {
    # --- record family (fully typed; callback-DI resolve_module) ---
    "create_record": StepCoverage(
        typed=True, schema=True, read=READ_PASS_THROUGH, priority=PRI_DONE,
        note="record_crud model; module->collection; is_upsert->upsert endpoint."),
    "insert_record": StepCoverage(
        typed=True, schema=True, read=READ_PASS_THROUGH, priority=PRI_DONE,
        note="shares RecordCrudArgs; module->collection."),
    "update_record": StepCoverage(
        typed=True, schema=True, read=READ_PASS_THROUGH, priority=PRI_DONE,
        note="RecordCrudArgs; module->collectionType (record IRI untouched)."),
    "delete_record": StepCoverage(
        typed=True, schema=True, read=READ_SUGAR_NOT_RECOVERED, priority=PRI_MED,
        note="compiles to cyops_utilities DELETE; round-trips as `connector`. "
             "decompiler envelope asymmetry open (G10 Tier 1)."),
    "find_record": StepCoverage(
        typed=True, schema=True, read=READ_PASS_THROUGH, priority=PRI_DONE,
        note="validation-only model; query left Any."),
    # --- post-write triggers (post_create/update/delete) ---
    "start_on_create": StepCoverage(
        typed=True, schema=True, read=READ_PASS_THROUGH, priority=PRI_DONE,
        note="post_create_update model; module->resource/resources + when->fbt."),
    "start_on_update": StepCoverage(
        typed=True, schema=True, read=READ_PASS_THROUGH, priority=PRI_DONE,
        note="shares PostCreateUpdateArgs."),
    "start_on_delete": StepCoverage(
        typed=True, schema=True, read=READ_PASS_THROUGH, priority=PRI_DONE,
        note="shares PostCreateUpdateArgs."),
    # --- simple / control steps (typed) ---
    "set_variable": StepCoverage(
        typed=True, schema=True, read=READ_MINIMIFIED, priority=PRI_DONE,
        note="arg_list->flat dict; decompiler recovers `vars:`."),
    "decision": StepCoverage(
        typed=True, schema=True, read=READ_MINIMIFIED, priority=PRI_DONE,
        note="conditions->display/when/next; branch promotion."),
    "delay": StepCoverage(
        typed=True, schema=True, read=READ_PASS_THROUGH, priority=PRI_DONE,
        note="friendly duration->TimeBased."),
    "code_snippet": StepCoverage(
        typed=True, schema=True, read=READ_PASS_THROUGH, priority=PRI_MED,
        note="python_function/config expansion. read pass-through leaves the "
             "full canonical block; a minimification branch would help agents."),
    "manual_input": StepCoverage(
        typed=True, schema=True, read=READ_MINIMIFIED, priority=PRI_MED,
        note="scalars typed + schema surface. P2 DONE: nested InputVariableArgs "
             "model makes the 28-kind inputs[] contract introspectable (the "
             "discover win -- was Any, schema emitted {}). The Literal derives "
             "from picklists._INPUT_FIELD_KINDS so it can't drift. Runtime "
             "per-entry validation stays in the resolver (richer suggestion-"
             "bearing messages than pydantic); the typed layer strips `inputs` "
             "before validate_args so it doesn't shadow them. Residual: the "
             "friendly->canonical transform itself stays imperative (F3 site) -- "
             "a future transform migration, low value (relocation, not a fix)."),
    # --- the keystone: connector (every real integration) ---
    "connector": StepCoverage(
        typed=True, schema=True, read=READ_MINIMIFIED, priority=PRI_MED,
        note="P3 DONE: ConnectorArgs envelope model (connector/operation/config/"
             "version/agent/operationTitle typed; params stays Any = per-op catalog). "
             "Validation-only -- the resolver's catalog checks (missing op/param, "
             "enum, visibility, required, auto-lift, difflib 'did you mean') own the "
             "richer runtime messages; connector/operation declared Optional so "
             "pydantic doesn't shadow the resolver's MISSING_FIELD. The shared "
             "backbone for the whole connector family (Connector/Code Snippet/"
             "Utilities/Send Email). Residual: per-op `params` schema is the live "
             "catalog (fsrpb find op), not static -- correct by design."),
    # --- utilities: the editor's "Utilities" palette entry (CyopsUtilices) ---
    # A connector-family alias, not a distinct step type: it routes through
    # ConnectorStepCtrl + connector.html, so its wire shape IS the connector
    # envelope. The normalizer defaults `connector: cyops_utilities` (one of
    # 55 utility ops) and falls through to `_resolve_connector_args`; reuses
    # the P3 ConnectorArgs model. Read = sugar-not-recovered (a pulled
    # Utilities step round-trips as `connector`, like stop/end/delete_record).
    "utilities": StepCoverage(
        typed=True, schema=True, read=READ_SUGAR_NOT_RECOVERED, priority=PRI_DONE,
        note="P4 DONE: CyopsUtilices palette alias. Connector-family (routes "
             "through ConnectorStepCtrl + connector.html); defaults "
             "connector:cyops_utilities, falls through to _resolve_connector_args, "
             "reuses the P3 ConnectorArgs envelope model. The 55 utility ops are "
             "the live catalog (fsrpb find op cyops_utilities). Read is "
             "sugar-not-recovered (Connectors last-wins -> connector), matching "
             "the stop/end/delete_record contract."),
    # --- triggers: the 6 ways a playbook starts (start step must be one) ---
    # `start` covers TWO of the 6: Manual (start+module -> cybersponse.action)
    # and Referenced (plain start -> cybersponse.abstract_trigger). These are
    # the two MOST COMMON triggers and are UNMODELED -- the biggest trigger
    # gap. record_action validates the Manual variant's scalars but is keyed
    # under "record_action", not "start", so `start` itself has no model.
    "start": StepCoverage(
        typed=True, schema=True, read=READ_MINIMIFIED, priority=PRI_MED,
        note="TRIGGER: Manual + Referenced (2 of 6 start variants). P1 DONE: "
             "RecordActionArgs registered under `start` (Manual scalars validated "
             "via the record_action call site; plain Referenced form validates "
             "clean -- all-Optional). Schema now introspectable. Residual: the "
             "schema doesn't model the module-presence discriminator (Manual vs "
             "Referenced) -- a discriminated union would add precision but low "
             "value since the Referenced variant takes no friendly scalars."),
    # --- action/notify steps (P5 DONE: envelope-schema typed) ---
    "send_email": StepCoverage(
        typed=True, schema=True, read=READ_PASS_THROUGH, priority=PRI_MED,
        note="CONNECTOR-FAMILY (SendMail, dispatcher /tasks/connector). P5 DONE: "
             "SendEmailArgs validation-only envelope (to/cc/bcc list-or-str, "
             "subject str, content=body rename, from_str=from rename). The "
             "normalizer owns the body->content / from->from_str transform + "
             "from_str default (SMTP default-from substituted at runtime). "
             "Residual wart: friendly `send_email` maps to the dead SendEmail "
             "label (occ=0), not the live SendMail (occ=22) -- latent "
             "forward-map issue, separate from this model. Params are the smtp "
             "connector's send_email_new op (catalog layer, stays Any)."),
    "create_task": StepCoverage(
        typed=True, schema=True, read=READ_PASS_THROUGH, priority=PRI_MED,
        note="ManualTask. P5 DONE: CreateTaskArgs validation-only envelope "
             "(collection str, resource Any). The normalizer owns the "
             "collection=tasks default + resource={} default (the editor "
             "hardcodes collection: tasks, bundle line 37569)."),
    "set_api_keys": StepCoverage(
        typed=True, schema=True, read=READ_PASS_THROUGH, priority=PRI_LOW,
        note="SetAPIKeys. P5 DONE: SetApiKeysArgs validation-only envelope "
             "(public_key/private_key, both jinja-capable str). No compile-time "
             "transform (controller validates UI state). Low frequency -- the "
             "win is schema introspection, not correction."),
    "approval": StepCoverage(
        typed=True, schema=True, read=READ_PASS_THROUGH, priority=PRI_LOW,
        note="Approval. P5 DONE: ApprovalArgs validation-only envelope "
             "(collection str, resource Any, timeout number, response_mapping "
             "Any). The normalizer owns the collection=approvals default + "
             "resource={} default (editor hardcodes collection: approvals, "
             "bundle line 37501). Legacy `approvers` accepted (not synthesized)."),
    "api_endpoint": StepCoverage(
        typed=True, schema=True, read=READ_MINIMIFIED, priority=PRI_DONE,
        note="TRIGGER: Custom API Endpoint (1 of 6, cybersponse.api_call). "
             "P1 DONE: ApiEndpointArgs validation-only model (route:str, "
             "authentication_methods:list). Token-based auth default + "
             "trigger-infra setdefaults stay imperative. NOT a drag-in step -- "
             "it is the 6th start variant. Schema now introspectable. G10 "
             "Tier-2 DONE: decompiler minimification drops the 5 re-derived "
             "trigger-infra defaults (authentication_methods=[''], step_variables "
             "default, triggerOnSource=True, triggerOnReplicate=False, "
             "__triggerLimit=True) so a pulled step surfaces just route (+ "
             "non-default auth); recompile re-adds them via the setdefaults."),
    "workflow_reference": StepCoverage(
        typed=True, schema=True, read=READ_PASS_THROUGH, priority=PRI_MED,
        note="calls another playbook (WorkflowReference). P5 DONE: "
             "WorkflowReferenceArgs validation-only envelope (target str -- "
             "local playbook name, workflowReference str -- cross-collection "
             "IRI, arguments Any). The resolver owns the required-target "
             "MISSING_FIELD check + target name-lookup + parameter validation "
             "against the target playbook's parameters; target/workflowReference "
             "declared Optional so pydantic doesn't shadow that. Cross-tenant "
             "sibling = trigger_tenant_playbook."),
    # --- trigger_tenant_playbook: cross-tenant call (RemotePlaybookReference) ---
    # Owns a distinct script handler (/wf/workflow/tasks/remote_workflow_reference),
    # so a real step type -- not a connector alias. The local sibling is
    # `workflow_reference` (WorkflowReference); Remote requires a `workflowReference:`
    # IRI (the local-name `target:` form can't cross tenants) + pickFromTenant.
    # Decompiles cleanly (1:1 canonical, no Connectors-style collision).
    "trigger_tenant_playbook": StepCoverage(
        typed=True, schema=True, read=READ_PASS_THROUGH, priority=PRI_DONE,
        note="P4 DONE: RemotePlaybookReference (Trigger Tenant Playbook). Own "
        "script handler (/wf/workflow/tasks/remote_workflow_reference); "
        "validation-only TriggerTenantPlaybookArgs envelope grounded in the "
        "live step_handlers signature: remote_workflow_reference(playbook_alias_id, "
        "tenant_id=None, *args, **kwargs). Resolver requires playbook_alias_id "
        "(not target/workflowReference -- cross-tenant uses a playbook alias, "
        "not a same-collection IRI); arg_validator independently enforces it "
        "against the live signature. extra='allow' rides the **kwargs envelope."),
    "ingest_bulk_feed": StepCoverage(
        typed=True, schema=True, read=READ_PASS_THROUGH, priority=PRI_MED,
        note="IngestBulkFeed -- bulk-ingest sibling of Create Record (inherits "
             "InsertDataCtrl; POSTs to /api/ingest-feeds/<module>, deletes "
             "operation/fieldOperation = implicitly upsert). P5 DONE: "
             "IngestBulkFeedArgs validation-only envelope (collection str, "
             "resource Any, for_each Any). DESIGN SPLIT (3-way): the typed "
             "model owns the envelope schema (the discover win) + scalar "
             "validation; the LINT layer (rulesets/_shared.py) owns the "
             "collection-prefix + no-operation checks; the EMITTER "
             "(_clean_step_arguments) owns the for_each loop-mode normalization "
             "(parallel/batch_size pruning, batch_size default). Validation-only "
             "here never mutates, so it cannot collide with either. Niche but a "
             "distinct authoring pattern (bulk feed ingest; occ=10)."),
    # --- one-way authoring sugars (compile to Connectors) ---
    "stop": StepCoverage(
        typed=False, schema=False, read=READ_SUGAR_NOT_RECOVERED, priority=PRI_LOW,
        note="compiles to cyops_utilities no_op; round-trips as `connector`. "
             "No distinct canonical to recover (by design)."),
    "end": StepCoverage(
        typed=False, schema=False, read=READ_SUGAR_NOT_RECOVERED, priority=PRI_LOW,
        note="same as stop."),
}


def coverage() -> dict[str, StepCoverage]:
    """The full matrix (defensive copy)."""
    return dict(COVERAGE)


# --- The editor palette axis ---
#
# The FortiSOAR playbook editor exposes a fixed palette a user drags onto the
# canvas (grouped Core / Logic / Execute / References / Email / Authentication).
# This is the real "what can an agent create" surface -- stronger ground truth
# than our authoring-friendly SHORT_TYPE_TO_FSR, which also carries triggers
# (start*) and one-way sugars (stop/end/delete_record) that are never dragged in.
#
# Grounded in the `step_types` table: `label` = the editor string, `script` =
# the FSR task handler. Two palette entries are NOT step types (no script):
#   - Evaluate          -> RunScript        (legacy "Run Utility Functions")
#   - Add Reference Block -> ReferenceBlock  (a reusable-block reference, not a step)
# They are excluded from EDITOR_PALETTE (which is authorable step types only)
# and tracked in NON_STEP_TYPES so the exclusion is a documented decision.
#
# Four palette entries are the CONNECTOR FAMILY -- first-class UI options that
# all route through the same connector dispatcher (`script:
# /wf/workflow/tasks/connector`): Connector, Code Snippet, Utilities, Send
# Email. They each carry a `connector`+`operation`+`params` envelope under the
# hood; the friendly surface (`connector`/`code_snippet`/`send_email`) hides it.
# Utilities (`CyopsUtilites`) is the one family member with NO direct friendly
# surface -- only `stop`/`end`/`delete_record` sugars compile to a Connectors
# step, none to CyopsUtilites directly.
EDITOR_PALETTE: dict[str, str] = {
    # Core -- record & data operations
    "Create Record": "InsertData",
    "Update Record": "UpdateRecord",
    "Find Records": "FindRecords",
    "Ingest Bulk Feed": "IngestBulkFeed",
    "Set Variable": "SetVariable",
    # Logic -- branching, pauses, human checkpoints
    "Decision": "Decision",
    "Wait": "Delay",
    "Approval": "Approval",
    "Manual Task": "ManualTask",
    "Manual Input": "ManualInput",
    # Execute -- run something / automation (the connector family + code)
    "Connector": "Connectors",
    "Utilities": "CyopsUtilites",
    "Code Snippet": "CodeSnippet",
    # References -- reusable / cross-playbook
    "Reference a Playbook": "WorkflowReference",
    "Trigger Tenant Playbook": "RemotePlaybookReference",
    # Email / Authentication. "Send Email" -> SendMail (the LIVE canonical,
    # occ=22, connector-dispatcher); SendEmail is a dead duplicate label (occ=0).
    "Send Email": "SendMail",
    "Set API Keys": "SetAPIKeys",
}

# Editor palette entries that are NOT step types (no `script` handler) -- kept
# out of EDITOR_PALETTE deliberately. If one ever gains a script (becomes a real
# step type), move it into EDITOR_PALETTE and add a coverage decision.
NON_STEP_TYPES: dict[str, str] = {
    "Evaluate": "RunScript",
    "Add Reference Block": "ReferenceBlock",
}

# The connector family: palette entries that all route through the connector
# dispatcher (`script: /wf/workflow/tasks/connector`). First-class UI options,
# but really a connector step (connector+operation+params envelope) under the
# hood. Grounded in the step_types `script` column.
CONNECTOR_FAMILY: frozenset[str] = frozenset({
    "Connectors",        # "Connector"
    "CodeSnippet",       # "Code Snippet"
    "CyopsUtilites",     # "Utilities"
    "SendMail",          # "Send Email" (the LIVE canonical; SendEmail is a
                         #   dead/legacy duplicate label, occ=0 -- see below)
})

# Canonical -> the friendly short type that covers it (None = no friendly
# surface; the agent cannot author this editor type in YAML). Derived from
# SHORT_TYPE_TO_FSR plus the action-trigger overlay (start+module -> action).
_CANONICAL_TO_FRIENDLY: dict[str, str | None] = {}


def _build_canonical_to_friendly() -> None:
    from fsr_playbooks.compiler.resolver import SHORT_TYPE_TO_FSR
    # Last-wins mirrors the decompiler's own _FSR_TO_SHORT comprehension; the
    # Connectors collision (connector/stop/end/delete_record) resolves to
    # `connector`, which is the right "is there a friendly surface" answer.
    for friendly, canonical in SHORT_TYPE_TO_FSR.items():
        _CANONICAL_TO_FRIENDLY[canonical] = friendly
    # start+module -> cybersponse.action is covered by `start` (decompiler
    # overlay agrees), so action counts as covered.
    _CANONICAL_TO_FRIENDLY.setdefault("cybersponse.action", "start")
    # The live "Send Email" canonical is SendMail (occ=22, connector-dispatcher).
    # `send_email` maps to SendEmail (occ=0, a dead duplicate label) in
    # SHORT_TYPE_TO_FSR -- a latent forward-map wart. For the *coverage* question
    # ("is Send Email authorable from YAML?"), both labels are covered by
    # `send_email`; flag the wart separately, don't let it read as a palette gap.
    _CANONICAL_TO_FRIENDLY.setdefault("SendMail", "send_email")
    # The editor palette's "Utilities" entry is canonical `CyopsUtilices` (the
    # widget name), but `utilities` compiles to `Connectors` (it routes through
    # ConnectorStepCtrl + connector.html, so its wire shape IS the connector
    # envelope -- a connector-family alias, the same way stop/end/delete_record
    # are). For the *coverage* question ("is Utilities authorable from YAML?"),
    # the palette canonical is covered by `utilities`; don't let the
    # widget-name vs compile-canonical split read as a palette gap.
    _CANONICAL_TO_FRIENDLY.setdefault("CyopsUtilites", "utilities")


def friendly_for_editor(label: str) -> str | None:
    """The friendly short type covering an editor palette entry, or None.

    None means: this editor step type has NO friendly YAML surface — an agent
    cannot create it through the YAML language at all. That is a palette gap.
    """
    if not _CANONICAL_TO_FRIENDLY:
        _build_canonical_to_friendly()
    canonical = EDITOR_PALETTE.get(label)
    if canonical is None:
        return None
    return _CANONICAL_TO_FRIENDLY.get(canonical)


def palette_gaps() -> list[tuple[str, str]]:
    """Editor palette entries with no friendly YAML surface, sorted.

    Each tuple is (editor_label, canonical). These are step types an agent can
    create in the UI but cannot author in YAML — the highest-leverage north-star
    gaps, because they mean a whole class of playbook is unreachable from the
    friendly surface and must be hand-edited as raw canonical JSON.
    """
    if not _CANONICAL_TO_FRIENDLY:
        _build_canonical_to_friendly()
    gaps = []
    for label, canonical in sorted(EDITOR_PALETTE.items()):
        if _CANONICAL_TO_FRIENDLY.get(canonical) is None:
            gaps.append((label, canonical))
    return gaps


# --- The trigger axis: the 6 ways a playbook starts ---
#
# A playbook's start step must be exactly one of these 6 trigger variants
# (the editor's trigger picker). `start` (friendly) covers TWO variants:
# Manual (start + module) and Referenced (plain start). The other 4 each map
# to their own friendly type. Grounded in the `step_types` table labels.
TRIGGER_VARIANTS: list[tuple[str, str, str]] = [
    # (trigger_name, canonical, friendly_type)
    ("Manual", "cybersponse.action", "start"),
    ("On Create", "cybersponse.post_create", "start_on_create"),
    ("On Update", "cybersponse.post_update", "start_on_update"),
    ("On Delete", "cybersponse.post_delete", "start_on_delete"),
    ("Referenced", "cybersponse.abstract_trigger", "start"),
    ("Custom API Endpoint", "cybersponse.api_call", "api_endpoint"),
]


def trigger_coverage() -> list[tuple[str, str, bool]]:
    """Per-trigger-variant: (name, friendly_type, typed?).

    A playbook start step must be one of 6 variants; this reports which have a
    typed model. Untyped variants are trigger-family gaps (the start step is
    the first thing an agent authors, so an unmodeled trigger is a front-door
    gap in the assistant).
    """
    out = []
    for name, _canon, friendly in TRIGGER_VARIANTS:
        c = COVERAGE.get(friendly)
        out.append((name, friendly, bool(c and c.typed)))
    return out


def trigger_gaps() -> list[str]:
    """Trigger variants whose friendly type is unmodeled, sorted."""
    return sorted(name for name, _f, typed in trigger_coverage() if not typed)


def prioritized(priority: str) -> list[str]:
    """Step types at a given priority level, sorted."""
    return sorted(t for t, c in COVERAGE.items() if c.priority == priority)


def render_matrix() -> str:
    """A fixed-width table of the matrix — the north-star dashboard."""
    rows = [("step_type", "typed", "schema", "read", "pri", "note")]
    for t in sorted(COVERAGE):
        c = COVERAGE[t]
        rows.append((t, "Y" if c.typed else ".", "Y" if c.schema else ".",
                     c.read, c.priority, c.note))
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    lines = []
    for r in rows:
        line = "  ".join(c.ljust(widths[i]) for i, c in enumerate(r))
        lines.append(line)
    # summarize
    n = len(COVERAGE)
    nt = sum(1 for c in COVERAGE.values() if c.typed)
    ns = sum(1 for c in COVERAGE.values() if c.schema)
    nm = sum(1 for c in COVERAGE.values() if c.read == READ_MINIMIFIED)
    lines.append("")
    lines.append(f"{n} step types | {nt}/{n} typed | {ns}/{n} schema(discover) "
                 f"| {nm}/{n} decompile-minimified")
    lines.append(f"priority: high={len(prioritized(PRI_HIGH))} "
                 f"med={len(prioritized(PRI_MED))} "
                 f"low={len(prioritized(PRI_LOW))} "
                 f"done={len(prioritized(PRI_DONE))}")
    return "\n".join(lines)
